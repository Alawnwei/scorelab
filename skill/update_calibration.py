#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准参数自动更新工具 v2.0
从 predictions_db.json 读取数据，计算最优 Platt Scaling 和 Temperature Scaling 参数，
更新到 predict.py 的 TEMP_T。

用法:
  python skill/update_calibration.py          # 查看当前校准状态
  python skill/update_calibration.py --apply  # 计算并应用新参数
  python skill/update_calibration.py --auto   # 数据≥20条时自动更新
"""
import sys, json, math, os, re
from datetime import datetime

def p(text):
    try:
        print(str(text).encode("utf-8", errors="replace").decode("gbk", errors="replace"))
    except:
        print(str(text))

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_FILE = os.path.join(BASE_DIR, "数据缓存", "predictions_db.json")
PREDICT_FILE = os.path.join(BASE_DIR, "skill", "predict.py")
DATAFPC_FILE = os.path.join(BASE_DIR, "skill", "datafc_provider.py")


def _assign_split(pred_id: str) -> str:
    """确定性分桶（与 predict.py 保持一致）"""
    _h = hash(pred_id) & 0xFFFF
    if _h % 10 < 6:
        return "train"
    elif _h % 10 < 8:
        return "calib"
    else:
        return "holdout"


def load_valid(split: str = "calib"):
    """加载有效校准数据 — 按分桶筛选

    v8.5: 默认只加载 calib 分桶，避免数据泄漏。
    train → 参数训练（α/θ），calib → 温度/Platt校准，holdout → 最终验证。

    Args:
        split: "train" | "calib" | "holdout" | "all"
    """
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
    valid = []
    excluded = {"inferred_neutral": 0, "p05_nodir": 0, "wrong_split": 0}
    for p in db["predictions"]:
        if p["p_final"] is None: continue
        if p["result"]["status"] != "matched": continue
        if p["result"]["correct"] is None: continue
        source = p.get("p_final_source", "")
        if source == "inferred_neutral":
            excluded["inferred_neutral"] += 1
            continue
        if p["p_final"] == 0.500:
            excluded["p05_nodir"] += 1
            continue
        # 分桶筛选
        if split != "all":
            _pid = p.get("id", "")
            if _assign_split(_pid) != split:
                excluded["wrong_split"] += 1
                continue
        valid.append(p)
    return valid, excluded


# ── 校准指标计算 ──

def calc_brier(valid, transform_fn):
    """计算 Brier Score = 平均 (P_cal - outcome)^2"""
    n = len(valid)
    if n == 0: return 0
    brier = 0
    for rec in valid:
        p_cal = transform_fn(rec["p_final"])
        outcome = 1 if rec["result"]["correct"] else 0
        brier += (p_cal - outcome) ** 2
    return round(brier / n, 4)


def calc_logloss(valid, transform_fn):
    """计算 Log Loss"""
    n = len(valid)
    if n == 0: return 0
    ll = 0
    for rec in valid:
        p_cal = transform_fn(rec["p_final"])
        p_cal = max(1e-10, min(1 - 1e-10, p_cal))
        outcome = 1 if rec["result"]["correct"] else 0
        ll += -math.log(p_cal) if outcome else -math.log(1 - p_cal)
    return round(ll / n, 4)


# ── 当前原始 Brier（不做任何校准）──

def raw_brier(valid):
    return calc_brier(valid, lambda pf: pf)


# ── Platt Scaling (Platt, 1999) ──

def platt_transform(pf, a, b):
    logit = math.log(pf / (1 - pf)) if 0 < pf < 1 else (math.log(0.001/0.999) if pf <= 0 else math.log(0.999/0.001))
    return 1 / (1 + math.exp(-(a * logit + b)))


def find_best_platt(valid):
    """网格搜索最优 Platt 参数 (a, b)"""
    best_brier = 999
    best_ll = 999
    best_a, best_b = 1.0, 0.0
    for a in [i*0.05 for i in range(0, 41)]:       # 0.0 ~ 2.0
        for b in [i*0.05 for i in range(-40, 41)]:  # -2.0 ~ 2.0
            brier = 0
            logloss = 0
            for rec2 in valid:
                p_cal = platt_transform(rec2["p_final"], a, b)
                p_cal = max(1e-10, min(1-1e-10, p_cal))
                outcome = 1 if rec2["result"]["correct"] else 0
                brier += (p_cal - outcome)**2
                logloss += -math.log(p_cal) if outcome else -math.log(1-p_cal)
            brier /= len(valid)
            logloss /= len(valid)
            if brier < best_brier - 0.0001 or (abs(brier - best_brier) < 0.0001 and logloss < best_ll):
                best_brier = brier
                best_ll = logloss
                best_a, best_b = round(a, 2), round(b, 2)
    return best_a, best_b, round(best_brier, 4), round(best_ll, 4)


# ── Temperature Scaling ──

def temp_transform(pf, t):
    pt = pf ** (1.0 / t)
    qt = (1.0 - pf) ** (1.0 / t)
    return pt / (pt + qt)


def find_best_temperature(valid):
    """网格搜索最优温度缩放 T"""
    best_brier = 999
    best_t = 1.0
    for t in [i*0.05 for i in range(4, 81)]:  # 0.20 ~ 4.00
        brier = calc_brier(valid, lambda pf, tt=t: temp_transform(pf, tt))
        if brier < best_brier:
            best_brier = brier
            best_t = round(t, 2)
    # 再 fine-tune
    for t in [round(best_t + i*0.01, 2) for i in range(-10, 11)]:
        if t <= 0: continue
        brier = calc_brier(valid, lambda pf, tt=t: temp_transform(pf, tt))
        if brier < best_brier:
            best_brier = brier
            best_t = t
    return best_t, round(best_brier, 4)


# ── 可靠性曲线数据（校准图的关键输入） ──

def calibration_curve_data(valid, transform_fn, bins=10):
    """生成可靠性曲线数据: [(bin_center, accuracy, avg_prob, count), ...]"""
    sorted_p = sorted(valid, key=lambda x: transform_fn(x["p_final"]))
    n = len(sorted_p)
    bin_size = max(1, n // bins)
    curve = []
    for i in range(0, n, bin_size):
        batch = sorted_p[i:i+bin_size]
        avg_prob = sum(transform_fn(p["p_final"]) for p in batch) / len(batch)
        acc = sum(1 for p in batch if p["result"]["correct"]) / len(batch)
        curve.append((round(avg_prob, 3), round(acc, 3), len(batch)))
    return curve


# ── 更新 predict.py ──

def update_predict_temp(t):
    """更新 predict.py 中的 TEMP_T"""
    with open(PREDICT_FILE, "r", encoding="utf-8") as f:
        content = f.read()

    content = re.sub(
        r'TEMP_T\s*=\s*[\d.]+[^#\n]*',
        f'TEMP_T = {t:.2f}  # 校准最优值 ({datetime.now().strftime("%Y-%m-%d")})',
        content
    )

    with open(PREDICT_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    p(f"  ✅ 已更新 predict.py TEMP_T = {t:.2f}")


def read_current_alpha():
    """读取 datafc_provider.py 中当前的 ALPHA_LOGISTIC 值"""
    try:
        with open(DATAFPC_FILE, "r", encoding="utf-8") as f:
            m = re.search(r'ALPHA_LOGISTIC\s*=\s*([\d.]+)', f.read())
            if m: return float(m.group(1))
    except: pass
    return 0.15


def update_alpha(a):
    """更新 datafc_provider.py 中的 ALPHA_LOGISTIC"""
    with open(DATAFPC_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    content = re.sub(
        r'ALPHA_LOGISTIC\s*=\s*[\d.]+[^#\n]*',
        f'ALPHA_LOGISTIC = {a:.4f}  # 校准最优值 ({datetime.now().strftime("%Y-%m-%d")})',
        content
    )
    with open(DATAFPC_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    p(f"  ✅ 已更新 datafc_provider.py ALPHA_LOGISTIC = {a:.4f}")


def find_best_alpha(valid, fixed_t=None):
    """网格搜索最优 α（Logistic 斜率）

    使用已有 score_diff 和 M_coef 记录来重算 P_base → P_final 路径。
    对无 score_diff 的旧记录，用当前 α 反估 score_diff。
    """
    if not valid:
        return 0.15, 999

    # 先确定用什么 T
    if fixed_t is None:
        fixed_t, _ = find_best_temperature(valid)

    best_brier = 999
    best_a = 0.15
    for a_candidate in [i*0.01 for i in range(3, 101)]:  # 0.03 ~ 1.00
        brier = 0
        count = 0
        for rec in valid:
            # 优先使用存储的 score_diff
            sd = rec.get("score_diff")
            mc = rec.get("M_coef", 1.0)

            if sd is not None:
                # 有 score_diff: 可重算 P_base
                p_base = 1.0 / (1.0 + math.exp(-a_candidate * sd))
                # 重算 P_final (无T): odds ratio * M
                odds_r = p_base / (1 - p_base) * mc
                pf_raw = odds_r / (1 + odds_r)
                pf_raw = max(0.01, min(0.99, pf_raw))
            else:
                # 无 score_diff: 无法重算，用记录的 p_final 反向推导
                # 这是近似处理
                pf_raw = rec["p_final"]

            # 应用温度缩放
            p_cal = temp_transform(pf_raw, fixed_t)
            p_cal = max(1e-10, min(1-1e-10, p_cal))
            outcome = 1 if rec["result"]["correct"] else 0
            brier += (p_cal - outcome) ** 2
            count += 1

        brier /= count
        if brier < best_brier - 0.0001:
            best_brier = brier
            best_a = round(a_candidate, 4)

    return best_a, round(best_brier, 4)


# ── θ MLE 拟合 ──

def _show_theta_fit(valid):
    """显示 θ 参数 MLE 拟合状态（按联赛分组）"""
    from collections import defaultdict
    import math

    # 按联赛分组
    by_league = defaultdict(list)
    for rec in valid:
        league = rec.get("league", "unknown")
        lam_h = rec.get("lam_h")
        lam_a = rec.get("lam_a")
        r = rec.get("result", {})
        sh = r.get("score_home")
        sa = r.get("score_away")
        if lam_h is None or lam_a is None or sh is None or sa is None:
            continue
        by_league[league].append({
            "lam_h": lam_h, "lam_a": lam_a,
            "goals": int(sh) + int(sa),
        })

    if not by_league:
        return

    p(f"\n  ── θ 负二项分散度 (MLE 拟合) ──")
    p(f"  {'联赛':<15} {'当前θ':<8} {'MLE最优θ':<10} {'样本':<6} {'似然改善':<10}")
    p(f"  {'-'*55}")

    # 导入 predict 的 THETA_MAP
    import predict as pr

    for league, matches in sorted(by_league.items()):
        n = len(matches)
        if n < 3:
            continue

        current_theta = pr.THETA_MAP.get(league, 8)

        # 网格搜索最优 θ（用于显示，不自动更新）
        best_theta = current_theta
        best_ll = -999
        for theta in range(1, 21):
            log_lik = 0
            for m in matches:
                lam = m["lam_h"] + m["lam_a"]
                k = m["goals"]
                if lam <= 0:
                    continue
                # 负二项对数似然
                p = theta / (theta + lam)
                ll_k = math.lgamma(k + theta) - math.lgamma(k + 1) - math.lgamma(theta)
                ll_k += theta * math.log(p) + k * math.log(1 - p)
                log_lik += ll_k
            if log_lik > best_ll:
                best_ll = log_lik
                best_theta = theta

        improve = (best_ll - (-999)) / abs(best_ll) * 100 if best_ll > -999 else 0
        tag = "✅" if best_theta == current_theta else "🟡 可调优"
        p(f"  {tag} {league:<13s} {current_theta:<8d} {best_theta:<10d} {n:<6d}")


# ── 参数状态总览 ──

def _show_all_params():
    """显示所有可调优参数及其当前值/校准状态"""
    import predict as pr
    import datafc_provider as dp

    p(f"\n  ── 参数校准状态 ──")
    p(f"  {'参数':<25} {'当前值':<12} {'校准状态':<12} {'建议'}")
    p(f"  {'─'*65}")

    # 1. Logistic α
    p(f"  {'Logistic α':<25} {dp.ALPHA_LOGISTIC:<12.4f} {'已参数化✅':<12} 需>5条score_diff")

    # 2. Temperature T
    # 从 predict.py 源码读取 TEMP_T
    _temp_val = 4.08
    try:
        with open(PREDICT_FILE, "r") as _f:
            _m = re.search(r'TEMP_T\s*=\s*([\d.]+)', _f.read())
            if _m: _temp_val = float(_m.group(1))
    except: pass
    p(f"  {'Temperature T':<25} {_temp_val:<12.2f} {'数据驱动✅':<12} --apply自动优化")

    # 3. θ 负二项分散度
    theta_range = f"{min(pr.THETA_MAP.values())}-{max(pr.THETA_MAP.values())}"
    p(f"  {'θ(分联赛)':<25} {theta_range:<12} {'手动设定🟡':<12} --params查看MLE")

    # 4. ELO adjust 系数
    _elo = getattr(dp, 'ELO_ADJUST_FACTOR', None)
    if _elo is not None:
        p(f"  {'ELO_ADJUST_FACTOR':<25} {_elo:<12.2f} {'已参数化✅':<12} 需>5条score_diff")
    else:
        p(f"  {'ELO_ADJUST_FACTOR':<25} {'0.20(硬编码)':<12} {'待参数化❌':<12}")

    # 5. adjust_lambda 权重
    p(f"  {'LAMBDA_ADJUST_WEIGHT':<25} {pr.LAMBDA_ADJUST_WEIGHT:<12.2f} {'已参数化✅':<12} 需>5条score_diff")

    # 6. 七维评分权重
    p(f"  {'七维评分权重':<25} {'20/20/15/15/15/10/5':<12} {'经验值🟡':<12} --simulate验证精简")


# ── 主入口 ──

def main():
    import argparse
    parser = argparse.ArgumentParser(description="校准参数自动更新")
    parser.add_argument("--apply", action="store_true", help="计算并应用新参数")
    parser.add_argument("--auto", action="store_true", help="数据>=20条时自动更新")
    parser.add_argument("--report", action="store_true", help="生成校准报告（不更新参数）")
    parser.add_argument("--params", action="store_true", help="查看所有参数校准状态")
    args = parser.parse_args()

    valid, excluded = load_valid()
    n = len(valid)
    total = n + excluded["inferred_neutral"] + excluded["p05_nodir"]

    # ── --params 模式：仅显示参数状态 ──
    if args.params:
        p("=" * 60)
        p("  参数校准状态")
        p("=" * 60)
        _show_all_params()
        if n >= 3:
            _show_theta_fit(valid)
        return

    p("=" * 60)
    p("  概率校准诊断 v2.0")
    p("=" * 60)
    p(f"\n  数据库总记录: {total}")
    p(f"  排除 legacy 占位: {excluded['inferred_neutral']} (inferred_neutral) + {excluded['p05_nodir']} (p=0.5)")
    p(f"  有效校准数据:  {n} 条")
    p(f"  其中正确:      {sum(1 for rec2 in valid if rec2['result']['correct'])}/{n}")
    p(f"  原始 Brier:    {raw_brier(valid):.4f} (0=完美, 0.25=随机)")

    if n < 5:
        p("\n⚠️ 样本太少(<5)，无法进行有意义校准")
        return

    # ── 查询当前 TEMP_T ──
    cur_temp = 1.60
    try:
        with open(PREDICT_FILE, "r") as f:
            m = re.search(r'TEMP_T\s*=\s*([\d.]+)', f.read())
            if m: cur_temp = float(m.group(1))
    except: pass

    # ── 计算全部指标 ──
    best_t, best_t_brier = find_best_temperature(valid)
    best_a, best_b, best_p_brier, best_p_ll = find_best_platt(valid)

    cur_t_brier = calc_brier(valid, lambda pf: temp_transform(pf, cur_temp))

    p(f"\n  ── 温度缩放 (Temperature Scaling) ──")
    p(f"  当前 T = {cur_temp:.2f} → Brier = {cur_t_brier:.4f}")
    p(f"  最优 T = {best_t:.2f} → Brier = {best_t_brier:.4f}")
    t_improve = (cur_t_brier - best_t_brier) / max(cur_t_brier, 0.001) * 100
    p(f"  改善: {t_improve:+.1f}%")
    p(f"  最优 LogLoss: {calc_logloss(valid, lambda pf: temp_transform(pf, best_t)):.4f}")

    # ── α (Logistic 斜率) 搜索 ──
    cur_alpha = read_current_alpha()
    # 统计多少条记录有 score_diff
    scorediff_count = sum(1 for rec2 in valid if rec2.get("score_diff") is not None)
    if scorediff_count >= 5:
        best_a, best_a_brier = find_best_alpha(valid, fixed_t=best_t)
        cur_a_brier = find_best_alpha(valid, fixed_t=best_t)[1]  # reuse
        # 用当前 α 重新计算 Brier 做对比
        cur_a_brier = 0
        count_a = 0
        for rec3 in valid:
            sd = rec3.get("score_diff")
            mc = rec3.get("M_coef", 1.0)
            if sd is not None:
                p_base = 1.0 / (1.0 + math.exp(-cur_alpha * sd))
                odds_r = p_base / (1 - p_base) * mc
                pf_raw = odds_r / (1 + odds_r)
                pf_raw = max(0.01, min(0.99, pf_raw))
                p_cal = temp_transform(pf_raw, best_t)
                p_cal = max(1e-10, min(1-1e-10, p_cal))
                outcome = 1 if rec3["result"]["correct"] else 0
                cur_a_brier += (p_cal - outcome) ** 2
                count_a += 1
        cur_a_brier = round(cur_a_brier / count_a, 4) if count_a > 0 else 999
        a_improve = (cur_a_brier - best_a_brier) / max(cur_a_brier, 0.001) * 100 if cur_a_brier < 999 else 0

        p(f"\n  ── Logistic 斜率 α ──")
        p(f"  当前 α = {cur_alpha:.4f} ({scorediff_count}条有score_diff)")
        p(f"  最优 α = {best_a:.4f} → Brier = {best_a_brier:.4f}")
        if cur_a_brier < 999:
            p(f"  当前 α Brier = {cur_a_brier:.4f}, 改善 = {a_improve:+.1f}%")
    else:
        best_a = cur_alpha
        best_a_brier = None
        p(f"\n  ── Logistic 斜率 α ──")
        p(f"  当前 α = {cur_alpha:.4f}")
        p(f"  ℹ️ 需要 {5-scorediff_count} 条更多含 score_diff 的记录才能优化 α")

    p(f"\n  ── Platt Scaling ──")
    p(f"  最优 A = {best_a:.2f}, B = {best_b:.2f}")
    p(f"  Brier = {best_p_brier:.4f}, LogLoss = {best_p_ll:.4f}")

    p(f"\n  ── 可靠性曲线 (Temperature T={best_t:.2f}) ──")
    curve = calibration_curve_data(valid, lambda pf: temp_transform(pf, best_t), bins=5)
    for avg_p, acc, cnt in curve:
        bar = "█" * int(acc * 20) + "░" * int((1-acc) * 20)
        p(f"    P≈{avg_p:.2f} | 实际{acc:.0%} | {bar} (n={cnt})")

    # ── 报告模式额外输出 ──
    # ── θ MLE 拟合（按联赛） ──
    if args.report or args.apply:
        _show_theta_fit(valid)

    if args.report:
        p(f"\n{'='*60}")
        p(f"  详细校准报告")
        p(f"{'='*60}")

        # 按 P_final 分桶的详细校准表
        p(f"\n  ── 概率分段校准明细 (原始 P_final) ──")
        p(f"  {'概率区间':<12} {'场次':<6} {'正确':<6} {'实际胜率':<10} {'预期胜率':<10} {'偏差':<10}")
        p(f"  {'-'*55}")
        for lo, hi in [(0.0,0.3), (0.3,0.4), (0.4,0.45), (0.45,0.48), (0.48,0.52),
                       (0.52,0.55), (0.55,0.6), (0.6,0.7), (0.7,1.0)]:
            batch = [rec for rec in valid if lo <= rec["p_final"] < hi]
            if not batch: continue
            n_b = len(batch)
            c_b = sum(1 for p in batch if p["result"]["correct"])
            actual = c_b / n_b * 100
            expected = (lo + hi) / 2 * 100
            dev = actual - expected
            tag = "高估🔴" if dev < -10 else ("低估🟢" if dev > 10 else "合理✅")
            p(f"  [{lo:.2f}-{hi:.2f})  {n_b:<6} {c_b:<6} {actual:<8.1f}% {expected:<8.1f}% {dev:<+7.1f}pp {tag}")

        # 校准曲线详细数据
        p(f"\n  ── 可靠性曲线 (经 T={best_t:.2f} 校准后) ──")
        curve = calibration_curve_data(valid, lambda pf: temp_transform(pf, best_t), bins=max(5, n//3))
        for avg_p, acc, cnt in curve:
            bar_len = int(acc * 25)
            bar = "█" * bar_len + "░" * (25 - bar_len)
            gap = acc - avg_p
            gap_tag = "" if abs(gap) < 0.05 else ("↑" if gap > 0 else "↓")
            p(f"  P≈{avg_p:.3f} | 实际{acc:.3f} | {bar} | n={cnt} {gap_tag}")

        # 每条记录明细
        p(f"\n  ── 校准数据集明细 ──")
        p(f"  {'主队':12s} {'客队':12s} {'P_final':8s} {'方向':16s} {'结果':6s} {'校正后P':8s}")
        p(f"  {'-'*65}")
        for p_rec in sorted(valid, key=lambda x: x["p_final"]):
            pf = p_rec["p_final"]
            p_cal = temp_transform(pf, best_t)
            corr = "✅" if p_rec["result"]["correct"] else "❌"
            p(f"  {p_rec['home'][:10]:12s} {p_rec['away'][:10]:12s} {pf:<8.4f} {p_rec.get('direction','?'):16s} {corr:6s} {p_cal:<8.4f}")

        # 汇总建议
        p(f"\n  ── 校准建议 ──")
        if n < 30:
            p(f"  ⚠️ 样本仅{n}条, 校准结果仅供参考。建议积累至50+条再硬应用。")
        if abs(1 - best_t / cur_temp) > 0.1:
            p(f"  💡 当前T={cur_temp:.2f} vs 最优T={best_t:.2f}差异>10%，可考虑 --apply")
        p(f"  📊 原始Brier={raw_brier(valid):.4f} (0=完美)")
        p(f"  📊 Brier改善潜力: {raw_brier(valid):.4f} → {best_t_brier:.4f} (T缩放后)")
        return

    # ── 决策：是否更新 ──
    should_apply = args.apply or (args.auto and n >= 20)
    if should_apply:
        updated_anything = False

        # 更新温度 T
        if abs(best_t - cur_temp) >= 0.05 and best_t_brier < cur_t_brier - 0.005:
            update_predict_temp(best_t)
            p(f"  温度缩放: {cur_temp:.2f} → {best_t:.2f}")
            updated_anything = True

        # 更新 α（仅当有足够 score_diff 数据时）
        if scorediff_count >= 5 and best_a_brier is not None and cur_a_brier < 999:
            if abs(best_a - cur_alpha) >= 0.01 and best_a_brier < cur_a_brier - 0.005:
                update_alpha(best_a)
                p(f"  Logistic α: {cur_alpha:.4f} → {best_a:.4f}")
                updated_anything = True

        if not updated_anything:
            p(f"\n  ℹ️ 改善不足，保持当前参数")
    else:
        p(f"\n  建议: 累积到20+条再 --apply (当前 {n} 条)")
        if abs(best_t - cur_temp) >= 0.1:
            p(f"  提示: 最优 T={best_t:.2f} 与当前 T={cur_temp:.2f} 差异明显，可考虑更新")


if __name__ == "__main__":
    main()
