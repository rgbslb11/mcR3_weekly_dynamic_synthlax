"""Historical preseason opening-state reconstruction for seasons 2021-2024.

The expected-margin and calibration lanes both need a *pregame* team strength
for historical games. V3 has one and only one construction for such a state --
the preseason Unified Master Z built for 2026 -- so the question this module
exists to answer is narrow and answerable: can that construction be run again,
unchanged, against seasons 2021 through 2024?

Everything here is built around two facts established from bytes before a line
of it was written.

**The 2026 construction, verified rather than assumed.** The lane instruction
described it as "Unified Master Z with four family Z components" and a point
transform of ``14 x Z``. That description is correct, and this module
reproduces it exactly from :data:`V3_PRESEASON_FAMILIES`. Two details of it,
however, were only recoverable by recomputing the workbook:

* The standard deviation each family is standardized by is the **sample**
  standard deviation, ``ddof=1``. The workbook's own sheet calls that block
  "Population Statistics", and reading the label as a specification produces a
  different number for every team: over the 121-team field the ``ddof=0``
  deviation for TrueSkill is 4.3412374, and the value the workbook actually
  divides by is 4.3592884. Recomputing with ``ddof=1`` reproduces all published
  family Z values to within 1e-14; ``ddof=0`` reproduces none of them.
  :data:`STANDARDIZATION_DDOF` records the measured convention, not the
  documented one.
* The Board family is not a fifth standardized quantity. Board I-H and Board
  J-B are standardized **separately**, each against its own field mean and
  deviation, and the family value is the arithmetic mean of the two resulting Z
  scores. Standardizing an average of the two native ratings instead gives a
  different number, because the two natives have different deviations.

**The historical component sources do not exist.** All four families were
traced to their origins. Every one of them begins at the synthetic 2025 season
or later, and the two rating artifacts carrying a 2021-2024 label are
season-final fits over that season's own games. There is therefore no season in
2021-2024 for which any family can be reconstructed, let alone all four.

That result is what :data:`HISTORICAL_OPENING_STATE_SOURCE_REGISTER` records,
per candidate, with a digest and a refusal reason each.

Given that, this module could have been a paragraph. It is not, for a reason
that matters to the lanes waiting on it: **the blocker is evidence, not
method.** If a governed 2021-2024 component source is later mounted, the
question "what is the opening Unified Z" must not need re-deriving from a
spreadsheet a second time. So the construction is implemented, pinned by test
against the 2026 workbook's own published values, and left ready -- and the
reconstruction is then run for real against the actual evidence, where it
refuses every team-season and says why.

Four refusals are deliberate and load-bearing:

* **Same-season and post-season sources are rejected at registration**, not at
  review. A season-final rating is the strongest-looking historical artifact
  available and it is exactly the one that would silently destroy a calibration
  lane, because it has already seen the games the lane is trying to predict.
* **A partial component set never produces a combined value.**
  :func:`combine_unified_z` requires all four families and refuses otherwise.
  Averaging whichever families happen to be present rescales the result against
  an unstated population, and the number that comes out looks exactly like the
  number that would have come out if nothing were missing.
* **No football points are emitted.** ``14 x Z`` is the 2026 neutral-field
  scale; whether it is historically reusable belongs to the parallel
  expected-margin audit and is not decided here.
  :func:`candidate_points_if_14x_z` exists for QA only, refuses to run without
  an explicit opt-in, and stamps every value it returns unauthorised.
* **FCS opponents get no opening points**, from Elo 1250 or anything else.
  :func:`refuse_fcs_opening_points` raises. The adapter that would make such a
  conversion meaningful is a different lane's open item.

Nothing here promotes a parameter, retires a blocker, widens an allowlist,
writes canonical configuration, or runs a simulation.
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .errors import GovernanceBlock, InputValidationError, V3Error
from .textio import write_json_lf

__all__ = [
    "ADMISSIBLE_SOURCE_CLASSES",
    "BOARD_FAMILY_MEMBERS",
    "ComponentFamily",
    "ComponentObservation",
    "ComponentUnavailable",
    "FutureLeakageRefused",
    "HISTORICAL_OPENING_STATE_SOURCE_REGISTER",
    "HISTORICAL_POPULATION_CANDIDATES",
    "HISTORICAL_SEASONS",
    "HistoricalTeamIdentity",
    "LEAKAGE_REFUSED_CLASSES",
    "MISSING_REASONS",
    "OPENING_STATE_STATUSES",
    "OpeningStateError",
    "OpeningStatus",
    "PopulationCandidate",
    "PopulationDefinition",
    "REQUIRED_FAMILY_IDS",
    "RegisteredSource",
    "SOURCE_CLASSES",
    "STANDARDIZATION_DDOF",
    "StandardizationRecord",
    "TeamSeasonOpeningState",
    "V3_INDEX_CENTER",
    "V3_INDEX_SCALE",
    "V3_NEUTRAL_FIELD_POINT_SCALE",
    "V3_POINT_SCALE_HISTORICAL_AUTHORITY",
    "V3_PRESEASON_FAMILIES",
    "board_family_z",
    "build_coverage_report",
    "build_opening_unified_z_table",
    "build_population_manifest",
    "build_source_manifest",
    "build_standardization_manifest",
    "build_status_record",
    "build_team_season_component_table",
    "candidate_points_if_14x_z",
    "combine_unified_z",
    "population_mean_sd",
    "reconstruct_season",
    "reconstruct_team_season",
    "refuse_fcs_opening_points",
    "require_preseason_source",
    "resolve_population",
    "standardize_family",
    "unified_power_index",
    "verify_registered_source_bytes",
    "week1_2_opening_state_availability",
    "write_opening_state_artifacts",
]


# ---------------------------------------------------------------------------
# 1. Seasons and errors
# ---------------------------------------------------------------------------

#: The seasons this lane was asked to reconstruct.
HISTORICAL_SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024)


class OpeningStateError(V3Error):
    """Base error for historical opening-state reconstruction."""


class FutureLeakageRefused(OpeningStateError):
    """Raised when a source could not have been known before a season began.

    Separate from :class:`~.errors.InputValidationError` because it is not a
    statement that the input is malformed. The input is usually perfectly well
    formed; it is simply information from the future, and a reconstruction that
    accepts it produces a state that has already seen what it is predicting.
    """


class ComponentUnavailable(OpeningStateError):
    """Raised when a combined state is requested without a full component set."""


# ---------------------------------------------------------------------------
# 2. The verified 2026 construction
# ---------------------------------------------------------------------------

#: Divisor convention for family standardization: sample SD, ``ddof=1``.
#:
#: Measured, not documented. See the module docstring -- the workbook labels the
#: block "Population Statistics" and then divides by the sample deviation.
STANDARDIZATION_DDOF = 1

#: Master Power Index center: ``index = center + scale * Z``.
V3_INDEX_CENTER = 100.0

#: Master Power Index points per standard deviation.
V3_INDEX_SCALE = 10.0

#: 2026 neutral-field football points per standard deviation.
#:
#: Recorded so the construction is complete, and applied to no historical
#: season. See :data:`V3_POINT_SCALE_HISTORICAL_AUTHORITY`.
V3_NEUTRAL_FIELD_POINT_SCALE = 14.0

#: Whether ``14 x Z`` may be reused for a historical season. It may not, here.
#:
#: The 2026 workbook describes the value as "Initial points per standard
#: deviation; recalibrate against game margins", which is a statement that the
#: scale is provisional even for the season it was built for. Reusing it across
#: seasons is a strictly larger claim, and it belongs to the expected-margin
#: audit rather than to this lane.
V3_POINT_SCALE_HISTORICAL_AUTHORITY = "UNRATIFIED_FOR_HISTORICAL_REUSE"

#: The two board artifacts that are standardized separately, then averaged.
BOARD_FAMILY_MEMBERS: tuple[str, ...] = ("BOARD_I_H", "BOARD_J_B")


@dataclass(frozen=True)
class ComponentFamily:
    """One weighted family of the V3 preseason ensemble.

    ``members`` is empty for a family standardized directly from a single
    native field, and populated for a family whose value is the mean of several
    separately standardized members.
    """

    family_id: str
    weight: float
    role: str
    native_field_2026: str
    directionality: str = "HIGHER_IS_STRONGER"
    members: tuple[str, ...] = ()

    @property
    def is_composite(self) -> bool:
        return bool(self.members)


#: The four families, their governed weights, and the 2026 fields they read.
V3_PRESEASON_FAMILIES: tuple[ComponentFamily, ...] = (
    ComponentFamily(
        family_id="TRUESKILL",
        weight=0.25,
        role="Results-based latent strength",
        native_field_2026="TrueSkill 2026 Preseason mu",
    ),
    ComponentFamily(
        family_id="LITKENHOUS",
        weight=0.25,
        role="Forward-looking offseason-adjusted power",
        native_field_2026="Litkenhous Adjusted Power",
    ),
    ComponentFamily(
        family_id="PURE_BAXTER",
        weight=0.25,
        role="Margin-based results carry-forward",
        native_field_2026="2026 Pure Baxter Rating",
    ),
    ComponentFamily(
        family_id="BOARD_FAMILY",
        weight=0.25,
        role="Forward-looking component family",
        native_field_2026="Average of standardized Board I-H and Board J-B",
        members=BOARD_FAMILY_MEMBERS,
    ),
)

#: Family ids that must all be present before a combined state exists.
REQUIRED_FAMILY_IDS: tuple[str, ...] = tuple(f.family_id for f in V3_PRESEASON_FAMILIES)


def _require_weights_sum_to_one() -> None:
    total = sum(f.weight for f in V3_PRESEASON_FAMILIES)
    if abs(total - 1.0) > 1e-12:
        raise GovernanceBlock(f"V3 preseason family weights sum to {total!r}, not 1.0")


_require_weights_sum_to_one()


# ---------------------------------------------------------------------------
# 3. Source classification and the leakage boundary
# ---------------------------------------------------------------------------

#: How a candidate source relates in time to the season it would describe.
SOURCE_CLASSES: tuple[str, ...] = (
    # Published before the season's first game. The only admissible class.
    "PRESEASON_SOURCE",
    # Fitted to, or derived from, games in the season being reconstructed.
    "SAME_SEASON_DERIVED",
    # Includes postseason results, final polls, or end-of-season ratings.
    "POSTSEASON_DERIVED",
    # A rating for a later season, however it was built.
    "FUTURE_SEASON_DERIVED",
    # A season-final rating: same-season leakage in its strongest form.
    "SEASON_FINAL_RATING",
    # Membership and division, which are settled before a season starts.
    "MEMBERSHIP_DECLARATION",
    # Nobody has classified it. Refused precisely because nobody has checked.
    "UNKNOWN",
)

#: The classes a component *value* may be read from.
#:
#: ``MEMBERSHIP_DECLARATION`` is deliberately not here. Membership is
#: leakage-clean and can define a population, but a conference table is not a
#: strength measurement and must never be read as one.
ADMISSIBLE_SOURCE_CLASSES: tuple[str, ...] = ("PRESEASON_SOURCE",)

#: Classes refused specifically because they postdate the season's first game.
LEAKAGE_REFUSED_CLASSES: tuple[str, ...] = (
    "SAME_SEASON_DERIVED",
    "POSTSEASON_DERIVED",
    "FUTURE_SEASON_DERIVED",
    "SEASON_FINAL_RATING",
)

#: Reasons a team-season may lack an opening state. Every gap carries one.
MISSING_REASONS: tuple[str, ...] = (
    "MISSING_SOURCE",
    "INSUFFICIENT_COMPONENTS",
    "HISTORICAL_ENTITY_UNRESOLVED",
    "OUTSIDE_POPULATION",
    "OTHER_EXPLICIT_REASON",
)


class OpeningStatus:
    """Reconstruction status values, per team-season."""

    FULLY_RECONSTRUCTED = "FULLY_RECONSTRUCTED"
    PARTIALLY_RECONSTRUCTED = "PARTIALLY_RECONSTRUCTED"
    UNAVAILABLE = "UNAVAILABLE"


#: The three statuses, as a tuple, for validation and reporting.
OPENING_STATE_STATUSES: tuple[str, ...] = (
    OpeningStatus.FULLY_RECONSTRUCTED,
    OpeningStatus.PARTIALLY_RECONSTRUCTED,
    OpeningStatus.UNAVAILABLE,
)


@dataclass(frozen=True)
class RegisteredSource:
    """A candidate opening-state source, examined and classified.

    ``sha256`` and ``size_bytes`` are recorded from the bytes at discovery.
    They are re-derivable by :func:`verify_registered_source_bytes` wherever the
    bytes are present, and honestly reported as absent where they are not: this
    lane's candidates live outside the repository, and a digest nobody can check
    is a claim rather than evidence.
    """

    source_id: str
    location: str
    sha256: str
    size_bytes: int
    seasons_declared: tuple[int, ...]
    source_class: str
    provides_families: tuple[str, ...]
    admissible: bool
    disposition: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.source_class not in SOURCE_CLASSES:
            raise InputValidationError(
                f"{self.source_id}: unknown source class {self.source_class!r}"
            )
        if self.admissible and self.source_class not in ADMISSIBLE_SOURCE_CLASSES:
            raise GovernanceBlock(
                f"{self.source_id}: class {self.source_class} is never admissible "
                "for a component value"
            )
        for family in self.provides_families:
            if family not in REQUIRED_FAMILY_IDS and family not in BOARD_FAMILY_MEMBERS:
                raise InputValidationError(f"{self.source_id}: unknown family {family!r}")


def require_preseason_source(source: RegisteredSource, season: int) -> RegisteredSource:
    """Return ``source`` if it may supply a component value for ``season``.

    Refuses on three separate grounds, checked in order, because they are
    different findings and collapsing them would hide which one applied: the
    class postdates kickoff; the class is not one that may carry a strength
    value at all; or the source does not cover the season asked for.
    """
    if source.source_class in LEAKAGE_REFUSED_CLASSES:
        raise FutureLeakageRefused(
            f"{source.source_id} is {source.source_class} and cannot supply a "
            f"{season} opening state"
        )
    if source.source_class not in ADMISSIBLE_SOURCE_CLASSES:
        raise GovernanceBlock(
            f"{source.source_id} has class {source.source_class}, which may not "
            "supply a component value"
        )
    if season not in source.seasons_declared:
        raise InputValidationError(f"{source.source_id} does not declare season {season}")
    return source


def verify_registered_source_bytes(
    source: RegisteredSource, *, search_root: Path | None = None
) -> dict[str, object]:
    """Re-hash ``source`` where its bytes are present; report honestly when not.

    ``search_root`` exists so a test can point the check at a fixture rather
    than at a machine-specific absolute path. When the bytes are absent the
    result is ``BYTES_NOT_PRESENT`` -- never a pass, and never an error either,
    because the register is the record of a search and some of what it records
    is correctly no longer here.
    """
    candidate = Path(source.location)
    if search_root is not None:
        candidate = search_root / Path(source.location).name
    if not candidate.exists() or not candidate.is_file():
        return {
            "source_id": source.source_id,
            "verification": "BYTES_NOT_PRESENT",
            "recorded_sha256": source.sha256,
            "observed_sha256": None,
        }
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    observed = digest.hexdigest()
    return {
        "source_id": source.source_id,
        "verification": "BYTES_MATCH" if observed == source.sha256 else "BYTES_DIFFER",
        "recorded_sha256": source.sha256,
        "observed_sha256": observed,
    }


# ---------------------------------------------------------------------------
# 4. Historical team identity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoricalTeamIdentity:
    """A team as it existed in one historical season.

    Two axes are kept strictly apart, because conflating them is the specific
    error that would make a historical reconstruction quietly wrong:

    ``division`` is the team's division **in that season**. It is the axis a
    population is defined over.

    ``canonical_schedule_id`` is the synthetic 2026 universe's identifier, when
    the entity binds to one. It is identity metadata only. The 2026 master
    classifies real FBS programs as schedule-only FCS and real FCS programs as
    FBS members, so its labels are facts about a synthetic 2026 season and are
    never reported as the division of a historical team.

    An entity that does not bind to the 2026 master is still a real historical
    program and is preserved with ``canonical_binding`` set to
    ``UNBOUND_HISTORICAL_ENTITY``. Dropping it would shrink the population
    silently, which changes every mean and every standard deviation computed
    over that population.
    """

    season: int
    historical_key: str
    historical_name: str
    division: str
    conference: str | None = None
    canonical_schedule_id: str | None = None
    canonical_binding: str = "UNBOUND_HISTORICAL_ENTITY"
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.canonical_schedule_id is None and self.canonical_binding not in (
            "UNBOUND_HISTORICAL_ENTITY",
            "OUT_OF_CANONICAL_UNIVERSE",
        ):
            raise InputValidationError(
                f"{self.historical_key}: binding {self.canonical_binding} claims a "
                "canonical id but none was supplied"
            )


# ---------------------------------------------------------------------------
# 5. Population definition
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PopulationCandidate:
    """One source's statement of who was in a season's population.

    Recorded per candidate rather than merged, because when two candidates
    disagree the disagreement is the finding. Merging them would produce a
    count that no source asserts.
    """

    population_id: str
    season: int
    source_id: str
    scope: str
    count: int
    basis: str


@dataclass(frozen=True)
class PopulationDefinition:
    """The resolved population a season's Z scores are computed over.

    ``status`` is ``RESOLVED`` only when exactly one candidate scope survives.
    When candidates disagree it is ``UNRESOLVED_CONFLICTING_CANDIDATES`` and
    ``included`` is empty: a Z score computed over a population nobody has
    ratified is a number with no defined meaning, and emitting one under a
    caveat is how the caveat gets lost.
    """

    season: int
    population_id: str
    scope: str
    status: str
    included: tuple[str, ...]
    excluded: tuple[tuple[str, str], ...]
    candidates: tuple[PopulationCandidate, ...]
    source_ids: tuple[str, ...] = ()

    @property
    def count(self) -> int:
        return len(self.included)

    def require_resolved(self) -> "PopulationDefinition":
        if self.status != "RESOLVED":
            raise GovernanceBlock(
                f"{self.season} population is {self.status}; candidate counts "
                + ", ".join(f"{c.population_id}={c.count}" for c in self.candidates)
            )
        return self


def resolve_population(
    season: int,
    candidates: Sequence[PopulationCandidate],
    *,
    scope: str,
    mounted_source_ids: Sequence[str] = (),
) -> PopulationDefinition:
    """Resolve a season's population from the candidate statements available.

    Deliberately conservative, and gated on ``mounted_source_ids`` rather than
    on candidate count alone. A lone candidate is not an authority merely by
    being lonely: the one located historical membership table names an upstream
    that is not on this filesystem, so nothing has ratified the scope it
    declares. A season resolves only when exactly one candidate is in scope
    *and* its source has been mounted.

    Three unresolved states are distinguished because they call for different
    remedies: no candidate at all needs a source found, an unmounted candidate
    needs a lineage closed, and conflicting candidates need a ruling. Picking
    the larger, the smaller or the more recent of two disagreeing candidates
    would each be defensible in isolation and none of them is a source fact, so
    none of them is done here.
    """
    mounted = set(mounted_source_ids)
    in_scope = tuple(c for c in candidates if c.season == season and c.scope == scope)
    admitted = tuple(c for c in in_scope if c.source_id in mounted)
    # Mounting one of two disagreeing candidates does not settle the
    # disagreement, it only picks a side. A conflict is resolved by a ruling
    # about which source governs, never by which one happened to be mounted.
    if len(in_scope) == 1 and len(admitted) == 1:
        only = admitted[0]
        return PopulationDefinition(
            season=season,
            population_id=only.population_id,
            scope=scope,
            status="RESOLVED",
            included=(),
            excluded=(),
            candidates=in_scope,
            source_ids=(only.source_id,),
        )
    if not in_scope:
        status = "UNRESOLVED_NO_CANDIDATE"
    elif len(in_scope) > 1:
        status = "UNRESOLVED_CONFLICTING_CANDIDATES"
    elif not admitted:
        status = "UNRESOLVED_SOURCE_NOT_MOUNTED"
    else:
        status = "UNRESOLVED_CONFLICTING_CANDIDATES"
    return PopulationDefinition(
        season=season,
        population_id=f"{scope}_{season}_UNRESOLVED",
        scope=scope,
        status=status,
        included=(),
        excluded=(),
        candidates=in_scope,
        source_ids=tuple(sorted({c.source_id for c in in_scope})),
    )


# ---------------------------------------------------------------------------
# 6. Standardization
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StandardizationRecord:
    """Everything needed to recompute one family's Z scores from its natives."""

    family_id: str
    season: int
    population_id: str
    formula: str
    mean: float
    standard_deviation: float
    ddof: int
    n: int
    directionality: str
    missing_value_handling: str
    native_field: str


