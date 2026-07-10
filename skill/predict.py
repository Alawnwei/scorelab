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

# 半场市场参数（v8.5）
HT_RATIO = 0.45      # 上半场xG占全场比例（经验值）
THETA_HT = 12        # 半场θ（半场方差小于全场）


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


def nb_team_over(lam: float, theta: float, line: float = 0.5, mg: int = 10) -> float:
    """P(某队进球 > line) — 球队进球数市场（v8.5）"""
    prob = 0.0
    for k in range(mg + 1):
        if k > line:
            prob += nb_prob(k, lam, theta)
    return prob


def nb_win_and_over(lam_h: float, lam_a: float, theta: float, line: float = 2.5, mg: int = 10) -> float:
    """P(主胜 & 总进球 > line) — 胜平负+大小球组合（v8.5）"""
    prob = 0.0
    for i in range(mg + 1):
        pi = nb_prob(i, lam_h, theta)
        for j in range(mg + 1):
            pj = nb_prob(j, lam_a, theta)
            if i > j and i + j > line:
                prob += pi * pj
    return prob


def nb_first_goal(lam_h: float, lam_a: float, home_factor: float = 1.05) -> tuple:
    """P(主先进球) 和 P(客先进球) — 泊松过程近似（v8.5）

    假设进球时间服从指数分布，主队先进球概率 ≈ λ_h / (λ_h + λ_a)。
    home_factor 微调主场进攻速率（通常 1.03-1.08）。

    Returns:
        (home_first, away_first, no_goal)
    """
    adj_h = lam_h * home_factor
    total = adj_h + lam_a
    if total <= 0:
        return 0.5, 0.5, 0.0
    # 考虑无进球概率
    no_goal = math.exp(-(adj_h + lam_a))  # 简化：所有进球率
    # 更精确：用零封概率乘积
    no_goal = (math.exp(-adj_h)) * (math.exp(-lam_a))
    home_first = adj_h / total * (1 - no_goal)
    away_first = lam_a / total * (1 - no_goal)
    return home_first, away_first, no_goal


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
    # 值域钳制：防止 OpenLigaDB 回退路径的异常值造成 λ 失真（v8.5）
    own_att_str = max(0.5, min(2.0, own_att_str))
    opp_def_str = max(0.5, min(2.0, opp_def_str))
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

def _calc_ko_lambda_factor() -> float:
    """动态计算淘汰赛 λ 衰减因子

    从已结算记录中统计淘汰赛场均总进球 / 联赛场均总进球，
    反映淘汰赛的节奏减慢程度。默认 0.85，样本≥5 场时动态计算。

    Returns:
        float: 0.70-1.00 之间的衰减因子
    """
    _db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "数据缓存", "predictions_db.json")
    _ko_total = 0
    _ko_count = 0
    _league_total = 0
    _league_count = 0
    try:
        with open(_db_path, "r", encoding="utf-8") as _f:
            _db = json.load(_f)
        for _p in _db.get("predictions", []):
            _r = _p.get("result", {})
            if _r.get("status") != "matched":
                continue
            _sh = _r.get("score_home"); _sa = _r.get("score_away")
            if _sh is None or _sa is None:
                continue
            _lg = _p.get("league", "")
            _goals = int(_sh) + int(_sa)
            # 已知淘汰赛联赛代码
            if _lg in ("wm26", "WC", "ucl", "uel", "uecl", "facup", "copadelrey", "dfbpokal", "coppaita"):
                _ko_total += _goals
                _ko_count += 1
            elif _lg in ("bl1", "epl", "laliga", "seriea", "ligue1", "kleague1", "jleague1"):
                _league_total += _goals
                _league_count += 1
    except Exception:
        pass
    if _ko_count >= 5 and _league_count >= 5:
        _ratio = (_ko_total / _ko_count) / (_league_total / _league_count)
        _ratio = max(0.70, min(1.00, _ratio))
        print(f"[λ校准] 淘汰赛进/联赛进球比={_ratio:.3f} ({_ko_count}场KO/{_league_count}场联赛)")
        return _ratio
    print(f"[λ校准] KO样本不足({_ko_count}场)，使用默认0.85")
    return 0.85

