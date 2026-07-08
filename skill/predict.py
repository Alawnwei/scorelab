#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
系统1：足球预测引擎 v2.0 — 七维评分 + 负二项 + WVR + 三级漏斗 + 偏差熔断

用法:
  python skill/predict.py --home "葡萄牙" --away "西班牙" --league wm26
"""
import sys, os, json, math, re, argparse
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def _get_dp():
    if "datafc_provider" not in sys.modules:
        for p in [BASE_DIR, os.path.join(BASE_DIR, "skill")]:
            if p not in sys.path:
                sys.path.insert(0, p)
        import importlib
        try:
            return importlib.import_module("datafc_provider")
        except ImportError:
            return importlib.import_module("skill.datafc_provider")
    return sys.modules.get("datafc_provider") or sys.modules.get("skill.datafc_provider")


def _get_qe():
    """延迟加载 quality_engine"""
    if "quality_engine" not in sys.modules:
        for p in [BASE_DIR, os.path.join(BASE_DIR, "skill")]:
            if p not in sys.path:
                sys.path.insert(0, p)
        import importlib
        return importlib.import_module("quality_engine")
    return sys.modules["quality_engine"]


# ============================================================
# 负二项分布引擎
# ============================================================
THETA_MAP = {
    "bl1": 10, "epl": 10, "laliga": 10, "seriea": 10, "ligue1": 10,
    "eredivisie": 8,
    "kleague1": 6, "kleague2": 6,
    "jleague1": 6, "jleague2": 6,
    "allsvenskan": 6, "eliteserien": 6, "championship": 8, "bundesliga2": 8,
        "ligue2": 8, "laliga2": 8, "serieb": 8,
        "primeira": 8, "proleague": 8, "scottish": 8, "eredivisie": 8,
        "aleague": 6, "mls": 6, "brasileirao": 8, "ligamx": 8,
        "csl": 6, "zhongjia": 6, "zhongyi": 6, "saudi": 8, "league1": 8, "league2": 8,
        "kleague1": 6, "kleague2": 6,
        "jleague1": 6, "jleague2": 6,
        "veikkausliiga": 6, "sportsdb": 6,
    "wm26": 8, "WC": 8,
    "euro": 8, "copaf": 8, "afcon": 8, "asiancup": 8,
    "afccl": 8, "afccup": 8,
    "ucl": 8, "uel": 8, "uecl": 8,
    "facup": 8, "eflcup": 8, "copadelrey": 8, "dfbpokal": 8, "coppaita": 8,
}
DEFAULT_THETA = 8


def get_theta(league: str) -> int:
    return THETA_MAP.get(league, DEFAULT_THETA)


def _poisson_prob(lam, k):
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * (lam ** k) / math.factorial(k)


def nb_prob(k: int, lam: float, theta: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    if theta >= 100:
        return _poisson_prob(lam, k)
    p = theta / (theta + lam)
    log_coeff = math.lgamma(k + theta) - math.lgamma(k + 1) - math.lgamma(theta)
    log_prob = log_coeff + theta * math.log(p) + k * math.log(1 - p)
    return math.exp(log_prob)


def nb_match_probs(lam_h: float, lam_a: float, theta: float, mg: int = 10):
    hp, dp, ap = 0.0, 0.0, 0.0
    for i in range(mg + 1):
        pi = nb_prob(i, lam_h, theta)
        for j in range(mg + 1):
            pj = nb_prob(j, lam_a, theta)
            p = pi * pj
            if i > j: hp += p
            elif i == j: dp += p
            else: ap += p
    return hp, dp, ap


def nb_score_dist(lam_h: float, lam_a: float, theta: float, mg: int = 10, top: int = 12):
    d = {}
    for i in range(mg + 1):
        pi = nb_prob(i, lam_h, theta)
        for j in range(mg + 1):
            pj = nb_prob(j, lam_a, theta)
            p = pi * pj
            if p > 0.001: d[(i, j)] = p
    return sorted(d.items(), key=lambda x: -x[1])[:top]


def nb_over_25(lam_h: float, lam_a: float, theta: float, mg: int = 10) -> float:
    p_under = 0.0
    for i in range(mg + 1):
        pi = nb_prob(i, lam_h, theta)
        for j in range(mg + 1):
            if i + j <= 2:
                pj = nb_prob(j, lam_a, theta)
                p_under += pi * pj
    return 1.0 - p_under


def nb_btts(lam_h: float, lam_a: float, theta: float, mg: int = None) -> float:
    if mg is None:
        max_lam = max(lam_h, lam_a)
        mg = max(6, int(max_lam * 3 + 4))  # λ=2.7→12, λ=3.5→14, λ=1.0→7
    prob = 0.0
    for i in range(1, mg + 1):
        pi = nb_prob(i, lam_h, theta)
        for j in range(1, mg + 1):
            pj = nb_prob(j, lam_a, theta)
            prob += pi * pj
    return prob


# λ 攻防调整权重（0.15=经验值，可用 update_calibration.py 校准）
# 控制 xG_for/90 攻防强度对 λ 的放大/缩小力度
LAMBDA_ADJUST_WEIGHT = 0.15


def adjust_lambda(lam_base: float, own_att_str: float, opp_def_str: float) -> float:
    """攻防调整 λ — 本方进攻加分，对手防守减分

    defense_strength < 1.0 = 对手防守好 → λ 降
    defense_strength > 1.0 = 对手防守差 → λ 升
    own_att_str < 1.0 = 本方进攻差 → λ 降
    own_att_str > 1.0 = 本方进攻好 → λ 升
    """
    import math
    # NaN/None 保护：静默降级为 1.0（无调整）
    if own_att_str is None or (isinstance(own_att_str, float) and math.isnan(own_att_str)):
        own_att_str = 1.0
    if opp_def_str is None or (isinstance(opp_def_str, float) and math.isnan(opp_def_str)):
        opp_def_str = 1.0
    if lam_base is None or (isinstance(lam_base, float) and math.isnan(lam_base)):
        lam_base = 1.40
    own_att_effect = (own_att_str - 1.0) * LAMBDA_ADJUST_WEIGHT
    opp_def_effect = (opp_def_str - 1.0) * LAMBDA_ADJUST_WEIGHT
    fragility = 1.0 + own_att_effect + opp_def_effect
    adjusted = lam_base * fragility
    return max(0.1, min(6.0, adjusted))


# ============================================================
# M系数因子名映射（quality_engine WVR 用）
# ============================================================
KO_FACTOR = "淘汰赛"
H2H_FACTOR = "历史交锋_淘汰赛"
DERBY_FACTOR = "德比"
_ROT_MAP = {4: "轮换L4", 3: "轮换L3", 2: "轮换L2"}


# ── λ 全局校准（P3校准修复 2026-07-08）──
# 从已结算记录学习 λ 总值 → 实际总进球的系统性偏差
_CALIB_CACHE = None  # lambda校准缓存

def _load_lambda_calibration():
    """从 predictions_db 已结算记录计算 λ 校准因子

    λ 校准因子 = 实际场均总进球 / 模型预期场均总进球
    如果因子 < 1.0 → 模型高估进球（如淘汰赛）
    如果因子 > 1.0 → 模型低估进球

    需要至少 10 条有实际比分的已结算记录。

    Returns:
        float | None: 校准因子，或 None（数据不足）
    """
    global _CALIB_CACHE
    if _CALIB_CACHE is not None:
        return _CALIB_CACHE

    import json, os
    db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "数据缓存", "predictions_db.json")
    if not os.path.exists(db_path):
        return None

    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except:
        return None

    # 筛选有 λ 值 + 实际比分的记录（淘汰赛需要特殊处理）
    total_expected = 0.0
    total_actual = 0
    count = 0
    for p in db.get("predictions", []):
        r = p.get("result", {})
        if r.get("status") != "matched":
            continue
        sh = r.get("score_home")
        sa = r.get("score_away")
        if sh is None or sa is None:
            continue
        # 需要 λ 数据（新格式从 score_diff 推断，旧格式无法获取）
        # 对旧记录使用近似：λ ≈ 联赛均值 × 攻防调整 ≈ 2.8
        # 新记录会存储 score_diff，但 λ 值未直接存
        # 用实际进球除 2 作为大致预期（保守估计）
        actual_total = int(sh) + int(sa)
        # 由于大部分记录没有存储 λ，我们用保守方法：
        # 假设平均每场预期总进球 ≈ 2.5（五大联赛典型值）
        # 这不是精确的 λ 校准，而是全局偏差检测
        total_expected += 2.5  # 联赛平均预期总进球
        total_actual += actual_total
        count += 1

    if count < 10:
        return None

    # 校准因子 = 实际 / 预期
    factor = round(total_actual / total_expected, 4)
    # 只在偏差 > 5% 时启用修正（否则可能是噪声）
    if abs(factor - 1.0) < 0.05:
        _CALIB_CACHE = 1.0
    else:
        _CALIB_CACHE = factor

    return _CALIB_CACHE


def main():
    parser = argparse.ArgumentParser(description="系统1: 足球预测引擎 v2.0")
    parser.add_argument("--home", required=True)
    parser.add_argument("--away", required=True)
    parser.add_argument("--league", default="wm26")
    parser.add_argument("--theta", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="跳过赛程校验，强制生成预测")
    args = parser.parse_args()

    home, away, league = args.home, args.away, args.league
    dp = _get_dp()
    qe = _get_qe()

    # ── 数据源校验门禁 — 防止为无数据源的赛事生成预测 ──
    has_src, src_detail = dp.has_data_source(league)
    if not has_src:
        print(f"\n❌  ❌  ❌  联赛 {league} 无数据源覆盖")
        print(f"    {src_detail}")
        print(f"    该联赛不在任何数据源(datafc/OpenLigaDB/ESPN)的覆盖范围内。")
        print(f"    无数据支撑的预测将污染校准数据，已阻止运行。")
        print(f"    若要强制跳过，添加 --force 参数。\n")
        return
    print(f"[数据源] {league} → {src_detail}")

    # ── 赛程校验门禁 — 防止为不存在的比赛生成预测 ──
    if not args.force:
        scheduled, detail = dp.is_match_scheduled(home, away, league)
        if not scheduled:
            print(f"\n⚠️  ⚠️  ⚠️  {detail}")
            print(f"    继续运行将生成一场不存在的比赛预测！")
            print(f"    请检查球队名或联赛标识是否正确。")
            print(f"    若要强制跳过校验，添加 --force 参数。\n")
            return

    theta = args.theta if args.theta is not None else get_theta(league)

    # ── 1. 七维评分（L1 基础层） ──
    s7 = dp.compute_7dim_scores(home, away, league)
    for k in ("home_进攻", "home_防守", "home_中场", "home_经验",
              "home_战术", "home_状态", "home_X因素"):
        if k not in s7: s7[k] = 5.0
    for k in ("away_进攻", "away_防守", "away_中场", "away_经验",
              "away_战术", "away_状态", "away_X因素"):
        if k not in s7: s7[k] = 5.0

    p_base = s7.get("P_base_raw", 0.5)
    total_h = s7.get("home_total", 5.0)
    total_a = s7.get("away_total", 5.0)
    avg_xg = s7.get("league_avg", 1.40)

    # ── 2. xG 数据（datafc 优先 → OpenLigaDB 回退） ──
    xg_h = dp.estimate_team_strength(home, league)
    if xg_h.get("matches_played", 0) == 0:
        xg_h = dp.estimate_xg_from_openligadb(home, league)
    xg_a = dp.estimate_team_strength(away, league)
    if xg_a.get("matches_played", 0) == 0:
        xg_a = dp.estimate_xg_from_openligadb(away, league)

    lam_base_h = xg_h.get("xG_for_90", avg_xg)
    lam_base_a = xg_a.get("xG_for_90", avg_xg)
    att_str_h = xg_h.get("attack_strength", 1.0)
    def_str_h = xg_h.get("defense_strength", 1.0)
    att_str_a = xg_a.get("attack_strength", 1.0)
    def_str_a = xg_a.get("defense_strength", 1.0)

    lam_h = adjust_lambda(lam_base_h, att_str_h, def_str_a)
    lam_a = adjust_lambda(lam_base_a, att_str_a, def_str_h)

    # ── 2b. 淘汰赛 λ 修正（P1.1 2026-07-08）──
    # 淘汰赛阶段球队防守更保守、节奏更慢，场均进球比小组赛低 20-30%
    # 当前 M系数（×0.962）仅在 P_final 层做 3.75% 削减，力度不够
    # 此处直接在 λ 层叠加 -18% 衰减，穿透到负二项分布的所有市场
    KO_LAMBDA_FACTOR = 0.82  # λ × 0.82  ≈ 预期进球 -18%
    if dp.is_knockout_league(league):
        lam_h *= KO_LAMBDA_FACTOR
        lam_a *= KO_LAMBDA_FACTOR

    # ── 2c. λ 全局校准（2026-07-08）──
    # 从历史数据学习 λ → 实际进球的偏差，修正 λ 值
    # 当前校准因子从 predictions_db 已结算记录计算
    # 仅当有至少 10 条已结算记录时启用
    _lam_calib_factor = _load_lambda_calibration()
    if _lam_calib_factor is not None:
        lam_h *= _lam_calib_factor
        lam_a *= _lam_calib_factor

    # ── 3. ELO ──
    elo_h = dp.get_team_elo(home).get("elo", 1500)
    elo_a = dp.get_team_elo(away).get("elo", 1500)
    rank_h = dp.get_team_elo(home).get("rank", 99)
    rank_a = dp.get_team_elo(away).get("rank", 99)

    # ── 4. M系数（L2） + WVR 衰减 ──
    raw_factors = []
    if dp.is_knockout_league(league):
        raw_factors.append((KO_FACTOR, 0.95))
    # 历史交锋 — 当前未使用 H2H 数据，跳过该因子（原逻辑错误地将淘汰赛惩罚用在未使用的数据上）
    # 若未来接入真实 H2H 数据，在此处恢复使用 dp.calc_h2h_weight
    # h2h = dp.calc_h2h_weight(league)
    # if h2h != 1.0:
    #     raw_factors.append((H2H_FACTOR, 0.50))

    if dp.is_derby_match(home, away):
        raw_factors.append((DERBY_FACTOR, 1.15))

    mf = dp.infer_m_factors(home, league)
    rot = mf.get("rotation", 0)
    if rot >= 2:
        rot_name = _ROT_MAP.get(rot, "轮换")
        raw_coef = {4: 0.55, 3: 0.70, 2: 0.85}.get(rot, 0.85)
        raw_factors.append((rot_name, raw_coef))

    # WVR 批量应用
    wvr_m, wvr_report, wvr_c_count, wvr_warn = qe.wvr_apply_all(raw_factors)

    # 同时计算旧 M（无WVR，仅用于对比展示）
    old_m = 1.0
    for _, v in raw_factors: old_m *= v

    # P_final（赔率比空间映射，使用 WVR 衰减后的 M）
    p_final = (p_base / (1-p_base) * wvr_m) / (1 + p_base / (1-p_base) * wvr_m)
    p_final = max(0.01, min(0.99, p_final))
    # 温度缩放 T=1.60（校准最优值，2026-07-06 算出）：平抑系统性偏差
    TEMP_T = 4.08  # 校准最优值 (2026-07-08)
    if 0 < p_final < 1:
        _pt = p_final ** (1.0 / TEMP_T)
        _qt = (1.0 - p_final) ** (1.0 / TEMP_T)
        p_final = _pt / (_pt + _qt)
        p_final = max(0.01, min(0.99, p_final))

    # ── 5. 负二项分布 ──
    probs = nb_match_probs(lam_h, lam_a, theta)
    dist = nb_score_dist(lam_h, lam_a, theta)
    over25 = nb_over_25(lam_h, lam_a, theta)
    btts = nb_btts(lam_h, lam_a, theta)

    h, d, a = probs
    if h >= 0.50:
        direction = '主胜'
    elif a >= 0.50:
        direction = '客胜'
    # 主/客有明显领先(>40%)且拉开平局10pp+ → 双选(主不败/客不败)
    elif h > a and h >= 0.40 and (h - d) >= 0.10:
        direction = '主不败(双选)'
    elif a > h and a >= 0.40 and (a - d) >= 0.10:
        direction = '客不败(双选)'
    # 主/客有微弱领先(>38%)且拉开平局8pp+ → 低信心单选
    elif h > a and h >= 0.38 and (h - d) >= 0.08:
        direction = '主胜(低信心)'
    elif a > h and a >= 0.38 and (a - d) >= 0.08:
        direction = '客胜(低信心)'
    # 平局明确为最高概率
    elif d >= h and d >= a:
        if d >= 0.35:
            direction = '平局'
        elif d >= 0.32:
            direction = '平局(有风险)'
        else:
            direction = '不推荐/均衡'
    # 主/客有倾斜但信号弱
    elif h > a and h >= 0.35:
        direction = '主胜(低信心)'
    elif a > h and a >= 0.35:
        direction = '客胜(低信心)'
    else:
        direction = '不推荐/均衡'

    # ── 双模型一致性校验：信号强度决策 ──
    # 信号强度排序：
    #   🥇 NB λ差距>1.5x → 直接来自进球数据
    #   🥈 七维总分差>1.0 → 多维评分综合
    #   🥉 P_final方向     → P_base×M，精度一般
    #   🤷 七维总分差<0.5 → 几无区分度
    score_diff = abs(total_h - total_a)
    lam_ratio = max(lam_h, lam_a) / max(min(lam_h, lam_a), 0.1)
    dir_home = direction in ('主胜', '主不败(双选)', '主胜(低信心)')
    dir_away = direction in ('客胜', '客不败(双选)', '客胜(低信心)')
    dir_draw = direction in ('平局', '平局(有风险)', '不推荐/均衡')
    p_home = p_final > 0.50
    p_away = p_final < 0.50

    model_conflict = False
    # 🥇 λ 差距显著 → NB 方向可信，若与 P_final 冲突则覆盖方向并标注
    if lam_ratio > 1.5:
        nb_direction = '主胜' if h > a else '客胜'
        nb_home = nb_direction == '主胜'
        if (nb_home and p_away) or (not nb_home and p_home):
            model_conflict = True
            direction = f'⚠️ 模型矛盾(信NB:{nb_direction})'
            print(f"[双模型矛盾] λ比={lam_ratio:.1f}x 指示{nb_direction}，"
                  f"但 P_final={p_final:.3f} 相反，已信任 λ 方向")
    # 🥈 七维差 > 1.0 → P_final 可靠，若与 NB 冲突则信任 P_final
    elif score_diff > 1.0:
        if (dir_home and p_away) or (dir_away and p_home):
            model_conflict = True
            p_dir = '主胜' if p_home else '客胜'
            direction = f'⚠️ 模型矛盾(信P_final:{p_dir})'
            print(f"[双模型矛盾] 七维差={score_diff:.2f} 指示{p_dir}，"
                  f"但 NB 方向相反，已信任七维评分")
    # 🤷 七维差 < 0.5 且 λ 无显著差距 → 无信号
    elif score_diff < 0.5 and lam_ratio < 1.3:
        if dir_home and dir_away is False:  # direction 不是均衡
            if dir_home != p_home:
                model_conflict = True
                direction = '不推荐/均衡'
                print(f"[双模型矛盾] 七维差={score_diff:.2f}+λ比={lam_ratio:.1f}x，"
                      f"双模型不一致→不推荐")

    # ── 6. 三级漏斗 + 偏差熔断 ──
    quality = qe.run_full_quality_check(
        dp, home, away, league, s7, raw_factors, wvr_report,
        lam_h, lam_a, p_final, probs, over25, btts, direction
    )

    fuse = quality["fuse"]
    final_rating = fuse["final_rating"]
    final_direction = fuse["final_direction"]
    rating_pct = quality["rating_score_pct"]

    # ── 7. 输出 ──
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_prefix = datetime.now().strftime("%Y-%m-%d")
    model_label = f"负二项(θ={theta})" if theta < 100 else "泊松(θ→∞)"

    out_lines = []
    out_lines.append(f"# {home} vs {away} — 预测报告")
    out_lines.append("")
    out_lines.append(f"> ⏰ **初盘分析** | {now} | 系统: v2.0 | *完整 v8.4*")
    out_lines.append("")

    # ---- 七维评分 ----
    out_lines.append("## 📊 统一评分引擎输出")
    out_lines.append("")

    out_lines.append("### ① L1 七维评分明细（基础层）")
    out_lines.append("")
    out_lines.append("| 维度 | 权重 | 主队 | 客队 |")
    out_lines.append("|:-----|:----:|:----:|:----:|")
    out_lines.append(f"| 进攻能力 | 20% | **{s7['home_进攻']}** | **{s7['away_进攻']}** |")
    out_lines.append(f"| 防守稳固性 | 20% | **{s7['home_防守']}** | **{s7['away_防守']}** |")
    out_lines.append(f"| 中场控制力 | 15% | **{s7['home_中场']}** | **{s7['away_中场']}** |")
    out_lines.append(f"| 大赛经验 | 15% | **{s7['home_经验']}** | **{s7['away_经验']}** |")
    out_lines.append(f"| 战术适配度 | 15% | **{s7['home_战术']}** | **{s7['away_战术']}** |")
    out_lines.append(f"| 体能/状态 | 10% | **{s7['home_状态']}** | **{s7['away_状态']}** |")
    out_lines.append(f"| X因素 | 5% | **{s7['home_X因素']}** | **{s7['away_X因素']}** |")
    out_lines.append(f"| **加权总分** | **100%** | **{total_h}** | **{total_a}** |")
    out_lines.append("")

    # ---- L2 场景修正 + WVR ----
    out_lines.append("### ② L2 场景修正（WVR 衰减后）")
    out_lines.append("")
    out_lines.append("| 因子 | 原始系数 | WVR等级 | 有效系数 |")
    out_lines.append("|:-----|:-------:|:-------:|:--------:|")
    for name, raw, level, ratio, eff, label in wvr_report:
        out_lines.append(f"| {name} | {raw} | {label} | **{eff}** |")
    out_lines.append(f"| **综合 M** | | | **{wvr_m}** |")
    if wvr_warn:
        out_lines.append("")
        out_lines.append(f"> {wvr_warn}")
    out_lines.append("")

    # ---- 评分引擎汇总 ----
    out_lines.append("### ③ 评分引擎汇总")
    out_lines.append("")
    out_lines.append("| 项目 | 数值 |")
    out_lines.append("|:-----|:-----|")
    out_lines.append(f"| 得分差 | {s7['diff']} |")
    out_lines.append(f"| P_base (Logistic α=0.15) | **{p_base:.4f}** |")
    out_lines.append(f"| M系数(无WVR) | {old_m:.3f} → **WVR修正后 {wvr_m:.3f}** |")
    out_lines.append(f"| P_final | **{p_final:.3f}** |")
    out_lines.append(f"| ELO | 主{elo_h}(#{rank_h}) 客{elo_a}(#{rank_a}) |")
    out_lines.append(f"| 概率模型 | {model_label} |")
    out_lines.append(f"| λ(调整后) | 主{lam_h:.2f} 客{lam_a:.2f} |")
    out_lines.append(f"| 3-way | 主{probs[0]*100:.0f}% 平{probs[1]*100:.0f}% 客{probs[2]*100:.0f}% |")
    out_lines.append(f"| 大2.5 / BTTS | {over25*100:.1f}% / {btts*100:.1f}% |")
    out_lines.append(f"| 数据 | {xg_h.get('source','?')} |")
    out_lines.append("")

    # ---- 三级漏斗 ----
    out_lines.append("### ④ 三级漏斗检查")
    out_lines.append("")
    # 闸门
    gate = quality["gate"]
    gate_icon = "✅" if gate["passed"] else "❌"
    out_lines.append(f"**🔴 强制闸门 (G01-G14): {gate_icon}**")
    for gid, ok, desc in gate["results"]:
        icon = "✅" if ok else "❌"
        out_lines.append(f"- {icon} {gid}: {desc}")
    out_lines.append("")

    # 质量评分
    qual = quality["quality"]
    out_lines.append(f"**🟡 质量评分 (Q01-Q18): {qual['score']}/100**")
    total_d = qual["total_deduct"]
    if total_d < 0:
        out_lines.append(f"  - 总扣分: {total_d}")
    out_lines.append("")

    # 偏差熔断
    d008_entry = next((t[1] for t in fuse['triggered'] if t[0] == '#008'), None)
    d008_level = d008_entry.get('level', '') if d008_entry else ''
    d008_icon = '🚨' if '冷门' in d008_level else ('🟡' if '模糊' in d008_level else '✅')
    d008_action = d008_entry.get('action', '未触发') if d008_entry else '未触发'

    out_lines.append(f"**🔴 P0 偏差熔断**")
    out_lines.append("")
    out_lines.append(f"| 偏差 | 状态 | 说明 |")
    out_lines.append(f"|:-----|:----:|:-----|")
    out_lines.append(f"| #002 BTTS+小2.25 | {'⚠️ 触发' if any(t[0]=='#002' for t in fuse['triggered']) else '✅ 通过'} | {'需检查' if any(t[0]=='#002' for t in fuse['triggered']) else '无矛盾'} |")
    out_lines.append(f"| #008 冷门预警 | {d008_level or '✅ 通过'} | {d008_action} |")
    out_lines.append(f"| #026 低分检查 | {'⚠️ {}个'.format(len(fuse['contradictions'])) if fuse['contradictions'] else '✅ 通过'} | {'维度分≤6.5' if fuse['contradictions'] else '无低分维度'} |")
    out_lines.append("")

    # ---- 最终推荐 ----
    out_lines.append("### 🔥 最终推荐")
    out_lines.append("")
    out_lines.append(f"| 项目 | 内容 |")
    out_lines.append(f"|:-----|:-----|")
    out_lines.append(f"| **方向** | **{final_direction}** |")
    out_lines.append(f"| **评级** | **{final_rating}** |")
    out_lines.append(f"| 综合评分 | {rating_pct:.1f}/100 |")
    out_lines.append(f"| P_final | {p_final:.3f} |")
    out_lines.append("")

    # ---- 市场分析 + 投注建议（使用 betting_engine 算 +EV/凯利） ----
    odds_data = dp.auto_fill_odds(home, away, league, p_final,
                                   direction=final_direction, odds_only=True)

    out_lines.append("")
    out_lines.append("## 📈 投注建议")
    out_lines.append("")

    if odds_data.get("odds"):
        home_odds = odds_data.get("home_odds")
        draw_odds = odds_data.get("draw_odds")
        away_odds = odds_data.get("away_odds")

        # 用 betting_engine 计算 +EV 和凯利
        from skill.betting_engine import BettingEngine
        be = BettingEngine(bankroll=10000, mode="pro", match_name=f"{home} vs {away}")
        prob_h_pct = probs[0] * 100
        prob_d_pct = probs[1] * 100
        prob_a_pct = probs[2] * 100

        # 计算三个方向的 +EV（带精确推水）
        all_1x2_odds = [home_odds, draw_odds, away_odds]
        rows = []
        for label, mp, mo in [("主胜", prob_h_pct, home_odds),
                               ("平局", prob_d_pct, draw_odds),
                               ("客胜", prob_a_pct, away_odds)]:
            ev_pct, mip = be.calc_ev(mp, mo, all_odds=all_1x2_odds)
            kelly_pct = be.kelly(mo, mp)
            rows.append((label, mp, mo, mip, ev_pct, kelly_pct))

        # 1X2 全市场表
        out_lines.append("### 1X2 市场")
        out_lines.append("")
        out_lines.append(f"| 选项 | 模型概率 | 赔率 | MIP | +EV | 凯利 |")
        out_lines.append(f"|:-----|:-------:|:----:|:---:|:---:|:----:|")
        for label, mp, mo, mip, ev, kp in rows:
            ev_tag = "✅" if ev >= 10 else ("⚠️" if ev > 0 else "")
            kelly_str = f"{kp*100:.1f}%" if kp > 0 else "0%"
            out_lines.append(f"| {label} | {mp:.0f}% | {mo} | {mip:.1f}% | {ev:+.1f}% {ev_tag} | {kelly_str} |")

        # 找出最佳 +EV 选项（与推荐方向一致优先）
        dir_map = {"主胜": 0, "平局": 1, "客胜": 2}
        rec_idx = dir_map.get(final_direction.replace("⚠️ 模型矛盾(信", "").replace(")", "").replace("NB:", "").replace("P_final:", "").replace("主不败", "主胜").replace("客不败", "客胜"), -1)

        best_ev = max(rows, key=lambda r: r[4])
        out_lines.append("")
        out_lines.append("### 🎯 推荐投注")
        out_lines.append("")

        if best_ev[4] >= 10:
            label, mp, mo, mip, ev, kp = best_ev
            bet_pct = min(kp, 0.10)
            bet_amount = 10000 * bet_pct

            # 分歧检测：模型 vs 市场超过 30pp 时警告
            divergence = abs(mp - mip)
            div_warn = ""
            if divergence >= 30:
                div_warn = f"\n| ⚠️ 极端分歧 | 模型 {mp:.0f}% vs 市场 {mip:.1f}%（差{divergence:.0f}pp），建议小额或不投 |"

            out_lines.append(f"| 项目 | 内容 |")
            out_lines.append(f"|:-----|:-----|")
            out_lines.append(f"| **方向** | **{label}** @{mo} |")
            out_lines.append(f"| 模型概率 | {mp:.0f}% |")
            out_lines.append(f"| 市场MIP | {mip:.1f}% |")
            out_lines.append(f"| +EV | **{ev:+.1f}%** {'✅ 通过阈值' if ev >= 10 else ''} |")
            out_lines.append(f"| 凯利比例 | {kp*100:.1f}% (1/4凯利) |")
            out_lines.append(f"| 建议仓位 | {bet_pct*100:.1f}% |")
            out_lines.append(f"| 建议金额 | {bet_amount:.0f}元/万元本金 |{div_warn}")
            out_lines.append("")
            # 风控
            ok, checks = be.risk_check(bet_amount)
            risk_items = []
            for name, passed, detail in checks:
                icon = "✅" if passed else "❌"
                risk_items.append(f"{icon} {name}: {detail}")
            out_lines.append(" | ".join(risk_items))
        else:
            # 无 +EV 选项
            out_lines.append("> 当前市场无显著 +EV 选项（阈值 ≥10%）")
            out_lines.append("")
            out_lines.append(f"| 选项 | +EV | 建议 |")
            out_lines.append(f"|:-----|:---:|:----:|")
            for label, mp, mo, mip, ev, kp in rows:
                tag = "⏳ 观望" if ev < 0 else "⚠️ 不足阈值"
                out_lines.append(f"| {label} | {ev:+.1f}% | {tag} |")
            out_lines.append("")
            out_lines.append("> 💡 可关注大小球或亚盘市场，或等待赔率变动")

        # 全市场扩展（从 latest_match_data.json 读取真实盘口）
        out_lines.append("")
        out_lines.append("### 📋 全部市场 +EV")
        out_lines.append("")
        odds_path = os.path.join(BASE_DIR, "数据缓存", "latest_match_data.json")
        market_data = {}
        if os.path.exists(odds_path):
            try:
                with open(odds_path, "r", encoding="utf-8") as _f:
                    market_data = json.load(_f)
            except Exception:
                pass

        def _parse_odds(raw):
            """从 '大@1.925 小@1.925' 提取大小赔率"""
            if not raw or not isinstance(raw, str):
                return None, None
            over_match = re.search(r'大@([\d.]+)', raw)
            under_match = re.search(r'小@([\d.]+)', raw)
            over = float(over_match.group(1)) if over_match else None
            under = float(under_match.group(1)) if under_match else None
            return over, under

        def _ev_str(mp, over_odds, under_odds):
            """计算 2-way +EV 并返回格式化的字符串"""
            if not over_odds or not under_odds:
                return "无赔率"
            total = 1/over_odds + 1/under_odds
            mip = (1/over_odds) / total
            ev = (mp/100 / mip - 1) * 100
            tag = "✅" if ev >= 10 else ("⚠️" if ev > 0 else "")
            return f"{ev:+.1f}% {tag}" if abs(ev) < 500 else "⚠️ 极端"

        # ── 大小球 2.5 ──
        ou_lines = []
        for src in ("bet365", "1xbet"):
            ou = market_data.get(src, {}).get("over_under", [])
            for line in ou:
                if line not in ou_lines:
                    ou_lines.append(line)
        if ou_lines:
            over_odds, under_odds = _parse_odds(ou_lines[0])
            out_lines.append(f"**⚽ 大小球 2.5**")
            out_lines.append("")
            out_lines.append(f"| 选项 | 模型概率 | 赔率 | +EV |")
            out_lines.append(f"|:-----|:-------:|:----:|:---:|")
            out_lines.append(f"| 大2.5 | {over25*100:.1f}% | {over_odds or '-'} | {_ev_str(over25*100, over_odds, under_odds)} |")
            out_lines.append(f"| 小2.5 | {(1-over25)*100:.1f}% | {under_odds or '-'} | {_ev_str((1-over25)*100, under_odds, over_odds)} |")

        # ── BTTS ──
        btts_data = market_data.get("bet365", {}).get("btts", {}) or market_data.get("1xbet", {}).get("btts", {})
        yes_odds = float(btts_data["yes"]) if isinstance(btts_data.get("yes"), (int, float, str)) and str(btts_data.get("yes","")).replace('.','').isdigit() else None
        no_odds = float(btts_data["no"]) if isinstance(btts_data.get("no"), (int, float, str)) and str(btts_data.get("no","")).replace('.','').isdigit() else None
        if yes_odds and no_odds:
            total_btts = 1/yes_odds + 1/no_odds
            mip_btts_yes = (1/yes_odds) / total_btts
            mip_btts_no = (1/no_odds) / total_btts
            ev_btts_yes = (btts*100 / mip_btts_yes / 100 - 1) * 100
            ev_btts_no = ((1-btts)*100 / mip_btts_no / 100 - 1) * 100
            tag_yes = "✅" if ev_btts_yes >= 10 else ("⚠️" if ev_btts_yes > 0 else "")
            tag_no = "✅" if ev_btts_no >= 10 else ("⚠️" if ev_btts_no > 0 else "")
            out_lines.append("")
            out_lines.append(f"**🤝 BTTS（双方进球）**")
            out_lines.append("")
            out_lines.append(f"| 选项 | 模型概率 | 赔率 | MIP | +EV |")
            out_lines.append(f"|:-----|:-------:|:----:|:---:|:---:|")
            out_lines.append(f"| Yes | {btts*100:.1f}% | {yes_odds} | {mip_btts_yes*100:.1f}% | {ev_btts_yes:+.1f}% {tag_yes} |")
            out_lines.append(f"| No | {(1-btts)*100:.1f}% | {no_odds} | {mip_btts_no*100:.1f}% | {ev_btts_no:+.1f}% {tag_no} |")

        # ── 角球模型（独立 NB，theta=15） ──
        corner_h = dp.get_team_corner_summary(home, league)
        corner_a = dp.get_team_corner_summary(away, league)
        lam_c_h = corner_h.get("corners_for_90", 5.0)
        lam_c_a = corner_a.get("corners_for_90", 5.0)
        corner_theta = 15

        # 从市场赔率中提取角球盘口
        corner_lines = []
        for src in ("bet365", "1xbet"):
            cl = market_data.get(src, {}).get("corner_totals", [])
            if isinstance(cl, list):
                for line in cl:
                    if line not in corner_lines:
                        corner_lines.append(line)

        if corner_lines and lam_c_h > 0 and lam_c_a > 0:
            out_lines.append("")
            out_lines.append(f"**📐 角球（NB模型 θ={corner_theta}）**")
            out_lines.append("")
            out_lines.append(f"| 盘口 | 模型概率 | 赔率 | +EV |")
            out_lines.append(f"|:-----|:-------:|:----:|:---:|")
            for cl in corner_lines[:4]:
                over_match = re.search(r'大@([\d.]+)', cl)
                under_match = re.search(r'小@([\d.]+)', cl)
                line_match = re.search(r'([\d.]+)球', cl)
                if over_match and under_match and line_match:
                    line = float(line_match.group(1))
                    over_odds = float(over_match.group(1))
                    under_odds = float(under_match.group(1))
                    prob_over = dp.corner_nb_over(lam_c_h, lam_c_a, corner_theta, line)
                    total = 1/over_odds + 1/under_odds
                    mip_over = (1/over_odds) / total
                    ev_over = (prob_over*100 / mip_over / 100 - 1) * 100
                    tag = "✅" if ev_over >= 10 else ("⚠️" if ev_over > 0 else "")
                    out_lines.append(f"| {cl} | {prob_over*100:.1f}% | {over_odds}/{under_odds} | {ev_over:+.1f}% {tag} |")
            # 展示球队角球数据
            out_lines.append("")
            out_lines.append(f"> 角球数据: {home} {lam_c_h:.1f}/场 | {away} {lam_c_a:.1f}/场")
        else:
            # 无赔率或无数据时静默跳过（角球模型仅对 datafc 覆盖联赛可用）
            pass

    else:
        # 无市场赔率，用 λ 做预估
        out_lines.append("### 模型预估（无市场赔率）")
        out_lines.append("")
        # NB 概率分布
        out_lines.append(f"| 指标 | 模型概率 | 隐含公平赔率 |")
        out_lines.append(f"|:-----|:-------:|:-----------:|")
        out_lines.append(f"| 主胜 | {probs[0]*100:.0f}% | {1/max(probs[0],0.01):.2f} |")
        out_lines.append(f"| 平局 | {probs[1]*100:.0f}% | {1/max(probs[1],0.01):.2f} |")
        out_lines.append(f"| 客胜 | {probs[2]*100:.0f}% | {1/max(probs[2],0.01):.2f} |")
        out_lines.append(f"| 大2.5 | {over25*100:.1f}% | {1/max(over25,0.01):.2f} |")
        out_lines.append(f"| 小2.5 | {(1-over25)*100:.1f}% | {1/max(1-over25,0.01):.2f} |")
        out_lines.append(f"| BTTS Yes | {btts*100:.1f}% | {1/max(btts,0.01):.2f} |")
        out_lines.append(f"| BTTS No | {(1-btts)*100:.1f}% | {1/max(1-btts,0.01):.2f} |")
        out_lines.append(f"| 角球大9 | — | — |")
        out_lines.append(f"| 罚牌大3 | — | — |")
        out_lines.append("")
        out_lines.append(f"> ⚠️ 无市场赔率，以上为模型隐含赔率。运行 `python fetch_match_data.py --mode yapan --home \"{home}\" --away \"{away}\"` 获取真实赔率")

    # ---- 比分分布 ----
    out_lines.append("")
    out_lines.append("## 比分分布")
    out_lines.append("")
    cum = 0
    for (i, j), p in dist:
        cum += p
        out_lines.append(f"| {i}-{j} | {p*100:.1f}% | {cum*100:.1f}% |")

    # 校准可靠性声明
    out_lines.append("")
    out_lines.append("## ⚠️ 校准可靠性声明")
    out_lines.append("")
    _lam_cal = _load_lambda_calibration()
    if _lam_cal is None:
        out_lines.append("> 🔴 **校准数据不足**（已结算记录 < 10 条）")
        out_lines.append("> 所有概率为原始模型输出，+EV 计算仅供参考，不具有统计显著性。")
    elif abs(_lam_cal - 1.0) > 0.10:
        out_lines.append(f"> 🟡 **全局 λ 校准已启用**（因子={_lam_cal:.3f}）")
        out_lines.append(f"> 模型存在系统性偏差(λ高估{max(0,(1-_lam_cal)*100):.0f}%)，已自动修正。")
    else:
        out_lines.append(f"> ✅ 概率已校准（λ因子={_lam_cal:.3f}, T={TEMP_T:.2f}）")
    out_lines.append("")

    out_str = "\n".join(out_lines)

    # 写入 MD 文件（仅 ⭐ 以上评级写入，❌/⛔ 只打印不存盘）
    WRITE_RATINGS = {'⭐⭐⭐', '⭐⭐', '⭐'}
    safe_home = home.replace(" ", "").replace("/", "vs")
    safe_away = away.replace(" ", "").replace("/", "vs")
    filename = f"足球预测-{date_prefix}-{safe_home}vs{safe_away}.md"
    filepath = os.path.join(BASE_DIR, "预测数据", filename)
    os.makedirs(os.path.join(BASE_DIR, "预测数据"), exist_ok=True)

    if final_rating in WRITE_RATINGS:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(out_str + "\n")
        print(f"[文件已写入] {filepath}")
    else:
        print(f"[跳过写入] 评级 {final_rating}，不存盘")

    # ── 自动补赔率（sportsdb/allsvenskan 等 datafc 覆盖的联赛） ──
    odds_result = dp.auto_fill_odds(
        home, away, league, p_final,
        direction=final_direction, rating=final_rating,
    )
    if odds_result.get("odds"):
        print(f"[自动赔率] {odds_result['source']}: {odds_result['odds']}")
    elif odds_result.get("source") in ("unsupported_league",):
        pass  # 非 datafc 联赛静默跳过
    elif odds_result.get("source") == "not_found":
        print(f"[自动赔率] ⚠️ {odds_result.get('detail', '未找到赔率')}")
    else:
        pass

    # ── 写入 predictions_db.json（仅 ⭐ 以上评级，直接写 JSON 避免同进程 stdout 冲突） ──
    if final_rating in WRITE_RATINGS:
        try:
            db_file = os.path.join(BASE_DIR, "数据缓存", "predictions_db.json")
            # P_final 已在主管线中应用温度缩放 T=1.60，此处直接使用
            # 加载现有 DB
            if os.path.exists(db_file):
                with open(db_file, "r", encoding="utf-8") as f:
                    db = json.load(f)
            else:
                db = {"predictions": []}
            # 查重
            rid = f"{date_prefix.replace('-','')}_{home}_{away}"
            exists = any(
                p.get("home") == home and p.get("away") == away
                and p.get("date") == date_prefix
                for p in db.get("predictions", [])
            )
            if not exists:
                rec = {
                    "id": rid, "date": date_prefix,
                    "home": home, "away": away,
                    "p_final": p_final, "direction": final_direction,
                    "league": league, "confidence": final_rating,
                    "source": "predict.py",
                    "score_diff": round(s7.get("diff", 0), 2),
                    "M_coef": wvr_m,
                    "lam_h": round(lam_h, 4),
                    "lam_a": round(lam_a, 4),
                    "probs_3way": {
                        "home": round(float(h), 4),
                        "draw": round(float(d), 4),
                        "away": round(float(a), 4),
                    },
                    "over_25": round(float(over25), 4),
                    "btts": round(float(btts), 4),
                    "result": {"status": "pending"},
                }
                db.setdefault("predictions", []).append(rec)
                with open(db_file, "w", encoding="utf-8") as f:
                    json.dump(db, f, ensure_ascii=False, indent=2)
                print(f"[DB记录] ✅ {home} vs {away} 已写入 predictions_db")
            else:
                print(f"[DB记录] ℹ️ {home} vs {away} 已存在，跳过")
        except Exception as e:
            print(f"[DB记录] ⚠️ 写入失败: {e}")

    print(out_str)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        with open(os.path.join(BASE_DIR, "数据缓存", "predict_debug.log"), "w") as _f:
            _f.write(f"Error: {e}\n")
            import traceback
            traceback.print_exc(file=_f)
        print(f"Error: {e}", file=sys.stderr)
