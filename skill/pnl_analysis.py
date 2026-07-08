#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PnL/Sharpe + 版本对比 + 错误归因 综合分析工具 v2.0
v2.0: 自动从 pnl_records.json 读取已结算记录，合并手工录入的 legacy 数据
"""
import sys, json, os
from collections import defaultdict

def p(text):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode('utf-8', errors='replace').decode('gbk', errors='replace'))

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
    return [r for r in data.get("records", []) if r.get("result") not in ("pending",)]


def pnl_to_matches(pnl_records):
    """将 pnl_records 转换为 PnL分析的 matches 格式"""
    matches = []
    result_map = {"win": "W", "loss": "L", "push": "D"}
    for r in pnl_records:
        direction = r.get("direction", "")
        result_raw = r.get("result", "")
        correct = "Y" if result_raw == "win" else ("N" if result_raw == "loss" else "Y")

        # 从 direction 反推 event
        league = r.get("league", "")
        if "世界杯" in league or "WC" in league.upper() or "wm26" in league:
            event = "世界杯"
        elif "芬超" in league or "sportsdb" in league:
            event = "联赛(北欧)"
        elif "K1" in league or "k1" in league or "kleague" in league:
            event = "K联赛"
        elif "瑞典超" in league or "瑞典" in league:
            event = "瑞典超"
        else:
            event = league if league else "其他"

        matches.append({
            "date": r.get("date", ""),
            "home": r.get("home", ""),
            "away": r.get("away", ""),
            "pred": direction,
            "odds": r.get("odds", 0),
            "result": result_map.get(result_raw, result_raw),
            "correct": correct,
            "stars": 2,
            "event": event,
            "h_rank": 999 if event in ("联赛(北欧)", "瑞典超", "K联赛") else None,
            "a_rank": 999 if event in ("联赛(北欧)", "瑞典超", "K联赛") else None,
            "_source": "pnl_records.json",
        })
    return matches


# ============================================================
# Legacy 手工录入数据（保留作为补充源）
# ============================================================

legacy_matches = [
    {"date":"06-27","home":"巴拿马","away":"英格兰","pred":"英格兰胜","odds":1.20,"result":"W","correct":"Y","stars":3,"event":"世界杯小组赛","h_rank":None,"a_rank":4,"_source":"legacy"},
    {"date":"06-27","home":"克罗地亚","away":"加纳","pred":"克罗地亚胜","odds":1.55,"result":"W","correct":"Y","stars":2,"event":"世界杯小组赛","h_rank":None,"a_rank":44,"_source":"legacy"},
    {"date":"06-27","home":"哥伦比亚","away":"葡萄牙","pred":"平局","odds":3.20,"result":"D","correct":"Y","stars":3,"event":"世界杯小组赛","h_rank":12,"a_rank":5,"_source":"legacy"},
    {"date":"06-27","home":"民主刚果","away":"乌兹别克斯坦","pred":"民主刚果胜","odds":2.10,"result":"W","correct":"Y","stars":3,"event":"世界杯小组赛","h_rank":None,"a_rank":None,"_source":"legacy"},
    {"date":"06-27","home":"约旦","away":"阿根廷","pred":"阿根廷胜","odds":1.15,"result":"W","correct":"Y","stars":3,"event":"世界杯小组赛","h_rank":None,"a_rank":1,"_source":"legacy"},
    {"date":"06-27","home":"阿尔及利亚","away":"奥地利","pred":"平局","odds":3.30,"result":"D","correct":"Y","stars":3,"event":"世界杯小组赛","h_rank":None,"a_rank":23,"_source":"legacy"},
    {"date":"06-27","home":"赫尔辛基","away":"库奥皮奥","pred":"库奥皮奥不败","odds":1.80,"result":"W","correct":"Y","stars":2,"event":"芬超","h_rank":999,"a_rank":999,"_source":"legacy"},
    {"date":"06-27","home":"玛丽港","away":"国际图尔库","pred":"国际图尔库胜","odds":2.20,"result":"W","correct":"Y","stars":2,"event":"芬超","h_rank":999,"a_rank":999,"_source":"legacy"},
    {"date":"06-27","home":"TPS图尔库","away":"雅罗","pred":"TPS胜","odds":2.00,"result":"W","correct":"Y","stars":2,"event":"芬超","h_rank":999,"a_rank":999,"_source":"legacy"},
    {"date":"06-27","home":"赫尔辛基火花","away":"瓦萨","pred":"平局","odds":3.00,"result":"D","correct":"Y","stars":2,"event":"芬超","h_rank":999,"a_rank":999,"_source":"legacy"},
    {"date":"06-27","home":"AC奥卢","away":"拉赫蒂","pred":"AC奥卢胜","odds":1.80,"result":"L","correct":"N","stars":2,"event":"芬超","h_rank":999,"a_rank":999,"_source":"legacy"},
    {"date":"06-27","home":"坦佩雷山猫","away":"塞伊奈约基","pred":"山猫不败","odds":1.70,"result":"D","correct":"Y","stars":2,"event":"芬超","h_rank":999,"a_rank":999,"_source":"legacy"},
    {"date":"06-28","home":"南非","away":"加拿大","pred":"加拿大胜","odds":2.10,"result":"W","correct":"Y","stars":2,"event":"1/16决赛","h_rank":None,"a_rank":None,"_source":"legacy"},
    {"date":"06-30","home":"巴西","away":"日本","pred":"巴西胜","odds":1.35,"result":"W","correct":"Y","stars":2,"event":"1/16决赛","h_rank":6,"a_rank":12,"_source":"legacy"},
    {"date":"06-30","home":"德国","away":"巴拉圭","pred":"德国胜","odds":1.22,"result":"L","correct":"N","stars":2,"event":"1/16决赛","h_rank":10,"a_rank":41,"_source":"legacy"},
    {"date":"06-30","home":"荷兰","away":"摩洛哥","pred":"平局","odds":3.40,"result":"D","correct":"Y","stars":2,"event":"1/16决赛","h_rank":7,"a_rank":6,"_source":"legacy"},
    {"date":"07-01","home":"墨西哥","away":"厄瓜多尔","pred":"平局","odds":3.00,"result":"L","correct":"N","stars":2,"event":"1/16决赛","h_rank":14,"a_rank":34,"_source":"legacy"},
    {"date":"07-01","home":"法国","away":"瑞典","pred":"法国胜","odds":1.35,"result":"W","correct":"Y","stars":3,"event":"1/16决赛","h_rank":2,"a_rank":23,"_source":"legacy"},
    {"date":"07-01","home":"科特迪瓦","away":"挪威","pred":"挪威胜","odds":2.10,"result":"W","correct":"Y","stars":2,"event":"1/16决赛","h_rank":40,"a_rank":28,"_source":"legacy"},
    {"date":"07-03","home":"西班牙","away":"奥地利","pred":"西班牙胜","odds":1.35,"result":"W","correct":"Y","stars":3,"event":"1/16决赛","h_rank":3,"a_rank":23,"_source":"legacy"},
    {"date":"07-03","home":"葡萄牙","away":"克罗地亚","pred":"葡萄牙胜","odds":1.85,"result":"W","correct":"Y","stars":2,"event":"1/16决赛","h_rank":5,"a_rank":11,"_source":"legacy"},
    {"date":"07-03","home":"哥伦比亚","away":"加纳","pred":"哥伦比亚胜","odds":1.42,"result":"W","correct":"Y","stars":3,"event":"1/16决赛","h_rank":12,"a_rank":44,"_source":"legacy"},
    {"date":"07-03","home":"天狼星","away":"米亚尔比","pred":"天狼星不败","odds":1.70,"result":"D","correct":"Y","stars":2,"event":"瑞典超","h_rank":999,"a_rank":999,"_source":"legacy"},
    {"date":"07-03","home":"澳大利亚","away":"埃及","pred":"平局(临场)","odds":2.88,"result":"D","correct":"Y","stars":2,"event":"1/16决赛","h_rank":38,"a_rank":33,"_source":"legacy"},
    {"date":"07-03","home":"阿根廷","away":"佛得角","pred":"阿根廷胜","odds":1.15,"result":"L","correct":"N","stars":3,"event":"1/16决赛","h_rank":1,"a_rank":78,"_source":"legacy"},
]


def merge_matches():
    """合并 pnl_records.json 自动数据 + legacy 数据"""
    auto_raw = auto_load_settled()
    auto = pnl_to_matches(auto_raw)

    seen = {}
    for m in legacy_matches:
        key = (m["date"], m["home"], m["away"])
        seen[key] = dict(m)

    for m in auto:
        key = (m["date"], m["home"], m["away"])
        if key in seen:
            seen[key].update({k: v for k, v in m.items() if v is not None or k not in seen[key]})
        else:
            seen[key] = m

    matches = list(seen.values())
    matches.sort(key=lambda x: (x.get("date",""), x.get("home","")))

    auto_count = sum(1 for m in matches if m.get("_source") == "pnl_records.json" or any(
        auto_m.get("home") == m["home"] and auto_m.get("away") == m["away"] for auto_m in auto))
    p(f"\n[数据] 共 {len(matches)} 场比赛 | pnl_records.json 自动加载 {auto_count} 场 | legacy 补充 {len(matches) - auto_count} 场")

    return matches


# ============================================================
# 加载数据
# ============================================================
matches = merge_matches()


# ============================================================
# PnL计算
# ============================================================
p("=" * 70)
p("PnL / Sharpe Ratio 计算")
p("假设：每场比赛投注100元，按模型推荐方向")
p("=" * 70)

total_bet = 0
total_return = 0
correct_count = 0
returns = []

for m in matches:
    stake = 100
    total_bet += stake
    m["stake"] = stake

    if m["correct"] == "Y":
        ret = stake * (m["odds"] - 1)
        total_return += stake * m["odds"]
        correct_count += 1
        m["return"] = stake * m["odds"]
        m["pnl"] = ret
    else:
        total_return += 0
        m["return"] = 0
        m["pnl"] = -stake

    returns.append(m["pnl"] / stake)

net_pnl = total_return - total_bet
roi = net_pnl / total_bet * 100

avg_return = sum(returns) / len(returns)
std_return = (sum((r - avg_return)**2 for r in returns) / len(returns))**0.5
sharpe = avg_return / std_return if std_return > 0 else 0

p(f"\n总投入: {total_bet}元 ({len(matches)}场 × 100元)")
p(f"总回报: {total_return:.0f}元")
p(f"净利润: {net_pnl:+.0f}元")
p(f"收益率(ROI): {roi:+.1f}%")
p(f"方向正确率: {correct_count}/{len(matches)} = {correct_count/len(matches)*100:.1f}%")
p(f"Sharpe Ratio: {sharpe:.2f}")
if sharpe > 1.0:
    p(f"评价: [OK] 优秀（模型盈利稳定）")
elif sharpe > 0.5:
    p(f"评价: [OK] 良好（风险可控）")
elif sharpe > 0:
    p(f"评价: ⚠️ 边缘（需检查+EV计算）")
else:
    p(f"评价: 🔴 亏损（模型失效）")

# 按赛事类型细分PnL
p(f"\n\n按赛事类型PnL:")
events = defaultdict(lambda: {"bet":0, "return":0, "count":0, "correct":0})
for m in matches:
    e = m["event"]
    events[e]["bet"] += m["stake"]
    events[e]["return"] += m["return"]
    events[e]["count"] += 1
    if m["correct"] == "Y":
        events[e]["correct"] += 1

p(f"  {'赛事':<16} {'场次':<6} {'投入':<8} {'回报':<8} {'PnL':<10} {'ROI':<8} {'正确率':<8}")
p(f"  {'-'*66}")
for e, d in sorted(events.items()):
    pnl = d["return"] - d["bet"]
    r = pnl/d["bet"]*100 if d["bet"] > 0 else 0
    acc = d["correct"]/d["count"]*100 if d["count"] > 0 else 0
    p(f"  {e:<16} {d['count']:<6} {d['bet']:<8} {d['return']:<8.0f} {pnl:<+8.0f} {r:<+7.1f}% {acc:<7.1f}%")

# 按⭐评级细分PnL
p(f"\n\n按Star评级PnL:")
stars_data = defaultdict(lambda: {"bet":0, "return":0, "count":0, "correct":0})
for m in matches:
    s = m["stars"]
    stars_data[s]["bet"] += m["stake"]
    stars_data[s]["return"] += m["return"]
    stars_data[s]["count"] += 1
    if m["correct"] == "Y":
        stars_data[s]["correct"] += 1

p(f"  {'评级':<8} {'场次':<6} {'投入':<8} {'回报':<8} {'PnL':<10} {'ROI':<8} {'正确率':<8}")
p(f"  {'-'*55}")
for s in sorted(stars_data.keys(), reverse=True):
    d = stars_data[s]
    pnl = d["return"] - d["bet"]
    r = pnl/d["bet"]*100 if d["bet"] > 0 else 0
    acc = d["correct"]/d["count"]*100 if d["count"] > 0 else 0
    label = "*" * s
    p(f"  {label:<8} {d['count']:<6} {d['bet']:<8} {d['return']:<8.0f} {pnl:<+8.0f} {r:<+7.1f}% {acc:<7.1f}%")

# 错误归因分析
p(f"\n\n{'='*70}")
p("错误归因分析")
p("=" * 70)

errors = [m for m in matches if m["correct"] == "N"]
p(f"\n共{len(errors)}场错误：")
for e in errors:
    if e["stars"] == 3 and e["odds"] <= 1.20:
        attribution = "L3偏差熔断: #008冷门预警未触发(超级热门冷门)"
    elif e["stars"] == 3 and e["odds"] > 1.20:
        attribution = "L2场景修正: 场景系数过度放大信心"
    elif e["stars"] == 2 and e["odds"] <= 1.50:
        attribution = "L1七维评分: 强弱差被高估"
    else:
        attribution = "L0随机波动: 足球固有偶然性"
    p(f"  ❌ {e['home']}vs{e['away']}: 推{e['pred']} @{e['odds']}, 实{e['result']}")
    p(f"     ⭐{e['stars']} | 归因: {attribution}")

attrib_count = defaultdict(int)
for e in errors:
    if e["stars"] == 3 and e["odds"] <= 1.20:
        attrib_count["L3偏差熔断"] += 1
    elif e["stars"] == 3 and e["odds"] > 1.20:
        attrib_count["L2场景修正"] += 1
    elif e["stars"] == 2 and e["odds"] <= 1.50:
        attrib_count["L1七维评分"] += 1
    else:
        attrib_count["L0随机波动"] += 1

p(f"\n错误归因分布:")
for layer, count in sorted(attrib_count.items(), key=lambda x: -x[1]):
    p(f"  {layer}: {count}次 ({count/len(errors)*100:.0f}%)")

# 版本对比
p(f"\n\n{'='*70}")
p("版本对比框架")
p("=" * 70)
p(f"\n当前版本表现 (数据来源: pnl_records.json + legacy):")
p(f"  v8.4 baseline: {correct_count}/{len(matches)} = {correct_count/len(matches)*100:.1f}%")
p(f"  v8.4 Sharpe: {sharpe:.2f}")
p(f"  v8.4 ROI: {roi:+.1f}%")

# 关键发现
p(f"\n\n{'='*70}")
p("关键发现")
p("=" * 70)
p(f"""
1. ROI = {roi:+.1f}%, Sharpe = {sharpe:.2f}
   {'[OK] 模型在样本中产生正收益' if sharpe > 0.5 else '⚠️ 收益率需关注'}

2. 按赛事类型 ROI 差异反映了不同赛事难度。

3. 错误归因:
   - {len(errors)}场错误中，{attrib_count.get('L3偏差熔断', 0)}场是L3层问题
   - {attrib_count.get('L0随机波动', 0)}场是纯粹偶然性

4. 建议:
   - 赛后及时更新 pnl_records.json 的结果（pnl_tracker.py --update）
   - 每10场重新运行此分析
   - 数据源已改为 pnl_records.json 自动加载，无需手动录入
""")
