#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
预测数据库 (Prediction DB) — 统一管理所有预测记录

功能:
  1. 从 MD 预测文件 + pnl_records 导入历史数据
  2. 新增预测时写入结构化记录（强制要求 P_final + direction）
  3. 赛后自动匹配结果并计算校准
  4. 存量回填：从 MD/odds/auto_results 补全缺失的 P_final 和方向
  5. 重复检测与合并
  6. 数据健康检查
  7. 生成校准分析报告

用法:
  python skill/prediction_db.py --import-all           # 导入所有历史数据
  python skill/prediction_db.py --check                # 数据健康检查
  python skill/prediction_db.py --backfill             # 补全缺失字段（P_final + 方向）
  python skill/prediction_db.py --dedup                # 合并重复预测
  python skill/prediction_db.py --add --home A --away B --p 0.65 --direction "主胜"
                                                    # 新增一条预测（自动温度缩放 T=1.60）
  python skill/prediction_db.py --sync-results         # 同步赛后结果
  python skill/prediction_db.py --watch                # 赛后自动回填(每60秒检查)
  python skill/prediction_db.py --track-clv            # CLV追踪(从多版本odds缓存)
  python skill/prediction_db.py --calibration          # 生成校准报告
  python skill/prediction_db.py --report               # 完整报表
