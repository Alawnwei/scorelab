#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
历史数据迁移 — 将现有的 pnl_records.json / predictions_db.json / MD文件
合并迁移到 unified_predictions.json

用法:
  python skill/migrate_to_unified_db.py

说明:
  - 尽量从每个源提取可用字段
  - 同一场比赛以 pnl_records 为准（数据最全）
  - MD文件仅补充 P_final（pnl_records 缺失时）
  - 此脚本可反复运行，不会重复添加
"""
import sys, os, json, glob, re
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
PRED_DIR = os.path.join(BASE_DIR, "预测数据")
DB_PATH = os.path.join(CACHE_DIR, "unified_predictions.json")


def log_msg(text):
    """安全打印（Windows GBK兼容）"""
    try:
        safe = str(text).encode('utf-8', errors='replace').decode('gbk', errors='replace')
        print(safe)
    except:
        print(str(text))


def norm(s):
    return s.strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def load_db():
    """加载现有统一数据库"""
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {"schema_version": 2, "predictions": []}


def save_db(db):
    """保存统一数据库"""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)


def build_key(match_home, match_away, date_str):
    """构建去重key"""
    return "%s|%s|%s" % (norm(match_home), norm(match_away), (date_str or "")[:10])


def extract_pfinal_from_md(content):
    """从MD文件内容提取 P_final"""
    patterns = [
        r'\|\s*P_final\s*\|\s*\*\*([\d.]+)\*\*',
        r'[Pp]_final\s*[=:≈]\s*([\d.]+)',
        r'\*\*P_final\*\*\s*\|\s*([\d.]+)',
        r'\|\s*P_final\s*\|\s*([\d.]+)',
    ]
    for pat in patterns:
        m = re.search(pat, content)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
    return None


def extract_direction_from_md(content):
    """从MD文件提取推荐方向"""
    patterns = [
        r'推荐方向[：:]\s*(\S+)',
        r'\*\*推荐方向\*\*[：:]?\s*\*\*(\S+)\*\*',
        r'方向[：:]\s*(\S+)',
    ]
    for pat in patterns:
        m = re.search(pat, content)
        if m:
            result = m.group(1).strip()
            if len(result) <= 10:
                return result
    return ""


def migrate_from_pnl(db):
    """从 pnl_records.json 迁移"""
    pnl_path = os.path.join(CACHE_DIR, "pnl_records.json")
    if not os.path.exists(pnl_path):
        log_msg("  [pnl] 文件不存在，跳过")
        return 0

    with open(pnl_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    records = data.get("records", [])
    added = 0
    skip = 0

    existing_keys = set()
    for p in db.get("predictions", []):
        pm = p.get("match", {})
        existing_keys.add(build_key(pm.get("home", ""), pm.get("away", ""),
                                    str(p.get("predicted_at", ""))[:10]))

    for r in records:
        home = r.get("home", "")
        away = r.get("away", "")
        date_str = r.get("date", "") or (r.get("timestamp", "") or "")[:10]

        key = build_key(home, away, date_str)
        if key in existing_keys:
            skip += 1
            continue

        # 判断赛果
        result_status = "pending"
        result_val = r.get("result", "pending")
        if result_val == "win":
            result_status = "finished"
        elif result_val == "loss":
            result_status = "finished"

        record = {
            "id": "mig_pnl_%s" % key[:20],
            "predicted_at": r.get("date", "") or r.get("timestamp", ""),
            "match": {"home": home, "away": away},
            "league": r.get("league", "unknown"),

            "model": {
                "version": "legacy",
                "p_home": None,
                "p_draw": None,
                "p_away": None,
                "lambda_A": None,
                "lambda_B": None,
                "distribution_most_likely": None,
                "star_rating": r.get("confidence", ""),
                "factors": {},
            },

            "odds": {
                "home": r.get("odds_home", r.get("odds", 0)),
                "draw": None,
                "away": None,
                "ah_hdp": None,
                "ah_home": None,
                "ah_away": None,
                "ou_line": None,
                "ou_over": None,
                "ou_under": None,
                "btts_yes": None,
                "btts_no": None,
                "source": "legacy_pnl",
            },

            "ev": {
                "best_direction": r.get("direction", ""),
                "value_pct": r.get("ev", 0),
                "recommendation": "",
            },

            "quality": {"score": None, "warnings": []},

            "baselines": {"elo": None, "market": None, "consistency": None},

            "result": {
                "status": result_status,
                "home_score": None,
                "away_score": None,
                "correct": result_val == "win",
                "pnl": None,
                "updated_at": None,
            },

            "meta": {
                "source": "migrate_pnl",
                "md_report": "",
            },
        }

        # P_final 处理：某些记录直接存了P_final字段
        p_final = r.get("P_final")
        if p_final is not None and p_final > 0:
            record["model"]["p_home"] = p_final
            if p_final >= 0.55:
                record["model"]["p_draw"] = None
                record["model"]["p_away"] = 1.0 - p_final
            elif p_final <= 0.45:
                record["model"]["p_away"] = p_final
                record["model"]["p_home"] = 1.0 - p_final

        db.setdefault("predictions", []).append(record)
        existing_keys.add(key)
        added += 1

    log_msg("  [pnl] 迁移 %d 条, 跳过 %d 条重复" % (added, skip))
    return added


def migrate_from_predictions_db(db):
    """从 predictions_db.json 迁移（补充 pnl 未覆盖的）"""
    pdb_path = os.path.join(CACHE_DIR, "predictions_db.json")
    if not os.path.exists(pdb_path):
        log_msg("  [pdb] 文件不存在，跳过")
        return 0

    with open(pdb_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    preds = data.get("predictions", [])
    added = 0
    skip = 0

    existing_keys = set()
    for p in db.get("predictions", []):
        pm = p.get("match", {})
        existing_keys.add(build_key(pm.get("home", ""), pm.get("away", ""),
                                    str(p.get("predicted_at", ""))[:10]))

    for r in preds:
        home = r.get("home", "")
        away = r.get("away", "")
        date_str = r.get("date", "")[:10]

        key = build_key(home, away, date_str)
        if key in existing_keys:
            skip += 1
            continue

        res = r.get("result", {})
        result_status = "finished" if res.get("status") == "matched" else "pending"
        correct = res.get("correct")

        p_final = r.get("p_final")
        direction = r.get("direction", "")

        record = {
            "id": "mig_pdb_%s" % key[:20],
            "predicted_at": date_str,
            "match": {"home": home, "away": away},
            "league": r.get("league", "unknown"),

            "model": {
                "version": "legacy",
                "p_home": p_final if p_final else None,
                "p_draw": None,
                "p_away": (1.0 - p_final) if p_final and p_final >= 0.55 else None,
                "lambda_A": None,
                "lambda_B": None,
                "distribution_most_likely": None,
                "star_rating": r.get("confidence", ""),
                "factors": {},
            },

            "odds": {"home": None, "draw": None, "away": None, "source": "legacy_pdb"},
            "ev": {"best_direction": direction, "value_pct": None, "recommendation": ""},

            "quality": {"score": None, "warnings": []},
            "baselines": {"elo": None, "market": None, "consistency": None},

            "result": {
                "status": result_status,
                "home_score": res.get("score_home"),
                "away_score": res.get("score_away"),
                "correct": correct,
                "pnl": None,
                "updated_at": None,
            },

            "meta": {"source": "migrate_pdb", "md_report": ""},
        }

        l1 = r.get("l1_scores", {})
        if l1:
            record["quality"]["l1_scores"] = l1

        db.setdefault("predictions", []).append(record)
        existing_keys.add(key)
        added += 1

    log_msg("  [pdb] 迁移 %d 条, 跳过 %d 条重复" % (added, skip))
    return added


def migrate_from_md(db, max_files=200):
    """从MD文件迁移（仅补充 P_final/方向 — pnl/pdb都缺失时）"""
    md_files = sorted(glob.glob(os.path.join(PRED_DIR, "足球预测-*.md")))
    log_msg("  [MD] 共 %d 个文件, 最多处理 %d 个" % (len(md_files), max_files))

    added = 0
    skip = 0

    existing_keys = set()
    for p in db.get("predictions", []):
        pm = p.get("match", {})
        existing_keys.add(build_key(pm.get("home", ""), pm.get("away", ""),
                                    str(p.get("predicted_at", ""))[:10]))

    for fpath in md_files[:max_files]:
        fname = os.path.basename(fpath)
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()

        # 从文件名解析队名
        stem = fname.replace(".md", "")
        tm = re.search(r"(\d{4}-\d{2}-\d{2})[-]*(.+?)(vs)(.+?)$", stem)
        if not tm:
            continue
        date_str = tm.group(1)
        home = tm.group(2).strip("-").strip()
        away = tm.group(4).strip()
        if "-" in home:
            home = home.split("-")[-1]

        key = build_key(home, away, date_str)
        if key in existing_keys:
            skip += 1
            continue

        p_final = extract_pfinal_from_md(content)
        if p_final is None:
            skip += 1
            continue

        direction = extract_direction_from_md(content)

        record = {
            "id": "mig_md_%s" % key[:20],
            "predicted_at": date_str,
            "match": {"home": home, "away": away},
            "league": "unknown",

            "model": {
                "version": "legacy",
                "p_home": p_final,
                "p_draw": None,
                "p_away": (1.0 - p_final) if p_final < 0.50 else None,
                "lambda_A": None,
                "lambda_B": None,
                "distribution_most_likely": None,
                "star_rating": "",
                "factors": {},
            },

            "odds": {"source": "legacy_md"},
            "ev": {"best_direction": direction, "value_pct": None, "recommendation": ""},
            "quality": {"score": None, "warnings": []},
            "baselines": {"elo": None, "market": None, "consistency": None},

            "result": {
                "status": "pending",
                "home_score": None, "away_score": None,
                "correct": None, "pnl": None, "updated_at": None,
            },

            "meta": {"source": "migrate_md", "md_report": fname},
        }

        db.setdefault("predictions", []).append(record)
        existing_keys.add(key)
        added += 1

    log_msg("  [MD] 迁移 %d 条, 跳过 %d 条（含无P_final）" % (added, skip))
    return added


# ============================================================
def main():
    log_msg("=" * 55)
    log_msg("  历史数据迁移 → unified_predictions.json")
    log_msg("=" * 55)

    db = load_db()
    before = len(db.get("predictions", []))
    log_msg("\n迁移前总记录: %d\n" % before)

    log_msg("[1/3] 从 pnl_records.json 迁移...")
    n1 = migrate_from_pnl(db)

    log_msg("\n[2/3] 从 predictions_db.json 迁移...")
    n2 = migrate_from_predictions_db(db)

    log_msg("\n[3/3] 从 MD预测文件 迁移...")
    n3 = migrate_from_md(db)

    # 按预测时间排序
    db["predictions"].sort(key=lambda x: str(x.get("predicted_at", "")))

    save_db(db)
    after = len(db["predictions"])

    log_msg("\n" + "=" * 55)
    log_msg("  迁移完成")
    log_msg("  迁移前: %d 条" % before)
    log_msg("  新增: %d 条 (pnl=%d + pdb=%d + md=%d)" % (after - before, n1, n2, n3))
    log_msg("  迁移后: %d 条" % after)
    log_msg("  文件: %s" % DB_PATH)
    log_msg("=" * 55)

    # 统计
    has_pf = sum(1 for p in db["predictions"] if p.get("model", {}).get("p_home"))
    has_result = sum(1 for p in db["predictions"] if p.get("result", {}).get("status") != "pending")
    finished = sum(1 for p in db["predictions"] if p.get("result", {}).get("correct") is not None)
    log_msg("\n可用校准样本: %d (有P_final=%d, 已完赛=%d, 有方向验证=%d)" %
      (after, has_pf, has_result, finished))


if __name__ == "__main__":
    main()
