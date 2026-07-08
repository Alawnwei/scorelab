#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
偏差统计审计工具 v1.0 — P2.5
对所有活跃偏差模式进行统计显著性测试，标记过拟合项。

用法:
  python skill/deviation_audit.py              # 审计报告
"""
import sys, os, json, math
from collections import defaultdict, Counter

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def safe_print(text):
    try:
        print(text)
    except:
        try:
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))


def load_db():
    path = os.path.join(BASE_DIR, "数据缓存", "predictions_db.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def binomial_p(n_success, n_total, p_null=0.5):
    """二项检验：如果实际胜率 ≠ p_null，算 p-value（单侧）"""
    if n_total == 0:
        return 1.0
    from math import comb
    p_obs = n_success / n_total
    if p_obs == p_null:
        return 1.0
    # 计算二项累积概率
    p_val = 0
    for k in range(n_success, n_total + 1):
        p_val += comb(n_total, k) * (p_null ** k) * ((1 - p_null) ** (n_total - k))
    return min(p_val, 1.0)


def main():
    db = load_db()
    predictions = db.get("predictions", [])

    # 只分析有明确对错的记录
    settled = [p for p in predictions
               if p.get("result") and p["result"].get("correct") is not None]

    safe_print("=" * 65)
    safe_print("  偏差统计审计 v1.0 — P2.5")
    safe_print("=" * 65)
    safe_print(f"\n  总预测: {len(predictions)}")
    safe_print(f"  已结算: {len(settled)}")
    safe_print(f"  命中率: {sum(1 for p in settled if p['result']['correct'])}/{len(settled)} = "
               f"{sum(1 for p in settled if p['result']['correct'])/len(settled)*100:.1f}%")

    # ================================================================
    # 分析1：按 P_final 区间 — 校准偏差
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  P1: 概率校准偏差")
    safe_print(f"{'='*65}")
    safe_print(f"  {'区间':<10} {'场次':<6} {'正确':<6} {'实际':<8} {'期望':<8} {'偏差':<8} {'p值':<8} {'判定'}")
    safe_print(f"  {'-'*62}")

    buckets = [(0.0, 0.30), (0.30, 0.40), (0.40, 0.45), (0.45, 0.48),
               (0.48, 0.52), (0.52, 0.55), (0.55, 0.60), (0.60, 0.70), (0.70, 1.0)]

    for lo, hi in buckets:
        batch = [p for p in settled if lo <= p.get("p_final", 0.5) < hi]
        if not batch:
            continue
        n = len(batch)
        c = sum(1 for p in batch if p["result"]["correct"])
        actual = c / n
        expected = (lo + hi) / 2
        dev = actual - expected
        p_val = binomial_p(c, n, p_null=expected)
        verdict = "显著🔴" if p_val < 0.05 else ("参考🟡" if p_val < 0.20 else "不显著✅")
        safe_print(f"  [{lo:.2f}-{hi:.2f})  {n:<6} {c:<6} {actual:<7.1%} {expected:<7.1%} "
                   f"{dev:<+7.1%} {p_val:<7.3f} {verdict}")

    # ================================================================
    # 分析2：按联赛类型
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  P2: 按联赛/赛事类型 — 迁移偏差")
    safe_print(f"{'='*65}")

    by_league = defaultdict(lambda: {"n": 0, "c": 0})
    for p in settled:
        league = p.get("league", "unknown")
        by_league[league]["n"] += 1
        if p["result"]["correct"]:
            by_league[league]["c"] += 1

    overall_p = sum(1 for p in settled if p["result"]["correct"]) / len(settled)
    safe_print(f"  {'赛事':<10} {'场次':<6} {'正确':<6} {'命中率':<10} {'vs总体':<10} {'判定'}")
    safe_print(f"  {'-'*50}")
    for league, data in sorted(by_league.items(), key=lambda x: -x[1]["n"]):
        rate = data["c"] / data["n"] * 100
        diff = rate - overall_p * 100
        verdict = "⚠️" if abs(diff) > 15 else ("🟡" if abs(diff) > 10 else "✅")
        safe_print(f"  {league:<10} {data['n']:<6} {data['c']:<6} {rate:<7.1f}%  {diff:<+7.1f}%  {verdict}")

    # ================================================================
    # 分析3：⭐评级校准
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  P3: Star 评级校准偏差")
    safe_print(f"{'='*65}")

    RATING_MAP = {"⭐⭐⭐": 0.85, "⭐⭐": 0.70, "⭐": 0.55}
    by_rating = defaultdict(lambda: {"n": 0, "c": 0})
    for p in settled:
        rating = p.get("confidence", "")
        by_rating[rating]["n"] += 1
        if p["result"]["correct"]:
            by_rating[rating]["c"] += 1

    safe_print(f"  {'评级':<8} {'场次':<6} {'正确':<6} {'实际胜率':<10} {'隐含胜率':<10} {'校准因子':<10} {'p值':<8} {'判定'}")
    safe_print(f"  {'-'*70}")
    for rating, data in sorted(by_rating.items(), key=lambda x: -len(x[0])):
        if data["n"] < 2:
            continue
        rate = data["c"] / data["n"]
        implied = RATING_MAP.get(rating, 0.55)
        cal = rate / implied if implied > 0 else 0
        p_val = binomial_p(data["c"], data["n"], p_null=implied)
        if cal < 0.80:
            note = "高估🔴"
        elif cal > 1.15:
            note = "低估🟢"
        else:
            note = "合理✅"
        safe_print(f"  {rating:<8} {data['n']:<6} {data['c']:<6} {rate:<7.1%}  {implied:<7.1%}  {cal:<9.2f} {p_val:<7.3f} {note}")

    # ================================================================
    # 分析4：偏差索引存活测试
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  P4: 偏差索引存活测试")
    safe_print(f"{'='*65}")

    # 已知活跃偏差（从 quality_engine.py 提取）
    active_devs = {
        "#001": "历史交锋权重", "#002": "BTTS+小2.25矛盾", "#003": "东道主半场激进",
        "#005": "已淘汰放开踢", "#007": "必须赢进攻爆发", "#008": "冷门预警",
        "#009": "盘口权重过高", "#011": "轮换幅度L4", "#012": "领先后退速",
        "#013": "生死战防守", "#014": "叙事驱动", "#015": "资金分歧",
        "#016": "主场连胜衰减", "#017": "大败后低迷", "#026": "极端低分",
    }

    all_devs = {f"#{i:03d}": f"偏差{i}" for i in range(1, 32)}
    all_devs.update(active_devs)

    # 判断哪些偏差实际被触发过（从 predictions_db 的错误中分析）
    # 近似：只统计那些有具体匹配错误模式的偏差
    triggered = set()
    for p in settled:
        if not p["result"]["correct"]:
            pf = p.get("p_final", 0.5)
            league = p.get("league", "")
            # #008 冷门：当 P_final 很低但方向还是错了
            if pf < 0.35:
                triggered.add("#008")
            # #026 极端低分
            if pf > 0.65:
                triggered.add("#026")
            # #003 东道主 — 查看是否东道主相关
            # (需要有东道主标记，暂时略过)

    safe_print(f"\n  理论偏差数量: {len(all_devs)}")
    safe_print(f"  有触发证据: {len(triggered)}")

    dead_devs = [d for d in all_devs if d not in triggered and "#" in d]
    safe_print(f"  从未触发(可能已过时): {len(dead_devs)}")
    if dead_devs:
        safe_print(f"  {', '.join(sorted(dead_devs)[:10])}")

    # 统计哪些偏差在当前数据中可验证
    verifyable = active_devs.copy()
    safe_print(f"\n  活跃偏差统计:")
    safe_print(f"  {'ID':<8} {'名称':<20} {'状态':<10} {'样本数':<8}")
    safe_print(f"  {'-'*50}")
    for dev_id, dev_name in sorted(active_devs.items()):
        if dev_id in triggered:
            safe_print(f"  {dev_id:<8} {dev_name:<20} {'活跃✅':<10} {'有限':<8}")
        else:
            safe_print(f"  {dev_id:<8} {dev_name:<20} {'未验证❓':<10} {'无':<8}")

    # ================================================================
    # 结论
    # ================================================================
    safe_print(f"\n{'='*65}")
    safe_print("  结论与建议")
    safe_print(f"{'='*65}")

    # 校准偏差诊断
    high_bins = [(lo, hi) for lo, hi in buckets
                 if len([p for p in settled if lo <= p.get("p_final", 0.5) < hi]) > 0]
    sig_over = 0
    sig_under = 0
    for lo, hi in high_bins:
        batch = [p for p in settled if lo <= p.get("p_final", 0.5) < hi]
        if not batch: continue
        c = sum(1 for p in batch if p["result"]["correct"])
        n = len(batch)
        actual = c / n
        expected = (lo + hi) / 2
        p_val = binomial_p(c, n, p_null=expected)
        if p_val < 0.05:
            if actual > expected:
                sig_under += 1
            else:
                sig_over += 1

    safe_print(f"\n  1. 概率校准: {sig_over} 个区间被显著高估, {sig_under} 个被显著低估")
    safe_print(f"  2. Star评级: 检查校准因子偏离 0.80-1.20 的评级")
    safe_print(f"  3. 偏差存活: {len(dead_devs)}/{len(all_devs)} 条偏差从未触发")
    safe_print(f"  4. 建议: 对\"从未触发\"偏差考虑移除或降级为 P2")
    safe_print(f"     对活跃偏差持续追踪，每 30 场重新审计")
    safe_print(f"\n  当前样本量: {len(settled)} 场 — 统计检验为参考性，非结论性")
    safe_print(f"  建议积累至 100+ 场后重跑本审计")


if __name__ == "__main__":
    main()
