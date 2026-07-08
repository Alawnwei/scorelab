#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
西班牙 vs 奥地利 — 综合预测模型
2026世界杯 1/16决赛
"""

import math

# ============================================================
# 基础数据
# ============================================================
spain_ranking_pts = 1864.32   # FIFA排名积分
austria_ranking_pts = 1619.47
spain_fifa_rank = 3
austria_fifa_rank = 23

# 近期战绩（近8场正式+友谊赛）
spain_results = [
    ("Saudi Arabia", 4, 0, "WC"),
    ("Uruguay", 1, 0, "WC"),
    ("Cape Verde", 0, 0, "WC"),
    ("Iraq", 1, 1, "Friendly"),
    ("Egypt", 0, 0, "Friendly"),
    ("Serbia", 3, 0, "Friendly"),
    ("Türkiye", 2, 2, "Qualifier"),
    ("Georgia", 4, 0, "Qualifier"),
]

austria_results = [
    ("Algeria", 3, 3, "WC"),
    ("Argentina", 0, 2, "WC"),
    ("Jordan", 3, 1, "WC"),
    ("Tunisia", 1, 0, "Friendly"),
    ("Korea Republic", 1, 0, "Friendly"),
    ("Ghana", 5, 1, "Friendly"),
    ("Bosnia", 1, 1, "Qualifier"),
]

def match_weight(mtype):
    if mtype == "WC": return 1.0
    elif mtype == "Qualifier": return 0.8
    elif mtype == "Friendly": return 0.5
    return 0.6

# ============================================================
# 模型一: ELO排名模型
# ============================================================
def elo_win_prob(rating_a, rating_b):
    expected_a = 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / 400.0))
    return expected_a

spain_elo_win = elo_win_prob(spain_ranking_pts, austria_ranking_pts)
austria_elo_win = elo_win_prob(austria_ranking_pts, spain_ranking_pts)
draw_elo = 1.0 - spain_elo_win - austria_elo_win

print("=" * 60)
print("  ESPANA vs AUSTRIA - 综合预测模型")
print("=" * 60)
print(f"\nFIFA排名积分: 西班牙 {spain_ranking_pts} (#{spain_fifa_rank}) vs 奥地利 {austria_ranking_pts} (#{austria_fifa_rank})")

print(f"\n--- 模型一: ELO排名模型 ---")
print(f"  西班牙胜率: {spain_elo_win*100:.1f}%")
print(f"  平局概率:   {draw_elo*100:.1f}%")
print(f"  奥地利胜率: {austria_elo_win*100:.1f}%")

# ============================================================
# 模型二: 泊松分布模型
# ============================================================
def weighted_avg_goals(results):
    total_weight = 0
    total_gf = 0
    total_ga = 0
    for opp, gf, ga, mtype in results:
        w = match_weight(mtype)
        total_weight += w
        total_gf += gf * w
        total_ga += ga * w
    return total_gf / total_weight, total_ga / total_weight

spain_avg_gf, spain_avg_ga = weighted_avg_goals(spain_results)
austria_avg_gf, austria_avg_ga = weighted_avg_goals(austria_results)

print(f"\n--- 模型二: 泊松分布模型 ---")
print(f"\n  加权平均数据:")
print(f"  西班牙: 场均进 {spain_avg_gf:.2f} 球, 场均失 {spain_avg_ga:.2f} 球")
print(f"  奥地利: 场均进 {austria_avg_gf:.2f} 球, 场均失 {austria_avg_ga:.2f} 球")

league_avg = 2.5
spain_attack = spain_avg_gf / league_avg
spain_defense = spain_avg_ga / league_avg
austria_attack = austria_avg_gf / league_avg
austria_defense = austria_avg_ga / league_avg

expected_spain_goals = spain_attack * austria_defense * league_avg
expected_austria_goals = austria_attack * spain_defense * league_avg

print(f"\n  期望进球:")
print(f"  西班牙期望进球: {expected_spain_goals:.2f}")
print(f"  奥地利期望进球: {expected_austria_goals:.2f}")

def poisson_prob(lam, k):
    return (lam ** k) * math.exp(-lam) / math.factorial(k)

# 各种比分概率
print(f"\n  比分概率 (Top 10):")
score_probs = []
for s in range(6):
    for a in range(5):
        prob = poisson_prob(expected_spain_goals, s) * poisson_prob(expected_austria_goals, a)
        score_probs.append((prob, f"{s}-{a}"))

score_probs.sort(reverse=True)
for prob, score in score_probs[:10]:
    print(f"    {score} -> {prob*100:.1f}%")

# 胜平负
spain_win_poisson = 0
draw_poisson = 0
austria_win_poisson = 0
for s in range(8):
    for a in range(8):
        prob = poisson_prob(expected_spain_goals, s) * poisson_prob(expected_austria_goals, a)
        if s > a: spain_win_poisson += prob
        elif s == a: draw_poisson += prob
        else: austria_win_poisson += prob

print(f"\n  泊松模型胜率:")
print(f"  西班牙胜: {spain_win_poisson*100:.1f}%  平局: {draw_poisson*100:.1f}%  奥地利胜: {austria_win_poisson*100:.1f}%")

# ============================================================
# 模型三: 历史交锋模型
# ============================================================
h2h_total = 16
h2h_spain = 9
h2h_draw = 3
h2h_austria = 4

h2h_recent_spain = 4   # 近5场西班牙赢4场
h2h_recent_draw = 1
h2h_recent_austria = 0

print(f"\n--- 模型三: 历史交锋模型 ---")
print(f"  全部16场: 西班牙 {h2h_spain}胜 {h2h_draw}平 {h2h_austria}负")
print(f"  近5场:    西班牙 {h2h_recent_spain}胜 {h2h_recent_draw}平 {h2h_recent_austria}负")

# ============================================================
# 模型四: 小组赛表现
# ============================================================
print(f"\n--- 模型四: 世界杯小组赛表现 ---")
print(f"  西班牙: 小组第1, 进5球/失0球, 7分, 零封全部对手")
print(f"  奥地利: 小组第2, 进6球/失6球, 4分, 防守漏洞明显")

# ============================================================
# 综合加权模型
# ============================================================
print(f"\n{'='*60}")
print(" 综合加权预测模型")
print('='*60)

W_ELO = 0.25
W_POISSON = 0.30
W_H2H = 0.15
W_H2H_RECENT = 0.15
W_FORM = 0.15

def recent_form(results, n=5):
    recent = results[-n:] if len(results) >= n else results
    points = 0
    max_points = len(recent) * 3
    for _, gf, ga, _ in recent:
        if gf > ga: points += 3
        elif gf == ga: points += 1
    return points / max_points if max_points > 0 else 0

spain_form = recent_form(spain_results)
austria_form = recent_form(austria_results)

print(f"\n  近期状态 (近5场得分率):")
print(f"  西班牙: {spain_form*100:.1f}%")
print(f"  奥地利: {austria_form*100:.1f}%")

# 综合
spain_composite = (
    spain_elo_win * W_ELO +
    spain_win_poisson * W_POISSON +
    (h2h_spain / h2h_total) * W_H2H +
    (h2h_recent_spain / 5) * W_H2H_RECENT +
    spain_form * W_FORM
)

austria_composite = (
    austria_elo_win * W_ELO +
    austria_win_poisson * W_POISSON +
    (h2h_austria / h2h_total) * W_H2H +
    (h2h_recent_austria / 5) * W_H2H_RECENT +
    austria_form * W_FORM
)

draw_composite = (
    draw_elo * W_ELO +
    draw_poisson * W_POISSON +
    (h2h_draw / h2h_total) * W_H2H +
    (h2h_recent_draw / 5) * W_H2H_RECENT
)

total = spain_composite + austria_composite + draw_composite
spain_final = spain_composite / total * 100
draw_final = draw_composite / total * 100
austria_final = austria_composite / total * 100

print(f"\n{'='*60}")
print(" FINAL PREDICTION - 最终预测")
print('='*60)
print(f"\n  Espana (西班牙) 胜:  {spain_final:.1f}%")
print(f"  Draw (平局):         {draw_final:.1f}%")
print(f"  Austria (奥地利) 胜: {austria_final:.1f}%")
print()

top_scores = score_probs[:5]
print(f"  最可能比分: ", end="")
for prob, score in top_scores:
    print(f"{score} ({prob*100:.1f}%)  ", end="")
print()

# 大小球
over_25 = 0
under_25 = 0
for s in range(8):
    for a in range(8):
        prob = poisson_prob(expected_spain_goals, s) * poisson_prob(expected_austria_goals, a)
        if s + a > 2: over_25 += prob
        else: under_25 += prob
print(f"\n  大2.5球: {over_25*100:.1f}%")
print(f"  小2.5球: {under_25*100:.1f}%")

# 双方进球
both_score = 0
for s in range(1, 8):
    for a in range(1, 8):
        prob = poisson_prob(expected_spain_goals, s) * poisson_prob(expected_austria_goals, a)
        both_score += prob
print(f"  双方进球(BTTS): {both_score*100:.1f}%")
print(f"  一方零封:        {(1-both_score)*100:.1f}%")

# 半全场
ht_exp_s = expected_spain_goals * 0.45
ht_exp_a = expected_austria_goals * 0.45
ht_spain = 0; ht_draw = 0; ht_austria = 0
for s in range(5):
    for a in range(5):
        prob = poisson_prob(ht_exp_s, s) * poisson_prob(ht_exp_a, a)
        if s > a: ht_spain += prob
        elif s == a: ht_draw += prob
        else: ht_austria += prob
print(f"\n  半场领先概率:")
print(f"  西班牙领先: {ht_spain*100:.1f}%  平局: {ht_draw*100:.1f}%  奥地利领先: {ht_austria*100:.1f}%")

print(f"\n{'='*60}")
print(" 综合结论")
print('='*60)
print(f"""
  综合4个模型（ELO排名、泊松期望进球、历史交锋、近期状态），
  西班牙占据明显优势：

  ✅ 西班牙胜率高达 {spain_final:.0f}%，是绝对热门
  ✅ 西班牙小组赛零失球，防守固若金汤
  ✅ 历史交锋西班牙占绝对上风（近5场4胜1平不败）
  ✅ 奥地利防守问题突出（小组赛丢6球）

  最可能比分: {top_scores[0][1]} ({top_scores[0][0]*100:.1f}%)
  次可能比分: {top_scores[1][1]} ({top_scores[1][0]*100:.1f}%)

  预警:
  - 西班牙小组赛进攻效率一般（场均1.67球）
  - 奥地利有反击能力（小组赛进6球）
  - 平局概率约 {draw_final:.0f}%，需警惕90分钟平局可能
""")
