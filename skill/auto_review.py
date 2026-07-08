#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动化赛后复盘管线 v1.0 — P2.2
结果回填后自动生成偏差分析报告：detect → 归因 → 建议

用法:
  python skill/auto_review.py                    # 复盘最近未复盘记录
  python skill/auto_review.py --all              # 复盘全部已结算记录
  python skill/auto_review.py --match "葡萄牙"    # 复盘指定比赛
"""
import sys, os, json, math
from datetime import datetime, timedelta
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
REVIEW_DIR = os.path.join(BASE_DIR, "预测数据")


def safe_print(text):
    try:
        print(text)
    except:
        try:
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))


# ============================================================
# 归因分析
# ============================================================

def analyze_error(pred):
    """对一条错误预测进行归因分析"""
    direction = pred.get("direction", "")
    p_final = pred.get("p_final", 0.5)
    correct = pred["result"].get("correct", None)
    score_h = pred["result"].get("score_home", "?")
    score_a = pred["result"].get("score_away", "?")
    league = pred.get("league", "")
    confidence = pred.get("confidence", "")

    if correct is not False:
        return None

    factors = []
    severity = "L0"

    # 1. 冷门类 (#008 + #026)
    if p_final < 0.35:
        factors.append(f"模型低信心(p={p_final:.3f}) → 本属小概率事件(#008)")
        severity = "L0"
    elif p_final > 0.65:
        factors.append(f"模型高信心(p={p_final:.3f})但错误 → 高估主导方向")
        severity = "L2"

    # 2. 极端低分 (#026)
    severity = "L1"
    if "026" not in [f for f in factors]:
        factors.append("七维评分极端值或数据质量不足(#026)")

    # 3. 淘汰赛
    if league in ("wm26",):
        factors.append("淘汰赛λ修正(×0.82)可能不足或过度")

    # 4. 结果特征
    actual_h = int(score_h) if str(score_h).isdigit() else 0
    actual_a = int(score_a) if str(score_a).isdigit() else 0
    total_goals = actual_h + actual_a
    if total_goals <= 1:
        factors.append("低进球比赛(≤1球)，模型偏好高估进球数")
    elif total_goals >= 4:
        factors.append("高进球比赛(≥4球)，防守评分可能低估")

    # 5. 评级信心
    if confidence in ("⭐⭐⭐",):
        factors.append(f"最高信心({confidence})出错 → L2场景修正过度自信")

    return {
        "match": f"{pred.get('home','?')} vs {pred.get('away','?')}",
        "direction": direction,
        "p_final": p_final,
        "score": f"{score_h}-{score_a}",
        "league": league,
        "confidence": confidence,
        "severity": severity,
        "factors": factors,
        "suggestion": _suggest_fix(factors, direction, p_final),
    }


def _suggest_fix(factors, direction, p_final):
    """根据归因生成改进建议"""
    suggestions = []
    for f in factors:
        if "高估" in f:
            suggestions.append("复核七维评分中进攻/防守维度的赋值依据")
        if "淘汰赛" in f:
            suggestions.append("淘汰赛λ衰减系数(当前0.82)可能需要调整")
        if "低进球" in f:
            suggestions.append("淘汰赛大小球核验：是否触发#002 BTTS矛盾检查")
        if "高信心" in f:
            suggestions.append("⭐⭐⭐评级需触发L3#008冷门预警复核")
        if "小概率" in f:
            suggestions.append("正确（小概率事件正常发生），无需调整")
    if not suggestions:
        suggestions.append("足球固有随机性，持续追踪")
    return suggestions


def generate_review(settled_preds, mode="recent"):
    """生成复盘报告"""
    total = len(settled_preds)
    correct = sum(1 for p in settled_preds if p["result"]["correct"] is True)
    incorrect = sum(1 for p in settled_preds if p["result"]["correct"] is False)
    unknown = sum(1 for p in settled_preds if p["result"]["correct"] is None)

    errors = [p for p in settled_preds if p["result"]["correct"] is False]

    lines = []
    lines.append("---")
    lines.append(f"title: 赛后复盘 {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"author: auto_review.py")
    lines.append("---")
    lines.append("")
    lines.append(f"# 赛后复盘报告 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    lines.append("")
    lines.append(f"> 自动生成 by auto_review.py — 基于 {total} 条已结算记录")
    lines.append("")
    lines.append("## 📊 总览")
    lines.append("")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|:-----|:----:|")
    lines.append(f"| 总场次 | {total} |")
    lines.append(f"| 正确 | {correct} ({correct/total*100:.1f}%) |")
    lines.append(f"| 错误 | {incorrect} |")
    lines.append(f"| 未判定 | {unknown} |")
    lines.append("")

    if not errors:
        lines.append("✅ 本次复盘范围内无错误预测")
        return "\n".join(lines)

    lines.append("## ❌ 错误归因")
    lines.append("")
    for err in errors:
        analysis = analyze_error(err)
        if not analysis:
            continue
        severity_icon = {"L2": "🔴", "L1": "🟡", "L0": "⚪"}.get(analysis["severity"], "⚪")
        lines.append(f"### {severity_icon} {analysis['match']}")
        lines.append(f"")
        lines.append(f"| 维度 | 内容 |")
        lines.append(f"|:-----|:------|")
        lines.append(f"| 预测方向 | {analysis['direction']} |")
        lines.append(f"| P_final | {analysis['p_final']:.3f} |")
        lines.append(f"| 实际比分 | {analysis['score']} |")
        lines.append(f"| 严重级别 | {analysis['severity']} |")
        lines.append(f"| 联赛 | {analysis['league']} |")
        lines.append(f"")
        lines.append(f"**根因分析:**")
        for f in analysis["factors"]:
            lines.append(f"- {f}")
        lines.append(f"")
        lines.append(f"**改进建议:**")
        for s in analysis["suggestion"]:
            lines.append(f"- {s}")
        lines.append("")

    # 模式发现
    lines.append("## 🔍 模式发现")
    lines.append("")
    factor_counts = defaultdict(int)
    for err in errors:
        analysis = analyze_error(err)
        if analysis:
            for f in analysis["factors"]:
                factor_counts[f] += 1
    lines.append("| 错误模式 | 出现次数 |")
    lines.append("|:---------|:--------:|")
    for factor, cnt in sorted(factor_counts.items(), key=lambda x: -x[1]):
        lines.append(f"| {factor} | {cnt} |")
    lines.append("")

    lines.append("## 📋 改进建议汇总")
    lines.append("")
    suggestion_counts = defaultdict(int)
    for err in errors:
        analysis = analyze_error(err)
        if analysis:
            for s in analysis["suggestion"]:
                suggestion_counts[s] += 1
    for sug, cnt in sorted(suggestion_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- {sug} ({cnt}次)")
    lines.append("")

    lines.append("---")
    lines.append(f"_生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自动化赛后复盘管线")
    parser.add_argument("--all", action="store_true", help="复盘全部已结算记录")
    parser.add_argument("--match", help="复盘指定比赛(关键词)")
    parser.add_argument("--days", type=int, default=7, help="最近N天(默认7)")
    args = parser.parse_args()

    # 加载数据
    db_path = os.path.join(CACHE_DIR, "predictions_db.json")
    with open(db_path, "r", encoding="utf-8") as f:
        db = json.load(f)

    predictions = db.get("predictions", [])
    settled = [p for p in predictions
               if p.get("result") and p["result"].get("correct") is not None]

    if args.match:
        kw = args.match.lower()
        settled = [p for p in settled
                   if kw in p.get("home", "").lower() or kw in p.get("away", "").lower()]

    if args.days and not args.all and not args.match:
        cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        settled = [p for p in settled if p.get("date", "") >= cutoff]

    if not settled:
        safe_print("没有符合条件的已结算记录")
        return

    report = generate_review(settled, "recent" if not args.all else "all")

    # 保存复盘文件
    date_str = datetime.now().strftime("%Y-%m-%d")
    match_str = f"_{args.match}" if args.match else ""
    filename = f"复盘-{date_str}-自动{match_str}.md"
    filepath = os.path.join(REVIEW_DIR, filename)
    os.makedirs(REVIEW_DIR, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report + "\n")

    safe_print(f"✅ 复盘报告已写入: {filepath}")
    safe_print("")
    safe_print(report)


if __name__ == "__main__":
    main()
