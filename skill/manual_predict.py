#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人工预测管线 — 原始SKILL方法论（人+数据，无自动公式）

用法:
  python skill/manual_predict.py --home "巴西" --away "挪威" --league wm26
  python skill/manual_predict.py --home "首尔FC" --away "仁川联" --league kleague1 --quick

参数:
  --quick     跳过交互式输入，从 xg_estimator 自动取 L1 评分
  --league    联赛代码: wm26/kleague1/sportsdb
"""
import sys, json, os, subprocess, re, argparse
from datetime import datetime, timezone

# Windows 编码
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
PRED_DIR = os.path.join(BASE_DIR, "预测数据")
DB_FILE = os.path.join(CACHE_DIR, "predictions_db.json")

def p(text):
    try:
        print(str(text).encode("utf-8", errors="replace").decode("gbk", errors="replace"))
    except:
        print(str(text))

# ============================================================
# L1评分参考表（SKILL.md 原始规则）
# ============================================================
ATTACK_TABLE = {
    "range": [
        (">= 2.0", 9, 10, "顶级进攻火力"),
        ("1.5 ~ 1.99", 7, 8, "进攻强队"),
        ("1.0 ~ 1.49", 5, 6, "联赛平均"),
        ("0.5 ~ 0.99", 3, 4, "进攻偏弱"),
        ("< 0.5", 1, 2, "进攻乏力"),
    ]
}

DEFENSE_TABLE = {
    "range": [
        ("< 0.5", 9, 10, "钢铁防线"),
        ("0.5 ~ 0.99", 7, 8, "防守稳固"),
        ("1.0 ~ 1.49", 5, 6, "联赛平均"),
        ("1.5 ~ 1.99", 3, 4, "防线漏洞"),
        (">= 2.0", 1, 2, "防线崩溃"),
    ]
}

STYLE_MATRIX = {
    "传控vs防反": "🐢慢 → 控球方压制但难破密集",
    "防反vs传控": "⚡快 → 防反方有反击空间",
    "传控vs传控": "⚡快 → 中场争夺激烈",
    "防反vs防反": "🐢慢 → 小球(0-1球)",
    "均衡vs均衡": "⚖️ → 看临场发挥",
    "传控vs均衡": "⚡快 → 控球方占优",
    "防反vs均衡": "🐢慢 → 防反方等待机会",
}

LEAGUE_ALIAS = {
    "wm26": "世界杯", "WC": "世界杯",
    "kleague1": "K1联赛", "kleague2": "K2联赛",
    "jleague1": "J1联赛", "jleague2": "J2联赛",
    "sportsdb": "瑞典超/芬超",
    "bl1": "德甲", "epl": "英超", "pd": "西甲",
}

# ============================================================
# 获取 xg_estimator 数据作为参考
# ============================================================
def fetch_xg_data(home, away, league):
    """从 xg_estimator 获取参考数据"""
    cmd = f'python "{os.path.join(BASE_DIR, "skill", "xg_estimator.py")}" --home "{home}" --away "{away}" --league {league} --max-games 10'
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, timeout=60)
        out = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
    except:
        return {}

    data = {}
    # L1 scores
    ha = re.search(r"L1进攻评分:\s*([\d.]+)", out)
    hd = re.search(r"L1防守评分:\s*([\d.]+)", out)
    all_att = list(re.finditer(r"L1进攻评分:\s*([\d.]+)", out))
    all_def = list(re.finditer(r"L1防守评分:\s*([\d.]+)", out))

    data["home_attack"] = float(all_att[0].group(1)) if all_att else None
    data["home_defense"] = float(all_def[0].group(1)) if all_def else None
    data["away_attack"] = float(all_att[1].group(1)) if len(all_att) > 1 else None
    data["away_defense"] = float(all_def[1].group(1)) if len(all_def) > 1 else None

    # Lambda
    la = re.search(r"λ_A.*?([\d.]+)", out)
    lb = re.search(r"λ_B.*?([\d.]+)", out)
    data["lambda_A"] = float(la.group(1)) if la else None
    data["lambda_B"] = float(lb.group(1)) if lb else None

    # Source
    src = re.search(r"数据来源:\s*(\S+)", out)
    data["source"] = src.group(1) if src else "unknown"

    data["raw_output"] = out[:3000]
    return data

# ============================================================
# 人工分析核心流程
# ============================================================
def manual_predict(home, away, league="wm26", quick=False):
    """人工分析流程"""
    p(f"\n{'='*60}")
    p(f"  人工预测分析  (SKILL原始方法论)")
    p(f"  {home} vs {away}")
    p(f"  联赛: {LEAGUE_ALIAS.get(league, league)}")
    p(f"  时间: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}")
    p(f"{'='*60}")

    # Step 1: 获取参考数据（xG + ELO + 赔率）
    p(f"\n[1/4] 获取参考数据...")
    xg = fetch_xg_data(home, away, league)
    ha = xg.get("home_attack")
    hd = xg.get("home_defense")
    aa = xg.get("away_attack")
    ad = xg.get("away_defense")
    la = xg.get("lambda_A")
    lb = xg.get("lambda_B")

    p(f"  xG来源: {xg.get('source', '无')}")
    p(f"  L1进攻评分: 主队 {ha or '?'}  |  客队 {aa or '?'}")
    p(f"  L1防守评分: 主队 {hd or '?'}  |  客队 {ad or '?'}")
    p(f"  λ预期进球:  主队 {la or '?'}  |  客队 {lb or '?'}")

    # ELO 参考
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from skill.datafc_provider import get_team_elo
        elo_h = get_team_elo(home).get("elo", 1500)
        elo_a = get_team_elo(away).get("elo", 1500)
        elo_diff = elo_h - elo_a
        elo_mark = "🔺" if elo_diff > 100 else ("🔻" if elo_diff < -100 else "➖")
        p(f"  ELO评分:   主队 {elo_h}  |  客队 {elo_a}  (差 {elo_diff:+d}) {elo_mark}")
    except Exception:
        elo_h = elo_a = 1500
    elo_diff = elo_h - elo_a

    # 赔率参考
    odds_ref = ""
    for f in sorted(os.listdir(CACHE_DIR), reverse=True):
        if not f.startswith("odds_") or not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(CACHE_DIR, f), "r", encoding="utf-8") as _fh:
                _d = json.load(_fh)
            hn = home.lower().replace(" ", "")
            an = away.lower().replace(" ", "")
            fn = f.lower()
            if hn in fn and an in fn:
                oh = _d.get("odds_home", "?")
                od = _d.get("odds_draw", "?")
                oa = _d.get("odds_away", "?")
                odds_ref = f"  📊 市场赔率:  主{oh}  平{od}  客{oa}  (来自 {f})"
                break
        except Exception:
            continue
    if odds_ref:
        p(odds_ref)

    # Step 2: 输入L1评分
    p(f"\n[2/4] L1评分输入")
    if quick:
        h_att = ha or 5.0
        h_def = hd or 5.0
        a_att = aa or 5.0
        a_def = ad or 5.0
        p(f"  (quick模式—使用xg_estimator数据)")
    else:
        p(f"  L1进攻评分参考表:")
        for r, lo, hi, desc in [(">= 2.0", 9, 10, "顶级"), ("1.5~1.99", 7, 8, "强队"), ("1.0~1.49", 5, 6, "平均"), ("0.5~0.99", 3, 4, "偏弱"), ("< 0.5", 1, 2, "乏力")]:
            p(f"    xG_for/90 {r} → {lo}-{hi} ({desc})")
        p(f"  L1防守评分参考表:")
        for r, lo, hi, desc in [("< 0.5", 9, 10, "钢铁防线"), ("0.5~0.99", 7, 8, "稳固"), ("1.0~1.49", 5, 6, "平均"), ("1.5~1.99", 3, 4, "漏洞"), (">= 2.0", 1, 2, "崩溃")]:
            p(f"    xG_against/90 {r} → {lo}-{hi} ({desc})")

        try:
            h_att = float(input(f"  主队({home}) L1进攻评分 [参考{ha or '?'}]: ") or ha or 5.0)
            h_def = float(input(f"  主队({home}) L1防守评分 [参考{hd or '?'}]: ") or hd or 5.0)
            a_att = float(input(f"  客队({away}) L1进攻评分 [参考{aa or '?'}]: ") or aa or 5.0)
            a_def = float(input(f"  客队({away}) L1防守评分 [参考{ad or '?'}]: ") or ad or 5.0)
        except:
            h_att, h_def, a_att, a_def = ha or 5.0, hd or 5.0, aa or 5.0, ad or 5.0

    p(f"  → {home}: 进攻 {h_att}  防守 {h_def}")
    p(f"  → {away}: 进攻 {a_att}  防守 {a_def}")

    # Step 3: 分析输入
    p(f"\n[3/4] 分析")
    style_map = {f"{h}vs{a}": k for k in STYLE_MATRIX.keys() for h in ["传控","防反","均衡"] for a in ["传控","防反","均衡"] if f"{h}vs{a}" == k}

    if quick:
        home_style = "均衡"
        away_style = "均衡"
        notes = "(quick模式—自动生成)"
    else:
        home_style = input(f"  主队({home})战术风格 [传控/防反/均衡]: ") or "均衡"
        away_style = input(f"  客队({away})战术风格 [传控/防反/均衡]: ") or "均衡"
        notes = input("  分析要点 (回车跳过): ") or ""

    style_key = f"{home_style}vs{away_style}"
    style_analysis = STYLE_MATRIX.get(style_key, "⚖️ → 均衡对决")

    # P_final 估算（从 L1 评分 + ELO 差）
    score_base = (h_att * 0.4 + h_def * 0.4) - (a_att * 0.4 + a_def * 0.4)  # -9 ~ +9
    elo_factor = min(3, max(-3, elo_diff / 150))  # ±3 分封顶
    combined_score = score_base + elo_factor  # -12 ~ +12
    # 映射到 0.05 ~ 0.95
    p_final = max(0.05, min(0.95, 0.5 + combined_score * 0.04))
    p(f"  P_final估算: {p_final:.3f} (评分差{score_base:+.1f} + ELO系数{elo_factor:+.1f})")

    # Step 4: 推荐
    p(f"\n[4/4] 推荐")
    if quick:
        # 基于L1评分差 + ELO差 自动判断方向
        vs = combined_score
        if vs > 2.0:
            direction = f"{home}胜"
            stars = 3
        elif vs > 0.8:
            direction = f"{home}胜"
            stars = 2
        elif vs > -0.8:
            direction = f"{home}不败(双选)"
            stars = 2
        elif vs > -2.0:
            direction = f"{away}不败(双选)"
            stars = 2
        else:
            direction = f"{away}胜"
            stars = 2
        confidence = "⭐" * stars
        p(f"  (quick模式—评分差{score_base:+.1f}+ELO差{elo_factor:+.1f}→综合{combined_score:+.1f})")
    else:
        direction = input("  推荐方向 (如 巴西胜/平局/客队不败): ")
        stars_input = input("  信心 (1-3): ") or "2"
        try:
            stars = max(1, min(3, int(stars_input)))
        except:
            stars = 2
        confidence = "⭐" * stars

    p(f"\n  → 推荐: {direction} | {confidence}")
    p(f"  → 风格: {style_analysis}")

    # ============================================================
    # 生成预测文件
    # ============================================================
    league_name = LEAGUE_ALIAS.get(league, league)
    filename = f"足球预测-{datetime.now().strftime('%Y-%m-%d')}-{home}vs{away}.md"
    filepath = os.path.join(PRED_DIR, filename)

    # 推荐评级文字
    star_text = {3: "⭐⭐⭐ (高度推荐)", 2: "⭐⭐ (推荐)", 1: "⭐ (值得关注)"}
    star_desc = star_text.get(stars, "⭐")

    odds_str = (odds_ref or "").replace("  📊 ", "")
    report = f"""# {home} vs {away} — 人工预测报告

