#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
⚡ 三步快速预测 — 填→看→确认

用法:
  python skill/quick_predict.py                          # 交互式三步走
  python skill/quick_predict.py --home "A" --away "B"    # 跳过第一步

三步流程:
  ① 填比赛信息
  ② 填预测 (方向 + 概率 + 信心)
  ③ 确认 → 自动入库 + 刷新看板
"""
import sys, os, json, argparse, subprocess, io
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
PRED_DIR = os.path.join(BASE_DIR, "预测数据")
DB_FILE = os.path.join(CACHE_DIR, "predictions_db.json")

LEAGUE_ALIAS = {
    "wm26": "世界杯", "kleague1": "K1联赛", "kleague2": "K2联赛",
    "jleague1": "J1联赛", "jleague2": "J2联赛",
    "sportsdb": "瑞典超/芬超", "bl1": "德甲", "epl": "英超",
}

COMMON_LEAGUES = ["wm26", "kleague1", "jleague1", "sportsdb", "epl", "bl1"]


def p(text):
    try:
        print(str(text))
    except UnicodeEncodeError:
        try:
            print(str(text).encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            print(str(text))


def clean(s):
    """移除 surrogate 字符，防止 json.dump 崩溃"""
    if not isinstance(s, str):
        return s
    return s.encode("utf-8", errors="replace").decode("utf-8")


def input_clean(prompt=""):
    """input + 自动清洗 surrogate"""
    try:
        val = input(prompt)
    except:
        val = ""
    return clean(val)


def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"predictions": []}


def save_db(db):
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def load_last_match():
    """取上一条手动预测，用作默认值"""
    db = load_db()
    for rec in reversed(db.get("predictions", [])):
        if rec.get("source") == "manual_analysis":
            return rec
    return None


def fetch_reference(home, away, league):
    """尝试拉参考数据，失败不影响主流程"""
    ref = {}
    try:
        result = subprocess.run(
            f'python "{os.path.join(BASE_DIR, "skill", "xg_estimator.py")}" '
            f'--home "{home}" --away "{away}" --league {league} --max-games 6',
            shell=True, capture_output=True, timeout=45
        )
        out = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
        import re
        atts = re.findall(r"L1进攻评分:\s*([\d.]+)", out)
        defs = re.findall(r"L1防守评分:\s*([\d.]+)", out)
        if len(atts) >= 2:
            ref["home_attack"] = atts[0]
            ref["away_attack"] = atts[1]
        if len(defs) >= 2:
            ref["home_defense"] = defs[0]
            ref["away_defense"] = defs[1]
        la = re.search(r"λ_A.*?([\d.]+)", out)
        lb = re.search(r"λ_B.*?([\d.]+)", out)
        if la: ref["lambda_A"] = la.group(1)
        if lb: ref["lambda_B"] = lb.group(1)
        src = re.search(r"数据来源:\s*(\S+)", out)
        if src: ref["source"] = src.group(1)
    except Exception:
        pass

    # ELO单独取（不依赖子进程）
    try:
        sys.path.insert(0, os.path.join(BASE_DIR))
        from skill.datafc_provider import get_team_elo
        elo_h = get_team_elo(home).get("elo", 0)
        elo_a = get_team_elo(away).get("elo", 0)
        if elo_h: ref["elo_h"] = str(elo_h)
        if elo_a: ref["elo_a"] = str(elo_a)
    except Exception:
        pass

    return ref


def show_reference(ref):
    """展示参考数据"""
    parts = []
    if ref.get("elo_h"):
        diff = int(ref["elo_h"]) - int(ref["elo_a"])
        mark = "🔺" if diff > 100 else ("🔻" if diff < -100 else "➖")
        parts.append(f"ELO {ref['elo_h']} vs {ref['elo_a']} (差{diff:+d}) {mark}")
    if ref.get("home_attack"):
        parts.append(f"进攻 {ref['home_attack']}/{ref['away_attack']}")
    if ref.get("home_defense"):
        parts.append(f"防守 {ref['home_defense']}/{ref['away_defense']}")
    if ref.get("lambda_A"):
        parts.append(f"xG {ref['lambda_A']}/{ref['lambda_B']}")
    if parts:
        p(f"  📊 参考数据: {' | '.join(parts)}")
    if ref.get("source"):
        p(f"     来源: {ref['source']}")


def guess_direction_category(direction, home, away):
    """从用户输入的方向文字推测分类"""
    d = direction.strip()
    if home[:2] in d or d.startswith("主"):
        return "主胜"
    if away[:2] in d or d.startswith("客"):
        return "客胜"
    if "平" in d:
        return "平局"
    if "不败" in d:
        return f"{home[:2]}不败" if home[:2] in d else f"{away[:2]}不败"
    return d[:8]


# ═══════════════════════════════════════════
#  三 步 流 程
# ═══════════════════════════════════════════

def step1_input(args):
    """① 填比赛信息"""
    p(f"\n{'─'*50}")
    p(f"  ① 比赛信息")
    p(f"{'─'*50}")

    last = load_last_match()
    default_home = last.get("home", "") if last else ""
    default_away = last.get("away", "") if last else ""
    default_league = last.get("league", "wm26") if last else "wm26"

    home = clean(args.home) if args.home else input_clean(f"  主队 [{default_home}]: ") or default_home
    away = clean(args.away) if args.away else input_clean(f"  客队 [{default_away}]: ") or default_away
    if not home or not away:
        p("  ❌ 主队和客队不能为空")
        sys.exit(1)

    if args.league:
        league = clean(args.league)
    else:
        league_prompt = f"  联赛代码 ({'/'.join(COMMON_LEAGUES)}) [{default_league}]: "
        league = input_clean(league_prompt) or default_league

    return clean(home), clean(away), clean(league)


def step2_predict(home, away, league):
    """② 填预测"""
    p(f"\n{'─'*50}")
    p(f"  ② 预测内容")
    p(f"{'─'*50}")

    # 展示参考数据
    ref = fetch_reference(home, away, league)
    show_reference(ref)

    # 方向
    direction = input_clean(f"  方向 (如 主胜/平局/客胜/主队不败): ") or "均衡"
    # 概率
    while True:
        p_input = input_clean(f"  P_final (0~100%, 直接输数字): ")
        if not p_input:
            p_final = 0.5
            break
        try:
            val = float(p_input)
            if val > 1:
                val /= 100
            if 0 <= val <= 1:
                p_final = round(val, 3)
                break
            p("  请输入 0~100 之间的数字")
        except ValueError:
            p("  请输入数字")

    # 信心
    p(f"  信心: 1=值得关注  2=推荐  3=高度推荐")
    star_input = input_clean(f"  信心 (1-3) [2]: ") or "2"
    try:
        stars = max(1, min(3, int(star_input)))
    except ValueError:
        stars = 2
    confidence = "⭐" * stars
    star_map = {1: "值得关注", 2: "推荐", 3: "高度推荐"}

    # 备注（可选）
    notes = input_clean(f"  备注 (可选，回车跳过): ") or ""

    return direction, p_final, confidence, stars, notes


def step3_confirm(home, away, league, direction, p_final, confidence, stars, notes):
    """③ 确认 → 保存"""
    league_name = LEAGUE_ALIAS.get(league, league)
    star_map = {1: "值得关注", 2: "推荐", 3: "高度推荐"}

    p(f"\n{'─'*50}")
    p(f"  ③ 确认预测")
    p(f"{'─'*50}")
    p(f"  {home} vs {away}")
    p(f"  联赛: {league_name}  |  方向: {direction}")
    p(f"  P_final: {p_final:.1%}  |  信心: {confidence} ({star_map[stars]})")
    if notes:
        p(f"  备注: {notes}")

    ok = input_clean(f"\n  确认保存？(Y/n): ").strip().lower()
    if ok == "n":
        p("  ❌ 已取消")
        return False

    # --- 存数据库 ---
    dir_category = guess_direction_category(direction, home, away)
    record = {
        "id": f"MANUAL_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{home[:4]}_{away[:4]}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "home": home,
        "away": away,
        "league": league,
        "p_final": p_final,
        "direction": dir_category,
        "is_bet": False,
        "odds": 0.0,
        "source": "manual_analysis",
        "confidence": confidence,
        "result": {"status": "pending", "score_home": None, "score_away": None,
                    "actual_result": None, "correct": None},
        "analysis_notes": notes or "",
    }

    db = load_db()
    # 简单去重
    def norm(s):
        return s.strip().lower().replace(" ", "").replace("-","")
    hn, an = norm(home), norm(away)
    exists = False
    for rec in db["predictions"]:
        if norm(rec.get("home","")) == hn and norm(rec.get("away","")) == an \
           and rec.get("source") == "manual_analysis":
            exists = True
            break
    if exists:
        p("  ⚠️ 该对阵的手工预测已存在，跳过")
    else:
        db.setdefault("predictions", []).append(record)
        save_db(db)
        p(f"  ✅ 已保存到 predictions_db.json")

    # --- 存分析报告 .md ---
    os.makedirs(PRED_DIR, exist_ok=True)
    md_path = os.path.join(PRED_DIR, f"足球预测-{datetime.now().strftime('%Y-%m-%d')}-{home}vs{away}.md")
    if not os.path.exists(md_path):
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"""# {home} vs {away} — 人工预测

