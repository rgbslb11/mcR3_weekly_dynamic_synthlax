"""Experiment harness for the one open FCS question: the point-scale adapter.

Ruling R2-FCS-ELO-1250 fixes FCS at **Elo 1250** and that is not reopened here.
:mod:`.fcs` already records why the adapter onto the unified neutral-field point
axis cannot be read out of the mounted 2026 corpus: the 13 schedule-only FCS
entities are not members of the closed 121-team FBS population the axis is
standardized over, and the only issued Elo relation covers 0.125 of it. That
module's answer is a refusal, and it is the correct answer *to a question asked
of the 2026 corpus alone*.

This module asks a different question, of different evidence::

    What V3 neutral-field football-point representation of the fixed FCS Elo
    1250 best explains real FBS-versus-FCS results?

That is an empirical question, and :data:`~.fcs.RECOGNISED_SCALE_AUTHORITIES`
already names the route it would travel: ``MARGIN_CALIBRATED_HOLDOUT``. What
this module supplies is the harness that route needs — an observation contract,
the governed expected-margin transform written in the FBS team's orientation, a
deterministic coarse-to-fine search over the unknown baseline, out-of-sample
validation, an uncertainty characterisation and an identification verdict.

What it deliberately does not supply
------------------------------------
A number. Two inputs are missing and neither is manufacturable here.

**The corpus.** :func:`bind_research_corpus` accepts a corpus only against
re-read bytes, a matching SHA-256 and an audit token. A candidate exists — see
:data:`CANDIDATE_CORPUS_ASSESSMENT` — and it is *not* bound: its own lane
terminal is ``READY_FOR_AUDIT``, which is a request for an audit, not the result
of one.

**The pregame FBS point states.** Every observation needs the FBS side's
strength *before kickoff*, on the V3 unified neutral-field axis, for a season
that is not 2026. That axis is **empirically calibratable** — the programme
classification is that its scale comes from real Week 1-2 margins once
historical opening standardized states exist — so this lane waits on a
calibration result, not on an authority. No ruling gates FCS scale estimation.
Until that result exists :func:`fit_fcs_point_baseline` refuses rather than
fitting, because a baseline fitted against an unestablished axis is not the FCS
baseline; see below.

The structural reason a corpus alone can never close this
---------------------------------------------------------
The FCS baseline enters :func:`expected_fbs_margin` as a pure additive location
term. Its least-squares estimate is therefore an arithmetic mean::

    F_hat = mean(fbs_pregame_points + venue_term - actual_margin_fbs)

which shifts one-for-one with any constant offset in ``fbs_pregame_points``. So
an unanchored historical axis does not merely make the fit imprecise, it makes
the fitted value *mean something different*: F_hat estimates the FCS baseline
plus the axis offset, and no quantity of observations separates the two.
:func:`anchor_confounding_statement` puts this in the artifact rather than
leaving an auditor to notice it. The same algebra is why a fitted value is not
"the FCS scale measured" unless the axis it was measured against is governed.

The venue term carries a second, smaller version of the same problem, and it is
handled the same way: :func:`expected_fbs_margin` refuses an unclassified venue
instead of defaulting, because a neutral site scored as a home game moves the
venue term by the full governed HFA and that displacement lands entirely in
F_hat. :func:`venue_misclassification_envelope` quantifies it.

Scope limits, all deliberate
----------------------------
* No canonical configuration is written and no adapter is registered. This
  module never calls :func:`.fcs.register_fcs_scale_adapter`; a research result
  is evidence for a human gate, not a substitute for one.
* One global FCS baseline, matching the governed one-fixed-Elo model. No
  team-specific, season-specific or conference-specific FCS values.
* No calibration parameter is fitted. This lane owns the FCS scale and nothing
  else.
* No season simulation, no probabilities, no sampling. Every number here is a
  closed-form function of the observations.
"""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from .errors import GovernanceBlock
from .fcs import (
    FCS_FIXED_ELO,
    FCS_FIXED_ELO_POLICY,
    FCS_UNIFIED_SCALE_BLOCKER,
    FORBIDDEN_BOARD_EQUIVALENTS,
    UNIFIED_NEUTRAL_POINTS_PER_SD,
    UNIFIED_POINTS_OBSERVED_RANGE,
    UNIFIED_Z_POPULATION_SIZE,
    reject_board_derived_conversion,
    reject_elo_as_points,
    require_fcs_hfa_modifier,
)
from .hfa import V3_FOOTBALL_POINT_HFA
from .rulings import R2_FCS, R2_HFA
from .textio import write_json_lf

#: Identity of this research lane. Recorded on every artifact it emits.
RESEARCH_LANE_ID = "V3-FCS-SCALE-RESEARCH-R1"

#: The blocker this lane studies. Studying is not retiring: see
#: :data:`PROMOTION_AUTHORISED`, a constant rather than a computed field.
STUDIED_BLOCKER = FCS_UNIFIED_SCALE_BLOCKER

#: This lane never authorises promotion. Held as a module constant so that no
#: code path can compute its way to True.
PROMOTION_AUTHORISED = False

#: The axis declaration an observation's point states must carry. A residual
#: computed across two axes is arithmetic, not evidence.
GOVERNED_STRENGTH_DOMAIN = "V3_UNIFIED_NEUTRAL_FIELD_POINTS"

#: Venue in the SUBJECT team's orientation, the subject being the FBS side. The
#: V3 schedule stores venue home-oriented over ``Literal["HOME", "NEUTRAL"]``
#: because a scheduled game names its own home team. An FBS-versus-FCS
#: observation has no such convention and the 2026 schedule already carries
#: three rows placing an FCS entity at a HOME venue, so the orientation is
#: stated rather than inferred from column order.
VENUE_VALUES = ("HOME", "AWAY", "NEUTRAL")

#: The venue term's sign in the FBS side's orientation. NEUTRAL is exactly 0.0,
#: matching ``game.simulate_game``; it is not a small HFA.
VENUE_SIGN = {"HOME": 1.0, "AWAY": -1.0, "NEUTRAL": 0.0}


# ---------------------------------------------------------------------------
# Invariants this lane must not move.
# ---------------------------------------------------------------------------

def assert_fcs_elo_invariant() -> float:
    """The fixed Elo is 1250 and this lane does not change it.

    Read from :mod:`.fcs` rather than restated, so a drift there fails here
    instead of leaving two constants to disagree quietly.
    """
    if FCS_FIXED_ELO != 1250.0:
        raise GovernanceBlock(
            f"FCS fixed Elo is {FCS_FIXED_ELO}, not 1250. Ruling "
            f"{R2_FCS.convergence_id} fixes it at 1250 and this research lane has no "
            "authority to move it."
        )
    return FCS_FIXED_ELO


def assert_no_legacy_board_substitution(candidate: float) -> float:
    """Refuse a candidate baseline that is a Board equivalent or an Elo magnitude.

    The recorded Board equivalents 0.294, 0.297 and 0.297514 are explicitly
    rejected as the FCS translation, and
    :func:`.fcs.reject_board_derived_conversion` additionally reconstructs the
    inversion for the governed Elo so the refusal does not rest on a literal
    blacklist. Applied to every value this lane reports, not only to values a
    caller proposes.
    """
    reject_board_derived_conversion(candidate)
    reject_elo_as_points(candidate)
    return float(candidate)


# ---------------------------------------------------------------------------
# Corpus binding.
# ---------------------------------------------------------------------------

#: Source authority classes admissible as FBS-versus-FCS result evidence.
ADMISSIBLE_CORPUS_AUTHORITY_CLASSES = ("GOVERNED_RESULT_SOURCE",)

#: A corpus is bound only against a token of this shape, issued by a human who
#: has audited it. Shaped like the FCS adapter approval token for the same
#: reason: a structurally valid artifact is still not an accepted one.
CORPUS_AUDIT_TOKEN_PREFIX = "AUDITED_V3_FCS_RESEARCH_CORPUS::"


@dataclass(frozen=True)
class ResearchCorpus:
    """A corpus bound by exact bytes, exact digest and an explicit audit."""

    corpus_id: str
    path: Path
    sha256: str
    rows: int
    source_authority: str
    source_authority_class: str
    audit_token: str
    seasons: tuple[int, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "corpus_id": self.corpus_id,
            "path": self.path.as_posix(),
            "sha256": self.sha256,
            "rows": self.rows,
            "source_authority": self.source_authority,
            "source_authority_class": self.source_authority_class,
            "seasons": list(self.seasons),
            "bound": True,
        }


def bind_research_corpus(
    *,
    corpus_id: str,
    path: Path,
    expected_sha256: str,
    source_authority: str,
    source_authority_class: str,
    audit_token: str,
    seasons: Sequence[int],
    rows: int,
) -> ResearchCorpus:
    """Bind a corpus by re-reading its bytes.

    A digest supplied alongside a row count is two caller-supplied strings
    agreeing with each other. This recomputes the digest from the bytes on disk,
    so a corpus that has moved, changed or never existed fails at binding rather
    than at review.
    """
    if not str(corpus_id or "").strip():
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a research corpus must carry a stable corpus_id."
        )
    if not path.is_file():
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: corpus {corpus_id} is not readable at "
            f"{path.as_posix()}. A corpus that cannot be re-read cannot be bound; a "
            "research result must stay tied to the exact bytes it was computed from."
        )
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != str(expected_sha256).lower():
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: corpus {corpus_id} digest mismatch — bytes on disk "
            f"hash to {actual}, the binding declared {expected_sha256}."
        )
    if source_authority_class not in ADMISSIBLE_CORPUS_AUTHORITY_CLASSES:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: source authority class {source_authority_class!r} is "
            f"not admissible; admissible classes are "
            f"{list(ADMISSIBLE_CORPUS_AUTHORITY_CLASSES)}."
        )
    if not str(audit_token or "").startswith(CORPUS_AUDIT_TOKEN_PREFIX):
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: corpus {corpus_id} carries no audit token. A lane "
            "reporting READY_FOR_AUDIT has requested an audit, not passed one, and its "
            "artifacts stay a candidate until an audit says otherwise. Expected "
            f"{CORPUS_AUDIT_TOKEN_PREFIX}<AUDIT_ID>."
        )
    if rows <= 0:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: corpus {corpus_id} declares {rows} rows."
        )
    return ResearchCorpus(
        corpus_id=corpus_id,
        path=path,
        sha256=actual,
        rows=int(rows),
        source_authority=source_authority,
        source_authority_class=source_authority_class,
        audit_token=audit_token,
        seasons=tuple(sorted({int(s) for s in seasons})),
    )


