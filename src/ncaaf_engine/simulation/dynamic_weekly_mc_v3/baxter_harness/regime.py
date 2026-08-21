"""Candidate regimes over the six unresolved V3 calibration axes.

A :class:`~..calibration.CandidateRegime` is a bag of values. This module gives
those values operational meaning for the experimental Baxter model and refuses
the two shapes that would quietly manufacture calibration:

* A **partial regime**. If a regime omits an axis, something has to supply it,
  and whatever supplies it becomes an unrecorded calibration value. All six axes
  must be stated, so every number that influenced a score is in the record.
* An **out-of-band value**. Each axis has a stated admissible band. A value
  outside it is refused rather than clipped, because clipping scores a regime
  the caller did not ask for and reports it under the caller's name.

Nothing here ships candidate numbers. Grids are built from values the caller
supplies; the repository's experimental regime file remains empty until a
governed calibration program authors it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import product
from typing import Any, Iterable, Mapping, Sequence

from ..calibration import CALIBRATION_FIELDS, CandidateRegime
from ..errors import GovernanceBlock, InputValidationError

BLOWOUT_MODES = ("none", "cap_margin", "diminishing_returns")
REGULARIZATION_MODES = ("none", "games_played_shrink")

#: Admissible bands. These bound what the *harness* will evaluate; they are not
#: claims about which values are correct, and no value inside them is approved.
RESIDUAL_COEFFICIENT_BAND = (0.0, 5.0)
MOVEMENT_CAP_BAND = (0.0, 100.0)
GAME_SD_BAND = (1.0, 60.0)
RECENT_FORM_MAX_TERMS = 12


def _finite(value: Any, label: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        raise InputValidationError(f"{label} must be numeric, got {value!r}.") from None
    if not math.isfinite(out):
        raise InputValidationError(f"{label} must be finite, got {value!r}.")
    return out


def _in_band(value: float, band: tuple[float, float], label: str) -> float:
    low, high = band
    if not (low <= value <= high):
        raise InputValidationError(
            f"{label} = {value} is outside the harness admissible band [{low}, {high}]. "
            "Out-of-band candidates are refused, not clipped."
        )
    return value


@dataclass(frozen=True)
class BlowoutTreatment:
    """How an outsized margin is allowed to move a rating."""

    mode: str
    cap_points: float | None = None
    threshold_points: float | None = None
    exponent: float | None = None

    def treat(self, residual: float) -> float:
        if self.mode == "none":
            return residual
        magnitude = abs(residual)
        sign = 1.0 if residual >= 0 else -1.0
        if self.mode == "cap_margin":
            return sign * min(magnitude, float(self.cap_points))
        threshold = float(self.threshold_points)
        if magnitude <= threshold:
            return residual
        excess = magnitude - threshold
        return sign * (threshold + excess ** float(self.exponent))

    @property
    def sensitivity_threshold(self) -> float | None:
        """Margin at which this treatment starts to bind, for blowout sensitivity."""
        if self.mode == "cap_margin":
            return float(self.cap_points)
        if self.mode == "diminishing_returns":
            return float(self.threshold_points)
        return None

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "cap_points": self.cap_points,
            "threshold_points": self.threshold_points,
            "exponent": self.exponent,
        }


@dataclass(frozen=True)
class SampleSizeRegularization:
    """How much a team's own short record is trusted against its prior."""

    mode: str
    prior_games: float = 0.0

    def shrink(self, games_played: int) -> float:
        if self.mode == "none":
            return 1.0
        denominator = games_played + self.prior_games
        if denominator <= 0.0:
            return 0.0
        return games_played / denominator

    def as_dict(self) -> dict[str, Any]:
        return {"mode": self.mode, "prior_games": self.prior_games}