def population_mean_sd(values: Sequence[float], *, ddof: int = STANDARDIZATION_DDOF):
    """Return ``(mean, sd)`` over ``values`` using the V3 divisor convention.

    Refuses a degenerate population rather than returning a value that cannot
    be divided by. Two of the three refusals here are not hypothetical: the one
    leak-free season-opening rating state found on this filesystem is a flat Elo
    of 1500 for every team, which has zero deviation, and standardizing it would
    have produced ``ZeroDivisionError`` or, worse, silently produced zeros that
    read as "every team is exactly average".
    """
    if len(values) < 2:
        raise InputValidationError(
            f"standardization needs at least 2 observations, got {len(values)}"
        )
    if len(values) - ddof < 1:
        raise InputValidationError(
            f"standardization with ddof={ddof} needs more than {ddof} observations"
        )
    mean = statistics.fmean(values)
    sd = statistics.stdev(values) if ddof == 1 else statistics.pstdev(values)
    if sd == 0.0:
        raise InputValidationError(
            "standardization refused: the population has zero dispersion, so no "
            "team differs from the mean and every Z score would be 0.0"
        )
    return mean, sd


def standardize_family(
    family_id: str,
    season: int,
    population_id: str,
    native_values: Mapping[str, float],
    *,
    native_field: str,
    directionality: str = "HIGHER_IS_STRONGER",
    ddof: int = STANDARDIZATION_DDOF,
):
    """Standardize one family's native values over its own population.

    Returns ``(record, z_by_team)``. The native values are not consumed or
    replaced: the caller keeps them, and :class:`ComponentObservation` carries
    both. A standardized value alone cannot be re-standardized against a
    different population later, which is exactly what a lane that changes its
    population definition will need to do.

    Missing values are not imputed. A team absent from ``native_values`` is
    absent from the returned mapping and from the mean and deviation, and the
    record says so.
    """
    if directionality not in ("HIGHER_IS_STRONGER", "LOWER_IS_STRONGER"):
        raise InputValidationError(f"unknown directionality {directionality!r}")
    ordered = sorted(native_values.items())
    values = [float(v) for _, v in ordered]
    mean, sd = population_mean_sd(values, ddof=ddof)
    sign = 1.0 if directionality == "HIGHER_IS_STRONGER" else -1.0
    z_by_team = {team: sign * (float(value) - mean) / sd for team, value in ordered}
    record = StandardizationRecord(
        family_id=family_id,
        season=season,
        population_id=population_id,
        formula=(
            "z = (x - mean) / sd"
            if sign > 0
            else "z = -(x - mean) / sd"
        ),
        mean=mean,
        standard_deviation=sd,
        ddof=ddof,
        n=len(values),
        directionality=directionality,
        missing_value_handling=(
            "EXCLUDED_FROM_POPULATION_AND_NOT_IMPUTED: a team without a native "
            "value contributes to neither the mean nor the deviation and receives "
            "no standardized value"
        ),
        native_field=native_field,
    )
    return record, z_by_team


