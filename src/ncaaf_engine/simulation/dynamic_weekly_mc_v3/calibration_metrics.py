"""Deterministic calibration scoring oracle for the V3 candidate search.

Frozen at :data:`ORACLE_FREEZE_ID` (``CAL-METRICS-R1``). The whole oracle --
criterion, tie-break hierarchy, stage and holdout policy, witness roles,
diagnostic conventions and emitted schema -- is digested into
:data:`ORACLE_FREEZE_SHA256`, which :func:`require_frozen_oracle` checks. A
shard worker running an altered oracle is detected before its scores are merged,
not after a candidate has been chosen under arithmetic nobody compared.

This module computes metrics. It does not choose a model, propose a parameter
grid, or promote a coefficient. Candidate generation belongs to the search lane;
what lives here is the fixed, auditable answer to "how did this candidate
score", so that every shard of that search is judged by identical arithmetic
rather than by whatever each worker decided to measure.

Ruling ``R2-CAL-OBJECTIVE`` fixes the criterion:
:data:`~.calibration.PRIMARY_CALIBRATION_METRIC` -- out-of-sample Baxter Rating
expected-margin RMSE -- minimised. Colley Matrix and SRS are witnesses reported
independently and are never folded into it. This module imports those constants
rather than restating them, so the criterion cannot drift by being written down
twice.

Four properties are load-bearing, and each is enforced rather than documented:

**Order and shard invariance.** The search will be sharded, and a metric that
depended on the order rows arrived in would make a candidate's score a function
of which worker drew it. Every aggregation sorts its inputs on a total key
(:func:`row_sort_key`) before consuming them, and every sum goes through
:func:`math.fsum`, which is correctly rounded and therefore permutation
invariant. Reordering rows, resharding candidates, or merging partial results
changes nothing about the output bytes.

**Fail closed on absent inputs.** Where a metric needs an input this repository
does not have, the field is ``None`` beside a named reason, never a plausible
number. Two such gaps are live today and both are structural rather than
oversights:

* No governed margin-to-probability conversion exists. The only logistic in the
  V3 tree is :func:`~.sor._reference_win_probability`, an Elo expectation scoped
  to SOR-B and stamped ``not_baxter_rating``. A Baxter conversion would need a
  per-game margin standard deviation, and ``calibration.game_sd_points`` is an
  open blocker -- so the conversion is blocked by the very quantity calibration
  exists to measure. Brier and log loss are implemented and tested here but
  gated behind :class:`ProbabilityConversionAuthority`; no conversion is defined
  in this module and none may be.
* No Colley Matrix implementation is mounted. Colley appears in the V3 tree only
  as the *name* of a witness. The witness machinery below is model agnostic and
  will accept a Colley rating vector the day one exists, but
  :data:`COLLEY_IMPLEMENTATION_MOUNTED` is ``False`` and the Colley witness
  reports unavailable rather than inventing a matrix solve.

Neither gap withholds a Baxter score, and the reason is not politeness -- it is
that blocking on either would be circular. ``game_sd_points`` is to be estimated
*from* out-of-sample residuals once a deterministic mean model exists, so a
probability conversion cannot precede the mean-model search that produces it;
and a witness comparison needs candidate rating state that the same search
produces. :data:`REQUIRED_INPUTS` therefore names only what the criterion
genuinely needs, :data:`OPTIONAL_DOWNSTREAM_INPUTS` names the rest, and an
absent witness emits :data:`WITNESS_UNAVAILABLE` beside a full score sheet.

**Holdout cannot be ranked by accident.** Holdout metrics are not merely
labelled: they sit in a :class:`SealedHoldout` that refuses to yield its
contents without an explicit release token, and :func:`rank_candidates` refuses
the holdout split outside the final designated stage. A worker that tries to
select on holdout raises, rather than quietly returning the best-looking score.

**Tie-breaks are fixed before any result exists.** :data:`TIE_BREAK_POLICY` is a
module constant with a digest (:data:`TIE_BREAK_POLICY_SHA256`) callers can
assert against. Choosing a tie-break after seeing the candidate surface is the
same defect as choosing an objective after seeing it, one order of magnitude
quieter.

Bands, thresholds and phase boundaries declared here (:data:`BLOWOUT_BANDS`,
:data:`LARGE_RESIDUAL_THRESHOLD_POINTS`, :data:`SEASON_PHASES`) are **reporting
conventions for diagnostics, not model parameters and not policy choices**. They
exist so that "candidate A beats candidate B only on blowouts" is a statement
someone can check. Choosing the blowout treatment is a blocker owned elsewhere;
:func:`reject_band_as_blowout_policy` refuses the confusion explicitly.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from .calibration import (
    DATA_SPLITS,
    INDEPENDENT_WITNESSES,
    PRIMARY_CALIBRATION_DIRECTION,
    PRIMARY_CALIBRATION_METRIC,
    EvaluationObjective,
    reject_witness_composite,
    require_primary_objective,
)
from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_CALIBRATION, R2_SRS
from .srs import CANONICAL_SRS_SPEC_MOUNTED, CANONICAL_VALIDATION_BLOCKER

# ---------------------------------------------------------------------------
# Declared conventions. Every one of these is a diagnostic reporting choice.
# None is a model parameter and none may be promoted.
# ---------------------------------------------------------------------------

#: Floats are emitted raw, as everywhere else in this package: determinism comes
#: from exact, order-invariant arithmetic rather than from post-hoc rounding, and
#: a rounded metric would hide the last digits an auditor needs to reproduce a
#: near-tie. The one normalisation applied is ``-0.0`` to ``0.0``
#: (:func:`_report_float`), because the two serialise differently and would give
#: two arithmetically identical records two different digests.
#:
#: One caveat, recorded rather than papered over: every operation used for the
#: primary criterion (``fsum``, ``/``, ``sqrt``) is correctly rounded under
#: IEEE-754 and is therefore bit-identical across platforms. :func:`math.log`, in
#: log loss alone, is not guaranteed correctly rounded and may differ in the last
#: ulp between libm implementations. Log loss is a gated diagnostic, never the
#: ranking criterion, so this cannot move a selection.
LOG_LOSS_PLATFORM_NOTE = "MATH_LOG_LAST_ULP_IS_LIBM_DEPENDENT"

#: Sample-quantile method. Type 7 (linear interpolation between order
#: statistics) is named explicitly because "the 90th percentile" is nine
#: different numbers across nine conventions, and a diagnostic that does not say
#: which one it used is not reproducible.
QUANTILE_METHOD = "linear_interpolation_type7"

#: Residual quantiles reported for every candidate.
RESIDUAL_QUANTILES: tuple[float, ...] = (
    0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99,
)

#: Movement-distribution quantiles. Fixed by the movement-diagnostic contract.
MOVEMENT_QUANTILES: tuple[float, ...] = (0.50, 0.90, 0.95, 0.99)

#: A residual at or beyond this magnitude counts as large. Three scores.
#: REPORT CONVENTION -- it sets what gets counted, not what gets fitted.
LARGE_RESIDUAL_THRESHOLD_POINTS = 21.0

#: Diagnostic bands over ``abs(actual_margin)`` as ``(band_id, low, high)``,
#: ``low`` inclusive and ``high`` exclusive, ``None`` meaning unbounded.
#: Predeclared and fixed, so "which games did this candidate win on" is
#: answerable without anyone choosing a cut after the fact.
#:
#: REPORT CONVENTION. ``calibration.blowout_treatment`` is an open blocker and is
#: neither decided nor prejudged by these bands.
BLOWOUT_BANDS: tuple[tuple[str, float, float | None], ...] = (
    ("margin_00_07", 0.0, 8.0),
    ("margin_08_14", 8.0, 15.0),
    ("margin_15_21", 15.0, 22.0),
    ("margin_22_28", 22.0, 29.0),
    ("margin_29_plus", 29.0, None),
)

#: The boundary used for the three headline blowout scores: a game is
#: "non-blowout" when ``abs(actual_margin) < 22``, the same 21-point edge the
#: bands use, stated once. REPORT CONVENTION.
BLOWOUT_BOUNDARY_POINTS = 22.0

#: Season-phase boundaries over ``week`` as ``(phase_id, low, high)``, ``low``
#: inclusive, ``high`` exclusive, ``None`` unbounded. REPORT CONVENTION.
SEASON_PHASES: tuple[tuple[str, int, int | None], ...] = (
    ("early_season", 1, 5),
    ("midseason", 5, 10),
    ("late_season", 10, None),
)

#: Rank displacement at or beyond which a witness disagreement is flagged for a
#: human to look at. REPORT CONVENTION; a flag is not a finding.
LARGE_RANK_DISAGREEMENT = 25

#: Probabilities are clipped into ``[eps, 1-eps]`` before ``log``. Without it a
#: single confident miss returns infinity and destroys the aggregate, which then
#: reports as "no result" rather than as "one bad game".
LOG_LOSS_EPSILON = 1e-15

#: Reliability-diagram bin count for the ECE diagnostic. Equal width on [0, 1].
RELIABILITY_BIN_COUNT = 10

#: Absolute tolerance for treating a movement as having hit its cap when the
#: producer did not say so explicitly. Points, and deliberately tight: this
#: derives a fact the record should have carried itself.
CAP_HIT_TOLERANCE_POINTS = 1e-9


# ---------------------------------------------------------------------------
# Statuses. Reported, never inferred by a caller from a missing key.
# ---------------------------------------------------------------------------

METRICS_COMPLETE = "METRICS_COMPLETE"
#: The expected state for the first mean-model search: the primary criterion and
#: every secondary margin metric are computed, and only downstream inputs
#: (probability conversion, witness state) are missing. This is a *ready* status,
#: not a degraded one -- see :data:`OPTIONAL_DOWNSTREAM_INPUTS`.
METRICS_PRIMARY_READY = "METRICS_PRIMARY_READY_OPTIONAL_INPUTS_UNAVAILABLE"
METRICS_UNAVAILABLE = "METRICS_UNAVAILABLE_PRIMARY_NOT_COMPUTABLE"

#: What the primary criterion actually needs. Absent any of these, no Baxter
#: score exists and the candidate is unrankable.
REQUIRED_INPUTS: tuple[str, ...] = (
    "accepted_historical_replay_rows",
    "actual_margin",
    "predicted_margin",
    "temporal_train_validation_holdout_identity",
    "candidate_id_and_experiment_bindings",
)

#: Computed from the required inputs alone. Reported for every candidate, and
#: never blocking.
SECONDARY_NON_BLOCKING_METRICS: tuple[str, ...] = (
    "out_of_sample_mae",
    "bias",
    "winner_accuracy",
    "movement_diagnostics",
    "blowout_diagnostics",
    "temporal_stability",
)

#: Downstream of a governed probability conversion or of a witness model that
#: does not exist yet. Their absence is reported and must never withhold a Baxter
#: score: the mean model has to exist before either can be built, so blocking the
#: mean-model search on them would be circular.
OPTIONAL_DOWNSTREAM_INPUTS: tuple[str, ...] = (
    "brier_score",
    "log_loss",
    "probability_calibration",
    "colley_matrix_witness",
    "srs_witness",
)

#: Emitted in place of a witness block's comparison fields. A witness that cannot
#: be computed is reported as unavailable; it never refuses the candidate score.
WITNESS_AVAILABLE = "WITNESS_AVAILABLE"
WITNESS_UNAVAILABLE = "WITNESS_UNAVAILABLE"

#: Named reasons. A caller can branch on these; it cannot branch on prose.
REASON_NO_PROBABILITY_CONVERSION = (
    "PROBABILITY_CONVERSION_NOT_GOVERNED: no governed Baxter margin-to-probability "
    "transform is mounted, and calibration.game_sd_points -- which any such "
    "transform requires -- is an open blocker. Brier, log loss and the "
    "reliability diagnostics are withheld rather than computed from an invented "
    "mapping."
)
REASON_NO_PROBABILITIES_SUPPLIED = (
    "PROBABILITIES_NOT_SUPPLIED: the replay rows carry no predicted_win_probability."
)
REASON_COLLEY_NOT_MOUNTED = (
    "COLLEY_IMPLEMENTATION_NOT_MOUNTED: the V3 tree names the Colley Matrix as an "
    "independent witness but contains no implementation of it. A witness state "
    "must come from the governed model, not from one written here to fill the "
    "field."
)
REASON_NO_WITNESS_SNAPSHOT = (
    "WITNESS_SNAPSHOT_NOT_SUPPLIED: no witness rating state was supplied for this "
    "evaluation boundary."
)
REASON_NO_CANDIDATE_RATING_STATE = (
    "CANDIDATE_RATING_STATE_NOT_SUPPLIED: a witness snapshot was supplied but the "
    "candidate carries no rating state at this evaluation boundary, so there is "
    "nothing to correlate against. Reporting a null correlation as an available "
    "witness would read as 'no agreement found' rather than 'nothing was compared'."
)
REASON_NO_MOVEMENT_RECORDS = (
    "MOVEMENT_RECORDS_NOT_SUPPLIED: no weekly rating-update records accompanied "
    "this candidate, so cap binding cannot be assessed."
)
REASON_NO_OUT_OF_SAMPLE_ROWS = (
    "NO_OUT_OF_SAMPLE_ROWS: the candidate replay contains no rows in the requested "
    "out-of-sample partition."
)

#: Programme state of the historical observation corpus this package will score
#: against. The corpus lane has produced an audited candidate; it is under narrow
#: record/provenance remediation and targeted re-audit, so it is a *candidate*
#: rather than an accepted corpus. This package neither reads nor copies the
#: mutable corpus worktree: it binds one accepted digest at execution time, via
#: :func:`bind_accepted_corpus`, and nothing before then.
CORPUS_INPUT_STATUS = "AUDITED_HISTORICAL_CORPUS_CANDIDATE_PENDING_FINAL_ACCEPTANCE"
CORPUS_CANDIDATE_OBSERVATIONS = 2241
CORPUS_CANDIDATE_SEASONS = "2021-2024"

#: Colley is a named witness with no mounted implementation. Stated as data so a
#: test can assert the state rather than trusting a comment.
COLLEY_IMPLEMENTATION_MOUNTED = False
COLLEY_WITNESS_BLOCKER = "witness.COLLEY_MATRIX_IMPLEMENTATION_NOT_MOUNTED"

#: No governed spread-to-probability mapping exists anywhere in the V3 tree.
PROBABILITY_CONVERSION_MOUNTED = False
PROBABILITY_CONVERSION_BLOCKER = "calibration.game_sd_points"

#: Selection stages. Holdout is scored once, in the final stage, under a token.
STAGE_COARSE = "COARSE"
STAGE_REFINEMENT = "REFINEMENT"
STAGE_FINAL_HOLDOUT = "FINAL_HOLDOUT"
SELECTION_STAGES = (STAGE_COARSE, STAGE_REFINEMENT, STAGE_FINAL_HOLDOUT)

#: The split each stage is permitted to rank on. Coarse and refinement rank on
#: validation; holdout is not a selection surface.
STAGE_RANKING_SPLIT: dict[str, str] = {
    STAGE_COARSE: "validation",
    STAGE_REFINEMENT: "validation",
    STAGE_FINAL_HOLDOUT: "holdout",
}

#: Mirrors the shape of ``calibration._APPROVAL_TOKEN``: releasing holdout is a
#: deliberate, attributable act, not a keyword argument someone flips.
_HOLDOUT_RELEASE_TOKEN = re.compile(r"^RELEASE_V3_CALIBRATION_HOLDOUT::[A-Z0-9_.-]{4,}$")

SEALED = "SEALED_HOLDOUT_NOT_RELEASED"


# ---------------------------------------------------------------------------
# Tie-break policy. Declared here, before any candidate result exists.
# ---------------------------------------------------------------------------

#: Ranking is primary-criterion-first and fully total. Every tier is a
#: minimisation on a quantity that is already being reported, so no tier can be
#: satisfied by a number invented at ranking time.
#:
#: The final tier is ``candidate_id`` ascending. It is not a quality signal; it
#: exists so that two arithmetically indistinguishable candidates still receive a
#: deterministic order instead of one that depends on dictionary insertion.
TIE_BREAK_POLICY: tuple[dict[str, str], ...] = (
    {
        "tier": "0",
        "field": PRIMARY_CALIBRATION_METRIC,
        "direction": PRIMARY_CALIBRATION_DIRECTION,
        "role": "PRIMARY_CRITERION",
        "authority": R2_CALIBRATION.convergence_id,
    },
    {
        "tier": "1",
        "field": "out_of_sample_mae",
        "direction": "minimize",
        "role": "TIE_BREAK",
        "authority": "LANE_DECLARED_BEFORE_RESULTS",
    },
    {
        "tier": "2",
        "field": "absolute_bias",
        "direction": "minimize",
        "role": "TIE_BREAK",
        "authority": "LANE_DECLARED_BEFORE_RESULTS",
    },
    {
        "tier": "3",
        "field": "season_rmse_sd",
        "direction": "minimize",
        "role": "TIE_BREAK_TEMPORAL_STABILITY",
        "authority": "LANE_DECLARED_BEFORE_RESULTS",
    },
    {
        "tier": "4",
        "field": "candidate_id",
        "direction": "ascending_lexicographic",
        "role": "TOTALITY_ONLY_NOT_A_QUALITY_SIGNAL",
        "authority": "LANE_DECLARED_BEFORE_RESULTS",
    },
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(payload: Any) -> str:
    """Canonical serialisation: sorted keys, no incidental whitespace.

    Matches ``calibration_evidence._canonical_digest`` byte for byte so a digest
    taken here and a digest taken there mean the same thing.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def canonical_digest(payload: Any) -> str:
    """SHA-256 over :func:`canonical_json`. Sixty-four lowercase hex characters."""
    return _sha256_bytes(canonical_json(payload).encode("utf-8"))


