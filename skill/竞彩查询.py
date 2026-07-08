#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
竞彩足球实时赔率查询工具
用法：双击运行，或在命令行输入比赛名过滤

数据来源：webapi.sporttery.cn（中国竞彩网）
"""

import json
import urllib.request
import sys
import os
from datetime import datetime

def fetch_odds():
    """从竞彩API获取实时赔率"""
    url = "https://webapi.sporttery.cn/gateway/jc/football/getMatchCalculatorV1.qry?poolCode=hhad,had,ttg&channel=c"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.sporttery.cn/",
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def print_matches(data, keyword=""):
    """格式化输出比赛数据"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n{'='*70}")
    print(f"  竞彩足球实时赔率  | 更新: {now}")
    if keyword:
        print(f"  筛选: [{keyword}]")
    print(f"{'='*70}")

    count = 0
    for day in data["value"]["matchInfoList"]:
        for m in day["subMatchList"]:
            # 关键词过滤
            name_all = m["homeTeamAllName"] + m["awayTeamAllName"] + m["awayTeamAbbName"]
            if keyword and keyword not in name_all and keyword not in m.get("homeRank", "") and keyword not in m.get("awayRank", ""):
                continue

            count += 1
            had = m.get("had", {})
            hhad = m.get("hhad", {})

            # 判断是否单关
            is_single = any(p.get("single") == 1 for p in m.get("poolList", []))
            tag = "[单关]" if is_single else " 串关"

            # 联赛颜色
            league = m.get("leagueAbbName", "")

            print(f"\n{'─'*70}")
            print(f"  {m['matchNumStr']} {tag} | {league}")
            print(f"  {m['homeTeamAllName']}  vs  {m['awayTeamAllName']}")
            print(f"  时间 {m['matchDate']} {m['matchTime']} | {m['matchStatus']}")
            print(f"  地点 {m.get('remark','')}")

            # 排名信息
            hr = m.get("homeRank", "")
            ar = m.get("awayRank", "")
            if hr or ar:
                print(f"  排名 {hr} vs {ar}")

            # 赔率
            if had and had.get("h"):
                print(f"  ┌─────────────────────────────────────────────")
                print(f"  │ 胜平负     {had['h']:>6}  {had['d']:>6}  {had['a']:>6}")
                print(f"  │            (主)     (平)     (客)")

            if hhad and hhad.get("h"):
                gl = hhad.get("goalLine", "")
                gl_display = gl if gl else "0"
                print(f"  │ 让球({gl_display})  {hhad['h']:>6}  {hhad['d']:>6}  {hhad['a']:>6}")
                print(f"  │            (主)     (平)     (客)")

            # 总进球数赔率（v8.5新增）
            ttg = m.get("ttg", {})
            if ttg and ttg.get("s2"):
                goal_labels = ["0球","1球","2球","3球","4球","5球","6球","7+球"]
                print(f"  │ 总进球:", end="")
                for i in range(8):
                    key = f"s{i}"
                    if key in ttg and ttg[key] and ttg[key] != "0":
                        print(f"  {goal_labels[i]}@{ttg[key]}", end="")
                print()

            if had and had.get("h"):
                print(f"  └─────────────────────────────────────────────")

    if count == 0:
        print(f"\n  未找到匹配 [{keyword}] 的比赛")
        print(f"  试试: {' / '.join(get_all_teams(data))}")

    print(f"\n{'='*70}")
    print(f"  共 {count} 场比赛 | 数据来源: 中国竞彩网 sporttery.cn")
    print(f"{'='*70}\n")

def get_all_teams(data):
    """获取所有球队名供提示"""
    teams = set()
    for day in data["value"]["matchInfoList"]:
        for m in day["subMatchList"]:
            teams.add(m["homeTeamAllName"])
            teams.add(m["awayTeamAbbName"])
    return sorted(teams)

def search(keyword=""):
    """搜索比赛，返回结构化数据（供系统2调用）"""
    data = fetch_odds()
    results = []
    for day in data["value"]["matchInfoList"]:
        for m in day["subMatchList"]:
            name_all = m["homeTeamAllName"] + m["awayTeamAllName"] + m["awayTeamAbbName"]
            if keyword and keyword not in name_all:
                continue
            had = m.get("had", {})
            hhad = m.get("hhad", {})
            ttg = m.get("ttg", {})
            ttg_goals = {}
            if ttg:
                goal_labels = ["0","1","2","3","4","5","6","7p"]
                for i in range(8):
                    key = f"s{i}"
                    if key in ttg and ttg[key] and ttg[key] != "0":
                        ttg_goals[goal_labels[i]] = ttg[key]
            results.append({
                "match_num": m["matchNumStr"],
                "home": m["homeTeamAllName"],
                "away": m["awayTeamAllName"],
                "date": m["matchDate"],
                "time": m["matchTime"],
                "league": m.get("leagueName", ""),
                "odds_h": float(had.get("h", 0)),
                "odds_d": float(had.get("d", 0)),
                "odds_a": float(had.get("a", 0)),
                "rq_h": float(hhad.get("h", 0)),
                "rq_d": float(hhad.get("d", 0)),
                "rq_a": float(hhad.get("a", 0)),
                "single": any(p.get("single") == 1 for p in m.get("poolList", [])),
                "ttg": ttg_goals,  # 总进球数赔率
            })
    return results

def main():
    keyword = ""
    json_mode = False
    for arg in sys.argv[1:]:
        if arg == "--json":
            json_mode = True
        else:
            keyword = arg

    try:
        data = fetch_odds()
        if json_mode:
            results = search(keyword)
            print(json.dumps(results, ensure_ascii=False, indent=2))
            return
        print_matches(data, keyword)
    except urllib.error.HTTPError as e:
        print(f"\n[错误] 网络错误: HTTP {e.code}")
        print("   可能被WAF拦截，稍后再试或加延迟")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\n[错误] 网络错误: {e.reason}")
        print("   请检查网络连接")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"\n[错误] 数据解析失败，API可能返回了非JSON内容")
        sys.exit(1)
    except Exception as e:
        print(f"\n[错误] 未知错误: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
