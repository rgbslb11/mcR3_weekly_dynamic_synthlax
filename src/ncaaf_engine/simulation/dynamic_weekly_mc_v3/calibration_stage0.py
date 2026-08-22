"""Stage 0 — identify the historical V3 point scale from Weeks 1-2.

The independent audit established that the historical point axis is
*empirically calibratable* rather than a value someone must first rule on. That
changes what this stage is: not a governance question waiting for an answer, but
a one-parameter estimation problem with an unusually clean identification.

Weeks 1-2 are the clean window. Nothing has been promoted yet — V3's first
promoted rerating lands after Week 2 — so every prediction in that window comes
from opening strength alone. No weekly residual coefficient, no movement cap, no
recent-form weighting and no regularization enter the arithmetic. Exactly one
unknown remains:

    team_points     = k * opening_standardized_state
    opponent_points = k * opponent_opening_standardized_state
    expected_margin = (team_points - opponent_points) + governed venue adjustment

so ``k`` is identified against real Week 1-2 margins without any of Stage 1's
parameters being chosen first. Running Stage 1 before Stage 0 would confound the
scale with the rerating coefficient, since a large ``k`` and a small coefficient
buy much the same thing.

Three properties are load-bearing.

``k`` is an experimental candidate, not an authority
    :data:`POINT_SCALE_STATUS` is
    :data:`~.calibration_search.EVIDENCE_PREDECLARED`. The grid is broad,
    deterministic, fixed in source before any result existed, and bound into a
    digest. It confers nothing toward a canonical promotion, which stays governed.

Inputs arrive sealed, never as paths
    Agent 6 produces the opening standardized state and Agent 5 the venue
    classification. :class:`SealedInput` carries a payload and the digest over it,
    and :func:`refuse_direct_worktree_read` refuses a path outside this repository
    outright. Reading a sibling worktree's file would make this lane's result
    depend on whatever that lane happened to have saved at the moment it was read.

FCS observations stay out
    Their point scale is a separate open blocker. Fitting them here would fit
    them on the very axis this stage is trying to identify.

Nothing here selects a scale. :func:`identify_point_scale` refuses unless every
real input is present, and even then its output is a ranked table.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import calibration as cal
from .calibration_scoring import (
    ExpectedMarginAuthority,
    ObservationRow,
    ObservationSet,
    SCALE_EXPERIMENT_BOUND,
    require_governed_structure,
)
from .calibration_search import (
    BOUNDARY_OPTIMUM,
    EVIDENCE_PREDECLARED,
    INTERIOR_OPTIMUM,
    MINIMUM_PREDECLARED_LEVELS,
    STAGE_POINT_SCALE,
    SUPPORTED_SHARD_COUNTS,
    CANDIDATE_ID_BITS,
    ExperimentPredeclaration,
    canonical_json,
    shard_of,
)
from .errors import GovernanceBlock, InputValidationError

__all__ = [
    "POINT_SCALE_SPACE_ID",
    "POINT_SCALE_STATUS",
    "STAGE0_ID",
    "STAGE0_PRIMARY_OBJECTIVE",
    "PointScaleCandidate",
    "PointScaleSpace",
    "SealedInput",
    "Stage0Result",
    "default_point_scale_space",
    "expand_point_scale_space",
    "identify_point_scale",
    "opening_state_key",
    "point_scale_boundary_report",
    "predeclare_point_scale",
    "refuse_direct_worktree_read",
    "require_sealed",
    "score_point_scale",
    "shard_point_scale",
    "stage0_weeks",
    "weeks_1_2_rows",
]

STAGE0_ID = "V3-CAL-STAGE0-POINT-SCALE-001"
POINT_SCALE_SPACE_ID = "V3-CAL-POINT-SCALE-001"
POINT_SCALE_STATUS = EVIDENCE_PREDECLARED

STAGE0_PRIMARY_OBJECTIVE = "out_of_sample_expected_margin_rmse_weeks_1_2"

#: The window in which opening-strength semantics are exact and nothing has been
#: promoted. Fixed by V3 governance, not chosen here.
stage0_weeks = (1, 2)

#: Producers this stage is designed to consume, named so a reviewer can tell
#: which lane owes which input.
PRODUCER_OPENING_STATE = "AGENT_6_HISTORICAL_OPENING_STANDARDIZED_STATE"
PRODUCER_VENUE_CLASSIFICATION = "AGENT_5_VENUE_NEUTRAL_SITE_CLASSIFICATION"


# --- sealed inputs -----------------------------------------------------------


@dataclass(frozen=True)
class SealedInput:
    """A payload plus the digest over it, produced by a named upstream lane.

    The alternative — reading a file out of a sibling worktree — makes this lane's
    result depend on whatever that lane had saved at the instant of the read, with
    no record of which version was used. A sealed input can be cited: the digest
    is in the Stage 0 record, and re-running against a different payload produces a
    different digest rather than a quietly different answer.
    """

    input_id: str
    producer: str
    sha256: str
    payload: Mapping[str, Any]

    @staticmethod
    def digest_of(input_id: str, producer: str, payload: Mapping[str, Any]) -> str:
        return hashlib.sha256(
            canonical_json(
                {"input_id": input_id, "producer": producer, "payload": dict(payload)}
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def seal(
        cls, *, input_id: str, producer: str, payload: Mapping[str, Any]
    ) -> "SealedInput":
        return cls(
            input_id=input_id,
            producer=producer,
            sha256=cls.digest_of(input_id, producer, payload),
            payload=dict(payload),
        )

    def verify(self) -> str:
        """Recompute the digest from the payload and refuse a disagreement."""
        recomputed = self.digest_of(self.input_id, self.producer, self.payload)
        if recomputed != self.sha256:
            raise GovernanceBlock(
                f"Sealed input {self.input_id} declares digest {self.sha256} but its "
                f"payload digests to {recomputed}. The bytes cited are not the bytes "
                "supplied."
            )
        return recomputed

    def as_dict(self) -> dict[str, Any]:
        return {
            "input_id": self.input_id,
            "producer": self.producer,
            "sha256": self.sha256,
            "entries": len(self.payload),
        }


def require_sealed(
    sealed: SealedInput | None, *, producer: str, expected_sha: str | None = None
) -> SealedInput:
    """Fail closed unless a verified input from the expected producer is present."""
    if sealed is None:
        raise GovernanceBlock(
            f"Stage 0 requires a sealed input from {producer}; none was supplied. It is "
            "not read from disk and has no default."
        )
    if sealed.producer != producer:
        raise GovernanceBlock(
            f"Sealed input {sealed.input_id} comes from {sealed.producer}, not the "
            f"expected {producer}."
        )
    sealed.verify()
    if expected_sha is not None and sealed.sha256 != expected_sha:
        raise GovernanceBlock(
            f"Sealed input {sealed.input_id} digests to {sealed.sha256} but the "
            f"experiment expects {expected_sha}."
        )
    if not sealed.payload:
        raise GovernanceBlock(
            f"Sealed input {sealed.input_id} carries an empty payload. An empty input "
            "is refused rather than treated as 'nothing to adjust'."
        )
    return sealed


def refuse_direct_worktree_read(path: Path, *, repo_root: Path) -> None:
    """Refuse to read an input from outside this repository.

    Stage 0 consumes sealed payloads. A path handed to it that resolves outside
    the repository is almost certainly a sibling agent's working tree, whose
    contents are mutable and unversioned from here. Refused rather than read.
    """
    resolved = Path(path).resolve()
    root = Path(repo_root).resolve()
    if root not in resolved.parents and resolved != root:
        raise GovernanceBlock(
            f"Refusing to read {resolved} from outside {root}. Stage 0 consumes sealed, "
            "digest-bound payloads; reading another lane's working tree would make this "
            "result depend on a file nobody versioned."
        )


def opening_state_key(season: int, team: str) -> str:
    """The key an opening standardized state is looked up under."""
    return f"{int(season)}|{team}"


# --- candidate scale ---------------------------------------------------------


@dataclass(frozen=True)
class PointScaleCandidate:
    """One candidate historical points-per-standardized-unit scale.

    An experimental calibration value, never an authority. Content-addressed on the
    same scheme as a mean-model candidate so Stage 0 shards and aggregates by the
    identical arithmetic.
    """

    points_per_standardized_unit: float
    status: str = SCALE_EXPERIMENT_BOUND

    def __post_init__(self) -> None:
        value = float(self.points_per_standardized_unit)
        if not math.isfinite(value) or value <= 0.0:
            raise InputValidationError(
                f"A point scale must be positive and finite; got "
                f"{self.points_per_standardized_unit!r}."
            )

    @property
    def canonical_serialization(self) -> str:
        return canonical_json(
            {
                "historical_points_per_standardized_unit": float(
                    self.points_per_standardized_unit
                )
            }
        )

    @property
    def candidate_key(self) -> str:
        return hashlib.sha256(self.canonical_serialization.encode("utf-8")).hexdigest()

    @property
    def candidate_id(self) -> int:
        raw = int.from_bytes(bytes.fromhex(self.candidate_key)[:8], "big")
        return raw >> (64 - CANDIDATE_ID_BITS)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_key": self.candidate_key,
            "points_per_standardized_unit": float(self.points_per_standardized_unit),
            "status": self.status,
            "confers_promotion_authority": False,
        }


@dataclass(frozen=True)
class PointScaleSpace:
    """The Stage 0 universe: one broad, predeclared, hash-bound scale axis."""

    space_id: str
    levels: tuple[float, ...]
    evidence_status: str = POINT_SCALE_STATUS
    parent_config_sha: str | None = None

    def __post_init__(self) -> None:
        ordered = sorted(float(v) for v in self.levels)
        if len(set(ordered)) != len(ordered):
            raise InputValidationError(f"Space {self.space_id} repeats a scale level.")
        if len(ordered) < MINIMUM_PREDECLARED_LEVELS or ordered[-1] <= ordered[0]:
            raise GovernanceBlock(
                f"Space {self.space_id} declares {len(ordered)} scale level(s) spanning "
                f"{ordered[0]}..{ordered[-1]}. A predeclared range needs at least "
                f"{MINIMUM_PREDECLARED_LEVELS} distinct levels with real spread; "
                "otherwise it declares the answer instead of searching for one."
            )
        if ordered[0] <= 0.0:
            raise InputValidationError("Every scale level must be positive.")

    @property
    def size(self) -> int:
        return len(self.levels)

    def enumerate(self) -> tuple[PointScaleCandidate, ...]:
        return tuple(
            PointScaleCandidate(level) for level in sorted(float(v) for v in self.levels)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "space_id": self.space_id,
            "stage": STAGE_POINT_SCALE,
            "levels": sorted(float(v) for v in self.levels),
            "level_count": self.size,
            "evidence_status": self.evidence_status,
            "parent_config_sha": self.parent_config_sha,
            "experimental_value": "historical_points_per_standardized_unit",
            "confers_promotion_authority": False,
        }

    @property
    def config_sha(self) -> str:
        return hashlib.sha256(canonical_json(self.as_dict()).encode("utf-8")).hexdigest()


#: Broad by construction. The plausible historical scale is not known to within a
#: factor of two, so the declared range spans an order of magnitude rather than
#: bracketing a guess, and :func:`expand_point_scale_space` widens it further if
#: the optimum lands on an edge.
DEFAULT_SCALE_STEP = 2.0
DEFAULT_SCALE_MINIMUM = 2.0
DEFAULT_SCALE_LEVELS = 20


def default_point_scale_space() -> PointScaleSpace:
    """The predeclared Stage 0 grid: 2.0 to 40.0 points per standardized unit."""
    return PointScaleSpace(
        space_id=POINT_SCALE_SPACE_ID,
        levels=tuple(
            round(DEFAULT_SCALE_MINIMUM + DEFAULT_SCALE_STEP * i, 6)
            for i in range(DEFAULT_SCALE_LEVELS)
        ),
    )


def predeclare_point_scale(
    space: PointScaleSpace,
    *,
    experiment_id: str,
    scored_split: str = "validation",
) -> ExperimentPredeclaration:
    """Bind the Stage 0 grid to a digest before any Week 1-2 margin is scored."""
    return ExperimentPredeclaration(
        experiment_id=experiment_id,
        config_sha=space.config_sha,
        stage=STAGE_POINT_SCALE,
        declared_scored_split=scored_split.strip().lower(),
    )


def point_scale_boundary_report(
    space: PointScaleSpace, winner: PointScaleCandidate
) -> dict[str, Any]:
    """Mark a winning scale that sits on the edge of the declared grid."""
    ordered = sorted(float(v) for v in space.levels)
    value = float(winner.points_per_standardized_unit)
    position = ordered.index(value)
    at_low = position == 0
    at_high = position == len(ordered) - 1
    return {
        "space_id": space.space_id,
        "winning_scale": value,
        "position": position,
        "level_count": len(ordered),
        "status": BOUNDARY_OPTIMUM if (at_low or at_high) else INTERIOR_OPTIMUM,
        "edge": "low" if at_low else ("high" if at_high else None),
        "identified": not (at_low or at_high),
        "expansion_required": at_low or at_high,
    }


def expand_point_scale_space(
    space: PointScaleSpace, winner: PointScaleCandidate, *, space_id: str | None = None
) -> PointScaleSpace:
    """Widen the grid past a boundary optimum rather than reporting the edge.

    An optimum at the edge is the grid running out. Expansion is deterministic —
    one full step past the edge, repeated for as many levels as the original grid
    reserved at that end — so the widened space is a pure function of the original
    and the winner.
    """
    report = point_scale_boundary_report(space, winner)
    ordered = sorted(float(v) for v in space.levels)
    if not report["expansion_required"]:
        raise InputValidationError(
            f"Scale {winner.points_per_standardized_unit} sits in the interior of "
            f"{space.space_id}; there is no boundary to expand past. Refine rather "
            "than widen."
        )
    step = min(b - a for a, b in zip(ordered, ordered[1:]))
    added: list[float] = []
    if report["edge"] == "high":
        added = [round(ordered[-1] + step * (i + 1), 6) for i in range(len(ordered) // 2)]
    else:
        added = [
            round(ordered[0] - step * (i + 1), 6)
            for i in range(len(ordered) // 2)
            if ordered[0] - step * (i + 1) > 0.0
        ]
    if not added:
        raise GovernanceBlock(
            f"Scale optimum sits at the low edge of {space.space_id} and the grid "
            "cannot be widened further without non-positive levels. The scale is not "
            "identified by this corpus."
        )
    return PointScaleSpace(
        space_id=space_id or f"{space.space_id}-EXPANDED",
        levels=tuple(sorted(set(ordered) | set(added))),
        parent_config_sha=space.config_sha,
    )


def shard_point_scale(
    candidates: Sequence[PointScaleCandidate], shard_count: int, shard_index: int
) -> tuple[PointScaleCandidate, ...]:
    """Same arithmetic as Stage 1: ``candidate_id % shard_count == shard_index``."""
    if shard_count not in SUPPORTED_SHARD_COUNTS:
        raise InputValidationError(
            f"shard_count {shard_count} is not supported; expected one of "
            f"{list(SUPPORTED_SHARD_COUNTS)}."
        )
    if not 0 <= shard_index < shard_count:
        raise InputValidationError(f"shard_index {shard_index} outside [0, {shard_count}).")
    return tuple(
        c for c in candidates if shard_of(c.candidate_id, shard_count) == shard_index
    )


# --- scoring -----------------------------------------------------------------


def weeks_1_2_rows(observations: ObservationSet) -> tuple[ObservationRow, ...]:
    """The Weeks 1-2, FBS-only window Stage 0 is identified in.

    FCS rows are already absent from ``calibration_rows``. Weeks beyond 2 are
    excluded here because a promoted rerating stands behind them, and a scale
    fitted against a promoted rating is confounded with the coefficient that
    produced it.
    """
    return tuple(
        r for r in observations.calibration_rows if int(r.week) in stage0_weeks
    )


@dataclass(frozen=True)
class Stage0Result:
    """One candidate scale, scored against real Week 1-2 margins."""

    candidate: PointScaleCandidate
    scored_split: str
    scored_count: int
    rmse: float
    mae: float
    residual_mean: float
    winner_accuracy: float | None
    train_count: int
    validation_count: int
    holdout_count: int
    fcs_excluded_count: int
    rerating_parameters_used: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate.candidate_id,
            "candidate_key": self.candidate.candidate_key,
            "points_per_standardized_unit": float(
                self.candidate.points_per_standardized_unit
            ),
            "stage": STAGE_POINT_SCALE,
            "scored_split": self.scored_split,
            "scored_count": self.scored_count,
            STAGE0_PRIMARY_OBJECTIVE: self.rmse,
            "expected_margin_rmse": self.rmse,
            "expected_margin_mae": self.mae,
            "residual_mean": self.residual_mean,
            "winner_accuracy": self.winner_accuracy,
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "holdout_count": self.holdout_count,
            "fcs_excluded_count": self.fcs_excluded_count,
            "rerating_parameters_used": self.rerating_parameters_used,
            "scale_status": self.candidate.status,
            "confers_promotion_authority": False,
        }


def score_point_scale(
    candidate: PointScaleCandidate,
    *,
    observations: ObservationSet,
    structure: ExpectedMarginAuthority,
    opening_state: SealedInput,
    scored_split: str = "validation",
) -> Stage0Result:
    """Score one candidate scale over the Weeks 1-2 window.

    No mean-model parameter enters. There is no coefficient, no cap, no
    recent-form weighting and no regularization in this arithmetic, which is what
    makes ``k`` identified rather than confounded — and
    ``rerating_parameters_used`` is reported as zero so that claim is a field
    rather than a sentence in a docstring.
    """
    split_key = scored_split.strip().lower()
    if split_key not in cal.DATA_SPLITS:
        raise InputValidationError(
            f"scored_split {scored_split!r}; expected one of {list(cal.DATA_SPLITS)}."
        )
    if split_key == "holdout":
        raise GovernanceBlock(
            "Stage 0 may not select a scale against the holdout. The holdout is scored "
            "once, at final evaluation, and never during identification."
        )
    require_governed_structure(structure)
    require_sealed(opening_state, producer=PRODUCER_OPENING_STATE)

    scaled = structure.with_scale(
        candidate.points_per_standardized_unit, status=candidate.status
    )
    window = weeks_1_2_rows(observations)
    if not window:
        raise InputValidationError(
            "No Weeks 1-2 observations are available; Stage 0 has no window to "
            "identify a scale in."
        )

    counts = {split: 0 for split in cal.DATA_SPLITS}
    residuals: list[float] = []
    decided = 0
    correct = 0
    missing: list[str] = []
    for row in window:
        counts[row.normalized_split] += 1
        if row.normalized_split != split_key:
            continue
        team_key = opening_state_key(row.season, row.team)
        opponent_key = opening_state_key(row.season, row.opponent)
        if team_key not in opening_state.payload or opponent_key not in opening_state.payload:
            missing.append(row.game_id)
            continue
        predicted = scaled.expected_margin_from_standardized(
            float(opening_state.payload[team_key]),
            float(opening_state.payload[opponent_key]),
            row.venue,
        )
        residuals.append(float(row.actual_margin) - predicted)
        if float(row.actual_margin) != 0.0:
            decided += 1
            if (predicted > 0) == (float(row.actual_margin) > 0) and predicted != 0:
                correct += 1
    if missing:
        raise GovernanceBlock(
            f"{len(missing)} Weeks 1-2 observation(s) have no opening standardized "
            f"state, first: {missing[:5]}. Stage 0 fails closed rather than scoring a "
            "game whose opening strength nobody supplied."
        )
    if not residuals:
        raise InputValidationError(
            f"No Weeks 1-2 observations fall in the {split_key} split."
        )

    n = len(residuals)
    return Stage0Result(
        candidate=candidate,
        scored_split=split_key,
        scored_count=n,
        rmse=math.sqrt(sum(r * r for r in residuals) / n),
        mae=sum(abs(r) for r in residuals) / n,
        residual_mean=sum(residuals) / n,
        winner_accuracy=(correct / decided) if decided else None,
        train_count=counts["training"],
        validation_count=counts["validation"],
        holdout_count=counts["holdout"],
        fcs_excluded_count=observations.fcs_exclusion_report()["excluded_count"],
        rerating_parameters_used=0,
    )


def identify_point_scale(
    *,
    observations: ObservationSet | None = None,
    structure: ExpectedMarginAuthority | None = None,
    opening_state: SealedInput | None = None,
    venue_classification: SealedInput | None = None,
    space: PointScaleSpace | None = None,
    predeclaration: ExperimentPredeclaration | None = None,
    scored_split: str = "validation",
) -> dict[str, Any]:
    """Run Stage 0 end to end, or refuse and say exactly what is missing.

    Every input is a parameter with no default. Called with nothing it reports the
    three real dependencies rather than estimating anything, which is the state
    this lane is in.
    """
    grid = space or default_point_scale_space()
    declaration = predeclaration or predeclare_point_scale(
        grid, experiment_id=STAGE0_ID, scored_split=scored_split
    )
    if declaration.config_sha != grid.config_sha:
        raise GovernanceBlock(
            f"Predeclaration {declaration.experiment_id} binds config "
            f"{declaration.config_sha} but this scale grid digests to "
            f"{grid.config_sha}."
        )

    missing: list[str] = []
    if observations is None:
        missing.append("AUDITED_HISTORICAL_OBSERVATION_CORPUS")
    if opening_state is None:
        missing.append("HISTORICAL_OPENING_STANDARDIZED_STATE")
    if venue_classification is None:
        missing.append("DEFENSIBLE_VENUE_HFA_CLASSIFICATION")
    if missing:
        raise GovernanceBlock(
            f"Stage 0 cannot run: {missing}. The point scale is an empirical quantity "
            "and no ruling substitutes for the observations that identify it."
        )

    assert observations is not None and opening_state is not None
    require_sealed(venue_classification, producer=PRODUCER_VENUE_CLASSIFICATION)
    require_governed_structure(structure)

    results = [
        score_point_scale(
            candidate,
            observations=observations,
            structure=structure,  # type: ignore[arg-type]
            opening_state=opening_state,
            scored_split=scored_split,
        )
        for candidate in grid.enumerate()
    ]
    ranked = sorted(results, key=lambda r: (r.rmse, r.candidate.candidate_id))
    boundary = point_scale_boundary_report(grid, ranked[0].candidate)
    return {
        "stage": STAGE_POINT_SCALE,
        "stage0_id": STAGE0_ID,
        "primary_objective": STAGE0_PRIMARY_OBJECTIVE,
        "space": grid.as_dict(),
        "config_sha": grid.config_sha,
        "predeclaration": declaration.as_dict(),
        "predeclaration_sha": declaration.predeclaration_sha,
        "inputs": {
            "opening_standardized_state": opening_state.as_dict(),
            "venue_classification": (
                venue_classification.as_dict() if venue_classification else None
            ),
            "dataset_sha": observations.dataset_sha,
            "split_sha": observations.split_sha,
        },
        "fcs_exclusion": observations.fcs_exclusion_report(),
        "ranked": [r.as_dict() for r in ranked],
        "leader": ranked[0].as_dict(),
        "boundary_report": boundary,
        "expansion_required": boundary["expansion_required"],
        "scale_selected": False,
        "scale_status": SCALE_EXPERIMENT_BOUND,
        "parameters_promoted": 0,
        "writes_canonical_config": False,
    }


def stage0_plan() -> dict[str, Any]:
    """What Stage 0 will do, statable before any input exists."""
    grid = default_point_scale_space()
    return {
        "stage": STAGE_POINT_SCALE,
        "stage0_id": STAGE0_ID,
        "window_weeks": list(stage0_weeks),
        "primary_objective": STAGE0_PRIMARY_OBJECTIVE,
        "arithmetic": (
            "team_points = k * opening_standardized_state; expected_margin = "
            "(team_points - opponent_points) + governed venue adjustment"
        ),
        "rerating_parameters_used": 0,
        "space": grid.as_dict(),
        "config_sha": grid.config_sha,
        "range_status": POINT_SCALE_STATUS,
        "ruling_required": False,
        "boundary_expansion": "expand_point_scale_space",
        "shard_counts_supported": list(SUPPORTED_SHARD_COUNTS),
        "required_inputs": {
            "AUDITED_HISTORICAL_OBSERVATION_CORPUS": "this lane",
            "HISTORICAL_OPENING_STANDARDIZED_STATE": PRODUCER_OPENING_STATE,
            "DEFENSIBLE_VENUE_HFA_CLASSIFICATION": PRODUCER_VENUE_CLASSIFICATION,
        },
        "fcs_policy": "EXCLUDED_UNTIL_POINT_SCALE_ADAPTER",
        "scale_selected": False,
        "parameters_promoted": 0,
    }
