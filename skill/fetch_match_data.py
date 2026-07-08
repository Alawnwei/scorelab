#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一比赛数据获取工具 — 多数据源（带交叉验证）
用法:
  python fetch_match_data.py --mode jingcai --home "挪威" --away "法国"
  python fetch_match_data.py --mode yapan --home "Croatia" --away "Ghana"
  python fetch_match_data.py --mode live --home "Uruguay" --away "Spain"
  python fetch_match_data.py --mode sportsdb --home "天狼星" --away "米亚尔比"
  python fetch_match_data.py --mode football --home "阿根廷" --away "巴西"
  python fetch_match_data.py --mode espn --home "nba"
  python fetch_match_data.py --mode espn --home "wnba"
  python fetch_match_data.py --mode espn --home "eng.fa" （足总杯）
  python fetch_match_data.py --mode espn --home "fifa.world" （世界杯）

数据源:
  - jingcai:   主=中国竞彩网, 辅=Bet365/1xbet
  - yapan:     主=Bet365/1xbet, 辅=中国竞彩网
  - sportsdb:  TheSportsDB（瑞典超等小众联赛，无需Key）
  - football:  football-data.org（世界杯/五大联赛/欧冠，需API Key）
  - espn:      ESPN公共API（NBA/WNBA/足总杯/全球足球联赛，无需Key）
  - live:      实时比赛状态

