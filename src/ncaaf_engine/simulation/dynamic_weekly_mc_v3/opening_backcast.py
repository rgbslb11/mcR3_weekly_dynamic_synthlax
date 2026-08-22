"""Leak-free historical opening backcast — research register, R1.

The question this module answers is narrower than it looks. V3's 2026 opening
strength is ``Unified Master Z``, a quarter-weighted ensemble of four preseason
families. Sibling lane ``claude/v3-historical-opening-state-r1`` established
that none of those four families has a state before 2025. This module asks
whether a *different* thing — a strictly leak-free **proxy** built only from
information that existed before each historical season kicked off — can stand in
for that opening state well enough to support parameter calibration research.

Two findings shape everything below and both are recorded as executable facts
rather than prose:

**The governed carryover transforms are affine, and standardization is
affine-invariant.** ``mu_Y = 25 + 0.70 * (mu_(Y-1) - 25)`` and
``pure_baxter_Y = 0.70 * baxter_ridge_(Y-1)`` are both ``a*x + b`` with
``a > 0``. A Z score is unchanged by either. So for a team that *has* a prior
state, the offseason regression step contributes nothing to the opening Z — the
opening Z of a carryover family simply *is* the standardized prior-season final
rating. A proxy does not approximate that step; it reproduces it exactly. What a
proxy cannot reproduce is the underlying prior-season rating engine and the two
forward-looking families.

**A multi-family proxy ensemble is refused by governance already in place.** The
families that are historically computable from results are Baxter, SRS and
Colley, and ruling R2-CAL-OBJECTIVE keeps the last two as *independent
witnesses*. ``srs.reject_witness_composite`` raises on any weighted blend of
them, because that blend is the Body-of-Work Index that ACC-EXT-12 records
PROPOSAL ONLY / NOT ADOPTED. So the only admissible proxy shape is
single-family with witnesses reported beside it — which is V3's own calibration
reporting shape, and is *not* the Unified Z ensemble shape.

Nothing here emits a per-team opening strength.
``require_no_canonical_opening_values`` fails closed on any attempt, because a
research table of them is one summarisation away from being read as an opening
state.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from .errors import GovernanceBlock, InputValidationError
from .srs import reject_witness_composite

LANE = "claude/v3-opening-backcast-r1"
ARTIFACT_STATUS = "HISTORICAL_OPENING_BACKCAST_RESEARCH_RECORD"
AUTHORITY = "EXPERIMENTAL / NOT CANONICAL / NO PARAMETER PROMOTED / NO BLOCKER RETIRED"

#: The divisor the 2026 workbook actually uses, re-derived by the historical
#: opening-state lane and restated here so a proxy standardizes the same way.
STANDARDIZATION_DDOF = 1


# --- the governed carryover transforms ---------------------------------------


@dataclass(frozen=True)
class CarryoverTransform:
    """An offseason transition rule recorded in a governed 2026 artifact."""

    family: str
    rule: str
    slope: float
    intercept: float
    authority: str

    def apply(self, prior: float) -> float:
        raise GovernanceBlock(
            "opening_backcast does not evaluate carryover transforms onto team values. "
            "The transform is registered so its affine form can be proved, not so a "
            "historical opening strength can be produced from it."
        )


#: FACT — 2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx!Data Dictionary.
#: The Pure Baxter slope is also confirmed against the Master Ratings sheet: the
#: ratio of column AQ to column AM is 0.70 for all 121 teams.
GOVERNED_CARRYOVER_TRANSFORMS: tuple[CarryoverTransform, ...] = (
    CarryoverTransform(
        family="TrueSkill",
        rule="mu_Y = 25 + 0.70 * (mu_(Y-1) - 25)",
        slope=0.70,
        intercept=7.5,
        authority=(
            "Unified Power Ratings workbook, Data Dictionary, 'TrueSkill 2026 Preseason mu'"
        ),
    ),
    CarryoverTransform(
        family="Pure Baxter",
        rule="pure_baxter_Y = 0.70 * baxter_ridge_(Y-1)",
        slope=0.70,
        intercept=0.0,
        authority=(
            "Unified Power Ratings workbook, Data Dictionary, '2026 Pure Baxter Rating'"
        ),
    ),
)


def standardize(
    values: Mapping[str, float], *, ddof: int = STANDARDIZATION_DDOF
) -> dict[str, float]:
    """Z scores over the supplied population, sample deviation by default.

    Refuses a degenerate population rather than returning zeros. A field with no
    dispersion is a source saying nothing, and zeros read as "every team is
    exactly average", which is a different claim.
    """
    if len(values) < 2:
        raise InputValidationError("standardization requires at least two members")
    series = list(values.values())
    spread = statistics.stdev(series) if ddof == 1 else statistics.pstdev(series)
    if spread == 0.0:
        raise InputValidationError(
            "population has zero dispersion; there is no deviation to divide by"
        )
    mean = statistics.fmean(series)
    return {team: (value - mean) / spread for team, value in values.items()}


def affine_invariance_witness(
    values: Mapping[str, float], transform: CarryoverTransform
) -> dict[str, object]:
    """Show that a governed carryover leaves the standardized state unchanged.

    This is the load-bearing result of the lane: the offseason regression step is
    a positive affine map, and a Z score is invariant under one. For any team
    carrying a prior state, the opening Z of a carryover family equals the
    standardized prior-season final rating, exactly and not approximately.
    """
    if transform.slope <= 0:
        raise InputValidationError(
            "a carryover slope must be positive to preserve ordering"
        )
    before = standardize(values)
    after = standardize(
        {
            team: transform.slope * value + transform.intercept
            for team, value in values.items()
        }
    )
    worst = max(abs(before[team] - after[team]) for team in before)
    return {
        "family": transform.family,
        "rule": transform.rule,
        "slope": transform.slope,
        "population": len(values),
        "max_abs_z_difference": worst,
        "z_invariant": worst < 1e-9,
        "consequence": (
            "The carryover step contributes nothing to a standardized opening state for "
            "a team that holds a prior state. It is not a source of proxy error."
        ),
    }


# --- the four V3 preseason families, and whether history can rebuild them -----


@dataclass(frozen=True)
class FamilyReproducibility:
    family: str
    weight: float
    native_field: str
    native_units: str
    standardization: str
    earliest_state: str
    historically_reproducible: bool
    basis: str


#: FACT — weights and native fields from the workbook's Ensemble Parameters
#: sheet; earliest-state findings from the historical opening-state lane.
V3_FAMILY_REPRODUCIBILITY: tuple[FamilyReproducibility, ...] = (
    FamilyReproducibility(
        family="TrueSkill",
        weight=0.25,
        native_field="TrueSkill 2026 Preseason mu",
        native_units="TrueSkill skill mu",
        standardization="Z over the 121-team field, ddof=1",
        earliest_state="2025 week 1, initialised flat at mu=25 for every team",
        historically_reproducible=False,
        basis=(
            "The transition rule is affine and would be reproducible, but no TrueSkill "
            "update engine is mounted anywhere in this repository and the chain has no "
            "pre-2025 posterior to carry. Fitting a substitute latent-skill model would "
            "be a new system, not a reconstruction."
        ),
    ),
    FamilyReproducibility(
        family="Litkenhous",
        weight=0.25,
        native_field="Litkenhous Adjusted Power",
        native_units="Litkenhous power margin; rating = power + 100",
        standardization="Z over the 121-team field, ddof=1",
        earliest_state="2025 final ratings",
        historically_reproducible=False,
        basis=(
            "Adjusted Power is a carryover plus an explicit offseason composite. The "
            "carryover half needs a prior Litkenhous rating that does not exist before "
            "2025; the composite half is not a function of results at all."
        ),
    ),
    FamilyReproducibility(
        family="Pure Baxter",
        weight=0.25,
        native_field="2026 Pure Baxter Rating",
        native_units="zero-centred margin points, season-specific scale",
        standardization="Z over the 121-team field, ddof=1",
        earliest_state="2025 Baxter ridge fit; 2024 and 2006-2011 fits also exist",
        historically_reproducible=True,
        basis=(
            "The fit is specified end to end by frozen doctrine BAXTER-MOV-v1.0-R and "
            "consumes only scored games and a neutral-site indicator. This is the one "
            "family a leak-free historical proxy can rebuild."
        ),
    ),
    FamilyReproducibility(
        family="Board family",
        weight=0.25,
        native_field="mean of standardized Board I-H and Board J-B power",
        native_units="board power units, two distinct dispersions",
        standardization="each board standardized separately, then averaged",
        earliest_state="2026 only; no board of any letter exists for 2021-2024",
        historically_reproducible=False,
        basis=(
            "Board J-B's components are baseline, returning production, movement, talent, "
            "coaching, market and 247 points. None is derivable from results, and no "
            "historical equivalent is mounted."
        ),
    ),
)

REPRODUCIBLE_FAMILY_WEIGHT = sum(
    f.weight for f in V3_FAMILY_REPRODUCIBILITY if f.historically_reproducible
)


def require_full_family_coverage(rebuilt: Iterable[str]) -> None:
    """Fail closed on any claim that a proxy reconstitutes the V3 ensemble."""
    have = {name.strip().lower() for name in rebuilt}
    want = {f.family.lower() for f in V3_FAMILY_REPRODUCIBILITY}
    missing = sorted(want - have)
    if missing:
        raise GovernanceBlock(
            f"A historical opening state is not the V3 preseason ensemble while "
            f"{missing} are unbuilt. Governed weights are 0.25 each; a proxy carrying "
            f"{REPRODUCIBLE_FAMILY_WEIGHT:.2f} of the ensemble weight is a "
            "HISTORICAL_CALIBRATION_PROXY and may not be labelled an opening ensemble."
        )


def refuse_multi_family_proxy_ensemble(components: Sequence[str]) -> None:
    """Refuse the Unified-Z-analogous blend of the computable historical families.

    The families a results-only proxy can compute are Baxter, SRS and Colley.
    Combining them into one standardized ensemble is exactly the Body-of-Work
    Index blend that ACC-EXT-12 records as NOT ADOPTED, so the refusal already
    exists and this function routes to it rather than restating it.
    """
    reject_witness_composite(components)


# --- the gate that keeps this a research lane ---------------------------------


def require_no_canonical_opening_values(*, values: object = None) -> None:
    """Fail closed on emitting a per-team historical opening strength.

    The lane is authorised to describe a methodology and to measure agreement.
    It is not authorised to write opening values, and a research table of them
    is one summarisation away from being read as one.
    """
    raise GovernanceBlock(
        "opening_backcast emits no per-team opening strength for any season. The lane "
        "produces a methodology, a coverage record and agreement statistics; a value "
        "column is out of scope under 'Do NOT write canonical V3 opening values'."
    )


# --- what the proxy may and may not be used to calibrate ----------------------


@dataclass(frozen=True)
class ParameterSupport:
    parameter: str
    support: str
    contamination: str
    direction: str
    basis: str


#: DERIVED — every direction below follows from one mechanism. A proxy opening
#: state is a noisier measurement of the latent one, so any slope regressed on
#: it is attenuated toward zero and any residual measured around it is inflated.
#: The biases are therefore *signed*, not noise, and do not average out across
#: seasons.
PROXY_CALIBRATION_SUPPORT: tuple[ParameterSupport, ...] = (
    ParameterSupport(
        parameter="POINT_SCALE_IDENTIFICATION",
        support="REFUSED",
        contamination="SEVERE",
        direction="biased low",
        basis=(
            "Errors-in-variables. The fitted points-per-standard-deviation is the true "
            "value times the proxy's reliability. Measured against a same-season "
            "reference the proxy recovers 0.48-0.68 of the slope, so a proxy estimate "
            "is a lower bound and may not be promoted."
        ),
    ),
    ParameterSupport(
        parameter="GAME_SD",
        support="BOUND_ONLY",
        contamination="SEVERE",
        direction="biased high",
        basis=(
            "game_sd_points is the residual dispersion around the deterministic mean. A "
            "weaker mean model leaves more variance behind, so a proxy-fitted value "
            "overstates it. It bounds the parameter from above and locates nothing."
        ),
    ),
    ParameterSupport(
        parameter="WEEKLY_UPDATE_RESPONSE",
        support="REFUSED",
        contamination="HIGH",
        direction="biased high",
        basis=(
            "The weekly residual is actual minus expected, and expected is built on the "
            "opening state in weeks 1-2. A shrunken opening state manufactures residuals "
            "that a fitted coefficient then absorbs. Independently blocked: no governed "
            "rerating formula exists for weeks 3+."
        ),
    ),
    ParameterSupport(
        parameter="MOVEMENT_CAP",
        support="REFUSED",
        contamination="HIGH",
        direction="inherits both",
        basis=(
            "A cap expressed in points inherits the axis scale, and a cap on weekly "
            "movement inherits the update response. It cannot be estimated ahead of the "
            "two parameters it is defined against."
        ),
    ),
    ParameterSupport(
        parameter="BLOWOUT_TREATMENT",
        support="RESEARCH_SUPPORTED",
        contamination="LOW",
        direction="mild",
        basis=(
            "Margins are observed directly; the proxy enters only through which games "
            "were expected to be lopsided. The two governed caps that already exist "
            "disagree — Baxter 49 points, SRS 24 — and both are measurable against real "
            "margins without an opening axis."
        ),
    ),
    ParameterSupport(
        parameter="RECENT_FORM",
        support="RESEARCH_SUPPORTED",
        contamination="LOWEST",
        direction="mild",
        basis=(
            "A within-season weighting over games. The opening state is the baseline for "
            "the first weeks only, and relative weights across a season are largely "
            "insensitive to it."
        ),
    ),
    ParameterSupport(
        parameter="SAMPLE_SIZE_REGULARIZATION",
        support="RESEARCH_SUPPORTED_WITH_A_SELECTION_DEFECT",
        contamination="LOW_FROM_THE_PROXY_HIGH_FROM_THE_CORPUS",
        direction="unquantified",
        basis=(
            "The proxy barely touches it. The corpus does: the observation set prunes "
            "team-seasons below eight admitted games, which removes exactly the "
            "small-sample cases this parameter governs. The defect is in the sample, not "
            "in the proxy, and it is the sharper of the two."
        ),
    ),
)

REFUSED_FOR_PROXY_CALIBRATION = tuple(
    p.parameter
    for p in PROXY_CALIBRATION_SUPPORT
    if p.support in ("REFUSED", "BOUND_ONLY")
)
RESEARCH_SUPPORTED_BY_PROXY = tuple(
    p.parameter
    for p in PROXY_CALIBRATION_SUPPORT
    if p.support.startswith("RESEARCH_SUPPORTED")
)


def require_proxy_admissible_parameter(parameter: str) -> ParameterSupport:
    """Fail closed on calibrating a parameter the proxy cannot carry."""
    key = parameter.strip().upper()
    for entry in PROXY_CALIBRATION_SUPPORT:
        if entry.parameter == key:
            if entry.support in ("REFUSED", "BOUND_ONLY"):
                raise GovernanceBlock(
                    f"{key} may not be calibrated against a historical opening proxy: "
                    f"{entry.contamination} contamination, {entry.direction}. {entry.basis}"
                )
            return entry
    raise InputValidationError(f"{parameter} is not a registered V3 calibration parameter")


# --- season coverage ----------------------------------------------------------


@dataclass(frozen=True)
class SeasonBackcast:
    opening_season: int
    prior_season: int
    constructible: bool
    reason: str


#: FACT — the R6 observation corpus admits 2021-2024; the 2020 census quoted
#: below is counted from bytes retrieved in this lane from the identical source
#: family, and is recorded in the lane artifact with its per-week digests.
SEASON_BACKCASTS: tuple[SeasonBackcast, ...] = (
    SeasonBackcast(
        2021,
        2020,
        False,
        "2020 is acquirable from the same NCAA feed but cannot supply a season-final "
        "state: under the corpus's own iterative eight-game floor the real 2020 "
        "FBS-versus-FBS season collapses from 489 games and 127 entities to 171 games "
        "and 38 entities, before any identity resolution.",
    ),
    SeasonBackcast(2022, 2021, True, "2021 final state available from the R6 corpus."),
    SeasonBackcast(2023, 2022, True, "2022 final state available from the R6 corpus."),
    SeasonBackcast(2024, 2023, True, "2023 final state available from the R6 corpus."),
)

CONSTRUCTIBLE_OPENINGS = tuple(
    s.opening_season for s in SEASON_BACKCASTS if s.constructible
)

PROXY_CLASS = "HISTORICAL_CALIBRATION_PROXY"
NOT_PROXY_CLASS = "EXACT_V3_PRESEASON_ENSEMBLE"


def classify(label: str) -> str:
    """Keep the two classes apart by name, in both directions."""
    normalised = label.strip().upper().replace(" ", "_")
    if normalised in (PROXY_CLASS, NOT_PROXY_CLASS):
        return normalised
    raise InputValidationError(
        f"{label!r} is neither {PROXY_CLASS} nor {NOT_PROXY_CLASS}; the distinction is "
        "the point of this lane and an unlabelled state collapses it."
    )


def require_proxy_not_presented_as_ensemble(label: str) -> None:
    """Refuse presenting the proxy as the 2026 opening ensemble."""
    if classify(label) == NOT_PROXY_CLASS:
        raise GovernanceBlock(
            "A historical backcast is not the exact V3 preseason ensemble. It rebuilds "
            f"{REPRODUCIBLE_FAMILY_WEIGHT:.2f} of the ensemble weight from one family, "
            "over a different population, from a different rating engine."
        )