# ---------------------------------------------------------------------------
# The observation contract.
# ---------------------------------------------------------------------------

#: What a usable FBS-versus-FCS observation must carry, and why. An observation
#: missing any *numeric* requirement is still recorded — it is structurally
#: ready and numerically unavailable, which is a different state from absent.
OBSERVATION_REQUIREMENTS: dict[str, str] = {
    "game_id": "Stable unique key, so a residual can be traced to one real game.",
    "season": "Bounds the population the strength axis is standardized over.",
    "week": "Decides whether the pregame state is opening strength or a rerating.",
    "order_key": (
        "Kickoff instant. The only field that can prove a pregame state pre-dates "
        "the game it predicts when two games share a week."
    ),
    "fbs_team": "Canonical team id of the FBS side. Free-text names are refused.",
    "fcs_team": "Canonical team id of the FCS side.",
    "fbs_score": "Real score, FBS side.",
    "fcs_score": "Real score, FCS side.",
    "fbs_pregame_points": (
        "FBS strength before kickoff on the declared axis. Never invented; an "
        "observation without it is structurally ready and numerically unavailable."
    ),
    "strength_domain": (
        "Axis declaration. Must be V3_UNIFIED_NEUTRAL_FIELD_POINTS for the governed "
        "transform to apply."
    ),
    "venue": (
        "HOME | AWAY | NEUTRAL from the FBS side's perspective. Never inferred from "
        "a designated-home column, because a neutral site is designated-home too."
    ),
    "venue_classification_source": (
        "Named authority for the venue call. A venue with no source is an assumption."
    ),
    "hfa_baseline_points": "Governed football-point HFA baseline. Never defaulted.",
    "home_hfa_modifier": (
        "Modifier of whichever side is at home. Null only at NEUTRAL, where the "
        "venue term is exactly 0.0. Never defaulted to 1.0."
    ),
    "source_provenance": "Named provenance for the row and for the point state.",
}

#: Readiness states an observation can be in. The middle one is the point of the
#: distinction: a real game with a real score and no governed pregame FBS point
#: state is evidence that exists and cannot yet be scored.
READY_FOR_FIT = "NUMERICALLY_READY"
STRUCTURALLY_READY = "STRUCTURALLY_READY_NUMERICALLY_UNAVAILABLE"
VENUE_AMBIGUOUS = "VENUE_AMBIGUOUS_EXCLUDED"


@dataclass(frozen=True)
class FbsVsFcsObservation:
    """One real FBS-versus-FCS game, in the FBS side's orientation.

    ``fbs_pregame_points``, ``venue`` and ``home_hfa_modifier`` are optional at
    construction and mandatory at fit. That split is the whole design: the
    harness can hold and count an observation it cannot yet score, instead of
    the corpus having to choose between fabricating a field and dropping a real
    game.
    """

    game_id: str
    season: int
    week: int
    order_key: str
    fbs_team: str
    fcs_team: str
    fbs_score: int
    fcs_score: int
    source_provenance: str
    fbs_pregame_points: float | None = None
    strength_domain: str | None = None
    venue: str | None = None
    venue_classification_source: str | None = None
    hfa_baseline_points: float | None = None
    home_hfa_modifier: float | None = None

    def __post_init__(self) -> None:
        for name in ("game_id", "fbs_team", "fcs_team", "order_key", "source_provenance"):
            if not str(getattr(self, name) or "").strip():
                raise GovernanceBlock(
                    f"{STUDIED_BLOCKER}: observation is missing {name!r}. "
                    f"{OBSERVATION_REQUIREMENTS[name]}"
                )
        if self.venue is not None and self.venue not in VENUE_VALUES:
            raise GovernanceBlock(
                f"{STUDIED_BLOCKER}: {self.game_id} declares venue {self.venue!r}; the "
                f"FBS-oriented vocabulary is {list(VENUE_VALUES)}."
            )
        if self.week <= 0:
            raise GovernanceBlock(
                f"{STUDIED_BLOCKER}: {self.game_id} declares week {self.week}."
            )

    @property
    def actual_margin_fbs(self) -> int:
        """Real margin from the FBS side. Derived from scores, never supplied."""
        return int(self.fbs_score) - int(self.fcs_score)

    @property
    def fbs_won(self) -> bool:
        return self.actual_margin_fbs > 0

    def readiness(self) -> str:
        """Which of the three states this observation is in.

        Venue ambiguity is reported ahead of the missing point state because it
        is the harder problem: a point state can be supplied later by an
        authority that already exists in principle, whereas a venue that no
        source published has to be classified from separate evidence.
        """
        if self.venue is None or not str(self.venue_classification_source or "").strip():
            return VENUE_AMBIGUOUS
        if self.fbs_pregame_points is None:
            return STRUCTURALLY_READY
        if self.strength_domain != GOVERNED_STRENGTH_DOMAIN:
            return STRUCTURALLY_READY
        if self.hfa_baseline_points is None and self.venue != "NEUTRAL":
            return STRUCTURALLY_READY
        return READY_FOR_FIT

    def require_numerically_usable(self) -> "FbsVsFcsObservation":
        """Fail closed, naming the one input that is missing.

        Every branch here is a refusal that a permissive implementation would
        have written as a default. There is no ``or 1.0``, no ``or HOME`` and no
        substituted point state.
        """
        if self.venue is None:
            raise GovernanceBlock(
                f"{STUDIED_BLOCKER}: {self.game_id} has no venue classification. The "
                "designated-home column of a result feed does not distinguish a true "
                "home game from a neutral-site game, and the two differ by the full "
                f"governed HFA of {V3_FOOTBALL_POINT_HFA} points, which lands entirely "
                "in the fitted FCS baseline. Classify it from authoritative evidence or "
                "exclude it; do not assume it."
            )
        if not str(self.venue_classification_source or "").strip():
            raise GovernanceBlock(
                f"{STUDIED_BLOCKER}: {self.game_id} declares venue {self.venue} with no "
                "classification source. A venue with no named authority is an assumption "
                "wearing a field name."
            )
        if self.fbs_pregame_points is None:
            raise GovernanceBlock(
                f"{STUDIED_BLOCKER}: {self.game_id} has no pregame FBS point state. It is "
                f"{STRUCTURALLY_READY}: the game, the score and the sides are real, and "
                "the predictor half of the residual does not exist. Inventing one would "
                "make the fitted FCS baseline a function of the invention."
            )
        if self.strength_domain != GOVERNED_STRENGTH_DOMAIN:
            raise GovernanceBlock(
                f"{STUDIED_BLOCKER}: {self.game_id} declares strength_domain "
                f"{self.strength_domain!r}; the governed transform applies only to "
                f"{GOVERNED_STRENGTH_DOMAIN}. A residual computed across two axes is "
                "arithmetic, not evidence."
            )
        return self

    def as_dict(self) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "season": self.season,
            "week": self.week,
            "order_key": self.order_key,
            "fbs_team": self.fbs_team,
            "fcs_team": self.fcs_team,
            "fbs_score": self.fbs_score,
            "fcs_score": self.fcs_score,
            "actual_margin_fbs": self.actual_margin_fbs,
            "fbs_pregame_points": self.fbs_pregame_points,
            "strength_domain": self.strength_domain,
            "venue": self.venue,
            "venue_classification_source": self.venue_classification_source,
            "hfa_baseline_points": self.hfa_baseline_points,
            "home_hfa_modifier": self.home_hfa_modifier,
            "source_provenance": self.source_provenance,
            "readiness": self.readiness(),
        }


# ---------------------------------------------------------------------------
# The governed expected-margin transform, in the FBS side's orientation.
# ---------------------------------------------------------------------------

#: FACT — ``game.simulate_game``. Transcribed, not paraphrased, so a drift in
#: production is visible here as a difference between two strings.
PRODUCTION_MARGIN_FORM = (
    "hfa = 0.0 if game.venue == 'NEUTRAL' else hfa_baseline_points * home_hfa_modifier; "
    "expected = home.current_strength_points - away.current_strength_points + hfa"
)


def venue_term(
    *,
    venue: str,
    hfa_baseline_points: float | None,
    home_hfa_modifier: float | None,
    game_id: str = "<observation>",
    fcs_is_home: bool = False,
) -> float:
    """The venue contribution to the FBS side's expected margin.

    Derived from the production form rather than restated. Production is
    home-oriented and adds ``+hfa`` to the home team; re-orienting onto the FBS
    side gives ``+hfa`` when the FBS side is home, ``-hfa`` when the FCS side is
    home, and exactly ``0.0`` at a neutral site — where the modifier is not
    consulted at all, because production does not consult it either.

    When the FCS side is the home team the modifier being asked for belongs to
    an FCS entity, and POWER_CRUNCH records every one of those as ``UNRESOLVED``.
    That case is routed through :func:`.fcs.require_fcs_hfa_modifier` so it
    refuses with the reason rather than with a generic message.
    """
    if venue not in VENUE_VALUES:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: {game_id} declares venue {venue!r}; the FBS-oriented "
            f"vocabulary is {list(VENUE_VALUES)}."
        )
    if venue == "NEUTRAL":
        # Exactly 0.0, as production computes it. Fails closed nowhere because
        # nothing is consumed: a neutral game needs no modifier.
        return 0.0
    if hfa_baseline_points is None:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: {game_id} is a {venue} game with no HFA baseline. "
            f"Ruling {R2_HFA.convergence_id} sets the V3 football-point baseline to "
            f"{V3_FOOTBALL_POINT_HFA}; it must be supplied, not defaulted."
        )
    if fcs_is_home:
        modifier = require_fcs_hfa_modifier(home_hfa_modifier, game_id)
    elif home_hfa_modifier is None:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: {game_id} is a {venue} game with no home-field "
            "modifier. Production multiplies the baseline by the home side's modifier; "
            "defaulting it to 1.0 would fabricate a governed quantity."
        )
    else:
        modifier = float(home_hfa_modifier)
    return VENUE_SIGN[venue] * float(hfa_baseline_points) * modifier