输出: 保存到 数据缓存/latest_match_data.json
"""

import json, sys, os, re, urllib.request, subprocess
from typing import Optional
from datetime import datetime

# Windows控制台编码
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "数据缓存")
OS_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# ============================================================
# football-data.org 配置（用户提供的API Key — 世界杯/五大联赛/欧冠）
# ============================================================
FOOTBALL_API_KEY = "93088066c7304ecf8b1631c631601a9a"
FOOTBALL_BASE = "https://api.football-data.org/v4"

# 中文队名 → football-data.org 竞赛代码映射
FOOTBALL_COMP_CODES = {
    "世界杯": "WC", "欧冠": "CL", "英超": "PL", "英冠": "ELC",
    "德甲": "BL1", "西甲": "PD", "意甲": "SA", "法甲": "FL1",
    "荷甲": "DED", "巴甲": "BSA", "葡超": "PPL", "欧洲杯": "EC",
}

# ============================================================
# TheSportsDB 配置（免费版，无需Key — 用于瑞典超等小众联赛）
# ============================================================
SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"
# 联赛ID映射：手动维护常见联赛
SPORTSDB_LEAGUES = {
    "allsvenskan": "4347",
    "swedish.1": "4347",
    "瑞典超": "4347",
}
# 队名映射：中文 → TheSportsDB英文队名
TEAM_SPORTSDB = {
    "天狼星": "Sirius",
    "米亚尔比": "Mjallby",
    "索尔纳": "AIK",
    "哥德堡": "IFK Gothenburg",
    "马尔默": "Malmo FF",
    "埃尔夫斯堡": "Elfsborg",
    "哈马比": "Hammarby",
    "尤尔加登": "Djurgarden",
    "赫根": "Hacken",
    "诺尔雪平": "Norrkoping",
    "北雪平": "Norrkoping",
    "布洛马波卡纳": "Brommapojkarna",
    "卡尔马": "Kalmar",
    "米约比": "Mjallby",
    "奥斯达": "Osters IF",
    "天狼星": "Sirius",
    "瓦纳默": "IFK Varnamo",
    "韦斯比联": "IF Brommapojkarna",
    "哈尔姆斯塔德": "Halmstad",
    "加尔斯": "GAIS",
    "韦斯特罗斯": "Vasteras SK",
    "代格福什": "Degerfors",
    # 芬超（Veikkausliiga）
    "拉赫蒂": "Lahti",
    "赫尔火花": "Gnistan",
    "赫尔辛基火花": "Gnistan",
    "塞伊奈": "SJK",
    "TPS图尔库": "TPS",
    "雅罗": "FF Jaro",
    "坦佩雷": "Tampere United",
    "赫尔辛基": "HJK",
    "瓦萨": "VPS",
    "玛丽港": "IFK Mariehamn",
    "国际图尔库": "FC Inter",
    "库奥皮奥": "KuPS",
    "AC奥卢": "AC Oulu",
    "埃尔维斯": "Ilves",
}

# 球队名中→英映射（用于 odds-api 查询）
TEAM_EN = {
    "挪威": "Norway", "法国": "France", "塞内加尔": "Senegal", "伊拉克": "Iraq",
    "佛得角": "Cape Verde", "沙特": "Saudi Arabia", "乌拉圭": "Uruguay",
    "西班牙": "Spain", "埃及": "Egypt", "伊朗": "Iran",
    "新西兰": "New Zealand", "比利时": "Belgium",
    "葡萄牙": "Portugal", "乌兹别克": "Uzbekistan",
    "英格兰": "England", "加纳": "Ghana",
    "巴拿马": "Panama", "克罗地亚": "Croatia",
    "哥伦比亚": "Colombia", "刚果金": "Congo DR",
    "德国": "Germany", "厄瓜多尔": "Ecuador",
    "库拉索": "Curacao", "科特迪瓦": "Ivory Coast",
    "突尼斯": "Tunisia", "荷兰": "Netherlands",
    "日本": "Japan", "瑞典": "Sweden",
    "土耳其": "Turkey", "美国": "USA",
    "巴拉圭": "Paraguay", "澳大利亚": "Australia",
    "瑞士": "Switzerland", "加拿大": "Canada",
    "波黑": "Bosnia", "卡塔尔": "Qatar",
    "苏格兰": "Scotland", "巴西": "Brazil",
    "摩洛哥": "Morocco", "海地": "Haiti",
    "捷克": "Czech Republic", "墨西哥": "Mexico",
    "南非": "South Africa", "韩国": "South Korea",
    "奥地利": "Austria", "阿尔及利": "Algeria",
    "约旦": "Jordan", "阿根廷": "Argentina",
}


# 队名英→中反向映射（用于亚盘模式查竞彩）
TEAM_CN = {v: k for k, v in TEAM_EN.items()}

# ============================================================
# TheSportsDB 数据获取（免费，无需Key — 瑞典超等小众联赛补充）
# ============================================================

def _sportsdb_get(path):
    """调用TheSportsDB API"""
    url = f"{SPORTSDB_BASE}/{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": OS_AGENT})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def fetch_sportsdb_match_data(home_name, away_name):
    """从TheSportsDB查询比赛数据（适用于OpenLigaDB未覆盖的联赛如瑞典超）

    返回:
        {
            "mode": "sportsdb",
            "source": "TheSportsDB",
            "match": { "home": ..., "away": ..., "league": ..., "venue": ..., "time": ... },
            "home_form": [{"date":..., "result":..., "score":...}],
            "away_form": [{"date":..., "result":..., "score":...}],
            "standings": { "home_pos": ..., "home_pts": ..., "away_pos": ..., "away_pts": ... }
        }
    """
    home_en = TEAM_SPORTSDB.get(home_name, home_name)
    away_en = TEAM_SPORTSDB.get(away_name, away_name)

    result = {
        "mode": "sportsdb",
        "source": "TheSportsDB",
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "match": {},
        "home_form": [],
        "away_form": [],
        "standings": {},
    }

    # 1. 搜索比赛（searchevents）
    search_key = f"{home_en}_vs_{away_en}"
    data = _sportsdb_get(f"searchevents.php?e={search_key}")
    if data and data.get("event"):
        ev = data["event"][0]
        result["match"] = {
            "home": ev.get("strHomeTeam", ""),
            "away": ev.get("strAwayTeam", ""),
            "league": ev.get("strLeague", ""),
            "venue": ev.get("strVenue", ""),
            "time": ev.get("dateEvent", ""),
            "round": ev.get("intRound", ""),
            "status": ev.get("strStatus", ""),
            "season": ev.get("strSeason", ""),
            "home_badge": ev.get("strHomeTeamBadge", ""),
            "away_badge": ev.get("strAwayTeamBadge", ""),
        }
        # 记录球队ID供后续查询
        home_id = ev.get("idHomeTeam", "")
        away_id = ev.get("idAwayTeam", "")

        # 2. 获取两队近期战绩（eventslast）
        if home_id:
            last = _sportsdb_get(f"eventslast.php?id={home_id}")
            if last and last.get("results"):
                for m in last["results"][:5]:
                    result["home_form"].append({
                        "date": m.get("dateEvent", ""),
                        "home": m.get("strHomeTeam", ""),
                        "away": m.get("strAwayTeam", ""),
                        "score": m.get("strScore", ""),
                    })

        if away_id:
            last = _sportsdb_get(f"eventslast.php?id={away_id}")
            if last and last.get("results"):
                for m in last["results"][:5]:
                    result["away_form"].append({
                        "date": m.get("dateEvent", ""),
                        "home": m.get("strHomeTeam", ""),
                        "away": m.get("strAwayTeam", ""),
                        "score": m.get("strScore", ""),
                    })

        # 3. 获取联赛积分榜（lookuptable）
        league_id = ev.get("idLeague", "")
        if league_id:
            season = ev.get("strSeason", "2025")
            table = _sportsdb_get(f"lookuptable.php?l={league_id}&s={season}")
            if table and table.get("table"):
                for t in table["table"]:
                    tname = t.get("strTeam", "")
                    pos = t.get("intRank", "")
                    pts = t.get("intPoints", "")
                    played = t.get("intPlayed", "")
                    form = t.get("strForm", "")
                    if home_en.lower() in tname.lower():
                        result["standings"]["home_pos"] = pos
                        result["standings"]["home_pts"] = pts
                        result["standings"]["home_played"] = played
                        result["standings"]["home_form"] = form
                    if away_en.lower() in tname.lower() or away_en.lower() in tname.lower().replace('ä','a').replace('ö','o'):
                        result["standings"]["away_pos"] = pos
                        result["standings"]["away_pts"] = pts
                        result["standings"]["away_played"] = played
                        result["standings"]["away_form"] = form

    else:
        # fallback: 分别查两队ID
        for team_name, team_en in [(home_name, home_en), (away_name, away_en)]:
            td = _sportsdb_get(f"searchteams.php?t={team_en}")
            if td and td.get("teams"):
                t = td["teams"][0]
                tid = t.get("idTeam", "")
                # 查该队下一场比赛
                next_ev = _sportsdb_get(f"eventsnext.php?id={tid}")
                if next_ev and next_ev.get("events"):
                    for ev in next_ev["events"]:
                        h = ev.get("strHomeTeam", "")
                        a = ev.get("strAwayTeam", "")
                        if home_en.lower() in h.lower() and away_en.lower() in a.lower():
                            result["match"] = {
                                "home": h, "away": a,
                                "league": ev.get("strLeague", ""),
                                "venue": ev.get("strVenue", ""),
                                "time": ev.get("dateEvent", ""),
                                "round": ev.get("intRound", ""),
                            }

    if not result["match"]:
        return {"error": f"TheSportsDB未找到 {home_name} vs {away_name}"}

    return result


# ============================================================
# football-data.org 数据获取（用户API Key — 世界杯/欧冠/五大联赛）
# ============================================================

def _football_get(path):
    """调用football-data.org API"""
    url = f"{FOOTBALL_BASE}/{path}"
    try:
        req = urllib.request.Request(url, headers={
            "X-Auth-Token": FOOTBALL_API_KEY,
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


# 常用竞赛代码 → 中文名（用于显示）
FOOTBALL_COMP_CN = {
    "WC": "世界杯", "CL": "欧冠", "PL": "英超", "ELC": "英冠",
    "BL1": "德甲", "PD": "西甲", "SA": "意甲", "FL1": "法甲",
    "DED": "荷甲", "BSA": "巴甲", "PPL": "葡超", "EC": "欧洲杯",
}


def _guess_competition_code(home_name, away_name):
    """根据队名推测竞赛（世界杯/欧冠为主）——先用英文名查通用matches接口"""
    home_en = TEAM_EN.get(home_name, home_name)
    away_en = TEAM_EN.get(away_name, away_name)

    # 先查所有比赛（最近7天），找到直接返回竞赛代码
    data = _football_get("matches")
    if data and data.get("matches"):
        for m in data["matches"]:
            h = (m.get("homeTeam", {}).get("name", "") or "").lower()
            a = (m.get("awayTeam", {}).get("name", "") or "").lower()
            hk = home_en.lower()
            ak = away_en.lower()
            if (hk in h or hk in a) and (ak in a or ak in h):
                comp = m.get("competition", {})
                return comp.get("code", "WC")
    # 没有找到实时的比赛，尝试逐个竞赛搜索
    for code in ["WC", "CL", "PL", "BL1", "PD", "SA", "FL1", "DED", "BSA", "PPL", "ELC", "EC"]:
        comp_data = _football_get(f"competitions/{code}/matches")
        if comp_data and comp_data.get("matches"):
            for m in comp_data["matches"]:
                h = (m.get("homeTeam", {}).get("name", "") or "").lower()
                a = (m.get("awayTeam", {}).get("name", "") or "").lower()
                hk = home_en.lower()
                ak = away_en.lower()
                if (hk in h or hk in a) and (ak in a or ak in h):
                    return code
    # 如果是世界杯球队，很可能是WC
    wc_teams = ["巴西","阿根廷","法国","德国","英格兰","西班牙","葡萄牙","荷兰",
                 "比利时","克罗地亚","瑞士","乌拉圭","哥伦比亚","墨西哥","日本","韩国"]
    if home_name in wc_teams or away_name in wc_teams:
        return "WC"
    return "PL"  # 默认英超


def fetch_football_data(home_name, away_name):
    """从football-data.org获取比赛数据

    覆盖:
      世界杯(WC)、欧冠(CL)、英超(PL)、德甲(BL1)、西甲(PD)、意甲(SA)、法甲(FL1)等
    """
    home_en = TEAM_EN.get(home_name, home_name)
    away_en = TEAM_EN.get(away_name, away_name)

    result = {
        "mode": "football",
        "source": "football-data.org",
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "match": {},
        "standings": {},
    }

    # 1. 获取竞赛代码
    comp_code = _guess_competition_code(home_name, away_name)

    # 2. 获取该竞赛的比赛列表，找本场
    data = _football_get(f"competitions/{comp_code}/matches")
    if "error" in data:
        return {"error": f"football-data.org: {data['error']}"}

    if data and data.get("matches"):
        for m in data["matches"]:
            h = m.get("homeTeam", {}).get("name", "") or ""
            a = m.get("awayTeam", {}).get("name", "") or ""
            hk = home_en.lower()
            ak = away_en.lower()
            # 模糊匹配英文队名
            h_lower = h.lower()
            a_lower = a.lower()
            if (hk in h_lower or hk in a_lower) and (ak in a_lower or ak in h_lower):
                comp = m.get("competition", {})
                score = m.get("score", {})
                ft = score.get("fullTime", {}) if isinstance(score, dict) else {}
                ht = score.get("halfTime", {}) if isinstance(score, dict) else {}
                status = m.get("status", "")
                stage = m.get("stage", "")

                result["match"] = {
                    "home": h,
                    "away": a,
                    "competition": comp.get("name", ""),
                    "comp_code": comp_code,
                    "matchday": m.get("matchday", ""),
                    "stage": stage,
                    "group": m.get("group", ""),
                    "status": status,
                    "date": m.get("utcDate", ""),
                    "score": {
                        "home": ft.get("home") if isinstance(ft, dict) else None,
                        "away": ft.get("away") if isinstance(ft, dict) else None,
                    },
                    "half_time": {
                        "home": ht.get("home") if isinstance(ht, dict) else None,
                        "away": ht.get("away") if isinstance(ht, dict) else None,
                    },
                    "winner": score.get("winner", "") if isinstance(score, dict) else "",
                }
                break

    if not result["match"]:
        return {"error": f"football-data.org未找到 {home_name} vs {away_name}"}

    # 3. 获取积分榜（如有）
    table_data = _football_get(f"competitions/{comp_code}/standings")
    if table_data and table_data.get("standings"):
        for standing in table_data["standings"]:
            s_type = standing.get("type", "")
            if s_type not in ("TOTAL", "总积分榜"):
                continue
            for entry in standing.get("table", []):
                team = entry.get("team", {})
                tname = (team.get("name", "") or "").lower()
                if home_en.lower() in tname or home_en.lower() == tname:
                    result["standings"]["home_pos"] = entry.get("position", "")
                    result["standings"]["home_pts"] = entry.get("points", "")
                    result["standings"]["home_played"] = entry.get("playedGames", "")
                    result["standings"]["home_form"] = (entry.get("form", "") or "")
                if away_en.lower() in tname or away_en.lower() == tname:
                    result["standings"]["away_pos"] = entry.get("position", "")
                    result["standings"]["away_pts"] = entry.get("points", "")
                    result["standings"]["away_played"] = entry.get("playedGames", "")
                    result["standings"]["away_form"] = (entry.get("form", "") or "")
            break  # 只用第一个积分榜

    return result


# ============================================================
# ESPN 公共API（免费，无需Key — NBA/WNBA/足总杯+全球足球联赛）
# ============================================================
ESPN_SPORT_MAP = {
    # 篮球
    "nba": "basketball/nba", "wnba": "basketball/wnba", "ncaa_mbb": "basketball/mens-college-basketball",
    # 足球 — 欧洲主流
    "eng.1": "soccer/eng.1", "eng.2": "soccer/eng.2", "eng.fa": "soccer/eng.fa",
    "esp.1": "soccer/esp.1", "ita.1": "soccer/ita.1", "ger.1": "soccer/ger.1",
    "fra.1": "soccer/fra.1", "ned.1": "soccer/ned.1", "por.1": "soccer/por.1",
    "sco.1": "soccer/sco.1", "bel.1": "soccer/bel.1", "tur.1": "soccer/tur.1",
    "uefa.champions": "soccer/uefa.champions", "uefa.europa": "soccer/uefa.europa",
    "fifa.world": "soccer/fifa.world", "concacaf.worldq": "soccer/concacaf.worldq",
    "afc.cup": "soccer/afc.cup",  # 亚洲杯/AFC Champions League
    # 亚洲足球
    "jpn.1": "soccer/jpn.1", "jpn.2": "soccer/jpn.2",
    "kor.1": "soccer/kor.1", "chn.1": "soccer/chn.1",
    # 北美
    "usa.1": "soccer/usa.1",
    # 南美
    "bra.1": "soccer/bra.1", "arg.1": "soccer/arg.1",
}

# 中文队名 → 英文队名（ESPN用英文）
TEAM_ESPN = {
    **TEAM_EN,  # 继承已有映射
    "佛得角": "Cape Verde",
    "刚果金": "DR Congo",
    "刚果(金)": "DR Congo",
}

# 中文运动名 → ESPN path
SPORT_CN = {
    "nba": "nba", "wnba": "wnba", "篮球": "basketball/nba",
    "英超": "eng.1", "西甲": "esp.1", "意甲": "ita.1", "德甲": "ger.1", "法甲": "fra.1",
    "荷甲": "ned.1", "葡超": "por.1", "苏超": "sco.1", "比甲": "bel.1",
    "欧冠": "uefa.champions", "欧联": "uefa.europa", "世界杯": "fifa.world",
    "亚洲杯": "afc.cup", "亚冠": "afc.cup",
    "足总杯": "eng.fa", "日职联": "jpn.1", "日乙": "jpn.2",
    "韩K联": "kor.1", "中超": "chn.1", "巴甲": "bra.1", "阿甲": "arg.1",
    "MLS": "usa.1", "美职联": "usa.1",
}

def _espn_fetch(path):
    """调用ESPN公共API（无需Key）"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": OS_AGENT})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": str(e)}


