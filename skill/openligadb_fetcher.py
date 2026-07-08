#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenLigaDB 数据采集器 — 免费足球基本面数据源

用途:
  作为 odds-api.io + 竞彩的补充基本面数据源，提供：
  - 历史比赛比分（全场/半场）
  - 进球详情（球员、分钟、点球/乌龙标记）
  - 球队赛程与赛果
  - 积分榜
  - 联赛列表

用法:
  python openligadb_fetcher.py --list                    # 列出可用联赛
  python openligadb_fetcher.py --league wm26 --season 2026  # 查世界杯全部比赛
  python openligadb_fetcher.py --team "英格兰"              # 查某队本届世界杯比赛
  python openligadb_fetcher.py --h2h "英格兰" "民主刚果"   # 查两队交锋历史
  python openligadb_fetcher.py --league bl1 --season 2024   # 查德甲2024/25

数据来源: https://www.openligadb.de (免费, 无需API Key)
"""

import json
import sys
import os
import urllib.request
import ssl
from typing import Optional, Dict, List, Tuple
from datetime import datetime

# Windows控制台编码处理
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        # Python < 3.7
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 配置
# ============================================================
BASE_URL = "https://api.openligadb.de"
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "数据缓存")

# ============================================================
# 队名映射：中文 → 德文（OpenLigaDB 使用德文队名）
# ============================================================
TEAM_DE = {
    # 2026世界杯球队
    "英格兰": "England",
    "民主刚果": "DR Kongo",
    "刚果金": "DR Kongo",
    "刚果(金)": "DR Kongo",
    "比利时": "Belgien",
    "塞内加尔": "Senegal",
    "美国": "USA",
    "波黑": "Bosnien und Herzegowina",
    "法国": "Frankreich",
    "挪威": "Norwegen",
    "瑞典": "Schweden",
    "墨西哥": "Mexiko",
    "厄瓜多尔": "Ecuador",
    "葡萄牙": "Portugal",
    "克罗地亚": "Kroatien",
    "西班牙": "Spanien",
    "奥地利": "Österreich",
    "阿根廷": "Argentinien",
    "巴西": "Brasilien",
    "荷兰": "Niederlande",
    "德国": "Deutschland",
    "瑞士": "Schweiz",
    "加拿大": "Kanada",
    "日本": "Japan",
    "韩国": "Südkorea",
    "南非": "Südafrika",
    "捷克": "Tschechien",
    "乌拉圭": "Uruguay",
    "沙特": "Saudi Arabien",
    "佛得角": "Kap Verde",
    "哥伦比亚": "Kolumbien",
    "乌兹别克": "Usbekistan",
    "加纳": "Ghana",
    "巴拿马": "Panama",
    "意大利": "Italien",
    "丹麦": "Dänemark",
    "波兰": "Polen",
    "匈牙利": "Ungarn",
    "土耳其": "Türkei",
    "澳大利亚": "Australien",
    "巴拉圭": "Paraguay",
    "卡塔尔": "Katar",
    "伊拉克": "Irak",
    "伊朗": "Iran",
    "新西兰": "Neuseeland",
    "埃及": "Ägypten",
    "阿尔及利亚": "Algerien",
    "摩洛哥": "Marokko",
    "海地": "Haiti",
    "苏格兰": "Schottland",
    "约旦": "Jordanien",
    "科特迪瓦": "Elfenbeinküste",
    "库拉索": "Curaçao",
    "突尼斯": "Tunesien",
    "厄瓜多尔": "Ecuador",
    "塞内加尔": "Senegal",
    "芬兰": "Finnland",
    "瑞典": "Schweden",
}

# 反向映射：德文 → 中文
TEAM_CN = {v: k for k, v in TEAM_DE.items()}


# ============================================================
# HTTP 工具
# ============================================================

def _http_get(path: str, timeout: int = 15) -> Optional[dict]:
    """调用 OpenLigaDB API 并返回 JSON"""
    url = f"{BASE_URL}{path}"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[错误] API请求失败: {url} — {e}", file=sys.stderr)
        return None


# ============================================================
# API 方法
# ============================================================

def get_available_leagues() -> List[dict]:
    """获取所有可用联赛列表"""
    data = _http_get("/getavailableleagues")
    return data if data else []


def get_matchdata(league_shortcut: str, season: str) -> List[dict]:
    """获取某联赛某赛季的所有比赛数据"""
    data = _http_get(f"/getmatchdata/{league_shortcut}/{season}")
    return data if data else []


def get_teams(league_shortcut: str, season: str) -> List[dict]:
    """获取某联赛的球队列表"""
    data = _http_get(f"/getteams/{league_shortcut}/{season}")
    return data if data else []


def get_match_by_id(match_id: int) -> Optional[dict]:
    """按ID获取单场比赛详情"""
    return _http_get(f"/getmatchdata/{match_id}")


def get_league_table(league_id: int) -> List[dict]:
    """获取联赛积分榜"""
    data = _http_get(f"/getbltable/{league_id}")
    return data if data else []


# ============================================================
# 业务方法
# ============================================================

def search_league(keyword: str = "", min_season: int = 2024) -> List[dict]:
    """搜索联赛，可按关键词过滤"""
    leagues = get_available_leagues()
    results = []
    for l in leagues:
        try:
            season = int(l.get("leagueSeason", 0))
        except (ValueError, TypeError):
            season = 0
        if season < min_season:
            continue
        name = l.get("leagueName", "")
        shortcut = l.get("leagueShortcut", "")
        if keyword.lower() in name.lower() or keyword.lower() in shortcut.lower():
            results.append({
                "id": l["leagueId"],
                "name": name,
                "shortcut": shortcut,
                "season": l["leagueSeason"],
                "sport": l.get("sport", {}).get("sportName", ""),
            })
    return results


def get_team_matches(team_name_cn: str, league_shortcut: str = "wm26", season: str = "2026") -> List[dict]:
    """获取某队在本届赛事的所有比赛"""
    team_de = TEAM_DE.get(team_name_cn, team_name_cn)
    all_matches = get_matchdata(league_shortcut, season)
    matches = []
    for m in all_matches:
        t1 = m.get("team1", {}).get("teamName", "")
        t2 = m.get("team2", {}).get("teamName", "")
        if team_de.lower() in t1.lower() or team_de.lower() in t2.lower():
            matches.append(_format_match(m))
    return matches


def get_h2h(team1_cn: str, team2_cn: str, league_shortcut: str = "wm26", season: str = "2026") -> List[dict]:
    """获取两队交锋记录"""
    team1_de = TEAM_DE.get(team1_cn, team1_cn)
    team2_de = TEAM_DE.get(team2_cn, team2_cn)
    all_matches = get_matchdata(league_shortcut, season)
    h2h = []
    for m in all_matches:
        t1 = m.get("team1", {}).get("teamName", "")
        t2 = m.get("team2", {}).get("teamName", "")
        t1_match = team1_de.lower() in t1.lower() and team2_de.lower() in t2.lower()
        t2_match = team1_de.lower() in t2.lower() and team2_de.lower() in t1.lower()
        if t1_match or t2_match:
            h2h.append(_format_match(m))
    return h2h


def _format_match(m: dict) -> dict:
    """将原始API返回格式化为统一格式"""
    t1 = m.get("team1", {})
    t2 = m.get("team2", {})

    # 找最终比分
    final_score = None
    half_score = None
    for r in m.get("matchResults", []):
        rname = r.get("resultName", "")
        if rname == "Endergebnis" or rname == "结果":
            final_score = f"{r['pointsTeam1']}-{r['pointsTeam2']}"
        elif rname == "Halbzeitergebnis" or rname == "半场结果":
            half_score = f"{r['pointsTeam1']}-{r['pointsTeam2']}"

    # 进球详情
    goals = []
    for g in m.get("goals", []):
        goals.append({
            "minute": g.get("matchMinute"),
            "scorer": g.get("goalGetterName"),
            "score": f"{g['scoreTeam1']}-{g['scoreTeam2']}",
            "team": t1.get("teamName") if g.get("scoringTeamId") == t1.get("teamId") else t2.get("teamName"),
            "is_penalty": g.get("isPenalty", False),
            "is_own_goal": g.get("isOwnGoal", False),
            "is_overtime": g.get("isOvertime", False),
        })

    group = m.get("group", {})
    location = m.get("location", {})

    return {
        "match_id": m.get("matchID"),
        "date": m.get("matchDateTime", ""),
        "finished": m.get("matchIsFinished", False),
        "group": group.get("groupName", ""),
        "team1": {
            "name_de": t1.get("teamName"),
            "name_cn": TEAM_CN.get(t1.get("teamName", ""), t1.get("teamName")),
            "team_id": t1.get("teamId"),
            "icon": t1.get("teamIconUrl"),
        },
        "team2": {
            "name_de": t2.get("teamName"),
            "name_cn": TEAM_CN.get(t2.get("teamName", ""), t2.get("teamName")),
            "team_id": t2.get("teamId"),
            "icon": t2.get("teamIconUrl"),
        },
        "final_score": final_score,
        "half_score": half_score,
        "goals": goals,
        "location": {
            "stadium": location.get("locationStadium", ""),
            "city": location.get("locationCity", ""),
        },
    }


# ============================================================
# 输出与保存
# ============================================================

def print_match_summary(matches: List[dict], title: str = ""):
    """打印比赛摘要到控制台"""
    if title:
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")

    if not matches:
        print("  (无数据)")
        return

    for m in matches:
        fin = "[x]" if m["finished"] else "[ ]"
        t1 = m["team1"]["name_cn"] or m["team1"]["name_de"]
        t2 = m["team2"]["name_cn"] or m["team2"]["name_de"]
        score = m["final_score"] or "?-?"
        group = m["group"] or ""
        date = m["date"][:16] if m["date"] else ""
        print(f"  {fin} {date} | {t1:<20s} vs {t2:<20s} | {score:5s} | {group}")

        # 显示进球
        if m["goals"]:
            goal_strs = []
            for g in m["goals"]:
                marker = ""
                if g["is_overtime"]: marker += "+OT"
                if g["is_own_goal"]: marker += "(OG)"
                if g["is_penalty"]: marker += "(P)"
                scorer = g["scorer"] or "?"
                goal_strs.append(f"{g['minute']}' {scorer}{marker}")
            if goal_strs:
                print(f"         进球: {', '.join(goal_strs)}")
        print()


def save_to_json(data: dict, filename: str):
    """保存数据到预测数据目录"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[保存] {filepath}")


