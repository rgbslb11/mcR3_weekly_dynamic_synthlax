"""Chairman V3 model-design rulings, round R1.

This module is an *authority record and a design specification*. It promotes no
calibration winner, runs no season, and touches no governed configuration value.
The three parameters the Chairman left open — the weekly performance-residual
coefficient, ``game_sd_points`` and the recent-form ``lambda`` — stay unbound
here and are described only as a deterministic sweep the later model-run
supervisor executes.

Why the identifiers are ``MDR1-`` and not ``R1-``
-------------------------------------------------
``blocker_report`` already uses ``R1_`` for the round-1 *blocker audit* baseline,
and :mod:`.rulings` reserves ``R2-``/``R3-``/``R4-`` for the governance
convergences. These are model-design rulings from a different instruction, so
they carry their own prefix and their own tuple. They are deliberately *not*
folded into :data:`.rulings.ALL_RULINGS`: that tuple is the governance-
convergence lineage, and merging two lineages would make the succession
unreadable in exactly the place it has to stay readable.

As everywhere else in this package, ``chairman_ruling_id`` stays ``None``. The
instruction issued the decisions but supplied no Chairman ruling identifiers, and
one is never invented.

Three epistemic classes are kept strictly apart, because the whole point of the
instruction is that they not be collapsed:

``FIXED_V3_POLICY`` / ``FIXED_V3_SYNTHETIC_SCALE``
    Chosen by direct Chairman authority. True by decision, not by measurement.
``DESIGN_TUNING_REQUIRED`` -> ``FIXED_BY_V3_*_DESIGN``
    Selected by a declared sweep against declared model-behaviour diagnostics.
``EMPIRICALLY_IDENTIFIED``
    Never claimed by anything in this module. :data:`EMPIRICALLY_IDENTIFIED` is
    defined only so it can be checked for and refused.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .errors import GovernanceBlock, InputValidationError
from .rulings import ChairmanRuling
from .textio import write_json_lf

#: Issued together as one instruction; recorded once so every ruling shares it.
MDR1_INSTRUCTION = "OPERATION SYTHALAX — V3 CHAIRMAN MODEL-DESIGN RULINGS R1"

MDR1_ARTIFACT = "V3_CHAIRMAN_MODEL_DESIGN_RULINGS_R1.json"


# ---------------------------------------------------------------------------
# 1. Governing domain
# ---------------------------------------------------------------------------

#: The production model's domain. Prior information and outcome are both
#: synthetic; nothing real is fitted against.
GOVERNING_DOMAIN = "SYNTHETIC_2024_2025_PRIOR_INFORMATION_TO_SYNTHETIC_2026"

#: Real historical football. Admissible as a witness, never as a fit target and
#: never as an override of a synthetic V3 design ruling.
REAL_FOOTBALL_STATUS = "EXTERNAL_WITNESS_ONLY"

#: The classification this module must never emit for any V3 parameter. Defined
#: so it can be searched for and refused, not so it can be used.
EMPIRICALLY_IDENTIFIED = "EMPIRICALLY_IDENTIFIED"

#: Every epistemic class this ruling round is allowed to assign.
PERMITTED_STATUSES = (
    "FIXED_V3_POLICY",
    "FIXED_V3_GLOBAL_POLICY",
    "FIXED_V3_SYNTHETIC_SCALE",
    "ADVISORY_ONLY",
    "DESIGN_TUNING_REQUIRED",
    "FIXED_BY_V3_RESPONSIVENESS_DESIGN",
    "FIXED_BY_V3_SENSITIVITY_DESIGN",
    "SYNTHETIC_FIT_RESULT",
    "EXTERNAL_WITNESS_ONLY",
    "NOT_EMPIRICALLY_IDENTIFIED",
    "BLOCKED_PENDING_GOVERNED_INPUT",
)


def reject_empirical_identification_claim(status: str) -> str:
    """Refuse any attempt to mark a V3 design parameter empirically identified."""
    if str(status).strip().upper() == EMPIRICALLY_IDENTIFIED:
        raise GovernanceBlock(
            "No V3 parameter governed by the R1 model-design rulings is empirically "
            "identified. Point scale 14.0 is a synthetic convention; the coefficient, "
            "game SD and recent-form lambda are selected by responsiveness/sensitivity "
            "design, not estimated from outcomes."
        )
    if status not in PERMITTED_STATUSES:
        raise GovernanceBlock(
            f"Status {status!r} is not one of the permitted R1 epistemic classes: "
            f"{', '.join(PERMITTED_STATUSES)}."
        )
    return status


# ---------------------------------------------------------------------------
# 2. Blowout treatment
# ---------------------------------------------------------------------------

BLOWOUT_TREATMENT = "CAP_UPDATE_DRIVING_MARGIN"
BLOWOUT_MARGIN_CAP_POINTS = 25.0
BLOWOUT_TREATMENT_STATUS = "FIXED_V3_POLICY"


def update_driving_margin(actual_margin: float) -> float:
    """Clip ``actual_margin`` to +/-25 for update purposes only.

    ``sign(m) * min(|m|, 25.0)``. The final score and the actual game margin are
    inputs to this function and are never written back by it: the cap exists
    inside the rating update and nowhere else. A margin of exactly zero has no
    sign and is returned unchanged.
    """
    margin = float(actual_margin)
    if math.isnan(margin):
        raise InputValidationError("actual_margin is NaN; a game margin must be a number")
    if margin == 0.0:
        return 0.0
    sign = 1.0 if margin > 0.0 else -1.0
    return sign * min(abs(margin), BLOWOUT_MARGIN_CAP_POINTS)


def blowout_cap_hit(actual_margin: float) -> bool:
    """Whether the cap actually bound for this game. Reported, never inferred."""
    return abs(float(actual_margin)) > BLOWOUT_MARGIN_CAP_POINTS


#: An Agent-3 experimental blowout optimum is evidence about the experiment, not
#: authority over the later direct ruling.
EXPERIMENTAL_BLOWOUT_RESULT_CLASS = "DIAGNOSTIC_WITNESS"


def classify_experimental_blowout_result(cap_points: float | None) -> dict[str, object]:
    """Record an experimental blowout optimum as a witness and keep 25.0 governing.

    Called with any value at all — including a different, better-fitting cap —
    this returns the same governed cap. That is the point: the Chairman ruled
    after the experiment, so the experiment cannot silently overwrite the ruling.
    """
    return {
        "experimental_cap_points": None if cap_points is None else float(cap_points),
        "experimental_result_class": EXPERIMENTAL_BLOWOUT_RESULT_CLASS,
        "governed_cap_points": BLOWOUT_MARGIN_CAP_POINTS,
        "governed_treatment": BLOWOUT_TREATMENT,
        "governed_by": "MDR1-BLOWOUT-CAP-25",
        "overrides_chairman_ruling": False,
        "note": (
            "Preserved as a diagnostic. The Chairman ruling is the later, direct "
            "authority and is the production V3 design decision."
        ),
    }


def governed_blowout_cap_points() -> float:
    """The one blowout cap V3 is authorised to apply."""
    return BLOWOUT_MARGIN_CAP_POINTS


# ---------------------------------------------------------------------------
# 3. Point scale
# ---------------------------------------------------------------------------

#: FACT — the V3 neutral-field point scale, frozen by direct Chairman authority.
#: Numerically identical to the mounted unified-ratings scale
#: (``2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Ensemble Parameters``,
#: "Neutral-field point scale | 14"), whose own source records it as "Initial
#: points per standard deviation; recalibrate against game margins".
V3_POINT_SCALE = 14.0
V3_POINT_SCALE_STATUS = "FIXED_V3_SYNTHETIC_SCALE"
V3_POINT_SCALE_IDENTIFICATION = "NOT_EMPIRICALLY_IDENTIFIED"
V3_POINT_SCALE_DEFINITION = "V3_NEUTRAL_FIELD_POINTS = 14.0 * Unified_Master_Z"


def v3_neutral_field_points(unified_master_z: float) -> float:
    """The scale definition, applied. Not a fitted transform."""
    return V3_POINT_SCALE * float(unified_master_z)


# ---------------------------------------------------------------------------
# 4. Weekly ranking movement — advisory only
# ---------------------------------------------------------------------------

WEEKLY_RANK_MOVEMENT_ADVISORY_SLOTS = 10
WEEKLY_RANK_MOVEMENT_STATUS = "ADVISORY_ONLY"
LARGE_WEEKLY_RANK_MOVE = "LARGE_WEEKLY_RANK_MOVE"

#: Every field an advisory must carry. Named here so an emitter cannot quietly
#: drop the ones that make the move reviewable.
LARGE_WEEKLY_RANK_MOVE_FIELDS = (
    "team",
    "prior_rank",
    "new_rank",
    "slot_change",
    "underlying_point_change",
    "performance_residual",
    "cap_hit",
)


@dataclass(frozen=True)
class LargeWeeklyRankMove:
    """One emitted advisory. Carries no authority to change a rating."""

    team: str
    prior_rank: int
    new_rank: int
    slot_change: int
    underlying_point_change: float
    performance_residual: float
    cap_hit: bool
    signal: str = LARGE_WEEKLY_RANK_MOVE

    def as_dict(self) -> dict[str, object]:
        return {
            "signal": self.signal,
            "team": self.team,
            "prior_rank": self.prior_rank,
            "new_rank": self.new_rank,
            "slot_change": self.slot_change,
            "underlying_point_change": self.underlying_point_change,
            "performance_residual": self.performance_residual,
            "cap_hit": self.cap_hit,
        }


def rank_move_advisory(
    *,
    team: str,
    prior_rank: int,
    new_rank: int,
    underlying_point_change: float,
    performance_residual: float,
    cap_hit: bool,
) -> LargeWeeklyRankMove | None:
    """Emit an advisory when absolute slot movement exceeds ten. Never clamp.

    Returns ``None`` below the threshold. It returns an *observation* above it:
    there is deliberately no code path here that adjusts a rank or a rating,
    because the threshold is a reporting rule and treating it as a cap is the
    exact mistake the ruling forbids.
    """
    slot_change = int(new_rank) - int(prior_rank)
    if abs(slot_change) <= WEEKLY_RANK_MOVEMENT_ADVISORY_SLOTS:
        return None
    return LargeWeeklyRankMove(
        team=team,
        prior_rank=int(prior_rank),
        new_rank=int(new_rank),
        slot_change=slot_change,
        underlying_point_change=float(underlying_point_change),
        performance_residual=float(performance_residual),
        cap_hit=bool(cap_hit),
    )


def rank_movement_is_capped() -> bool:
    """Always ``False``. Ranking movement is never truncated to satisfy the advisory."""
    return False


# ---------------------------------------------------------------------------
# 5. Weekly performance residual coefficient — sweep, not estimate
# ---------------------------------------------------------------------------

COEFFICIENT_STATUS_BEFORE_SWEEP = "DESIGN_TUNING_REQUIRED"
COEFFICIENT_STATUS_AFTER_SWEEP = "FIXED_BY_V3_RESPONSIVENESS_DESIGN"
COEFFICIENT_SELECTION_METHOD = "500_PATH_RESPONSIVENESS_SWEEP"
COEFFICIENT_SELECTION_OBJECTIVE = "MODEL_RESPONSIVENESS"

#: The refusal token a caller sees when it asks for candidate values that no
#: governed source has declared.
COEFFICIENT_UNIVERSE_MISSING = "COEFFICIENT_SEARCH_UNIVERSE_SOURCE_MISSING"

#: Where a predeclared coefficient universe was looked for, and what was there.
#: The instruction says to reuse an existing declared universe rather than
#: invent one. It was searched for and it is not present, so the axis carries
#: three named slots and no numbers.
COEFFICIENT_UNIVERSE_SEARCH = (
    {
        "location": "config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json",
        "finding": (
            "regimes: []. The file's own _governance block states it 'ships with zero "
            "regimes on purpose: no candidate coefficient values have been authored, "
            "because authoring them would invent calibration data.'"
        ),
    },
    {
        "location": "config/dynamic_weekly_mc_v3/v3_experimental.json",
        "finding": "calibration.weekly_performance_residual_coefficient is null.",
    },
    {
        "location": "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_DATA_CONTRACT.json",
        "finding": (
            "Declares the fields a fit would require and records the coefficient as "
            "unidentifiable without a named rating-to-margin transform. Declares no "
            "candidate values."
        ),
    },
    {
        "location": "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_EVIDENCE_DISCOVERY_R5.json",
        "finding": "Evidence discovery record. No candidate coefficient universe.",
    },
    {
        "location": "src/ncaaf_engine/simulation/dynamic_weekly_mc_v3/calibration.py",
        "finding": (
            "Provides the CandidateRegime/ExperimentRecord machinery and the ranking "
            "objective. Declares no coefficient values."
        ),
    },
)

COEFFICIENT_UNIVERSE_STATUS = "PREDECLARED_COEFFICIENT_UNIVERSE_NOT_PRESENT"

#: The three deterministic slots the design matrix reserves. They are slots, not
#: values: binding them is the later supervisor's job, from a governed universe.
COEFFICIENT_CANDIDATE_SLOTS = ("LOW", "MIDDLE", "HIGH")


def coefficient_candidates(
    universe: Sequence[float] | None = None,
) -> tuple[float, float, float]:
    """LOW / MIDDLE / HIGH drawn deterministically from a supplied universe.

    ``universe`` is the *governed, predeclared* candidate set. None is mounted in
    this repository, so calling this with nothing fails closed rather than
    returning an invented triple. When a universe is supplied the refinement is
    deterministic — sorted, then minimum / median / maximum — and the full source
    universe travels with the result via :func:`coefficient_axis_as_dict`.
    """
    if universe is None:
        raise GovernanceBlock(
            f"{COEFFICIENT_UNIVERSE_MISSING}: no governed or predeclared coefficient "
            "search universe exists in this repository. "
            "config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json carries "
            "regimes: [] by design and every other calibration record leaves the "
            "coefficient null. The R1 rulings therefore reserve three candidate slots "
            f"{COEFFICIENT_CANDIDATE_SLOTS} and bind no values."
        )
    values = sorted(float(v) for v in universe)
    if len(values) < 3:
        raise GovernanceBlock(
            "A coefficient universe must offer at least three distinct candidates to "
            f"populate {COEFFICIENT_CANDIDATE_SLOTS}; got {len(values)}."
        )
    return (values[0], values[len(values) // 2], values[-1])


#: The diagnostics the sweep must expose. Minimum set, in the order the
#: instruction lists them, so a reviewer can check coverage by reading down.
COEFFICIENT_SWEEP_DIAGNOSTICS = (
    "mean_absolute_weekly_v3_point_movement",
    "sd_of_weekly_point_movement",
    "maximum_weekly_point_movement",
    "ten_slot_advisory_frequency",
    "sign_reversals_or_oscillation",
    "repeated_reversal_frequency",
    "blowout_cap_hit_frequency",
    "favorite_win_rate",
    "upset_rate",
    "undefeated_team_frequency",
    "conference_title_concentration",
    "cfp_concentration",
    "national_title_concentration",
    "probability_volatility",
)

#: The preferred reading, recorded as prose on purpose. Turning "lowest
#: coefficient that produces meaningful responsiveness without pathological
#: oscillation" into a numeric threshold here would be inventing the selection
#: rule the Chairman reserved for review.
COEFFICIENT_SELECTION_PREFERENCE = (
    "Choose the lowest coefficient that produces meaningful weekly responsiveness "
    "without pathological oscillation or instability."
)
COEFFICIENT_SELECTION_THRESHOLD_NUMERIC = None
COEFFICIENT_SELECTION_THRESHOLD_NOTE = (
    "Deliberately null. The qualitative preference is not converted into an "
    "arbitrary numeric threshold in this lane; the sweep exposes the diagnostics "
    "and the selection is a deterministic/Chairman review step."
)


def coefficient_axis_as_dict(universe: Sequence[float] | None = None) -> dict[str, object]:
    """The coefficient axis of the design matrix, with its provenance attached."""
    try:
        candidates: list[float] | None = list(coefficient_candidates(universe))
        bound = True
    except GovernanceBlock:
        candidates, bound = None, False
    return {
        "parameter": "weekly_performance_residual_coefficient",
        "status_before_sweep": COEFFICIENT_STATUS_BEFORE_SWEEP,
        "status_after_sweep": COEFFICIENT_STATUS_AFTER_SWEEP,
        "selection_method": COEFFICIENT_SELECTION_METHOD,
        "selection_objective": COEFFICIENT_SELECTION_OBJECTIVE,
        "candidate_slots": list(COEFFICIENT_CANDIDATE_SLOTS),
        "candidate_values": candidates,
        "candidates_bound": bound,
        "source_universe": None if universe is None else [float(v) for v in universe],
        "source_universe_status": COEFFICIENT_UNIVERSE_STATUS,
        "source_universe_search": [dict(x) for x in COEFFICIENT_UNIVERSE_SEARCH],
        "refusal_token": None if bound else COEFFICIENT_UNIVERSE_MISSING,
        "diagnostics_required": list(COEFFICIENT_SWEEP_DIAGNOSTICS),
        "selection_preference": COEFFICIENT_SELECTION_PREFERENCE,
        "selection_threshold_numeric": COEFFICIENT_SELECTION_THRESHOLD_NUMERIC,
        "selection_threshold_note": COEFFICIENT_SELECTION_THRESHOLD_NOTE,
        "empirically_identified": False,
    }


# ---------------------------------------------------------------------------
# 6. Game SD points — a result-dispersion axis, not a rating-uncertainty one
# ---------------------------------------------------------------------------

GAME_SD_STATUS_BEFORE_SWEEP = "DESIGN_TUNING_REQUIRED"
GAME_SD_STATUS_AFTER_SWEEP = "FIXED_BY_V3_SENSITIVITY_DESIGN"

#: FACT — ``Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER`` CCG-SIGMA_ELO
#: = 68, parameter_name ``sigma_elo``, note "Rating uncertainty per iteration".
#: A rating-state uncertainty in the Elo namespace. Never a game-result SD.
SIGMA_ELO_RATING_STATE_UNCERTAINTY = 68.0

#: Elo-layer / rating-state magnitudes that must never be accepted as a
#: game-level result dispersion, whatever units they superficially resemble.
FORBIDDEN_AS_GAME_SD = {
    SIGMA_ELO_RATING_STATE_UNCERTAINTY: (
        "CCG-SIGMA_ELO 68 is per-iteration rating-state uncertainty in the Elo "
        "namespace, not game-level result dispersion in V3 points."
    ),
}


def reject_rating_state_uncertainty_as_game_sd(candidate: float) -> None:
    """Refuse a rating-state uncertainty offered as ``game_sd_points``."""
    value = float(candidate)
    for forbidden, why in FORBIDDEN_AS_GAME_SD.items():
        if math.isclose(value, forbidden, rel_tol=0.0, abs_tol=1e-9):
            raise GovernanceBlock(
                f"{value} is refused as game_sd_points: {why} Game-level result "
                "dispersion is a separate parameter and is selected by the R1 "
                "sensitivity design."
            )


#: What was inspected when looking for an explicit *generator* game SD belonging
#: to the synthetic 2024/2025 prior-information provenance.
GAME_SD_GENERATOR_PROVENANCE_SEARCH = (
    {
        "location": (
            "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Sources / "
            "!Data Dictionary / !Ensemble Parameters"
        ),
        "finding": (
            "The synthetic 2024/2025 prior enters only as rating carry-forwards — "
            "TrueSkill mu2026 = 25 + 0.70*(mu2025 - 25), 2025 Baxter ridge ratings, "
            "Litkenhous offseason adjustment. Population statistics are rating SDs "
            "per family (TrueSkill 4.359, Litkenhous 9.540, Board I-H 0.143, Board "
            "J-B 0.128, Pure Baxter 15.071). None is a game-result dispersion."
        ),
    },
    {
        "location": (
            "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Sources rows 8-9 "
            "(Baxter carry-forward / Baxter_Ratings_v1_2025_Fit.xlsx)"
        ),
        "finding": (
            "The 2025 Baxter margin fit is the closest thing to a synthetic "
            "generating process, but only its derived rating columns are mounted. "
            "The fit artifact itself is not in this repository, so no residual "
            "dispersion is recoverable from bytes."
        ),
    },
    {
        "location": (
            "V2_1_STATIC_CONTROL_2026_CFB_10000_Season_Monte_Carlo.xlsx!Methodology"
        ),
        "finding": (
            "Game model: 'Margin = home unified neutral-field points - away points "
            "+ 4.0 home advantage + Normal(0,20.2)'. This is the V2.1 static "
            "control's own 2026 dispersion, carrying the superseded 4.0 HFA. It is "
            "a 2026 control parameter, not a 2024/2025 generator SD."
        ),
    },
    {
        "location": "Model_Parameters_v2_5_APPROVED.xlsx!CALIBRATION",
        "finding": (
            "Margin SD achieved 20.2 against a 16-18 harness band, from a Jul 13-14 "
            "cfb_sim.py engine run. Recorded 'Above band ... Re-verify against "
            "cfb_sim.py's current constants before accepting', and carried as OPEN "
            "item ENG-CAL-MARGIN. An open, out-of-band engine diagnostic."
        ),
    },
)

#: DERIVED — the search above found no explicit independent synthetic generator
#: game SD, so the ruling's own fallback branch applies.
GENERATOR_GAME_SD_POINTS = None
GAME_SD_SOURCE = "CHAIRMAN_FALLBACK_SENSITIVITY_GRID"

#: The Chairman-approved fallback sensitivity grid.
GAME_SD_FALLBACK_GRID = {"LOW": 16.0, "MIDDLE": 20.0, "HIGH": 24.0}

#: Multipliers applied to a generator SD *if one is ever mounted*. Recorded so
#: the generator branch is specified rather than merely mentioned.
GAME_SD_GENERATOR_MULTIPLIERS = {"LOW": 0.80, "MIDDLE": 1.00, "HIGH": 1.20}

#: Witnesses. Preserved as diagnostics; none of them is the selected value and
#: none of them is a generator SD.
GAME_SD_WITNESSES = (
    {
        "value": 20.2,
        "source": "V2_1_STATIC_CONTROL!Methodology game model / ENG-CAL-MARGIN",
        "class": "DIAGNOSTIC_WITNESS",
        "note": "2026 control dispersion; OPEN calibration item, above its own 16-18 band.",
    },
    {
        "value": None,
        "range": [16.0, 18.0],
        "source": "Model_Parameters_v2_5_APPROVED.xlsx!CALIBRATION Margin SD band",
        "class": "DIAGNOSTIC_WITNESS",
        "note": "Harness target band, not a governed V3 parameter.",
    },
    {
        "value": SIGMA_ELO_RATING_STATE_UNCERTAINTY,
        "source": "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER CCG-SIGMA_ELO",
        "class": "REFUSED_WRONG_AXIS",
        "note": "Rating-state uncertainty in the Elo namespace. Explicitly not game SD.",
    },
)

GAME_SD_SWEEP_DIAGNOSTICS = (
    "favorite_win_rates",
    "upset_rates",
    "tail_frequency",
    "undefeated_teams",
    "conference_title_concentration",
    "cfp_concentration",
    "national_title_concentration",
    "extreme_score_or_result_behavior",
    "probability_dispersion",
)


def game_sd_candidates(generator_game_sd_points: float | None = None) -> dict[str, float]:
    """LOW / MIDDLE / HIGH game-SD candidates.

    With a defensible generator SD, the grid is 0.80x / 1.00x / 1.20x of it. With
    none — the situation in this repository — the Chairman-approved fallback grid
    16.0 / 20.0 / 24.0 applies. A rating-state uncertainty offered here is refused
    rather than scaled.
    """
    if generator_game_sd_points is None:
        return dict(GAME_SD_FALLBACK_GRID)
    base = float(generator_game_sd_points)
    reject_rating_state_uncertainty_as_game_sd(base)
    if base <= 0.0:
        raise InputValidationError("generator_game_sd_points must be positive")
    return {slot: mult * base for slot, mult in GAME_SD_GENERATOR_MULTIPLIERS.items()}


def game_sd_axis_as_dict(generator_game_sd_points: float | None = None) -> dict[str, object]:
    candidates = game_sd_candidates(generator_game_sd_points)
    return {
        "parameter": "game_sd_points",
        "status_before_sweep": GAME_SD_STATUS_BEFORE_SWEEP,
        "status_after_sweep": GAME_SD_STATUS_AFTER_SWEEP,
        "generator_game_sd_points": generator_game_sd_points,
        "source": (
            "GENERATOR_SCALED_GRID"
            if generator_game_sd_points is not None
            else GAME_SD_SOURCE
        ),
        "generator_multipliers": dict(GAME_SD_GENERATOR_MULTIPLIERS),
        "fallback_grid": dict(GAME_SD_FALLBACK_GRID),
        "candidate_values": candidates,
        "generator_provenance_search": [dict(x) for x in GAME_SD_GENERATOR_PROVENANCE_SEARCH],
        "witnesses": [dict(w) for w in GAME_SD_WITNESSES],
        "refused_substitutions": {
            str(k): v for k, v in FORBIDDEN_AS_GAME_SD.items()
        },
        "diagnostics_required": list(GAME_SD_SWEEP_DIAGNOSTICS),
        "empirically_identified": False,
    }


# ---------------------------------------------------------------------------
# 7. Recent form — residual-driven, never win/loss
# ---------------------------------------------------------------------------

RECENT_FORM_EXISTS = True
RECENT_FORM_BASIS = "PERFORMANCE_RELATIVE_TO_EXPECTATION"
RECENT_FORM_STATUS_BEFORE_SWEEP = "DESIGN_TUNING_REQUIRED"
RECENT_FORM_STATUS_AFTER_SWEEP = "FIXED_BY_V3_RESPONSIVENESS_DESIGN"

#: The three Chairman-approved experimental decay rates. All three enter the
#: sweep; none of them is preferred here.
RECENT_FORM_LAMBDA_CANDIDATES = {"FAST": 0.60, "MEDIUM": 0.75, "SLOW": 0.90}

RECENT_FORM_DEFINITION = (
    "performance_residual = observed_update_margin - expected_margin, where "
    "observed_update_margin carries the approved +/-25 blowout/update cap; "
    "weight(k) = lambda ** k with k = 0 the most recent completed game."
)

#: Tokens that look like a performance signal and are not one. A result is not a
#: residual: a win over a much weaker opponent can carry a negative residual and
#: a narrow loss a positive one.
WIN_LOSS_TOKENS = ("W", "L", "T", "WIN", "LOSS", "TIE", "WON", "LOST")


def reject_win_loss_as_residual(value: object) -> float:
    """Refuse a raw result where a performance residual is required.

    Booleans are refused alongside the string tokens: ``True`` is a result, and
    Python would otherwise let it through as ``1.0``.
    """
    if isinstance(value, bool):
        raise GovernanceBlock(
            "A boolean win/loss cannot substitute for a performance residual. Recent "
            "form is defined from performance relative to expectation, not from the "
            "result. Supply observed_update_margin - expected_margin."
        )
    if isinstance(value, str):
        raise GovernanceBlock(
            f"Result token {value!r} cannot substitute for a performance residual. "
            "Recent form is defined from performance relative to expectation, not "
            "from wins and losses."
        )
    if isinstance(value, (int, float)):
        return float(value)
    raise InputValidationError(
        f"A performance residual must be a number; got {type(value).__name__}."
    )


def performance_residual(observed_update_margin: float, expected_margin: float) -> float:
    """``observed_update_margin - expected_margin``.

    The first argument is expected to be the *capped* update-driving margin. Pass
    a raw actual margin and the residual will overstate a blowout, which is the
    coupling the blowout ruling exists to remove.
    """
    observed = reject_win_loss_as_residual(observed_update_margin)
    expected = reject_win_loss_as_residual(expected_margin)
    return observed - expected


def residual_from_game(actual_margin: float, expected_margin: float) -> float:
    """Cap first, then difference. The governed order, in one call."""
    return performance_residual(update_driving_margin(actual_margin), expected_margin)


def recent_form_weight(k: int, lam: float) -> float:
    """``lambda ** k``; ``k = 0`` is the most recent completed game."""
    index = int(k)
    if index < 0:
        raise InputValidationError("recent-form index k must be >= 0")
    decay = float(lam)
    if not 0.0 < decay < 1.0:
        raise InputValidationError(
            f"recent-form lambda must lie strictly between 0 and 1; got {decay}"
        )
    return decay**index


def recent_form_signal(residuals: Sequence[float], lam: float) -> float:
    """Weighted mean of the residual history, most recent first.

    ``residuals[0]`` is the most recent completed game. Normalizing by the weight
    sum keeps the signal on the residual's own point scale, so a five-game and a
    twelve-game history of the same residual give the same pressure instead of
    the longer history simply accumulating more of it.
    """
    values = [reject_win_loss_as_residual(r) for r in residuals]
    if not values:
        return 0.0
    weights = [recent_form_weight(k, lam) for k in range(len(values))]
    total = sum(weights)
    return sum(w * v for w, v in zip(weights, values)) / total


#: Recent form is a *separate* pressure term. If the evolved core state already
#: carries the same residual contribution, applying both counts it twice.
DOUBLE_COUNTING_TEST_REQUIRED = True
DOUBLE_COUNTING_TEST = (
    "Hold the residual history fixed and vary only whether the recent-form term "
    "is applied. If the evolved in-season state already contains that residual "
    "contribution, the difference is double counting and the sweep cell is "
    "refused rather than scored."
)


def recent_form_axis_as_dict() -> dict[str, object]:
    return {
        "parameter": "recent_form_lambda",
        "exists_in_v3": RECENT_FORM_EXISTS,
        "basis": RECENT_FORM_BASIS,
        "definition": RECENT_FORM_DEFINITION,
        "status_before_sweep": RECENT_FORM_STATUS_BEFORE_SWEEP,
        "status_after_sweep": RECENT_FORM_STATUS_AFTER_SWEEP,
        "candidate_values": dict(RECENT_FORM_LAMBDA_CANDIDATES),
        "win_loss_substitution_permitted": False,
        "intended_behavior": [
            "Sustained positive performance residuals produce persistent positive "
            "recent-form pressure.",
            "Sustained negative performance residuals produce persistent negative "
            "recent-form pressure.",
            "A win over a much weaker opponent does not automatically create a "
            "strongly positive recent-form signal.",
            "A narrow loss while massively outperforming expectation does not "
            "automatically create a strongly negative signal.",
        ],
        "double_counting_test_required": DOUBLE_COUNTING_TEST_REQUIRED,
        "double_counting_test": DOUBLE_COUNTING_TEST,
        "empirically_identified": False,
    }


# ---------------------------------------------------------------------------
# 8. Preseason prior decay
# ---------------------------------------------------------------------------

#: Weeks completed -> preseason-prior weight. Key 0 is the opening state.
MDR1_PRESEASON_PRIOR_DECAY = {
    0: 1.00,
    1: 0.80,
    2: 0.60,
    3: 0.50,
    4: 0.40,
    5: 0.30,
    6: 0.20,
    7: 0.15,
}

#: The prior never reaches zero during the 2026 season.
PRESEASON_PRIOR_FLOOR = 0.15
PRESEASON_PRIOR_DECAY_STATUS = "FIXED_V3_POLICY"

#: The currently mounted configuration still carries the earlier placeholder
#: schedule, which decays to 0.00 after Week 5. This lane records authority and
#: promotes nothing, so the configuration is left exactly as audited; the delta
#: below is what a later promotion lane has to change.
CONFIG_ALIGNMENT_REQUIRED = (
    {
        "target": "config/dynamic_weekly_mc_v3/v3_experimental.json prior_decay",
        "current": {"0": 1.0, "1": 0.8, "2": 0.6, "3": 0.4, "4": 0.2, "5": 0.0},
        "ruled": {str(k): v for k, v in MDR1_PRESEASON_PRIOR_DECAY.items()},
        "reason": (
            "The mounted schedule decays the preseason prior to 0.00 after Week 5. "
            "Ruling MDR1-PRESEASON-DECAY sets 0.50/0.40/0.30/0.20 for weeks 3-6 and "
            "a 0.15 floor from Week 7 onward, and states the prior never reaches "
            "zero during the 2026 season."
        ),
        "promoted_by_this_lane": False,
    },
    {
        "target": (
            "src/ncaaf_engine/simulation/dynamic_weekly_mc_v3/config.py "
            "DEFAULT_PRIOR_DECAY and V3Config.prior_weight_after_week"
        ),
        "current": "Mirrors the mounted placeholder schedule; returns 0.0 for week > 5.",
        "ruled": (
            "Must mirror MDR1_PRESEASON_PRIOR_DECAY and return the 0.15 floor for "
            "week >= 7."
        ),
        "reason": "Runtime must not disagree with the ruled schedule once promoted.",
        "promoted_by_this_lane": False,
    },
)


def preseason_prior_weight(weeks_completed: int) -> float:
    """Preseason-prior weight after ``weeks_completed`` weeks of realized results."""
    week = int(weeks_completed)
    if week < 0:
        raise InputValidationError("weeks_completed must be >= 0")
    if week >= 7:
        return PRESEASON_PRIOR_FLOOR
    return MDR1_PRESEASON_PRIOR_DECAY[week]


def evolved_state_weight(weeks_completed: int) -> float:
    """The complementary share supplied by the evolved in-season state."""
    return 1.0 - preseason_prior_weight(weeks_completed)


# ---------------------------------------------------------------------------
# 9. First full dynamic rerating
# ---------------------------------------------------------------------------

FIRST_PROMOTED_RERATING_AFTER_WEEK = 2
SWEEP_ORIGIN_STATE = "FROZEN_POST_WEEK_2_STATE"

FIRST_RERATING_DESIGN = (
    "W1 and W2 begin from the preseason/opening state. After W1 an 80% preseason "
    "prior exists for audit/state tracking; after W2, 60%. The first fully "
    "promoted V3 rerating becomes effective after Week 2, and the design sweep "
    "runs from that frozen post-Week-2 state."
)


# ---------------------------------------------------------------------------
# 10. The 500-path design matrix
# ---------------------------------------------------------------------------

DESIGN_PATHS_PER_CELL = 500
DESIGN_RANDOM_NUMBER_POLICY = "COMMON_RANDOM_NUMBERS_IDENTICAL_SEED_SCHEDULE"
DESIGN_WORKLOAD_CLASS = "EXPERIMENT_WORKLOAD_NOT_A_PRODUCTION_SEASON_RUN"

#: A cell may not read another cell's simulated outcomes, and no cell may write
#: back into the frozen state it started from.
DESIGN_CELL_ISOLATION = (
    "Every cell consumes the same frozen post-Week-2 state and the same common "
    "seed schedule. Simulated outcomes from one candidate cell never feed another "
    "candidate cell and never feed the frozen rating state."
)


def design_matrix_cells(
    *,
    coefficient_universe: Sequence[float] | None = None,
    generator_game_sd_points: float | None = None,
) -> int:
    """Total simulated paths across the design experiment.

    ``3 x 3 x 3 x 500 = 13500`` under the reserved slot counts. The count is
    derived from the axis sizes rather than written down, so a later change to
    an axis cannot leave a stale total behind.
    """
    n_coef = len(COEFFICIENT_CANDIDATE_SLOTS) if coefficient_universe is None else 3
    n_sd = len(game_sd_candidates(generator_game_sd_points))
    n_lambda = len(RECENT_FORM_LAMBDA_CANDIDATES)
    return n_coef * n_sd * n_lambda * DESIGN_PATHS_PER_CELL


def design_matrix_as_dict(
    *,
    coefficient_universe: Sequence[float] | None = None,
    generator_game_sd_points: float | None = None,
) -> dict[str, object]:
    coef = coefficient_axis_as_dict(coefficient_universe)
    sd = game_sd_axis_as_dict(generator_game_sd_points)
    form = recent_form_axis_as_dict()
    return {
        "origin_state": SWEEP_ORIGIN_STATE,
        "first_promoted_rerating_after_week": FIRST_PROMOTED_RERATING_AFTER_WEEK,
        "paths_per_cell": DESIGN_PATHS_PER_CELL,
        "random_number_policy": DESIGN_RANDOM_NUMBER_POLICY,
        "cell_isolation": DESIGN_CELL_ISOLATION,
        "workload_class": DESIGN_WORKLOAD_CLASS,
        "axes": {
            "coefficient": coef,
            "game_sd_points": sd,
            "recent_form_lambda": form,
        },
        "axis_sizes": {
            "coefficient": len(COEFFICIENT_CANDIDATE_SLOTS),
            "game_sd_points": len(sd["candidate_values"]),
            "recent_form_lambda": len(RECENT_FORM_LAMBDA_CANDIDATES),
        },
        "cells": (
            len(COEFFICIENT_CANDIDATE_SLOTS)
            * len(sd["candidate_values"])
            * len(RECENT_FORM_LAMBDA_CANDIDATES)
        ),
        "total_simulated_paths": design_matrix_cells(
            coefficient_universe=coefficient_universe,
            generator_game_sd_points=generator_game_sd_points,
        ),
        "executable_now": False,
        "not_executable_because": [
            COEFFICIENT_UNIVERSE_MISSING,
            "This lane records authority and specifications only; it runs no sweep.",
        ],
    }


# ---------------------------------------------------------------------------
# 11. Monte Carlo feedback firewall
# ---------------------------------------------------------------------------

MC_FEEDBACK_FIREWALL = "SIMULATED_MC_OUTCOMES_NEVER_UPDATE_THE_GOVERNED_WEEKLY_RATING_STATE"

REALIZED_RESULT = "REALIZED_SYNTHETIC_WEEKLY_RESULT"
SIMULATED_RESULT = "SIMULATED_MC_OUTCOME"


@dataclass(frozen=True)
class FrozenWeeklyState:
    """A governed weekly rating state, frozen after its one realized update.

    Frozen in the dataclass sense as well as the governance sense: the MC reads
    it and cannot write to it, so a feedback loop has no path to form.
    """

    week: int
    strength_points: Mapping[str, float]

    def __post_init__(self) -> None:
        # Copy on the way in. Without this the caller keeps a live handle on the
        # mapping and could edit a frozen state through the back door, which is
        # the same outcome the firewall exists to prevent.
        object.__setattr__(self, "strength_points", dict(self.strength_points))

    def advanced_by(
        self, *, week: int, strength_points: Mapping[str, float], origin: str
    ) -> "FrozenWeeklyState":
        """Produce the next frozen state from realized results only."""
        require_realized_origin(origin)
        return FrozenWeeklyState(week=int(week), strength_points=dict(strength_points))


def require_realized_origin(origin: str) -> str:
    """Fail closed unless the update is driven by realized synthetic results."""
    if origin == REALIZED_RESULT:
        return origin
    raise GovernanceBlock(
        f"{MC_FEEDBACK_FIREWALL}. Refused a weekly rating-state update whose origin is "
        f"{origin!r}. Only {REALIZED_RESULT} may update the governed team-strength "
        "state; the Monte Carlo forecasts forward from a frozen weekly state and "
        "writes nothing back."
    )


def reject_simulated_state_update(origin: str = SIMULATED_RESULT) -> None:
    """Explicit refusal helper for callers that already know the origin is simulated."""
    require_realized_origin(origin)


# ---------------------------------------------------------------------------
# 12-13. FCS entity policy and FCS home-field advantage
# ---------------------------------------------------------------------------

FCS_ELO = 1250.0
FCS_ENTITY_CLASS = "SCHEDULE_ONLY_FCS"
FCS_BASELINE_POLICY = "ONE_COMMON_V3_FCS_BASELINE_FOR_SCHEDULE_SIMULATION"

#: Routes to an FCS point value that are refused as a matter of method.
FCS_PROHIBITED_ROUTES = {
    "ELO_1250_AS_POINTS": "Elo and V3 neutral points are different axes; 1250 is not 1250 points.",
    "BOARD_IH_INVERSE": "The Board I-H inverse mapping is closed and is not resurrected.",
    "BOARD_EQUIVALENT_0P294_0P297": "The old .294/.297 equivalents are not V3 point values.",
    "INDIVIDUAL_FCS_RATINGS": "No unsupported per-entity FCS rating is created.",
}

#: Forbidden equivalents, kept as literals so they can be refused by name.
FCS_FORBIDDEN_BOARD_EQUIVALENTS = (0.294, 0.297, 0.297514)

GLOBAL_HOME_FIELD_ADVANTAGE_POINTS = 3.5
NEUTRAL_VENUE_ADJUSTMENT_POINTS = 0.0
FCS_HFA_STATUS = "FIXED_V3_GLOBAL_POLICY"
FCS_TEAM_SPECIFIC_HFA_PERMITTED = False


def venue_adjustment_points(*, neutral: bool) -> float:
    """The venue adjustment for any governed game, FCS home side included.

    There is one home-field advantage in V3 points and it does not vary by
    opponent class. This function takes no team argument on purpose: a signature
    that accepted one would invite a per-team FCS modifier to be threaded in.
    """
    return NEUTRAL_VENUE_ADJUSTMENT_POINTS if neutral else GLOBAL_HOME_FIELD_ADVANTAGE_POINTS


def reject_fcs_specific_hfa(modifier: float | None) -> None:
    """Refuse any team-specific FCS home-field modifier, including a plausible one."""
    if modifier is None:
        return
    raise GovernanceBlock(
        f"An FCS-specific home-field modifier ({modifier}) is refused. "
        f"GLOBAL_HOME_FIELD_ADVANTAGE_POINTS = {GLOBAL_HOME_FIELD_ADVANTAGE_POINTS} "
        "applies to every non-neutral governed game and 0.0 to every neutral game; "
        "no team-specific FCS modifier is inferred or manufactured."
    )


def reject_elo_as_v3_points(candidate: float) -> None:
    """Refuse Elo 1250 — or a Board equivalent — offered as a V3 point value."""
    value = float(candidate)
    if math.isclose(value, FCS_ELO, rel_tol=0.0, abs_tol=1e-9):
        raise GovernanceBlock(
            f"Elo {FCS_ELO} cannot be used directly as V3 football points. "
            "FCS_PROHIBITED_ROUTES['ELO_1250_AS_POINTS']: "
            + FCS_PROHIBITED_ROUTES["ELO_1250_AS_POINTS"]
        )
    for forbidden in FCS_FORBIDDEN_BOARD_EQUIVALENTS:
        if math.isclose(value, forbidden, rel_tol=0.0, abs_tol=1e-6):
            raise GovernanceBlock(
                f"{value} is a Board I-H equivalent. "
                + FCS_PROHIBITED_ROUTES["BOARD_EQUIVALENT_0P294_0P297"]
            )


def reject_board_inverse_route(route: str = "BOARD_IH_INVERSE") -> None:
    """Refuse the Board I-H inverse route by name, whatever number it would yield."""
    raise GovernanceBlock(
        f"Route {route!r} is refused: "
        + FCS_PROHIBITED_ROUTES["BOARD_IH_INVERSE"]
        + " The approved V3 adapter standardizes Elo 1250 against the governed 2026 "
        "FBS Elo population and multiplies by the 14.0 point scale."
    )


# ---------------------------------------------------------------------------
# 14. FCS Elo -> V3 point adapter
# ---------------------------------------------------------------------------

FCS_ADAPTER_METHOD = "FCS_ELO_Z_TIMES_V3_POINT_SCALE"
FCS_ADAPTER_FORMULA = (
    "FCS_ELO_Z = (1250 - mean(FBS_2026_ELO)) / sd(FBS_2026_ELO); "
    "FCS_V3_NEUTRAL_POINTS = 14.0 * FCS_ELO_Z"
)
FCS_ADAPTER_AUTHORITY = "DIRECT_CHAIRMAN_AUTHORITY"

#: The refusal token returned when the adapter's one input is not available.
FCS_ADAPTER_INPUT_MISSING = "FCS_ADAPTER_INPUT_ELO_VECTOR_MISSING"

#: SD conventions the adapter will accept. Neither is defaulted: the convention
#: has to be stated because it must match the governed 2026 Elo population
#: definition, and that definition is exactly what is missing.
SD_CONVENTIONS = ("POPULATION_SD_DDOF0", "SAMPLE_SD_DDOF1")

#: Sources the 2026 FBS Elo population may never be taken from.
FORBIDDEN_ELO_POPULATION_SOURCES = {
    "BOARD_IH_PARTIAL_AXIS_INVERSION": (
        "Board I-H supplies 0.125 of Unified Master Z and is superseded as Board of "
        "Record by Board I-K; inverting its axis manufactures a population."
    ),
    "HISTORICAL_2025_ELO": (
        "2025_Preseason_Elo_CARRY_v1.xlsx is recorded REFERENCE (UNRATIFIED), "
        "'REJECT FOR CURRENT USE', with R-ELO-01/H1 blocking automatic adoption."
    ),
    "REAL_WORLD_NCAA_DATA": (
        "Real football is EXTERNAL_WITNESS_ONLY and never enters the synthetic fit."
    ),
    "FABRICATED_ELO_BRIDGE": "An invented Elo bridge is not an authority.",
    "PYTEST_FIXTURE": "A value chosen because a test turns green is not evidence.",
}


def reject_forbidden_elo_population_source(source: str) -> str:
    """Refuse a 2026 FBS Elo population drawn from a closed route."""
    key = str(source).strip().upper()
    if key in FORBIDDEN_ELO_POPULATION_SOURCES:
        raise GovernanceBlock(
            f"The 2026 FBS Elo population may not be obtained from {key}: "
            + FORBIDDEN_ELO_POPULATION_SOURCES[key]
        )
    return source


#: Where the authoritative current 2026 FBS Elo vector was looked for, and what
#: each candidate actually is. Recorded so a reader can see the search was
#: exhaustive rather than abandoned.
FBS_ELO_VECTOR_SEARCH = (
    {
        "location": "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Master Ratings",
        "columns_present": 78,
        "finding": (
            "The current V3 model state's rating source. Carries TrueSkill, "
            "Litkenhous, Board I-H, Board J-B, Baxter, Billingsley, Markov, Unified "
            "Master Z and Unified Neutral-Field Points for 121 FBS teams. It carries "
            "no Elo column at all."
        ),
        "usable": False,
    },
    {
        "location": (
            "POWER_CRUNCH_2026_Team_Reconciled_Master_134_v2_2.xlsx!Reconciled Master"
            ".scheme_master_primary_elo"
        ),
        "finding": (
            "The only per-team Elo-shaped column in the mounted corpus. Its own Build "
            "Manifest states primary_elo = 999.986237 * board_power_H + 1099.999878, "
            "so it is the Board I-H axis re-expressed — the closed route. It also "
            "carries rating_source/rating_authority BOARD_I-H, spans 134 entities "
            "rather than the governed 121, and the same workbook records "
            "model_use_authorized = FALSE."
        ),
        "usable": False,
        "refused_as": "BOARD_IH_PARTIAL_AXIS_INVERSION",
    },
    {
        "location": (
            "Model_Parameters_v2_5_APPROVED.xlsx!20_CANON_MANIFEST_INGEST "
            "2025_Preseason_Elo_CARRY_v1.xlsx"
        ),
        "finding": (
            "REFERENCE (UNRATIFIED), disposition 'REJECT FOR CURRENT USE / RETAIN "
            "UNRATIFIED', 'No current forward-prior authority'. Historical 2025 and "
            "not mounted in this repository in any case."
        ),
        "usable": False,
        "refused_as": "HISTORICAL_2025_ELO",
    },
    {
        "location": (
            "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER "
            "CCG-HFA_ELO 65 / CCG-SIGMA_ELO 68 / CCG-R_REF 1893.3"
        ),
        "finding": (
            "Elo-layer scalars that operate inside the Elo domain. Parameters, not a "
            "team-level population, and they convert nothing."
        ),
        "usable": False,
    },
    {
        "location": "config/dynamic_weekly_mc_v3/governed/",
        "finding": "Contains the AAC divisions CSV and its provenance. No Elo vector.",
        "usable": False,
    },
)

#: DERIVED — the search above returns nothing admissible.
FBS_ELO_VECTOR_SOURCE = None
FBS_ELO_VECTOR_PRESENT = False
FCS_ADAPTER_STATUS = FCS_ADAPTER_INPUT_MISSING
FCS_ADAPTER_MISSING_DEPENDENCY = (
    "An authoritative, current 2026 FBS Elo vector over the governed 121-team FBS "
    "population, issued by a governed register, together with an explicit "
    "population-SD convention for that population. The mounted V3 rating axis is "
    "Unified Master Z / Unified Neutral-Field Points and contains no Elo column; the "
    "only per-team Elo in the corpus is the Board I-H forward transform in "
    "POWER_CRUNCH (model_use_authorized = FALSE), which the ruling closes."
)


@dataclass(frozen=True)
class FcsAdapterResult:
    """A computed adapter candidate. Frozen, and never auto-promoted."""

    fbs_elo_count: int
    fbs_elo_mean: float
    fbs_elo_sd: float
    fcs_elo: float
    fcs_elo_z: float
    fcs_v3_points: float
    sd_convention: str
    source: str
    point_scale: float = V3_POINT_SCALE
    status: str = "ADAPTER_CANDIDATE_FROZEN"

    def as_dict(self) -> dict[str, object]:
        return {
            "fbs_elo_count": self.fbs_elo_count,
            "fbs_elo_mean": self.fbs_elo_mean,
            "fbs_elo_sd": self.fbs_elo_sd,
            "fcs_elo": self.fcs_elo,
            "fcs_elo_z": self.fcs_elo_z,
            "fcs_v3_points": self.fcs_v3_points,
            "sd_convention": self.sd_convention,
            "source": self.source,
            "point_scale": self.point_scale,
            "status": self.status,
        }


def locate_governed_2026_fbs_elo_vector() -> Sequence[float] | None:
    """The authoritative 2026 FBS Elo vector, or ``None``.

    Always ``None`` here, and deliberately so: there is no admissible vector in
    the mounted corpus. This function exists as the single place a later lane
    mounts one, so the adapter never grows an inline fallback.
    """
    return None


def compute_fcs_adapter(
    elo_vector: Sequence[float] | None = None,
    *,
    sd_convention: str | None = None,
    source: str | None = None,
    fcs_elo: float = FCS_ELO,
) -> FcsAdapterResult:
    """Apply the approved adapter formula, or fail cleanly naming the dependency.

    Nothing here substitutes for a missing vector. A one-team or zero-variance
    population is refused too: standardizing against it would emit a number with
    no meaning rather than an error a reviewer can act on.
    """
    if elo_vector is None:
        elo_vector = locate_governed_2026_fbs_elo_vector()
    if elo_vector is None:
        raise GovernanceBlock(
            f"{FCS_ADAPTER_INPUT_MISSING}: {FCS_ADAPTER_MISSING_DEPENDENCY}"
        )
    if source is None:
        raise GovernanceBlock(
            f"{FCS_ADAPTER_INPUT_MISSING}: an Elo vector was supplied without naming "
            "its source. The governed 2026 Elo population must be identified before "
            "it can be standardized against."
        )
    reject_forbidden_elo_population_source(source)
    if sd_convention not in SD_CONVENTIONS:
        raise GovernanceBlock(
            "The population SD convention must be stated explicitly and must match "
            "the governed 2026 Elo population definition. Expected one of "
            f"{SD_CONVENTIONS}; got {sd_convention!r}."
        )

    values = [float(v) for v in elo_vector]
    n = len(values)
    if n < 2:
        raise InputValidationError(
            f"An Elo population of {n} value(s) cannot supply a standard deviation."
        )
    mean = sum(values) / n
    ddof = 0 if sd_convention == "POPULATION_SD_DDOF0" else 1
    variance = sum((v - mean) ** 2 for v in values) / (n - ddof)
    sd = math.sqrt(variance)
    if sd == 0.0:
        raise InputValidationError(
            "The Elo population has zero dispersion; a Z-score is undefined."
        )
    z = (float(fcs_elo) - mean) / sd
    return FcsAdapterResult(
        fbs_elo_count=n,
        fbs_elo_mean=mean,
        fbs_elo_sd=sd,
        fcs_elo=float(fcs_elo),
        fcs_elo_z=z,
        fcs_v3_points=V3_POINT_SCALE * z,
        sd_convention=sd_convention,
        source=source,
    )


def fcs_adapter_as_dict() -> dict[str, object]:
    return {
        "method": FCS_ADAPTER_METHOD,
        "formula": FCS_ADAPTER_FORMULA,
        "authority": FCS_ADAPTER_AUTHORITY,
        "point_scale": V3_POINT_SCALE,
        "fcs_elo": FCS_ELO,
        "fbs_elo_vector_source": FBS_ELO_VECTOR_SOURCE,
        "fbs_elo_vector_present": FBS_ELO_VECTOR_PRESENT,
        "fbs_elo_count": None,
        "fbs_elo_mean": None,
        "fbs_elo_sd": None,
        "fcs_elo_z": None,
        "fcs_v3_points": None,
        "sd_convention": None,
        "sd_convention_note": (
            "Unresolved. The convention must match the governed 2026 Elo population "
            "definition, and that definition is the missing dependency."
        ),
        "permitted_sd_conventions": list(SD_CONVENTIONS),
        "status": FCS_ADAPTER_STATUS,
        "missing_dependency": FCS_ADAPTER_MISSING_DEPENDENCY,
        "search": [dict(x) for x in FBS_ELO_VECTOR_SEARCH],
        "forbidden_population_sources": dict(FORBIDDEN_ELO_POPULATION_SOURCES),
        "blocks_other_rulings": False,
    }


# ---------------------------------------------------------------------------
# 15. FCS weekly result treatment
# ---------------------------------------------------------------------------

FCS_BASELINE_EVOLVES = False
FCS_GAME_IS_A_GOVERNED_OBSERVATION_FOR_THE_FBS_TEAM = True

FCS_WEEKLY_RESULT_TREATMENT = (
    "The FCS baseline itself stays fixed unless later governance changes it. An FBS "
    "team's realized game against an FCS opponent IS a legitimate synthetic-2026 "
    "observation for that FBS team's next weekly update: expected FBS margin vs "
    "realized FBS-perspective margin -> performance residual -> normal governed FBS "
    "update, subject to the +/-25 update-driving margin cap. The schedule-only FCS "
    "entity does not become a full evolving FBS rating-state member."
)


# ---------------------------------------------------------------------------
# 16. Sample-size regularization — authority stays external
# ---------------------------------------------------------------------------

SAMPLE_SIZE_REGULARIZATION_AUTHORITY = "AGENT_3_SYNTHETIC_DOMAIN_EXPERIMENT"
SAMPLE_SIZE_REGULARIZATION_DECIDED_HERE = False
SAMPLE_SIZE_REGULARIZATION_RESULT_CLASS_IF_IDENTIFIED = "SYNTHETIC_FIT_RESULT"
SAMPLE_SIZE_REGULARIZATION_RESULT_CLASS_IF_UNSTABLE = "BOUNDARY_OR_UNIDENTIFIED"


def assert_sample_size_regularization_not_decided_here() -> None:
    """This ruling round decides nothing about sample-size regularization."""
    if SAMPLE_SIZE_REGULARIZATION_DECIDED_HERE:
        raise GovernanceBlock(
            "sample_size_regularization is Agent 3's synthetic-domain experiment. "
            "The R1 model-design rulings neither decide it nor overwrite its result."
        )


def classify_sample_size_regularization_result(identified: bool) -> str:
    """Preserve Agent 3's outcome as-is, including a boundary/unidentified one."""
    return (
        SAMPLE_SIZE_REGULARIZATION_RESULT_CLASS_IF_IDENTIFIED
        if identified
        else SAMPLE_SIZE_REGULARIZATION_RESULT_CLASS_IF_UNSTABLE
    )


