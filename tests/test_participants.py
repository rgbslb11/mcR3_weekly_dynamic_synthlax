from ncaaf_engine.config import DEFAULT_CONFIG
from ncaaf_engine.enums import Direction
from ncaaf_engine.simulation.participants import contrarian_intent, retail_crowd_intent


def test_retail_below_threshold_no_order():
    assert retail_crowd_intent(.05, DEFAULT_CONFIG.retail_crowd) is None


def test_retail_positive_buys_yes():
    intent = retail_crowd_intent(.4, DEFAULT_CONFIG.retail_crowd)
    assert intent is not None
    assert intent.direction == Direction.YES


def test_contrarian_buys_no_when_market_too_high():
    intent = contrarian_intent(.50, .54, DEFAULT_CONFIG.contrarian)
    assert intent is not None
    assert intent.direction == Direction.NO
