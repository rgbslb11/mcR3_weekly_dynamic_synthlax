"""Temporal walk-forward scorer for V3 calibration candidates.

:mod:`.calibration_search` says which parameter vectors exist. This says what a
number attached to one of them means.

The whole value of a calibration search is the claim that its winner generalises,
and that claim is destroyed by defects that leave no trace in the output: a
random split, a rating recomputed from the full season, a within-week update that
lets one Saturday result inform another Saturday prediction. Each produces a
lower RMSE and a better-looking winner. So the guards here are structural rather
than procedural.

Chronology is enforced, not assumed
    Rows are ordered by ``(event_time, game_id)`` and a stream whose event times
    or week indices go backwards is refused. :class:`Prediction` carries the
    ``information_cutoff`` — the event time of the last result folded into the
    state that produced it — and :func:`require_no_future_leakage` proves every
    cutoff strictly precedes the game it predicted. That converts "no leakage"
    from a description of the code into a property of the output.

Reratings promote at week boundaries, never per game
    A per-game promotion lets a team's noon result move the rating that predicts
    its conference-mate's evening game, inside a week the model has not finished
    observing. Weeks 1-2 promote nothing at all — opening-strength semantics stay
    exact — and the first promoted rerating lands after Week 2, which is the
    governed V3 rule restated as executable code rather than as a comment.

Raw observations and derived state are different types
    :class:`ObservationRow` is frozen and never written to. Everything the model
    learns lives in :class:`TeamCalibrationState`. There is no field an update
    could write back into an observation, so the corpus cannot be quietly
    reshaped by the candidate being scored against it.

Expected margin fails closed
    The rating-to-margin transform is the disputed point-axis question, so it is
    not implemented here. It arrives as an :class:`ExpectedMarginAuthority`, and
    :func:`require_governed_authority` refuses the fixture one. A missing
    expected margin raises; it never defaults to zero, because a zero expected
    margin is a confident prediction of a tie, not an absence of one.

``game_sd_points`` is estimated, never fitted
    See :func:`estimate_game_sd_points`. The mean model is selected on RMSE,
    which needs no dispersion at all; dispersion is then read off the residuals
    that selection left behind and used only for the probabilistic diagnostics.
    :func:`require_residual_based_game_sd` refuses an estimate taken from the SD
    of actual margins, which measures how variable college football is rather
    than how wrong the model is.

Nothing here promotes a value or writes canonical configuration.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from . import calibration as cal
from . import colley as colley_witness
from . import srs as srs_witness
from .calibration_search import (
    CalibrationCandidate,
    canonical_json,
)
from .config import DEFAULT_PRIOR_DECAY
from .errors import GovernanceBlock, InputValidationError

__all__ = [
    "EXPECTED_MARGIN_INPUT_CONTRACT",
    "FAILURE_DEGENERATE",
    "FAILURE_GOVERNANCE",
    "FAILURE_INPUT",
    "FAILURE_NONE",
    "FIRST_PROMOTED_RERATING_AFTER_WEEK",
    "FIXTURE_AUTHORITY_ID",
    "GAME_SD_METHOD_ACTUAL_MARGIN",
    "GAME_SD_METHOD_RESIDUAL",
    "VENUES",
    "CandidateScore",
    "CapIdentification",
    "ExpectedMarginAuthority",
    "GameSdEstimate",
    "MovementDistribution",
    "ObservationRow",
    "ObservationSet",
    "Prediction",
    "ShardResultRow",
    "TeamCalibrationState",
    "WitnessRatings",
    "actual_margin_dispersion",
    "compute_witnesses",
    "estimate_game_sd_points",
    "fixture_authority",
    "game_sd_from_actual_margins",
    "require_governed_authority",
    "require_no_future_leakage",
    "require_residual_based_game_sd",
    "score_candidate",
    "score_shard",
    "shard_table_as_dict",
    "spearman_rank_correlation",
]


VENUES = ("HOME", "AWAY", "NEUTRAL")

#: Governed V3 rule: Weeks 1-2 are audit-only and the first promoted rerating
#: lands after Week 2. Restated here because the scorer enforces it directly;
#: :func:`assert_matches_governed_config` proves it still agrees with V3Config.
FIRST_PROMOTED_RERATING_AFTER_WEEK = 2

FAILURE_NONE = "OK"
FAILURE_GOVERNANCE = "GOVERNANCE_BLOCK"
FAILURE_INPUT = "INPUT_VALIDATION"
FAILURE_DEGENERATE = "METRIC_NOT_MATHEMATICALLY_VALID"

FIXTURE_AUTHORITY_ID = "FIXTURE_NON_PROMOTING_IDENTITY_POINT_AXIS"

#: Tolerance, in points, when checking that the supplied transform reproduces the
#: corpus's own governed expected margins. Tight: this is a check that two
#: implementations of one transform agree, not a modelling tolerance.
AUTHORITY_AGREEMENT_TOLERANCE_POINTS = 1e-6

#: Probability clamp for the log-loss diagnostic. A prediction of exactly 0 or 1
#: is infinitely penalised, which turns one saturated game into the whole metric.
_LOGLOSS_EPSILON = 1e-15

#: Kickoff instants are compared as strings, so the format has to be one whose
#: lexicographic order is its chronological order: fixed-width, zero-padded, with
#: an explicit offset. A date written ``2021-9-4`` sorts after ``2021-10-02``.
_EVENT_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


# --- input contract ----------------------------------------------------------

#: What the parallel expected-margin lane must supply, field by field. Stated as
#: data rather than prose so the supplying lane can diff against it, and kept
#: separate from :mod:`.calibration_contract` — that module specifies the
#: *observation corpus*, this one specifies the *prediction boundary* between
#: that corpus and this scorer.
EXPECTED_MARGIN_INPUT_CONTRACT: dict[str, Any] = {
    "contract_id": "V3-CAL-EXPECTED-MARGIN-BOUNDARY-001",
    "status": "SPECIFICATION_ONLY_NO_AUTHORITY_MOUNTED",
    "per_observation_fields": {
        "game_id": "Stable unique key. Deduplication and split assignment key.",
        "season": "Season the game belongs to. State is re-initialised per season.",
        "week": "Week PLAYED. Establishes which rerating boundary the game sits behind.",
        "event_time": (
            "ISO-8601 kickoff instant. The chronological key. It, not week, is what "
            "orders two games inside one week and what proves a prediction preceded "
            "its outcome."
        ),
        "team": "Canonical subject team id.",
        "opponent": "Canonical opponent id.",
        "venue": f"One of {list(VENUES)}, from the subject team's perspective.",
        "pregame_team_points": (
            "Subject team's point strength BEFORE kickoff, on the authority's declared "
            "axis. Used as the season opening strength on a team's first appearance and "
            "as the transform cross-check thereafter."
        ),
        "pregame_opponent_points": "Opponent's pregame point strength on the same axis.",
        "governed_expected_margin": (
            "The authority's own pregame predicted margin for this game. Required, and "
            "never defaulted: see the module docstring."
        ),
        "actual_margin": "Final scoring margin from the subject team's perspective.",
        "split": f"One of {list(cal.DATA_SPLITS)}. Assigned in the corpus, temporally.",
        "provenance": "Named origin of the row, carried through to the shard table.",
    },
    "authority_fields": {
        "authority_id": "Stable id of the expected-margin authority.",
        "transform_id": "Named rating-to-margin transform.",
        "hfa_points": "Home-field advantage in points, on the same axis.",
        "hfa_treatment": "How venue maps onto the HFA term.",
        "point_axis_id": "The declared point axis. The disputed resolution lives here.",
        "status": "GOVERNED, or a non-promoting fixture class.",
    },
    "separations": {
        "raw_vs_derived": (
            "ObservationRow is frozen and is never written to. All model state lives in "
            "TeamCalibrationState."
        ),
        "expected_margin_vs_prediction": (
            "governed_expected_margin is the authority's number and is corpus data. The "
            "candidate's own evolving prediction is derived state and is what the "
            "primary objective scores."
        ),
    },
    "fail_closed": {
        "missing_authority": "GovernanceBlock. Never a default transform.",
        "missing_expected_margin": "GovernanceBlock. Never 0.0.",
        "fixture_authority": "Refused for any run whose results could be cited.",
    },
}


def assert_matches_governed_config() -> None:
    """Prove the scorer's weekly semantics still match the governed V3 schedule."""
    if FIRST_PROMOTED_RERATING_AFTER_WEEK != 2:
        raise GovernanceBlock(
            "V3 requires the first promoted rerating after Week 2; the scorer declares "
            f"week {FIRST_PROMOTED_RERATING_AFTER_WEEK}."
        )
    if DEFAULT_PRIOR_DECAY.get(0) != 1.00 or DEFAULT_PRIOR_DECAY.get(5) != 0.00:
        raise GovernanceBlock(
            "Preseason-prior decay schedule has drifted from the governed V3 values; "
            "the walk-forward blends against it and must not carry a private copy."
        )


