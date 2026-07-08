#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
校准分析 + Baseline对比工具 v2.0
v2.0: 自动从 pnl_records.json 读取已结算记录，合并手工录入的 legacy 数据
"""
import sys, json, os
from collections import defaultdict

# 安全打印
def p(text):
    try:
        print(text)
    except UnicodeEncodeError:
        safe = text.encode('utf-8', errors='replace').decode('gbk', errors='replace')
        print(safe)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# 自动从 pnl_records.json 加载已结算记录
# ============================================================

def auto_load_settled():
    """从 pnl_records.json 加载 result!=pending 的记录"""
    pnl_path = os.path.join(BASE_DIR, "数据缓存", "pnl_records.json")
    if not os.path.exists(pnl_path):
        return []

    with open(pnl_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    settled = [r for r in records if r.get("result") not in ("pending",)]
    return settled


def pnl_to_matches(pnl_records):
    """将 pnl_records.json 的记录转换为校准分析的 matches 格式"""
    matches = []
    result_map = {"win": "胜", "loss": "负", "push": "平"}
    for r in pnl_records:
        direction = r.get("direction", "")
        result_raw = r.get("result", "")

        # 判定模型是否正确
        if result_raw == "win":
            correct = "Y"
        elif result_raw == "loss":
            correct = "N"
        else:  # push
            correct = "Y"

        matches.append({
            "date": r.get("date", "")[-5:],  # 取 MM-DD
            "home": r.get("home", ""),
            "away": r.get("away", ""),
            "h_rank": None,
            "a_rank": None,
            "pred": direction,
            "stars": 2,  # 默认，来自 pnl 记录无此字段
            "p_final": r.get("P_final"),
            "result": result_map.get(result_raw, result_raw),
            "score": None,
            "correct": correct,
            "baseline_fav": None,
            "baseline_correct": None,
            "_source": "pnl_records.json",
        })
    return matches


# ============================================================
# Legacy 手工录入数据（保留作为补充源）
# ============================================================

legacy_matches = [
    # === 2026-06-27 世界杯小组赛 (6场) ===
    {"date":"06-27","home":"巴拿马","away":"英格兰","h_rank":None,"a_rank":4,
     "pred":"英格兰胜","stars":3,"p_final":None,
     "result":"英格兰胜","score":"0-2","correct":"Y",
     "baseline_fav":"英格兰","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"06-27","home":"克罗地亚","away":"加纳","h_rank":None,"a_rank":44,
     "pred":"克罗地亚胜","stars":2,"p_final":None,
     "result":"克罗地亚胜","score":"2-1","correct":"Y",
     "baseline_fav":"克罗地亚","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"06-27","home":"哥伦比亚","away":"葡萄牙","h_rank":12,"a_rank":5,
     "pred":"平局","stars":3,"p_final":None,
     "result":"平局","score":"0-0","correct":"Y",
     "baseline_fav":"葡萄牙","baseline_correct":"N",
     "_source":"legacy"},
    {"date":"06-27","home":"民主刚果","away":"乌兹别克斯坦","h_rank":None,"a_rank":None,
     "pred":"民主刚果胜","stars":3,"p_final":None,
     "result":"民主刚果胜","score":"3-1","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    {"date":"06-27","home":"约旦","away":"阿根廷","h_rank":None,"a_rank":1,
     "pred":"阿根廷胜","stars":3,"p_final":None,
     "result":"阿根廷胜","score":"1-3","correct":"Y",
     "baseline_fav":"阿根廷","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"06-27","home":"阿尔及利亚","away":"奥地利","h_rank":None,"a_rank":23,
     "pred":"平局","stars":3,"p_final":None,
     "result":"平局","score":"3-3","correct":"Y",
     "baseline_fav":"奥地利","baseline_correct":"N",
     "_source":"legacy"},
    # === 2026-06-27 芬超 (6场) ===
    {"date":"06-27","home":"赫尔辛基","away":"库奥皮奥","h_rank":999,"a_rank":999,
     "pred":"库奥皮奥不败","stars":2,"p_final":None,
     "result":"库奥皮奥胜","score":"0-4","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    {"date":"06-27","home":"玛丽港","away":"国际图尔库","h_rank":999,"a_rank":999,
     "pred":"国际图尔库胜","stars":2,"p_final":None,
     "result":"国际图尔库胜","score":"0-2","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    {"date":"06-27","home":"TPS图尔库","away":"雅罗","h_rank":999,"a_rank":999,
     "pred":"TPS胜","stars":2,"p_final":None,
     "result":"TPS胜","score":"3-2","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    {"date":"06-27","home":"赫尔辛基火花","away":"瓦萨","h_rank":999,"a_rank":999,
     "pred":"平局","stars":2,"p_final":None,
     "result":"平局","score":"1-1","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    {"date":"06-27","home":"AC奥卢","away":"拉赫蒂","h_rank":999,"a_rank":999,
     "pred":"AC奥卢胜","stars":2,"p_final":None,
     "result":"平局","score":"1-1","correct":"N",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    {"date":"06-27","home":"坦佩雷山猫","away":"塞伊奈约基","h_rank":999,"a_rank":999,
     "pred":"山猫不败","stars":2,"p_final":None,
     "result":"平局","score":"2-2","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    # === 2026-06-28 ===
    {"date":"06-28","home":"南非","away":"加拿大","h_rank":None,"a_rank":None,
     "pred":"加拿大胜","stars":2,"p_final":None,
     "result":"加拿大胜","score":"0-1","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    # === 2026-06-30 1/16决赛 ===
    {"date":"06-30","home":"巴西","away":"日本","h_rank":6,"a_rank":12,
     "pred":"巴西胜","stars":2,"p_final":None,
     "result":"巴西胜","score":"2-1","correct":"Y",
     "baseline_fav":"巴西","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"06-30","home":"德国","away":"巴拉圭","h_rank":10,"a_rank":41,
     "pred":"德国胜","stars":2,"p_final":None,
     "result":"平局","score":"1-1","correct":"N",
     "baseline_fav":"德国","baseline_correct":"N",
     "_source":"legacy"},
    {"date":"06-30","home":"荷兰","away":"摩洛哥","h_rank":7,"a_rank":6,
     "pred":"平局","stars":2,"p_final":None,
     "result":"平局","score":"1-1","correct":"Y",
     "baseline_fav":"荷兰","baseline_correct":"N",
     "_source":"legacy"},
    # === 2026-07-01 1/16决赛 ===
    {"date":"07-01","home":"墨西哥","away":"厄瓜多尔","h_rank":14,"a_rank":34,
     "pred":"平局","stars":2,"p_final":None,
     "result":"墨西哥胜","score":"2-0","correct":"N",
     "baseline_fav":"墨西哥","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"07-01","home":"法国","away":"瑞典","h_rank":2,"a_rank":23,
     "pred":"法国胜","stars":3,"p_final":None,
     "result":"法国胜","score":"3-0","correct":"Y",
     "baseline_fav":"法国","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"07-01","home":"科特迪瓦","away":"挪威","h_rank":40,"a_rank":28,
     "pred":"挪威胜","stars":2,"p_final":None,
     "result":"挪威胜","score":"1-2","correct":"Y",
     "baseline_fav":"挪威","baseline_correct":"Y",
     "_source":"legacy"},
    # === 2026-07-03 1/16决赛+联赛 ===
    {"date":"07-03","home":"西班牙","away":"奥地利","h_rank":3,"a_rank":23,
     "pred":"西班牙胜","stars":3,"p_final":None,
     "result":"西班牙胜","score":"3-0","correct":"Y",
     "baseline_fav":"西班牙","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"07-03","home":"葡萄牙","away":"克罗地亚","h_rank":5,"a_rank":11,
     "pred":"葡萄牙胜","stars":2,"p_final":None,
     "result":"葡萄牙胜","score":"2-1","correct":"Y",
     "baseline_fav":"葡萄牙","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"07-03","home":"哥伦比亚","away":"加纳","h_rank":12,"a_rank":44,
     "pred":"哥伦比亚胜","stars":3,"p_final":None,
     "result":"哥伦比亚胜","score":"1-0","correct":"Y",
     "baseline_fav":"哥伦比亚","baseline_correct":"Y",
     "_source":"legacy"},
    {"date":"07-03","home":"天狼星","away":"米亚尔比","h_rank":999,"a_rank":999,
     "pred":"天狼星不败","stars":2,"p_final":None,
     "result":"平局","score":"4-4","correct":"Y",
     "baseline_fav":None,"baseline_correct":None,
     "_source":"legacy"},
    {"date":"07-03","home":"澳大利亚","away":"埃及","h_rank":38,"a_rank":33,
     "pred":"平局(临场修正)","stars":2,"p_final":None,
     "result":"平局","score":"1-1","correct":"Y",
     "baseline_fav":"埃及","baseline_correct":"N",
     "_source":"legacy"},
    {"date":"07-03","home":"阿根廷","away":"佛得角","h_rank":1,"a_rank":78,
     "pred":"阿根廷胜","stars":3,"p_final":0.625,
     "result":"平局","score":"1-1","correct":"N",
     "baseline_fav":"阿根廷","baseline_correct":"N",
     "_source":"legacy"},
]


def merge_matches():
    """合并 pnl_records.json 自动数据 + legacy 数据，按 (date, home, away) 去重"""
    auto_raw = auto_load_settled()
    auto = pnl_to_matches(auto_raw)

    # 合并：auto 优先覆盖 legacy
    seen = {}
    for m in legacy_matches:
        key = (m["date"], m["home"], m["away"])
        seen[key] = dict(m)

    for m in auto:
        key = (m["date"], m["home"], m["away"])
        if key in seen:
            # auto 数据覆盖，但保留 legacy 中 auto 没有的字段
            seen[key].update({k: v for k, v in m.items() if v is not None or k not in seen[key]})
        else:
            seen[key] = m

    matches = list(seen.values())
    # 按日期排序
    matches.sort(key=lambda x: (x.get("date",""), x.get("home","")))

    # 统计来源
    auto_count = sum(1 for m in matches if m.get("_source") == "pnl_records.json" or any(
        auto_m.get("home") == m["home"] and auto_m.get("away") == m["away"]
        for auto_m in auto))
    p(f"\n[数据] 共 {len(matches)} 场比赛 | pnl_records.json 自动加载 {auto_count} 场 | legacy 补充 {len(matches) - auto_count} 场")

    return matches


# ============================================================
# 加载数据
# ============================================================
matches = merge_matches()


# ============================================================
# 分析1: Baseline对比
# ============================================================
p("=" * 70)
p("P0-1: BASELINE 对 比 分 析")
p("=" * 70)

model_total = 0
model_correct = 0
baseline_total = 0
baseline_correct = 0
both_correct = 0
model_only = 0
baseline_only = 0

for m in matches:
    model_total += 1
    if m["correct"] == "Y":
        model_correct += 1

    if m["baseline_fav"] is not None and m["baseline_correct"] is not None:
        baseline_total += 1
        if m["baseline_correct"] == "Y":
            baseline_correct += 1
        if m["correct"] == "Y" and m["baseline_correct"] == "Y":
            both_correct += 1
        elif m["correct"] == "Y" and m["baseline_correct"] == "N":
            model_only += 1
        elif m["correct"] == "N" and m["baseline_correct"] == "Y":
            baseline_only += 1

p(f"\n总体统计:")
p(f"  总比赛数: {model_total}场")
p(f"  有FIFA排名可做baseline: {baseline_total}场")
p(f"  无FIFA排名(芬超/数据不足): {model_total - baseline_total}场")

p(f"\n模型表现 (全部{model_total}场):")
model_acc = model_correct/model_total*100
p(f"  方向正确: {model_correct}/{model_total} = {model_acc:.1f}%")

p(f"\nBaseline表现 (FIFA排名更高者胜, {baseline_total}场):")
baseline_acc = baseline_correct/baseline_total*100 if baseline_total > 0 else 0
p(f"  方向正确: {baseline_correct}/{baseline_total} = {baseline_acc:.1f}%")

p(f"\n交叉对比 ({baseline_total}场有排名):")
p(f"  模型+Baseline都对: {both_correct}场 ({both_correct/baseline_total*100:.1f}%)")
p(f"  模型对,Baseline错(模型附加值): {model_only}场 ({model_only/baseline_total*100:.1f}%)")
p(f"  模型错,Baseline对(模型减分): {baseline_only}场 ({baseline_only/baseline_total*100:.1f}%)")

bl_adjusted = (model_correct - (model_total - baseline_total)) / baseline_total * 100 if baseline_total > 0 else 0
p(f"\n净效果 (仅看有排名的{baseline_total}场):")
p(f"  模型: {model_correct - (model_total - baseline_total)}/{baseline_total} = {bl_adjusted:.1f}%")
p(f"  Baseline: {baseline_correct}/{baseline_total} = {baseline_acc:.1f}%")
net = bl_adjusted - baseline_acc
if net > 0:
    p(f"  模型净比Baseline好 {net:.1f}个百分点 --- 模型有附加价值")
else:
    p(f"  模型净比Baseline差 {abs(net):.1f}个百分点 --- 模型在减分")


# 按赛事类型细分
p(f"\n\n按赛事类型细分:")
events = defaultdict(lambda: {"total":0, "correct":0, "bl_total":0, "bl_correct":0})
for m in matches:
    if m["h_rank"] == 999:
        event = "联赛(芬超/瑞典超)"
    elif m["date"].startswith("06-27"):
        event = "世界杯小组赛"
    elif any(m["date"].startswith(d) for d in ["06-30","07-01","07-03"]):
        event = "世界杯淘汰赛"
    else:
        event = "其他"

    events[event]["total"] += 1
    if m["correct"] == "Y":
        events[event]["correct"] += 1
    if m["baseline_fav"] is not None:
        events[event]["bl_total"] += 1
        if m["baseline_correct"] == "Y":
            events[event]["bl_correct"] += 1

for event, data in sorted(events.items()):
    acc = data["correct"]/data["total"]*100 if data["total"] > 0 else 0
    bl_acc = data["bl_correct"]/data["bl_total"]*100 if data["bl_total"] > 0 else 0
    bl_str = f" | Baseline: {data['bl_correct']}/{data['bl_total']}={bl_acc:.0f}%" if data["bl_total"] > 0 else " | Baseline: N/A"
    p(f"  {event}: {data['correct']}/{data['total']} = {acc:.1f}%{bl_str}")


# ============================================================
# 分析2: 概率校准
# ============================================================
p(f"\n\n{'='*70}")
p("P0-2: 概 率 校 准 表")
p("=" * 70)

star_buckets = defaultdict(lambda: {"total":0, "correct":0, "matches":[]})
for m in matches:
    stars = m["stars"]
    star_buckets[stars]["total"] += 1
    if m["correct"] == "Y":
        star_buckets[stars]["correct"] += 1
    label = f"{m['home']}vs{m['away']}({m['result']})"
    star_buckets[stars]["matches"].append(label)

implied_map = {3: 85, 2: 70, 1: 55}

p(f"\n  {'评级':<8} {'场次':<6} {'正确':<6} {'实际胜率':<10} {'隐含概率':<10} {'校准因子':<10} {'状态'}")
p(f"  {'-'*65}")
for stars in sorted(star_buckets.keys(), reverse=True):
    d = star_buckets[stars]
    rate = d["correct"]/d["total"]*100 if d["total"] > 0 else 0
    implied = implied_map.get(stars, 50)
    cal = rate / implied if implied > 0 else 0
    if cal < 0.80:
        note = "高估(过度自信)"
    elif cal > 1.20:
        note = "低估(过于保守)"
    else:
        note = "校准合理"
    star_label = "*" * stars if stars else "无"
    p(f"  {star_label:<8} {d['total']:<6} {d['correct']:<6} {rate:<8.1f}% {implied:<8}% {cal:<9.2f} {note}")


# ============================================================
# 分析3: 偏差索引命中率
# ============================================================
p(f"\n\n{'='*70}")
p("P0-3: 偏 差 索 引 命 中 率")
p("=" * 70)

p(f"\n根据已有偏差分析记录，识别从未触发的偏差:")
all_devs = [f"#{i:03d}" for i in range(1, 32)]
triggered_devs = ["#001","#002","#003","#004","#005","#007","#008","#009",
                  "#011","#012","#013","#016","#017","#021","#025","#026","#029"]
dead_devs = [d for d in all_devs if d not in triggered_devs]

p(f"\n  共{len(all_devs)}条偏差索引")
p(f"  有触发记录: {len(triggered_devs)}条")
p(f"  从未触发(可能为死代码): {len(dead_devs)}条")
p(f"  {', '.join(dead_devs)}")


# ============================================================
# 总结
# ============================================================
p(f"\n\n{'='*70}")
p("P0 执 行 结 果 总 结")
p("=" * 70)

p(f"""
模型总体准确率:        {model_correct}/{model_total} = {model_acc:.1f}%
Baseline准确率:        {baseline_correct}/{baseline_total} = {baseline_acc:.1f}%
模型净附加值:          {model_only}场对 + {baseline_only}场错 = {model_only-baseline_only:+d}场净胜

Star评级校准状态:""")

for stars in sorted(star_buckets.keys(), reverse=True):
    d = star_buckets[stars]
    rate = d["correct"]/d["total"]*100 if d["total"] > 0 else 0
    implied = implied_map.get(stars, 50)
    cal = rate / implied if implied > 0 else 0
    star_label = "*" * stars if stars else "无"
    if 0.85 <= cal <= 1.15:
        status = "[OK]"
    elif cal > 1.15:
        status = "[低估]"
    else:
        status = "[高估]"
    p(f"  {star_label}: 隐含={implied}% 实际={rate:.1f}% 因子={cal:.2f} {status}")

p(f"""
当前结论:
1. 模型在{model_total}场样本中准确率{model_acc:.1f}%, 在可对比的{baseline_total}场中比
   FIFA排名基准高{net:.1f}个百分点。
2. {'*'*3}区间存在{'高估' if star_buckets[3]['correct']/star_buckets[3]['total']*100 < 85 else '合理'}倾向。
3. 偏差索引中{len(dead_devs)}条从未触发, 建议退役以降低复杂度。
4. 校准数据自动从 pnl_records.json 加载中。建议赛后及时更新结果。
""")
