"""Deterministic candidate universe and staged search plan for V3 calibration.

The six calibration blockers cannot be closed by reasoning about coefficients.
They close by scoring candidates against governed observations. That scoring is
embarrassingly parallel, and the only thing standing between "we have data" and
"four workers are computing" is a candidate universe that every worker agrees on
without talking to any other worker.

This module is that agreement. It defines the universe once, gives every
parameter vector a content-addressed identity, and makes the universe splittable
by arithmetic rather than by coordination.

Four properties are load-bearing and each closes a specific way a parallel search
silently produces a wrong answer.

``candidate_id`` is content-addressed, not ordinal
    An ordinal index means the same parameter vector is candidate 4,117 in one
    run and candidate 3,902 in the next, because somebody widened an axis. Two
    shard files from either side of that edit then merge without complaint into a
    result table where one row's parameters are not the parameters that produced
    its metrics. Here the id is derived from the parameter vector's canonical
    serialization, so the id travels with the meaning: an edit that widens an
    axis changes which ids exist, and never what an existing id means.

The grid is defined once and distributed, never re-derived per worker
    :func:`shard_candidates` partitions by ``candidate_id % shard_count``. That
    only proves coverage if every worker enumerated the same universe, so a
    worker is handed a :class:`SearchSpace` and checks its
    :attr:`SearchSpace.config_sha` against what it was told to expect. A worker
    that built a different grid fails at startup rather than returning a shard of
    a universe nobody else searched.

``game_sd_points`` is not an axis
    It is a property of the residuals a mean model leaves behind, so it is
    estimated after the mean model is chosen and lives in
    :mod:`.calibration_scoring`. Putting it on the grid would let a candidate win
    by choosing the dispersion its own errors are scored against.

The ranges are predeclared and hash-bound, which is what makes them executable
    Every axis here carries :data:`EVIDENCE_PREDECLARED`: declared before any
    result existed, bound into the experiment digest, and broad enough that
    :func:`require_predeclared_breadth` accepts it. A research search runs under
    :func:`require_executable_ranges` and needs no governance ruling, because
    choosing which numbers to *try* and choosing which number becomes *canonical*
    are different acts and only the second needs an authority. The levels are
    wide and deliberately not centred on the prior 0.18/depth-6 result.

Nothing here promotes a value, writes canonical configuration, or retires a
blocker.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from .errors import GovernanceBlock, InputValidationError
from .textio import write_json_lf

__all__ = [
    "BLOWOUT_POLICY_IDS",
    "CANDIDATE_ID_BITS",
    "COARSE_SPACE_ID",
    "EVIDENCE_GOVERNED",
    "EVIDENCE_PENDING",
    "EVIDENCE_PREDECLARED",
    "EXECUTABLE_EVIDENCE_STATUSES",
    "FIXTURE_RANGE_AUTHORITY",
    "HISTORICAL_RESEARCH_CONTEXT",
    "MEAN_MODEL_FAMILIES",
    "MEAN_MODEL_STAGES",
    "MINIMUM_PREDECLARED_LEVELS",
    "PARAMETER_FAMILIES",
    "RECENT_FORM_SCHEMES",
    "REGULARIZATION_POLICY_IDS",
    "STAGES",
    "STAGE_COARSE",
    "STAGE_HOLDOUT",
    "STAGE_POINT_SCALE",
    "STAGE_REFINEMENT",
    "SUPPORTED_SHARD_COUNTS",
    "BlowoutPolicy",
    "CalibrationCandidate",
    "ExperimentPredeclaration",
    "HoldoutLedger",
    "RecentFormPolicy",
    "RegularizationPolicy",
    "SearchAxis",
    "SearchSpace",
    "assert_families_match_calibration",
    "boundary_report",
    "canonical_json",
    "coarse_space",
    "explicit_space",
    "holdout_space",
    "main",
    "plan_as_dict",
    "predeclare",
    "prove_shard_partition",
    "range_status",
    "refine_space",
    "require_executable_ranges",
    "require_predeclared_breadth",
    "require_range_authority",
    "shard_candidates",
    "shard_of",
    "space_for_stage",
]


# --- families ----------------------------------------------------------------

#: The six unresolved families, in canonical config order. Restated here rather
#: than imported so this module's own contract is readable without following a
#: reference; :func:`assert_families_match_calibration` proves the two agree.
PARAMETER_FAMILIES = (
    "weekly_performance_residual_coefficient",
    "weekly_movement_cap_points",
    "recent_form_weights",
    "blowout_treatment",
    "game_sd_points",
    "sample_size_regularization",
)

#: The five families that describe the *mean* model and are therefore searched.
#: ``game_sd_points`` is absent by design: see the module docstring and
#: :mod:`.calibration_scoring`.
MEAN_MODEL_FAMILIES = (
    "weekly_performance_residual_coefficient",
    "weekly_movement_cap_points",
    "recent_form_weights",
    "blowout_treatment",
    "sample_size_regularization",
)

#: The family estimated from out-of-sample residuals rather than enumerated.
DISPERSION_FAMILY = "game_sd_points"

#: Stage 0 identifies the historical point scale from Weeks 1-2 and lives in
#: :mod:`.calibration_stage0`. It is named here so the staged plan is readable in
#: one place, and it is kept out of :data:`MEAN_MODEL_STAGES` because its universe
#: is one experimental scale axis rather than a cross product of the five
#: mean-model families - a :class:`SearchSpace` is the wrong shape for it.
STAGE_POINT_SCALE = "point_scale"
STAGE_COARSE = "coarse"
STAGE_REFINEMENT = "refinement"
STAGE_HOLDOUT = "holdout"

#: Stages a :class:`SearchSpace` may carry.
MEAN_MODEL_STAGES = (STAGE_COARSE, STAGE_REFINEMENT, STAGE_HOLDOUT)

#: The whole staged plan, in execution order.
STAGES = (STAGE_POINT_SCALE, *MEAN_MODEL_STAGES)

SUPPORTED_SHARD_COUNTS = (1, 2, 4, 8)

#: Bits of the SHA-256 digest used as the candidate id. One bit is dropped so the
#: value is unambiguously non-negative in every language a downstream reader might
#: use, including those whose integers are signed 64-bit.
CANDIDATE_ID_BITS = 63

#: An axis nobody has declared. Enumerable and benchmarkable; never executable.
EVIDENCE_PENDING = "RANGE_PENDING_EVIDENCE"

#: An axis declared before any result was observed, bound into the experiment
#: configuration digest, and broad enough to test the surface rather than assert
#: an answer. This is the status a *research* search executes under.
#:
#: The correction this represents is worth stating plainly. Requiring a named
#: governance ruling before an experimental range may be explored confuses two
#: different acts: choosing which numbers to *try*, and choosing which number
#: becomes canonical. Only the second needs an authority. The first needs to be
#: honest, and honesty here is mechanical rather than procedural - see
#: :class:`ExperimentPredeclaration`.
EVIDENCE_PREDECLARED = "EXPERIMENT_PREDECLARED_AND_HASH_BOUND"

#: An axis whose range a named authority has fixed. Required only on the path
#: toward a canonical promotion, which remains separately governed.
EVIDENCE_GOVERNED = "RANGE_FIXED_BY_NAMED_AUTHORITY"

#: Statuses under which a real (non-fixture) search may run.
EXECUTABLE_EVIDENCE_STATUSES = (EVIDENCE_PREDECLARED, EVIDENCE_GOVERNED)

#: Distinct levels an ordered axis must carry before a predeclared range counts
#: as testing the parameter surface. A "range" of one point is a declaration of
#: the answer wearing a search's clothes.
MINIMUM_PREDECLARED_LEVELS = 3

#: The only range authority this module ships. It permits enumeration, sharding
#: and micro-benchmarking, and :func:`require_range_authority` refuses it for a
#: scoring run whose results could be cited.
FIXTURE_RANGE_AUTHORITY = "FIXTURE_NON_PROMOTING_BENCHMARK_ONLY"

COARSE_SPACE_ID = "V3-CAL-SEARCH-COARSE-001"

#: Recorded so the prior experiment is visible as context and unusable as an
#: anchor. Research output with three identification defects: its cap did not
#: bind, its depth optimum sat on the evidence boundary, and its corpus
#: provenance does not meet the current admission bar. The coarse axes below
#: deliberately do not centre on it.
HISTORICAL_RESEARCH_CONTEXT: dict[str, Any] = {
    "reported_best_coefficient": 0.18,
    "reported_best_depth": 6,
    "reported_best_scheme": "GEOMETRIC_0.6",
    "reported_best_cap_points": 6.0,
    "reported_best_regularization": "NONE",
    "reported_best_blowout": "NO_SPECIAL_TREATMENT",
    "reported_validation_rmse": 18.5156,
    "status": "HISTORICAL_RESEARCH_CONTEXT_NOT_EVIDENCE",
    "identification_defects": [
        "movement cap did not bind, so its value is not identified",
        "depth optimum sat on the search boundary, so it is not identified",
        "corpus provenance does not satisfy the current admission contract",
    ],
    "usable_as_anchor": False,
    "usable_as_prior": False,
}


def assert_families_match_calibration() -> None:
    """Prove this module's family list is the governed one, not a copy that drifted."""
    from . import calibration as cal

    if tuple(PARAMETER_FAMILIES) != tuple(cal.CALIBRATION_FIELDS):
        raise GovernanceBlock(
            "Search families have drifted from calibration.CALIBRATION_FIELDS: "
            f"{list(PARAMETER_FAMILIES)} vs {list(cal.CALIBRATION_FIELDS)}"
        )
    if DISPERSION_FAMILY in MEAN_MODEL_FAMILIES:
        raise GovernanceBlock(
            f"{DISPERSION_FAMILY} must not be a searched axis; it is estimated from "
            "out-of-sample residuals of the selected mean model."
        )


