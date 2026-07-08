"""
战术分析引擎
基于《足球分析.md》中的三大战术风格对阵矩阵
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Optional
from team_data import Team, TacticalStyle, TeamStrength


# ============================================================
# 核心对阵矩阵
# 基于文档总结的战术对阵规律
# ============================================================

@dataclass
class TacticalMatchupResult:
    """战术对阵分析结果"""
    pace: str                              # 比赛节奏: "快" / "慢" / "中等"
    big_ball_probability: str              # 大球概率: "高" / "中" / "低"
    small_ball_probability: str            # 小球概率: "高" / "中" / "低"
    expected_goals_range: Tuple[int, int]  # 预期进球范围
    description: str                       # 分析描述
    home_advantage: float = 0.0            # 主场优势修正
    confidence: str = "中"                 # 信心程度: "高" / "中" / "低"


def _normalize_style(team: Team) -> TacticalStyle:
    """规范化球队战术风格，HYBRID映射到主要倾向"""
    if team.primary_style == TacticalStyle.HYBRID:
        # HYBRID球队要看具体描述判断倾向
        if "控场" in team.notes or "传控" in team.notes:
            return TacticalStyle.POSSESSION
        else:
            return TacticalStyle.HIGH_PRESS
    return team.primary_style


def _is_possession_first(team: Team) -> bool:
    """判断传控是否为主导（对于复合型）"""
    return TacticalStyle.POSSESSION in team.tactical_styles


# ============================================================
# 对阵矩阵规则
# 文档结论：
#   防守反击 vs 防守反击 → 节奏慢，小球
#   传控 vs 防守反击 → 节奏慢，小球
#   防守反击 vs 高位逼抢 → 节奏快，大球
#   传控 vs 高位逼抢 → 进球数2-3球范围
#   高位逼抢 vs 高位逼抢 → 节奏快，大球
#   传控 vs 传控 → 节奏中等
# ============================================================

_MATCHUP_MATRIX = {
    # (Style_A, Style_B) -> (pace, big_ball_prob, small_ball_prob, goal_range, desc)
    (TacticalStyle.COUNTER_ATTACK, TacticalStyle.COUNTER_ATTACK): (
        "慢", "低", "高", (0, 2), "防守反击vs防守反击：两队都立足防守，节奏不会快，容易出小球"
    ),
    (TacticalStyle.POSSESSION, TacticalStyle.COUNTER_ATTACK): (
        "慢", "低", "高", (1, 2), "传控vs防守反击：控场球队遇防反球队，大概率慢节奏，大球或穿盘不容易出"
    ),
    (TacticalStyle.COUNTER_ATTACK, TacticalStyle.POSSESSION): (
        "慢", "低", "高", (1, 2), "防守反击vs传控：反击球队遇传控，节奏慢，小球概率高"
    ),
    (TacticalStyle.COUNTER_ATTACK, TacticalStyle.HIGH_PRESS): (
        "快", "高", "低", (2, 4), "防守反击vs高位逼抢：节奏快，容易出大球"
    ),
    (TacticalStyle.HIGH_PRESS, TacticalStyle.COUNTER_ATTACK): (
        "快", "高", "低", (2, 4), "高位逼抢vs防守反击：节奏快，容易出大球"
    ),
    (TacticalStyle.POSSESSION, TacticalStyle.HIGH_PRESS): (
        "中", "中", "中", (2, 3), "传控vs高位逼抢：一方节奏快，一方抓漏洞，进球数易出2-3球"
    ),
    (TacticalStyle.HIGH_PRESS, TacticalStyle.POSSESSION): (
        "中", "中", "中", (2, 3), "高位逼抢vs传控：对攻有空间，进球数2-3球范围"
    ),
    (TacticalStyle.HIGH_PRESS, TacticalStyle.HIGH_PRESS): (
        "快", "高", "低", (3, 5), "高位逼抢vs高位逼抢：对攻大战，节奏快，容易出大球"
    ),
    (TacticalStyle.POSSESSION, TacticalStyle.POSSESSION): (
        "中", "低", "中", (1, 3), "传控vs传控：控球争夺，节奏中等，进球一般不会太多"
    ),
    (TacticalStyle.COUNTER_ATTACK, TacticalStyle.HYBRID): (
        "中", "中", "中", (1, 3), "防守反击vs混合型：取决于混合型球队的临场倾向"
    ),
    (TacticalStyle.HYBRID, TacticalStyle.COUNTER_ATTACK): (
        "中", "中", "中", (1, 3), "混合型vs防守反击：节奏不确定，看混合型球队进攻投入度"
    ),
    (TacticalStyle.POSSESSION, TacticalStyle.HYBRID): (
        "中", "中", "中", (2, 3), "传控vs混合型：控场争夺，节奏中等"
    ),
    (TacticalStyle.HYBRID, TacticalStyle.POSSESSION): (
        "中", "中", "中", (2, 3), "混合型vs传控：节奏中等，看混合型球队打法倾向"
    ),
    (TacticalStyle.HIGH_PRESS, TacticalStyle.HYBRID): (
        "快", "高", "低", (2, 4), "高位逼抢vs混合型：节奏偏快，大球概率较高"
    ),
    (TacticalStyle.HYBRID, TacticalStyle.HIGH_PRESS): (
        "快", "高", "低", (2, 4), "混合型vs高位逼抢：节奏偏快，容易出大球"
    ),
    (TacticalStyle.HYBRID, TacticalStyle.HYBRID): (
        "中", "中", "中", (2, 3), "混合型vs混合型：节奏和进球取决于双方临场战术安排"
    ),
}


def analyze_tactical_matchup(home_team: Team, away_team: Team) -> TacticalMatchupResult:
    """
    分析两队战术对阵结果
    基于文档中的三大战术风格对阵矩阵
    """
    home_style = _normalize_style(home_team)
    away_style = _normalize_style(away_team)

    key = (home_style, away_style)
    result = _MATCHUP_MATRIX.get(key)

    if not result:
        pace, big_ball, small_ball = "中等", "中", "中"
        goal_range = (1, 3)
        desc = f"{home_style.value}vs{away_style.value}：待补充分析"
    else:
        pace, big_ball, small_ball, goal_range, desc = result

    # 实力差距修正
    strength_diff = _get_strength_diff(home_team, away_team)
    home_adv = 0.0

    if strength_diff > 0:
        # 实力更强的一方进攻可能更猛
        desc += f"\n⚠ {home_team.name}实力占优，进攻压制力因素需考虑"
    elif strength_diff < 0:
        desc += f"\n⚠ {away_team.name}实力占优，客场压制力因素需考虑"

    # 综合考虑进攻和防守数据修正
    goals_low, goals_high = goal_range
    total_attack = home_team.attacking_power + away_team.attacking_power
    total_defense = home_team.defensive_stability + away_team.defensive_stability

    if total_attack > 14 and total_defense < 10:
        # 攻击强防守弱 → 进球偏多
        goals_low += 1
        goals_high += 1
        big_ball = "高"
    elif total_attack < 8 and total_defense > 14:
        # 攻击弱防守强 → 进球偏少
        goals_low = max(0, goals_low - 1)
        goals_high = max(goals_low, goals_high - 1)
        small_ball = "高"

    # 信心度评定
    if home_style == TacticalStyle.HYBRID or away_style == TacticalStyle.HYBRID:
        confidence = "低"  # 复合型球队不确定性高
    elif key in _MATCHUP_MATRIX:
        confidence = "高" if result[1] != "中" else "中"
    else:
        confidence = "低"

    return TacticalMatchupResult(
        pace=pace,
        big_ball_probability=big_ball,
        small_ball_probability=small_ball,
        expected_goals_range=(goals_low, goals_high),
        description=desc,
        home_advantage=home_adv,
        confidence=confidence
    )


def _get_strength_diff(team_a: Team, team_b: Team) -> int:
    """计算两队实力差（正值表示A强于B）"""
    strength_order = {
        TeamStrength.TOP: 4,
        TeamStrength.STRONG: 3,
        TeamStrength.MIDDLE: 2,
        TeamStrength.WEAK: 1,
    }
    return strength_order.get(team_a.strength, 2) - strength_order.get(team_b.strength, 2)


def analyze_corner_tendency(home_team: Team, away_team: Team) -> dict:
    """
    分析角球趋势
    文档要点：
    - 高位逼抢/压迫式打法 → 爱刷角
    - 中锋争顶/定位球头球战术 → 刷角能力强
    - 边路冲击型 → 爱刷角
    """
    home_corner = _get_corner_score(home_team)
    away_corner = _get_corner_score(away_team)
    total_corner = home_corner + away_corner

    if total_corner >= 16:
        corner_verdict = "大角概率高"
        recommendation = "建议关注大角方向"
    elif total_corner >= 12:
        corner_verdict = "大角概率中等"
        recommendation = "大角可考虑，但需结合其他因素"
    else:
        corner_verdict = "大角概率较低"
        recommendation = "不太建议主攻大角方向"

    return {
        "home_corner_score": home_corner,
        "away_corner_score": away_corner,
        "total_corner_score": total_corner,
        "verdict": corner_verdict,
        "recommendation": recommendation,
        "details": f"{home_team.name}({home_corner}/10) vs {away_team.name}({away_corner}/10)"
    }


def _get_corner_score(team: Team) -> int:
    """计算球队刷角能力评分 (1-10)"""
    score = 5  # 基准分

    # 高位逼抢风格 +2
    if TacticalStyle.HIGH_PRESS in team.tactical_styles or team.primary_style == TacticalStyle.HIGH_PRESS:
        score += 2
    if TacticalStyle.HYBRID in team.tactical_styles and "进攻" in team.notes:
        score += 1

    # 边路冲击型 +1
    if "边路" in team.notes:
        score += 1

    # 定位球/头球战术 +2
    if team.good_at_set_pieces:
        score += 2

    # 直接标注刷角强
    if team.corner_tendency == "刷角强":
        score += 1

    # 防守反击风格但边路快 +1
    if TacticalStyle.COUNTER_ATTACK in team.tactical_styles and team.good_at_counter:
        score += 1

    return min(10, max(1, score))
