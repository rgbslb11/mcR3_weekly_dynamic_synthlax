from __future__ import annotations

from ..config import ContrarianConfig, MomentumRetailConfig, RetailCrowdConfig
from ..domain import SimulationIntent
from ..enums import Direction, ParticipantType


def retail_crowd_intent(relative_crowding: float, config: RetailCrowdConfig) -> SimulationIntent | None:
    if not config.enabled or abs(relative_crowding) < config.activation_threshold:
        return None
    quantity = config.base_quantity * (abs(relative_crowding) ** config.exponent)
    direction = Direction.YES if relative_crowding > 0 else Direction.NO
    return SimulationIntent(
        participant_type=ParticipantType.RETAIL_CROWD,
        direction=direction,
        quantity=quantity,
        reason=f"relative_crowding={relative_crowding:.6f}",
    )


def momentum_retail_intent(recent_difference: float, config: MomentumRetailConfig) -> SimulationIntent | None:
    if not config.enabled or abs(recent_difference) < config.activation_threshold:
        return None
    direction = Direction.YES if recent_difference > 0 else Direction.NO
    quantity = config.base_quantity * abs(recent_difference)
    return SimulationIntent(
        participant_type=ParticipantType.MOMENTUM_RETAIL,
        direction=direction,
        quantity=quantity,
        reason=f"recent_concentration_difference={recent_difference:.6f}",
    )


def contrarian_intent(
    belief_probability_yes: float,
    market_probability_yes: float,
    config: ContrarianConfig,
) -> SimulationIntent | None:
    edge = belief_probability_yes - market_probability_yes
    if not config.enabled or abs(edge) < config.minimum_absolute_edge:
        return None
    direction = Direction.YES if edge > 0 else Direction.NO
    return SimulationIntent(
        participant_type=ParticipantType.CONTRARIAN,
        direction=direction,
        quantity=config.base_quantity,
        reason=f"belief_market_edge={edge:.6f}",
    )
