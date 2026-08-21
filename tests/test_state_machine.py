import pytest

from ncaaf_engine.enums import ContractState
from ncaaf_engine.state_machine import can_transition, require_transition


def test_created_to_open_allowed():
    assert can_transition(ContractState.CREATED, ContractState.OPEN)


def test_open_to_result_pending_rejected():
    with pytest.raises(ValueError):
        require_transition(ContractState.OPEN, ContractState.RESULT_PENDING)


def test_settled_to_open_rejected():
    with pytest.raises(ValueError):
        require_transition(ContractState.SETTLED, ContractState.OPEN)
