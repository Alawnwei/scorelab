"""
NB 分布核心函数单元测试
测试: nb_prob, nb_match_probs, nb_over_25, nb_btts,
      nb_team_over, nb_win_and_over, nb_first_goal
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skill'))

import math
from predict import (
    nb_prob, nb_match_probs, nb_over_25, nb_btts,
    nb_team_over, nb_win_and_over, nb_first_goal
)


def test_nb_prob_basic():
    """nb_prob: 基本概率计算"""
    p = nb_prob(0, 1.5, 8)
    assert 0 < p < 1, f"P(0|λ=1.5) should be 0-1, got {p}"

    p = nb_prob(1, 1.5, 8)
    assert 0 < p < 1, f"P(1|λ=1.5) should be 0-1, got {p}"

    # 概率和（0到10的PMF和 ≈ 1.0）
    total = sum(nb_prob(k, 1.5, 8) for k in range(11))
    assert abs(total - 1.0) < 0.01, f"PMF sum should ≈1.0, got {total}"


def test_nb_prob_poisson_limit():
    """nb_prob: θ→∞时趋近泊松"""
    p_nb = nb_prob(2, 1.5, 1000)  # θ很大 ≈ 泊松
    p_poi = math.exp(-1.5) * (1.5 ** 2) / math.factorial(2)
    assert abs(p_nb - p_poi) < 0.001, f"θ→∞ should ≈ Poisson, {p_nb} vs {p_poi}"


def test_nb_prob_zero_lam():
    """nb_prob: λ=0 时 P(0) = 1"""
    p = nb_prob(0, 0, 8)
    assert p == 1.0, f"P(0|λ=0) should be 1.0, got {p}"

    p = nb_prob(1, 0, 8)
    assert p == 0.0, f"P(1|λ=0) should be 0.0, got {p}"


def test_nb_match_probs_sum():
    """nb_match_probs: 三种结果概率和应为1.0"""
    hp, dp, ap = nb_match_probs(1.5, 1.2, 8)
    total = hp + dp + ap
    assert abs(total - 1.0) < 0.01, f"1X2 sum should ≈1.0, got {total}"


def test_nb_match_probs_symmetric():
    """nb_match_probs: λ相等时主客胜概率应相等"""
    hp, dp, ap = nb_match_probs(1.5, 1.5, 8)
    assert abs(hp - ap) < 0.01, f"Equal λ: home({hp}) should ≈ away({ap})"


def test_nb_match_probs_extreme():
    """nb_match_probs: λ差距大时强队应占明显优势"""
    hp, dp, ap = nb_match_probs(3.0, 0.5, 8)
    assert hp > 0.7, f"λ=3.0 vs 0.5: home should dominate, got {hp}"
    assert ap < 0.2, f"λ=3.0 vs 0.5: away should be weak, got {ap}"


def test_nb_over_25_range():
    """nb_over_25: 输出应在0-1之间"""
    ov = nb_over_25(1.5, 1.2, 8)
    assert 0 < ov < 1, f"over_25 should be 0-1, got {ov}"

    ov_high = nb_over_25(3.0, 2.0, 8)
    ov_low = nb_over_25(0.5, 0.5, 8)
    assert ov_high > ov_low, f"Higher λ should give higher over probability"


def test_nb_btts_range():
    """nb_btts: 输出应在0-1之间"""
    bt = nb_btts(1.5, 1.2, 8)
    assert 0 < bt < 1, f"btts should be 0-1, got {bt}"


def test_nb_team_over():
    """nb_team_over: P(进球 > line)"""
    p = nb_team_over(2.0, 8, 0.5)  # P(>0.5球) = 1 - P(0)
    p0 = nb_prob(0, 2.0, 8)
    assert abs(p - (1 - p0)) < 0.01, f"P(>0.5) should = 1-P(0)"


def test_nb_win_and_over_subset():
    """nb_win_and_over: P(主胜&大2.5) ≤ P(主胜)"""
    wo = nb_win_and_over(2.0, 1.0, 8, 2.5)
    hp, dp, ap = nb_match_probs(2.0, 1.0, 8)
    assert wo <= hp + 0.01, f"win_and_over({wo}) should <= home_prob({hp})"


def test_nb_first_goal():
    """nb_first_goal: 三种结果和应为1.0"""
    fg_h, fg_a, fg_no = nb_first_goal(2.0, 1.0)
    total = fg_h + fg_a + fg_no
    assert abs(total - 1.0) < 0.01, f"first_goal sum should ≈1.0, got {total}"

    # 强队先进球概率应更高
    assert fg_h > fg_a, f"Home(λ=2.0) should have higher first goal than away(λ=1.0)"


def test_nb_first_goal_equal():
    """nb_first_goal: λ相等时，主场因素让主队略占优"""
    fg_h, fg_a, fg_no = nb_first_goal(1.0, 1.0)
    assert fg_h > fg_a, f"Equal λ: home factor should give edge, {fg_h} vs {fg_a}"
    assert abs(fg_h - fg_a) < 0.05, f"Home edge should be small, diff={abs(fg_h-fg_a)}"


if __name__ == "__main__":
    tests = [fn for fn in dir() if fn.startswith('test_')]
    passed = 0
    failed = 0
    for name in tests:
        try:
            globals()[name]()
            print(f"  ✅ {name}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ {name}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{passed+failed} 通过")
    sys.exit(0 if failed == 0 else 1)