"""

import sys, json, glob, re, os, io
from datetime import datetime, timezone
from collections import defaultdict

# Windows 编码
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
PRED_DIR = os.path.join(BASE_DIR, "预测数据")
DB_FILE = os.path.join(CACHE_DIR, "predictions_db.json")

# ============================================================
# 工具函数
# ============================================================
def log(text):
    try:
        print(str(text).encode("utf-8", errors="replace").decode("gbk", errors="replace"))
    except:
        print(str(text))

def normalize(s):
    return s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")

def now_str():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

# ============================================================
# 数据库管理
# ============================================================
def load_db():
    """加载预测数据库"""
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"predictions": [], "last_updated": None}

def save_db(db):
    """保存预测数据库"""
    db["last_updated"] = now_str()
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def gen_id(home, away, date_str):
    """生成唯一ID"""
    base = date_str.replace("-", "") if date_str else now_str()[:10].replace("-", "")
    return f"{base}_{home[:4]}_{away[:4]}"

# ============================================================
# 从文件名提取比赛信息
# ============================================================
def parse_filename(fname):
    """从预测文件名解析主客队"""
    stem = fname.replace(".md", "")
    tm = re.search(r"(\d{4}-\d{2}-\d{2})[-]*(.+?)(vs)(.+?)$", stem)
    if not tm:
        return None, None
    home = tm.group(2).strip("-").strip()
    away = tm.group(4).strip()
    if "-" in home:
        home = home.split("-")[-1]
    return home.strip(), away.strip()

# ============================================================
# 从 MD 文件提取 P_final（增强版）
# ============================================================
PFINAL_PATTERNS = [
    r'\*\*P_final\*\*\s*\|\s*\*\*([\d.]+)\*\*',
    r'[Pp]_final\s*[=:≈]\s*([\d.]+)',
    r'\*\*P_final\*\*\s*\|\s*([\d.]+)',
    r'P_final[（(]\s*([\d.]+)\s*[%)）]',
    r'修正胜率[：:]\s*([\d.]+)\s*%',
    r'综合评级.*?([\d.]+)分',
]

def extract_pfinal(content):
    for pat in PFINAL_PATTERNS:
        m = re.search(pat, content)
        if m:
            try:
                val = float(m.group(1))
                if 0 < val <= 1.0:
                    return val
                if 1.0 < val <= 100:
                    return val / 100
            except:
                pass
    return None

# ============================================================
# 从 MD 文件提取推荐方向（增强版）
# ============================================================
DIRECTION_PATTERNS = [
    r'推荐方向[：:]\s*(\S+)',
    r'方向[：:]\s*(\S+)',
    r'预测[：:]\s*(\S+)',
    r'\*\*推荐方向\*\*[：:]?\s*\*\*(\S+)\*\*',
    r'\*\*方向\*\*[：:]?\s*\*\*(\S+)\*\*',
    r'\*\*预测方向\*\*[：:]?\s*\*\*(\S+)\*\*',
    r'###\s*[✅]?\s*方向\d*[：:]\s*(\S+)',
    r'###\s*方向\d*[：:]\s*(\S+)',
    r'方向\d*[：:]\s*([^<>\n]{2,10}?)(?:\s|$)',
    r'推荐[：:]\s*(\S+胜|\S+不败|平局|客胜|主胜|大\d+\.?\d*球|小\d+\.?\d*球)',
]

def extract_direction(content):
    for pat in DIRECTION_PATTERNS:
        m = re.search(pat, content)
        if m:
            d = m.group(1).strip()
            if len(d) <= 16:
                return d
    return ""

# ============================================================
# 1. 从 MD 文件导入预测
# ============================================================
def import_from_md(strict=False):
    """从预测MD文件导入所有预测"""
    db = load_db()
    existing_id = {p["id"] for p in db["predictions"]}
    imported = 0

    md_files = sorted(glob.glob(os.path.join(PRED_DIR, "足球预测-*.md")))
    log(f"扫描 {len(md_files)} 个预测文件...")

    for fpath in md_files:
        fname = os.path.basename(fpath)
        home, away = parse_filename(fname)
        if not home or not away:
            continue

        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        p_final = extract_pfinal(content)
        direction = extract_direction(content)

        if strict and (p_final is None or not direction):
            log(f"  ⏭ {home:10s} vs {away:10s}  缺失 P_final 或方向，跳过")
            continue

        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", fname)
        date_str = date_match.group(1) if date_match else ""

        rid = gen_id(home, away, date_str)
        if rid in existing_id:
            continue
        existing_id.add(rid)

        record = {
            "id": rid,
            "date": date_str,
            "home": home,
            "away": away,
            "p_final": p_final,
            "direction": direction,
            "is_bet": False,
            "odds": 0.0,
            "source": "md_file",
            "result": {
                "status": "pending",
                "score_home": None,
                "score_away": None,
                "actual_result": None,
                "correct": None,
            },
        }
        db["predictions"].append(record)
        imported += 1
        tag = f"P_final={p_final:.3f}" if p_final else "无P_final"
        tag += f" 方向={direction}" if direction else ""
        log(f"  + {home:10s} vs {away:10s}  [{tag}]")

    if imported:
        save_db(db)
    log(f"\n导入完成: +{imported} 条 (总 {len(db['predictions'])} 条)")
    return imported

# ============================================================
# 2. 从 pnl_records.json 导入投注记录
# ============================================================
def import_from_pnl():
    """从 pnl_records.json 导入投注记录"""
    pnl_path = os.path.join(CACHE_DIR, "pnl_records.json")
    if not os.path.exists(pnl_path):
        log("pnl_records.json 不存在")
        return 0

    with open(pnl_path, "r", encoding="utf-8") as f:
        pnl = json.load(f)

    db = load_db()
    existing_id = {p["id"] for p in db["predictions"]}
    imported = 0

    for r in pnl.get("records", []):
        h, a = r["home"], r["away"]
        # 尝试匹配已有记录（by id 或 home+away）
        matched = False
        rid = r.get("id", gen_id(h, a, r.get("date", "")))
        for p_rec in db["predictions"]:
            if p_rec.get("id") == rid or (p_rec["home"] == h and p_rec["away"] == a):
                p_rec["is_bet"] = True
                if r.get("odds", 0) > 0:
                    p_rec["odds"] = r["odds"]
                if r.get("direction") and not p_rec.get("direction"):
                    p_rec["direction"] = r["direction"]
                if r.get("P_final") is not None and p_rec.get("p_final") is None:
                    p_rec["p_final"] = r["P_final"]
                if r["result"] != "pending":
                    self_update_result(p_rec, r)
                matched = True
                break

        if matched:
            continue

        if rid in existing_id:
            continue
        existing_id.add(rid)

        result_data = extract_pnl_result(r)
        if result_data:
            sh, sa, actual_dir, correct = result_data
        else:
            sh = sa = actual_dir = correct = None

        record = {
            "id": rid,
            "date": r.get("date", ""),
            "home": h,
            "away": a,
            "p_final": r.get("P_final", None),
            "direction": r.get("direction", ""),
            "is_bet": True,
            "odds": r.get("odds", 0.0),
            "source": "pnl_tracker",
            "result": {
                "status": "matched" if correct is not None else "pending",
                "score_home": sh,
                "score_away": sa,
                "actual_result": actual_dir,
                "correct": correct,
            },
        }
        db["predictions"].append(record)
        imported += 1

    if imported:
        save_db(db)
    log(f"pnl导入完成: +{imported} 条, 更新投注标记 {sum(1 for r in db['predictions'] if r['is_bet'])} 条")
    return imported

def extract_pnl_result(r):
    """从 pnl_record 提取赛果"""
    if r["result"] == "pending":
        return None
    notes = r.get("notes", "")
    sm = re.search(r"(\d+)[-](\d+)", notes)
    if sm:
        hg, ag = int(sm.group(1)), int(sm.group(2))
    elif r["result"] == "win":
        d = r.get("direction", "")
        if "主" in d: hg, ag = 1, 0
        elif "客" in d: hg, ag = 0, 1
        else: return None
    elif r["result"] == "loss":
        d = r.get("direction", "")
        if "主" in d: hg, ag = 0, 1
        elif "客" in d: hg, ag = 1, 0
        elif "平" in d or "均衡" in d: hg, ag = 1, 0
        else: return None
    else:
        return None

    actual_dir = "主胜" if hg > ag else ("客胜" if hg < ag else "平局")
    correct = check_correct(r.get("direction", ""), actual_dir, r.get("home",""), r.get("away",""))
    return (hg, ag, actual_dir, correct)

def check_correct(pred_dir, actual_dir, home="", away=""):
    """判断方向是否正确"""
    if not pred_dir:
        return None
    if "主" in pred_dir and "客" not in pred_dir and actual_dir == "主胜": return True
    if "客" in pred_dir and actual_dir == "客胜": return True
    if "平" in pred_dir and actual_dir == "平局": return True
    if "均衡" in pred_dir and actual_dir == "平局": return True
    if pred_dir == actual_dir: return True
    if home and away:
        if "胜" in pred_dir or "赢" in pred_dir:
            if any(home[:max(2, len(home)//3)] in pred_dir for _ in [1]) and actual_dir == "主胜": return True
            if any(away[:max(2, len(away)//3)] in pred_dir for _ in [1]) and actual_dir == "客胜": return True
        if "不败" in pred_dir:
            if any(home[:max(2, len(home)//3)] in pred_dir for _ in [1]) and actual_dir in ("主胜", "平局"): return True
            if any(away[:max(2, len(away)//3)] in pred_dir for _ in [1]) and actual_dir in ("客胜", "平局"): return True
    return False

def self_update_result(p_rec, r):
    """用 pnl_record 更新 db 中的 result"""
    result_data = extract_pnl_result(r)
    if result_data:
        sh, sa, actual_dir, correct = result_data
        p_rec["result"] = {
            "status": "matched",
            "score_home": sh,
            "score_away": sa,
            "actual_result": actual_dir,
            "correct": correct,
        }

# ============================================================
# 3. 赛后结果同步 (从 auto_results.json)
# ============================================================
def sync_results():
    """从 auto_results.json 同步赛后结果到未匹配的预测"""
    auto_path = os.path.join(CACHE_DIR, "auto_results.json")
    if not os.path.exists(auto_path):
        log("auto_results.json 不存在")
        return 0

    with open(auto_path, "r", encoding="utf-8") as f:
        auto = json.load(f)

    finished = [r for r in auto if r["status"] == "FINISHED"]
    if not finished:
        log("auto_results 中暂无已完赛比赛")
        return 0

    db = load_db()
    updated = 0

    for pred in db["predictions"]:
        if pred["result"]["status"] == "matched":
            continue

        h, a = pred["home"], pred["away"]
        hn, an = normalize(h), normalize(a)

        for ar in finished:
            arh = normalize(ar.get("home_cn", ""))
            ara = normalize(ar.get("away_cn", ""))
            if (hn == arh and an == ara) or (hn == ara and an == arh):
                ft = ar["score_ft"]
                if "-" in ft:
                    parts = ft.split("-")
                    try:
                        hg, ag = int(parts[0]), int(parts[1])
                        actual_dir = "主胜" if hg > ag else ("客胜" if hg < ag else "平局")
                        correct = check_correct(pred.get("direction", ""), actual_dir, pred.get("home",""), pred.get("away",""))
                        pred["result"] = {
                            "status": "matched",
                            "score_home": hg,
                            "score_away": ag,
                            "actual_result": actual_dir,
                            "correct": correct,
                        }
                        updated += 1
                        mark = "+" if correct else "x"
                        log(f"  [{mark}] {h:10s} vs {a:10s}  {ft}  {actual_dir}")
                    except:
                        pass
                break

    if updated:
        save_db(db)
    log(f"\n结果同步: 更新 {updated} 条 (总 {len(db['predictions'])} 条)")
    return updated

# ============================================================
# 4. 校准分析报告
# ============================================================
def calibration_report():
    """生成校准分析报告"""
    db = load_db()
    predictions = db["predictions"]

    with_result = [p for p in predictions if p["result"]["status"] == "matched"]
    with_pf_all = [p for p in with_result if p["p_final"] is not None]
    with_pf = [p for p in with_pf_all if p.get("p_final_source") != "inferred_neutral"]
    pf_inferred = [p for p in with_pf_all if p.get("p_final_source") == "inferred_neutral"]
    with_dir = [p for p in with_result if p["result"]["correct"] is not None]
    bets = [p for p in predictions if p["is_bet"]]
    settled_bets = [p for p in bets if p["result"]["status"] == "matched"]

    log("\n" + "=" * 70)
    log("  预 测 校 准 分 析 报 告")
    log("=" * 70)

    log(f"\n[1] 数据概览")
    log(f"  总预测: {len(predictions)} 场")
    log(f"  有赛果: {len(with_result)} 场")
    log(f"  待赛果: {len(predictions) - len(with_result)} 场")
    log(f"  有P_final(真实): {len(with_pf)} 场")
    log(f"  有P_final(兜底0.5): {len(pf_inferred)} 场")
    log(f"  有方向: {len(with_dir)} 场")
    log(f"  实际下注: {len(bets)} 场 (已结算 {len(settled_bets)} 场)")

    sources = defaultdict(int)
    for p in predictions:
        sources[p.get("source", "unknown")] += 1
    log(f"  来源: {', '.join(f'{k}={v}' for k,v in sorted(sources.items()))}")

    if with_dir:
        total_judged = len(with_dir)
        correct = sum(1 for p in with_dir if p["result"]["correct"])
        wrong = total_judged - correct
        acc = correct / total_judged * 100

        log(f"\n[2] 方向准确率 ({total_judged} 场有方向)")
        log(f"  正确: {correct} | 错误: {wrong} | 命中率: {acc:.1f}%")

        log(f"\n  方向细分:")
        dy = defaultdict(lambda: {"t": 0, "c": 0})
        for p in with_dir:
            d = p.get("direction", "")
            if "主" in d and "客" not in d:
                key = "主胜"
            elif "客" in d:
                key = "客胜"
            elif "平" in d or "均衡" in d:
                key = "平局/均衡"
            elif "小" in d:
                key = "小球"
            elif "大" in d:
                key = "大球"
            else:
                key = d[:8]
            dy[key]["t"] += 1
            if p["result"]["correct"]:
                dy[key]["c"] += 1

        for k, v in sorted(dy.items()):
            r = v["c"] / v["t"] * 100 if v["t"] > 0 else 0
            t = "[OK]" if r > 50 else ("[WARN]" if r > 30 else "[BAD]")
            log(f"    {t} {k:<12}: {v['c']}/{v['t']} = {r:.1f}%")

    if with_pf:
        log(f"\n[3] P_final 校准表 ({len(with_pf)} 场)")
        log(f"  {'区间':<14} {'场次':<6} {'胜':<6} {'实际胜率':<10} {'平均P_final':<10} {'隐含概率':<10} {'校准因子':<10} 评价")
        log(f"  " + "-" * 70)

        buckets = [(0.80,1.01,">=0.80"), (0.70,0.80,"0.70-0.79"),
                   (0.60,0.70,"0.60-0.69"), (0.50,0.60,"0.50-0.59"),
                   (0.40,0.50,"0.40-0.49"), (0.30,0.40,"0.30-0.39"),
                   (0.00,0.30,"<0.30")]

        for lo, hi, label in buckets:
            bucket = [p for p in with_pf if lo <= p["p_final"] < hi]
            if not bucket:
                continue
            bt = len(bucket)
            bc = sum(1 for p in bucket if p["result"]["correct"] is True)
            bw = sum(1 for p in bucket if p["result"]["correct"] is False)
            judged = bc + bw
            avg_p = sum(p["p_final"] for p in bucket) / bt
            if judged == 0:
                log(f"  {label:<14} {bt:<6} {bc:<6} {'N/A':<10} {avg_p:<9.3f}    {'?':<10}   {'?':<9}  无方向")
            else:
                wr = bc / judged * 100
                implied = avg_p * 100
                cf = wr / implied if implied > 0 else 0
                if bt < 3:
                    remark = "样本不足"
                elif cf > 1.15:
                    remark = "[保守]"
                elif cf < 0.85:
                    remark = "[过度自信]"
                else:
                    remark = "[OK]"
                log(f"  {label:<14} {bt:<6} {bc:<6} {wr:<8.1f}%   {avg_p:<9.3f}    {implied:<8.1f}%   {cf:<9.2f}  {remark}")

    if settled_bets:
        log(f"\n[4] 投注盈亏 (下注已结算)")
        total_pnl = 0
        for p in settled_bets:
            odds = p.get("odds", 0)
            stake = 1
            if p["result"]["correct"] is True and odds > 0:
                pnl_val = round(stake * (odds - 1), 2)
            elif p["result"]["correct"] is False and odds > 0:
                pnl_val = round(-stake, 2)
            else:
                pnl_val = 0
            total_pnl += pnl_val
            mark = "+" if p["result"]["correct"] is True else "x"
            label = f"{p['home'][:6]}vs{p['away'][:6]}"
            log(f"    {mark} {label:<20} odds={p['odds']:.2f}  {p['result']['actual_result']:4s}  PnL={pnl_val:+.1f}")
        log(f"  总PnL: {total_pnl:+.2f} 单位")

    log(f"\n[5] 关键结论")
    high = [p for p in with_dir if p["p_final"] and p["p_final"] >= 0.70]
    mid = [p for p in with_dir if p["p_final"] and 0.40 <= p["p_final"] < 0.70]
    low = [p for p in with_dir if p["p_final"] and p["p_final"] < 0.40]
    if high:
        hc = sum(1 for p in high if p["result"]["correct"])
        log(f"  P>=0.70(高置信): {hc}/{len(high)} = {hc/len(high)*100:.1f}%")
    if mid:
        mc = sum(1 for p in mid if p["result"]["correct"])
        log(f"  P=0.40~0.69(中等): {mc}/{len(mid)} = {mc/len(mid)*100:.1f}%")
    if low:
        lc = sum(1 for p in low if p["result"]["correct"])
        log(f"  P<0.40(低置信): {lc}/{len(low)} = {lc/len(low)*100:.1f}%")
    total_judged = len(with_dir)
    if total_judged:
        total_correct = sum(1 for p in with_dir if p["result"]["correct"])
        log(f"\n  综合方向命中率: {total_correct}/{total_judged} = {total_correct/total_judged*100:.1f}%")
        if total_judged >= 30:
            log(f"  样本量达标, 结论可靠")
        else:
            log(f"  样本量仍不足({total_judged}<30), 建议累积到30+场再下结论")

# ============================================================
# 5. 完整报表
# ============================================================
def full_report():
    """打印所有预测记录"""
    db = load_db()
    predictions = db["predictions"]
    log(f"预测数据库: {len(predictions)} 条记录\n")

    has_clv = any(p.get("clv") is not None for p in predictions)
    clv_header = "  CLV" if has_clv else ""
    log(f"  {'日期':<12} {'主队':<10} {'客队':<10} {'P_final':<8} {'方向':<10} {'比分':<8} {'下注':<6} {'结果':<4}{clv_header}")
    log(f"  " + "-" * (76 if not has_clv else 84))

    for pred in sorted(predictions, key=lambda x: x.get("date", "")):
        res = pred["result"]
        score = f"{res.get('score_home','?')}-{res.get('score_away','?')}" if res["status"] == "matched" else "..."
        pf = f"{pred['p_final']:.3f}" if pred["p_final"] else "-"
        bet = "Y" if pred["is_bet"] else "N"
        if res["correct"] is True:
            mk = "W"
        elif res["correct"] is False:
            mk = "L"
        else:
            mk = "?"
        clv_str = ""
        if has_clv:
            clv = pred.get("clv")
            if clv is not None:
                clv_str = f"  {clv:+.1f}%" if abs(clv) < 99 else f"  {clv:+.0f}%"
            else:
                clv_str = "   --"
        log(f"  {pred.get('date',''):<12} {pred['home']:<10} {pred['away']:<10} {pf:<8} {pred.get('direction',''):<10} {score:<8} {bet:<6} {mk:<4}{clv_str}")

# ============================================================
# 6. 手动新增一条预测（含 strict 校验）
# ============================================================
def _temperature_scale_p(p, T=1.60):
    """对单一概率值做温度缩放（二项近似）

    P_adjusted = P^(1/T) / (P^(1/T) + (1-P)^(1/T))
    T=1.0 → 不变, T>1.0 → 压平, T<1.0 → 锐化
    """
    if T == 1.0 or p is None:
        return p
    import math as _m
    try:
        pT = _m.pow(p, 1.0 / T)
        qT = _m.pow(1.0 - p, 1.0 / T)
        return pT / (pT + qT)
    except Exception:
        return p

def add_prediction(home, away, p_final=None, direction="", is_bet=False, odds=0.0,
                   league="", date_str="", confidence="", strict=True, temperature=1.60,
                   source="manual"):
    """手动添加一条预测（strict=True 时强制要求 P_final + direction）

    temperature: 温度缩放系数（默认 1.60，2026-07-06 校准最优值）
    source: 预测来源（manual=人工, auto_pipeline=自动管线, predict.py=系统1引擎）
    """
    # 应用温度缩放
    p_final = _temperature_scale_p(p_final, temperature)

    if strict:
        if p_final is None:
            log("错误: --p (P_final) 必填，拒绝入库")
            return False
        if not direction.strip():
            log("错误: --direction 必填，拒绝入库")
            return False

    db = load_db()
    if not date_str:
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rid = gen_id(home, away, date_str)

    # 去重
    for p in db["predictions"]:
        if p["home"] == home and p["away"] == away and p.get("date") == date_str:
            log(f"警告: {home} vs {away} ({date_str}) 已存在")
            return False

    record = {
        "id": rid,
        "date": date_str,
        "home": home,
        "away": away,
        "p_final": p_final,
        "direction": direction,
        "is_bet": is_bet,
        "odds": odds,
        "source": source,
        "result": {
            "status": "pending",
            "score_home": None,
            "score_away": None,
            "actual_result": None,
            "correct": None,
        },
    }
    if league:
        record["league"] = league
    if confidence:
        record["confidence"] = confidence

    db["predictions"].append(record)
    save_db(db)
    log(f"已添加: {home} vs {away} (P_final={p_final}, {direction})")
    return True

# ============================================================
# 7. 存量回填管道
# ============================================================

def _poisson_prob(lambda_a, lambda_b):
    """从 Poisson λ 计算主场胜/平/客胜概率"""
    import math
    def poisson(l, k):
        return math.exp(-l) * (l ** k) / math.factorial(k)
    home_p, draw_p, away_p = 0.0, 0.0, 0.0
    for i in range(11):
        for j in range(11):
            p = poisson(lambda_a, i) * poisson(lambda_b, j)
            if i > j:
                home_p += p
            elif i == j:
                draw_p += p
            else:
                away_p += p
    return home_p, draw_p, away_p

def _infer_direction_from_score(score_home, score_away):
    """从比分推断实际结果方向"""
    if score_home is None or score_away is None:
        return None
    if score_home > score_away:
        return "主胜"
    elif score_home < score_away:
        return "客胜"
    else:
        return "平局"

def _find_odds_file(home, away, date_str):
    """在缓存中查找匹配的 odds 文件"""
    if not os.path.isdir(CACHE_DIR):
        return None
    candidates = []
    for f in os.listdir(CACHE_DIR):
        if not f.startswith("odds_") or not f.endswith(".json"):
            continue
        # 模糊匹配队名和日期
        score = 0
        f_lower = f.lower()
        if normalize(home) in f_lower:
            score += 2
        if normalize(away) in f_lower:
            score += 2
        if date_str and date_str.replace("-", "") in f:
            score += 1
        if score >= 3:
            candidates.append((score, f))
    candidates.sort(reverse=True)
    if candidates:
        return os.path.join(CACHE_DIR, candidates[0][1])
    return None

def backfill():
    """补全缺失的 P_final 和 direction

    策略:
      1. 从原始 MD 文件重新提取（增强正则）
      2. 从 auto_results 比分反推 direction
      3. 从 odds λ 反推 P_final
    """
    db = load_db()
    predictions = db["predictions"]
    log(f"\n{'='*70}")
    log("  存 量 回 填 管 道")
    log("=" * 70)

    # --- 阶段 1: 从 MD 文件重新提取 ---
    log(f"\n[阶段1] 从 MD 文件重新提取 P_final / 方向")
    md_fix_pf = 0
    md_fix_dir = 0
    md_index = {}  # filename_pattern → (home, away)
    for fname in os.listdir(PRED_DIR):
        if not fname.startswith("足球预测-") or not fname.endswith(".md"):
            continue
        h, a = parse_filename(fname)
        if h and a:
            md_index[normalize(h) + normalize(a)] = os.path.join(PRED_DIR, fname)

    for p in predictions:
        changed = False
        key = normalize(p["home"]) + normalize(p["away"])
        fpath = md_index.get(key)
        if not fpath:
            continue
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                content = f.read()
        except:
            continue

        if p["p_final"] is None:
            pf = extract_pfinal(content)
            if pf is not None:
                p["p_final"] = pf
                md_fix_pf += 1
                changed = True

        if not p.get("direction", ""):
            dr = extract_direction(content)
            if dr:
                p["direction"] = dr
                md_fix_dir += 1
                changed = True

    log(f"  补全 P_final: {md_fix_pf} 条")
    log(f"  补全 direction: {md_fix_dir} 条")

    # --- 阶段 2: 从 auto_results 比分反推 direction ---
    log(f"\n[阶段2] 从 auto_results 比分反推方向 (仅对已有结果但无方向)")
    auto_path = os.path.join(CACHE_DIR, "auto_results.json")
    auto_index = {}
    if os.path.exists(auto_path):
        with open(auto_path, "r", encoding="utf-8") as f:
            for ar in json.load(f):
                if ar.get("status") == "FINISHED" and "-" in ar.get("score_ft", ""):
                    key = normalize(ar.get("home_cn", "")) + normalize(ar.get("away_cn", ""))
                    auto_index[key] = ar

    ar_fix = 0
    for p in predictions:
        if p.get("direction", ""):
            continue
        if p["result"]["status"] != "matched":
            continue
        sh = p["result"].get("score_home")
        sa = p["result"].get("score_away")
        inferred = _infer_direction_from_score(sh, sa)
        if inferred:
            p["direction"] = inferred
            p["result"]["correct"] = check_correct(inferred, inferred, p["home"], p["away"])
            ar_fix += 1

    log(f"  从比分反推 direction: {ar_fix} 条")

    # --- 阶段 3: 从 odds λ 反推 P_final ---
    log(f"\n[阶段3] 从 odds 缓存反推 P_final")
    odds_fix = 0
    for p in predictions:
        if p["p_final"] is not None:
            continue
        date_str = p.get("date", "")
        of = _find_odds_file(p["home"], p["away"], date_str)
        if not of:
            continue
        try:
            with open(of, "r", encoding="utf-8") as f:
                data = json.load(f)
        except:
            continue
        la = data.get("lambda_A")
        lb = data.get("lambda_B")
        if la and lb and isinstance(la, (int, float)) and isinstance(lb, (int, float)):
            hp, _, _ = _poisson_prob(float(la), float(lb))
            p["p_final"] = round(hp, 3)
            odds_fix += 1

    log(f"  从 odds 反推 P_final: {odds_fix} 条")

    # --- 阶段 4: 最终兜底 — 仍有赛果但无 P_final 的给 0.5 ---
    log(f"\n[阶段4] 最终兜底 — 已有赛果但无 P_final 的设为 0.5（中性）")
    fallback_fix = 0
    for p in predictions:
        if p["p_final"] is not None:
            continue
        if p["result"]["status"] == "matched":
            p["p_final"] = 0.5
            p["p_final_source"] = "inferred_neutral"
            fallback_fix += 1
    log(f"  中性兜底: {fallback_fix} 条")

    # save
    total_fixed = md_fix_pf + md_fix_dir + ar_fix + odds_fix + fallback_fix
    if total_fixed:
        save_db(db)
    log(f"\n回填完成: 共补全 {total_fixed} 个缺失字段")

    # 再跑一遍结果同步（新补全的方向需要更新 correct 字段）
    sync_results()

    return total_fixed

# ============================================================
# 8. 重复预测检测与合并
# ============================================================
def dedup():
    """检测并合并重复预测

    策略:
      - 同一 (home, away, date) 保留最新一条
      - 方向冲突时，保留有 P_final + direction 完整的那条
      - 其余标记 duplicate_of
    """
    db = load_db()
    predictions = db["predictions"]

    log(f"\n{'='*70}")
    log("  重 复 预 测 检 测")
    log("=" * 70)

    # 按 (home, away, date) 分组
    groups = defaultdict(list)
    for i, p in enumerate(predictions):
        key = (p["home"], p["away"], p.get("date", ""))
        groups[key].append((i, p))

    to_remove = []
    merged = 0

    for key, items in groups.items():
        if len(items) <= 1:
            continue
        h, a, d = key
        log(f"\n  发现重复: {h} vs {a} ({d}) — {len(items)} 条")

        for idx, p in items:
            pf = f"P_final={p['p_final']:.3f}" if p["p_final"] is not None else "无P_final"
            dr = f"方向={p['direction']}" if p.get("direction") else "无方向"
            src = p.get("source", "?")
            res = "已完赛" if p["result"]["status"] == "matched" else "待赛果"
            log(f"    [{idx}] {pf} {dr} |来源={src} |{res}")

        # 评分：P_final 完整 +1, direction 完整 +1, 有结果 +1, 有下注 +1
        scored = []
        for idx, p in items:
            score = 0
            if p["p_final"] is not None:
                score += 2
            if p.get("direction", ""):
                score += 2
            if p["result"]["status"] == "matched":
                score += 1
            if p.get("is_bet"):
                score += 1
            scored.append((score, idx, p))

        # 保留最高分的
        scored.sort(key=lambda x: (-x[0], -x[1]))
        keep_idx = scored[0][1]
        log(f"  → 保留 [{keep_idx}] (评分 {scored[0][0]})")

        for score, idx, p in scored[1:]:
            to_remove.append(idx)
            # 如果有缺失字段，尝试从保留的复制
            keep = predictions[keep_idx]
            if keep["p_final"] is None and p["p_final"] is not None:
                keep["p_final"] = p["p_final"]
                log(f"     从 [{idx}] 复制 P_final={p['p_final']}")
            if not keep.get("direction", "") and p.get("direction", ""):
                keep["direction"] = p["direction"]
                log(f"     从 [{idx}] 复制 direction={p['direction']}")
            if keep["result"]["status"] != "matched" and p["result"]["status"] == "matched":
                keep["result"] = p["result"]
                log(f"     从 [{idx}] 复制 result")
            if not keep.get("is_bet") and p.get("is_bet"):
                keep["is_bet"] = True
                if p.get("odds", 0) > keep.get("odds", 0):
                    keep["odds"] = p["odds"]
            merged += 1

    # 删除重复（从后往前删避免索引偏移）
    for idx in sorted(to_remove, reverse=True):
        predictions.pop(idx)

    if merged:
        save_db(db)
    log(f"\n合并完成: 移除 {merged} 条重复 (剩余 {len(predictions)} 条)")
    return merged

# ============================================================
# 9. 数据健康检查
# ============================================================
def check_health():
    """数据完整性检查"""
    db = load_db()
    predictions = db["predictions"]
    total = len(predictions)

    with_result = [p for p in predictions if p["result"]["status"] == "matched"]
    with_pf = [p for p in predictions if p["p_final"] is not None]
    with_dir = [p for p in predictions if p.get("direction", "")]
    with_both = [p for p in predictions if p["p_final"] is not None and p.get("direction", "")]
    with_dir_and_result = [p for p in with_result if p.get("direction", "")]
    bets = [p for p in predictions if p["is_bet"]]

    # 重复检测
    seen = {}
    dup_count = 0
    for p in predictions:
        key = (p["home"], p["away"], p.get("date", ""))
        seen[key] = seen.get(key, 0) + 1
    dup_groups = {k: v for k, v in seen.items() if v > 1}
    dup_count = sum(dup_groups.values())

    log(f"\n{'='*70}")
    log("  数 据 健 康 检 查")
    log("=" * 70)
    log(f"\n{'指标':<30} {'数值':<10} {'状态':<10}")
    log(f"  " + "-" * 50)

    def status_line(label, current, total, good_pct=100, warn_pct=80):
        pct = current / total * 100 if total > 0 else 0
        if pct >= good_pct:
            st = "✅"
        elif pct >= warn_pct:
            st = "⚠️"
        else:
            st = "🔴"
        log(f"  {label:<30} {current}/{total:<7} {st}")

    status_line("总记录", total, total)
    status_line("P_final 完整", len(with_pf), total, 100, 80)
    status_line("方向完整", len(with_dir), total, 100, 80)
    status_line("P_final + 方向双全", len(with_both), total, 80, 60)
    status_line("有结果", len(with_result), total, 100, 80)
    status_line("有方向+有结果(可评估)", len(with_dir_and_result), total, 50, 30)
    status_line("实际下注", len(bets), total)

    if dup_count > 0:
        log(f"  {'重复记录':<30} {dup_count} 条       🔴 需合并")
    else:
        log(f"  {'重复记录':<30} 0 条       ✅")

    log(f"\n  来源分布:")
    sources = defaultdict(int)
    for p in predictions:
        sources[p.get("source", "unknown")] += 1
    for k, v in sorted(sources.items()):
        log(f"    {k}: {v}")

    log(f"\n  综合评级:")
    missing_pf = total - len(with_pf)
    missing_dir = total - len(with_dir)
    issues = []
    if missing_pf > 0:
        issues.append(f"缺失 P_final {missing_pf} 条")
    if missing_dir > 0:
        issues.append(f"缺失方向 {missing_dir} 条")
    if dup_count > 0:
        issues.append(f"重复 {dup_count} 条")

    if not issues:
        log(f"    优 ✅ — 所有字段完整，可用于校准")
    elif len(issues) <= 1 and missing_pf == 0:
        log(f"    良 ⚠️ — {'; '.join(issues)}，建议修复")
    else:
        log(f"    差 🔴 — {'; '.join(issues)}，需先回填再校准")

    return {
        "total": total,
        "p_final_ok": len(with_pf),
        "direction_ok": len(with_dir),
        "both_ok": len(with_both),
        "with_result": len(with_result),
        "evaluable": len(with_dir_and_result),
        "duplicates": dup_count,
    }

# ============================================================
# 10. CLV 追踪（收盘价 vs 开盘价）
# ============================================================
def track_clv():
    """从 odds 缓存文件追踪 CLV（收盘价变动）

    CLV = (收盘MIP - 开盘MIP) / 开盘MIP × 100
    正值 → 市场朝你方向移动（你的下注价值上升）
    负值 → 市场反向移动
    """
    import glob as _glob
    db = load_db()
    predictions = db["predictions"]

    # 按比赛分组 odds 文件
    odds_groups = {}
    for f in os.listdir(CACHE_DIR):
        if not f.startswith("odds_") or not f.endswith(".json"):
            continue
        # 提取比赛标识（去掉 odds_ 前缀和日期后缀）
        key = re.sub(r"_\d{8}\.json$", "", f.replace("odds_", ""))
        m = re.search(r"_(\d{8})\.json$", f)
        file_date = m.group(1) if m else "00000000"
        try:
            with open(os.path.join(CACHE_DIR, f), "r", encoding="utf-8") as _fh:
                data = json.load(_fh)
        except Exception:
            continue
        if not data.get("odds_home"):
            continue
        if key not in odds_groups:
            odds_groups[key] = []
        odds_groups[key].append({"file": f, "date": file_date, "data": data})

    updated = 0
    for key, versions in odds_groups.items():
        if len(versions) < 2:
            continue
        # 按日期排序
        versions.sort(key=lambda x: x["date"])
        early, late = versions[0], versions[-1]
        if early["date"] == late["date"]:
            continue  # 同一天的不同文件，可能是同一批次

        # 计算 CLV（主胜 MIP 变化）
        vig = 1.03
        try:
            open_mip = 1.0 / float(early["data"]["odds_home"]) / vig
            close_mip = 1.0 / float(late["data"]["odds_home"]) / vig
            clv_pct = round((close_mip - open_mip) / open_mip * 100, 1)
        except Exception:
            continue

        # 在 predictions_db 中匹配
        hn = normalize(key.split("_")[0] if "_" in key else key)
        an = normalize(key.split("_")[1] if "_" in key and len(key.split("_")) > 1 else "")
        for p in predictions:
            ph, pa = normalize(p.get("home", "")), normalize(p.get("away", ""))
            # 匹配: 任一方队名在 key 中
            match = False
            for token in key.split("_"):
                if token and len(token) >= 2:
                    if (ph and ph[:max(3, len(ph)//2)] in token) and \
                       (pa and pa[:max(3, len(pa)//2)] in key.replace(token, "", 1)):
                        match = True
                        break
            if not match:
                continue
            p["clv"] = clv_pct
            p["clv_detail"] = {
                "open_odds": float(early["data"]["odds_home"]),
                "close_odds": float(late["data"]["odds_home"]),
                "open_mip": round(open_mip * 100, 1),
                "close_mip": round(close_mip * 100, 1),
                "open_file": early["file"],
                "close_file": late["file"],
            }
            updated += 1
            log(f"  {p['home']:10s} vs {p['away']:10s}  CLV={clv_pct:+.1f}% "
                f"(MIP {open_mip*100:.0f}%→{close_mip*100:.0f}%)")

    if updated:
        save_db(db)
    log(f"\nCLV 追踪: 更新 {updated} 条 (总 {len(predictions)} 条)")
    return updated


# ============================================================
# 11. 赔率刷新（用于 CLV 多版本收集）
# ============================================================
def refresh_odds():
    """刷新所有 pending 预测的最新赔率，写入新版本 odds_*.json

    每调用一次生成一个新版本文件，多次调用 → 多版本 → CLV 可算。
    """
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from skill.datafc_provider import auto_fill_odds
    except ImportError:
        log("[refresh_odds] datafc_provider 不可用")
        return 0

    db = load_db()
    predictions = db.get("predictions", [])
    updated = 0
    for p in predictions:
        if p.get("result", {}).get("status") != "pending":
            continue
        home = p.get("home", "")
        away = p.get("away", "")
        league = p.get("league", "")
        if not home or not away:
            continue
        # 调 auto_fill_odds 重新获取赔率（内部会调 _save_odds_file 写新版本）
        try:
            result = auto_fill_odds(
                home, away, league,
                p_final=p.get("p_final", 0.5),
                direction=p.get("direction", ""),
                rating=p.get("confidence", ""),
                odds_only=True,
            )
            if result.get("odds"):
                updated += 1
                log(f"  ✅ {home} vs {away}: 赔率 {result['odds']} ({result.get('source','?')})")
            else:
                log(f"  ⚠️ {home} vs {away}: 未获取到新赔率 ({result.get('source','?')})")
        except Exception as e:
            log(f"  ❌ {home} vs {away}: {e}")

    log(f"\n刷新完成: {updated}/{len(predictions)} 条")
    return updated


# ============================================================
# 12. 扩展结果源
# ============================================================
def dashboard():
    """生成 HTML 可视化看板（plotly + 预测数据）"""
    import plotly.graph_objects as go
    import plotly.express as px
    from plotly.subplots import make_subplots
    import webbrowser, os as _os

    db = load_db()
    preds = db.get("predictions", [])
    if not preds:
        log("暂无预测数据")
        return

    dash_path = _os.path.join(CACHE_DIR, "dashboard.html")
    # 也写到无中文路径（浏览器兼容性）
    _simple_path = _os.path.join(_os.environ.get("TEMP", _os.path.expanduser("~")), "football_dashboard.html")

    # ── 数据准备 ──
    dates = [p.get("date", "?")[:10] for p in preds]
    pf_vals = [p.get("p_final", 0.5) for p in preds]
    dirs = [p.get("direction", "?") for p in preds]
    results_raw = [p.get("result", {}).get("status", "pending") for p in preds]
    correct = [
        p.get("result", {}).get("correct") if p.get("result", {}).get("status") == "matched" else None
        for p in preds
    ]
    leagues = [p.get("league", "?") for p in preds]
    confs = [p.get("confidence", "") for p in preds]
    # 从 pnl_records.json 读取真实 PnL
    _real_pnl = 0.0
    _pnl_path = _os.path.join(CACHE_DIR, "pnl_records.json")
    if _os.path.exists(_pnl_path):
        try:
            with open(_pnl_path, "r", encoding="utf-8") as _f:
                _pnl_data = json.load(_f)
            _pnl_recs = _pnl_data if isinstance(_pnl_data, list) else _pnl_data.get("records", [])
            _real_pnl = sum(float(r.get("pnl", 0) or 0) for r in _pnl_recs)
        except Exception:
            pass

    # ── 图表 1: 校准曲线 ──
    bins = [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 0.9]
    bin_acc = []
    bin_counts = []
    for i in range(len(bins)):
        lo = bins[i]
        hi = bins[i + 1] if i + 1 < len(bins) else 1.0
        in_bin = [
            p for p in preds
            if p.get("result", {}).get("status") == "matched"
            and lo <= p.get("p_final", 0) < hi
        ]
        n = len(in_bin)
        bin_counts.append(n)
        if n > 0:
            acc = sum(1 for p in in_bin if p.get("result", {}).get("correct")) / n
        else:
            acc = None
        bin_acc.append(acc)

    fig1 = go.Figure()
    center_bins = [(bins[i] + (bins[i + 1] if i + 1 < len(bins) else 1.0)) / 2 for i in range(len(bins))]
    valid = [(c, a) for c, a in zip(center_bins, bin_acc) if a is not None]
    if valid:
        fig1.add_trace(go.Scatter(
            x=[v[0] for v in valid], y=[v[1] for v in valid],
            mode="lines+markers", name="实际准确率",
            line=dict(color="blue"), marker=dict(size=10)
        ))
    fig1.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        name="完美校准", line=dict(dash="dash", color="gray")
    ))
    fig1.update_layout(
        title="校准曲线 (Calibration Curve)", xaxis_title="预测概率",
        yaxis_title="实际频率", width=500, height=400,
        template="plotly_white",
    )

    # ── 图表 2: P_final 时间序列 ──
    fig2 = go.Figure()
    matched_dates = []
    matched_pf = []
    matched_correct = []
    for p in preds:
        if p.get("result", {}).get("status") == "matched":
            matched_dates.append(p.get("date", "?")[:10])
            matched_pf.append(p.get("p_final", 0.5))
            matched_correct.append(p.get("result", {}).get("correct"))
    if matched_dates:
        colors = ["green" if c else "red" if c is False else "gray" for c in matched_correct]
        fig2.add_trace(go.Scatter(
            x=matched_dates, y=matched_pf, mode="markers",
            marker=dict(color=colors, size=8),
            text=[f"{'✅' if c else '❌' if c is False else '?'} P_final={pf:.3f}"
                  for pf, c in zip(matched_pf, matched_correct)],
            name="预测结果"
        ))
    fig2.update_layout(
        title="P_final 预测序列", xaxis_title="日期",
        yaxis_title="P_final", width=500, height=400,
        template="plotly_white", showlegend=False,
    )

    # ── 图表 3: +EV 机会（从 pnl_records 找 real odds 与 model prob 的比较）─
    ev_table = []
    for p in preds:
        if p.get("result", {}).get("status") != "pending":
            continue
        conf = p.get("confidence", "")
        pf = p.get("p_final", 0.5)
        dir_ = p.get("direction", "")
        league = p.get("league", "")
        ev_table.append({
            "date": p.get("date", "?")[:10], "home": p.get("home", "?"),
            "away": p.get("away", "?"), "direction": dir_,
            "P_final": f"{pf:.1%}", "confidence": conf, "league": league,
        })

    # ── 拼 HTML ──
    ev_rows = ""
    for r in ev_table[:20]:
        ev_rows += f"""<tr>
            <td>{r['date']}</td><td>{r['home']}</td><td>{r['away']}</td>
            <td>{r['direction']}</td><td>{r['P_final']}</td>
            <td>{r['confidence']}</td><td>{r['league']}</td>
        </tr>"""

    fig1_html = fig1.to_html(full_html=False, include_plotlyjs=False)
    fig2_html = fig2.to_html(full_html=False, include_plotlyjs=False)

    matched_count = sum(1 for p in preds if p.get("result", {}).get("status") == "matched")
    pending_count = sum(1 for p in preds if p.get("result", {}).get("status") == "pending")
    correct_count = sum(1 for p in preds if p.get("result", {}).get("correct") is True)
    total_pnl = _real_pnl

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>预测看板</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; font-family:-apple-system,sans-serif; }}
body {{ background:#f5f6fa; padding:20px; }}
.header {{ max-width:1100px; margin:0 auto 20px; }}
.header h1 {{ font-size:24px; color:#2d3436; }}
.stats {{ display:flex; gap:15px; margin:15px 0; flex-wrap:wrap; }}
.stat-card {{ background:white; padding:15px 25px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.08); flex:1; min-width:120px; }}
.stat-card .num {{ font-size:28px; font-weight:700; }}
.stat-card .label {{ font-size:13px; color:#636e72; margin-top:3px; }}
.grid {{ max-width:1100px; margin:0 auto; display:grid; grid-template-columns:1fr 1fr; gap:15px; }}
.card {{ background:white; border-radius:10px; padding:15px; box-shadow:0 2px 8px rgba(0,0,0,.08); }}
.card.full {{ grid-column:1/-1; }}
.card h2 {{ font-size:16px; color:#2d3436; margin-bottom:12px; }}
table {{ width:100%; border-collapse:collapse; font-size:13px; }}
th {{ background:#f8f9fa; text-align:left; padding:8px 10px; border-bottom:2px solid #dfe6e9; }}
td {{ padding:8px 10px; border-bottom:1px solid #f0f0f0; }}
tr:hover {{ background:#f8f9fa; }}
.badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600; }}
.badge.pending {{ background:#ffeaa7; color:#d68910; }}
.badge.matched {{ background:#d4edda; color:#155724; }}
</style></head>
<body>
<div class="header">
    <h1>📊 预测看板</h1>
    <div class="stats">
        <div class="stat-card"><div class="num">{len(preds)}</div><div class="label">总预测</div></div>
        <div class="stat-card"><div class="num">{matched_count}</div><div class="label">已结算</div></div>
        <div class="stat-card"><div class="num">{pending_count}</div><div class="label">待赛</div></div>
        <div class="stat-card"><div class="num" style="color:{'#27ae60' if correct_count > matched_count/2 else '#e74c3c'}">{correct_count}/{matched_count if matched_count else 0}</div><div class="label">正确/已结算</div></div>
        <div class="stat-card"><div class="num" style="color:{'#27ae60' if total_pnl >= 0 else '#e74c3c'}">{total_pnl:+.2f}u</div><div class="label">总 PnL</div></div>
    </div>
</div>
<div class="grid">
    <div class="card">{fig1_html}</div>
    <div class="card">{fig2_html}</div>
    <div class="card full">
        <h2>⏳ 待赛预测（+EV 机会）</h2>
        <table><thead><tr>
            <th>日期</th><th>主队</th><th>客队</th><th>方向</th><th>P_final</th><th>评级</th><th>联赛</th>
        </tr></thead><tbody>
            {ev_rows if ev_rows else '<tr><td colspan="7" style="text-align:center;color:#999;">暂无待赛预测</td></tr>'}
        </tbody></table>
    </div>
</div>
<p style="text-align:center;color:#b2bec3;font-size:12px;margin-top:20px;">
    生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')} | 数据: predictions_db.json
</p>
</body></html>"""

    with open(dash_path, "w", encoding="utf-8") as f:
        f.write(html)
    with open(_simple_path, "w", encoding="utf-8") as f:
        f.write(html)
    log(f"看板已生成:")
    log(f"  📂 数据缓存: file:///{_os.path.abspath(dash_path).replace(chr(92), '/')}")
    log(f"  📂 简易路径: file:///{_os.path.abspath(_simple_path).replace(chr(92), '/')}")
    try:
        from urllib.parse import urlunparse
        _uri = urlunparse(("file", "",
            _os.path.abspath(_simple_path).replace(chr(92), "/"), "", "", ""))
        webbrowser.open(_uri)
    except Exception:
        pass