# ---------------------------------------------------------------------------
# 7. Combination and the point transforms
# ---------------------------------------------------------------------------


def board_family_z(member_z: Mapping[str, float]) -> float:
    """Mean of the separately standardized board members.

    Refuses a partial board. One member standing in for two is a different
    estimator with a different variance, and nothing downstream would be able to
    tell the two apart from the value alone.
    """
    missing = [m for m in BOARD_FAMILY_MEMBERS if m not in member_z]
    if missing:
        raise ComponentUnavailable(
            f"board family needs {list(BOARD_FAMILY_MEMBERS)}; missing {missing}"
        )
    return statistics.fmean(float(member_z[m]) for m in BOARD_FAMILY_MEMBERS)


def combine_unified_z(family_z: Mapping[str, float]) -> float:
    """Weighted Unified Master Z from a complete set of family Z scores.

    Fails closed. Every one of :data:`REQUIRED_FAMILY_IDS` must be present; a
    subset is refused rather than renormalized. Renormalizing over the present
    families returns a plausible number computed against a population that was
    never stated, and it is indistinguishable at the call site from a complete
    result.
    """
    missing = [f for f in REQUIRED_FAMILY_IDS if f not in family_z]
    if missing:
        raise ComponentUnavailable(
            f"unified Z needs all of {list(REQUIRED_FAMILY_IDS)}; missing {missing}"
        )
    unknown = [f for f in family_z if f not in REQUIRED_FAMILY_IDS]
    if unknown:
        raise InputValidationError(f"unknown families supplied to unified Z: {unknown}")
    return sum(family.weight * float(family_z[family.family_id]) for family in V3_PRESEASON_FAMILIES)


def unified_power_index(unified_z: float) -> float:
    """Master Power Index: ``100 + 10 * Z``.

    Unit-free by construction -- an index, not football points -- so it is safe
    to emit for any season whose Z is defined. It is the one derived quantity
    this lane will produce without a governance gate.
    """
    return V3_INDEX_CENTER + V3_INDEX_SCALE * float(unified_z)


def candidate_points_if_14x_z(unified_z: float, *, research_only: bool = False) -> dict[str, object]:
    """Illustrative ``14 x Z``, for QA only, never as an authorised value.

    The keyword is required and must be passed explicitly. That is not
    ceremony: the whole risk with this function is that a number produced for a
    QA eyeball gets copied into a table, and a value that can only be obtained
    by writing ``research_only=True`` at the call site cannot be obtained by
    accident. The return is a dict rather than a float for the same reason --
    the authority stamp travels with the number instead of being left behind at
    the boundary.
    """
    if not research_only:
        raise GovernanceBlock(
            "candidate_points_if_14x_z is research-only; the historical "
            "authority of the 14x scale belongs to the expected-margin audit. "
            "Pass research_only=True to obtain an explicitly unauthorised value."
        )
    return {
        "candidate_points_if_14xZ": V3_NEUTRAL_FIELD_POINT_SCALE * float(unified_z),
        "scale": V3_NEUTRAL_FIELD_POINT_SCALE,
        "authority": V3_POINT_SCALE_HISTORICAL_AUTHORITY,
        "status": "NON_AUTHORIZED_RESEARCH_ONLY",
        "usable_as_v3_football_points": False,
    }


def refuse_fcs_opening_points(team_key: str, *, elo: float = 1250.0) -> None:
    """Always raise. FCS opponents receive no unified-point opening strength.

    Elo 1250 is a rating on a foreign scale with no ratified mapping into V3
    points. Converting it would require choosing that mapping, which is the
    open item ``model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER`` and not
    this lane's to choose. The FCS entity itself is preserved -- it is a real
    participant in real games -- it simply has no point strength here.
    """
    raise GovernanceBlock(
        f"{team_key}: refusing to derive V3 opening points from FCS Elo {elo}. "
        "The FCS-to-unified-point adapter is unresolved; the entity is retained "
        "without a point strength."
    )


# ---------------------------------------------------------------------------
# 8. Team-season reconstruction
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ComponentObservation:
    """One family value for one team-season, native and standardized together.

    ``native_value`` is never discarded. ``standardized_value`` is ``None``
    until a population exists to standardize against, which for this lane it
    never does.
    """

    season: int
    team_key: str
    family_id: str
    native_value: float | None
    native_source_id: str | None
    standardized_value: float | None = None
    status: str = "MISSING_SOURCE"


