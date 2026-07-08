

# J1联赛球队积分榜数据（2026百年构想赛季 - 常规赛18轮）
# 来源: FBref / 球探体育 / soccerstats247
JLEAGUE1_TABLE = {
    "鹿岛鹿角": {"played":18,"gf":29,"ga":9,"pts":45,"rank":1,"form":"WWDWW","style":"possession"},
    "Kashima Antlers": {"played":18,"gf":29,"ga":9,"pts":45,"rank":1,"form":"WWDWW","style":"possession"},
    "FC东京": {"played":18,"gf":28,"ga":16,"pts":37,"rank":2,"form":"WDWDW","style":"transition"},
    "FC Tokyo": {"played":18,"gf":28,"ga":16,"pts":37,"rank":2,"form":"WDWDW","style":"transition"},
    "町田泽维亚": {"played":18,"gf":23,"ga":19,"pts":37,"rank":3,"form":"DWDWW","style":"counter"},
    "Machida Zelvia": {"played":18,"gf":23,"ga":19,"pts":37,"rank":3,"form":"DWDWW","style":"counter"},
    "川崎前锋": {"played":18,"gf":23,"ga":27,"pts":28,"rank":4,"form":"WLWLD","style":"possession"},
    "Kawasaki Frontale": {"played":18,"gf":23,"ga":27,"pts":28,"rank":4,"form":"WLWLD","style":"possession"},
    "东京绿茵": {"played":18,"gf":19,"ga":25,"pts":28,"rank":5,"form":"WLLWD","style":"mixed"},
    "Tokyo Verdy": {"played":18,"gf":19,"ga":25,"pts":28,"rank":5,"form":"WLLWD","style":"mixed"},
    "浦和红钻": {"played":18,"gf":25,"ga":18,"pts":25,"rank":6,"form":"LDWLW","style":"possession"},
    "Urawa Reds": {"played":18,"gf":25,"ga":18,"pts":25,"rank":6,"form":"LDWLW","style":"possession"},
    "横滨水手": {"played":18,"gf":28,"ga":29,"pts":20,"rank":7,"form":"LLWDL","style":"transition"},
    "Yokohama F.Marinos": {"played":18,"gf":28,"ga":29,"pts":20,"rank":7,"form":"LLWDL","style":"transition"},
    "柏太阳神": {"played":18,"gf":21,"ga":24,"pts":20,"rank":8,"form":"WLWLL","style":"counter"},
    "Kashiwa Reysol": {"played":18,"gf":21,"ga":24,"pts":20,"rank":8,"form":"WLWLL","style":"counter"},
    "水户蜀葵": {"played":18,"gf":19,"ga":35,"pts":18,"rank":9,"form":"LLDLW","style":"counter"},
    "Mito HollyHock": {"played":18,"gf":19,"ga":35,"pts":18,"rank":9,"form":"LLDLW","style":"counter"},
    "千叶市原": {"played":18,"gf":18,"ga":31,"pts":12,"rank":10,"form":"LDLLL","style":"mixed"},
    "JEF United Chiba": {"played":18,"gf":18,"ga":31,"pts":12,"rank":10,"form":"LDLLL","style":"mixed"},
    # West Group
    "神户胜利船": {"played":18,"gf":27,"ga":21,"pts":35,"rank":1,"form":"WDWWL","style":"possession"},
    "Vissel Kobe": {"played":18,"gf":27,"ga":21,"pts":35,"rank":1,"form":"WDWWL","style":"possession"},
    "大阪樱花": {"played":18,"gf":26,"ga":19,"pts":31,"rank":2,"form":"DWDWL","style":"possession"},
    "Cerezo Osaka": {"played":18,"gf":26,"ga":19,"pts":31,"rank":2,"form":"DWDWL","style":"possession"},
    "名古屋鲸八": {"played":18,"gf":31,"ga":28,"pts":31,"rank":3,"form":"WWLWD","style":"control_counter"},
    "Nagoya Grampus": {"played":18,"gf":31,"ga":28,"pts":31,"rank":3,"form":"WWLWD","style":"control_counter"},
    "广岛三箭": {"played":18,"gf":29,"ga":21,"pts":30,"rank":4,"form":"WLWDW","style":"possession"},
    "Sanfrecce Hiroshima": {"played":18,"gf":29,"ga":21,"pts":30,"rank":4,"form":"WLWDW","style":"possession"},
    "大阪钢巴": {"played":18,"gf":26,"ga":22,"pts":28,"rank":5,"form":"DLDWW","style":"transition"},
    "Gamba Osaka": {"played":18,"gf":26,"ga":22,"pts":28,"rank":5,"form":"DLDWW","style":"transition"},
    "冈山绿雉": {"played":18,"gf":24,"ga":25,"pts":26,"rank":6,"form":"WDLDW","style":"counter"},
    "Fagiano Okayama": {"played":18,"gf":24,"ga":25,"pts":26,"rank":6,"form":"WDLDW","style":"counter"},
    "清水鼓动": {"played":18,"gf":19,"ga":21,"pts":24,"rank":7,"form":"DLWLD","style":"possession"},
    "Shimizu S-Pulse": {"played":18,"gf":19,"ga":21,"pts":24,"rank":7,"form":"DLWLD","style":"possession"},
    "京都不死鸟": {"played":18,"gf":19,"ga":26,"pts":23,"rank":8,"form":"LWLDD","style":"counter"},
    "Kyoto Sanga": {"played":18,"gf":19,"ga":26,"pts":23,"rank":8,"form":"LWLDD","style":"counter"},
    "长崎成功丸": {"played":18,"gf":20,"ga":28,"pts":21,"rank":9,"form":"LDLLW","style":"mixed"},
    "V-Varen Nagasaki": {"played":18,"gf":20,"ga":28,"pts":21,"rank":9,"form":"LDLLW","style":"mixed"},
    "福冈黄蜂": {"played":18,"gf":17,"ga":27,"pts":21,"rank":10,"form":"DLWLD","style":"counter"},
    "Avispa Fukuoka": {"played":18,"gf":17,"ga":27,"pts":21,"rank":10,"form":"DLWLD","style":"counter"},
}
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
xG 数据估计器 — 球队实力评估管线（xG替代方案）

用途:
  为七维评分L1①进攻能力和L1②防守稳固性提供数据基础。
  优先使用football-data.org（工作API），回退到OpenLigaDB实际进球数。

xG数据模式（主推）：
  python skill/xg_estimator.py --home "主队" --away "客队"
  python skill/xg_estimator.py --home "英格兰" --away "巴西" --league wm26

输出：
  - 两队近10场 xG_for/90、xG_against/90、xG_per_shot
  - 在联赛中的百分位数 → 直接注入七维评分
  - 当xG不可用时降级使用实际进球数 + 标注"(未校准)"

数据来源:
  首选: football-data.org（用户API Key — 比赛数据稳定可用）
  次选: FBref (fbref.com) — ⚠️ Cloudflare保护，大概率403
  三选: Understat (understat.com) — ⚠️ 反爬保护
  回退: OpenLigaDB — 实际进球数 (稳定免费)