def expected_fbs_margin(
    observation: FbsVsFcsObservation,
    fcs_point_baseline: float,
) -> float:
    """Expected margin for the FBS side under a candidate FCS point baseline.

    ``fbs_pregame_points - fcs_point_baseline + venue_term``, which is the
    production form re-oriented onto the FBS side. The candidate baseline is
    checked against the refused conversions on every evaluation, so a search
    cannot walk onto a forbidden value and report it as an optimum.
    """
    observation.require_numerically_usable()
    assert_no_legacy_board_substitution(fcs_point_baseline)
    term = venue_term(
        venue=str(observation.venue),
        hfa_baseline_points=observation.hfa_baseline_points,
        home_hfa_modifier=observation.home_hfa_modifier,
        game_id=observation.game_id,
        fcs_is_home=observation.venue == "AWAY",
    )
    return float(observation.fbs_pregame_points) - float(fcs_point_baseline) + term


# ---------------------------------------------------------------------------
# Metrics.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResidualMetrics:
    """The full residual picture. Winner accuracy is reported, never optimised.

    A margin model scored on winner accuracy is scored on the sign of its own
    output, which an FBS-versus-FCS sample makes nearly free: the FBS side wins
    most of these games, so a baseline far from the truth still calls most
    winners. RMSE is the primary objective for exactly that reason.
    """

    n: int
    rmse: float
    mae: float
    bias: float
    median_residual: float
    residual_sd: float
    winner_accuracy: float

    def as_dict(self) -> dict[str, object]:
        return {
            "n": self.n,
            "rmse": round(self.rmse, 6),
            "mae": round(self.mae, 6),
            "bias": round(self.bias, 6),
            "median_residual": round(self.median_residual, 6),
            "residual_sd": round(self.residual_sd, 6),
            "winner_accuracy": round(self.winner_accuracy, 6),
        }


def residuals(
    observations: Sequence[FbsVsFcsObservation],
    fcs_point_baseline: float,
) -> list[float]:
    """Actual minus expected, FBS-oriented, one per observation."""
    return [
        float(o.actual_margin_fbs) - expected_fbs_margin(o, fcs_point_baseline)
        for o in observations
    ]


def score(
    observations: Sequence[FbsVsFcsObservation],
    fcs_point_baseline: float,
) -> ResidualMetrics:
    """Score a candidate baseline over a set of numerically usable observations."""
    if not observations:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: cannot score an empty observation set. An objective "
            "over zero games is not a small sample, it is no evidence."
        )
    res = residuals(observations, fcs_point_baseline)
    n = len(res)
    correct = 0
    for obs in observations:
        predicted_fbs_win = expected_fbs_margin(obs, fcs_point_baseline) >= 0.0
        if predicted_fbs_win == obs.fbs_won:
            correct += 1
    return ResidualMetrics(
        n=n,
        rmse=math.sqrt(sum(r * r for r in res) / n),
        mae=sum(abs(r) for r in res) / n,
        bias=sum(res) / n,
        median_residual=statistics.median(res),
        residual_sd=statistics.stdev(res) if n > 1 else 0.0,
        winner_accuracy=correct / n,
    )


# ---------------------------------------------------------------------------
# Deterministic coarse-to-fine search.
# ---------------------------------------------------------------------------

#: The default search interval, in unified neutral-field points.
#:
#: Chosen to be wide enough that no optimum inside it is an artefact of the
#: bound. The observed FBS range is -17.4576 to +32.8847, a span of about 50
#: points or 3.6 standard deviations at the governed 14 points/SD. The interval
#: below reaches roughly 7.3 SD below the weakest FBS team and 0.5 SD above the
#: strongest, so a prior that the FCS baseline is "somewhere below FBS" does not
#: constrain the answer. :func:`search_fcs_point_baseline` expands it anyway if
#: the optimum lands on an edge.
DEFAULT_SEARCH_INTERVAL = (-120.0, 40.0)

#: Coarse step, then the factor each refinement divides it by, then how many
#: refinements run. 5.0 / 5 / 4 lands on a final step of 0.008 points.
DEFAULT_COARSE_STEP = 5.0
DEFAULT_REFINEMENT_FACTOR = 5
DEFAULT_REFINEMENTS = 4

#: How many times the search may widen a boundary-hugging interval before it
#: gives up and says so. Each expansion adds a full interval width.
MAX_BOUNDARY_EXPANSIONS = 6

#: An RMSE surface whose best and worst points differ by less than this over the
#: whole coarse grid carries no information about the baseline.
FLAT_SURFACE_TOLERANCE_POINTS = 1e-6

#: Baselines whose RMSE is within this fraction of the best are not materially
#: distinguishable by the objective.
EQUIVALENCE_RELATIVE_TOLERANCE = 0.005

#: A confidence half-width wider than this is reported as weak identification.
#: 4.0 points is about 8% of the observed FBS span and more than the governed
#: HFA, so a baseline known only to within it cannot be told apart from one
#: displaced by a venue error.
MATERIAL_HALF_WIDTH_POINTS = 4.0

SEARCH_OPTIMUM_INTERIOR = "OPTIMUM_INTERIOR"
SEARCH_OPTIMUM_ON_BOUNDARY = "OPTIMUM_ON_BOUNDARY_AFTER_MAX_EXPANSION"
SEARCH_FLAT_SURFACE = "FLAT_SURFACE"


@dataclass(frozen=True)
class SearchResult:
    """The outcome of a deterministic grid search over the FCS baseline."""

    best_baseline: float
    best_rmse: float
    status: str
    interval: tuple[float, float]
    initial_interval: tuple[float, float]
    coarse_step: float
    final_step: float
    refinements: int
    expansions: int
    evaluations: int
    equivalence_range: tuple[float, float]
    surface: tuple[tuple[float, float], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "best_baseline": round(self.best_baseline, 6),
            "best_rmse": round(self.best_rmse, 6),
            "status": self.status,
            "search_interval": [round(v, 6) for v in self.interval],
            "initial_search_interval": [round(v, 6) for v in self.initial_interval],
            "coarse_step": self.coarse_step,
            "final_step": round(self.final_step, 9),
            "refinements": self.refinements,
            "boundary_expansions": self.expansions,
            "evaluations": self.evaluations,
            "rmse_equivalence_range": [round(v, 6) for v in self.equivalence_range],
            "rmse_equivalence_width": round(
                self.equivalence_range[1] - self.equivalence_range[0], 6
            ),
            "surface_around_optimum": [
                [round(b, 6), round(r, 6)] for b, r in self.surface
            ],
        }


def _grid(lo: Decimal, hi: Decimal, step: Decimal) -> list[Decimal]:
    """Half-open-free inclusive grid built on Decimal so ticks are exact.

    Float accumulation would make the grid depend on where it started, which is
    the difference between a deterministic search and one that reproduces to
    within a rounding error.
    """
    out: list[Decimal] = []
    ticks = int((hi - lo) / step)
    for i in range(ticks + 1):
        out.append(lo + step * i)
    if out[-1] != hi:
        out.append(hi)
    return out


def search_fcs_point_baseline(
    observations: Sequence[FbsVsFcsObservation],
    *,
    interval: tuple[float, float] = DEFAULT_SEARCH_INTERVAL,
    coarse_step: float = DEFAULT_COARSE_STEP,
    refinement_factor: int = DEFAULT_REFINEMENT_FACTOR,
    refinements: int = DEFAULT_REFINEMENTS,
    max_expansions: int = MAX_BOUNDARY_EXPANSIONS,
) -> SearchResult:
    """Search the FCS point baseline by deterministic coarse-to-fine grid.

    Three outcomes are distinguished rather than collapsed.

    An **interior** optimum is a real optimum. A **boundary** optimum is not: it
    means the interval, not the evidence, chose the answer, so the interval is
    widened by a full width and the search restarts. Only after
    ``max_expansions`` does the search report the boundary as the finding.

    A **flat** surface is reported as such. If the best and worst RMSE over the
    whole coarse grid differ by less than
    :data:`FLAT_SURFACE_TOLERANCE_POINTS`, the objective does not distinguish
    baselines at all and no argmin from it is a measurement.

    Ties are broken toward the lower baseline for reproducibility, and the tie
    is *also* reported through ``equivalence_range`` so a tie-break can never be
    mistaken for a decision.
    """
    if not observations:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: cannot search over an empty observation set."
        )
    if coarse_step <= 0 or refinement_factor < 2 or refinements < 0:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: search parameters must describe a converging grid; got "
            f"step={coarse_step}, factor={refinement_factor}, refinements={refinements}."
        )
    initial = (float(interval[0]), float(interval[1]))
    if initial[0] >= initial[1]:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: search interval {initial} is empty or inverted."
        )

    evaluated: dict[Decimal, float] = {}

    def rmse_at(value: Decimal) -> float:
        if value not in evaluated:
            evaluated[value] = score(observations, float(value)).rmse
        return evaluated[value]

    lo, hi = Decimal(str(initial[0])), Decimal(str(initial[1]))
    step = Decimal(str(coarse_step))
    expansions = 0
    flat = False

    while True:
        grid = _grid(lo, hi, step)
        values = [rmse_at(v) for v in grid]
        best_rmse = min(values)
        if max(values) - best_rmse < FLAT_SURFACE_TOLERANCE_POINTS:
            flat = True
            break
        best_index = values.index(best_rmse)
        if best_index not in (0, len(grid) - 1):
            break
        if expansions >= max_expansions:
            break
        width = hi - lo
        if best_index == 0:
            lo = lo - width
        else:
            hi = hi + width
        expansions += 1

    if flat:
        grid = _grid(lo, hi, step)
        best = min(grid, key=lambda v: (rmse_at(v), v))
        return SearchResult(
            best_baseline=float(best),
            best_rmse=rmse_at(best),
            status=SEARCH_FLAT_SURFACE,
            interval=(float(lo), float(hi)),
            initial_interval=initial,
            coarse_step=float(coarse_step),
            final_step=float(step),
            refinements=0,
            expansions=expansions,
            evaluations=len(evaluated),
            equivalence_range=(float(lo), float(hi)),
            surface=tuple((float(v), rmse_at(v)) for v in grid),
        )

    grid = _grid(lo, hi, step)
    best = min(grid, key=lambda v: (rmse_at(v), v))
    on_boundary = best in (grid[0], grid[-1])
    final_step = step

    if not on_boundary:
        for _ in range(refinements):
            window_lo = max(best - final_step, lo)
            window_hi = min(best + final_step, hi)
            final_step = final_step / refinement_factor
            window = _grid(window_lo, window_hi, final_step)
            best = min(window, key=lambda v: (rmse_at(v), v))

    best_rmse = rmse_at(best)
    threshold = best_rmse * (1.0 + EQUIVALENCE_RELATIVE_TOLERANCE)
    near = sorted(v for v, r in evaluated.items() if r <= threshold)
    equivalence = (float(near[0]), float(near[-1]))

    surface_window = sorted(
        v for v in evaluated if abs(v - best) <= Decimal(str(coarse_step)) * 4
    )
    surface = tuple((float(v), evaluated[v]) for v in surface_window)

    return SearchResult(
        best_baseline=float(best),
        best_rmse=best_rmse,
        status=SEARCH_OPTIMUM_ON_BOUNDARY if on_boundary else SEARCH_OPTIMUM_INTERIOR,
        interval=(float(lo), float(hi)),
        initial_interval=initial,
        coarse_step=float(coarse_step),
        final_step=float(final_step),
        refinements=0 if on_boundary else refinements,
        expansions=expansions,
        evaluations=len(evaluated),
        equivalence_range=equivalence,
        surface=surface,
    )