# --- canonical serialization -------------------------------------------------


def _canonical_float(value: float) -> str:
    """Round-trip-exact, platform-stable text for a float.

    ``repr`` is used rather than a fixed format because CPython's float repr is
    the shortest string that round-trips to the same double, and it is the same
    string on every platform. A fixed ``%.6f`` would map 0.1000001 and 0.1 to one
    id, which is the one thing a content-addressed identity may never do.
    """
    number = float(value)
    if not math.isfinite(number):
        raise InputValidationError(
            f"Candidate parameters must be finite; got {value!r}. A non-finite level "
            "has no stable serialization and would produce an unreproducible id."
        )
    return repr(number)


def canonical_json(payload: Any) -> str:
    """Deterministic JSON: sorted keys, no incidental whitespace, LF-safe.

    Floats are wrapped and pre-rendered through :func:`_canonical_float` so the
    serialization does not depend on ``json``'s own float formatting, and so an
    integer-valued float never collapses onto the integer that happens to equal
    it: ``6.0`` and ``6`` are different levels of different families and must not
    hash alike.
    """

    def convert(node: Any) -> Any:
        if node is None or isinstance(node, (bool, int, str)):
            return node
        if isinstance(node, float):
            return {"__f__": _canonical_float(node)}
        if isinstance(node, dict):
            return {
                str(k): convert(v) for k, v in sorted(node.items(), key=lambda kv: str(kv[0]))
            }
        if isinstance(node, (list, tuple)):
            return [convert(v) for v in node]
        if hasattr(node, "as_dict"):
            return convert(node.as_dict())
        raise InputValidationError(f"Cannot canonically serialize {type(node).__name__}")

    return json.dumps(convert(payload), sort_keys=True, separators=(",", ":"))


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- policies ----------------------------------------------------------------

BLOWOUT_NONE = "NO_SPECIAL_TREATMENT"
BLOWOUT_RESIDUAL_CLIP = "RESIDUAL_CLIP"
BLOWOUT_SMOOTH_SATURATION = "SMOOTH_SATURATION"
BLOWOUT_POLICY_IDS = (BLOWOUT_NONE, BLOWOUT_RESIDUAL_CLIP, BLOWOUT_SMOOTH_SATURATION)


@dataclass(frozen=True)
class BlowoutPolicy:
    """An explicit, serializable blowout policy.

    Blowout handling is represented as a named policy rather than a clip buried in
    the update step, because the two are indistinguishable in results and entirely
    different in review: a policy appears in the candidate id, in the shard table
    and in the audit record, whereas a magic number inside an update function is
    invisible to all three. No policy here is canonical; all three are candidates.
    """

    policy_id: str
    threshold_points: float | None = None

    def __post_init__(self) -> None:
        if self.policy_id not in BLOWOUT_POLICY_IDS:
            raise InputValidationError(
                f"Unknown blowout policy {self.policy_id!r}; expected one of "
                f"{list(BLOWOUT_POLICY_IDS)}. Blowout treatment is an explicit policy, "
                "so an unrecognised one is refused rather than treated as no treatment."
            )
        if self.policy_id == BLOWOUT_NONE:
            if self.threshold_points is not None:
                raise InputValidationError(
                    f"{BLOWOUT_NONE} takes no threshold; got {self.threshold_points!r}."
                )
        elif self.threshold_points is None or float(self.threshold_points) <= 0:
            raise InputValidationError(
                f"Blowout policy {self.policy_id} requires a positive threshold in "
                f"points; got {self.threshold_points!r}."
            )

    def apply(self, residual: float) -> float:
        """Map a raw residual through the policy. Pure and total."""
        if self.policy_id == BLOWOUT_NONE:
            return float(residual)
        threshold = float(self.threshold_points or 0.0)
        if self.policy_id == BLOWOUT_RESIDUAL_CLIP:
            return max(-threshold, min(threshold, float(residual)))
        return threshold * math.tanh(float(residual) / threshold)

    def as_dict(self) -> dict[str, Any]:
        return {"policy_id": self.policy_id, "threshold_points": self.threshold_points}

    @property
    def label(self) -> str:
        if self.threshold_points is None:
            return self.policy_id
        return f"{self.policy_id}@{_canonical_float(self.threshold_points)}"


RECENT_FORM_UNIFORM = "UNIFORM"
RECENT_FORM_GEOMETRIC = "GEOMETRIC"
RECENT_FORM_LINEAR = "LINEAR"
RECENT_FORM_SCHEMES = (RECENT_FORM_UNIFORM, RECENT_FORM_GEOMETRIC, RECENT_FORM_LINEAR)


@dataclass(frozen=True)
class RecentFormPolicy:
    """How much of the current rating each recent update is allowed to explain.

    Depth and decay are held together in one policy because they are not separable
    parameters: geometric decay 0.9 over depth 2 and decay 0.5 over depth 8 are
    nearly the same weighting, and searching them as independent axes reports two
    findings where there is one.
    """

    scheme: str
    depth: int
    decay: float | None = None

    def __post_init__(self) -> None:
        if self.scheme not in RECENT_FORM_SCHEMES:
            raise InputValidationError(
                f"Unknown recent-form scheme {self.scheme!r}; expected one of "
                f"{list(RECENT_FORM_SCHEMES)}."
            )
        if int(self.depth) < 1:
            raise InputValidationError(f"Recent-form depth must be >= 1; got {self.depth}")
        if self.scheme == RECENT_FORM_GEOMETRIC:
            if self.decay is None or not 0.0 < float(self.decay) < 1.0:
                raise InputValidationError(
                    f"{RECENT_FORM_GEOMETRIC} requires 0 < decay < 1; got {self.decay!r}."
                )
        elif self.decay is not None:
            raise InputValidationError(
                f"Recent-form scheme {self.scheme} takes no decay; got {self.decay!r}."
            )

    def weights(self) -> tuple[float, ...]:
        """Normalized weights, index 0 being the most recent update."""
        if self.scheme == RECENT_FORM_UNIFORM:
            raw = [1.0] * int(self.depth)
        elif self.scheme == RECENT_FORM_GEOMETRIC:
            decay = float(self.decay or 0.0)
            raw = [decay**i for i in range(int(self.depth))]
        else:
            raw = [float(int(self.depth) - i) for i in range(int(self.depth))]
        total = sum(raw)
        return tuple(w / total for w in raw)

    def effective_contributions(self, history_length: int) -> tuple[float, ...]:
        """Weight actually carried by each of the last ``history_length`` updates.

        R13 of the lane instruction asks for the effective contribution of each
        historical update to current state. A depth that exceeds the available
        history contributes nothing beyond it rather than silently re-normalizing
        onto a shorter window: re-normalizing would make a deep policy behave like
        a shallow one early in a season and hide the depth being tested.
        """
        if history_length < 0:
            raise InputValidationError(f"history_length must be >= 0; got {history_length}")
        return self.weights()[: min(history_length, int(self.depth))]

    @property
    def tail_mass(self) -> float:
        """Weight on the oldest update inside the window.

        A depth optimum on the search boundary matters only if the boundary update
        still carries mass. Reported so a ``BOUNDARY_OPTIMUM`` mark can be read as
        "the window wants to be wider" rather than as a bare warning.
        """
        return self.weights()[-1]

    def as_dict(self) -> dict[str, Any]:
        return {"scheme": self.scheme, "depth": int(self.depth), "decay": self.decay}

    @property
    def label(self) -> str:
        if self.decay is None:
            return f"{self.scheme}_d{int(self.depth)}"
        return f"{self.scheme}_{_canonical_float(self.decay)}_d{int(self.depth)}"