## 基本面

| 维度 | {home} | {away} |
|:-----|:-------|:-------|
| 联赛 | {league_name} | {league_name} |
| ELO评分 | {elo_h} | {elo_a} |
| L1进攻评分 | {h_att} | {a_att} |
| L1防守评分 | {h_def} | {a_def} |
| λ预期进球 | {la or '?'} | {lb or '?'} |
| 战术风格 | {home_style} | {away_style} |
| 市场赔率 | {odds_str} | |

## 分析

- **实力差**: ELO {elo_diff:+d} | 综合评分 {combined_score:+.1f}
- **风格矩阵**: {style_analysis}
- **分析要点**: {notes or '无'}

## 🎯 预测

| 指标 | 值 |
|:-----|:---|
| **方向** | **{direction}** |
| **信心** | {confidence} |
| **P_final** | {p_final:.3f} |

- **分析方法**: 原始SKILL人工研判
- **分析时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **系统**: 人工预测管线 v1.0

> ⚠️ 本预测基于人工分析，仅供参考。
"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report)
    p(f"\n  ✅ 已保存: {filename}")

    # ============================================================
    # 记录到 predictions_db.json
    # ============================================================
    def normalize(s):
        return s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")

    # 判断方向类别
    if home[:2] in direction or ("主" in direction and "不败" not in direction):
        dir_category = "主胜"
    elif away[:2] in direction or "客" in direction:
        dir_category = "客胜"
    elif "平" in direction:
        dir_category = "平局"
    elif "不败" in direction:
        if home[:2] in direction:
            dir_category = "主队不败"
        else:
            dir_category = "客队不败"
    else:
        dir_category = direction[:8]

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
        "result": {
            "status": "pending",
            "score_home": None,
            "score_away": None,
            "actual_result": None,
            "correct": None,
        },
        "analysis_notes": notes or "",
        "l1_scores": {"home_attack": h_att, "home_defense": h_def,
                       "away_attack": a_att, "away_defense": a_def},
    }

    db = {"predictions": []}
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            db = json.load(f)

    # 去重
    hn, an = normalize(home), normalize(away)
    exists = False
    for p_rec in db["predictions"]:
        ph, pa = normalize(p_rec.get("home", "")), normalize(p_rec.get("away", ""))
        if (hn == ph and an == pa) and p_rec.get("source") == "manual_analysis":
            exists = True
            p("  同名手工分析已存在，跳过记录")
            break

    if not exists:
        db.setdefault("predictions", []).append(record)
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
        p(f"  ✅ 已记录到 predictions_db.json")

    # 返回结果
    result = {
        "home": home, "away": away, "league": league,
        "direction": direction, "confidence": confidence,
        "scores": {"home_attack": h_att, "home_defense": h_def,
                   "away_attack": a_att, "away_defense": a_def},
        "file": filepath,
    }
    return result

