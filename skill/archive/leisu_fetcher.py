#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
雷速体育数据采集器 v1.0
用途: 获取K联赛赔率+统计+H2H数据（替代iSports API缺失的模块）
数据流: leisu_fetcher → System 1(七维评分) → System 2(+EV计算)

当前状态: 使用 odds-api.io 作为主要数据源，Leisu API预留接口
待Playwright安装完成后，启用 Canvas Hook 模式获取更详细数据
"""
import json, subprocess, os, re

ODDS_API_KEY = "33981e151ca87be10db961395d6a2ff963602d60a7dd7b421b046295b614e8c3"
LEAGUES = {
    "kleague1": "republic-of-korea-k-league-1",
}

# ============================================================
# 核心功能: 获取K联赛赔率+赛程（已可用）
# 数据源: odds-api.io（已验证通过）
# ============================================================
def get_odds(home_team, away_team, league="kleague1"):
    """获取一场比赛的赔率数据（主数据源: odds-api.io）"""
    league_slug = LEAGUES.get(league, league)

    # 查找比赛
    r = subprocess.run(['curl','-s','--max-time','12',
        f'https://api.odds-api.io/v3/events?sport=football&league={league_slug}&apiKey={ODDS_API_KEY}'],
        capture_output=True, timeout=15)
    events = json.loads(r.stdout)
    if not isinstance(events, list):
        return {"error": "无法获取比赛列表"}

    match = None
    for e in events:
        h = (e.get('home','') or '').lower()
        a = (e.get('away','') or '').lower()
        hk = home_team.lower()
        ak = away_team.lower()
        if (hk in h and ak in a) or (hk in a and ak in h):
            match = e
            break

    if not match:
        return {"error": f"未找到比赛: {home_team} vs {away_team}"}

    eid = match['id']
    result = {
        "match_id": eid,
        "home": match.get('home'),
        "away": match.get('away'),
        "status": match.get('status'),
        "odds": {},
    }

    # 获取赔率（仅对未开始的比赛有效）
    if match.get('status') == 'pending':
        r2 = subprocess.run(['curl','-s','--max-time','10',
            f'https://api.odds-api.io/v3/odds?eventId={eid}&bookmakers=Bet365&apiKey={ODDS_API_KEY}'],
            capture_output=True, timeout=12)
        odds_data = json.loads(r2.stdout)
        # odds-api.io返回格式: 如果有赔率，返回 [{"bookmakers": {...}}]
        # 如果没有赔率，返回 {"id": ..., "home": ..., "status": "pending"}
        if isinstance(odds_data, list) and odds_data:
            bms = odds_data[0].get('bookmakers', {})
            for bm, markets in bms.items():
                for m in markets:
                    mk = m.get('name','')
                    odds = m.get('odds',[])
                    if mk == 'ML' and odds:
                        o = odds[0]
                        result["odds"]["1x2"] = {"home": o.get('home'), "draw": o.get('draw'), "away": o.get('away')}
                    elif mk == 'Spread':
                        result["odds"]["asian"] = []
                        for s in odds:
                            result["odds"]["asian"].append({"hdp": s.get('hdp'), "home": s.get('home'), "away": s.get('away')})
                    elif mk in ('Totals','Goals Over/Under'):
                        if "ou" not in result["odds"]:
                            result["odds"]["ou"] = []
                        for t in odds:
                            result["odds"]["ou"].append({"line": t.get('hdp'), "over": t.get('over'), "under": t.get('under')})

    return result

def get_league_matches(league="kleague1"):
    """获取联赛全部赛程"""
    league_slug = LEAGUES.get(league, league)
    r = subprocess.run(['curl','-s','--max-time','12',
        f'https://api.odds-api.io/v3/events?sport=football&league={league_slug}&apiKey={ODDS_API_KEY}'],
        capture_output=True, timeout=15)
    events = json.loads(r.stdout)
    if not isinstance(events, list):
        return []
    return [{"home": e.get('home'), "away": e.get('away'), "date": e.get('date'), "status": e.get('status')} for e in events]


# ============================================================
# Leisu API 接口（预留，待激活）
# 当前状态: 占位。Leisu的API需要sign签名+解密响应数据
# 待以下条件满足后启用：
#   1. Playwright安装完成（pip install playwright && playwright install chromium）
#   2. 或者逆向得到sign算法
# ============================================================
def fetch_leisu_match(match_id):
    """从Leisu获取比赛详情（预留）"""
    # TODO: 实现Leisu API调用
    # API端点: https://api.leisu.com/api/match/detail/{match_id}
    # 需要: sign参数 + 解密响应(base64+zlib+字母翻转)
    return {"error": "Leisu API未激活，请先安装Playwright"}

def fetch_leisu_odds(match_id):
    """从Leisu获取赔率（预留）"""
    return {"error": "Leisu API未激活"}

def fetch_leisu_h2h(team1_id, team2_id):
    """从Leisu获取历史交锋（预留）"""
    return {"error": "Leisu API未激活"}


# ============================================================
# 中国队名 → Leisu队名映射（完善中）
# ============================================================
TEAM_LEISU = {
    "全北现代": "全北现代",
    "江原FC": "江原FC",
    "安养FC": "FC安养",
    "浦项制铁": "浦项制铁",
    "大田市民": "大田市民",
    "富川FC": "富川FC",
}


# ============================================================
# 命令行接口
# ============================================================
if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 3:
        result = get_odds(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) >= 4 else "kleague1")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        matches = get_league_matches()
        print(f"K League 1 赛程: {len(matches)}场")
        for m in matches[:10]:
            print(f"  {m['home']:25s} vs {m['away']:25s}")
