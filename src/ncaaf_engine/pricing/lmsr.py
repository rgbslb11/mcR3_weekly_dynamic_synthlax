from __future__ import annotations

from dataclasses import dataclass
from math import exp, log

from ..enums import Direction


@dataclass(frozen=True)
class TradeQuote:
    direction: Direction
    quantity: float
    cost: float
    average_price: float
    probability_before: float
    probability_after: float
    q_yes_after: float
    q_no_after: float


def _logsumexp2(a: float, b: float) -> float:
    m = max(a, b)
    return m + log(exp(a - m) + exp(b - m))


def cost(q_yes: float, q_no: float, liquidity_b: float) -> float:
    if liquidity_b <= 0:
        raise ValueError("liquidity_b must be positive")
    return liquidity_b * _logsumexp2(q_yes / liquidity_b, q_no / liquidity_b)


def probability_yes(q_yes: float, q_no: float, liquidity_b: float) -> float:
    if liquidity_b <= 0:
        raise ValueError("liquidity_b must be positive")
    delta = (q_no - q_yes) / liquidity_b
    if delta >= 0:
        z = exp(-delta)
        return z / (1.0 + z)
    z = exp(delta)
    return 1.0 / (1.0 + z)


def quote_trade(
    q_yes: float,
    q_no: float,
    liquidity_b: float,
    direction: Direction,
    quantity: float,
) -> TradeQuote:
    if quantity <= 0:
        raise ValueError("quantity must be positive")
    before = probability_yes(q_yes, q_no, liquidity_b)
    old_cost = cost(q_yes, q_no, liquidity_b)
    if direction == Direction.YES:
        q_yes_after, q_no_after = q_yes + quantity, q_no
    elif direction == Direction.NO:
        q_yes_after, q_no_after = q_yes, q_no + quantity
    else:
        raise ValueError(f"unsupported direction: {direction}")
    new_cost = cost(q_yes_after, q_no_after, liquidity_b)
    trade_cost = new_cost - old_cost
    average_price = trade_cost / quantity
    after = probability_yes(q_yes_after, q_no_after, liquidity_b)
    return TradeQuote(
        direction=direction,
        quantity=quantity,
        cost=trade_cost,
        average_price=average_price,
        probability_before=before,
        probability_after=after,
        q_yes_after=q_yes_after,
        q_no_after=q_no_after,
    )


def maximum_binary_subsidy(liquidity_b: float) -> float:
    if liquidity_b <= 0:
        raise ValueError("liquidity_b must be positive")
    return liquidity_b * log(2.0)