@dataclass(frozen=True)
class ResolvedRegime:
    """A fully specified, validated candidate over all six axes."""

    regime_id: str
    residual_coefficient: float
    movement_cap_points: float
    recent_form_weights: tuple[float, ...]
    blowout_treatment: BlowoutTreatment
    game_sd_points: float
    sample_size_regularization: SampleSizeRegularization
    rationale: str = ""

    @property
    def normalized_recent_form_weights(self) -> tuple[float, ...]:
        total = math.fsum(self.recent_form_weights)
        return tuple(w / total for w in self.recent_form_weights)

    def as_dict(self) -> dict[str, Any]:
        return {
            "regime_id": self.regime_id,
            "status": "EXPERIMENTAL",
            "weekly_performance_residual_coefficient": self.residual_coefficient,
            "weekly_movement_cap_points": self.movement_cap_points,
            "recent_form_weights": list(self.recent_form_weights),
            "recent_form_weights_normalized": list(self.normalized_recent_form_weights),
            "blowout_treatment": self.blowout_treatment.as_dict(),
            "game_sd_points": self.game_sd_points,
            "sample_size_regularization": self.sample_size_regularization.as_dict(),
            "rationale": self.rationale,
        }

    def candidate_values(self) -> dict[str, Any]:
        """The six axis values, in canonical field names, for the provenance record."""
        return {
            "weekly_performance_residual_coefficient": self.residual_coefficient,
            "weekly_movement_cap_points": self.movement_cap_points,
            "recent_form_weights": list(self.recent_form_weights),
            "blowout_treatment": self.blowout_treatment.as_dict(),
            "game_sd_points": self.game_sd_points,
            "sample_size_regularization": self.sample_size_regularization.as_dict(),
        }


def _resolve_weights(value: Any, regime_id: str) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise InputValidationError(
            f"Regime {regime_id}: recent_form_weights must be a non-empty list of weights."
        )
    if len(value) > RECENT_FORM_MAX_TERMS:
        raise InputValidationError(
            f"Regime {regime_id}: recent_form_weights has {len(value)} terms; the harness "
            f"admits at most {RECENT_FORM_MAX_TERMS}."
        )
    weights = tuple(
        _finite(w, f"Regime {regime_id}: recent_form_weights[{i}]") for i, w in enumerate(value)
    )
    if any(w < 0.0 for w in weights):
        raise InputValidationError(
            f"Regime {regime_id}: recent_form_weights must be non-negative."
        )
    if math.fsum(weights) <= 0.0:
        raise InputValidationError(
            f"Regime {regime_id}: recent_form_weights sum to zero, which erases recent form "
            "instead of weighting it."
        )
    return weights


def _resolve_blowout(value: Any, regime_id: str) -> BlowoutTreatment:
    if not isinstance(value, Mapping):
        raise InputValidationError(
            f"Regime {regime_id}: blowout_treatment must be an object naming a mode."
        )
    mode = str(value.get("mode", "")).strip().lower()
    if mode not in BLOWOUT_MODES:
        raise InputValidationError(
            f"Regime {regime_id}: blowout_treatment mode {mode!r} is not one of "
            f"{list(BLOWOUT_MODES)}."
        )
    if mode == "none":
        return BlowoutTreatment(mode=mode)
    if mode == "cap_margin":
        cap = _finite(value.get("cap_points"), f"Regime {regime_id}: blowout cap_points")
        if cap <= 0.0:
            raise InputValidationError(
                f"Regime {regime_id}: blowout cap_points must be positive."
            )
        return BlowoutTreatment(mode=mode, cap_points=cap)
    threshold = _finite(
        value.get("threshold_points"), f"Regime {regime_id}: blowout threshold_points"
    )
    exponent = _finite(value.get("exponent"), f"Regime {regime_id}: blowout exponent")
    if threshold <= 0.0:
        raise InputValidationError(
            f"Regime {regime_id}: blowout threshold_points must be positive."
        )
    if not (0.0 < exponent <= 1.0):
        raise InputValidationError(
            f"Regime {regime_id}: blowout exponent must lie in (0, 1]; {exponent} would make "
            "large margins count for more, not less."
        )
    return BlowoutTreatment(mode=mode, threshold_points=threshold, exponent=exponent)


