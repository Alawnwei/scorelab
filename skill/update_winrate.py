#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ 赢盘率自动更新工具 v3.0

智能区分联赛 vs 杯赛模式:
  - 联赛模式: 关注近期状态(默认近6轮)，看近期赢盘趋势
  - 杯赛模式: 自动查该队在同赛事历届数据(如世界杯查近3届)

数据流:
  1. OpenLigaDB → 历史比分（稳定免费）
  2. odds-api.io → 让球盘口（仅有实时数据时有效）
  3. 无盘口时: 比分差智能估算
  4. 手动模式: 人工输入精确盘口

用法:
  python update_winrate.py --team "英格兰"                    自动识别联赛/杯赛
  python update_winrate.py --team "利物浦" --league epl       英超(近6轮)
  python update_winrate.py --team "拜仁" --league bl1         德甲(近6轮)
  python update_winrate.py --team "英格兰" --detail           显示明细
  python update_winrate.py --team "英格兰" --manual-hdp       手动输入盘口
  python update_winrate.py --team "英格兰" --update-db        更新 winrate_db.py
  python update_winrate.py --team "英格兰" --history-cup      查历届世界杯数据(杯赛专用)
  python update_winrate.py --list                             列出可用联赛
"""

import json, sys, os, re, urllib.request, ssl, subprocess
from datetime import datetime
from collections import defaultdict
from typing import Optional, List, Dict, Tuple

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
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
WINRATE_DB_PATH = os.path.join(BASE_DIR, "skill", "winrate_db.py")
os.makedirs(CACHE_DIR, exist_ok=True)

ODDS_API_KEY = "33981e151ca87be10db961395d6a2ff963602d60a7dd7b421b046295b614e8c3"
ODDS_API_BASE = "https://api.odds-api.io/v3"

# ============================================================
# 赛事分类: 联赛 vs 杯赛
# ============================================================
# 联赛类: 默认看近6轮
LEAGUE_SHORTCUTS = {
    "bl1", "bl2", "epl", "sa", "liga1", "liga", "seriea", "serie",
    "fr1", "fr2", "ned", "por", "gre", "tur", "sco", "bel", "aut", "swi",
    "chn", "jpn", "kor", "usa", "bra", "arg",
}
# 杯赛类: 可查历届数据
CUP_SHORTCUTS = {
    "wm26": {"type": "世界杯", "prev": ["wm22", "wm18", "wm14"], "default_lookback": 20},
    "wm22": {"type": "世界杯", "prev": ["wm18", "wm14", "wm10"], "default_lookback": 20},
    "em2024": {"type": "欧洲杯", "prev": ["em2021", "em2016"], "default_lookback": 20},
    "em2021": {"type": "欧洲杯", "prev": ["em2016", "em2012"], "default_lookback": 20},
    "ucl2024": {"type": "欧冠", "prev": ["ucl2023", "ucl2022"], "default_lookback": 30},
    "ucl2023": {"type": "欧冠", "prev": ["ucl2022", "ucl2021"], "default_lookback": 30},
    "dfb": {"type": "德国杯", "prev": [], "default_lookback": 15},
    "unl": {"type": "欧国联", "prev": [], "default_lookback": 15},
    "ca2024": {"type": "美洲杯", "prev": ["ca2021", "ca2019"], "default_lookback": 20},
    "ca2021": {"type": "美洲杯", "prev": ["ca2019"], "default_lookback": 20},
}
# 未知shortcut: 按联赛处理（近6轮），可通过 --mode cup 强制杯赛模式

# ============================================================
# 队名映射
# ============================================================
TEAM_DE = {
    "英格兰": "England", "民主刚果": "DR Kongo", "刚果金": "DR Kongo",
    "比利时": "Belgien", "塞内加尔": "Senegal",
    "美国": "USA", "波黑": "Bosnien und Herzegowina",
    "法国": "Frankreich", "挪威": "Norwegen", "瑞典": "Schweden",
    "墨西哥": "Mexiko", "厄瓜多尔": "Ecuador",
    "葡萄牙": "Portugal", "克罗地亚": "Kroatien",
    "西班牙": "Spanien", "奥地利": "Österreich",
    "阿根廷": "Argentinien", "巴西": "Brasilien",
    "荷兰": "Niederlande", "德国": "Deutschland",
    "瑞士": "Schweiz", "加拿大": "Kanada",
    "日本": "Japan", "韩国": "Südkorea",
    "南非": "Südafrika", "捷克": "Tschechien",
    "乌拉圭": "Uruguay", "沙特": "Saudi Arabien",
    "哥伦比亚": "Kolumbien", "乌兹别克": "Usbekistan",
    "加纳": "Ghana", "巴拿马": "Panama",
    "意大利": "Italien", "丹麦": "Dänemark",
    "波兰": "Polen", "匈牙利": "Ungarn",
    "土耳其": "Türkei", "澳大利亚": "Australien",
    "巴拉圭": "Paraguay", "卡塔尔": "Katar",
    "伊拉克": "Irak", "伊朗": "Iran",
    "新西兰": "Neuseeland", "埃及": "Ägypten",
    "阿尔及利亚": "Algerien", "摩洛哥": "Marokko",
    "海地": "Haiti", "苏格兰": "Schottland",
    "约旦": "Jordanien", "科特迪瓦": "Elfenbeinküste",
    "库拉索": "Curaçao", "突尼斯": "Tunesien",
    "芬兰": "Finnland",
    "拜仁慕尼黑": "Bayern München", "拜仁": "Bayern München",
    "多特蒙德": "Borussia Dortmund", "多特": "Borussia Dortmund",
    "勒沃库森": "Bayer Leverkusen", "药厂": "Bayer Leverkusen",
    "莱比锡": "RB Leipzig", "法兰克福": "Eintracht Frankfurt",
    "门兴": "Borussia Mönchengladbach", "沃尔夫斯堡": "VfL Wolfsburg",
    "斯图加特": "VfB Stuttgart",
    "巴黎圣日耳曼": "Paris Saint-Germain", "巴黎": "Paris Saint-Germain",
    "摩纳哥": "AS Monaco",
    "利物浦": "Liverpool", "曼联": "Manchester United", "曼城": "Manchester City",
    "阿森纳": "Arsenal", "切尔西": "Chelsea", "热刺": "Tottenham",
    "纽卡斯尔": "Newcastle", "阿斯顿维拉": "Aston Villa",
    "巴塞罗那": "Barcelona", "皇马": "Real Madrid", "皇家马德里": "Real Madrid",
    "马竞": "Atletico Madrid", "国际米兰": "Inter", "AC米兰": "Milan",
    "尤文图斯": "Juventus", "那不勒斯": "Napoli",
}
TEAM_CN = {v: k for k, v in TEAM_DE.items()}

# ============================================================
# HTTP 工具
# ============================================================

def http_get_ol(path: str) -> Optional[dict]:
    url = f"https://api.openligadb.de{path}"
    try:
        ctx = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return None


def oddsapi_get(path: str) -> Optional[dict]:
    url = f"{ODDS_API_BASE}{path}&apiKey={ODDS_API_KEY}"
    try:
        r = subprocess.run(["curl", "-s", "--max-time", "10", url],
                           capture_output=True, text=True, timeout=15)
        data = json.loads(r.stdout)
        if isinstance(data, dict) and "error" in data:
            return None
        return data
    except:
        return None


# ============================================================
# 比赛结果获取
# ============================================================

def fetch_team_matches(team_cn: str, league: str = "wm26", season: str = "2026") -> List[dict]:
    """获取某队在某个赛事的所有已完赛比赛"""
    team_de = TEAM_DE.get(team_cn, team_cn)
    data = http_get_ol(f"/getmatchdata/{league}/{season}")
    if not data:
        return []

    matches = []
    for m in data:
        t1_name = m.get("team1", {}).get("teamName", "")
        t2_name = m.get("team2", {}).get("teamName", "")
        if team_de.lower() not in t1_name.lower() and team_de.lower() not in t2_name.lower():
            continue
        if not m.get("matchIsFinished", False):
            continue

        final_score = None
        for r in m.get("matchResults", []):
            if r.get("resultName") in ("Endergebnis", "结果"):
                final_score = (int(r["pointsTeam1"]), int(r["pointsTeam2"]))
                break
        if not final_score:
            continue

        is_home = team_de.lower() in t1_name.lower()
        team_score = final_score[0] if is_home else final_score[1]
        opp_score = final_score[1] if is_home else final_score[0]
        opp_name = t2_name if is_home else t1_name

        matches.append({
            "date": m.get("matchDateTime", "")[:10],
            "team": team_cn,
            "opponent_de": opp_name,
            "opponent_cn": TEAM_CN.get(opp_name, opp_name) or opp_name,
            "team_score": team_score,
            "opp_score": opp_score,
            "score_diff": team_score - opp_score,
            "is_home": is_home,
            "won": team_score > opp_score,
            "draw": team_score == opp_score,
            "lost": team_score < opp_score,
        })

    matches.sort(key=lambda x: x["date"], reverse=True)
    return matches


# ============================================================
# 赛事分类检测
# ============================================================

def detect_competition_type(league_shortcut: str) -> dict:
    """
    判断是联赛还是杯赛, 返回配置信息。
    """
    sc = league_shortcut.lower()

    if sc in CUP_SHORTCUTS:
        info = CUP_SHORTCUTS[sc]
        info["mode"] = "cup"
        info["label"] = info["type"]
        return info

    if sc in LEAGUE_SHORTCUTS:
        return {"mode": "league", "label": "联赛", "default_lookback": 6, "prev": []}

    # 未知 → 按联赛处理
    return {"mode": "league", "label": "联赛", "default_lookback": 6, "prev": []}


def fetch_cup_history(team_cn: str, league_shortcut: str = "wm26", max_prev: int = 3) -> List[dict]:
    """
    杯赛模式: 获取历届同赛事数据
    注意: OpenLigaDB 仅存近期赛事，早期杯赛可能无数据
    """
    all_matches = []
    info = CUP_SHORTCUTS.get(league_shortcut.lower(), {})

    # 本届
    cur_season = "2026"
    if len(league_shortcut) >= 4 and league_shortcut[-4:].isdigit():
        cur_season = league_shortcut[-4:]
    current = fetch_team_matches(team_cn, league_shortcut, cur_season)
    all_matches.extend(current)
    print(f"   本届({league_shortcut}): {len(current)}场")

    # 历届
    found_prev = 0
    for prev_sc in info.get("prev", [])[:max_prev]:
        prev_season = "2022"
        if len(prev_sc) >= 4 and prev_sc[-4:].isdigit():
            prev_season = prev_sc[-4:]
        prev_matches = fetch_team_matches(team_cn, prev_sc, prev_season)
        if prev_matches:
            all_matches.extend(prev_matches)
            found_prev += 1
            print(f"   历届 {prev_sc}({prev_season}): {len(prev_matches)}场")

    if found_prev == 0:
        print(f"   历届: OpenLigaDB无更早数据(仅本届{len(current)}场)")

    all_matches.sort(key=lambda x: x["date"], reverse=True)
    return all_matches


# ============================================================
# 赢盘估算
# ============================================================

def estimate_winrate(matches: List[dict], lookback: int = 20,
                     source_label: str = "比分差估算") -> dict:
    """比分差分档估算赢盘率"""
    recent = matches[:lookback]
    total = len(recent)
    if total == 0:
        return {"error": "无比赛数据"}

    cover_wins = cover_losses = cover_pushes = uncertain = 0
    details = []

    for m in recent:
        diff = m["score_diff"]
        # 分档估算
        if diff >= 2:
            cover = "W"; weight = 0.85
        elif diff == 1:
            cover = "W"; weight = 0.5
        elif diff == 0:
            cover = "?"; weight = 0
        elif diff == -1:
            cover = "L"; weight = 0.5
        else:
            cover = "L"; weight = 0.85

        if cover == "W":
            cover_wins += weight
            if weight < 1: cover_losses += (1 - weight)
        elif cover == "L":
            cover_losses += weight
            if weight < 1: cover_wins += (1 - weight)
        elif cover == "?":
            uncertain += 1

        details.append({
            "date": m["date"], "opponent": m["opponent_cn"] or m["opponent_de"],
            "score": f"{m['team_score']}-{m['opp_score']}", "diff": diff,
            "cover": cover, "confidence": f"{int(weight*100)}%",
            "result": "W" if m["won"] else ("D" if m["draw"] else "L"),
        })

    total_analyzed = cover_wins + cover_losses
    cover_rate = round(cover_wins / total_analyzed * 100, 1) if total_analyzed > 0 else None

    wins = sum(1 for m in recent if m["won"])
    draws = sum(1 for m in recent if m["draw"])
    losses = sum(1 for m in recent if m["lost"])

    if uncertain <= total * 0.1: reliability = "高"
    elif uncertain <= total * 0.3: reliability = "中"
    else: reliability = "低"

    return {
        "total_matches": len(matches),
        "lookback": total,
        "record": f"{wins}胜 {draws}平 {losses}负",
        "win_rate": round(wins / total * 100, 1) if total > 0 else 0,
        "cover_data_source": source_label,
        "cover_wins": round(cover_wins, 1),
        "cover_losses": round(cover_losses, 1),
        "cover_pushes": cover_pushes,
        "cover_rate": cover_rate,
        "reliability": reliability,
        "uncertain_matches": uncertain,
        "details": details,
    }


# ============================================================
# 手动输入盘口模式
# ============================================================

def manual_handicap_mode(matches: List[dict], lookback: int = 20):
    recent = matches[:lookback]
    print(f"\n{'='*60}")
    print(f"  手动输入盘口模式 — {len(recent)} 场比赛")
    print(f"  盘口格式: -1.5 (让1.5)  +0.5 (受让0.5)  0 (平手)")
    print(f"{'='*60}")

    cw = cl = cp = 0
    details = []

    for i, m in enumerate(recent):
        opp = m["opponent_cn"] or m["opponent_de"]
        print(f"\n  [{i+1}/{len(recent)}] {m['date']} vs {opp}")
        print(f"     比分: {m['team_score']}-{m['opp_score']} (净胜{m['score_diff']:+d})")
        inp = input(f"     盘口(回车跳过): ").strip()

        if not inp:
            hdp = None
            if m["score_diff"] >= 2: hdp = -1.0
            elif m["score_diff"] == 1: hdp = -0.5
            elif m["score_diff"] <= -2: hdp = 1.0
            elif m["score_diff"] == -1: hdp = 0.5
            if hdp is not None:
                print(f"     -> 估算盘口: {hdp:+.1f}")
            else:
                print(f"     -> 跳过(无法估算)")
                details.append({"date": m["date"], "opponent": opp,
                    "score": f"{m['team_score']}-{m['opp_score']}", "diff": m["score_diff"],
                    "handicap": None, "cover": "?"})
                continue
        else:
            try:
                hdp = float(inp.replace("让", "-").replace("受", "+"))
            except ValueError:
                print("     格式错误，跳过")
                continue

        diff = m["score_diff"]
        if hdp < 0:
            cover = "W" if diff > -hdp else ("P" if diff == -hdp else "L")
        elif hdp > 0:
            cover = "W" if diff + hdp > 0 else ("P" if diff + hdp == 0 else "L")
        else:
            cover = "W" if diff > 0 else ("P" if diff == 0 else "L")

        if cover == "W": cw += 1
        elif cover == "L": cl += 1
        else: cp += 1

        details.append({"date": m["date"], "opponent": opp,
            "score": f"{m['team_score']}-{m['opp_score']}", "diff": m["score_diff"],
            "handicap": hdp, "cover": cover})

    total = cw + cl
    rate = round(cw / total * 100, 1) if total > 0 else 0
    rel = "高" if total >= 15 else ("中" if total >= 8 else "低")
    return {"cover_data_source": "手动输入", "cover_wins": cw, "cover_losses": cl,
            "cover_pushes": cp, "cover_rate": rate, "reliability": rel}, details


# ============================================================
# 输出报告
# ============================================================

def print_report(report: dict, details: List[dict] = None, show_detail: bool = False,
                 mode_label: str = "", team: str = "", league_label: str = ""):
    if "error" in report:
        print(f"\n[错误] {report['error']}")
        return

    # 读取现有值
    existing = None
    if team and os.path.exists(WINRATE_DB_PATH):
        with open(WINRATE_DB_PATH, "r", encoding="utf-8") as f:
            m = re.search(rf'"{re.escape(team)}":\s*\((\d+(?:\.\d+)?)', f.read())
            if m: existing = float(m.group(1))

    print(f"\n{'='*60}")
    print(f"  [赢盘率] {team} @ {league_label}")
    if mode_label:
        print(f"  模式: {mode_label}")
    print(f"{'='*60}")
    print(f"  比赛总数: {report.get('total_matches', 0)} | 分析近{report['lookback']}场")
    print(f"  战绩: {report['record']} | 胜率: {report['win_rate']}%")

    if existing is not None and report.get("cover_rate"):
        delta = report["cover_rate"] - existing
        print(f"  winrate_db当前: {existing}% | 本次计算: {report['cover_rate']}% ({delta:+.1f}%)")
    else:
        print(f"  winrate_db当前: {'--' if existing is None else f'{existing}%'}")

    print(f"  ─────────────────────────────────")
    print(f"  来源: {report['cover_data_source']}")
    cr = report.get("cover_rate")
    if cr is not None:
        print(f"  赢{report['cover_wins']} / 输{report['cover_losses']} / 走{report.get('cover_pushes',0)}")
        print(f"  >> 赢盘率: {cr}% ({report['cover_wins']+report['cover_losses']}场可判)")
        rel = report.get("reliability", "低")
        sym = {"高": "🟢", "中": "🟡", "低": "🔴"}
        print(f"  可靠性: {sym.get(rel, '❓')} {rel}")

    if report.get("uncertain_matches", 0) > 0:
        print(f"  无法判断: {report['uncertain_matches']}场(平局/数据不足)")

    if details and show_detail:
        print(f"\n  明细:")
        print(f"  {'日期':<12s} {'对手':<18s} {'比分':<8s} {'净胜':>4s} {'盘口':>8s} {'盘果':>4s}")
        print(f"  {'-'*56}")
        for m in details:
            h = f"{m.get('handicap','?'):+.1f}" if isinstance(m.get('handicap'), (int,float)) else "估?"
            cs = {"W":"W","L":"L","P":"P","?":"?"}
            c = cs.get(m.get("cover","?"),"?")
            opp = (m["opponent"] or "")[:16]
            print(f"  {m['date']:<12s} {opp:<18s} {m['score']:<8s} {m['diff']:+3d} {h:>8s} {c:>4s}")

    if cr is not None:
        print(f"\n  >> 建议: \"{team}\": ({cr}, \"{report['reliability']}\"),")
    print()


# ============================================================
# 更新 winrate_db.py
# ============================================================

def update_winrate_db(team: str, rate: float, reliability: str):
    if not os.path.exists(WINRATE_DB_PATH):
        print(f"[错误] 找不到 {WINRATE_DB_PATH}")
        return False
    with open(WINRATE_DB_PATH, "r", encoding="utf-8") as f:
        content = f.read()
    pattern = rf'("{re.escape(team)}":\s*)\(\d+(\.\d+)?,\s*"[^"]*"\)'
    if re.search(pattern, content):
        content = re.sub(pattern, rf'\1({rate}, "{reliability}")', content)
        with open(WINRATE_DB_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"  [OK] winrate_db.py 已更新: {team} -> {rate}% ({reliability})")
        return True
    else:
        print(f"  [!] 未找到 '{team}'，手动添加:")
        print(f'     "{team}": ({rate}, "{reliability}"),')
        return False


# ============================================================
# 命令行入口
# ============================================================

def print_help():
    print(f"""世界杯赢盘率分析 v3.0

