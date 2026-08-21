"""Model-scale adapter for schedule-only FCS entities: Elo 1250 -> V3 unified points.

Ruling ``R2-FCS-ELO-1250`` is settled and is **not** reopened here: schedule-only
FCS opponents carry Elo 1250, fixed, with no toggle. See :mod:`.fcs`. This module
addresses the one thing that ruling deliberately does not settle — the
*model-scale adapter* that carries a value on the Elo axis onto the unified
neutral-field points axis the V3 engine actually rates on.

What the search found
---------------------
Two transforms in the mounted artifacts touch these axes, and both reproduce
exactly from this repository:

``Elo <-> Board I-H``
    ``primary_elo = 999.986237 * board_power_H + 1099.999878``, recorded on
    ``POWER_CRUNCH…v2_2.xlsx!Build Manifest``. Reproduced here on all 121
    board-rated rows, max residual 0.014933, matching the manifest's own
    "max residual 0.0149 / 121 teams".

``Unified neutral-field points``
    ``points = 14 * UnifiedMasterZ``, where ``UnifiedMasterZ`` is the four-family
    ensemble ``0.25*z(TrueSkill) + 0.25*z(Litkenhous) + 0.25*z(PureBaxter) +
    0.25*mean(z(Board I-H), z(Board J-B))``. Recorded on
    ``2026_CFB…Unified_Power_Ratings.xlsx!Ensemble Parameters`` and
    ``!Data Dictionary``. Reproduced here on all 121 FBS rows to 0.0 error.

**They do not compose into an Elo -> points rule.** Three independent reasons,
each of which is on its own sufficient:

1. Ruling ``R2-FCS-ELO-1250`` forbids inverting the Elo/Board transform and
   forbids the Board equivalent as a conversion rule. The only direction the
   Build Manifest issues is Board -> Elo.
2. Even if the inversion were permitted it yields a *Board I-H power value*,
   which carries 12.5% of the unified composite. Three of the four families —
   TrueSkill, Litkenhous, Pure Baxter — supply no value for any FCS entity, and
   the ratings workbook holds 121 FBS rows and no FCS rows at all. A Unified
   Master Z cannot be formed from one eighth of its inputs.
3. The Board axis is blank by canonical policy for exactly these entities:
   ``Board columns for FCS: BLANK — Board-equivalent recorded not issued``. All
   13 rows carry ``board_power_H = 'UNRATED'``.

So the blocker is **retained**, and this module is the adapter *interface* plus
an experimental calibration harness — never a value. Its invariants mirror
:mod:`.calibration`:

* ``CANONICAL_FCS_UNIFIED_POINTS`` is ``None`` and no code path in this package
  can set it. Promotion needs an explicit human token.
* An experiment can never write the canonical config.
* Every route the ruling closes is refused *by name*, including the one number
  the new Elo would newly make available — see
  :data:`MANUFACTURED_BOARD_EQUIVALENT_FOR_ELO_1250`.
"""

from __future__ import annotations

import abc
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import fcs
from .calibration import EvaluationObjective
from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_CALIBRATION, R2_FCS

# --- FACT: the two mounted transforms ----------------------------------------

#: FACT — POWER_CRUNCH…v2_2.xlsx!Build Manifest 'Elo <-> Board transform'.
#: Re-exported from :mod:`.fcs` so the two modules can never drift apart.
ELO_BOARD_SLOPE = fcs.POWER_CRUNCH_ELO_BOARD_SLOPE
ELO_BOARD_INTERCEPT = fcs.POWER_CRUNCH_ELO_BOARD_INTERCEPT

#: FACT — the same manifest row: "max residual 0.0149 / 121 teams". Stated to
#: four decimal places by the manifest itself.
ELO_BOARD_RECORDED_MAX_RESIDUAL = 0.0149
ELO_BOARD_RECORDED_ROW_COUNT = 121

#: DERIVED — the residual this repository actually reproduces over those 121
#: rows. Recorded at full precision so the match with the manifest's rounded
#: figure is visible rather than asserted.
ELO_BOARD_REPRODUCED_MAX_RESIDUAL = 0.014932610474716057

#: FACT — 2026_CFB…Unified_Power_Ratings.xlsx!Ensemble Parameters,
#: 'Neutral-field point scale' = 14, "Initial points per standard deviation;
#: recalibrate against game margins". Confirmed by !Data Dictionary,
#: 'Unified Neutral-Field Points' = "14 x Unified Master Z".
UNIFIED_POINTS_PER_Z = 14.0

#: FACT — same sheet: 'Index center' 100, 'Index scale' 10 points per SD.
UNIFIED_INDEX_CENTER = 100.0
UNIFIED_INDEX_POINTS_PER_Z = 10.0

#: FACT — !Ensemble Parameters component weights. Board family is one quarter,
#: split evenly between Board I-H and Board J-B, so Board I-H alone is 12.5%.
FAMILY_WEIGHTS: dict[str, float] = {
    "trueskill": 0.25,
    "litkenhous": 0.25,
    "pure_baxter": 0.25,
    "board_family": 0.25,
}
BOARD_FAMILY_MEMBER_WEIGHTS: dict[str, float] = {"board_i_h": 0.5, "board_j_b": 0.5}