def _prior_weight(week_completed: int) -> float:
    """Governed preseason-prior weight after ``week_completed``.

    This is V3 configuration, not a calibration parameter, and is read from
    :data:`config.DEFAULT_PRIOR_DECAY` rather than restated so a candidate can
    never move it.
    """
    if week_completed <= 5:
        return DEFAULT_PRIOR_DECAY[week_completed]
    return 0.0


# --- expected-margin authority ----------------------------------------------


@dataclass(frozen=True)
class ExpectedMarginAuthority:
    """The rating-to-margin transform, supplied rather than invented.

    The historical point-axis resolution is disputed and is not settled here. The
    authority owns the transform, declares the axis it is on, and carries a status
    that :func:`require_governed_authority` checks. ``transform`` is a callable so
    the governed lane can supply something this module never anticipated without
    the scorer having to model it.
    """

    authority_id: str
    transform_id: str
    point_axis_id: str
    hfa_points: float
    hfa_treatment: str
    status: str
    transform: Callable[[float, float, float], float]

    def __post_init__(self) -> None:
        if not self.authority_id.strip():
            raise InputValidationError("Expected-margin authority must carry an id.")
        if not math.isfinite(float(self.hfa_points)):
            raise InputValidationError(
                f"Authority {self.authority_id} declares non-finite HFA "
                f"{self.hfa_points!r}."
            )

    def signed_hfa(self, venue: str) -> float:
        """HFA in the subject team's favour, by venue."""
        key = venue.strip().upper()
        if key not in VENUES:
            raise InputValidationError(
                f"Unknown venue {venue!r}; expected one of {list(VENUES)}. Venue is not "
                "inferred from team order: inferring it folds the home-field term into "
                "the residual it exists to separate out."
            )
        if key == "HOME":
            return float(self.hfa_points)
        if key == "AWAY":
            return -float(self.hfa_points)
        return 0.0

    def expected_margin(self, team_points: float, opponent_points: float, venue: str) -> float:
        value = float(
            self.transform(float(team_points), float(opponent_points), self.signed_hfa(venue))
        )
        if not math.isfinite(value):
            raise InputValidationError(
                f"Authority {self.authority_id} produced a non-finite expected margin "
                f"for {team_points!r} vs {opponent_points!r} at {venue!r}."
            )
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority_id": self.authority_id,
            "transform_id": self.transform_id,
            "point_axis_id": self.point_axis_id,
            "hfa_points": float(self.hfa_points),
            "hfa_treatment": self.hfa_treatment,
            "status": self.status,
        }


AUTHORITY_STATUS_GOVERNED = "GOVERNED"
AUTHORITY_STATUS_FIXTURE = "FIXTURE_NON_PROMOTING"


def require_governed_authority(authority: ExpectedMarginAuthority | None) -> ExpectedMarginAuthority:
    """Fail closed unless a governed expected-margin authority is mounted."""
    if authority is None:
        raise GovernanceBlock(
            "No expected-margin authority supplied. Scoring is refused rather than run "
            "against a default transform: the historical point-axis resolution is the "
            "disputed question, and inventing one here would answer it by accident."
        )
    if authority.status != AUTHORITY_STATUS_GOVERNED:
        raise GovernanceBlock(
            f"Expected-margin authority {authority.authority_id} has status "
            f"{authority.status!r}. Only {AUTHORITY_STATUS_GOVERNED} authorities may "
            "produce results that are cited; fixtures benchmark the harness and "
            "nothing else."
        )
    return authority


def fixture_authority(*, hfa_points: float = 2.5) -> ExpectedMarginAuthority:
    """A non-promoting identity-axis transform, for benchmarking the harness only.

    It answers no disputed question: it asserts that a point of strength is a
    point of margin, which is the assumption the governed lane exists to replace.
    :func:`require_governed_authority` refuses it, so it can measure how fast the
    scorer runs and can never measure how good a candidate is.
    """
    return ExpectedMarginAuthority(
        authority_id=FIXTURE_AUTHORITY_ID,
        transform_id="IDENTITY_POINTS_TO_MARGIN_PLUS_SIGNED_HFA",
        point_axis_id="FIXTURE_UNRESOLVED_POINT_AXIS",
        hfa_points=float(hfa_points),
        hfa_treatment="SIGNED_BY_VENUE_ZERO_AT_NEUTRAL",
        status=AUTHORITY_STATUS_FIXTURE,
        transform=lambda team, opponent, hfa: (team - opponent) + hfa,
    )


# --- raw observations --------------------------------------------------------


@dataclass(frozen=True)
class ObservationRow:
    """One historical game, as observed. Never written to by the model."""

    game_id: str
    season: int
    week: int
    event_time: str
    team: str
    opponent: str
    venue: str
    pregame_team_points: float
    pregame_opponent_points: float
    governed_expected_margin: float | None
    actual_margin: float
    split: str
    provenance: str

    def __post_init__(self) -> None:
        if self.venue.strip().upper() not in VENUES:
            raise InputValidationError(
                f"Observation {self.game_id} has venue {self.venue!r}; expected one of "
                f"{list(VENUES)}."
            )
        if self.split.strip().lower() not in cal.DATA_SPLITS:
            raise InputValidationError(
                f"Observation {self.game_id} has split {self.split!r}; expected one of "
                f"{list(cal.DATA_SPLITS)}."
            )
        if self.team == self.opponent:
            raise InputValidationError(
                f"Observation {self.game_id} lists {self.team} against itself."
            )
        if int(self.week) < 1:
            raise InputValidationError(
                f"Observation {self.game_id} has week {self.week}; weeks are 1-indexed."
            )
        for name in ("pregame_team_points", "pregame_opponent_points", "actual_margin"):
            value = getattr(self, name)
            if value is None or not math.isfinite(float(value)):
                raise InputValidationError(
                    f"Observation {self.game_id} has non-finite {name}={value!r}."
                )
        if not _EVENT_TIME.match(self.event_time):
            raise InputValidationError(
                f"Observation {self.game_id} has event_time {self.event_time!r}, which is "
                "not a fixed-width ISO-8601 instant with an explicit offset. The whole "
                "leakage proof orders games by comparing these strings, and an "
                "unpadded or offset-less timestamp sorts by spelling rather than by time."
            )

    def require_expected_margin(self) -> float:
        """The authority's pregame margin, or a refusal. Never a default.

        Zero is a *confident prediction of a tie*, not an absence of a prediction.
        Substituting it would leave a corpus with a missing predictor scoring
        better than one with a bad predictor.
        """
        if self.governed_expected_margin is None:
            raise GovernanceBlock(
                f"Observation {self.game_id} carries no governed expected margin. "
                "Scoring fails closed rather than defaulting it to 0.0."
            )
        value = float(self.governed_expected_margin)
        if not math.isfinite(value):
            raise InputValidationError(
                f"Observation {self.game_id} has non-finite governed expected margin."
            )
        return value

    @property
    def normalized_split(self) -> str:
        return self.split.strip().lower()

    def as_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "season": int(self.season),
            "week": int(self.week),
            "event_time": self.event_time,
            "team": self.team,
            "opponent": self.opponent,
            "venue": self.venue.strip().upper(),
            "split": self.normalized_split,
            "provenance": self.provenance,
        }