@dataclass(frozen=True)
class TeamSeasonOpeningState:
    """The opening state for one team in one season, or the reason there is none."""

    season: int
    team_key: str
    identity: HistoricalTeamIdentity
    native_inputs: tuple[tuple[str, float | None], ...]
    standardized_components: tuple[tuple[str, float | None], ...]
    board_family_z: float | None
    opening_unified_z: float | None
    included_family_count: int
    status: str
    missing_reasons: tuple[tuple[str, str], ...]
    population_id: str
    confidence: str

    def __post_init__(self) -> None:
        if self.status not in OPENING_STATE_STATUSES:
            raise InputValidationError(f"unknown opening status {self.status!r}")
        if self.status == OpeningStatus.FULLY_RECONSTRUCTED and self.opening_unified_z is None:
            raise InputValidationError(
                f"{self.team_key} {self.season}: FULLY_RECONSTRUCTED without a "
                "unified Z"
            )
        if self.status != OpeningStatus.FULLY_RECONSTRUCTED and self.opening_unified_z is not None:
            raise InputValidationError(
                f"{self.team_key} {self.season}: a unified Z was produced without "
                "a complete component set"
            )
        for reason, _ in self.missing_reasons:
            if reason not in MISSING_REASONS:
                raise InputValidationError(f"unknown missing reason {reason!r}")


def reconstruct_team_season(
    identity: HistoricalTeamIdentity,
    population: PopulationDefinition,
    observations: Sequence[ComponentObservation],
    *,
    standardized: Mapping[str, float] | None = None,
) -> TeamSeasonOpeningState:
    """Build one team-season opening state, or refuse it with reasons.

    The order of the gates is the order in which the answers stop being useful.
    A team outside the population has no population to be standardized against,
    so asking which of its components are present is meaningless; an unresolved
    population makes the same question meaningless for every team at once.
    """
    natives = tuple(sorted((o.family_id, o.native_value) for o in observations))
    reasons: list[tuple[str, str]] = []

    if population.status != "RESOLVED":
        reasons.append(
            (
                "OTHER_EXPLICIT_REASON",
                f"season population is {population.status}: "
                + ", ".join(f"{c.population_id}={c.count}" for c in population.candidates),
            )
        )
    if identity.canonical_binding == "UNBOUND_HISTORICAL_ENTITY":
        reasons.append(
            (
                "HISTORICAL_ENTITY_UNRESOLVED",
                f"{identity.historical_name} does not bind to the canonical master; "
                "retained in the population, not silently dropped",
            )
        )

    present = {o.family_id for o in observations if o.native_value is not None}
    absent = [f for f in REQUIRED_FAMILY_IDS if f not in present]
    if absent:
        reasons.append(
            (
                "INSUFFICIENT_COMPONENTS" if present else "MISSING_SOURCE",
                "no preseason source supplies " + ", ".join(absent),
            )
        )

    std_map = dict(standardized or {})
    if reasons or not std_map:
        return TeamSeasonOpeningState(
            season=identity.season,
            team_key=identity.historical_key,
            identity=identity,
            native_inputs=natives,
            standardized_components=tuple(sorted((f, None) for f in REQUIRED_FAMILY_IDS)),
            board_family_z=None,
            opening_unified_z=None,
            included_family_count=len(present),
            status=(
                OpeningStatus.PARTIALLY_RECONSTRUCTED
                if present
                else OpeningStatus.UNAVAILABLE
            ),
            missing_reasons=tuple(reasons),
            population_id=population.population_id,
            confidence="NONE",
        )

    unified = combine_unified_z(std_map)
    return TeamSeasonOpeningState(
        season=identity.season,
        team_key=identity.historical_key,
        identity=identity,
        native_inputs=natives,
        standardized_components=tuple(sorted(std_map.items())),
        board_family_z=std_map.get("BOARD_FAMILY"),
        opening_unified_z=unified,
        included_family_count=len(REQUIRED_FAMILY_IDS),
        status=OpeningStatus.FULLY_RECONSTRUCTED,
        missing_reasons=(),
        population_id=population.population_id,
        confidence="HIGH",
    )


def reconstruct_season(
    season: int,
    population: PopulationDefinition,
    identities: Sequence[HistoricalTeamIdentity],
    observations_by_team: Mapping[str, Sequence[ComponentObservation]],
) -> tuple[TeamSeasonOpeningState, ...]:
    """Reconstruct every team-season in one season, in deterministic key order."""
    if population.season != season:
        raise InputValidationError(
            f"population is for {population.season}, not {season}"
        )
    out = []
    for identity in sorted(identities, key=lambda i: i.historical_key):
        if identity.season != season:
            raise InputValidationError(
                f"{identity.historical_key} is a {identity.season} identity in a "
                f"{season} reconstruction"
            )
        out.append(
            reconstruct_team_season(
                identity,
                population,
                tuple(observations_by_team.get(identity.historical_key, ())),
            )
        )
    return tuple(out)


# ---------------------------------------------------------------------------
# 9. Week 1 / Week 2 readiness
# ---------------------------------------------------------------------------


def week1_2_opening_state_availability(
    states: Sequence[TeamSeasonOpeningState],
    games: Sequence[Mapping[str, object]],
    *,
    weeks: tuple[int, ...] = (1, 2),
) -> dict[str, object]:
    """Count Weeks 1-2 games where **both** participants have an opening state.

    V3 governance runs Weeks 1 and 2 off preseason opening strength and promotes
    the first rerating after Week 2, so this count is the size of the cleanest
    early-season calibration subset obtainable without any in-season state.

    ``both_states`` counts only ``FULLY_RECONSTRUCTED`` participants.
    A partially reconstructed team has no unified Z, so a game involving one
    cannot yield an expected margin, and counting it would overstate the subset.
    """
    usable = {
        s.team_key
        for s in states
        if s.status == OpeningStatus.FULLY_RECONSTRUCTED and s.opening_unified_z is not None
    }
    in_window = [g for g in games if int(g["week"]) in weeks]
    both = 0
    one = 0
    neither = 0
    for game in in_window:
        have = sum(1 for side in ("home_team", "away_team") if game.get(side) in usable)
        if have == 2:
            both += 1
        elif have == 1:
            one += 1
        else:
            neither += 1
    return {
        "weeks": list(weeks),
        "games_in_window": len(in_window),
        "both_states": both,
        "exactly_one_state": one,
        "neither_state": neither,
        "teams_with_opening_state": len(usable),
    }


# ---------------------------------------------------------------------------
# 10. The evidence register
# ---------------------------------------------------------------------------
#
# Every candidate that could conceivably carry a 2021-2024 preseason strength
# for a V3 family, with the digest it hashed to when it was read and the reason
# it is or is not admissible. The register is the finding of this lane; the
# machinery above is what will consume a replacement for it.
#
# Locations are absolute and machine-specific on purpose. They are where the
# bytes were, and :func:`verify_registered_source_bytes` will say so plainly on
# a machine where they are not.

