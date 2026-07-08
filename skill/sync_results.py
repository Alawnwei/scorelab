#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
赛后结果自动回填工具 v1.1 — 加固版
用途：从 auto_results.json 和 TheSportsDB 拉取比赛结果，
      自动匹配并更新 pnl_records.json 中的 pending 记录
修复: Unicode 编码崩溃、网络异常崩溃、方向匹配逻辑
"""
import sys, os, json, urllib.request, ssl
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "数据缓存")
PNL_FILE = os.path.join(CACHE_DIR, "pnl_records.json")
AUTO_RESULTS_FILE = os.path.join(CACHE_DIR, "auto_results.json")


def safe_print(text):
    """安全打印 — 避免 GBK 编码崩溃"""
    try:
        print(text)
    except UnicodeEncodeError:
        try:
            print(text.encode("utf-8", errors="replace").decode("gbk", errors="replace"))
        except:
            print(str(text).encode("ascii", errors="replace").decode("ascii"))


# ============================================================
# 加载数据
# ============================================================

def load_json(path, default=None):
    """安全加载 JSON — 文件不存在或解析失败则返回 default"""
    if not os.path.exists(path):
        return default if default is not None else []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        safe_print(f"  [WARN] 无法加载 {path}: {e}")
        return default if default is not None else []


def load_pnl():
    return load_json(PNL_FILE, {}).get("records", [])


def save_pnl(records):
    data = {"records": records, "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M")}
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(PNL_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError as e:
        safe_print(f"  [ERROR] 保存失败: {e}")


def load_auto_results():
    return load_json(AUTO_RESULTS_FILE, [])


# ============================================================
# 结果匹配逻辑
# ============================================================

def normalize(s):
    return s.strip().lower().replace(" ", "").replace("-", "").replace("_", "").replace("(", "").replace(")", "")


def match_result(pnl_record, auto_result):
    p_home = normalize(pnl_record.get("home", ""))
    p_away = normalize(pnl_record.get("away", ""))
    a_home = normalize(auto_result.get("home_cn", ""))
    a_away = normalize(auto_result.get("away_cn", ""))
    return (p_home == a_home and p_away == a_away) or \
           (p_home == a_away and p_away == a_home)


def parse_score(score_str):
    if not score_str or "-" not in score_str:
        return None, None
    try:
        parts = score_str.replace(" ", "").split("-")
        scores = [int(p) for p in parts[:2]]
        return scores[0], scores[1]
    except (ValueError, IndexError):
        return None, None


def determine_result(pnl, home_goals, away_goals):
    """根据实际比分判断预测是否正确 — v1.1 修复双向预测"""
    direction = pnl.get("direction", "")
    if not direction or home_goals is None:
        return None, None

    # 判断实际结果
    if home_goals > away_goals:
        actual = "主胜"
    elif home_goals < away_goals:
        actual = "客胜"
    else:
        actual = "平局"

    dir_clean = direction.replace("系统2-", "").replace("1X2-", "")
    dir_lower = dir_clean.lower()

    # 处理"不败"类双向预测
    if "不败" in dir_clean:
        if actual == "平局" or (actual == "主胜" and "主" in dir_clean) or (actual == "客胜" and "客" in dir_clean):
            return "win", actual
        return "loss", actual

    # 大小球
    if "大" in dir_clean and "小" not in dir_clean:
        total = home_goals + away_goals
        return "win" if total >= 2.5 else "loss", actual
    if "小" in dir_clean and "大" not in dir_clean:
        total = home_goals + away_goals
        return "loss" if total >= 2.5 else "win", actual

    # 胜平负 —— 用更精确匹配避免"主队不败"误判为"主胜"
    if dir_clean == "主胜" or dir_clean == "主" or "主胜" in dir_clean:
        return ("win" if actual == "主胜" else "loss"), actual
    if dir_clean == "客胜" or dir_clean == "客" or "客胜" in dir_clean:
        return ("win" if actual == "客胜" else "loss"), actual
    if "平" in dir_clean and "不败" not in dir_clean:
        return ("win" if actual == "平局" else "loss"), actual

    # 串关/混合方向 — 不自动判定，保留 pending
    return None, actual


# ============================================================
# TheSportsDB 查询
# ============================================================

SPORTSDB_BASE = "https://www.thesportsdb.com/api/v1/json/3"

TEAM_SPORTSDB = {
    "拉赫蒂": "Lahti", "赫尔火花": "Gnistan", "赫尔辛基火花": "Gnistan",
    "哈尔姆斯塔德": "Halmstad", "韦斯特罗斯": "Vasteras",
    "代格福什": "Degerfors", "马尔默": "Malmo FF",
    "塞伊奈": "SJK", "TPS图尔库": "TPS", "TPS图尔": "TPS",
    "雅罗": "FF Jaro", "坦佩雷": "Tampere United", "坦山猫": "Tampere United",
    "赫尔辛基": "HJK", "瓦萨": "VPS", "玛丽港": "IFK Mariehamn",
    "国际图尔库": "FC Inter", "库奥皮奥": "KuPS", "AC奥卢": "AC Oulu",
    "索尔纳": "AIK", "哥德堡": "IFK Gothenburg", "埃尔维斯": "Ilves",
    "埃尔夫斯堡": "Elfsborg", "哈马比": "Hammarby", "赫根": "Hacken",
    "北雪平": "Norrkoping", "卡尔马": "Kalmar",
    "天狼星": "Sirius", "米亚尔比": "Mjallby",
    "布洛马波卡纳": "Brommapojkarna",
}


def _sportsdb_request(url):
    """安全请求 TheSportsDB API"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        safe_print(f"  [WARN] SportsDB 请求失败: {e}")
        return None