@dataclass(frozen=True)
class ObservationSet:
    """A chronologically validated corpus, with the digests a shard row must cite."""

    rows: tuple[ObservationRow, ...]
    dataset_sha: str
    provenance: str

    def __post_init__(self) -> None:
        if not self.rows:
            raise InputValidationError(
                "Observation set is empty. A header is a schema, not evidence."
            )
        ids = [r.game_id for r in self.rows]
        duplicates = sorted({i for i in ids if ids.count(i) > 1}) if len(set(ids)) != len(ids) else []
        if duplicates:
            raise InputValidationError(
                f"Observation set repeats game ids {duplicates[:5]}. A mirrored corpus "
                "carrying both team perspectives of one game must be deduplicated at "
                "ingestion; scoring both counts every result twice."
            )
        object.__setattr__(
            self, "_ordered", tuple(sorted(self.rows, key=lambda r: (r.event_time, r.game_id)))
        )
        self._require_chronological()
        payload = {r.game_id: r.normalized_split for r in self._ordered}
        object.__setattr__(
            self,
            "_split_sha",
            hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest(),
        )

    def _require_chronological(self) -> None:
        """Refuse a corpus whose orderings contradict each other.

        The stream is sorted by ``event_time``, so event times cannot be observed
        going backwards — which is precisely why the checks here are about whether
        that sort means anything.

        Timestamp shape is checked first. Comparing ISO-8601 instants as strings
        is chronological only while every instant has the same width and the same
        UTC offset; mix ``+00:00`` with ``-05:00`` and the sort silently orders
        two kickoffs by their spelling. Every subsequent guarantee, including the
        leakage proof, rests on this one.

        Then season and week must agree with time. A week index going backwards
        inside a season while time advances means the two disagree about what
        happened first, and the rerating boundary would be drawn in the wrong
        place — promoting a rating on the strength of a game that had not been
        played.
        """
        ordered = self.ordered_rows
        shapes = {(len(r.event_time), r.event_time[-6:]) for r in ordered}
        if len(shapes) > 1:
            raise InputValidationError(
                f"Observation event times are not written in one uniform format: "
                f"{sorted(shapes)}. Ordering by string comparison is chronological only "
                "within a single fixed-width format and offset."
            )
        last_week: dict[int, int] = {}
        last_season: int | None = None
        for row in ordered:
            season = int(row.season)
            if last_season is not None and season < last_season:
                raise InputValidationError(
                    f"Observation {row.game_id} belongs to season {season} but follows "
                    f"season {last_season} in time; seasons must not interleave."
                )
            last_season = season
            week = int(row.week)
            if season in last_week and week < last_week[season]:
                raise InputValidationError(
                    f"Observation {row.game_id} is week {week} of {season} but follows "
                    f"week {last_week[season]}; week and event_time disagree about "
                    "order, so the rerating boundary cannot be placed."
                )
            last_week[season] = week

    @property
    def ordered_rows(self) -> tuple[ObservationRow, ...]:
        """The one chronological order every candidate is scored in.

        Sorted once at construction. Every candidate in a shard walks the same
        corpus, so re-sorting per candidate would multiply the sort by the size of
        the universe for an answer that cannot have changed.
        """
        return self._ordered  # type: ignore[attr-defined,no-any-return]

    @property
    def split_sha(self) -> str:
        """Digest of the partition itself.

        Distinct from :attr:`dataset_sha`: the same bytes partitioned differently
        are a different experiment, and the aggregator refuses to merge results
        whose partitions disagree.
        """
        return self._split_sha  # type: ignore[attr-defined,no-any-return]

    def split_counts(self) -> dict[str, int]:
        counts = {s: 0 for s in cal.DATA_SPLITS}
        for row in self.rows:
            counts[row.normalized_split] += 1
        return counts

    def require_temporal_split_integrity(self) -> dict[str, Any]:
        """Delegate to the governed proof that the partition is ordered in time."""
        return cal.require_temporal_split_integrity(
            {r.game_id: (r.normalized_split, r.event_time) for r in self.rows}
        )

    def require_authority_agreement(
        self, authority: ExpectedMarginAuthority, *, tolerance: float = AUTHORITY_AGREEMENT_TOLERANCE_POINTS
    ) -> dict[str, Any]:
        """Prove the mounted transform reproduces the corpus's own expected margins.

        The corpus was produced by an authority that already applied a transform.
        If the transform mounted here disagrees, every residual is measured against
        a predictor the corpus never used, and the search optimises a model of the
        wrong thing. Checking it is cheap and candidate-independent, so it happens
        once, before any compute is spent.
        """
        disagreements: list[str] = []
        for row in self.ordered_rows:
            governed = row.require_expected_margin()
            computed = authority.expected_margin(
                row.pregame_team_points, row.pregame_opponent_points, row.venue
            )
            if abs(computed - governed) > tolerance:
                disagreements.append(
                    f"{row.game_id}: authority={governed!r} transform={computed!r}"
                )
                if len(disagreements) >= 5:
                    break
        if disagreements:
            raise GovernanceBlock(
                f"Expected-margin authority {authority.authority_id} does not reproduce "
                f"the corpus's own governed margins: {disagreements}. The residuals the "
                "search would minimise are measured against a predictor the corpus never "
                "used."
            )
        return {
            "authority_id": authority.authority_id,
            "transform_id": authority.transform_id,
            "rows_checked": len(self.rows),
            "tolerance_points": tolerance,
            "agrees": True,
        }


# --- derived state -----------------------------------------------------------


@dataclass
class TeamCalibrationState:
    """Everything the model believes about one team. Derived, mutable, per season.

    Held apart from :class:`ObservationRow` by type rather than by convention, so
    there is no field an update could write back into the corpus.
    """

    team: str
    opening_strength_points: float
    promoted_strength_points: float
    games_played: int = 0
    #: Capped updates, most recent first. Recent-form weights index into this.
    update_history: list[float] = field(default_factory=list)

    def performance_state(self, weights: Sequence[float]) -> float:
        """Opening strength plus the recent-form-weighted recent updates."""
        contribution = sum(
            w * u for w, u in zip(weights, self.update_history)
        )
        return self.opening_strength_points + contribution


