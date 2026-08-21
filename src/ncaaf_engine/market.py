from __future__ import annotations

from dataclasses import dataclass

from .config import EngineConfig
from .enums import ContractState, Direction
from .pricing.lmsr import TradeQuote, quote_trade


@dataclass(frozen=True)
class ExecutionResult:
    trade: TradeQuote
    expected_edge_at_entry: float


def expected_edge(direction: Direction, belief_yes: float, average_price: float) -> float:
    if not 0 < belief_yes < 1:
        raise ValueError("belief probability must be in (0,1)")
    if not 0 < average_price < 1:
        raise ValueError("average execution price must be in (0,1)")
    if direction == Direction.YES:
        return belief_yes - average_price
    return (1.0 - belief_yes) - average_price


def execute_order(
    *,
    contract_state: ContractState,
    q_yes: float,
    q_no: float,
    direction: Direction,
    quantity: float,
    belief_yes: float,
    config: EngineConfig,
    maximum_cost: float | None = None,
) -> ExecutionResult:
    if contract_state != ContractState.OPEN:
        raise ValueError("orders may execute only while contract is OPEN")
    if quantity > config.risk_limits.maximum_single_order_quantity:
        raise ValueError("quantity exceeds configured single-order limit")
    trade = quote_trade(q_yes, q_no, config.amm.liquidity_b, direction, quantity)
    if maximum_cost is not None and trade.cost > maximum_cost:
        raise ValueError("quoted cost exceeds maximum_cost")
    price_for_direction = trade.average_price if direction == Direction.YES else trade.average_price
    edge = expected_edge(direction, belief_yes, price_for_direction)
    return ExecutionResult(trade=trade, expected_edge_at_entry=edge)