def sportsdb_search_team(team_name):
    team_en = TEAM_SPORTSDB.get(team_name, team_name)
    data = _sportsdb_request(f"{SPORTSDB_BASE}/searchteams.php?t={team_en}")
    if data and data.get("teams"):
        return data["teams"][0]
    return None


def sportsdb_get_recent_result(team_name):
    team = sportsdb_search_team(team_name)
    if not team:
        return None
    team_id = team.get("idTeam")
    if not team_id:
        return None

    data = _sportsdb_request(f"{SPORTSDB_BASE}/eventslast.php?id={team_id}")
    if not data:
        return None

    events = data.get("results", [])
    for e in events:
        score = (e.get("strScore") or "").strip()
        if "-" in score:
            try:
                parts = score.replace(" ", "").split("-")
                return {
                    "home": e.get("strHomeTeam", ""),
                    "away": e.get("strAwayTeam", ""),
                    "home_goals": int(parts[0]),
                    "away_goals": int(parts[1]),
                    "date": e.get("dateEvent", ""),
                }
            except (ValueError, IndexError):
                pass
    return None


# ============================================================
# ESPN API 回退（新 — 自动补全世界杯结果）
# ============================================================

def espn_get_scores(date_str):
    """从 ESPN API 获取某天的世界杯赛果"""
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date_str.replace('-', '')}"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        safe_print(f"  [WARN] ESPN 请求失败: {e}")
        return []

    results = []
    for e in data.get("events", []):
        comp = e.get("competitions", [{}])[0] if e.get("competitions") else {}
        competitors = comp.get("competitors", [])
        scores = {}
        for c in competitors:
            team = c.get("team", {}).get("displayName", "")
            score = c.get("score", "0")
            scores[team] = int(score) if score and score.isdigit() else 0
        if len(scores) >= 2:
            teams = list(scores.keys())
            results.append({
                "home_cn": teams[1],  # ESPN 有时顺序是 客@主
                "away_cn": teams[0],
                "score_ft": f"{scores[teams[1]]}-{scores[teams[0]]}",
                "status": "FINISHED",
                "date": date_str,
            })
    return results


# ============================================================
# 主流程
# ============================================================