REGULARIZATION_NONE = "NONE"
REGULARIZATION_GAMES_PLAYED_SHRINKAGE = "GAMES_PLAYED_SHRINKAGE"
REGULARIZATION_POLICY_IDS = (REGULARIZATION_NONE, REGULARIZATION_GAMES_PLAYED_SHRINKAGE)


@dataclass(frozen=True)
class RegularizationPolicy:
    """Sample-size regularization, stated rather than implied.

    A shrinkage that lives in the update step as ``n / (n + 3)`` is regularization
    nobody voted for. Here the schedule is a policy with an id and a parameter, and
    :meth:`report` emits the early- and late-season amounts the lane instruction
    asks to see, so "no implicit regularization" is checkable rather than claimed.
    """

    policy_id: str
    prior_games: float | None = None

    def __post_init__(self) -> None:
        if self.policy_id not in REGULARIZATION_POLICY_IDS:
            raise InputValidationError(
                f"Unknown regularization policy {self.policy_id!r}; expected one of "
                f"{list(REGULARIZATION_POLICY_IDS)}."
            )
        if self.policy_id == REGULARIZATION_NONE:
            if self.prior_games is not None:
                raise InputValidationError(
                    f"{REGULARIZATION_NONE} takes no prior_games; got {self.prior_games!r}."
                )
        elif self.prior_games is None or float(self.prior_games) <= 0:
            raise InputValidationError(
                f"{self.policy_id} requires positive prior_games; got {self.prior_games!r}."
            )

    def shrinkage(self, games_played: int) -> float:
        """Fraction of the raw update that survives at this sample size."""
        if games_played < 0:
            raise InputValidationError(f"games_played must be >= 0; got {games_played}")
        if self.policy_id == REGULARIZATION_NONE:
            return 1.0
        prior = float(self.prior_games or 0.0)
        return float(games_played) / (float(games_played) + prior)

    def effective_sample_count(self, games_played: int) -> float:
        """Observations the update behaves as though it had."""
        if self.policy_id == REGULARIZATION_NONE:
            return float(games_played)
        return float(games_played) + float(self.prior_games or 0.0)

    def regularization_amount(self, games_played: int) -> float:
        """Fraction of the raw update withheld at this sample size."""
        return 1.0 - self.shrinkage(games_played)

    def report(self, *, early_games: int = 1, late_games: int = 11) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "prior_games": self.prior_games,
            "early_season_games": early_games,
            "early_season_regularization_amount": self.regularization_amount(early_games),
            "early_season_effective_sample_count": self.effective_sample_count(early_games),
            "late_season_games": late_games,
            "late_season_regularization_amount": self.regularization_amount(late_games),
            "late_season_effective_sample_count": self.effective_sample_count(late_games),
        }

    def as_dict(self) -> dict[str, Any]:
        return {"policy_id": self.policy_id, "prior_games": self.prior_games}

    @property
    def label(self) -> str:
        if self.prior_games is None:
            return self.policy_id
        return f"{self.policy_id}@{_canonical_float(self.prior_games)}"


# --- candidate ---------------------------------------------------------------


@dataclass(frozen=True)
class CalibrationCandidate:
    """One fully specified mean-model parameter vector.

    Frozen and content-addressed: :attr:`candidate_id` is a function of the vector
    alone, so the same parameters produce the same id in every stage, every shard
    and every run, and two shard files can be merged on it safely.
    """

    coefficient: float
    movement_cap_points: float
    recent_form: RecentFormPolicy
    blowout: BlowoutPolicy
    regularization: RegularizationPolicy

    def __post_init__(self) -> None:
        for name in ("coefficient", "movement_cap_points"):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise InputValidationError(f"Candidate {name} must be finite; got {value!r}")
        if float(self.movement_cap_points) <= 0:
            raise InputValidationError(
                f"movement_cap_points must be positive; got {self.movement_cap_points!r}. "
                "An absent cap is expressed as a level wide enough never to bind, which "
                "the cap-identification report then marks as unidentified rather than "
                "letting 'no cap' hide as a missing value."
            )

    def parameter_vector(self) -> dict[str, Any]:
        """The vector in governed family names, for serialization and reporting."""
        return {
            "weekly_performance_residual_coefficient": float(self.coefficient),
            "weekly_movement_cap_points": float(self.movement_cap_points),
            "recent_form_weights": self.recent_form.as_dict(),
            "blowout_treatment": self.blowout.as_dict(),
            "sample_size_regularization": self.regularization.as_dict(),
        }

    @property
    def canonical_serialization(self) -> str:
        return canonical_json(self.parameter_vector())

    @property
    def candidate_key(self) -> str:
        """Full SHA-256 of the canonical serialization. The auditable identity."""
        return _digest(self.canonical_serialization)

    @property
    def candidate_id(self) -> int:
        """Non-negative integer identity, derived from :attr:`candidate_key`.

        Shard assignment is ``candidate_id % shard_count``. Because the id comes
        from a digest rather than an enumeration order, that modulus distributes
        evenly without anybody choosing an ordering, and it keeps distributing
        evenly when an axis is widened.
        """
        raw = int.from_bytes(bytes.fromhex(self.candidate_key)[:8], "big")
        return raw >> (64 - CANDIDATE_ID_BITS)

    @property
    def label(self) -> str:
        return "|".join(
            (
                f"coef={_canonical_float(self.coefficient)}",
                f"cap={_canonical_float(self.movement_cap_points)}",
                self.recent_form.label,
                self.blowout.label,
                self.regularization.label,
            )
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_key": self.candidate_key,
            "label": self.label,
            "parameters": self.parameter_vector(),
        }


# --- search space ------------------------------------------------------------