## 🎯 预测

| 指标 | 值 |
|:-----|:---|
| 方向 | **{direction}** |
| P_final | {p_final:.1%} |
| 信心 | {confidence} ({star_map[stars]}) |
| 联赛 | {league_name} |
| 分析时间 | {datetime.now().strftime('%Y-%m-%d %H:%M')} |

{ f'## 备注\\n\\n{notes}\\n' if notes else '' }
> ⚡ 由 quick_predict.py 生成
""")
        p(f"  ✅ 已保存分析报告")

    # --- 刷新看板（可选） ---
    rebuild = input_clean(f"\n  刷新看板 (report_to_html.py)？(Y/n): ").strip().lower()
    if rebuild != "n":
        p(f"\n  📊 刷新看板中...")
        subprocess.run(f'python "{os.path.join(BASE_DIR, "skill", "report_to_html.py")}"', shell=True)
        p(f"  ✅ 看板已刷新")
        p(f"  📱 手机访问: python skill/quick_predict.py")
    else:
        p(f"  💡 稍后可手动运行: python skill/report_to_html.py")

    p(f"\n{'='*50}")
    p(f"  ✅ 完成！")
    p(f"{'='*50}")
    return True


# ═══════════════════════════════════════════
#  主 入 口
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="⚡ 三步快速预测")
    parser.add_argument("--home", help="主队")
    parser.add_argument("--away", help="客队")
    parser.add_argument("--league", help="联赛代码")
    args = parser.parse_args()

    p(f"\n{'='*50}")
    p(f"  ⚡ 三步快速预测")
    p(f"  填 → 确认 → 自动入库")
    p(f"{'='*50}")

    home, away, league = step1_input(args)
    direction, p_final, confidence, stars, notes = step2_predict(home, away, league)
    step3_confirm(home, away, league, direction, p_final, confidence, stars, notes)


if __name__ == "__main__":
    main()
