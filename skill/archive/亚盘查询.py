#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
亚盘/欧赔实时数据查询工具 - 使用curl（更稳定）
用法: python 亚盘查询.py "挪威"
      不加参数则列出所有世界杯比赛
"""
import json, subprocess, sys

API_KEY = "33981e151ca87be10db961395d6a2ff963602d60a7dd7b421b046295b614e8c3"
BASE = "https://api.odds-api.io/v3"

def curl_get(path):
    separator = "&" if "?" in path else "?"
    url = f"{BASE}{path}{separator}apiKey={API_KEY}"
    try:
        r = subprocess.run(
            ["curl", "-s", "--max-time", "15", url],
            capture_output=True, text=True, timeout=20
        )
        return json.loads(r.stdout)
    except Exception as e:
        print(f"[错误] {e}")
        return None

LEAGUES = {
    "wm26": "international-fifa-world-cup",
    "kleague1": "republic-of-korea-k-league-1",
    "kleague2": "republic-of-korea-k-league-2",
    "sweden": "sweden-allsvenskan",
}

TEAM_CN = {
    # K League 1 中文 -> 英文
    "全北现代": "Jeonbuk", "全北": "Jeonbuk",
    "江原FC": "Gangwon", "江原": "Gangwon",
    "安养FC": "FC Anyang", "安养": "FC Anyang",
    "浦项制铁": "Pohang Steelers", "浦项": "Pohang Steelers",
    "大田市民": "Daejeon Citizen", "大田": "Daejeon Citizen",
    "富川FC": "Bucheon", "富川": "Bucheon",
    "蔚山HD": "Ulsan HD", "蔚山": "Ulsan HD",
    "首尔FC": "Seoul", "首尔": "Seoul",
    "仁川联": "Incheon Utd", "仁川": "Incheon Utd",
    "光州FC": "Gwangju", "光州": "Gwangju",
    "金泉尚武": "Gimcheon Sangmu", "金泉": "Gimcheon Sangmu",
    "济州SK": "Jeju SK", "济州": "Jeju SK",
}

def find_event(home_kw, away_kw="", league="wm26"):
    league_slug = LEAGUES.get(league, league)
    # 中文队名 -> 英文
    home_en = TEAM_CN.get(home_kw, home_kw)
    away_en = TEAM_CN.get(away_kw, away_kw) if away_kw else ""
    events = curl_get(f"/events?sport=football&league={league_slug}")
    if not events or not isinstance(events, list): return None
    for e in events:
        if not isinstance(e, dict): continue
        h, a = (e.get("home","") or "").lower(), (e.get("away","") or "").lower()
        hk, ak = home_en.lower(), away_en.lower()
        if hk in h or hk in a:
            if not ak or ak in h or ak in a:
                return (e["id"], e.get("home",""), e.get("away",""), (e.get("date","") or "")[:19])
    return None

def query(home_kw, away_kw="", league="wm26"):
    info = find_event(home_kw, away_kw, league)
    if not info:
        print(f"未找到比赛: {home_kw} vs {away_kw}")
        return

    eid, h_name, a_name, dt = info
    print(f"\n{'='*60}")
    print(f"  {h_name} vs {a_name}  |  {dt}")
    print(f"{'='*60}")

    for bm in ["Bet365"]:
        data = curl_get(f"/odds?eventId={eid}&bookmakers={bm}")
        if not data: continue
        if isinstance(data, dict): data = [data]
        for match in data:
            bms = match.get("bookmakers", {})
            if bm not in bms: continue
            print(f"\n【{bm}】")
            for m in bms[bm]:
                mk, odds = m.get("name",""), m.get("odds",[])
                if mk == "ML" and odds:
                    o = odds[0]
                    print(f"  欧赔: {o.get('home','-')}  /  {o.get('draw','-')}  /  {o.get('away','-')}")
                elif mk == "Spread":
                    for s in odds:
                        pt = s.get("hdp",""); h = s.get("home","-"); a = s.get("away","-")
                        if h != "-" and a != "-": print(f"  亚盘: {h_name} +{pt} @ {h}  |  {a_name} -{pt} @ {a}")
                elif mk == "Totals":
                    for t in odds:
                        pt = t.get("hdp",""); ov = t.get("over","-"); un = t.get("under","-")
                        if ov != "-" and un != "-": print(f"  大小球: 大{pt} @ {ov}  |  小{pt} @ {un}")
                elif mk == "Goals Over/Under" and odds:
                    t = odds[0]; pt = t.get("hdp","")
                    print(f"  大小球({pt}): 大@{t.get('over','-')} 小@{t.get('under','-')}")
                elif mk == "Both Teams To Score" and odds:
                    o = odds[0]; print(f"  双方进球: 是 @ {o.get('yes','-')}  |  否 @ {o.get('no','-')}")

    # Also show 1xbet for more detailed Asian lines
    for bm in ["1xbet"]:
        data = curl_get(f"/odds?eventId={eid}&bookmakers={bm}")
        if not data: continue
        if isinstance(data, dict): data = [data]
        for match in data:
            bms = match.get("bookmakers", {})
            if bm not in bms: continue
            print(f"\n【{bm}（详细亚盘）】")
            for m in bms[bm]:
                mk, odds = m.get("name",""), m.get("odds",[])
                if mk == "ML" and odds:
                    o = odds[0]; print(f"  欧赔: {o.get('home','-')} / {o.get('draw','-')} / {o.get('away','-')}")
                elif mk == "Spread":
                    lines = [(s.get("hdp",""), s.get("home","-"), s.get("away","-")) for s in odds]
                    # Print most relevant lines (near even money)
                    for pt, h_od, a_od in lines:
                        try:
                            if h_od != "-" and a_od != "-":
                                hv, av = float(h_od), float(a_od)
                                if 1.2 <= hv <= 5.0 or 1.2 <= av <= 5.0:
                                    print(f"  亚盘: +{pt} @ {h_od}  |  -{pt} @ {a_od}")
                        except: pass
                elif mk == "Goals Over/Under":
                    for t in odds:
                        pt = t.get("hdp",""); ov = t.get("over","-"); un = t.get("under","-")
                        try:
                            if float(ov) < 5.0 and float(un) < 5.0:
                                print(f"  大小球({pt}球): 大@{ov} 小@{un}")
                        except: pass
                elif mk == "Both Teams To Score" and odds:
                    o = odds[0]; print(f"  双方进球: 是 @ {o.get('yes','-')}  |  否 @ {o.get('no','-')}")

if __name__ == "__main__":
    league = "wm26"
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    flags = [a for a in sys.argv[1:] if a.startswith('--')]
    for f in flags:
        if f == '--kleague':
            league = "kleague1"
        elif f.startswith('--league='):
            league = f.split('=')[1]
    home = args[0] if len(args) >= 1 else ""
    away = args[1] if len(args) >= 2 else ""
    if home:
        query(home, away, league)
    else:
        league_slug = LEAGUES.get(league, league)
        events = curl_get(f"/events?sport=football&league={league_slug}")
        if events and isinstance(events, list):
            pending = [e for e in events if isinstance(e, dict) and e.get('status') == 'pending']
            league_name = {"wm26":"世界杯","kleague1":"K1联赛","kleague2":"K2联赛"}.get(league, league)
            print(f"\n{league_name} 赛程 ({len(pending)} 场未赛)")
            for e in pending:
                d = (e.get("date","") or "")[:19]
                print(f"  {e.get('home',''):25s} vs {e.get('away',''):25s}  {d}")