#: FACT — !Ensemble Parameters 'Population Statistics' (mean, standard deviation).
FAMILY_POPULATION_STATS: dict[str, tuple[float, float]] = {
    "trueskill": (25.1494226461405, 4.35928836282486),
    "litkenhous": (0.0, 9.54007859451885),
    "board_i_h": (0.477925892561984, 0.14339718564206),
    "board_j_b": (0.488572704315886, 0.127624569655263),
    "pure_baxter": (-0.0855901237090821, 15.0707902024811),
}

#: The four independent families a Unified Master Z requires. An FCS entity
#: supplies none of them.
REQUIRED_RATING_FAMILIES = ("trueskill", "litkenhous", "pure_baxter", "board_family")

#: DERIVED — reproduced from the 121 FBS rows of the mounted ratings workbook.
#: The V3 engine's rating axis, recorded so an Elo-magnitude candidate is
#: visibly a category error rather than merely a large number.
OBSERVED_FBS_UNIFIED_POINTS_MIN = -17.4576
OBSERVED_FBS_UNIFIED_POINTS_MAX = 32.8847

#: FACT — the ratings workbook carries 121 FBS rows and no FCS row.
UNIFIED_RATINGS_FBS_ROWS = 121
UNIFIED_RATINGS_FCS_ROWS = 0

# --- FACT: the closed routes, each named so it is refused rather than missed --

#: FACT — POWER_CRUNCH!Build Manifest 'Ruling applied': R-FCS-RATING-01 set
#: ``FCS sim_rating = 1397.51``. Superseded for V3 by R2-FCS-ELO-1250.
SUPERSEDED_OPERATOR_COMPOSITE_ELO = 1397.51

#: FACT — POWER_CRUNCH!Reconciled Master ``board_power_H_equivalent`` on all 13
#: FCS rows, and !Conflict Ledger "Board-equivalent 0.297514 recorded, not issued".
RECORDED_NOT_ISSUED_BOARD_EQUIVALENT = 0.297514

#: DERIVED — ``(1397.51 - intercept) / slope``. Demonstrates that the recorded
#: Board equivalent *is* the inverted transform, which is why the ruling closes
#: that route rather than merely disliking the number.
DERIVED_INVERSE_OF_SUPERSEDED_COMPOSITE = (
    SUPERSEDED_OPERATOR_COMPOSITE_ELO - ELO_BOARD_INTERCEPT
) / ELO_BOARD_SLOPE

#: DERIVED AND REFUSED — ``(1250 - intercept) / slope``. This is the number the
#: new ruling would newly make available, and it is the same forbidden route
#: wearing a different value. It is computed here once, for the sole purpose of
#: being refused by name; nothing consumes it.
MANUFACTURED_BOARD_EQUIVALENT_FOR_ELO_1250 = (
    fcs.FCS_FIXED_ELO - ELO_BOARD_INTERCEPT
) / ELO_BOARD_SLOPE

#: Elo-layer constants that must never be read as football points. Each is a
#: real governed value on a different axis, which is exactly what makes the
#: confusion plausible enough to guard against.
ELO_LAYER_CONSTANTS: dict[str, float] = {
    "R2-FCS-ELO-1250 fixed FCS Elo": fcs.FCS_FIXED_ELO,
    "R-FCS-RATING-01 operator composite (superseded)": SUPERSEDED_OPERATOR_COMPOSITE_ELO,
    "CCG-R_REF SOR reference Elo": 1893.3,
    "CCG-HFA_ELO Elo-layer home-field advantage": 65.0,
    "CCG-SIGMA_ELO rating uncertainty": 68.0,
}


def elo_from_board_power_h(board_power_h: float) -> float:
    """The Build Manifest transform, in the one direction it was issued.

    Board -> Elo is the direction the manifest states and is safe to reproduce.
    The inverse is refused by :func:`fcs.invert_board_transform`, which this
    module never calls and never reimplements.
    """
    return ELO_BOARD_SLOPE * float(board_power_h) + ELO_BOARD_INTERCEPT


def standardize(value: float, family: str) -> float:
    """Standardize a raw family rating using the workbook's population statistics."""
    try:
        mean, sd = FAMILY_POPULATION_STATS[family]
    except KeyError:
        raise InputValidationError(
            f"Unknown rating family {family!r}; known families are "
            f"{sorted(FAMILY_POPULATION_STATS)}."
        ) from None
    return (float(value) - mean) / sd


def unified_master_z(
    *,
    trueskill_z: float,
    litkenhous_z: float,
    pure_baxter_z: float,
    board_i_h_z: float,
    board_j_b_z: float,
) -> float:
    """Reproduce ``Unified Master Z`` from four independent family Z scores."""
    board_family_z = (
        BOARD_FAMILY_MEMBER_WEIGHTS["board_i_h"] * board_i_h_z
        + BOARD_FAMILY_MEMBER_WEIGHTS["board_j_b"] * board_j_b_z
    )
    return (
        FAMILY_WEIGHTS["trueskill"] * trueskill_z
        + FAMILY_WEIGHTS["litkenhous"] * litkenhous_z
        + FAMILY_WEIGHTS["pure_baxter"] * pure_baxter_z
        + FAMILY_WEIGHTS["board_family"] * board_family_z
    )


def unified_neutral_field_points(master_z: float) -> float:
    """Reproduce ``Unified Neutral-Field Points = 14 x Unified Master Z``."""
    return UNIFIED_POINTS_PER_Z * float(master_z)


def unified_master_power_index(master_z: float) -> float:
    """Reproduce ``Unified Master Power Index = 100 + 10 x Unified Master Z``."""
    return UNIFIED_INDEX_CENTER + UNIFIED_INDEX_POINTS_PER_Z * float(master_z)