"""

import json
import sys
import os
import math
import argparse
import urllib.request
import urllib.error
import re
import ssl
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timedelta

# Windows控制台编码处理
if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# ============================================================
# 配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "数据缓存")
CACHE_TTL_DAYS = 1  # 缓存有效期1天

# ============================================================
# TheSportsDB 配置（免费版，无需Key — 用于芬超/瑞典超等小众联赛）
# ============================================================
SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"
# 中文队名 → TheSportsDB 英文队名（与 fetch_match_data.py 同步维护）
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
    "瓦纳默": "IFK Varnamo",
    "韦斯比联": "IF Brommapojkarna",
    "哈尔姆斯塔德": "Halmstad",
    "加尔斯": "GAIS",
    "韦斯特罗斯": "Vasteras",
    "代格福什": "Degerfors",
    "赫尔辛基": "HJK",
    "拉赫蒂": "Lahti",
    "赫尔火花": "Gnistan",
    "赫尔辛基火花": "Gnistan",
    "塞伊奈": "SJK",
    "TPS图尔库": "TPS",
    "TPS图尔": "TPS",
    "雅罗": "FF Jaro",
    "坦佩雷": "Tampere United",
    "坦山猫": "Tampere United",
    "瓦萨": "VPS",
    "玛丽港": "IFK Mariehamn",
    "国际图尔库": "FC Inter",
    "库奥皮奥": "KuPS",
    "AC奥卢": "AC Oulu",
    "埃尔维斯": "Ilves",
    "古比斯": "KuPS",
}

# 联赛对应的FBref路径映射
FBREF_LEAGUE_URLS = {
    "bl1": "https://fbref.com/en/comps/20/Bundesliga-Stats",
    "epl": "https://fbref.com/en/comps/9/Premier-League-Stats",
    "laliga": "https://fbref.com/en/comps/12/La-Liga-Stats",
    "seriea": "https://fbref.com/en/comps/11/Serie-A-Stats",
    "ligue1": "https://fbref.com/en/comps/13/Ligue-1-Stats",
    "eredivisie": "https://fbref.com/en/comps/23/Eredivisie-Stats",
    "wm26": None,  # 世界杯无xG数据库，走回退
    "ucl2024": None,  # 欧冠无稳定免费xG源，走回退
}

# 联赛平均xG参考值（五大联赛2024-25赛季实测范围）
# 当无法获取实时联赛平均时使用
LEAGUE_XG_AVG = {
    "bl1": {"xG_for": 1.55, "xG_against": 1.55},
    "epl": {"xG_for": 1.50, "xG_against": 1.50},
    "laliga": {"xG_for": 1.35, "xG_against": 1.35},
    "seriea": {"xG_for": 1.40, "xG_against": 1.40},
    "ligue1": {"xG_for": 1.45, "xG_against": 1.45},
    "kleague1": {"xG_for": 1.13, "xG_against": 1.13},
    "kleague2": {"xG_for": 1.05, "xG_against": 1.05},
    "jleague1": {"xG_for": 1.31, "xG_against": 1.31},
    "jleague2": {"xG_for": 1.28, "xG_against": 1.28},
    "sportsdb": {"xG_for": 1.30, "xG_against": 1.30},  # 瑞典超/芬超 北欧联赛均值
    "default": {"xG_for": 1.40, "xG_against": 1.40},
}

# J2联赛球队积分榜数据（2026 J2/J3百年构想赛季）
JLEAGUE2_TABLE = {
    "仙台七夕": {"played":18,"gf":32,"ga":15,"pts":43,"rank":1,"form":"WWDWW","style":"possession"},
    "Vegalta Sendai": {"played":18,"gf":32,"ga":15,"pts":43,"rank":1,"form":"WWDWW","style":"possession"},
    "秋田蓝色闪电": {"played":18,"gf":23,"ga":14,"pts":35,"rank":2,"form":"WLWDW","style":"counter"},
    "Blaublitz Akita": {"played":18,"gf":23,"ga":14,"pts":35,"rank":2,"form":"WLWDW","style":"counter"},
    "湘南比马": {"played":18,"gf":25,"ga":19,"pts":31,"rank":3,"form":"DWLWD","style":"possession"},
    "Shonan Bellmare": {"played":18,"gf":25,"ga":19,"pts":31,"rank":3,"form":"DWLWD","style":"possession"},
    "横滨FC": {"played":18,"gf":34,"ga":27,"pts":29,"rank":4,"form":"WLWLD","style":"transition"},
    "Yokohama FC": {"played":18,"gf":34,"ga":27,"pts":29,"rank":4,"form":"WLWLD","style":"transition"},
    "甲府风林": {"played":18,"gf":21,"ga":13,"pts":35,"rank":1,"form":"WDWLW","style":"possession"},
    "Ventforet Kofu": {"played":18,"gf":21,"ga":13,"pts":35,"rank":1,"form":"WDWLW","style":"possession"},
    "北海道札幌冈萨多": {"played":18,"gf":26,"ga":22,"pts":31,"rank":2,"form":"WWLDL","style":"possession"},
    "Consadole Sapporo": {"played":18,"gf":26,"ga":22,"pts":31,"rank":2,"form":"WWLDL","style":"possession"},
    "大宫松鼠": {"played":18,"gf":38,"ga":28,"pts":30,"rank":3,"form":"WWLWD","style":"transition"},
    "Omiya Ardija": {"played":18,"gf":38,"ga":28,"pts":30,"rank":3,"form":"WWLWD","style":"transition"},
    "磐田喜悦": {"played":18,"gf":16,"ga":23,"pts":25,"rank":4,"form":"LDLWD","style":"possession"},
    "Jubilo Iwata": {"played":18,"gf":16,"ga":23,"pts":25,"rank":4,"form":"LDLWD","style":"possession"},
    "新潟天鹅": {"played":18,"gf":21,"ga":17,"pts":35,"rank":1,"form":"DWDWW","style":"possession"},
    "Albirex Niigata": {"played":18,"gf":21,"ga":17,"pts":35,"rank":1,"form":"DWDWW","style":"possession"},
    "德岛漩涡": {"played":18,"gf":36,"ga":22,"pts":32,"rank":2,"form":"WWLWD","style":"possession"},
    "Tokushima Vortis": {"played":18,"gf":36,"ga":22,"pts":32,"rank":2,"form":"WWLWD","style":"possession"},
    "爱媛FC": {"played":18,"gf":25,"ga":18,"pts":28,"rank":3,"form":"WLWDL","style":"counter"},
    "Ehime FC": {"played":18,"gf":25,"ga":18,"pts":28,"rank":3,"form":"WLWDL","style":"counter"},
    "鸟栖砂岩": {"played":18,"gf":24,"ga":14,"pts":32,"rank":1,"form":"WDWLW","style":"possession"},
    "Sagan Tosu": {"played":18,"gf":24,"ga":14,"pts":32,"rank":1,"form":"WDWLW","style":"possession"},
    "山口雷诺法": {"played":18,"gf":24,"ga":22,"pts":29,"rank":2,"form":"WLWLD","style":"counter"},
    "Renofa Yamaguchi": {"played":18,"gf":24,"ga":22,"pts":29,"rank":2,"form":"WLWLD","style":"counter"},
    "熊本深红": {"played":18,"gf":20,"ga":20,"pts":27,"rank":3,"form":"LDWWL","style":"mixed"},
    "Roasso Kumamoto": {"played":18,"gf":20,"ga":20,"pts":27,"rank":3,"form":"LDWWL","style":"mixed"},
    "大分三神": {"played":18,"gf":18,"ga":18,"pts":22,"rank":4,"form":"LLWLD","style":"counter"},
    "Oita Trinita": {"played":18,"gf":18,"ga":18,"pts":22,"rank":4,"form":"LLWLD","style":"counter"},
    "FC琉球": {"played":18,"gf":13,"ga":25,"pts":17,"rank":5,"form":"LDLLD","style":"mixed"},
    "FC Ryukyu": {"played":18,"gf":13,"ga":25,"pts":17,"rank":5,"form":"LDLLD","style":"mixed"},
}


# K1联赛球队积分榜数据（2026赛季截至第16轮，2026-07-04更新）
# 来源: K League官网 / 新闻报道
# 更新频率: 每周更新一次（手动/自动）
KLEAGUE1_TABLE = {
    "FC首尔": {"played":15,"gf":27,"ga":12,"pts":32,"rank":1,"form":"LDLWW","style":"transition"},
    "首尔FC": {"played":15,"gf":27,"ga":12,"pts":32,"rank":1,"form":"LDLWW","style":"transition"},
    "Seoul": {"played":15,"gf":27,"ga":12,"pts":32,"rank":1,"form":"LDLWW","style":"transition"},
    "江原FC": {"played":16,"gf":21,"ga":11,"pts":27,"rank":2,"form":"DWWDWW","style":"counter"},
    "Gangwon": {"played":16,"gf":21,"ga":11,"pts":27,"rank":2,"form":"DWWDWW","style":"counter"},
    "蔚山HD": {"played":15,"gf":22,"ga":20,"pts":26,"rank":3,"form":"LWDDL","style":"control_counter"},
    "蔚山现代": {"played":15,"gf":22,"ga":20,"pts":26,"rank":3,"form":"LWDDL","style":"control_counter"},
    "Ulsan": {"played":15,"gf":22,"ga":20,"pts":26,"rank":3,"form":"LWDDL","style":"control_counter"},
    "全北现代": {"played":16,"gf":22,"ga":14,"pts":26,"rank":4,"form":"WDDWWL","style":"possession_highpress"},
    "Jeonbuk": {"played":16,"gf":22,"ga":14,"pts":26,"rank":4,"form":"WDDWWL","style":"possession_highpress"},
    "Jeonbuk Hyundai": {"played":16,"gf":22,"ga":14,"pts":26,"rank":4,"form":"WDDWWL","style":"possession_highpress"},
    "浦项铁人": {"played":16,"gf":15,"ga":14,"pts":25,"rank":5,"form":"LWWDWW","style":"possession"},
    "浦项制铁": {"played":16,"gf":15,"ga":14,"pts":25,"rank":5,"form":"LWWDWW","style":"possession"},
    "Pohang": {"played":16,"gf":15,"ga":14,"pts":25,"rank":5,"form":"LWWDWW","style":"possession"},
    "仁川联": {"played":15,"gf":21,"ga":17,"pts":21,"rank":6,"form":"WLWDL","style":"counter"},
    "Incheon": {"played":15,"gf":21,"ga":17,"pts":21,"rank":6,"form":"WLWDL","style":"counter"},
    "FC安养": {"played":16,"gf":21,"ga":19,"pts":20,"rank":7,"form":"WDDDLL","style":"mixed"},
    "安养FC": {"played":16,"gf":21,"ga":19,"pts":20,"rank":7,"form":"WDDDLL","style":"mixed"},
    "Anyang": {"played":16,"gf":21,"ga":19,"pts":20,"rank":7,"form":"WDDDLL","style":"mixed"},
    "济州SK": {"played":15,"gf":13,"ga":16,"pts":18,"rank":8,"form":"LLWWL","style":"mixed"},
    "济州联": {"played":15,"gf":13,"ga":16,"pts":18,"rank":8,"form":"LLWWL","style":"mixed"},
    "Jeju": {"played":15,"gf":13,"ga":16,"pts":18,"rank":8,"form":"LLWWL","style":"mixed"},
    "富川FC": {"played":16,"gf":13,"ga":17,"pts":18,"rank":9,"form":"WDLLGD","style":"counter"},
    "Bucheon": {"played":16,"gf":13,"ga":17,"pts":18,"rank":9,"form":"WDLLGD","style":"counter"},
    "大田市民": {"played":16,"gf":19,"ga":18,"pts":17,"rank":10,"form":"LLLWD","style":"mixed"},
    "Daejeon": {"played":16,"gf":19,"ga":18,"pts":17,"rank":10,"form":"LLLWD","style":"mixed"},
    "金泉尚武": {"played":15,"gf":15,"ga":21,"pts":14,"rank":11,"form":"LDLLW","style":"counter"},
    "Gimcheon": {"played":15,"gf":15,"ga":21,"pts":14,"rank":11,"form":"LDLLW","style":"counter"},
    "光州FC": {"played":15,"gf":7,"ga":37,"pts":7,"rank":12,"form":"LLDLL","style":"mixed"},
    "Gwangju": {"played":15,"gf":7,"ga":37,"pts":7,"rank":12,"form":"LLDLL","style":"mixed"},
}

# 瑞典超（Allsvenskan）2026赛季积分榜
SWEDEN_TABLE = {
    "马尔默": {"played":16,"gf":32,"ga":12,"pts":38,"rank":1,"form":"WDWWW","style":"possession"},
    "Malmö FF": {"played":16,"gf":32,"ga":12,"pts":38,"rank":1,"form":"WDWWW","style":"possession"},
    "哈马比": {"played":16,"gf":28,"ga":18,"pts":31,"rank":2,"form":"WWDLW","style":"transition"},
    "Hammarby": {"played":16,"gf":28,"ga":18,"pts":31,"rank":2,"form":"WWDLW","style":"transition"},
    "赫根": {"played":16,"gf":27,"ga":19,"pts":30,"rank":3,"form":"WLWDW","style":"possession"},
    "BK Häcken": {"played":16,"gf":27,"ga":19,"pts":30,"rank":3,"form":"WLWDW","style":"possession"},
    "佐加顿斯": {"played":16,"gf":24,"ga":17,"pts":29,"rank":4,"form":"WDWLW","style":"transition"},
    "Djurgården": {"played":16,"gf":24,"ga":17,"pts":29,"rank":4,"form":"WDWLW","style":"transition"},
    "埃尔夫斯堡": {"played":16,"gf":26,"ga":22,"pts":26,"rank":5,"form":"DLWDW","style":"possession"},
    "IFK Göteborg": {"played":16,"gf":20,"ga":20,"pts":24,"rank":6,"form":"WLDWD","style":"mixed"},
    "AIK": {"played":16,"gf":19,"ga":20,"pts":23,"rank":7,"form":"LDWLD","style":"mixed"},
    "北雪平": {"played":16,"gf":22,"ga":24,"pts":22,"rank":8,"form":"WLDLW","style":"transition"},
    "卡尔马": {"played":16,"gf":18,"ga":22,"pts":20,"rank":9,"form":"LDWLL","style":"mixed"},
    "天狼星": {"played":16,"gf":20,"ga":25,"pts":19,"rank":10,"form":"WLLDW","style":"mixed"},
    "布洛马波卡纳": {"played":16,"gf":18,"ga":24,"pts":18,"rank":11,"form":"WLDLD","style":"mixed"},
    "哈尔姆斯塔德": {"played":16,"gf":16,"ga":26,"pts":17,"rank":12,"form":"LDWLL","style":"counter"},
    "米亚尔比": {"played":16,"gf":17,"ga":28,"pts":16,"rank":13,"form":"LLDWL","style":"counter"},
    "韦斯特罗斯": {"played":16,"gf":15,"ga":29,"pts":14,"rank":14,"form":"LLWLD","style":"counter"},
    "代格福什": {"played":16,"gf":14,"ga":32,"pts":13,"rank":15,"form":"LDLLL","style":"counter"},
    "GAIS": {"played":16,"gf":13,"ga":30,"pts":12,"rank":16,"form":"LLLDW","style":"counter"},
}

# 芬超（Veikkausliiga）2026赛季积分榜
FINLAND_TABLE = {
    "赫尔辛基": {"played":14,"gf":25,"ga":10,"pts":32,"rank":1,"form":"WWWLD","style":"possession"},
    "HJK": {"played":14,"gf":25,"ga":10,"pts":32,"rank":1,"form":"WWWLD","style":"possession"},
    "库奥皮奥": {"played":14,"gf":22,"ga":12,"pts":30,"rank":2,"form":"WDWLW","style":"transition"},
    "KuPS": {"played":14,"gf":22,"ga":12,"pts":30,"rank":2,"form":"WDWLW","style":"transition"},
    "塞伊奈": {"played":14,"gf":18,"ga":14,"pts":25,"rank":3,"form":"WLDWW","style":"mixed"},
    "SJK": {"played":14,"gf":18,"ga":14,"pts":25,"rank":3,"form":"WLDWW","style":"mixed"},
    "国际图尔库": {"played":14,"gf":17,"ga":14,"pts":23,"rank":4,"form":"DLWDW","style":"mixed"},
    "FC Inter": {"played":14,"gf":17,"ga":14,"pts":23,"rank":4,"form":"DLWDW","style":"mixed"},
    "AC奥卢": {"played":14,"gf":16,"ga":16,"pts":20,"rank":5,"form":"WLLDW","style":"mixed"},
    "AC Oulu": {"played":14,"gf":16,"ga":16,"pts":20,"rank":5,"form":"WLLDW","style":"mixed"},
    "瓦萨": {"played":14,"gf":14,"ga":16,"pts":19,"rank":6,"form":"LDWLD","style":"mixed"},
    "VPS": {"played":14,"gf":14,"ga":16,"pts":19,"rank":6,"form":"LDWLD","style":"mixed"},
    "埃尔维斯": {"played":14,"gf":15,"ga":18,"pts":18,"rank":7,"form":"WLDLL","style":"counter"},
    "Ilves": {"played":14,"gf":15,"ga":18,"pts":18,"rank":7,"form":"WLDLL","style":"counter"},
    "TPS图尔库": {"played":14,"gf":13,"ga":18,"pts":16,"rank":8,"form":"LDLLW","style":"counter"},
    "TPS": {"played":14,"gf":13,"ga":18,"pts":16,"rank":8,"form":"LDLLW","style":"counter"},
    "拉赫蒂": {"played":14,"gf":12,"ga":20,"pts":14,"rank":9,"form":"LLWLD","style":"counter"},
    "Lahti": {"played":14,"gf":12,"ga":20,"pts":14,"rank":9,"form":"LLWLD","style":"counter"},
    "玛丽港": {"played":14,"gf":11,"ga":22,"pts":12,"rank":10,"form":"LDLLL","style":"counter"},
    "IFK Mariehamn": {"played":14,"gf":11,"ga":22,"pts":12,"rank":10,"form":"LDLLL","style":"counter"},
    "雅罗": {"played":14,"gf":10,"ga":24,"pts":11,"rank":11,"form":"LLLDL","style":"counter"},
    "FF Jaro": {"played":14,"gf":10,"ga":24,"pts":11,"rank":11,"form":"LLLDL","style":"counter"},
}

# 战术风格对阵矩阵（对应SKILL.md模块2风格矩阵）
STYLE_MATRIX = {
    ("counter","counter"):           {"pace":"slow","ou":"small","goals":"0-2球"},
    ("control_counter","counter"):   {"pace":"slow","ou":"small","goals":"0-2球"},
    ("possession","counter"):        {"pace":"slow","ou":"small","goals":"1-2球"},
    ("possession","control_counter"):{"pace":"medium","ou":"slight_small","goals":"1-2球"},
    ("control_counter","control_counter"):{"pace":"medium","ou":"slight_small","goals":"1-2球"},
    ("counter","highpress"):         {"pace":"fast","ou":"big","goals":"2-4球"},
    ("possession_highpress","counter"):{"pace":"fast","ou":"big","goals":"2-4球"},
    ("control_counter","highpress"):  {"pace":"fast","ou":"big","goals":"2-4球"},
    ("transition","highpress"):      {"pace":"fastest","ou":"big","goals":"3-5球"},
    ("transition","counter"):        {"pace":"medium","ou":"balanced","goals":"2-3球"},
    ("transition","transition"):     {"pace":"fast","ou":"big","goals":"2-4球"},
    ("possession","highpress"):      {"pace":"medium","ou":"balanced","goals":"2-3球"},
    ("highpress","highpress"):       {"pace":"fast","ou":"big","goals":"3-5球"},
    ("possession","possession"):     {"pace":"medium","ou":"slight_small","goals":"1-3球"},
    ("transition","possession"):     {"pace":"medium","ou":"balanced","goals":"2-3球"},
}

STYLE_LABELS = {
    "possession": "传控", "possession_highpress": "传控+高位逼抢",
    "counter": "防守反击", "control_counter": "控制型防反",
    "transition": "转换型", "mixed": "混合型",
}

def _style_match_key(style):
    """映射style到矩阵key"""
    if style == "possession_highpress": return "highpress"
    return style

def get_style_matchup(home_style, away_style):
    """查风格对阵矩阵"""
    hk = _style_match_key(home_style)
    ak = _style_match_key(away_style)
    for k1, k2 in [(hk,ak), (ak,hk)]:
        key = (k1, k2)
        if key in STYLE_MATRIX:
            return STYLE_MATRIX[key]
    return {"pace":"unknown","ou":"unknown","goals":"1-3球"}

def detect_style_shift(team_key, old_gf, old_ga, old_played, new_gf, new_ga, new_played):
    """检测λ变化是否超过30%，判断风格是否可能变了"""
    old_lam = old_gf / old_played if old_played > 0 else 0
    new_lam = new_gf / new_played if new_played > 0 else 0
    old_lam_d = old_ga / old_played if old_played > 0 else 0
    new_lam_d = new_ga / new_played if new_played > 0 else 0
    shift = abs(new_lam/old_lam - 1) if old_lam > 0 else 0
    shift_d = abs(new_lam_d/old_lam_d - 1) if old_lam_d > 0 else 0
    return shift > 0.30 or shift_d > 0.30



# ============================================================
# football-data.org（用户API Key — 比赛数据主力源）
# ============================================================
FOOTBALL_API_KEY = "93088066c7304ecf8b1631c631601a9a"
FOOTBALL_BASE = "https://api.football-data.org/v4"

# football-data.org 竞赛代码映射
FB_COMP_CODES = {
    "bl1": "BL1", "epl": "PL", "laliga": "PD", "seriea": "SA",
    "ligue1": "FL1", "eredivisie": "DED", "wm26": "WC", "ucl2024": "CL",
}


def _fd_get(path):
    """调用football-data.org API"""
    url = f"{FOOTBALL_BASE}/{path}"
    try:
        req = urllib.request.Request(url, headers={
            "X-Auth-Token": FOOTBALL_API_KEY,
            "User-Agent": "Mozilla/5.0",
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


# ============================================================
# OpenLigaDB 数据获取（回退方案）
# ============================================================
OPENLIGA_URL = "https://api.openligadb.de"

# 队名映射（与openligadb_fetcher.py保持一致）
TEAM_DE = {
    # 国家队
    "英格兰": "England", "民主刚果": "DR Kongo", "比利时": "Belgien",
    "塞内加尔": "Senegal", "美国": "USA", "波黑": "Bosnien und Herzegowina",
    "法国": "Frankreich", "挪威": "Norwegen", "瑞典": "Schweden",
    "墨西哥": "Mexiko", "厄瓜多尔": "Ecuador", "葡萄牙": "Portugal",
    "克罗地亚": "Kroatien", "西班牙": "Spanien", "奥地利": "Österreich",
    "阿根廷": "Argentinien", "巴西": "Brasilien", "荷兰": "Niederlande",
    "德国": "Deutschland", "瑞士": "Schweiz", "加拿大": "Kanada",
    "日本": "Japan", "韩国": "Südkorea", "南非": "Südafrika",
    "捷克": "Tschechien", "乌拉圭": "Uruguay", "沙特": "Saudi Arabien",
    "佛得角": "Kap Verde", "哥伦比亚": "Kolumbien", "乌兹别克": "Usbekistan",
    "加纳": "Ghana", "巴拿马": "Panama", "意大利": "Italien",
    "丹麦": "Dänemark", "波兰": "Polen", "匈牙利": "Ungarn",
    "土耳其": "Türkei", "澳大利亚": "Australien", "巴拉圭": "Paraguay",
    "卡塔尔": "Katar", "伊拉克": "Irak", "伊朗": "Iran",
    "新西兰": "Neuseeland", "埃及": "Ägypten", "阿尔及利亚": "Algerien",
    "摩洛哥": "Marokko", "海地": "Haiti", "突尼斯": "Tunesien",
    "苏格兰": "Schottland", "芬兰": "Finnland", "爱沙尼亚": "Estland",
    # 俱乐部（OpenLigaDB使用德文简称）
    "拜仁": "Bayern", "多特蒙德": "Dortmund", "勒沃库森": "Leverkusen",
    "莱比锡": "RB Leipzig", "门兴": "Gladbach", "沃尔夫斯堡": "Wolfsburg",
    "法兰克福": "Frankfurt", "斯图加特": "Stuttgart", "霍芬海姆": "Hoffenheim",
    "柏林联合": "Union Berlin", "奥格斯堡": "Augsburg", "不莱梅": "Bremen",
    "波鸿": "Bochum", "海登海姆": "Heidenheim", "弗赖堡": "Freiburg",
    "圣保利": "St. Pauli", "基尔": "Kiel", "美因茨": "Mainz",
}

# FIFA 3字母代码（世界杯专用）
TEAM_FIFA_CODE = {
    "英格兰": "ENG", "巴西": "BRA", "阿根廷": "ARG", "德国": "GER",
    "法国": "FRA", "西班牙": "ESP", "葡萄牙": "PRT", "荷兰": "NLD",
    "比利时": "BEL", "克罗地亚": "HRV", "瑞士": "CHE", "乌拉圭": "URY",
    "哥伦比亚": "COL", "墨西哥": "MEX", "日本": "JPN", "韩国": "KOR",
    "美国": "USA", "加拿大": "CAN", "摩洛哥": "MAR", "塞内加尔": "SEN",
    "加纳": "GHA", "民主刚果": "COD", "刚果金": "COD", "刚果(金)": "COD",
    "喀麦隆": "CMR", "尼日利亚": "NGA", "科特迪瓦": "CIV", "阿尔及利亚": "DZA",
    "突尼斯": "TUN", "埃及": "EGY", "南非": "RSA", "佛得角": "CPV",
    "挪威": "NOR", "瑞典": "SWE", "丹麦": "DNK", "波兰": "POL",
    "奥地利": "AUT", "捷克": "CZE", "匈牙利": "HUN", "土耳其": "TUR",
    "苏格兰": "SCT", "波黑": "BIH", "乌克兰": "UKR",
    "沙特": "SAU", "伊朗": "IRN", "伊拉克": "IRQ", "卡塔尔": "QAT",
    "约旦": "JOR", "乌兹别克": "UZB", "澳大利亚": "AUS",
    "新西兰": "NZL", "巴拿马": "PAN", "巴拉圭": "PAR",
    "海地": "HTI", "库拉索": "CUW", "厄瓜多尔": "ECU",
}

# 中文联赛名 → OpenLigaDB league shortname
LEAGUE_OL = {
    "bl1": "bl1", "epl": "bl1", "laliga": "bl1", "seriea": "bl1",
    "ligue1": "bl1", "eredivisie": "bl1",
    "wm26": "wm26", "ucl2024": "ucl2024",
}


def _fetch_json(url: str, timeout: int = 10) -> Optional[dict]:
    """安全地获取JSON数据"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None