# ============================================================
# 比赛基本面分析 — 直接输出为分析报告格式
# ============================================================

def generate_team_report(team_cn: str, league_shortcut: str = "wm26", season: str = "2026") -> dict:
    """生成某队在本届赛事的基本面分析报告"""
    matches = get_team_matches(team_cn, league_shortcut, season)
    if not matches:
        return {"team": team_cn, "error": "未找到比赛数据"}

    # 统计
    total = len(matches)
    played = [m for m in matches if m["finished"]]
    wins = draws = losses = 0
    goals_for = goals_against = 0
    clean_sheets = 0
    scored_in_all = True

    for m in played:
        if not m["final_score"]:
            continue
        try:
            g1, g2 = map(int, m["final_score"].split("-"))
        except (ValueError, AttributeError):
            continue

        # 判断球队在比赛中的位置
        t1_de = m["team1"]["name_de"]
        t2_de = m["team2"]["name_de"]
        team_de = TEAM_DE.get(team_cn, team_cn)

        if team_de.lower() in t1_de.lower():
            gf, ga = g1, g2
        else:
            gf, ga = g2, g1

        goals_for += gf
        goals_against += ga
        if gf > ga:
            wins += 1
        elif gf == ga:
            draws += 1
        else:
            losses += 1
        if ga == 0:
            clean_sheets += 1
        if gf == 0:
            scored_in_all = False

    return {
        "team_cn": team_cn,
        "team_de": TEAM_DE.get(team_cn, team_cn),
        "total_matches": total,
        "played": len(played),
        "record": f"{wins}胜 {draws}平 {losses}负",
        "goals_for": goals_for,
        "goals_against": goals_against,
        "avg_goals_for": round(goals_for / len(played), 2) if played else 0,
        "avg_goals_against": round(goals_against / len(played), 2) if played else 0,
        "clean_sheets": clean_sheets,
        "scored_in_all_matches": scored_in_all,
        "matches": matches,
    }