# ---------------------------------------------------------------------------
# 18. Weekly operating loop
# ---------------------------------------------------------------------------

WEEKLY_LOOP_BOOTSTRAP = (
    "PRESEASON_STATE",
    "W1_REALIZED_RESULTS",
    "UPDATE_STATE_PRIOR_80_PCT",
    "W2_REALIZED_RESULTS",
    "UPDATE_STATE_PRIOR_60_PCT",
    "FREEZE_POST_W2_STATE",
    "RUN_500_PATH_DESIGN_SWEEP",
    "SELECT_AND_BIND_COEFFICIENT_GAME_SD_RECENT_FORM_LAMBDA",
    "FREEZE_V3_DYNAMIC_PARAMETER_PACKAGE",
    "RUN_REMAINING_SEASON_MC",
)

WEEKLY_LOOP_STEADY_STATE = (
    "INGEST_REALIZED_WEEK_N_RESULTS",
    "VERIFY_COMPLETENESS_AND_IDENTITIES",
    "COMPUTE_CAPPED_UPDATE_MARGINS",
    "COMPUTE_PERFORMANCE_RESIDUALS",
    "UPDATE_EVOLVED_STRENGTH_STATE",
    "UPDATE_RECENT_FORM_HISTORY",
    "APPLY_PRIOR_DECAY_POLICY",
    "EMIT_LARGE_WEEKLY_RANK_MOVE_ADVISORIES",
    "FREEZE_WEEK_N_STATE",
    "RUN_GOVERNED_REMAINING_SEASON_MONTE_CARLO",
    "VALIDATE",
    "FREEZE_WEEKLY_REPORT",
    "AWAIT_NEXT_REALIZED_RESULTS",
)