# --- the governed-mapping search, recorded as a result rather than a claim ----

NO_GOVERNED_MAPPING = "NO_GOVERNED_ELO_TO_UNIFIED_POINTS_MAPPING_EXISTS"


@dataclass(frozen=True)
class MappingSearchResult:
    """What an exhaustive search of the mounted artifacts actually found."""

    outcome: str
    reproducible_mappings: tuple[str, ...]
    missing_link: str
    reasons_not_composable: tuple[str, ...]
    artifacts_searched: tuple[str, ...]

    @property
    def governed_mapping_exists(self) -> bool:
        return self.outcome != NO_GOVERNED_MAPPING

    def as_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "governed_mapping_exists": self.governed_mapping_exists,
            "reproducible_mappings": list(self.reproducible_mappings),
            "missing_link": self.missing_link,
            "reasons_not_composable": list(self.reasons_not_composable),
            "artifacts_searched": list(self.artifacts_searched),
        }


GOVERNED_MAPPING_SEARCH = MappingSearchResult(
    outcome=NO_GOVERNED_MAPPING,
    reproducible_mappings=(
        "Board I-H -> Elo: primary_elo = 999.986237 * board_power_H + 1099.999878 "
        "(POWER_CRUNCH…v2_2.xlsx!Build Manifest; reproduced on 121 rows, max residual 0.014933)",
        "four-family ensemble -> unified points: points = 14 * UnifiedMasterZ "
        "(2026_CFB…Unified_Power_Ratings.xlsx!Ensemble Parameters + !Data Dictionary; "
        "reproduced on 121 FBS rows to 0.0 error)",
    ),
    missing_link="Elo -> unified neutral-field points, for an entity with no rating family values",
    reasons_not_composable=(
        f"Ruling {R2_FCS.convergence_id} forbids inverting the Elo/Board transform and forbids "
        "the Board equivalent as a conversion rule. The manifest issues Board -> Elo only.",
        "Board I-H carries 12.5% of the unified composite. The other three families — TrueSkill, "
        "Litkenhous, Pure Baxter — supply no value for any schedule-only FCS entity, so no "
        "Unified Master Z can be formed even if the inversion were permitted.",
        "The unified ratings workbook holds 121 FBS rows and no FCS row, so there is nothing to "
        "read the missing families from.",
        "POWER_CRUNCH!Build Manifest records 'Board columns for FCS: BLANK — Board-equivalent "
        "recorded not issued', and all 13 FCS rows carry board_power_H = 'UNRATED'.",
        "No register, ruling or workbook row anywhere in the mounted set states a points-per-Elo "
        "rate, an Elo-to-points table, or an FCS unified-points value.",
    ),
    artifacts_searched=(
        "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx (all 5 sheets)",
        "POWER_CRUNCH_2026_Team_Reconciled_Master_134_v2_2.xlsx (all 3 sheets)",
        "Model_Parameters_v2_5_APPROVED.xlsx (all 27 sheets)",
        "V2_1_STATIC_CONTROL_2026_CFB_10000_Season_Monte_Carlo.xlsx (all 7 sheets)",
        "2026 Bracket Regime LOCKED.xlsx (all 3 sheets)",
        "2026 Playoff Calendar OFFICIAL 2.xlsx (all 5 sheets)",
        "2026_FBS_Schedule_LOCKED_v5.xlsx (Games, Certification)",
        "2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md",
    ),
)


def search_governed_elo_to_points_mapping() -> MappingSearchResult:
    """The recorded result of searching every mounted artifact for the bridge."""
    return GOVERNED_MAPPING_SEARCH


# --- the adapter interface ----------------------------------------------------

#: The canonical FCS unified-points value. ``None``, and only a human promotion
#: can change that. Nothing in this package writes it.
CANONICAL_FCS_UNIFIED_POINTS: float | None = None

#: The canonical HFA modifier for an FCS entity hosting. Also ``None``: three
#: scheduled games have a schedule-only FCS entity as the nominal home team and
#: ``SCHED-HFA-BASE`` defines ``team_home_edge_points = modifier * 3.5``.
CANONICAL_FCS_HOME_HFA_MODIFIER: float | None = None

ADAPTER_AUTHORITY_GOVERNED = "GOVERNED_SCALE_RULE"
ADAPTER_AUTHORITY_EXPERIMENTAL = "EXPERIMENTAL_CANDIDATE"
ADAPTER_AUTHORITIES = (ADAPTER_AUTHORITY_GOVERNED, ADAPTER_AUTHORITY_EXPERIMENTAL)


class FcsPointScaleAdapter(abc.ABC):
    """Carries a schedule-only FCS entity from the Elo axis onto the points axis.

    The interface exists so the engine has one named seam to consume once a
    scale rule is issued or calibrated, instead of a value appearing inline. It
    deliberately has no default implementation that returns a number.
    """

    adapter_id: str
    authority: str

    @abc.abstractmethod
    def unified_points(self, elo: float = fcs.FCS_FIXED_ELO) -> float:
        """The unified neutral-field points an FCS entity at ``elo`` carries."""

    @abc.abstractmethod
    def home_hfa_modifier(self) -> float:
        """The HFA modifier to apply when this entity is the nominal home team."""

    @property
    @abc.abstractmethod
    def governed_for_execution(self) -> bool:
        """True only for an adapter a governed V3 run may consume."""

    def as_dict(self) -> dict[str, object]:
        return {
            "adapter_id": self.adapter_id,
            "authority": self.authority,
            "governed_for_execution": self.governed_for_execution,
            "blocker": fcs.FCS_UNIFIED_SCALE_BLOCKER,
        }


