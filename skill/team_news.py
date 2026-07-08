#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
球队新闻 & 首发预测 — 辅助分析师录入结构化赛前情报

用途:
  为L0-L4轮换分级、核心球员缺阵量化、阵型稳定性分析提供结构化输入。
  当前为手动输入模式（免费源无可靠自动获取方式），
  分析师赛前查WhoScored/Flashscore后按格式填入。

用法:
  python skill/team_news.py --home "主队" --away "客队"  # 交互式输入
  python skill/team_news.py --file news.json              # 从文件加载
  python skill/team_news.py --report                      # 生成报告
"""

import json, sys, os, argparse
from datetime import datetime
from typing import Optional, Dict, List

if sys.platform == "win32" and hasattr(sys.stdout, "buffer"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "数据缓存")

# ============================================================
# 球队新闻数据结构
# ============================================================

# 标准模板（分析师赛前填写）
DEFAULT_TEMPLATE = {
    "match_id": None,
    "date": None,
    "home_team": None,
    "away_team": None,
    "home": {
        "formation": "",           # 如 "4-3-3"
        "formation_stability": "", # stable / changed / new (近3场变化)
        "rotation_level": "",      # L0/L1/L2/L3/L4
        "rotation_note": "",       # 轮换说明
        "key_injuries": [],        # [{"player":"...", "impact":"high/mid/low"}]
        "key_returns": [],         # [{"player":"..."}]
        "tactical_style": "",      # 高位逼抢/传控/防反/控制型防反/转换型/混合型
        "notes": "",               # 其他情报
    },
    "away": {
        "formation": "",
        "formation_stability": "",
        "rotation_level": "",
        "rotation_note": "",
        "key_injuries": [],
        "key_returns": [],
        "tactical_style": "",
        "notes": "",
    },
    "weather": {
        "condition": "",           # clear/rain/snow
        "temperature": "",         # Celsius
        "pitch": "",              # natural/artificial
    },
    "referee": {
        "name": "",
        "cards_per_game": "",     # 场均罚牌数
    },
    "last_updated": None,
}


def create_template(home: str, away: str) -> dict:
    """创建标准赛前情报模板"""
    t = dict(DEFAULT_TEMPLATE)
    t["match_id"] = f"{home}_vs_{away}_{datetime.now().strftime('%Y%m%d')}"
    t["date"] = datetime.now().strftime("%Y-%m-%d")
    t["home_team"] = home
    t["away_team"] = away
    t["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return t


# ============================================================
# 辅助函数
# ============================================================

def rotation_level_from_subs(subs_count: int, total_xi: int = 11) -> str:
    """根据轮换人数自动判断L0-L4

    Args:
        subs_count: 预计轮换人数（与上一场首发对比）
        total_xi: 首发总人数（默认11）

    Returns:
        L0/L1/L2/L3/L4
    """
    ratio = subs_count / total_xi
    if ratio == 0:      return "L0"
    if ratio <= 0.27:   return "L1"   # 1-3人
    if ratio <= 0.54:   return "L2"   # 4-6人
    if ratio <= 0.72:   return "L3"   # 7-8人
    return "L4"  # 9-11人


def rotation_effective_coefficient(level: str, wvr: bool = True) -> float:
    """获取L0-L4有效系数（入M系数）

    Args:
        level: L0/L1/L2/L3/L4
        wvr: 是否使用WVR衰减后的值

    Returns:
        有效系数
    """
    raw = {"L0": 1.00, "L1": 0.95, "L2": 0.85, "L3": 0.70, "L4": 0.55}
    wvr_adj = {"L0": 1.000, "L1": 0.962, "L2": 0.887, "L3": 0.850, "L4": 0.775}
    return wvr_adj.get(level, 1.0) if wvr else raw.get(level, 1.0)


def formation_stability_factor(formation: str, prev_formations: List[str], is_new_threshold: int = 3) -> float:
    """根据阵型稳定性计算战术适配度降权系数

    Args:
        formation: 本场阵型
        prev_formations: 近N场阵型列表
        is_new_threshold: 新阵型使用≤几场视为不稳定

    Returns:
        1.0 = 稳定, 0.5 = 不稳定（降权50%）
    """
    if not prev_formations:
        return 0.5  # 无数据默认保守
    matches = sum(1 for f in prev_formations if f == formation)
    if matches >= is_new_threshold:
        return 1.0
    elif matches >= 1:
        return 0.7
    else:
        return 0.5


def injury_impact_on_attack(injuries: List[dict], team_attack_score: float) -> float:
    """根据伤病信息估算进攻评分损失

    简化版：每个high impact扣1.5分，mid扣0.8分，low扣0.3分
    """
    impact_scores = {"high": 1.5, "mid": 0.8, "low": 0.3}
    total = sum(impact_scores.get(i.get("impact", "low"), 0.3) for i in injuries)
    return max(0, team_attack_score - total)


def injury_impact_on_defense(injuries: List[dict], team_defense_score: float) -> float:
    """简化版防守评分损失（与进攻同逻辑）"""
    return injury_impact_on_attack(injuries, team_defense_score)


# ============================================================
# 保存 & 生成报告
# ============================================================

def save_team_news(data: dict):
    """保存球队新闻数据"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    match_id = data.get("match_id", "unknown")
    path = os.path.join(OUTPUT_DIR, f"team_news_{match_id}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"\n[OK] 已保存到 {path}")
    return path


def generate_report(data: dict) -> str:
    """生成结构化情报报告"""
    h = data.get("home", {})
    a = data.get("away", {})
    w = data.get("weather", {})
    r = data.get("referee", {})

    lines = []
    lines.append(f"[赛前情报报告] {data.get('home_team','?')} vs {data.get('away_team','?')}")
    lines.append(f"   日期: {data.get('date','?')} | 更新: {data.get('last_updated','?')}")
    lines.append("")

    for side, label, team_name in [(h, "== 主队 ==", data.get("home_team","?")),
                                    (a, "== 客队 ==", data.get("away_team","?"))]:
        lines.append(f"{label} {team_name}")
        lines.append(f"   阵型: {side.get('formation','?')} | 稳定性: {side.get('formation_stability','?')}")
        rot = side.get("rotation_level", "?")
        coef = rotation_effective_coefficient(rot) if rot in ("L0","L1","L2","L3","L4") else 0
        lines.append(f"   轮换: {rot} (M系数: {coef})")
        if side.get("rotation_note"):
            lines.append(f"   轮换说明: {side['rotation_note']}")
        lines.append(f"   战术风格: {side.get('tactical_style','?')}")

        injuries = side.get("key_injuries", [])
        if injuries:
            parts = []
            for i in injuries:
                parts.append(f"{i['player']}({i['impact']})")
            lines.append(f"   伤病: {', '.join(parts)}")
        returns = side.get("key_returns", [])
        if returns:
            lines.append(f"   回归: {', '.join([r['player'] for r in returns])}")
        if side.get("notes"):
            lines.append(f"   备注: {side['notes']}")
        lines.append("")

    lines.append(f"  天气: {w.get('condition','?')} | {w.get('temperature','?')}C | 场地: {w.get('pitch','?')}")
    lines.append(f"  裁判: {r.get('name','?')} | 场均罚牌: {r.get('cards_per_game','?')}")
    lines.append("")
    lines.append("=" * 50)

    return "\n".join(lines)


# ============================================================
# 交互式输入
# ============================================================

def interactive_input(home: str, away: str) -> dict:
    """交互式填写赛前情报"""
    t = create_template(home, away)

    for side_key, side_label in [("home", "主队"), ("away", "客队")]:
        print(f"\n{'='*40}")
        print(f"  {side_label}: {home if side_key=='home' else away}")
        print(f"{'='*40}")
        s = t[side_key]
        s["formation"] = input(f"  阵型 (如 4-3-3) [{s['formation']}]: ") or s["formation"]
        s["formation_stability"] = input(f"  阵型稳定性 (stable/changed/new) [{s['formation_stability']}]: ") or s["formation_stability"]
        rot_options = "L0(全主力)/L1(1-3人)/L2(4-6人)/L3(7-10人)/L4(全替补)"
        s["rotation_level"] = input(f"  轮换级别 ({rot_options}) [{s['rotation_level']}]: ") or s["rotation_level"]
        s["rotation_note"] = input(f"  轮换说明 [{s['rotation_note']}]: ") or s["rotation_note"]
        style_options = "高位逼抢/传控/防反/控制型防反/转换型/混合型"
        s["tactical_style"] = input(f"  战术风格 ({style_options}) [{s['tactical_style']}]: ") or s["tactical_style"]

        injuries_str = input(f"  伤病 (格式: 球员名:high, 球员名:mid, 多个用逗号分隔) []: ")
        if injuries_str:
            for item in injuries_str.split(","):
                parts = item.strip().split(":")
                if len(parts) >= 2:
                    s["key_injuries"].append({"player": parts[0], "impact": parts[1]})
                elif parts[0]:
                    s["key_injuries"].append({"player": parts[0], "impact": "mid"})

        returns_str = input(f"  回归球员 (逗号分隔) []: ")
        if returns_str:
            for p in returns_str.split(","):
                if p.strip():
                    s["key_returns"].append({"player": p.strip()})

        s["notes"] = input(f"  其他情报 [{s['notes']}]: ") or s["notes"]

    print(f"\n{'='*40}")
    print(f"  天气 & 裁判")
    print(f"{'='*40}")
    t["weather"]["condition"] = input(f"  天气 (clear/rain/snow) [{t['weather']['condition']}]: ") or t["weather"]["condition"]
    t["weather"]["temperature"] = input(f"  温度 (°C) [{t['weather']['temperature']}]: ") or t["weather"]["temperature"]
    t["weather"]["pitch"] = input(f"  场地 (natural/artificial) [{t['weather']['pitch']}]: ") or t["weather"]["pitch"]
    t["referee"]["name"] = input(f"  裁判姓名 [{t['referee']['name']}]: ") or t["referee"]["name"]
    t["referee"]["cards_per_game"] = input(f"  场均罚牌 [{t['referee']['cards_per_game']}]: ") or t["referee"]["cards_per_game"]

    t["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return t


def auto_fill(home: str, away: str, league: str = "wm26") -> dict:
    """从 datafc/Sofascore 自动填充赛前情报"""
    t = create_template(home, away)
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from skill.datafc_provider import (
            get_matches, get_formations, get_pregame_form,
            get_lineups, get_match_details
        )

        match_df = get_matches(league, team_name=home)
        if not match_df.empty:
            fm = get_formations(match_df.head(1))
            pf = get_pregame_form(match_df.head(1))
            lu = get_lineups(match_df.head(1))
            md = get_match_details(match_df.head(1))

            if fm:
                t["home"]["formation"] = fm.get("home_formation", "")
                t["away"]["formation"] = fm.get("away_formation", "")
            if pf:
                form_h = pf.get("home_last5", "")
                form_a = pf.get("away_last5", "")
                if form_h:
                    t["home"]["notes"] = f"近5场: {form_h} | 评分: {pf.get('home_avg_rating','?')}"
                if form_a:
                    t["away"]["notes"] = f"近5场: {form_a} | 评分: {pf.get('away_avg_rating','?')}"
            if lu:
                home_lineup = lu.get("home_lineup", [])
                away_lineup = lu.get("away_lineup", [])
                if home_lineup:
                    t["home"]["formation_stability"] = "auto"
                    t["home"]["rotation_note"] = f"使用{len(home_lineup)}名球员"
                if away_lineup:
                    t["away"]["formation_stability"] = "auto"
                    t["away"]["rotation_note"] = f"使用{len(away_lineup)}名球员"
            if md:
                t["referee"]["name"] = md.get("referee", "")
                t["weather"]["pitch"] = md.get("venue", "")
    except ImportError:
        pass
    except Exception as e:
        print(f"[auto_fill] {e}")

    t["last_updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    return t


# ============================================================
# 命令行
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="球队新闻 & 首发预测")
    parser.add_argument("--home", help="主队名")
    parser.add_argument("--away", help="客队名")
    parser.add_argument("--league", default="wm26", help="联赛代码")
    parser.add_argument("--file", help="从JSON文件加载")
    parser.add_argument("--report", action="store_true", help="生成报告")
    parser.add_argument("--generate", action="store_true", help="生成空模板JSON")
    parser.add_argument("--auto", action="store_true", help="从datafc自动填充（无需交互）")
    args = parser.parse_args()

    if args.file and args.report:
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(generate_report(data))
        return

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            data = json.load(f)
        print(f"已加载: {data.get('match_id','?')}")
        print(generate_report(data))
        return

    if args.generate and args.home and args.away:
        t = create_template(args.home, args.away)
        path = save_team_news(t)
        print(f"空模板已生成，请编辑后使用 --file 加载")
        return

    if args.auto and args.home and args.away:
        t = auto_fill(args.home, args.away, args.league)
        path = save_team_news(t)
        print(f"已从 datafc 自动填充赛前情报: {path}")
        print(generate_report(t))
        return

    if args.home and args.away:
        data = interactive_input(args.home, args.away)
        save_team_news(data)
        print(generate_report(data))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