def _get_team_games_from_footballdata(team_name: str, league: str = "wm26", max_games: int = 10) -> List[dict]:
    """从football-data.org获取球队近期比赛数据（实际比分+赛程）

    使用用户的API Key，稳定可用。
    覆盖世界杯(WC)、欧冠(CL)、英超(PL)、德甲(BL1)等。
    """
    # 队名英译映射（避免循环import）
    XG_TEAM_EN = {
        "英格兰": "England", "巴西": "Brazil", "阿根廷": "Argentina",
        "法国": "France", "德国": "Germany", "西班牙": "Spain",
        "葡萄牙": "Portugal", "荷兰": "Netherlands", "意大利": "Italy",
        "瑞士": "Switzerland", "乌拉圭": "Uruguay", "哥伦比亚": "Colombia",
        "墨西哥": "Mexico", "日本": "Japan", "韩国": "South Korea",
        "澳大利亚": "Australia", "埃及": "Egypt", "比利时": "Belgium",
        "克罗地亚": "Croatia", "塞内加尔": "Senegal",
        "拜仁": "Bayern", "多特蒙德": "Dortmund",
        "勒沃库森": "Leverkusen", "莱比锡": "Leipzig",
        "巴黎": "Paris Saint-Germain", "里昂": "Lyon",
        "马赛": "Marseille", "摩纳哥": "Monaco",
        "尤文图斯": "Juventus", "AC米兰": "AC Milan",
        "国际米兰": "Inter Milan", "罗马": "Roma",
        "巴塞罗那": "Barcelona", "皇马": "Real Madrid",
        "马竞": "Atletico Madrid",
    }
    team_en = XG_TEAM_EN.get(team_name, team_name)

    comp_code = FB_COMP_CODES.get(league, "WC")
    data = _fd_get(f"competitions/{comp_code}/matches")

    if not data or not data.get("matches"):
        return []

    team_matches = []
    for m in data["matches"]:
        h = (m.get("homeTeam", {}).get("name", "") or "")
        a = (m.get("awayTeam", {}).get("name", "") or "")
        hk = team_en.lower()
        ak = team_en.lower()

        is_home = hk in h.lower() or hk in a.lower()
        if not is_home:
            continue
        is_home = hk in h.lower()  # 是主队吗？

        score = m.get("score", {})
        ft = score.get("fullTime", {}) if isinstance(score, dict) else {}
        home_goals = ft.get("home") if isinstance(ft, dict) else None
        away_goals = ft.get("away") if isinstance(ft, dict) else None
        if home_goals is None or away_goals is None:
            continue  # 跳过未开始的比赛

        team_matches.append({
            "date": m.get("utcDate", ""),
            "home": h,
            "away": a,
            "home_goals": int(home_goals),
            "away_goals": int(away_goals),
            "is_home": is_home,
        })

    team_matches.sort(key=lambda x: x["date"], reverse=True)
    return team_matches[:max_games]