HISTORICAL_OPENING_STATE_SOURCE_REGISTER: tuple[RegisteredSource, ...] = (
    RegisteredSource(
        source_id="V3_UNIFIED_PRESEASON_RATINGS_2026",
        location=(
            "reference/dynamic_weekly_mc_v3/inputs/"
            "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx"
        ),
        sha256="4b2535459ec069b8dc16edb64a90df694562746035279f961aa8f73530807a4a",
        size_bytes=113260,
        seasons_declared=(2026,),
        source_class="FUTURE_SEASON_DERIVED",
        provides_families=("TRUESKILL", "LITKENHOUS", "PURE_BAXTER", "BOARD_I_H", "BOARD_J_B"),
        admissible=False,
        disposition="REFUSED_FUTURE_SEASON",
        evidence=(
            "This is the construction being mirrored, not a source for it. Its "
            "121 rows are 2026 preseason states.",
            "Ensemble Parameters sheet fixes the four weights at 0.25 each and "
            "the board family as the average of standardized I-H and J-B.",
            "Recomputation over its 121 rows reproduces every published family Z "
            "with ddof=1 and none with ddof=0.",
        ),
    ),
    RegisteredSource(
        source_id="TRUESKILL_2025_2026_THREAD_CONSOLIDATION",
        location="C:/Users/dbaxt/Downloads/Operation_Sythalax_TrueSkill_2025_2026_Thread_Consolidation.xlsx",
        sha256="4b7d84d8a4b626c7f207162cb8748268d4d3f2608e41cba376a4272c6c7dfc79",
        size_bytes=555190,
        seasons_declared=(2025, 2026),
        source_class="FUTURE_SEASON_DERIVED",
        provides_families=("TRUESKILL",),
        admissible=False,
        disposition="REFUSED_NO_PRE_2025_STATE_EXISTS",
        evidence=(
            "Sheet '21 2026 P0 Params' records population_mu 25 and "
            "population_sigma 8.333333 as the *initial* prior; the TrueSkill "
            "chain is initialised there, not carried in from an earlier season.",
            "Sheet '14 2025 Rating History' shows every 2025 Week 1 row with "
            "pregame_mu 25 and pregame_sigma 8.333333 for both participants, so "
            "the 2025 season opened with an equal prior for all teams.",
            "The 2026 carryover formula 'mu_2026 = 25 + 0.70 * (mu_2025 - 25)' "
            "consumes a 2025 posterior. No 2020-2023 posterior exists to feed an "
            "equivalent 2021-2024 transition.",
        ),
    ),
    RegisteredSource(
        source_id="LITKENHOUS_2026_PRESEASON_THREE_LAYER",
        location="C:/Users/dbaxt/Downloads/2026_Synthetic_FBS_Litkenhous_Preseason_Three_Layer.xlsx",
        sha256="5ad5125a306601eeca67a3750c7fa8e556a5c8bdb8680f5031b6818e86ff37db",
        size_bytes=101165,
        seasons_declared=(2026,),
        source_class="FUTURE_SEASON_DERIVED",
        provides_families=("LITKENHOUS",),
        admissible=False,
        disposition="REFUSED_FUTURE_SEASON",
        evidence=(
            "Methodology sheet: pure carryover is '60% of each team's 2025 "
            "Litkenhous power margin after recentering the 2026 field'.",
            "Inputs and Lineage sheet names exactly one rating input, the 2025 "
            "final ratings. The Litkenhous chain has no season before 2025.",
        ),
    ),
    RegisteredSource(
        source_id="LITKENHOUS_2025_FINAL_RATINGS",
        location="C:/Users/dbaxt/Downloads/2025_Synthetic_CFB_Litkenhous_Inspired_Final_Ratings.xlsx",
        sha256="716151059052d30b24cffe90b22f30a5d2c9a9df66cc5a5877b38527773d6708",
        size_bytes=100546,
        seasons_declared=(2025,),
        source_class="SEASON_FINAL_RATING",
        provides_families=("LITKENHOUS",),
        admissible=False,
        disposition="REFUSED_SEASON_FINAL_AND_OUT_OF_SCOPE",
        evidence=(
            "A 2025 season-final rating. Out of the 2021-2024 scope in any case, "
            "and a season-final value is same-season information for 2025.",
        ),
    ),
    RegisteredSource(
        source_id="BOARD_I_H_V2_2026",
        location="C:/Users/dbaxt/Downloads/2026_Board_I-H_v2.xlsx",
        sha256="278701fc8e8ef62f992cf9f04f2ddddb6ba15c428cbd833a7bd14babf62b2213",
        size_bytes=17442,
        seasons_declared=(2026,),
        source_class="FUTURE_SEASON_DERIVED",
        provides_families=("BOARD_I_H",),
        admissible=False,
        disposition="REFUSED_FUTURE_SEASON",
        evidence=(
            "A 2026 board. The board series (I-H, I-I, I-K, J-A, J-B, J-C) is "
            "2026-only across every located artifact; no 2021-2024 board exists.",
        ),
    ),
    RegisteredSource(
        source_id="BOARD_J_B_RUN2_2026",
        location="C:/Users/dbaxt/Downloads/2026_Board_J-B_Run2.xlsx",
        sha256="bcec6150b9bf46b9cee2fb8accb3f0a7875848d09983a5b2e0a17374d6df46aa",
        size_bytes=31394,
        seasons_declared=(2026,),
        source_class="FUTURE_SEASON_DERIVED",
        provides_families=("BOARD_J_B",),
        admissible=False,
        disposition="REFUSED_FUTURE_SEASON",
        evidence=("A 2026 board run. Same series, same absence of history.",),
    ),
    RegisteredSource(
        source_id="BAXTER_RATINGS_2024_SEASON_FINAL",
        location=(
            "C:/Local-mcR3_calibration_staging/"
            "Baxter_v1_2006_2011_2024_2025_Complete_Package/Baxter_Ratings_2024.csv"
        ),
        sha256="b7d3e08490a68f2cd8dd4a08312a639a2622b7ea3dbd05d262939a419863920b",
        size_bytes=15652,
        seasons_declared=(2024,),
        source_class="SEASON_FINAL_RATING",
        provides_families=("PURE_BAXTER",),
        admissible=False,
        disposition="REFUSED_SAME_SEASON_FIT",
        evidence=(
            "The single most tempting artifact in this register: it carries a "
            "2024 label and a Baxter rating, which is two of the four families' "
            "worth of shape at a glance.",
            "It is a ridge fit over 2024's own games. Its header carries a "
            "'games' column and its first rows read 'Notre Dame ... 14' and "
            "'Ohio State ... 12' -- game counts only obtainable after the season.",
            "A 2024 *preseason* Pure Baxter would have to carry forward a 2023 "
            "fit, in the way the 2026 value carries forward 2025. The package "
            "covers 2006-2011, 2024 and 2025; there is no 2020, 2021, 2022 or "
            "2023 fit to carry forward.",
        ),
    ),
    RegisteredSource(
        source_id="BAXTER_V1_COMPLETE_METRICS",
        location=(
            "C:/Local-mcR3_calibration_staging/"
            "Baxter_v1_2006_2011_2024_2025_Complete_Package/Baxter_v1_complete_metrics.csv"
        ),
        sha256="6603ac9d8be1105ca31a9ddf7f09936e8acba72d39846d2f9df054ea43095996",
        size_bytes=1429,
        seasons_declared=(2006, 2007, 2008, 2009, 2010, 2011, 2024, 2025),
        source_class="POSTSEASON_DERIVED",
        provides_families=("PURE_BAXTER",),
        admissible=False,
        disposition="REFUSED_COVERAGE_EVIDENCE_ONLY",
        evidence=(
            "Registered for what it proves about coverage rather than for a "
            "value: its eight season rows are 2006-2011, 2024 and 2025, which "
            "is the whole Baxter universe and contains no 2021, 2022 or 2023.",
        ),
    ),
    RegisteredSource(
        source_id="PHASE5J_2024_FACT_RATINGS_PACKAGE",
        location="C:/Users/dbaxt/Downloads/Power_Crunch_Research_Lab_Phase5J_2024_FACT_Ratings_Package.zip",
        sha256="9788d1a70481d4027a916a92c4d5463b6f6d3fb553705e31d72797939e9d6a49",
        size_bytes=143786,
        seasons_declared=(2024,),
        provides_families=(),
        source_class="SAME_SEASON_DERIVED",
        admissible=False,
        disposition="REFUSED_SAME_SEASON_DERIVED",
        evidence=(
            "00_Control/season_config_2024.json declares season_status COMPLETE, "
            "include_postseason true, and calculation_cutoff_date 2025-01-31.",
            "The same file declares preseason_prior false and "
            "previous_season_carryover false: the ratings are built from the "
            "season's own game ledger and from nothing that predates it.",
            "Not a V3 family in any case. FACT is a separate rating system.",
        ),
    ),
    RegisteredSource(
        source_id="PHASE5M_2024_CPI_RATINGS_PACKAGE",
        location="C:/Users/dbaxt/Downloads/Power_Crunch_Research_Lab_Phase5M_2024_CPI_Ratings_Package.zip",
        sha256="3c1276ffe4a614d57137e13467957d2aceac0ae72fed32d0bac62192beda0880",
        size_bytes=106700,
        seasons_declared=(2024,),
        provides_families=(),
        source_class="SAME_SEASON_DERIVED",
        admissible=False,
        disposition="REFUSED_SAME_SEASON_DERIVED",
        evidence=(
            "Built from 02_Validation/accepted_games_2024.csv. Same shape as "
            "Phase5J: a 2024 rating computed from 2024 results.",
        ),
    ),
    RegisteredSource(
        source_id="EXPANDED_ENGINE_COMPARISON_2011_2024_2025",
        location=(
            "C:/Users/dbaxt/Downloads/"
            "Power_Crunch_Expanded_Rating_Engine_Comparison_2011_2024_2025_Package.zip"
        ),
        sha256="8eda3469d7a4790153f2715e2904b2210a935f07dc05e447a0c36aebf0ec44e3",
        size_bytes=389983,
        seasons_declared=(2011, 2024, 2025),
        provides_families=(),
        source_class="SAME_SEASON_DERIVED",
        admissible=False,
        disposition="REFUSED_SAME_SEASON_DERIVED",
        evidence=(
            "Its per-season payloads are elo_game_log_<season>.csv and "
            "side-by-side rating tables built from them. Seasons 2011, 2024 and "
            "2025 only; 2021-2023 are absent even as game logs.",
        ),
    ),
    RegisteredSource(
        source_id="POWER_CRUNCH_PREGAME_STATES_2024_2025",
        location=(
            "C:/Local-mcR3_calibration_staging/"
            "Power_Crunch_Research_Lab_Phase5D_WalkForward_Package/"
            "Power_Crunch_Research_Lab_Phase5D_WalkForward/03_Pregame_States/"
            "pregame_states_2024_2025.csv"
        ),
        sha256="8d8822eea90ee4127ded31374c983a1ebf84c82f5851f9dbbdbb5db80d06c622",
        size_bytes=214578,
        seasons_declared=(2024, 2025),
        provides_families=(),
        source_class="UNKNOWN",
        admissible=False,
        disposition="REFUSED_DEGENERATE_AND_FOREIGN_SCALE",
        evidence=(
            "The only genuinely leak-free season-opening rating state on this "
            "filesystem, and it carries no information. Every 2024 week-0 row "
            "has elo_a_pre and elo_b_pre exactly 1500.0, and every 2025 week-0 "
            "or week-1 row likewise: 1 distinct opening value across both "
            "seasons.",
            "A population with zero dispersion has no standard deviation to "
            "divide by, which is why population_mean_sd refuses it rather than "
            "returning zeros that would read as 'every team is average'.",
            "It is also a foreign scale -- research Elo, base 1500 -- and not "
            "any of the four V3 families.",
        ),
    ),
    RegisteredSource(
        source_id="SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026",
        location="C:/Users/dbaxt/Downloads/Synthetic_NCAA_Conference_Distribution_2021_2026.xlsx",
        sha256="376a6f624eea6c60794f061de27f3d875c127e89afc80ec4f81664742588e2ac",
        size_bytes=22942,
        seasons_declared=(2021, 2022, 2023, 2024, 2025, 2026),
        provides_families=(),
        source_class="MEMBERSHIP_DECLARATION",
        admissible=False,
        disposition="POPULATION_CANDIDATE_LINEAGE_OPEN",
        evidence=(
            "Membership and division are settled before a season starts, so "
            "this class is leakage-clean. It is registered as a population "
            "candidate and never as a strength value.",
            "Team Affiliations gives a per-season subdivision and conference "
            "for 251 entities; recomputing over its bytes yields FBS counts of "
            "130 (2021), 131 (2022), 133 (2023) and 133 (2024).",
            "Its Methodology sheet names one upstream, "
            "Synthetic_CFB_2021_2026_Walkover_RERUN.csv. A filesystem sweep did "
            "not find that file, so the chain is documented but cannot be "
            "closed to bytes here.",
        ),
    ),
    RegisteredSource(
        source_id="PHASE5J_TEAM_REGISTRY_2024",
        location=(
            "C:/Users/dbaxt/Downloads/"
            "Power_Crunch_Research_Lab_Phase5J_2024_FACT_Ratings_Package.zip"
            "!01_Inputs/team_registry_2024.csv"
        ),
        sha256="0cf7ac5704a78d56d8bbbacdaec23c0e7e4f802edbce181ad10b817f4e0e16ef",
        size_bytes=5500,
        seasons_declared=(2024,),
        provides_families=(),
        source_class="MEMBERSHIP_DECLARATION",
        admissible=False,
        disposition="POPULATION_CANDIDATE_CONFLICTING",
        evidence=(
            "118 rows, every one division FBS and active_for_rating True; the "
            "package's season_config_2024.json states expected_team_count 118 "
            "under universe_policy REGISTRY_ONLY.",
            "It disagrees with the conference distribution's 133 for the same "
            "season, and the two disagree about membership, not merely about "
            "eligibility: the registry carries Colgate and Cornell as FBS in a "
            "conference named ECL.",
            "Neither source is subordinate to the other, so resolve_population "
            "returns UNRESOLVED_CONFLICTING_CANDIDATES for 2024 rather than "
            "choosing.",
        ),
    ),
    RegisteredSource(
        source_id="V3_CANONICAL_TEAM_MASTER_2026",
        location=(
            "reference/dynamic_weekly_mc_v3/inputs/"
            "2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md"
        ),
        sha256="fd8fcb1bec40e26168d600e9cdb8fbf2de6a421fe13218face588a48c48a83a0",
        size_bytes=278106,
        seasons_declared=(2026,),
        provides_families=(),
        source_class="MEMBERSHIP_DECLARATION",
        admissible=False,
        disposition="REFUSED_AS_HISTORICAL_POPULATION",
        evidence=(
            "The canonical identity authority, and explicitly not a historical "
            "population. Its 134 entities are a synthetic 2026 universe.",
            "It classifies Toledo, Western Michigan, Arkansas State, Charlotte, "
            "Eastern Michigan, Louisiana, Louisiana-Monroe and Western Kentucky "
            "as SCHEDULE_ONLY_FCS, and Colgate, Cornell, Harvard, Holy Cross, "
            "Lehigh, Penn, Princeton, Yale and North Dakota State as "
            "FBS_MEMBER. Neither statement is true of 2021-2024 football.",
            "Usable for identity binding, never as the historical division of a "
            "historical team.",
        ),
    ),
)


