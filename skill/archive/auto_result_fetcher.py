#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动结果回填工具 v2.0
数据源: football-data.org (主) + OpenLigaDB (备)
比赛结束后自动拉取结果，输出结构化数据用于偏差分析+校准
"""
import sys, os, json, urllib.request, ssl
from datetime import datetime

def p(text):
    try:
        print(text)
    except:
        print(str(text).encode('utf-8', errors='replace').decode('gbk', errors='replace'))

# ============================================================
# 队名映射: 中文 -> football-data.org 英文名
# ============================================================
TEAM_FD = {
    "英格兰":"England","民主刚果":"Congo DR","刚果金":"Congo DR","刚果(金)":"Congo DR",
    "比利时":"Belgium","塞内加尔":"Senegal","美国":"United States","波黑":"Bosnia-Herzegovina",
    "法国":"France","挪威":"Norway","瑞典":"Sweden","墨西哥":"Mexico","厄瓜多尔":"Ecuador",
    "葡萄牙":"Portugal","克罗地亚":"Croatia","西班牙":"Spain","奥地利":"Austria",
    "阿根廷":"Argentina","巴西":"Brazil","荷兰":"Netherlands","德国":"Germany",
    "瑞士":"Switzerland","加拿大":"Canada","日本":"Japan","韩国":"South Korea",
    "南非":"South Africa","捷克":"Czechia","乌拉圭":"Uruguay","沙特":"Saudi Arabia",
    "佛得角":"Cape Verde Islands","哥伦比亚":"Colombia","乌兹别克斯坦":"Uzbekistan",
    "加纳":"Ghana","巴拿马":"Panama","意大利":"Italy","丹麦":"Denmark","波兰":"Poland",
    "匈牙利":"Hungary","土耳其":"Turkey","澳大利亚":"Australia","巴拉圭":"Paraguay",
    "卡塔尔":"Qatar","伊拉克":"Iraq","伊朗":"Iran","新西兰":"New Zealand","埃及":"Egypt",
    "阿尔及利亚":"Algeria","摩洛哥":"Morocco","海地":"Haiti","苏格兰":"Scotland",
    "约旦":"Jordan","科特迪瓦":"Ivory Coast","库拉索":"Curaçao","突尼斯":"Tunisia",
    "芬兰":"Finland","瑞典":"Sweden","伊拉克":"Iraq","伊朗":"Iran","天狼星":"Sirius",
    "米亚尔比":"Mjällby",
}

# 反向: 英文 -> 中文
TEAM_CN = {v:k for k,v in TEAM_FD.items()}
# 补 football-data.org 中的特例
TEAM_CN["Congo DR"] = "民主刚果"
TEAM_CN["Cape Verde Islands"] = "佛得角"
TEAM_CN["Ivory Coast"] = "科特迪瓦"
TEAM_CN["United States"] = "美国"
TEAM_CN["South Korea"] = "韩国"
TEAM_CN["Saudi Arabia"] = "沙特"
TEAM_CN["Bosnia-Herzegovina"] = "波黑"

FD_API_KEY = "93088066c7304ecf8b1631c631601a9a"
FD_BASE = "https://api.football-data.org/v4"

def _fd_get(path):
    """调用football-data.org API"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    url = f"{FD_BASE}{path}"
    req = urllib.request.Request(url, headers={"X-Auth-Token": FD_API_KEY})
    try:
        resp = urllib.request.urlopen(req, context=ctx, timeout=15)
        return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}

# ============================================================
# 追踪比赛列表
# ============================================================
TRACKED = [
    # [日期, 主队, 客队, 联赛(用于FD查询)]
    ["2026-06-27","巴拿马","英格兰","WC"],
    ["2026-06-27","克罗地亚","加纳","WC"],
    ["2026-06-27","哥伦比亚","葡萄牙","WC"],
    ["2026-06-27","民主刚果","乌兹别克斯坦","WC"],
    ["2026-06-27","约旦","阿根廷","WC"],
    ["2026-06-27","阿尔及利亚","奥地利","WC"],
    ["2026-06-28","南非","加拿大","WC"],
    ["2026-06-30","巴西","日本","WC"],
    ["2026-06-30","德国","巴拉圭","WC"],
    ["2026-06-30","荷兰","摩洛哥","WC"],
    ["2026-07-01","墨西哥","厄瓜多尔","WC"],
    ["2026-07-01","法国","瑞典","WC"],
    ["2026-07-01","科特迪瓦","挪威","WC"],
    ["2026-07-03","西班牙","奥地利","WC"],
    ["2026-07-03","葡萄牙","克罗地亚","WC"],
    ["2026-07-03","哥伦比亚","加纳","WC"],
    ["2026-07-03","澳大利亚","埃及","WC"],
    ["2026-07-03","阿根廷","佛得角","WC"],
]

