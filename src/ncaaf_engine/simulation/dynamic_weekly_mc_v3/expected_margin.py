"""Historical pre-game expected-margin construction for V3 — fail-closed.

Calibration needs, for a historical game ``g``::

    actual_margin_g - governed_pregame_expected_margin_g = performance_residual_g

The middle term is the one V3 does not currently hand anybody. This module works
out how much of it is already governed, builds the part that is, and refuses the
part that is not — with the refusal naming what is missing rather than
substituting a plausible number for it.

What is already governed
------------------------
V3's rating-to-margin transform is not missing. It is mounted, ratified and in
production in :func:`game.simulate_game`::

    hfa      = 0.0 if venue == "NEUTRAL" else hfa_baseline_points * home_hfa_modifier
    expected = home.current_strength_points - away.current_strength_points + hfa

Two properties make that an *exact* construction rather than a convention:

``the strength axis is already a margin axis``
    Team strength is read verbatim from
    ``2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Master Ratings`` column
    **"Unified Neutral-Field Points"** (``inputs.load_preseason_ratings``). It is
    a *neutral-field point* quantity by construction, so the difference of two of
    them is a neutral-field margin in points. No rating-to-margin coefficient is
    interposed and none is needed: on this axis the transform is the identity.

``the venue term is additive in the same unit and exactly zero at neutral``
    Because the axis is defined at neutral field, the venue correction is the
    whole of the departure from neutral, and it is carried by the one governed
    football-point HFA — ``SCHED-HFA-BASE = 3.5``, LOCKED, ruling ``R2-HFA-3P5``
    (:mod:`hfa`).

So the formula has no free parameter. In particular it does **not** consume
``calibration.game_sd_points``: ``simulate_game`` uses the SD only for the
stochastic draw, never for ``expected``. Expected-margin reconstruction is
therefore independent of the game-SD blocker.

What P_TO_STRENGTH_TRANSFORM and REFERENCE_HFA actually are
-----------------------------------------------------------
Both are **SOR-B items in the Elo domain** and neither is on this path. Read
against :mod:`sor` rather than against their names:

* ``P`` is the Poisson-binomial *reference win probability* ``p_ref_ge_w``,
  dimensionless on [0, 1]. ``P_TO_STRENGTH_TRANSFORM`` is the unverified mapping
  from that probability to a resume scalar, inside an unmounted
  ``compute_sor_b.py``. It sits output-side of a report stamped
  ``RESEARCH_REPORT_ONLY``, whose own two presentations of it are labelled
  "REPORT CONVENTION, not a governed transform".
* ``REFERENCE_HFA`` is whether and how home-field advantage enters
  ``sor._reference_win_probability(r_ref, opponent_elo)`` — an **Elo**-point term
  inside a logistic on a 400-point scale. ``SorOpponent`` carries ``home`` and
  ``neutral_site``; that function ignores both, which is precisely the gap.

Ratifying either would change a research resume metric and would not produce a
single football point. Conversely the football-point expected margin is exact
without them. ``docs/v3_calibration_evidence_lane.md`` §9 and §14 step 3 infer
the opposite from the two labels' names; that inference does not survive reading
the module that defines them, and :data:`SOR_B_SCOPE_FINDING` records the
correction. Nothing in that document is rewritten here.

What is genuinely missing for a *historical* reconstruction
------------------------------------------------------------
Not the transform — the **axis**. ``Unified Neutral-Field Points = 14 x Unified
Master Z`` (:mod:`fcs`), and both halves of that are 2026-specific:

* ``Unified Master Z`` is standardized over a **closed 121-team FBS population**.
  A different season is a different population, so re-standardizing yields a
  different axis; two seasons' point values are not commensurable without a
  governed anchoring rule, and no register issues one.
* The ``14`` points/SD is marked in its own source "initial scale pending margin
  calibration", and open item ``ENG-CAL-MARGIN`` is OPEN. It is provisional
  against exactly the calibration this expected margin is meant to feed.

The second point is the identification hazard the data contract names under
``expected_margin_transform``: if the scale is free at the same time as
``weekly_performance_residual_coefficient``, the two trade off exactly and
neither is identified. The scale must be anchored *before*, not *during*.

So the missing authority is :data:`HISTORICAL_AXIS_ANCHOR_DEPENDENCY`. It is
recorded as a model-identification dependency, **not** as a formal project
blocker: no governed authority requires blocker registration for it, and this
module contributes nothing to ``V3Config.execution_blockers``.

Fail-closed policy
------------------
No silent default HFA, no ``or 1.0``, no implied zero, no FCS substitution, no
missing-point fallback. A numeric ``expected_margin_points`` is returned only
under :data:`STATUS_AUTHORIZED`; every other outcome carries a reason and no
number.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from . import fcs as fcs_policy
from . import hfa as hfa_policy
from . import sor
from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_CALIBRATION, R2_FCS, R2_HFA, R2_SRS
from .textio import write_json_lf

# ---------------------------------------------------------------------------
# Identity of the construction
# ---------------------------------------------------------------------------

#: The one formula this module will evaluate, pinned to the production
#: implementation it reproduces so a divergence is a test failure rather than a
#: drift nobody notices.
FORMULA_ID = "V3-EXPECTED-MARGIN-001"
FORMULA_SOURCE = "ncaaf_engine.simulation.dynamic_weekly_mc_v3.game.simulate_game"
FORMULA_EXPRESSION = (
    "expected_home_margin = home_strength_points - away_strength_points "
    "+ (0.0 if venue == NEUTRAL else hfa_baseline_points * home_hfa_modifier)"
)

MATRIX_ID = "V3-HISTORICAL-EXPECTED-MARGIN-AUTHORITY-MATRIX-001"

#: The only strength axis on which the transform above is exact. Named, because
#: a residual computed across two axes is arithmetic and not evidence.
V3_POINT_DOMAIN = "V3_UNIFIED_NEUTRAL_FIELD_POINTS"

#: The axis definition, transcribed from the mounted source. Not re-derived here.
V3_POINT_DOMAIN_DEFINITION = "Unified Neutral-Field Points = 14 x Unified Master Z"
V3_POINT_DOMAIN_SOURCE = (
    "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Master Ratings"
    "!'Unified Neutral-Field Points' (loaded verbatim by inputs.load_preseason_ratings)"
)
V3_POINT_DOMAIN_SCALE_STATUS = "initial scale pending margin calibration"

Status = Literal["AUTHORIZED", "DERIVABLE", "UNAVAILABLE"]

#: Every input and every binding is present; a number is produced.
STATUS_AUTHORIZED = "AUTHORIZED"
#: The formula is exact and every term is mathematically determined, but at
#: least one binding is not governed. No number is produced.
STATUS_DERIVABLE = "DERIVABLE"
#: An input is absent, refused, or on the wrong axis. No number is produced.
STATUS_UNAVAILABLE = "UNAVAILABLE"

VenueTreatment = Literal["HOME", "AWAY", "NEUTRAL"]

#: Where a pregame point state came from in the weekly sequence.
ORIGIN_PRESEASON_OPENING = "PRESEASON_OPENING_STRENGTH"
ORIGIN_PROMOTED_RERATING = "PROMOTED_WEEKLY_RERATING"

#: FACT — ``config.DEFAULT_PRIOR_DECAY`` with
#: ``first_promoted_rerating_after_week = 2`` and
#: ``config.audit_only_after_week(w) = w < 2``. Week 1's rerating is audit-only
#: and never promoted; week 2's games are played *before* the after-week-2
#: promotion. Both weeks therefore open on preseason strength.
PRESEASON_OPENING_WEEKS: tuple[int, ...] = (1, 2)
FIRST_WEEK_REQUIRING_PROMOTED_RERATING = 3


# ---------------------------------------------------------------------------
# Findings recorded by this lane
# ---------------------------------------------------------------------------

#: The correction this lane makes to the prior calibration-evidence conclusion.
#: Recorded here rather than applied to that document, which stays as issued.
SOR_B_SCOPE_FINDING: dict[str, Any] = {
    "finding_id": "EM-SOR-B-SCOPE-001",
    "claim_reviewed": (
        "docs/v3_calibration_evidence_lane.md sections 9 and 14 step 3: 'V3 has no "
        "ratified rating-to-margin transform. sor.py records P_TO_STRENGTH_TRANSFORM "
        "and REFERENCE_HFA as unratified' — therefore expected_margin cannot exist in "
        "V3 units."
    ),
    "disposition": "NOT_SUPPORTED_BY_THE_MODULE_THAT_DEFINES_THE_TWO_LABELS",
    "why": (
        "Both labels are SOR-B items in the Elo domain. sor.UNRATIFIED_SOR_B_ITEMS is "
        "reachable only from sor.weekly_sor_row, which stamps a report whose status is "
        f"{sor.REPORT_STATUS_RESEARCH!r} and which is never a committee or Monte Carlo "
        "input. 'P' is the Poisson-binomial reference win probability p_ref_ge_w, "
        "dimensionless on [0,1] — not a power index and not a point quantity. "
        "REFERENCE_HFA is an Elo-point term inside _reference_win_probability, on the "
        "400-point logistic scale rather than the football-point scale. Neither is read "
        "by game.simulate_game, by engine, or by any point-domain code path."
    ),
    "what_is_true_instead": (
        "The V3 rating-to-margin transform is mounted and ratified: it is the identity "
        "on the unified neutral-field point axis plus the governed additive HFA "
        f"{hfa_policy.V3_FOOTBALL_POINT_HFA} (ruling {R2_HFA.convergence_id}). It has "
        "no free parameter and consumes no calibration coefficient."
    ),
    "residual_gap_after_the_correction": "HISTORICAL_STRENGTH_AXIS_ANCHOR",
    "opens_formal_blocker": False,
    "rewrites_prior_artifact": False,
}

#: The one authority this lane finds genuinely absent, stated in the terms a
#: ruling would need. A model-identification dependency, not a formal blocker.
HISTORICAL_AXIS_ANCHOR_DEPENDENCY: dict[str, Any] = {
    "dependency_id": "HISTORICAL_STRENGTH_AXIS_ANCHOR",
    "classification": "HUMAN_GOVERNANCE_REQUIRED",
    "is_formal_project_blocker": False,
    "why_not_a_formal_blocker": (
        "No governed authority requires blocker registration for it, and it gates no "
        "V3 execution path: V3 runs the 2026 population, where the axis is fully "
        "defined. It gates only historical reconstruction, which is evidence work."
    ),
    "statement": (
        "Historical pregame strengths cannot be placed on "
        f"{V3_POINT_DOMAIN} without a governed rule anchoring the axis across "
        "populations and seasons."
    ),
    "two_independent_reasons": {
        "population_closure": (
            "Unified Master Z is standardized over a closed "
            f"{fcs_policy.UNIFIED_Z_POPULATION_SIZE}-team FBS population. Another season "
            "is another population; re-standardizing produces a different axis, so point "
            "values from two seasons are not commensurable. No register issues an "
            "anchoring rule, and the canonical 2026 universe is itself synthetic — it "
            "contains members no real season had."
        ),
        "scale_provisionality": (
            f"The {fcs_policy.UNIFIED_NEUTRAL_POINTS_PER_SD} points/SD scale is marked "
            f"{V3_POINT_DOMAIN_SCALE_STATUS!r} in its own source and open item "
            "ENG-CAL-MARGIN is OPEN. Fitting weekly_performance_residual_coefficient "
            "while the scale is free leaves the two exactly confounded — any residual is "
            "absorbable by rescaling the axis instead, which is the unidentifiability "
            "the data contract names under expected_margin_transform."
        ),
    },
    "why_not_engineering_derivable": (
        "A Z-score carries no information about the scale of the population it was taken "
        "over. Recovering an anchor from the mounted corpus would require a second "
        "governed quantity on the same axis in a second season, and there is none."
    ),
    "minimum_ruling_question": (
        "For a historical season outside the closed 2026 121-team FBS population, is "
        "there a governed rule placing that season's pregame team strengths on the V3 "
        "unified neutral-field point axis — and if so, does it fix the points-per-SD "
        "scale independently of margin calibration, or does the provisional 14 remain "
        "subject to it?"
    ),
    "not_bundled_with": (
        "the synthetic-universe admissibility question already raised by the "
        "calibration-evidence lane",
        "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
        "P_TO_STRENGTH_TRANSFORM / REFERENCE_HFA, which this lane finds out of scope",
    ),
}


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PregameTeamPoints:
    """One team's strength as it stood before kickoff, with the axis it is on.

    ``domain`` is required and never defaulted. A point value whose axis nobody
    declared is the one input that cannot be checked, and it is also the one that
    silently produces a plausible number on the wrong scale.
    """

    schedule_id: str
    points: float
    domain: str
    #: Last completed week folded into this state. Preseason is 0.
    state_effective_through_week: int
    origin: str
    source: str

    def __post_init__(self) -> None:
        if not self.schedule_id:
            raise InputValidationError("Pregame point state requires a schedule_id")
        if not self.domain:
            raise InputValidationError(
                f"{self.schedule_id}: pregame point state requires an explicit domain"
            )
        if not self.source:
            raise InputValidationError(
                f"{self.schedule_id}: pregame point state requires a named source"
            )
        if self.origin not in {ORIGIN_PRESEASON_OPENING, ORIGIN_PROMOTED_RERATING}:
            raise InputValidationError(
                f"{self.schedule_id}: unknown pregame state origin {self.origin!r}"
            )
        if self.state_effective_through_week < 0:
            raise InputValidationError(
                f"{self.schedule_id}: state_effective_through_week cannot be negative"
            )


@dataclass(frozen=True)
class HistoricalGameContext:
    """The pregame half of one historical observation.

    Deliberately narrow. Fields the construction does not consume are not
    required, so a corpus is not asked to supply more than the mathematics needs.
    """

    game_id: str
    season: int
    week: int
    subject_team: str
    opponent_team: str
    #: Venue from the *subject* team's perspective. The V3 schedule stores venue
    #: from the home team's perspective (``models.Venue`` is HOME|NEUTRAL, with
    #: away-ness positional), so a corpus row must state which side it describes.
    venue: VenueTreatment
    #: Home-field modifier of whichever team is at home. ``None`` at a neutral
    #: site, where no modifier applies. Never defaulted to 1.0 — POWER_CRUNCH
    #: records it UNRESOLVED for all 13 FCS entities, and three scheduled games
    #: place one of them at a HOME venue.
    home_field_modifier: float | None
    source: str

    def __post_init__(self) -> None:
        if self.venue not in ("HOME", "AWAY", "NEUTRAL"):
            raise InputValidationError(
                f"{self.game_id}: venue must be HOME, AWAY or NEUTRAL, not {self.venue!r}"
            )
        if self.week < 1:
            raise InputValidationError(f"{self.game_id}: week must be >= 1")
        if self.subject_team == self.opponent_team:
            raise InputValidationError(f"{self.game_id}: a team cannot play itself")
        if not self.source:
            raise InputValidationError(f"{self.game_id}: requires a named source")


@dataclass(frozen=True)
class HistoricalExpectedMarginResult:
    """The outcome of one reconstruction attempt.

    ``expected_margin_points`` is ``None`` under every status but
    :data:`STATUS_AUTHORIZED`. There is no partial number.
    """

    status: Status
    game_id: str
    formula_id: str | None
    expected_margin_points: float | None
    team_pregame_points: float | None
    opponent_pregame_points: float | None
    venue_adjustment_points: float | None
    strength_domain: str
    source_bindings: dict[str, str]
    authority_bindings: dict[str, str]
    reason_if_unavailable: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "game_id": self.game_id,
            "formula_id": self.formula_id,
            "expected_margin_points": self.expected_margin_points,
            "team_pregame_points": self.team_pregame_points,
            "opponent_pregame_points": self.opponent_pregame_points,
            "venue_adjustment_points": self.venue_adjustment_points,
            "strength_domain": self.strength_domain,
            "source_bindings": dict(sorted(self.source_bindings.items())),
            "authority_bindings": dict(sorted(self.authority_bindings.items())),
            "reason_if_unavailable": self.reason_if_unavailable,
        }


# ---------------------------------------------------------------------------
# The transform
# ---------------------------------------------------------------------------


def v3_expected_home_margin(
    *,
    home_strength_points: float,
    away_strength_points: float,
    venue: str,
    hfa_baseline_points: float,
    home_hfa_modifier: float | None,
) -> float:
    """Reproduce ``game.simulate_game``'s deterministic mean, exactly.

    Written out here so the historical path and the simulation path cannot drift:
    a test evaluates both and requires bit-identical agreement.

    ``home_hfa_modifier`` is refused when absent at a non-neutral venue rather
    than defaulted, through the same accessor ``simulate_game`` uses.
    """
    if venue == "NEUTRAL":
        hfa = 0.0
    else:
        modifier = fcs_policy.require_fcs_hfa_modifier(home_hfa_modifier, "<home>")
        hfa = hfa_baseline_points * modifier
    return home_strength_points - away_strength_points + hfa


def venue_adjustment_for_subject(
    *,
    venue: VenueTreatment,
    hfa_baseline_points: float,
    home_field_modifier: float | None,
) -> float:
    """The venue term in the subject team's orientation.

    A re-orientation of the governed home-oriented term, not a second parameter.
    At an AWAY venue the modifier still belongs to the *home* side and the whole
    term changes sign; that is arithmetic on one governed quantity, so it adds no
    authority. At NEUTRAL the term is exactly zero because the strength axis is
    itself defined at neutral field — not because zero is a convenient default.
    """
    if venue == "NEUTRAL":
        return 0.0
    modifier = fcs_policy.require_fcs_hfa_modifier(home_field_modifier, "<home side>")
    magnitude = hfa_baseline_points * modifier
    return magnitude if venue == "HOME" else -magnitude


# ---------------------------------------------------------------------------
# Pregame-state contract
# ---------------------------------------------------------------------------


def require_leak_free_pregame_state(
    state: PregameTeamPoints, *, game_week: int, game_id: str
) -> None:
    """Refuse a state that could contain the game it is meant to predict.

    Two conditions, both structural rather than statistical:

    ``no same-or-later week folded in``
        A state effective through week ``w`` has absorbed every result of week
        ``w``. Predicting a week-``w`` game with it leaks the outcome into its own
        predictor. Required: ``state_effective_through_week <= game_week - 1``.

    ``the governed opening weeks really are opening weeks``
        Weeks 1 and 2 open on preseason strength by governance. A state offered
        for them that claims any completed week, or any origin but preseason, is
        not the state V3 would have held.
    """
    if state.state_effective_through_week >= game_week:
        raise GovernanceBlock(
            f"{game_id}: {state.schedule_id} pregame state is effective through week "
            f"{state.state_effective_through_week}, which includes week {game_week}. A "
            "state containing the game it predicts leaks the outcome into its own "
            "predictor and makes every out-of-sample number optimistic."
        )
    if game_week in PRESEASON_OPENING_WEEKS:
        if state.origin != ORIGIN_PRESEASON_OPENING:
            raise GovernanceBlock(
                f"{game_id}: week {game_week} opens on preseason strength "
                "(first_promoted_rerating_after_week=2), but "
                f"{state.schedule_id} offers origin {state.origin!r}."
            )
        if state.state_effective_through_week != 0:
            raise GovernanceBlock(
                f"{game_id}: week {game_week} opens on preseason strength, but "
                f"{state.schedule_id} claims completed week "
                f"{state.state_effective_through_week}."
            )


def pregame_state_contract() -> dict[str, Any]:
    """The minimum historical state this construction consumes, and nothing more.

    Narrower than ``calibration_contract.REQUIRED_CONTRACT_FIELDS``, which is the
    superset the six coefficients need. This is the subset *expected margin*
    needs, so a corpus supplier can see which fields are load-bearing for which
    purpose instead of being handed one undifferentiated list.
    """
    return {
        "contract_id": "V3-HISTORICAL-PREGAME-STATE-CONTRACT-001",
        "scope": "EXPECTED_MARGIN_CONSTRUCTION_ONLY",
        "required_fields": {
            "game_id": "Stable unique key for the observation.",
            "season": "Season the game belongs to; bounds the population the axis is over.",
            "week": (
                "Week the game was PLAYED. Decides whether the state is preseason "
                "opening strength or a promoted rerating."
            ),
            "order_key": (
                "Kickoff instant, or an equivalent total order within the week. The only "
                "field that can prove a state pre-dates its game when two games share a "
                "week."
            ),
            "subject_team": "Canonical team id. Free-text names are refused.",
            "opponent_team": "Canonical team id.",
            "venue": (
                "HOME | AWAY | NEUTRAL, from the SUBJECT team's perspective. The V3 "
                "schedule stores venue home-oriented, so the orientation must be stated "
                "rather than inferred from column order."
            ),
            "subject_pregame_points": "Subject strength before kickoff, on a declared axis.",
            "opponent_pregame_points": "Opponent strength before kickoff, on the same axis.",
            "strength_domain": (
                f"Axis declaration. Must be {V3_POINT_DOMAIN} for the governed transform "
                "to apply."
            ),
            "state_effective_through_week": (
                "Last completed week folded into both states. 0 for preseason. Must be "
                "strictly less than week."
            ),
            "state_origin": f"{ORIGIN_PRESEASON_OPENING} | {ORIGIN_PROMOTED_RERATING}.",
            "home_field_modifier": (
                "Modifier of the team at home; null only at NEUTRAL. Never defaulted "
                "to 1.0."
            ),
            "source": "Named provenance for the row and for each point state.",
        },
        "not_required_and_why": {
            "actual_margin": (
                "The outcome half of the residual. Needed by calibration, not by the "
                "predictor half this module builds."
            ),
            "game_sd_points": (
                "simulate_game consumes it for the stochastic draw only. The "
                "deterministic mean does not depend on it."
            ),
            "final_committee_rank, SOS, SOR, SOR-B": (
                "Season-end or forward-looking. None enters the transform."
            ),
            "recent_form_weights, blowout_treatment": (
                "Rerating-formula inputs. They shape the state, and a corpus supplies "
                "the state directly."
            ),
        },
        "refused_inputs": [
            "postgame rating",
            "end-of-week rating containing the game itself",
            "season-end rating",
            "future opponent results",
            "final committee rank",
            "future standings, SRS, SOS or SOR",
        ],
        "preseason_opening_weeks": list(PRESEASON_OPENING_WEEKS),
        "first_week_requiring_promoted_rerating": FIRST_WEEK_REQUIRING_PROMOTED_RERATING,
    }


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def _unavailable(
    game_id: str, domain: str, reason: str, bindings: dict[str, str]
) -> HistoricalExpectedMarginResult:
    return HistoricalExpectedMarginResult(
        status=STATUS_UNAVAILABLE,
        game_id=game_id,
        formula_id=None,
        expected_margin_points=None,
        team_pregame_points=None,
        opponent_pregame_points=None,
        venue_adjustment_points=None,
        strength_domain=domain,
        source_bindings=bindings,
        authority_bindings={},
        reason_if_unavailable=reason,
    )


def construct_historical_expected_margin(
    *,
    context: HistoricalGameContext,
    subject_state: PregameTeamPoints,
    opponent_state: PregameTeamPoints,
    hfa_baseline_points: float | None,
    axis_anchor_authority: str | None = None,
) -> HistoricalExpectedMarginResult:
    """Build one historical expected margin, or refuse and say why.

    ``axis_anchor_authority`` is the named governance placing this season's
    strengths on the V3 axis. It has no default and no fallback. Absent it the
    result is :data:`STATUS_DERIVABLE`: every term is mathematically determined
    and the formula is exact, but the axis binding is ungoverned, so no number is
    handed back. That distinction is the point of the three statuses — a reader
    can tell "we cannot compute this" from "we can compute this and are not
    permitted to".

    Two kinds of refusal are deliberately different in kind. A *missing or
    refused input* returns :data:`STATUS_UNAVAILABLE`, because a corpus can
    supply it later. A *governance violation* — a leaking state, or an HFA that
    is not the ruled value — raises, because no later supply fixes it and it must
    not be summarisable as one unavailable row among many.
    """
    bindings = {
        "game": context.source,
        "subject_state": subject_state.source,
        "opponent_state": opponent_state.source,
    }

    if subject_state.schedule_id != context.subject_team:
        raise InputValidationError(
            f"{context.game_id}: subject state is for {subject_state.schedule_id}, "
            f"not {context.subject_team}"
        )
    if opponent_state.schedule_id != context.opponent_team:
        raise InputValidationError(
            f"{context.game_id}: opponent state is for {opponent_state.schedule_id}, "
            f"not {context.opponent_team}"
        )

    # Axis first. A mismatched domain makes every later check meaningless, and a
    # number produced across two axes is arithmetic rather than evidence.
    for state in (subject_state, opponent_state):
        if state.domain != V3_POINT_DOMAIN:
            return _unavailable(
                context.game_id,
                state.domain,
                f"{state.schedule_id} is on axis {state.domain!r}; the governed "
                f"transform is exact only on {V3_POINT_DOMAIN} "
                f"({V3_POINT_DOMAIN_DEFINITION}). No conversion between axes is governed.",
                bindings,
            )

    # Leakage. Structural, and it raises rather than returning a status.
    require_leak_free_pregame_state(
        subject_state, game_week=context.week, game_id=context.game_id
    )
    require_leak_free_pregame_state(
        opponent_state, game_week=context.week, game_id=context.game_id
    )

    # Weeks >= 3 need a promoted rerating, and V3 has no governed rerating
    # *formula* at all — rerating.BlockedGovernedRerater raises unconditionally,
    # so this is stronger than six unset coefficients. A corpus may still supply
    # the state from its own source system; what it may not do is have V3
    # reconstruct one.
    if context.week >= FIRST_WEEK_REQUIRING_PROMOTED_RERATING:
        for state in (subject_state, opponent_state):
            if state.origin == ORIGIN_PRESEASON_OPENING:
                return _unavailable(
                    context.game_id,
                    V3_POINT_DOMAIN,
                    f"week {context.week} opens on a promoted rerating, but "
                    f"{state.schedule_id} offers preseason opening strength. Weeks "
                    f"{FIRST_WEEK_REQUIRING_PROMOTED_RERATING}+ carry the after-week-"
                    f"{context.week - 1} promoted state; substituting preseason would "
                    "silently reconstruct a different model.",
                    bindings,
                )

    if hfa_baseline_points is None:
        return _unavailable(
            context.game_id,
            V3_POINT_DOMAIN,
            "no football-point HFA supplied. There is no default: ruling "
            f"{R2_HFA.convergence_id} sets the V3 baseline to "
            f"{hfa_policy.V3_FOOTBALL_POINT_HFA}, and it must be passed explicitly so "
            "every reconstruction records which HFA governed it.",
            bindings,
        )
    # Rejects the legacy 4.0, and any Elo-layer value, by name.
    hfa_policy.require_governed_hfa(hfa_baseline_points)

    try:
        venue_points = venue_adjustment_for_subject(
            venue=context.venue,
            hfa_baseline_points=hfa_baseline_points,
            home_field_modifier=context.home_field_modifier,
        )
    except GovernanceBlock as exc:
        return _unavailable(context.game_id, V3_POINT_DOMAIN, str(exc), bindings)

    if not axis_anchor_authority:
        return HistoricalExpectedMarginResult(
            status=STATUS_DERIVABLE,
            game_id=context.game_id,
            formula_id=FORMULA_ID,
            expected_margin_points=None,
            team_pregame_points=None,
            opponent_pregame_points=None,
            venue_adjustment_points=None,
            strength_domain=V3_POINT_DOMAIN,
            source_bindings=bindings,
            authority_bindings={
                "hfa": f"{R2_HFA.convergence_id} / SCHED-HFA-BASE",
                "transform": f"{FORMULA_ID} ({FORMULA_SOURCE})",
                "axis_anchor": "ABSENT",
            },
            reason_if_unavailable=(
                f"Every term is determined and the transform is exact, but no governed "
                f"authority places season {context.season} strengths on "
                f"{V3_POINT_DOMAIN}. "
                f"{HISTORICAL_AXIS_ANCHOR_DEPENDENCY['dependency_id']}: "
                f"{HISTORICAL_AXIS_ANCHOR_DEPENDENCY['statement']}"
            ),
        )

    expected = subject_state.points - opponent_state.points + venue_points
    return HistoricalExpectedMarginResult(
        status=STATUS_AUTHORIZED,
        game_id=context.game_id,
        formula_id=FORMULA_ID,
        expected_margin_points=expected,
        team_pregame_points=subject_state.points,
        opponent_pregame_points=opponent_state.points,
        venue_adjustment_points=venue_points,
        strength_domain=V3_POINT_DOMAIN,
        source_bindings=bindings,
        authority_bindings={
            "hfa": f"{R2_HFA.convergence_id} / SCHED-HFA-BASE",
            "transform": f"{FORMULA_ID} ({FORMULA_SOURCE})",
            "axis_anchor": axis_anchor_authority,
        },
        reason_if_unavailable=None,
    )


# ---------------------------------------------------------------------------
# Identification structure
# ---------------------------------------------------------------------------

#: Whether the weekly recursion is genuinely circular, tested rather than assumed.
#:
#: The suspected circle is: expected margin needs pregame strength; pregame
#: strength needs the prior rerating; the prior rerating needs the coefficient
#: being calibrated. Traced against ``engine`` and ``rerating`` it is a recursion
#: with a **well-founded base case** — weeks 1 and 2 open on preseason strength
#: and consume no coefficient — so for any candidate parameter vector the whole
#: walk-forward is deterministic and leak-free. That is a profile/outer-loop
#: estimation structure, not a circular definition.
#:
#: What *is* a real identification failure is separate and is not about the
#: coefficient at all: the points-per-SD scale and the residual coefficient are
#: exactly confounded while both are free.
IDENTIFICATION_STRUCTURE: dict[str, Any] = {
    "circularity": "NOT_CIRCULAR__PARAMETER_CONDITIONAL_RECURSION",
    "base_case": (
        "Weeks 1 and 2 open on preseason opening strength "
        "(config.first_promoted_rerating_after_week = 2; week 1's rerating is "
        "audit-only and week 2's games precede the after-week-2 promotion), so their "
        "expected margins consume no calibration coefficient."
    ),
    "recursion": (
        "For week w >= 3 the opening state is the after-week-(w-1) promoted rerating, "
        "which is a function of the candidate parameters. Given a candidate vector the "
        "trajectory is deterministic and uses only prior completed games, so an outer "
        "walk-forward loop over candidates is statistically valid. This lane does not "
        "run one."
    ),
    "genuine_identification_failure": {
        "id": "SCALE_COEFFICIENT_CONFOUNDING",
        "statement": (
            "weekly_performance_residual_coefficient and the points-per-SD scale of the "
            "strength axis are not separately identified while both are free. Scaling "
            "the axis by k and the coefficient by 1/k leaves every predicted margin "
            "unchanged, so no objective over margins can distinguish them."
        ),
        "resolution_order": (
            "Anchor the axis first (HISTORICAL_STRENGTH_AXIS_ANCHOR), then estimate the "
            "coefficient against it. The reverse order is not merely harder — it is "
            "unidentified."
        ),
    },
    "stronger_than_unset_coefficients": (
        "For weeks 3+ V3 carries no governed rerating *formula* at all: "
        "rerating.BlockedGovernedRerater raises unconditionally and FixtureResidualRerater "
        "is test-only and explicitly not a canonical V3 calibration formula. So even a "
        "fully specified parameter vector would not let V3 reconstruct a week-3 state."
    ),
}

#: The staged experiment design, as a dependency graph. Each stage records what
#: must already hold; no stage estimates anything here.
IDENTIFICATION_STAGES: tuple[dict[str, Any], ...] = (
    {
        "stage": "A",
        "name": "GOVERNED_OPENING_WEEK_RESIDUAL_DISPERSION",
        "scope": "Weeks 1-2 only.",
        "depends_on": ["HISTORICAL_STRENGTH_AXIS_ANCHOR", "an admitted historical corpus"],
        "does_not_depend_on": [
            "calibration.weekly_performance_residual_coefficient",
            "calibration.weekly_movement_cap_points",
            "calibration.recent_form_weights",
            "calibration.blowout_treatment",
            "calibration.sample_size_regularization",
            "a governed weekly rerating formula",
        ],
        "valid": True,
        "caveat": (
            "Two weeks per season is a thin base, the estimate is conditional on the "
            "anchored scale, and opening weeks are not a random sample of the season — "
            "they are systematically heavy in mismatches. An estimate from them bounds "
            "and informs; it does not settle game_sd_points."
        ),
    },
    {
        "stage": "B",
        "name": "OUTER_WALK_FORWARD_OVER_CANDIDATE_RERATING_PARAMETERS",
        "scope": "Weeks 3+.",
        "depends_on": [
            "Stage A",
            "a governed weekly rerating formula (absent today)",
            "HISTORICAL_STRENGTH_AXIS_ANCHOR",
        ],
        "valid": True,
        "caveat": (
            "Valid as a procedure, not runnable: the formula the parameters would "
            "parameterise does not exist in governed form."
        ),
    },
    {
        "stage": "C",
        "name": "HFA_AS_AN_EXPERIMENTAL_WITNESS",
        "scope": "Any stage.",
        "depends_on": ["Stage A"],
        "valid": True,
        "caveat": (
            "A historically estimated HFA is a witness quantity in its own namespace. "
            f"The canonical V3 football-point HFA {hfa_policy.V3_FOOTBALL_POINT_HFA} is "
            f"LOCKED by ruling {R2_HFA.convergence_id} and is not an estimand here. "
            "Estimating HFA jointly with the axis scale re-opens the same confounding "
            "as the coefficient, so it is estimated only against an anchored axis."
        ),
    },
    {
        "stage": "D",
        "name": "HOLDOUT_VALIDATION",
        "scope": "Reserved seasons.",
        "depends_on": ["Stages A-C", "calibration_contract.SPLIT_POLICY"],
        "valid": True,
        "caveat": "Scored once, never used for selection.",
    },
)

#: Residual game SD is not the unconditional signed-margin SD, and the arithmetic
#: relating them is what makes 19.764 a bound rather than a value.
GAME_SD_IDENTIFICATION: dict[str, Any] = {
    "unconditional_signed_margin_sd": {
        "definition": "sd(actual_margin) over observations, ignoring any predictor.",
        "observed_2024_corpus_value": 19.764,
        "is_game_sd_points": False,
    },
    "residual_game_sd": {
        "definition": "sd(actual_margin - governed_pregame_expected_margin).",
        "is_game_sd_points": True,
        "role_in_v3": (
            "game.simulate_game draws simulated_home_margin ~ Normal(expected, "
            "game_sd_points), so game_sd_points is the dispersion *around* the "
            "deterministic mean, by construction."
        ),
    },
    "why_19_764_is_an_upper_bound_only": (
        "Var(actual) = Var(expected) + Var(residual) + 2*Cov(expected, residual). A "
        "pregame predictor with no systematic bias has Cov ~ 0, giving Var(residual) = "
        "Var(actual) - Var(expected) <= Var(actual). So the unconditional SD bounds the "
        "residual SD from above, strictly whenever the predictor explains any strength "
        "difference at all. It locates nothing."
    ),
    "must_be_known_first": [
        "HISTORICAL_STRENGTH_AXIS_ANCHOR — the SD is in points, so it inherits the axis "
        "scale directly; an unanchored axis makes the number unitless.",
        "A governed pregame expected margin per observation — the subtrahend.",
        "game_type and overtime_periods tagging — both are contract fields awaiting an "
        "admission ruling, and both inflate an untagged residual pool.",
        "opponent_division — FBS-vs-FCS residuals cannot be pooled while the FCS point "
        "scale is an open blocker.",
    ],
    "weeks_1_2_could_support_an_initial_estimate": True,
    "weeks_1_2_caveat": (
        "Conditional on the anchor, and on a corpus this repository does not hold. Not "
        "estimated here."
    ),
    "governed_open_item": "ENG-CAL-MARGIN (OPEN); 20.2 remains unpromoted.",
}


# ---------------------------------------------------------------------------
# Authority matrix
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorityEntry:
    """One object in the expected-margin authority chain."""

    label: str
    status: str
    unit: str
    scope: str
    source: str
    governed: bool
    historical_calibration_usable: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "status": self.status,
            "unit": self.unit,
            "scope": self.scope,
            "source": self.source,
            "governed": self.governed,
            "historical_calibration_usable": self.historical_calibration_usable,
            "reason": self.reason,
        }


AUTHORITY_MATRIX: tuple[AuthorityEntry, ...] = (
    AuthorityEntry(
        label="CURRENT_V3_FOOTBALL_STRENGTH_DOMAIN",
        status="GOVERNED_AND_IN_PRODUCTION",
        unit="unified neutral-field points",
        scope="2026 closed 121-team FBS population",
        source=V3_POINT_DOMAIN_SOURCE,
        governed=True,
        historical_calibration_usable=False,
        reason=(
            "Exact for 2026, where the values are read verbatim from the mounted "
            "workbook. Not usable historically: the axis is defined over a closed "
            "population that no historical season belongs to."
        ),
    ),
    AuthorityEntry(
        label="PRESEASON_STRENGTH_TRANSFORM",
        status="CANONICAL_INPUT_CONSTRUCTION__2026_CROSS_SECTIONAL_ONLY",
        unit="points per standard deviation",
        scope="2026 preseason, 121-team population",
        source=(
            "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Data Dictionary and "
            "!Ensemble Parameters"
        ),
        governed=True,
        historical_calibration_usable=False,
        reason=(
            f"{V3_POINT_DOMAIN_DEFINITION}, four families at 0.25 each. It is the "
            "construction of a governed *input*, not a portable transform: Z is "
            "population-relative and the 14 is marked "
            f"{V3_POINT_DOMAIN_SCALE_STATUS!r}. V3 never applies it at runtime — "
            "inputs.load_preseason_ratings reads the finished points column."
        ),
    ),
    AuthorityEntry(
        label="P_TO_STRENGTH_TRANSFORM",
        status="UNRATIFIED__SOR_B_SCOPE_ONLY",
        unit="dimensionless probability -> resume scalar",
        scope="SOR-B research report",
        source="sor.UNRATIFIED_SOR_B_ITEMS; compute_sor_b.py is not mounted",
        governed=False,
        historical_calibration_usable=False,
        reason=(
            "'P' is the Poisson-binomial reference win probability, not a power index. "
            "The item is output-side of a RESEARCH_REPORT_ONLY metric and is not on the "
            "expected-margin path. Ratifying it would not produce a football point."
        ),
    ),
    AuthorityEntry(
        label="REFERENCE_HFA",
        status="UNRATIFIED__SOR_B_SCOPE_ONLY",
        unit="Elo points",
        scope="SOR-B reference-team win probability",
        source="sor._reference_win_probability; no mounted artifact records it",
        governed=False,
        historical_calibration_usable=False,
        reason=(
            "An Elo-layer term on the 400-point logistic scale, describing the reference "
            "team's per-game expectation. Not the football-point venue term, and not "
            "read by any point-domain code path."
        ),
    ),
    AuthorityEntry(
        label="V3_HFA_3_5",
        status="LOCKED",
        unit="football points",
        scope="V3 football-point layer",
        source=f"SCHED-HFA-BASE; ruling {R2_HFA.convergence_id}; hfa.HFA_REGISTER",
        governed=True,
        historical_calibration_usable=True,
        reason=(
            "The venue term of the governed transform. Usable historically *only* for "
            "strengths already on the V3 point axis, because an HFA is meaningful solely "
            "in the units of the strengths it is added to."
        ),
    ),
    AuthorityEntry(
        label="V2_1_HFA_4_0",
        status="HISTORICAL / NOT CURRENT",
        unit="football points",
        scope="legacy V2 drive engine",
        source="ENG-HOME-FIELD in 02_PARAMETER_REGISTER; hfa.LEGACY_V2_DRIVE_ENGINE_HFA",
        governed=False,
        historical_calibration_usable=False,
        reason=(
            "Preserved unedited and never applied by V3. hfa.require_governed_hfa "
            "refuses it by name, so it cannot enter a reconstruction as a plausible "
            "number."
        ),
    ),
    AuthorityEntry(
        label="ELO_HFA_55",
        status="NOT_PRESENT_IN_THIS_REPOSITORY",
        unit="Elo points",
        scope="Elo layer",
        source="named in the lane instruction; no mounted module or register carries it",
        governed=False,
        historical_calibration_usable=False,
        reason=(
            "Recorded as a distinct Elo-layer parameter that must not be collapsed into "
            "any other HFA. It is not defined anywhere in this repository, so nothing "
            "here may cite it and no value is asserted for it."
        ),
    ),
    AuthorityEntry(
        label="CCG_MC_ELO_HFA_65",
        status="LOCKED",
        unit="Elo points",
        scope="CCG / Monte Carlo Elo layer",
        source="CCG-HFA_ELO under R-CCG-06 / DEF-CCG-6; hfa.CCG_ELO_HFA",
        governed=True,
        historical_calibration_usable=False,
        reason=(
            "A separate parameter in a separate namespace. Adding it to a football-point "
            "difference is a unit error, not a substitution."
        ),
    ),
    AuthorityEntry(
        label="BAXTER_DOMAIN",
        status="PRIMARY_OBJECTIVE__NOT_A_MARGIN_SCALE",
        unit="Baxter rating units (undeclared here)",
        scope="calibration objective",
        source=f"ruling {R2_CALIBRATION.convergence_id}; 'Pure Baxter' is one of the four "
               "unified Z families",
        governed=True,
        historical_calibration_usable=False,
        reason=(
            "Governed as the primary out-of-sample criterion, not as a point scale. It "
            "enters the unified axis only after standardization, so a raw Baxter rating "
            "is not in points and needs a transform that no register issues. Mounted "
            "Baxter artifacts are season-final and classified ENGINE_OUTPUT, so they are "
            "not admissible as a pregame state either."
        ),
    ),
    AuthorityEntry(
        label="COLLEY_DOMAIN",
        status="NAMED_WITNESS__NOT_IMPLEMENTED",
        unit="dimensionless rating on (0, 1)",
        scope="calibration witness",
        source=f"ruling {R2_CALIBRATION.convergence_id}",
        governed=True,
        historical_calibration_usable=False,
        reason=(
            "Named as an independent witness and reported separately; no implementation "
            "exists in this repository. A Colley rating is result-based and carries no "
            "margin information at all, so it cannot form an expected margin under any "
            "transform."
        ),
    ),
    AuthorityEntry(
        label="SRS_DOMAIN",
        status="IMPLEMENTED_WITNESS",
        unit="capped-margin points (per-game cap +/-24)",
        scope="calibration witness",
        source=f"ruling {R2_SRS.convergence_id}; srs.py",
        governed=True,
        historical_calibration_usable=False,
        reason=(
            "Point-like and margin-derived, but not the V3 axis: the +/-24 cap "
            "deliberately compresses exactly the blowouts a margin predictor must "
            "predict, and the rating is centred on its own population. Reconstructable "
            "from prior games alone, so it is a usable *witness*; it is not an "
            "expected-margin source."
        ),
    ),
    AuthorityEntry(
        label="FCS_ELO_1250",
        status="LOCKED",
        unit="Elo points",
        scope="13 schedule-only FCS entities",
        source=f"ruling {R2_FCS.convergence_id}; fcs.FCS_FIXED_ELO",
        governed=True,
        historical_calibration_usable=False,
        reason=(
            "The FCS rating policy is settled and is not reopened. An Elo is not a point "
            "value, and no governed register maps this one onto the points axis."
        ),
    ),
    AuthorityEntry(
        label="FCS_POINT_ADAPTER",
        status="OPEN_FORMAL_BLOCKER",
        unit="unified neutral-field points",
        scope="13 schedule-only FCS entities",
        source="model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER; fcs.CANDIDATE_SCALE_ROUTES",
        governed=False,
        historical_calibration_usable=False,
        reason=(
            "No adapter is registered. Every FBS-vs-FCS expected margin fails closed on "
            "this existing blocker; none is invented here."
        ),
    ),
    AuthorityEntry(
        label="HISTORICAL_STRENGTH_AXIS_ANCHOR",
        status="ABSENT__HUMAN_GOVERNANCE_REQUIRED",
        unit="points per standard deviation, across populations",
        scope="any season outside the closed 2026 population",
        source="no mounted artifact",
        governed=False,
        historical_calibration_usable=False,
        reason=(
            "The one authority this lane finds genuinely missing. Without it no "
            "historical strength can be placed on the V3 axis, and the axis scale stays "
            "confounded with the residual coefficient."
        ),
    ),
)


def authority_matrix_as_dict() -> dict[str, Any]:
    """The deterministic machine-readable authority matrix.

    Every value is either transcribed from a mounted artifact or derived from
    code in this repository. Nothing is fitted and nothing is promoted.
    """
    return {
        "matrix_id": MATRIX_ID,
        "status": "EXPERIMENTAL_SUCCESSOR_ARTIFACT__NO_HISTORICAL_ARTIFACT_REWRITTEN",
        "formula": {
            "formula_id": FORMULA_ID,
            "source": FORMULA_SOURCE,
            "expression": FORMULA_EXPRESSION,
            "orientation": "HOME_ORIENTED",
            "subject_oriented_venue_term": (
                "+hfa at HOME, -hfa at AWAY, exactly 0.0 at NEUTRAL; the modifier always "
                "belongs to the home side"
            ),
            "unit": "football points",
            "free_parameters": [],
            "consumes_calibration_coefficients": False,
        },
        "strength_domain": {
            "id": V3_POINT_DOMAIN,
            "definition": V3_POINT_DOMAIN_DEFINITION,
            "source": V3_POINT_DOMAIN_SOURCE,
            "scale_status": V3_POINT_DOMAIN_SCALE_STATUS,
            "points_per_sd": fcs_policy.UNIFIED_NEUTRAL_POINTS_PER_SD,
            "z_population": fcs_policy.UNIFIED_Z_POPULATION_SIZE,
        },
        "entries": [e.as_dict() for e in AUTHORITY_MATRIX],
        "sor_b_scope_finding": dict(SOR_B_SCOPE_FINDING),
        "historical_axis_anchor_dependency": {
            **HISTORICAL_AXIS_ANCHOR_DEPENDENCY,
            "not_bundled_with": list(HISTORICAL_AXIS_ANCHOR_DEPENDENCY["not_bundled_with"]),
        },
        "identification_structure": dict(IDENTIFICATION_STRUCTURE),
        "identification_stages": [dict(s) for s in IDENTIFICATION_STAGES],
        "game_sd_identification": dict(GAME_SD_IDENTIFICATION),
        "pregame_state_contract": pregame_state_contract(),
        "week_dispositions": {
            "week_1": STATUS_DERIVABLE,
            "week_2": STATUS_DERIVABLE,
            "week_3_plus": STATUS_UNAVAILABLE,
            "week_3_plus_reason": IDENTIFICATION_STRUCTURE[
                "stronger_than_unset_coefficients"
            ],
        },
        "fcs_expected_margin": {
            "status": STATUS_UNAVAILABLE,
            "blocker": fcs_policy.FCS_UNIFIED_SCALE_BLOCKER,
            "fixed_elo": fcs_policy.FCS_FIXED_ELO,
            "point_mapping": None,
        },
        "parameters_promoted": [],
        "canonical_config_written": False,
        "formal_blockers_opened": [],
        "formal_blockers_retired": [],
    }


def write_authority_matrix(path: Path) -> Path:
    """Emit the authority matrix as a reviewable JSON artifact.

    LF is pinned rather than inherited, for the reason ``textio`` documents: this
    artifact is compared by digest across machines.
    """
    return write_json_lf(path, authority_matrix_as_dict(), trailing_newline=True)