def generate_h2h_report(team1_cn: str, team2_cn: str, league_shortcut: str = "wm26", season: str = "2026") -> dict:
    """生成两队交锋分析报告"""
    h2h = get_h2h(team1_cn, team2_cn, league_shortcut, season)
    if not h2h:
        return {"team1": team1_cn, "team2": team2_cn, "error": "未找到交锋记录"}

    t1_de = TEAM_DE.get(team1_cn, team1_cn)
    t2_de = TEAM_DE.get(team2_cn, team2_cn)
    t1_wins = t2_wins = draws = 0
    t1_goals = t2_goals = 0

    for m in h2h:
        if not m["finished"] or not m["final_score"]:
            continue
        try:
            g1, g2 = map(int, m["final_score"].split("-"))
        except (ValueError, AttributeError):
            continue

        if t1_de.lower() in m["team1"]["name_de"].lower():
            tg1, tg2 = g1, g2
        else:
            tg1, tg2 = g2, g1

        t1_goals += tg1
        t2_goals += tg2
        if tg1 > tg2:
            t1_wins += 1
        elif tg1 < tg2:
            t2_wins += 1
        else:
            draws += 1

    return {
        "team1": team1_cn,
        "team2": team2_cn,
        "matches_count": len(h2h),
        "h2h_record": f"{t1_wins}胜 {draws}平 {t2_wins}负",
        "goals": f"{t1_goals}-{t2_goals}",
        "matches": h2h,
    }


