from decimal import Decimal

import pytest

from ncaaf_engine.config import DEFAULT_CONFIG, PublicCrowdingConfig
from ncaaf_engine.signals.public_money import (
    PublicMoneyRaw,
    crowding_score,
    derive_public_money,
    empirical_percentiles,
    recent_money_ratio,
    relative_crowding,
)


def test_recent_ratio():
    assert recent_money_ratio(Decimal("4000000"), Decimal("1000000")) == pytest.approx(0.25)


def test_zero_denominator_is_none():
    assert recent_money_ratio(Decimal("0"), Decimal("0")) is None


def test_negative_money_rejected():
    with pytest.raises(ValueError):
        recent_money_ratio(Decimal("-1"), Decimal("0"))


def test_crowding_weights_sum_to_one():
    cfg = DEFAULT_CONFIG.public_crowding
    assert cfg.season_weight + cfg.recent_weight + cfg.concentration_weight == pytest.approx(1)


def test_invalid_weight_sum_rejected():
    with pytest.raises(ValueError):
        PublicCrowdingConfig(season_weight=.5, recent_weight=.5, concentration_weight=.5)


def test_crowding_formula():
    cfg = DEFAULT_CONFIG.public_crowding
    score = crowding_score(1.0, 0.5, 0.0, cfg)
    assert score == pytest.approx(0.40 + 0.175)


def test_empirical_percentile_ties_are_deterministic():
    values = [1.0, 2.0, 2.0, 4.0]
    result = empirical_percentiles(values)
    assert result[0] == pytest.approx(0)
    assert result[1] == result[2]
    assert result[3] == pytest.approx(1)


def test_derive_public_money():
    rows = [
        PublicMoneyRaw("a", Decimal("100"), Decimal("10")),
        PublicMoneyRaw("b", Decimal("200"), Decimal("100")),
        PublicMoneyRaw("c", Decimal("300"), Decimal("300")),
    ]
    derived = derive_public_money(rows, DEFAULT_CONFIG.public_crowding)
    assert len(derived) == 3
    assert derived[2].crowding_score > derived[0].crowding_score


def test_relative_crowding_is_antisymmetric():
    assert relative_crowding(.8, .2) == pytest.approx(.6)
    assert relative_crowding(.2, .8) == pytest.approx(-.6)