WEEKLY_LOOP_STEADY_STATE_FIRST_WEEK = 3


# ---------------------------------------------------------------------------
# 21. Prohibited interpretations
# ---------------------------------------------------------------------------

PROHIBITED_INTERPRETATIONS = (
    "Reading point scale 14.0 as an independently estimated quantity. It is an "
    "explicit synthetic V3 model convention.",
    "Reading the 10-slot weekly ranking rule as a state or rating cap. It is an "
    "advisory; ratings are never reordered or truncated to satisfy it.",
    "Continuing to fit alternative blowout caps as though 25.0 were unresolved.",
    "Letting an earlier Agent-3 experimental blowout optimum overwrite the later "
    "direct Chairman +/-25 ruling.",
    "Substituting sigma_elo = 68, or any other rating-state uncertainty, for "
    "game_sd_points.",
    "Defining recent form from wins and losses instead of from performance "
    "relative to expectation.",
    "Applying a recent-form term on top of an evolved state that already carries "
    "the same residual contribution, without testing for double counting.",
    "Letting the preseason prior decay to zero during the 2026 season.",
    "Feeding simulated Monte Carlo outcomes back into the governed weekly rating "
    "state, or across candidate cells of the design sweep.",
    "Using FCS Elo 1250 directly as V3 football points.",
    "Resurrecting the Board I-H inverse mapping or the .294 / .297 equivalents.",
    "Creating individual unsupported FCS ratings, or a team-specific FCS "
    "home-field modifier.",
    "Obtaining the 2026 FBS Elo population from Board I-H inversion, historical "
    "2025 Elo, real-world NCAA data, a fabricated bridge, or a pytest fixture.",
    "Inventing a 2026 FBS Elo vector so the adapter calculation can complete.",
    "Inventing a coefficient search universe when no governed one exists.",
    "Overwriting or pre-empting Agent 3's sample-size regularization result.",
    "Promoting the coefficient, game SD or recent-form lambda before the sweep "
    "has run and been reviewed.",
    "Marking any of these parameters EMPIRICALLY_IDENTIFIED.",
    "Using real 2021-2024 football to override a synthetic V3 design ruling.",
    "Rewriting or editing preserved historical evidence.",
)