@dataclass(frozen=True)
class Prediction:
    """One pregame prediction and the exact information that produced it."""

    game_id: str
    season: int
    week: int
    event_time: str
    split: str
    predicted_margin: float
    actual_margin: float
    #: Event time of the most recent result folded into the state behind this
    #: prediction, or ``None`` when the state is still opening strength.
    information_cutoff: str | None

    @property
    def residual(self) -> float:
        return float(self.actual_margin) - float(self.predicted_margin)


def require_no_future_leakage(predictions: Sequence[Prediction]) -> dict[str, Any]:
    """Prove every prediction preceded the information it was made from.

    A walk-forward that is correct by construction still deserves a check on its
    output, because the failure mode is silent: a leaking scorer returns better
    numbers and no error. This compares each prediction's information cutoff
    against its own kickoff and refuses on any overlap.
    """
    violations: list[str] = []
    for prediction in predictions:
        cutoff = prediction.information_cutoff
        if cutoff is not None and cutoff >= prediction.event_time:
            violations.append(
                f"{prediction.game_id}: state included results through {cutoff} but "
                f"kicked off at {prediction.event_time}"
            )
            if len(violations) >= 5:
                break
    if violations:
        raise GovernanceBlock(
            f"Future leakage detected in {len(violations)} prediction(s): {violations}. "
            "An out-of-sample metric computed over these is not out of sample."
        )
    return {
        "predictions_checked": len(predictions),
        "violations": 0,
        "leak_free": True,
        "opening_strength_predictions": sum(
            1 for p in predictions if p.information_cutoff is None
        ),
    }


# --- identification reporting ------------------------------------------------


@dataclass(frozen=True)
class CapIdentification:
    """Whether the movement cap did anything at all.

    A cap that never binds is a parameter the data cannot see. Ranking two such
    caps and reporting the winner is reporting a tie-break as a discovery, which
    is one of the three identification defects that disqualified the prior
    experiment.
    """

    cap_points: float
    update_count: int
    cap_hit_count: int
    max_uncapped_update: float
    max_capped_update: float

    @property
    def cap_hit_rate(self) -> float:
        return self.cap_hit_count / self.update_count if self.update_count else 0.0

    @property
    def identified(self) -> bool:
        return self.cap_hit_count > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "cap_points": self.cap_points,
            "update_count": self.update_count,
            "cap_hit_count": self.cap_hit_count,
            "cap_hit_rate": self.cap_hit_rate,
            "max_uncapped_update": self.max_uncapped_update,
            "max_capped_update": self.max_capped_update,
            "cap_identified": self.identified,
            "identification_note": (
                "Cap binds on this corpus."
                if self.identified
                else "Cap never binds; its value is not identified by this corpus and "
                "must not be reported as an empirical finding."
            ),
        }


@dataclass(frozen=True)
class MovementDistribution:
    """Week-to-week promoted-strength movement, as a distribution rather than a mean."""

    count: int
    mean: float
    sd: float
    p95: float
    maximum: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "movement_count": self.count,
            "movement_mean": self.mean,
            "movement_sd": self.sd,
            "movement_p95": self.p95,
            "movement_max": self.maximum,
        }


def _distribution(values: Sequence[float]) -> MovementDistribution:
    """Summarise absolute movements. ``p95`` uses the nearest-rank method.

    Nearest-rank rather than an interpolated percentile so the value is always an
    observed movement and is identical on every implementation; an interpolating
    percentile invents a number between two weeks that never happened.
    """
    if not values:
        return MovementDistribution(0, 0.0, 0.0, 0.0, 0.0)
    ordered = sorted(float(v) for v in values)
    n = len(ordered)
    mean = sum(ordered) / n
    variance = sum((v - mean) ** 2 for v in ordered) / (n - 1) if n > 1 else 0.0
    rank = max(1, math.ceil(0.95 * n))
    return MovementDistribution(
        count=n,
        mean=mean,
        sd=math.sqrt(variance),
        p95=ordered[rank - 1],
        maximum=ordered[-1],
    )


# --- game_sd_points ----------------------------------------------------------

GAME_SD_METHOD_RESIDUAL = "OUT_OF_SAMPLE_RESIDUAL_DISPERSION"
GAME_SD_METHOD_ACTUAL_MARGIN = "SD_OF_ACTUAL_MARGIN"


@dataclass(frozen=True)
class GameSdEstimate:
    """A dispersion estimate that carries how it was obtained."""

    method: str
    value: float
    observations: int
    split: str
    residual_mean: float
    residual_sd_about_mean: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "game_sd_points": self.value,
            "game_sd_method": self.method,
            "game_sd_observations": self.observations,
            "game_sd_split": self.split,
            "game_sd_residual_mean": self.residual_mean,
            "game_sd_residual_sd_about_mean": self.residual_sd_about_mean,
            "admissible_for_game_sd_points": self.method == GAME_SD_METHOD_RESIDUAL,
        }


def estimate_game_sd_points(
    residuals: Sequence[float], *, split: str
) -> GameSdEstimate:
    """Estimate ``game_sd_points`` from out-of-sample prediction residuals.

    Two things are computed and both are reported, because they answer different
    questions. ``value`` is the root mean square about **zero**, which is the
    dispersion a probability model needs: ``P(win) = Phi(predicted / sd)`` is
    measured about the prediction, not about the average error.
    ``residual_sd_about_mean`` is the classical sample SD, and the gap between the
    two is the model's bias — worth seeing rather than absorbing.

    The training split is refused. A dispersion read off the residuals the mean
    model was chosen to minimise is optimistic by construction, and
    ``game_sd_points`` feeds a probability the engine will publish.
    """
    key = split.strip().lower()
    if key not in cal.DATA_SPLITS:
        raise InputValidationError(
            f"game_sd_points split {split!r}; expected one of {list(cal.DATA_SPLITS)}."
        )
    if key == "training":
        raise GovernanceBlock(
            "game_sd_points may not be estimated on the training split. The mean model "
            "was selected to minimise exactly those residuals, so their dispersion "
            "understates the error the engine will actually make."
        )
    clean = [float(r) for r in residuals if math.isfinite(float(r))]
    if len(clean) < 2:
        raise InputValidationError(
            f"game_sd_points needs at least 2 residuals; got {len(clean)}."
        )
    n = len(clean)
    mean = sum(clean) / n
    rms = math.sqrt(sum(r * r for r in clean) / n)
    variance = sum((r - mean) ** 2 for r in clean) / (n - 1)
    return GameSdEstimate(
        method=GAME_SD_METHOD_RESIDUAL,
        value=rms,
        observations=n,
        split=key,
        residual_mean=mean,
        residual_sd_about_mean=math.sqrt(variance),
    )


def actual_margin_dispersion(margins: Sequence[float]) -> float:
    """Sample SD of actual margins. Present so it can be named and refused."""
    clean = [float(m) for m in margins]
    if len(clean) < 2:
        raise InputValidationError("Actual-margin dispersion needs at least 2 margins.")
    n = len(clean)
    mean = sum(clean) / n
    return math.sqrt(sum((m - mean) ** 2 for m in clean) / (n - 1))


def game_sd_from_actual_margins(margins: Sequence[float], *, split: str) -> GameSdEstimate:
    """Build the inadmissible estimate explicitly, so the gate has something to refuse.

    This exists to make the distinction testable rather than asserted. SD of actual
    margin measures how variable college football is. ``game_sd_points`` must
    measure how wrong the model is. They differ by everything the model explains,
    which on any useful model is most of the variance — so substituting one for the
    other inflates the published uncertainty and is precisely the direction of the
    unexplained legacy 20.2 observation.
    """
    return GameSdEstimate(
        method=GAME_SD_METHOD_ACTUAL_MARGIN,
        value=actual_margin_dispersion(margins),
        observations=len(margins),
        split=split.strip().lower(),
        residual_mean=float("nan"),
        residual_sd_about_mean=float("nan"),
    )


