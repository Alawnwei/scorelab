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
import sys, os, json, math, glob
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


# ============================================================
# 推荐复盘（检查每条推荐是否命中）
# ============================================================

def review_recommendations(pred, save=True):
    """检查一条预测的推荐快照是否命中，回填 hit 字段

    支持的市场类型:
      大小球大X: 总进球 > X
      大小球小X: 总进球 <= X
      亚盘主-X:  主队净胜 >= X (quarter-ball取整)
      亚盘客+X:  主队净胜 < X
      BTTS Yes:  双方都进球
      BTTS No:   一方未进球
      1X2 主胜:  主队赢
      1X2 客胜:  客队赢
    """
    recs = pred.get("recommendations", [])
    if not recs:
        return []

    result = pred.get("result", {})
    sh = result.get("score_home")
    sa = result.get("score_away")
    if sh is None or sa is None:
        return recs  # 未结算，跳过

    sh, sa = int(sh), int(sa)
    total = sh + sa
    margin = sh - sa

    results = []
    for rec in recs:
        market = rec.get("market", "")
        hit = None
        if "大小球大" in market:
            line_str = market.replace("大小球大", "").replace("球", "")
            try:
                line = float(line_str)
                hit = total > line
            except:
                hit = None
        elif "大小球小" in market:
            line_str = market.replace("大小球小", "").replace("球", "")
            try:
                line = float(line_str)
                hit = total < line
            except:
                hit = None
        elif "亚盘主" in market:
            line_str = market.replace("亚盘主", "").replace("球", "")
            try:
                hdp = abs(float(line_str))
                # 对 quarter-ball 保守判断: 赢1球以上算全赢
                hit = margin > hdp - 0.5
            except:
                hit = None
        elif "亚盘客" in market:
            line_str = market.replace("亚盘客", "").replace("球", "")
            try:
                hdp = abs(float(line_str))
                # 客队受让: 主队净胜 < hdp
                hit = margin < hdp
            except:
                hit = None
        elif "BTTS Yes" in market or "BTTS" in market:
            hit = (sh > 0) and (sa > 0)
        elif "BTTS No" in market:
            hit = (sh == 0) or (sa == 0)
        elif "1X2 主胜" in market or "1X2-主胜" in market:
            hit = sh > sa
        elif "1X2 客胜" in market or "1X2-客胜" in market:
            hit = sh < sa
        elif "1X2 平" in market:
            hit = sh == sa

        rec["hit"] = hit
        results.append(rec)

    # 保存回 DB
    if save:
        try:
            db_path = os.path.join(CACHE_DIR, "predictions_db.json")
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            for p in db.get("predictions", []):
                if p.get("id") == pred.get("id"):
                    p["recommendations"] = results
                    break
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
        except:
            pass

    return results


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

    # ============================================================
    # 推荐复盘
    # ============================================================
    rec_total = 0
    rec_hit = 0
    rec_by_market = defaultdict(lambda: {"total": 0, "hit": 0})

    for p in settled_preds:
        recs = review_recommendations(p, save=True)
        for r in recs:
            if r.get("hit") is not None:
                rec_total += 1
                if r["hit"]:
                    rec_hit += 1
                mkt = r.get("market", "未知")
                # 提取市场大类
                if "大小球" in mkt: cat = "大小球"
                elif "亚盘" in mkt: cat = "亚盘"
                elif "BTTS" in mkt: cat = "BTTS"
                elif "1X2" in mkt: cat = "1X2"
                else: cat = "其他"
                rec_by_market[cat]["total"] += 1
                if r["hit"]:
                    rec_by_market[cat]["hit"] += 1

    if rec_total > 0:
        lines.append("## 🎯 推荐命中率")
        lines.append("")
        lines.append(f"| 市场 | 命中/总数 | 命中率 |")
        lines.append(f"|:-----|:---------:|:------:|")
        lines.append(f"| **全部** | **{rec_hit}/{rec_total}** | **{rec_hit/rec_total*100:.0f}%** |")
        for cat in ["大小球", "亚盘", "BTTS", "1X2", "其他"]:
            d = rec_by_market.get(cat)
            if d and d["total"] > 0:
                pct = d["hit"] / d["total"] * 100
                lines.append(f"| {cat} | {d['hit']}/{d['total']} | {pct:.0f}% |")
        lines.append("")

        # EV 校准检查：按 +EV 分桶看实际命中率
        ev_buckets = defaultdict(lambda: {"total": 0, "hit": 0, "sum_ev": 0})
        for p in settled_preds:
            for r in p.get("recommendations", []):
                if r.get("hit") is None:
                    continue
                ev = r.get("ev", 0)
                bucket = f"{int(ev // 20) * 20}+" if ev >= 0 else "负EV"
                ev_buckets[bucket]["total"] += 1
                if r["hit"]:
                    ev_buckets[bucket]["hit"] += 1
                ev_buckets[bucket]["sum_ev"] += ev

        if ev_buckets:
            lines.append("### +EV 分桶命中率")
            lines.append("")
            lines.append(f"| +EV 区间 | 命中/总数 | 命中率 | 平均+EV |")
            lines.append(f"|:--------|:---------:|:------:|:-------:|")
            for bucket in sorted(ev_buckets.keys(), key=lambda x: float(x.replace("+","").replace("负EV","-999")), reverse=True):
                d = ev_buckets[bucket]
                if d["total"] > 0:
                    pct = d["hit"] / d["total"] * 100
                    avg_ev = d["sum_ev"] / d["total"]
                    lines.append(f"| {bucket} | {d['hit']}/{d['total']} | {pct:.0f}% | {avg_ev:+.0f}% |")
            lines.append("")

    lines.append("---")
    lines.append(f"_生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    return "\n".join(lines)


def _fetch_closing_odds(home: str, away: str) -> tuple:
    """从 odds 缓存文件获取开赛赔率近似值（v8.5）

    在 odds_*.json 缓存中查找匹配该场比赛的最新赔率文件，
    用作开赛赔率（final_odds）的近似。

    Returns:
        (final_odds, source) 或 (None, "")
    """
    home_norm = home.replace(" ", "").replace("/", "_")
    away_norm = away.replace(" ", "").replace("/", "_")
    pattern = os.path.join(CACHE_DIR, f"odds_{home_norm}_{away_norm}_*.json")

    best_file, best_ts = None, ""
    for fpath in glob.glob(pattern):
        fname = os.path.basename(fpath)
        parts = fname.replace(".json", "").split("_")
        if len(parts) >= 4:
            ts = "_".join(parts[-2:])
            if ts > best_ts:
                best_ts = ts
                best_file = fpath

    if not best_file:
        return None, ""

    try:
        with open(best_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        home_odds = data.get("odds_home")
        draw_odds = data.get("odds_draw")
        away_odds = data.get("odds_away")
        source = data.get("source", "unknown")
        return (home_odds, draw_odds, away_odds), source
    except Exception:
        return None, ""


def compute_clv_summary(predictions: list) -> dict:
    """计算 CLV 聚合统计（v8.5）

    分析 predictions_db 中有 CLV 记录的预测，返回：
      - avg_clv: 平均 CLV（%）
      - count: 有 CLV 的记录数
      - good_ratio: CLV>0 的比例
      - warning: 是否需要预警
    """
    clv_vals = []
    for p in predictions:
        clv = p.get("clv")
        if clv is not None:
            clv_vals.append(clv)

    if not clv_vals:
        return {"avg_clv": None, "count": 0, "good_ratio": 0, "warning": ""}

    avg_clv = sum(clv_vals) / len(clv_vals)
    good = sum(1 for v in clv_vals if v > 0)
    good_ratio = good / len(clv_vals)

    warning = ""
    n = len(clv_vals)
    if n >= 5 and avg_clv < -5:
        warning = (
            f"⚠️ CLV 预警：最近 {n} 场平均 CLV = {avg_clv:.1f}%\n"
            f"   → 下注赔率持续差于市场收盘价\n"
            f"   → 可能原因：下注太早 / 选错盘口 / 模型在追已消化的信息"
        )
    elif n >= 10 and good_ratio < 0.3:
        warning = (
            f"⚠️ CLV 预警：{n} 场中仅 {good} 场({good_ratio:.0%})获得正CLV\n"
            f"   → 多数投注的赔率在开赛时已变差"
        )

    return {
        "avg_clv": round(avg_clv, 2),
        "count": n,
        "good_ratio": round(good_ratio, 2),
        "warning": warning,
    }



def compute_odds_trend(home: str, away: str, direction: str = "") -> dict:
    """分析某场比赛的赔率变动趋势（v8.5）"""
    home_norm = home.replace(" ", "").replace("/", "_")
    away_norm = away.replace(" ", "").replace("/", "_")
    pattern = os.path.join(CACHE_DIR, f"odds_{home_norm}_{away_norm}_*.json")
    odds_records = []
    for fpath in sorted(glob.glob(pattern)):
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                data = json.load(f)
            ts = data.get("timestamp", "")
            odds_h = data.get("odds_home")
            odds_a = data.get("odds_away")
            if odds_h and ts:
                odds_records.append((ts, float(odds_h), float(odds_a) if odds_a else None))
        except Exception:
            continue
    if len(odds_records) < 2:
        return {"samples": len(odds_records), "direction": "flat",
                "change_pct": 0, "earliest_odds": None, "latest_odds": None}
    _first_ts, first_h, first_a = odds_records[0]
    _last_ts, last_h, last_a = odds_records[-1]
    if "主" in direction and first_h and last_h:
        earliest, latest = first_h, last_h
    elif "客" in direction and first_a and last_a:
        earliest, latest = first_a, last_a
    else:
        earliest, latest = first_h, last_h
    change_pct = round((latest - earliest) / earliest * 100, 2)
    if change_pct < -2: trend_dir = "down"
    elif change_pct > 2: trend_dir = "up"
    else: trend_dir = "flat"
    return {"samples": len(odds_records), "direction": trend_dir,
            "change_pct": change_pct, "earliest_odds": earliest, "latest_odds": latest}


def sync_predictions_db_results() -> int:
    """从 auto_results.json 同步实际比分到 predictions_db.json（v8.5）

    自动回填 pending 预测的实际比分、方向和正确性。
    匹配策略：以 team_en 归一化后模糊匹配主客队名。

    Returns: 回填的记录数
    """
    db_path = os.path.join(CACHE_DIR, "predictions_db.json")
    auto_path = os.path.join(CACHE_DIR, "auto_results.json")

    if not os.path.exists(db_path) or not os.path.exists(auto_path):
        return 0

    try:
        with open(db_path, "r", encoding="utf-8") as f:
            db = json.load(f)
        with open(auto_path, "r", encoding="utf-8") as f:
            auto_results = json.load(f)
    except Exception:
        return 0

    # 构建 auto_results 索引：(归一化主队, 归一化客队) → 比分
    auto_index = {}
    for r in auto_results:
        h = r.get("home_cn", ""); a = r.get("away_cn", "")
        score = r.get("score_ft", "0-0")
        if h and a:
            key = (h.lower().replace(" ", ""), a.lower().replace(" ", ""))
            auto_index[key] = score

    import re
    updated = 0
    for p in db.get("predictions", []):
        res = p.get("result", {})
        if res.get("status") == "matched":
            continue
        home = p.get("home", ""); away = p.get("away", "")
        if not home or not away:
            continue
        # 尝试直接匹配
        key = (home.lower().replace(" ", ""), away.lower().replace(" ", ""))
        score = auto_index.get(key)
        # 失败时尝试反向匹配
        if not score:
            rev_key = (away.lower().replace(" ", ""), home.lower().replace(" ", ""))
            score = auto_index.get(rev_key)
        if not score:
            continue

        # 解析比分
        m = re.match(r'(\d+)\s*[-:]\s*(\d+)', str(score))
        if not m:
            continue
        sh, sa = int(m.group(1)), int(m.group(2))

        # 解析方向判断正确性
        direction = p.get("direction", "")
        if "主胜" in direction or "主不败" in direction:
            correct = (sh > sa)
        elif "客胜" in direction or "客不败" in direction:
            correct = (sa > sh)
        elif "平局" in direction:
            correct = (sh == sa)
        elif "大" in direction:
            m_line = re.search(r'[\d.]+', direction.replace("大", ""))
            line = float(m_line.group()) if m_line else 2.5
            correct = ((sh + sa) > line)
        elif "小" in direction:
            m_line = re.search(r'[\d.]+', direction.replace("小", ""))
            line = float(m_line.group()) if m_line else 2.5
            correct = ((sh + sa) <= line)
        elif "不推荐" in direction or "均衡" in direction:
            correct = None
        else:
            correct = (sh > sa)

        # 实际结果文本
        if sh > sa:
            actual = "主胜"
        elif sh < sa:
            actual = "客胜"
        else:
            actual = "平局"

        p["result"]["status"] = "matched"
        p["result"]["score_home"] = sh
        p["result"]["score_away"] = sa
        p["result"]["actual_result"] = actual
        p["result"]["correct"] = correct

        # ── CLV 计算（v8.5） ──
        # 从 recommendations 取最佳推荐赔率
        bet_odds = p.get("odds")
        if not bet_odds or bet_odds <= 0:
            _recs = p.get("recommendations", [])
            if _recs:
                _best = max(_recs, key=lambda r: r.get("ev", 0))
                bet_odds = _best.get("odds", 0)
        if bet_odds and bet_odds > 0:
            closing, _src = _fetch_closing_odds(home, away)
            if closing:
                odds_h, odds_d, odds_a = closing
                direction = p.get("direction", "")
                if "主" in direction and odds_h:
                    final_odds = odds_h
                elif "客" in direction and odds_a:
                    final_odds = odds_a
                elif "平" in direction and odds_d:
                    final_odds = odds_d
                else:
                    final_odds = odds_h or odds_a or odds_d
                if final_odds and final_odds > 0:
                    clv = round((float(bet_odds) - float(final_odds)) / float(final_odds) * 100, 2)
                    p["clv"] = clv
                    p["clv_quality"] = "good" if clv > 0 else "bad"
        if "clv" not in p:
            p["clv"] = None
            p["clv_quality"] = "none"

        updated += 1

    if updated > 0:
        try:
            with open(db_path, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            safe_print(f"[自动回填] ✅ 已回填 {updated} 条预测结果到 predictions_db.json")
        except Exception as e:
            safe_print(f"[自动回填] ❌ 写入失败: {e}")

    # ── 更新 bankroll 统计（v8.5） ──
    _update_bankroll()

    return updated


def _update_bankroll():
    """从 pnl_records 更新 bankroll 统计（最大回撤等）"""
    pnl_path = os.path.join(CACHE_DIR, "pnl_records.json")
    if not os.path.exists(pnl_path):
        return
    try:
        with open(pnl_path, "r", encoding="utf-8") as f:
            pnl = json.load(f)
        _total = sum(r.get("pnl", 0) for r in pnl.get("records", [])
                     if r.get("result") in ("win", "loss"))
        b = pnl.setdefault("bankroll", {})
        b.setdefault("initial", 10000)
        b["current"] = b["initial"] + _total
        b["peak"] = max(b.get("peak", b["initial"]), b["current"])
        b["lowest"] = min(b.get("lowest", b["initial"]), b["current"])
        _drawdown = (b["peak"] - b["current"]) / b["peak"] * 100 if b["peak"] > 0 else 0
        b["max_drawdown"] = max(b.get("max_drawdown", 0), round(_drawdown, 2))
        b["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        with open(pnl_path, "w", encoding="utf-8") as f:
            json.dump(pnl, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自动化赛后复盘管线")
    parser.add_argument("--all", action="store_true", help="复盘全部已结算记录")
    parser.add_argument("--match", help="复盘指定比赛(关键词)")
    parser.add_argument("--days", type=int, default=7, help="最近N天(默认7)")
    parser.add_argument("--sync", action="store_true", help="从 auto_results 同步比分到 predictions_db（v8.5 自动回填）")
    parser.add_argument("--clv", action="store_true", help="查看 CLV 聚合统计")
    args = parser.parse_args()

    # ── --sync 模式：自动回填 + CLV 摘要 ──
    if args.sync:
        n = sync_predictions_db_results()
        safe_print(f"同步完成: {n} 条")
        # 回填后显示 CLV 摘要
        db_path = os.path.join(CACHE_DIR, "predictions_db.json")
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            summary = compute_clv_summary(db.get("predictions", []))
            if summary["count"] > 0:
                safe_print(f"📊 CLV 统计: {summary['count']} 场 | "
                           f"平均 {summary['avg_clv']:+.1f}% | "
                           f"正CLV占比 {summary['good_ratio']:.0%}")
                if summary["warning"]:
                    safe_print(summary["warning"])
        except Exception:
            pass
        return

    # ── --clv 模式：查看 CLV 统计 ──
    if args.clv:
        db_path = os.path.join(CACHE_DIR, "predictions_db.json")
        try:
            with open(db_path, "r", encoding="utf-8") as f:
                db = json.load(f)
            summary = compute_clv_summary(db.get("predictions", []))
            safe_print(f"📊 CLV 聚合统计")
            safe_print(f"{'='*40}")
            safe_print(f"  有CLV数据: {summary['count']} 场")
            if summary["count"] > 0:
                safe_print(f"  平均 CLV: {summary['avg_clv']:+.1f}%")
                safe_print(f"  正CLV占比: {summary['good_ratio']:.0%}")
                if summary["warning"]:
                    safe_print(f"\n{summary['warning']}")
            else:
                safe_print(f"  (无 CLV 数据，运行 --sync 回填结果后自动计算)")
        except Exception as e:
            safe_print(f"读取失败: {e}")
        return

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