# ---------------------------------------------------------------------------
# The rulings themselves
# ---------------------------------------------------------------------------

def _ruling(
    convergence_id: str,
    subject: str,
    decision: str,
    *,
    evidence: tuple[str, ...] = (),
    supersedes: tuple[str, ...] = (),
    provenance: str = "FACT",
) -> ChairmanRuling:
    return ChairmanRuling(
        convergence_id=convergence_id,
        subject=subject,
        decision=decision,
        evidence=evidence,
        retires=(),
        supersedes=supersedes,
        provenance=provenance,  # type: ignore[arg-type]
        chairman_ruling_id=None,
        instruction=MDR1_INSTRUCTION,
        resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
    )


MDR1_DOMAIN = _ruling(
    "MDR1-DOMAIN",
    "Governing domain of the production model",
    "The production model runs SYNTHETIC 2024/2025 prior information into SYNTHETIC "
    "2026. Real historical football remains EXTERNAL_WITNESS_ONLY: it may be cited "
    "as a witness and must never be mixed into the primary synthetic model fit or "
    "used to override a synthetic V3 design ruling.",
    evidence=(
        "MDR1 instruction section 1: 'Production model: SYNTHETIC 2024 / 2025 PRIOR "
        "INFORMATION -> SYNTHETIC 2026. Real historical football remains "
        "EXTERNAL_WITNESS_ONLY.'",
    ),
)