def require_residual_based_game_sd(estimate: GameSdEstimate) -> GameSdEstimate:
    """Refuse any ``game_sd_points`` not taken from out-of-sample residuals."""
    if estimate.method != GAME_SD_METHOD_RESIDUAL:
        raise GovernanceBlock(
            f"game_sd_points was estimated by {estimate.method}, which is not admissible. "
            f"Only {GAME_SD_METHOD_RESIDUAL} may fill game_sd_points: the SD of actual "
            "margins measures the sport's variability, not the model's error."
        )
    return estimate


# --- metric helpers ----------------------------------------------------------


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _ranks(values: Sequence[float]) -> list[float]:
    """Average ranks, so ties do not depend on input order."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position
        while end + 1 < len(order) and values[order[end + 1]] == values[order[position]]:
            end += 1
        average = (position + end) / 2.0 + 1.0
        for k in range(position, end + 1):
            ranks[order[k]] = average
        position = end + 1
    return ranks


def spearman_rank_correlation(left: Mapping[str, float], right: Mapping[str, float]) -> float | None:
    """Spearman correlation over the keys the two mappings share.

    Returns ``None`` rather than a number when it is not mathematically defined —
    fewer than two shared keys, or one side constant. A witness that reports 0.0
    for "undefined" is indistinguishable from one reporting genuine independence.
    """
    shared = sorted(set(left) & set(right))
    if len(shared) < 2:
        return None
    left_ranks = _ranks([float(left[k]) for k in shared])
    right_ranks = _ranks([float(right[k]) for k in shared])
    n = len(shared)
    mean_left = sum(left_ranks) / n
    mean_right = sum(right_ranks) / n
    numerator = sum(
        (a - mean_left) * (b - mean_right) for a, b in zip(left_ranks, right_ranks)
    )
    denominator = math.sqrt(
        sum((a - mean_left) ** 2 for a in left_ranks)
        * sum((b - mean_right) ** 2 for b in right_ranks)
    )
    if denominator == 0.0:
        return None
    return numerator / denominator


# --- witnesses ---------------------------------------------------------------


@dataclass(frozen=True)
class WitnessRatings:
    """Colley and SRS ratings for a corpus. Candidate-independent, so computed once."""

    colley: dict[str, float]
    srs: dict[str, float]
    game_count: int
    srs_status: str
    colley_status: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "witness_game_count": self.game_count,
            "colley_status": self.colley_status,
            "srs_status": self.srs_status,
            "colley_team_count": len(self.colley),
            "srs_team_count": len(self.srs),
        }


def compute_witnesses(rows: Sequence[ObservationRow]) -> WitnessRatings:
    """Colley and SRS over the observed results.

    Both are computed from outcomes alone and know nothing about any candidate,
    which is what makes their agreement with a candidate's ratings informative.
    SRS can legitimately fail on a disconnected schedule graph; that is recorded
    as a status rather than raised, because a witness being unavailable must not
    take the primary objective down with it.
    """
    decided = [r for r in rows if float(r.actual_margin) != 0.0]
    colley_ratings: dict[str, float] = {}
    colley_status = "COMPUTED"
    try:
        colley_ratings = colley_witness.compute_colley(
            [
                colley_witness.ColleyGame(
                    game_id=r.game_id,
                    team=r.team,
                    opponent=r.opponent,
                    team_won=float(r.actual_margin) > 0.0,
                )
                for r in decided
            ]
        )
    except (GovernanceBlock, InputValidationError) as exc:
        colley_status = f"UNAVAILABLE: {exc}"

    srs_ratings: dict[str, float] = {}
    srs_status = "COMPUTED"
    try:
        # srs.compute_srs accumulates margins and opponent counts for the subject
        # side of each row only, so it expects a corpus carrying both perspectives.
        # This corpus carries one row per game, so each row is mirrored here. Doing
        # it at the call site rather than changing srs.py keeps the governed
        # witness module untouched: its input contract is what it always was.
        srs_ratings = srs_witness.compute_srs(
            [
                srs_witness.SrsGame(
                    game_id=game_id,
                    team=team,
                    opponent=opponent,
                    margin=margin,
                )
                for r in rows
                for game_id, team, opponent, margin in (
                    (r.game_id, r.team, r.opponent, float(r.actual_margin)),
                    (f"{r.game_id}:mirror", r.opponent, r.team, -float(r.actual_margin)),
                )
            ]
        )
    except (GovernanceBlock, InputValidationError) as exc:
        srs_status = f"UNAVAILABLE: {exc}"

    return WitnessRatings(
        colley=colley_ratings,
        srs=srs_ratings,
        game_count=len(rows),
        srs_status=srs_status,
        colley_status=colley_status,
    )


#: A witness agreeing this strongly or better is called directionally coherent.
#: A threshold, not a gate: nothing is accepted or rejected on it, and it is
#: never blended into the primary criterion.
WITNESS_COHERENCE_THRESHOLD = 0.5


# --- the walk-forward --------------------------------------------------------


@dataclass(frozen=True)
class CandidateScore:
    """Everything one candidate produced. Metrics, identification and diagnostics."""

    candidate: CalibrationCandidate
    scored_split: str
    split_counts: dict[str, int]
    predictions: tuple[Prediction, ...]
    metrics: dict[str, Any]
    cap: CapIdentification
    movement: MovementDistribution
    game_sd: GameSdEstimate | None
    witness_fields: dict[str, Any]
    regularization_report: dict[str, Any]
    recent_form_report: dict[str, Any]
    leakage_proof: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "candidate": self.candidate.as_dict(),
            "scored_split": self.scored_split,
            "split_counts": dict(self.split_counts),
            "metrics": dict(self.metrics),
            "movement": self.movement.as_dict(),
            "cap_identification": self.cap.as_dict(),
            "witnesses": dict(self.witness_fields),
            "regularization": dict(self.regularization_report),
            "recent_form": dict(self.recent_form_report),
            "leakage_proof": dict(self.leakage_proof),
        }
        payload["game_sd"] = self.game_sd.as_dict() if self.game_sd else None
        return payload


def _walk_forward(
    candidate: CalibrationCandidate,
    rows: Sequence[ObservationRow],
    authority: ExpectedMarginAuthority,
) -> tuple[list[Prediction], CapIdentification, MovementDistribution, dict[str, Any]]:
    """One chronological pass. Predict, then observe, then promote at week close."""
    weights = candidate.recent_form.weights()
    cap = float(candidate.movement_cap_points)
    coefficient = float(candidate.coefficient)

    predictions: list[Prediction] = []
    movements: list[float] = []
    update_count = 0
    cap_hits = 0
    max_uncapped = 0.0
    max_capped = 0.0
    contribution_depths: list[int] = []

    # Rows arrive already ordered and validated by ObservationSet.
    blocks: list[tuple[int, int, list[ObservationRow]]] = []
    for row in rows:
        key = (int(row.season), int(row.week))
        if blocks and (blocks[-1][0], blocks[-1][1]) == key:
            blocks[-1][2].append(row)
        else:
            blocks.append((key[0], key[1], [row]))

    states: dict[str, TeamCalibrationState] = {}
    current_season: int | None = None
    promoted_cutoff: str | None = None
    # Final promoted strengths per season. Kept per season because state is
    # re-initialised at each season boundary, so there is no single "final" rating
    # for a multi-season corpus.
    season_final_strengths: dict[int, dict[str, float]] = {}

    def _state(team: str, opening: float) -> TeamCalibrationState:
        existing = states.get(team)
        if existing is None:
            existing = TeamCalibrationState(
                team=team,
                opening_strength_points=float(opening),
                promoted_strength_points=float(opening),
            )
            states[team] = existing
        return existing

    for season, week, block in blocks:
        if season != current_season:
            # Season state is re-initialised, not carried. A team's opening strength
            # is a property of the season it opens; carrying last year's promoted
            # rating forward would score a model nobody proposed.
            if current_season is not None:
                season_final_strengths[current_season] = {
                    team: s.promoted_strength_points for team, s in states.items()
                }
            states = {}
            current_season = season
            promoted_cutoff = None

        # --- predict, using only state promoted before this week opened ---
        for row in block:
            team_state = _state(row.team, row.pregame_team_points)
            opponent_state = _state(row.opponent, row.pregame_opponent_points)
            predicted = authority.expected_margin(
                team_state.promoted_strength_points,
                opponent_state.promoted_strength_points,
                row.venue,
            )
            predictions.append(
                Prediction(
                    game_id=row.game_id,
                    season=season,
                    week=week,
                    event_time=row.event_time,
                    split=row.normalized_split,
                    predicted_margin=predicted,
                    actual_margin=float(row.actual_margin),
                    information_cutoff=promoted_cutoff,
                )
            )

        # --- observe, and stage updates without promoting them ---
        #
        # Both sides of every game are updated. The corpus carries one row per game
        # from the subject team's perspective (a mirrored corpus is refused at
        # construction), so the opponent's update is the mirror of the subject's:
        # its residual is the negation, and every blowout policy here is an odd
        # function, so the treated residual negates with it. Updating only the
        # subject would make what a team learns depend on which perspective the
        # corpus happened to record, which is a property of the file rather than of
        # the football.
        by_game = {p.game_id: p for p in predictions[-len(block):]}
        for row in block:
            prediction = by_game[row.game_id]
            raw_residual = prediction.residual
            for team_id, treated in (
                (row.team, candidate.blowout.apply(raw_residual)),
                (row.opponent, candidate.blowout.apply(-raw_residual)),
            ):
                side_state = states[team_id]
                shrunk = coefficient * treated * candidate.regularization.shrinkage(
                    side_state.games_played
                )
                capped = max(-cap, min(cap, shrunk))
                update_count += 1
                max_uncapped = max(max_uncapped, abs(shrunk))
                max_capped = max(max_capped, abs(capped))
                if abs(shrunk) > cap:
                    cap_hits += 1
                side_state.update_history.insert(0, capped)
                side_state.games_played += 1

        # --- promote, only where governance permits ---
        if week >= FIRST_PROMOTED_RERATING_AFTER_WEEK:
            prior_weight = _prior_weight(week)
            for state in states.values():
                if not state.update_history:
                    continue
                performance = state.performance_state(weights)
                promoted = (
                    prior_weight * state.opening_strength_points
                    + (1.0 - prior_weight) * performance
                )
                movements.append(abs(promoted - state.promoted_strength_points))
                state.promoted_strength_points = promoted
                contribution_depths.append(
                    len(candidate.recent_form.effective_contributions(len(state.update_history)))
                )
            promoted_cutoff = max(r.event_time for r in block)

    season_final_strengths[current_season] = {
        team: s.promoted_strength_points for team, s in states.items()
    }
    recent_form_report = {
        "scheme": candidate.recent_form.scheme,
        "depth": int(candidate.recent_form.depth),
        "decay": candidate.recent_form.decay,
        "weights": list(weights),
        "tail_mass": candidate.recent_form.tail_mass,
        "mean_effective_contribution_depth": (
            sum(contribution_depths) / len(contribution_depths) if contribution_depths else 0.0
        ),
        "promotions_observed": len(contribution_depths),
    }
    return (
        predictions,
        CapIdentification(
            cap_points=cap,
            update_count=update_count,
            cap_hit_count=cap_hits,
            max_uncapped_update=max_uncapped,
            max_capped_update=max_capped,
        ),
        _distribution(movements),
        {
            "recent_form": recent_form_report,
            "season_final_strengths": season_final_strengths,
        },
    )


def _mean_model_metrics(scored: Sequence[Prediction]) -> dict[str, Any]:
    """RMSE, MAE and winner accuracy. No dispersion parameter is involved.

    Kept apart from the probabilistic diagnostics because selection happens here:
    the mean model is chosen on RMSE alone, so ``game_sd_points`` cannot influence
    which candidate wins.
    """
    n = len(scored)
    if n == 0:
        raise InputValidationError(
            "No predictions fell in the scored split; there is nothing to measure."
        )
    residuals = [p.residual for p in scored]
    rmse = math.sqrt(sum(r * r for r in residuals) / n)
    mae = sum(abs(r) for r in residuals) / n

    decided = [p for p in scored if float(p.actual_margin) != 0.0]
    correct = sum(
        1
        for p in decided
        if (p.predicted_margin > 0) == (p.actual_margin > 0) and p.predicted_margin != 0
    )
    winner_accuracy = correct / len(decided) if decided else None
    return {
        cal.PRIMARY_CALIBRATION_METRIC: rmse,
        "baxter_rmse": rmse,
        "baxter_mae": mae,
        "winner_accuracy": winner_accuracy,
        "ties_excluded_from_winner_accuracy": n - len(decided),
        "scored_prediction_count": n,
        "residual_mean": sum(residuals) / n,
    }


def _probabilistic_diagnostics(
    scored: Sequence[Prediction], sd: float, *, bins: int = 10
) -> dict[str, Any]:
    """Brier, log loss and a calibration table, from an already-fixed mean model.

    ``sd`` enters here and nowhere else. It converts a margin into a win
    probability and cannot change any prediction, so using a dispersion read off
    these same residuals cannot alter which candidate is selected. It can make the
    diagnostics themselves mildly optimistic, which is why the returned payload
    says which split the dispersion came from rather than leaving a reader to
    assume it was independent.
    """
    if not math.isfinite(sd) or sd <= 0.0:
        return {
            "brier_score": None,
            "log_loss": None,
            "calibration_bins": [],
            "status": FAILURE_DEGENERATE,
            "reason": f"Dispersion {sd!r} is not positive; P(win) is undefined.",
        }
    decided = [p for p in scored if float(p.actual_margin) != 0.0]
    if not decided:
        return {
            "brier_score": None,
            "log_loss": None,
            "calibration_bins": [],
            "status": FAILURE_DEGENERATE,
            "reason": "No decided games in the scored split.",
        }
    probabilities = [_normal_cdf(p.predicted_margin / sd) for p in decided]
    outcomes = [1.0 if p.actual_margin > 0 else 0.0 for p in decided]
    brier = sum((q - y) ** 2 for q, y in zip(probabilities, outcomes)) / len(decided)
    log_loss = -sum(
        y * math.log(min(max(q, _LOGLOSS_EPSILON), 1.0 - _LOGLOSS_EPSILON))
        + (1.0 - y) * math.log(min(max(1.0 - q, _LOGLOSS_EPSILON), 1.0 - _LOGLOSS_EPSILON))
        for q, y in zip(probabilities, outcomes)
    ) / len(decided)

    table: list[dict[str, Any]] = []
    for index in range(bins):
        low = index / bins
        high = (index + 1) / bins
        members = [
            (q, y)
            for q, y in zip(probabilities, outcomes)
            if (low <= q < high) or (index == bins - 1 and q == 1.0)
        ]
        if not members:
            continue
        table.append(
            {
                "bin_low": low,
                "bin_high": high,
                "count": len(members),
                "mean_predicted": sum(q for q, _ in members) / len(members),
                "observed_rate": sum(y for _, y in members) / len(members),
            }
        )
    return {
        "brier_score": brier,
        "log_loss": log_loss,
        "calibration_bins": table,
        "decided_game_count": len(decided),
        "status": FAILURE_NONE,
    }


def score_candidate(
    candidate: CalibrationCandidate,
    observations: ObservationSet,
    authority: ExpectedMarginAuthority,
    *,
    scored_split: str = "validation",
    sd_override: GameSdEstimate | None = None,
    witnesses: WitnessRatings | None = None,
) -> CandidateScore:
    """Score one candidate by temporal walk-forward over the whole corpus.

    State evolves across every observation in chronological order; metrics are
    computed only over predictions falling in ``scored_split``. That is what makes
    a validation number out-of-sample without a second pass: by the time a
    validation game is predicted, the state behind it has seen training games and
    earlier validation games, and nothing later.

    ``sd_override`` exists for the holdout stage. A holdout run should carry the
    dispersion estimated during validation rather than re-estimating on the
    holdout it is about to score, which would let the holdout inform its own
    diagnostics.
    """
    split_key = scored_split.strip().lower()
    if split_key not in cal.DATA_SPLITS:
        raise InputValidationError(
            f"scored_split {scored_split!r}; expected one of {list(cal.DATA_SPLITS)}."
        )

    rows = observations.ordered_rows
    predictions, cap, movement, extras = _walk_forward(candidate, rows, authority)
    leakage = require_no_future_leakage(predictions)

    scored = [p for p in predictions if p.split == split_key]
    metrics = _mean_model_metrics(scored)

    if sd_override is not None:
        game_sd: GameSdEstimate | None = require_residual_based_game_sd(sd_override)
    elif split_key == "training":
        # Selection never happens on training, and a training dispersion is
        # inadmissible, so no estimate is produced rather than a refused one.
        game_sd = None
    else:
        try:
            game_sd = estimate_game_sd_points(
                [p.residual for p in scored], split=split_key
            )
        except (GovernanceBlock, InputValidationError):
            game_sd = None

    diagnostics = _probabilistic_diagnostics(scored, game_sd.value if game_sd else 0.0)
    metrics.update(
        {
            "brier_score": diagnostics["brier_score"],
            "log_loss": diagnostics["log_loss"],
            "calibration_bins": diagnostics["calibration_bins"],
            "probabilistic_diagnostics_status": diagnostics["status"],
            "dispersion_source_split": game_sd.split if game_sd else None,
            "dispersion_independent_of_scored_split": bool(
                game_sd and sd_override is not None
            ),
        }
    )

    # Witnesses are computed from the scored split's own games, and the candidate
    # ratings they are compared against are that split's closing strengths. Comparing
    # a whole-corpus witness against one season's ratings would report a correlation
    # between two different spans and call it coherence.
    scored_rows = [r for r in rows if r.normalized_split == split_key]
    witness_ratings = (
        witnesses if witnesses is not None else compute_witnesses(scored_rows)
    )
    season_finals: dict[int, dict[str, float]] = extras["season_final_strengths"]
    scored_season = max(int(r.season) for r in scored_rows)
    final_strengths = season_finals.get(scored_season, {})
    colley_rho = spearman_rank_correlation(final_strengths, witness_ratings.colley)
    srs_rho = spearman_rank_correlation(final_strengths, witness_ratings.srs)
    witness_fields = {
        "colley_rank_correlation": colley_rho,
        "colley_directionally_coherent": (
            None if colley_rho is None else colley_rho >= WITNESS_COHERENCE_THRESHOLD
        ),
        "colley_status": witness_ratings.colley_status,
        "colley_team_count": len(witness_ratings.colley),
        "srs_rank_correlation": srs_rho,
        "srs_directionally_coherent": (
            None if srs_rho is None else srs_rho >= WITNESS_COHERENCE_THRESHOLD
        ),
        "srs_status": witness_ratings.srs_status,
        "srs_team_count": len(witness_ratings.srs),
        "witness_coherence_threshold": WITNESS_COHERENCE_THRESHOLD,
        "blended_into_primary_criterion": False,
        "scales_converted_to_v3_points": False,
    }

    return CandidateScore(
        candidate=candidate,
        scored_split=split_key,
        split_counts=observations.split_counts(),
        predictions=tuple(predictions),
        metrics=metrics,
        cap=cap,
        movement=movement,
        game_sd=game_sd,
        witness_fields=witness_fields,
        regularization_report=candidate.regularization.report(),
        recent_form_report=extras["recent_form"],
        leakage_proof=leakage,
    )


# --- shard output ------------------------------------------------------------


@dataclass(frozen=True)
class ShardResultRow:
    """One row of one worker's deterministic result table."""

    candidate_id: int
    candidate_key: str
    parameters: dict[str, Any]
    stage: str
    shard_index: int
    shard_count: int
    train_count: int
    validation_count: int
    holdout_count: int
    scored_split: str
    baxter_rmse: float | None
    baxter_mae: float | None
    brier_score: float | None
    log_loss: float | None
    winner_accuracy: float | None
    game_sd_points: float | None
    game_sd_method: str | None
    cap_hit_count: int
    cap_hit_rate: float
    max_uncapped_update: float
    max_capped_update: float
    cap_identified: bool
    movement_mean: float
    movement_sd: float
    movement_p95: float
    movement_max: float
    colley_rank_correlation: float | None
    colley_directionally_coherent: bool | None
    srs_rank_correlation: float | None
    srs_directionally_coherent: bool | None
    failure_status: str
    failure_reason: str | None
    input_dataset_sha: str
    split_sha: str
    expected_margin_authority_id: str
    experiment_config_sha: str
    model_version: str
    regularization: dict[str, Any]
    recent_form: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "candidate_key": self.candidate_key,
            "parameters": dict(self.parameters),
            "stage": self.stage,
            "shard_index": self.shard_index,
            "shard_count": self.shard_count,
            "train_count": self.train_count,
            "validation_count": self.validation_count,
            "holdout_count": self.holdout_count,
            "scored_split": self.scored_split,
            "baxter_rmse": self.baxter_rmse,
            "baxter_mae": self.baxter_mae,
            "brier_score": self.brier_score,
            "log_loss": self.log_loss,
            "winner_accuracy": self.winner_accuracy,
            "game_sd_points": self.game_sd_points,
            "game_sd_method": self.game_sd_method,
            "cap_hit_count": self.cap_hit_count,
            "cap_hit_rate": self.cap_hit_rate,
            "max_uncapped_update": self.max_uncapped_update,
            "max_capped_update": self.max_capped_update,
            "cap_identified": self.cap_identified,
            "movement_mean": self.movement_mean,
            "movement_sd": self.movement_sd,
            "movement_p95": self.movement_p95,
            "movement_max": self.movement_max,
            "colley_rank_correlation": self.colley_rank_correlation,
            "colley_directionally_coherent": self.colley_directionally_coherent,
            "srs_rank_correlation": self.srs_rank_correlation,
            "srs_directionally_coherent": self.srs_directionally_coherent,
            "failure_status": self.failure_status,
            "failure_reason": self.failure_reason,
            "input_dataset_sha": self.input_dataset_sha,
            "split_sha": self.split_sha,
            "expected_margin_authority_id": self.expected_margin_authority_id,
            "experiment_config_sha": self.experiment_config_sha,
            "model_version": self.model_version,
            "regularization": dict(self.regularization),
            "recent_form": dict(self.recent_form),
        }