def find_in_fd(matches_fd, home_cn, away_cn):
    """在football-data.org数据中匹配比赛"""
    home_en = TEAM_FD.get(home_cn, home_cn)
    away_en = TEAM_FD.get(away_cn, away_cn)
    for m in matches_fd:
        h = m.get("homeTeam",{}).get("name","")
        a = m.get("awayTeam",{}).get("name","")
        # 双向匹配
        if (home_en.lower() == h.lower() and away_en.lower() == a.lower()) or \
           (home_en.lower() == a.lower() and away_en.lower() == h.lower()):
            return m
    return None

def format_result(m):
    """格式化比赛结果"""
    score = m.get("score",{}) or {}
    ft = score.get("fullTime",{}) or {}
    ht = score.get("halfTime",{}) or {}
    h_name = m.get("homeTeam",{}).get("name","?")
    a_name = m.get("awayTeam",{}).get("name","?")
    h_cn = TEAM_CN.get(h_name, h_name)
    a_cn = TEAM_CN.get(a_name, a_name)
    return {
        "match": f"{h_cn} vs {a_cn}",
        "home_cn": h_cn, "away_cn": a_cn,
        "score_ht": f"{ht.get('home','?')}-{ht.get('away','?')}",
        "score_ft": f"{ft.get('home','?')}-{ft.get('away','?')}",
        "status": m.get("status","?"),
        "date": m.get("utcDate","")[:10],
        "stage": m.get("stage",""),
    }

def run():
    p("=" * 60)
    p("自动结果回填 v2.0 (football-data.org)")
    p("=" * 60)

    # 获取世界杯全部比赛
    p("\n获取 football-data.org 数据...")
    data = _fd_get("/competitions/WC/matches")
    if data.get("error"):
        p(f"  API错误: {data['error']}")
        return

    matches_fd = data.get("matches", [])
    p(f"  找到 {len(matches_fd)} 场世界杯比赛\n")

    # 逐场匹配
    p(f"{'比赛':<30} {'状态':<10} {'半场':<10} {'全场':<10}")
    p("-"*60)

    found = 0; not_found = 0
    results = []

    for date, home, away, comp in TRACKED:
        match = find_in_fd(matches_fd, home, away)
        label = f"{home} vs {away}"

        if not match:
            p(f"{label:<30} {'未匹配':<10} {'-':<10} {'-':<10}")
            not_found += 1
            continue

        r = format_result(match)
        results.append(r)
        found += 1
        status_map = {"FINISHED":"已完赛","SCHEDULED":"待进行","TIMED":"待进行","IN_PLAY":"进行中"}
        s = status_map.get(r["status"], r["status"])
        p(f"{r['match']:<30} {s:<10} {r['score_ht']:<10} {r['score_ft']:<10}")

    # 统计
    p(f"\n{'='*60}")
    p(f"统计")
    p(f"{'='*60}")
    p(f"  追踪: {len(TRACKED)}场 | 已匹配: {found}场 | 未匹配: {not_found}场")

    # 输出JSON供其他工具使用
    json_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "数据缓存", "auto_results.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    p(f"\n  结果已保存: {json_path}")
    p(f"  共 {found} 场比赛数据可供偏差分析")

    # 建议
    p(f"\n{'='*60}")
    p(f"下一步")
    p(f"{'='*60}")
    p(f"  运行校准分析: python skill/calibration_analysis.py")
    p(f"  运行PnL分析:  python skill/pnl_analysis.py")
    p(f"  查看投注决策: python skill/betting_engine.py")

if __name__ == "__main__":
    run()