#: Digest of the tie-break policy as shipped. A shard worker can assert this
#: value and prove the policy it ranked under is the policy that was declared.
TIE_BREAK_POLICY_SHA256 = canonical_digest([dict(t) for t in TIE_BREAK_POLICY])


# ---------------------------------------------------------------------------
# Deterministic numeric primitives.
# ---------------------------------------------------------------------------


def _report_float(value: float | None) -> float | None:
    """Normalise one reported float. ``None`` passes through as ``None``.

    Does not round -- see :data:`LOG_LOSS_PLATFORM_NOTE`. It normalises ``-0.0``
    to ``0.0`` and refuses to emit a non-finite value: a metric that is not a
    number must be reported as unavailable with a named reason, because ``inf``
    in a ranking column sorts, and sorting it would silently rank on nonsense.
    """
    if value is None:
        return None
    if not math.isfinite(value):
        raise InputValidationError(
            f"Refusing to report a non-finite metric value ({value!r}); a metric that "
            "is not a number must be reported as unavailable with a reason, not as inf."
        )
    return value + 0.0


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return math.fsum(values) / len(values)


def _sample_sd(values: Sequence[float]) -> float | None:
    """Sample standard deviation, ``ddof=1``.

    ``ddof=1`` because a candidate's residuals are a sample of its error
    behaviour, not the population of it. With one observation the answer is
    undefined and is reported as ``None`` rather than as zero -- zero would read
    as "perfectly stable" for the case where nothing is known.
    """
    n = len(values)
    if n < 2:
        return None
    mu = math.fsum(values) / n
    return math.sqrt(math.fsum((v - mu) ** 2 for v in values) / (n - 1))