def _failed_row(
    candidate: CalibrationCandidate,
    *,
    status: str,
    reason: str,
    stage: str,
    shard_index: int,
    shard_count: int,
    observations: ObservationSet,
    authority: ExpectedMarginAuthority,
    config_sha: str,
    model_version: str,
) -> ShardResultRow:
    counts = observations.split_counts()
    return ShardResultRow(
        candidate_id=candidate.candidate_id,
        candidate_key=candidate.candidate_key,
        parameters=candidate.parameter_vector(),
        stage=stage,
        shard_index=shard_index,
        shard_count=shard_count,
        train_count=counts["training"],
        validation_count=counts["validation"],
        holdout_count=counts["holdout"],
        scored_split="",
        baxter_rmse=None,
        baxter_mae=None,
        brier_score=None,
        log_loss=None,
        winner_accuracy=None,
        game_sd_points=None,
        game_sd_method=None,
        cap_hit_count=0,
        cap_hit_rate=0.0,
        max_uncapped_update=0.0,
        max_capped_update=0.0,
        cap_identified=False,
        movement_mean=0.0,
        movement_sd=0.0,
        movement_p95=0.0,
        movement_max=0.0,
        colley_rank_correlation=None,
        colley_directionally_coherent=None,
        srs_rank_correlation=None,
        srs_directionally_coherent=None,
        failure_status=status,
        failure_reason=reason,
        input_dataset_sha=observations.dataset_sha,
        split_sha=observations.split_sha,
        expected_margin_authority_id=authority.authority_id,
        experiment_config_sha=config_sha,
        model_version=model_version,
        regularization={},
        recent_form={},
    )