MDR1_BLOWOUT = _ruling(
    "MDR1-BLOWOUT-CAP-25",
    "Blowout treatment",
    "BLOWOUT_TREATMENT = CAP_UPDATE_DRIVING_MARGIN with "
    "BLOWOUT_MARGIN_CAP_POINTS = 25.0. The actual final score and the actual game "
    "margin are unchanged; only the margin entering the dynamic performance/update "
    "calculation is clipped: update_margin = sign(actual) * min(|actual|, 25.0). "
    "FIXED_V3_POLICY. Alternative caps are not fitted as though the value were "
    "still open, and an experimental blowout optimum is preserved as a diagnostic "
    "witness rather than allowed to override this ruling.",
    evidence=(
        "MDR1 instruction section 2, worked examples: +42 -> +25, -38 -> -25, "
        "+13 -> +13.",
        "MDR1 instruction section 17: experimental blowout result = "
        "diagnostic/witness; the Chairman +/-25 ruling is production V3 design "
        "authority.",
    ),
    supersedes=(
        "Any treatment of calibration.blowout_treatment as an open fitting question "
        "for the purpose of V3 production design. The blocker itself is untouched by "
        "this lane and the configuration value stays null.",
    ),
)

MDR1_POINT_SCALE = _ruling(
    "MDR1-POINT-SCALE-14",
    "V3 neutral-field point scale",
    "point_scale = 14.0, defining V3_NEUTRAL_FIELD_POINTS = 14.0 * "
    "Unified_Master_Z. Status FIXED_V3_SYNTHETIC_SCALE; identification "
    "NOT_EMPIRICALLY_IDENTIFIED. It is an explicit synthetic V3 model convention "
    "and must not be described as independently estimated from historical or "
    "synthetic outcomes.",
    evidence=(
        "MDR1 instruction section 3.",
        "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Ensemble Parameters: "
        "'Neutral-field point scale | 14 | Initial points per standard deviation; "
        "recalibrate against game margins' — the mounted artifact records the same "
        "number and describes it as provisional, which is consistent with a "
        "convention and inconsistent with an estimate.",
    ),
)