def fetch_espn_data(sport_or_league, team_name=None):
    """从ESPN公共API获取比赛数据（NBA/WNBA/全球足球）

    参数:
        sport_or_league: "nba" / "wnba" / "eng.1" / "esp.1" 等
        team_name: 可选，筛选特定球队

    返回:
        {
            "mode": "espn",
            "source": "ESPN",
            "sport": ...,
            "teams": [...],    # 球队列表
            "games": [...]     # 比赛数据
        }
    """
    league_path = SPORT_CN.get(sport_or_league.lower(), sport_or_league)
    espn_path = ESPN_SPORT_MAP.get(league_path, league_path)

    result = {
        "mode": "espn",
        "source": "ESPN (Public API)",
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sport": league_path,
        "teams": [],
        "games": [],
    }

    # 1. 获取球队列表
    teams_data = _espn_fetch(f"{espn_path}/teams")
    if teams_data and not teams_data.get("error"):
        for s in teams_data.get("sports", []):
            for l in s.get("leagues", []):
                for t in l.get("teams", []):
                    team = t.get("team", {})
                    result["teams"].append({
                        "name": team.get("displayName", ""),
                        "abbrev": team.get("abbreviation", ""),
                        "logo": team.get("logo", ""),
                    })

    # 2. 获取赛程/比分
    scoreboard = _espn_fetch(f"{espn_path}/scoreboard")
    if scoreboard and not scoreboard.get("error"):
        for event in scoreboard.get("events", []):
            comp = event.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            home = [c for c in competitors if c.get("homeAway") == "home"]
            away = [c for c in competitors if c.get("homeAway") == "away"]
            if not home or not away:
                continue
            home = home[0]
            away = away[0]
            status = event.get("status", {}).get("type", {}).get("description", "")
            venue = comp.get("venue", {})
            date = event.get("date", "")[:10]

            game = {
                "date": date,
                "status": status,
                "home": {
                    "name": home.get("team", {}).get("displayName", ""),
                    "score": home.get("score", ""),
                    "record": home.get("records", [{}])[0].get("summary", "") if home.get("records") else "",
                },
                "away": {
                    "name": away.get("team", {}).get("displayName", ""),
                    "score": away.get("score", ""),
                    "record": away.get("records", [{}])[0].get("summary", "") if away.get("records") else "",
                },
                "venue": venue.get("fullName", ""),
                "id": event.get("id", ""),
            }

            # 按球队筛选
            if team_name:
                tn = team_name.lower()
                if tn not in game["home"]["name"].lower() and tn not in game["away"]["name"].lower():
                    continue

            result["games"].append(game)

    return result