class GovernedFcsPointScaleAdapter(FcsPointScaleAdapter):
    """The only adapter a governed run may consume. It fails closed today.

    It holds no value because no governed scale rule has been issued. It refuses
    rather than defaulting, so an absent rule can never be mistaken for a rule
    that happens to evaluate to something reasonable.
    """

    adapter_id = "FCS_POINT_SCALE_GOVERNED"
    authority = ADAPTER_AUTHORITY_GOVERNED

    def unified_points(self, elo: float = fcs.FCS_FIXED_ELO) -> float:
        require_governed_fcs_elo(elo)
        if CANONICAL_FCS_UNIFIED_POINTS is None:
            # Single source of truth: the R2 refusal text, unweakened.
            return fcs.require_fcs_unified_points()
        return CANONICAL_FCS_UNIFIED_POINTS

    def home_hfa_modifier(self) -> float:
        if CANONICAL_FCS_HOME_HFA_MODIFIER is None:
            raise GovernanceBlock(
                f"{fcs.FCS_UNIFIED_SCALE_BLOCKER}: no HFA modifier is governed for a "
                "schedule-only FCS entity as nominal home team. Three scheduled games need "
                "one (G0019 SJSU@EMU, G0213 SDSU@TOL, G0224 BOISE@WMU) and "
                "SCHED-HFA-BASE defines team_home_edge_points = modifier * 3.5. Issue the "
                "modifier; do not default it to 1.0."
            )
        return CANONICAL_FCS_HOME_HFA_MODIFIER

    @property
    def governed_for_execution(self) -> bool:
        return (
            CANONICAL_FCS_UNIFIED_POINTS is not None
            and CANONICAL_FCS_HOME_HFA_MODIFIER is not None
        )


GOVERNED_FCS_POINT_SCALE_ADAPTER = GovernedFcsPointScaleAdapter()


def require_governed_fcs_elo(elo: float) -> float:
    """Fail closed unless the Elo presented is the one the ruling fixes."""
    if float(elo) != fcs.FCS_FIXED_ELO:
        raise GovernanceBlock(
            f"FCS Elo {elo} is not the governed value {fcs.FCS_FIXED_ELO} "
            f"(ruling {R2_FCS.convergence_id}). The rating policy is closed and is not "
            "reopened by the model-scale adapter."
        )
    return float(elo)


def require_governed_adapter(adapter: FcsPointScaleAdapter) -> FcsPointScaleAdapter:
    """Gate the engine seam. An experimental adapter can never reach a run."""
    if adapter.authority != ADAPTER_AUTHORITY_GOVERNED:
        raise GovernanceBlock(
            f"Adapter {adapter.adapter_id} carries authority {adapter.authority!r} and may not "
            "be consumed by a governed V3 run. Experimental results never become canonical "
            "without an explicit human promotion."
        )
    if not adapter.governed_for_execution:
        raise GovernanceBlock(
            f"{fcs.FCS_UNIFIED_SCALE_BLOCKER}: adapter {adapter.adapter_id} holds no governed "
            "scale rule. Issue an Elo-to-unified-points rule, or calibrate one, before a run."
        )
    return adapter


# --- refusal surface ----------------------------------------------------------


def reject_manufactured_board_equivalent(candidate: float) -> None:
    """Refuse every Board-equivalent route, including the newly available one.

    :func:`fcs.reject_board_derived_conversion` already names the values recorded
    against the superseded composite. Ruling ``R2-FCS-ELO-1250`` changes the Elo,
    which makes a *new* Board equivalent computable — the same closed route with
    a different number. It is refused here by name so it cannot arrive as an
    apparently novel derivation.
    """
    fcs.reject_board_derived_conversion(candidate)
    value = float(candidate)
    if round(value, 9) == round(MANUFACTURED_BOARD_EQUIVALENT_FOR_ELO_1250, 9):
        raise GovernanceBlock(
            f"Board equivalent {value} is (1250 - {ELO_BOARD_INTERCEPT}) / {ELO_BOARD_SLOPE}, "
            "the inverted POWER_CRUNCH Elo/Board transform applied to the newly ruled Elo. "
            f"Ruling {R2_FCS.convergence_id} forbids that inversion; a new Elo does not make "
            "the closed route available again."
        )


def reject_elo_read_as_points(candidate: float) -> None:
    """Refuse an Elo-layer constant presented as a football-point value."""
    value = float(candidate)
    for label, constant in ELO_LAYER_CONSTANTS.items():
        if value == constant:
            raise GovernanceBlock(
                f"{value} is {label}, a value on the Elo axis. The V3 engine rates in unified "
                f"neutral-field points (observed FBS range {OBSERVED_FBS_UNIFIED_POINTS_MIN} to "
                f"{OBSERVED_FBS_UNIFIED_POINTS_MAX}). An Elo is not a point total, and reading "
                "it as one is the category error this adapter exists to prevent."
            )


def outside_observed_fbs_points_span(candidate: float) -> bool:
    """Report — never refuse — a candidate outside the observed FBS points span.

    A schedule-only FCS entity is expected to sit *below* the FBS minimum, so
    this is a reviewer signal and deliberately not a validation band. Inventing
    a band here would be inventing calibration.
    """
    return not (
        OBSERVED_FBS_UNIFIED_POINTS_MIN <= float(candidate) <= OBSERVED_FBS_UNIFIED_POINTS_MAX
    )