@dataclass(frozen=True)
class SearchAxis:
    """One family's enumerated levels, with the status of those levels attached."""

    family: str
    levels: tuple[Any, ...]
    evidence_status: str
    boundary_expandable: bool
    rationale: str

    def __post_init__(self) -> None:
        if self.family not in MEAN_MODEL_FAMILIES:
            raise InputValidationError(
                f"Axis family {self.family!r} is not a searched mean-model family "
                f"{list(MEAN_MODEL_FAMILIES)}."
            )
        if not self.levels:
            raise InputValidationError(f"Axis {self.family} declares no levels.")
        if self.evidence_status not in (
            EVIDENCE_PENDING,
            EVIDENCE_PREDECLARED,
            EVIDENCE_GOVERNED,
        ):
            raise InputValidationError(
                f"Axis {self.family} has unknown evidence status {self.evidence_status!r}."
            )
        serialized = [canonical_json(level) for level in self.levels]
        duplicates = sorted({s for s in serialized if serialized.count(s) > 1})
        if duplicates:
            raise InputValidationError(
                f"Axis {self.family} repeats levels {duplicates}. A repeated level makes "
                "the universe smaller than its declared size, so the shard-completeness "
                "proof would be comparing a set against a longer list of itself."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "levels": [
                level.as_dict() if hasattr(level, "as_dict") else level for level in self.levels
            ],
            "level_count": len(self.levels),
            "evidence_status": self.evidence_status,
            "boundary_expandable": self.boundary_expandable,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class SearchSpace:
    """The candidate universe for one stage, defined once and shipped to workers."""

    space_id: str
    stage: str
    axes: tuple[SearchAxis, ...]
    range_authority: str | None = None
    parent_config_sha: str | None = None
    #: Present only for the holdout stage, whose universe is an explicit shortlist
    #: rather than a cross product.
    explicit_candidates: tuple[CalibrationCandidate, ...] = ()

    def __post_init__(self) -> None:
        if self.stage not in MEAN_MODEL_STAGES:
            raise InputValidationError(
                f"Unknown stage {self.stage!r} for a mean-model search space; expected "
                f"one of {list(MEAN_MODEL_STAGES)}. Stage 0 ({STAGE_POINT_SCALE}) has a "
                "single experimental scale axis and is built by calibration_stage0."
            )
        if self.explicit_candidates:
            if self.axes:
                raise InputValidationError(
                    "A space may be a cross product or an explicit shortlist, not both."
                )
            return
        families = [axis.family for axis in self.axes]
        missing = [f for f in MEAN_MODEL_FAMILIES if f not in families]
        if missing:
            raise InputValidationError(
                f"Space {self.space_id} does not span every mean-model family; missing "
                f"{missing}. A partially specified candidate is not a candidate."
            )
        if len(set(families)) != len(families):
            raise InputValidationError(f"Space {self.space_id} declares a family twice.")

    def axis(self, family: str) -> SearchAxis:
        for candidate_axis in self.axes:
            if candidate_axis.family == family:
                return candidate_axis
        raise InputValidationError(f"Space {self.space_id} has no axis for {family!r}")

    @property
    def size(self) -> int:
        if self.explicit_candidates:
            return len(self.explicit_candidates)
        total = 1
        for candidate_axis in self.axes:
            total *= len(candidate_axis.levels)
        return total

    def enumerate(self) -> tuple[CalibrationCandidate, ...]:
        """The whole universe, in one fixed order, with id collisions refused.

        Enumeration order is the nested loop over families in
        :data:`MEAN_MODEL_FAMILIES` order. Workers do not depend on that order —
        they shard by id — but the aggregator compares an expected id set against a
        received one, and a stable order makes the two comparable by construction.
        """
        if self.explicit_candidates:
            candidates: tuple[CalibrationCandidate, ...] = tuple(self.explicit_candidates)
        else:
            coefficients = self.axis("weekly_performance_residual_coefficient").levels
            caps = self.axis("weekly_movement_cap_points").levels
            forms = self.axis("recent_form_weights").levels
            blowouts = self.axis("blowout_treatment").levels
            regularizations = self.axis("sample_size_regularization").levels
            built: list[CalibrationCandidate] = []
            for coefficient in coefficients:
                for cap in caps:
                    for form in forms:
                        for blowout in blowouts:
                            for regularization in regularizations:
                                built.append(
                                    CalibrationCandidate(
                                        coefficient=float(coefficient),
                                        movement_cap_points=float(cap),
                                        recent_form=form,
                                        blowout=blowout,
                                        regularization=regularization,
                                    )
                                )
            candidates = tuple(built)

        seen: dict[int, str] = {}
        for candidate in candidates:
            key = candidate.candidate_key
            previous = seen.get(candidate.candidate_id)
            if previous is not None and previous != key:
                raise GovernanceBlock(
                    f"Candidate id collision in space {self.space_id}: {previous} and "
                    f"{key} both map to id {candidate.candidate_id}. Sharding by id would "
                    "silently drop one of them, so the universe is refused."
                )
            seen[candidate.candidate_id] = key
        return candidates

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "stage": self.stage,
            "axes": [a.as_dict() for a in self.axes],
            "explicit_candidates": [c.as_dict() for c in self.explicit_candidates],
            "range_authority": self.range_authority,
            "parent_config_sha": self.parent_config_sha,
            "mean_model_families": list(MEAN_MODEL_FAMILIES),
            "dispersion_family_not_searched": DISPERSION_FAMILY,
            "size": self.size,
        }

    @property
    def config_sha(self) -> str:
        """Digest of the space definition. The thing every worker must agree on.

        ``size`` is included even though it is derivable: a reader that cannot
        fully parse a space should still fail on the digest rather than proceed
        with a universe of a different size.
        """
        return _digest(canonical_json(self.as_dict()))


@dataclass(frozen=True)
class ExperimentPredeclaration:
    """A range declaration made before any result existed, bound to a digest.

    This is what replaces "a named authority must first rule on the ranges" for a
    *research* search. The substitution is only worth making if predeclaration is
    mechanical rather than a promise, so three things carry the weight:

    ``config_sha`` covers every axis and every level
        Narrowing a range after seeing the table changes the digest. The narrowed
        run is therefore visibly a different experiment rather than the same one
        reported differently, and the aggregate record cites the declaration it
        was run under. Nobody has to be trusted not to peek; peeking leaves a
        mark.

    Breadth is checked, not asserted
        :func:`require_predeclared_breadth` refuses an ordered axis carrying fewer
        than :data:`MINIMUM_PREDECLARED_LEVELS` distinct levels, or one with no
        spread at all. A one-point "range" would satisfy every other condition
        here while being a declaration of the answer wearing a search's clothes.

    The obligations travel with the declaration
        Boundary optima must expand rather than conclude, the holdout stays sealed
        until its designated evaluation, and nothing promotes automatically. They
        are recorded on the declaration so an aggregate can be checked against
        what was promised rather than against what a reader assumes.

    None of this confers promotion authority. Canonical promotion stays governed
    by :func:`calibration.promote_regime_r2` and its human approval token.
    """

    experiment_id: str
    config_sha: str
    stage: str
    declared_scored_split: str
    declared_before_results: bool = True

    def __post_init__(self) -> None:
        if not self.experiment_id.strip():
            raise InputValidationError("A predeclaration must name its experiment.")
        if not self.declared_before_results:
            raise GovernanceBlock(
                f"Predeclaration {self.experiment_id} does not claim to precede its "
                "results. A range declared after the table is not a predeclaration; it "
                "is a description of the winner."
            )
        if self.declared_scored_split.strip().lower() == "holdout":
            raise GovernanceBlock(
                f"Predeclaration {self.experiment_id} nominates the holdout as its "
                "scored split. Ranges may never be selected against the holdout; its "
                "single use is reserved for final evaluation."
            )

    @property
    def obligations(self) -> dict[str, Any]:
        return {
            "boundary_optimum_must_expand": True,
            "holdout_sealed_until_final_evaluation": True,
            "automatic_promotion": False,
            "confers_promotion_authority": False,
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "config_sha": self.config_sha,
            "stage": self.stage,
            "declared_scored_split": self.declared_scored_split,
            "declared_before_results": self.declared_before_results,
            "range_status": EVIDENCE_PREDECLARED,
            "obligations": self.obligations,
        }

    @property
    def predeclaration_sha(self) -> str:
        return _digest(canonical_json(self.as_dict()))


def _ordered_levels(axis: SearchAxis) -> list[float]:
    """The distinct positions of an ordered axis, as comparable numbers."""
    if axis.family == "recent_form_weights":
        return sorted({float(level.depth) for level in axis.levels})
    if axis.family == "sample_size_regularization":
        return sorted({float(level.prior_games or 0.0) for level in axis.levels})
    return sorted({float(level) for level in axis.levels})


def require_predeclared_breadth(space: SearchSpace) -> dict[str, Any]:
    """Refuse a declared range too narrow to have tested anything.

    Applied to ordered families only. ``blowout_treatment`` is exempt because its
    levels are shapes rather than points on a ladder, and counting the shapes
    somebody happened to write down would measure vocabulary, not breadth.
    """
    if space.explicit_candidates:
        return {
            "checked_families": [],
            "broad_enough": True,
            "reason": "An explicit shortlist is not a range and has no breadth to test.",
        }
    narrow: list[str] = []
    detail: dict[str, Any] = {}
    for family in ORDERED_FAMILIES:
        levels = _ordered_levels(space.axis(family))
        detail[family] = {
            "distinct_levels": len(levels),
            "minimum": levels[0],
            "maximum": levels[-1],
        }
        if len(levels) < MINIMUM_PREDECLARED_LEVELS or levels[-1] <= levels[0]:
            narrow.append(family)
    if narrow:
        raise GovernanceBlock(
            f"Space {space.space_id} declares ranges too narrow to test the parameter "
            f"surface on: {narrow}. Each ordered family needs at least "
            f"{MINIMUM_PREDECLARED_LEVELS} distinct levels with real spread; a range of "
            "one point is a declaration of the answer, not a search for it."
        )
    return {
        "checked_families": list(ORDERED_FAMILIES),
        "families": detail,
        "broad_enough": True,
    }