#: What each source says the population of a season was.
#:
#: Two candidates exist for 2024 and they disagree; one exists for 2021, 2022
#: and 2023. The disagreement is recorded rather than adjudicated.
HISTORICAL_POPULATION_CANDIDATES: tuple[PopulationCandidate, ...] = (
    PopulationCandidate(
        population_id="SYNTHETIC_WALKOVER_FBS_2021",
        season=2021,
        source_id="SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026",
        scope="FBS",
        count=130,
        basis="2021 Subdivision == FBS over 251 affiliation rows",
    ),
    PopulationCandidate(
        population_id="SYNTHETIC_WALKOVER_FBS_2022",
        season=2022,
        source_id="SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026",
        scope="FBS",
        count=131,
        basis="2022 Subdivision == FBS over 251 affiliation rows",
    ),
    PopulationCandidate(
        population_id="SYNTHETIC_WALKOVER_FBS_2023",
        season=2023,
        source_id="SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026",
        scope="FBS",
        count=133,
        basis="2023 Subdivision == FBS over 251 affiliation rows",
    ),
    PopulationCandidate(
        population_id="SYNTHETIC_WALKOVER_FBS_2024",
        season=2024,
        source_id="SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026",
        scope="FBS",
        count=133,
        basis="2024 Subdivision == FBS over 251 affiliation rows",
    ),
    PopulationCandidate(
        population_id="PHASE5J_REGISTRY_FBS_2024",
        season=2024,
        source_id="PHASE5J_TEAM_REGISTRY_2024",
        scope="FBS",
        count=118,
        basis="118 registry rows, division == FBS, universe_policy REGISTRY_ONLY",
    ),
)


# ---------------------------------------------------------------------------
# 11. Artifacts
# ---------------------------------------------------------------------------
#
# Seven artifacts, each a plain JSON-able structure with sorted keys and no
# timestamp. Determinism is not decoration here: the lane is asked to prove
# repeat-generation byte identity, and a generated_at field would defeat that on
# the second run. Provenance travels in the SHA manifest and in git, both of
# which record when without putting it inside the bytes being hashed.

ARTIFACT_FILENAMES: tuple[str, ...] = (
    "historical_opening_state_source_manifest.json",
    "historical_opening_state_population_manifest.json",
    "historical_opening_state_standardization_manifest.json",
    "historical_opening_state_component_table.json",
    "historical_opening_state_unified_z_table.json",
    "historical_opening_state_coverage_report.json",
    "historical_opening_state_status.json",
)

#: Version of the artifact schema, so a later regeneration is comparable.
OPENING_STATE_ARTIFACT_VERSION = "V3-HISTORICAL-OPENING-STATE-R1"


def _source_payload(source: RegisteredSource) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "location": source.location,
        "sha256": source.sha256,
        "size_bytes": source.size_bytes,
        "seasons_declared": list(source.seasons_declared),
        "source_class": source.source_class,
        "provides_families": list(source.provides_families),
        "admissible": source.admissible,
        "disposition": source.disposition,
        "evidence": list(source.evidence),
    }


def build_source_manifest(
    sources: Sequence[RegisteredSource] = HISTORICAL_OPENING_STATE_SOURCE_REGISTER,
) -> dict[str, object]:
    """The candidate register, with every refusal reason attached."""
    ordered = sorted(sources, key=lambda s: s.source_id)
    return {
        "artifact": "historical_opening_state_source_manifest",
        "artifact_version": OPENING_STATE_ARTIFACT_VERSION,
        "seasons_in_scope": list(HISTORICAL_SEASONS),
        "admissible_source_classes": list(ADMISSIBLE_SOURCE_CLASSES),
        "leakage_refused_classes": list(LEAKAGE_REFUSED_CLASSES),
        "sources": [_source_payload(s) for s in ordered],
        "admissible_source_count": sum(1 for s in ordered if s.admissible),
        "refused_source_count": sum(1 for s in ordered if not s.admissible),
    }


def build_population_manifest(
    populations: Sequence[PopulationDefinition],
) -> dict[str, object]:
    """Per-season population, resolved or explicitly not."""
    return {
        "artifact": "historical_opening_state_population_manifest",
        "artifact_version": OPENING_STATE_ARTIFACT_VERSION,
        "population_scope_note": (
            "Historical membership follows the season being reconstructed. The "
            "synthetic 2026 canonical scope is identity metadata and is never "
            "used as historical NCAA truth."
        ),
        "seasons": [
            {
                "season": p.season,
                "population_id": p.population_id,
                "scope": p.scope,
                "status": p.status,
                "resolved_count": p.count if p.status == "RESOLVED" else None,
                "included_teams": list(p.included),
                "excluded_teams": [
                    {"team": t, "reason": r} for t, r in p.excluded
                ],
                "source_ids": list(p.source_ids),
                "candidates": [
                    {
                        "population_id": c.population_id,
                        "source_id": c.source_id,
                        "scope": c.scope,
                        "count": c.count,
                        "basis": c.basis,
                    }
                    for c in sorted(p.candidates, key=lambda c: c.population_id)
                ],
            }
            for p in sorted(populations, key=lambda p: p.season)
        ],
    }


def build_standardization_manifest(
    records: Sequence[StandardizationRecord],
) -> dict[str, object]:
    """Formula, population, mean, SD, directionality and missing handling."""
    return {
        "artifact": "historical_opening_state_standardization_manifest",
        "artifact_version": OPENING_STATE_ARTIFACT_VERSION,
        "ddof_convention": STANDARDIZATION_DDOF,
        "ddof_note": (
            "Sample standard deviation. Measured from the 2026 workbook rather "
            "than read from its 'Population Statistics' label: ddof=1 "
            "reproduces every published family Z to within 1e-14 and ddof=0 "
            "reproduces none of them."
        ),
        "families": [
            {
                "family_id": f.family_id,
                "weight": f.weight,
                "role": f.role,
                "native_field_2026": f.native_field_2026,
                "directionality": f.directionality,
                "members": list(f.members),
            }
            for f in V3_PRESEASON_FAMILIES
        ],
        "records": [
            {
                "family_id": r.family_id,
                "season": r.season,
                "population_id": r.population_id,
                "formula": r.formula,
                "mean": r.mean,
                "standard_deviation": r.standard_deviation,
                "ddof": r.ddof,
                "n": r.n,
                "directionality": r.directionality,
                "missing_value_handling": r.missing_value_handling,
                "native_field": r.native_field,
            }
            for r in sorted(records, key=lambda r: (r.season, r.family_id))
        ],
        "records_present": len(records),
    }