# ============================================================
# 命令行入口
# ============================================================

def print_help():
    print("""OpenLigaDB 数据采集器 — 免费足球基本面数据源

用法:
  python openligadb_fetcher.py --list [--season 2024]    列出可用联赛
  python openligadb_fetcher.py --search <关键词>           搜索联赛
  python openligadb_fetcher.py --league <shortcut> --season <赛季>  查联赛比赛
  python openligadb_fetcher.py --team <球队名>            查某队本届世界杯比赛
  python openligadb_fetcher.py --h2h <球队A> <球队B>     查两队交锋历史
  python openligadb_fetcher.py --report <球队名>          生成某队基本面分析报告
  python openligadb_fetcher.py --save <球队名>            保存分析报告到文件

常用联赛 shortcut:
  wm26      — 2026世界杯
  em2024    — 2024欧洲杯
  bl1       — 德甲 (season=2024 即 2024/25)
  bl2       — 德乙
  dfb       — 德国杯
  ucl2024   — 欧冠2024/25
  unl       — 欧国联
  ca2024    — 美洲杯2024

示例:
  python openligadb_fetcher.py --league wm26 --season 2026
  python openligadb_fetcher.py --team "英格兰"
  python openligadb_fetcher.py --h2h "英格兰" "民主刚果"
  python openligadb_fetcher.py --report "美国" --save
""")