def predeclare(
    space: SearchSpace,
    *,
    experiment_id: str,
    scored_split: str = "validation",
) -> ExperimentPredeclaration:
    """Bind a space's ranges to a digest, after proving they are broad enough."""
    require_predeclared_breadth(space)
    undeclared = [
        a.family
        for a in space.axes
        if a.evidence_status not in EXECUTABLE_EVIDENCE_STATUSES
    ]
    if undeclared:
        raise GovernanceBlock(
            f"Space {space.space_id} cannot be predeclared while these axes are still "
            f"{EVIDENCE_PENDING}: {undeclared}."
        )
    return ExperimentPredeclaration(
        experiment_id=experiment_id,
        config_sha=space.config_sha,
        stage=space.stage,
        declared_scored_split=scored_split.strip().lower(),
    )


def range_status(space: SearchSpace) -> str:
    """The weakest status any axis of this space carries."""
    statuses = {a.evidence_status for a in space.axes}
    if not statuses:
        return EVIDENCE_PREDECLARED
    if EVIDENCE_PENDING in statuses:
        return EVIDENCE_PENDING
    if EVIDENCE_PREDECLARED in statuses:
        return EVIDENCE_PREDECLARED
    return EVIDENCE_GOVERNED


def require_executable_ranges(
    space: SearchSpace, *, predeclaration: ExperimentPredeclaration | None = None
) -> dict[str, Any]:
    """The gate a *research* search passes through. Two admissible paths.

    A named governance ruling fixing the ranges is one of them, and it is not
    required. Exploring an experimental parameter range is not an act that needs
    an authority; promoting a value out of one is, and that gate lives elsewhere
    and is untouched by this.

    The fixture authority is refused on both paths. It exists so the harness can
    be enumerated, sharded and benchmarked before any evidence arrives, and the
    one thing it must never do is let a benchmark result be read as a search
    result.
    """
    if space.range_authority == FIXTURE_RANGE_AUTHORITY:
        raise GovernanceBlock(
            f"Search space {space.space_id} is marked {FIXTURE_RANGE_AUTHORITY}. That "
            "permits enumeration, sharding and micro-benchmarking and never a scoring "
            "run whose results are read as evidence about a parameter."
        )
    status = range_status(space)
    if status == EVIDENCE_PENDING:
        pending = [a.family for a in space.axes if a.evidence_status == EVIDENCE_PENDING]
        raise GovernanceBlock(
            f"Space {space.space_id} has undeclared axes {pending}. A research search "
            f"needs ranges that are {EVIDENCE_PREDECLARED}: declared before results, "
            "bound into the experiment digest, and broad enough to test the surface."
        )
    if status == EVIDENCE_GOVERNED:
        return {
            "range_status": EVIDENCE_GOVERNED,
            "path": "NAMED_GOVERNANCE_AUTHORITY",
            "range_authority": space.range_authority,
            "ruling_required": False,
            "confers_promotion_authority": False,
        }
    if predeclaration is None:
        raise GovernanceBlock(
            f"Space {space.space_id} declares {EVIDENCE_PREDECLARED} ranges but no "
            "predeclaration was supplied. The digest binding is what makes 'declared "
            "before results' checkable, so the declaration has to be present."
        )
    if predeclaration.config_sha != space.config_sha:
        raise GovernanceBlock(
            f"Predeclaration {predeclaration.experiment_id} binds config "
            f"{predeclaration.config_sha} but this space digests to {space.config_sha}. "
            "The ranges being searched are not the ranges that were declared."
        )
    require_predeclared_breadth(space)
    return {
        "range_status": EVIDENCE_PREDECLARED,
        "path": EVIDENCE_PREDECLARED,
        "experiment_id": predeclaration.experiment_id,
        "predeclaration_sha": predeclaration.predeclaration_sha,
        "ruling_required": False,
        "confers_promotion_authority": False,
        "obligations": predeclaration.obligations,
    }


def require_range_authority(space: SearchSpace) -> str:
    """The promotion-grade gate: a named authority has fixed these ranges.

    Kept, and deliberately no longer on the research path. Reaching a canonical
    promotion still requires this; running an experiment does not.
    :func:`require_executable_ranges` is what a worker calls.
    """
    if space.range_authority is None:
        raise GovernanceBlock(
            f"Search space {space.space_id} carries no named range authority. A "
            "research search does not need one - see require_executable_ranges - but a "
            "promotion citing these ranges does."
        )
    if space.range_authority == FIXTURE_RANGE_AUTHORITY:
        raise GovernanceBlock(
            f"Search space {space.space_id} is authorised only as "
            f"{FIXTURE_RANGE_AUTHORITY}, which is never a promotion authority."
        )
    ungoverned = [a.family for a in space.axes if a.evidence_status != EVIDENCE_GOVERNED]
    if ungoverned:
        raise GovernanceBlock(
            f"Space {space.space_id} names authority {space.range_authority} but these "
            f"axes are not {EVIDENCE_GOVERNED}: {ungoverned}."
        )
    return space.range_authority


# --- the coarse space --------------------------------------------------------


def coarse_space(*, range_authority: str | None = None) -> SearchSpace:
    """Stage 1. Broad, cheap, and deliberately not centred on the prior result.

    Every level is :data:`EVIDENCE_PREDECLARED`: fixed in source before any result
    existed, bound into :attr:`SearchSpace.config_sha`, and broad enough to pass
    :func:`require_predeclared_breadth`. That is what makes this executable as
    research without a named governance ruling - and it confers nothing toward a
    canonical promotion, which stays separately governed.

    The widths are chosen for a property the search needs rather than for a belief
    about the answer: wide enough that a winner in the interior is a finding, and
    coarse enough that Stage 1 spends its compute locating regions instead of
    resolving a third decimal place that Stage 2 will resolve anyway.

    Two levels are present specifically to be *falsified*. The 16-point cap is
    wide enough that it should never bind, so a search that ranks it first is
    reporting a tie-break rather than a discovery, and
    :func:`calibration_aggregate.cap_identification` will say so. The deepest
    recent-form levels sit at the top of their ladder, so a winner there is marked
    ``BOUNDARY_OPTIMUM`` and Stage 2 widens rather than concludes.
    """
    return SearchSpace(
        space_id=COARSE_SPACE_ID,
        stage=STAGE_COARSE,
        range_authority=range_authority,
        axes=(
            SearchAxis(
                family="weekly_performance_residual_coefficient",
                levels=(0.05, 0.15, 0.25, 0.35, 0.45),
                evidence_status=EVIDENCE_PREDECLARED,
                boundary_expandable=True,
                rationale=(
                    "Spans near-inert to strongly reactive on a 0.10 step. Not centred "
                    "on the prior 0.18: that value's corpus is inadmissible, so "
                    "anchoring on it would import the provenance defect as a prior."
                ),
            ),
            SearchAxis(
                family="weekly_movement_cap_points",
                levels=(2.0, 4.0, 8.0, 16.0),
                evidence_status=EVIDENCE_PREDECLARED,
                boundary_expandable=True,
                rationale=(
                    "Doubling ladder. 16.0 is included as a non-binding control: if it "
                    "ranks first, the cap family is unidentified on this corpus, which "
                    "is a result worth measuring rather than a level worth omitting."
                ),
            ),
            SearchAxis(
                family="recent_form_weights",
                levels=(
                    RecentFormPolicy(RECENT_FORM_UNIFORM, 2),
                    RecentFormPolicy(RECENT_FORM_UNIFORM, 4),
                    RecentFormPolicy(RECENT_FORM_UNIFORM, 6),
                    RecentFormPolicy(RECENT_FORM_GEOMETRIC, 4, 0.5),
                    RecentFormPolicy(RECENT_FORM_GEOMETRIC, 4, 0.7),
                    RecentFormPolicy(RECENT_FORM_GEOMETRIC, 4, 0.9),
                    RecentFormPolicy(RECENT_FORM_GEOMETRIC, 8, 0.5),
                    RecentFormPolicy(RECENT_FORM_GEOMETRIC, 8, 0.7),
                    RecentFormPolicy(RECENT_FORM_GEOMETRIC, 8, 0.9),
                ),
                evidence_status=EVIDENCE_PREDECLARED,
                boundary_expandable=True,
                rationale=(
                    "Depth and decay travel together because they are not separable: "
                    "decay 0.9 over depth 2 and decay 0.5 over depth 8 are nearly one "
                    "weighting. Deepest levels sit at the ladder top so a boundary "
                    "optimum is detectable, which the prior experiment could not do."
                ),
            ),
            SearchAxis(
                family="blowout_treatment",
                levels=(
                    BlowoutPolicy(BLOWOUT_NONE),
                    BlowoutPolicy(BLOWOUT_RESIDUAL_CLIP, 21.0),
                    BlowoutPolicy(BLOWOUT_RESIDUAL_CLIP, 28.0),
                    BlowoutPolicy(BLOWOUT_SMOOTH_SATURATION, 24.0),
                ),
                evidence_status=EVIDENCE_PREDECLARED,
                boundary_expandable=False,
                rationale=(
                    "Two shapes plus the null policy. Thresholds are placeholders; the "
                    "shapes are the question, since a hard clip and a smooth saturation "
                    "differ in what they do to the residual distribution's tail."
                ),
            ),
            SearchAxis(
                family="sample_size_regularization",
                levels=(
                    RegularizationPolicy(REGULARIZATION_NONE),
                    RegularizationPolicy(REGULARIZATION_GAMES_PLAYED_SHRINKAGE, 2.0),
                    RegularizationPolicy(REGULARIZATION_GAMES_PLAYED_SHRINKAGE, 5.0),
                ),
                evidence_status=EVIDENCE_PREDECLARED,
                boundary_expandable=True,
                rationale=(
                    "The null policy competes explicitly, so 'no regularization' is a "
                    "measured outcome rather than the default nobody tested."
                ),
            ),
        ),
    )