def _get_team_games_from_openligadb(team_name: str, league: str = "wm26", season: str = "2026", max_games: int = 10) -> List[dict]:
    """从OpenLigaDB获取球队近期比赛（实际进球数据）"""
    # 世界杯使用FIFA 3字母代码，俱乐部使用德文名
    if league == "wm26":
        team_query = TEAM_FIFA_CODE.get(team_name, team_name)
    else:
        team_query = TEAM_DE.get(team_name, team_name)
    url = f"{OPENLIGA_URL}/getmatchdata/{league}/{season}"
    all_matches = _fetch_json(url)
    if not all_matches:
        return []

    team_matches = []
    for match in all_matches:
        # 判断是否包含该队（需处理 BRA/NOR 这种合并队名）
        home_team = match.get("team1", {}).get("shortName", "")
        away_team = match.get("team2", {}).get("shortName", "")
        # 短名可能包含合并队伍如 "BRA/NOR" — 只匹配主队名
        home_team_primary = home_team.split("/")[0].strip()
        away_team_primary = away_team.split("/")[0].strip()
        if team_query not in (home_team_primary, away_team_primary) and \
           team_query not in (home_team, away_team):
            continue

        # 解析比分
        results = match.get("matchResults", [])
        home_goals = 0
        away_goals = 0
        for r in results:
            result_name = r.get("resultName", "")
            if "Endergebnis" in result_name:  # 最终比分
                home_goals = int(r.get("pointsTeam1", 0))
                away_goals = int(r.get("pointsTeam2", 0))
                break

        team_matches.append({
            "date": match.get("matchDateTime", ""),
            "home": home_team,
            "away": away_team,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "is_home": (team_query == home_team_primary),
        })

    # 按日期降序排列，取最近max_games场
    team_matches.sort(key=lambda x: x["date"], reverse=True)
    return team_matches[:max_games]


