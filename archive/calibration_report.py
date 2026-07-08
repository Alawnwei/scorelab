#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准分析报告 — 合并 pnl_records + auto_results + MD预测文件
验证 P_final 是否校准、方向命中率
"""
import sys, json, glob, re, os

def p(text):
    try:
        safe = str(text).encode("utf-8", errors="replace").decode("gbk", errors="replace")
        print(safe)
    except:
        safe = str(text).encode("utf-8", errors="replace").decode("gbk", errors="ignore")
        print(safe)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
PRED_DIR = os.path.join(BASE_DIR, "预测数据")

def normalize(s):
    return s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")

# ============================================================
# 1. 加载数据
# ============================================================
with open(os.path.join(CACHE_DIR, "pnl_records.json"), "r", encoding="utf-8") as f:
    pnl = json.load(f)
with open(os.path.join(CACHE_DIR, "auto_results.json"), "r", encoding="utf-8") as f:
    auto = json.load(f)

settled = [r for r in pnl["records"] if r["result"] != "pending"]
finished = [r for r in auto if r["status"] == "FINISHED"]

p(f"pnl_records 已结算: {len(settled)} 条")
p(f"auto_results 已完赛: {len(finished)} 场")

# ============================================================
# 2. 从 pnl_records 构建匹配数据
# ============================================================
def get_result_from_pnl(r):
    """从 pnl_record 获取比分和实际结果"""
    h, a = r["home"], r["away"]
    notes = r.get("notes", "")
    sm = re.search(r"(\d+)[-](\d+)", notes)
    if sm:
        hg, ag = int(sm.group(1)), int(sm.group(2))
    elif r["result"] == "win":
        d = r.get("direction", "")
        if "主" in d: hg, ag = 1, 0
        elif "客" in d: hg, ag = 0, 1
        else: return None
    elif r["result"] == "loss":
        d = r.get("direction", "")
        if "主" in d: hg, ag = 0, 1
        elif "客" in d: hg, ag = 1, 0
        elif "平" in d or "均衡" in d: hg, ag = 1, 0
        else: return None
    else:
        return None

    if hg > ag: actual_dir = "主胜"
    elif hg < ag: actual_dir = "客胜"
    else: actual_dir = "平局"
    return (hg, ag, actual_dir)

def check_correct(pred_dir, actual_dir):
    """判断方向命中"""
    if not pred_dir:
        return None
    if "主" in pred_dir and "客" not in pred_dir and actual_dir == "主胜": return True
    if "客" in pred_dir and actual_dir == "客胜": return True
    if "平" in pred_dir and actual_dir == "平局": return True
    if "均衡" in pred_dir and actual_dir == "平局": return True
    if pred_dir == actual_dir: return True
    return False

all_matches = []
seen = set()

for r in settled:
    if r.get("P_final", 0) <= 0:
        continue
    h, a = r["home"], r["away"]
    pair = (h, a)
    if pair in seen:
        continue

    result = get_result_from_pnl(r)
    if not result:
        continue
    hg, ag, actual_dir = result
    pred_dir = r.get("direction", "")
    correct = check_correct(pred_dir, actual_dir)

    seen.add(pair)
    all_matches.append({
        "home": h, "away": a, "p_final": r["P_final"],
        "direction": pred_dir, "score": f"{hg}-{ag}",
        "actual_dir": actual_dir, "correct": correct,
    })

p(f"pnl_records 提取: {len(all_matches)} 场")

# ============================================================
# 3. 从 MD 文件补充 P_final（未在 pnl 中的比赛）
# ============================================================
md_files = sorted(glob.glob(os.path.join(PRED_DIR, "足球预测-*.md")))
for fpath in md_files:
    fname = os.path.basename(fpath)
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    pf_match = re.search(r"\*\*P_final\*\*\s*\|\s*\*\*([\d.]+)\*\*", content)
    if not pf_match:
        continue
    p_final = float(pf_match.group(1))

    stem = fname.replace(".md", "")
    tm = re.search(r"(\d{4}-\d{2}-\d{2})[-]*(.+?)(vs)(.+?)$", stem)
    if not tm:
        continue
    home = tm.group(2).strip("-").strip()
    away = tm.group(4).strip()
    if "-" in home:
        home = home.split("-")[-1]

    pair = (home, away)
    if pair in seen:
        continue

    # 在 auto_results 中匹配赛果
    matched = False
    for ar in finished:
        arh = normalize(ar.get("home_cn", ""))
        ara = normalize(ar.get("away_cn", ""))
        hn = normalize(home)
        an = normalize(away)
        if (hn == arh and an == ara) or (hn == ara and an == arh):
            ft = ar["score_ft"]
            if "-" in ft:
                parts = ft.split("-")
                try:
                    hg, ag = int(parts[0]), int(parts[1])
                    actual_dir = "主胜" if hg > ag else ("客胜" if hg < ag else "平局")
                    seen.add(pair)
                    all_matches.append({
                        "home": home, "away": away, "p_final": p_final,
                        "direction": "", "score": f"{hg}-{ag}",
                        "actual_dir": actual_dir, "correct": None,
                    })
                    matched = True
                except:
                    pass
            break

    if not matched:
        # P_final 在 MD 中有但还没赛果
        seen.add(pair)
        all_matches.append({
            "home": home, "away": away, "p_final": p_final,
            "direction": "", "score": "?",
            "actual_dir": "?", "correct": None,
        })

p(f"MD文件补充: 总 {len(all_matches)} 场 (含无赛果)")

# ============================================================
# 4. 生成校准报告
# ============================================================
with_result = [m for m in all_matches if m.get("score") != "?"]
no_result = [m for m in all_matches if m.get("score") == "?"]
with_dir = [m for m in with_result if m["correct"] is not None]
no_dir = [m for m in with_result if m["correct"] is None]

correct = sum(1 for m in with_dir if m["correct"])
wrong = len(with_dir) - correct
accuracy = correct / len(with_dir) * 100 if with_dir else 0

p("\n" + "=" * 70)
p("  P_final 校 准 分 析 报 告")
p("=" * 70)

p(f"\n[1] 总样本")
p(f"  总预测: {len(all_matches)} 场")
p(f"  已有赛果: {len(with_result)} 场")
p(f"  尚无赛果(今晚或未来): {len(no_result)} 场")
p(f"  有方向可验证: {len(with_dir)} 场 (正确={correct}, 错误={wrong})")
if with_dir:
    p(f"  方向命中率: {accuracy:.1f}%")
p(f"  仅有比分无方向: {len(no_dir)} 场 (不参与准确率统计)")

p(f"\n[2] P_final 校准表 (有方向可验证)")
p(f"  {'区间':<14} {'场次':<6} {'胜':<6} {'实际胜率':<10} {'平均P_final':<12} {'隐含概率':<10} {'校准因子':<10} 评价")
p(f"  " + "-" * 72)

buckets = [(0.80, 1.01, ">=0.80"), (0.70, 0.80, "0.70-0.79"),
           (0.60, 0.70, "0.60-0.69"), (0.50, 0.60, "0.50-0.59"),
           (0.40, 0.50, "0.40-0.49"), (0.30, 0.40, "0.30-0.39"),
           (0.00, 0.30, "<0.30")]

for lo, hi, label in buckets:
    bucket = [m for m in with_dir if lo <= m["p_final"] < hi]
    if not bucket:
        continue
    bt = len(bucket)
    bc = sum(1 for m in bucket if m["correct"])
    wr = bc / bt * 100
    avg_p = sum(m["p_final"] for m in bucket) / bt
    implied = avg_p * 100
    cf = wr / implied if implied > 0 else 0
    if bt < 3:
        remark = "样本不足"
    elif cf > 1.15:
        remark = "[保守] 预测偏低"
    elif cf < 0.85:
        remark = "[过度自信] 预测偏高"
    else:
        remark = "[OK] 校准合理"
    p(f"  {label:<14} {bt:<6} {bc:<6} {wr:<8.1f}%   {avg_p:<9.3f}    {implied:<8.1f}%   {cf:<9.2f}  {remark}")

# 无方向的
has_nodir_bucket = False
for lo, hi, label in buckets:
    bucket = [m for m in no_dir if lo <= m["p_final"] < hi]
    if not has_nodir_bucket and bucket:
        p(f"\n  (以下 {len(no_dir)} 场无方向，仅显示分布)")
        has_nodir_bucket = True
    if bucket:
        bt = len(bucket)
        avg_p = sum(m["p_final"] for m in bucket) / bt
        p(f"  {label:<14} {bt:<6} {'?':<6} {'?':>8}    {avg_p:<9.3f}")

p(f"\n[3] 方向准确率 (按方向分组)")
dirs = {}
for m in with_dir:
    d = m.get("direction", "")
    if not d:
        d = "未知"
    if "主" in d and "客" not in d:
        dr = "主胜"
    elif "客" in d:
        dr = "客胜"
    elif "平" in d or "均衡" in d:
        dr = "平局/均衡"
    else:
        dr = d[:8]
    dirs.setdefault(dr, {"t": 0, "c": 0})
    dirs[dr]["t"] += 1
    if m["correct"]:
        dirs[dr]["c"] += 1

for d, v in sorted(dirs.items()):
    r = v["c"] / v["t"] * 100 if v["t"] > 0 else 0
    tag = "[OK]" if r > 50 else ("[WARN]" if r > 30 else "[BAD]")
    p(f"  {tag} {d:<14}: {v['c']}/{v['t']} = {r:.1f}%")

p(f"\n[4] 全部记录 (按 P_final 降序)")
p(f"  {'排名':<5} {'比赛':<28} {'P_final':<8} {'方向':<12} {'比分':<8} {'结果'}")
p(f"  " + "-" * 65)
sorted_all = sorted(all_matches, key=lambda x: x["p_final"], reverse=True)
for i, m in enumerate(sorted_all):
    if m.get("score") == "?":
        mrk = "..."
    elif m["correct"] is True:
        mrk = "+"
    elif m["correct"] is False:
        mrk = "x"
    else:
        mrk = "?"
    label = f"{m['home'][:6]}vs{m['away'][:6]}"
    d = m.get("direction", "")[:10]
    sc = m.get("score", "?")
    p(f"  #{i+1:<3} {label:<28} {m['p_final']:.3f}   {d:<12} {sc:<8} {mrk}")

# ============================================================
# 5. 结论
# ============================================================
p(f"\n[5] 关键发现")
if with_dir:
    high = [m for m in with_dir if m["p_final"] >= 0.70]
    mid = [m for m in with_dir if 0.40 <= m["p_final"] < 0.70]
    low = [m for m in with_dir if m["p_final"] < 0.40]
    if high:
        hc = sum(1 for m in high if m["correct"])
        p(f"  高置信(P>=0.70): {hc}/{len(high)} = {hc/len(high)*100:.1f}%")
    if mid:
        mc = sum(1 for m in mid if m["correct"])
        p(f"  中等置信(0.40~0.69): {mc}/{len(mid)} = {mc/len(mid)*100:.1f}%")
    if low:
        lc = sum(1 for m in low if m["correct"])
        p(f"  低置信(P<0.40): {lc}/{len(low)} = {lc/len(low)*100:.1f}%")
    p(f"\n  综合: {correct}/{len(with_dir)} = {accuracy:.1f}% 方向命中率")
    p(f"  PnL: 仅下注比赛算盈亏; 校准看所有预测")

# ============================================================
# 保存结构化数据
# ============================================================
output = {
    "total_predictions": len(all_matches),
    "with_results": len(with_result),
    "judged": len(with_dir),
    "correct": correct,
    "wrong": wrong,
    "accuracy_pct": round(accuracy, 1),
    "matches": all_matches,
}
out_path = os.path.join(CACHE_DIR, "calibration_data.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
p(f"\n 数据已保存到 calibration_data.json")