# ============================================================
# 主入口
# ============================================================
def main():
    parser = argparse.ArgumentParser(description="人工预测管线 (SKILL原始方法论)")
    parser.add_argument("--home", required=True, help="主队")
    parser.add_argument("--away", required=True, help="客队")
    parser.add_argument("--league", default="wm26", help="联赛代码 (默认wm26)")
    parser.add_argument("--quick", action="store_true", help="自动获取L1评分，跳过输入")
    parser.add_argument("--force", action="store_true", help="跳过赛程校验，强制生成预测")
    args = parser.parse_args()

    # ── 赛程校验门禁 — 防止为不存在的比赛生成预测 ──
    if not args.force:
        try:
            sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
            from skill.datafc_provider import is_match_scheduled
            scheduled, detail = is_match_scheduled(args.home, args.away, args.league)
            if not scheduled:
                p(f"\n⚠️  ⚠️  ⚠️  {detail}")
                p(f"    继续运行将生成一场不存在的比赛预测！")
                p(f"    请检查球队名或联赛标识是否正确。")
                p(f"    若要强制跳过校验，添加 --force 参数。\n")
                return
        except ImportError:
            pass  # 无法加载校验函数时静默跳过

    result = manual_predict(args.home, args.away, args.league, quick=args.quick)

    p(f"\n{'='*60}")
    p(f"  预测完成!")
    p(f"  {result['home']} vs {result['away']}")
    p(f"  推荐: {result['direction']} | {result['confidence']}")
    p(f"  文件: {result['file']}")
    p(f"{'='*60}")

if __name__ == "__main__":
    main()