# --- exact evidence requirements ---------------------------------------------

ROUTE_ISSUED = "ISSUED_SCALE_RULE"
ROUTE_CALIBRATED = "CALIBRATED_SCALE_RULE"
ROUTE_EITHER = "EITHER_ROUTE"
CLOSURE_ROUTES = (ROUTE_ISSUED, ROUTE_CALIBRATED)


@dataclass(frozen=True)
class EvidenceRequirement:
    """One thing that must be supplied before the blocker can defensibly close."""

    requirement_id: str
    route: str
    requirement: str
    why_required: str
    satisfied: bool = False

    def __post_init__(self) -> None:
        if self.route not in (*CLOSURE_ROUTES, ROUTE_EITHER):
            raise InputValidationError(
                f"{self.requirement_id} names unknown closure route {self.route!r}"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "requirement_id": self.requirement_id,
            "route": self.route,
            "requirement": self.requirement,
            "why_required": self.why_required,
            "satisfied": self.satisfied,
        }


FCS_POINT_SCALE_EVIDENCE_REQUIREMENTS: tuple[EvidenceRequirement, ...] = (
    # --- route A: an issued scale rule ---------------------------------------
    EvidenceRequirement(
        requirement_id="FCS-SCALE-A1",
        route=ROUTE_ISSUED,
        requirement=(
            "An issued rule stating either (a) the exact unified neutral-field points value a "
            "schedule-only FCS entity carries at Elo 1250, or (b) an explicit Elo-to-points "
            "function with its coefficients stated in the ruling itself."
        ),
        why_required=(
            "The engine consumes a points value. No mounted artifact states one, and no "
            "artifact states a points-per-Elo rate from which one could be computed."
        ),
    ),
    EvidenceRequirement(
        requirement_id="FCS-SCALE-A2",
        route=ROUTE_ISSUED,
        requirement=(
            "The ruling must state that the value is issued, and not derived from the Board "
            "I-H equivalent nor from inverting the POWER_CRUNCH Elo/Board transform."
        ),
        why_required=(
            f"Ruling {R2_FCS.convergence_id} closes both routes. A value that silently arrived "
            "by the closed route would satisfy the engine while violating the ruling."
        ),
    ),
    EvidenceRequirement(
        requirement_id="FCS-SCALE-A3",
        route=ROUTE_ISSUED,
        requirement=(
            "Whether one value covers all 13 entities or each is rated separately, stated "
            "explicitly."
        ),
        why_required=(
            "Every mounted source treats the 13 as undifferentiated: one sim_rating, one "
            "Board equivalent, one ruling. Assuming that carries onto the points axis would "
            "be an assumption, and assuming it does not would be another."
        ),
    ),
    EvidenceRequirement(
        requirement_id="FCS-SCALE-A4",
        route=ROUTE_ISSUED,
        requirement=(
            "Whether an FCS entity's points value participates in weekly rerating or stays "
            "fixed for the season."
        ),
        why_required=(
            "V2.1 recorded 'Power ratings do not update for injuries or simulated results "
            "during a season'. V3 reretes weekly. An FCS entity plays one game and the "
            "rerating treatment of a one-game entity is not governed."
        ),
    ),
    # --- route B: a calibrated scale rule ------------------------------------
    EvidenceRequirement(
        requirement_id="FCS-SCALE-B1",
        route=ROUTE_CALIBRATED,
        requirement=(
            "A mounted governed historical calibration observation set of completed "
            "FBS-versus-FCS games with actual margins, passing calibration.register_dataset."
        ),
        why_required=(
            "No observation set is mounted anywhere in this repository. The 15 mounted "
            "FBS-v-FCS fixtures are 2026 games that have not been played, so they are the "
            "thing to be predicted and can never be their own training data."
        ),
    ),
    EvidenceRequirement(
        requirement_id="FCS-SCALE-B2",
        route=ROUTE_CALIBRATED,
        requirement=(
            "A named evaluation objective for this parameter, consistent with ruling "
            f"{R2_CALIBRATION.convergence_id}."
        ),
        why_required=(
            "Ranking candidates against an unstated goal is how an arbitrary choice acquires "
            "the appearance of evidence."
        ),
    ),
    EvidenceRequirement(
        requirement_id="FCS-SCALE-B3",
        route=ROUTE_CALIBRATED,
        requirement="Training / validation / holdout separation, with promotion evidence from holdout.",
        why_required=(
            f"Ruling {R2_CALIBRATION.convergence_id} keeps the three splits separated and "
            "requires out-of-sample evidence."
        ),
    ),
    # --- either route ---------------------------------------------------------
    EvidenceRequirement(
        requirement_id="FCS-SCALE-C1",
        route=ROUTE_EITHER,
        requirement=(
            "An HFA modifier for a schedule-only FCS entity as nominal home team, for the "
            "three scheduled games G0019 (SJSU@EMU), G0213 (SDSU@TOL) and G0224 (BOISE@WMU)."
        ),
        why_required=(
            "Team.hfa_modifier is None for all 13 FCS entities and SCHED-HFA-BASE defines "
            "team_home_edge_points = modifier * 3.5. The engine currently reads "
            "`home_team.hfa_modifier or 1.0`, which would silently default an ungoverned "
            "entity to the full FBS home edge."
        ),
    ),
    EvidenceRequirement(
        requirement_id="FCS-SCALE-C2",
        route=ROUTE_EITHER,
        requirement=(
            "An explicit human promotion token, "
            "APPROVE_V3_FCS_POINT_SCALE_PROMOTION::<RULING_ID>, plus a named promotion "
            "authority."
        ),
        why_required=(
            "No experiment and no ranking promotes itself. This mirrors the calibration "
            "promotion gate and is refused by default."
        ),
    ),
)

