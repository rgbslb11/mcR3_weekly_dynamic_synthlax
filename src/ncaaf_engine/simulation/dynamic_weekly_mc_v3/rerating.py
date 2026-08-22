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


@dataclass(frozen=True)
class PromotedRegimeRerater:
    """The governed weekly rerating, driven by a promoted calibration regime.

    :class:`BlockedGovernedRerater` refuses until "the configured residual,
    recent-form, blowout, regularization, and cap policies are promoted as one
    explicit experimental regime". This is that regime, and nothing less: it
    refuses to construct itself from a configuration that leaves any of the six
    values null, so a partially-calibrated configuration still cannot run.

    The arithmetic is not written here. It is
    :func:`mvp_control.weekly_delta`, the same function the control calibration
    scored candidates with, so the update a parameter was chosen under and the
    update it is applied under cannot drift apart.

    What this class owns is the part the engine hands it: the preseason
    prior-decay blend. That schedule is governed, not calibrated —
    :meth:`V3Config.validate_architecture` refuses a configuration carrying a
    different one — so it is read from the configuration rather than from the
    regime.
    """

    regime: object

    @classmethod
    def from_config(cls, config: V3Config) -> "PromotedRegimeRerater":
        from .mvp_control import regime_from_values

        blockers = config.calibration.blockers()
        if blockers:
            raise GovernanceBlock(
                "Weekly rerating cannot be activated from a configuration with unresolved "
                "calibration values: " + ", ".join(blockers)
            )
        calibration = config.calibration
        return cls(
            regime=regime_from_values(
                config.configuration_version,
                {
                    "weekly_performance_residual_coefficient": (
                        calibration.weekly_performance_residual_coefficient
                    ),
                    "weekly_movement_cap_points": calibration.weekly_movement_cap_points,
                    "recent_form_weights": list(calibration.recent_form_weights or ()),
                    "blowout_treatment": calibration.blowout_treatment,
                    "game_sd_points": calibration.game_sd_points,
                    "sample_size_regularization": calibration.sample_size_regularization,
                },
            )
        )

    def rerate(
        self, *, week_completed: int, states: dict[str, TeamPathState], config: V3Config
    ) -> dict[str, float]:
        from .mvp_control import weekly_delta

        prior_weight = config.prior_weight_after_week(week_completed)
        out: dict[str, float] = {}
        for team_id, state in states.items():
            _, delta = weekly_delta(
                self.regime,
                residual_history=state.residual_history,
                games_played=state.games_played,
            )
            performance_state = state.promoted_strength_points + delta
            out[team_id] = (
                prior_weight * state.preseason_strength_points
                + (1.0 - prior_weight) * performance_state
            )
        return out
