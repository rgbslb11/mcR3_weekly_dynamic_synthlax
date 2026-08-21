import pytest

from ncaaf_engine.enums import Direction, SkillTier
from ncaaf_engine.signals.capper import WeightedPick, sharp_consensus


def test_no_picks_no_consensus():
    assert sharp_consensus([]) is None


def test_no_positive_weight_capper_is_excluded():
    picks = [WeightedPick("Insiderone777", Direction.YES, .99, SkillTier.NO_POSITIVE_WEIGHT)]
    assert sharp_consensus(picks) is None


def test_weighted_consensus():
    picks = [
        WeightedPick("mollydog", Direction.NO, 1.00, SkillTier.ELITE),
        WeightedPick("Insiderone777", Direction.NO, .99, SkillTier.ELITE),
        WeightedPick("courtney1966", Direction.NO, .82, SkillTier.STRONG),
        WeightedPick("BammBamm64", Direction.YES, .76, SkillTier.STRONG),
    ]
    value = sharp_consensus(picks)
    assert value is not None
    assert value < 0
    assert value == pytest.approx((-1 - .99 - .82 + .76) / (1 + .99 + .82 + .76))
