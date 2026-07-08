#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模型准确率仪表盘 v1.0

系统单命令查看自身准确率：
  - 总体命中率 (方向/Brier/LogLoss)
  - 校准曲线 (P_final 分段实际胜率)
  - ⭐ 评级校准 (各评级的实际胜率)
  - 联赛迁移偏差
  - 时间序列趋势 (最近 N 场滚动准确率)

用法:
  python skill/accuracy_report.py                 # 完整报告
  python skill/accuracy_report.py --summary       # 仅汇总
  python skill/accuracy_report.py --trend         # 趋势图
"""
import sys, os, json, math
from datetime import datetime, timedelta
from collections import defaultdict, Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")


def safe_print(text):
    try:
        print(text)
    except:
        try:
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))


# ============================================================
# 核心指标计算
# ============================================================

def brier_score(records):
    """Brier Score: Σ(P_pred - outcome)² / N, 0=完美 0.25=随机"""
    n = len(records)
    if n == 0:
        return 0
    bs = sum((r["p_pred"] - r["outcome"]) ** 2 for r in records)
    return round(bs / n, 4)


def log_loss(records):
    """Log Loss: 惩罚高确信错误, 越小越好"""
    n = len(records)
    if n == 0:
        return 0
    ll = 0
    for r in records:
        p = max(1e-10, min(1 - 1e-10, r["p_pred"]))
        ll += -math.log(p) if r["outcome"] == 1 else -math.log(1 - p)
    return round(ll / n, 4)


def expected_vs_actual(records):
    """分段校准: [P区间] → 实际胜率 vs 预测均值"""
    segments = [
        (0.0, 0.30, "[0.00-0.30)"), (0.30, 0.40, "[0.30-0.40)"),
        (0.40, 0.45, "[0.40-0.45)"), (0.45, 0.48, "[0.45-0.48)"),
        (0.48, 0.52, "[0.48-0.52]"), (0.52, 0.55, "(0.52-0.55]"),
        (0.55, 0.60, "(0.55-0.60]"), (0.60, 0.70, "(0.60-0.70]"),
        (0.70, 1.0,  "(0.70-1.00]"),
    ]
    results = []
    for lo, hi, label in segments:
        batch = [r for r in records if lo <= r["p_pred"] < hi]
        if not batch:
            continue
        n = len(batch)
        correct = sum(1 for r in batch if r["outcome"])
        actual_rate = correct / n
        avg_pred = sum(r["p_pred"] for r in batch) / n
        gap = actual_rate - avg_pred
        results.append({
            "segment": label, "n": n, "correct": correct,
            "actual": round(actual_rate, 3),
            "predicted": round(avg_pred, 3),
            "gap_pp": round(gap * 100, 1),
            "severity": "🔴" if abs(gap) > 0.15 else ("🟡" if abs(gap) > 0.05 else "🟢"),
        })
    return results


# ============================================================
# 加载 & 对齐数据
# ============================================================

def load_records():
    """从 predictions_db.json 加载所有可用的准确率数据

    每条记录包含:
      p_pred: 预测概率 (P_final, 0-1)
      outcome: 实际结果 (1=正确, 0=错误)
      direction: 预测方向
      league: 联赛
      confidence: ⭐评级
      date: 日期
    """
    path = os.path.join(CACHE_DIR, "predictions_db.json")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        db = json.load(f)

    records = []
    for p in db.get("predictions", []):
        r = p.get("result", {})
        if r.get("status") != "matched":
            continue
        correct = r.get("correct")
        if correct is None:
            continue
        records.append({
            "p_pred": p.get("p_final", 0.5),
            "outcome": 1 if correct else 0,
            "correct": correct,
            "direction": p.get("direction", ""),
            "league": p.get("league", "unknown"),
            "confidence": p.get("confidence", ""),
            "date": p.get("date", ""),
            "home": p.get("home", ""),
            "away": p.get("away", ""),
        })

    return records


# ============================================================
# 报告生成
# ============================================================

def build_report(records, mode="full"):
    """构建准确率报告"""
    n = len(records)
    if n == 0:
        return "无已结算记录"

    correct = sum(1 for r in records if r["correct"])
    acc = correct / n

    lines = []
    lines.append("=" * 65)
    lines.append(f"  模型准确率仪表盘 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    lines.append("=" * 65)

    # ── K1: 总体指标 ──
    brier = brier_score(records)
    ll = log_loss(records)
    brier_grade = "🏆" if brier < 0.15 else ("✅" if brier < 0.22 else ("⚠️" if brier < 0.25 else "🔴"))
    ll_grade = "🏆" if ll < 0.50 else ("✅" if ll < 0.65 else ("⚠️" if ll < 0.69 else "🔴"))

    lines.append(f"\n📊 K1 — 总体指标 ({n} 场)")
    lines.append(f"{'─' * 40}")
    lines.append(f"  方向准确率:  {correct}/{n} = {acc:.1%}")
    lines.append(f"  Brier Score: {brier:.4f}  {brier_grade} (0=完美, 0.25=随机)")
    lines.append(f"  Log Loss:    {ll:.4f}  {ll_grade} (越小越好)")
    if acc > 0.65:
        lines.append(f"  评级:  🏆 模型优于随机（需校准验证）")
    elif acc > 0.5:
        lines.append(f"  评级:  ⚠️ 模型略优于随机")
    else:
        lines.append(f"  评级:  🔴 模型低于随机")

    if mode == "summary":
        return "\n".join(lines)

    # ── K2: 校准曲线 ──
    lines.append(f"\n📈 K2 — 校准曲线 (P_final 分段实际胜率)")
    lines.append(f"{'─' * 60}")
    lines.append(f"  {'概率区间':<14} {'场次':<6} {'正确':<6} {'实际胜率':<10} {'预测均值':<10} {'偏差':<8}")
    lines.append(f"  {'─' * 58}")

    cal_results = expected_vs_actual(records)
    total_gap = 0
    for cr in cal_results:
        bar = "█" * int(cr["actual"] * 20) + "░" * (20 - int(cr["actual"] * 20))
        lines.append(f"  {cr['segment']:<14} {cr['n']:<6} {cr['correct']:<6} {cr['actual']:<7.1%}  {cr['predicted']:<7.1%}  {cr['gap_pp']:<+6.1f}pp {cr['severity']}")
        total_gap += cr["gap_pp"] ** 2

    # 校准质量分
    cal_rmse = round(math.sqrt(total_gap / max(len(cal_results), 1)), 1)
    cal_grade = "🏆" if cal_rmse < 5 else ("✅" if cal_rmse < 10 else ("⚠️" if cal_rmse < 15 else "🔴"))
    lines.append(f"  {'─' * 58}")
    lines.append(f"  校准 RMSE: {cal_rmse:.1f}pp  {cal_grade} (越小=校准越好)")

    # ── K3: ⭐ 评级校准 ──
    lines.append(f"\n⭐ K3 — 评级校准")
    lines.append(f"{'─' * 55}")
    lines.append(f"  {'评级':<10} {'场次':<6} {'正确':<6} {'实际胜率':<10} {'隐含胜率':<10} {'校准因子':<10}")
    lines.append(f"  {'─' * 52}")

    RATING_IMPLIED = {"⭐⭐⭐": 0.85, "⭐⭐": 0.70, "⭐": 0.55}
    by_rating = defaultdict(lambda: {"n": 0, "c": 0})
    for r in records:
        conf = r["confidence"]
        by_rating[conf]["n"] += 1
        if r["correct"]:
            by_rating[conf]["c"] += 1

    for rating in ["⭐⭐⭐", "⭐⭐", "⭐", ""]:
        data = by_rating.get(rating)
        if not data or data["n"] == 0:
            continue
        rate = data["c"] / data["n"]
        implied = RATING_IMPLIED.get(rating, 0.55)
        cal = rate / implied if implied > 0 else 0
        if cal < 0.80:
            grade = "高估🔴"
        elif cal > 1.15:
            grade = "低估🟢"
        else:
            grade = "合理✅"
        lines.append(f"  {rating if rating else '无':<10} {data['n']:<6} {data['c']:<6} {rate:<7.1%}  {implied:<7.1%}  {cal:<9.2f} {grade}")

    # ── K4: 联赛迁移偏差 ──
    lines.append(f"\n🌍 K4 — 联赛准确率")
    lines.append(f"{'─' * 45}")
    by_league = defaultdict(lambda: {"n": 0, "c": 0})
    for r in records:
        l = r["league"] if r["league"] else "未知"
        by_league[l]["n"] += 1
        if r["correct"]:
            by_league[l]["c"] += 1

    overall = correct / n
    for league, data in sorted(by_league.items(), key=lambda x: -x[1]["n"]):
        rate = data["c"] / data["n"]
        dev = (rate - overall) * 100
        tag = "✅" if abs(dev) < 10 else ("🟡" if abs(dev) < 20 else "⚠️")
        lines.append(f"  {tag} {league:<12s} {data['n']:<4d}场 {data['c']}/{data['n']} = {rate:.0%} (vs总体{dev:+.0f}pp)")

    # ── K5: 滚动准确率趋势 ──
    if mode in ("full", "trend"):
        lines.append(f"\n📉 K5 — 准确率趋势 (每10场滚动)")
        lines.append(f"{'─' * 55}")
        sorted_recs = sorted(records, key=lambda x: x["date"])
        window = 10
        for i in range(0, len(sorted_recs), max(1, window // 2)):
            batch = sorted_recs[i:i + window]
            if len(batch) < 5:
                continue
            w_correct = sum(1 for r in batch if r["correct"])
            w_rate = w_correct / len(batch)
            dates = batch[0]["date"][-5:] + "~" + batch[-1]["date"][-5:]
            bar = "🟢" * int(w_rate * 10) + "🔴" * (10 - int(w_rate * 10))
            lines.append(f"  {dates:<15s} {bar} {w_rate:.0%} ({w_correct}/{len(batch)})")

    # ── K6: 错误最多的队伍 ──
    lines.append(f"\n❌ K6 — 错误最频繁的队伍")
    lines.append(f"{'─' * 40}")
    errors_by_team = Counter()
    for r in records:
        if not r["correct"]:
            errors_by_team[r["home"]] += 1
            errors_by_team[r["away"]] += 1
    for team, cnt in errors_by_team.most_common(8):
        lines.append(f"  {team:<12s} {cnt} 次错误")

    lines.append(f"\n{'=' * 65}")
    lines.append(f"  报告结束 (数据源: predictions_db.json)")
    lines.append(f"{'=' * 65}")

    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="模型准确率仪表盘")
    parser.add_argument("--summary", action="store_true", help="仅汇总")
    parser.add_argument("--trend", action="store_true", help="趋势图")
    args = parser.parse_args()

    records = load_records()

    if not records:
        safe_print("❌ 无已结算记录（predictions_db.json 中没有 correct!=None 的记录）")
        safe_print("   提示: 运行 python skill/post_match_analysis.py --all 后重试")
        return

    mode = "trend" if args.trend else ("summary" if args.summary else "full")
    report = build_report(records, mode)
    safe_print(report)


if __name__ == "__main__":
    main()