def build_team_season_component_table(
    states: Sequence[TeamSeasonOpeningState],
) -> dict[str, object]:
    """Native and standardized component values, per team-season.

    Native values are carried alongside standardized ones rather than replaced
    by them, so a later lane that changes the population definition can restate
    the Z scores without going back to the sources.
    """
    return {
        "artifact": "historical_opening_state_component_table",
        "artifact_version": OPENING_STATE_ARTIFACT_VERSION,
        "required_families": list(REQUIRED_FAMILY_IDS),
        "board_family_members": list(BOARD_FAMILY_MEMBERS),
        "rows": [
            {
                "season": s.season,
                "team_key": s.team_key,
                "team_name": s.identity.historical_name,
                "historical_division": s.identity.division,
                "historical_conference": s.identity.conference,
                "canonical_schedule_id": s.identity.canonical_schedule_id,
                "canonical_binding": s.identity.canonical_binding,
                "aliases": list(s.identity.aliases),
                "population_id": s.population_id,
                "native_inputs": {k: v for k, v in s.native_inputs},
                "standardized_components": {k: v for k, v in s.standardized_components},
                "included_family_count": s.included_family_count,
                "status": s.status,
            }
            for s in sorted(states, key=lambda s: (s.season, s.team_key))
        ],
    }


def build_opening_unified_z_table(
    states: Sequence[TeamSeasonOpeningState],
) -> dict[str, object]:
    """The opening Unified Z per team-season, and nothing derived in points."""
    return {
        "artifact": "historical_opening_state_unified_z_table",
        "artifact_version": OPENING_STATE_ARTIFACT_VERSION,
        "point_transform_status": V3_POINT_SCALE_HISTORICAL_AUTHORITY,
        "point_transform_note": (
            "No football points are emitted. The 2026 neutral-field scale is "
            f"{V3_NEUTRAL_FIELD_POINT_SCALE} points per standard deviation; "
            "whether it is historically reusable is owned by the expected-margin "
            "audit. opening_unified_z is supplied in standard-deviation units so "
            "either later ruling can be applied without recomputing anything."
        ),
        "index_transform": {
            "formula": "unified_power_index = 100 + 10 * opening_unified_z",
            "center": V3_INDEX_CENTER,
            "scale": V3_INDEX_SCALE,
            "unit": "DIMENSIONLESS_INDEX",
        },
        "rows": [
            {
                "season": s.season,
                "team_key": s.team_key,
                "population_id": s.population_id,
                "opening_unified_z": s.opening_unified_z,
                "board_family_z": s.board_family_z,
                "included_family_count": s.included_family_count,
                "status": s.status,
                "confidence": s.confidence,
            }
            for s in sorted(states, key=lambda s: (s.season, s.team_key))
        ],
        "rows_with_unified_z": sum(1 for s in states if s.opening_unified_z is not None),
    }


def build_coverage_report(
    states: Sequence[TeamSeasonOpeningState],
    week1_2: Mapping[int, Mapping[str, object]] | None = None,
) -> dict[str, object]:
    """Coverage, exclusions and Week 1-2 readiness, per season and overall."""
    seasons = sorted({s.season for s in states} | set(HISTORICAL_SEASONS))
    per_season = []
    for season in seasons:
        rows = [s for s in states if s.season == season]
        reasons: dict[str, int] = {}
        for row in rows:
            for reason, _ in row.missing_reasons:
                reasons[reason] = reasons.get(reason, 0) + 1
        per_season.append(
            {
                "season": season,
                "team_seasons": len(rows),
                "fully_reconstructed": sum(
                    1 for r in rows if r.status == OpeningStatus.FULLY_RECONSTRUCTED
                ),
                "partially_reconstructed": sum(
                    1 for r in rows if r.status == OpeningStatus.PARTIALLY_RECONSTRUCTED
                ),
                "unavailable": sum(
                    1 for r in rows if r.status == OpeningStatus.UNAVAILABLE
                ),
                "missing_reason_counts": dict(sorted(reasons.items())),
                "week1_2": dict((week1_2 or {}).get(season, {})) or None,
            }
        )
    return {
        "artifact": "historical_opening_state_coverage_report",
        "artifact_version": OPENING_STATE_ARTIFACT_VERSION,
        "missing_reason_vocabulary": list(MISSING_REASONS),
        "imputation_policy": (
            "NONE. A team-season without a complete component set is reported "
            "as UNAVAILABLE or PARTIALLY_RECONSTRUCTED with a reason, never "
            "filled from a neighbour, a conference mean or a prior season."
        ),
        "per_season": per_season,
        "team_season_total": len(states),
        "fully_reconstructed_total": sum(
            1 for s in states if s.status == OpeningStatus.FULLY_RECONSTRUCTED
        ),
        "partially_reconstructed_total": sum(
            1 for s in states if s.status == OpeningStatus.PARTIALLY_RECONSTRUCTED
        ),
        "unavailable_total": sum(
            1 for s in states if s.status == OpeningStatus.UNAVAILABLE
        ),
    }


def build_status_record(
    states: Sequence[TeamSeasonOpeningState],
    populations: Sequence[PopulationDefinition],
    *,
    terminal_status: str,
) -> dict[str, object]:
    """The lane's machine-readable disposition."""
    families_available = sorted(
        {
            family
            for source in HISTORICAL_OPENING_STATE_SOURCE_REGISTER
            if source.admissible
            for family in source.provides_families
        }
    )
    return {
        "artifact": "historical_opening_state_status",
        "artifact_version": OPENING_STATE_ARTIFACT_VERSION,
        "terminal_status": terminal_status,
        "seasons_in_scope": list(HISTORICAL_SEASONS),
        "component_families_required": list(REQUIRED_FAMILY_IDS),
        "component_families_available": families_available,
        "opening_unified_z_status": (
            "NOT_PRODUCED_FOR_ANY_TEAM_SEASON"
            if not any(s.opening_unified_z is not None for s in states)
            else "PRODUCED"
        ),
        "population_status": {
            str(p.season): p.status for p in sorted(populations, key=lambda p: p.season)
        },
        "future_leakage_result": (
            "NO_SAME_SEASON_OR_POSTSEASON_SOURCE_ADMITTED"
        ),
        "fcs_opening_point_status": (
            "REFUSED_NO_POINT_STRENGTH_DERIVED_FROM_ELO_1250"
        ),
        "point_transform_status": V3_POINT_SCALE_HISTORICAL_AUTHORITY,
        "parameters_promoted": 0,
        "blockers_retired": 0,
        "simulations_run": 0,
        "writes_canonical_config": False,
    }


def write_opening_state_artifacts(
    output_dir: Path,
    *,
    states: Sequence[TeamSeasonOpeningState],
    populations: Sequence[PopulationDefinition],
    standardization: Sequence[StandardizationRecord] = (),
    week1_2: Mapping[int, Mapping[str, object]] | None = None,
    terminal_status: str,
    sources: Sequence[RegisteredSource] = HISTORICAL_OPENING_STATE_SOURCE_REGISTER,
) -> dict[str, str]:
    """Emit all seven artifacts and return ``{filename: sha256}``.

    Byte-identical on repeat generation from identical inputs, on any platform:
    every artifact is written through :func:`~.textio.write_json_lf`, which
    pins UTF-8, LF and sorted keys, and no artifact carries a timestamp.
    """
    payloads = {
        "historical_opening_state_source_manifest.json": build_source_manifest(sources),
        "historical_opening_state_population_manifest.json": build_population_manifest(
            populations
        ),
        "historical_opening_state_standardization_manifest.json": (
            build_standardization_manifest(standardization)
        ),
        "historical_opening_state_component_table.json": (
            build_team_season_component_table(states)
        ),
        "historical_opening_state_unified_z_table.json": (
            build_opening_unified_z_table(states)
        ),
        "historical_opening_state_coverage_report.json": build_coverage_report(
            states, week1_2
        ),
        "historical_opening_state_status.json": build_status_record(
            states, populations, terminal_status=terminal_status
        ),
    }
    if tuple(sorted(payloads)) != tuple(sorted(ARTIFACT_FILENAMES)):
        raise GovernanceBlock("artifact set does not match ARTIFACT_FILENAMES")
    digests: dict[str, str] = {}
    for filename in sorted(payloads):
        path = write_json_lf(output_dir / filename, payloads[filename])
        digests[filename] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digests


# ---------------------------------------------------------------------------
# 12. The reconstruction frame, and running the whole thing
# ---------------------------------------------------------------------------
#
# The frame answers "which team-seasons does this lane report on", which is a
# smaller question than "what was the population", and is answerable when that
# one is not. It is committed to the repository as a deterministic CSV so the
# coverage report can be regenerated from repository bytes by an auditor who
# does not have the original workbook, and it is labelled a frame rather than a
# population everywhere it appears -- no standardization is ever performed over
# it.

#: Where the committed frame and the emitted artifacts live.
OPENING_STATE_REFERENCE_DIR = Path("reference/dynamic_weekly_mc_v3/historical_opening_state_r1")

#: The committed membership frame.
MEMBERSHIP_FRAME_FILENAME = "historical_membership_frame_2021_2024.csv"

#: Digest of the committed frame, so a mutated frame is caught rather than used.
MEMBERSHIP_FRAME_SHA256 = "ad93c7c71131c59947d5f84677d10679461e3239e5028ceb03fd04f774c4d08b"

#: The division value the FBS reconstruction frame is drawn from.
FBS_DIVISION_LABEL = "FBS"