def main():
    if len(sys.argv) < 2:
        print_help()
        return

    # --- --list: 列出可用联赛 ---
    if "--list" in sys.argv:
        min_season = 2024
        if "--season" in sys.argv:
            try:
                idx = sys.argv.index("--season")
                min_season = int(sys.argv[idx + 1])
            except (IndexError, ValueError):
                pass
        leagues = search_league("", min_season)
        print(f"\n{'='*60}")
        print(f"  可用联赛 (season>={min_season}, total={len(leagues)})")
        print(f"{'='*60}")
        for l in sorted(leagues, key=lambda x: x["name"]):
            print(f"  ID={l['id']:>5} | {l['name']:<50s} | shortcut={l['shortcut']:<12s} | 赛季={l['season']}")
        return

    # --- --search: 搜索联赛 ---
    if "--search" in sys.argv:
        try:
            idx = sys.argv.index("--search")
            keyword = sys.argv[idx + 1]
        except IndexError:
            print("请指定搜索关键词")
            return
        results = search_league(keyword, min_season=0)
        print(f"\n搜索 '{keyword}' 找到 {len(results)} 个联赛:")
        for l in results:
            print(f"  ID={l['id']:>5} | {l['name']:<50s} | shortcut={l['shortcut']:<12s} | 赛季={l['season']}")
        return

    # --- --league: 查联赛比赛 ---
    if "--league" in sys.argv:
        try:
            idx = sys.argv.index("--league")
            shortcut = sys.argv[idx + 1]
        except IndexError:
            print("请指定联赛 shortcut")
            return
        season = "2026"
        if "--season" in sys.argv:
            try:
                idx2 = sys.argv.index("--season")
                season = sys.argv[idx2 + 1]
            except (IndexError, ValueError):
                pass
        matches = get_matchdata(shortcut, season)
        formatted = [_format_match(m) for m in matches]
        # 分组打印
        groups = {}
        for m in formatted:
            grp = m["group"] or "未分组"
            if grp not in groups:
                groups[grp] = []
            groups[grp].append(m)
        print(f"\n{'='*60}")
        print(f"  {shortcut}/{season} | total={len(formatted)}")
        print(f"{'='*60}")
        for gname in sorted(groups.keys()):
            print(f"\n-- {gname} --")
            for m in groups[gname]:
                fin = "[x]" if m["finished"] else "[ ]"
                t1 = m["team1"]["name_cn"] or m["team1"]["name_de"]
                t2 = m["team2"]["name_cn"] or m["team2"]["name_de"]
                score = m["final_score"] or "?-?"
                print(f"  {fin} {t1:<20s} vs {t2:<20s} | {score:5s}")
        return

    # --- --team: 查某队比赛 ---
    if "--team" in sys.argv:
        try:
            idx = sys.argv.index("--team")
            team = sys.argv[idx + 1]
        except IndexError:
            print("请指定球队名")
            return
        league = "wm26"
        season = "2026"
        if "--league" in sys.argv:
            idx2 = sys.argv.index("--league")
            league = sys.argv[idx2 + 1]
        if "--season" in sys.argv:
            idx3 = sys.argv.index("--season")
            season = sys.argv[idx3 + 1]
        matches = get_team_matches(team, league, season)
        print_match_summary(matches, f"{team} | {league}/{season}")
        return

    # --- --h2h: 查交锋 ---
    if "--h2h" in sys.argv:
        try:
            idx = sys.argv.index("--h2h")
            t1 = sys.argv[idx + 1]
            t2 = sys.argv[idx + 2]
        except IndexError:
            print("请指定两支球队名")
            return
        league = "wm26"
        season = "2026"
        if "--league" in sys.argv:
            idx2 = sys.argv.index("--league")
            league = sys.argv[idx2 + 1]
        if "--season" in sys.argv:
            idx3 = sys.argv.index("--season")
            season = sys.argv[idx3 + 1]
        h2h = get_h2h(t1, t2, league, season)
        print_match_summary(h2h, f"{t1} vs {t2} — {league}/{season} 交锋记录")

        # 生成统计
        if h2h:
            report = generate_h2h_report(t1, t2, league, season)
            print(f"  [交锋统计] {report['h2h_record']} | 进球 {report['goals']}")
        return

    # --- --report: 生成基本面报告 ---
    if "--report" in sys.argv:
        try:
            idx = sys.argv.index("--report")
            team = sys.argv[idx + 1]
        except IndexError:
            print("请指定球队名")
            return
        league = "wm26"
        season = "2026"
        if "--league" in sys.argv:
            idx2 = sys.argv.index("--league")
            league = sys.argv[idx2 + 1]
        if "--season" in sys.argv:
            idx3 = sys.argv.index("--season")
            season = sys.argv[idx3 + 1]
        report = generate_team_report(team, league, season)
        print(f"\n{'='*60}")
        print(f"  [基本面] {team} — {league}/{season}")
        print(f"{'='*60}")
        if "error" in report:
            print(f"  [错误] {report['error']}")
        else:
            print(f"  总比赛: {report['total_matches']} | 已赛: {report['played']}")
            print(f"  战绩: {report['record']}")
            print(f"  进球: {report['goals_for']} | 失球: {report['goals_against']}")
            print(f"  场均进: {report['avg_goals_for']} | 场均失: {report['avg_goals_against']}")
            print(f"  零封: {report['clean_sheets']}场 | 全部场次进球: {'是' if report['scored_in_all_matches'] else '否'}")
            print()
            print_match_summary(report["matches"])

        if "--save" in sys.argv:
            save_to_json(report, f"openligadb_{team}_{league}_{season}.json")
        return

    # 默认：显示帮助
    print_help()


if __name__ == "__main__":
    main()
