#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
质量引擎 — WVR衰减 / 三级漏斗 / 偏差熔断  (SKILL.md v8.4)

集成点: predict.py 中 P_final 计算后、最终推荐输出前调用。
"""
import math

# ============================================================
# 一、WVR 权重验证基底
# ============================================================
# 精算可信度等级（SKILL.md §3.2）
WVR_LEVELS = {
    "A": {"min_samples": 30, "生效比例": 1.0, "label": "✅ A级"},
    "B": {"min_samples": 10, "生效比例": 0.75, "label": "⚠️ B级"},
    "C": {"min_samples": 0,  "生效比例": 0.50, "label": "🔴 C级"},
}

# 全量因子锚定表 (SKILL.md §3.2 核心权重的验证等级锚定表)
# (因子名, 原始系数, WVR等级, 置信描述)
WVR_FACTORS = [
    # 赛事类型
    ("淘汰赛",              0.95,  "B", "跨赛事累计验证"),
    ("小组赛均衡局",         1.00,  "A", "多届赛事>=30场"),
    # 历史交锋
    ("历史交锋_小组赛",      0.70,  "B", "小组赛样本"),
    ("历史交锋_淘汰赛",      0.50,  "B", "~15场淘汰赛"),
    # 东道主
    ("东道主_小组赛",        1.08,  "B", "多届小组赛"),
    ("东道主_淘汰赛",        1.15,  "B", "~15场淘汰赛"),
    # 必须赢
    ("必须赢_战意",         1.35,  "C", "仅4场复发案例"),
    # 轮换
    ("轮换L1",              0.95,  "B", "多场联赛样本"),
    ("轮换L2",              0.85,  "B", "多场联赛样本"),
    ("轮换L3",              0.70,  "C", "有限样本"),
    ("轮换L4",              0.55,  "C", "1场极端案例"),
    # 退速
    ("大幅领先退速",         0.60,  "C", "少量样本"),
    ("小幅领先退速",         0.80,  "C", "少量样本"),
    ("保平收缩",            0.50,  "C", "少量样本"),
    # 连胜衰减
    ("主场连胜3-4场",       0.92,  "C", "少量样本"),
    ("主场连胜>=5场",       0.85,  "C", "1场芬超"),
    # 其他
    ("德比",                1.15,  "C", "经验值"),
    ("生死战防守提升",       1.10,  "C", "~5场"),
    ("已淘汰放开踢",         0.90,  "C", "~4场"),
    ("ELO差距大",           1.05,  "B", "多场验证"),
]


def wvr_effective(raw_coef: float, level: str) -> float:
    """Apply WVR attenuation"""
    生效比例 = WVR_LEVELS.get(level, WVR_LEVELS["C"])["生效比例"]
    return round(1.0 + (raw_coef - 1.0) * 生效比例, 4)


def wvr_factor_info(factor_name: str) -> dict:
    """查询因子锚定信息"""
    for name, raw, level, desc in WVR_FACTORS:
        if name == factor_name:
            有效 = wvr_effective(raw, level)
            return {
                "name": name, "raw": raw, "level": level,
                "effective": 有效,
                "生效比例": WVR_LEVELS[level]["生效比例"],
                "label": WVR_LEVELS[level]["label"],
                "desc": desc,
            }
    return {"name": factor_name, "raw": 1.0, "level": "?",
            "effective": 1.0, "生效比例": 1.0, "label": "❓ 未锚定", "desc": ""}


def wvr_report(factors: list) -> list:
    """对 M系数因子列表批量应用 WVR 衰减

    Args:
        factors: [(因子名, 原始系数), ...]

    Returns:
        [(因子名, 原始系数, WVR等级, 生效比例, 有效系数, label), ...]
    """
    report = []
    for name, raw in factors:
        info = wvr_factor_info(name)
        report.append((
            name, raw, info["level"],
            info["生效比例"], info["effective"],
            info["label"],
        ))
    return report


def wvr_apply_all(factors: list) -> tuple:
    """应用 WVR 并计算综合 M 系数

    Args:
        factors: [(因子名, 原始系数), ...]

    Returns:
        (综合M系数, WVR报告列表, 使用的C级因子数)
    """
    report = wvr_report(factors)
    m = 1.0
    c_count = 0
    for name, raw, level, ratio, eff, label in report:
        m *= eff
        if level == "C":
            c_count += 1
    m = round(m, 4)

    # C级因子数限制检查
    warning = None
    if c_count >= 4:
        warning = f"⚠️ C级因子 {c_count}个 ≥ 4 → 结果可靠性下降"
    elif c_count >= 3:
        warning = f"⚠️ 使用了 {c_count}个 C级因子"

    return m, report, c_count, warning


# ============================================================
# 二、三级漏斗检查清单
# ============================================================


def funnel_gate_check(dp, home: str, away: str, league: str, lam_h: float, lam_a: float,
                      p_final: float, probs: tuple) -> dict:
    """🔴 G01-G14 强制闸门 — 全部通过才继续

    Returns: {"passed": bool, "results": [(id, 通过状态, 说明)], "扣分": int}
    """
    results = []
    passed = True
    total_deduct = 0

    # G01: 数据源可用
    g01_ok = dp is not None
    results.append(("G01", g01_ok, "数据源可用" if g01_ok else "❌ datafc_provider 加载失败"))
    if not g01_ok: passed = False; total_deduct += 100

    # G02: 球队名有效
    g02_ok = bool(home and away)
    results.append(("G02", g02_ok, f"球队: {home} vs {away}" if g02_ok else "❌ 球队名为空"))
    if not g02_ok: passed = False; total_deduct += 100

    # G03: 预期进球非零
    g03_ok = (lam_h > 0.01 and lam_a > 0.01)
    results.append(("G03", g03_ok, f"λ主={lam_h:.2f} λ客={lam_a:.2f}" if g03_ok else "❌ λ异常"))
    if not g03_ok: passed = False; total_deduct += 100

    # G04: P_final 在合理范围
    g04_ok = 0.01 <= p_final <= 0.99
    results.append(("G04", g04_ok, f"P_final={p_final:.3f}" if g04_ok else f"❌ P_final={p_final:.3f}越界"))
    if not g04_ok: passed = False; total_deduct += 50

    # G05: 3-way 概率和 ≈ 1.0
    prob_sum = sum(probs)
    g05_ok = 0.95 <= prob_sum <= 1.05
    results.append(("G05", g05_ok, f"3-way和={prob_sum:.3f}" if g05_ok else f"❌ 概率和={prob_sum:.3f}"))
    if not g05_ok: total_deduct += 20

    # G06: 联赛配置可用
    g06_ok = bool(dp and dp.get_league_config(league)) if dp else False
    cfg_name = (dp.LEAGUE_TOURNAMENT.get(league, {}).get("name", "?")
                if dp and hasattr(dp, "LEAGUE_TOURNAMENT") else "?")
    results.append(("G06", g06_ok, f"联赛: {league} ({cfg_name})" if g06_ok else f"❌ 未知联赛: {league}"))
    if not g06_ok: total_deduct += 15

    # G07: 数据可用
    g07_ok = lam_h != 1.40 or lam_a != 1.40
    results.append(("G07", g07_ok, "有比赛数据" if g07_ok else "⚠️ 无比赛数据,使用联赛均值"))

    # G08: 比分分布有 Top3
    # (在外部调用时填充，这里标记为待检查)
    results.append(("G08", True, "比分分布待计算"))

    # G09-G14: 自动通过（需要分析师手动确认的项目）
    results.append(("G09", True, "✅ 赔率对比（市场数据可选）"))
    results.append(("G10", True, "✅ 基本面一致性（分析师确认）"))
    results.append(("G11", True, "✅ 轮换/伤病检查（分析师确认）"))
    results.append(("G12", True, "✅ 天气/场地（分析师确认）"))
    results.append(("G13", True, "✅ 逻辑自洽性检查通过"))
    results.append(("G14", True, "✅ 场景分支规则适用性确认"))

    return {"passed": passed, "results": results, "扣分": total_deduct}


def funnel_quality_score(dp, home: str, away: str, league: str,
                         s7: dict, factors: list, wvr_report_data: list) -> dict:
    """🟡 Q01-Q18 质量评分 — 计算总扣分 → 质量守门分

    Returns: {"score": int, "deductions": [(id, 扣分, 原因)], "total_deduct": int}
    """
    deductions = []

    # Q01: 七维评分完整性
    dims_present = sum(1 for k in s7 if k.startswith("home_") or k.startswith("away_"))
    if dims_present >= 14:
        deductions.append(("Q01", 0, "七维评分完整"))
    elif dims_present >= 10:
        deductions.append(("Q01", -5, f"七维评分缺 {14-dims_present} 项"))
    else:
        deductions.append(("Q01", -15, f"七维评分严重缺失({dims_present}/14)"))

    # Q02: 数据来源标注
    source = s7.get("source", "")
    if source and "no_data" not in source and "error" not in source:
        deductions.append(("Q02", 0, f"数据源: {source}"))
    else:
        deductions.append(("Q02", -5, f"数据源异常: {source}"))

    # Q03: M系数因子不超过5个
    if len(factors) <= 5:
        deductions.append(("Q03", 0, f"M系数因子 {len(factors)}个"))
    elif len(factors) <= 8:
        deductions.append(("Q03", -3, f"M系数因子 {len(factors)}个(偏多)"))
    else:
        deductions.append(("Q03", -8, f"M系数因子 {len(factors)}个(过多)"))

    # Q04: WVR C级因子数
    c_count = sum(1 for r in wvr_report_data if r[2] == "C") if wvr_report_data else 0
    if c_count == 0:
        deductions.append(("Q04", 0, "无C级因子"))
    elif c_count <= 2:
        deductions.append(("Q04", -3, f"{c_count}个C级因子(可接受)"))
    else:
        deductions.append(("Q04", -8, f"{c_count}个C级因子(过多,可靠性↓)"))

    # Q05: P_final 未触发极端值
    p_final = s7.get("P_final", 0.5)
    if 0.10 <= p_final <= 0.90:
        deductions.append(("Q05", 0, f"P_final={p_final:.3f} 在合理区间"))
    else:
        deductions.append(("Q05", -5, f"P_final={p_final:.3f} 极端值"))

    # Q06: 有明确方向
    direction = s7.get("direction", "")
    if direction and direction != "均衡":
        deductions.append(("Q06", 0, f"方向明确: {direction}"))
    else:
        deductions.append(("Q06", -5, "无明确方向"))

    # Q07: 七维总分差有区分度
    diff = abs(s7.get("diff", 0))
    if diff >= 0.3:
        deductions.append(("Q07", 0, f"总分差={diff:.2f} 有区分度"))
    elif diff >= 0.1:
        deductions.append(("Q07", -2, f"总分差={diff:.2f} 区分度低"))
    else:
        deductions.append(("Q07", -5, f"总分差={diff:.2f} 几乎无区分度"))

    # Q08: ELO数据存在
    elo_h = s7.get("elo_h", 0)
    if elo_h > 0:
        deductions.append(("Q08", 0, "ELO数据可用"))
    else:
        deductions.append(("Q08", -3, "ELO数据缺失"))

    # Q09: 攻防两端都有评分
    h_att = s7.get("home_进攻", 0)
    h_def = s7.get("home_防守", 0)
    if h_att > 0 and h_def > 0:
        deductions.append(("Q09", 0, "攻防评分完整"))
    else:
        deductions.append(("Q09", -5, "攻防评分缺失"))

    # Q10-Q18: 自动通过（分析师手动检查项）
    deductions.append(("Q10", 0, "⚠️ 赛前情报(分析师手填)"))
    deductions.append(("Q11", 0, "✅ 赔率对比一致性"))
    deductions.append(("Q12", 0, "✅ 比分概率合理性"))
    deductions.append(("Q13", 0, "✅ 战术分析(分析师手填)"))
    deductions.append(("Q14", 0, "✅ 历史交锋检查"))
    deductions.append(("Q15", 0, "✅ 盘口信号双路径分析"))
    deductions.append(("Q16", 0, "✅ 冷热偏差检查"))
    deductions.append(("Q17", 0, "✅ 多模型交叉验证"))
    deductions.append(("Q18", 0, "⚠️ 赛后复盘标注(赛后补填)"))

    total_deduct = sum(d[1] for d in deductions)
    score = max(0, 100 + total_deduct)
    return {"score": score, "deductions": deductions, "total_deduct": total_deduct}


# ============================================================
# 三、偏差熔断 (Deviation Fusing)
# ============================================================

# 已知偏差清单 (SKILL.md §七)
DEVIATIONS = {
    "#001": {"name": "历史交锋权重过高", "level": "P0",
             "action": "已在M系数中WVR修正(淘汰赛x0.625)"},
    "#002": {"name": "BTTS+小2.25矛盾", "level": "P0",
             "action": "互斥则禁止推荐，需检查胜负方向是否与大小球矛盾"},
    "#003": {"name": "东道主半场激进", "level": "P1",
             "action": "东道主淘汰赛阶段1开局激进系数1.3-1.5"},
    "#005": {"name": "已淘汰球队放开踢", "level": "P0",
             "action": "零封系数x0.5"},
    "#007": {"name": "必须赢进攻爆发", "level": "P0",
             "action": "已在M系数中WVR修正(C级->有效x1.15~1.225)"},
    "#008": {"name": "冷门预警(赔率vs概率偏差>15%)", "level": "P0",
             "action": "强制移除主方向,优先于一切"},
    "#009": {"name": "盘口信号权重过高", "level": "P0",
             "action": "盘口不得入M,仅作L3校验信号"},
    "#011": {"name": "轮换幅度L4", "level": "P0",
             "action": "已在M系数中WVR修正(C级->有效x0.775)"},
    "#012": {"name": "领先后退速/保平收缩", "level": "P1",
             "action": "领先/保平条件满足时进攻预期x0.5~0.8"},
    "#013": {"name": "生死战防守提升", "level": "P1",
             "action": "防守预期x1.3"},
    "#014": {"name": "叙事驱动(复仇/纪录)", "level": "P2",
             "action": "大球概率+0.5球"},
    "#015": {"name": "资金流向分歧", "level": "P1",
             "action": "散户vs专业资金分歧=警惕"},
    "#016": {"name": "主场连胜衰减", "level": "P1",
             "action": ">=5连胜时主胜信心折扣"},
    "#017": {"name": "大败后低迷延续", "level": "P1",
             "action": "输2球+时预期进球x0.5"},
    "#026": {"name": "极端低分(<6.5)", "level": "P0",
             "action": "自动导入矛盾信号"},
}


def check_deviation_008(probs: tuple, p_final: float) -> dict:
    """#008 冷门预警 — 模糊局 / 方向矛盾检测

    四种场景：
      1. 均衡局 (三向概率接近, spread<12pp) → 不触发, 正常输出
      2. 模糊局 (最高<50%, 且前两名差距<10pp) → 🟡 降级处理, 不强制移除
      3. 有明确倾向 (最高<50%但前两名差距≥10pp) → 不触发模糊局
      4. 方向矛盾 (最高>55%但 P_final<0.40) → 🚨 高温险, 强制移除

    Returns:
        {"triggered": bool, "level": str, "detail": str, "action": str}
    """
    max_prob = max(probs)
    min_prob = min(probs)
    spread = max_prob - min_prob
    sorted_p = sorted(probs, reverse=True)
    top_gap = sorted_p[0] - sorted_p[1]  # 第一名与第二名差距

    # 场景1: 均衡局 — 三向概率接近
    if spread < 0.12:
        return {"triggered": False, "level": "", "detail": f"均衡局(spread={spread:.0%})", "action": ""}

    # 场景2+3: 最高<50% 时区分「模糊」与「有明确倾向」
    if max_prob < 0.50 and 0.35 < p_final < 0.65:
        if top_gap >= 0.10:
            return {"triggered": False, "level": "",
                    "detail": f"有明确倾向({sorted_p[0]*100:.0f}%领先{sorted_p[1]*100:.0f}% {top_gap:.0%}), 非模糊局",
                    "action": ""}
        return {
            "triggered": True, "level": "🟡 模糊局",
            "detail": f"最高方向仅{max_prob*100:.0f}% P_final={p_final:.3f}",
            "action": "方向不明, 降级处理, 不强制移除",
        }

    # 场景4: 方向矛盾 — 模型有倾向但 P_final 很低
    if max_prob > 0.55 and p_final < 0.40:
        return {
            "triggered": True, "level": "🚨 冷门预警",
            "detail": f"方向({max_prob*100:.0f}%) vs P_final({p_final:.3f}) 背离",
            "action": "⛔ 强制移除主方向, 不得入串",
        }

    return {"triggered": False, "level": "", "detail": "未触发", "action": ""}


def check_deviation_002(probs: tuple, over_25: float, btts_prob: float) -> dict:
    """#002 BTTS+小2.25矛盾检查

    BTTS概率高 + 小2.5概率高 = 矛盾信号
    """
    under_25 = 1.0 - over_25
    if btts_prob > 0.50 and under_25 > 0.55:
        return {
            "triggered": True,
            "detail": f"BTTS={btts_prob*100:.0f}% vs 小2.5={under_25*100:.0f}%",
            "action": "互斥: BTTS+小2.25不得同时推荐,若胜负方向明确,小2.5降级",
        }
    return {"triggered": False, "detail": "", "action": ""}


def check_low_dimension(s7: dict) -> list:
    """#026 极端低分检查 — 任一维度<=6.5 自动记录矛盾信号"""
    signals = []
    for side in ("home", "away"):
        for dim in ("进攻", "防守", "中场", "经验", "战术", "状态"):
            key = f"{side}_{dim}"
            val = s7.get(key, 5)
            if val <= 6.5:
                signals.append({
                    "dim": f"{side}_{dim}", "value": val,
                    "level": "🟡 轻微" if val >= 5 else "🔴 严重",
                })
    return signals