def quantile(sorted_values: Sequence[float], q: float) -> float | None:
    """Type-7 sample quantile of an already-sorted sequence.

    The caller sorts, because every call site here has already sorted for its own
    reasons and re-sorting would be the only non-linear cost in the hot path.
    """
    if not sorted_values:
        return None
    if not 0.0 <= q <= 1.0:
        raise InputValidationError(f"Quantile must lie in [0, 1], got {q!r}")
    n = len(sorted_values)
    if n == 1:
        return float(sorted_values[0])
    pos = (n - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return float(sorted_values[int(pos)])
    frac = pos - lo
    return float(sorted_values[lo]) * (1.0 - frac) + float(sorted_values[hi]) * frac


def _quantile_map(sorted_values: Sequence[float], qs: Sequence[float]) -> dict[str, float | None]:
    """Quantiles keyed by a stable string, so JSON keys do not float-format."""
    return {
        f"p{int(round(q * 100)):02d}": _report_float(quantile(sorted_values, q)) for q in qs
    }


def _skewness(values: Sequence[float]) -> float | None:
    """Fisher-Pearson sample skewness ``g1``.

    ``None`` below three observations, and ``None`` for a degenerate spread: a
    constant residual stream has no skew, and reporting ``0.0`` would be
    indistinguishable from a symmetric one.
    """
    n = len(values)
    if n < 3:
        return None
    mu = math.fsum(values) / n
    m2 = math.fsum((v - mu) ** 2 for v in values) / n
    if m2 <= 0.0:
        return None
    m3 = math.fsum((v - mu) ** 3 for v in values) / n
    return m3 / (m2 ** 1.5)


# ---------------------------------------------------------------------------
# Input contract.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReplayRow:
    """One candidate's prediction for one historical game.

    This is the whole input contract for the primary criterion. It deliberately
    stops at what a *scorer* needs: the fields that produce a prediction --
    pregame ratings, prior rating state, the rating-to-margin transform -- belong
    upstream, and requiring them here would make the metric package a second
    place where the model is specified.

    ``order_index`` is the within-season ordering scalar. ``week`` is reported
    separately because a postseason game has an order but its week label is not
    a week; keeping them apart is what lets season-phase diagnostics abstain on
    rows that have no week rather than binning them as late season.
    """

    candidate_id: str
    game_id: str
    season: int
    order_index: int
    split: str
    actual_margin: float
    predicted_margin: float
    team: str
    opponent: str
    week: int | None = None
    predicted_win_probability: float | None = None
    #: Winner as a team identity. Supplied where the source records it; where it
    #: is absent the sign of ``actual_margin`` is authoritative and this stays
    #: ``None``. It is validated against the margin when both are present, which
    #: is the point of carrying it at all.
    winner: str | None = None
    loser: str | None = None
    #: Optional validation-fold label for cross-validated candidate surfaces.
    fold_id: str | None = None

    def __post_init__(self) -> None:
        split = self.split.strip().lower()
        if split not in DATA_SPLITS:
            raise InputValidationError(
                f"Replay row {self.game_id} for candidate {self.candidate_id} declares "
                f"split {self.split!r}; expected one of {list(DATA_SPLITS)}"
            )
        if split != self.split:
            object.__setattr__(self, "split", split)
        for name in ("actual_margin", "predicted_margin"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                raise InputValidationError(
                    f"Replay row {self.game_id} has non-finite {name}={value!r}"
                )
            object.__setattr__(self, name, float(value))
        if self.team == self.opponent:
            raise InputValidationError(
                f"Replay row {self.game_id} lists {self.team!r} against itself"
            )
        p = self.predicted_win_probability
        if p is not None:
            if not isinstance(p, (int, float)) or not math.isfinite(float(p)):
                raise InputValidationError(
                    f"Replay row {self.game_id} has non-finite "
                    f"predicted_win_probability={p!r}"
                )
            if not 0.0 <= float(p) <= 1.0:
                raise InputValidationError(
                    f"Replay row {self.game_id} has predicted_win_probability={p!r} "
                    "outside [0, 1]"
                )
            object.__setattr__(self, "predicted_win_probability", float(p))
        if self.winner is not None:
            if self.winner not in (self.team, self.opponent):
                raise InputValidationError(
                    f"Replay row {self.game_id} names winner {self.winner!r}, which is "
                    f"neither {self.team!r} nor {self.opponent!r}"
                )
            # A winner that contradicts the margin is not a labelling nit: the
            # margin sign is what winner accuracy is scored against, so a silent
            # disagreement would score the candidate against the wrong outcome.
            implied = self.team if self.actual_margin > 0 else (
                self.opponent if self.actual_margin < 0 else None
            )
            if implied is not None and self.winner != implied:
                raise InputValidationError(
                    f"Replay row {self.game_id} names winner {self.winner!r} but "
                    f"actual_margin={self.actual_margin} implies {implied!r}"
                )
            if self.actual_margin == 0.0:
                raise InputValidationError(
                    f"Replay row {self.game_id} names a winner but records a zero margin"
                )
        if self.loser is not None and self.loser not in (self.team, self.opponent):
            raise InputValidationError(
                f"Replay row {self.game_id} names loser {self.loser!r}, which is neither "
                f"{self.team!r} nor {self.opponent!r}"
            )
        if self.winner is not None and self.loser is not None and self.winner == self.loser:
            raise InputValidationError(
                f"Replay row {self.game_id} names {self.winner!r} as both winner and loser"
            )

    @property
    def residual(self) -> float:
        """``actual - predicted``. Positive means the candidate under-predicted."""
        return self.actual_margin - self.predicted_margin


def row_sort_key(row: ReplayRow) -> tuple[Any, ...]:
    """Total order over replay rows, independent of arrival order.

    ``game_id`` last makes the key total: two rows cannot tie on it within one
    candidate, so a permuted input and a sharded input reduce to the same
    sequence before any arithmetic happens.
    """
    return (row.candidate_id, row.season, row.order_index, row.game_id, row.split)


@dataclass(frozen=True)
class MovementRecord:
    """One weekly rating update for one team under one candidate.

    ``cap_applied`` is what the producer observed; where it is ``None`` the cap
    hit is derived from the magnitude against ``cap_points``. Which of the two
    was used is reported, because a derived cap-hit count is weaker evidence than
    an observed one and the difference should not be invisible.
    """

    candidate_id: str
    team: str
    season: int
    order_index: int
    movement_points: float
    week: int | None = None
    cap_points: float | None = None
    cap_applied: bool | None = None

    def __post_init__(self) -> None:
        if not math.isfinite(float(self.movement_points)):
            raise InputValidationError(
                f"Movement record for {self.team} has non-finite movement_points"
            )
        object.__setattr__(self, "movement_points", float(self.movement_points))
        if self.cap_points is not None:
            cap = float(self.cap_points)
            if not math.isfinite(cap) or cap <= 0.0:
                raise InputValidationError(
                    f"Movement record for {self.team} declares cap_points={self.cap_points!r}; "
                    "a cap must be a positive finite magnitude"
                )
            object.__setattr__(self, "cap_points", cap)


def movement_sort_key(record: MovementRecord) -> tuple[Any, ...]:
    return (
        record.candidate_id,
        record.season,
        record.order_index,
        record.team,
    )


@dataclass(frozen=True)
class WitnessSnapshot:
    """A witness model's rating state as of one evaluation boundary.

    ``as_of`` is an ISO-8601 instant or any lexicographically ordered stamp; it
    is compared as a string, which is why the ordering property matters. The
    boundary check is the whole reason this type exists separately from a plain
    dict of ratings.
    """

    witness_id: str
    as_of: str
    ratings: Mapping[str, float]
    #: ``True`` marks a state that legitimately postdates the evaluation
    #: boundary. Such a comparison is a retrospective study, and is labelled as
    #: one in the output. It is never labelled a pregame witness.
    retrospective: bool = False

    def __post_init__(self) -> None:
        wid = self.witness_id.strip().lower()
        if wid not in INDEPENDENT_WITNESSES:
            raise InputValidationError(
                f"Witness id {self.witness_id!r} is not one of the governed independent "
                f"witnesses {list(INDEPENDENT_WITNESSES)}"
            )
        object.__setattr__(self, "witness_id", wid)
        if not self.as_of:
            raise InputValidationError(
                f"Witness {wid} snapshot carries no as_of; a witness state with no time "
                "cannot be proven to precede the evaluation boundary"
            )
        cleaned = {}
        for team, value in self.ratings.items():
            if not math.isfinite(float(value)):
                raise InputValidationError(
                    f"Witness {wid} rating for {team!r} is non-finite"
                )
            cleaned[team] = float(value)
        object.__setattr__(self, "ratings", dict(sorted(cleaned.items())))


@dataclass(frozen=True)
class ProbabilityConversionAuthority:
    """The governed authority under which supplied probabilities may be scored.

    Presenting one of these does not create a conversion. It asserts that the
    probabilities already on the replay rows came out of a named, governed
    transform upstream. The distinction is the whole fail-closed posture: this
    module never maps a margin to a probability, and without this record it will
    not score probabilities that arrived from nowhere.
    """

    authority_id: str
    transform_name: str
    #: The governance artifact or ruling admitting the transform.
    evidence: str

    def __post_init__(self) -> None:
        for name in ("authority_id", "transform_name", "evidence"):
            if not str(getattr(self, name)).strip():
                raise InputValidationError(
                    f"Probability conversion authority requires a non-empty {name}"
                )


@dataclass(frozen=True)
class CandidateReplay:
    """Everything the oracle needs to score one candidate, and nothing more.

    ``candidate_values`` is carried opaquely and never interpreted. This module
    must be able to report *which* candidate scored what without acquiring an
    opinion about what the values mean -- reading them would be the first step
    toward recommending one.
    """

    candidate_id: str
    rows: tuple[ReplayRow, ...]
    input_dataset_sha: str
    split_sha: str
    experiment_config_sha: str
    candidate_values: Mapping[str, Any] = None  # type: ignore[assignment]
    movement_records: tuple[MovementRecord, ...] = ()
    witness_snapshots: tuple[WitnessSnapshot, ...] = ()
    #: Candidate rating state per evaluation boundary, keyed by ``as_of``. Only
    #: needed for witness comparison; the primary criterion never touches it.
    candidate_rating_states: Mapping[str, Mapping[str, float]] = None  # type: ignore[assignment]
    probability_authority: ProbabilityConversionAuthority | None = None

    def __post_init__(self) -> None:
        if self.candidate_values is None:
            object.__setattr__(self, "candidate_values", {})
        if self.candidate_rating_states is None:
            object.__setattr__(self, "candidate_rating_states", {})
        object.__setattr__(self, "rows", tuple(self.rows))
        object.__setattr__(self, "movement_records", tuple(self.movement_records))
        object.__setattr__(self, "witness_snapshots", tuple(self.witness_snapshots))
        stray = sorted({r.candidate_id for r in self.rows} - {self.candidate_id})
        if stray:
            raise InputValidationError(
                f"CandidateReplay {self.candidate_id} carries rows belonging to {stray}"
            )
        stray_moves = sorted(
            {m.candidate_id for m in self.movement_records} - {self.candidate_id}
        )
        if stray_moves:
            raise InputValidationError(
                f"CandidateReplay {self.candidate_id} carries movement records belonging "
                f"to {stray_moves}"
            )
        seen: dict[tuple[str, str], None] = {}
        for row in self.rows:
            key = (row.split, row.game_id)
            if key in seen:
                raise InputValidationError(
                    f"CandidateReplay {self.candidate_id} repeats game {row.game_id} within "
                    f"split {row.split}; a duplicated observation silently reweights it"
                )
            seen[key] = None
        for name in ("input_dataset_sha", "split_sha", "experiment_config_sha"):
            value = str(getattr(self, name))
            if not value.strip():
                raise InputValidationError(
                    f"CandidateReplay {self.candidate_id} carries no {name}. A score with "
                    "no provenance cannot be compared with another score."
                )


# ---------------------------------------------------------------------------
# Margin metrics. The primary criterion and its companions.
# ---------------------------------------------------------------------------


def _residuals(rows: Sequence[ReplayRow]) -> list[float]:
    """Residuals in canonical row order.

    Ordering here is what makes the whole package shard-invariant, so it happens
    once, in the one place every margin metric goes through.
    """
    return [row.residual for row in sorted(rows, key=row_sort_key)]


def rmse(residuals: Sequence[float]) -> float | None:
    """Root mean squared residual. ``None`` on an empty sample.

    This is the primary criterion. It is defined over residuals rather than over
    rows so that the blowout bands, the season slices and the pooled score are
    provably the same arithmetic applied to different subsets, not three
    similar-looking implementations that could drift apart.
    """
    if not residuals:
        return None
    return math.sqrt(math.fsum(r * r for r in residuals) / len(residuals))


def mae(residuals: Sequence[float]) -> float | None:
    if not residuals:
        return None
    return math.fsum(abs(r) for r in residuals) / len(residuals)


def bias(residuals: Sequence[float]) -> float | None:
    """Mean signed residual, ``actual - predicted``.

    Positive means the candidate systematically under-predicts margin. Reported
    signed, because the direction of a bias is the whole diagnostic; the ranking
    tie-break uses its absolute value and says so.
    """
    return _mean(residuals)


def median_absolute_error(residuals: Sequence[float]) -> float | None:
    if not residuals:
        return None
    return quantile(sorted(abs(r) for r in residuals), 0.5)


def winner_accuracy(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    """Straight-up accuracy, with both awkward cases decided in the open.

    A true tie (``actual_margin == 0``) is excluded from the denominator: there
    is no correct side to have picked, and scoring it either way would be a
    convention masquerading as a measurement. It is counted and reported.

    A candidate that predicts exactly zero margin has declined to pick, and is
    scored **incorrect** rather than excluded. Excluding it would let a model
    raise its accuracy by abstaining, which is the one behaviour a straight-up
    accuracy figure must not reward.
    """
    ordered = sorted(rows, key=row_sort_key)
    correct = 0
    decidable = 0
    ties = 0
    no_pick = 0
    for row in ordered:
        if row.actual_margin == 0.0:
            ties += 1
            continue
        decidable += 1
        if row.predicted_margin == 0.0:
            no_pick += 1
            continue
        if (row.predicted_margin > 0.0) == (row.actual_margin > 0.0):
            correct += 1
    return {
        "correct": correct,
        "decidable_games": decidable,
        "actual_ties_excluded": ties,
        "no_pick_scored_incorrect": no_pick,
        "accuracy": _report_float(correct / decidable) if decidable else None,
        "convention": (
            "true ties excluded from the denominator; a zero predicted margin is "
            "scored incorrect, never excluded"
        ),
    }


def residual_package(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    """The residual stream, described. Not the margin distribution.

    ``residual_sd`` and ``actual_margin_sd`` are both reported and they are not
    the same quantity: the first is the spread of what the candidate got wrong,
    the second is the spread of what happened. A downstream ``game_sd_points``
    fitted to the second would be measuring college football's scoring variance
    and calling it the model's unexplained error. Both appear here, adjacent and
    labelled, precisely so the substitution is visible rather than convenient.
    """
    residuals = _residuals(rows)
    sorted_residuals = sorted(residuals)
    actual = sorted(row.actual_margin for row in rows)
    large = sum(1 for r in residuals if abs(r) >= LARGE_RESIDUAL_THRESHOLD_POINTS)
    return {
        "count": len(residuals),
        "residual_mean": _report_float(_mean(residuals)),
        "residual_sd": _report_float(_sample_sd(residuals)),
        "residual_rmse": _report_float(rmse(residuals)),
        "residual_quantiles": _quantile_map(sorted_residuals, RESIDUAL_QUANTILES),
        "residual_skewness": _report_float(_skewness(residuals)),
        "residual_min": _report_float(sorted_residuals[0]) if sorted_residuals else None,
        "residual_max": _report_float(sorted_residuals[-1]) if sorted_residuals else None,
        "large_residual_threshold_points": LARGE_RESIDUAL_THRESHOLD_POINTS,
        "large_residual_count": large,
        "large_residual_rate": _report_float(large / len(residuals)) if residuals else None,
        # Adjacent, labelled, and explicitly not the residual SD.
        "actual_margin_sd": _report_float(_sample_sd(actual)),
        "residual_sd_is_not_actual_margin_sd": True,
        "game_sd_points_note": (
            "This residual stream is an input to a future game_sd_points "
            "determination. It does not make one. calibration.game_sd_points and "
            "governance.GAME_SD_CALIBRATION_OPEN remain open blockers."
        ),
        "sd_convention": "sample standard deviation, ddof=1",
        "quantile_method": QUANTILE_METHOD,
    }


def reject_actual_margin_sd_as_residual_sd(quantity_name: str) -> None:
    """Refuse the one substitution that would silently corrupt ``game_sd_points``.

    SD of the observed margins is a property of the sport. SD of the residuals is
    a property of the model. They differ by exactly the variance the model
    explains, which is the quantity under calibration -- so swapping them does
    not merely bias the answer, it removes the thing being measured.
    """
    banned = {
        "ACTUAL_MARGIN_SD",
        "MARGIN_SD",
        "SD_ACTUAL_MARGIN",
        "OBSERVED_MARGIN_SD",
    }
    if quantity_name.strip().upper() in banned:
        raise GovernanceBlock(
            f"{quantity_name!r} is the spread of observed margins, not the spread of "
            "residuals, and may not stand in for residual SD or for game_sd_points. "
            f"Ruling {R2_CALIBRATION.convergence_id} keeps the calibration criterion "
            "defined over out-of-sample error; the recorded legacy margin SD of 20.2 is "
            "an engine self-observation and is explicitly not promotable."
        )


# ---------------------------------------------------------------------------
# Score block: one reusable summary applied to every subset.
# ---------------------------------------------------------------------------


def score_block(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    """The same five numbers for any subset of rows.

    Every slice in this module -- pooled, per band, per season, per phase, per
    fold -- routes through here. One implementation means a season score and a
    blowout-band score are comparable by construction rather than by review.
    """
    residuals = _residuals(rows)
    return {
        "games": len(residuals),
        "rmse": _report_float(rmse(residuals)),
        "mae": _report_float(mae(residuals)),
        "bias": _report_float(bias(residuals)),
        "median_absolute_error": _report_float(median_absolute_error(residuals)),
        "residual_sd": _report_float(_sample_sd(residuals)),
        "winner_accuracy": winner_accuracy(rows)["accuracy"],
    }


# ---------------------------------------------------------------------------
# Blowout sensitivity.
# ---------------------------------------------------------------------------


def _band_of(actual_margin: float) -> str:
    magnitude = abs(actual_margin)
    for band_id, low, high in BLOWOUT_BANDS:
        if magnitude >= low and (high is None or magnitude < high):
            return band_id
    # Unreachable while the bands tile [0, inf): the last band is unbounded.
    raise InputValidationError(
        f"Margin magnitude {magnitude} falls outside the declared bands; the band table "
        "no longer tiles the real line."
    )


def blowout_diagnostics(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    """Scores by actual-margin magnitude, on fixed predeclared bands.

    The question this answers is narrow and worth stating: does a candidate's
    advantage survive when the blowouts are removed? A candidate that wins only
    on the tail is winning on the games whose treatment is an open blocker, and
    that is a fact a selection should have in front of it.

    It does not answer which blowout policy to adopt. It cannot: the bands are a
    reporting grid, chosen before any candidate existed and identical for all of
    them.
    """
    ordered = sorted(rows, key=row_sort_key)
    non_blowout = [r for r in ordered if abs(r.actual_margin) < BLOWOUT_BOUNDARY_POINTS]
    large = [r for r in ordered if abs(r.actual_margin) >= BLOWOUT_BOUNDARY_POINTS]
    by_band: dict[str, Any] = {band_id: [] for band_id, _, _ in BLOWOUT_BANDS}
    for row in ordered:
        by_band[_band_of(row.actual_margin)].append(row)
    return {
        "boundary_points": BLOWOUT_BOUNDARY_POINTS,
        "bands": [
            {"band_id": band_id, "low_inclusive": low, "high_exclusive": high}
            for band_id, low, high in BLOWOUT_BANDS
        ],
        "all_games": score_block(ordered),
        "non_blowout": score_block(non_blowout),
        "large_margin": score_block(large),
        "by_band": {band_id: score_block(by_band[band_id]) for band_id in sorted(by_band)},
        "is_a_blowout_policy": False,
        "blowout_policy_blocker": "calibration.blowout_treatment",
    }


def reject_band_as_blowout_policy(claim: str) -> None:
    """Refuse any reading of these bands as a blowout treatment decision."""
    if "POLICY" in claim.strip().upper() or "TREATMENT" in claim.strip().upper():
        raise GovernanceBlock(
            "The diagnostic margin bands in calibration_metrics are a fixed reporting "
            "grid. They are not a blowout treatment, they do not imply one, and "
            "calibration.blowout_treatment remains an open blocker owned elsewhere."
        )


# ---------------------------------------------------------------------------
# Movement diagnostics.
# ---------------------------------------------------------------------------


def movement_diagnostics(records: Sequence[MovementRecord]) -> dict[str, Any]:
    """Distribution of weekly rating movement, and whether the cap ever binds.

    Reported on ``abs(movement)``, because a cap clamps magnitude: a cap that a
    signed mean sits comfortably inside can still be struck every week by
    alternating moves. The signed mean is reported alongside as a drift check,
    not as the cap diagnostic.

    The point of the cap-hit rate is the *zero* case. A cap that never binds is
    not a conservative cap, it is an absent one -- the candidate is
    indistinguishable from the same candidate with no cap at all, and any search
    that treats the two as different points is spending its budget on a
    parameter that does nothing. That is the finding this hands back; what to do
    about it is the search lane's call, and ``calibration.weekly_movement_cap_points``
    stays open regardless.
    """
    if not records:
        return {
            "available": False,
            "unavailable_reason": REASON_NO_MOVEMENT_RECORDS,
            "updates": 0,
        }
    ordered = sorted(records, key=movement_sort_key)
    signed = [r.movement_points for r in ordered]
    magnitudes = sorted(abs(v) for v in signed)

    declared_caps = sorted({r.cap_points for r in ordered if r.cap_points is not None})
    observed_flags = [r for r in ordered if r.cap_applied is not None]
    if observed_flags and len(observed_flags) == len(ordered):
        cap_hits = sum(1 for r in ordered if r.cap_applied)
        source = "OBSERVED_FROM_PRODUCER_FLAG"
    elif declared_caps:
        cap_hits = sum(
            1
            for r in ordered
            if r.cap_points is not None
            and abs(r.movement_points) >= r.cap_points - CAP_HIT_TOLERANCE_POINTS
        )
        source = "DERIVED_FROM_MAGNITUDE_AGAINST_DECLARED_CAP"
    else:
        cap_hits = None
        source = "UNAVAILABLE_NO_CAP_DECLARED_AND_NO_PRODUCER_FLAG"

    max_abs = magnitudes[-1]
    binding: bool | None
    headroom: float | None
    if cap_hits is None:
        binding = None
        headroom = None
    else:
        binding = cap_hits > 0
        headroom = (
            _report_float(min(declared_caps) - max_abs) if declared_caps else None
        )

    return {
        "available": True,
        "updates": len(ordered),
        "mean_abs_movement": _report_float(_mean(magnitudes)),
        "sd_abs_movement": _report_float(_sample_sd(magnitudes)),
        "median_abs_movement": _report_float(quantile(magnitudes, 0.5)),
        "abs_movement_quantiles": _quantile_map(magnitudes, MOVEMENT_QUANTILES),
        "max_abs_movement": _report_float(max_abs),
        "signed_mean_movement": _report_float(_mean(signed)),
        "declared_cap_points": declared_caps,
        "cap_hit_count": cap_hits,
        "cap_hit_rate": (
            _report_float(cap_hits / len(ordered)) if cap_hits is not None else None
        ),
        "cap_hit_source": source,
        "cap_is_binding": binding,
        "cap_headroom_points": headroom,
        "non_binding_cap_detected": binding is False,
        "cap_points_blocker": "calibration.weekly_movement_cap_points",
        "quantile_method": QUANTILE_METHOD,
    }


# ---------------------------------------------------------------------------
# Temporal stability.
# ---------------------------------------------------------------------------


def _phase_of(week: int | None) -> str | None:
    """Season phase for a week, or ``None`` when the row carries no week.

    Abstaining is deliberate. A postseason row has an order but not a week, and
    binning it as late season would put bowl games into a regular-season
    diagnostic -- which is the exact confusion the calibration contract flags
    ``game_type`` as necessary to prevent.
    """
    if week is None:
        return None
    for phase_id, low, high in SEASON_PHASES:
        if week >= low and (high is None or week < high):
            return phase_id
    return None


def temporal_stability(rows: Sequence[ReplayRow]) -> dict[str, Any]:
    """Per season, per season phase, and per validation fold.

    A single pooled RMSE hides the failure mode that matters most here: a
    candidate that is excellent in two seasons and poor in a third pools to the
    same number as one that is mediocre in all three, and only the second is
    actually stable. ``season_rmse_sd`` and ``season_rmse_spread`` surface the
    difference, and the ranking tie-break uses the former.
    """
    ordered = sorted(rows, key=row_sort_key)
    seasons: dict[int, list[ReplayRow]] = {}
    phases: dict[str, list[ReplayRow]] = {p: [] for p, _, _ in SEASON_PHASES}
    unphased: list[ReplayRow] = []
    folds: dict[str, list[ReplayRow]] = {}
    for row in ordered:
        seasons.setdefault(row.season, []).append(row)
        phase = _phase_of(row.week)
        if phase is None:
            unphased.append(row)
        else:
            phases[phase].append(row)
        if row.fold_id is not None:
            folds.setdefault(row.fold_id, []).append(row)

    by_season = {str(s): score_block(seasons[s]) for s in sorted(seasons)}
    season_rmses = [
        block["rmse"] for block in by_season.values() if block["rmse"] is not None
    ]
    return {
        "by_season": by_season,
        "by_phase": {p: score_block(phases[p]) for p in sorted(phases)},
        "rows_without_week": len(unphased),
        "unphased_note": (
            "Rows carrying no week are excluded from the phase diagnostic rather than "
            "binned as late season."
        ),
        "by_validation_fold": {f: score_block(folds[f]) for f in sorted(folds)},
        "season_count": len(seasons),
        "season_rmse_sd": _report_float(_sample_sd(season_rmses)),
        "season_rmse_spread": _report_float(
            max(season_rmses) - min(season_rmses) if season_rmses else None
        ),
        "worst_season_rmse": _report_float(max(season_rmses)) if season_rmses else None,
        "best_season_rmse": _report_float(min(season_rmses)) if season_rmses else None,
        "phase_boundaries": [
            {"phase_id": p, "week_low_inclusive": lo, "week_high_exclusive": hi}
            for p, lo, hi in SEASON_PHASES
        ],
    }


# ---------------------------------------------------------------------------
# Probability diagnostics. Implemented, tested, and gated shut.
# ---------------------------------------------------------------------------


def require_governed_probability_conversion(
    authority: ProbabilityConversionAuthority | None,
) -> ProbabilityConversionAuthority:
    """Fail closed unless a governed conversion authority is presented.

    Modelled on :func:`~.srs.require_canonical_validated_srs`. The arithmetic
    below this gate is ordinary and correct; what is missing is the authority to
    call the numbers it consumes probabilities. No such authority exists today,
    and the reason is structural rather than administrative: a Baxter
    margin-to-probability transform needs a per-game margin standard deviation,
    and ``calibration.game_sd_points`` is one of the open blockers the
    calibration is running to close. Inventing a sigma here to produce a Brier
    score would be scoring the model against an assumption made by the scorer.
    """
    if authority is None:
        raise GovernanceBlock(
            f"{PROBABILITY_CONVERSION_BLOCKER}: {REASON_NO_PROBABILITY_CONVERSION} "
            "Present a ProbabilityConversionAuthority naming the governed transform "
            "that produced these probabilities, or accept that Brier and log loss are "
            "unavailable for this candidate."
        )
    return authority


def brier_score(pairs: Sequence[tuple[float, int]]) -> float | None:
    """Mean squared error of probability against a 0/1 outcome."""
    if not pairs:
        return None
    return math.fsum((p - o) ** 2 for p, o in pairs) / len(pairs)


def log_loss(pairs: Sequence[tuple[float, int]]) -> float | None:
    """Mean negative log likelihood, with probabilities clipped off the bounds."""
    if not pairs:
        return None
    total = math.fsum(
        -(
            math.log(min(max(p, LOG_LOSS_EPSILON), 1.0 - LOG_LOSS_EPSILON))
            if o == 1
            else math.log(min(max(1.0 - p, LOG_LOSS_EPSILON), 1.0 - LOG_LOSS_EPSILON))
        )
        for p, o in pairs
    )
    return total / len(pairs)


def reliability_bins(pairs: Sequence[tuple[float, int]]) -> list[dict[str, Any]]:
    """Equal-width reliability bins over [0, 1]. Empty bins are reported, not dropped.

    An empty bin is information -- it says the candidate never made a prediction
    of that confidence -- and silently omitting it makes a sparse diagram look
    like a complete one.
    """
    bins: list[list[tuple[float, int]]] = [[] for _ in range(RELIABILITY_BIN_COUNT)]
    for p, o in pairs:
        idx = min(int(p * RELIABILITY_BIN_COUNT), RELIABILITY_BIN_COUNT - 1)
        bins[idx].append((p, o))
    out: list[dict[str, Any]] = []
    for idx, bucket in enumerate(bins):
        low = idx / RELIABILITY_BIN_COUNT
        high = (idx + 1) / RELIABILITY_BIN_COUNT
        ordered = sorted(bucket)
        out.append(
            {
                "bin_index": idx,
                "low_inclusive": _report_float(low),
                "high_exclusive": _report_float(high) if idx < RELIABILITY_BIN_COUNT - 1 else 1.0,
                "count": len(ordered),
                "mean_predicted": _report_float(_mean([p for p, _ in ordered])),
                "observed_rate": _report_float(_mean([float(o) for _, o in ordered])),
            }
        )
    return out


def expected_calibration_error(bins: Sequence[Mapping[str, Any]], total: int) -> float | None:
    """Count-weighted mean gap between predicted confidence and observed rate."""
    if not total:
        return None
    return math.fsum(
        b["count"] * abs(b["mean_predicted"] - b["observed_rate"])
        for b in bins
        if b["count"]
    ) / total


def calibration_slope_intercept(
    pairs: Sequence[tuple[float, int]]
) -> tuple[float | None, float | None]:
    """Least-squares fit of outcome on predicted probability.

    A slope near one with an intercept near zero is a calibrated candidate. This
    is the linear-probability form rather than a logistic recalibration: the
    logistic form needs an iterative fit, and an iterative fit that stops on a
    tolerance is a source of platform-dependent last digits in a package that
    otherwise has none. The linear form is closed, exact, and adequate for a
    diagnostic that exists to be eyeballed beside the reliability bins.
    """
    n = len(pairs)
    if n < 2:
        return (None, None)
    ordered = sorted(pairs)
    xs = [p for p, _ in ordered]
    ys = [float(o) for _, o in ordered]
    mx = math.fsum(xs) / n
    my = math.fsum(ys) / n
    sxx = math.fsum((x - mx) ** 2 for x in xs)
    if sxx <= 0.0:
        # Every prediction identical: the slope is undefined, not flat.
        return (None, None)
    sxy = math.fsum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    return (slope, my - slope * mx)


def probability_diagnostics(
    rows: Sequence[ReplayRow],
    authority: ProbabilityConversionAuthority | None,
) -> dict[str, Any]:
    """Brier, log loss and calibration diagnostics -- or a named refusal.

    Three ways this returns unavailable, each distinguishable by the caller:
    no probabilities on the rows, no governed conversion authority, or no
    decidable games. None of them returns a number.

    The outcome scored is ``actual_margin > 0`` -- the subject team winning --
    which is the event the probability on the row is defined over. True ties are
    dropped, as in :func:`winner_accuracy`, for the same reason.
    """
    ordered = sorted(rows, key=row_sort_key)
    with_probability = [r for r in ordered if r.predicted_win_probability is not None]
    base: dict[str, Any] = {
        "available": False,
        "brier_score": None,
        "log_loss": None,
        "reliability_bins": None,
        "expected_calibration_error": None,
        "calibration_slope": None,
        "calibration_intercept": None,
        "governed_conversion_mounted": PROBABILITY_CONVERSION_MOUNTED,
        "conversion_blocker": PROBABILITY_CONVERSION_BLOCKER,
        "rows_carrying_probability": len(with_probability),
    }
    if not with_probability:
        base["unavailable_reason"] = REASON_NO_PROBABILITIES_SUPPLIED
        return base
    if authority is None:
        base["unavailable_reason"] = REASON_NO_PROBABILITY_CONVERSION
        return base

    pairs = [
        (r.predicted_win_probability, 1 if r.actual_margin > 0.0 else 0)
        for r in with_probability
        if r.actual_margin != 0.0
    ]
    if not pairs:
        base["unavailable_reason"] = (
            "NO_DECIDABLE_GAMES: every row carrying a probability records a tie."
        )
        return base

    bins = reliability_bins(pairs)
    slope, intercept = calibration_slope_intercept(pairs)
    base.update(
        {
            "available": True,
            "unavailable_reason": None,
            "scored_games": len(pairs),
            "brier_score": _report_float(brier_score(pairs)),
            "log_loss": _report_float(log_loss(pairs)),
            "reliability_bins": bins,
            "reliability_bin_count": RELIABILITY_BIN_COUNT,
            "expected_calibration_error": _report_float(
                expected_calibration_error(bins, len(pairs))
            ),
            "calibration_slope": _report_float(slope),
            "calibration_intercept": _report_float(intercept),
            "log_loss_epsilon": LOG_LOSS_EPSILON,
            "log_loss_platform_note": LOG_LOSS_PLATFORM_NOTE,
            "conversion_authority_id": authority.authority_id,
            "conversion_transform": authority.transform_name,
            "conversion_evidence": authority.evidence,
            "is_a_selection_criterion": False,
        }
    )
    return base


# ---------------------------------------------------------------------------
# Witnesses. Model-agnostic comparison, plus one hard gate per witness.
# ---------------------------------------------------------------------------


def _ranks(ratings: Mapping[str, float], teams: Sequence[str]) -> dict[str, float]:
    """Competition ranks with ties averaged, best rating first.

    Averaging ties is what keeps Spearman well defined when two teams share a
    rating -- common early in a season, when every unbeaten team sits at the
    same value.
    """
    ordered = sorted(teams, key=lambda t: (-ratings[t], t))
    out: dict[str, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j + 1 < len(ordered) and ratings[ordered[j + 1]] == ratings[ordered[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            out[ordered[k]] = average
        i = j + 1
    return out


def spearman_rank_correlation(
    left: Mapping[str, float], right: Mapping[str, float]
) -> float | None:
    """Pearson correlation of the two average-tie rank vectors over shared teams."""
    teams = sorted(set(left) & set(right))
    if len(teams) < 2:
        return None
    lr = _ranks(left, teams)
    rr = _ranks(right, teams)
    n = len(teams)
    ml = math.fsum(lr[t] for t in teams) / n
    mr = math.fsum(rr[t] for t in teams) / n
    sll = math.fsum((lr[t] - ml) ** 2 for t in teams)
    srr = math.fsum((rr[t] - mr) ** 2 for t in teams)
    if sll <= 0.0 or srr <= 0.0:
        return None
    slr = math.fsum((lr[t] - ml) * (rr[t] - mr) for t in teams)
    return slr / math.sqrt(sll * srr)


def kendall_tau_b(left: Mapping[str, float], right: Mapping[str, float]) -> float | None:
    """Tie-corrected Kendall tau over shared teams, in canonical pair order."""
    teams = sorted(set(left) & set(right))
    n = len(teams)
    if n < 2:
        return None
    concordant = discordant = tied_left = tied_right = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = teams[i], teams[j]
            dl = left[a] - left[b]
            dr = right[a] - right[b]
            if dl == 0.0 and dr == 0.0:
                tied_left += 1
                tied_right += 1
                continue
            if dl == 0.0:
                tied_left += 1
                continue
            if dr == 0.0:
                tied_right += 1
                continue
            if (dl > 0.0) == (dr > 0.0):
                concordant += 1
            else:
                discordant += 1
    pairs = n * (n - 1) / 2
    denominator = math.sqrt((pairs - tied_left) * (pairs - tied_right))
    if denominator <= 0.0:
        return None
    return (concordant - discordant) / denominator


def directional_agreement(
    left: Mapping[str, float], right: Mapping[str, float]
) -> dict[str, Any]:
    """Share of team pairs the two models order the same way.

    Pairs either model calls a tie are excluded from the rate and counted
    separately: a tie is not agreement and it is not disagreement, and folding it
    into either would move the number in whichever direction the caller was
    hoping for.
    """
    teams = sorted(set(left) & set(right))
    n = len(teams)
    agree = disagree = tied = 0
    for i in range(n):
        for j in range(i + 1, n):
            a, b = teams[i], teams[j]
            dl = left[a] - left[b]
            dr = right[a] - right[b]
            if dl == 0.0 or dr == 0.0:
                tied += 1
            elif (dl > 0.0) == (dr > 0.0):
                agree += 1
            else:
                disagree += 1
    decided = agree + disagree
    return {
        "shared_teams": n,
        "pairs_agreeing": agree,
        "pairs_disagreeing": disagree,
        "pairs_tied_excluded": tied,
        "agreement_rate": _report_float(agree / decided) if decided else None,
    }


def large_disagreements(
    left: Mapping[str, float], right: Mapping[str, float]
) -> list[dict[str, Any]]:
    """Teams whose rank differs by at least :data:`LARGE_RANK_DISAGREEMENT`.

    A flag, not a finding: the two models measure different things, so a large
    displacement is expected somewhere. What it is for is spotting the case where
    a candidate's ordering has drifted somewhere no independent model follows.
    """
    teams = sorted(set(left) & set(right))
    if not teams:
        return []
    lr = _ranks(left, teams)
    rr = _ranks(right, teams)
    flagged = [
        {
            "team": t,
            "candidate_rank": _report_float(lr[t]),
            "witness_rank": _report_float(rr[t]),
            "rank_delta": _report_float(abs(lr[t] - rr[t])),
        }
        for t in teams
        if abs(lr[t] - rr[t]) >= LARGE_RANK_DISAGREEMENT
    ]
    return sorted(flagged, key=lambda f: (-f["rank_delta"], f["team"]))


def require_walk_forward_witness(snapshot: WitnessSnapshot, evaluation_as_of: str) -> str:
    """Refuse a witness state that postdates the evaluation boundary.

    Comparing a Week 4 candidate state against a season-final witness and
    reporting the result as a pregame witness is not a small labelling error: the
    witness has seen the outcomes the candidate is being scored on, so the
    comparison measures hindsight and reads as agreement. A genuinely
    retrospective study is legitimate, and is admitted here -- but only by
    setting ``retrospective`` on the snapshot, and the returned label says so for
    the rest of the record's life.
    """
    if snapshot.as_of <= evaluation_as_of:
        return "WALK_FORWARD"
    if snapshot.retrospective:
        return "RETROSPECTIVE_NOT_A_PREGAME_WITNESS"
    raise GovernanceBlock(
        f"Witness {snapshot.witness_id} state is as of {snapshot.as_of}, which is after "
        f"the evaluation boundary {evaluation_as_of}. A witness that has already seen the "
        "outcomes under evaluation is not a pregame witness. Supply walk-forward state, "
        "or mark the snapshot retrospective and accept that label on the output."
    )


def witness_comparison(
    candidate_ratings: Mapping[str, float],
    snapshot: WitnessSnapshot,
    evaluation_as_of: str,
) -> dict[str, Any]:
    """Compare one candidate rating state against one witness state.

    Correlations and agreement rates only. No blend, no composite, no combined
    score -- :func:`~.calibration.reject_witness_composite` is called on the way
    in, so a caller that tries to route a blend through this function is refused
    by the same gate that refuses it everywhere else.
    """
    reject_witness_composite([snapshot.witness_id])
    temporal_label = require_walk_forward_witness(snapshot, evaluation_as_of)
    ratings = {t: float(v) for t, v in candidate_ratings.items()}
    if not ratings:
        raise InputValidationError(REASON_NO_CANDIDATE_RATING_STATE)
    shared = sorted(set(ratings) & set(snapshot.ratings))
    return {
        "witness_id": snapshot.witness_id,
        "witness_as_of": snapshot.as_of,
        "evaluation_as_of": evaluation_as_of,
        "temporal_validity": temporal_label,
        "retrospective": bool(snapshot.retrospective),
        "shared_teams": len(shared),
        "candidate_only_teams": sorted(set(ratings) - set(snapshot.ratings)),
        "witness_only_teams": sorted(set(snapshot.ratings) - set(ratings)),
        "spearman_rank_correlation": _report_float(
            spearman_rank_correlation(ratings, snapshot.ratings)
        ),
        "kendall_tau_b": _report_float(kendall_tau_b(ratings, snapshot.ratings)),
        "directional_agreement": directional_agreement(ratings, snapshot.ratings),
        "large_disagreement_threshold": LARGE_RANK_DISAGREEMENT,
        "large_disagreements": large_disagreements(ratings, snapshot.ratings),
        "is_blended_into_primary_criterion": False,
        "role": "INDEPENDENT_WITNESS",
    }


def srs_witness(
    candidate_ratings: Mapping[str, float],
    snapshot: WitnessSnapshot | None,
    evaluation_as_of: str,
) -> dict[str, Any]:
    """SRS witness comparison, carrying the SRS authority boundary forward.

    :mod:`.srs` solves the governed capped-margin system exactly, and that much
    is verified. What is not verified is agreement with a canonical SRS
    implementation or its historical anchors, because neither is mounted. Any
    number derived from SRS therefore travels with
    ``NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS`` attached, exactly as
    :func:`~.srs.witness_as_dict` stamps it -- so a rank correlation computed
    here cannot be cited downstream as canonical-anchor validation of anything.
    """
    boundary = {
        "witness_id": "srs",
        "ruling": R2_SRS.convergence_id,
        "canonical_spec_mounted": CANONICAL_SRS_SPEC_MOUNTED,
        "canonical_validation_status": "NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS",
        "canonical_validation_blocker": CANONICAL_VALIDATION_BLOCKER,
        "authority_boundary_preserved": True,
    }
    if snapshot is None:
        return {
            **boundary,
            "available": False,
            "witness_status": WITNESS_UNAVAILABLE,
            "unavailable_reason": REASON_NO_WITNESS_SNAPSHOT,
        }
    if snapshot.witness_id != "srs":
        raise InputValidationError(
            f"srs_witness received a {snapshot.witness_id!r} snapshot"
        )
    if not candidate_ratings:
        return {
            **boundary,
            "available": False,
            "witness_status": WITNESS_UNAVAILABLE,
            "unavailable_reason": REASON_NO_CANDIDATE_RATING_STATE,
        }
    return {
        **boundary,
        "available": True,
        "witness_status": WITNESS_AVAILABLE,
        "unavailable_reason": None,
        **witness_comparison(candidate_ratings, snapshot, evaluation_as_of),
    }


def colley_witness(
    candidate_ratings: Mapping[str, float],
    snapshot: WitnessSnapshot | None,
    evaluation_as_of: str,
) -> dict[str, Any]:
    """Colley witness comparison -- unavailable, because Colley is unimplemented.

    ``INDEPENDENT_WITNESSES`` names ``colley_matrix``; the V3 tree contains no
    implementation of it, only the name. The comparison machinery above is
    model-agnostic and will produce a full Colley witness block the moment a
    governed Colley state is supplied, which is why the snapshot path is live
    rather than stubbed. What this function will not do is solve a Colley system
    of its own to fill the field: a witness written by the scorer is not
    independent of the scorer, and an independent witness is the entire point.
    """
    boundary = {
        "witness_id": "colley_matrix",
        "implementation_mounted": COLLEY_IMPLEMENTATION_MOUNTED,
        "blocker": COLLEY_WITNESS_BLOCKER,
        "authority_boundary_preserved": True,
    }
    if snapshot is None:
        return {
            **boundary,
            "available": False,
            "witness_status": WITNESS_UNAVAILABLE,
            "unavailable_reason": REASON_COLLEY_NOT_MOUNTED,
        }
    if snapshot.witness_id != "colley_matrix":
        raise InputValidationError(
            f"colley_witness received a {snapshot.witness_id!r} snapshot"
        )
    if not candidate_ratings:
        return {
            **boundary,
            "available": False,
            "witness_status": WITNESS_UNAVAILABLE,
            "unavailable_reason": REASON_NO_CANDIDATE_RATING_STATE,
        }
    # A governed Colley state supplied from outside is admissible; one computed
    # here would not be. The distinction is the source, not the arithmetic.
    return {
        **boundary,
        "available": True,
        "witness_status": WITNESS_AVAILABLE,
        "unavailable_reason": None,
        "state_source": "SUPPLIED_BY_CALLER_NOT_COMPUTED_HERE",
        **witness_comparison(candidate_ratings, snapshot, evaluation_as_of),
    }


def require_no_colley_implementation_here(_name: str = "") -> None:
    """Fail closed on any attempt to have this module compute a Colley rating.

    Modelled on :func:`~.srs.require_canonical_validated_srs`: an unconditional
    refusal, present so that the absence is a gate rather than an omission
    somebody later fills in without noticing what it cost.
    """
    raise GovernanceBlock(
        f"{COLLEY_WITNESS_BLOCKER}: {REASON_COLLEY_NOT_MOUNTED} The metrics package "
        "compares against a supplied witness state; it does not become the witness."
    )


# ---------------------------------------------------------------------------
# Holdout discipline. A mechanism, not a convention.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SealedHoldout:
    """Holdout metrics that will not come out without an explicit release token.

    A label saying "this is holdout" prevents nothing: the number is still
    sitting in the record, one dictionary lookup from a sort key. This wraps it
    so the only way to read it is :meth:`open`, and the only way to call
    :meth:`open` is to have written the release token down. The token is
    attributable, which is the property that makes the release a decision
    somebody made rather than a default somebody inherited.

    :meth:`as_dict` emits :data:`SEALED` in place of the payload, so serialising
    a candidate record for a coarse-stage worker cannot leak the holdout score
    through the artifact either.
    """

    payload: Mapping[str, Any]
    released: bool = False

    def open(self, release_token: str) -> Mapping[str, Any]:
        """Return the holdout metrics, or refuse."""
        if not isinstance(release_token, str) or not _HOLDOUT_RELEASE_TOKEN.match(
            release_token
        ):
            raise GovernanceBlock(
                "Holdout metrics require an explicit release token of the form "
                "RELEASE_V3_CALIBRATION_HOLDOUT::<IDENTIFIER>. Holdout is scored once, "
                "in the final designated stage, and the release is recorded against "
                f"whoever made it. Ruling {R2_CALIBRATION.convergence_id} keeps training, "
                "validation and holdout separated."
            )
        return dict(self.payload)

    def as_dict(self) -> dict[str, Any]:
        return {"holdout": SEALED, "release_required": True}


def require_holdout_release(release_token: str | None) -> str:
    """Validate a holdout release token, or fail closed."""
    if release_token is None or not _HOLDOUT_RELEASE_TOKEN.match(str(release_token)):
        raise GovernanceBlock(
            f"Holdout release requires a token matching "
            f"{_HOLDOUT_RELEASE_TOKEN.pattern!r}; got {release_token!r}."
        )
    return str(release_token)


def require_selection_stage(stage: str) -> str:
    if stage not in SELECTION_STAGES:
        raise InputValidationError(
            f"Selection stage {stage!r} is not one of {list(SELECTION_STAGES)}"
        )
    return stage


# ---------------------------------------------------------------------------
# The candidate metric record.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CandidateMetricRecord:
    """One candidate's complete, deterministic score sheet.

    ``primary_metric_value`` is the out-of-sample RMSE on the ranking split, and
    it is named after :data:`~.calibration.PRIMARY_CALIBRATION_METRIC` in
    :meth:`as_dict` rather than under a local alias, so a downstream consumer
    reading the governed key finds the governed quantity.

    Holdout never appears in the ranking fields. It is reachable only through
    :attr:`sealed_holdout`.
    """

    candidate_id: str
    #: The out-of-sample partition these headline numbers were measured on.
    evaluation_split: str
    primary_metric: str
    primary_metric_value: float | None
    out_of_sample_mae: float | None
    bias: float | None
    absolute_bias: float | None
    winner_accuracy: dict[str, Any]
    residuals: dict[str, Any]
    blowout: dict[str, Any]
    movement: dict[str, Any]
    temporal: dict[str, Any]
    probability: dict[str, Any]
    colley_witness: dict[str, Any]
    srs_witness: dict[str, Any]
    by_split: dict[str, Any]
    sealed_holdout: SealedHoldout
    candidate_values: Mapping[str, Any]
    input_dataset_sha: str
    split_sha: str
    experiment_config_sha: str
    status: str
    #: True when the Baxter out-of-sample RMSE exists. This, and not
    #: :attr:`status`, is what decides whether a candidate can be ranked.
    primary_selection_ready: bool = False
    #: Reasons the primary criterion does not exist. Empty whenever
    #: :attr:`primary_selection_ready` is true.
    failure_reasons: tuple[str, ...] = ()
    #: Optional or downstream inputs that were absent. Reported, never blocking.
    non_blocking_reasons: tuple[str, ...] = ()

    @property
    def witness_status(self) -> dict[str, str]:
        """Per-witness availability, so a consumer need not infer it."""
        return {
            "colley_matrix": self.colley_witness.get("witness_status", WITNESS_UNAVAILABLE),
            "srs": self.srs_witness.get("witness_status", WITNESS_UNAVAILABLE),
        }

    @property
    def season_rmse_sd(self) -> float | None:
        """Temporal-instability tie-break input. ``None`` under two seasons."""
        return self.temporal.get("season_rmse_sd")

    def as_dict(self) -> dict[str, Any]:
        """Deterministic, JSON-native, holdout-safe."""
        return {
            "candidate_id": self.candidate_id,
            "evaluation_split": self.evaluation_split,
            "primary_metric": self.primary_metric,
            self.primary_metric: self.primary_metric_value,
            "out_of_sample_mae": self.out_of_sample_mae,
            "bias": self.bias,
            "absolute_bias": self.absolute_bias,
            "winner_accuracy": dict(self.winner_accuracy),
            "residuals": dict(self.residuals),
            "blowout_diagnostics": dict(self.blowout),
            "movement_diagnostics": dict(self.movement),
            "temporal_stability": dict(self.temporal),
            "season_rmse_sd": self.season_rmse_sd,
            "probability_diagnostics": dict(self.probability),
            "brier_score": self.probability.get("brier_score"),
            "log_loss": self.probability.get("log_loss"),
            "colley_witness": dict(self.colley_witness),
            "srs_witness": dict(self.srs_witness),
            "by_split": {k: dict(v) for k, v in sorted(self.by_split.items())},
            "holdout": self.sealed_holdout.as_dict(),
            "candidate_values": dict(sorted(self.candidate_values.items())),
            "input_dataset_sha": self.input_dataset_sha,
            "split_sha": self.split_sha,
            "experiment_config_sha": self.experiment_config_sha,
            "status": self.status,
            "primary_selection_ready": self.primary_selection_ready,
            "failure_reasons": list(self.failure_reasons),
            "non_blocking_reasons": list(self.non_blocking_reasons),
            "witness_status": dict(self.witness_status),
            "witnesses_required_for_primary_selection": False,
            "corpus_input_status": CORPUS_INPUT_STATUS,
            "tie_break_policy_sha256": TIE_BREAK_POLICY_SHA256,
            "primary_direction": PRIMARY_CALIBRATION_DIRECTION,
            "ruling": R2_CALIBRATION.convergence_id,
            "witness_composite_authorised": False,
            "parameters_promoted": False,
        }

    def digest(self) -> str:
        """SHA-256 over :meth:`as_dict`. Stable across runs, shards and orders."""
        return canonical_digest(self.as_dict())


#: The keys :meth:`CandidateMetricRecord.as_dict` always emits, in sorted order.
#: Published so a consumer can assert the schema rather than discover it.
RESULT_SCHEMA_KEYS: tuple[str, ...] = tuple(
    sorted(
        {
            "candidate_id",
            "evaluation_split",
            "primary_metric",
            PRIMARY_CALIBRATION_METRIC,
            "out_of_sample_mae",
            "bias",
            "absolute_bias",
            "winner_accuracy",
            "residuals",
            "blowout_diagnostics",
            "movement_diagnostics",
            "temporal_stability",
            "season_rmse_sd",
            "probability_diagnostics",
            "brier_score",
            "log_loss",
            "colley_witness",
            "srs_witness",
            "by_split",
            "holdout",
            "candidate_values",
            "input_dataset_sha",
            "split_sha",
            "experiment_config_sha",
            "status",
            "primary_selection_ready",
            "failure_reasons",
            "non_blocking_reasons",
            "witness_status",
            "witnesses_required_for_primary_selection",
            "corpus_input_status",
            "tie_break_policy_sha256",
            "primary_direction",
            "ruling",
            "witness_composite_authorised",
            "parameters_promoted",
        }
    )
)


# ---------------------------------------------------------------------------
# Evaluation.
# ---------------------------------------------------------------------------


def evaluate_candidate(
    replay: CandidateReplay,
    *,
    evaluation_split: str = "validation",
    evaluation_as_of: str | None = None,
) -> CandidateMetricRecord:
    """Score one candidate. Deterministic, order-invariant, side-effect free.

    ``evaluation_split`` is the out-of-sample partition the headline numbers are
    measured on. It defaults to ``validation`` and refuses ``training``
    outright: an in-sample RMSE is not the primary criterion, and letting it be
    requested through the same argument that requests the real one is how the
    substitution happens.

    Holdout may be *computed* here -- it has to be, for the final stage to have
    anything to release -- but it is sealed on the way out and
    :func:`rank_candidates` will not rank on it outside the final stage.
    """
    split = evaluation_split.strip().lower()
    if split == "training":
        raise GovernanceBlock(
            f"Ruling {R2_CALIBRATION.convergence_id} names "
            f"{PRIMARY_CALIBRATION_METRIC} -- an out-of-sample criterion. Refusing to "
            "report a training-split score as the primary metric. Training metrics are "
            "available under by_split for diagnosis, and are not rankable."
        )
    if split not in DATA_SPLITS:
        raise InputValidationError(
            f"evaluation_split {evaluation_split!r} is not one of {list(DATA_SPLITS)}"
        )

    ordered = sorted(replay.rows, key=row_sort_key)
    by_split_rows: dict[str, list[ReplayRow]] = {s: [] for s in DATA_SPLITS}
    for row in ordered:
        by_split_rows[row.split].append(row)
    target = by_split_rows[split]

    # Blocking reasons stop the primary criterion existing. Non-blocking ones
    # describe an optional or downstream input that is absent. Conflating them
    # is what would let a missing witness -- a model that cannot be built until
    # after this calibration produces a mean model -- withhold the very score
    # that calibration needs.
    blocking: list[str] = []
    non_blocking: list[str] = []
    if not target:
        blocking.append(REASON_NO_OUT_OF_SAMPLE_ROWS)

    residuals = _residuals(target)
    primary = rmse(residuals)
    mean_error = bias(residuals)

    probability = probability_diagnostics(target, replay.probability_authority)
    if not probability["available"]:
        non_blocking.append(probability["unavailable_reason"])

    movement = movement_diagnostics(replay.movement_records)
    if not movement["available"]:
        non_blocking.append(movement["unavailable_reason"])

    # Witness comparison needs a boundary. Absent an explicit one the latest row
    # in the evaluated partition is the boundary, which is the tightest defensible
    # default: any witness state at or before the last evaluated game is
    # walk-forward with respect to the whole partition.
    boundary = evaluation_as_of
    if boundary is None:
        boundary = (
            f"{target[-1].season:04d}-{target[-1].order_index:04d}" if target else "0000-0000"
        )
    candidate_state = replay.candidate_rating_states.get(boundary, {})
    snapshots = {s.witness_id: s for s in replay.witness_snapshots}

    def _witness(fn, witness_id):
        """Compute a witness block, degrading a refusal to WITNESS_UNAVAILABLE.

        The leakage gate stays hard for anyone calling
        :func:`require_walk_forward_witness` or :func:`witness_comparison`
        directly -- a witness that has seen the outcomes is still refused, and
        loudly. What changes here is only the blast radius: inside candidate
        scoring the refusal degrades that one witness block instead of taking
        the Baxter score down with it. A witness problem is not a reason to have
        no primary criterion.
        """
        try:
            return fn(candidate_state, snapshots.get(witness_id), boundary)
        except (GovernanceBlock, InputValidationError) as err:
            return {
                "witness_id": witness_id,
                "available": False,
                "witness_status": WITNESS_UNAVAILABLE,
                "unavailable_reason": f"WITNESS_REFUSED: {err}",
                "authority_boundary_preserved": True,
                "blocked_primary_selection": False,
            }

    colley = _witness(colley_witness, "colley_matrix")
    if not colley["available"]:
        non_blocking.append(colley["unavailable_reason"])
    srs = _witness(srs_witness, "srs")
    if not srs["available"]:
        non_blocking.append(srs["unavailable_reason"])

    # Status turns on the primary criterion alone. Optional and downstream gaps
    # are reported, never promoted into a failure.
    primary_ready = bool(target) and primary is not None
    if not primary_ready:
        status = METRICS_UNAVAILABLE
    elif non_blocking:
        status = METRICS_PRIMARY_READY
    else:
        status = METRICS_COMPLETE

    return CandidateMetricRecord(
        candidate_id=replay.candidate_id,
        evaluation_split=split,
        primary_metric=PRIMARY_CALIBRATION_METRIC,
        primary_metric_value=_report_float(primary),
        out_of_sample_mae=_report_float(mae(residuals)),
        bias=_report_float(mean_error),
        absolute_bias=_report_float(abs(mean_error) if mean_error is not None else None),
        winner_accuracy=winner_accuracy(target),
        residuals=residual_package(target),
        blowout=blowout_diagnostics(target),
        movement=movement,
        temporal=temporal_stability(target),
        probability=probability,
        colley_witness=colley,
        srs_witness=srs,
        # Holdout is present as a key and sealed as a value. Emitting a real
        # score_block here would hand the holdout RMSE to every consumer of
        # by_split -- the same leak the sealed container exists to close, one
        # dictionary lookup further away and therefore easier to take by
        # accident. Training and validation stay visible: they are what
        # by_split is for.
        by_split={
            s: (score_block(by_split_rows[s]) if s != "holdout" else {"holdout": SEALED})
            for s in DATA_SPLITS
        },
        sealed_holdout=SealedHoldout(
            payload={
                "split": "holdout",
                **score_block(by_split_rows["holdout"]),
                "residuals": residual_package(by_split_rows["holdout"]),
                "temporal_stability": temporal_stability(by_split_rows["holdout"]),
            }
        ),
        candidate_values=dict(replay.candidate_values),
        input_dataset_sha=replay.input_dataset_sha,
        split_sha=replay.split_sha,
        experiment_config_sha=replay.experiment_config_sha,
        status=status,
        primary_selection_ready=primary_ready,
        failure_reasons=tuple(sorted(set(blocking))),
        non_blocking_reasons=tuple(sorted(set(non_blocking))),
    )


def evaluate_candidates(
    replays: Iterable[CandidateReplay],
    *,
    evaluation_split: str = "validation",
    evaluation_as_of: str | None = None,
) -> tuple[CandidateMetricRecord, ...]:
    """Score many candidates, returned in ``candidate_id`` order.

    The return order is canonical rather than input order, which is what makes a
    sharded run and a single-process run produce the same tuple.
    """
    records = [
        evaluate_candidate(
            replay,
            evaluation_split=evaluation_split,
            evaluation_as_of=evaluation_as_of,
        )
        for replay in replays
    ]
    seen: set[str] = set()
    for record in records:
        if record.candidate_id in seen:
            raise InputValidationError(
                f"Candidate {record.candidate_id} was evaluated twice in one batch"
            )
        seen.add(record.candidate_id)
    return tuple(sorted(records, key=lambda r: r.candidate_id))


def merge_shard_results(
    shards: Iterable[Sequence[CandidateMetricRecord]],
) -> tuple[CandidateMetricRecord, ...]:
    """Merge per-shard result sets into the single canonical result set.

    Refuses a candidate that appears in two shards. Silently keeping one of the
    two would make the merged answer depend on shard iteration order, which is
    the exact property the sharding is required not to have -- and it would hide
    a partitioning bug behind a plausible result.
    """
    merged: dict[str, CandidateMetricRecord] = {}
    for shard in shards:
        for record in shard:
            existing = merged.get(record.candidate_id)
            if existing is not None:
                raise InputValidationError(
                    f"Candidate {record.candidate_id} appears in more than one shard. "
                    "Shards must partition the candidate set, not overlap it."
                )
            merged[record.candidate_id] = record
    return tuple(merged[c] for c in sorted(merged))


# ---------------------------------------------------------------------------
# Ranking.
# ---------------------------------------------------------------------------


def _rank_key(record: CandidateMetricRecord) -> tuple[Any, ...]:
    """The tie-break hierarchy in :data:`TIE_BREAK_POLICY`, as a sort key.

    Unscored candidates sort last on every tier via a leading availability flag,
    rather than by substituting ``inf`` for their missing metric. An ``inf``
    would participate in the arithmetic tiers and could tie two candidates that
    failed for different reasons; the flag keeps "no score" outside the ordering
    entirely.
    """
    def _or_last(value: float | None) -> tuple[int, float]:
        return (1, 0.0) if value is None else (0, value)

    return (
        _or_last(record.primary_metric_value),
        _or_last(record.out_of_sample_mae),
        _or_last(record.absolute_bias),
        _or_last(record.season_rmse_sd),
        record.candidate_id,
    )


def rank_candidates(
    records: Sequence[CandidateMetricRecord],
    *,
    stage: str,
    objective: EvaluationObjective | None,
    holdout_release_token: str | None = None,
) -> tuple[CandidateMetricRecord, ...]:
    """Deterministic ranking under the governed criterion. Best first.

    Three gates, in order:

    1. :func:`~.calibration.require_primary_objective` -- the objective must be
       the governed one. A caller cannot rank on a metric it picked.
    2. The stage must permit the split these records were scored on.
       :data:`STAGE_RANKING_SPLIT` maps coarse and refinement to ``validation``;
       only :data:`STAGE_FINAL_HOLDOUT` maps to ``holdout``, and it additionally
       requires a release token. This is the explicit mechanism preventing
       accidental holdout ranking: a coarse-stage worker holding a set of
       holdout-scored records is refused rather than served.
    3. Records must agree on the split they were scored on, mirroring
       :func:`~.calibration.rank_experiments_governed` -- a validation score and
       a holdout score are not comparable and must not be sorted together.
    """
    require_primary_objective(objective)
    require_selection_stage(stage)
    if not records:
        return ()

    splits = {r.evaluation_split for r in records}
    if len(splits) > 1:
        raise GovernanceBlock(
            f"Refusing to rank across mixed splits {sorted(splits)}; scores from "
            "different partitions are not comparable."
        )
    scored_split = splits.pop()
    permitted = STAGE_RANKING_SPLIT[stage]
    if scored_split != permitted:
        raise GovernanceBlock(
            f"Stage {stage} ranks on the {permitted!r} split; these records were scored "
            f"on {scored_split!r}. Holdout is scored once, in {STAGE_FINAL_HOLDOUT}, and "
            "is not a coarse or refinement selection surface."
        )
    if scored_split == "holdout":
        require_holdout_release(holdout_release_token)

    return tuple(sorted(records, key=_rank_key))


def ranking_interface_as_dict() -> dict[str, Any]:
    """The scoring oracle's contract, as a reviewable payload.

    Agent 3 asserts this. If any of it has moved, the shard workers are not
    ranking under the criterion this lane declared, and the assertion fails
    before a candidate surface exists rather than after one has been chosen.
    """
    return {
        "ruling": R2_CALIBRATION.convergence_id,
        "primary_metric": PRIMARY_CALIBRATION_METRIC,
        "primary_direction": PRIMARY_CALIBRATION_DIRECTION,
        "tie_break_policy": [dict(t) for t in TIE_BREAK_POLICY],
        "tie_break_policy_sha256": TIE_BREAK_POLICY_SHA256,
        "tie_breaks_declared_before_results": True,
        "selection_stages": list(SELECTION_STAGES),
        "stage_ranking_split": dict(sorted(STAGE_RANKING_SPLIT.items())),
        "holdout_release_token_pattern": _HOLDOUT_RELEASE_TOKEN.pattern,
        "holdout_sealed_by_default": True,
        "training_split_rankable": False,
        "independent_witnesses": list(INDEPENDENT_WITNESSES),
        "witness_composite_authorised": False,
        "witnesses_blended_into_primary": False,
        "colley_implementation_mounted": COLLEY_IMPLEMENTATION_MOUNTED,
        "colley_blocker": COLLEY_WITNESS_BLOCKER,
        "srs_canonical_spec_mounted": CANONICAL_SRS_SPEC_MOUNTED,
        "srs_canonical_validation_blocker": CANONICAL_VALIDATION_BLOCKER,
        "probability_conversion_mounted": PROBABILITY_CONVERSION_MOUNTED,
        "probability_conversion_blocker": PROBABILITY_CONVERSION_BLOCKER,
        "result_schema_keys": list(RESULT_SCHEMA_KEYS),
        "diagnostic_conventions": {
            "blowout_bands": [
                {"band_id": b, "low_inclusive": lo, "high_exclusive": hi}
                for b, lo, hi in BLOWOUT_BANDS
            ],
            "blowout_boundary_points": BLOWOUT_BOUNDARY_POINTS,
            "large_residual_threshold_points": LARGE_RESIDUAL_THRESHOLD_POINTS,
            "season_phases": [
                {"phase_id": p, "week_low_inclusive": lo, "week_high_exclusive": hi}
                for p, lo, hi in SEASON_PHASES
            ],
            "residual_quantiles": list(RESIDUAL_QUANTILES),
            "movement_quantiles": list(MOVEMENT_QUANTILES),
            "quantile_method": QUANTILE_METHOD,
            "sd_convention": "sample standard deviation, ddof=1",
            "large_rank_disagreement": LARGE_RANK_DISAGREEMENT,
            "are_model_parameters": False,
            "are_policy_choices": False,
        },
        "shard_invariant": True,
        "order_invariant": True,
        "parameters_promoted": False,
        "recommends_a_candidate": False,
        # Composition. Workers score; central aggregation ranks. A worker that
        # ranks locally has, by construction, chosen a selection criterion.
        "workers_score_only": True,
        "ranking_is_central": True,
        "worker_may_redefine_primary_objective": False,
        "worker_may_redefine_tie_breaks": False,
        "worker_may_redefine_holdout_policy": False,
        "worker_may_redefine_witness_role": False,
        # Input classification for the first mean-model search.
        "required_inputs": list(REQUIRED_INPUTS),
        "secondary_non_blocking_metrics": list(SECONDARY_NON_BLOCKING_METRICS),
        "optional_downstream_inputs": list(OPTIONAL_DOWNSTREAM_INPUTS),
        "witnesses_required_for_primary_selection": False,
        "witness_unavailable_sentinel": WITNESS_UNAVAILABLE,
        "corpus_input_status": CORPUS_INPUT_STATUS,
    }


#: Digest over everything a shard worker must not vary: the criterion, the
#: tie-break hierarchy, the stage/holdout policy, the witness roles, the
#: diagnostic conventions and the emitted schema. Frozen at CAL-METRICS-R1.
#:
#: The tie-break digest alone would not catch a worker that kept the tie-breaks
#: and moved a band edge or a stage mapping. This covers the whole oracle, so
#: "are we all scoring the same way" is one comparison rather than a review.
ORACLE_FREEZE_ID = "CAL-METRICS-R1"
ORACLE_FREEZE_SHA256 = canonical_digest(ranking_interface_as_dict())


def require_frozen_oracle(expected_sha256: str) -> dict[str, Any]:
    """Fail closed unless this process carries the frozen scoring oracle.

    Agent 3 asserts this once, before fanning out. A worker running an altered
    oracle is detected before its scores enter the merge, rather than after a
    candidate has been selected under arithmetic nobody compared.
    """
    actual = canonical_digest(ranking_interface_as_dict())
    if expected_sha256 != actual:
        raise GovernanceBlock(
            f"Scoring oracle digest mismatch: expected {expected_sha256}, this process "
            f"computes {actual}. The frozen evaluation oracle is {ORACLE_FREEZE_ID}; a "
            "candidate scored under a different one is not comparable with the rest of "
            "the search and must not be merged into it."
        )
    return {
        "freeze_id": ORACLE_FREEZE_ID,
        "oracle_sha256": actual,
        "tie_break_policy_sha256": TIE_BREAK_POLICY_SHA256,
        "verified": True,
    }


_SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")

#: Markers that must never be accepted as an accepted-corpus digest. The corpus
#: lane's worktree is mutable and under re-audit; binding to it, or to a
#: placeholder, would bind to bytes that can change after the binding.
REFUSED_CORPUS_BINDINGS = (
    "SYNTHETIC_NOT_ADMISSIBLE",
    "PENDING",
    "TBD",
    "WORKTREE",
    "HEAD",
)


def bind_accepted_corpus(accepted_sha256: str, *, accepted: bool) -> dict[str, Any]:
    """Bind execution to one exact accepted corpus digest, or refuse.

    Two separate refusals, because they are two separate mistakes. A digest that
    is not 64 lowercase hex characters is not a digest. A digest that is well
    formed but not yet accepted is a candidate -- the corpus is under narrow
    record/provenance remediation and targeted re-audit, and binding to a
    candidate would let the bytes move under a score that had already been
    recorded against them.
    """
    value = str(accepted_sha256).strip()
    if value.upper() in REFUSED_CORPUS_BINDINGS or not _SHA256_HEX.match(value):
        raise InputValidationError(
            f"Corpus binding {accepted_sha256!r} is not an exact SHA-256 digest. "
            "Bind one accepted corpus by its 64-character digest; never to a branch, "
            "a worktree path or a placeholder."
        )
    if not accepted:
        raise GovernanceBlock(
            f"Corpus {value} is {CORPUS_INPUT_STATUS}. Execution binds an accepted "
            "corpus only. Re-audit acceptance is the corpus lane's to declare, not "
            "this package's to assume."
        )
    return {
        "corpus_sha256": value,
        "binding": "EXACT_ACCEPTED_CORPUS_SHA256",
        "corpus_input_status": "ACCEPTED_AND_BOUND",
        "oracle_sha256": ORACLE_FREEZE_SHA256,
    }


def metrics_package_status() -> dict[str, Any]:
    """One-call disposition of the metric package, for a preflight or an audit."""
    return {
        "package": "calibration_metrics",
        "primary_metric": PRIMARY_CALIBRATION_METRIC,
        "primary_direction": PRIMARY_CALIBRATION_DIRECTION,
        "ruling": R2_CALIBRATION.convergence_id,
        "margin_metrics": "IMPLEMENTED",
        "residual_package": "IMPLEMENTED",
        "blowout_diagnostics": "IMPLEMENTED",
        "movement_diagnostics": "IMPLEMENTED",
        "temporal_stability": "IMPLEMENTED",
        "brier_and_log_loss": "IMPLEMENTED_GATED_CLOSED",
        "brier_and_log_loss_blocker": PROBABILITY_CONVERSION_BLOCKER,
        "srs_witness": "IMPLEMENTED_AUTHORITY_BOUNDARY_PRESERVED",
        "colley_witness": "UNAVAILABLE_NO_IMPLEMENTATION_MOUNTED",
        "colley_blocker": COLLEY_WITNESS_BLOCKER,
        "holdout_isolation": "ENFORCED_BY_SEALED_CONTAINER_AND_STAGE_GATE",
        "shard_order_invariance": "ENFORCED_BY_CANONICAL_SORT_AND_FSUM",
        "governed_observation_dataset_mounted": False,
        "corpus_input_status": CORPUS_INPUT_STATUS,
        "corpus_candidate_observations": CORPUS_CANDIDATE_OBSERVATIONS,
        "corpus_candidate_seasons": CORPUS_CANDIDATE_SEASONS,
        "corpus_worktree_read": False,
        "witnesses_required_for_primary_selection": False,
        "game_sd_points_required_for_primary_selection": False,
        "game_sd_points_estimated_from": (
            "out-of-sample model residuals, after a deterministic mean model exists"
        ),
        "freeze_id": ORACLE_FREEZE_ID,
        "oracle_sha256": ORACLE_FREEZE_SHA256,
        "disposition": "FROZEN_READY_FOR_INPUTS",
        "parameters_promoted": False,
        "candidates_generated": False,
        "season_monte_carlo_run": False,
    }


# ---------------------------------------------------------------------------
# Benchmark. Synthetic fixture only -- never a governed dataset.
# ---------------------------------------------------------------------------


def synthetic_benchmark_fixture(
    *,
    candidates: int,
    rows_per_candidate: int,
    seed: int = 20260822,
) -> tuple[CandidateReplay, ...]:
    """Deterministic non-governed rows for timing the scorer.

    A linear congruential generator rather than :mod:`random`, so the fixture is
    reproducible without touching global RNG state, and an explicit
    ``SYNTHETIC_NOT_ADMISSIBLE`` marker on every provenance field so these rows
    cannot be mistaken for evidence if one ever escapes a benchmark.

    This measures throughput. It measures nothing about football.
    """
    if candidates < 1 or rows_per_candidate < 1:
        raise InputValidationError(
            "Benchmark fixture needs at least one candidate and one row"
        )
    state = seed & 0xFFFFFFFF

    def _next() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    out: list[CandidateReplay] = []
    for c in range(candidates):
        rows: list[ReplayRow] = []
        for i in range(rows_per_candidate):
            season = 2020 + (i % 3)
            week = 1 + (i % 14)
            actual = round((_next() - 0.5) * 80.0, 3)
            predicted = round(actual + (_next() - 0.5) * 24.0, 3)
            rows.append(
                ReplayRow(
                    candidate_id=f"BENCH_{c:04d}",
                    game_id=f"G{c:04d}_{i:06d}",
                    season=season,
                    order_index=i,
                    week=week,
                    split="validation" if i % 5 else "holdout",
                    actual_margin=actual,
                    predicted_margin=predicted,
                    team=f"T{i % 130:03d}",
                    opponent=f"T{(i + 7) % 130:03d}",
                )
            )
        out.append(
            CandidateReplay(
                candidate_id=f"BENCH_{c:04d}",
                rows=tuple(rows),
                input_dataset_sha="SYNTHETIC_NOT_ADMISSIBLE",
                split_sha="SYNTHETIC_NOT_ADMISSIBLE",
                experiment_config_sha="SYNTHETIC_NOT_ADMISSIBLE",
            )
        )
    return tuple(out)
