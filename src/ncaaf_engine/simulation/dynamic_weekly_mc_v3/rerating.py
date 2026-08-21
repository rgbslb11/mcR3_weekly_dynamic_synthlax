from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import V3Config
from .errors import GovernanceBlock
from .models import TeamPathState


class WeeklyRerater(Protocol):
    def rerate(self, *, week_completed: int, states: dict[str, TeamPathState], config: V3Config) -> dict[str, float]: ...


class BlockedGovernedRerater:
    """Production-facing guardrail until the experimental rerating calibration is approved."""

    def rerate(self, *, week_completed: int, states: dict[str, TeamPathState], config: V3Config) -> dict[str, float]:
        blockers = config.calibration.blockers()
        if blockers:
            raise GovernanceBlock(
                "Weekly rerating is blocked pending explicit experimental configuration: " + ", ".join(blockers)
            )
        raise GovernanceBlock(
            "Weekly rerating math is intentionally not activated until the configured residual, recent-form, "
            "blowout, regularization, and cap policies are promoted as one explicit experimental regime."
        )


@dataclass(frozen=True)
class FixtureResidualRerater:
    """Test-only deterministic rerater. Never loaded by the V3 CLI.

    It exists to verify weekly-state promotion, path isolation, caps, and prior decay without
    asserting a canonical V3 calibration formula.
    """

    coefficient: float
    movement_cap_points: float

    def rerate(self, *, week_completed: int, states: dict[str, TeamPathState], config: V3Config) -> dict[str, float]:
        out: dict[str, float] = {}
        prior_weight = config.prior_weight_after_week(week_completed)
        for team_id, state in states.items():
            residual = state.residual_history[-1] if state.residual_history else 0.0
            raw_delta = self.coefficient * residual
            delta = max(-self.movement_cap_points, min(self.movement_cap_points, raw_delta))
            performance_state = state.promoted_strength_points + delta
            out[team_id] = (
                prior_weight * state.preseason_strength_points
                + (1.0 - prior_weight) * performance_state
            )
        return out