# ============================================================
# 竞彩数据获取（中国竞彩网官方API）
# ============================================================

def fetch_jingcai_data(home_name, away_name, skip_cross_ref=False):
    """从竞彩API获取指定比赛的赔率数据"""
    url = ("https://webapi.sporttery.cn/gateway/jc/football/"
           "getMatchCalculatorV1.qry?poolCode=hhad,had&channel=c")
    req = urllib.request.Request(url, headers={"User-Agent": OS_AGENT, "Referer": "https://www.sporttery.cn/"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"error": f"竞彩API请求失败: {e}"}

    # 在所有比赛日中搜索
    for day in data["value"]["matchInfoList"]:
        for m in day["subMatchList"]:
            h = m.get("homeTeamAllName", "")
            a = m.get("awayTeamAllName", "")
            # 模糊匹配
            if (home_name in h or home_name in a) and (away_name in a or away_name in h):
                had = m.get("had", {}) or {}
                hhad = m.get("hhad", {}) or {}
                is_single = any(p.get("single") == 1 for p in m.get("poolList", []))

                # 构建基础结果
                result = {
                    "mode": "jingcai",
                    "source": "中国竞彩网",
                    "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "match": {
                        "home": m.get("homeTeamAllName", ""),
                        "away": m.get("awayTeamAllName", ""),
                        "league": m.get("leagueAbbName", ""),
                        "time": f"{m.get('matchDate','')} {m.get('matchTime','')}",
                        "home_rank": m.get("homeRank", ""),
                        "away_rank": m.get("awayRank", ""),
                        "match_num": m.get("matchNumStr", ""),
                    },
                    "spf": {
                        "home_win": had.get("h"),
                        "draw": had.get("d"),
                        "away_win": had.get("a"),
                    } if had.get("h") else None,
                    "let_ball": {
                        "goal_line": hhad.get("goalLine", ""),
                        "home_win": hhad.get("h"),
                        "draw": hhad.get("d"),
                        "away_win": hhad.get("a"),
                    } if hhad.get("h") else None,
                    "is_single": is_single,
                }

                # ===== 交叉验证：拉取Bet365/1xbet数据（多线亚盘/角球/罚牌） =====
                home_en = TEAM_EN.get(m.get("homeTeamAllName", ""), m.get("homeTeamAllName", ""))
                away_en = TEAM_EN.get(m.get("awayTeamAllName", ""), m.get("awayTeamAllName", ""))
                yp_data = fetch_yapan_data(home_en, away_en, skip_cross_ref=True)
                if "error" not in yp_data:
                    result["cross_ref_yapan"] = {
                        "bet365": yp_data.get("bet365"),
                        "1xbet": yp_data.get("1xbet"),
                    }

                return result

    return {"error": f"在竞彩数据中未找到 {home_name} vs {away_name}"}