def explicit_space(
    candidates: Sequence[CalibrationCandidate],
    *,
    space_id: str,
    stage: str,
    range_authority: str | None = None,
    parent_config_sha: str | None = None,
) -> SearchSpace:
    """A space whose universe is a named list rather than a cross product."""
    if not candidates:
        raise InputValidationError(f"Explicit space {space_id} carries no candidates.")
    return SearchSpace(
        space_id=space_id,
        stage=stage,
        axes=(),
        range_authority=range_authority,
        parent_config_sha=parent_config_sha,
        explicit_candidates=tuple(candidates),
    )


# --- sharding ----------------------------------------------------------------


def _require_shard_arguments(shard_count: int, shard_index: int) -> None:
    if shard_count not in SUPPORTED_SHARD_COUNTS:
        raise InputValidationError(
            f"shard_count {shard_count} is not supported; expected one of "
            f"{list(SUPPORTED_SHARD_COUNTS)}."
        )
    if not 0 <= shard_index < shard_count:
        raise InputValidationError(f"shard_index {shard_index} outside [0, {shard_count}).")


def shard_of(candidate_id: int, shard_count: int) -> int:
    """Which shard owns a candidate. Pure arithmetic, no coordination."""
    if shard_count < 1:
        raise InputValidationError(f"shard_count must be >= 1; got {shard_count}")
    return int(candidate_id) % int(shard_count)


def shard_candidates(
    candidates: Sequence[CalibrationCandidate], shard_count: int, shard_index: int
) -> tuple[CalibrationCandidate, ...]:
    """The subset of the universe this worker owns."""
    _require_shard_arguments(shard_count, shard_index)
    return tuple(
        c for c in candidates if shard_of(c.candidate_id, shard_count) == shard_index
    )


def prove_shard_partition(
    candidates: Sequence[CalibrationCandidate], shard_count: int
) -> dict[str, Any]:
    """Prove the shards reconstruct the universe exactly.

    Returned rather than asserted so the proof can be written into the run record:
    a claim that four shards covered the universe is worth exactly as much as the
    numbers behind it, and those numbers belong in the artifact.
    """
    _require_shard_arguments(shard_count, 0)
    universe_ids = [c.candidate_id for c in candidates]
    universe = set(universe_ids)
    if len(universe) != len(universe_ids):
        raise GovernanceBlock(
            "The unsharded universe already contains duplicate candidate ids; a shard "
            "partition proof over it would be meaningless."
        )
    union: list[int] = []
    per_shard: dict[int, int] = {}
    for index in range(shard_count):
        member = [c.candidate_id for c in shard_candidates(candidates, shard_count, index)]
        per_shard[index] = len(member)
        union.extend(member)
    counts = Counter(union)
    duplicates = sorted(i for i, n in counts.items() if n > 1)
    missing = sorted(universe - set(union))
    unexpected = sorted(set(union) - universe)
    if missing or duplicates or unexpected:
        raise GovernanceBlock(
            f"Shard partition over {shard_count} shards is not exact: "
            f"missing={len(missing)} duplicates={len(duplicates)} "
            f"unexpected={len(unexpected)}."
        )
    return {
        "shard_count": shard_count,
        "universe_size": len(universe),
        "union_size": len(set(union)),
        "missing": 0,
        "duplicates": 0,
        "unexpected": 0,
        "per_shard_sizes": {str(k): v for k, v in sorted(per_shard.items())},
        "exact": True,
    }


# --- boundary identification -------------------------------------------------

BOUNDARY_OPTIMUM = "BOUNDARY_OPTIMUM"
INTERIOR_OPTIMUM = "INTERIOR_OPTIMUM"

#: Families whose levels form a ladder, so "the optimum sat at the edge" is
#: meaningful. ``blowout_treatment`` is excluded: its levels are shapes, and the
#: edge of an unordered set is an artifact of the order somebody typed them in.
ORDERED_FAMILIES = (
    "weekly_performance_residual_coefficient",
    "weekly_movement_cap_points",
    "recent_form_weights",
    "sample_size_regularization",
)


def _axis_position(
    space: SearchSpace, family: str, candidate: CalibrationCandidate
) -> tuple[int, int]:
    axis_levels = space.axis(family).levels
    if family == "weekly_performance_residual_coefficient":
        ordered = sorted(float(v) for v in axis_levels)
        return ordered.index(float(candidate.coefficient)), len(ordered)
    if family == "weekly_movement_cap_points":
        ordered = sorted(float(v) for v in axis_levels)
        return ordered.index(float(candidate.movement_cap_points)), len(ordered)
    if family == "recent_form_weights":
        depths = sorted({int(level.depth) for level in axis_levels})
        return depths.index(int(candidate.recent_form.depth)), len(depths)
    if family == "sample_size_regularization":
        priors = sorted({float(level.prior_games or 0.0) for level in axis_levels})
        return priors.index(float(candidate.regularization.prior_games or 0.0)), len(priors)
    raise InputValidationError(f"{family} has no ordered position to test for boundary")


def boundary_report(space: SearchSpace, winner: CalibrationCandidate) -> dict[str, Any]:
    """Mark every ordered family whose winning level sits on the search boundary.

    An optimum at the edge of the grid is not an optimum; it is the grid running
    out. The prior 9,600-candidate experiment reported a depth-6 winner at the top
    of a depth ladder that stopped at 6, and recorded it as a finding. Here it is
    recorded as :data:`BOUNDARY_OPTIMUM` and handed to :func:`refine_space`, which
    widens the ladder instead of concluding.
    """
    if space.explicit_candidates:
        return {
            "space_id": space.space_id,
            "stage": space.stage,
            "winner_candidate_id": winner.candidate_id,
            "families": {},
            "boundary_families": [],
            "identified": True,
            "note": "An explicit shortlist has no grid boundary to sit on.",
        }
    families: dict[str, Any] = {}
    for family in ORDERED_FAMILIES:
        position, count = _axis_position(space, family, winner)
        at_low = position == 0 and count > 1
        at_high = position == count - 1 and count > 1
        families[family] = {
            "position": position,
            "level_count": count,
            "status": BOUNDARY_OPTIMUM if (at_low or at_high) else INTERIOR_OPTIMUM,
            "edge": "low" if at_low else ("high" if at_high else None),
            "expandable": space.axis(family).boundary_expandable,
        }
    boundary = sorted(f for f, v in families.items() if v["status"] == BOUNDARY_OPTIMUM)
    report: dict[str, Any] = {
        "space_id": space.space_id,
        "stage": space.stage,
        "winner_candidate_id": winner.candidate_id,
        "families": families,
        "boundary_families": boundary,
        "identified": not boundary,
    }
    if "recent_form_weights" in boundary:
        report["recent_form_tail_mass"] = winner.recent_form.tail_mass
    return report