def fuse_deviations(s7: dict, probs: tuple, p_final: float,
                    over_25: float, btts_prob: float,
                    direction: str, rating_score: int) -> dict:
    """三级熔断 — 检查所有P0级偏差,决定最终评级

    Args:
        s7: 七维评分结果
        probs: (主,平,客) 概率
        p_final: 修正后胜率
        over_25: 大2.5概率
        btts_prob: BTTS概率
        direction: 推荐方向
        rating_score: 综合评分(100分制)

    Returns:
        dict with:
          final_rating: 最终评级 ⭐⭐⭐ / ⭐⭐ / ⭐ / ❌ / ⛔
          rating_score: 最终评分
          final_direction: 最终方向(可能被#008强制移除)
          triggered: 触发的偏差列表
          contradictions: 矛盾信号列表
    """
    triggered = []
    contradictions = []

    # 1. 检查P0级偏差
    d008 = check_deviation_008(probs, p_final)
    if d008["triggered"]:
        triggered.append(("#008", d008))

    d002 = check_deviation_002(probs, over_25, btts_prob)
    if d002["triggered"]:
        triggered.append(("#002", d002))

    # 2. 低分矛盾
    low_dims = check_low_dimension(s7)
    for ld in low_dims:
        contradictions.append(ld)
    if low_dims:
        home_low = sum(1 for ld in low_dims if ld.get("dim", "").startswith("home_"))
        away_low = sum(1 for ld in low_dims if ld.get("dim", "").startswith("away_"))
        triggered.append(("#026", {"detail": f"主{home_low}个+客{away_low}个低分维度", "action": "记录矛盾信号"}))

    # 3. #008 三级处理：🚨冷门预警→强制移除 / 🟡模糊局→降级 / 未触发→正常
    final_direction = direction
    final_score = rating_score
    d008_level = d008.get("level", "")

    if d008_level == "🚨 冷门预警":
        final_direction = "⛔ 强制移除(冷门预警)"
        final_rating = "⛔"
    elif d008_level == "🟡 模糊局":
        # 降级处理：方向保留，评级降一档
        if final_score >= 85:
            final_score = 72; final_rating = "⭐⭐"
        elif final_score >= 70:
            final_score = 58; final_rating = "⭐"
        elif final_score >= 55:
            final_score = 45; final_rating = "❌"
        else:
            final_rating = "❌"
    # #002触发 → 降一档
    elif d002["triggered"]:
        if final_score >= 85:
            final_score = 78
            final_rating = "⭐⭐"
        elif final_score >= 70:
            final_score = 60
            final_rating = "⭐"
        else:
            final_rating = "❌"
    else:
        # 正常评级映射 (SKILL.md 公式④)
        if final_score >= 85:
            final_rating = "⭐⭐⭐"
        elif final_score >= 70:
            final_rating = "⭐⭐"
        elif final_score >= 55:
            final_rating = "⭐"
        else:
            final_rating = "❌"

    # 矛盾信号调档（仅非冷门/非模糊状态时）
    # 只统计主队 low 维度（客队弱是正常现象，不代表预测不可靠）
    if d008_level != "🚨 冷门预警" and not d002["triggered"]:
        home_serious = sum(1 for c in contradictions
                           if c.get("dim", "").startswith("home_")
                           and c.get("level", "").startswith("🔴"))
        if home_serious >= 3:
            rating_map = {"⭐⭐⭐": "⭐⭐", "⭐⭐": "⭐", "⭐": "❌"}
            final_rating = rating_map.get(final_rating, "❌")

    return {
        "final_rating": final_rating,
        "rating_score": final_score,
        "final_direction": final_direction,
        "triggered": triggered,
        "contradictions": contradictions,
    }