# ============================================================
# 亚盘/欧赔数据获取（odds-api.io）
# ============================================================

API_KEY = "33981e151ca87be10db961395d6a2ff963602d60a7dd7b421b046295b614e8c3"
BASE = "https://api.odds-api.io/v3"

def _curl_get(path):
    url = f"{BASE}{path}&apiKey={API_KEY}"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "15", url],
            capture_output=True, text=True, timeout=20
        )
        data = json.loads(r.stdout)
        # 检测速率限制
        if isinstance(data, dict) and "rate limit" in str(data.get("error", "")).lower():
            return None
        return data
    except:
        return None

def _find_event_id(home_kw, away_kw):
    """查找比赛ID（带重试）"""
    for attempt in range(3):
        events = _curl_get("/events?sport=football&league=international-fifa-world-cup")
        if events and isinstance(events, list):
            break
    if not events or not isinstance(events, list):
        for attempt in range(2):
            events = _curl_get("/events?sport=football")
            if events and isinstance(events, list):
                break
    if not events or not isinstance(events, list):
        return None
    for e in events:
        if not isinstance(e, dict):
            continue
        h = (e.get("home", "") or "").lower()
        a = (e.get("away", "") or "").lower()
        hk = home_kw.lower()
        ak = away_kw.lower()
        if (hk in h or hk in a) and (ak in a or ak in h):
            return {
                "id": e["id"],
                "home": e.get("home", ""),
                "away": e.get("away", ""),
                "date": (e.get("date", "") or "")[:19],
            }
    return None