MDR1_RANK_ADVISORY = _ruling(
    "MDR1-RANK-ADVISORY-10",
    "Weekly ranking movement advisory",
    "WEEKLY_RANK_MOVEMENT_ADVISORY_SLOTS = 10, status ADVISORY_ONLY. This is not a "
    "state or rating cap: a team may legitimately move more than ten ranking "
    "positions if its underlying rating state warrants it. Whenever absolute rank "
    "movement between consecutive weekly frozen states exceeds ten slots, emit "
    "LARGE_WEEKLY_RANK_MOVE recording team, prior rank, new rank, slot change, "
    "underlying point change, performance residual and cap-hit status. Ratings are "
    "never reordered or truncated merely to satisfy the advisory.",
    evidence=("MDR1 instruction section 4.",),
)

MDR1_COEFFICIENT = _ruling(
    "MDR1-COEFFICIENT-SWEEP",
    "Weekly performance residual coefficient",
    "The coefficient is NOT declared empirically identified. Status before the "
    "sweep is DESIGN_TUNING_REQUIRED; the selection method is a "
    "500_PATH_RESPONSIVENESS_SWEEP against MODEL RESPONSIVENESS, using common "
    "random numbers across candidates, run from the frozen post-Week-2 state. The "
    "eventual selected status is FIXED_BY_V3_RESPONSIVENESS_DESIGN, never "
    "EMPIRICALLY_IDENTIFIED. The sweep must expose at minimum the fourteen declared "
    "diagnostics. The preferred reading — the lowest coefficient producing "
    "meaningful weekly responsiveness without pathological oscillation or "
    "instability — is recorded as prose and is not converted into a numeric "
    "threshold in this lane.",
    evidence=(
        "MDR1 instruction section 5.",
        "config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json carries "
        "regimes: [] and states the emptiness is deliberate, so no governed or "
        "predeclared coefficient universe exists to reuse; three candidate slots are "
        "reserved and no values are bound.",
    ),
    provenance="FACT",
)

MDR1_GAME_SD = _ruling(
    "MDR1-GAME-SD-SWEEP",
    "Game-level result dispersion (game_sd_points)",
    "game_sd_points is a game-level result dispersion and is separate from "
    "rating-state uncertainty: sigma_elo = 68 and any comparable rating-state "
    "number is refused as a substitute. The synthetic 2024/2025 generating "
    "provenance carries no explicit independent generator game SD, so the "
    "Chairman-approved fallback sensitivity grid applies: LOW 16.0 / MIDDLE 20.0 / "
    "HIGH 24.0, run under identical common seeds inside the 500-path experiment. "
    "Status before the sweep is DESIGN_TUNING_REQUIRED; the eventual selected "
    "status is FIXED_BY_V3_SENSITIVITY_DESIGN, never EMPIRICALLY_IDENTIFIED.",
    evidence=(
        "MDR1 instruction section 6.",
        "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER CCG-SIGMA_ELO = 68, "
        "parameter_name sigma_elo, note 'Rating uncertainty per iteration'.",
        "Generator search: the synthetic 2024/2025 prior enters only as rating "
        "carry-forwards; the 2025 Baxter margin-fit artifact is not mounted; the 20.2 "
        "in V2_1_STATIC_CONTROL!Methodology is the 2026 control's own dispersion and "
        "is carried as OPEN item ENG-CAL-MARGIN, above its own 16-18 band.",
    ),
)

MDR1_RECENT_FORM = _ruling(
    "MDR1-RECENT-FORM-RESIDUAL",
    "Recent-form mechanism",
    "Recent form SHALL exist in V3 and SHALL NOT be defined as wins and losses. It "
    "is defined from performance relative to expectation: performance_residual = "
    "observed_update_margin - expected_margin, where observed_update_margin carries "
    "the approved +/-25 cap. History decays exponentially, weight(k) = lambda ** k "
    "with k = 0 the most recent completed game. The experimental lambda candidates "
    "are exactly FAST 0.60, MEDIUM 0.75 and SLOW 0.90, and all three enter the "
    "500-path responsiveness sweep. Sustained positive residuals produce persistent "
    "positive pressure and sustained negative residuals persistent negative "
    "pressure; a win over a much weaker opponent does not automatically create a "
    "strongly positive signal, and a narrow loss while massively outperforming "
    "expectation does not automatically create a strongly negative one. Eventual "
    "selected status FIXED_BY_V3_RESPONSIVENESS_DESIGN, never EMPIRICALLY_IDENTIFIED.",
    evidence=("MDR1 instruction section 7.",),
)

