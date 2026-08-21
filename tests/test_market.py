import pytest

from ncaaf_engine.config import DEFAULT_CONFIG
from ncaaf_engine.enums import ContractState, Direction
from ncaaf_engine.market import execute_order, expected_edge


def test_locked_contract_rejects_trade():
    with pytest.raises(ValueError, match="OPEN"):
        execute_order(
            contract_state=ContractState.LOCKED,
            q_yes=0,
            q_no=0,
            direction=Direction.YES,
            quantity=10,
            belief_yes=.5,
            config=DEFAULT_CONFIG,
        )


def test_open_contract_executes_and_records_edge():
    result = execute_order(
        contract_state=ContractState.OPEN,
        q_yes=0,
        q_no=0,
        direction=Direction.YES,
        quantity=10,
        belief_yes=.55,
        config=DEFAULT_CONFIG,
    )
    assert result.trade.probability_after > .5
    assert result.expected_edge_at_entry == pytest.approx(.55 - result.trade.average_price)


def test_no_edge_uses_no_belief():
    assert expected_edge(Direction.NO, .6, .35) == pytest.approx(.05)


def test_maximum_cost_enforced():
    with pytest.raises(ValueError, match="maximum_cost"):
        execute_order(
            contract_state=ContractState.OPEN,
            q_yes=0,
            q_no=0,
            direction=Direction.YES,
            quantity=20,
            belief_yes=.5,
            config=DEFAULT_CONFIG,
            maximum_cost=.01,
        )