def fetch_yapan_data(home_name, away_name, skip_cross_ref=False):
    """从 odds-api.io 获取亚盘/欧赔数据"""
    # 尝试中文名→英文
    home_en = TEAM_EN.get(home_name, home_name)
    away_en = TEAM_EN.get(away_name, away_name)

    info = _find_event_id(home_en, away_en)
    if not info:
        # 用原中文名再试
        info = _find_event_id(home_name, away_name)
    if not info:
        return {"error": f"在 odds-api 未找到 {home_name} vs {away_name}（试试英文名）"}

    result = {
        "mode": "yapan",
        "source": "odds-api.io",
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "match": {
            "home": info["home"],
            "away": info["away"],
            "date": info["date"],
        },
        "bet365": {},
        "1xbet": {},
    }

    # Bet365
    data = _curl_get(f"/odds?eventId={info['id']}&bookmakers=Bet365")
    if data and not isinstance(data, dict):
        data = data[0] if isinstance(data, list) else data
    if data and isinstance(data, dict):
        bms = data.get("bookmakers", {})
        bet365 = bms.get("Bet365", []) if isinstance(bms, dict) else []
        for m in bet365:
            mk = m.get("name", "")
            odds = m.get("odds", [])
            if mk == "ML" and odds:
                o = odds[0]
                result["bet365"]["european"] = {
                    "home": o.get("home"), "draw": o.get("draw"), "away": o.get("away"),
                }
            elif mk == "Spread":
                for s in odds:
                    pt = s.get("hdp", ""); h = s.get("home", "-"); a = s.get("away", "-")
                    if h != "-" and a != "-":
                        spt = str(pt).replace('+', '').replace('-', '')
                        if "asian_lines" not in result["bet365"]:
                            result["bet365"]["asian_lines"] = []
                        result["bet365"]["asian_lines"].append(f"{spt} @ {h} / -{spt} @ {a}")
            elif mk == "Totals" or mk == "Goals Over/Under":
                for t in odds:
                    pt = t.get("hdp", ""); ov = t.get("over", "-"); un = t.get("under", "-")
                    if ov != "-" and un != "-":
                        if "over_under" not in result["bet365"]:
                            result["bet365"]["over_under"] = []
                        result["bet365"]["over_under"].append(f"{pt}球 大@{ov} 小@{un}")
            elif mk == "Both Teams To Score" and odds:
                o = odds[0]
                result["bet365"]["btts"] = {"yes": o.get("yes"), "no": o.get("no")}
            elif mk in ("Bookings Totals", "Number of Cards In Match") and odds:
                for t in odds:
                    pt = t.get("hdp", ""); ov = t.get("over", "-"); un = t.get("under", "-")
                    if ov != "-" and un != "-":
                        if "cards" not in result["bet365"]:
                            result["bet365"]["cards"] = []
                        result["bet365"]["cards"].append(f"{pt}球 大@{ov} 小@{un}")
            elif mk == "Card Handicap" and odds:
                lines = []
                for s in odds:
                    pt = s.get("hdp", ""); h = s.get("home", "-"); a = s.get("away", "-")
                    if h != "-" and a != "-":
                        lines.append(f"{pt} @ {h} / -{pt} @ {a}")
                if lines:
                    result["bet365"]["card_handicap"] = lines
            elif mk == "Half Time Result" and odds:
                ht = {}
                for o in odds:
                    label = o.get("label", "")
                    if label == "1":    ht["home"] = o.get("under")
                    elif label == "Draw": ht["draw"] = o.get("under")
                    elif label == "2":  ht["away"] = o.get("under")
                if ht:
                    result["bet365"]["half_time"] = ht
            elif mk == "Totals HT" and odds:
                for t in odds:
                    pt = t.get("hdp", ""); ov = t.get("over", "-"); un = t.get("under", "-")
                    if ov != "-" and un != "-":
                        if "ht_over_under" not in result["bet365"]:
                            result["bet365"]["ht_over_under"] = []
                        result["bet365"]["ht_over_under"].append(f"半场{pt}球 大@{ov} 小@{un}")
            elif mk == "Corners Totals" and odds:
                # Bet365的角球主盘线
                for t in odds:
                    pt = t.get("hdp", ""); ov = t.get("over", "-"); un = t.get("under", "-")
                    if ov != "-" and un != "-":
                        if "corner_totals" not in result["bet365"]:
                            result["bet365"]["corner_totals"] = []
                        result["bet365"]["corner_totals"].append(f"{pt}球 大@{ov} 小@{un}")
            elif mk == "Alternative Asian Handicap" and odds:
                lines = []
                for s in odds:
                    pt = s.get("hdp", ""); h = s.get("home", "-"); a = s.get("away", "-")
                    if h != "-" and a != "-":
                        spt = str(pt).replace('+','').replace('-','')
                        lines.append(f"{spt} @ {h} / -{spt} @ {a}")
                if lines:
                    result["bet365"]["alt_asian"] = lines
            elif mk == "Alternative Goal Line" and odds:
                ous = []
                for t in odds:
                    pt = t.get("hdp", ""); ov = t.get("over", "-"); un = t.get("under", "-")
                    if ov != "-" and un != "-":
                        ous.append(f"{pt}球 大@{ov} 小@{un}")
                if ous:
                    result["bet365"]["alt_goal_lines"] = ous

    # ===== 交叉验证：拉取竞彩数据（单关标记+竞彩赔率） =====
    if not skip_cross_ref:
        jc_home = TEAM_CN.get(result["match"]["home"], result["match"]["home"])
        jc_away = TEAM_CN.get(result["match"]["away"], result["match"]["away"])
        jc_data = fetch_jingcai_data(jc_home, jc_away, skip_cross_ref=True)
        if "error" not in jc_data:
            result["cross_ref_jingcai"] = {
                "spf": jc_data.get("spf"),
                "let_ball": jc_data.get("let_ball"),
                "is_single": jc_data.get("is_single"),
                "match": jc_data.get("match"),
            }

    # 1xbet（更详细亚盘 + 角球）
    data2 = _curl_get(f"/odds?eventId={info['id']}&bookmakers=1xbet")
    if data2 and not isinstance(data2, dict):
        data2 = data2[0] if isinstance(data2, list) else data2
    if data2 and isinstance(data2, dict):
        bms = data2.get("bookmakers", {})
        xbet = bms.get("1xbet", []) if isinstance(bms, dict) else []
        for m in xbet:
            mk = m.get("name", "")
            odds = m.get("odds", [])
            if mk == "ML" and odds:
                o = odds[0]
                result["1xbet"]["european"] = {
                    "home": o.get("home"), "draw": o.get("draw"), "away": o.get("away"),
                }
            elif mk == "Spread":
                lines = []
                for s in odds:
                    pt = s.get("hdp", ""); h = s.get("home", "-"); a = s.get("away", "-")
                    if h != "-" and a != "-":
                        try:
                            hv, av = float(h), float(a)
                            if 1.1 <= hv <= 10.0 and 1.1 <= av <= 10.0:
                                lines.append(f"+{pt} @ {h} / -{pt} @ {a}")
                        except:
                            pass
                if lines:
                    result["1xbet"]["asian_lines"] = lines
            elif mk == "Goals Over/Under":
                ous = []
                for t in odds:
                    pt = t.get("hdp", ""); ov = t.get("over", "-"); un = t.get("under", "-")
                    try:
                        if float(ov) < 5.0 and float(un) < 5.0:
                            ous.append(f"{pt}球 大@{ov} 小@{un}")
                    except:
                        pass
                if ous:
                    result["1xbet"]["over_under"] = ous
            elif mk == "Both Teams To Score" and odds:
                o = odds[0]
                result["1xbet"]["btts"] = {"yes": o.get("yes"), "no": o.get("no")}
            elif mk == "Corners Totals" and odds:
                corners = []
                for t in odds:
                    pt = t.get("hdp", ""); ov = t.get("over", "-"); un = t.get("under", "-")
                    try:
                        if float(ov) < 20.0 and float(un) < 20.0:
                            corners.append(f"{pt}球 大@{ov} 小@{un}")
                    except: pass
                if corners:
                    result["1xbet"]["corner_totals"] = corners
            elif mk == "Corners Spread" and odds:
                lines = []
                for s in odds:
                    pt = s.get("hdp", ""); h = s.get("home", "-"); a = s.get("away", "-")
                    if h != "-" and a != "-":
                        lines.append(f"+{pt} @ {h} / -{pt} @ {a}")
                if lines:
                    result["1xbet"]["corner_spread"] = lines

    return result