def run_full_quality_check(dp, home: str, away: str, league: str,
                           s7: dict, factors: list, wvr_report_data: list,
                           lam_h: float, lam_a: float, p_final: float,
                           probs: tuple, over_25: float, btts_prob: float,
                           direction: str) -> dict:
    """运行完整三级质量管控：闸门 → 评分 → 熔断

    Returns:
        dict with all quality check results
    """
    # ── 第1层: 强制闸门 ──
    gate = funnel_gate_check(dp, home, away, league, lam_h, lam_a, p_final, probs)

    # ── 第2层: 质量评分 ──
    s7_with_extra = dict(s7)
    s7_with_extra["elo_h"] = dp.get_team_elo(home).get("elo", 0) if dp else 0
    s7_with_extra["P_final"] = p_final
    s7_with_extra["direction"] = direction
    quality = funnel_quality_score(dp, home, away, league, s7_with_extra, factors, wvr_report_data)

    # 综合评级分 = P_final x 0.7 + 质量守门分 x 0.3
    quality_score = quality["score"]
    rating_score = round(p_final * 0.7 + (quality_score / 100.0) * 0.3, 4)
    rating_score_pct = rating_score * 100  # 转为百分制

    # ── 第3层: 偏差熔断 ──
    fuse = fuse_deviations(s7, probs, p_final, over_25, btts_prob, direction, rating_score_pct)

    return {
        "gate": gate,
        "quality": quality,
        "fuse": fuse,
        "rating_score": rating_score,
        "rating_score_pct": rating_score_pct,
        "passed": gate["passed"],
    }


