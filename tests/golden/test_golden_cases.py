import pytest

from ncaaf_engine.belief import apply_public_money_to_belief
from ncaaf_engine.config import DEFAULT_CONFIG
from ncaaf_engine.enums import Direction, IdentityStatus, ParticipantType
from ncaaf_engine.identity import resolve_source_team_label
from ncaaf_engine.pricing.lmsr import quote_trade
from ncaaf_engine.simulation.participants import contrarian_intent, retail_crowd_intent


def test_golden_a_no_signal():
    belief = .5
    market = .5
    assert belief == market
    assert contrarian_intent(belief, market, DEFAULT_CONFIG.contrarian) is None


def test_golden_b_public_crowding_moves_market_not_belief():
    belief = apply_public_money_to_belief(.5, public_crowding=.9)
    retail = retail_crowd_intent(.8, DEFAULT_CONFIG.retail_crowd)
    assert retail is not None and retail.direction == Direction.YES
    trade = quote_trade(0, 0, DEFAULT_CONFIG.amm.liquidity_b, retail.direction, retail.quantity)
    assert belief == pytest.approx(.5)
    assert trade.probability_after > .5


def test_golden_c_contrarian_responds_to_divergence():
    intent = contrarian_intent(.5, .54, DEFAULT_CONFIG.contrarian)
    assert intent is not None
    assert intent.participant_type == ParticipantType.CONTRARIAN
    assert intent.direction == Direction.NO
    after = quote_trade(160, 0, 1000, Direction.NO, 20)
    assert after.probability_after < after.probability_before


def test_golden_e_ambiguous_tigers_blocks():
    identity = resolve_source_team_label("Tigers")
    assert identity.status == IdentityStatus.BLOCKED
    assert identity.stable_id is None