# --- stage 2: refinement -----------------------------------------------------


def _refine_scalar(
    levels: Sequence[float], value: float, *, expandable: bool
) -> tuple[float, ...]:
    """Half-step neighbours around ``value``, widened when it sits on an edge."""
    ordered = sorted(float(v) for v in levels)
    target = float(value)
    if target not in ordered:
        raise InputValidationError(
            f"Cannot refine around {target!r}: it is not a level of the parent axis "
            f"{ordered}. Refining around a value the coarse stage never scored would "
            "invent a leader."
        )
    position = ordered.index(target)
    step: float | None = None
    if position > 0:
        step = target - ordered[position - 1]
    if position < len(ordered) - 1:
        above = ordered[position + 1] - target
        step = above if step is None else min(step, above)
    if step is None:
        step = abs(target) or 1.0
    half = step / 2.0
    out = {target, target - half, target + half}
    if expandable:
        if position == 0:
            out.add(target - step)
        if position == len(ordered) - 1:
            out.add(target + step)
    return tuple(sorted(v for v in out if v > 0.0))


def refine_space(
    base: SearchSpace,
    winners: Sequence[CalibrationCandidate],
    *,
    space_id: str | None = None,
    range_authority: str | None = None,
) -> SearchSpace:
    """Stage 2. A deterministic local grid around the Stage-1 leaders.

    Deterministic in the strict sense: the returned space is a pure function of
    ``base`` and the ordered ``winners``, so two operators handed the same Stage-1
    ranking build byte-identical Stage-2 universes and their shards interlock.

    Widening is driven by boundary position, not by taste. Where a leader sat on
    an edge of an expandable ladder the refined axis reaches one full step past
    it; where a leader sat in the interior the refined axis subdivides. That is
    the mechanism the lane instruction asks for: a boundary optimum causes the
    search to grow rather than to be reported as an answer.
    """
    if not winners:
        raise InputValidationError(
            "Refinement requires at least one Stage-1 leader; refining around nothing "
            "would silently reproduce the coarse grid under a new stage name."
        )
    if base.explicit_candidates:
        raise InputValidationError("An explicit shortlist cannot be refined; it has no axes.")

    coefficients: set[float] = set()
    caps: set[float] = set()
    forms: dict[str, RecentFormPolicy] = {}
    blowouts: dict[str, BlowoutPolicy] = {}
    regularizations: dict[str, RegularizationPolicy] = {}

    coefficient_axis = base.axis("weekly_performance_residual_coefficient")
    cap_axis = base.axis("weekly_movement_cap_points")
    form_axis = base.axis("recent_form_weights")
    regularization_axis = base.axis("sample_size_regularization")
    deepest = max(int(level.depth) for level in form_axis.levels)

    for winner in winners:
        coefficients.update(
            _refine_scalar(
                [float(v) for v in coefficient_axis.levels],
                float(winner.coefficient),
                expandable=coefficient_axis.boundary_expandable,
            )
        )
        caps.update(
            _refine_scalar(
                [float(v) for v in cap_axis.levels],
                float(winner.movement_cap_points),
                expandable=cap_axis.boundary_expandable,
            )
        )

        depth = int(winner.recent_form.depth)
        depths = {depth, max(1, depth - 1), depth + 1}
        if form_axis.boundary_expandable and depth >= deepest:
            # The ladder ran out underneath the leader. Reach past it rather than
            # reporting the edge as the answer.
            depths.add(depth + 2)
        if winner.recent_form.decay is None:
            decays: set[float | None] = {None}
        else:
            centre = float(winner.recent_form.decay)
            decays = {
                round(d, 6)
                for d in (centre - 0.1, centre, centre + 0.1)
                if 0.0 < round(d, 6) < 1.0
            }
        for candidate_depth in sorted(depths):
            for decay in sorted(decays, key=lambda x: (x is None, x)):
                policy_f = RecentFormPolicy(winner.recent_form.scheme, candidate_depth, decay)
                forms[canonical_json(policy_f)] = policy_f

        blowouts[canonical_json(winner.blowout)] = winner.blowout
        if winner.blowout.threshold_points is not None:
            for delta in (-3.0, 3.0):
                threshold = float(winner.blowout.threshold_points) + delta
                if threshold > 0:
                    policy_b = BlowoutPolicy(winner.blowout.policy_id, threshold)
                    blowouts[canonical_json(policy_b)] = policy_b

        regularizations[canonical_json(winner.regularization)] = winner.regularization
        if winner.regularization.prior_games is not None:
            for prior in _refine_scalar(
                [
                    float(level.prior_games)
                    for level in regularization_axis.levels
                    if level.prior_games is not None
                ],
                float(winner.regularization.prior_games),
                expandable=regularization_axis.boundary_expandable,
            ):
                policy_r = RegularizationPolicy(winner.regularization.policy_id, prior)
                regularizations[canonical_json(policy_r)] = policy_r

    def _ordered(mapping: dict[str, Any]) -> tuple[Any, ...]:
        return tuple(mapping[key] for key in sorted(mapping))

    return SearchSpace(
        space_id=space_id or f"{base.space_id}-REFINE",
        stage=STAGE_REFINEMENT,
        range_authority=range_authority if range_authority is not None else base.range_authority,
        parent_config_sha=base.config_sha,
        axes=(
            SearchAxis(
                family="weekly_performance_residual_coefficient",
                levels=tuple(sorted(coefficients)),
                evidence_status=coefficient_axis.evidence_status,
                boundary_expandable=coefficient_axis.boundary_expandable,
                rationale="Half-step subdivision around Stage-1 leaders; widened at edges.",
            ),
            SearchAxis(
                family="weekly_movement_cap_points",
                levels=tuple(sorted(caps)),
                evidence_status=cap_axis.evidence_status,
                boundary_expandable=cap_axis.boundary_expandable,
                rationale="Half-step subdivision around Stage-1 leaders; widened at edges.",
            ),
            SearchAxis(
                family="recent_form_weights",
                levels=_ordered(forms),
                evidence_status=form_axis.evidence_status,
                boundary_expandable=form_axis.boundary_expandable,
                rationale=(
                    "Depth +/-1 and decay +/-0.1 around leaders; the depth ladder is "
                    "extended past any boundary optimum rather than stopping at it."
                ),
            ),
            SearchAxis(
                family="blowout_treatment",
                levels=_ordered(blowouts),
                evidence_status=base.axis("blowout_treatment").evidence_status,
                boundary_expandable=False,
                rationale="Leaders' shapes retained; thresholds probed +/-3 points.",
            ),
            SearchAxis(
                family="sample_size_regularization",
                levels=_ordered(regularizations),
                evidence_status=regularization_axis.evidence_status,
                boundary_expandable=regularization_axis.boundary_expandable,
                rationale="Leaders' policies retained; prior_games subdivided.",
            ),
        ),
    )


# --- stage 3: holdout --------------------------------------------------------

HOLDOUT_SEALED = "HOLDOUT_SEALED_SCORED_ONCE"
HOLDOUT_REFUSED_SECOND_LOOK = "HOLDOUT_REFUSED_SECOND_LOOK"

#: How many candidates may ever meet the holdout. Small on purpose; see
#: :func:`holdout_space`.
MAX_HOLDOUT_SHORTLIST = 8