def main():
    safe_print("=" * 60)
    safe_print("  赛后结果自动回填 v1.1")
    safe_print("=" * 60)

    try:
        records = load_pnl()
        pending = [r for r in records if r.get("result") == "pending"]
        auto_results = load_auto_results()

        safe_print(f"\n  pnl_records: {len(records)} 条总记录")
        safe_print(f"  待结算: {len(pending)} 条")
        safe_print(f"  auto_results.json: {len(auto_results)} 场")

        if not pending:
            safe_print("\n  没有待结算的记录，无需回填。")
            return

        updated = 0
        matched_from_auto = 0
        matched_from_sportsdb = 0
        matched_from_espn = 0

        for pnl in pending:
            p_home = pnl.get("home", "")
            p_away = pnl.get("away", "")
            record_id = pnl.get("id", "")
            p_date = pnl.get("date", "")

            # 1. 先尝试从 auto_results.json 匹配
            found = None
            for ar in auto_results:
                if match_result(pnl, ar):
                    found = ar
                    matched_from_auto += 1
                    break

            # 2. auto_results 没匹配到，尝试 TheSportsDB
            if not found:
                try:
                    result = sportsdb_get_recent_result(p_home)
                    if result and result.get("home_goals") is not None:
                        home_ok = normalize(p_home) in normalize(result["home"]) or \
                                  normalize(p_home) in normalize(result["away"])
                        away_ok = normalize(p_away) in normalize(result["home"]) or \
                                  normalize(p_away) in normalize(result["away"])
                        if home_ok and away_ok:
                            found = result
                            matched_from_sportsdb += 1
                except Exception:
                    pass

            # 3. 还没匹配到，尝试 ESPN（适用于世界杯）
            if not found and p_date:
                try:
                    espn_results = espn_get_scores(p_date)
                    for ar in espn_results:
                        if match_result(pnl, ar):
                            found = ar
                            matched_from_espn += 1
                            # 也追加到 auto_results 以便下次直接匹配
                            auto_results.append(ar)
                            break
                except Exception:
                    pass

            # 更新 pnl 记录
            if found:
                if "home_cn" in found:
                    home_goals, away_goals = parse_score(found.get("score_ft", ""))
                else:
                    home_goals = found.get("home_goals")
                    away_goals = found.get("away_goals")

                result_type, actual = determine_result(pnl, home_goals, away_goals)
                if result_type:
                    odds = pnl.get("odds", 0)
                    if odds > 0:
                        if result_type == "win":
                            pnl["pnl"] = round(pnl.get("stake", 1) * (odds - 1), 2)
                        else:
                            pnl["pnl"] = round(-pnl.get("stake", 1), 2)
                    else:
                        pnl["pnl"] = 0

                    pnl["result"] = result_type
                    note = f"自动回填: 实际{actual} {home_goals}-{away_goals}"
                    existing = pnl.get("notes", "")
                    pnl["notes"] = (existing + " | " + note).strip(" |")
                    updated += 1
                    safe_print(f"  [OK] {pnl['home']} vs {pnl['away']} -> {result_type} ({actual} {home_goals}-{away_goals})")
                else:
                    safe_print(f"  [SKIP] {pnl['home']} vs {pnl['away']} -> 无法判定方向，保留 pending")
            else:
                safe_print(f"  [WAIT] {pnl['home']} vs {pnl['away']} -> 未找到赛后结果，保留 pending")

        # 保存更新
        if updated > 0:
            save_pnl(records)
            # 同时保存 ESPN 补充到 auto_results
            try:
                with open(AUTO_RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(auto_results, f, ensure_ascii=False, indent=2)
            except Exception:
                pass
            safe_print(f"\n  [OK] 已更新 {updated} 条记录")
        else:
            safe_print(f"\n  无记录需要更新。")

        safe_print(f"\n  匹配来源: auto={matched_from_auto} sportsdb={matched_from_sportsdb} espn={matched_from_espn} | 未匹配 {len(pending) - updated}")

    except Exception as e:
        safe_print(f"\n  [ERROR] 脚本运行异常: {e}")
        import traceback
        safe_print(traceback.format_exc())


if __name__ == "__main__":
    main()