用法:
  python update_winrate.py --team "英格兰"               自动识别(杯赛查历届/联赛看近6轮)
  python update_winrate.py --team "英格兰" --detail      显示明细
  python update_winrate.py --team "英格兰" --manual-hdp  手动输入盘口
  python update_winrate.py --team "英格兰" --update-db   更新winrate_db.py
  python update_winrate.py --team "利物浦" --league epl  英超(近6轮)
  python update_winrate.py --team "拜仁" --league bl1    德甲(近6轮)
  python update_winrate.py --team "巴西" --league ca2024 美洲杯
  python update_winrate.py --team "英格兰" --history-cup 查历届世界杯
  python update_winrate.py --list                        可用联赛

联赛(近6轮): epl, bl1, bl2, sa, seriea, liga1, fr1, ned ...
杯赛(查历届): wm26(世界杯)  em2024(欧洲杯)  ucl2024(欧冠)
               ca2024(美洲杯)  unl(欧国联)  dfb(德国杯)
""")


def list_leagues():
    data = http_get_ol("/getavailableleagues")
    if not data:
        return
    print(f"\n{'='*60}\n  可用联赛\n{'='*60}")
    for l in sorted(data, key=lambda x: x.get("leagueName", "")):
        try:
            if int(l.get("leagueSeason", 0)) < 2024: continue
        except: continue
        sc = l["leagueShortcut"]
        mode = "🏆杯赛" if sc.lower() in CUP_SHORTCUTS else ("⚽联赛" if sc.lower() in LEAGUE_SHORTCUTS else "⚽联赛")
        print(f"  {mode} {sc:<12s} | {l['leagueName']:<40s} | 赛季={l['leagueSeason']}")


def main():
    if len(sys.argv) < 2 or "--help" in sys.argv or "-h" in sys.argv:
        print_help(); return
    if "--list" in sys.argv:
        list_leagues(); return

    # 解析参数
    team = None; league = "wm26"; season = "2026"
    lookback = None; do_detail = "--detail" in sys.argv
    do_save = "--save" in sys.argv; do_update_db = "--update-db" in sys.argv
    do_manual = "--manual-hdp" in sys.argv; do_history = "--history-cup" in sys.argv

    for i, a in enumerate(sys.argv):
        if a == "--team" and i+1 < len(sys.argv): team = sys.argv[i+1]
        if a == "--league" and i+1 < len(sys.argv): league = sys.argv[i+1]
        if a == "--season" and i+1 < len(sys.argv): season = sys.argv[i+1]
        if a == "--lookback" and i+1 < len(sys.argv):
            try: lookback = int(sys.argv[i+1])
            except: pass

    if not team:
        print_help(); return

    # ---- 检测赛事类型 ----
    comp = detect_competition_type(league)
    mode_label = f"{comp['label']}模式"
    if comp["mode"] == "cup":
        prev_list = comp.get("prev", [])
        if prev_list:
            mode_label += f" (+{len(prev_list)}届历史)"
    else:
        mode_label += " (近6轮)"

    if lookback is None:
        lookback = comp.get("default_lookback", 20)

    # ---- 查数据 ----
    print(f"\n[查询] {team} @ {league}/{season}")
    print(f"  模式: {mode_label} | 分析近{lookback}场")

    if comp["mode"] == "cup" and do_history:
        # 杯赛: 查历届
        print(f"  杯赛历史: 本届 + {len(comp.get('prev',[]))}届历届")
        all_matches = fetch_cup_history(team, league, 3)
    else:
        all_matches = fetch_team_matches(team, league, season)

    if not all_matches:
        print(f"[!] 未找到比赛数据")
        return

    league_label = f"{league}/{season}"
    print(f"  -> 找到 {len(all_matches)} 场已完赛")

    # 尝试 odds-api
    print(f"  -> 尝试 odds-api.io 获取盘口...")
    handicaps = oddsapi_get(f"/events?sport=football")
    hdp_found = 0
    if handicaps and isinstance(handicaps, list):
        for e in handicaps:
            if not isinstance(e, dict): continue
            h = e.get("home","").lower(); a = e.get("away","").lower()
            td = TEAM_DE.get(team, team).lower()
            if td in h or td in a: hdp_found += 1
    print(f"  -> 找到 {hdp_found} 场相关盘口数据" if hdp_found else "  -> 无实时盘口(使用比分差估算)")

    # ---- 计算 ----
    if do_manual:
        report, details = manual_handicap_mode(all_matches, lookback)
        print_report(report, details, True, mode_label, team, league_label)
    else:
        src = f"比分差估算({'历届' if comp['mode']=='cup' and do_history else '本届'})"
        report = estimate_winrate(all_matches, lookback, src)
        print_report(report, report.get("details"), do_detail, mode_label, team, league_label)

    # 保存/更新
    if do_save and report.get("cover_rate") is not None:
        path = os.path.join(CACHE_DIR, f"winrate_{team}_{league}_{season}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"  [保存] {path}")

    if do_update_db and report.get("cover_rate") is not None:
        update_winrate_db(team, report["cover_rate"], report["reliability"])


if __name__ == "__main__":
    main()