#: Division labels that are preserved and reported but never given a strength.
#:
#: FCS entities are real participants in real games and are kept in the record.
#: They are outside the FBS population, and under the unresolved FCS adapter
#: they have no route to a unified point value either.
NON_FBS_DIVISION_LABELS: tuple[str, ...] = (
    "FCS",
    "Division II",
    "Inactive / No varsity football",
)


def load_membership_frame(path: Path) -> tuple[HistoricalTeamIdentity, ...]:
    """Load the committed frame, refusing a frame whose bytes have moved.

    The digest check is not belt-and-braces. Every count this lane reports --
    team-season totals, per-division breakdowns, the coverage denominators --
    is a count over these rows, and a frame that has been edited in place would
    change all of them while every other artifact continued to look consistent.
    """
    import csv as _csv

    if not path.exists():
        raise InputValidationError(f"membership frame not found: {path}")
    raw = path.read_bytes()
    observed = hashlib.sha256(raw).hexdigest()
    if observed != MEMBERSHIP_FRAME_SHA256:
        raise InputValidationError(
            f"membership frame digest mismatch: expected {MEMBERSHIP_FRAME_SHA256}, "
            f"observed {observed}"
        )
    rows = list(_csv.DictReader(raw.decode("utf-8").splitlines()))
    identities = []
    for row in rows:
        identities.append(
            HistoricalTeamIdentity(
                season=int(row["season"]),
                historical_key=row["team_key"],
                historical_name=row["team_name"],
                division=row["division"],
                conference=row["conference"] or None,
            )
        )
    return tuple(identities)


def bind_canonical_identity(
    identity: HistoricalTeamIdentity, canonical_index: Mapping[str, Mapping[str, object]]
) -> HistoricalTeamIdentity:
    """Attach the synthetic 2026 canonical id when an exact key matches.

    Exact keys only -- ``schedule_id``, ``team_name`` or ``abbreviated_name``.
    No expansion, no punctuation folding, no nearest match. A wrong binding is
    worse than no binding, because a bound entity looks reconciled: the master
    carries both ``Miami`` and no ``Miami (OH)``, so any rule loose enough to
    fold ``NC St.`` onto ``NC State`` is also loose enough to fold two distinct
    programs onto one.

    Binding is refused when two historical entities would land on one canonical
    id, for the same reason: no source fact says which of them is correct.

    Nothing is dropped either way. An unbound entity keeps its row and its
    division and is reported as ``HISTORICAL_ENTITY_UNRESOLVED``, because
    dropping historically valid programs would silently shrink every population
    a later lane computes over.
    """
    from dataclasses import replace as _replace

    keys: dict[str, str] = {}
    for schedule_id, row in canonical_index.items():
        for field in ("schedule_id", "team_name", "abbreviated_name"):
            value = row.get(field)
            if isinstance(value, str) and value:
                keys.setdefault(value, schedule_id)
    hit = keys.get(identity.historical_key) or keys.get(identity.historical_name)
    if hit is None:
        return identity
    return _replace(
        identity,
        canonical_schedule_id=hit,
        canonical_binding="EXACT_CANONICAL_KEY",
        aliases=tuple(sorted({identity.historical_name, hit})),
    )


def bind_frame_identities(
    identities: Sequence[HistoricalTeamIdentity],
    canonical_index: Mapping[str, Mapping[str, object]],
) -> tuple[HistoricalTeamIdentity, ...]:
    """Bind a whole season frame, refusing any binding that is not injective.

    Injectivity is enforced per season rather than globally, because the same
    canonical id legitimately recurs across seasons and only a collision inside
    one season is ambiguous.
    """
    bound = [bind_canonical_identity(i, canonical_index) for i in identities]
    by_season: dict[int, dict[str, list[str]]] = {}
    for identity in bound:
        if identity.canonical_schedule_id is None:
            continue
        by_season.setdefault(identity.season, {}).setdefault(
            identity.canonical_schedule_id, []
        ).append(identity.historical_key)
    from dataclasses import replace as _replace

    collided: set[tuple[int, str]] = set()
    for season, mapping in by_season.items():
        for _, teams in mapping.items():
            if len(teams) > 1:
                for team in teams:
                    collided.add((season, team))
    if not collided:
        return tuple(bound)
    return tuple(
        _replace(
            identity,
            canonical_schedule_id=None,
            canonical_binding="UNBOUND_HISTORICAL_ENTITY",
            aliases=(),
        )
        if (identity.season, identity.historical_key) in collided
        else identity
        for identity in bound
    )


def _no_component_observations(identity: HistoricalTeamIdentity) -> tuple[ComponentObservation, ...]:
    """Every family, explicitly absent, with the reason attached.

    Emitting a row of ``None`` per family rather than an empty list is the
    point: the component table then states which four families were looked for
    and did not exist, instead of being silent about all of them at once.
    """
    return tuple(
        ComponentObservation(
            season=identity.season,
            team_key=identity.historical_key,
            family_id=family_id,
            native_value=None,
            native_source_id=None,
            standardized_value=None,
            status="MISSING_SOURCE",
        )
        for family_id in REQUIRED_FAMILY_IDS
    )


def build_reconstruction(
    identities: Sequence[HistoricalTeamIdentity],
    populations: Sequence[PopulationDefinition],
) -> tuple[TeamSeasonOpeningState, ...]:
    """Run the reconstruction over a bound frame against the real evidence.

    Non-FBS entities are carried through with ``OUTSIDE_POPULATION`` rather than
    filtered out. They are real participants and a later lane needs to know they
    were seen and deliberately left without a strength, which is a different
    statement from never having appeared.
    """
    by_season = {p.season: p for p in populations}
    states = []
    for identity in sorted(identities, key=lambda i: (i.season, i.historical_key)):
        population = by_season.get(identity.season)
        if population is None:
            raise InputValidationError(f"no population record for season {identity.season}")
        if identity.division != FBS_DIVISION_LABEL:
            states.append(
                TeamSeasonOpeningState(
                    season=identity.season,
                    team_key=identity.historical_key,
                    identity=identity,
                    native_inputs=(),
                    standardized_components=tuple(
                        sorted((f, None) for f in REQUIRED_FAMILY_IDS)
                    ),
                    board_family_z=None,
                    opening_unified_z=None,
                    included_family_count=0,
                    status=OpeningStatus.UNAVAILABLE,
                    missing_reasons=(
                        (
                            "OUTSIDE_POPULATION",
                            f"{identity.division} in {identity.season}: outside the "
                            "FBS unified-point domain. The entity is preserved; no "
                            "opening strength is fabricated for it.",
                        ),
                    ),
                    population_id=population.population_id,
                    confidence="NONE",
                )
            )
            continue
        states.append(
            reconstruct_team_season(
                identity, population, _no_component_observations(identity)
            )
        )
    return tuple(states)


def generate_opening_state_artifacts(
    repo_root: Path, output_dir: Path, *, terminal_status: str
) -> dict[str, object]:
    """End-to-end: load the frame, bind identity, reconstruct, emit, digest.

    Returns the digests alongside the counts a report needs, so the numbers in
    a written report and the numbers in the artifacts come from one call rather
    than from two computations that can drift apart.
    """
    from .inputs import load_canonical_team_index

    frame_path = repo_root / OPENING_STATE_REFERENCE_DIR / MEMBERSHIP_FRAME_FILENAME
    identities = load_membership_frame(frame_path)
    canonical_index = load_canonical_team_index(
        repo_root
        / "reference/dynamic_weekly_mc_v3/inputs/2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md"
    )
    bound = bind_frame_identities(identities, canonical_index)
    populations = tuple(
        resolve_population(season, HISTORICAL_POPULATION_CANDIDATES, scope="FBS")
        for season in HISTORICAL_SEASONS
    )
    states = build_reconstruction(bound, populations)

    # Weeks 1-2 readiness. No historical schedule is mounted in this lane, and
    # the count would be zero for any schedule at all, because no team-season
    # carries a usable opening state. Both facts are reported: a zero that comes
    # from an absent schedule and a zero that comes from absent strength are
    # different findings and a later lane needs to know which applies.
    week1_2 = {
        season: {
            **week1_2_opening_state_availability(
                [s for s in states if s.season == season], []
            ),
            "schedule_mounted": False,
            "schedule_status": (
                "NO_HISTORICAL_SCHEDULE_MOUNTED_IN_THIS_LANE; the count is zero "
                "on opening-state grounds regardless of schedule, because no "
                "team-season is FULLY_RECONSTRUCTED"
            ),
        }
        for season in HISTORICAL_SEASONS
    }

    digests = write_opening_state_artifacts(
        output_dir,
        states=states,
        populations=populations,
        standardization=(),
        week1_2=week1_2,
        terminal_status=terminal_status,
    )
    return {
        "artifact_sha256": digests,
        "team_season_total": len(states),
        "fully_reconstructed": sum(
            1 for s in states if s.status == OpeningStatus.FULLY_RECONSTRUCTED
        ),
        "partially_reconstructed": sum(
            1 for s in states if s.status == OpeningStatus.PARTIALLY_RECONSTRUCTED
        ),
        "unavailable": sum(1 for s in states if s.status == OpeningStatus.UNAVAILABLE),
        "population_status": {p.season: p.status for p in populations},
        "week1_2": week1_2,
        "bound_identities": sum(
            1 for i in bound if i.canonical_binding == "EXACT_CANONICAL_KEY"
        ),
        "unbound_identities": sum(
            1 for i in bound if i.canonical_binding == "UNBOUND_HISTORICAL_ENTITY"
        ),
    }
