import math

import pytest

from ncaaf_engine.enums import Direction
from ncaaf_engine.pricing.lmsr import maximum_binary_subsidy, probability_yes, quote_trade


def test_initial_probability_is_half():
    assert probability_yes(0, 0, 1000) == pytest.approx(0.5)


def test_yes_purchase_raises_yes_probability():
    q = quote_trade(0, 0, 1000, Direction.YES, 25)
    assert q.probability_after > q.probability_before
    assert 0 < q.average_price < 1
    assert q.cost > 0


def test_no_purchase_lowers_yes_probability():
    q = quote_trade(0, 0, 1000, Direction.NO, 25)
    assert q.probability_after < q.probability_before
    assert 0 < q.average_price < 1


def test_complement_is_one():
    py = probability_yes(100, -50, 1000)
    assert py + (1 - py) == pytest.approx(1)


def test_larger_yes_trade_costs_more_and_moves_more():
    small = quote_trade(0, 0, 1000, Direction.YES, 10)
    large = quote_trade(0, 0, 1000, Direction.YES, 50)
    assert large.cost > small.cost
    assert large.probability_after > small.probability_after


def test_deterministic():
    a = quote_trade(12.5, -3, 1000, Direction.YES, 17)
    b = quote_trade(12.5, -3, 1000, Direction.YES, 17)
    assert a == b


def test_subsidy_bound_formula():
    assert maximum_binary_subsidy(1000) == pytest.approx(1000 * math.log(2))


def test_invalid_liquidity_rejected():
    with pytest.raises(ValueError):
        probability_yes(0, 0, 0)