def holdout_space(
    shortlist: Sequence[CalibrationCandidate],
    *,
    parent: SearchSpace,
    space_id: str | None = None,
    max_shortlist: int = MAX_HOLDOUT_SHORTLIST,
) -> SearchSpace:
    """Stage 3. The shortlist, and only the shortlist.

    A shortlist cap is applied rather than left to the operator because the
    holdout's protection is arithmetic, not procedural: scoring 2,000 candidates
    against it and taking the best is selection on the holdout however sincerely
    the run is described as a final check.
    """
    if not shortlist:
        raise InputValidationError("Holdout stage requires a non-empty shortlist.")
    if len(shortlist) > max_shortlist:
        raise GovernanceBlock(
            f"Holdout shortlist of {len(shortlist)} exceeds the maximum of "
            f"{max_shortlist}. Scoring a wide field against the untouched holdout and "
            "taking the minimum is selection against the holdout, which is the one "
            "thing the holdout exists to prevent."
        )
    return explicit_space(
        shortlist,
        space_id=space_id or f"{parent.space_id}-HOLDOUT",
        stage=STAGE_HOLDOUT,
        range_authority=parent.range_authority,
        parent_config_sha=parent.config_sha,
    )


@dataclass
class HoldoutLedger:
    """One-shot custody for the untouched holdout split.

    "No iterative tuning against holdout" cannot be enforced by intent, because
    the second run always has a reason. This records that the split was consumed,
    against specific dataset and split digests, and refuses the next request.
    Re-opening it means constructing a new ledger, which is a visible act rather
    than a re-run of the same command.
    """

    split_sha: str
    dataset_sha: str
    consumed_by_config_sha: str | None = None
    consumed_candidate_ids: tuple[int, ...] = ()

    def consume(self, *, config_sha: str, candidate_ids: Iterable[int]) -> dict[str, Any]:
        if self.consumed_by_config_sha is not None:
            raise GovernanceBlock(
                f"{HOLDOUT_REFUSED_SECOND_LOOK}: holdout split {self.split_sha[:12]} was "
                f"already scored by experiment config {self.consumed_by_config_sha[:12]}. "
                "A second scoring makes the holdout a validation set."
            )
        ids = tuple(sorted({int(i) for i in candidate_ids}))
        if not ids:
            raise InputValidationError("Holdout consumption must name at least one candidate.")
        if len(ids) > MAX_HOLDOUT_SHORTLIST:
            raise GovernanceBlock(
                f"{len(ids)} candidates were presented to the holdout; the maximum is "
                f"{MAX_HOLDOUT_SHORTLIST}."
            )
        self.consumed_by_config_sha = config_sha
        self.consumed_candidate_ids = ids
        return {
            "status": HOLDOUT_SEALED,
            "split_sha": self.split_sha,
            "dataset_sha": self.dataset_sha,
            "config_sha": config_sha,
            "candidate_count": len(ids),
            "candidate_ids": list(ids),
        }


# --- operator interface ------------------------------------------------------


def space_for_stage(stage: str, *, range_authority: str | None = None) -> SearchSpace:
    """The named space a worker is expected to build for a stage.

    Only the coarse stage has a standing definition. Refinement and holdout spaces
    are functions of earlier results, so a worker must be handed one rather than
    invent it — which is the whole point of refusing to let a worker choose a grid.
    """
    if stage == STAGE_COARSE:
        return coarse_space(range_authority=range_authority)
    raise GovernanceBlock(
        f"Stage {stage!r} has no standing space definition. A {stage} universe is "
        "derived from the previous stage's aggregated ranking and must be supplied to "
        "the worker, so that every worker searches the same universe."
    )


def plan_as_dict(space: SearchSpace, *, shard_count: int | None = None) -> dict[str, Any]:
    """Everything an operator needs before spending compute, and nothing measured."""
    candidates = space.enumerate()
    plan: dict[str, Any] = {
        "space": space.as_dict(),
        "config_sha": space.config_sha,
        "candidate_count": len(candidates),
        "supported_shard_counts": list(SUPPORTED_SHARD_COUNTS),
        "shard_partition_proofs": {
            str(count): prove_shard_partition(candidates, count)
            for count in SUPPORTED_SHARD_COUNTS
        },
        "historical_research_context": dict(HISTORICAL_RESEARCH_CONTEXT),
        "parameters_promoted": 0,
        "writes_canonical_config": False,
    }
    if shard_count is not None:
        _require_shard_arguments(shard_count, 0)
        plan["selected_shard_count"] = shard_count
    return plan


def main(argv: list[str] | None = None) -> int:
    """Operator entry point for one shard of one stage.

    ``--plan`` is the mode that works today: it enumerates the universe, proves
    the shard partition for every supported shard count and writes the plan.
    Scoring requires governed inputs and refuses without them, which is why the
    two are separate flags rather than one command that quietly does less than it
    says.
    """
    parser = argparse.ArgumentParser(
        prog="sythalax-v3-calibration-search",
        description=(
            "Enumerate, shard and (when inputs are governed) score the V3 calibration "
            "candidate universe."
        ),
    )
    parser.add_argument("--stage", choices=list(STAGES), default=STAGE_COARSE)
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    parser.add_argument(
        "--expect-config-sha",
        default=None,
        help="Refuse to run unless the built space digests to this value.",
    )
    parser.add_argument(
        "--range-authority",
        default=None,
        help="Optional named governance authority. Not required: predeclared, "
        "hash-bound ranges are executable for research on their own.",
    )
    parser.add_argument(
        "--experiment-id",
        default=None,
        help="Identifier the predeclared ranges are bound under.",
    )
    parser.add_argument(
        "--plan",
        action="store_true",
        help="Enumerate and prove the partition without scoring. Works without inputs.",
    )
    parser.add_argument("--observations", default=None, help="Governed observation dataset.")
    parser.add_argument(
        "--expected-margin-authority",
        default=None,
        help="Identifier of the governed expected-margin STRUCTURE. The point scale "
        "it carries may be an experiment-bound candidate.",
    )
    parser.add_argument(
        "--output-dir", default="output/dynamic_weekly_mc_v3/calibration_search"
    )
    args = parser.parse_args(argv)

    try:
        assert_families_match_calibration()
        _require_shard_arguments(args.shard_count, args.shard_index)
        space = space_for_stage(args.stage, range_authority=args.range_authority)
        if args.expect_config_sha and space.config_sha != args.expect_config_sha:
            raise GovernanceBlock(
                f"Worker built space {space.config_sha} but was told to expect "
                f"{args.expect_config_sha}. Refusing to search a universe the rest of "
                "the fleet is not searching."
            )
        candidates = space.enumerate()
        shard = shard_candidates(candidates, args.shard_count, args.shard_index)

        if args.plan:
            plan = plan_as_dict(space, shard_count=args.shard_count)
            plan["shard_index"] = args.shard_index
            plan["shard_candidate_count"] = len(shard)
            target = Path(args.output_dir).resolve() / (
                f"PLAN_{args.stage}_shard{args.shard_index}of{args.shard_count}.json"
            )
            write_json_lf(target, plan)
            print(
                json.dumps(
                    {
                        "status": "PLANNED",
                        "written": str(target),
                        "config_sha": space.config_sha,
                        "candidate_count": len(candidates),
                        "shard_candidate_count": len(shard),
                        "parameters_promoted": 0,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        predeclaration = (
            predeclare(space, experiment_id=args.experiment_id)
            if args.experiment_id
            else None
        )
        require_executable_ranges(space, predeclaration=predeclaration)
        if not args.observations or not args.expected_margin_authority:
            raise GovernanceBlock(
                "Scoring requires an audited observation corpus and a governed "
                "expected-margin structure. Neither has a default: an expected margin "
                "that defaults is an invented one. The point *scale* inside that "
                "structure may be an experiment-bound candidate and needs no ruling."
            )
        raise GovernanceBlock(
            "No audited calibration corpus is mounted in this repository. The search "
            "universe, sharding and scorer are ready; the inputs are not."
        )
    except (GovernanceBlock, InputValidationError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "stage": args.stage,
                    "shard_index": args.shard_index,
                    "shard_count": args.shard_count,
                    "reason": str(exc),
                    "parameters_promoted": 0,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