MDR1_PRESEASON_DECAY = _ruling(
    "MDR1-PRESEASON-DECAY",
    "Preseason prior decay schedule",
    "Preseason-prior weights are frozen at 1.00 opening / W0, then 0.80, 0.60, "
    "0.50, 0.40, 0.30, 0.20 after W1-W6, and 0.15 after W7 and thereafter. The "
    "prior never decays to zero during the 2026 season. FIXED_V3_POLICY. The "
    "non-prior share is supplied by the evolved in-season state under governed V3 "
    "update mechanics, and recent form must not be double-counted where the "
    "evolved state already carries the same residual contribution — this is to be "
    "tested explicitly.",
    evidence=("MDR1 instruction section 8.",),
    supersedes=(
        "The placeholder prior_decay schedule mounted in "
        "config/dynamic_weekly_mc_v3/v3_experimental.json (1.0 / 0.8 / 0.6 / 0.4 / "
        "0.2 / 0.0), which reaches zero after Week 5. The mounted file is left "
        "unedited by this lane; the required alignment is recorded in "
        "config_alignment_required.",
    ),
)

MDR1_FIRST_RERATING = _ruling(
    "MDR1-FIRST-RERATING-W2",
    "First full dynamic rerating",
    "The existing design is preserved: W1 and W2 begin from the preseason/opening "
    "state; an 80% preseason prior exists after W1 for audit/state tracking and 60% "
    "after W2; the first fully promoted V3 rerating becomes effective after Week 2. "
    "The coefficient x Game-SD x recent-form responsiveness sweep runs from the "
    "frozen post-Week-2 state.",
    evidence=("MDR1 instruction section 9.",),
)

MDR1_DESIGN_MATRIX = _ruling(
    "MDR1-DESIGN-MATRIX-500",
    "500-path design matrix",
    "The design specification is coefficient candidates x Game-SD candidates x "
    "recent-form lambda {0.60, 0.75, 0.90} x 500 paths, under common random "
    "numbers. With three coefficient candidates and three SD candidates this is "
    "3 x 3 x 3 x 500 = 13,500 simulated paths across the design experiment — an "
    "experiment workload, not a single 13,500-path production season run. Every "
    "cell consumes the same frozen post-W2 state and the same common seed "
    "schedule; simulated outcomes from one candidate cell never feed another cell "
    "and never feed the frozen rating state.",
    evidence=("MDR1 instruction section 10.",),
)

MDR1_MC_FIREWALL = _ruling(
    "MDR1-MC-FIREWALL",
    "Monte Carlo feedback firewall",
    "SIMULATED_MC_OUTCOMES_NEVER_UPDATE_THE_GOVERNED_WEEKLY_RATING_STATE. Only "
    "realized synthetic weekly results may update the governed team-strength "
    "state. The Monte Carlo forecasts forward from a frozen weekly state. Each "
    "weekly cycle ingests realized results, updates team states once, freezes the "
    "new state and runs a new forward Monte Carlo. Simulation -> rating update -> "
    "simulation feedback loops are prevented unless a future separately governed "
    "methodology explicitly authorizes them.",
    evidence=("MDR1 instruction section 11.",),
)

MDR1_FCS_ENTITY = _ruling(
    "MDR1-FCS-ENTITY",
    "FCS entity policy",
    "FCS_ELO = 1250 is preserved. 1250 is not used directly as V3 football points. "
    "The Board I-H inverse mapping is not resurrected and the old .294 / .297 "
    "equivalents are not used. No individual unsupported FCS ratings are created. "
    "The canonical synthetic universe contains schedule-only FCS entities outside "
    "the governed FBS rating population, and one common V3 FCS baseline is used for "
    "schedule simulation.",
    evidence=(
        "MDR1 instruction section 12.",
        "Consistent with the pre-existing ruling R2-FCS-ELO-1250, which this ruling "
        "does not reopen.",
    ),
)

MDR1_FCS_HFA = _ruling(
    "MDR1-FCS-HFA-3P5",
    "Global home-field advantage, including FCS home sides",
    "GLOBAL_HOME_FIELD_ADVANTAGE_POINTS = 3.5. For all non-neutral governed games "
    "the designated home side receives +3.5 points; for neutral games the venue "
    "adjustment is 0.0. This applies unchanged when the designated home side is a "
    "schedule-only FCS entity. No team-specific FCS home-field modifier is inferred "
    "or manufactured. FIXED_V3_GLOBAL_POLICY.",
    evidence=(
        "MDR1 instruction section 13.",
        "Numerically consistent with ruling R2-HFA-3P5 and with "
        "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER SCHED-HFA-BASE = "
        "3.5 (LOCKED, SOURCE-VERIFIED).",
        "POWER_CRUNCH!Reconciled Master records the FCS home_field_advantage_modifier "
        "as the sentinel UNRESOLVED, so there is nothing to infer even if inference "
        "were permitted.",
    ),
)

MDR1_FCS_ADAPTER = _ruling(
    "MDR1-FCS-ADAPTER",
    "FCS Elo -> V3 point adapter method",
    "The approved V3 adapter method is FCS_ELO_Z = (1250 - mean(FBS_2026_ELO)) / "
    "sd(FBS_2026_ELO), then FCS_V3_NEUTRAL_POINTS = 14.0 * FCS_ELO_Z, computed over "
    "the exact governed/current 2026 FBS Elo population consumed by the relevant "
    "current V3 model state, with the population SD convention explicitly recorded. "
    "The population may not be obtained from Board I-H partial-axis inversion, "
    "historical 2025 Elo, real-world NCAA data, a fabricated Elo bridge, or a "
    "pytest fixture. No such governed 2026 FBS Elo vector exists in the mounted "
    "corpus, so the numeric adapter candidate is not frozen and the status is "
    f"{FCS_ADAPTER_INPUT_MISSING}. This missing calculation does not invalidate any "
    "other ruling in this round.",
    evidence=(
        "MDR1 instruction section 14.",
        "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Master Ratings carries 78 "
        "columns across 121 FBS teams and no Elo column.",
        "POWER_CRUNCH_2026_Team_Reconciled_Master_134_v2_2.xlsx!Build Manifest: "
        "'primary_elo = 999.986237 * board_power_H + 1099.999878'; the same workbook "
        "records rating_authority BOARD_I-H and model_use_authorized = FALSE.",
        "Model_Parameters_v2_5_APPROVED.xlsx!20_CANON_MANIFEST_INGEST records "
        "2025_Preseason_Elo_CARRY_v1.xlsx as REFERENCE (UNRATIFIED) / REJECT FOR "
        "CURRENT USE with no current forward-prior authority.",
    ),
)

MDR1_FCS_WEEKLY = _ruling(
    "MDR1-FCS-WEEKLY-RESULT",
    "FCS weekly result treatment",
    FCS_WEEKLY_RESULT_TREATMENT,
    evidence=("MDR1 instruction section 15.",),
)

MDR1_SAMPLE_REGULARIZATION = _ruling(
    "MDR1-SAMPLE-REGULARIZATION-EXTERNAL",
    "Sample-size regularization authority",
    "Agent 3 is not overridden. Its synthetic-domain experiment may provide an "
    "experimental fit result, which is preserved as SYNTHETIC_FIT_RESULT if properly "
    "identified. If it returns boundary or unidentified instability, that status is "
    "preserved rather than a winner being manufactured. This ruling round decides "
    "nothing about sample_size_regularization.",
    evidence=("MDR1 instruction section 16.",),
)

MDR1_WEEKLY_LOOP = _ruling(
    "MDR1-WEEKLY-LOOP",
    "Weekly operating loop",
    "The intended weekly operation is recorded as an ordered bootstrap sequence "
    "through the frozen post-W2 state, the design sweep, parameter binding and the "
    "remaining-season Monte Carlo, followed from Week 3 onward by the steady-state "
    "sequence: ingest realized results, verify completeness and identities, compute "
    "capped update margins, compute performance residuals, update the evolved "
    "strength state, update recent-form history, apply prior decay, emit >10-slot "
    "advisories, freeze the Week-N state, run the governed remaining-season Monte "
    "Carlo, validate, freeze the weekly report, and await the next realized results.",
    evidence=("MDR1 instruction section 18.",),
)


MODEL_DESIGN_R1_RULINGS: tuple[ChairmanRuling, ...] = (
    MDR1_DOMAIN,
    MDR1_BLOWOUT,
    MDR1_POINT_SCALE,
    MDR1_RANK_ADVISORY,
    MDR1_COEFFICIENT,
    MDR1_GAME_SD,
    MDR1_RECENT_FORM,
    MDR1_PRESEASON_DECAY,
    MDR1_FIRST_RERATING,
    MDR1_DESIGN_MATRIX,
    MDR1_MC_FIREWALL,
    MDR1_FCS_ENTITY,
    MDR1_FCS_HFA,
    MDR1_FCS_ADAPTER,
    MDR1_FCS_WEEKLY,
    MDR1_SAMPLE_REGULARIZATION,
    MDR1_WEEKLY_LOOP,
)

_BY_ID = {r.convergence_id: r for r in MODEL_DESIGN_R1_RULINGS}


def ruling(convergence_id: str) -> ChairmanRuling:
    try:
        return _BY_ID[convergence_id]
    except KeyError:
        raise GovernanceBlock(
            f"No such R1 model-design ruling: {convergence_id!r}"
        ) from None


# ---------------------------------------------------------------------------
# Parameter register and artifact emission
# ---------------------------------------------------------------------------