def _assign_split(pred_id: str) -> str:
    """确定性分桶：根据 prediction ID hash 分配 train/calib/holdout

    60% train / 20% calib / 20% holdout — 同一 ID 始终分到同一桶
    """
    _h = hash(pred_id) & 0xFFFF  # 取低16位保持稳定
    if _h % 10 < 6:
        return "train"
    elif _h % 10 < 8:
        return "calib"
    else:
        return "holdout"

def _load_lambda_calibration():
    """从 predictions_db 已结算记录计算 λ 校准因子

    v8.5: 仅使用 calib 分桶记录（独立于训练集），有存储 λ 值时优先使用。

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

    # 仅 calib 分桶 + 有实际比分的记录
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
        # 分桶过滤：仅 calib 集
        _pid = p.get("id", "")
        if _assign_split(_pid) != "calib":
            continue

        actual_total = int(sh) + int(sa)
        # 优先使用存储的 λ 值（新格式）
        lam_h = p.get("lam_h")
        lam_a = p.get("lam_a")
        if lam_h is not None and lam_a is not None and lam_h > 0 and lam_a > 0:
            total_expected += lam_h + lam_a
        else:
            # 旧格式无 λ，用 score_diff 反推
            sd = p.get("score_diff")
            if sd is not None and abs(sd) > 0:
                p_base = 1.0 / (1.0 + math.exp(-0.15 * sd))
                # 粗略反推 λ ≈ 2.0 + sd*0.3（经验公式）
                total_expected += max(1.5, 2.0 + abs(sd) * 0.3)
            else:
                continue  # 无法估算 λ 的记录跳过
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


def suggest_parlays(current_home: str = "", current_away: str = "", max_legs: int = 3) -> list:
    """从 predictions_db 读取当日待结算预测，寻找串关机会（v8.5）

    排除当前比赛自身，推荐 EV 最高的串关组合。

    Returns:
        [{"legs": int, "odds": float, "ev": float, "detail": str, "stake": float}, ...]
    """
    db_path = os.path.join(BASE_DIR, "数据缓存", "predictions_db.json")
    if not os.path.exists(db_path):
        return []

    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
    except Exception:
        return []

    # 收集今日待结算且有 +EV 的推荐
    today = datetime.now().strftime("%Y-%m-%d")
    picks = []
    for p in db.get("predictions", []):
        pid = p.get("id", "")
        if p.get("date", "") != today:
            continue
        res = p.get("result", {})
        if res.get("status") == "matched":
            continue
        home = p.get("home", ""); away = p.get("away", "")
        # 排除当前比赛
        if home == current_home and away == current_away:
            continue
        direction = p.get("direction", "")
        if not direction or direction in ("不推荐/均衡",):
            continue
        # 从 recommendations 找最佳 +EV
        recs = p.get("recommendations", [])
        if recs:
            best = max(recs, key=lambda r: r.get("ev", 0))
            if best.get("ev", 0) >= 8:
                picks.append({
                    "match": f"{home} vs {away}",
                    "direction": best.get("market", direction),
                    "odds": best.get("odds", 1.5),
                    "model_prob": best.get("model_prob", 50),
                    "ev": best.get("ev", 0),
                })
        else:
            # 无推荐快照，用 P_final 近似
            p_final = p.get("p_final", 0.5)
            ev_approx = (p_final / 0.5 - 1) * 100
            if ev_approx >= 8:
                picks.append({
                    "match": f"{home} vs {away}",
                    "direction": direction,
                    "odds": 1 / max(p_final, 0.01),
                    "model_prob": p_final * 100,
                    "ev": round(ev_approx, 1),
                })

    if len(picks) < 2:
        return []

    # 计算串关
    from skill.betting_engine import BettingEngine
    be = BettingEngine(bankroll=10000, mode="pro")
    result = be.optimize_parlay(picks, max_legs=max_legs, total_bankroll=10000)
    if result.get("recommend"):
        return [{
            "legs": len(picks) if result.get("type") else 2,
            "odds": result.get("odds", 0),
            "ev": result.get("ev", 0),
            "stake": result.get("stake", 0),
            "detail": " | ".join([f"{p['match']} {p['direction']}@{p['odds']}" for p in picks[:3]]),
        }]
    return []


def _get_match_start_time(home: str, away: str, league: str) -> tuple:
    """获取比赛开始时间（v8.5 仓位时间管理）"""
    try:
        dp = _get_dp()
        df = dp.get_matches(league, team_name=home)
        if df is not None and not df.empty:
            team_en = dp.TEAM_EN.get(home, home).lower().replace(" ", "")
            away_en = dp.TEAM_EN.get(away, away).lower().replace(" ", "")
            for _, row in df.iterrows():
                ht = str(row.get("home_team", "")).lower().replace(" ", "")
                at = str(row.get("away_team", "")).lower().replace(" ", "")
                if (team_en in ht and away_en in at) or (team_en in at and away_en in ht):
                    ts = row.get("start_timestamp")
                    if ts:
                        match_dt = datetime.fromtimestamp(int(ts))
                        now = datetime.now()
                        hours = max(0, (match_dt - now).total_seconds() / 3600)
                        return match_dt, round(hours, 1)
    except Exception:
        pass
    return datetime.now(), None


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

    # ── 仓位时间管理：获取比赛开始时间（v8.5） ──
    _match_dt, _match_hours = _get_match_start_time(home, away, league)
    if _match_hours is not None:
        print(f"[时间管理] 距离开赛约 {_match_hours:.1f}h")
    else:
        print(f"[时间管理] ⚠️ 无法获取比赛时间")
        _match_hours = 24

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

    # ── 1. 六维评分（L1 基础层，X因素已移除 v8.5） ──
    s7 = dp.compute_7dim_scores(home, away, league)
    for k in ("home_进攻", "home_防守", "home_中场", "home_经验",
              "home_战术", "home_状态"):
        if k not in s7: s7[k] = 5.0
    for k in ("away_进攻", "away_防守", "away_中场", "away_经验",
              "away_战术", "away_状态"):
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

    # ── 2b. 淘汰赛 λ 修正（v8.5：仅用于有淘汰赛阶段的赛事）──
    # uefa(欧冠/欧联) 和 world_cup(世界杯) 的淘汰赛阶段节奏更慢、进球更少
    # 纯淘汰赛(足总杯等)一轮定胜负，进球节奏与联赛无异，不触发
    if dp.has_knockout_stage(league):
        _ko_factor = _calc_ko_lambda_factor()
        lam_h *= _ko_factor
        lam_a *= _ko_factor

    # ── 2c. λ 全局校准（2026-07-08）──
    # 从历史数据学习 λ → 实际进球的偏差，修正 λ 值
    # 仅当有至少 10 条已结算记录且 xG 数据未校准时启用
    # datafc_xg 来自 Sofascore 真实射门数据（已校准），无需再用实际进球校准
    _xg_is_calibrated = (xg_h.get("source") == "datafc_xg" and
                         xg_a.get("source") == "datafc_xg")
    _lam_calib_factor = _load_lambda_calibration()
    if _lam_calib_factor is not None and not _xg_is_calibrated:
        lam_h *= _lam_calib_factor
        lam_a *= _lam_calib_factor

    # ── 3. ELO ──
    elo_h = dp.get_team_elo(home).get("elo", 1500)
    elo_a = dp.get_team_elo(away).get("elo", 1500)
    rank_h = dp.get_team_elo(home).get("rank", 99)
    rank_a = dp.get_team_elo(away).get("rank", 99)

    # ── 4. M系数（L2） + WVR 衰减 ──
    raw_factors = []
    # KO 场景系数：仅用于有淘汰赛阶段的赛事（uefa/world_cup）
    if dp.has_knockout_stage(league):
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
    # 温度缩放 T=1.50（轻度正则化，2026-07-09 修正）
    # T=4.08 是旧 λ 时代（法国 λ=3.45）校准出的极端值，
    # 现已禁用的 λ 全局校准 + 修复 Sofascore xG 路径后 λ 回归合理，
    # T=4.08 反而把有区分度的概率压到~0.52 附近，使模型失效。
    # T=1.50 提供温和防过信，同时保留 p_final 的区分能力。
    TEMP_T = 1.50
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

    # ── 双模型融合（v8.5）：方向一致时在 log-odds 空间融合 ──
    # log-odds 是 GLM 的自然参数空间，线性组合比概率空间更合理
    _nb_win_prob = max(h, a)
    _nb_dir = '主胜' if h > a else '客胜'
    _p_dir = '主胜' if p_final > 0.50 else '客胜'
    if not model_conflict and _nb_dir == _p_dir and _nb_win_prob > 0.40:
        _nb_weight = min(0.30, max(0.10, lam_ratio * 0.10))
        _nb_prob_for = h if _nb_dir == '主胜' else a
        # log-odds 空间融合
        _logit_base = math.log(p_final / (1 - p_final))
        _logit_nb = math.log(_nb_prob_for / (1 - _nb_prob_for))
        _logit_fused = _logit_base * (1 - _nb_weight) + _logit_nb * _nb_weight
        p_final = 1 / (1 + math.exp(-_logit_fused))
        p_final = max(0.01, min(0.99, p_final))
        print(f"[双模型融合(log-odds)] 方向一致(NB:{_nb_dir}), "
              f"P_final({p_final:.3f}) = logit⁻¹({1-_nb_weight:.0%}×logit(P_base) + {_nb_weight:.0%}×logit(NB={_nb_prob_for:.3f}))")

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

    # 存储推荐快照（赛后复盘用）
    rec_recommendations = []

    if odds_data.get("odds"):
        home_odds = odds_data.get("home_odds")
        draw_odds = odds_data.get("draw_odds")
        away_odds = odds_data.get("away_odds")

        # 用 betting_engine 计算 +EV 和凯利
        from skill.betting_engine import BettingEngine
        be = BettingEngine(bankroll=10000, mode="pro", match_name=f"{home} vs {away}")
        be.set_lambda(lam_h, lam_a)
        if _match_hours is not None:
            be.set_hours_to_match(_match_hours)
        be.total_recommended += 1
        # 跨比赛相关性折扣（v8.5）：当天多场时仓位递减
        if be.total_recommended > 1:
            _multi_factor = max(0.5, 1.0 - (be.total_recommended - 1) * 0.2)
            be.max_bet_pct *= _multi_factor
        prob_h_pct = probs[0] * 100
        prob_d_pct = probs[1] * 100
        prob_a_pct = probs[2] * 100

        # 收集所有市场结果用于排序
        all_be_results = []

        # 计算三个方向的 +EV（带精确推水）
        all_1x2_odds = [home_odds, draw_odds, away_odds]
        rows = []
        for label, mp, mo in [("主胜", prob_h_pct, home_odds),
                               ("平局", prob_d_pct, draw_odds),
                               ("客胜", prob_a_pct, away_odds)]:
            ev_pct, mip = be.calc_ev(mp, mo, all_odds=all_1x2_odds)
            kelly_pct = be.kelly(mo, mp)
            rows.append((label, mp, mo, mip, ev_pct, kelly_pct))
            # 加入排名池
            if ev_pct >= be.min_ev:
                all_be_results.append({
                    "market": f"1X2 {label}",
                    "direction": label,
                    "model_prob": round(mp, 1),
                    "mip": round(mip, 1),
                    "ev": round(ev_pct, 1),
                    "odds": mo,
                    "kelly_pct": round(kelly_pct*100, 1),
                    "bet_pct": round(min(kelly_pct, be.max_bet_pct)*100, 1),
                    "depth": abs(mp-50),
                    "group": "1x2",
                })

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

            # 分歧仓位控制：模型 vs 市场偏差超过阈值时强制降仓（v8.5）
            divergence = abs(mp - mip)
            div_warn = ""
            if divergence >= 25:
                # 极端分歧 → 强制 1/8 凯利
                max_kelly_frac = 0.125
                kp = min(kp, max_kelly_frac)
                bet_pct = min(bet_pct, max_kelly_frac)
                bet_amount = 10000 * bet_pct
                div_warn = f"\n| 🚨 极端分歧(≥25pp) | 仓位强制降至1/8凯利({kp*100:.1f}%) |"
            elif divergence >= 15:
                # 中度分歧 → 半仓
                bet_pct = min(bet_pct, 0.05)
                bet_amount = 10000 * bet_pct
                div_warn = f"\n| ⚠️ 显著分歧(≥15pp) | 建议减半仓({bet_pct*100:.1f}%) |"

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

        # ── 全市场扫描（使用 betting_engine 多盘口分析） ──
        out_lines.append("")
        out_lines.append("### 📊 全市场 +EV 扫描")
        out_lines.append("")
        odds_path = os.path.join(BASE_DIR, "数据缓存", "latest_match_data.json")
        market_data = {}
        if os.path.exists(odds_path):
            try:
                with open(odds_path, "r", encoding="utf-8") as _f:
                    market_data = json.load(_f)
            except Exception:
                pass

        # ── 大小球全盘口扫描 ──
        ou_market = {}
        for src in ("bet365", "1xbet"):
            ou_raw = market_data.get(src, {}).get("over_under", [])
            for raw in ou_raw:
                m = re.search(r'([\d.]+)球.*?大@([\d.]+).*?小@([\d.]+)', raw)
                if m:
                    line = float(m.group(1))
                    over_odds, under_odds = float(m.group(2)), float(m.group(3))
                    ou_market[line] = (over_odds, under_odds)
        if ou_market:
            ou_results = be.scan_ou_all(f"{home} vs {away}", ou_market, lam_h, lam_a)
            all_be_results.extend(ou_results)
            if ou_results:
                out_lines.append(f"**⚽ 大小球（{len(ou_results)}条+EV）**")
                out_lines.append("")
                out_lines.append(f"| 盘口 | 模型概率 | 赔率 | MIP | +EV | 凯利 |")
                out_lines.append(f"|:-----|:-------:|:----:|:---:|:---:|:----:|")
                for r in ou_results[:6]:
                    tag = "✅" if r['ev'] >= 20 else "⚠️"
                    out_lines.append(f"| {r['direction']} | {r['model_prob']:.0f}% | {r['odds']} | {r['mip']:.0f}% | {r['ev']:+.1f}% {tag} | {r['kelly_pct']:.1f}% |")
                out_lines.append("")

        # ── 亚盘全盘口扫描 ──
        ah_market = {}
        for src in ("bet365", "1xbet"):
            ah_raw = market_data.get(src, {}).get("asian_handicap", [])
            if isinstance(ah_raw, dict):
                ah_raw = [ah_raw]
            elif not isinstance(ah_raw, list):
                continue
            for raw in ah_raw:
                if isinstance(raw, dict) and "line" in raw:
                    line_val = float(raw["line"])
                    h_odds = raw.get("home_odds") or raw.get("主")
                    a_odds = raw.get("away_odds") or raw.get("客")
                    if h_odds and a_odds:
                        ah_market[line_val] = (float(h_odds), float(a_odds))
                elif isinstance(raw, str):
                    m = re.search(r'([\d.]+)球.*?(?:主|上)@([\d.]+).*(?:客|下)@([\d.]+)', raw)
                    if m:
                        line_val = float(m.group(1))
                        ah_market[line_val] = (float(m.group(2)), float(m.group(3)))
        if ah_market:
            ah_results = be.scan_asian_all(f"{home} vs {away}", ah_market, lam_h, lam_a, side="home")
            all_be_results.extend(ah_results)
            if ah_results:
                out_lines.append(f"**📐 亚盘（{len(ah_results)}条+EV）**")
                out_lines.append("")
                out_lines.append(f"| 盘口 | 模型概率 | 赔率 | MIP | +EV | 凯利 |")
                out_lines.append(f"|:-----|:-------:|:----:|:---:|:---:|:----:|")
                for r in ah_results[:6]:
                    tag = "✅" if r['ev'] >= 20 else "⚠️"
                    out_lines.append(f"| {r['direction']} | {r['model_prob']:.0f}% | {r['odds']} | {r['mip']:.0f}% | {r['ev']:+.1f}% {tag} | {r['kelly_pct']:.1f}% |")
                out_lines.append("")

        # ── BTTS ──
        btts_data = market_data.get("bet365", {}).get("btts", {}) or market_data.get("1xbet", {}).get("btts", {})
        yes_odds = float(btts_data["yes"]) if isinstance(btts_data.get("yes"), (int, float, str)) and str(btts_data.get("yes","")).replace('.','').isdigit() else None
        no_odds = float(btts_data["no"]) if isinstance(btts_data.get("no"), (int, float, str)) and str(btts_data.get("no","")).replace('.','').isdigit() else None
        if yes_odds and no_odds:
            for label, prob, odds in [("Yes", btts*100, yes_odds), ("No", (1-btts)*100, no_odds)]:
                ev_pct, mip = be.calc_ev(prob, odds, [yes_odds, no_odds], market_type="btts")
                if ev_pct >= be.min_ev:
                    kelly = be.kelly(odds, prob)
                    all_be_results.append({
                        "market": f"BTTS {label}",
                        "direction": f"BTTS {label}",
                        "model_prob": round(prob, 1),
                        "mip": round(mip, 1),
                        "ev": round(ev_pct, 1),
                        "odds": odds,
                        "kelly_pct": round(kelly*100, 1),
                        "bet_pct": round(min(kelly, be.max_bet_pct)*100, 1),
                        "depth": abs(prob-50),
                        "group": "btts",
                    })
            out_lines.append(f"**🤝 BTTS（双方进球）**")
            out_lines.append("")
            out_lines.append(f"| 选项 | 模型概率 | 赔率 | MIP | +EV |")
            out_lines.append(f"|:-----|:-------:|:----:|:---:|:---:|")
            for label, prob, odds in [("Yes", btts*100, yes_odds), ("No", (1-btts)*100, no_odds)]:
                ev_pct, mip = be.calc_ev(prob, odds, [yes_odds, no_odds], market_type="btts")
                tag = "✅" if ev_pct >= 10 else ("⚠️" if ev_pct > 0 else "")
                out_lines.append(f"| {label} | {prob:.0f}% | {odds} | {mip:.0f}% | {ev_pct:+.1f}% {tag} |")
            out_lines.append("")

        # ── 角球模型（独立 NB，theta=15） ──
        corner_h = dp.get_team_corner_summary(home, league)
        corner_a = dp.get_team_corner_summary(away, league)
        lam_c_h = corner_h.get("corners_for_90", 5.0)
        lam_c_a = corner_a.get("corners_for_90", 5.0)
        corner_theta = 15
        corner_lines = []
        for src in ("bet365", "1xbet"):
            cl = market_data.get(src, {}).get("corner_totals", [])
            if isinstance(cl, list):
                for line in cl:
                    if line not in corner_lines:
                        corner_lines.append(line)
        if corner_lines and lam_c_h > 0 and lam_c_a > 0:
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
                    ev_pct, mip = be.calc_ev(prob_over*100, over_odds, [over_odds, under_odds], market_type="ou")
                    tag = "✅" if ev_pct >= 10 else ("⚠️" if ev_pct > 0 else "")
                    out_lines.append(f"| {cl} | {prob_over*100:.0f}% | {over_odds}/{under_odds} | {ev_pct:+.1f}% {tag} |")
            out_lines.append(f"> 角球数据: {home} {lam_c_h:.1f}/场 | {away} {lam_c_a:.1f}/场")
            out_lines.append("")

        # ── 推荐排序输出 ──
        if all_be_results:
            top = be.recommend_sorted(all_be_results, max_picks=3, bankroll=10000)
            # 保存推荐快照用于赛后复盘
            rec_recommendations = [{
                "market": r["market"],
                "ev": r["ev"],
                "odds": r["odds"],
                "model_prob": r["model_prob"],
                "kelly_pct": r["kelly_pct"],
                "bet_amount": r.get("bet_amount", 0),
                "hit": None,  # 赛后回填
            } for r in top]
            out_lines.append("### 🏆 推荐排序 Top 3")
            out_lines.append("")
            out_lines.append(f"| # | 市场 | 模型概率 | 赔率 | +EV | 凯利 | 金额 |")
            out_lines.append(f"|:-:|:-----|:-------:|:----:|:---:|:----:|:----:|")
            for i, r in enumerate(top, 1):
                amt = r.get("bet_amount", 0)
                out_lines.append(f"| **{i}** | {r['market']} | {r['model_prob']:.0f}% | {r['odds']} | **{r['ev']:+.1f}%** | {r['kelly_pct']:.1f}% | {amt}元 |")
            out_lines.append("")
            # 推荐自洽性摘要（v8.5）
            _markets = [r.get("market", "") for r in top]
            _has_over = any("大" in m for m in _markets)
            _has_under = any("小" in m for m in _markets)
            _has_btts = any("BTTS" in m.upper() or "双方进球" in m for m in _markets)
            _has_home = any("主" in m for m in _markets if "1X2" in m or "胜平负" in m)
            _has_away = any("客" in m for m in _markets if "1X2" in m or "胜平负" in m)
            _consistency = "🟢 推荐自洽"
            if _has_over and _has_under:
                _consistency = "🔴 推荐矛盾：同时推荐大小球"
            elif _has_home and _has_away:
                _consistency = "🔴 推荐矛盾：同时推荐主客胜"
            elif _has_over and _has_btts:
                _consistency = "🟢 推荐自洽 | 大球✅BTTS✅方向一致"
            elif _has_under and _has_btts:
                _consistency = "🟡 推荐注意 | 小球+BTTS需确认是否矛盾"
            out_lines.append(f"> {_consistency}")
            out_lines.append("")

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
        # 零封（v8.5）
        _cs_h = nb_prob(0, lam_a, theta) * 100
        _cs_a = nb_prob(0, lam_h, theta) * 100
        out_lines.append(f"| 主零封 | {_cs_h:.0f}% | {1/max(_cs_h/100,0.01):.2f} |")
        out_lines.append(f"| 客零封 | {_cs_a:.0f}% | {1/max(_cs_a/100,0.01):.2f} |")
        # 先进球（v8.5）
        _fg_h, _fg_a, _fg_no = nb_first_goal(lam_h, lam_a, home_factor=1.05)
        out_lines.append(f"| 主先进球 | {_fg_h*100:.0f}% | {1/max(_fg_h,0.01):.2f} |")
        out_lines.append(f"| 客先进球 | {_fg_a*100:.0f}% | {1/max(_fg_a,0.01):.2f} |")
        out_lines.append(f"| 无进球 | {_fg_no*100:.0f}% | {1/max(_fg_no,0.01):.2f} |")
        # 球队进球数（P0 新市场 v8.5）
        _prob_h1 = nb_team_over(lam_h, theta, 0.5, mg=15)
        _prob_a1 = nb_team_over(lam_a, theta, 0.5, mg=15)
        _prob_h15 = nb_team_over(lam_h, theta, 1.5, mg=15)
        _prob_a15 = nb_team_over(lam_a, theta, 1.5, mg=15)
        out_lines.append(f"| 主≥1球 | {_prob_h1*100:.0f}% | {1/max(_prob_h1,0.01):.2f} |")
        out_lines.append(f"| 客≥1球 | {_prob_a1*100:.0f}% | {1/max(_prob_a1,0.01):.2f} |")
        out_lines.append(f"| 主≥1.5 | {_prob_h15*100:.0f}% | {1/max(_prob_h15,0.01):.2f} |")
        out_lines.append(f"| 客≥1.5 | {_prob_a15*100:.0f}% | {1/max(_prob_a15,0.01):.2f} |")
        # 胜平负+大小球组合（P0 新市场 v8.5）
        _win_over = nb_win_and_over(lam_h, lam_a, theta, 2.5, mg=15)
        _win_over_away = nb_win_and_over(lam_a, lam_h, theta, 2.5, mg=15)
        out_lines.append(f"| 主胜&大2.5 | {_win_over*100:.1f}% | {1/max(_win_over,0.01):.2f} |")
        out_lines.append(f"| 客胜&大2.5 | {_win_over_away*100:.1f}% | {1/max(_win_over_away,0.01):.2f} |")
        out_lines.append(f"| 角球大9 | — | — |")
        out_lines.append(f"| 罚牌大3 | — | — |")
        out_lines.append("")
        out_lines.append(f"> ⚠️ 无市场赔率，以上为模型隐含赔率。运行 `python fetch_match_data.py --mode yapan --home \"{home}\" --away \"{away}\"` 获取真实赔率")

        # ── 半场市场（v8.5） ──
        _ht_lam_h = lam_h * HT_RATIO
        _ht_lam_a = lam_a * HT_RATIO
        _ht_h, _ht_d, _ht_a = nb_match_probs(_ht_lam_h, _ht_lam_a, THETA_HT, mg=8)
        _ht_over_15 = nb_over_25(_ht_lam_h, _ht_lam_a, THETA_HT, mg=8)
        _ht_btts = nb_btts(_ht_lam_h, _ht_lam_a, THETA_HT, mg=8)
        out_lines.append("")
        out_lines.append("### 半场市场（模型预估）")
        out_lines.append("")
        out_lines.append("| 指标 | 模型概率 | 公平赔率 |")
        out_lines.append("|:-----|:-------:|:-------:|")
        out_lines.append(f"| 主胜 | {_ht_h*100:.0f}% | {1/max(_ht_h,0.01):.2f} |")
        out_lines.append(f"| 平局 | {_ht_d*100:.0f}% | {1/max(_ht_d,0.01):.2f} |")
        out_lines.append(f"| 客胜 | {_ht_a*100:.0f}% | {1/max(_ht_a,0.01):.2f} |")
        out_lines.append(f"| 大1.5 | {_ht_over_15*100:.1f}% | {1/max(_ht_over_15,0.01):.2f} |")
        out_lines.append(f"| 小1.5 | {(1-_ht_over_15)*100:.1f}% | {1/max(1-_ht_over_15,0.01):.2f} |")
        out_lines.append(f"| BTTS Yes | {_ht_btts*100:.1f}% | {1/max(_ht_btts,0.01):.2f} |")
        out_lines.append(f"| BTTS No | {(1-_ht_btts)*100:.1f}% | {1/max(1-_ht_btts,0.01):.2f} |")

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
    _xg_is_calibrated = (xg_h.get("source") == "datafc_xg" and
                         xg_a.get("source") == "datafc_xg")
    if _xg_is_calibrated:
        out_lines.append("> ✅ **xG 数据源**: Sofascore 真实射门 xG（已校准）")
        out_lines.append(f"> 温度缩放 T={TEMP_T:.2f}，输出概率可直接使用。")
    else:
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

    # 写入 MD 文件（v8.5 全部写入）
    safe_home = home.replace(" ", "").replace("/", "vs")
    safe_away = away.replace(" ", "").replace("/", "vs")
    filename = f"足球预测-{date_prefix}-{safe_home}vs{safe_away}.md"
    filepath = os.path.join(BASE_DIR, "预测数据", filename)
    os.makedirs(os.path.join(BASE_DIR, "预测数据"), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(out_str + chr(92) + "n")
    print(f"[文件已写入] {filepath}")

    
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

    # ── 写入 predictions_db.json（v8.5 全部写入，低信心预测的 λ 值对校准有用） ──
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
        _upgraded = False
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
                "recommendations": rec_recommendations,
                "odds": odds_result.get("odds"),
                "result": {"status": "pending"},
                "bet_ts": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "hours_to_match": _match_hours,
            }
            db.setdefault("predictions", []).append(rec)
            print(f"[DB记录] ✅ {home} vs {away} 已写入 predictions_db (新)")
            _upgraded = True

        else:
            for _p in db["predictions"]:
                if _p.get("home") == home and _p.get("away") == away and _p.get("date") == date_prefix:
                    if "lam_h" not in _p or "recommendations" not in _p:
                        _p["score_diff"] = round(s7.get("diff", 0), 2)
                        _p["M_coef"] = wvr_m
                        _p["lam_h"] = round(lam_h, 4)
                        _p["lam_a"] = round(lam_a, 4)
                        _p["probs_3way"] = {"home": round(float(h), 4), "draw": round(float(d), 4), "away": round(float(a), 4)}
                        _p["over_25"] = round(float(over25), 4)
                        _p["btts"] = round(float(btts), 4)
                        _p["recommendations"] = rec_recommendations
                        _p["bet_ts"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                        _p["hours_to_match"] = _match_hours
                        _upgraded = True
                        print(f"[DB记录] 🔄 {home} vs {away} 已升级为完整新格式")
                    else:
                        print(f"[DB记录] ℹ️ {home} vs {away} 已是最新格式，跳过")
                    break

        # DB 写入
        with open(db_file, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
            print(f"[DB记录] ⚠️ 写入失败: {e}")

    print(out_str)

    # ── 自动回填已完赛结果（v8.5） ──
    try:
        _review_path = os.path.join(BASE_DIR, "skill", "auto_review.py")
        _ret = subprocess.run(
            [sys.executable, _review_path, "--sync"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace"
        )
        if _ret.stdout:
            _sync_line = [l for l in _ret.stdout.strip().split("\n") if "回填" in l or "同步" in l]
            if _sync_line:
                print(f"[自动回填] {_sync_line[0]}")
    except Exception:
        pass  # 回填失败不影响主流程


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        with open(os.path.join(BASE_DIR, "数据缓存", "predict_debug.log"), "w") as _f:
            _f.write(f"Error: {e}\n")
            import traceback
            traceback.print_exc(file=_f)
        print(f"Error: {e}", file=sys.stderr)