def _resolve_regularization(value: Any, regime_id: str) -> SampleSizeRegularization:
    if not isinstance(value, Mapping):
        raise InputValidationError(
            f"Regime {regime_id}: sample_size_regularization must be an object naming a mode."
        )
    mode = str(value.get("mode", "")).strip().lower()
    if mode not in REGULARIZATION_MODES:
        raise InputValidationError(
            f"Regime {regime_id}: sample_size_regularization mode {mode!r} is not one of "
            f"{list(REGULARIZATION_MODES)}."
        )
    if mode == "none":
        return SampleSizeRegularization(mode=mode)
    prior_games = _finite(
        value.get("prior_games"), f"Regime {regime_id}: sample_size_regularization prior_games"
    )
    if prior_games < 0.0:
        raise InputValidationError(
            f"Regime {regime_id}: sample_size_regularization prior_games must be non-negative."
        )
    return SampleSizeRegularization(mode=mode, prior_games=prior_games)


def resolve_regime(regime: CandidateRegime) -> ResolvedRegime:
    """Validate a candidate regime into an executable one. All six axes required."""
    missing = [f for f in CALIBRATION_FIELDS if regime.values.get(f) is None]
    if missing:
        raise GovernanceBlock(
            f"Regime {regime.regime_id} does not state {missing}. A partial regime is completed "
            "by defaults the record never shows, so the harness refuses to score one."
        )
    values = regime.values
    coefficient = _in_band(
        _finite(
            values["weekly_performance_residual_coefficient"],
            f"Regime {regime.regime_id}: weekly_performance_residual_coefficient",
        ),
        RESIDUAL_COEFFICIENT_BAND,
        f"Regime {regime.regime_id}: weekly_performance_residual_coefficient",
    )
    cap = _in_band(
        _finite(
            values["weekly_movement_cap_points"],
            f"Regime {regime.regime_id}: weekly_movement_cap_points",
        ),
        MOVEMENT_CAP_BAND,
        f"Regime {regime.regime_id}: weekly_movement_cap_points",
    )
    game_sd = _in_band(
        _finite(values["game_sd_points"], f"Regime {regime.regime_id}: game_sd_points"),
        GAME_SD_BAND,
        f"Regime {regime.regime_id}: game_sd_points",
    )
    return ResolvedRegime(
        regime_id=regime.regime_id,
        residual_coefficient=coefficient,
        movement_cap_points=cap,
        recent_form_weights=_resolve_weights(values["recent_form_weights"], regime.regime_id),
        blowout_treatment=_resolve_blowout(values["blowout_treatment"], regime.regime_id),
        game_sd_points=game_sd,
        sample_size_regularization=_resolve_regularization(
            values["sample_size_regularization"], regime.regime_id
        ),
        rationale=regime.rationale,
    )


def resolve_regimes(regimes: Iterable[CandidateRegime]) -> list[ResolvedRegime]:
    resolved = [resolve_regime(r) for r in regimes]
    ids = [r.regime_id for r in resolved]
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        raise InputValidationError(
            f"Duplicate regime ids in the candidate set: {duplicates}. Results are keyed by "
            "regime id and would overwrite one another."
        )
    return resolved


def regime_grid(
    grid_id: str, axes: Mapping[str, Sequence[Any]], *, rationale: str = ""
) -> list[CandidateRegime]:
    """Build a deterministic full-factorial candidate set over the six axes.

    Every axis must be given at least one value by the caller. The harness
    authors no candidate numbers of its own, so an omitted axis is an error
    rather than an opportunity to supply a default.
    """
    missing = [f for f in CALIBRATION_FIELDS if not axes.get(f)]
    if missing:
        raise GovernanceBlock(
            f"Grid {grid_id} supplies no values for {missing}. The harness does not author "
            "candidate calibration values, so every axis must be given explicitly."
        )
    ordered_axes = [list(axes[field]) for field in CALIBRATION_FIELDS]
    out: list[CandidateRegime] = []
    for index, combination in enumerate(product(*ordered_axes)):
        values = dict(zip(CALIBRATION_FIELDS, combination))
        out.append(
            CandidateRegime(
                regime_id=f"{grid_id}-{index:04d}",
                values=values,
                rationale=rationale or f"Full-factorial cell {index} of grid {grid_id}",
            )
        )
    return out