def parameter_register() -> list[dict[str, object]]:
    """Every parameter this round touches, with its epistemic class.

    The ``empirically_identified`` column is present on every row and is ``False``
    on every row. It is written out rather than omitted so that a reader — and a
    test — can check the claim directly instead of inferring it from absence.
    """
    rows = [
        {
            "parameter": "blowout_treatment",
            "value": BLOWOUT_TREATMENT,
            "status": BLOWOUT_TREATMENT_STATUS,
            "ruling": MDR1_BLOWOUT.convergence_id,
        },
        {
            "parameter": "blowout_margin_cap_points",
            "value": BLOWOUT_MARGIN_CAP_POINTS,
            "status": BLOWOUT_TREATMENT_STATUS,
            "ruling": MDR1_BLOWOUT.convergence_id,
        },
        {
            "parameter": "point_scale",
            "value": V3_POINT_SCALE,
            "status": V3_POINT_SCALE_STATUS,
            "identification": V3_POINT_SCALE_IDENTIFICATION,
            "ruling": MDR1_POINT_SCALE.convergence_id,
        },
        {
            "parameter": "weekly_rank_movement_advisory_slots",
            "value": WEEKLY_RANK_MOVEMENT_ADVISORY_SLOTS,
            "status": WEEKLY_RANK_MOVEMENT_STATUS,
            "ruling": MDR1_RANK_ADVISORY.convergence_id,
        },
        {
            "parameter": "weekly_performance_residual_coefficient",
            "value": None,
            "status": COEFFICIENT_STATUS_BEFORE_SWEEP,
            "status_after_selection": COEFFICIENT_STATUS_AFTER_SWEEP,
            "ruling": MDR1_COEFFICIENT.convergence_id,
        },
        {
            "parameter": "game_sd_points",
            "value": None,
            "status": GAME_SD_STATUS_BEFORE_SWEEP,
            "status_after_selection": GAME_SD_STATUS_AFTER_SWEEP,
            "ruling": MDR1_GAME_SD.convergence_id,
        },
        {
            "parameter": "recent_form_lambda",
            "value": None,
            "status": RECENT_FORM_STATUS_BEFORE_SWEEP,
            "status_after_selection": RECENT_FORM_STATUS_AFTER_SWEEP,
            "ruling": MDR1_RECENT_FORM.convergence_id,
        },
        {
            "parameter": "preseason_prior_decay",
            "value": {str(k): v for k, v in MDR1_PRESEASON_PRIOR_DECAY.items()},
            "status": PRESEASON_PRIOR_DECAY_STATUS,
            "floor": PRESEASON_PRIOR_FLOOR,
            "ruling": MDR1_PRESEASON_DECAY.convergence_id,
        },
        {
            "parameter": "global_home_field_advantage_points",
            "value": GLOBAL_HOME_FIELD_ADVANTAGE_POINTS,
            "status": FCS_HFA_STATUS,
            "ruling": MDR1_FCS_HFA.convergence_id,
        },
        {
            "parameter": "neutral_venue_adjustment_points",
            "value": NEUTRAL_VENUE_ADJUSTMENT_POINTS,
            "status": FCS_HFA_STATUS,
            "ruling": MDR1_FCS_HFA.convergence_id,
        },
        {
            "parameter": "fcs_elo",
            "value": FCS_ELO,
            "status": "FIXED_V3_POLICY",
            "ruling": MDR1_FCS_ENTITY.convergence_id,
        },
        {
            "parameter": "fcs_v3_neutral_points",
            "value": None,
            "status": "BLOCKED_PENDING_GOVERNED_INPUT",
            "blocked_by": FCS_ADAPTER_INPUT_MISSING,
            "ruling": MDR1_FCS_ADAPTER.convergence_id,
        },
        {
            "parameter": "sample_size_regularization",
            "value": None,
            "status": "SYNTHETIC_FIT_RESULT",
            "authority": SAMPLE_SIZE_REGULARIZATION_AUTHORITY,
            "decided_by_this_ruling": SAMPLE_SIZE_REGULARIZATION_DECIDED_HERE,
            "ruling": MDR1_SAMPLE_REGULARIZATION.convergence_id,
        },
    ]
    for row in rows:
        reject_empirical_identification_claim(str(row["status"]))
        row["empirically_identified"] = False
    return rows


def rulings_as_dict() -> dict[str, object]:
    """The complete machine-readable R1 authority artifact."""
    return {
        "artifact": MDR1_ARTIFACT,
        "artifact_status": "CHAIRMAN_MODEL_DESIGN_AUTHORITY_RECORD",
        "authority": "DIRECT_CHAIRMAN_AUTHORITY / V3 MODEL DESIGN",
        "issued_by": "CHAIRMAN",
        "instruction": MDR1_INSTRUCTION,
        "scope": "MODEL_DESIGN_AUTHORITY_AND_DETERMINISTIC_SWEEP_SPECIFICATION_ONLY",
        "model": "DYNAMIC_WEEKLY_MC_V3_EXPERIMENTAL",
        "chairman_ruling_ids_supplied": False,
        "chairman_ruling_id_note": (
            "The instruction issued these decisions directly but supplied no Chairman "
            "ruling identifiers. Each entry carries a locally assigned convergence_id "
            "(DERIVED, stable, prefixed MDR1-) and a chairman_ruling_id that stays "
            "null. No historical Chairman ruling ID was fabricated."
        ),
        "containing_commit_sha": None,
        "containing_commit_sha_note": (
            "Deliberately null. A committed artifact cannot contain the SHA of the "
            "commit that contains it; the candidate SHA belongs to the handoff receipt."
        ),
        "governing_domain": GOVERNING_DOMAIN,
        "real_football_status": REAL_FOOTBALL_STATUS,
        "supersession": {
            "supersedes_artifacts": [],
            "superseded_records_are_preserved_unedited": True,
            "rule": (
                "These rulings are later, direct model-design authority. Where an "
                "earlier experiment or placeholder disagrees, the earlier record is "
                "preserved unedited as a diagnostic witness and this ruling governs "
                "production V3 design. An earlier experimental result never silently "
                "overwrites a later direct ruling."
            ),
            "per_ruling_supersessions": [
                {"ruling": r.convergence_id, "supersedes": list(r.supersedes)}
                for r in MODEL_DESIGN_R1_RULINGS
                if r.supersedes
            ],
        },
        "rulings": [r.as_dict() for r in MODEL_DESIGN_R1_RULINGS],
        "parameter_register": parameter_register(),
        "permitted_statuses": list(PERMITTED_STATUSES),
        "empirically_identified_claims": [],
        "fixed_values": {
            "blowout_treatment": BLOWOUT_TREATMENT,
            "blowout_margin_cap_points": BLOWOUT_MARGIN_CAP_POINTS,
            "point_scale": V3_POINT_SCALE,
            "point_scale_definition": V3_POINT_SCALE_DEFINITION,
            "weekly_rank_movement_advisory_slots": WEEKLY_RANK_MOVEMENT_ADVISORY_SLOTS,
            "preseason_prior_decay": {
                str(k): v for k, v in MDR1_PRESEASON_PRIOR_DECAY.items()
            },
            "preseason_prior_floor": PRESEASON_PRIOR_FLOOR,
            "first_promoted_rerating_after_week": FIRST_PROMOTED_RERATING_AFTER_WEEK,
            "global_home_field_advantage_points": GLOBAL_HOME_FIELD_ADVANTAGE_POINTS,
            "neutral_venue_adjustment_points": NEUTRAL_VENUE_ADJUSTMENT_POINTS,
            "fcs_elo": FCS_ELO,
            "recent_form_lambda_candidates": dict(RECENT_FORM_LAMBDA_CANDIDATES),
            "game_sd_fallback_grid": dict(GAME_SD_FALLBACK_GRID),
            "design_paths_per_cell": DESIGN_PATHS_PER_CELL,
        },
        "blowout_policy": {
            "treatment": BLOWOUT_TREATMENT,
            "cap_points": BLOWOUT_MARGIN_CAP_POINTS,
            "status": BLOWOUT_TREATMENT_STATUS,
            "formula": "update_margin = sign(actual_margin) * min(abs(actual_margin), 25.0)",
            "actual_score_unchanged": True,
            "actual_margin_unchanged": True,
            "worked_examples": [
                {"actual_margin": 42.0, "update_margin": 25.0},
                {"actual_margin": -38.0, "update_margin": -25.0},
                {"actual_margin": 13.0, "update_margin": 13.0},
            ],
            "experimental_result_class": EXPERIMENTAL_BLOWOUT_RESULT_CLASS,
        },
        "rank_advisory_policy": {
            "slots": WEEKLY_RANK_MOVEMENT_ADVISORY_SLOTS,
            "status": WEEKLY_RANK_MOVEMENT_STATUS,
            "signal": LARGE_WEEKLY_RANK_MOVE,
            "recorded_fields": list(LARGE_WEEKLY_RANK_MOVE_FIELDS),
            "is_a_rating_cap": False,
            "reordering_or_truncation_permitted": False,
        },
        "preseason_decay_policy": {
            "weights_by_weeks_completed": {
                str(k): v for k, v in MDR1_PRESEASON_PRIOR_DECAY.items()
            },
            "floor": PRESEASON_PRIOR_FLOOR,
            "floor_applies_from_weeks_completed": 7,
            "reaches_zero_during_2026": False,
            "status": PRESEASON_PRIOR_DECAY_STATUS,
            "non_prior_share": "EVOLVED_IN_SEASON_STATE",
            "double_counting_test_required": DOUBLE_COUNTING_TEST_REQUIRED,
        },
        "first_rerating": {
            "design": FIRST_RERATING_DESIGN,
            "first_promoted_rerating_after_week": FIRST_PROMOTED_RERATING_AFTER_WEEK,
            "sweep_origin_state": SWEEP_ORIGIN_STATE,
        },
        "design_sweep": design_matrix_as_dict(),
        "mc_feedback_firewall": {
            "rule": MC_FEEDBACK_FIREWALL,
            "realized_origin_token": REALIZED_RESULT,
            "simulated_origin_token": SIMULATED_RESULT,
            "simulated_outcomes_may_update_state": False,
            "cycle": (
                "Ingest realized results, update team states once, freeze the new "
                "state, run a new forward Monte Carlo from the frozen state."
            ),
            "future_authorisation_required_to_change": True,
        },
        "fcs_entity_policy": {
            "fcs_elo": FCS_ELO,
            "entity_class": FCS_ENTITY_CLASS,
            "baseline_policy": FCS_BASELINE_POLICY,
            "in_governed_fbs_rating_population": False,
            "becomes_evolving_rating_state_member": FCS_BASELINE_EVOLVES,
            "prohibited_routes": dict(FCS_PROHIBITED_ROUTES),
            "forbidden_board_equivalents": list(FCS_FORBIDDEN_BOARD_EQUIVALENTS),
            "weekly_result_treatment": FCS_WEEKLY_RESULT_TREATMENT,
            "fbs_update_from_fcs_game_permitted": (
                FCS_GAME_IS_A_GOVERNED_OBSERVATION_FOR_THE_FBS_TEAM
            ),
        },
        "fcs_hfa_policy": {
            "global_home_field_advantage_points": GLOBAL_HOME_FIELD_ADVANTAGE_POINTS,
            "neutral_venue_adjustment_points": NEUTRAL_VENUE_ADJUSTMENT_POINTS,
            "applies_when_home_side_is_schedule_only_fcs": True,
            "team_specific_fcs_modifier_permitted": FCS_TEAM_SPECIFIC_HFA_PERMITTED,
            "status": FCS_HFA_STATUS,
        },
        "fcs_adapter": fcs_adapter_as_dict(),
        "recent_form_policy": recent_form_axis_as_dict(),
        "sample_size_regularization": {
            "authority": SAMPLE_SIZE_REGULARIZATION_AUTHORITY,
            "decided_by_this_ruling": SAMPLE_SIZE_REGULARIZATION_DECIDED_HERE,
            "result_class_if_identified": (
                SAMPLE_SIZE_REGULARIZATION_RESULT_CLASS_IF_IDENTIFIED
            ),
            "result_class_if_unstable": (
                SAMPLE_SIZE_REGULARIZATION_RESULT_CLASS_IF_UNSTABLE
            ),
            "overwrite_permitted": False,
        },
        "weekly_loop": {
            "bootstrap": list(WEEKLY_LOOP_BOOTSTRAP),
            "steady_state": list(WEEKLY_LOOP_STEADY_STATE),
            "steady_state_first_week": WEEKLY_LOOP_STEADY_STATE_FIRST_WEEK,
        },
        "config_alignment_required": [dict(x) for x in CONFIG_ALIGNMENT_REQUIRED],
        "prohibited_interpretations": list(PROHIBITED_INTERPRETATIONS),
        "lane_actions": {
            "parameters_promoted": [],
            "blockers_retired": [],
            "blockers_opened": [],
            "configuration_files_edited": [],
            "season_simulation_run": False,
            "dev_500_run": False,
            "analysis_2000_run": False,
            "publish_10000_run": False,
            "historical_evidence_edited": False,
            "agent_3_results_overwritten": False,
        },
    }


def write_rulings(path: Path) -> Path:
    """Emit the artifact. LF and sorted keys, so the bytes are host-independent."""
    return write_json_lf(path, rulings_as_dict(), trailing_newline=True)
