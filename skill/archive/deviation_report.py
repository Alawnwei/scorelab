#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
偏差分析报告 — 评估模型当前预测能力
"""
import sys, json, math
sys.stdout.reconfigure(encoding="utf-8")

def pt(text):
    try:
        safe = str(text).encode("utf-8", errors="replace").decode("gbk", errors="replace")
        print(safe)
    except:
        print(str(text))

with open("数据缓存/predictions_db.json", "r", encoding="utf-8") as f:
    db = json.load(f)

preds = db["predictions"]
matched = [p for p in preds if p["result"]["status"] == "matched"]
with_dir = [p for p in matched if p["result"]["correct"] is not None]
with_pf = [p for p in matched if p["p_final"] is not None and p["result"]["correct"] is not None]
bets = [p for p in preds if p.get("is_bet")]
settled = [p for p in bets if p["result"]["status"] == "matched"]

correct = sum(1 for p in with_dir if p["result"]["correct"])
total_dir = len(with_dir)
acc = correct / total_dir * 100 if total_dir > 0 else 0

# Brier
brier = sum((p["p_final"] - (1 if p["result"]["correct"] else 0))**2 for p in with_pf) / len(with_pf) if with_pf else 0
logloss = sum(-math.log(p["p_final"]) if p["result"]["correct"] else -math.log(1-p["p_final"]) for p in with_pf) / len(with_pf) if with_pf else 0

pt("=" * 65)
pt("  偏 差 分 析 报 告")
pt("=" * 65)

pt(f"\n[1] 数据概览")
pt(f"  总预测: {len(preds)} 场")
pt(f"  已有赛果: {len(matched)} 场")
pt(f"  待赛果: {len(preds)-len(matched)} 场 (今晚巴西vs挪威)")
pt(f"  有P_final+方向+赛果: {len(with_pf)} 场  ← 核心校准样本")
pt(f"  有方向已验证: {len(with_dir)} 场")
pt(f"  实际下注: {len(settled)} 场")

pt(f"\n[2] 方向命中率 (核心指标)")
pt(f"  总样本: {total_dir} 场")
pt(f"  正确: {correct} 场 | 错误: {total_dir-correct} 场")
pt(f"  命中率: {acc:.1f}%  (随机=50%)")
if acc < 40:
    pt(f"  >> 🔴 低于随机，模型判断不可靠")
elif acc < 50:
    pt(f"  >> 🟡 略低于随机")

# 方向细分
dirs = {}
for p in with_dir:
    d = p.get("direction", "") or "(空)"
    if "主" in d and "客" not in d:
        key = "主胜"
    elif "客" in d:
        key = "客胜"
    elif "平" in d or "均衡" in d:
        key = "平局/均衡"
    elif "大" in d:
        key = "大球"
    elif "小" in d:
        key = "小球"
    elif "不败" in d:
        key = "不败(双选)"
    elif "胜" in d or "赢" in d:
        # 队名直接判断（如英格兰胜）
        if p["home"] and p["home"][:2] in d:
            key = "主胜"
        elif p["away"] and p["away"][:2] in d:
            key = "客胜"
        else:
            key = d[:8]
    else:
        key = d[:8]
    dirs.setdefault(key, {"t": 0, "c": 0})
    dirs[key]["t"] += 1
    if p["result"]["correct"]:
        dirs[key]["c"] += 1

pt(f"\n  方向细分 (排除样本<2的):")
for d, v in sorted(dirs.items()):
    r = v["c"] / v["t"] * 100 if v["t"] > 0 else 0
    if v["t"] < 2:
        continue
    tag = "[OK]" if r > 50 else ("[--]" if r > 30 else "[BAD]")
    pt(f"    {tag} {d:<16}: {v['c']}/{v['t']} = {r:.1f}%")

singles = {d: v for d, v in dirs.items() if v["t"] < 2}

# P_final 校准分析
pt(f"\n[3] P_final 校准表 ({len(with_pf)} 场)")
pt(f"  {'区间':<12} {'场次':<5} {'胜':<4} {'负':<4} {'实际胜率':<9} {'隐含概率':<9} {'校准因子':<7} {'偏差':<8} 评价")
pt(f"  " + "-" * 68)

buckets = [(0.80, 1.01, ">=0.80"), (0.70, 0.80, "0.70-0.79"),
           (0.60, 0.70, "0.60-0.69"), (0.50, 0.60, "0.50-0.59"),
           (0.40, 0.50, "0.40-0.49"), (0.30, 0.40, "0.30-0.39"),
           (0.00, 0.30, "<0.30")]

for lo, hi, label in buckets:
    bucket = [p for p in with_pf if lo <= p["p_final"] < hi]
    if not bucket:
        continue
    bt = len(bucket)
    bc = sum(1 for p in bucket if p["result"]["correct"])
    bw = bt - bc
    wr = bc / bt * 100
    avg_p = sum(p["p_final"] for p in bucket) / bt
    implied = avg_p * 100
    cf = wr / implied if implied > 0 else 0
    diff = wr - implied
    if bt < 3:
        remark = "样本不足"
    elif cf > 1.15:
        remark = "低估(太保守)"
    elif cf < 0.85:
        remark = "高估(过度自信)"
    else:
        remark = "校准合理"
    pt(f"  {label:<12} {bt:<5} {bc:<4} {bw:<4} {wr:<7.1f}%  {implied:<7.1f}%   {cf:<6.2f}  {diff:+.1f}%  {remark}")

# 模型指标
pt(f"\n  模型整体指标:")
pt(f"    Brier Score: {brier:.4f}  (0=完美, 0.25=随机)")
pt(f"    Log Loss:   {logloss:.4f}  (0=完美)")
if brier > 0.23:
    pt(f"    >> 🔴 接近随机水平，无预测能力")
elif brier > 0.20:
    pt(f"    >> 🟡 略好于随机，但不可靠")
else:
    pt(f"    >> 🟢 有一定预测能力")

pt(f"\n  校准稳定性: ")
# Check if all buckets point in same direction
overconfident = sum(1 for p in with_pf if p["p_final"] > 0.5 and not p["result"]["correct"])
underconfident = sum(1 for p in with_pf if p["p_final"] < 0.5 and p["result"]["correct"])
total_bias = overconfident + underconfident
bias_pct = total_bias / len(with_pf) * 100 if with_pf else 0
if overconfident > underconfident * 2:
    pt(f"系统倾向于过度自信 (高估{overconfident}次 vs 低估{underconfident}次)")
elif underconfident > overconfident * 2:
    pt(f"系统倾向于过于保守 (低估{underconfident}次 vs 高估{overconfident}次)")
else:
    pt(f"无明显偏向 (高估{overconfident}次 vs 低估{underconfident}次)")

# 投注盈亏
pt(f"\n[4] 投注盈亏")
if settled:
    total_pnl = 0
    total_stake = 0
    for p in settled:
        odds = p.get("odds", 0)
        stake = p.get("stake", 1)
        total_stake += stake
        if p["result"]["correct"] is True and odds > 0:
            pnl_val = round(stake * (odds - 1), 2)
        elif p["result"]["correct"] is False and odds > 0:
            pnl_val = round(-stake, 2)
        else:
            pnl_val = 0
        total_pnl += pnl_val
        won = "+" if p["result"]["correct"] is True else "x"
        label = f"{p['home'][:12]}vs{p['away'][:12]}"
        odds_str = f"{odds:.2f}" if odds else "N/A"
        pt(f"    {won} {label:<28} {odds_str:>5}  PnL={pnl_val:+.1f}")

    # Aggregate
    real_bets = [p for p in settled if p.get("odds", 0) > 0]
    real_pnl = sum(
        round(p.get("stake",1) * (p["odds"]-1), 2) if p["result"]["correct"] is True
        else round(-p.get("stake",1), 2)
        for p in real_bets
    )
    real_stake = sum(p.get("stake",1) for p in real_bets)
    pt(f"\n  有赔率的投注 ({len(real_bets)} 次):")
    pt(f"    投入: {real_stake:.0f} 单位")
    pt(f"    盈亏: {real_pnl:+.1f} 单位")
    if real_stake > 0:
        pt(f"    ROI: {real_pnl/real_stake*100:+.1f}%")

    all_pnl = sum(p.get("pnl", 0) for p in preds if p.get("pnl") is not None and p["result"] != "pending")
    pt(f"\n  全部已结算 ({len(settled)} 次, 含无赔率): {all_pnl:+.1f} 单位")

# 最终结论
pt(f"\n" + "=" * 65)
pt(f"  最 终 结 论")
pt(f"=" * 65)

issues = []
if len(with_pf) < 30:
    issues.append(f"样本不足({len(with_pf)}场)，任何结论都可能是噪音")
if acc < 40:
    issues.append(f"方向命中率{acc:.1f}%低于随机")
if brier > 0.23:
    issues.append(f"Brier {brier:.3f}接近随机(0.25)，模型无预测能力")
if real_stake > 0 and real_pnl < 0:
    issues.append(f"实盘亏损{real_pnl:.1f}单位")

if issues:
    pt(f"\n  问题: ")
    for i, issue in enumerate(issues, 1):
        pt(f"    {i}. {issue}")
else:
    pt(f"\n  暂未发现明显问题，继续积累数据")

pt(f"\n  建议行动:")
pt(f"    1. 继续用当前版本预测并回填，积累到 100+ 场")
pt(f"    2. 不要根据当前数据做投注决策 (15场不够)")
pt(f"    3. 100场后运行 python skill/update_calibration.py --apply")
pt(f"    4. 100场后重新跑本报告看模型是否有改进")
