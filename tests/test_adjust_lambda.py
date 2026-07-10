"""
λ 调整函数单元测试
测试: adjust_lambda, _calc_ko_lambda_factor, get_time_adjustment
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'skill'))

import math
from predict import adjust_lambda
from betting_engine import BettingEngine


# ============ adjust_lambda ============

def test_adjust_lambda_normal():
    """adjust_lambda: 正常攻防值"""
    lam = adjust_lambda(1.5, 1.2, 0.8)
    assert 0.1 < lam < 6.0, f"Normal case should be in range, got {lam}"
    # att=1.2(好) + def=0.8(好) → 预期略高于1.5
    assert lam >= 1.4, f"Good att+def should increase λ, got {lam}"


def test_adjust_lambda_att_high():
    """adjust_lambda: 进攻强→λ高"""
    lam_high = adjust_lambda(1.5, 1.5, 1.0)
    lam_low = adjust_lambda(1.5, 0.5, 1.0)
    assert lam_high > lam_low, f"Strong attack should give higher λ"


def test_adjust_lambda_def_good():
    """adjust_lambda: 对手防守好→λ低"""
    lam_vs_good = adjust_lambda(1.5, 1.0, 0.5)   # 对手防守好(def_str<1)
    lam_vs_bad = adjust_lambda(1.5, 1.0, 1.5)    # 对手防守差(def_str>1)
    assert lam_vs_good < lam_vs_bad, f"Good defense should reduce λ"


def test_adjust_lambda_clamping():
    """adjust_lambda: 极端值应被钳制"""
    # att_str=5.0 应被钳制到 2.0
    lam_clamped = adjust_lambda(1.5, 5.0, 0.5)
    lam_normal = adjust_lambda(1.5, 2.0, 0.5)  # 2.0 是钳制上限
    assert abs(lam_clamped - lam_normal) < 0.01, \
        f"att_str=5.0 should clamp to 2.0: {lam_clamped} vs {lam_normal}"

    # def_str=0.1 应被钳制到 0.5
    lam_c2 = adjust_lambda(1.5, 1.0, 0.1)
    lam_n2 = adjust_lambda(1.5, 1.0, 0.5)
    assert abs(lam_c2 - lam_n2) < 0.01, \
        f"def_str=0.1 should clamp to 0.5: {lam_c2} vs {lam_n2}"


def test_adjust_lambda_nan_protection():
    """adjust_lambda: NaN 应降级为 1.0"""
    lam = adjust_lambda(1.5, float('nan'), float('nan'))
    assert 0.1 < lam < 6.0, f"NaN should be handled, got {lam}"


def test_adjust_lambda_none_protection():
    """adjust_lambda: None 应降级为 1.0"""
    lam = adjust_lambda(1.5, None, None)
    assert lam == 1.5, f"None att/def should give λ=1.5, got {lam}"


def test_adjust_lambda_lam_base_nan():
    """adjust_lambda: λ_base 为 NaN 时用 1.40 默认"""
    lam = adjust_lambda(float('nan'), 1.0, 1.0)
    assert abs(lam - 1.40) < 0.01, f"NaN lam_base should default to 1.40, got {lam}"


# ============ get_time_adjustment ============

def test_time_adjustment_boundaries():
    """get_time_adjustment: 边界值"""
    be = BettingEngine(bankroll=10000, mode='pro')
    assert be.get_time_adjustment(1) == 0.5     # < 3h
    assert be.get_time_adjustment(6) == 1.0     # 3-12h
    assert be.get_time_adjustment(24) == 1.0    # 12-48h
    assert be.get_time_adjustment(60) == 0.8    # 48-72h
    assert be.get_time_adjustment(96) == 0.6    # > 72h


def test_time_adjustment_edge():
    """get_time_adjustment: 边界值附近的整数"""
    be = BettingEngine(bankroll=10000, mode='pro')
    assert be.get_time_adjustment(0) == 0.5     # 临界 0h
    assert be.get_time_adjustment(3) == 1.0     # 正好 3h
    assert be.get_time_adjustment(47) == 1.0    # 47h 仍在正常范围
    assert be.get_time_adjustment(48) == 0.8    # 48h 进入折扣
    assert be.get_time_adjustment(71) == 0.8    # 71h 仍在折扣
    assert be.get_time_adjustment(72) == 0.6    # 72h 进入过低折扣


# ============ 市场 EV 阈值 ============

def test_market_min_ev():
    """get_market_min_ev: 分市场阈值"""
    be = BettingEngine(bankroll=10000, mode='pro')
    assert be.get_market_min_ev('1x2') == 10
    assert be.get_market_min_ev('asian') == 12
    assert be.get_market_min_ev('ou') == 8
    assert be.get_market_min_ev('btts') == 10
    assert be.get_market_min_ev('corners') == 15
    assert be.get_market_min_ev('unknown') == 10  # 默认回退


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
