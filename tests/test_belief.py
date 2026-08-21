import pytest

from ncaaf_engine.belief import apply_public_money_to_belief, apply_sharp_consensus_to_belief, initial_belief
from ncaaf_engine.config import DEFAULT_CONFIG


def test_initial_belief_is_half():
    assert initial_belief(DEFAULT_CONFIG) == pytest.approx(.5)


def test_public_money_does_not_move_belief():
    assert apply_public_money_to_belief(.5, public_crowding=.99) == pytest.approx(.5)


def test_sharp_consensus_disabled_does_not_move_belief():
    assert apply_sharp_consensus_to_belief(.5, .8, DEFAULT_CONFIG) == pytest.approx(.5)
