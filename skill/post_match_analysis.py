#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
赛后结构化复盘引擎 v1.0

赛前预测 vs 实际结果的全维度对比：
  1X2   → 方向正确？概率偏差多少？
  大2.5 → 大小球偏差？
  BTTS  → 双方进球偏差？
  λ     → 预期进球 vs 实际进球偏差？
  七维   → 各维度评分偏差？

用法:
  python skill/post_match_analysis.py                 # 复盘所有未复盘的已结算记录
  python skill/post_match_analysis.py --match 巴西      # 复盘指定比赛
  python skill/post_match_analysis.py --all            # 复盘全部
"""
import sys, os, json, math
from datetime import datetime
from collections import defaultdict

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
DB_FILE = os.path.join(CACHE_DIR, "predictions_db.json")
REVIEW_DIR = os.path.join(BASE_DIR, "预测数据")


def safe_print(text):
    try:
        print(text)
    except:
        try:
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            pass


# ============================================================
# 单场复盘
# ============================================================

def analyze_market(predicted, actual, market_name):
    """对比单个市场的预测 vs 实际

    Args:
        predicted: 预测值（概率 0-1）
        actual: 实际是否发生 (True/False)
        market_name: 市场名称（用于输出）

    Returns:
        dict: {market, predicted_pct, actual,偏差_pct, correct, severity}
    """
    pred_pct = round(predicted * 100, 1) if predicted is not None else None
    correct = (predicted >= 0.5) == actual if predicted is not None else None
    dev = round(abs(predicted - (1.0 if actual else 0.0)) * 100, 1) if predicted is not None else None
    severity = "🔴" if dev and dev > 25 else ("🟡" if dev and dev > 15 else "🟢")
    return {
        "market": market_name,
        "predicted_pct": pred_pct,
        "actual": actual,
        "偏差_pp": dev,
        "correct": correct,
        "severity": severity,
    }


def classify_root_cause(analysis_results, rec):
    """根据多市场偏差归类根因"""
    causes = []
    lam_h = rec.get("lam_h", 1.4)
    lam_a = rec.get("lam_a", 1.4)
    score_diff = rec.get("score_diff", 0)
    actual_h = rec.get("result", {}).get("score_home")
    actual_a = rec.get("result", {}).get("score_away")

    # 1. λ 偏差：预期进球 vs 实际进球
    if actual_h is not None and actual_a is not None:
        expected_total = lam_h + lam_a
        actual_total = int(actual_h) + int(actual_a)
        lam_dev = abs(actual_total - expected_total)
        if lam_dev >= 2.0:
            causes.append({
                "type": "λ偏差",
                "detail": f"预期总进球={expected_total:.1f}, 实际={actual_total}, 偏差={actual_total-expected_total:+.1f}球",
                "severity": "🔴" if lam_dev >= 3.0 else "🟡",
                "suggestion": "检查对手防守评分是否合理，淘汰赛λ修正系数可能需要调整",
            })
        elif lam_dev >= 1.0:
            causes.append({
                "type": "λ偏差",
                "detail": f"预期总进球={expected_total:.1f}, 实际={actual_total}, 偏差={actual_total-expected_total:+.1f}球",
                "severity": "🟡",
                "suggestion": "小偏差，属于正常波动范围",
            })

    # 2. 七维评分偏差：score_diff 方向 vs 实际结果
    result_dir = rec.get("result", {}).get("actual_result", "")
    pred_dir = rec.get("direction", "")
    if result_dir and pred_dir:
        dir_map = {"主胜": "home", "客胜": "away", "平局": "draw"}
        pdir = dir_map.get(pred_dir, "")
        rdir = dir_map.get(result_dir, "")
        if pdir and rdir and pdir != rdir:
            causes.append({
                "type": "方向偏差",
                "detail": f"预测{pred_dir}, 实际{result_dir} (score_diff={score_diff:+.2f})",
                "severity": "🔴",
                "suggestion": "七维评分可能高估了某一方，检查进攻/防守评分赋值",
            })

    # 3. 大小球/BTTS 矛盾
    for ar in analysis_results:
        if ar["market"] in ("over_25", "btts") and ar["correct"] is False and ar["偏差_pp"] and ar["偏差_pp"] > 20:
            causes.append({
                "type": f"{ar['market']}偏差",
                "detail": f"模型概率{ar['predicted_pct']:.0f}% vs 实际{'发生' if ar['actual'] else '未发生'} (偏差{ar['偏差_pp']:.0f}pp)",
                "severity": ar["severity"],
                "suggestion": "λ值偏高导致大小球/BTTS被高估，检查淘汰赛λ修正是否充分",
            })

    if not causes:
        causes.append({
            "type": "正常波动",
            "detail": "所有市场偏差在合理范围内",
            "severity": "🟢",
            "suggestion": "保持现有参数",
        })

    return causes


def analyze_prediction(rec):
    """对一条预测记录进行全维度复盘

    Returns:
        dict: 结构化复盘结果
    """
    result = rec.get("result", {})
    if result.get("status") != "matched":
        return None
    if result.get("reviewed"):
        return None  # 已复盘

    actual_h = result.get("score_home")
    actual_a = result.get("score_away")
    if actual_h is None or actual_a is None:
        return None

    actual_h = int(actual_h)
    actual_a = int(actual_a)
    total_goals = actual_h + actual_a
    btts_actual = actual_h > 0 and actual_a > 0

    # 获取预测数据
    probs_3way = rec.get("probs_3way", {})
    h_pred = probs_3way.get("home")
    d_pred = probs_3way.get("draw")
    a_pred = probs_3way.get("away")
    over25_pred = rec.get("over_25")
    btts_pred = rec.get("btts")

    analysis_results = []

    # 实际结果分类
    if actual_h > actual_a:
        actual_1x2 = "home"
    elif actual_h < actual_a:
        actual_1x2 = "away"
    else:
        actual_1x2 = "draw"
    dir_map_actual = {"home": "主胜", "away": "客胜", "draw": "平局"}
    h_actual = actual_1x2 == "home"
    d_actual = actual_1x2 == "draw"
    a_actual = actual_1x2 == "away"

    # 1X2 市场（仅当有概率数据时）
    if h_pred is not None:
        for pred_prob, actual_flag, label in [(h_pred, h_actual, "主胜"), (d_pred, d_actual, "平局"), (a_pred, a_actual, "客胜")]:
            analysis_results.append(analyze_market(pred_prob, actual_flag, f"1X2-{label}"))

        # 方向正确性：优先使用 DB 中已存储的 correct 字段
        db_correct = rec.get("result", {}).get("correct")
        if db_correct is not None:
            is_correct = db_correct
        else:
            # 从 direction 字符串推断
            dir_pred = rec.get("direction", "")
            if "主" in dir_pred and "客" not in dir_pred:
                is_correct = actual_1x2 == "home"
            elif "客" in dir_pred and "主" not in dir_pred:
                is_correct = actual_1x2 == "away"
            elif "平" in dir_pred and "不败" not in dir_pred:
                is_correct = actual_1x2 == "draw"
            elif "大" in dir_pred and "小" not in dir_pred:
                is_correct = total_goals > 2.5
            elif "小" in dir_pred and "大" not in dir_pred:
                is_correct = total_goals <= 2.5
            elif "不败" in dir_pred:
                if "主" in dir_pred:
                    is_correct = actual_1x2 in ("home", "draw")
                elif "客" in dir_pred:
                    is_correct = actual_1x2 in ("away", "draw")
                else:
                    is_correct = None
            else:
                is_correct = None  # 无法判定（如"不推荐/均衡"）

        # ← 1X2概率分析结束

    # 方向正确性（独立于概率数据，对所有记录适用）
    db_correct = rec.get("result", {}).get("correct")
    if db_correct is not None:
        is_correct = db_correct
    else:
        # 从 direction 字符串推断
        dir_pred = rec.get("direction", "")
        if "主" in dir_pred and "客" not in dir_pred and "不败" not in dir_pred:
            is_correct = actual_1x2 == "home"
        elif "客" in dir_pred and "主" not in dir_pred and "不败" not in dir_pred:
            is_correct = actual_1x2 == "away"
        elif "平" in dir_pred and "不败" not in dir_pred:
            is_correct = actual_1x2 == "draw"
        elif "大" in dir_pred and "小" not in dir_pred:
            is_correct = total_goals > 2.5
        elif "小" in dir_pred and "大" not in dir_pred:
            is_correct = total_goals <= 2.5
        elif "不败" in dir_pred:
            is_correct = actual_1x2 in (("home", "draw") if "主" in dir_pred else ("away", "draw"))
        else:
            is_correct = None  # "不推荐/均衡"等

    analysis_results.insert(0, {
        "market": "方向",
        "predicted_pct": rec.get("p_final", 0.5) * 100 if rec.get("p_final") else None,
        "actual": dir_map_actual.get(actual_1x2, "?"),
        "correct": is_correct,
        "severity": "🟢" if is_correct else ("🔴" if is_correct is False else "⚪"),
    })

    # 大小球
    if over25_pred is not None:
        analysis_results.append(analyze_market(over25_pred, total_goals > 2.5, "over_25"))

    # BTTS
    if btts_pred is not None:
        analysis_results.append(analyze_market(btts_pred, btts_actual, "btts"))

    # 根因归类
    causes = classify_root_cause(analysis_results, rec)

    # λ 偏差明细
    lam_h = rec.get("lam_h", 1.4)
    lam_a = rec.get("lam_a", 1.4)

    return {
        "match": f"{rec.get('home','?')} vs {rec.get('away','?')}",
        "date": rec.get("date", ""),
        "league": rec.get("league", ""),
        "score": f"{actual_h}-{actual_a}",
        "direction": rec.get("direction", ""),
        "p_final": rec.get("p_final", 0.5),
        "lam_expected": f"{lam_h:.2f}+{lam_a:.2f}={lam_h+lam_a:.2f}",
        "lam_actual": str(total_goals),
        "results": analysis_results,
        "causes": causes,
    }


# ============================================================
# 报告生成
# ============================================================

def generate_review(analyses):
    """生成结构化复盘报告"""
    lines = []
    lines.append("---")
    lines.append(f"title: 结构化复盘 {datetime.now().strftime('%Y-%m-%d')}")
    lines.append(f"author: post_match_analysis.py")
    lines.append("---")
    lines.append("")
    lines.append(f"# 赛后结构化复盘 ({datetime.now().strftime('%Y-%m-%d %H:%M')})")
    lines.append("")

    total = len(analyses)
    correct_dir = sum(1 for a in analyses if any(r.get("market") == "方向" and r.get("correct") for r in a["results"]))
    lines.append(f"**总览**: {total} 场复盘, 方向正确 {correct_dir}/{total} = {correct_dir/total*100:.0f}%")
    lines.append("")

    # 偏差分类汇总
    cause_counter = defaultdict(int)
    for a in analyses:
        for c in a["causes"]:
            cause_counter[c["type"]] += 1

    if cause_counter:
        lines.append("## 偏差分类汇总")
        lines.append("")
        lines.append("| 偏差类型 | 出现次数 |")
        lines.append("|:---------|:--------:|")
        for ctype, cnt in sorted(cause_counter.items(), key=lambda x: -x[1]):
            lines.append(f"| {ctype} | {cnt} |")
        lines.append("")

    # 逐场详细复盘
    lines.append("## 逐场复盘")
    lines.append("")
    for analysis in analyses:
        lines.append("---")
        lines.append(f"### {analysis['match']}")
        lines.append("")
        lines.append(f"| 维度 | 内容 |")
        lines.append(f"|:-----|:------|")
        lines.append(f"| 日期 | {analysis['date']} |")
        lines.append(f"| 联赛 | {analysis['league']} |")
        lines.append(f"| 预测方向 | {analysis['direction']} (P_final={analysis['p_final']:.3f}) |")
        lines.append(f"| 实际比分 | {analysis['score']} |")
        lines.append(f"| λ预期 | {analysis['lam_expected']} |")
        lines.append(f"| λ实际 | {analysis['lam_actual']} 球 |")
        lines.append("")

        # 各市场
        lines.append("#### 市场对比")
        lines.append("")
        lines.append("| 市场 | 模型概率 | 实际 | 偏差(pp) | 判定 |")
        lines.append("|:-----|:--------:|:----:|:--------:|:----:|")
        for r in analysis["results"]:
            if r["market"] == "方向":
                pred_str = f"{r['predicted_pct']:.1f}%"
                icon = "✅" if r["correct"] else "❌"
                lines.append(f"| 方向 | {pred_str} | {r['actual']} | — | {icon} |")
            else:
                pred_str = f"{r['predicted_pct']:.0f}%" if r['predicted_pct'] is not None else "N/A"
                actual_str = "✅发生" if r["actual"] else "❌未发生"
                dev_str = f"{r['偏差_pp']:.0f}pp" if r['偏差_pp'] is not None else "N/A"
                icon = "✅" if r["correct"] else "❌"
                lines.append(f"| {r['market']} | {pred_str} | {actual_str} | {dev_str} | {icon} |")

        # 根因分析
        lines.append("")
        lines.append("#### 根因分析")
        lines.append("")
        for c in analysis["causes"]:
            lines.append(f"- {c['severity']} **{c['type']}**: {c['detail']}")
            lines.append(f"  → {c['suggestion']}")

        lines.append("")

    lines.append("---")
    lines.append(f"_生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    return "\n".join(lines)


def save_review_report(report_text):
    """保存复盘报告到文件"""
    fname = f"结构化复盘-{datetime.now().strftime('%Y-%m-%d')}.md"
    fpath = os.path.join(REVIEW_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(report_text + "\n")
    safe_print(f"✅ 复盘报告已写入: {fpath}")


def mark_reviewed(predictions):
    """标记已复盘"""
    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)
    reviewed_ids = {(p.get("home", ""), p.get("away", ""), p.get("date", "")) for p in predictions}

    updated = 0
    for rec in db["predictions"]:
        key = (rec.get("home", ""), rec.get("away", ""), rec.get("date", ""))
        if key in reviewed_ids:
            if "result" not in rec:
                rec["result"] = {}
            if not rec["result"].get("reviewed"):
                rec["result"]["reviewed"] = True
                rec["result"]["reviewed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                updated += 1

    if updated:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        safe_print(f"✅ 已标记 {updated} 条为已复盘")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="赛后结构化复盘引擎")
    parser.add_argument("--match", help="复盘指定比赛(关键词)")
    parser.add_argument("--all", action="store_true", help="复盘全部已结算记录")
    parser.add_argument("--days", type=int, default=7, help="最近N天")
    parser.add_argument("--no-mark", action="store_true", help="不标记已复盘")
    args = parser.parse_args()

    with open(DB_FILE, "r", encoding="utf-8") as f:
        db = json.load(f)

    predictions = db.get("predictions", [])
    settled = [p for p in predictions
               if p.get("result", {}).get("status") == "matched"
               and p.get("result", {}).get("score_home") is not None]

    # 过滤
    if args.match:
        kw = args.match.lower()
        settled = [p for p in settled
                   if kw in p.get("home", "").lower() or kw in p.get("away", "").lower()]
    elif args.days and not args.all:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")
        settled = [p for p in settled if p.get("date", "") >= cutoff]

    # 补齐老记录（有比分但无 probs_3way 的 legacy 数据也能复盘方向）
    analyses = []
    for rec in settled:
        analysis = analyze_prediction(rec)
        if analysis:
            analyses.append(analysis)

    if not analyses:
        safe_print("没有符合条件的未复盘记录")
        return

    report = generate_review(analyses)
    save_review_report(report)
    safe_print(report[:500] + "...")

    if not args.no_mark:
        mark_reviewed([a for a in analyses])


if __name__ == "__main__":
    main()