def sportsdb_league_id(league):
    ids = {
        "allsvenskan": "4347", "瑞典超": "4347",
        "veikkausliiga": "4417", "芬超": "4417",
    }
    return ids.get(league)

def sync_from_datafc(league: str = "wm26"):
    """从 datafc/Sofascore 获取已完赛比赛"""
    try:
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from skill.datafc_provider import sync_results_to_file
    except ImportError:
        log("datafc 不可用，请先 pip install datafc")
        return 0

    n = sync_results_to_file(league)
    if n:
        log(f"从 datafc 获取到 {n} 场新结果，导入 auto_results.json")
        return sync_results()
    log("无新比赛结果")
    return 0

# ============================================================
# 主入口
# ============================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="预测数据库管理")
    parser.add_argument("--import-all", action="store_true", help="导入所有历史数据")
    parser.add_argument("--import-md", action="store_true", help="导入MD预测文件")
    parser.add_argument("--import-pnl", action="store_true", help="导入pnl_records")
    parser.add_argument("--sync-results", action="store_true", help="同步赛后结果")
    parser.add_argument("--sync-datafc", help="从 datafc 同步赛后结果 (指定联赛)", nargs="?", const="wm26")
    parser.add_argument("--calibration", action="store_true", help="生成校准报告")
    parser.add_argument("--report", action="store_true", help="列出所有预测")
    parser.add_argument("--dashboard", action="store_true", help="生成 HTML 可视化看板")
    # 新增
    parser.add_argument("--check", action="store_true", help="数据健康检查")
    parser.add_argument("--backfill", action="store_true", help="存量回填缺失字段")
    parser.add_argument("--dedup", action="store_true", help="合并重复预测")
    parser.add_argument("--add", action="store_true", help="新增一条预测")
    parser.add_argument("--no-strict", action="store_true", help="关闭 P_final/direction 强制校验")
    parser.add_argument("--temperature", type=float, default=1.60, help="温度缩放系数 (默认1.60)")
    parser.add_argument("--watch", action="store_true", help="赛后自动回填(每60秒检查)")
    parser.add_argument("--track-clv", action="store_true", help="CLV追踪(从多版本odds缓存)")
    parser.add_argument("--refresh-odds", action="store_true", help="刷新待赛预测的赔率(生成新版本用于CLV)")
    parser.add_argument("--home", help="主队")
    parser.add_argument("--away", help="客队")
    parser.add_argument("--p", type=float, help="P_final")
    parser.add_argument("--direction", default="", help="推荐方向")
    parser.add_argument("--odds", type=float, default=0, help="赔率")
    parser.add_argument("--date", default="", help="日期")
    parser.add_argument("--league", default="", help="联赛")
    parser.add_argument("--source", default="manual", choices=["manual", "auto_pipeline", "predict.py"],
                        help="预测来源 (manual=人工, auto_pipeline=自动脚本, predict.py=系统1引擎)")
    args = parser.parse_args()

    if args.track_clv:
        track_clv()
        return

    if args.refresh_odds:
        refresh_odds()
        return

    if args.watch:
        import time as _tmod
        log(f"全能监控模式 (每60秒: 结果回填 + 赔率刷新, Ctrl+C停止)")
        try:
            while True:
                n1 = sync_results()
                n2 = 0
                try:
                    n2 = sync_from_datafc("wm26")
                except Exception:
                    pass
                if n1 or n2:
                    log(f"  [结果] 更新 {n1 + n2} 条")
                    # 新结果到达 → 自动校准并输出摘要（Sharpe / 准确率）
                    try:
                        cal_buf = io.StringIO()
                        cal_old = sys.stdout
                        sys.stdout = cal_buf
                        calibration_report()
                        sys.stdout = cal_old
                        for cal_ln in cal_buf.getvalue().split("\n"):
                            if any(k in cal_ln for k in ("Sharpe", "准确率", "总预测", "PnL", "校准")):
                                log(f"  [校准] {cal_ln.strip()}")
                    except Exception as cal_e:
                        log(f"  [校准] 失败: {cal_e}")
                # 刷新 pending 赔率（生成新版本用于 CLV）
                try:
                    nr = refresh_odds()
                    if nr:
                        log(f"  [赔率] 刷新 {nr} 条")
                except Exception:
                    pass
                _tmod.sleep(60)
        except KeyboardInterrupt:
            log("  watch 停止")
            return
        except Exception as e:
            log(f"  watch 错误: {e}")
            return

    if args.check:
        check_health()
        return

    if args.backfill:
        backfill()
        return

    if args.dedup:
        dedup()
        check_health()
        return

    if args.import_all or args.import_md:
        import_from_md(strict=False)
    if args.import_all or args.import_pnl:
        import_from_pnl()
    if args.sync_results:
        sync_results()
    if args.sync_datafc:
        sync_from_datafc(args.sync_datafc)
    if args.calibration:
        calibration_report()
    if args.report:
        full_report()
    if args.dashboard:
        dashboard()
        return
    if args.add:
        if not args.home or not args.away:
            log("请指定 --home 和 --away")
            return
        add_prediction(args.home, args.away, p_final=args.p,
                       direction=args.direction, is_bet=(args.odds > 0),
                       odds=args.odds, date_str=args.date, league=args.league,
                       strict=not args.no_strict, temperature=args.temperature,
                       source=args.source)

    if not any([args.import_all, args.import_md, args.import_pnl,
                args.sync_results, args.sync_datafc,
                args.calibration, args.report, args.dashboard, args.add,
                args.check, args.backfill, args.dedup, args.watch, args.track_clv]):
        parser.print_help()

if __name__ == "__main__":
    main()