# ---------------------------------------------------------------------------
# Uncertainty.
# ---------------------------------------------------------------------------

def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function (Lentz's method)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            break
    return h


def regularized_incomplete_beta(a: float, b: float, x: float) -> float:
    """``I_x(a, b)``. Pure stdlib, so the harness carries no numeric dependency."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - _log_beta(a, b))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(
        b * math.log(1.0 - x) + a * math.log(x) - _log_beta(b, a)
    ) * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided_quantile(df: int, level: float = 0.95) -> float:
    """The two-sided t quantile, by bisection on the exact CDF.

    Deterministic to 1e-10 and dependency-free. A normal quantile would
    understate the interval at these sample sizes, which is the direction that
    overstates precision — the one direction this lane must not err in.
    """
    if df < 1:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a t quantile needs at least one degree of freedom; "
            f"df={df} means the sample cannot support an interval at all."
        )
    target = 1.0 - (1.0 - level) / 2.0

    def cdf(t: float) -> float:
        x = df / (df + t * t)
        tail = 0.5 * regularized_incomplete_beta(df / 2.0, 0.5, x)
        return 1.0 - tail if t > 0 else tail

    lo, hi = 0.0, 200.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if cdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2.0, 10)


@dataclass(frozen=True)
class BaselineInterval:
    """A confidence interval on the FCS baseline, and what it is conditional on."""

    point_estimate: float
    standard_error: float
    half_width: float
    lower: float
    upper: float
    level: float
    degrees_of_freedom: int
    conditional_on: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "point_estimate": round(self.point_estimate, 6),
            "standard_error": round(self.standard_error, 6),
            "half_width": round(self.half_width, 6),
            "lower": round(self.lower, 6),
            "upper": round(self.upper, 6),
            "level": self.level,
            "degrees_of_freedom": self.degrees_of_freedom,
            "conditional_on": list(self.conditional_on),
        }


def baseline_interval(
    observations: Sequence[FbsVsFcsObservation],
    fcs_point_baseline: float,
    *,
    level: float = 0.95,
) -> BaselineInterval:
    """Interval for a location parameter: residual SD over the root of n.

    The FCS baseline enters the expected margin additively, so its least-squares
    estimator is a sample mean and its sampling distribution is the textbook one.
    The interval is nonetheless *conditional*, and the conditions are carried in
    the result rather than left to a footnote.
    """
    metrics = score(observations, fcs_point_baseline)
    if metrics.n < 2:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: an interval needs at least two observations; got "
            f"{metrics.n}."
        )
    se = metrics.residual_sd / math.sqrt(metrics.n)
    t = student_t_two_sided_quantile(metrics.n - 1, level)
    half = t * se
    return BaselineInterval(
        point_estimate=float(fcs_point_baseline),
        standard_error=se,
        half_width=half,
        lower=float(fcs_point_baseline) - half,
        upper=float(fcs_point_baseline) + half,
        level=level,
        degrees_of_freedom=metrics.n - 1,
        conditional_on=(
            "the historical pregame FBS point states being on the governed axis",
            "the venue classification of every included observation being correct",
            f"the governed HFA baseline {V3_FOOTBALL_POINT_HFA} (ruling "
            f"{R2_HFA.convergence_id})",
        ),
    )


def observations_required_for_half_width(
    residual_sd: float,
    target_half_width: float,
    *,
    level: float = 0.95,
) -> int:
    """Smallest ``n`` whose interval half-width reaches ``target_half_width``.

    Solved by walking ``n`` upward rather than by the normal-approximation
    closed form, because the t quantile depends on ``n`` too and the closed form
    understates the requirement at exactly the sample sizes this lane deals in.
    """
    if target_half_width <= 0:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a target half-width must be positive; got "
            f"{target_half_width}."
        )
    n = 2
    while n < 100_000:
        if student_t_two_sided_quantile(n - 1, level) * float(residual_sd) / math.sqrt(
            n
        ) <= float(target_half_width):
            return n
        n += 1
    raise GovernanceBlock(
        f"{STUDIED_BLOCKER}: a half-width of {target_half_width} points is not "
        f"reachable at dispersion {residual_sd} within any practical sample."
    )


def precision_envelope(residual_sd: float, n: int, *, level: float = 0.95) -> dict[str, object]:
    """How precisely a sample of size ``n`` could pin the baseline, before fitting.

    A design question, not a result: it consumes a dispersion and a count, never
    a point state or a fitted value. Feeding it the *unconditional* margin SD
    gives an upper bound on the half-width, because conditioning on FBS strength
    can only reduce dispersion.
    """
    if n < 2:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a precision envelope needs at least two observations."
        )
    se = float(residual_sd) / math.sqrt(n)
    t = student_t_two_sided_quantile(n - 1, level)
    return {
        "n": n,
        "residual_sd_input": round(float(residual_sd), 6),
        "standard_error": round(se, 6),
        "t_quantile": t,
        "half_width": round(t * se, 6),
        "level": level,
        "interpretation": (
            "Half-width of the confidence interval on the FCS point baseline that a "
            "sample of this size and dispersion supports. Computed from a dispersion "
            "and a count only; it is a property of the design, not an estimate of the "
            "baseline."
        ),
    }


# ---------------------------------------------------------------------------
# Confounding statements. Both are algebra, and both belong in the artifact.
# ---------------------------------------------------------------------------

def anchor_confounding_statement() -> dict[str, object]:
    """Why an unanchored strength axis is not merely a precision problem."""
    return {
        "id": "FCS_BASELINE_ABSORBS_AXIS_OFFSET",
        "statement": (
            "The FCS baseline enters the expected margin additively, so its "
            "least-squares estimate is mean(fbs_pregame_points + venue_term - "
            "actual_margin_fbs). Adding a constant c to every historical FBS point "
            "state adds exactly c to the fitted baseline and leaves every residual, "
            "every RMSE and the whole objective surface unchanged."
        ),
        "consequence": (
            "The fitted value estimates the FCS baseline plus the offset of whatever "
            "axis the point states were expressed on. No sample size separates them, "
            "so an unanchored axis does not make the estimate imprecise — it makes it "
            "an estimate of a different quantity."
        ),
        "resolution_order": (
            "Anchor the historical strength axis first, then estimate the FCS baseline "
            "against it. The reverse order is not harder, it is unidentified."
        ),
        "detectable_by_more_data": False,
    }


def scale_confounding_statement() -> dict[str, object]:
    """Why the axis *scale*, unlike its offset, leaves a testable signature."""
    return {
        "id": "AXIS_SCALE_LEAVES_A_SLOPE_SIGNATURE",
        "statement": (
            "Scaling the axis by k multiplies the spread of fbs_pregame_points by k "
            "while the observed margins are fixed in real points, so the regression of "
            "(actual_margin_fbs - venue_term) on fbs_pregame_points has slope 1/k "
            "rather than 1."
        ),
        "consequence": (
            "Unlike the offset, a scale error is visible in the data. "
            "unit_slope_witness reports the slope as a diagnostic; a slope far from 1 "
            "is evidence the axis is mis-scaled, not evidence about the FCS baseline."
        ),
        "not_an_estimand_here": (
            "The slope is reported and never fitted into the adapter. The governed FCS "
            "model is one fixed Elo mapped to one point value; adding a scale "
            "parameter would be a different model and this lane has no authority to "
            "propose one."
        ),
        "detectable_by_more_data": True,
    }


def venue_misclassification_envelope(
    *,
    fraction_misclassified: float,
    hfa_baseline_points: float = V3_FOOTBALL_POINT_HFA,
) -> dict[str, object]:
    """How far a fitted baseline moves when neutral sites are scored as home.

    The displacement is exactly ``fraction * hfa``: each misclassified game
    contributes a venue term of ``+hfa`` where the truth is ``0.0``, and the
    baseline is the mean of those terms plus the rest.
    """
    if not 0.0 <= float(fraction_misclassified) <= 1.0:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a misclassified fraction must lie in [0, 1]; got "
            f"{fraction_misclassified}."
        )
    shift = float(fraction_misclassified) * float(hfa_baseline_points)
    return {
        "fraction_misclassified": round(float(fraction_misclassified), 6),
        "hfa_baseline_points": float(hfa_baseline_points),
        "baseline_displacement_points": round(shift, 6),
        "direction": (
            "A neutral-site game scored as an FBS home game inflates the venue term by "
            "the full HFA, and the fitted FCS baseline absorbs it upward by the same "
            "amount per unit of misclassified share."
        ),
    }


def unit_slope_witness(observations: Sequence[FbsVsFcsObservation]) -> dict[str, object]:
    """Regress the venue-adjusted margin on FBS strength. The slope should be 1.

    A diagnostic, never an adapter parameter. It exists because a scale error in
    the historical axis is the one part of the anchoring problem the data can
    speak to, and reporting it costs nothing while hiding it would let a fitted
    baseline stand on an axis the same data had already contradicted.
    """
    usable = [o.require_numerically_usable() for o in observations]
    if len(usable) < 3:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a slope witness needs at least three observations; got "
            f"{len(usable)}."
        )
    xs = [float(o.fbs_pregame_points) for o in usable]
    ys = [
        float(o.actual_margin_fbs)
        - venue_term(
            venue=str(o.venue),
            hfa_baseline_points=o.hfa_baseline_points,
            home_hfa_modifier=o.home_hfa_modifier,
            game_id=o.game_id,
            fcs_is_home=o.venue == "AWAY",
        )
        for o in usable
    ]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0.0:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: every observation carries the same FBS point state, so "
            "the axis scale leaves no signature to test."
        )
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    return {
        "slope": round(slope, 6),
        "expected_slope": 1.0,
        "intercept": round(my - slope * mx, 6),
        "n": len(usable),
        "fbs_point_state_spread": round(
            statistics.stdev(xs) if len(xs) > 1 else 0.0, 6
        ),
        "role": "DIAGNOSTIC_ONLY_NOT_AN_ADAPTER_PARAMETER",
    }


# ---------------------------------------------------------------------------
# Validation and sensitivity.
# ---------------------------------------------------------------------------

VALIDATION_LEAVE_SEASON_OUT = "LEAVE_SEASON_OUT"
VALIDATION_TEMPORAL_HOLDOUT = "TEMPORAL_HOLDOUT_LAST_SEASON"


def _by_season(
    observations: Sequence[FbsVsFcsObservation],
) -> dict[int, list[FbsVsFcsObservation]]:
    grouped: dict[int, list[FbsVsFcsObservation]] = {}
    for obs in observations:
        grouped.setdefault(int(obs.season), []).append(obs)
    return {s: sorted(v, key=lambda o: (o.order_key, o.game_id)) for s, v in sorted(grouped.items())}


def leave_season_out(
    observations: Sequence[FbsVsFcsObservation],
    **search_kwargs: object,
) -> dict[str, object]:
    """Fit on every season but one, score on the one held out. Repeat.

    Whole seasons, not random rows. A randomly held-out game sits earlier in
    time than training games that already reflect its result, so the error it
    measures is not out-of-sample; season boundaries need no argument because
    they are months wide.
    """
    grouped = _by_season(observations)
    if len(grouped) < 2:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: leave-season-out needs at least two seasons; the "
            f"observation set covers {sorted(grouped)}."
        )
    folds: list[dict[str, object]] = []
    pooled: list[float] = []
    for held, held_rows in grouped.items():
        train = [o for s, rows in grouped.items() if s != held for o in rows]
        fit = search_fcs_point_baseline(train, **search_kwargs)  # type: ignore[arg-type]
        held_metrics = score(held_rows, fit.best_baseline)
        pooled.extend(residuals(held_rows, fit.best_baseline))
        folds.append(
            {
                "held_out_season": held,
                "train_n": len(train),
                "held_out_n": len(held_rows),
                "fitted_baseline": round(fit.best_baseline, 6),
                "search_status": fit.status,
                "out_of_sample": held_metrics.as_dict(),
            }
        )
    n = len(pooled)
    return {
        "method": VALIDATION_LEAVE_SEASON_OUT,
        "folds": folds,
        "pooled_out_of_sample": {
            "n": n,
            "rmse": round(math.sqrt(sum(r * r for r in pooled) / n), 6),
            "mae": round(sum(abs(r) for r in pooled) / n, 6),
            "bias": round(sum(pooled) / n, 6),
            "median_residual": round(statistics.median(pooled), 6),
            "residual_sd": round(statistics.stdev(pooled) if n > 1 else 0.0, 6),
        },
        "fitted_baseline_spread": round(
            max(f["fitted_baseline"] for f in folds)  # type: ignore[type-var]
            - min(f["fitted_baseline"] for f in folds),  # type: ignore[type-var]
            6,
        ),
    }


def temporal_holdout(
    observations: Sequence[FbsVsFcsObservation],
    **search_kwargs: object,
) -> dict[str, object]:
    """Fit on all seasons but the last, score the last one once."""
    grouped = _by_season(observations)
    if len(grouped) < 2:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a temporal holdout needs at least two seasons."
        )
    seasons = sorted(grouped)
    held = seasons[-1]
    train = [o for s in seasons[:-1] for o in grouped[s]]
    fit = search_fcs_point_baseline(train, **search_kwargs)  # type: ignore[arg-type]
    return {
        "method": VALIDATION_TEMPORAL_HOLDOUT,
        "train_seasons": seasons[:-1],
        "holdout_season": held,
        "train_n": len(train),
        "holdout_n": len(grouped[held]),
        "fitted_baseline": round(fit.best_baseline, 6),
        "in_sample": score(train, fit.best_baseline).as_dict(),
        "holdout": score(grouped[held], fit.best_baseline).as_dict(),
        "holdout_use": "SCORED_ONCE_NEVER_FOR_SELECTION",
    }


def season_sensitivity(
    observations: Sequence[FbsVsFcsObservation],
    **search_kwargs: object,
) -> dict[str, object]:
    """Refit with each season removed. A baseline that moves is not measured."""
    grouped = _by_season(observations)
    full = search_fcs_point_baseline(observations, **search_kwargs)  # type: ignore[arg-type]
    drops: list[dict[str, object]] = []
    for dropped in sorted(grouped):
        kept = [o for s, rows in grouped.items() if s != dropped for o in rows]
        if not kept:
            continue
        fit = search_fcs_point_baseline(kept, **search_kwargs)  # type: ignore[arg-type]
        drops.append(
            {
                "season_removed": dropped,
                "n_remaining": len(kept),
                "fitted_baseline": round(fit.best_baseline, 6),
                "shift_from_full": round(fit.best_baseline - full.best_baseline, 6),
            }
        )
    shifts = [abs(float(d["shift_from_full"])) for d in drops]
    return {
        "full_sample_baseline": round(full.best_baseline, 6),
        "drops": drops,
        "max_absolute_shift": round(max(shifts), 6) if shifts else 0.0,
    }


def venue_sensitivity(
    observations: Sequence[FbsVsFcsObservation],
    **search_kwargs: object,
) -> dict[str, object]:
    """Refit under each venue subset the evidence can actually support.

    The subsets are all *admissible*: every one of them is built from
    observations whose venue was classified by a named authority. There is no
    "treat designated-home as home" variant, because that is not a sensitivity,
    it is the assumption this lane refuses.
    """
    subsets = {
        "ALL_CLASSIFIED": list(observations),
        "FBS_HOME_ONLY": [o for o in observations if o.venue == "HOME"],
        "FCS_HOME_ONLY": [o for o in observations if o.venue == "AWAY"],
        "NEUTRAL_ONLY": [o for o in observations if o.venue == "NEUTRAL"],
        "NEUTRAL_EXCLUDED": [o for o in observations if o.venue != "NEUTRAL"],
    }
    out: dict[str, object] = {}
    for name, rows in subsets.items():
        if len(rows) < 2:
            out[name] = {
                "n": len(rows),
                "status": "INSUFFICIENT_SUPPORT",
                "fitted_baseline": None,
            }
            continue
        fit = search_fcs_point_baseline(rows, **search_kwargs)  # type: ignore[arg-type]
        out[name] = {
            "n": len(rows),
            "status": fit.status,
            "fitted_baseline": round(fit.best_baseline, 6),
            "rmse": round(fit.best_rmse, 6),
        }
    return out


# ---------------------------------------------------------------------------
# The venue ledger.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VenueLedger:
    """The counts the lane instruction asks for, plus the reason for each."""

    usable_home: int
    usable_away: int
    usable_neutral: int
    venue_ambiguous_excluded: int
    structurally_ready_no_point_state: int
    total: int

    def as_dict(self) -> dict[str, object]:
        return {
            "usable_home": self.usable_home,
            "usable_away": self.usable_away,
            "usable_neutral": self.usable_neutral,
            "venue_ambiguous_excluded": self.venue_ambiguous_excluded,
            "structurally_ready_numerically_unavailable": (
                self.structurally_ready_no_point_state
            ),
            "total": self.total,
            "numerically_usable": (
                self.usable_home + self.usable_away + self.usable_neutral
            ),
        }


def venue_ledger(observations: Sequence[FbsVsFcsObservation]) -> VenueLedger:
    """Classify every observation into exactly one bucket. The counts reconcile."""
    home = away = neutral = ambiguous = structural = 0
    for obs in observations:
        state = obs.readiness()
        if state == VENUE_AMBIGUOUS:
            ambiguous += 1
        elif state == STRUCTURALLY_READY:
            structural += 1
        elif obs.venue == "HOME":
            home += 1
        elif obs.venue == "AWAY":
            away += 1
        else:
            neutral += 1
    return VenueLedger(
        usable_home=home,
        usable_away=away,
        usable_neutral=neutral,
        venue_ambiguous_excluded=ambiguous,
        structurally_ready_no_point_state=structural,
        total=len(observations),
    )


# ---------------------------------------------------------------------------
# Identification verdict.
# ---------------------------------------------------------------------------

IDENTIFIED = "IDENTIFIED"
WEAKLY_IDENTIFIED = "WEAKLY_IDENTIFIED_RANGE_ONLY"
NOT_IDENTIFIED = "NOT_IDENTIFIED"
BLOCKED_ON_INPUTS = "BLOCKED_ON_INPUTS"

#: Every condition a candidate must satisfy before it may be *recommended*.
#: Recommending is still not promoting: see :data:`PROMOTION_AUTHORISED`.
PROMOTION_STANDARD = (
    "source evidence admissible and byte-bound",
    "pregame FBS point states governed on the declared axis",
    "venue treatment defensible, with no designated-home assumption",
    "search optimum interior, not on a boundary",
    "sample support adequate for the reported interval",
    "leave-season-out behaviour stable",
    "no material residual bias",
    "materially better supported than leaving the blocker open",
)


def identification_verdict(
    *,
    search: SearchResult,
    interval: BaselineInterval,
    season: dict[str, object],
    metrics: ResidualMetrics,
) -> dict[str, object]:
    """Turn the numbers into one verdict, with each failing condition named.

    Three distinct failures are kept distinct. A flat surface means the
    objective carries no information. A wide interval means it carries some, but
    not enough to name a value. A boundary optimum means the interval chose the
    answer instead of the evidence.
    """
    reasons: list[str] = []
    if search.status == SEARCH_FLAT_SURFACE:
        reasons.append(
            "The RMSE surface is flat over the whole search interval, so no argmin "
            "from it is a measurement."
        )
    if search.status == SEARCH_OPTIMUM_ON_BOUNDARY:
        reasons.append(
            "The optimum sits on the search boundary after the maximum number of "
            "expansions, so the interval and not the evidence chose it."
        )
    if interval.half_width > MATERIAL_HALF_WIDTH_POINTS:
        reasons.append(
            f"The {interval.level:.0%} interval half-width is "
            f"{interval.half_width:.3f} points, wider than the material threshold of "
            f"{MATERIAL_HALF_WIDTH_POINTS}; the evidence supports a range, not a value."
        )
    equivalence_width = search.equivalence_range[1] - search.equivalence_range[0]
    if equivalence_width > 2 * MATERIAL_HALF_WIDTH_POINTS:
        reasons.append(
            f"Baselines spanning {equivalence_width:.3f} points score within "
            f"{EQUIVALENCE_RELATIVE_TOLERANCE:.1%} of the best RMSE, so the objective "
            "does not separate them."
        )
    max_shift = float(season.get("max_absolute_shift", 0.0))
    if max_shift > MATERIAL_HALF_WIDTH_POINTS:
        reasons.append(
            f"Removing a single season moves the fitted baseline by up to "
            f"{max_shift:.3f} points, which is not stable enough to call measured."
        )

    if search.status == SEARCH_FLAT_SURFACE:
        status = NOT_IDENTIFIED
    elif reasons:
        status = WEAKLY_IDENTIFIED
    else:
        status = IDENTIFIED
    return {
        "identification_status": status,
        "failing_conditions": reasons,
        "supported_range": [
            round(min(search.equivalence_range[0], interval.lower), 6),
            round(max(search.equivalence_range[1], interval.upper), 6),
        ],
        "best_point_baseline": round(search.best_baseline, 6),
        "objective_rmse": round(metrics.rmse, 6),
        "promotion_standard": list(PROMOTION_STANDARD),
        "promotion_authorised": PROMOTION_AUTHORISED,
    }


# ---------------------------------------------------------------------------
# The full experiment.
# ---------------------------------------------------------------------------

def fit_fcs_point_baseline(
    observations: Sequence[FbsVsFcsObservation],
    *,
    corpus: ResearchCorpus,
    interval: tuple[float, float] = DEFAULT_SEARCH_INTERVAL,
    coarse_step: float = DEFAULT_COARSE_STEP,
    refinement_factor: int = DEFAULT_REFINEMENT_FACTOR,
    refinements: int = DEFAULT_REFINEMENTS,
) -> dict[str, object]:
    """Run the whole study against a bound corpus of numerically usable rows.

    Refuses on the two inputs that are actually missing today: a corpus that is
    not bound, and observations that carry no governed pregame FBS point state.
    Every other gate is downstream of those two.
    """
    assert_fcs_elo_invariant()
    if not isinstance(corpus, ResearchCorpus):
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: a fit requires a corpus bound by "
            "bind_research_corpus. A result untied to exact bytes cannot be re-checked, "
            "and an FCS baseline that cannot be re-checked is not evidence."
        )
    ledger = venue_ledger(observations)
    usable = [o for o in observations if o.readiness() == READY_FOR_FIT]
    if not usable:
        raise GovernanceBlock(
            f"{STUDIED_BLOCKER}: no numerically usable observations. Of "
            f"{ledger.total}, {ledger.venue_ambiguous_excluded} lack a classified venue "
            f"and {ledger.structurally_ready_no_point_state} are structurally ready with "
            "no governed pregame FBS point state."
        )

    search_kwargs = {
        "interval": interval,
        "coarse_step": coarse_step,
        "refinement_factor": refinement_factor,
        "refinements": refinements,
    }
    search = search_fcs_point_baseline(usable, **search_kwargs)  # type: ignore[arg-type]
    assert_no_legacy_board_substitution(search.best_baseline)
    metrics = score(usable, search.best_baseline)
    ci = baseline_interval(usable, search.best_baseline)
    seasons = _by_season(usable)
    season_report = (
        season_sensitivity(usable, **search_kwargs)  # type: ignore[arg-type]
        if len(seasons) > 1
        else {"drops": [], "max_absolute_shift": 0.0, "full_sample_baseline": round(search.best_baseline, 6)}
    )
    validation = (
        leave_season_out(usable, **search_kwargs)  # type: ignore[arg-type]
        if len(seasons) > 1
        else {"method": VALIDATION_LEAVE_SEASON_OUT, "status": "SINGLE_SEASON_NOT_AVAILABLE"}
    )
    holdout = (
        temporal_holdout(usable, **search_kwargs)  # type: ignore[arg-type]
        if len(seasons) > 1
        else {"method": VALIDATION_TEMPORAL_HOLDOUT, "status": "SINGLE_SEASON_NOT_AVAILABLE"}
    )
    verdict = identification_verdict(
        search=search, interval=ci, season=season_report, metrics=metrics
    )
    return {
        "corpus": corpus.as_dict(),
        "venue_ledger": ledger.as_dict(),
        "season_counts": {str(s): len(rows) for s, rows in seasons.items()},
        "search": search.as_dict(),
        "metrics": metrics.as_dict(),
        "baseline_interval": ci.as_dict(),
        "validation": validation,
        "temporal_holdout": holdout,
        "season_sensitivity": season_report,
        "venue_sensitivity": venue_sensitivity(usable, **search_kwargs),  # type: ignore[arg-type]
        "unit_slope_witness": unit_slope_witness(usable),
        "anchor_confounding": anchor_confounding_statement(),
        "scale_confounding": scale_confounding_statement(),
        "identification": verdict,
        "recommended_adapter_if_identified": (
            round(search.best_baseline, 6)
            if verdict["identification_status"] == IDENTIFIED
            else None
        ),
        "promotion_authorised": PROMOTION_AUTHORISED,
        "canonical_config_written": False,
        "no_season_simulation": True,
    }


# ---------------------------------------------------------------------------
# What exists today, stated as findings rather than as absence.
# ---------------------------------------------------------------------------

#: The corpus candidate this lane assessed and did **not** bind.
#:
#: Every number here was read from artifacts committed at the exact SHA below,
#: in this repository's object store. Reading a committed artifact to decide
#: whether it is admissible is assessment; binding it would be use, and
#: :func:`bind_research_corpus` refuses it because the lane that produced it
#: reports ``READY_FOR_AUDIT`` — a request for an audit, not the result of one.
CANDIDATE_CORPUS_ASSESSMENT: dict[str, object] = {
    "candidate_id": "V3_R6_OBSERVATION_CORPUS",
    "producing_lane": "claude/v3-historical-observation-corpus-r6",
    "commit_sha": "fb817a6a08df598038966c8f5fe345153dd302f3",
    "lane_terminal": "HISTORICAL_OBSERVATION_CORPUS_R6_READY_FOR_AUDIT",
    "merged_to_main": False,
    "audited": False,
    "bound_by_this_lane": False,
    "source_authority": "NCAA_OFFICIAL_SCOREBOARD_FEED",
    "source_authority_class": "GOVERNED_RESULT_SOURCE",
    "source_authority_tier": "TIER_1_NCAA_OFFICIAL",
    "inventory_artifact": (
        "reference/dynamic_weekly_mc_v3/observation_corpus_r6/V3_R6_EXCLUSION_REPORT.json"
        "!fbs_vs_fcs_inventory"
    ),
    "fbs_vs_fcs_identified": 43,
    "fbs_vs_fcs_admitted_to_corpus": 0,
    "exclusion_reason_in_source_lane": "FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED",
    "season_counts": {"2021": 11, "2022": 9, "2023": 12, "2024": 11},
    "week_counts": {"1": 15, "2": 16, "3": 7, "4": 1, "5": 1, "7": 2, "11": 1},
    "distinct_fcs_participants": 10,
    "fcs_participants": (
        "COLG", "CP", "DEL", "DUQ", "HC", "IDHO", "NDSU", "SAC", "SUU", "YALE",
    ),
    "fields_present": (
        "season", "week", "event_time", "fbs_side", "fcs_side", "source_home",
        "source_away", "source_game_id", "margin_home_perspective",
    ),
    "fields_absent_that_this_lane_requires": (
        "venue (HOME|AWAY|NEUTRAL) — the feed publishes no neutral-site indicator",
        "venue_classification_source",
        "fbs_pregame_points on V3_UNIFIED_NEUTRAL_FIELD_POINTS",
        "strength_domain declaration",
        "home_hfa_modifier",
    ),
    "designated_home_side": {
        "fbs_designated_home": 43,
        "fcs_designated_home": 0,
        "note": (
            "All 43 place the FCS entity on the designated-away side. Designated home "
            "is not venue: a neutral-site game is also designated-home in this feed."
        ),
    },
    "unconditional_margin_sd_points": 24.4831,
    "unconditional_margin_mean_points": 23.6512,
    "fcs_wins": 7,
    "assessment": "ADMISSIBLE_IN_PRINCIPLE_NOT_YET_ADMISSIBLE_IN_FACT",
}

#: Whether the historical pregame FBS point states this lane consumes exist yet,
#: and by what route they arrive.
#:
#: The classification here was corrected by a cross-lane update. An independent
#: audit of the historical expected-margin lane **refuted** that lane's earlier
#: ``HUMAN_GOVERNANCE_REQUIRED`` reading of ``HISTORICAL_STRENGTH_AXIS_ANCHOR``.
#: The programme classification is now that the historical point-axis scale is
#: **empirically calibratable** from real Week 1-2 margins once historical
#: opening standardized states are available. So this lane must not say, and no
#: longer says, that a Chairman ruling gates FCS scale estimation: the axis
#: arrives by calibration against real margins, and this lane waits on its
#: output rather than on an authority.
#:
#: What does *not* change is the mathematics. The FCS baseline is a location
#: parameter and absorbs a constant axis offset one-for-one, so the axis has to
#: be established — by whatever route — before a fitted baseline means the FCS
#: baseline. That is an ordering constraint on the estimation, not a governance
#: prerequisite. See :func:`anchor_confounding_statement`.
HISTORICAL_POINT_STATE_AVAILABILITY: dict[str, object] = {
    "available": False,
    "dependency_id": "HISTORICAL_STRENGTH_AXIS_ANCHOR",
    "studying_lane": "claude/v3-historical-expected-margin",
    "commit_sha": "327b65e",
    "artifact": (
        "reference/dynamic_weekly_mc_v3/"
        "V3_HISTORICAL_EXPECTED_MARGIN_AUTHORITY_MATRIX.json"
    ),
    "merged_to_main": False,
    "classification": "EMPIRICALLY_CALIBRATABLE",
    "superseded_classification": "HUMAN_GOVERNANCE_REQUIRED",
    "superseded_by": (
        "The independent historical expected-margin audit refuted the "
        "HUMAN_GOVERNANCE_REQUIRED reading. The programme classification is that the "
        "historical point-axis scale is empirically calibratable from real Week 1-2 "
        "margins once historical opening standardized states are available."
    ),
    "chairman_ruling_required_for_fcs_scale_estimation": False,
    "arrives_by": (
        "Empirical calibration of the historical point axis against real Week 1-2 "
        "margins, given historical opening standardized states."
    ),
    "why_weeks_1_2": (
        "Opening weeks run on preseason opening strength, so their expected margins "
        "consume no weekly rerating coefficient and the axis is not confounded with "
        "parameters that are themselves unfitted."
    ),
    "why_it_matters_here": (
        "The FCS baseline is a location parameter, so it absorbs the axis offset "
        "one-for-one. Until the axis is established the fitted number is not the FCS "
        "baseline. This is an ordering constraint on the estimation, not an authority "
        "gate."
    ),
    "open_scale_note": (
        f"The {UNIFIED_NEUTRAL_POINTS_PER_SD} points/SD scale is still marked 'initial "
        "scale pending margin calibration' in its own source, which is what the "
        "empirical calibration resolves."
    ),
}


# ---------------------------------------------------------------------------
# The freeze.
# ---------------------------------------------------------------------------

#: The harness is frozen as an input-ready research tool. Frozen means its
#: mathematics, its refusals and its search are settled and are not to be
#: redesigned; it does not mean sealed. Handing it the three inputs below runs
#: the study through exactly the code that is frozen here, which is the point of
#: freezing it in this state rather than in a half-built one.
HARNESS_FROZEN = True
HARNESS_STATUS = "FROZEN_READY_FOR_INPUTS"

#: The three numerical inputs a fit needs, in the programme's own terms. Every
#: one is an evidence dependency. None is an authority gate.
REQUIRED_NUMERICAL_INPUTS: tuple[str, ...] = (
    "governed / empirically established historical FBS pregame V3 point states",
    "audited real FBS-vs-FCS observations",
    "defensible venue classification for observations used",
)

#: No Chairman ruling is a prerequisite for FCS scale estimation. Recorded as a
#: constant, and asserted by test, because the superseded classification said
#: otherwise and a stale reading of it would misdirect the whole programme.
CHAIRMAN_RULING_REQUIRED = False

#: The mathematical findings this lane established, pinned so a later change to
#: the harness that contradicts one of them fails a test rather than passing
#: quietly. These are frozen; the harness may be re-run, not re-derived.
PRESERVED_FINDINGS: tuple[dict[str, object], ...] = (
    {
        "id": "F_HAT_IS_A_MEAN",
        "finding": (
            "F_hat = mean(FBS_pregame_points + venue_adjustment - actual_margin_FBS)"
        ),
        "why": (
            "The FCS baseline enters the expected margin additively, so its "
            "least-squares estimate is an arithmetic mean and nothing more."
        ),
    },
    {
        "id": "FCS_ELO_FIXED_AT_1250",
        "finding": "FCS Elo = 1250, fixed.",
        "why": f"Ruling {R2_FCS.convergence_id}. Not reopened by this lane.",
    },
    {
        "id": "FORTY_THREE_GIVES_RANGE_ONLY",
        "finding": (
            "The 43 current candidate observations provide weak, range-level "
            "identification, not high-precision standalone identification."
        ),
        "why": (
            "At the candidate's unconditional margin dispersion the 95% half-width is "
            "at most 7.53 points, wider than the 4.0-point material threshold."
        ),
    },
    {
        "id": "ALL_FORTY_THREE_ARE_FBS_DESIGNATED_HOME",
        "finding": "All 43 are currently FBS-designated-home.",
        "why": (
            "The venue term never varies sign across the candidate, so it gives the "
            "FCS-home orientation no support at all."
        ),
    },
    {
        "id": "AXIS_OFFSET_SHIFTS_F_HAT_ONE_FOR_ONE",
        "finding": (
            "A constant shift in the FBS point-axis zero shifts F_hat one-for-one "
            "while preserving every game residual."
        ),
        "why": (
            "The objective surface is invariant under the joint shift, so no sample "
            "size and no objective over margins can separate the two."
        ),
    },
    {
        "id": "VENUE_MISCLASSIFICATION_BIASES_F_HAT",
        "finding": (
            "Venue misclassification directly biases the fitted FCS baseline, by "
            "misclassified_share x HFA."
        ),
        "why": (
            "A neutral site scored as a home game carries a venue term of +HFA where "
            "the truth is 0.0, and F_hat is the mean of those terms."
        ),
    },
)


def freeze_record() -> dict[str, object]:
    """What was frozen, what it still needs, and what it does not need.

    The third field is the one that earns its place: a reader who arrives with
    the superseded ``HUMAN_GOVERNANCE_REQUIRED`` reading in mind would otherwise
    conclude this lane is waiting on a ruling, and it is not.
    """
    return {
        "harness_frozen": HARNESS_FROZEN,
        "harness_status": HARNESS_STATUS,
        # The lane terminal is unchanged. Freezing records that the harness
        # phase is complete; it does not advance the research status, which
        # still turns on inputs that do not exist.
        "lane_terminal": READY_FOR_INPUTS,
        "freeze_terminal": FROZEN_READY_FOR_INPUTS,
        "required_numerical_inputs": list(REQUIRED_NUMERICAL_INPUTS),
        "chairman_ruling_required": CHAIRMAN_RULING_REQUIRED,
        "historical_axis_classification": (
            HISTORICAL_POINT_STATE_AVAILABILITY["classification"]
        ),
        "superseded_axis_classification": (
            HISTORICAL_POINT_STATE_AVAILABILITY["superseded_classification"]
        ),
        "preserved_findings": [dict(f) for f in PRESERVED_FINDINGS],
        "research_mathematics_changed": False,
        "numerical_fitting_performed": False,
        "additional_observations_acquired": False,
        "fcs_elo_changed": False,
        "adapter_promoted": False,
        "season_monte_carlo_run": False,
    }


# ---------------------------------------------------------------------------
# Terminal status.
# ---------------------------------------------------------------------------

READY_FOR_AUDIT = "FCS_SCALE_RESEARCH_READY_FOR_AUDIT"
READY_FOR_INPUTS = "FCS_SCALE_RESEARCH_READY_FOR_INPUTS"
RESEARCH_NOT_IDENTIFIED = "FCS_SCALE_RESEARCH_NOT_IDENTIFIED"
RESEARCH_BLOCKED = "FCS_SCALE_RESEARCH_BLOCKED"
FROZEN_READY_FOR_INPUTS = "FCS_SCALE_RESEARCH_R1_FROZEN_READY_FOR_INPUTS"


def blocking_inputs() -> list[dict[str, object]]:
    """Exactly which inputs stop a numerical fit, most binding first.

    All three are *evidence* dependencies. None of them is an authority gate:
    the point states arrive by empirical calibration of the historical axis, the
    corpus by an audit, and the venue classification by evidence a result feed
    does not happen to carry. Nothing here waits on a ruling.
    """
    return [
        {
            "input": "governed_pregame_fbs_point_state",
            "status": "UNAVAILABLE",
            "blocking": True,
            "supplied_by": HISTORICAL_POINT_STATE_AVAILABILITY["arrives_by"],
            "classification": HISTORICAL_POINT_STATE_AVAILABILITY["classification"],
            "chairman_ruling_required": False,
            "why": HISTORICAL_POINT_STATE_AVAILABILITY["why_it_matters_here"],
            "substitutable_by_more_data": False,
        },
        {
            "input": "audited_fbs_vs_fcs_corpus",
            "status": "CANDIDATE_PRESENT_UNAUDITED",
            "blocking": True,
            "supplied_by": (
                "an audit of "
                f"{CANDIDATE_CORPUS_ASSESSMENT['commit_sha']}, then a binding through "
                "bind_research_corpus"
            ),
            "why": (
                "The candidate's own lane terminal is READY_FOR_AUDIT and it is not "
                "merged. Binding it would treat a request for review as its outcome."
            ),
            "substitutable_by_more_data": False,
        },
        {
            "input": "venue_classification",
            "status": "UNAVAILABLE_FOR_ALL_43",
            "blocking": True,
            "supplied_by": (
                "independent authoritative classification of each game's site, or "
                "explicit exclusion of the ambiguous ones"
            ),
            "why": (
                "The NCAA scoreboard feed publishes no neutral-site indicator, so all "
                "43 candidate observations are designated-home and none is classified. "
                f"A neutral site scored as home displaces the baseline by the full "
                f"{V3_FOOTBALL_POINT_HFA}-point HFA on that share of the sample."
            ),
            "substitutable_by_more_data": False,
        },
    ]


def research_status() -> str:
    """The lane's terminal, computed from what is actually available.

    ``READY_FOR_INPUTS`` rather than ``BLOCKED`` because nothing here is stuck:
    the harness is complete and every missing input has a named supplier.
    """
    blocking = [b for b in blocking_inputs() if b["blocking"]]
    return READY_FOR_INPUTS if blocking else READY_FOR_AUDIT


# ---------------------------------------------------------------------------
# The research result artifact.
# ---------------------------------------------------------------------------

#: Filename of the deterministic result artifact this lane emits.
RESULT_ARTIFACT_NAME = "V3_FCS_SCALE_RESEARCH_R1.json"


def fcs_scale_research_result(
    *,
    corpus: ResearchCorpus | None = None,
    observations: Sequence[FbsVsFcsObservation] = (),
) -> dict[str, object]:
    """The deterministic research result.

    With no bound corpus this reports the design, the blocking inputs and the
    two confounding statements, and reports ``BLOCKED_ON_INPUTS`` — which is a
    result, not a failure to produce one. With a bound corpus and numerically
    usable observations it additionally runs the study and reports its verdict.
    """
    assert_fcs_elo_invariant()
    ledger = venue_ledger(observations)
    payload: dict[str, object] = {
        "artifact": RESULT_ARTIFACT_NAME,
        "artifact_status": "RESEARCH_RESULT__EXPERIMENTAL__NOT_CANONICAL",
        "lane": RESEARCH_LANE_ID,
        "studied_blocker": STUDIED_BLOCKER,
        "freeze": freeze_record(),
        "governance": {
            "fcs_elo": FCS_FIXED_ELO,
            "fcs_elo_changed": False,
            "fcs_translation_policy": FCS_FIXED_ELO_POLICY,
            "ruling": R2_FCS.convergence_id,
            "rejected_as_the_fcs_translation": list(FORBIDDEN_BOARD_EQUIVALENTS),
            "hfa_baseline_points": V3_FOOTBALL_POINT_HFA,
            "hfa_ruling": R2_HFA.convergence_id,
            "blocker_retired": False,
            "blocker_opened": False,
            "promotion_authorised": PROMOTION_AUTHORISED,
            "canonical_config_written": False,
            "adapter_registered": False,
            "team_specific_fcs_ratings": False,
            "calibration_parameters_fitted": [],
            "season_monte_carlo_run": False,
        },
        "model": {
            "unknown": "one global FCS neutral-field point baseline",
            "fixed": f"FCS Elo {FCS_FIXED_ELO}, ruling {R2_FCS.convergence_id}",
            "production_form": PRODUCTION_MARGIN_FORM,
            "fbs_oriented_form": (
                "expected_fbs_margin = fbs_pregame_points - fcs_point_baseline + "
                "venue_term, venue_term = sign * hfa_baseline_points * "
                "home_hfa_modifier with sign +1 at FBS HOME, -1 at FCS HOME and the "
                "term exactly 0.0 at NEUTRAL"
            ),
            "venue_orientation": "SUBJECT_IS_THE_FBS_SIDE",
            "neutral_handling": "FAILS_CLOSED_NO_HFA_FALLBACK",
            "strength_domain": GOVERNED_STRENGTH_DOMAIN,
            "target_axis": {
                "points_per_sd": UNIFIED_NEUTRAL_POINTS_PER_SD,
                "z_population": UNIFIED_Z_POPULATION_SIZE,
                "observed_fbs_range": list(UNIFIED_POINTS_OBSERVED_RANGE),
            },
        },
        "design": {
            "objective": "OUT_OF_SAMPLE_EXPECTED_MARGIN_RMSE",
            "also_reported": [
                "MAE", "bias", "median_residual", "residual_sd", "winner_accuracy",
            ],
            "winner_accuracy_is_not_optimised": True,
            "validation_methods": [
                VALIDATION_LEAVE_SEASON_OUT, VALIDATION_TEMPORAL_HOLDOUT,
            ],
            "random_row_split_permitted": False,
            "search_interval": list(DEFAULT_SEARCH_INTERVAL),
            "search_coarse_step": DEFAULT_COARSE_STEP,
            "search_refinement_factor": DEFAULT_REFINEMENT_FACTOR,
            "search_refinements": DEFAULT_REFINEMENTS,
            "search_final_step": DEFAULT_COARSE_STEP
            / DEFAULT_REFINEMENT_FACTOR**DEFAULT_REFINEMENTS,
            "boundary_expansion_limit": MAX_BOUNDARY_EXPANSIONS,
            "flat_surface_tolerance": FLAT_SURFACE_TOLERANCE_POINTS,
            "equivalence_relative_tolerance": EQUIVALENCE_RELATIVE_TOLERANCE,
            "material_half_width_points": MATERIAL_HALF_WIDTH_POINTS,
            "observation_requirements": dict(OBSERVATION_REQUIREMENTS),
            "promotion_standard": list(PROMOTION_STANDARD),
        },
        "inputs": {
            "corpus_bound": corpus is not None,
            "corpus_sha": None if corpus is None else corpus.sha256,
            "candidate_corpus": {
                k: (list(v) if isinstance(v, tuple) else v)
                for k, v in CANDIDATE_CORPUS_ASSESSMENT.items()
            },
            "historical_fbs_point_state": dict(HISTORICAL_POINT_STATE_AVAILABILITY),
        },
        "venue_ledger": ledger.as_dict(),
        "candidate_venue_ledger": {
            **VenueLedger(
                usable_home=0,
                usable_away=0,
                usable_neutral=0,
                venue_ambiguous_excluded=int(
                    CANDIDATE_CORPUS_ASSESSMENT["fbs_vs_fcs_identified"]
                ),
                structurally_ready_no_point_state=0,
                total=int(CANDIDATE_CORPUS_ASSESSMENT["fbs_vs_fcs_identified"]),
            ).as_dict(),
            "why_every_one_is_ambiguous": (
                "The NCAA scoreboard feed publishes no neutral-site indicator, so a "
                "designated-home game and a neutral-site game are indistinguishable in "
                "it. None of the 43 is classified, so none is usable and none is "
                "silently treated as a true home game."
            ),
            "fcs_home_orientation_support": 0,
            "why_fcs_home_support_is_zero": (
                "All 43 place the FCS entity on the designated-away side. Even a "
                "perfect venue classification of this candidate would exercise only "
                "the FBS-home and neutral orientations, while the 2026 schedule "
                "carries three real FCS-home games."
            ),
        },
        "confounding": {
            "axis_offset": anchor_confounding_statement(),
            "axis_scale": scale_confounding_statement(),
            "venue_misclassification_per_10pct": venue_misclassification_envelope(
                fraction_misclassified=0.10
            ),
            "venue_misclassification_full_sample": venue_misclassification_envelope(
                fraction_misclassified=1.0
            ),
        },
        "precision_envelope_at_candidate_scale": {
            **precision_envelope(
                float(CANDIDATE_CORPUS_ASSESSMENT["unconditional_margin_sd_points"]),
                int(CANDIDATE_CORPUS_ASSESSMENT["fbs_vs_fcs_identified"]),
            ),
            "basis": "CANDIDATE_ASSESSMENT_NOT_A_FIT",
            "bound_direction": (
                "Upper bound. It uses the unconditional margin SD; conditioning on FBS "
                "strength can only reduce dispersion, so the achievable half-width is "
                "no larger than this."
            ),
            "observations_required_for_material_half_width": (
                observations_required_for_half_width(
                    float(
                        CANDIDATE_CORPUS_ASSESSMENT["unconditional_margin_sd_points"]
                    ),
                    MATERIAL_HALF_WIDTH_POINTS,
                )
            ),
            "observations_required_for_two_point_half_width": (
                observations_required_for_half_width(
                    float(
                        CANDIDATE_CORPUS_ASSESSMENT["unconditional_margin_sd_points"]
                    ),
                    2.0,
                )
            ),
        },
        "blocked_inputs": blocking_inputs(),
        "no_season_simulation": True,
        "no_probabilities_emitted": True,
    }

    usable = [o for o in observations if o.readiness() == READY_FOR_FIT]
    if corpus is not None and usable:
        study = fit_fcs_point_baseline(usable, corpus=corpus)
        payload["study"] = study
        payload["results"] = {
            "best_point_baseline": study["search"]["best_baseline"],
            **{
                key: study["metrics"][key]
                for key in (
                    "rmse", "mae", "bias", "median_residual", "residual_sd",
                    "winner_accuracy",
                )
            },
            "baseline_interval": study["baseline_interval"],
            "season_sensitivity": study["season_sensitivity"],
            "venue_sensitivity": study["venue_sensitivity"],
            "validation": study["validation"],
        }
        payload["identification_status"] = study["identification"][
            "identification_status"
        ]
        payload["recommended_adapter_if_identified"] = study[
            "recommended_adapter_if_identified"
        ]
        payload["terminal"] = READY_FOR_AUDIT
    else:
        payload["study"] = None
        # Explicit nulls rather than absent keys. An auditor reading for a
        # number should find the field and find it empty, with the reason
        # attached, instead of having to conclude anything from a missing key.
        payload["results"] = {
            "best_point_baseline": None,
            "rmse": None,
            "mae": None,
            "bias": None,
            "median_residual": None,
            "residual_sd": None,
            "winner_accuracy": None,
            "baseline_interval": None,
            "season_sensitivity": None,
            "venue_sensitivity": None,
            "validation": None,
            "not_computed_because": (
                "No numerically usable observation exists. The harness is complete and "
                "every gate is exercised by tests; what is absent is evidence, and this "
                "lane does not manufacture it."
            ),
        }
        payload["identification_status"] = BLOCKED_ON_INPUTS
        payload["recommended_adapter_if_identified"] = None
        payload["terminal"] = research_status()
    payload["promotion_authorised"] = PROMOTION_AUTHORISED
    return payload


def write_research_result(path: Path, payload: dict[str, object] | None = None) -> Path:
    """Emit the result as deterministic JSON: sorted keys, 2-space indent, LF.

    A writer for an evidence artifact, never for configuration. Nothing in this
    module can write ``config/``.
    """
    return write_json_lf(path, payload or fcs_scale_research_result(), trailing_newline=True)