#: Routes that are explicitly **not** sufficient, recorded so a reviewer can see
#: they were considered and rejected rather than overlooked.
INSUFFICIENT_EVIDENCE: tuple[str, ...] = (
    "Inverting the POWER_CRUNCH Elo/Board transform to obtain a Board power value — forbidden "
    f"by ruling {R2_FCS.convergence_id}.",
    "The recorded Board equivalents 0.294 / 0.297 / 0.297514 — 'recorded not issued', and "
    "forbidden as a conversion rule by the same ruling.",
    f"The Board equivalent {MANUFACTURED_BOARD_EQUIVALENT_FOR_ELO_1250!r} computable from Elo "
    "1250 — the same closed route with a new number.",
    "Reading 1250, or the superseded 1397.51, as a football-point value — a category error "
    "between the Elo and unified-points axes.",
    "Running the four-family unified ensemble for an FCS entity — three of four families "
    "supply no value and Board I-H is recorded UNRATED.",
    "Fitting any affine, logistic or inverse transform between the axes from the 121 FBS rows "
    "and extrapolating it to an entity outside that population — an invented rule no source "
    "issued.",
    "V2.1's bridge, which is the Board I-H equivalent route the ruling closes.",
)


def unsatisfied_evidence_requirements(
    register: Iterable[EvidenceRequirement] | None = None,
) -> tuple[EvidenceRequirement, ...]:
    entries = tuple(register) if register is not None else FCS_POINT_SCALE_EVIDENCE_REQUIREMENTS
    return tuple(e for e in entries if not e.satisfied)


# --- coverage over the 13 identities and every FBS-v-FCS game ----------------

#: FACT — 2026_TEAM_CANONICAL_MASTER_v2 entity_scope SCHEDULE_ONLY_FCS, cross-checked
#: against POWER_CRUNCH!Reconciled Master. Held here so a test can prove the set is
#: exactly these and not merely thirteen of something.
SCHEDULE_ONLY_FCS_IDS: frozenset[str] = frozenset(
    {"ARST", "CHAR", "CP", "DUQ", "EMU", "IDHO", "SAC", "SUU", "TOL", "ULL", "ULM", "WKU", "WMU"}
)

#: FACT — 2026_FBS_Schedule_LOCKED_v5.xlsx!Games. Every game touching a
#: schedule-only FCS entity, in schedule order.
FBS_V_FCS_GAME_IDS: tuple[str, ...] = (
    "G0019", "G0045", "G0056", "G0071", "G0074", "G0096", "G0123", "G0144",
    "G0151", "G0168", "G0193", "G0213", "G0214", "G0224", "G0575",
)

#: FACT — the three of those games in which the FCS entity is the nominal home
#: team, which is the second gap the adapter must close.
FCS_HOME_GAME_IDS: tuple[str, ...] = ("G0019", "G0213", "G0224")

#: FACT — the weeks those games fall in.
FBS_V_FCS_WEEKS: tuple[int, ...] = (2, 3, 4, 5, 12)


def fcs_scale_coverage(teams: Mapping[str, Any], schedule: Iterable[Any]) -> dict[str, object]:
    """Report every identity and every game the missing adapter blocks.

    Computed from the mounted inputs rather than asserted, so the counts move if
    the schedule or the canonical master ever does.
    """
    fcs_ids = {
        sid for sid, team in teams.items() if team.entity_scope == "SCHEDULE_ONLY_FCS"
    }
    identities = [
        {
            "schedule_id": sid,
            "team_name": teams[sid].team_name,
            "governed_elo": fcs.FCS_FIXED_ELO,
            "preseason_strength_points": teams[sid].preseason_strength_points,
            "hfa_modifier": teams[sid].hfa_modifier,
            "unified_points_resolvable": False,
            "blocked_by": fcs.FCS_UNIFIED_SCALE_BLOCKER,
        }
        for sid in sorted(fcs_ids)
    ]
    games = []
    for game in schedule:
        home_is_fcs = game.home_team in fcs_ids
        away_is_fcs = game.away_team in fcs_ids
        if not (home_is_fcs or away_is_fcs):
            continue
        games.append(
            {
                "game_id": game.game_id,
                "week": game.week,
                "game_type": game.game_type,
                "home_team": game.home_team,
                "away_team": game.away_team,
                "venue": game.venue,
                "fcs_entity_is_home": home_is_fcs,
                "requires_points_adapter": True,
                "requires_home_hfa_modifier": home_is_fcs,
                "simulatable": False,
                "blocked_by": fcs.FCS_UNIFIED_SCALE_BLOCKER,
            }
        )
    games.sort(key=lambda row: (row["week"], row["game_id"]))
    return {
        "blocker": fcs.FCS_UNIFIED_SCALE_BLOCKER,
        "fcs_identities": identities,
        "fcs_identity_count": len(identities),
        "fbs_v_fcs_games": games,
        "fbs_v_fcs_game_count": len(games),
        "fcs_home_game_ids": [g["game_id"] for g in games if g["fcs_entity_is_home"]],
        "weeks_affected": sorted({int(g["week"]) for g in games}),
        "identities_resolvable": 0,
        "games_simulatable": 0,
    }


