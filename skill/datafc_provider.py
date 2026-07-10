#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
datafc 统一数据提供器 — 替代 OpenLigaDB + xg_estimator + 内置积分表

提供:
  - match_data:     赛程/比分/状态
  - shots_data:     射门明细（含 xG/xGOT）
  - match_odds:     赔率（欧赔/亚盘/大小球/角球/罚牌/BTTS）
  - standings:      积分榜
  - lineups:        首发阵容 + 球员数据
  - formations:     阵型
  - pregame_form:   赛前近况（近5场结果、平均评分、联赛排名）
  - match_details:  裁判/场地信息
  - match_h2h:      交锋记录
  - sync_results:   赛后结果同步到 auto_results.json

数据源: Sofascore（通过 datafc 库）
"""

import sys, os, json, re, math
from datetime import datetime, timezone
from time import time
from typing import Optional, Dict, List, Tuple

# Logistic 斜率 α — P_base = 1/(1+exp(-α * 得分差))
# 控制七维评分差距到胜率映射的敏感度
# 该值可通过 update_calibration.py --apply 自动优化
ALPHA_LOGISTIC = 0.15

# ELO 调整系数 — λ 偏移 = (team_elo - avg_elo) / 100 × ELO_ADJUST_FACTOR
# 控制 ELO 评分差距对预期进球的放大力度
# 该值可通过 update_calibration.py --apply 自动优化
ELO_ADJUST_FACTOR = 0.20

# ============================================================
# 联赛平均 xG 基准（v8.5 全局化 + datafc 可覆盖）
# ============================================================
LEAGUE_XG_AVG = {
    "bl1": 1.55, "epl": 1.50, "laliga": 1.35, "seriea": 1.40,
    "ligue1": 1.45, "kleague1": 1.13, "kleague2": 1.05,
    "jleague1": 1.31, "jleague2": 1.28,
    "allsvenskan": 1.30, "eliteserien": 1.30, "championship": 1.25,
    "bundesliga2": 1.30, "ligue2": 1.25, "laliga2": 1.25, "serieb": 1.25,
    "primeira": 1.30, "proleague": 1.40, "scottish": 1.30, "eredivisie": 1.50,
    "aleague": 1.30, "mls": 1.50, "brasileirao": 1.35, "ligamx": 1.40,
    "csl": 1.25, "zhongjia": 1.20, "zhongyi": 1.10, "saudi": 1.30,
    "league1": 1.25, "league2": 1.20,
    "kleague1": 1.13, "kleague2": 1.05, "jleague1": 1.31, "jleague2": 1.28,
    "veikkausliiga": 1.25,
    "ucl": 1.50, "uel": 1.45, "uecl": 1.40,
    "facup": 1.40, "eflcup": 1.35, "copadelrey": 1.35, "dfbpokal": 1.35, "coppaita": 1.35,
    "rsl": 1.30, "bul": 1.30, "cro": 1.35, "svk": 1.30, "hun": 1.35, "irl": 1.25,
    "sportsdb": 1.30, "wm26": 1.40,
    "euro": 1.40, "copaf": 1.40, "afcon": 1.35, "asiancup": 1.35,
    "afccl": 1.40, "afccup": 1.35,
    "default": 1.40,
}

# 联赛平均 ELO 获取函数（v8.5 数据驱动）
_LEAGUE_AVG_ELO_CACHE = {}

def get_league_avg_elo(league: str) -> int:
    """获取联赛平均 ELO（从已缓存数据动态计算，v8.5）

    对 wm26/WC：取国家队 ELO 前 48 均值 ≈ 1750-1900
    对其他杯赛：取前 24 均值 ≈ 1600-1750
    对 club 联赛：返回默认 1500（俱乐部球队无 ELO）
    """
    if league in _LEAGUE_AVG_ELO_CACHE:
        return _LEAGUE_AVG_ELO_CACHE[league]

    _data = _load_elo_rankings()
    if _data and len(_data) > 10:
        _elos = sorted([v.get("elo", 1500) for v in _data.values()
                       if isinstance(v, dict) and v.get("elo")], reverse=True)
        if _elos:
            # 世界杯级：取前 48 强均值
            if league in ("wm26", "WC"):
                _top_n = min(48, len(_elos))
            # 洲际杯赛：取前 24
            elif league in ("euro", "copaf", "afcon", "asiancup"):
                _top_n = min(24, len(_elos))
            else:
                _top_n = 0
            if _top_n > 0:
                _avg = int(sum(_elos[:_top_n]) / _top_n)
                _LEAGUE_AVG_ELO_CACHE[league] = _avg
                return _avg

    # 俱乐部赛事或数据不足时回退
    _LEAGUE_AVG_ELO_CACHE[league] = 1500
    return 1500


# ============================================================
# 联赛平均角球基准（v8.5 全局化 + datafc 可覆盖）
# ============================================================
LEAGUE_AVG_CORNER = {
    "bl1": 4.8, "epl": 5.5, "laliga": 5.0, "seriea": 5.0, "ligue1": 5.2,
    "bundesliga2": 5.2, "championship": 5.5, "ligue2": 5.0, "laliga2": 5.0, "serieb": 5.0,
    "kleague1": 4.0, "kleague2": 3.8,
    "jleague1": 4.2, "jleague2": 4.0,
    "allsvenskan": 5.0, "eliteserien": 5.0, "veikkausliiga": 4.5,
    "eredivisie": 5.0, "primeira": 5.0, "proleague": 5.0, "scottish": 5.0,
    "aleague": 5.0, "mls": 5.0, "brasileirao": 5.0, "ligamx": 5.0,
    "csl": 3.5, "zhongjia": 3.5, "zhongyi": 3.0, "saudi": 4.5,
    "rsl": 4.5, "bul": 4.5, "cro": 4.8, "svk": 4.5, "hun": 4.5, "irl": 4.5,
    "sportsdb": 5.0,
    "default": 5.0,
}


import pandas as pd

# === datafc 导入 ===
try:
    from datafc import (
        match_data as dfc_match_data,
        shots_data as dfc_shots_data,
        match_odds_data as dfc_match_odds,
        match_h2h_data as dfc_match_h2h,
        lineups_data as dfc_lineups,
        formations_data as dfc_formations,
        pregame_form_data as dfc_pregame_form,
        match_details_data as dfc_match_details,
        standings_data as dfc_standings,
        seasons_data as dfc_seasons,
        search_data as dfc_search,
        eloratings,
    )
    DATAFIC_AVAILABLE = True
except ImportError:
    DATAFIC_AVAILABLE = False

# === SofaScore 连通性 ===
# 动态检测：用 datafc 自身 search 探活（绕过 Cloudflare 对直连的 403 阻断）
# v8.6: 改为动态探活 + 5 分钟自动重检，避免一次失败永远锁死在回退路径
_DATAFIC_ALIVE_STATE = None       # None=未初始化, True/False=上次结果
_DATAFIC_ALIVE_LAST_CHECK = 0.0   # 上次检查时间戳
_DATAFIC_ALIVE_TTL = 300          # 探活缓存有效期（秒）

def _fast_check_datafc_alive() -> bool:
    """用较短超时（10s）快速检查 datafc 连通性，避免硬等 30s+3 次重试"""
    try:
        from datafc import search_data
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as _ex:
            _fut = _ex.submit(search_data, "France", entity_type="team")
            _r = _fut.result(timeout=10)
            return (_r is not None and not _r.empty)
    except concurrent.futures.TimeoutError:
        return False
    except Exception:
        return False

def get_datafc_alive() -> bool:
    """动态获取 Sofascore 连通状态（缓存 5 分钟后自动重检）

    首次调用触发真实探活，后续 300 秒内返回缓存结果。
    过期后异步重检一次，检测到恢复/断开自动切换数据源。

    Returns:
        True  → datafc (Sofascore) 可用
        False → 已断开，上游应回退到 OpenLigaDB
    """
    global _DATAFIC_ALIVE_STATE, _DATAFIC_ALIVE_LAST_CHECK
    _now = time()
    # 首次 || 缓存过期 → 重新探活
    if _DATAFIC_ALIVE_STATE is None or (_now - _DATAFIC_ALIVE_LAST_CHECK) > _DATAFIC_ALIVE_TTL:
        _new = _fast_check_datafc_alive()
        if _new != _DATAFIC_ALIVE_STATE:
            if _new:
                print("[datafc] →→→ Sofascore API 恢复可用，切回主通路", flush=True)
            else:
                print("[datafc] →→→ Sofascore API 不可达，降级到 OpenLigaDB 回退", flush=True)
        _DATAFIC_ALIVE_STATE = _new
        _DATAFIC_ALIVE_LAST_CHECK = _now
    return _DATAFIC_ALIVE_STATE

# 兼容旧调用方式（通过名字引用，但本质上已不再是静态常量）
DATAFIC_ALIVE = get_datafc_alive()

# datafc 调用超时保护（秒）：datafc 内部默认 30s×3 次重试太慢，
# 包装器用较短超时快速失败，避免单次调用卡住整个预测管线
_DATAFIC_CALL_TIMEOUT = 25  # 单次 datafc 函数调用的最大等待时间

def _call_datafc(func, *args, timeout: int = None, **kwargs):
    """调用 datafc 函数并带超时保护

    用 ThreadPoolExecutor 包装，超时后抛出 TimeoutError。
    datafc 库内部有 30s×3 次重试，我们外层再加一道 25s 的熔断，
    防止 Cloudflare 卡住时整个进程挂起。

    Args:
        func: datafc 函数对象
        timeout: 自定义超时（秒），默认 _DATAFIC_CALL_TIMEOUT
        *args, **kwargs: 传递给 func

    Returns:
        func 的返回值，或超时时返回 None
    """
    import concurrent.futures
    _to = timeout if timeout is not None else _DATAFIC_CALL_TIMEOUT
    _ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    try:
        _fut = _ex.submit(func, *args, **kwargs)
        try:
            return _fut.result(timeout=_to)
        except concurrent.futures.TimeoutError:
            log(f"[datafc] 调用超时 ({_to}s): {func.__name__} — 网络抖动跳过")
            _fut.cancel()
            return None
    except Exception as _e:
        log(f"[datafc] 调用异常: {func.__name__} → {_e}")
        return None
    finally:
        # shutdown(wait=False) 防止超时后线程池还没退出导致整个流程卡住
        _ex.shutdown(wait=False)

# Windows 编码
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8:replace")
    import io
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        except Exception:
            pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
os.makedirs(CACHE_DIR, exist_ok=True)

# ============================================================
# League → Sofascore Tournament ID 映射
# ============================================================
# 来源: Sofascore 搜索 + 手动验证
LEAGUE_TOURNAMENT = {
    # 世界杯/国家队
    "wm26":       {"tid": 16, "sid": 58210, "name": "World Cup 2026", "type": "world_cup"},
    "WC":         {"tid": 16, "sid": 58210, "name": "World Cup 2026", "type": "world_cup"},
    # 五大联赛
    "bl1":        {"tid": 35, "sid": 97464, "name": "Bundesliga 26/27", "type": "league"},
    "epl":        {"tid": 17, "sid": 96668, "name": "Premier League 26/27", "type": "league"},
    "laliga":     {"tid": 8,  "sid": 97268, "name": "LaLiga 26/27", "type": "league"},
    "seriea":     {"tid": 23, "sid": 95836, "name": "Serie A 26/27", "type": "league"},
    "ligue1":     {"tid": 34, "sid": 96127, "name": "Ligue 1 26/27", "type": "league"},
    # 其他欧洲联赛
    "eredivisie": {"tid": 37, "name": "Eredivisie", "type": "league"},
    "primeira":   {"tid": 238, "sid": 97436, "name": "Liga Portugal 26/27", "type": "league"},
    "proleague":  {"tid": 38, "sid": 96616, "name": "Pro League 26/27", "type": "league"},
    "scottish":   {"tid": 36, "sid": 96658, "name": "Premiership 26/27", "type": "league"},
    # 次级联赛
    "championship": {"tid": 18, "sid": 97037, "name": "Championship 26/27", "type": "league"},
    "bundesliga2":  {"tid": 44, "sid": 97406, "name": "2. Bundesliga 26/27", "type": "league"},
    "ligue2":       {"tid": 182, "sid": 96109, "name": "Ligue 2 26/27", "type": "league"},
    "laliga2":      {"tid": 54, "sid": 97280, "name": "LaLiga 2 26/27", "type": "league"},
    "serieb":       {"tid": 53, "sid": 79502, "name": "Serie B 25/26", "type": "league"},
    # 亚洲联赛
    "csl":       {"tid": 649, "sid": 90049, "name": "中超 2026", "type": "league"},
    "zhongjia":  {"tid": 782, "sid": 90905, "name": "中甲 2026", "type": "league"},
    "zhongyi":   {"tid": 10381, "sid": 91320, "name": "中乙 2026", "type": "league"},
    "league1":   {"tid": 24, "sid": 97077, "name": "League One 26/27", "type": "league"},
    "league2":   {"tid": 25, "sid": 97078, "name": "League Two 26/27", "type": "league"},
    "saudi":     {"tid": 955, "sid": 80443, "name": "Saudi Pro League 25/26", "type": "league"},
    "kleague1":   {"tid": 410, "name": "K League 1", "type": "league"},
    "kleague2":   {"tid": 777, "name": "K League 2", "type": "league"},
    "jleague1":   {"tid": 397, "name": "J1 League", "type": "league"},
    "jleague2":   {"tid": 398, "name": "J2 League", "type": "league"},
    # 美洲/大洋洲联赛
    "aleague":    {"tid": 136, "sid": 82603, "name": "A-League 25/26", "type": "league"},
    "mls":        {"tid": 242, "sid": 86668, "name": "MLS 2026", "type": "league"},
    "brasileirao":{"tid": 325, "sid": 87678, "name": "Brasileirão 2026", "type": "league"},
    "ligamx":     {"tid": 11620, "sid": 87699, "name": "Liga MX 2026", "type": "league"},
    # 北欧联赛
    "sportsdb":   {"tid": 40, "sid": 87925, "name": "Allsvenskan 2026", "type": "league"},
    "allsvenskan": {"tid": 40, "sid": 87925, "name": "Allsvenskan 2026", "type": "league"},
    "eliteserien": {"tid": 20, "sid": 87809, "name": "Eliteserien 2026", "type": "league"},
    "veikkausliiga": {"tid": 41, "sid": 87930, "name": "Veikkausliiga 2026", "type": "league"},
    # 东欧/小联赛（欧战资格赛球队的国内联赛，v8.5）
    "rsl":      {"tid": 210, "sid": 96249, "name": "Mozzart Bet Superliga", "type": "league"},
    "bul":      {"tid": 247, "sid": 95923, "name": "Parva Liga", "type": "league"},
    "cro":      {"tid": 170, "sid": 95727, "name": "HNL", "type": "league"},
    "svk":      {"tid": 211, "sid": 96151, "name": "Niké Liga", "type": "league"},
    "hun":      {"tid": 187, "sid": 96914, "name": "OTP Bank Liga", "type": "league"},
    "irl":      {"tid": 382, "name": "League of Ireland", "type": "league"},
    # 杯赛（⚠️ cup 赛事需要 tournament_stage 参数，auto_fill_odds 暂未支持）
    "ucl":      {"tid": 7, "sid": 96758, "name": "UEFA Champions League", "type": "uefa"},
    "uel":      {"tid": 679, "sid": 96522, "name": "UEFA Europa League", "type": "uefa"},
    "uecl":     {"tid": 17015, "sid": 96529, "name": "UEFA Conference League", "type": "uefa"},
    "facup":    {"tid": 19, "sid": 82557, "name": "FA Cup", "type": "knockout"},
    "eflcup":   {"tid": 21, "sid": 96185, "name": "EFL Cup", "type": "knockout"},
    "copadelrey":{"tid": 329, "sid": 82988, "name": "Copa del Rey", "type": "knockout"},
    "dfbpokal": {"tid": 217, "sid": 95860, "name": "DFB Pokal", "type": "knockout"},
    "coppaita": {"tid": 328, "sid": 97028, "name": "Coppa Italia", "type": "knockout"},
    # 国家队洲际杯赛
    "euro":      {"tid": 15, "sid": 88447, "name": "UEFA Euro", "type": "world_cup"},
    "copaf":     {"tid": 15, "sid": 88442, "name": "Copa America", "type": "world_cup"},
    "afcon":     {"tid": 15, "sid": 88446, "name": "Africa Cup of Nations", "type": "world_cup"},
    "asiancup":  {"tid": 15, "sid": 88445, "name": "AFC Asian Cup", "type": "world_cup"},
    # 亚足联赛事（datafc 覆盖，v8.5 移除 ESPN）
    "afccl":     {"tid": 15, "sid": 88448, "name": "AFC Champions League Elite", "type": "uefa"},
    "afccup":    {"tid": 15, "sid": 88449, "name": "AFC Cup", "type": "uefa"},
}

# 中文队名 → Sofascore 英文队名（辅助匹配）
TEAM_EN = {
    "英格兰": "England", "巴西": "Brazil", "阿根廷": "Argentina",
    "法国": "France", "德国": "Germany", "西班牙": "Spain",
    "葡萄牙": "Portugal", "荷兰": "Netherlands", "意大利": "Italy",
    "瑞士": "Switzerland", "乌拉圭": "Uruguay", "哥伦比亚": "Colombia",
    "墨西哥": "Mexico", "日本": "Japan", "韩国": "South Korea",
    "澳大利亚": "Australia", "埃及": "Egypt", "比利时": "Belgium",
    "克罗地亚": "Croatia", "塞内加尔": "Senegal",
    "佛得角": "Cape Verde", "沙特": "Saudi Arabia",
    "美国": "USA", "加拿大": "Canada", "摩洛哥": "Morocco",
    "丹麦": "Denmark", "瑞典": "Sweden", "挪威": "Norway",
    "波兰": "Poland", "奥地利": "Austria", "捷克": "Czech Republic",
    "匈牙利": "Hungary", "土耳其": "Turkey", "苏格兰": "Scotland",
    "波黑": "Bosnia", "卡塔尔": "Qatar", "新西兰": "New Zealand",
    "巴拉圭": "Paraguay", "厄瓜多尔": "Ecuador",
    "南非": "South Africa", "加纳": "Ghana",
    # 补充国家队（用于 OpenLigaDB / datafc）
    "乌兹别克斯坦": "Uzbekistan", "民主刚果": "DR Congo",
    "阿尔及利亚": "Algeria", "巴拿马": "Panama",
    "科特迪瓦": "Ivory Coast", "约旦": "Jordan",
    "突尼斯": "Tunisia", "海地": "Haiti", "库拉索": "Curacao",
    "伊朗": "Iran", "伊拉克": "Iraq",
    "喀麦隆": "Cameroon", "尼日利亚": "Nigeria",
    "秘鲁": "Peru", "智利": "Chile",
    "委内瑞拉": "Venezuela", "哥斯达黎加": "Costa Rica",
    "牙买加": "Jamaica", "刚果(布)": "Congo",
    "布基纳法索": "Burkina Faso", "科摩罗": "Comoros",
    "刚果金": "DR Congo", "沙特阿拉伯": "Saudi Arabia",

    # 英超
    "曼城": "Manchester City", "阿森纳": "Arsenal", "利物浦": "Liverpool",
    "曼联": "Manchester United", "切尔西": "Chelsea", "热刺": "Tottenham",
    "纽卡斯尔": "Newcastle United", "阿斯顿维拉": "Aston Villa",
    "布莱顿": "Brighton", "西汉姆联": "West Ham", "狼队": "Wolves",
    "伯恩茅斯": "Bournemouth", "富勒姆": "Fulham", "布伦特福德": "Brentford",
    "水晶宫": "Crystal Palace", "埃弗顿": "Everton", "诺丁汉森林": "Nottingham Forest",
    "莱斯特城": "Leicester City", "伊普斯维奇": "Ipswich Town", "南安普顿": "Southampton",
    # 西甲
    "巴萨": "Barcelona", "巴塞罗那": "Barcelona",
    "皇马": "Real Madrid", "皇家马德里": "Real Madrid",
    "马竞": "Atletico Madrid", "马德里竞技": "Atletico Madrid",
    "毕尔巴鄂": "Athletic Bilbao", "皇家社会": "Real Sociedad",
    "比利亚雷亚尔": "Villarreal", "贝蒂斯": "Real Betis",
    "塞维利亚": "Sevilla", "巴伦西亚": "Valencia", "西班牙人": "Espanyol",
    "赫罗纳": "Girona", "奥萨苏纳": "Osasuna", "塞尔塔": "Celta Vigo",
    "马洛卡": "Mallorca", "巴列卡诺": "Rayo Vallecano",
    "阿拉维斯": "Alaves", "赫塔费": "Getafe", "拉斯帕尔马斯": "Las Palmas",
    "瓦拉杜利德": "Real Valladolid", "莱加内斯": "Leganes",
    # 德甲
    "拜仁": "Bayern Munich", "拜仁慕尼黑": "Bayern Munich",
    "多特蒙德": "Borussia Dortmund", "勒沃库森": "Bayer Leverkusen",
    "莱比锡": "RB Leipzig", "法兰克福": "Eintracht Frankfurt",
    "斯图加特": "Stuttgart", "门兴": "Borussia Monchengladbach",
    "沃尔夫斯堡": "Wolfsburg", "弗赖堡": "Freiburg",
    "霍芬海姆": "Hoffenheim", "柏林联合": "Union Berlin",
    "美因茨": "Mainz", "奥格斯堡": "Augsburg",
    "不莱梅": "Werder Bremen", "波鸿": "Bochum",
    "海登海姆": "Heidenheim", "圣保利": "St. Pauli", "基尔": "Holstein Kiel",
    # 意甲
    "国米": "Inter", "国际米兰": "Inter",
    "AC米兰": "AC Milan", "米兰": "AC Milan",
    "尤文": "Juventus", "尤文图斯": "Juventus",
    "那不勒斯": "Napoli", "罗马": "Roma", "拉齐奥": "Lazio",
    "亚特兰大": "Atalanta", "佛罗伦萨": "Fiorentina",
    "博洛尼亚": "Bologna", "都灵": "Torino",
    "乌迪内斯": "Udinese", "热那亚": "Genoa",
    "蒙扎": "Monza", "维罗纳": "Verona",
    "卡利亚里": "Cagliari", "恩波利": "Empoli",
    "帕尔马": "Parma", "威尼斯": "Venezia", "科莫": "Como",
    # 法甲
    "巴黎": "Paris Saint-Germain", "巴黎圣日耳曼": "Paris Saint-Germain",
    "马赛": "Marseille", "里昂": "Lyon", "摩纳哥": "Monaco",
    "里尔": "Lille", "尼斯": "Nice", "朗斯": "Lens",
    "雷恩": "Rennes", "斯特拉斯堡": "Strasbourg",
    "南特": "Nantes", "图卢兹": "Toulouse",
    "兰斯": "Reims", "布雷斯特": "Brest",
    "欧塞尔": "Auxerre", "昂热": "Angers", "圣埃蒂安": "Saint-Etienne",

    # K联赛球队
    # 中超
    "上海海港": "Shanghai Port", "上海申花": "Shanghai Shenhua",
    "山东泰山": "Shandong Taishan", "成都蓉城": "Chengdu Rongcheng",
    "北京国安": "Beijing Guoan", "武汉三镇": "Wuhan Three Towns",
    "浙江队": "Zhejiang FC", "河南队": "Henan FC",
    "天津津门虎": "Tianjin Jinmen Tiger", "长春亚泰": "Changchun Yatai",
    "深圳新鹏城": "Shenzhen Peng City", "青岛海牛": "Qingdao Hainiu",
    # 沙特联赛
    "利雅得新月": "Al Hilal", "利雅得胜利": "Al Nassr",
    "吉达联合": "Al Ittihad", "吉达国民": "Al Ahli",
    "利雅得青年": "Al Shabab", "达曼协作": "Al Ettifaq",

    "全北现代": "Jeonbuk Hyundai Motors", "蔚山现代": "Ulsan HD",
    "首尔FC": "FC Seoul", "FC首尔": "FC Seoul",
    "浦项制铁": "Pohang Steelers", "仁川联": "Incheon United",
    "江原FC": "Gangwon FC", "光州FC": "Gwangju FC",
    "济州SK": "Jeju SK", "济州联": "Jeju United",
    "大田市民": "Daejeon Hana Citizen", "金泉尚武": "Gimcheon Sangmu",
    "水原FC": "Suwon FC", "大邱FC": "Daegu FC",
    "安养FC": "FC Anyang", "富川FC": "Bucheon FC 1995",
    # K联赛英文别名（predictions_db中存在英文名记录）
    "Jeonbuk": "Jeonbuk Hyundai Motors", "Gangwon": "Gangwon FC",
    "厄格里特": "Orgryte IS",

    # 瑞典超
    "天狼星": "Sirius", "米亚尔比": "Mjallby",
    "马尔默": "Malmö FF", "哈马比": "Hammarby",
    "赫根": "BK Hacken", "佐加顿斯": "Djurgarden",
    "埃尔夫斯堡": "Elfsborg", "哥德堡": "IFK Göteborg",
    "索尔纳": "AIK", "北雪平": "IFK Norrkoping",
    "卡尔马": "Kalmar FF", "哈尔姆斯塔德": "Halmstads BK",
    "韦斯特罗斯": "Vasteras SK", "代格福什": "Degerfors IF",
    "布洛马波卡纳": "Brommapojkarna",

    # 挪超
    # 澳超
    "墨尔本胜利": "Melbourne Victory", "悉尼FC": "Sydney FC", "墨尔本城": "Melbourne City",
    "中央海岸": "Central Coast", "阿德莱德": "Adelaide United", "西部联": "Western United",
    "珀斯光荣": "Perth Glory", "布里斯班": "Brisbane Roar", "纽卡斯尔喷气机": "Newcastle Jets",
    "惠灵顿": "Wellington Phoenix", "西悉尼": "Western Sydney", "麦克阿瑟": "Macarthur",
    "奥克兰FC": "Auckland FC",
    # 美职联
    "迈阿密国际": "Inter Miami", "洛杉矶FC": "Los Angeles FC", "纽约城": "New York City",
    "亚特兰大联": "Atlanta United", "西雅图海湾人": "Seattle Sounders",
    "洛杉矶银河": "LA Galaxy", "芝加哥火焰": "Chicago Fire",
    # 巴甲
    "弗拉门戈": "Flamengo", "帕尔梅拉斯": "Palmeiras", "科林蒂安": "Corinthians",
    "圣保罗": "São Paulo", "桑托斯": "Santos", "克鲁塞罗": "Cruzeiro",
    # 墨超
    "美洲队": "Club América", "瓜达拉哈拉": "Guadalajara", "老虎大学": "Tigres UANL",
    "蒙特雷": "Monterrey", "蓝十字": "Cruz Azul",
    # 葡超
    "本菲卡": "Benfica", "波尔图": "Porto", "葡萄牙体育": "Sporting CP",
    "布拉加": "Braga", "吉马良斯": "Vitória Guimarães",
    # 比甲
    "布鲁日": "Club Brugge", "安德莱赫特": "Anderlecht", "标准列日": "Standard Liège",
    "根特": "Gent", "安特卫普": "Antwerp",
    # 苏超
    "凯尔特人": "Celtic", "流浪者": "Rangers", "哈茨": "Heart of Midlothian",
    "阿伯丁": "Aberdeen", "希伯尼安": "Hibernian",

    "博德闪耀": "Bodo/Glimt", "莫尔德": "Molde", "维京": "Viking",
    "布兰": "Brann", "罗森博格": "Rosenborg", "利勒斯特罗姆": "Lillestrøm",
    "萨普斯堡": "Sarpsborg", "斯特罗姆": "Strømsgodset", "汉坎": "HamKam",
    "奥德": "Odd", "特罗姆瑟": "Tromsø", "克里斯蒂安": "Kristiansund",
    "腓特烈斯塔": "Fredrikstad", "海于格松": "Haugesund", "桑讷菲尤尔": "Sandefjord",
    "KFUM奥斯陆": "KFUM Oslo",

    # 芬超
    "赫尔辛基": "HJK", "库奥皮奥": "KuPS",
    "塞伊奈": "SJK", "国际图尔库": "FC Inter",
    "AC奥卢": "AC Oulu", "瓦萨": "VPS",
    "埃尔维斯": "Ilves", "TPS图尔库": "TPS",
    "拉赫蒂": "Lahti", "玛丽港": "IFK Mariehamn",
    "雅罗": "FF Jaro", "坦佩雷": "Tampere United",
    "赫尔火花": "Gnistan", "赫尔辛基火花": "Gnistan",
    "古比斯": "KuPS",
    # 芬超球队别名
    "塞伊奈约基": "SJK", "坦佩雷山猫": "Tampere United",

    # 欧战俱乐部
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "伏伊伏丁": "Vojvodina", "Vojvodina": "Vojvodina",
    "费伦茨": "Ferencváros", "Ferencváros": "Ferencváros", "Ferencvaros": "Ferencváros",
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "伏伊伏丁": "Vojvodina", "Vojvodina": "Vojvodina",
    "费伦茨": "Ferencváros", "Ferencváros": "Ferencváros",
    "阿拉木图": "Kairat Almaty", "Kairat Almaty": "Kairat Almaty",
    "苏捷斯卡": "FK Sutjeska", "FK Sutjeska": "FK Sutjeska",

    # 德甲
    "拜仁": "Bayern Munich", "多特蒙德": "Borussia Dortmund",
    "勒沃库森": "Bayer Leverkusen", "莱比锡": "RB Leipzig",
}
# 中文队名 -> OpenLigaDB 德文队名（用于该数据源匹配）
TEAM_DE = {
    "英格兰": "England", "巴西": "Brasilien", "阿根廷": "Argentinien",
    "法国": "Frankreich", "德国": "Deutschland", "西班牙": "Spanien",
    "葡萄牙": "Portugal", "荷兰": "Niederlande", "意大利": "Italien",
    "瑞士": "Schweiz", "乌拉圭": "Uruguay", "哥伦比亚": "Kolumbien",
    "墨西哥": "Mexiko", "日本": "Japan", "韩国": "Suedkorea",
    "澳大利亚": "Australien", "埃及": "Aegypten", "比利时": "Belgien",
    "克罗地亚": "Kroatien", "塞内加尔": "Senegal",
    "佛得角": "Kap Verde", "沙特": "Saudi Arabien",
    "美国": "USA", "加拿大": "Kanada", "摩洛哥": "Marokko",
    "丹麦": "Daenemark", "瑞典": "Schweden", "挪威": "Norwegen",
    "波兰": "Polen", "奥地利": "Oesterreich", "捷克": "Tschechien",
    "匈牙利": "Ungarn", "土耳其": "Tuerkei", "苏格兰": "Schottland",
    "波黑": "Bosnien und Herzegowina", "卡塔尔": "Katar",
    "新西兰": "Neuseeland", "巴拉圭": "Paraguay", "厄瓜多尔": "Ecuador",
    "南非": "Suedafrika", "加纳": "Ghana",
    "民主刚果": "DR Kongo", "刚果金": "DR Kongo",
    "阿尔及利亚": "Algerien",
    "突尼斯": "Tunesien", "海地": "Haiti", "库拉索": "Curacao",
    "科特迪瓦": "Elfenbeinkueste", "巴拿马": "Panama",
    "乌兹别克": "Usbekistan", "伊朗": "Iran", "伊拉克": "Irak",
    "约旦": "Jordanien",
    "乌兹别克斯坦": "Usbekistan",  # 与"乌兹别克"同义变体
    "喀麦隆": "Kamerun", "尼日利亚": "Nigeria", "布基纳法索": "Burkina Faso",
    "科摩罗": "Komoren", "刚果布": "Kongo",
    "冰岛": "Island", "芬兰": "Finnland", "塞尔维亚": "Serbien",
    "斯洛伐克": "Slowakei", "斯洛文尼亚": "Slowenien", "罗马尼亚": "Rumaenien",
    "保加利亚": "Bulgarien", "希腊": "Griechenland", "以色列": "Israel",
    "威尔士": "Wales", "北爱尔兰": "Nordirland", "爱尔兰": "Irland",
    "白俄罗斯": "Weissrussland", "乌克兰": "Ukraine", "俄罗斯": "Russland",
    "秘鲁": "Peru", "智利": "Chile", "委内瑞拉": "Venezuela",
    "哥斯达黎加": "Costa Rica", "牙买加": "Jamaika", "洪都拉斯": "Honduras",
    "沙特阿拉伯": "Saudi Arabien", "阿曼": "Oman", "巴林": "Bahrain",
    "阿联酋": "VAE", "叙利亚": "Syrien", "黎巴嫩": "Libanon",
    "泰国": "Thailand", "越南": "Vietnam", "印尼": "Indonesien",
    "中国": "China", "朝鲜": "Nordkorea", "马来西亚": "Malaysia",
    "刚果(金)": "DR Kongo", "刚果(布)": "Kongo",
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "伏伊伏丁": "Vojvodina", "Vojvodina": "Vojvodina",
    "费伦茨": "Ferencváros", "Ferencváros": "Ferencváros", "Ferencvaros": "Ferencváros",
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "索陆军": "CSKA Sofia", "CSKA Sofia": "CSKA Sofia",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "斯海杜克": "Hajduk Split", "Hajduk Split": "Hajduk Split",
    "日利纳": "Žilina", "Žilina": "Žilina",
    "德里城": "Derry City", "Derry City": "Derry City",
    "伏伊伏丁": "Vojvodina", "Vojvodina": "Vojvodina",
    "费伦茨": "Ferencváros", "Ferencváros": "Ferencváros",
    "阿拉木图": "Kairat Almaty", "Kairat Almaty": "Kairat Almaty",
    "苏捷斯卡": "FK Sutjeska", "FK Sutjeska": "FK Sutjeska",
}

# === 自动反向映射：英文 → 德文（用于 OpenLigaDB 队名匹配）===

_ALIAS: dict = {}
for _cn in TEAM_DE:
    _de = TEAM_DE.get(_cn, "").lower().replace(" ", "")
    _en = TEAM_EN.get(_cn, "").lower().replace(" ", "")
    if _de:
        _ALIAS[_cn.lower().replace(" ", "")] = _de
        _ALIAS[_de] = _de
        if _en and _en != _de:
            _ALIAS[_en] = _de
for _k, _v in {
    # 常见英文→德文别名
    "usa": "usa", "unitedstates": "usa",
    "southkorea": "suedkorea", "czech": "tschechien",
    "czechrepublic": "tschechien", "bosnia": "bosnienundherzegowina",
    "ivorycoast": "elfenbeinkueste", "drcongo": "drkongo",
    "saudiarabia": "saudiarabien", "capeverde": "kapverde",
    "democraticrepublicofcongo": "drkongo",
    # Umlaut 变体（API 返回带变音符号，代码存 ASCII 替代写法）
    "suedkorea": "suedkorea", "südkorea": "suedkorea",
    "tuerkei": "tuerkei", "türkei": "tuerkei",
    "aegypten": "aegypten", "ägypten": "aegypten",
    "oesterreich": "oesterreich", "österreich": "oesterreich",
    "suedafrika": "suedafrika", "südafrika": "suedafrika",
    "elfenbeinkueste": "elfenbeinkueste", "elfenbeinküste": "elfenbeinkueste",
    "curacao": "curacao", "curaçao": "curacao",
}.items():
    _ALIAS[_k] = _v

# 补全 TEAM_DE 和 TEAM_EN 缺失的球队
_TEAM_EXTRA_DE = {
    "英格兰": "England",
    "荷兰": "Niederlande",
    "丹麦": "Daenemark",
    "波兰": "Polen",
    "匈牙利": "Ungarn",
    "意大利": "Italien",
    "塞尔维亚": "Serbien",
    "乌克兰": "Ukraine",
    "俄罗斯": "Russland",
}
_TEAM_EXTRA_EN = {
    "俄罗斯": "Russia",
    "塞尔维亚": "Serbia",
    "乌克兰": "Ukraine",
}
for _cn, _de in _TEAM_EXTRA_DE.items():
    if _cn not in TEAM_DE:
        TEAM_DE[_cn] = _de
for _cn, _en in _TEAM_EXTRA_EN.items():
    if _cn not in TEAM_EN:
        TEAM_EN[_cn] = _en
# 为新增的也生成别名
for _cn in _TEAM_EXTRA_DE:
    _de = TEAM_DE.get(_cn, "").lower().replace(" ", "")
    _en = TEAM_EN.get(_cn, "").lower().replace(" ", "")
    if _de:
        _ALIAS[_cn.lower().replace(" ", "")] = _de
        _ALIAS[_de] = _de
        if _en and _en != _de:
            _ALIAS[_en] = _de


def _norm(s: str) -> str:
    """归一化队名：去除空格、转小写、变音符→ASCII（ü→ue, ä→ae, ö→oe, ç→c）"""
    s2 = s.lower().replace(" ", "").replace("-", "").replace("'", "")
    UMLAUT_MAP = str.maketrans({
        'ü': 'ue', 'ä': 'ae', 'ö': 'oe', 'é': 'e', 'è': 'e', 'ê': 'e',
        'à': 'a', 'á': 'a', 'ç': 'c', 'ñ': 'n',
        'Ü': 'ue', 'Ä': 'ae', 'Ö': 'oe', 'É': 'e', 'Ç': 'c',
    })
    s2 = s2.translate(UMLAUT_MAP)
    return s2


def log(msg):
    """安全打印"""
    try:
        print(str(msg))
    except:
        pass


# ============================================================
# 工具函数
# ============================================================

def _fraction_to_decimal(fraction: str) -> Optional[float]:
    """英式分数赔率 → 十进制赔率: '12/25' → 1.48"""
    if not fraction:
        return None
    try:
        parts = fraction.split("/")
        if len(parts) == 2:
            num, den = float(parts[0]), float(parts[1])
            if den > 0:
                return round(num / den + 1, 4)
        # 已经是十进制
        return float(fraction)
    except (ValueError, ZeroDivisionError):
        return None


def _get_season_id(tid: int, target_year: Optional[int] = None) -> Optional[int]:
    """获取联赛当前赛季 ID（自动检测最新赛季）"""
    try:
        seasons = dfc_seasons(tournament_id=tid)
        if seasons.empty:
            return None
        # 按 season_id 降序取最新
        seasons = seasons.sort_values("season_id", ascending=False)
        if target_year:
            year_str = str(target_year)
            for _, row in seasons.iterrows():
                if year_str in str(row.get("season_year", "")):
                    return int(row["season_id"])
        return int(seasons.iloc[0]["season_id"])
    except Exception:
        return None


def _find_team_in_matches(match_df: pd.DataFrame, team_name: str) -> pd.DataFrame:
    """在 match_df 中查找包含某队的比赛（支持中文名→英文名映射）"""
    if match_df.empty:
        return match_df
    # 中文→英文
    team_en = TEAM_EN.get(team_name, team_name)
    tn_lower = team_en.lower().replace(" ", "").replace("-", "")
    # 直接在 home_team / away_team 中匹配
    mask = (match_df["home_team"].str.lower().str.replace(" ", "", regex=False).str.replace("-", "", regex=False).str.contains(tn_lower, na=False) |
            match_df["away_team"].str.lower().str.replace(" ", "", regex=False).str.replace("-", "", regex=False).str.contains(tn_lower, na=False))
    return match_df[mask].copy()


# ============================================================
# 主接口
# ============================================================

def get_league_config(league: str) -> Optional[dict]:
    """获取联赛的 Sofascore 配置"""
    return LEAGUE_TOURNAMENT.get(league)


def get_matches(league: str, week_number: Optional[int] = None,
                team_name: Optional[str] = None) -> pd.DataFrame:
    """获取比赛列表

    Args:
        league: 联赛代码 (wm26/bl1/epl/kleague1/...)
        week_number: 轮次（世界杯需要，联赛可省略）
        team_name: 可选，按球队筛选

    Returns:
        DataFrame with columns:
          game_id, home_team, away_team, status, start_timestamp,
          home_score_normaltime, away_score_normaltime, week, ...
    """
    cfg = get_league_config(league)
    if not cfg:
        log(f"[datafc] 未知联赛: {league}")
        return pd.DataFrame()

    tid = cfg["tid"]
    sid = cfg.get("sid")
    tour_type = cfg.get("type")

    # 如果没有硬编码 season_id，自动检测
    if not sid:
        sid = _get_season_id(tid)
        if not sid:
            log(f"[datafc] 无法获取联赛 {league} 的赛季 ID")
            return pd.DataFrame()

    try:
        kwargs = {"tournament_id": tid, "season_id": sid}
        if tour_type in ("world_cup", "cup") or week_number is not None:
            kwargs["week_number"] = week_number or 1
        df = _call_datafc(dfc_match_data, **kwargs)
        if df is None:
            return pd.DataFrame()
    except Exception as e:
        log(f"[datafc] match_data 失败: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    # 如果指定了week_number但没有数据，尝试其他轮次
    if df.empty and week_number is not None:
        for w in range(1, 20):
            df = _call_datafc(dfc_match_data, tournament_id=tid, season_id=sid, week_number=w)
            if df is not None and not df.empty:
                break

    # 按球队筛选
    if team_name and not df.empty:
        df = _find_team_in_matches(df, team_name)

    return df


# 近期比赛数据缓存 {(league): DataFrame} — 避免重复网络请求
_RECENT_MATCHES_CACHE: dict = {}
_RECENT_MATCHES_CACHE_FILE = os.path.join(CACHE_DIR, "recent_matches_cache.json")
_STRENGTH_CACHE: dict = {}
_STRENGTH_CACHE_FILE = os.path.join(CACHE_DIR, "team_strength_cache.json")


def _load_match_disk_cache() -> dict:
    """从磁盘加载近期比赛缓存（所有联赛/球队复用同一文件）"""
    try:
        if os.path.exists(_RECENT_MATCHES_CACHE_FILE):
            with open(_RECENT_MATCHES_CACHE_FILE, "r", encoding="utf-8") as _f:
                _raw = json.load(_f)
            _result = {}
            for _key, _entry in _raw.items():
                try:
                    _df = pd.DataFrame(_entry["data"], columns=_entry["columns"])
                    _result[_key] = _df
                except Exception:
                    continue
            return _result
    except Exception:
        pass
    return {}


def _save_match_disk_cache(cache_key: str, df: pd.DataFrame) -> None:
    """单条写入磁盘缓存（增量更新，不重写整个文件）"""
    try:
        # 读现有缓存
        _existing = {}
        if os.path.exists(_RECENT_MATCHES_CACHE_FILE):
            with open(_RECENT_MATCHES_CACHE_FILE, "r", encoding="utf-8") as _f:
                _existing = json.load(_f)
        # 更新当前键
        if df.empty:
            _existing.pop(cache_key, None)
        else:
            _existing[cache_key] = {
                "columns": df.columns.tolist(),
                "data": df.where(df.notna(), None).values.tolist(),
            }
        # 写回
        with open(_RECENT_MATCHES_CACHE_FILE, "w", encoding="utf-8") as _f:
            json.dump(_existing, _f, ensure_ascii=False, default=str)
    except Exception:
        pass

# OpenLigaDB 赛果缓存 {(league): (list_of_dicts, timestamp)}
_OPENLIGA_MATCHES_CACHE: dict = {}

def _fetch_openligadb_matches_inner(league: str, max_weeks: int = 8, include_future: bool = False) -> pd.DataFrame:
    """从 OpenLigaDB 获取某联赛的完赛结果（带缓存，重复调用不重复请求）

    缓存键 = league，有效期 300 秒（5 分钟）。
    include_future=True：包含未来未开始的比赛（用于赛程校验）
    """
    # 检查缓存
    now_ts = time()
    cached_entry = _OPENLIGA_MATCHES_CACHE.get(league)
    if cached_entry is not None:
        cached_df, cached_at = cached_entry
        if now_ts - cached_at < 300:
            return cached_df

    import urllib.request, json, ssl

    # OpenLigaDB 联赛代码映射
    OLG_LEAGUE = {
        "wm26": "wm26", "WC": "wm26",
        "bl1": "bl1", "epl": "bl1",
        "kleague1": "kleague1", "kleague2": "kleague2",
        "jleague1": "jleague1", "jleague2": "jleague2",
        "allsvenskan": "allsvenskan", "sportsdb": "allsvenskan",
        "eliteserien": "eliteserien",
        "championship": "championship",
        "bundesliga2": "bundesliga2",
        "ligue2": "ligue2",
        "laliga2": "laliga2",
        "serieb": "serieb",
        "primeira": "primeira",
        "proleague": "proleague",
        "scottish": "scottish",
        "eredivisie": "eredivisie",
        "aleague": "aleague",
        "mls": "mls",
        "brasileirao": "brasileirao",
        "ligamx": "ligamx",
        "kleague1": "kleague1", "kleague2": "kleague2",
        "jleague1": "jleague1", "jleague2": "jleague2",
        "veikkausliiga": "veikkausliiga",
    }
    olg_league = OLG_LEAGUE.get(league)
    if not olg_league:
        return pd.DataFrame()

    ctx = ssl.create_default_context()
    url = f"https://api.openligadb.de/getmatchdata/{olg_league}/2026"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=8) as r:
            all_matches = json.loads(r.read().decode("utf-8"))
    except Exception:
        return pd.DataFrame()

    rows = []
    for m in all_matches:
        t1 = m["team1"]["teamName"]
        t2 = m["team2"]["teamName"]
        results = m.get("matchResults", [])
        ft = next((r for r in results if r.get("resultTypeID") == 2), None)
        try:
            match_date = datetime.strptime(m.get("matchDateTime", "")[:10], "%Y-%m-%d")
        except Exception:
            match_date = datetime.now()

        if ft:
            # 已完赛
            rows.append({
                "home_team": t1, "away_team": t2,
                "home_score_normaltime": int(ft["pointsTeam1"]),
                "away_score_normaltime": int(ft["pointsTeam2"]),
                "status": "Ended",
                "start_timestamp": match_date.timestamp(),
                "match_date": match_date,
                "_source": "openligadb",
            })
        elif include_future:
            # 未来比赛（无比分，仅作赛程校验用）
            rows.append({
                "home_team": t1, "away_team": t2,
                "home_score_normaltime": 0, "away_score_normaltime": 0,
                "status": "Scheduled",
                "start_timestamp": match_date.timestamp(),
                "match_date": match_date,
                "_source": "openligadb",
            })
    if not rows:
        _OPENLIGA_MATCHES_CACHE[league] = (pd.DataFrame(), now_ts)
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values("start_timestamp", ascending=False)
    _OPENLIGA_MATCHES_CACHE[league] = (df, time())
    return df


# ============================================================
# 队名模糊回退 — 当 TEAM_DE 未覆盖时从 OpenLigaDB 数据自动发现
# ============================================================

def _fuzzy_discover_team(team_name: str, df: pd.DataFrame) -> Optional[str]:
    """模糊回退：当 TEAM_DE/TEAM_EN 无覆盖时，从 OpenLigaDB 数据中扫描匹配

    策略：
      1. 用归一化后的输入直接匹配
      2. 用 TEAM_EN 的英文名匹配德文名（如 Cameroon 匹配 Kamerun）
      3. 用归一化截断匹配（前 4 字符）
    """
    norm_input = _norm(team_name)

    # 收集该联赛所有出现过的队名
    all_teams = set()
    for _, row in df.iterrows():
        all_teams.add(row.get("home_team", ""))
        all_teams.add(row.get("away_team", ""))

    # 策略1: 归一化精确匹配
    for t in all_teams:
        if norm_input == _norm(t):
            return t

    # 策略2: 用英文名匹配德文名（vowel 模糊化：camerun ≈ kamerun）
    en = TEAM_EN.get(team_name)
    if en:
        norm_en = _norm(en)
        for t in all_teams:
            norm_t = _norm(t)
            if norm_en == norm_t:
                return t
            # 音近模糊化：c/ck/k互换, ae/ä≈a, oe/ö≈o, ue/ü≈u, sz/ß≈ss
            def _blur(s):
                return (s.replace('ck','k').replace('c','k')
                        .replace('ss','s').replace('sz','s')
                        .replace('ae','a').replace('oe','o').replace('ue','u')
                        .replace('ä','a').replace('ö','o').replace('ü','u')
                        .replace('ß','ss'))
            if _blur(norm_en) == _blur(norm_t):
                return t
            # 长度≥4时子串匹配（防过短误匹配）
            if len(norm_en) >= 4 and (norm_en in norm_t or norm_t in norm_en):
                return t

    # 策略3: 归一化截断前 4 字符（对付 ARG/EGY→ARG 类组合队名）
    if len(norm_input) >= 4:
        prefix = norm_input[:4]
        for t in all_teams:
            if _norm(t).startswith(prefix):
                return t

    return None


def _enrich_match_names(team_name: str, df: pd.DataFrame) -> set:
    """构建队名匹配集，末尾加模糊回退"""
    names = set()
    key = _norm(team_name)
    de = TEAM_DE.get(team_name)
    if de:
        names.add(_norm(de))
    en = TEAM_EN.get(team_name)
    if en:
        names.add(_norm(en))
    alias = _ALIAS.get(key)
    if alias:
        names.add(alias)
    names.add(key)
    # 模糊回退：当精确映射未覆盖时从数据中自动发现
    if df is not None:
        fuzzy = _fuzzy_discover_team(team_name, df)
        if fuzzy:
            names.add(_norm(fuzzy))
    return names


# ============================================================
# 数据源覆盖检查 — 防止为无数据的赛事生成预测
# ============================================================

SUPPORTED_DATA_SOURCES = {"datafc", "openligadb"}

def has_data_source(league: str) -> tuple:
    """检查联赛是否有至少一个数据源覆盖

    Returns:
        (bool, str): (是否有数据源, 详情)
    """
    cfg = LEAGUE_TOURNAMENT.get(league)
    if not cfg:
        return False, f"联赛 {league} 未在 LEAGUE_TOURNAMENT 中配置"

    # 所有赛事类型优先尝试 datafc (Sofascore)，OpenLigaDB 作为回退
    return True, "datafc (Sofascore) + OpenLigaDB 回退"


# ============================================================
# 赛程校验 — 防止为不存在的比赛生成预测
# ============================================================

def is_match_scheduled(home: str, away: str, league: str = "wm26") -> tuple:
    """校验两队赛程：datafc 优先 → OpenLigaDB 回退

    v8.5: 移除 ESPN 回退（datafc 已全覆盖）
    """
    # datafc 优先
    if get_datafc_alive():
        try:
            _df_dfc = get_matches(league, team_name=home)
            if _df_dfc is not None and not _df_dfc.empty:
                _hn = _enrich_match_names(home, _df_dfc)
                _an = _enrich_match_names(away, _df_dfc)
                for _, _r in _df_dfc.iterrows():
                    _ht = _norm(_r.get("home_team", ""))
                    _at = _norm(_r.get("away_team", ""))
                    if (any(n in _ht for n in _hn) and any(n in _at for n in _an)) or                        (any(n in _at for n in _hn) and any(n in _ht for n in _an)):
                        return True, f"✅ datafc 赛程确认: {_r.get('home_team','?')} vs {_r.get('away_team','?')}"
        except Exception:
            pass
    # OpenLigaDB 回退
    df = _fetch_openligadb_matches_inner(league, include_future=True)
    if df.empty:
        return True, "⚠️ 无法获取赛程数据，跳过校验"

    # 构建两队各自的匹配名集合（含模糊回退）
    h_names = _enrich_match_names(home, df)
    a_names = _enrich_match_names(away, df)

    # 遍历所有比赛，检查两队是否作为对手出现
    for _, row in df.iterrows():
        ht = _norm(row.get("home_team", ""))
        at = _norm(row.get("away_team", ""))

        h_in_h = any(n in ht for n in h_names)
        h_in_a = any(n in at for n in h_names)
        a_in_h = any(n in ht for n in a_names)
        a_in_a = any(n in at for n in a_names)

        # 两队同时出现在同一场比赛中，且各占一边
        if (h_in_h and a_in_a) or (h_in_a and a_in_h):
            return True, f"✅ 赛程确认: {row.get('home_team','?')} vs {row.get('away_team','?')}"

    return False, f"❌ 未找到赛程: 「{home} vs {away}」不在 {league} 的 OpenLigaDB 赛程中"


# ============================================================
# 赔率自动补全 — 预测后自动拉 market odds 写入 PnL
# ============================================================

_ODDS_TIMESTAMPS: set = set()  # 用于避免同一次运行重复写 odds 文件


def _save_odds_file(home: str, away: str, odds_data: dict, source: str = "odds-api"):
    """保存带时间戳的 odds_*.json（覆盖同秒文件，不同秒追加新版本）"""
    try:
        _now = datetime.now().strftime("%Y%m%d_%H%M%S")
        _safe_h = home.replace(" ", "").replace("/", "_")
        _safe_a = away.replace(" ", "").replace("/", "_")
        _fname = f"odds_{_safe_h}_{_safe_a}_{_now}.json"
        _fpath = os.path.join(CACHE_DIR, _fname)
        if _fname in _ODDS_TIMESTAMPS:
            return
        _ODDS_TIMESTAMPS.add(_fname)
        with open(_fpath, "w", encoding="utf-8") as _f:
            json.dump(odds_data, _f, ensure_ascii=False, indent=2, default=str)
        # 清理旧缓存：每场比赛保留最新 5 个文件（v8.5）
        _existing = sorted(glob.glob(os.path.join(CACHE_DIR, f"odds_{_safe_h}_{_safe_a}_*.json")))
        for _old_f in _existing[:-5]:
            try:
                os.remove(_old_f)
            except Exception:
                pass
    except Exception:
        pass


def auto_fill_odds(home: str, away: str, league: str, p_final: float,
                    direction: str = "", rating: str = "",
                    odds_only: bool = False) -> dict:
    """预测后自动补赔率：对支持 datafc 的联赛拉取 match odds

    Args:
        home, away: 中文队名
        league: 联赛标识（sportsdb/allsvenskan）
        p_final: 模型概率（0-1）
        direction: 推荐方向
        rating: ⭐评级
        odds_only: True=只查赔率不写 PnL

    Returns:
        {"odds": float or None, "home_odds": float, ...}
    """
    LEAGUES_WITH_DATAFIC = {"sportsdb", "allsvenskan", "eliteserien",
                             "championship", "bundesliga2", "ligue2", "laliga2", "serieb",
                             "aleague", "mls", "brasileirao", "ligamx",
                             "primeira", "proleague", "scottish",
                             "kleague1", "kleague2", "jleague1", "jleague2", "eredivisie",
                             "bl1", "epl", "laliga", "seriea", "ligue1",
                             "csl", "zhongjia", "zhongyi", "saudi", "league1", "league2",
                             "ucl", "uel", "uecl", "facup", "eflcup", "copadelrey", "dfbpokal", "coppaita"}

    cfg = LEAGUE_TOURNAMENT.get(league)
    if not cfg:
        return {"odds": None, "source": "no_config"}
    tid = cfg["tid"]
    sid = cfg.get("sid") or _get_season_id(tid)
    if not sid:
        return {"odds": None, "source": "no_season_id"}

    # 构建匹配名
    h_norm = _norm(home)
    a_norm = _norm(away)
    h_en = _norm(TEAM_EN.get(home, home))
    a_en = _norm(TEAM_EN.get(away, away))

    # 仅 datafc 覆盖的联赛才走 Sofascore 扫描
    if league in LEAGUES_WITH_DATAFIC:
        from datafc import match_data as dfc_match_data
        tour_type = cfg.get("type", "league")

        # 根据赛事类型构建扫描参数
        if tour_type == "uefa":
            scan_plan = []
            for w in range(1, 9):
                scan_plan.append(("uefa", w, "group_stage_week"))
            for stage in ("round_of_16", "quarterfinals", "semifinals", "final"):
                scan_plan.append(("uefa", 1, stage))
        elif tour_type == "knockout":
            scan_plan = [("default", w, None) for w in range(1, 13)]
        else:
            scan_plan = [("default", w, None) for w in range(18, 0, -1)]

        for tt, wk, stage in scan_plan:
            kwargs = {"tournament_id": tid, "season_id": sid, "week_number": wk}
            if tt == "uefa":
                kwargs["tournament_type"] = "uefa"
                kwargs["tournament_stage"] = stage
            df = _call_datafc(dfc_match_data, **kwargs)
            if df is None or df.empty:
                continue

            for idx, row in df.iterrows():
                ht = _norm(str(row.get("home_team", "")))
                at = _norm(str(row.get("away_team", "")))

                h_match = (h_norm in ht or h_en in ht or ht in h_norm or ht in h_en)
                a_match = (a_norm in at or a_en in at or at in a_norm or at in a_en)
                if h_match and a_match:
                    match_row = df.loc[[idx]] if isinstance(idx, int) else df.iloc[[idx]]
                    odds_info = get_odds(match_row)
                    if odds_info and odds_info.get("odds_1x2"):
                        o = odds_info["odds_1x2"]
                        home_odds, draw_odds, away_odds = o.get("home"), o.get("draw"), o.get("away")

                        selected_odds = None
                        if "主" in direction and home_odds:
                            selected_odds = home_odds
                        elif "客" in direction and away_odds:
                            selected_odds = away_odds
                        elif "平" in direction and draw_odds:
                            selected_odds = draw_odds
                        else:
                            selected_odds = home_odds or away_odds

                        if odds_only:
                            asian = odds_info.get("asian_handicap", [])
                            _save_odds_file(home, away, {
                                "home": home, "away": away,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "source": "datafc",
                                "odds_home": home_odds, "odds_draw": draw_odds,
                                "odds_away": away_odds,
                                "asian_handicap": odds_info.get("asian_handicap", []),
                            })
                            return {"odds": selected_odds, "home_odds": home_odds,
                                    "draw_odds": draw_odds, "away_odds": away_odds,
                                    "asian_lines": asian,
                                    "source": "datafc", "week": w}

                        # 写入 PnL 记录
                        try:
                            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
                            from skill.pnl_tracker import add_record
                            add_record(
                                home=home, away=away, p_final=p_final,
                                odds=selected_odds or 0,
                                direction=direction, league=league,
                                confidence=rating,
                                result="pending",
                            )
                            log(f"[auto_fill_odds] 已记录赔率: {selected_odds}")
                        except Exception as e:
                            log(f"[auto_fill_odds] PnL 写入失败: {e}")

                        _save_odds_file(home, away, {
                            "home": home, "away": away,
                            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "source": "datafc",
                            "odds_home": home_odds, "odds_draw": draw_odds,
                            "odds_away": away_odds,
                            "asian_handicap": odds_info.get("asian_handicap", []),
                        })

                        # ── 跨源赔率交叉验证（v8.5） ──
                        try:
                            from skill.fetch_match_data import fetch_yapan_data
                            _yp = fetch_yapan_data(home, away)
                            if _yp and "error" not in _yp:
                                _b365 = _yp.get("bet365", {})
                                _eu = _b365.get("european", {}) or _yp.get("1xbet", {}).get("european", {})
                                _alt_h = float(_eu.get("home", 0)) if _eu.get("home") else 0
                                if _alt_h > 0 and home_odds:
                                    _diff = abs(home_odds - _alt_h) / home_odds
                                    if _diff > 0.15:
                                        log(f"[⚠️ 赔率分歧] datafc={home_odds:.2f} odds-api={_alt_h:.2f} "
                                            f"差异{_diff:.1%}，已取较保守值")
                                        # 取较保守值（较高赔率=较低概率=安全）
                                        selected_odds = max(home_odds, _alt_h)
                        except Exception:
                            pass

                        return {"odds": selected_odds, "home_odds": home_odds,
                                "draw_odds": draw_odds, "away_odds": away_odds,
                                "source": "datafc", "week": w}

    # ── datafc 未找到 → 回退到 odds-api.io（世界杯/杯赛等） ──
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
        from skill.fetch_match_data import fetch_yapan_data
        yp = fetch_yapan_data(home, away)
        if yp and "error" not in yp:
            bet365 = yp.get("bet365", {})
            eu = bet365.get("european", {}) or yp.get("1xbet", {}).get("european", {})
            home_odds = eu.get("home")
            draw_odds = eu.get("draw")
            away_odds = eu.get("away")
            if home_odds:
                # odds-api.io 返回字符串，转 float
                home_odds = float(home_odds)
                draw_odds = float(draw_odds) if draw_odds else None
                away_odds = float(away_odds) if away_odds else None
                log(f"[auto_fill_odds] odds-api.io 赔率: {home_odds}/{draw_odds}/{away_odds}")

                # 保存带时间戳的 odds 文件（含全市场数据）
                try:
                    _ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    if "fetch_time" in yp:
                        _ts = yp.get("fetch_time", _ts)
                    _save_odds_file(home, away, {
                        "home": home, "away": away,
                        "timestamp": _ts,
                        "source": "odds-api",
                        "odds_home": home_odds, "odds_draw": draw_odds,
                        "odds_away": away_odds,
                        "bet365": yp.get("bet365", {}),
                        "1xbet": yp.get("1xbet", {}),
                        "match": yp.get("match", {}),
                    })
                except Exception:
                    pass

                # 写入 PnL 记录（同 datafc 分支逻辑，仅非 odds_only 时）
                if not odds_only:
                    try:
                        from skill.pnl_tracker import add_record
                        selected_odds = home_odds
                        if "主" in direction and home_odds:
                            selected_odds = home_odds
                        elif "客" in direction and away_odds:
                            selected_odds = away_odds
                        elif "平" in direction and draw_odds:
                            selected_odds = draw_odds
                        else:
                            selected_odds = home_odds or away_odds
                        add_record(
                            home=home, away=away, p_final=p_final,
                            odds=selected_odds or 0,
                            direction=direction, league=league,
                            confidence=rating,
                            result="pending",
                        )
                        log(f"[auto_fill_odds] 已记录赔率（odds-api.io）: {selected_odds}")
                    except Exception as e:
                        log(f"[auto_fill_odds] PnL 写入失败（odds-api.io）: {e}")

                # ── 极端赔率标注（低流动性警告 v8.5） ──
                _liquidity_warn = ""
                for _name, _odds in [("主胜", home_odds), ("平局", draw_odds), ("客胜", away_odds)]:
                    if _odds and (_odds > 10.0 or _odds < 1.10):
                        _liquidity_warn = f"⚠️ 低流动性：{_name}@{_odds}"
                        log(f"[auto_fill_odds] {_liquidity_warn}")
                        break

                return {"odds": home_odds, "home_odds": home_odds,
                        "draw_odds": draw_odds, "away_odds": away_odds,
                        "source": "odds-api", "liquidity_warning": _liquidity_warn}
    except Exception as e:
        log(f"[auto_fill_odds] odds-api.io 失败: {e}")

    return {"odds": None, "source": "not_found",
            "detail": f"在 Sofascore 未找到 {home} vs {away}"}


# ============================================================
# 角球模型 — 独立管道，不从进球管线取数据
# ============================================================

def get_team_corner_summary(team_name: str, league: str, max_games: int = 5) -> dict:
    """获取球队近期角球数据（独立于进球管线）

    Returns:
        dict with keys:
          corners_for_90, corners_against_90, matches_played
    """
    # 仅 datafc 覆盖的联赛有角球数据
    LEAGUES_WITH_CORNER = {"allsvenskan", "sportsdb", "eliteserien", "championship",
                            "bl1", "epl", "laliga", "seriea", "ligue1",
                            "eredivisie", "kleague1", "jleague1", "mls", "brasileirao"}
    if league not in LEAGUES_WITH_CORNER:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}
    cfg = LEAGUE_TOURNAMENT.get(league)
    if not cfg:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}
    tid, sid = cfg["tid"], cfg.get("sid") or _get_season_id(tid)
    if not sid:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    from datafc import match_data as dfc_match_data
    from datafc import match_stats_data as dfc_stats

    # 构建队名
    h_norm = _norm(team_name)
    h_en = _norm(TEAM_EN.get(team_name, team_name))

    # 扫描近几周，收集该队的完赛比赛
    team_matches = []
    for w in range(18, 0, -1):
        if len(team_matches) >= max_games:
            break
        df = _call_datafc(dfc_match_data, tournament_id=tid, season_id=sid, week_number=w)
        if df is None or df.empty:
            continue
            continue
        ended = df[df["status"] == "Ended"]
        if ended.empty:
            continue
        for idx, row in ended.iterrows():
            ht = _norm(str(row.get("home_team", "")))
            at = _norm(str(row.get("away_team", "")))
            if h_norm in ht or h_en in ht or ht in h_norm or ht in h_en:
                is_home = (h_norm in ht or h_en in ht or ht in h_norm or ht in h_en)
                team_matches.append((idx, row, is_home))
                if len(team_matches) >= max_games:
                    break

    if not team_matches:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    # 批量取这些比赛的 stats
    match_rows = []
    for idx, row, _ in team_matches:
        match_rows.append(row)
    if not match_rows:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    import pandas as pd
    match_df = pd.DataFrame(match_rows)
    if match_df.empty:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    try:
        stats = dfc_stats(match_df=match_df)
    except Exception:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    if stats is None or stats.empty:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    # 提取角球数据
    ck = stats[stats["stat_name"] == "Corner kicks"]
    if ck.empty:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    # 只取 ALL 时段（非半场）
    ck_all = ck[ck["period"] == "ALL"]
    if ck_all.empty:
        ck_all = ck

    total_cf, total_ca = 0, 0
    n = 0
    for _, r in ck_all.iterrows():
        try:
            hv = float(r["home_team_stat"])
            av = float(r["away_team_stat"])
            # 找到这场比赛对应的 team_matches 项（按 game_id）
            gid = r.get("game_id", "")
            for _, row, is_home in team_matches:
                if str(row.get("game_id", "")) == str(gid):
                    if is_home:
                        total_cf += hv
                        total_ca += av
                    else:
                        total_cf += av
                        total_ca += hv
                    n += 1
                    break
        except (ValueError, TypeError):
            continue

    if n == 0:
        return {"corners_for_90": 5.0, "corners_against_90": 5.0, "matches_played": 0}

    # 贝叶斯收缩（prior=联赛平均角球，v8.5 全局化）
    raw_cf = total_cf / n
    raw_ca = total_ca / n
    _corner_prior = LEAGUE_AVG_CORNER.get(league, LEAGUE_AVG_CORNER["default"])
    prior = 3
    shrunken_cf = (raw_cf * n + _corner_prior * prior) / (n + prior)
    shrunken_ca = (raw_ca * n + _corner_prior * prior) / (n + prior)

    return {
        "corners_for_90": round(shrunken_cf, 2),
        "corners_against_90": round(shrunken_ca, 2),
        "matches_played": n,
    }


def corner_nb_over(lam_h: float, lam_a: float, theta: float = 15, line: float = 9.5, mg: int = 25) -> float:
    """P(总角球 > line) — 独立 NB 模型，theta=15（角球方差小于进球）"""
    from skill.predict import nb_prob
    prob = 0.0
    max_k = mg
    for i in range(max_k + 1):
        pi = nb_prob(i, lam_h, theta)
        for j in range(max_k + 1):
            if i + j > line:
                pj = nb_prob(j, lam_a, theta)
                prob += pi * pj
    return prob


def get_team_recent_matches(team_name: str, league: str, max_games: int = 10) -> pd.DataFrame:
    """获取某队近期比赛（自动选择数据源，带缓存和超时保护）

    策略：
      1. 若 DATAFIC_ALIVE 为 True → 走 Sofascore (datafc)，倒序轮次+提前退出
      2. 若 DATAFIC_ALIVE 为 False → 走 OpenLigaDB 备选通路（稳定可用）
      3. 结果缓存，避免重复请求
    """
    # ── 先查缓存（内存 → 磁盘 → API） ──
    cache_key = f"{league}_{team_name}_{max_games}"
    cached = _RECENT_MATCHES_CACHE.get(cache_key)
    if cached is not None:
        return cached
    # 磁盘缓存
    _disk = _load_match_disk_cache()
    if cache_key in _disk:
        _RECENT_MATCHES_CACHE[cache_key] = _disk[cache_key]
        return _disk[cache_key]

    if get_datafc_alive():
        # ── 主通路：Sofascore (datafc) ──
        cfg = get_league_config(league)
        if not cfg:
            return pd.DataFrame()
        # UEFA/淘汰赛：Sofascore 对欧战赛事覆盖差，但欧战球队同时参加本国联赛
        # 放行 datafc 尝试扫描（能找到最好），找不到时上游调用者会走 OpenLigaDB 回退
        if cfg.get("type") in ("uefa", "knockout"):
            # 直接放行到下面的 datafc 扫描，不做提前返回
            pass
        tid = cfg["tid"]
        sid = cfg.get("sid") or _get_season_id(tid)
        if not sid:
            return pd.DataFrame()

        all_matches = []
        # 获取赛季实际轮次（Sofascore），失败时默认 38 轮
        max_week = 20
        try:
            from datafc import season_rounds_data
            _rdf = _call_datafc(season_rounds_data, tournament_id=tid, season_id=sid)
            if _rdf is not None and not _rdf.empty:
                max_week = int(_rdf['round_number'].max())
        except Exception:
            max_week = 38
        # 杯赛（世界杯等）最多 ~7 个比赛轮次，设上限避免大量空请求
        _is_cup = cfg.get("type") in ("world_cup", "cup")
        if _is_cup and max_week > 10:
            max_week = 10
        # 从最近轮次开始倒序扫描，找到足够场次即退出
        for w in range(max_week, 0, -1):
            if len(all_matches) >= max_games:
                break
            df = _call_datafc(dfc_match_data, tournament_id=tid, season_id=sid, week_number=w)
            if df is None or df.empty:
                continue
            team_df = _find_team_in_matches(df, team_name)
            if not team_df.empty:
                # 只取已完赛的比赛（跳过 "Not started" / "Inplay"）
                if "status" in team_df.columns:
                    team_df = team_df[team_df["status"] == "Ended"]
                if not team_df.empty:
                    all_matches.append(team_df)

        if not all_matches:
            return pd.DataFrame()
        result = pd.concat(all_matches, ignore_index=True)
        if "start_timestamp" in result.columns:
            result = result.sort_values("start_timestamp", ascending=False)
        result = result.head(max_games)
    else:
        # ── 备选通路：OpenLigaDB（稳定，无需 API Key）──
        df = _fetch_openligadb_matches_inner(league, max_weeks=8)
        if df.empty:
            return pd.DataFrame()
        # 匹配球队（双方 _norm 归一化，解决 ü→ue 变音符差异）
        match_names = set()
        team_key = _norm(team_name)
        de = TEAM_DE.get(team_name)
        if de:
            match_names.add(_norm(de))
        en = TEAM_EN.get(team_name)
        if en:
            match_names.add(_norm(en))
        alias_name = _ALIAS.get(team_key)
        if alias_name:
            match_names.add(alias_name)
        match_names.add(team_key)

        def _row_matches(row):
            ht = _norm(row.get("home_team", ""))
            at = _norm(row.get("away_team", ""))
            return any(n in ht or n in at for n in match_names)

        mask = df.apply(_row_matches, axis=1)
        result = df[mask].head(max_games).copy()

    _RECENT_MATCHES_CACHE[cache_key] = result
    if not result.empty:
        _save_match_disk_cache(cache_key, result)  # 持久化到磁盘
    return result


def get_xg_data(match_df: pd.DataFrame) -> pd.DataFrame:
    """获取射门级 xG 数据（逐场获取，包容404错误）

    Returns:
        DataFrame with per-shot xG data
    """
    if match_df.empty:
        return pd.DataFrame()

    # 逐场获取，某场失败不影响其他
    all_shots = []
    for idx in match_df.index:
        single = match_df.loc[[idx]]  # one-row DataFrame
        try:
            shots = dfc_shots_data(match_df=single)
            if not shots.empty:
                all_shots.append(shots)
        except Exception as _ex:
            _gid = "?"
            try:
                _gid = str(single.iloc[0].get("game_id", "?")) if not single.empty else "?"
            except Exception:
                pass
            log(f"[datafc] shots_data 失败: {_ex} (match_id={_gid}) — 跳过该场")
            continue

    if not all_shots:
        return pd.DataFrame()
    return pd.concat(all_shots, ignore_index=True)


def get_team_xg_summary(team_name: str, league: str, max_games: int = 8) -> dict:
    """估算球队的 xG 数据（基于 shots_data 聚合）

    v8.5: 时间指数衰减加权 + 对手强度调整

    Args:
        team_name: 球队名（中文）
        league: 联赛代码
        max_games: 参考场次

    Returns:
        dict with keys:
          xG_for_90, xG_against_90, matches_played,
          shots_for_90, shots_against_90, source
    """
    # 1. 获取近期比赛
    matches = get_team_recent_matches(team_name, league, max_games=max_games)
    if matches.empty:
        # v8.6: datafc/OpenLigaDB 都无数据 → 五大联赛尝试 Understat 回退
        if league in ("epl", "laliga", "bl1", "seriea", "ligue1"):
            try:
                from understat_provider import fetch_team_xg
                _us = fetch_team_xg(team_name, league)
                if _us.get("source") == "understat" and _us.get("matches_played", 0) > 0:
                    return {
                        "xG_for_90": _us["xG_for_90"],
                        "xG_against_90": _us["xG_against_90"],
                        "matches_played": _us["matches_played"],
                        "source": "understat",
                        "is_calibrated": True,
                    }
            except Exception:
                pass
        return {"xG_for_90": 0, "xG_against_90": 0, "matches_played": 0,
                "source": "datafc_no_data", "is_calibrated": False}

    # 2. 获取射门数据
    shots = get_xg_data(matches)
    if shots.empty:
        # v8.6: datafc 无 xG → 五大联赛尝试 Understat 回退
        if league in ("epl", "laliga", "bl1", "seriea", "ligue1"):
            try:
                from understat_provider import fetch_team_xg
                _us = fetch_team_xg(team_name, league)
                if _us.get("source") == "understat" and _us.get("matches_played", 0) > 0:
                    return {
                        "xG_for_90": _us["xG_for_90"],
                        "xG_against_90": _us["xG_against_90"],
                        "matches_played": _us["matches_played"],
                        "source": "understat",
                        "is_calibrated": True,
                    }
            except Exception:
                pass
        return _estimate_from_scores(matches, team_name)

    # 3. 构建 match_id → {时间戳, 对手名} 映射（用于权重计算）
    _now_ts = time()
    _HALF_LIFE_DAYS = 14          # 14天半衰期
    _HALF_LIFE_SECS = _HALF_LIFE_DAYS * 86400
    team_en = TEAM_EN.get(team_name, team_name).lower().replace(" ", "")

    _match_info = {}
    for _idx, _row in matches.iterrows():
        _gid = _row.get("game_id")
        _ts = _row.get("start_timestamp", _now_ts)
        if not _ts or _ts == 0:
            _ts = _now_ts
        # 判断本队是主还是客，提取对手名
        _ht = str(_row.get("home_team", "")).lower().replace(" ", "")
        _at = str(_row.get("away_team", "")).lower().replace(" ", "")
        _is_h = team_en in _ht
        _opponent = str(_row.get("away_team", "") if _is_h else _row.get("home_team", ""))
        # 对手 ELO（用于强度调整）
        _opp_elo = get_team_elo(_opponent).get("elo", 1500)
        _match_info[_gid] = {"ts": int(_ts), "opponent_elo": _opp_elo}

    # 4. 按 game_id 分组聚合 xG
    _match_xg = {}  # game_id -> {"xg_for": 0, "xg_against": 0, "shots_for": 0, ...}
    for _, _row in shots.iterrows():
        _gid = _row.get("game_id")
        if _gid not in _match_xg:
            _match_xg[_gid] = {"xg_for": 0.0, "xg_against": 0.0,
                                "shots_for": 0, "shots_against": 0}
        _is_home = _row.get("is_home")
        if _is_home is None:
            _htid = _row.get("home_team_id")
            _tid = _row.get("team_id")
            if _htid is not None and _tid is not None:
                try:
                    _is_home = (int(_htid) == int(_tid))
                except (ValueError, TypeError):
                    _is_home = None
            if _is_home is None:
                continue
        _xg = _row.get("xg", 0)
        if _xg is None or (isinstance(_xg, float) and math.isnan(_xg)):
            _xg = 0.0
        _st = _row.get("shot_type", "")
        if _is_home:
            _match_xg[_gid]["xg_for"] += float(_xg)
            if _st not in ("blocked",):
                _match_xg[_gid]["shots_for"] += 1
        else:
            _match_xg[_gid]["xg_against"] += float(_xg)
            if _st not in ("blocked",):
                _match_xg[_gid]["shots_against"] += 1

    if not _match_xg:
        return _estimate_from_scores(matches, team_name)

    # 5. 加权聚合（时间衰减 × 对手强度）
    _total_w = 0.0
    _wgted_xg_for = 0.0
    _wgted_xg_against = 0.0
    _wgted_shots_for = 0.0
    _wgted_shots_against = 0.0
    _LEAGUE_BASELINE_ELO = 1500

    for _gid, _mxg in _match_xg.items():
        _info = _match_info.get(_gid, {"ts": _now_ts, "opponent_elo": 1500})
        # 时间衰减权重：exp(-days_ago / half_life)
        _days_ago = max(0, (_now_ts - _info["ts"]) / 86400)
        _time_w = math.exp(-_days_ago / _HALF_LIFE_DAYS)
        # 对手强度权重：弱队(ELO低)的进球含金量低→权重降，强队(ELO高)的进球含金量高→权重升
        # 对手防守强度≈ opp_elo / baseline, 我方进攻权重按此缩放
        _opp_w = _info["opponent_elo"] / _LEAGUE_BASELINE_ELO
        _opp_w = max(0.5, min(2.0, _opp_w))  # 钳制在 0.5-2.0
        _w = _time_w * _opp_w
        _total_w += _w
        _wgted_xg_for += _mxg["xg_for"] * _w
        _wgted_xg_against += _mxg["xg_against"] * _w
        _wgted_shots_for += _mxg["shots_for"] * _w
        _wgted_shots_against += _mxg["shots_against"] * _w

    if _total_w <= 0:
        return _estimate_from_scores(matches, team_name)

    _match_count = len(_match_xg)
    _xg_for = round(_wgted_xg_for / _total_w, 2)
    _xg_against = round(_wgted_xg_against / _total_w, 2)

    # v8.6: datafc xG 全为 0 → 五大联赛尝试 Understat 回退
    if _xg_for == 0 and _xg_against == 0 and league in ("epl", "laliga", "bl1", "seriea", "ligue1"):
        try:
            from understat_provider import fetch_team_xg
            _us = fetch_team_xg(team_name, league)
            if _us.get("source") == "understat" and _us.get("matches_played", 0) > 0:
                return {
                    "xG_for_90": _us["xG_for_90"],
                    "xG_against_90": _us["xG_against_90"],
                    "matches_played": _us["matches_played"],
                    "source": "understat",
                    "is_calibrated": True,
                    "_datafc_raw": {"xG_for_90": _xg_for, "xG_against_90": _xg_against},
                }
        except Exception:
            pass

    return {
        "xG_for_90": _xg_for,
        "xG_against_90": round(_wgted_xg_against / _total_w, 2),
        "matches_played": _match_count,
        "shots_for_90": round(_wgted_shots_for / _total_w, 1),
        "shots_against_90": round(_wgted_shots_against / _total_w, 1),
        "source": "datafc_xg",
        "is_calibrated": True,
        "_time_weighted": True,
        "_effective_n": round(_total_w, 1),
    }


def _estimate_from_scores(matches: pd.DataFrame, team_name: str) -> dict:
    """从比分估算 xG（当无射门数据时回退）

    v8.5: 时间指数衰减加权 + 对手强度调整
    """
    team_en = TEAM_EN.get(team_name, team_name)
    team_lower = team_en.lower().replace(" ", "")
    _now_ts = time()
    _HALF_LIFE_DAYS = 14
    _LEAGUE_BASELINE_ELO = 1500

    _total_w = 0.0
    _wgted_gf = 0.0
    _wgted_ga = 0.0
    _count = 0

    for _, _row in matches.iterrows():
        _ht = str(_row.get("home_team", "")).lower().replace(" ", "")
        _at = str(_row.get("away_team", "")).lower().replace(" ", "")
        _hs = _row.get("home_score_normaltime") or _row.get("home_score_display") or 0
        _as_ = _row.get("away_score_normaltime") or _row.get("away_score_display") or 0
        try:
            _hs, _as_ = int(_hs), int(_as_)
        except (ValueError, TypeError):
            continue

        # 判断本队角色，提取对手
        _is_h = team_lower in _ht
        if not _is_h and team_lower not in _at:
            continue
        _opponent = str(_row.get("away_team", "") if _is_h else _row.get("home_team", ""))
        _gf = _hs if _is_h else _as_
        _ga = _as_ if _is_h else _hs

        # 时间衰减
        _ts = _row.get("start_timestamp", _now_ts)
        if not _ts or _ts == 0:
            _ts = _now_ts
        _days_ago = max(0, (_now_ts - int(_ts)) / 86400)
        _time_w = math.exp(-_days_ago / _HALF_LIFE_DAYS)

        # 对手强度调整
        _opp_elo = get_team_elo(_opponent).get("elo", 1500)
        _opp_w = _opp_elo / _LEAGUE_BASELINE_ELO
        _opp_w = max(0.5, min(2.0, _opp_w))

        _w = _time_w * _opp_w
        _total_w += _w
        _wgted_gf += _gf * _w
        _wgted_ga += _ga * _w
        _count += 1

    if _count == 0 or _total_w <= 0:
        return {"xG_for_90": 0, "xG_against_90": 0,
                "matches_played": 0, "source": "datafc_no_matches"}

    return {
        "xG_for_90": round(_wgted_gf / _total_w, 2),
        "xG_against_90": round(_wgted_ga / _total_w, 2),
        "matches_played": _count,
        "source": "datafc_goals_fallback",
        "is_calibrated": False,
        "_time_weighted": True,
        "_effective_n": round(_total_w, 1),
    }


def get_odds(match_df: pd.DataFrame, decimal: bool = True) -> dict:
    """获取比赛赔率（含欧赔/亚盘/大小球/角球/罚牌/BTTS）

    Args:
        match_df: 比赛 DataFrame（1行）
        decimal: True=返回十进制赔率, False=英式分数

    Returns:
        dict with keys:
          odds_1x2: {home, draw, away}
          asian_handicap: [{hdp, home_odds, away_odds}, ...]
          over_under: [{line, over_odds, under_odds}, ...]
          btts: {yes_odds, no_odds}
          corners: [{over_odds, under_odds}, ...]
          cards: [{over_odds, under_odds}, ...]
    """
    if match_df.empty:
        return {}

    try:
        odds_df = dfc_match_odds(match_df=match_df)
    except Exception as e:
        log(f"[datafc] match_odds 失败: {e}")
        return {}

    if odds_df.empty:
        return {}

    result = {}

    # 解析不同市场
    full_time = odds_df[odds_df["market_name"] == "Full time"]
    if not full_time.empty:
        odds_1x2 = {}
        for _, row in full_time.iterrows():
            choice = row.get("choice_name", "")
            val = row.get("current_fractional_value", "")
            dec = _fraction_to_decimal(val) if decimal else val
            if choice == "1":
                odds_1x2["home"] = dec
            elif choice == "X":
                odds_1x2["draw"] = dec
            elif choice == "2":
                odds_1x2["away"] = dec
        if odds_1x2:
            result["odds_1x2"] = odds_1x2

    # 亚洲盘口
    ah = odds_df[odds_df["market_name"] == "Asian handicap"]
    if not ah.empty:
        asian_lines = []
        for _, row in ah.iterrows():
            choice = row.get("choice_name", "")
            val = row.get("current_fractional_value", "")
            dec = _fraction_to_decimal(val) if decimal else val
            # choice 格式: "(-1.25) Mexico" 或 "(1.25) South Africa"
            hdp_match = re.match(r'\((-?[\d.]+)\)\s+(.+)', str(choice))
            if hdp_match:
                hdp = float(hdp_match.group(1))
                team = hdp_match.group(2)
                asian_lines.append({
                    "hdp": hdp, "team": team, "odds": dec
                })
        if asian_lines:
            result["asian_handicap"] = asian_lines

    # 大小球 (Match goals)
    mg = odds_df[odds_df["market_name"] == "Match goals"]
    if not mg.empty:
        ou_lines = {}
        for _, row in mg.iterrows():
            choice = str(row.get("choice_name", ""))
            val = row.get("current_fractional_value", "")
            dec = _fraction_to_decimal(val) if decimal else val
            # choice 格式: "Over 2.5" 或 "Under 2.5"
            m = re.match(r'(Over|Under)\s+([\d.]+)', choice)
            if m:
                direction = m.group(1).lower()
                line = float(m.group(2))
                if line not in ou_lines:
                    ou_lines[line] = {}
                ou_lines[line][direction] = dec
        result["over_under"] = [
            {"line": k, "over": v.get("over"), "under": v.get("under")}
            for k, v in sorted(ou_lines.items())
        ]

    # BTTS
    btts = odds_df[odds_df["market_name"] == "Both teams to score"]
    if not btts.empty:
        btts_data = {}
        for _, row in btts.iterrows():
            choice = str(row.get("choice_name", ""))
            val = row.get("current_fractional_value", "")
            dec = _fraction_to_decimal(val) if decimal else val
            if choice.lower() == "yes":
                btts_data["yes_odds"] = dec
            elif choice.lower() == "no":
                btts_data["no_odds"] = dec
        if btts_data:
            result["btts"] = btts_data

    # 角球
    corners = odds_df[odds_df["market_name"] == "Corners 2-Way"]
    if not corners.empty:
        corner_odds = {}
        for _, row in corners.iterrows():
            choice = str(row.get("choice_name", ""))
            val = row.get("current_fractional_value", "")
            dec = _fraction_to_decimal(val) if decimal else val
            if choice.lower() == "over":
                corner_odds["over_odds"] = dec
            elif choice.lower() == "under":
                corner_odds["under_odds"] = dec
        if corner_odds:
            result["corners"] = corner_odds

    # 罚牌
    cards = odds_df[odds_df["market_name"] == "Cards in match"]
    if not cards.empty:
        card_odds = {}
        for _, row in cards.iterrows():
            choice = str(row.get("choice_name", ""))
            val = row.get("current_fractional_value", "")
            dec = _fraction_to_decimal(val) if decimal else val
            if choice.lower() == "over":
                card_odds["over_odds"] = dec
            elif choice.lower() == "under":
                card_odds["under_odds"] = dec
        if card_odds:
            result["cards"] = card_odds

    return result


def get_standings(league: str) -> list:
    """获取联赛积分榜

    Returns:
        list of dicts: {
          position, team, played, wins, draws, losses,
          goals_for, goals_against, points, form
        }
    """
    cfg = get_league_config(league)
    if not cfg:
        return []

    tid = cfg["tid"]
    sid = cfg.get("sid") or _get_season_id(tid)
    if not sid:
        return []

    try:
        sd = dfc_standings(tournament_id=tid, season_id=sid)
    except Exception as e:
        log(f"[datafc] standings 失败: {e}")
        return []

    if sd.empty:
        return []

    standings = []
    for _, row in sd.iterrows():
        standings.append({
            "position": row.get("position"),
            "team": row.get("team_name"),
            "played": row.get("matches"),
            "wins": row.get("wins"),
            "draws": row.get("draws"),
            "losses": row.get("losses"),
            "goals_for": row.get("scores_for"),
            "goals_against": row.get("scores_against"),
            "points": row.get("points"),
            "form": row.get("form"),
        })
    return standings


def get_lineups(match_df: pd.DataFrame) -> dict:
    """获取首发阵容"""
    if match_df.empty:
        return {}
    try:
        lu = dfc_lineups(match_df=match_df)
        if not lu.empty:
            # 分组: team=home/away, player_name, stat_name, stat_value
            home = lu[lu["team"] == "home"]["player_name"].unique().tolist()
            away = lu[lu["team"] == "away"]["player_name"].unique().tolist()
            return {"home_lineup": home, "away_lineup": away}
    except Exception:
        pass
    return {}


def get_formations(match_df: pd.DataFrame) -> dict:
    """获取阵型"""
    if match_df.empty:
        return {}
    try:
        fm = dfc_formations(match_df=match_df)
        if not fm.empty:
            result = {}
            for _, row in fm.iterrows():
                team_side = row.get("team")
                formation = row.get("formation")
                if team_side and formation:
                    result[f"{team_side}_formation"] = formation
            return result
    except Exception:
        pass
    return {}


def get_pregame_form(match_df: pd.DataFrame) -> dict:
    """获取赛前近况"""
    if match_df.empty:
        return {}
    try:
        pf = dfc_pregame_form(match_df=match_df)
        if not pf.empty:
            result = {}
            for _, row in pf.iterrows():
                team_side = row.get("team")
                if team_side:
                    result[f"{team_side}_last5"] = row.get("last_5")
                    result[f"{team_side}_avg_rating"] = row.get("avg_rating")
                    result[f"{team_side}_league_pos"] = row.get("position")
            return result
    except Exception:
        pass
    return {}


def get_match_details(match_df: pd.DataFrame) -> dict:
    """获取裁判/场地信息"""
    if match_df.empty:
        return {}
    try:
        md = dfc_match_details(match_df=match_df)
        if not md.empty:
            details = {}
            if "referee_name" in md.columns:
                details["referee"] = md.iloc[0].get("referee_name")
            if "venue_name" in md.columns:
                details["venue"] = md.iloc[0].get("venue_name")
            if "attendance" in md.columns:
                details["attendance"] = md.iloc[0].get("attendance")
            return details
    except Exception:
        pass
    return {}


def get_h2h(match_df: pd.DataFrame) -> dict:
    """获取交锋记录统计"""
    if match_df.empty:
        return {}
    try:
        h2h = dfc_match_h2h(match_df=match_df)
        if not h2h.empty:
            row = h2h.iloc[0]
            return {
                "home_wins": int(row.get("home_wins", 0)),
                "away_wins": int(row.get("away_wins", 0)),
                "draws": int(row.get("draws", 0)),
                "total": int(row.get("home_wins", 0)) + int(row.get("away_wins", 0)) + int(row.get("draws", 0)),
            }
    except Exception:
        pass
    return {}


# ============================================================
# 赛后结果同步
# ============================================================

def sync_results_to_file(league: str = "wm26", week_numbers: list = None) -> int:
    """从 datafc 获取已完赛比赛 → 写入 auto_results.json

    Returns: 同步的比赛数
    """
    auto_path = os.path.join(CACHE_DIR, "auto_results.json")

    # 读取已有的
    existing = []
    if os.path.exists(auto_path):
        with open(auto_path, "r", encoding="utf-8") as f:
            try:
                existing = json.load(f)
            except:
                existing = []

    existing_ids = {r.get("game_id") for r in existing if r.get("game_id")}

    cfg = get_league_config(league)
    if not cfg:
        return 0

    tid = cfg["tid"]
    sid = cfg.get("sid") or _get_season_id(tid)
    if not sid:
        return 0

    new_results = []
    weeks = week_numbers or list(range(1, 20))

    for w in weeks:
        df = _call_datafc(dfc_match_data, tournament_id=tid, season_id=sid, week_number=w)
        if df is None or df.empty:
            continue

        finished = df[df["status"] == "Ended"]
        for _, row in finished.iterrows():
            gid = row.get("game_id")
            if gid in existing_ids:
                continue

            hs = (row.get("home_score_normaltime") or row.get("home_score_display") or 0)
            as_ = (row.get("away_score_normaltime") or row.get("away_score_display") or 0)
            try:
                hs, as_ = int(hs), int(as_)
            except (ValueError, TypeError):
                hs, as_ = 0, 0

            result = {
                "game_id": gid,
                "home_cn": row.get("home_team", ""),
                "away_cn": row.get("away_team", ""),
                "score_ft": f"{hs}-{as_}",
                "status": "FINISHED",
                "week": w,
                "tournament": row.get("tournament", ""),
            }
            new_results.append(result)
            existing_ids.add(gid)

    if new_results:
        all_results = new_results + existing
        with open(auto_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        log(f"[datafc] 同步 {len(new_results)} 场比赛结果到 {auto_path}")

    return len(new_results)


# ============================================================
# 综合球队数据获取（替代 xg_estimator 的 estimate_xg）
# ============================================================

def estimate_team_strength(team_name: str, league: str, max_games: int = 10) -> dict:
    """估算球队攻防强度（替代 xg_estimator.estimate_xg）

    Returns:
        dict with keys:
          xG_for_90, xG_against_90, matches_played, source, is_calibrated
          home_attack, home_defense (L1评分 1-10)
          form_rating (近期状态评分)
    """
    # ── 磁盘缓存检查 ──
    _cache_key = f"strength_{league}_{team_name}_{max_games}"
    if get_datafc_alive():
        try:
            if os.path.exists(_STRENGTH_CACHE_FILE):
                with open(_STRENGTH_CACHE_FILE, "r", encoding="utf-8") as _f:
                    _all = json.load(_f)
                if _cache_key in _all:
                    return _all[_cache_key]
        except Exception:
            pass

    # 1. 从 datafc 获取 xG
    xg = get_team_xg_summary(team_name, league, max_games=max_games)

    # 1b. 自动检测联赛：当当前联赛无数据时用球队名反查正确赛事
    if xg.get("matches_played", 0) == 0:
        detected = detect_team_league(team_name, fallback_league=league)
        if detected != league:
            log(f"[datafc] ⚠️ {team_name} 在联赛 {league} 无数据，自动检测到 {detected}，重试")
            xg = get_team_xg_summary(team_name, detected, max_games=max_games)
            if xg.get("matches_played", 0) > 0:
                league = detected  # 后续逻辑用新联赛

    # 2. 联赛平均（全局 LEAGUE_XG_AVG，datafc 可覆盖）
    avg_xg = LEAGUE_XG_AVG.get(league, LEAGUE_XG_AVG["default"])

    # 3. ELO 驱动的大 λ差调整
    # 以国家队平均 ELO(≈1850) 为锚，每偏离 100 分 → λ 偏移 ±0.20 球
    # 攻防双向偏移：进攻加分、防守减分
    # 西班牙(2159) vs 佛得角(1619) → P_home 从 55% → ~80%
    elo_data = get_team_elo(team_name)
    team_elo = elo_data.get("elo", 1500)
    avg_elo = get_league_avg_elo(league)
    elo_adjust = ((team_elo - avg_elo) / 100) * ELO_ADJUST_FACTOR
    xg_for_raw = xg.get("xG_for_90", avg_xg)
    xg_against_raw = xg.get("xG_against_90", avg_xg)
    # NaN 保护：无效数据替换为联赛均值
    if xg_for_raw is None or (isinstance(xg_for_raw, float) and math.isnan(xg_for_raw)):
        xg_for_raw = avg_xg
    if xg_against_raw is None or (isinstance(xg_against_raw, float) and math.isnan(xg_against_raw)):
        xg_against_raw = avg_xg
    xg_for_adj = xg_for_raw + elo_adjust
    xg_against_adj = xg_against_raw - elo_adjust
    # 钳制最小值防止负值
    xg_for = max(0.1, xg_for_adj)
    xg_against = max(0.1, xg_against_adj)

    def score_from_xg(value, avg, higher_is_better=True):
        """映射到 1-10 分（tanh 饱和曲线，防止顶级球队封顶）"""
        ratio = value / avg if avg > 0 else 1.0
        if higher_is_better:
            score = 5 + 5 * math.tanh(0.8 * (ratio - 1.0))
        else:
            score = 5 + 5 * math.tanh(0.8 * (1.0 - ratio))
        return max(1, min(10, round(score, 1)))

    xg["home_attack"] = score_from_xg(xg_for, avg_xg, higher_is_better=True)
    xg["home_defense"] = score_from_xg(xg_against, avg_xg, higher_is_better=False)

    # 4. 近期状态评分
    matches = get_team_recent_matches(team_name, league, max_games=max_games)
    if not matches.empty:
        team_en = TEAM_EN.get(team_name, team_name)
        total_pts = 0
        total_m = 0
        team_lower = team_en.lower().replace(" ", "")
        for _, row in matches.iterrows():
            ht = str(row.get("home_team", "")).lower().replace(" ", "")
            at = str(row.get("away_team", "")).lower().replace(" ", "")
            hs = row.get("home_score_normaltime") or row.get("home_score_display") or 0
            as_ = row.get("away_score_normaltime") or row.get("away_score_display") or 0
            try:
                hs, as_ = int(hs), int(as_)
            except (ValueError, TypeError):
                continue
            if team_lower in ht:
                if hs > as_: total_pts += 3
                elif hs == as_: total_pts += 1
            elif team_lower in at:
                if as_ > hs: total_pts += 3
                elif as_ == hs: total_pts += 1
            else:
                continue
            total_m += 1
        if total_m > 0:
            xg["form_rating"] = round(total_pts / total_m, 2)
        else:
            xg["form_rating"] = 1.5
    else:
        xg["form_rating"] = 1.5

    # ── 写入磁盘缓存（仅 datafc 路径，含 NaN 保护） ──
    if get_datafc_alive():
        try:
            # 丢弃无效数据：NaN、matches_played=0 不缓存
            _xg_for = xg.get("xG_for_90")
            if _xg_for is None or (isinstance(_xg_for, float) and math.isnan(_xg_for)):
                pass
            elif xg.get("matches_played", 0) == 0:
                pass
            else:
                _existing = {}
                if os.path.exists(_STRENGTH_CACHE_FILE):
                    with open(_STRENGTH_CACHE_FILE, "r", encoding="utf-8") as _f:
                        _existing = json.load(_f)
                _existing[_cache_key] = xg
                with open(_STRENGTH_CACHE_FILE, "w", encoding="utf-8") as _f:
                    json.dump(_existing, _f, ensure_ascii=False, indent=2, default=str)
        except Exception:
            pass

    return xg


def estimate_xg_from_openligadb(team_name: str, league: str = "wm26") -> dict:
    """从 OpenLigaDB 比分估算 xG 和 L1 评分（复用共享缓存，零重复网络请求）

    替代 datafc/SofaScore 不可用时的 xG 获取路径。
    与 _fetch_openligadb_matches_inner 共享 API 数据缓存，避免重复请求。

    Returns:
        dict with keys: xG_for_90, xG_against_90, matches_played, source,
                        home_attack, home_defense, form_rating, is_calibrated
    """
    avg_xg = LEAGUE_XG_AVG.get(league, LEAGUE_XG_AVG["default"])

    def score_from_xg(value, avg, higher_is_better=True):
        """映射到 1-10 分（tanh 饱和曲线，防止顶级球队封顶）"""
        ratio = value / avg if avg > 0 else 1.0
        if higher_is_better:
            score = 5 + 5 * math.tanh(0.8 * (ratio - 1.0))
        else:
            score = 5 + 5 * math.tanh(0.8 * (1.0 - ratio))
        return max(1, min(10, round(score, 1)))

    # 复用共享缓存的数据（避免重复的 HTTP 请求）
    df = _fetch_openligadb_matches_inner(league)
    if df.empty:
        return {"xG_for_90": avg_xg, "xG_against_90": avg_xg, "matches_played": 0,
                "source": "openligadb_no_data", "is_calibrated": False,
                "home_attack": 5.0, "home_defense": 5.0, "form_rating": 1.5,
                "attack_strength": 1.0, "defense_strength": 1.0, "league_avg": avg_xg}

    # 构建队名匹配集（中文→TEAM_DE / 英文→_ALIAS / 原始输入 + 模糊回退）
    match_names = _enrich_match_names(team_name, df)

    # 筛选该队比赛（双方都 _norm 归一化，解决 ü→ue 类变音符差异）
    team_games = []
    for _, row in df.iterrows():
        ht = _norm(row.get("home_team", ""))
        at = _norm(row.get("away_team", ""))
        if not any(n in ht or n in at for n in match_names):
            continue
        is_home = any(n in ht for n in match_names)
        team_games.append({
            "home": row["home_team"], "away": row["away_team"],
            "is_home": is_home,
            "gf": int(row["home_score_normaltime"]) if is_home else int(row["away_score_normaltime"]),
            "ga": int(row["away_score_normaltime"]) if is_home else int(row["home_score_normaltime"]),
        })

        if not team_games:
            return {"xG_for_90": avg_xg, "xG_against_90": avg_xg, "matches_played": 0,
                    "source": "openligadb_no_data", "is_calibrated": False, "home_attack": 5.0, "home_defense": 5.0, "form_rating": 1.5, "attack_strength": 1.0, "defense_strength": 1.0, "league_avg": 1.4}

    # 计算场均进/失
    total_gf, total_ga, total_pts = 0, 0, 0
    for g in team_games:
        total_gf += g["gf"]
        total_ga += g["ga"]
        if g["gf"] > g["ga"]:
            total_pts += 3
        elif g["gf"] == g["ga"]:
            total_pts += 1

    n = len(team_games)
    raw_xg_for = round(total_gf / n, 2) if n else avg_xg
    raw_xg_against = round(total_ga / n, 2) if n else avg_xg
    # ELO 驱动的大 λ差调整
    elo_data = get_team_elo(team_name)
    team_elo = elo_data.get("elo", 1500)
    avg_elo = get_league_avg_elo(league)
    elo_adjust = ((team_elo - avg_elo) / 100) * ELO_ADJUST_FACTOR

    # 贝叶斯收缩：小样本下向联赛均值回归（实际进球方差是 xG 的 3-5 倍）
    prior_matches = 3
    attack_shrunken = (raw_xg_for * n + avg_xg * prior_matches) / (n + prior_matches) if n else raw_xg_for
    defense_shrunken = (raw_xg_against * n + avg_xg * prior_matches) / (n + prior_matches) if n else raw_xg_against

    xg_for = max(0.1, attack_shrunken + elo_adjust)
    xg_against = max(0.1, defense_shrunken - elo_adjust)
    form_rating = round(total_pts / n, 2) if n else 1.5

    league_avg_for_poisson = LEAGUE_XG_AVG.get(league, 1.40)
    attack_strength = round(xg_for / league_avg_for_poisson, 3) if league_avg_for_poisson > 0 else 1.0
    defense_strength = round(xg_against / league_avg_for_poisson, 3) if league_avg_for_poisson > 0 else 1.0

    return {
        "xG_for_90": xg_for,
        "xG_against_90": xg_against,
        "matches_played": n,
        "source": "openligadb",
        "is_calibrated": False,
        "home_attack": score_from_xg(xg_for, avg_xg, higher_is_better=True),
        "home_defense": score_from_xg(xg_against, avg_xg, higher_is_better=False),
        "form_rating": form_rating,
        "attack_strength": attack_strength,
        "defense_strength": defense_strength,
        "league_avg": round(league_avg_for_poisson, 3),
    }


# ============================================================
# 七维评分系统（统一评分引擎 L1 基础层）
# ============================================================

def compute_7dim_scores(home: str, away: str, league: str = "wm26") -> dict:
    """计算两队六维评分（1-10），用于 L1 → P_base

    六维及权重（v8.5，X因素已移除）：
      ① 进攻能力    22%
      ② 防守稳固性   22%
      ③ 中场控制力   18%
      ④ 大赛经验    18%
      ⑤ 战术适配度   15%
      ⑥ 体能/状态    5%

    Returns:
        dict with keys:
          home_进攻, home_防守, home_中场, home_经验, home_战术, home_状态,
          away_同理, 以及 home_total, away_total
    """
    avg_xg = LEAGUE_XG_AVG.get(league, LEAGUE_XG_AVG["default"])

    def _score_from_ratio(value, avg, higher_is_better=True):
        """将实际值/平均值的比率映射到 1-10 分（tanh 饱和曲线，防止顶级球队封顶）"""
        ratio = value / avg if avg > 0 else 1.0
        if higher_is_better:
            s = 5 + 5 * math.tanh(0.8 * (ratio - 1.0))
        else:
            s = 5 + 5 * math.tanh(0.8 * (1.0 - ratio))
        return max(1, min(10, round(s, 1)))

    # ── 获取两队基础数据（datafc → OpenLigaDB 双源回退） ──
    xg_h = estimate_team_strength(home, league)
    if xg_h.get("matches_played", 0) == 0:
        xg_h = estimate_xg_from_openligadb(home, league)
    xg_a = estimate_team_strength(away, league)
    if xg_a.get("matches_played", 0) == 0:
        xg_a = estimate_xg_from_openligadb(away, league)
    elo_h = get_team_elo(home).get("elo", 1500)
    elo_a = get_team_elo(away).get("elo", 1500)
    rank_h = get_team_elo(home).get("rank", 99)
    rank_a = get_team_elo(away).get("rank", 99)

    # 近期比赛（用于状态评分）
    matches_h = get_team_recent_matches(home, league, max_games=6)
    matches_a = get_team_recent_matches(away, league, max_games=6)

    # λ (预期进球)
    lam_h = xg_h.get("xG_for_90", avg_xg)
    lam_a = xg_a.get("xG_for_90", avg_xg)

    # ═══════════════════════════════════════════════════════════
    # ① 进攻能力（20%）— 基于 xG_for/90
    # ═══════════════════════════════════════════════════════════
    if lam_h is None or (isinstance(lam_h, float) and math.isnan(lam_h)):
        lam_h = avg_xg
    if lam_a is None or (isinstance(lam_a, float) and math.isnan(lam_a)):
        lam_a = avg_xg
    att_h = _score_from_ratio(lam_h, avg_xg, higher_is_better=True)
    att_a = _score_from_ratio(lam_a, avg_xg, higher_is_better=True)

    # ═══════════════════════════════════════════════════════════
    # ② 防守稳固性（20%）— 基于 xG_against/90
    # ═══════════════════════════════════════════════════════════
    _raw_def_h = xg_h.get("xG_against_90", avg_xg)
    _raw_def_a = xg_a.get("xG_against_90", avg_xg)
    if _raw_def_h is None or (isinstance(_raw_def_h, float) and math.isnan(_raw_def_h)):
        _raw_def_h = avg_xg
    if _raw_def_a is None or (isinstance(_raw_def_a, float) and math.isnan(_raw_def_a)):
        _raw_def_a = avg_xg
    def_rating_h = _score_from_ratio(_raw_def_h, avg_xg, higher_is_better=False)
    def_rating_a = _score_from_ratio(_raw_def_a, avg_xg, higher_is_better=False)

    # ═══════════════════════════════════════════════════════════
    # ③ 中场控制力（15%）— 基于攻防综合 + ELO 修正
    #    进攻强+防守稳=控制力强。用 att_strength/def_strength 比率
    #    加上 ELO 水平修正（高 ELO 球队通常控球更好）
    # ═══════════════════════════════════════════════════════════
    att_str_h = xg_h.get("attack_strength", 1.0)
    def_str_h = xg_h.get("defense_strength", 1.0)
    att_str_a = xg_a.get("attack_strength", 1.0)
    def_str_a = xg_a.get("defense_strength", 1.0)

    # 中场控制 ≈ 攻防压制比 × ELO 水平，tanh 饱和映射防止封顶
    ctrl_raw_h = (att_str_h / max(def_str_h, 0.3)) * (elo_h / 1500)
    ctrl_raw_a = (att_str_a / max(def_str_a, 0.3)) * (elo_a / 1500)
    mid_h = 5 + 5 * math.tanh(0.35 * (ctrl_raw_h - 1.0))
    mid_a = 5 + 5 * math.tanh(0.35 * (ctrl_raw_a - 1.0))
    mid_h = max(1, min(10, round(mid_h, 1)))
    mid_a = max(1, min(10, round(mid_a, 1)))
    # 无数据时默认 5
    if xg_h.get("matches_played", 0) == 0:
        mid_h = 5.0
    if xg_a.get("matches_played", 0) == 0:
        mid_a = 5.0

    # ═══════════════════════════════════════════════════════════
    # ④ 大赛经验（15%）— 基于 ELO 排名
    #    ELO top5=8-10, top10=7-8, top20=5-7, top40=3-5, else=1-3
    # ═══════════════════════════════════════════════════════════
    def _exp_from_rank(r):
        if r is None or r > 100: return 2.0
        if r <= 5:   return 8.5
        elif r <= 10:  return 7.5
        elif r <= 20:  return 6.0
        elif r <= 30:  return 5.0
        elif r <= 40:  return 4.0
        elif r <= 60:  return 3.0
        else:          return 2.0
    exp_h = _exp_from_rank(rank_h)
    exp_a = _exp_from_rank(rank_a)

    # ═══════════════════════════════════════════════════════════
    # ⑤ 战术适配度（15%）— 风格克制关系
    #     用进攻vs防守的交叉对比：我进攻 vs 你防守，你进攻 vs 我防守
    #     若一方进攻评分远高于对方防守评分 → 战术优势
    #     再加 ELO 差修正
    # ═══════════════════════════════════════════════════════════
    # 我方进攻 vs 对方防守
    home_tactical_advantage = att_h - def_rating_a   # 正值=主队有优势
    away_tactical_advantage = att_a - def_rating_h   # 正值=客队有优势
    # 映射到 1-10 (以 5 为基准，±4 分极值)
    tact_h = max(1, min(10, round(5.0 + home_tactical_advantage * 0.6, 1)))
    tact_a = max(1, min(10, round(5.0 + away_tactical_advantage * 0.6, 1)))

    # ═══════════════════════════════════════════════════════════
    # ⑥ 体能/状态（10%）— 基于近 6 场指数衰减加权胜率
    #    从 form_rating(场均积分): ≥2.3=8-10, 1.8-2.29=6-7,
    #                          1.2-1.79=4-5, 0.6-1.19=2-3, <0.6=1-2
    # ═══════════════════════════════════════════════════════════
    form_h = xg_h.get("form_rating", 1.5)
    form_a = xg_a.get("form_rating", 1.5)

    # ═══════════════════════════════════════════════════════════
    # ⑥ 体能/状态（10%）— 基于近 6 场指数衰减加权胜率
    #    从 form_rating(场均积分): ≥2.3=8-10, 1.8-2.29=6-7,
    #                          1.2-1.79=4-5, 0.6-1.19=2-3, <0.6=1-2
    # ═══════════════════════════════════════════════════════════
    form_h = xg_h.get("form_rating", 1.5)
    form_a = xg_a.get("form_rating", 1.5)

    def _form_to_score(fr):
        if fr >= 2.3:  return 8.0
        elif fr >= 1.8: return 6.5
        elif fr >= 1.2: return 5.0
        elif fr >= 0.6: return 3.0
        else:           return 1.5
    cond_h = _form_to_score(form_h)
    cond_a = _form_to_score(form_a)

    # ═══════════════════════════════════════════════════════════
    # 加权总分（六维，X因素已移除，权重重分配: 进攻22% 防守22%
    # 中场18% 经验18% 战术15% 状态5%）
    # ═══════════════════════════════════════════════════════════
    w = [0.22, 0.22, 0.18, 0.18, 0.15, 0.05]
    total_h = (att_h * w[0] + def_rating_h * w[1] + mid_h * w[2]
               + exp_h * w[3] + tact_h * w[4] + cond_h * w[5])
    total_a = (att_a * w[0] + def_rating_a * w[1] + mid_a * w[2]
               + exp_a * w[3] + tact_a * w[4] + cond_a * w[5])
    total_h = round(total_h, 2)
    total_a = round(total_a, 2)

    return {
        "home_进攻": att_h, "home_防守": def_rating_h,
        "home_中场": mid_h, "home_经验": exp_h,
        "home_战术": tact_h, "home_状态": cond_h,
        "home_total": total_h,
        "away_进攻": att_a, "away_防守": def_rating_a,
        "away_中场": mid_a, "away_经验": exp_a,
        "away_战术": tact_a, "away_状态": cond_a,
        "away_total": total_a,
        "diff": round(total_h - total_a, 2),
        "P_base_raw": round(1.0 / (1.0 + math.exp(-ALPHA_LOGISTIC * (total_h - total_a))), 4),
        "league_avg": avg_xg,
    }


# ============================================================
# ELO 排名 + 比赛类型权重
# ============================================================

# 中文队名 → eloratings.net 2字母代码
TEAM_ELO_CODE = {
    "英格兰": "EN", "巴西": "BR", "阿根廷": "AR",
    "法国": "FR", "德国": "DE", "西班牙": "ES",
    "葡萄牙": "PT", "荷兰": "NL", "意大利": "IT",
    "瑞士": "CH", "乌拉圭": "UY", "哥伦比亚": "CO",
    "墨西哥": "MX", "日本": "JP", "韩国": "KR",
    "澳大利亚": "AU", "埃及": "EG", "比利时": "BE",
    "克罗地亚": "HR", "塞内加尔": "SN",
    "佛得角": "CV", "沙特": "SA",
    "美国": "US", "加拿大": "CA", "摩洛哥": "MA",
    "丹麦": "DK", "瑞典": "SE", "挪威": "NO",
    "波兰": "PL", "奥地利": "AT", "捷克": "CZ",
    "匈牙利": "HU", "土耳其": "TR", "苏格兰": "SCT",
    "波黑": "BA", "卡塔尔": "QA", "新西兰": "NZ",
    "巴拉圭": "PY", "厄瓜多尔": "EC",
    "南非": "ZA", "加纳": "GH",
    "民主刚果": "CD", "刚果金": "CD", "刚果(金)": "CD",
    "伊拉克": "IQ", "伊朗": "IR", "约旦": "JO",
    "乌兹别克": "UZ", "阿尔及利亚": "DZ",
    "突尼斯": "TN", "海地": "HT", "库拉索": "CW",
    "科特迪瓦": "CI", "巴拿马": "PA",
    # 欧战俱乐部
    "索陆军": "CSS", "CSKA Sofia": "CSS",
    "斯海杜克": "HAJ", "Hajduk Split": "HAJ",
    "日利纳": "ZIL", "Žilina": "ZIL",
    "德里城": "DER", "Derry City": "DER",
    "伏伊伏丁": "VOJ", "Vojvodina": "VOJ",
    "费伦茨": "FER", "Ferencváros": "FER", "Ferencvaros": "FER",
    "阿拉木图": "KRT", "Kairat Almaty": "KRT", "Kairat": "KRT",
    "苏捷斯卡": "SUT", "FK Sutjeska": "SUT", "Sutjeska": "SUT",
}

# 比赛类型权重（与 SKILL 方法论一致）
MATCH_WEIGHTS = {
    "world_cup": 1.0,
    "world cup": 1.0,
    "world championship": 1.0,
    "qualification": 0.8,
    "qualifier": 0.8,
    "friendly": 0.5,
    "international friendly": 0.5,
    "league": 0.9,
    "cup": 0.85,
}

# ELO 数据缓存（内存 + 磁盘双重缓存）
_ELO_CACHE = None
_ELO_CACHE_FILE = os.path.join(CACHE_DIR, "elo_rankings_cache.json")
_ELO_CACHE_TTL = 86400  # 24小时


def _load_elo_rankings() -> dict:
    """加载 ELO 排名（磁盘缓存 → API → 过期缓存回退）

    API 超时或返回空数据时保留现有磁盘缓存，不覆盖。
    """
    global _ELO_CACHE

    # 内存缓存
    if _ELO_CACHE is not None:
        return _ELO_CACHE

    # 磁盘缓存（优先取有效 TTL 的，失败后仍保留变量用于过期回退）
    stale_data = None
    if os.path.exists(_ELO_CACHE_FILE):
        try:
            with open(_ELO_CACHE_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            cache_data = cached.get("data", {})
            age = time() - cached.get("ts", 0)
            if age < _ELO_CACHE_TTL:
                _ELO_CACHE = cache_data
                return _ELO_CACHE
            stale_data = cache_data  # 保存过期数据备用
        except Exception:
            pass

    # API 获取（仅 datafc 包可用时）
    if DATAFIC_AVAILABLE:
        for attempt in range(3):
            try:
                df = eloratings.world_ranking_data()
                if df is not None and not df.empty:
                    elo_map = {}
                    for _, row in df.iterrows():
                        code = str(row.get("country", "") or row.get("Country", "") or "")
                        elo_val = row.get("elo", row.get("Elo", 1500))
                        rank = row.get("rank", row.get("Rank"))
                        if code:
                            elo_map[code] = {"elo": int(elo_val), "rank": int(rank) if rank else None}
                    # 仅非空数据才写入磁盘缓存
                    if elo_map:
                        _ELO_CACHE = elo_map
                        try:
                            with open(_ELO_CACHE_FILE, "w", encoding="utf-8") as f:
                                json.dump({"ts": time(), "data": _ELO_CACHE}, f, ensure_ascii=False)
                        except Exception:
                            pass
                        return _ELO_CACHE
                    # 空数据：不覆盖磁盘缓存，尝试过期回退
                    break
            except Exception:
                if attempt < 2:
                    import time as _tmod
                    _tmod.sleep(2)
                continue

    # API 失败或无数据 → 回退到过期磁盘缓存
    if stale_data:
        _ELO_CACHE = stale_data
        return _ELO_CACHE

    return {}


def get_team_elo(team_name: str) -> dict:
    """获取球队 ELO 评分（直接从磁盘缓存读取，不过期）

    不过期：宁可读 7 天前的数据，也不返回默认 1500 低估强队。

    Returns:
        {"elo": int, "rank": int} or {"elo": 1500, "rank": None}
    """
    code = TEAM_ELO_CODE.get(team_name)
    if not code:
        return {"elo": 1500, "rank": None}
    # 直接读缓存文件，绕开 _load_elo_rankings 的API超时问题
    try:
        import json as _j, os as _o
        if _o.path.exists(_ELO_CACHE_FILE):
            with open(_ELO_CACHE_FILE, "r", encoding="utf-8") as _f:
                _cached = _j.load(_f)
            _data = _cached.get("data", {})
            if isinstance(_data, dict) and code in _data:
                # 即使过期也返回，有数据总比默认1500好
                _val = _data[code]
                if isinstance(_val, dict) and _val.get("elo"):
                    return _val
    except Exception:
        pass
    return {"elo": 1500, "rank": None}


def calc_elo_prob(elo_a: int, elo_b: int) -> float:
    """ELO 胜率公式: P = 1 / (1 + 10^((elo_B - elo_A) / 400))"""
    return 1.0 / (1.0 + 10 ** ((elo_b - elo_a) / 400.0))


def get_match_type_weight(tournament_name: str) -> float:
    """根据比赛名称获取比赛类型权重"""
    if not tournament_name:
        return 0.8
    tn = tournament_name.lower()
    for pattern, weight in MATCH_WEIGHTS.items():
        if pattern in tn:
            return weight
    return 0.8

def get_h2h_prob(home_team: str, away_team: str, league: str) -> dict:
    """获取交锋历史概率"""
    default = {"home_win": 1/3, "draw": 1/3, "away_win": 1/3, "total": 0}
    try:
        matches = get_matches(league, team_name=home_team)
        if matches.empty:
            return default
        team_h_en = TEAM_EN.get(home_team, home_team)
        team_a_en = TEAM_EN.get(away_team, away_team)
        for _, row in matches.iterrows():
            ht = str(row.get("home_team", ""))
            at = str(row.get("away_team", ""))
            if (team_h_en.lower() in ht.lower() and team_a_en.lower() in at.lower()) or                (team_h_en.lower() in at.lower() and team_a_en.lower() in ht.lower()):
                single = matches.loc[[row.name]]
                try:
                    h2h = dfc_match_h2h(match_df=single)
                    if not h2h.empty:
                        r = h2h.iloc[0]
                        hw = int(r.get("home_wins", 0))
                        aw = int(r.get("away_wins", 0))
                        d = int(r.get("draws", 0))
                        total = hw + aw + d
                        if total > 0:
                            return {
                                "home_win": round(hw / total, 3),
                                "draw": round(d / total, 3),
                                "away_win": round(aw / total, 3),
                                "total": total,
                            }
                except Exception:
                    continue
    except Exception:
        pass
    return default


# ============================================================
# 快速验证
    tn = tournament_name.lower()
    for pattern, weight in MATCH_WEIGHTS.items():
        if pattern in tn:
            return weight
    return 0.8


# ============================================================
# 轮换/大败/休息差 自动推断（用于 M 系数）
# ============================================================

def get_team_starting_xi(team_name: str, league: str, match_count: int = 3) -> list:
    """获取球队近期首发阵容列表

    从 lineups_data 中找出 minutesPlayed >= 80 的球员作为首发。
    每场比赛返回一个 set(球员名)。

    注意：当 DATAFIC_ALIVE=False 时（Sofascore 被封禁），
    阵容数据不可用，直接返回空列表（轮换级别默认为 L0）。

    Returns:
        [set(["球员A","球员B",...]), set(...)]   # 最新在前
    """
    if not get_datafc_alive():
        return []  # Sofascore 不可用，阵容数据不可获取

    matches = get_team_recent_matches(team_name, league, max_games=match_count)
    if matches.empty:
        return []

    start_xis = []
    # 逐场获取首发
    for idx in matches.head(match_count).index:
        single = matches.loc[[idx]]
        try:
            lu = dfc_lineups(match_df=single)
        except Exception:
            continue
        if lu.empty:
            continue

        team_en = TEAM_EN.get(team_name, team_name)
        tn_lower = team_en.lower().replace(" ", "")

        # 判断是主队还是客队
        home_team = single.iloc[0].get("home_team", "")
        away_team = single.iloc[0].get("away_team", "")
        is_home_match = tn_lower in home_team.lower().replace(" ", "")
        team_side = "home" if is_home_match else "away"

        team_rows = lu[lu["team"] == team_side]
        if team_rows.empty:
            continue

        # 找首发的球员（minutesPlayed >= 80 视为首发）
        starters = set()
        for _, row in team_rows.iterrows():
            player = row.get("player_name", "")
            stat = row.get("stat_name", "")
            val = row.get("stat_value", 0)
            if stat == "minutesPlayed" and val is not None:
                try:
                    mins = int(val)
                    if mins >= 80:
                        starters.add(player)
                except (ValueError, TypeError):
                    pass

        if starters:
            start_xis.append(starters)

    return start_xis


def infer_rotation_level(team_name: str, league: str) -> int:
    """推断轮换幅度 L0-L4

    基于近2-3场首发阵容的变化程度：
      L0 (0): 无轮换 — 连续2场以上首发完全相同
      L1 (1): 微调 — 变化1-2人
      L2 (2): 常规轮换 — 变化3-4人
      L3 (3): 大幅轮换 — 变化5-6人
      L4 (4): 全替补 — 变化7人以上

    Returns: 0-4
    """
    start_xis = get_team_starting_xi(team_name, league, match_count=3)
    if len(start_xis) < 2:
        return 0  # 数据不足，默认无轮换

    # 最新 vs 上一场的差异
    latest = start_xis[0]
    prev = start_xis[1]

    changes = len(latest.symmetric_difference(prev))
    avg_size = (len(latest) + len(prev)) / 2

    # 归一化到更合理的值
    if avg_size == 0:
        return 0

    # change_ratio = changes / avg_size   # 0.0 ~ 1.0+
    if changes <= 1:
        return 0  # L0
    elif changes <= 2:
        return 1  # L1
    elif changes <= 4:
        return 2  # L2
    elif changes <= 6:
        return 3  # L3
    else:
        return 4  # L4


def infer_big_loss(team_name: str, league: str) -> int:
    """推断上轮输球数（用于 M系数 big_loss）

    检查最近一场已完赛比赛，如果球队输了，
    返回净负球数（2 = 输2球，3 = 输3球...）。

    Returns: 0-5+
    """
    matches = get_team_recent_matches(team_name, league, max_games=1)
    if matches.empty:
        return 0

    row = matches.iloc[0]
    team_en = TEAM_EN.get(team_name, team_name)
    tn_lower = team_en.lower().replace(" ", "")

    home_team = str(row.get("home_team", "")).lower().replace(" ", "")
    away_team = str(row.get("away_team", "")).lower().replace(" ", "")
    hs = row.get("home_score_normaltime") or row.get("home_score_display") or 0
    as_ = row.get("away_score_normaltime") or row.get("away_score_display") or 0

    try:
        hs, as_ = int(hs), int(as_)
    except (ValueError, TypeError):
        return 0

    if tn_lower in home_team:
        # 主队
        if hs >= as_:
            return 0  # 没输
        return as_ - hs  # 输了几球
    elif tn_lower in away_team:
        if as_ >= hs:
            return 0
        return hs - as_
    return 0


def infer_rest_diff(team_name: str, league: str) -> int:
    """推断休息天数差（用于 M系数 rest_diff）

    返回最近2场比赛之间的间隔天数。
    正值 = 休息充分，负值 = 密集赛程。

    Returns: 天数差 (0 ~ 10+)
    """
    matches = get_team_recent_matches(team_name, league, max_games=2)
    if len(matches) < 2:
        return 0

    # 最新两场
    t1 = matches.iloc[0].get("start_timestamp")
    t2 = matches.iloc[1].get("start_timestamp")
    if t1 and t2:
        try:
            from datetime import datetime
            d1 = datetime.fromtimestamp(int(t1))
            d2 = datetime.fromtimestamp(int(t2))
            diff = (d1 - d2).days
            return min(diff, 14)  # 上限14天
        except:
            pass
    return 7  # 默认一周一赛


# ============================================================
# 淘汰赛 / 德比 检测
# ============================================================

def is_knockout_league(league: str) -> bool:
    """判断联赛是否属于淘汰赛制（杯赛/世界杯/俱乐部欧战淘汰赛阶段）

    淘汰赛制下历史交锋参考价值下降（×0.625），
    但比赛重要性上升（淘汰赛/德比 → ×1.15）。

    注意：club cup (ucl/uel/uecl) 同时包含小组赛和淘汰赛，
    当前整赛事视为淘汰赛权重（保守处理），后续可细化到 stage 级别。
    """
    if not league:
        return False
    info = LEAGUE_TOURNAMENT.get(league, {})
    tour_type = info.get("type", "")
    # world_cup + cup + uefa + knockout 都视为淘汰赛权重
    # fix: 漏掉了俱乐部欧战(type=uefa) 和国内杯赛(type=knockout)
    if tour_type in ("world_cup", "cup", "uefa", "knockout"):
        return True
    # 联赛名为纯 league 类型 → 不是淘汰赛
    return False


def has_knockout_stage(league: str) -> bool:
    """联赛是否有淘汰赛阶段（区别于纯联赛/纯淘汰赛制）

    仅 uefa（欧冠/欧联/欧协联）和 world_cup（世界杯/欧洲杯等）有小组赛+淘汰赛结构。
    纯淘汰赛（facup/dfbpokal 等）一轮定胜负，节奏与联赛无显著差异，不触发 λ 衰减。

    用于 KO λ 系数和 KO M 系数的触发条件。
    """
    if not league:
        return False
    info = LEAGUE_TOURNAMENT.get(league, {})
    return info.get("type") in ("uefa", "world_cup")


def is_derby_match(home_team: str, away_team: str) -> bool:
    """判断是否为德比（国家德比 / 地区德比 / 经典对决）

    德比赛事增加叙事驱动溢价：
      - 大球概率 +0.5 球
      - 战意因子（must_win）自动升级
    """
    if not home_team or not away_team:
        return False

    # 互为英文名（去空格小写）
    h_en = TEAM_EN.get(home_team, home_team).lower().replace(" ", "")
    a_en = TEAM_EN.get(away_team, away_team).lower().replace(" ", "")

    DERBY_PAIRS = [
        # 国家队经典德比
        ("argentina", "brazil"),       # 南美超级德比
        ("argentina", "uruguay"),       #  Río de la Plata
        ("brazil", "uruguay"),          # 南美经典
        ("germany", "netherlands"),     # 欧洲经典
        ("germany", "england"),         # 英德
        ("england", "scotland"),        # 不列颠德比
        ("england", "france"),          # 英法
        ("italy", "france"),            # 意法
        ("italy", "germany"),           # 意德
        ("spain", "portugal"),          # 伊比利亚德比
        ("spain", "italy"),             # 意西
        ("france", "portugal"),         # 法葡
        ("netherlands", "belgium"),     # 比荷
        ("portugal", "spain"),          # 伊比利亚 (对称)
        ("mexico", "usa"),              # 中北美德比
        ("colombia", "venezuela"),      # 南美地区
        ("chile", "peru"),              # 太平洋德比
        ("japan", "southkorea"),        # 东亚德比
        ("japan", "korea"),             # 东亚德比 (备用名)
        ("southkorea", "japan"),        # 东亚德比
    ]

    pair = (h_en, a_en)
    if pair in DERBY_PAIRS or (pair[1], pair[0]) in DERBY_PAIRS:
        return True

    # 共享国家/城市名（俱乐部德比）
    # 用共享国家代码或俱乐部前缀判断
    return False


def calc_h2h_weight(league: str) -> float:
    """计算历史交锋权重因子（WVR 衰减后）

    来自 SKILL.md v7.3 统一评分引擎规范：
      小组赛 1.0 / 淘汰赛 0.625(B级)
    """
    if is_knockout_league(league):
        return 0.625
    return 1.0


def calc_derby_goal_bonus(home_team: str, away_team: str) -> float:
    """计算德比叙事驱动的预期进球溢价

    德比战叙事驱动（复仇/纪录/荣誉）增加进球预期：
      - 基础溢价 +0.5 球
      - 仅当确认为德比时触发
    """
    if is_derby_match(home_team, away_team):
        return 0.5
    return 0.0


def infer_m_factors(team_name: str, league: str) -> dict:
    """自动推断 M 系数因子

    Returns:
        dict with keys:
          rotation     (int 0-4)  轮换级别
          big_loss     (int)      上轮净负球
          rest_diff    (int)      休息天数差
          must_win     (str)      战意: none / low / high
          league_type  (str)      赛事阶段: group / knockout
          h2h_weight   (float)    历史交锋权重 (1.0 / 0.625)
    """
    factors = {}

    # 轮换检测 — 仅联赛和纯淘汰赛(足总杯等)运行（v8.5）
    # 国家队杯赛(world_cup)和俱乐部欧战(uefa)的淘汰赛阶段不检测
    # 原因：国家队阵容数据不全，易误判为L4（摩洛哥bug）
    # 纯淘汰赛(足总杯)运行轮换检测（英超队确实会轮换）
    if is_knockout_league(league) and has_knockout_stage(league):
        factors["rotation"] = 0
    else:
        try:
            factors["rotation"] = infer_rotation_level(team_name, league)
        except Exception:
            factors["rotation"] = 0

    # 大败
    try:
        factors["big_loss"] = infer_big_loss(team_name, league)
    except Exception:
        factors["big_loss"] = 0

    # 休息差
    try:
        factors["rest_diff"] = infer_rest_diff(team_name, league)
    except Exception:
        factors["rest_diff"] = 7

    # 赛事类型
    factors["league_type"] = "knockout" if is_knockout_league(league) else "group"

    # 历史交锋权重
    factors["h2h_weight"] = calc_h2h_weight(league)

    # 战意推断（淘汰赛/保级/争冠自动高战意）
    factors["must_win"] = "high" if is_knockout_league(league) else "none"

    return factors


# ============================================================
# 快速验证
# ============================================================

def search_team(team_name: str) -> list:
    """搜索球队（用于查找 Sofascore 上的队名）"""
    try:
        r = dfc_search(team_name, entity_type="team")
        return r.to_dict("records") if not r.empty else []
    except Exception:
        return []


def detect_team_league(team_name: str, fallback_league: str = "wm26") -> str:
    """通过 Sofascore 搜索自动检测球队当前参加的联赛/赛事

    当指定联赛找不到球队数据时，用球队名搜索 Sofascore，
    从搜索结果中提取球队当前参与的赛事 ID，映射回 LEAGUE_TOURNAMENT 中的联赛代码。

    Args:
        team_name: 球队名（中文/英文）
        fallback_league: 未找到时的默认联赛

    Returns:
        联赛代码（如 "ucl", "bl1", "kleague1"），或 fallback_league
    """
    if not DATAFIC_AVAILABLE:
        return fallback_league

    # 已有缓存：本次会话中查过的球队
    _detect_cache = getattr(detect_team_league, "_cache", {})
    if team_name in _detect_cache:
        return _detect_cache[team_name]

    try:
        results = search_team(team_name)
        if not results:
            return fallback_league

        # 从搜索结果提取 tournament_id
        for r in results:
            tid = r.get("tournament_id") or r.get("tournament", {}).get("id")
            if not tid:
                continue
            tid = int(tid)
            # 反向查找 LEAGUE_TOURNAMENT：哪个联赛代码匹配这个 tid？
            for code, cfg in LEAGUE_TOURNAMENT.items():
                if cfg.get("tid") == tid:
                    _detect_cache[team_name] = code
                    detect_team_league._cache = _detect_cache
                    return code

        # 已知欧战资格赛球队的国内联赛映射（search 失败时回退）
        _TEAM_LEAGUE_MAP = {
            "伏伊伏丁": "rsl", "Vojvodina": "rsl", "FK Vojvodina": "rsl",
            "索陆军": "bul", "CSKA Sofia": "bul",
            "斯海杜克": "cro", "Hajduk Split": "cro",
            "日利纳": "svk", "Zilina": "svk",
            "德里城": "irl", "Derry City": "irl",
            "费伦茨": "hun", "Ferencvaros": "hun", "Ferencváros": "hun",
        }
        _norm_input = _norm(team_name)
        for _tn, _lc in _TEAM_LEAGUE_MAP.items():
            if _norm_input == _norm(_tn):
                _detect_cache[team_name] = _lc
                detect_team_league._cache = _detect_cache
                return _lc

        # tid 未直接映射 → 尝试通过 tournament_name 模糊匹配
        for r in results:
            tour_name = (r.get("tournament", {}) or {}).get("name", "") or r.get("tournament_name", "")
            if not tour_name:
                continue
            tn = tour_name.lower()
            for code, cfg in LEAGUE_TOURNAMENT.items():
                cfg_name = cfg.get("name", "").lower()
                # 赛事名部分匹配（如 "UEFA Champions League" → "ucl"）
                if cfg_name and (cfg_name in tn or tn in cfg_name):
                    _detect_cache[team_name] = code
                    detect_team_league._cache = _detect_cache
                    return code
    except Exception:
        pass

    _detect_cache[team_name] = fallback_league
    detect_team_league._cache = _detect_cache
    return fallback_league


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="datafc 统一数据提供器")
    parser.add_argument("--test", help="测试: 联赛代码 + 球队名", nargs=2, metavar=("LEAGUE", "TEAM"))
    parser.add_argument("--sync", help="同步赛后结果到 auto_results.json", metavar="LEAGUE")
    args = parser.parse_args()

    if args.test:
        league, team = args.test
        log(f"\n=== 测试 {league}: {team} ===\n")
        # xG 数据
        xg = estimate_team_strength(team, league)
        log(f"xG数据:")
        for k, v in xg.items():
            log(f"  {k}: {v}")

        # 近期比赛
        log(f"\n近期比赛:")
        matches = get_team_recent_matches(team, league, max_games=5)
        if not matches.empty:
            for _, row in matches.iterrows():
                hs = row.get("home_score_normaltime") or row.get("home_score_display", "")
                as_ = row.get("away_score_normaltime") or row.get("away_score_display", "")
                log(f"  {row.get('home_team','?')} {hs}-{as_} {row.get('away_team','?')}")
        else:
            log(f"  (无数据)")

        # 积分榜
        log(f"\n积分榜:")
        st = get_standings(league)
        if st:
            for s in st[:5]:
                log(f"  #{s['position']} {s['team']} {s['points']}pts")
        else:
            log(f"  (无数据)")

    elif args.sync:
        n = sync_results_to_file(args.sync)
        log(f"同步完成: {n} 场")
    else:
        parser.print_help()