# ============================================================
# 统一保存
# ============================================================

def save_data(data):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "latest_match_data.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n✅ 已保存到 {path}")
    return path


# ============================================================
# ESPN模式：快速查询（非比赛日也用—直接显示球队/赛程）
# ============================================================

def _print_espn_result(data):
    """打印ESPN数据摘要"""
    print(f"\n  联赛/运动: {data.get('sport', '?')}")
    print(f"  数据来源: {data['source']}")

    if data.get("teams"):
        print(f"\n  🏀 球队 ({len(data['teams'])}):")
        for t in data["teams"][:5]:
            print(f"     {t['name']} ({t['abbrev']})")
        if len(data["teams"]) > 5:
            print(f"     ... 还有 {len(data['teams'])-5} 支")

    if data.get("games"):
        print(f"\n  📋 比赛 ({len(data['games'])}):")
        for g in data["games"]:
            print(f"     {g['date']}: {g['away']['name']} {g['away']['score']} @ {g['home']['name']} {g['home']['score']} [{g['status']}]")
    else:
        print("\n  今日无比赛安排")


# ============================================================
# 命令行入口
# ============================================================

# ============================================================
# 滚球：实时比赛状态查询
# ============================================================

def fetch_live_state(home_name, away_name):
    """查询比赛实时状态（比分+时间+事件）"""
    home_en = TEAM_EN.get(home_name, home_name)
    away_en = TEAM_EN.get(away_name, away_name)
    info = _find_event_id(home_en, away_en)
    if not info:
        info = _find_event_id(home_name, away_name)
    if not info:
        return {"error": f"未找到 {home_name} vs {away_name}"}

    result = {
        "mode": "live",
        "fetch_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "match": {
            "home": info["home"],
            "away": info["away"],
            "date": info["date"],
        },
    }

    # 从events API获取状态
    events = _curl_get("/events?sport=football&league=international-fifa-world-cup")
    if not events or not isinstance(events, list):
        return {**result, "error": "无法获取赛事状态"}

    for e in events:
        if not isinstance(e, dict):
            continue
        if e.get("id") == info["id"]:
            scores = e.get("scores", {})
            status = e.get("status", "")
            result["status"] = status
            result["scores"] = {
                "home": scores.get("home", 0),
                "away": scores.get("away", 0),
                "halftime": scores.get("periods", {}).get("p1", {}) if isinstance(scores.get("periods"), dict) else {},
            }
            break

    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="统一比赛数据获取工具")
    parser.add_argument("--mode", required=True, choices=["jingcai", "yapan", "live", "sportsdb", "football", "espn"],
                        help="jingcai=竞彩 / yapan=亚盘欧赔 / live=实时 / sportsdb=TheSportsDB / football=football-data.org / espn=ESPN公共API(NBA/WNBA/足球)")
    parser.add_argument("--home", required=True,
                        help="主队名称（espn模式=联赛名如nba/wnba/eng.1/esp.1/fifa.world）")
    parser.add_argument("--away", required=False, default="",
                        help="客队名称（espn模式可选=球队筛选，不填则显示全部比赛）")
    args = parser.parse_args()

    print(f"\n{'='*50}")
    print(f"  [{args.mode.upper()}] 正在获取 {args.home} vs {args.away} 数据...")
    print(f"{'='*50}")

    if args.mode == "jingcai":
        data = fetch_jingcai_data(args.home, args.away)
    elif args.mode == "live":
        data = fetch_live_state(args.home, args.away)
    elif args.mode == "sportsdb":
        data = fetch_sportsdb_match_data(args.home, args.away)
    elif args.mode == "football":
        data = fetch_football_data(args.home, args.away)
    elif args.mode == "espn":
        data = fetch_espn_data(args.home, args.away)
    else:
        data = fetch_yapan_data(args.home, args.away)

    if "error" in data:
        print(f"\n❌ {data['error']}")
        sys.exit(1)

    # ESPN模式特殊处理（数据结构不同，没有match字段）
    if args.mode == "espn":
        _print_espn_result(data)
        save_data(data)
        return

    # 打印摘要
    print(f"\n== 比赛: {data['match'].get('home','?')} vs {data['match'].get('away','?')} ==")
    if args.mode != "live":
        print(f"   来源: {data['source']} | {data['fetch_time']}")

    if args.mode == "sportsdb":
        if "error" in data:
            print(f"\n❌ {data['error']}")
            sys.exit(1)
        m = data.get("match", {})
        print(f"   联赛: {m.get('league', '?')} | 轮次: {m.get('round', '?')}")
        print(f"   场地: {m.get('venue', '?')}")
        print(f"   时间: {m.get('time', '?')}")
        st = data.get("standings", {})
        if st:
            print(f"   主队排名: #{st.get('home_pos','?')} ({st.get('home_pts','?')}pts)")
            print(f"   客队排名: #{st.get('away_pos','?')} ({st.get('away_pts','?')}pts)")
        hf = data.get("home_form", [])
        if hf:
            print(f"   主队近5场: {' '.join([f.get('score','-') for f in hf])}")
        af = data.get("away_form", [])
        if af:
            print(f"   客队近5场: {' '.join([f.get('score','-') for f in af])}")
        save_data(data)
        return

    if args.mode == "football":
        if "error" in data:
            print(f"\n! {data['error']}")
            sys.exit(1)
        m = data.get("match", {})
        print(f"   赛事: {m.get('competition', '?')} | 轮次: {m.get('matchday', '?')} {m.get('stage', '')} {m.get('group', '')}")
        print(f"   状态: {m.get('status', '?')}")
        sc = m.get("score", {})
        if sc.get("home") is not None:
            print(f"   比分: {sc.get('home')} - {sc.get('away')}")
            ht = m.get("half_time", {})
            if ht.get("home") is not None:
                print(f"   半场: {ht.get('home')} - {ht.get('away')}")
        print(f"   时间: {m.get('date', '?')}")
        st = data.get("standings", {})
        if st:
            hf = st.get("home_form", "")
            af = st.get("away_form", "")
            print(f"   主队: #{st.get('home_pos','?')} ({st.get('home_pts','?')}pts/{st.get('home_played','?')}场) {'最近:'+hf if hf else ''}")
            print(f"   客队: #{st.get('away_pos','?')} ({st.get('away_pts','?')}pts/{st.get('away_played','?')}场) {'最近:'+af if af else ''}")
        save_data(data)
        return

    if args.mode == "live":
        if "error" in data:
            print(f"\n❌ {data['error']}")
            sys.exit(1)
        st = data.get("status", "unknown")
        sc = data.get("scores", {})
        print(f"   状态: {st}")
        print(f"   比分: {sc.get('home', '?')} - {sc.get('away', '?')}")
        if sc.get("halftime"):
            ht = sc["halftime"]
            print(f"   半场: {ht.get('home', '?')} - {ht.get('away', '?')}")
        save_data(data)
        return

    if args.mode == "jingcai":
        spf = data.get("spf")
        if spf:
            print(f"   胜平负: {spf['home_win']} / {spf['draw']} / {spf['away_win']}")
        lb = data.get("let_ball")
        if lb:
            print(f"   让球({lb['goal_line']}): {lb['home_win']} / {lb['draw']} / {lb['away_win']}")
        print(f"   单关: {'是 ✅' if data.get('is_single') else '否'}")
        # 交叉验证数据
        xr = data.get("cross_ref_yapan", {})
        if xr:
            b3 = xr.get("bet365", {})
            xb = xr.get("1xbet", {})
            print(f"   ── 交叉验证 ──")
            if b3.get("european"):
                eu = b3["european"]
                print(f"   Bet365 欧赔: {eu.get('home','-')} / {eu.get('draw','-')} / {eu.get('away','-')}")
            if xb.get("european"):
                eu = xb["european"]
                print(f"   1xbet 欧赔: {eu.get('home','-')} / {eu.get('draw','-')} / {eu.get('away','-')}")
            if b3.get("asian_lines"):
                print(f"   Bet365 亚盘: {b3['asian_lines'][0]}")
            if xb.get("asian_lines"):
                for l in xb["asian_lines"]:
                    nums = re.findall(r'@ ([\d.]+)', l)
                    if len(nums) >= 2:
                        try:
                            v1, v2 = float(nums[0]), float(nums[1])
                            if 1.70 <= v1 <= 2.20 and 1.70 <= v2 <= 2.20:
                                print(f"   1xbet 亚盘主盘: {l}")
                                break
                        except: pass
            if xb.get("corner_totals"):
                print(f"   1xbet 角球参考: {xb['corner_totals'][-1]}")
            if b3.get("cards"):
                print(f"   Bet365 罚牌参考: {b3['cards'][0]}")
    else:
        b3 = data.get("bet365", {})
        if b3.get("european"):
            eu = b3["european"]
            print(f"   Bet365 欧赔: {eu.get('home','-')} / {eu.get('draw','-')} / {eu.get('away','-')}")
        if b3.get("asian_lines"):
            for l in b3["asian_lines"][:2]:
                print(f"   Bet365 亚盘: {l.replace('+-','').replace('--','')}")
        xb = data.get("1xbet", {})
        if xb.get("european"):
            eu = xb["european"]
            print(f"   1xbet 欧赔: {eu.get('home','-')} / {eu.get('draw','-')} / {eu.get('away','-')}")
        if xb.get("asian_lines"):
            lines = xb["asian_lines"]
            # 找水位最接近1.85~2.00的线作为主盘
            best = lines[0]
            for l in lines:
                nums = re.findall(r'@ ([\d.]+)', l)
                if len(nums) >= 2:
                    try:
                        v1, v2 = float(nums[0]), float(nums[1])
                        if 1.70 <= v1 <= 2.20 and 1.70 <= v2 <= 2.20:
                            best = l; break
                    except: pass
            print(f"   1xbet 主亚盘: {best.replace('+-','').replace('--','')}")
        if b3.get("over_under"):
            print(f"   大小球: {b3['over_under'][0]}")
        if xb.get("corner_totals"):
            corners = xb["corner_totals"]
            best_c = corners[-1]  # 默认最后一条（高盘口值）
            for c in corners:
                parts = c.split()
                odds_vals = []
                for p in parts:
                    if '@' in p:
                        try: odds_vals.append(float(p.split('@')[1]))
                        except: pass
                if len(odds_vals) >= 2:
                    if 1.70 <= odds_vals[0] <= 2.10 and 1.70 <= odds_vals[1] <= 2.10:
                        best_c = c; break
                    if 1.50 <= odds_vals[0] <= 2.50 and 1.50 <= odds_vals[1] <= 2.50:
                        best_c = c  # 记录最后备选
            print(f"   角球大小: {best_c}")
        if b3.get("cards"):
            print(f"   罚牌大小: {b3['cards'][0]}")
        if b3.get("half_time"):
            ht = b3["half_time"]
            print(f"   半全场主客: {ht.get('home','-')} / {ht.get('draw','-')} / {ht.get('away','-')}")
        # 交叉验证：竞彩数据
        xr = data.get("cross_ref_jingcai", {})
        if xr:
            print(f"   ── 交叉验证：竞彩 ──")
            if xr.get("spf"):
                s = xr["spf"]
                print(f"   竞彩胜平负: {s.get('home_win','-')} / {s.get('draw','-')} / {s.get('away_win','-')}")
            if xr.get("let_ball"):
                l = xr["let_ball"]
                print(f"   竞彩让球({l.get('goal_line','')}): {l.get('home_win','-')} / {l.get('draw','-')} / {l.get('away_win','-')}")
            print(f"   竞彩单关: {'是 ✅' if xr.get('is_single') else '否'}")

    save_data(data)

if __name__ == "__main__":
    main()