# --- experimental calibration harness ----------------------------------------
#
# Mirrors :mod:`.calibration` deliberately: same shape, same invariants, separate
# namespace. A candidate FCS scale rule must not be promotable by the calibration
# token, and a calibration coefficient must not be promotable by this one.

#: The fields a candidate FCS scale regime may set, and nothing else.
FCS_SCALE_FIELDS = ("fcs_unified_points_equivalent", "fcs_home_hfa_modifier")

_FCS_SCALE_APPROVAL_TOKEN = re.compile(
    r"^APPROVE_V3_FCS_POINT_SCALE_PROMOTION::[A-Z0-9_.-]{4,}$"
)

BLOCKED_ON_FCS_SCALE_EVIDENCE = "BLOCKED_ON_FCS_SCALE_EVIDENCE"


@dataclass(frozen=True)
class CandidateFcsScaleRegime:
    """A named candidate Elo-to-points scale rule. Never canonical."""

    regime_id: str
    values: dict[str, Any]
    rationale: str
    status: str = "EXPERIMENTAL"

    def __post_init__(self) -> None:
        if self.status != "EXPERIMENTAL":
            raise GovernanceBlock(
                f"Candidate FCS scale regime {self.regime_id} must be EXPERIMENTAL, "
                f"got {self.status!r}"
            )
        unknown = sorted(set(self.values) - set(FCS_SCALE_FIELDS))
        if unknown:
            raise InputValidationError(
                f"Regime {self.regime_id} sets unknown fields: {unknown}"
            )
        points = self.values.get("fcs_unified_points_equivalent")
        if points is not None:
            value = float(points)
            if not math.isfinite(value):
                raise InputValidationError(
                    f"Regime {self.regime_id} proposes a non-finite points value."
                )
            # Every closed route is refused here, at the point a candidate is
            # authored, rather than downstream where it would already look like data.
            reject_elo_read_as_points(value)
            reject_manufactured_board_equivalent(value)


class ExperimentalFcsPointScaleAdapter(FcsPointScaleAdapter):
    """A candidate adapter for experimentation. Never consumable by a run."""

    authority = ADAPTER_AUTHORITY_EXPERIMENTAL

    def __init__(self, regime: CandidateFcsScaleRegime) -> None:
        self.regime = regime
        self.adapter_id = f"FCS_POINT_SCALE_EXPERIMENTAL::{regime.regime_id}"

    def unified_points(self, elo: float = fcs.FCS_FIXED_ELO) -> float:
        require_governed_fcs_elo(elo)
        value = self.regime.values.get("fcs_unified_points_equivalent")
        if value is None:
            raise GovernanceBlock(
                f"Experimental regime {self.regime.regime_id} proposes no points value. "
                f"{BLOCKED_ON_FCS_SCALE_EVIDENCE}."
            )
        return float(value)

    def home_hfa_modifier(self) -> float:
        value = self.regime.values.get("fcs_home_hfa_modifier")
        if value is None:
            raise GovernanceBlock(
                f"Experimental regime {self.regime.regime_id} proposes no FCS home HFA "
                f"modifier. {BLOCKED_ON_FCS_SCALE_EVIDENCE}."
            )
        return float(value)

    @property
    def governed_for_execution(self) -> bool:
        return False

    def as_dict(self) -> dict[str, object]:
        payload = super().as_dict()
        payload.update(
            {
                "regime_id": self.regime.regime_id,
                "candidate_values": dict(self.regime.values),
                "status": "EXPERIMENTAL_CANDIDATE_NOT_PROMOTED",
            }
        )
        return payload


def load_candidate_fcs_scale_regimes(path: Path) -> list[CandidateFcsScaleRegime]:
    """Load candidate scale regimes from the experimental config path only."""
    resolved = Path(path).resolve()
    if resolved.name == "v3_experimental.json":
        raise GovernanceBlock(
            "Candidate FCS scale regimes must not live in the canonical V3 config. "
            "Use config/dynamic_weekly_mc_v3/experimental/."
        )
    if "experimental" not in resolved.parts:
        raise GovernanceBlock(
            f"Candidate FCS scale regimes must load from an experimental config path, "
            f"got {resolved}"
        )
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return [
        CandidateFcsScaleRegime(
            regime_id=entry["regime_id"],
            values=entry.get("values", {}),
            rationale=entry.get("rationale", ""),
            status=entry.get("status", "EXPERIMENTAL"),
        )
        for entry in raw.get("regimes", [])
    ]


def require_fcs_scale_objective(objective: EvaluationObjective | None) -> EvaluationObjective:
    """Fail closed unless an explicit named objective is supplied."""
    if objective is None:
        raise GovernanceBlock(
            "No evaluation objective supplied. A candidate FCS point-scale rule cannot be "
            "called best without an explicit, named objective (ruling "
            f"{R2_CALIBRATION.convergence_id})."
        )
    return objective