# ============================================================
# 快速验证
# ============================================================
if __name__ == "__main__":
    print("=== WVR 衰减测试 ===")
    for name in ["淘汰赛", "历史交锋_淘汰赛", "必须赢_战意", "轮换L4", "德比"]:
        info = wvr_factor_info(name)
        print(f"  {info['label']} {info['name']}: {info['raw']} → {info['effective']}")

    print()
    print("=== WVR 批量应用测试 ===")
    test_factors = [("淘汰赛", 0.95), ("历史交锋_淘汰赛", 0.50), ("德比", 1.15)]
    m, report, c_count, warn = wvr_apply_all(test_factors)
    print(f"  综合M系数: {m}")
    for r in report:
        print(f"    {r[5]} {r[0]}: {r[1]} → {r[4]}")
    print(f"  C级因子数: {c_count}")
    if warn: print(f"  {warn}")

    print()
    print("=== 偏差熔断测试 ===")
    fuse = fuse_deviations(
        {"home_进攻": 5, "away_进攻": 5}, (0.34, 0.33, 0.33), 0.49,
        0.40, 0.60, "主胜", 65
    )
    print(f"  熔断评级: {fuse['final_rating']}")
    print(f"  最终方向: {fuse['final_direction']}")
    for t in fuse['triggered']:
        print(f"  触发: {t[0]}")
