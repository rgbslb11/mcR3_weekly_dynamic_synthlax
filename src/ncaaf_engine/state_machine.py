from __future__ import annotations

from .enums import ContractState


ALLOWED_TRANSITIONS: dict[ContractState, set[ContractState]] = {
    ContractState.DISCOVERED: {ContractState.OBSERVED, ContractState.VOID},
    ContractState.OBSERVED: {ContractState.CREATED, ContractState.VOID},
    ContractState.CREATED: {ContractState.OPEN, ContractState.SUSPENDED, ContractState.VOID},
    ContractState.OPEN: {ContractState.SUSPENDED, ContractState.LOCKED, ContractState.VOID},
    ContractState.SUSPENDED: {ContractState.OPEN, ContractState.LOCKED, ContractState.VOID},
    ContractState.LOCKED: {ContractState.RESULT_PENDING, ContractState.VOID},
    ContractState.RESULT_PENDING: {ContractState.SETTLED, ContractState.DISPUTED, ContractState.VOID},
    ContractState.DISPUTED: {ContractState.SETTLED, ContractState.VOID},
    ContractState.SETTLED: set(),
    ContractState.VOID: set(),
}


def can_transition(current: ContractState, target: ContractState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def require_transition(current: ContractState, target: ContractState) -> None:
    if not can_transition(current, target):
        raise ValueError(f"invalid contract transition: {current} -> {target}")
