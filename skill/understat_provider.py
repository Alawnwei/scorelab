#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Understat xG 数据提供器 — 作为 datafc 的 big league xG 回退

当 datafc 无法获取 xG 数据（shots_data 为空或 xG=None）时，
对五大联赛尝试从 Understat 补 xG 数据。

数据源: understat.com (通过 understatapi 库)
覆盖联赛: EPL, La_Liga, Bundesliga, Serie_A, Ligue_1
"""

import sys, os, json, math, time
from typing import Optional, Dict, List
from datetime import datetime

# 我们的联赛代码 → Understat 联赛名
UNDERSTAT_LEAGUE_MAP = {
    "epl":    "EPL",
    "laliga": "La_Liga",
    "bl1":    "Bundesliga",
    "seriea": "Serie_A",
    "ligue1": "Ligue_1",
}

# Understat 赛季参数：2025 = 2025/2026 赛季（最新完整赛季）
UNDERSTAT_SEASON = "2025"

# 球队名缓存 {league_code: {team_name_en: xg_data}}
_UNDERSTAT_CACHE: dict = {}
_UNDERSTAT_CACHE_TIME = 0
_UNDERSTAT_CACHE_TTL = 3600  # 1小时缓存

# 内存缓存：当前进程内的 team → Understat 队名
_TEAM_NAME_CACHE: dict = {}

# 控制台输出
def _log(msg):
    try:
        print(f"[understat] {msg}", flush=True)
    except:
        pass


def _get_understat_data(league_code: str) -> Optional[dict]:
    """从 Understat 获取某联赛的全部球队 xG 数据（带缓存）

    Args:
        league_code: 我们的联赛代码 (epl/laliga/bl1/seriea/ligue1)

    Returns:
        {team_name_en: {xG, xGA, matches}}, or None on failure
    """
    global _UNDERSTAT_CACHE, _UNDERSTAT_CACHE_TIME
    now = time.time()

    # 缓存命中 & 未过期
    if league_code in _UNDERSTAT_CACHE and (now - _UNDERSTAT_CACHE_TIME) < _UNDERSTAT_CACHE_TTL:
        return _UNDERSTAT_CACHE[league_code]

    us_league = UNDERSTAT_LEAGUE_MAP.get(league_code)
    if not us_league:
        return None

    try:
        from understatapi import UnderstatClient
        uc = UnderstatClient()
        league = uc.league(league=us_league)
        teams = league.get_team_data(season=UNDERSTAT_SEASON)
    except Exception as e:
        _log(f"获取 {us_league} 数据失败: {e}")
        return None

    if not teams:
        _log(f"{us_league} 无数据")
        return None

    # 处理为 {team_name_en: {xG_for_total, xGA_total, count, xG_list, xGA_list, results}}
    result = {}
    for tid, tdata in teams.items():
        name = tdata.get("title", "")
        history = tdata.get("history", [])
        if not name or not history:
            continue

        total_xg = 0.0
        total_xga = 0.0
        n = 0
        match_results = []

        for h in history:
            try:
                xg = float(h.get("xG", 0))
                xga = float(h.get("xGA", 0))
                scored = int(h.get("scored", 0))
                missed = int(h.get("missed", 0))
                is_home = (h.get("h_a") == "h")
                date_str = h.get("date", "")
            except (ValueError, TypeError):
                continue

            total_xg += xg
            total_xga += xga
            n += 1
            match_results.append({
                "is_home": is_home,
                "xG": xg,
                "xGA": xga,
                "scored": scored,
                "missed": missed,
                "date": date_str,
            })

        # 保存：用原始名（小写无空格）做键，同时保存显示名
        key = name.lower().replace(" ", "").replace("-", "")
        result[key] = {
            "display_name": name,
            "xG_for_90": round(total_xg / n, 2) if n > 0 else 0,
            "xG_against_90": round(total_xga / n, 2) if n > 0 else 0,
            "matches_played": n,
            "total_xG": round(total_xg, 2),
            "total_xGA": round(total_xga, 2),
            "history": match_results[-10:],  # 只保留最近10场
        }

    # 写入缓存
    _UNDERSTAT_CACHE[league_code] = result
    _UNDERSTAT_CACHE_TIME = now
    _log(f"{us_league}: 缓存 {len(result)} 队 xG 数据")
    return result


def _find_team(team_name_en: str, league_data: dict) -> Optional[dict]:
    """在 Understat 数据中模糊查找球队（归一化匹配）

    策略:
      1. 精确归一化匹配
      2. 包含关系匹配
      3. 截断前 4 字符匹配
    """
    if not team_name_en or not league_data:
        return None

    norm = team_name_en.lower().replace(" ", "").replace("-", "").replace("'", "")

    # 精确匹配
    if norm in league_data:
        return league_data[norm]

    # 包含匹配
    for key, val in league_data.items():
        if norm in key or key in norm:
            return val

    # 截断匹配（前 5 字符）
    if len(norm) >= 5:
        prefix = norm[:5]
        for key, val in league_data.items():
            if key.startswith(prefix):
                return val

    return None


def _get_team_name_en(team_name: str) -> str:
    """获取球队英文名（从内存缓存或 TEAM_EN 映射）"""
    if team_name in _TEAM_NAME_CACHE:
        return _TEAM_NAME_CACHE[team_name]

    # 从 datafc_provider 的 TEAM_EN 映射取英文名
    try:
        from datafc_provider import TEAM_EN
        en = TEAM_EN.get(team_name, team_name)
    except Exception:
        en = team_name

    _TEAM_NAME_CACHE[team_name] = en
    return en


def fetch_team_xg(team_name: str, league_code: str) -> dict:
    """获取某队在 Understat 的 xG 数据

    Args:
        team_name: 球队名（中文或英文均可）
        league_code: 联赛代码 (epl/laliga/bl1/seriea/ligue1)

    Returns:
        {
            "xG_for_90": float,
            "xG_against_90": float,
            "matches_played": int,
            "source": "understat",
            "team_name_en": str,
        }
        失败时返回 {"xG_for_90": 0, "xG_against_90": 0, "matches_played": 0, "source": "understat_failed"}
    """
    # 检查是否在支持的联赛范围内
    if league_code not in UNDERSTAT_LEAGUE_MAP:
        return {"xG_for_90": 0, "xG_against_90": 0, "matches_played": 0, "source": "understat_unsupported"}

    # 获取联赛数据
    league_data = _get_understat_data(league_code)
    if not league_data:
        return {"xG_for_90": 0, "xG_against_90": 0, "matches_played": 0, "source": "understat_empty"}

    # 获取英文队名
    team_en = _get_team_name_en(team_name)

    # 模糊查找
    found = _find_team(team_en, league_data)
    if not found:
        _log(f"未找到 {team_name}({team_en}) 在 {league_code} 中")
        # 调试：打印所有队名
        _log(f"可用球队: {[v['display_name'] for v in league_data.values()]}")
        return {"xG_for_90": 0, "xG_against_90": 0, "matches_played": 0, "source": "understat_team_not_found"}

    _log(f"{team_name} → {found['display_name']}: xG_for={found['xG_for_90']}, xG_against={found['xG_against_90']}")
    return {
        "xG_for_90": found["xG_for_90"],
        "xG_against_90": found["xG_against_90"],
        "matches_played": found["matches_played"],
        "source": "understat",
        "team_name_en": found["display_name"],
    }


def clear_cache():
    """清空 Understat 缓存（强制下次重新获取）"""
    global _UNDERSTAT_CACHE, _UNDERSTAT_CACHE_TIME
    _UNDERSTAT_CACHE.clear()
    _UNDERSTAT_CACHE_TIME = 0
    _TEAM_NAME_CACHE.clear()
    _log("缓存已清空")


# ============================================================
# 快速测试（python skill/understat_provider.py）
# ============================================================
if __name__ == "__main__":
    # 测试几个队
    tests = [
        ("曼城", "epl"),
        ("阿森纳", "epl"),
        ("拜仁", "bl1"),
        ("巴黎", "ligue1"),
        ("皇马", "laliga"),
        ("米兰", "seriea"),
        ("马尔默", "allsvenskan"),  # 小联赛 → 应返回 unsupported
    ]
    for team, league in tests:
        result = fetch_team_xg(team, league)
        status = "✅" if result["source"] == "understat" else "❌"
        print(f"{status} {team:6s} @ {league:10s} → xG_for={result['xG_for_90']}, xG_against={result['xG_against_90']}, src={result['source']}")