def promote_fcs_scale_regime(
    regime: CandidateFcsScaleRegime,
    *,
    authority: str | None = None,
    approval_token: str | None = None,
    justification: str = "",
    evidence: dict[str, Any] | None = None,
    ranked_first: bool = False,
) -> dict[str, Any]:
    """Promotion gate for a candidate FCS scale rule.

    Refuses everything except an explicit human token in this parameter's own
    namespace. ``ranked_first`` is accepted only so it can be explicitly
    ignored: winning an evaluation is not authority to become canonical.
    """
    from .calibration import (
        PROMOTION_AUTHORITIES,
        PROMOTION_AUTHORITY_CHAIRMAN,
        PROMOTION_AUTHORITY_MATHEMATICAL,
    )

    if authority is None:
        raise GovernanceBlock(
            f"Regime {regime.regime_id} cannot be promoted: no promotion authority named. "
            f"Recognised authorities are {list(PROMOTION_AUTHORITIES)}."
            + (" A top ranking is not an authority." if ranked_first else "")
        )
    if authority not in PROMOTION_AUTHORITIES:
        raise GovernanceBlock(
            f"Unknown promotion authority {authority!r}; expected one of "
            f"{list(PROMOTION_AUTHORITIES)}."
        )
    if authority == PROMOTION_AUTHORITY_MATHEMATICAL:
        supplied = evidence or {}
        if supplied.get("split") != "holdout":
            raise GovernanceBlock(
                "Mathematical promotion evidence must come from the holdout split; "
                f"got {supplied.get('split')!r}."
            )
        if not supplied.get("dataset_sha256"):
            raise GovernanceBlock(
                f"Promotion of {regime.regime_id} under {PROMOTION_AUTHORITY_MATHEMATICAL} "
                "requires a registered calibration dataset digest. "
                f"{BLOCKED_ON_FCS_SCALE_EVIDENCE}: none is mounted."
            )
    if authority == PROMOTION_AUTHORITY_CHAIRMAN and not justification.strip():
        raise GovernanceBlock(
            f"Promotion of {regime.regime_id} under {PROMOTION_AUTHORITY_CHAIRMAN} requires an "
            "explicit written justification."
        )
    if approval_token is None:
        raise GovernanceBlock(
            f"Regime {regime.regime_id} cannot be promoted: no human approval token. "
            "Experimental results never update canonical V3 configuration automatically"
            + (" (including the top-ranked regime)." if ranked_first else ".")
        )
    if not _FCS_SCALE_APPROVAL_TOKEN.match(approval_token):
        raise GovernanceBlock(
            f"Malformed FCS point-scale promotion approval token for {regime.regime_id}. "
            "Expected APPROVE_V3_FCS_POINT_SCALE_PROMOTION::<RULING_ID>. The calibration "
            "token is a different namespace and does not authorise this parameter."
        )
    return {
        "regime_id": regime.regime_id,
        "approval_token": approval_token,
        "promotion_authority": authority,
        "justification": justification,
        "evidence": dict(evidence or {}),
        "promoted_values": dict(regime.values),
        "blocker": fcs.FCS_UNIFIED_SCALE_BLOCKER,
        "note": (
            "Promotion authorized. Canonical config is still written by a human-reviewed "
            "change, not by this harness."
        ),
        "writes_canonical_config": False,
    }


# --- status -------------------------------------------------------------------


def fcs_point_scale_status() -> dict[str, object]:
    """The adapter's disposition, for preflight and for the handoff record."""
    return {
        "blocker": fcs.FCS_UNIFIED_SCALE_BLOCKER,
        "blocker_retained": True,
        "disposition": "MODEL_SCALE_ADAPTER_REQUIRED",
        "rating_policy_resolved": fcs.FCS_RATING_POLICY_RESOLVED,
        "rating_policy_ruling": R2_FCS.convergence_id,
        "governed_fcs_elo": fcs.FCS_FIXED_ELO,
        "adapter_interface_implemented": True,
        "adapter_constructed": False,
        "canonical_unified_points": CANONICAL_FCS_UNIFIED_POINTS,
        "canonical_home_hfa_modifier": CANONICAL_FCS_HOME_HFA_MODIFIER,
        "governed_for_execution": GOVERNED_FCS_POINT_SCALE_ADAPTER.governed_for_execution,
        "mapping_search": GOVERNED_MAPPING_SEARCH.as_dict(),
        "closure_routes": list(CLOSURE_ROUTES),
        "evidence_requirements": [
            e.as_dict() for e in FCS_POINT_SCALE_EVIDENCE_REQUIREMENTS
        ],
        "unsatisfied_evidence_requirement_ids": [
            e.requirement_id for e in unsatisfied_evidence_requirements()
        ],
        "insufficient_evidence": list(INSUFFICIENT_EVIDENCE),
        "reproduced_transforms": {
            "elo_from_board_power_h": (
                f"primary_elo = {ELO_BOARD_SLOPE} * board_power_H + {ELO_BOARD_INTERCEPT}"
            ),
            "unified_neutral_field_points": (
                f"points = {UNIFIED_POINTS_PER_Z} * UnifiedMasterZ"
            ),
            "elo_board_recorded_max_residual": ELO_BOARD_RECORDED_MAX_RESIDUAL,
            "elo_board_reproduced_max_residual": ELO_BOARD_REPRODUCED_MAX_RESIDUAL,
        },
        "observed_fbs_unified_points_span": [
            OBSERVED_FBS_UNIFIED_POINTS_MIN,
            OBSERVED_FBS_UNIFIED_POINTS_MAX,
        ],
        "schedule_only_fcs_identities": sorted(SCHEDULE_ONLY_FCS_IDS),
        "fbs_v_fcs_game_ids": list(FBS_V_FCS_GAME_IDS),
        "fcs_home_game_ids": list(FCS_HOME_GAME_IDS),
        "experimental_regimes_authored": 0,
        "automatic_promotion": False,
        "writes_canonical_config": False,
        "dataset_mounted": False,
    }