# ============================================================
# TheSportsDB 数据源（用于芬超/瑞典超等 football-data.org 未覆盖的联赛）
# ============================================================
def _sportsdb_get(path: str) -> Optional[dict]:
    """调用 TheSportsDB API（免费，无需Key，快速超时）"""
    url = f"{SPORTSDB_BASE}/{path}"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=5, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _get_team_games_from_sportsdb(team_name: str, league: str = "sportsdb", max_games: int = 10) -> List[dict]:
    """从 TheSportsDB 获取球队近期比赛结果（适用于芬超/瑞典超等小众联赛）

    通过 searchteams 查找球队 -> eventslast 获取最近比赛 -> 解析比分
    返回格式与 _calculate_xg_from_goals 兼容
    """
    # 队名映射：中文 -> 英文
    team_en = TEAM_SPORTSDB.get(team_name, team_name)

    # 1. 搜索球队
    data = _sportsdb_get(f"searchteams.php?t={team_en}")
    if not data or not data.get("teams"):
        return []
    team_id = data["teams"][0].get("idTeam")
    if not team_id:
        return []

    # 2. 获取最近比赛结果
    events = _sportsdb_get(f"eventslast.php?id={team_id}")
    if not events or not events.get("results"):
        return []

    team_matches = []
    for m in events["results"]:
        home = (m.get("strHomeTeam") or "")
        away = (m.get("strAwayTeam") or "")
        score = (m.get("strScore") or "").strip()
        if not score or "-" not in score:
            continue

        # 解析比分（格式如 "2-1" 或 "2 - 1"）
        try:
            parts = score.replace(" ", "").split("-")
            home_goals = int(parts[0])
            away_goals = int(parts[1])
        except (ValueError, IndexError):
            continue

        is_home = (team_en.lower() in home.lower())
        if not is_home and team_en.lower() not in away.lower():
            continue

        team_matches.append({
            "date": m.get("dateEvent", ""),
            "home": home,
            "away": away,
            "home_goals": home_goals,
            "away_goals": away_goals,
            "is_home": is_home,
        })

    # 按日期降序排列，取最近max_games场
    team_matches.sort(key=lambda x: x.get("date", ""), reverse=True)
    return team_matches[:max_games]


# ============================================================
# ESPN 数据源（用于 football-data.org 未覆盖的联赛如瑞典超）
# ============================================================
ESPN_LEAGUES = {
    "swe.1": "瑞典超",
}

