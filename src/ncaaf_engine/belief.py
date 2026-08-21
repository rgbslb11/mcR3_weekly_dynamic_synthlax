from __future__ import annotations

from .config import EngineConfig


def initial_belief(config: EngineConfig) -> float:
    return config.initial_belief_probability


def apply_public_money_to_belief(belief_probability: float, *_args, **_kwargs) -> float:
    """Invariant: public money is flow evidence only in v0."""
    return belief_probability


def apply_sharp_consensus_to_belief(
    belief_probability: float,
    sharp_consensus: float | None,
    config: EngineConfig,
) -> float:
    if sharp_consensus is None:
        return belief_probability
    if not config.feature_flags.sharp_belief_adjustment:
        return belief_probability
    raise RuntimeError("BLOCKED: sharp consensus probability calibration is not implemented")
