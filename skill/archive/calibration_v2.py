#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准分析 v2.0 — 从所有数据源汇总 P_final 校准
数据源: 预测MD文件 + auto_results.json + pnl_records.json
"""
import sys, json, glob, re, os

def p(text):
    try:
        safe = str(text).encode('utf-8', errors='replace').decode('gbk', errors='replace')
        print(safe)
    except:
        safe = str(text).encode('utf-8', errors='replace').decode('gbk', errors='ignore')
        print(safe)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
PRED_DIR = os.path.join(BASE_DIR, "预测数据")

def normalize(s):
    return s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")

def extract_pfinal(content):
    """提取 P_final 值"""
    patterns = [
        r'\*\*P_final\*\*\s*\|\s*\*\*([\d.]+)\*\*',
        r'[Pp]_final\s*[=:≈]\s*([\d.]+)',
        r'[Pp]_final[^0-9.]*?([\d.]+)',
        r'\*\*P_final\*\*\s*\|\s*([\d.]+)',
        r'\|\s*P_final\s*\|\s*([\d.]+)',
    ]
    for pat in patterns:
        m = re.search(pat, content)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None

def extract_direction(content):
    """从预测文件内容提取推荐方向"""
    patterns = [
        r'推荐方向[：:]\s*(\S+)',
        r'方向[：:]\s*(\S+)',
        r'预测[：:]\s*(\S+)',
        r'推荐[：:]\s*(\S+)',
        r'\*\*预测方向\*\*[：:]?\s*\*\*(\S+)\*\*',
        r'\*\*推荐方向\*\*[：:]?\s*\*\*(\S+)\*\*',
        r'\*\*方向\*\*[：:]?\s*\*\*(\S+)\*\*',          # **方向**:**主胜**
        r'###.*?方向\d*[：:]\s*(\S+)',                  # ### 方向1: 平局
        r'方向\d*[：:]\s*([^<>\n]{2,8}?)',              # 方向1：平局/客胜
    ]
    for pat in patterns:
        m = re.search(pat, content)
        if m:
            result = m.group(1).strip()
            if len(result) <= 10:  # 避免取到过长文本
                return result
    return ""

def infer_actual_from_result(home, away, result_type, direction):
    """从 pnl_records 的 result 和 direction 反推实际结果"""
    if result_type == "win":
        if "主" in direction: return (1, 0, "主胜")
        if "客" in direction: return (0, 1, "客胜")
        # 如果是平局方向就win不了
    elif result_type == "loss":
        if "主" in direction: return (0, 1, "客胜")     # 预测主胜输了 -> 客胜
        if "客" in direction: return (1, 0, "主胜")     # 预测客胜输了 -> 主胜
        if "平" in direction or "均衡" in direction:
            return (1, 0, "主胜")                       # 预测平局输了 -> 不是平局，默认为主胜
    return None

def match_result(home_cn, away_cn, auto_results, pnl_records):
    """匹配实际赛果"""
    h_norm = normalize(home_cn)
    a_norm = normalize(away_cn)

    # 在 auto_results 中找赛果
    for ar in auto_results:
        arh = normalize(ar.get("home_cn", ""))
        ara = normalize(ar.get("away_cn", ""))
        if (h_norm == arh and a_norm == ara) or (h_norm == ara and a_norm == arh):
            ft = ar.get("score_ft", "")
            if "-" in ft:
                parts = ft.split("-")
                try:
                    hg, ag = int(parts[0]), int(parts[1])
                    if hg > ag: actual_dir = "主胜"
                    elif hg < ag: actual_dir = "客胜"
                    else: actual_dir = "平局"
                    return (hg, ag, actual_dir)
                except:
                    pass
            break

    # 在 pnl_records 中找赛果（从 notes 提取比分 或 从 score_ft/score 字段）
    for r in pnl_records:
        ph = normalize(r.get("home", ""))
        pa = normalize(r.get("away", ""))
        if (h_norm == ph and a_norm == pa) or (h_norm == pa and a_norm == ph):
            # 尝试从 notes 提取比分
            notes = r.get("notes", "")
            sm = re.search(r"(\d+)[-](\d+)", notes)
            if sm:
                hg, ag = int(sm.group(1)), int(sm.group(2))
                if hg > ag: actual_dir = "主胜"
                elif hg < ag: actual_dir = "客胜"
                else: actual_dir = "平局"
                return (hg, ag, actual_dir)
            # 从 result 字段反向推断
            result = r.get("result", "")
            inferred = infer_actual_from_result(h, a, result, r.get("direction", ""))
            if inferred:
                return inferred
            break
    return None

def is_correct(pred_dir, actual_dir):
    """判断方向是否命中, 无方向返回 None"""
    if not pred_dir:
        return None
    if "主" in pred_dir and "客" not in pred_dir and actual_dir == "主胜": return True
    if "客" in pred_dir and actual_dir == "客胜": return True
    if "平" in pred_dir and actual_dir == "平局": return True
    if "均衡" in pred_dir and actual_dir == "平局": return True
    if pred_dir == actual_dir: return True
    # 如果方向里有主也有客（如主胜/客胜）但没精确匹配
    return False

# ============================================================
# 1. 加载数据
# ============================================================
# pnl_records
pnl_path = os.path.join(CACHE_DIR, "pnl_records.json")
if os.path.exists(pnl_path):
    with open(pnl_path, "r", encoding="utf-8") as f:
        pnl = json.load(f)
    pnl_records = pnl.get("records", [])
else:
    pnl_records = []
p(f"pnl_records: {len(pnl_records)} 条")

# auto_results (已完赛)
auto_path = os.path.join(CACHE_DIR, "auto_results.json")
if os.path.exists(auto_path):
    with open(auto_path, "r", encoding="utf-8") as f:
        auto_results = json.load(f)
    finished = [r for r in auto_results if r.get("status") == "FINISHED"]
else:
    finished = []
p(f"auto_results 已完赛: {len(finished)} 场")

# ============================================================
# 2. 从MD文件提取 P_final
# ============================================================
md_files = sorted(glob.glob(os.path.join(PRED_DIR, "足球预测-*.md")))
p(f"预测MD文件: {len(md_files)} 个")

predictions = []
seen_pairs = set()

for fpath in md_files:
    fname = os.path.basename(fpath)
    with open(fpath, "r", encoding="utf-8") as f:
        content = f.read()

    p_final = extract_pfinal(content)
    if p_final is None:
        continue

    direction = extract_direction(content)

    # 从文件名提取队名
    stem = fname.replace(".md", "")
    team_match = re.search(r"(\d{4}-\d{2}-\d{2})[-]*(.+?)(vs)(.+?)$", stem)
    if team_match:
        teams_part = team_match.group(2).strip("-")
        home = teams_part.strip()
        away = team_match.group(4).strip()
        if "-" in home:
            home = home.split("-")[-1]
    else:
        continue

    if not home or not away:
        continue

    pair = (home.strip(), away.strip())
    if pair in seen_pairs:
        continue
    seen_pairs.add(pair)

    predictions.append({
        "home": home.strip(),
        "away": away.strip(),
        "p_final": p_final,
        "direction": direction,
        "source_file": fname,
    })
    p(f"  [提取] {home.strip():10s} vs {away.strip():10s}  P_final={p_final:.3f}  方向={direction or '(空)'}")

p(f"\n预测文件解析: {len(predictions)} 场有效预测")

# ============================================================
# 3. 匹配赛果
# ============================================================
all_matches = []
seen_match = set()

for pred in predictions:
    h, a = pred["home"], pred["away"]
    pair = (h, a)
    if pair in seen_match:
        continue

    result = match_result(h, a, finished, pnl_records)
    if result:
        hg, ag, actual_dir = result
        pred_dir = pred["direction"]
        correct = is_correct(pred_dir, actual_dir)
        seen_match.add(pair)
        all_matches.append({
            "home": h, "away": a, "p_final": pred["p_final"],
            "direction": pred_dir, "actual_result": actual_dir,
            "score": f"{hg}-{ag}", "correct": correct,
        })

# 补充 pnl_records 中未匹配到的
for r in pnl_records:
    h, a = r["home"], r["away"]
    pair = (h, a)
    if pair in seen_match or r["result"] == "pending" or r.get("P_final", 0) <= 0:
        continue
    result = match_result(h, a, finished, pnl_records)
    if result:
        hg, ag, actual_dir = result
        pred_dir = r.get("direction", "")
        correct = is_correct(pred_dir, actual_dir)
        seen_match.add(pair)
        all_matches.append({
            "home": h, "away": a, "p_final": r["P_final"],
            "direction": pred_dir, "actual_result": actual_dir,
            "score": f"{hg}-{ag}", "correct": correct,
        })

p(f"成功匹配赛果: {len(all_matches)} 场\n")

# ============================================================
# 4. 校准分析
# ============================================================
if not all_matches:
    p("没有可用的校准数据")
    sys.exit(0)

total = len(all_matches)
correct = sum(1 for m in all_matches if m["correct"] is True)
wrong = sum(1 for m in all_matches if m["correct"] is False)
unknown = sum(1 for m in all_matches if m["correct"] is None)
judged = correct + wrong  # 有方向可判断的
accuracy = correct / judged * 100 if judged > 0 else 0

p("=" * 70)
p("  校 准 分 析 报 告")
p("=" * 70)

# --- 1. 总体统计 ---
p("\n[1] 总体")
p(f"  总样本: {total} 场")
p(f"  方向正确: {correct} 场 ({accuracy:.1f}%)")
p(f"  方向错误: {wrong} 场 ({100-accuracy:.1f}%)")

# --- 2. P_final 分桶校准 ---
p("\n[2] P_final 校准表 (核心)")
header = f"  {'区间':<16} {'场次':<6} {'正确':<6} {'实际胜率':<10} {'隐含概率':<12} {'校准因子':<10} 评价"
p(header)
p("  " + "-" * 70)

buckets = [
    (0.80, 1.01, ">= 0.80"),
    (0.70, 0.80, "0.70~0.79"),
    (0.60, 0.70, "0.60~0.69"),
    (0.50, 0.60, "0.50~0.59"),
    (0.40, 0.50, "0.40~0.49"),
    (0.30, 0.40, "0.30~0.39"),
    (0.00, 0.30, "< 0.30"),
]

total_bucket_samples = 0
for lo, hi, label in buckets:
    bucket = [m for m in all_matches if lo <= m["p_final"] < hi]
    if not bucket:
        continue
    b_total = len(bucket)
    b_correct = sum(1 for m in bucket if m["correct"])
    b_win_rate = b_correct / b_total * 100
    avg_p = sum(m["p_final"] for m in bucket) / b_total
    implied = avg_p * 100
    cal_factor = b_win_rate / implied if implied > 0 else 0
    total_bucket_samples += b_total

    if cal_factor > 1.15:
        remark = "[低估 太保守]"
    elif cal_factor < 0.85:
        remark = "[高估 过度自信]"
    else:
        remark = "[OK 校准合理]"

    p(f"  {label:<16} {b_total:<6} {b_correct:<6} {b_win_rate:<8.1f}%   {implied:<8.1f}%     {cal_factor:<8.2f}  {remark}")

# --- 3. 方向细分 ---
p("\n[3] 方向命中率")
directions = {}
for m in all_matches:
    d = m.get("direction", "")
    if not d:
        d = "未知"
    key = d[:6]
    directions.setdefault(key, {"total": 0, "correct": 0})
    directions[key]["total"] += 1
    if m["correct"]:
        directions[key]["correct"] += 1

for d, v in sorted(directions.items()):
    rate = v["correct"] / v["total"] * 100 if v["total"] > 0 else 0
    tag = "[OK]" if rate > 50 else "[WARN]" if rate > 30 else "[BAD]"
    p(f"  {tag} {d:<12}: {v['correct']}/{v['total']} = {rate:.1f}%")

# --- 4. P_final 排序 ---
p("\n[4] 高置信预测明细 (P_final 降序)")
sorted_matches = sorted(all_matches, key=lambda x: x["p_final"], reverse=True)
p(f"  {'排名':<5} {'比赛':<28} {'P_final':<8} {'方向':<10} {'实际':<6} 结果")
p(f"  " + "-" * 60)
for i, m in enumerate(sorted_matches[:12]):
    mark = "+" if m["correct"] else "x"
    label = f"{m['home'][:6]}vs{m['away'][:6]}"
    p(f"  #{i+1:<3} {label:<28} {m['p_final']:.3f}   {m['direction'][:8]:<10} {m['actual_result']:<6} {mark}")
if len(sorted_matches) > 12:
    p(f"  ... 共 {len(sorted_matches)} 场")

# --- 5. 来源细分 ---
p("\n[5] 数据来源")
from_files = sum(1 for m in all_matches if any(m["home"] in p["home"] and m["away"] in p["away"] for p in predictions))
from_pnl = total - from_files
p(f"  MD预测文件匹配: {from_files} 场")
p(f"  pnl_records补充: {from_pnl} 场")

# --- 6. 结论 ---
p("\n[6] 关键发现")
high_conf = [m for m in all_matches if m["p_final"] >= 0.70]
low_conf = [m for m in all_matches if m["p_final"] < 0.40]
mid_conf = [m for m in all_matches if 0.40 <= m["p_final"] < 0.70]

if high_conf:
    hc_c = sum(1 for m in high_conf if m["correct"])
    hc_r = hc_c / len(high_conf) * 100
    tag = "[OK]" if hc_r >= 70 else "[WARN]"
    p(f"  高置信 (P>=0.70): {hc_c}/{len(high_conf)} = {hc_r:.1f}% {tag}")
if mid_conf:
    mc_c = sum(1 for m in mid_conf if m["correct"])
    mc_r = mc_c / len(mid_conf) * 100
    tag = "[OK]" if 40 <= mc_r <= 60 else "[WARN]"
    p(f"  中等置信 (0.40~0.69): {mc_c}/{len(mid_conf)} = {mc_r:.1f}% {tag}")
if low_conf:
    lc_c = sum(1 for m in low_conf if m["correct"])
    lc_r = lc_c / len(low_conf) * 100
    tag = "[OK]" if lc_r <= 30 else "[WARN]"
    p(f"  低置信 (P<0.40): {lc_c}/{len(low_conf)} = {lc_r:.1f}% {tag}")

# 找出最不准的区间
worst_bucket = None
worst_factor = 999
for lo, hi, label in buckets:
    bucket = [m for m in all_matches if lo <= m["p_final"] < hi]
    if len(bucket) >= 3:
        b_correct = sum(1 for m in bucket if m["correct"])
        b_win_rate = b_correct / len(bucket) * 100
        avg_p = sum(m["p_final"] for m in bucket) / len(bucket)
        cal = b_win_rate / (avg_p * 100) if avg_p > 0 else 1
        diff = abs(1 - cal)
        if diff > abs(1 - worst_factor):
            worst_factor = cal
            worst_bucket = (label, cal, b_win_rate)

if worst_bucket:
    tag = "过度自信" if worst_bucket[1] < 1 else "过于保守"
    p(f"\n  >> 最大偏差区间: {worst_bucket[0]} (校准因子={worst_bucket[1]:.2f}, {tag})")
    p(f"     预测隐含概率约{(worst_bucket[2]/worst_bucket[1]):.0f}%, 实际{worst_bucket[2]:.0f}%")

# ============================================================
# 保存
# ============================================================
output = {
    "generated_at": "2026-07-05 07:00",
    "total_samples": total,
    "accuracy": round(accuracy, 1),
    "matches": all_matches,
}
out_path = os.path.join(CACHE_DIR, "calibration_data.json")
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)
p(f"\n 数据已保存到: calibration_data.json")