def score_shard(
    candidates: Sequence[CalibrationCandidate],
    observations: ObservationSet,
    authority: ExpectedMarginAuthority,
    *,
    stage: str,
    shard_index: int,
    shard_count: int,
    config_sha: str,
    model_version: str,
    scored_split: str = "validation",
    sd_override: GameSdEstimate | None = None,
) -> tuple[ShardResultRow, ...]:
    """Score every candidate this worker owns, emitting one row each.

    Per-candidate failures become rows rather than exceptions. A shard that dies
    on candidate 400 of 540 loses the other 140 evaluations and, worse, returns a
    file the aggregator will reject for missing ids without saying why any of them
    are missing. A recorded failure carries its own reason to the aggregator.

    Whole-run refusals are different and are raised before the loop: an ungoverned
    authority or a corpus whose transform disagrees is not a property of any one
    candidate, and retrying it 540 times would only produce 540 identical refusals.
    """
    assert_matches_governed_config()
    observations.require_authority_agreement(authority)
    # Candidate-independent, so computed once for the whole shard rather than once
    # per candidate: a Colley and an SRS solve per candidate would dominate a run
    # whose witnesses cannot change between candidates.
    witnesses = compute_witnesses(
        [
            r
            for r in observations.ordered_rows
            if r.normalized_split == scored_split.strip().lower()
        ]
    )

    rows: list[ShardResultRow] = []
    counts = observations.split_counts()
    for candidate in candidates:
        try:
            score = score_candidate(
                candidate,
                observations,
                authority,
                scored_split=scored_split,
                sd_override=sd_override,
                witnesses=witnesses,
            )
        except (GovernanceBlock, InputValidationError, ValueError, ZeroDivisionError) as exc:
            status = (
                FAILURE_GOVERNANCE if isinstance(exc, GovernanceBlock) else FAILURE_INPUT
            )
            rows.append(
                _failed_row(
                    candidate,
                    status=status,
                    reason=str(exc),
                    stage=stage,
                    shard_index=shard_index,
                    shard_count=shard_count,
                    observations=observations,
                    authority=authority,
                    config_sha=config_sha,
                    model_version=model_version,
                )
            )
            continue

        metrics = score.metrics
        rows.append(
            ShardResultRow(
                candidate_id=candidate.candidate_id,
                candidate_key=candidate.candidate_key,
                parameters=candidate.parameter_vector(),
                stage=stage,
                shard_index=shard_index,
                shard_count=shard_count,
                train_count=counts["training"],
                validation_count=counts["validation"],
                holdout_count=counts["holdout"],
                scored_split=score.scored_split,
                baxter_rmse=metrics["baxter_rmse"],
                baxter_mae=metrics["baxter_mae"],
                brier_score=metrics["brier_score"],
                log_loss=metrics["log_loss"],
                winner_accuracy=metrics["winner_accuracy"],
                game_sd_points=score.game_sd.value if score.game_sd else None,
                game_sd_method=score.game_sd.method if score.game_sd else None,
                cap_hit_count=score.cap.cap_hit_count,
                cap_hit_rate=score.cap.cap_hit_rate,
                max_uncapped_update=score.cap.max_uncapped_update,
                max_capped_update=score.cap.max_capped_update,
                cap_identified=score.cap.identified,
                movement_mean=score.movement.mean,
                movement_sd=score.movement.sd,
                movement_p95=score.movement.p95,
                movement_max=score.movement.maximum,
                colley_rank_correlation=score.witness_fields["colley_rank_correlation"],
                colley_directionally_coherent=score.witness_fields[
                    "colley_directionally_coherent"
                ],
                srs_rank_correlation=score.witness_fields["srs_rank_correlation"],
                srs_directionally_coherent=score.witness_fields["srs_directionally_coherent"],
                failure_status=FAILURE_NONE,
                failure_reason=None,
                input_dataset_sha=observations.dataset_sha,
                split_sha=observations.split_sha,
                expected_margin_authority_id=authority.authority_id,
                experiment_config_sha=config_sha,
                model_version=model_version,
                regularization=score.regularization_report,
                recent_form=score.recent_form_report,
            )
        )
    return tuple(rows)


def shard_table_as_dict(
    rows: Sequence[ShardResultRow],
    *,
    stage: str,
    shard_index: int,
    shard_count: int,
    observations: ObservationSet,
    authority: ExpectedMarginAuthority,
    config_sha: str,
    model_version: str,
) -> dict[str, Any]:
    """One worker's whole emission: a header the aggregator checks, then the rows.

    The header repeats what every row already carries. That redundancy is the
    point: the aggregator can reject a mismatched shard on the header without
    parsing rows, and a header that disagrees with its own rows is itself a
    detectable corruption.
    """
    return {
        "stage": stage,
        "shard_index": shard_index,
        "shard_count": shard_count,
        "row_count": len(rows),
        "input_dataset_sha": observations.dataset_sha,
        "split_sha": observations.split_sha,
        "expected_margin_authority_id": authority.authority_id,
        "expected_margin_authority": authority.as_dict(),
        "experiment_config_sha": config_sha,
        "model_version": model_version,
        "dataset_provenance": observations.provenance,
        "split_counts": observations.split_counts(),
        "writes_canonical_config": False,
        "parameters_promoted": 0,
        "rows": [r.as_dict() for r in sorted(rows, key=lambda r: r.candidate_id)],
    }