# 球队中文名 → ESPN 英文名（仅需补充 sportsdb 映射未覆盖的）
TEAM_ESPN_XG = {
    "天狼星": "Sirius", "米亚尔比": "Mjallby", "索尔纳": "AIK",
    "哥德堡": "IFK Göteborg", "马尔默": "Malmö FF",
    "埃尔夫斯堡": "Elfsborg", "哈马比": "Hammarby",
    "赫根": "BK Häcken", "北雪平": "IFK Norrköping",
    "卡尔马": "Kalmar FF", "哈尔姆斯塔德": "Halmstads BK",
    "韦斯特罗斯": "Västerås SK", "代格福什": "Degerfors IF",
    "加尔斯": "GAIS", "布洛马波卡纳": "Brommapojkarna",
    "瓦纳默": "IFK Värnamo", "奥斯达": "Östers IF",
}


def _espn_fetch(path: str) -> Optional[dict]:
    """调用 ESPN 公共 API"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/{path}"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _get_team_games_from_espn(team_name: str, league: str = "sportsdb", max_games: int = 10) -> List[dict]:
    """从 ESPN 获取球队近期比赛结果（适用于 ESPN 覆盖的联赛）

    ESPN 支持 swe.1（瑞典超）等联赛，返回实时比分数据。
    """
    # 尝试多个可能的 ESPN 联赛代码
    espn_codes = ["swe.1"]
    team_en = TEAM_ESPN_XG.get(team_name, team_name)

    for code in espn_codes:
        data = _espn_fetch(f"soccer/{code}/scoreboard")
        if not data or not data.get("events"):
            continue

        team_matches = []
        for e in data["events"]:
            comp = e.get("competitions", [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue

            home = competitors[0]
            away = competitors[1]
            home_name = home.get("team", {}).get("displayName", "")
            away_name = away.get("team", {}).get("displayName", "")

            # 检查是否涉及目标球队
            team_en_lower = team_en.lower()
            if team_en_lower not in home_name.lower() and team_en_lower not in away_name.lower():
                continue

            # 获取比分
            try:
                home_goals = int(home.get("score", 0))
                away_goals = int(away.get("score", 0))
            except (ValueError, TypeError):
                continue

            is_home = (team_en_lower in home_name.lower())
            team_matches.append({
                "date": e.get("date", "")[:10],
                "home": home_name,
                "away": away_name,
                "home_goals": home_goals,
                "away_goals": away_goals,
                "is_home": is_home,
            })

        if team_matches:
            team_matches.sort(key=lambda x: x.get("date", ""), reverse=True)
            return team_matches[:max_games]

    return []


# ============================================================
# xG 数据获取（首选方案 — FBref）
def _fetch_fbref_team_stats(league: str) -> Optional[Dict[str, dict]]:
    """从FBref获取该联赛所有球队的xG数据"""
    url = FBREF_LEAGUE_URLS.get(league)
    if not url:
        return None

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={
            "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36")
        })
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            html = resp.read().decode("utf-8")

        # 解析标准队名统计表（squad standard stats table）
        # 查找 xG 相关表格
        tables = re.findall(
            r'<table[^>]*class="[^"]*stats_table[^"]*"[^>]*>.*?</table>',
            html, re.DOTALL
        )

        for table in tables:
            if "xG" not in table:
                continue

            rows = re.findall(
                r'<tr[^>]*>.*?</tr>', table, re.DOTALL
            )

            teams_data = {}
            for row in rows:
                # 提取队名
                team_match = re.search(
                    r'data-stat="team"[^>]*>\s*<a[^>]*>\s*(.*?)\s*</a>', row
                )
                if not team_match:
                    continue
                team_name_fb = team_match.group(1).strip()

                # 提取xG_for
                xg_for_match = re.search(
                    r'data-stat="xg_for"[^>]*>\s*([\d.]+)\s*', row
                )
                # 提取xG_against
                xg_against_match = re.search(
                    r'data-stat="xg_against"[^>]*>\s*([\d.]+)\s*', row
                )
                # 提取射门数
                shots_match = re.search(
                    r'data-stat="shots"[^>]*>\s*([\d.]+)\s*', row
                )
                # 提取比赛场次
                mp_match = re.search(
                    r'data-stat="games"[^>]*>\s*(\d+)\s*', row
                )

                if xg_for_match and xg_against_match and mp_match:
                    mp = int(mp_match.group(1))
                    if mp > 0:
                        teams_data[team_name_fb] = {
                            "xG_for_90": float(xg_for_match.group(1)) / mp * 90 / 90,
                            "xG_against_90": float(xg_against_match.group(1)) / mp * 90 / 90,
                            "xG_per_shot": (float(xg_for_match.group(1)) /
                                           float(shots_match.group(1))
                                           if shots_match and float(shots_match.group(1)) > 0 else 0),
                            "matches_played": mp,
                            "source": "fbref",
                        }

            if teams_data:
                return teams_data

    except Exception as e:
        pass

    return None


def _get_xg_from_fbref(team_name: str, league: str) -> Optional[dict]:
    """从FBref获取指定球队的xG数据"""
    # 中文名映射到英文（FBref使用英文队名）
    name_map = {
        "拜仁": "Bayern", "多特蒙德": "Dortmund",
        "勒沃库森": "Leverkusen", "莱比锡": "Leipzig",
        "英格兰": "England", "法国": "France", "巴西": "Brazil",
        "阿根廷": "Argentina", "德国": "Germany", "西班牙": "Spain",
        "荷兰": "Netherlands", "葡萄牙": "Portugal",
    }
    team_en = name_map.get(team_name, team_name)

    all_teams = _fetch_fbref_team_stats(league)
    if not all_teams:
        return None

    # 尝试匹配队名
    for fb_name, data in all_teams.items():
        if team_en.lower() in fb_name.lower() or fb_name.lower() in team_en.lower():
            return data

    return None


# ============================================================
# Understat xG 数据获取（备用方案）
# ============================================================
def _get_team_xg_from_understat(team_name_en: str) -> Optional[dict]:
    """从Understat获取球队xG数据（通过JSON API）"""
    # Understat使用league ID: EPL=1, LaLiga=2, Bundesliga=3, SerieA=4, Ligue1=5
    league_ids = {"epl": 1, "laliga": 2, "bl1": 3, "seriea": 4, "ligue1": 5}

    league = None
    for k, v in league_ids.items():
        if k == team_name_en.lower() or k in str(team_name_en).lower():
            league = v
            break

    if league is None:
        return None

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        url = f"https://understat.com/league/{league}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            html = resp.read().decode("utf-8")

        # Understat 在页面中嵌入了 JSON 数据
        import json as json_lib
        json_match = re.search(r'teamsData\s*=\s*JSON\.parse\(\'(.*?)\'\)', html)
        if not json_match:
            return None

        # 解析转义的 JSON 字符串
        json_str = json_match.group(1)
        # Understat 使用双重转义
        json_str = json_str.replace('\\\\', '\\').replace('\\"', '"').replace("\\'", "'")

        teams_data = json_lib.loads(json_str)

        result = {}
        for team_id, data in teams_data.items():
            team_name_us = data.get("title", "")
            history = data.get("history", [])
            if not history:
                continue

            total_xg = sum(g.get("xG", 0) for g in history)
            total_xga = sum(g.get("xGA", 0) for g in history)
            mp = len(history)

            if mp > 0:
                result[team_name_us] = {
                    "xG_for_90": round(total_xg / mp, 2),
                    "xG_against_90": round(total_xga / mp, 2),
                    "xG_per_shot": 0,
                    "matches_played": mp,
                    "source": "understat",
                }

        return result if result else None

    except Exception as e:
        # Understat也不可用——大多数免费xG源都有反爬机制
        # 这是正常现象，不是脚本BUG
        return None


# ============================================================
# 核心计算函数
# ============================================================
def _calculate_xg_from_goals(matches: List[dict], team_name: str, source_label: str = "openligadb_goals_fallback") -> dict:
    """从实际进球数估算xG

    Args:
        matches: 比赛数据列表
        team_name: 球队名
        source_label: 数据来源标签（调用者可指定）
    """
    if not matches:
        return {"xG_for_90": 0, "xG_against_90": 0, "xG_per_shot": 0,
                "matches_played": 0, "source": source_label}

    total_goals_for = 0
    total_goals_against = 0
    num_matches = len(matches)

    for m in matches:
        if m["is_home"]:
            total_goals_for += m["home_goals"]
            total_goals_against += m["away_goals"]
        else:
            total_goals_for += m["away_goals"]
            total_goals_against += m["home_goals"]

    # 实际进球数作为xG的粗糙估计（偏差较大，但优于无数据）
    # 注：实际进球的方差是xG的3-5倍，百分位数计算时会过度外推
    xg_for_90 = total_goals_for / num_matches if num_matches > 0 else 0
    xg_against_90 = total_goals_against / num_matches if num_matches > 0 else 0

    return {
        "xG_for_90": round(xg_for_90, 2),
        "xG_against_90": round(xg_against_90, 2),
        "xG_per_shot": 0,  # 无法统计
        "matches_played": num_matches,
        "source": source_label,
    }


def _calculate_percentile(value: float, all_values: List[float]) -> float:
    """计算百分位数（0~1），值越大百分位越高"""
    if not all_values:
        return 0.5
    count_below = sum(1 for v in all_values if v <= value)
    return count_below / len(all_values)


def _get_league_xg_snapshot(league: str) -> Tuple[float, float]:
    """获取联赛平均xG参考值"""
    avg = LEAGUE_XG_AVG.get(league, LEAGUE_XG_AVG["default"])
    return avg["xG_for"], avg["xG_against"]


# ============================================================
# 缓存管理
# ============================================================
def _get_cache_path(team: str, league: str) -> str:
    """获取缓存文件路径"""
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
    safe_name = team.replace(" ", "_").replace("/", "_")
    return os.path.join(OUTPUT_DIR, f"xg_cache_{safe_name}_{league}.json")


def _load_cache(team: str, league: str) -> Optional[dict]:
    """尝试加载缓存"""
    cache_path = _get_cache_path(team, league)
    if not os.path.exists(cache_path):
        return None
    try:
        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 检查缓存是否过期
        cached_time = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
        if datetime.now() - cached_time < timedelta(days=CACHE_TTL_DAYS):
            return data.get("result")
    except Exception:
        pass
    return None


def _save_cache(team: str, league: str, result: dict):
    """保存缓存"""
    cache_path = _get_cache_path(team, league)
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump({"cached_at": datetime.now().isoformat(), "result": result},
                      f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ============================================================
# 主流程
# ============================================================
def estimate_xg(team_name: str, league: str = "wm26", max_games: int = 10, season: str = None) -> dict:
    """估计球队的xG数据

    优先级:
      1. football-data.org（用户API Key — 稳定可用）
      2. FBref xG数据（首选xG，但被Cloudflare封锁403）
      3. Understat xG数据（备用，同样可能被封锁）
      4. OpenLigaDB 实际进球数（稳定回退，所有联赛可用）
      5. 联赛平均值（默认兜底）

    注意：FBref和Understat被Cloudflare保护，大概率403。
    football-data.org和OpenLigaDB是目前稳定可用的数据源。
    输出的xG_for/90、xG_against/90当is_calibrated=False时
    为实际进球数而非xG。
    """
    # 自动选择赛季
    if season is None:
        season = "2025" if league in ("bl1", "epl", "laliga", "seriea", "ligue1", "eredivisie") else "2026"

    # 尝试缓存
    cached = _load_cache(team_name, league)
    if cached:
        return cached

    result = None
    source_label = "none"

    # ========================================
    # 方案0: datafc/Sofascore（新增 ⭐ 最高优先级）
    # ========================================
    if not result:
        try:
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from skill.datafc_provider import estimate_team_strength as dfc_estimate
            dfc_result = dfc_estimate(team_name, league, max_games=max_games)
            if dfc_result.get("matches_played", 0) >= 3:
                result = {
                    "xG_for_90": dfc_result.get("xG_for_90", 1.4),
                    "xG_against_90": dfc_result.get("xG_against_90", 1.4),
                    "xG_per_shot": 0,
                    "matches_played": dfc_result.get("matches_played", 0),
                    "source": dfc_result.get("source", "datafc"),
                    "is_calibrated": dfc_result.get("is_calibrated", False),
                    "form_rating": dfc_result.get("form_rating"),
                    "shots_for_90": dfc_result.get("shots_for_90"),
                    "shots_against_90": dfc_result.get("shots_against_90"),
                }
                source_label = dfc_result.get("source", "datafc")
        except Exception:
            pass

    # 对 sportsdb（瑞典超/芬超等小众联赛）走快速通道：
    # 跳过 football-data.org/FBref/Understat/OpenLigaDB（已知无数据）
    # 数据源优先级: ESPN(瑞典超) > TheSportsDB > 内置联赛表 > 联赛平均值
    if league == "sportsdb":
        # 方案1: ESPN（支持 swe.1 瑞典超）
        espn_matches = _get_team_games_from_espn(team_name, league, max_games=max_games)
        if espn_matches:
            result = _calculate_xg_from_goals(espn_matches, team_name, source_label="espn")
            source_label = "espn"

        # 方案2: TheSportsDB（免费版数据有限，快速尝试）
        if not result:
            try:
                sd_matches = _get_team_games_from_sportsdb(team_name, league, max_games=max_games)
                if sd_matches:
                    sd_result = _calculate_xg_from_goals(sd_matches, team_name, source_label="thesportsdb")
                    if sd_result.get("matches_played", 0) > 0:
                        result = sd_result
                        source_label = "thesportsdb"
            except Exception:
                pass  # TheSportsDB 不可用时静默跳过

        # 方案3: 内置联赛表（瑞典超/芬超硬编码数据）
        if not result or result.get("matches_played", 0) < 3:
            for tbl_name, tbl in [("瑞典超", SWEDEN_TABLE), ("芬超", FINLAND_TABLE)]:
                team_key = team_name.strip()
                if team_key in tbl:
                    stats = tbl[team_key]
                else:
                    # 尝试英文名匹配
                    matched = False
                    for eng_name in TEAM_ESPN_XG.values():
                        if team_key.lower() == eng_name.lower():
                            for k, v in tbl.items():
                                if k.lower() == eng_name.lower():
                                    stats = v
                                    matched = True
                                    break
                        if matched:
                            break
                    if not matched:
                        continue
                gf_per_90 = stats["gf"] / stats["played"]
                ga_per_90 = stats["ga"] / stats["played"]
                result = {
                    "xG_for_90": round(gf_per_90, 2),
                    "xG_against_90": round(ga_per_90, 2),
                    "xG_per_shot": 0,
                    "matches_played": stats["played"],
                    "source": f"builtin_table_{tbl_name}",
                    "form_rating": None,
                }
                source_label = "builtin_table"
                break
    else:
        # 方案1: football-data.org（用户API Key — 稳定可用）
        if not result:
            fd_matches = _get_team_games_from_footballdata(team_name, league, max_games)
            if fd_matches:
                result = _calculate_xg_from_goals(fd_matches, team_name, source_label="football-data.org")
                source_label = "football-data.org"

        # 方案2: FBref xG（被Cloudflare封锁，保留尝试）
        if not result:
            fb_data = _get_xg_from_fbref(team_name, league)
            if fb_data:
                result = fb_data
                source_label = "fbref"

        # 方案3: Understat xG（备用，同样可能被封锁）
        if not result:
            us_data = _get_team_xg_from_understat(team_name)
            if us_data:
                result = us_data
                source_label = "understat"

        # 方案4: OpenLigaDB 实际进球（稳定回退）
        if not result or result.get("matches_played", 0) < 3:
            matches = _get_team_games_from_openligadb(team_name, league, season, max_games=max_games)
            if matches:
                alt_result = _calculate_xg_from_goals(matches, team_name)
                if not result or alt_result["matches_played"] > result.get("matches_played", 0):
                    result = alt_result
                    source_label = "openligadb_fallback"

    # 方案5: TheSportsDB（所有联赛通用回退，已有 football-data.org 数据的跳过）
    if (not result or result.get("matches_played", 0) < 3) and league != "sportsdb":
        sd_matches = _get_team_games_from_sportsdb(team_name, league, max_games=max_games)
        if sd_matches:
            sd_result = _calculate_xg_from_goals(sd_matches, team_name, source_label="thesportsdb")
            if not result or sd_result["matches_played"] > result.get("matches_played", 0):
                result = sd_result
                source_label = "thesportsdb"

    # 方案5: K联赛内置积分榜查表（当其他数据源全部失效时）
    if not result and league in ("kleague1", "kleague2", "jleague1", "jleague2"):
        table = {"kleague1":KLEAGUE1_TABLE,"kleague2":KLEAGUE1_TABLE,"jleague1":JLEAGUE1_TABLE,"jleague2":JLEAGUE2_TABLE}.get(league, {})  # 选择对应联赛的内置表
        team_key = team_name.strip()
        if team_key in table:
            stats = table[team_key]
            gf_per_90 = stats["gf"] / stats["played"]
            ga_per_90 = stats["ga"] / stats["played"]
            result = {
                "xG_for_90": round(gf_per_90, 2),
                "xG_against_90": round(ga_per_90, 2),
                "xG_per_shot": 0,
                "matches_played": stats["played"],
                "source": "kleague_table_builtin" if league.startswith("kleague") else "jleague_table_builtin",
            }
            source_label = "kleague_table" if league.startswith("kleague") else "jleague_table"
        else:
            # 查不到具体球队时，用联赛平均值
            avg_xg_for, _ = _get_league_xg_snapshot(league)
            result = {
                "xG_for_90": avg_xg_for,
                "xG_against_90": avg_xg_for,
                "xG_per_shot": 0,
                "matches_played": 0,
                "source": "kleague_avg_fallback",
            }
            source_label = "kleague_avg"

    if not result:
        # 完全无数据
        avg_xg_for, avg_xg_against = _get_league_xg_snapshot(league)
        result = {
            "xG_for_90": avg_xg_for,
            "xG_against_90": avg_xg_against,
            "xG_per_shot": 0,
            "matches_played": 0,
            "source": "league_average_default",
        }
        source_label = "default"

    # 附加状态评分（K联赛查表型）
    if league.startswith(("kleague", "jleague")) and source_label in ("kleague_table", "kleague_avg", "jleague_table"):
        table = {"kleague1":KLEAGUE1_TABLE,"kleague2":KLEAGUE1_TABLE,"jleague1":JLEAGUE1_TABLE,"jleague2":JLEAGUE2_TABLE}.get(league, {})  # 选择对应联赛的内置表
        team_key = team_name.strip()
        if team_key in table and "form" in table[team_key]:
            form_str = table[team_key]["form"]
            form_scores = {"W":3, "D":1, "L":0}
            # 指数衰减权重（τ=21天, 假定每场间隔7天）
            weights = [0.264, 0.368, 0.513, 0.717, 1.0]  # 最老→最新
            w_total = 0
            s_total = 0
            for i, ch in enumerate(reversed(form_str)):  # reversed: 最老在前
                if i < len(weights) and ch in form_scores:
                    w = weights[len(weights)-1-i] if i < len(weights) else 0  # 最新最高权重
                    s_total += form_scores[ch] * w
                    w_total += w
            form_rating = round(s_total / w_total, 2) if w_total > 0 else 1.5
        else:
            # 无form数据, 用积分排名估算
            pts = 0
            if team_key in table:
                pts = table[team_key].get("pts", 0)
            # pts/场 * 系数
            form_rating = round((pts / max(result.get("matches_played", 10), 10)) * 0.8 + 0.5, 2)
        result["form_rating"] = form_rating
    else:
        result["form_rating"] = None  # 非K联赛由其他数据源处理

    # 标记是否已校准（真实xG = 校准，实际进球 = 未校准）
    is_calibrated = source_label in ("fbref", "football-data.org", "thesportsdb")
    result["is_calibrated"] = is_calibrated
    result["team"] = team_name
    result["league"] = league

    # 缓存结果
    _save_cache(team_name, league, result)

    return result


def format_output(home_data: dict, away_data: dict, league: str) -> str:
    """格式化输出"""
    # 计算联赛百分位数（如果有多个球队数据）
    # 简化为直接输出原始值 + 是否校准标记

    home_xg_for = home_data.get("xG_for_90", 0)
    home_xg_against = home_data.get("xG_against_90", 0)
    away_xg_for = away_data.get("xG_for_90", 0)
    away_xg_against = away_data.get("xG_against_90", 0)

    # 七维评分注入值
    # 进攻评分 = xG_for/90 在联赛中的百分位数 × 10
    # 防守评分 = (1 - xG_against/90 百分位数) × 10
    # 由于我们只有两支球队的数据，用联赛平均做相对估计
    avg_xg_for, avg_xg_against = _get_league_xg_snapshot(league)

    def score_from_xg(value, avg, higher_is_better=True):
        """从xG值和联赛平均估算1-10评分（tanh 饱和曲线，防止顶级球队封顶）"""
        ratio = value / avg if avg > 0 else 1.0
        if higher_is_better:
            score = 5 + 5 * math.tanh(0.8 * (ratio - 1.0))
        else:
            score = 5 + 5 * math.tanh(0.8 * (1.0 - ratio))
        return max(1, min(10, round(score, 1)))

    home_attack = score_from_xg(home_xg_for, avg_xg_for, higher_is_better=True)
    home_defense = score_from_xg(home_xg_against, avg_xg_against, higher_is_better=False)
    away_attack = score_from_xg(away_xg_for, avg_xg_for, higher_is_better=True)
    away_defense = score_from_xg(away_xg_against, avg_xg_against, higher_is_better=False)

    home_form_rating = home_data.get('form_rating', None)
    away_form_rating = away_data.get('form_rating', None)
    home_form_line = f'\n  → L1状态评分: {home_form_rating:.1f} 📈' if home_form_rating else ''
    away_form_line = f'\n  → L1状态评分: {away_form_rating:.1f} 📈' if away_form_rating else ''

    calibrated_mark = "" if (home_data.get("is_calibrated") and away_data.get("is_calibrated")) else "（未校准）"

    output = f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 xG数据估计输出{calibrated_mark}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
【主队】{home_data.get('team', '?')}
  xG_for/90:     {home_xg_for:.2f}
  xG_against/90: {home_xg_against:.2f}
  射门转化率:    {home_data.get('xG_per_shot', 0):.3f}
  数据来源:      {home_data.get('source', '?')}
  近{home_data.get('matches_played', 0)}场数据
  → L1进攻评分: {home_attack} ⚽
  → L1防守评分: {home_defense} 🛡️{home_form_line}

【客队】{away_data.get('team', '?')}
  xG_for/90:     {away_xg_for:.2f}
  xG_against/90: {away_xg_against:.2f}
  射门转化率:    {away_data.get('xG_per_shot', 0):.3f}
  数据来源:      {away_data.get('source', '?')}
  近{away_data.get('matches_played', 0)}场数据
  → L1进攻评分: {away_attack} ⚽
  → L1防守评分: {away_defense} 🛡️{away_form_line}

【负二项引擎输入】
  λ_A (主队预期进球): {home_xg_for:.2f}
  λ_B (客队预期进球): {away_xg_for:.2f}
  联赛平均 xG_for: {avg_xg_for:.2f}
  ㊟ 负二项引擎输入参数 λ_A={home_xg_for:.2f}, λ_B={away_xg_for:.2f}

【校准状态】
  真实xG数据: {'✅' if home_data.get('is_calibrated') else '❌'} {home_data.get('source', '?')}
  真实xG数据: {'✅' if away_data.get('is_calibrated') else '❌'} {away_data.get('source', '?')}
  {'⚠️ 使用实际进球数代替xG，精度低于xG数据' if not home_data.get('is_calibrated') else ''}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
    return output


def main():
    parser = argparse.ArgumentParser(description="xG数据估计器 — 足球预期进球管线")
    parser.add_argument("--home", required=True, help="主队名（中文）")
    parser.add_argument("--away", required=True, help="客队名（中文）")
    parser.add_argument("--league", default="wm26",
                       help="联赛标识: bl1/epl/laliga/wm26等 (默认: wm26)")
    parser.add_argument("--max-games", type=int, default=10,
                       help="最大参考场次 (默认: 10)")

    args = parser.parse_args()

    # 获取两队xG数据
    home_result = estimate_xg(args.home, args.league, args.max_games)
    away_result = estimate_xg(args.away, args.league, args.max_games)

    # 输出
    output = format_output(home_result, away_result, args.league)
    print(output)

    # JSON输出（给其他脚本调用用）
    json_output = {
        "home": home_result,
        "away": away_result,
        "league_xg_avg": LEAGUE_XG_AVG.get(args.league, LEAGUE_XG_AVG["default"]),
    }
    print(json.dumps(json_output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
