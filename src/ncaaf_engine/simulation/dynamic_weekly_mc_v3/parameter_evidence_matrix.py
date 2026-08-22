"""The V3 parameter evidence matrix.

The calibration data plane is frozen. ``V3_CALIBRATION_CORPUS_R9.csv`` holds
5,148 corpus members and ``V3_CALIBRATION_OBSERVATIONS_R8.csv`` holds the 3,259
fully paired walk-forward observations derived from it. Neither is rebuilt,
reinterpreted or mutated here. This module answers a different question, one
step before any fit:

    For each unresolved V3 numerical parameter, what evidence does the
    estimation mathematically require, how many corpus rows presently supply
    it, and which of those rows may be read for fitting, for selection, and
    never.

Three properties are structural rather than incidental.

**Populations come from capability requirements, never from a universal mask.**
Ruling R9-CAL-FULL-CORPUS-USE-SPECIFIC-ELIGIBILITY separates corpus membership
from use-specific eligibility, and this module honours that separation
parameter by parameter. ``blowout_treatment`` read as an outcome-only question
is a function of the realised margin alone, so it does not ask whether a pregame
prediction exists and reaches 5,144 rows. ``game_sd_points`` read as a residual
question needs the prediction and reaches 4,643. The strictest use, the full
walk-forward observation contract, reaches 3,259. A parameter that needs less is
not charged for what another parameter needs.

**The holdout is counted and never scored.** 2025 row counts appear in this
matrix because a census of how much evidence exists is not a measurement of how
well a candidate performs. Every population this module exposes for fitting or
for selection refuses the holdout by construction, through
:func:`require_fitting_population` and :func:`require_selection_population`,
which delegate to ``calibration.require_selection_split``. No statistic beyond a
row count is computed on any 2025 row anywhere in this module.

**An ambiguity is reported, not resolved.** Two of the six parameters cannot be
given a settled mathematical target from the repository as it stands, because
the V3 weekly rerating formula is not defined anywhere in it:
``BlockedGovernedRerater`` refuses to rerate, and ``FixtureResidualRerater``
states in its own docstring that it is test-only and asserts no canonical V3
calibration formula. Where that gap changes which rows are admissible evidence
-- and for ``weekly_movement_cap_points`` it changes the population by a factor
of four -- the alternatives are named with their exact populations and the
question is raised in :data:`CHAIRMAN_RULINGS_REQUIRED` rather than settled here.

Nothing in this module fits a coefficient, ranks a candidate, selects a regime,
or retires a blocker. ``fitted`` and ``promoted`` are ``False`` on every record
and there is no code path that sets either to anything else.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import blocker_report
from . import calibration as cal
from . import calibration_contract as contract
from . import config as v3_config
from .errors import GovernanceBlock, InputValidationError

MATRIX_ID = "V3-PARAMETER-EVIDENCE-MATRIX"
MATRIX_VERSION = "R1"
MATRIX_LANE = "EVIDENCE_MATRIX_ONLY"

#: This lane fits nothing and promotes nothing. Both are module-level facts, not
#: per-call arguments, so no caller can flip either.
LANE_FITS_PARAMETERS = False
LANE_PROMOTES_PARAMETERS = False
LANE_SCORES_HOLDOUT = False
LANE_REBUILDS_CORPUS = False


# ---------------------------------------------------------------------------
# The frozen data plane
# ---------------------------------------------------------------------------

CORPUS_PATH = Path("reference/dynamic_weekly_mc_v3/V3_CALIBRATION_CORPUS_R9.csv")
CORPUS_SHA256 = "1b91fe0ffc6e205243b88b996c3489735ea90cac1635126b487a11e5cec5f720"
CANONICAL_CORPUS_ROWS = 5148

OBSERVATIONS_PATH = Path(
    "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_OBSERVATIONS_R8.csv"
)
OBSERVATIONS_SHA256 = "eb5179ef6e8b5379c96a1423c826af61876712d1f4138110d6a66bf81744ac43"
PAIRED_OBSERVATION_ROWS = 3259

#: Corpus members the full walk-forward observation contract does not admit.
#: They remain members: under ruling R9 non-admission to one use is a fact about
#: that use, not a deletion from the corpus.
LIMITED_CAPABILITY_CORPUS_MEMBERS = CANONICAL_CORPUS_ROWS - PAIRED_OBSERVATION_ROWS

#: Fields a parameter may need that the governed observation allowlist does not
#: yet admit. Read from the contract rather than restated, so a field that is
#: later admitted stops being reported as pending without this module changing.
FIELDS_AWAITING_ADMISSION_RULING: tuple[str, ...] = tuple(
    sorted(f.name for f in contract.FIELDS_REQUIRING_ADMISSION_RULING)
)

TRAINING_SEASONS: tuple[int, ...] = (2006, 2007, 2008, 2009, 2010, 2011)
VALIDATION_SEASONS: tuple[int, ...] = (2024,)
HOLDOUT_SEASONS: tuple[int, ...] = (2025,)
ALL_SEASONS: tuple[int, ...] = TRAINING_SEASONS + VALIDATION_SEASONS + HOLDOUT_SEASONS

SPLIT_OF_SEASON: dict[int, str] = {
    **{s: "training" for s in TRAINING_SEASONS},
    **{s: "validation" for s in VALIDATION_SEASONS},
    **{s: "holdout" for s in HOLDOUT_SEASONS},
}

#: What each split may decide. Read from the calibration harness rather than
#: restated, so this lane cannot drift from the gate that enforces it.
SPLIT_POLICY: dict[str, str] = {
    "training": "MAY_FURNISH_CANDIDATE_ESTIMATES",
    "validation": "MAY_SELECT_AMONG_CANDIDATE_METHODS_AND_REGIMES",
    "holdout": cal.HOLDOUT_USE,
}

#: The exact decisions the holdout may not participate in. Enumerated because
#: "do not use the holdout" is easy to agree with and easy to violate one
#: convenience at a time.
HOLDOUT_PROHIBITED_DECISIONS: tuple[str, ...] = (
    "choose a formula",
    "choose a coefficient",
    "choose a cap",
    "choose weights",
    "choose a threshold",
    "choose regularization",
    "choose game SD",
    "choose an FCS point mapping",
)


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_frozen_artifacts(root: Path | None = None) -> dict[str, Any]:
    """Fail closed unless both frozen artifacts are byte-exact.

    The matrix is a statement about specific bytes. Computed against different
    bytes it is a statement about nothing, so verification happens before a
    single row is read rather than being reported alongside the result.
    """
    base = root or repository_root()
    verified: dict[str, Any] = {}
    for name, rel, expected, rows in (
        ("corpus", CORPUS_PATH, CORPUS_SHA256, CANONICAL_CORPUS_ROWS),
        ("observations", OBSERVATIONS_PATH, OBSERVATIONS_SHA256, PAIRED_OBSERVATION_ROWS),
    ):
        path = base / rel
        if not path.exists():
            raise GovernanceBlock(
                f"Frozen calibration artifact {rel.as_posix()} is not present. The "
                "evidence matrix is computed against pinned bytes and refuses to run "
                "against absent ones."
            )
        actual = _sha256_file(path)
        if actual != expected:
            raise GovernanceBlock(
                f"{rel.as_posix()} has SHA-256 {actual}, expected {expected}. The "
                "frozen calibration data plane has changed; this matrix is not "
                "recomputed against unpinned bytes."
            )
        verified[name] = {
            "path": rel.as_posix(),
            "sha256": actual,
            "expected_sha256": expected,
            "expected_records": rows,
            "mutated_by_this_lane": False,
        }
    return verified


def load_corpus(root: Path | None = None) -> list[dict[str, str]]:
    """Read the frozen corpus. Read-only, and verified before it is read."""
    base = root or repository_root()
    verify_frozen_artifacts(base)
    with (base / CORPUS_PATH).open("r", encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    if len(records) != CANONICAL_CORPUS_ROWS:
        raise GovernanceBlock(
            f"Canonical corpus holds {len(records)} records, expected "
            f"{CANONICAL_CORPUS_ROWS}. The corpus is frozen and is not rebuilt here."
        )
    return records


def load_observations(root: Path | None = None) -> list[dict[str, str]]:
    """Read the frozen fully paired walk-forward observation subset."""
    base = root or repository_root()
    verify_frozen_artifacts(base)
    with (base / OBSERVATIONS_PATH).open("r", encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    if len(records) != PAIRED_OBSERVATION_ROWS:
        raise GovernanceBlock(
            f"Observation subset holds {len(records)} records, expected "
            f"{PAIRED_OBSERVATION_ROWS}."
        )
    return records


# ---------------------------------------------------------------------------
# Row predicates
#
# Every predicate reads a field the corpus actually records. None supplies a
# value for a field the source left empty, and none reads an UNKNOWN as a
# decided value: `overtime_status_known` being false means the status is
# unknown, and unknown never becomes "no overtime".
# ---------------------------------------------------------------------------


def _flag(row: Mapping[str, str], capability: str) -> bool:
    key = f"cap_{capability}"
    if key not in row:
        raise InputValidationError(f"Corpus row carries no capability column {key!r}")
    return row[key].strip() == "True"


def _uses(row: Mapping[str, str]) -> set[str]:
    return {u for u in str(row["eligible_uses"]).split("|") if u}


def _week_recorded(row: Mapping[str, str]) -> bool:
    return str(row["week"]).strip() != ""


def _season(row: Mapping[str, str]) -> int:
    return int(row["season"])


def split_of(row: Mapping[str, str]) -> str:
    return SPLIT_OF_SEASON[_season(row)]


@dataclass(frozen=True)
class EvidencePredicate:
    """One named requirement, with the mathematics that makes it a requirement."""

    predicate_id: str
    kind: str  # calibration_use | capability | recorded_field
    reason: str
    test: Callable[[Mapping[str, str]], bool]

    def as_dict(self) -> dict[str, Any]:
        return {"predicate_id": self.predicate_id, "kind": self.kind, "reason": self.reason}


def _use_predicate(use: str, reason: str) -> EvidencePredicate:
    return EvidencePredicate(
        predicate_id=use,
        kind="calibration_use",
        reason=reason,
        test=lambda row, use=use: use in _uses(row),
    )


def _capability_predicate(capability: str, reason: str) -> EvidencePredicate:
    return EvidencePredicate(
        predicate_id=capability,
        kind="capability",
        reason=reason,
        test=lambda row, capability=capability: _flag(row, capability),
    )


WEEK_ORDINAL_RECORDED = EvidencePredicate(
    predicate_id="week_ordinal_recorded",
    kind="recorded_field",
    reason=(
        "A weekly update is indexed by the week it follows. Where the source "
        "recorded no week ordinal the row still has a provable temporal order, but "
        "it cannot be assigned to a weekly update step, and a week is never inferred "
        "from a label: under ruling R6-CAL-TEMPORAL-ORDER week_label and stage_label "
        "are verbatim provenance and are never parsed for ordering."
    ),
    test=_week_recorded,
)

RESIDUAL_USE = _use_predicate(
    "EXPECTED_MARGIN_RESIDUAL",
    "Any quantity of the form actual_margin - expected_margin needs both halves, a "
    "provable position in time, and both participants placed on a resolved point "
    "scale. The use refuses rows requiring the unresolved FCS point adapter rather "
    "than fitting them on a scale nobody has issued.",
)
OUTCOME_USE = _use_predicate(
    "ACTUAL_MARGIN_DISTRIBUTION",
    "A function of the realised margin alone. It does not ask whether a pregame "
    "prediction exists, because it does not use one.",
)
OVERTIME_USE = _use_predicate(
    "OVERTIME_SENSITIVE",
    "Any procedure that filters, removes or conditions on overtime needs the status "
    "to be KNOWN. UNKNOWN is never read as regulation.",
)
COMPONENT_RATINGS = _capability_predicate(
    "component_ratings_available",
    "The two pregame team ratings behind the predicted margin. Recorded only where "
    "the governed source recorded them; never reconstructed by replay, because a "
    "reconstructed rating presented as an observation is weaker provenance than the "
    "recorded prediction it would justify.",
)
OVERTIME_KNOWN = _capability_predicate(
    "overtime_status_known",
    "The source recorded an overtime status for this row. False means unknown, and "
    "unknown is never converted to False-the-value.",
)


# ---------------------------------------------------------------------------
# Population computation
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Population:
    """A row population, its per-season shape, and its evidence-domain census.

    Counts only. No statistic of any row's numeric content is computed here, on
    any split, which is what keeps a holdout census a census.
    """

    population_id: str
    predicates: tuple[EvidencePredicate, ...]
    rows: int
    by_season: dict[int, int]
    by_split: dict[str, int]
    by_evidence_domain: dict[str, int]
    fbs_rows: int
    fcs_rows: int
    other_or_unknown_division_rows: int
    overtime_known_rows: int
    overtime_unknown_rows: int

    @property
    def training_rows(self) -> int:
        return self.by_split["training"]

    @property
    def validation_rows(self) -> int:
        return self.by_split["validation"]

    @property
    def holdout_rows(self) -> int:
        return self.by_split["holdout"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "population_id": self.population_id,
            "requirements": [p.as_dict() for p in self.predicates],
            "rows": self.rows,
            "by_season": {str(k): v for k, v in sorted(self.by_season.items())},
            "by_split": dict(sorted(self.by_split.items())),
            "training_eligible_rows": self.training_rows,
            "validation_eligible_rows": self.validation_rows,
            "holdout_available_rows": self.holdout_rows,
            "holdout_usable_for_selection": False,
            "evidence_domain_census": dict(sorted(self.by_evidence_domain.items())),
            "division_census": {
                "fbs_rows": self.fbs_rows,
                "fcs_rows": self.fcs_rows,
                "other_or_unknown_classification_rows": self.other_or_unknown_division_rows,
            },
            "overtime_census": {
                "ot_known_rows": self.overtime_known_rows,
                "ot_unknown_rows": self.overtime_unknown_rows,
                "ot_unknown_converted_to_regulation": False,
            },
        }


def _division_class(row: Mapping[str, str]) -> str:
    team, opponent = row["team_division"], row["opponent_division"]
    if team == "FBS" and opponent == "FBS":
        return "fbs"
    if "FCS" in (team, opponent):
        return "fcs"
    return "other_or_unknown"


def build_population(
    population_id: str,
    records: Sequence[Mapping[str, str]],
    predicates: Sequence[EvidencePredicate],
) -> Population:
    """Select rows by what the estimation needs, and by nothing else.

    Each predicate is a stated mathematical requirement. There is no shared
    exclusion mask: a population is exactly the conjunction of its own
    predicates, so a parameter that needs no overtime status is never charged
    for the fact that another parameter does.
    """
    selected = [r for r in records if all(p.test(r) for p in predicates)]
    divisions = Counter(_division_class(r) for r in selected)
    return Population(
        population_id=population_id,
        predicates=tuple(predicates),
        rows=len(selected),
        by_season={s: sum(1 for r in selected if _season(r) == s) for s in ALL_SEASONS},
        by_split={
            split: sum(1 for r in selected if split_of(r) == split)
            for split in cal.DATA_SPLITS
        },
        by_evidence_domain=dict(Counter(r["evidence_domain"] for r in selected)),
        fbs_rows=divisions["fbs"],
        fcs_rows=divisions["fcs"],
        other_or_unknown_division_rows=divisions["other_or_unknown"],
        overtime_known_rows=sum(1 for r in selected if _flag(r, "overtime_status_known")),
        overtime_unknown_rows=sum(
            1 for r in selected if not _flag(r, "overtime_status_known")
        ),
    )


def require_fitting_population(split: str) -> str:
    """Refuse any split but training as a source of candidate estimates."""
    key = (split or "").strip().lower()
    if key not in cal.DATA_SPLITS:
        raise InputValidationError(f"Split {split!r} is not one of {list(cal.DATA_SPLITS)}")
    if key == "holdout":
        raise GovernanceBlock(
            "The holdout split may not furnish a candidate estimate. Holdout use is "
            f"{cal.HOLDOUT_USE}."
        )
    if key != "training":
        raise GovernanceBlock(
            "Candidate estimates are furnished from the training split. The "
            f"{cal.SELECTION_SPLIT!r} split selects among candidates; it does not "
            "produce them."
        )
    return key


def require_selection_population(split: str, *, purpose: str = "method selection") -> str:
    """Refuse any split but validation as a selection surface.

    Delegated rather than restated, so a change to the calibration gate cannot
    leave this lane enforcing a weaker rule than the harness does.
    """
    return cal.require_selection_split(split, purpose=purpose)


def refuse_holdout_decision(decision: str) -> None:
    """Refuse, by name, each decision the holdout may not participate in."""
    raise GovernanceBlock(
        f"The 2025 holdout may not be read to {decision}. Holdout use is "
        f"{cal.HOLDOUT_USE}, and a holdout consulted during selection has been fitted "
        "to. Population census is permitted; model-selection statistics are not."
    )


# ---------------------------------------------------------------------------
# The V3 weekly rerating architecture, as the repository actually defines it
# ---------------------------------------------------------------------------

#: What the repository states about the weekly update, with where it states it.
#: Recorded because the gap between these two rows is the whole reason two
#: parameters below carry an unresolved mathematical target.
WEEKLY_UPDATE_ARCHITECTURE: dict[str, Any] = {
    "state_quantity": "team football-strength points, per team, per path",
    "state_carrier": "models.TeamPathState.promoted_strength_points",
    "weekly_signal": "performance residual, preserved per game per team",
    "weekly_signal_source": (
        "docs/dynamic_weekly_mc_v3.md step 3: each simulated game preserves expected "
        "margin, simulated margin, winner/loser, venue, performance residual and "
        "rating-state version"
    ),
    "residual_definition_in_engine": (
        "game.simulate_game: residual_home = simulated_margin - expected_margin, where "
        "expected_margin = home strength - away strength + HFA"
    ),
    "governed_preseason_prior_decay": {
        str(k): v for k, v in sorted(v3_config.DEFAULT_PRIOR_DECAY.items())
    },
    "governed_preseason_prior_decay_status": "GOVERNED_AND_FROZEN_NOT_A_CALIBRATION_TARGET",
    "first_promoted_rerating_after_week": 2,
    "production_rerater": "rerating.BlockedGovernedRerater",
    "production_rerater_behaviour": (
        "Raises GovernanceBlock. It never computes an update, so it defines no formula."
    ),
    "only_executable_rerater": "rerating.FixtureResidualRerater",
    "only_executable_rerater_status": (
        "TEST_ONLY. Its own docstring states it is never loaded by the V3 CLI and that "
        "it exists to verify weekly-state promotion, path isolation, caps and prior "
        "decay 'without asserting a canonical V3 calibration formula'."
    ),
    "canonical_v3_weekly_update_formula_defined_in_repository": False,
    "consequence": (
        "The residual is established as the weekly signal and the team strength point "
        "as the state it moves. The functional form that maps one to the other is not "
        "defined anywhere in this repository, so any parameter whose evidence "
        "requirement depends on that form -- specifically what the movement cap binds "
        "-- cannot be settled from the code and is referred rather than inferred."
    ),
}


# ---------------------------------------------------------------------------
# The movement-cap identifiability finding
# ---------------------------------------------------------------------------

#: Recorded reading of the corpus, computed by
#: :func:`weekly_identifiability_evidence` and asserted by test. Stated as a
#: constant so the finding has a checkable shape rather than only prose.
MOVEMENT_CAP_FINDING = "MATCHUP_MARGIN_MOVEMENT_DOES_NOT_IDENTIFY_INDIVIDUAL_TEAM_MOVEMENT"


def weekly_identifiability_evidence(records: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Whether a week's recorded matchup margins identify individual team movement.

    Each game contributes one equation, ``expected_margin = R_team - R_opponent
    + home-field term``, in two unknown team ratings. Inside one week the system
    is therefore solvable only up to one free additive constant per connected
    component of that week's opponent graph. Where a component holds exactly two
    teams the free constant has the same dimension as the answer: for any
    observed change of ``d`` in a matchup's predicted margin, every pair
    ``(c, c - d)`` of individual team movements reproduces it, for every real
    ``c``. An individual-team movement magnitude is then not merely noisy, it is
    unidentified, and a cap on it cannot be measured, checked, or shown to have
    been violated.

    This function counts the components. It computes no rating, no movement and
    no statistic of any margin, on any split.
    """
    pool = [
        r
        for r in records
        if RESIDUAL_USE.test(r) and WEEK_ORDINAL_RECORDED.test(r)
    ]
    by_week: dict[tuple[int, int], list[Mapping[str, str]]] = defaultdict(list)
    for row in pool:
        by_week[(_season(row), int(float(row["week"])))].append(row)

    component_sizes: Counter[int] = Counter()
    team_week_slots = 0
    repeat_slots = 0
    for games in by_week.values():
        adjacency: dict[str, set[str]] = defaultdict(set)
        appearances: Counter[str] = Counter()
        for row in games:
            a, b = row["team"], row["opponent"]
            adjacency[a].add(b)
            adjacency[b].add(a)
            appearances[a] += 1
            appearances[b] += 1
        team_week_slots += len(appearances)
        repeat_slots += sum(1 for count in appearances.values() if count > 1)
        seen: set[str] = set()
        for team in adjacency:
            if team in seen:
                continue
            stack, component = [team], set()
            while stack:
                node = stack.pop()
                if node in component:
                    continue
                component.add(node)
                stack.extend(adjacency[node] - component)
            seen |= component
            component_sizes[len(component)] += 1

    components = sum(component_sizes.values())
    isolated_pairs = component_sizes[2]
    same_season_matchups = Counter(
        (_season(r), frozenset((r["team"], r["opponent"]))) for r in pool
    )
    repeated_matchups = sum(1 for count in same_season_matchups.values() if count > 1)
    return {
        "population_id": "EXPECTED_MARGIN_RESIDUAL_AND_WEEK_ORDINAL",
        "rows": len(pool),
        "distinct_season_weeks": len(by_week),
        "weekly_opponent_graph_components": components,
        "component_size_distribution": {
            str(k): v for k, v in sorted(component_sizes.items())
        },
        "components_of_exactly_two_teams": isolated_pairs,
        "team_week_slots": team_week_slots,
        "team_week_slots_with_more_than_one_game": repeat_slots,
        "free_dimensions_in_the_weekly_system": components,
        "unknown_team_week_ratings": team_week_slots,
        "equations_available": len(pool),
        "system_is_rank_deficient": team_week_slots > len(pool),
        "same_season_matchups": len(same_season_matchups),
        "same_season_matchups_observed_more_than_once": repeated_matchups,
        "finding": MOVEMENT_CAP_FINDING,
        "finding_detail": (
            f"{isolated_pairs} of {components} weekly opponent-graph components hold "
            "exactly two teams, so almost every week the recorded matchup margin gives "
            "one equation in two unknown team ratings. Individual team movement is "
            "identified only up to a free additive constant per component, and a bound "
            "on an unidentified quantity is not measurable. Differencing the same "
            "matchup across weeks does not rescue it either: only "
            f"{repeated_matchups} of {len(same_season_matchups)} season-matchups are "
            "observed more than once in the whole corpus."
        ),
    }


@dataclass(frozen=True)
class CapAlternative:
    """One reading of what the weekly movement cap constrains."""

    option: str
    binds: str
    identifiable_from: str
    population_id: str
    consequence: str


MOVEMENT_CAP_ALTERNATIVES: tuple[CapAlternative, ...] = (
    CapAlternative(
        option="A",
        binds="individual TEAM football-strength movement, week over week, in points",
        identifiable_from=(
            "recorded pregame component ratings on consecutive weeks for the same team"
        ),
        population_id="RESIDUAL_WEEK_AND_COMPONENT_RATINGS",
        consequence=(
            "Requires cap_component_ratings_available. The governed sources record the "
            "two component ratings for 2006 and 2007 only, so this population is "
            "entirely inside the training split: it has zero validation rows and zero "
            "holdout rows. A cap chosen this way cannot be selected on the validation "
            "split under ruling R2-CAL-OBJECTIVE and can never be scored out of sample. "
            "The two seasons are also on season-specific Baxter rating scales that the "
            "source declares not comparable across seasons, so they are two separate "
            "samples on the rating axis rather than one pooled sample."
        ),
    ),
    CapAlternative(
        option="B",
        binds="predicted MATCHUP margin movement, in points",
        identifiable_from="source-recorded predicted margins across weeks",
        population_id="RESIDUAL_AND_WEEK_ORDINAL",
        consequence=(
            "Identifiable from recorded predicted margins, but it bounds a different "
            "quantity from option A. Matchup margin movement mixes both participants' "
            "movement and the change of opponent between appearances; per "
            f"{MOVEMENT_CAP_FINDING} it does not resolve into individual team movement. "
            "Choosing this option is a decision to cap a matchup-scale quantity, not a "
            "cheaper way to cap a team-scale one."
        ),
    ),
    CapAlternative(
        option="C",
        binds=(
            "the residual contribution itself -- the pre-blend, pre-cap delta the "
            "residual coefficient produces"
        ),
        identifiable_from="the residual, which is directly observed",
        population_id="RESIDUAL_AND_WEEK_ORDINAL",
        consequence=(
            "Directly identified: the residual is observed and the contribution is the "
            "residual times the coefficient, so the cap is a bound on an observable "
            "times a parameter. This is what the test-only FixtureResidualRerater does "
            "-- it clamps coefficient*residual before prior blending -- but that fixture "
            "disclaims being the canonical V3 formula, so it is evidence of one "
            "possible reading and not authority for it."
        ),
    ),
    CapAlternative(
        option="D",
        binds=(
            "nothing measurable: the cap is a hyperparameter selected under the "
            "governed objective rather than a quantity estimated from evidence"
        ),
        identifiable_from=(
            "out-of-sample performance of the whole update rule on the validation split"
        ),
        population_id="RESIDUAL_AND_WEEK_ORDINAL",
        consequence=(
            "Needs no direct measurement of movement at all: candidate caps are scored "
            f"by {cal.PRIMARY_CALIBRATION_METRIC} on the {cal.SELECTION_SPLIT} split. "
            "It is available under every one of A, B and C, and it does not answer what "
            "the cap binds -- it only says how a value would be chosen once that is "
            "settled."
        ),
    ),
)


# ---------------------------------------------------------------------------
# Parameter specifications
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParameterSpec:
    """One unresolved V3 numerical parameter and everything its estimate needs."""

    parameter_name: str
    blocker_id: str
    mathematical_target: str
    mathematical_target_settled: bool
    required_fields: tuple[str, ...]
    optional_fields: tuple[str, ...]
    prohibited_imputations: tuple[str, ...]
    primary_population: str
    alternative_populations: tuple[str, ...]
    requires_expected_margin: bool
    requires_component_ratings: bool | str
    requires_individual_team_state: bool | str
    requires_fcs_point_adapter: bool
    fcs_disposition: str
    requires_ot_status: bool | str
    candidate_metrics: tuple[str, ...]
    selection_metric: str
    stability_checks: tuple[str, ...]
    open_methodology_questions: tuple[str, ...]
    chairman_ruling_required: bool
    notes: tuple[str, ...] = ()


#: FCS dispositions, per the mission's three-way question. FCS games stay in the
#: corpus in every case; what changes is whether a given fitting exercise may
#: read them while model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER is open.
FCS_USABLE_WITHOUT_ADAPTER = "A_USABLE_WITHOUT_THE_POINT_ADAPTER"
FCS_EXCLUDE_FROM_THIS_FIT = "B_TEMPORARILY_EXCLUDED_FROM_THIS_FITTING_EXERCISE"
FCS_RESOLVE_ADAPTER_FIRST = "C_RESOLVE_THE_ADAPTER_BEFORE_FITTING_THIS_PARAMETER"

_NO_FABRICATION = (
    "expected_margin derived from, or in any way informed by, the game's actual result",
    "expected_margin taken from a full-season retrospective fit",
    "pregame component ratings reconstructed by replay and presented as observations",
    "a synthetic kickoff time, or any default time of day, standing in for event_time",
    "overtime UNKNOWN read as regulation",
    "an invented FCS Elo-to-V3-point mapping",
    "a week ordinal inferred from week_label or stage_label",
)

PARAMETER_SPECS: tuple[ParameterSpec, ...] = (
    ParameterSpec(
        parameter_name="weekly_performance_residual_coefficient",
        blocker_id="calibration.weekly_performance_residual_coefficient",
        mathematical_target=(
            "The coefficient mapping a pregame performance residual, actual_margin - "
            "expected_margin in football points, onto the change it produces in the "
            "subject team's weekly football-strength state, before the governed "
            "preseason-prior blend and before any movement cap. The residual is "
            "established as the weekly signal by docs/dynamic_weekly_mc_v3.md step 3 "
            "and by game.simulate_game; the functional form that consumes it is not "
            "defined in the repository, so the coefficient's position in that form is "
            "known only as 'the multiplier on the residual'."
        ),
        mathematical_target_settled=False,
        required_fields=(
            "game_id",
            "season",
            "week",
            "team",
            "opponent",
            "venue",
            "expected_margin",
            "expected_margin_source_type",
            "expected_margin_provenance",
            "actual_margin",
            "temporal_order_basis",
            "temporal_order_key",
            "team_division",
            "opponent_division",
            "split",
            "evidence_domain",
        ),
        optional_fields=(
            "pregame_team_rating",
            "pregame_opponent_rating",
            "prior_rating_state",
            "game_type",
            "overtime_periods",
        ),
        prohibited_imputations=_NO_FABRICATION,
        primary_population="RESIDUAL_AND_WEEK_ORDINAL",
        alternative_populations=("RESIDUAL_WEEK_AND_COMPONENT_RATINGS",),
        requires_expected_margin=True,
        requires_component_ratings="CONDITIONAL_ON_ESTIMATION_MODE",
        requires_individual_team_state="CONDITIONAL_ON_ESTIMATION_MODE",
        requires_fcs_point_adapter=False,
        fcs_disposition=FCS_EXCLUDE_FROM_THIS_FIT,
        requires_ot_status=False,
        candidate_metrics=(
            cal.PRIMARY_CALIBRATION_METRIC,
            "residual_mean_bias_by_week",
            "week_to_week_movement_distribution",
            "rating_stability",
        ),
        selection_metric=cal.PRIMARY_CALIBRATION_METRIC,
        stability_checks=(
            "leave-one-season-out across the six training seasons",
            "residual dispersion homogeneity across week ordinals",
            "sensitivity to the 1,046 residual-eligible rows whose governed "
            "walk-forward eligibility flag is unset",
            "sensitivity to the source model's own +/-49 rating-fit margin cap",
        ),
        open_methodology_questions=(
            "ESTIMATION MODE. Two modes are available and they need different "
            "evidence. Mode A regresses observed team-state movement on the residual "
            "and needs recorded component ratings, which exist for 2006 and 2007 only. "
            "Mode B treats the coefficient as a parameter of the update rule and scores "
            "candidates by the governed out-of-sample objective, which needs no "
            "recorded rating state. Ruling R2-CAL-OBJECTIVE settles how candidates are "
            "SELECTED; it does not state how they are GENERATED.",
            "JOINT IDENTIFIABILITY WITH recent_form_weights. If the weekly performance "
            "signal is the coefficient times a weighted sum of recent residuals, and "
            "the weights are unconstrained, then scaling the coefficient by c and every "
            "weight by 1/c is observationally identical. The pair is identified only "
            "once a normalisation is stated -- weights summing to one is the obvious "
            "one, and it is not stated anywhere in this repository.",
            "Whether the coefficient is one global scalar, or varies by week, by "
            "games-played regime, or by venue.",
        ),
        chairman_ruling_required=True,
        notes=(
            "The population is stable across both estimation modes at the residual "
            "level, because both need the same residual evidence. Only mode A adds the "
            "component-rating requirement, and the matrix reports that population "
            "separately rather than choosing between them.",
        ),
    ),
    ParameterSpec(
        parameter_name="weekly_movement_cap_points",
        blocker_id="calibration.weekly_movement_cap_points",
        mathematical_target=(
            "UNRESOLVED. A bound, in football points, on some weekly movement quantity. "
            "Which quantity is not determined by the repository: the production rerater "
            "raises rather than computes, and the only executable rerater is documented "
            "as test-only and as asserting no canonical V3 formula. Four readings are "
            "enumerated in MOVEMENT_CAP_ALTERNATIVES and they do not share a population."
        ),
        mathematical_target_settled=False,
        required_fields=(
            "game_id",
            "season",
            "week",
            "team",
            "opponent",
            "expected_margin",
            "actual_margin",
            "temporal_order_basis",
            "temporal_order_key",
            "team_division",
            "opponent_division",
            "split",
        ),
        optional_fields=("prior_rating_state", "venue"),
        prohibited_imputations=_NO_FABRICATION
        + (
            "individual team movement solved out of matchup margin movement by assuming "
            "the opponent's rating held still",
            "the 2006 and 2007 rating scales pooled across seasons as though they were "
            "one scale",
        ),
        primary_population="UNRESOLVED_PENDING_RULING",
        alternative_populations=(
            "RESIDUAL_WEEK_AND_COMPONENT_RATINGS",
            "RESIDUAL_AND_WEEK_ORDINAL",
        ),
        requires_expected_margin=True,
        requires_component_ratings="TRUE_UNDER_OPTION_A_FALSE_UNDER_B_C_D",
        requires_individual_team_state="TRUE_UNDER_OPTION_A_FALSE_UNDER_B_C_D",
        requires_fcs_point_adapter=False,
        fcs_disposition=FCS_EXCLUDE_FROM_THIS_FIT,
        requires_ot_status=False,
        candidate_metrics=(
            cal.PRIMARY_CALIBRATION_METRIC,
            "week_to_week_movement_distribution",
            "rating_stability",
            "cap_binding_frequency",
        ),
        selection_metric=cal.PRIMARY_CALIBRATION_METRIC,
        stability_checks=(
            "share of weekly updates at which the cap binds, by week ordinal",
            "sensitivity of the selection metric to the cap over a range, to establish "
            "whether the objective distinguishes cap values at all",
            "under option A only: agreement between the 2006 and 2007 samples, which "
            "sit on non-comparable season-specific rating scales",
        ),
        open_methodology_questions=(
            "WHAT THE CAP BINDS. Options A through D in MOVEMENT_CAP_ALTERNATIVES. This "
            "is the question that moves the population from 1,014 rows to 4,448, and it "
            "is a semantic question about the V3 update rule, not a preference between "
            "sample sizes.",
            "Under option A the evidence is confined to two training seasons: zero "
            "validation rows and zero holdout rows. A cap ruled to bind individual team "
            "movement therefore cannot be selected on the validation split under ruling "
            "R2-CAL-OBJECTIVE, and the governed selection procedure would have to be "
            "ruled on as well.",
            "Whether the cap is symmetric, and whether it applies before or after the "
            "preseason-prior blend. The test-only fixture clamps before the blend; that "
            "is a fixture, not authority.",
        ),
        chairman_ruling_required=True,
        notes=(
            "The prior adapter report surfaced 1,014 versus 4,448 as an open question. "
            "This lane returns the mathematical finding behind it rather than a "
            "preference: matchup margin movement does not identify individual team "
            "movement, so the larger population is not a broader measurement of the "
            "same quantity -- it is a measurement of a different one.",
        ),
    ),
    ParameterSpec(
        parameter_name="recent_form_weights",
        blocker_id="calibration.recent_form_weights",
        mathematical_target=(
            "The weights applied to a team's most recent completed-game performance "
            "signals when the weekly performance state is formed. Distinct from the "
            "governed preseason-prior decay, which is already frozen at 1.00 / 0.80 / "
            "0.60 / 0.40 / 0.20 / 0.00 and is validated by "
            "V3Config.validate_architecture. Prior decay governs how fast the preseason "
            "prior stops mattering; recent-form weights govern how the in-season "
            "signals are weighted against each other. Resolving one says nothing about "
            "the other."
        ),
        mathematical_target_settled=False,
        required_fields=(
            "game_id",
            "season",
            "week",
            "team",
            "opponent",
            "expected_margin",
            "actual_margin",
            "temporal_order_basis",
            "temporal_order_key",
            "team_division",
            "opponent_division",
            "split",
        ),
        optional_fields=("prior_rating_state", "game_type", "venue"),
        prohibited_imputations=_NO_FABRICATION
        + (
            "a prior game supplied for a team that has none in the corpus",
            "a form history stitched across a season boundary",
        ),
        primary_population="RESIDUAL_AND_WEEK_ORDINAL",
        alternative_populations=("ACTUAL_MARGIN_ONLY",),
        requires_expected_margin=True,
        requires_component_ratings=False,
        requires_individual_team_state=(
            "SEQUENCE_ONLY_PER_TEAM_PRIOR_OBSERVATIONS_NOT_RECORDED_RATING_STATE"
        ),
        requires_fcs_point_adapter=False,
        fcs_disposition=FCS_EXCLUDE_FROM_THIS_FIT,
        requires_ot_status=False,
        candidate_metrics=(
            cal.PRIMARY_CALIBRATION_METRIC,
            "rating_stability",
            "week_to_week_movement_distribution",
        ),
        selection_metric=cal.PRIMARY_CALIBRATION_METRIC,
        stability_checks=(
            "history-depth strata: the estimate must be reported at each window length "
            "against the rows that actually support that window",
            "leave-one-season-out across the six training seasons",
            "agreement between the subject-only and symmetric history derivations",
        ),
        open_methodology_questions=(
            "WINDOW LENGTH. Nothing in the repository states how many prior games the "
            "weights span. The supporting population falls with window length and the "
            "matrix reports it at each depth so a window is chosen against its real "
            "sample rather than against the headline 4,448.",
            "WHETHER A TEAM'S OPPONENT-SIDE ROWS COUNT AS ITS OWN FORM HISTORY. The "
            "corpus carries one row per game from the subject team's perspective. The "
            "opponent's residual is the negation of the subject's, which is arithmetic "
            "rather than fabrication, but treating an opponent-side row as an "
            "observation of that team's form is a modelling decision. Subject-only "
            "gives 2,547 training rows at one prior game and 483 at five; symmetric "
            "gives 2,833 and 1,696. Both are reported; neither is chosen.",
            "Whether form is carried on residuals or on realised margins.",
            "NORMALISATION, shared with weekly_performance_residual_coefficient: "
            "unconstrained weights and a free coefficient are jointly unidentified.",
        ),
        chairman_ruling_required=True,
        notes=(
            "The governed preseason-prior decay is deliberately excluded from every "
            "population and every metric here. It is resolved, and re-fitting a "
            "resolved parameter under a different name is how a governed decision gets "
            "quietly reopened.",
        ),
    ),
    ParameterSpec(
        parameter_name="blowout_treatment",
        blocker_id="calibration.blowout_treatment",
        mathematical_target=(
            "UNRESOLVED, and it is at least three separable questions. (A) The "
            "descriptive frequency and shape of large realised margins, which is a "
            "function of the outcome alone. (B) How a large residual influences the "
            "weekly rerating -- clipping, winsorisation, nonlinear damping, or no "
            "special treatment -- which is a function of the prediction error. (C) "
            "Whether overtime games are treated separately, which needs a known "
            "overtime status. The three do not share a population and cannot share one "
            "ruling."
        ),
        mathematical_target_settled=False,
        required_fields=("game_id", "season", "team", "opponent", "actual_margin", "split"),
        optional_fields=(
            "expected_margin",
            "expected_margin_source_type",
            "overtime_status",
            "overtime_periods",
            "game_result",
            "game_type",
            "week",
        ),
        prohibited_imputations=_NO_FABRICATION
        + (
            "a blowout threshold read off the data and then presented as a governed "
            "definition",
            "overtime games silently pooled with regulation games in a residual tail",
        ),
        primary_population="ACTUAL_MARGIN_ONLY",
        alternative_populations=(
            "RESIDUAL_ONLY",
            "OVERTIME_KNOWN_OUTCOMES",
            "RESIDUAL_AND_OVERTIME_KNOWN",
        ),
        requires_expected_margin="FALSE_FOR_DOMAIN_A_TRUE_FOR_DOMAIN_B",
        requires_component_ratings=False,
        requires_individual_team_state=False,
        requires_fcs_point_adapter=False,
        fcs_disposition=(
            f"{FCS_USABLE_WITHOUT_ADAPTER} for domain A; "
            f"{FCS_EXCLUDE_FROM_THIS_FIT} for domains B and C"
        ),
        requires_ot_status="FALSE_FOR_DOMAINS_A_AND_B_TRUE_FOR_DOMAIN_C",
        candidate_metrics=(
            cal.PRIMARY_CALIBRATION_METRIC,
            "blowout_sensitivity",
            "rating_stability",
            "week_to_week_movement_distribution",
        ),
        selection_metric=cal.PRIMARY_CALIBRATION_METRIC,
        stability_checks=(
            "sensitivity of the selection metric to the threshold across a stated grid",
            "domain A versus domain B agreement on which rows are tail rows",
            "overtime-known subset versus overtime-unknown subset, reported separately "
            "and never pooled into a single 'no overtime' assumption",
        ),
        open_methodology_questions=(
            "THE REGIME. Clipping, winsorisation, nonlinear damping, threshold "
            "definition, or no special treatment. Nothing in the repository selects "
            "among these and this lane does not.",
            "THE THRESHOLD. There is no governed margin at which a game becomes a "
            "blowout. No threshold-conditioned tail census appears in this matrix "
            "precisely because publishing one would make an unissued threshold look "
            "settled.",
            "WHETHER THE TREATMENT APPLIES TO THE MARGIN OR THE RESIDUAL. Domain A and "
            "domain B answer different questions and support different populations.",
            "OVERTIME. Domain C has 174 validation rows and zero training rows: no "
            "training season carries a known overtime status at all. An "
            "overtime-conditioned blowout rule cannot be estimated on training "
            "evidence, only selected on validation, and that is itself a ruling.",
            "The source model already caps the margin it fits ratings on at +/-49 "
            "points, so its residual tails are partly a property of a blowout treatment "
            "the source model already applies. That is evidence about the source, not a "
            "neutral observation of an untreated regime.",
        ),
        chairman_ruling_required=True,
    ),
    ParameterSpec(
        parameter_name="game_sd_points",
        blocker_id="calibration.game_sd_points",
        mathematical_target=(
            "SPECIFIED BY V3 USE, not by a promoted value. game.simulate_game draws the "
            "simulated margin as Normal(expected_margin, game_sd_points) where "
            "expected_margin is the V3 strength difference plus the home-field term. "
            "game_sd_points is therefore the conditional dispersion of a game margin "
            "about the V3 model's own pregame expectation -- definition C, model "
            "conditional error SD -- and definition B, the SD of prediction residuals, "
            "is its empirical estimator. Definition A, the SD of raw actual margins, is "
            "a different quantity: it includes the between-team strength spread the "
            "expectation already explains, and it is systematically larger."
        ),
        mathematical_target_settled=True,
        required_fields=(
            "game_id",
            "season",
            "team",
            "opponent",
            "venue",
            "expected_margin",
            "expected_margin_source_type",
            "expected_margin_provenance",
            "actual_margin",
            "team_division",
            "opponent_division",
            "split",
        ),
        optional_fields=("overtime_status", "overtime_periods", "game_type", "week"),
        prohibited_imputations=_NO_FABRICATION
        + (
            "legacy margin SD 20.2 adopted as a value because V2 used it",
            "an overtime-excluded SD computed by treating overtime-unknown rows as "
            "regulation",
        ),
        primary_population="RESIDUAL_ONLY",
        alternative_populations=(
            "ACTUAL_MARGIN_ONLY",
            "RESIDUAL_AND_OVERTIME_KNOWN",
            "RESIDUAL_AND_OVERTIME_UNKNOWN",
        ),
        requires_expected_margin=True,
        requires_component_ratings=False,
        requires_individual_team_state=False,
        requires_fcs_point_adapter=False,
        fcs_disposition=FCS_EXCLUDE_FROM_THIS_FIT,
        requires_ot_status="NOT_TO_ESTIMATE_BUT_TO_BOUND_THE_ESTIMATE",
        candidate_metrics=(
            cal.PRIMARY_CALIBRATION_METRIC,
            "probability_calibration",
            "brier_score",
            "log_loss",
        ),
        selection_metric=cal.PRIMARY_CALIBRATION_METRIC,
        stability_checks=(
            "season-by-season dispersion across the six training seasons",
            "overtime-known versus overtime-unknown subsets, reported separately",
            "scale transfer: the corpus residuals are BAXTER-MOV-v1.0-R errors, and V3 "
            "strength points are a different axis; the transfer is an assumption to be "
            "checked, not a given",
        ),
        open_methodology_questions=(
            "OVERTIME. 3,783 of the 4,643 residual rows carry overtime status UNKNOWN, "
            "and every overtime-known residual row is in 2024 or 2025 -- the training "
            "split has none. Any SD computed from the training split is therefore a "
            "mixture over an unknown overtime proportion, and college overtime "
            "manufactures margins no pregame model predicts, which is the direction of "
            "the unexplained 20.2. Whether overtime games are excluded is unresolved "
            "and the corpus cannot settle it for the training split at all.",
            "SCALE. The residuals available are the source model's prediction errors on "
            "a season-specific opponent-adjusted margin scale. game_sd_points is a V3 "
            "quantity. Whether the source model's conditional error SD may stand as the "
            "V3 conditional error SD is a ruling, and the FCS point-scale adapter is a "
            "narrower instance of the same unresolved question.",
            "Whether the Gaussian form itself is right, which Brier and log-loss "
            "diagnostics bear on but this lane does not test.",
        ),
        chairman_ruling_required=True,
        notes=(
            "Legacy 20.2 stays UNAPPROVED_HISTORICAL_EVIDENCE. It is also, on its own "
            "terms, definition A measured on simulated engine output, not definition B "
            "measured on prediction errors, so it is not even a candidate value for the "
            "quantity V3 actually consumes.",
            "governance.GAME_SD_CALIBRATION_OPEN is a separate blocker from "
            "calibration.game_sd_points and retires separately. Numerical evidence for "
            "the coefficient does not close the governance item: the register records "
            "margin calibration as OPEN with recommended action 'rerun current engine "
            "calibration', and closing that needs its own Chairman promotion after the "
            "evidence exists. This lane produces neither.",
        ),
    ),
    ParameterSpec(
        parameter_name="sample_size_regularization",
        blocker_id="calibration.sample_size_regularization",
        mathematical_target=(
            "The shrinkage applied to a team's performance-derived weekly state as a "
            "function of how many games that team has completed. It is explicitly a "
            "separate mechanism from the preseason-prior decay: "
            "docs/dynamic_weekly_mc_v3.md step 7 records that after Week 5 the "
            "preseason-specific prior is zero while sample-size regularization 'remains "
            "a separate unresolved mechanism'. Its argument is the team's prior-game "
            "count; its target is the weight on the performance state."
        ),
        mathematical_target_settled=False,
        required_fields=(
            "game_id",
            "season",
            "week",
            "team",
            "opponent",
            "expected_margin",
            "actual_margin",
            "games_played_to_date",
            "temporal_order_basis",
            "temporal_order_key",
            "split",
        ),
        optional_fields=("prior_rating_state", "pregame_team_rating", "game_type"),
        prohibited_imputations=_NO_FABRICATION
        + (
            "games_played_to_date derived by counting a team's appearances inside the "
            "corpus and presented as the source-recorded count -- the corpus is not the "
            "team's schedule, and a count over rows that happen to be present is a "
            "different quantity",
            "a low-sample regime extrapolated from the fitted shape of a "
            "higher-sample one",
        ),
        primary_population="FULL_WALKFORWARD_OBSERVATION_CONTRACT",
        alternative_populations=("RESIDUAL_AND_WEEK_ORDINAL",),
        requires_expected_margin=True,
        requires_component_ratings=False,
        requires_individual_team_state=True,
        requires_fcs_point_adapter=False,
        fcs_disposition=FCS_EXCLUDE_FROM_THIS_FIT,
        requires_ot_status=False,
        candidate_metrics=(
            cal.PRIMARY_CALIBRATION_METRIC,
            "rating_stability",
            "week_to_week_movement_distribution",
        ),
        selection_metric=cal.PRIMARY_CALIBRATION_METRIC,
        stability_checks=(
            "estimate reported per prior-game stratum, never pooled into a single "
            "number that hides which regimes carry it",
            "leave-one-season-out across the six training seasons",
            "behaviour at the stratum boundaries, where a shrinkage schedule is most "
            "likely to be discontinuous",
        ),
        open_methodology_questions=(
            "FIELD ADMISSION. games_played_to_date sits in "
            "calibration_contract.FIELDS_REQUIRING_ADMISSION_RULING and is not on the "
            "governed observation allowlist. The count is recorded inside "
            "prior_rating_state on all 3,259 paired observations, but a shrinkage "
            "schedule fitted against a field reachable only inside an opaque blob is "
            "fitted against a field no reviewer can see. This needs its own ruling, and "
            "widening the allowlist because a fit wanted the column is exactly the move "
            "the contract forbids.",
            "THE LOW-SAMPLE REGIME IS ABSENT. Every recorded prior-game count in the "
            "paired subset is at least three, because the frozen BAXTER-MOV-v1.0-R "
            "control requires three prior games per team and its own eligibility flag "
            "excludes the rest. There are zero admitted observations at zero, one or "
            "two prior games -- precisely the regime this parameter exists to govern. "
            "1,046 residual-eligible corpus rows carry that unset eligibility flag and "
            "are the only trace of the regime, and they carry no admitted games-played "
            "count. No candidate schedule can be estimated below three prior games from "
            "the frozen artifacts, and extrapolating into it would be invention.",
            "WHAT IS SHRUNK TOWARD WHAT. A shrinkage target -- the preseason prior, the "
            "league mean, zero -- is not stated anywhere, and after Week 5 the "
            "preseason prior weight is governed to zero, so it cannot be the target "
            "there without contradicting a resolved decision.",
        ),
        chairman_ruling_required=True,
    ),
)

PARAMETER_SPECS_BY_NAME = {spec.parameter_name: spec for spec in PARAMETER_SPECS}


# ---------------------------------------------------------------------------
# Named populations
# ---------------------------------------------------------------------------

#: Each named population is the conjunction of the requirements the estimation
#: actually has. They are deliberately different from each other: that
#: difference is the whole content of ruling R9's separation of membership from
#: use-specific eligibility.
POPULATION_DEFINITIONS: dict[str, tuple[EvidencePredicate, ...]] = {
    "ACTUAL_MARGIN_ONLY": (OUTCOME_USE,),
    "RESIDUAL_ONLY": (RESIDUAL_USE,),
    "RESIDUAL_AND_WEEK_ORDINAL": (RESIDUAL_USE, WEEK_ORDINAL_RECORDED),
    "RESIDUAL_WEEK_AND_COMPONENT_RATINGS": (
        RESIDUAL_USE,
        WEEK_ORDINAL_RECORDED,
        COMPONENT_RATINGS,
    ),
    "OVERTIME_KNOWN_OUTCOMES": (OVERTIME_USE,),
    "RESIDUAL_AND_OVERTIME_KNOWN": (RESIDUAL_USE, OVERTIME_KNOWN),
    "RESIDUAL_AND_OVERTIME_UNKNOWN": (
        RESIDUAL_USE,
        EvidencePredicate(
            predicate_id="overtime_status_unknown",
            kind="capability",
            reason=(
                "The complement, reported so the overtime uncertainty is visible as a "
                "population rather than absorbed silently into a pooled estimate."
            ),
            test=lambda row: not _flag(row, "overtime_status_known"),
        ),
    ),
    "FULL_WALKFORWARD_OBSERVATION_CONTRACT": (
        _use_predicate(
            "FULL_WALKFORWARD_OBSERVATION_CONTRACT",
            "The strictest use: the full residual-model observation contract enforced "
            "by calibration.load_admitted_observations. It is the only population whose "
            "rows carry a recorded prior-game count.",
        ),
    ),
}


def named_populations(records: Sequence[Mapping[str, str]]) -> dict[str, Population]:
    return {
        name: build_population(name, records, predicates)
        for name, predicates in POPULATION_DEFINITIONS.items()
    }


# ---------------------------------------------------------------------------
# Depth and stratum censuses
# ---------------------------------------------------------------------------


def recent_form_depth_census(
    records: Sequence[Mapping[str, str]], *, max_depth: int = 6
) -> dict[str, Any]:
    """How many rows have at least k prior residual-bearing observations.

    Counts prior observations that exist in the corpus. It is not a claim about
    how many games a team had actually played: the corpus is a governed evidence
    set, not a schedule, and conflating the two is how a fabricated field enters
    under an honest name. Reported under both readings of a team's history --
    subject-side rows only, and both sides -- because which one counts is an
    open modelling question rather than a settled fact.
    """
    pool = [r for r in records if RESIDUAL_USE.test(r) and WEEK_ORDINAL_RECORDED.test(r)]
    pool.sort(key=lambda r: (_season(r), int(float(r["week"])), int(r["source_sequence"])))
    out: dict[str, Any] = {
        "ordering_basis": "season, source-recorded week ordinal, governed source sequence",
        "counts_corpus_rows_not_games_played": True,
    }
    for mode in ("subject_only", "symmetric"):
        seen: Counter[tuple[int, str]] = Counter()
        by_depth: dict[int, Counter[str]] = {k: Counter() for k in range(max_depth + 1)}
        by_depth_season: dict[int, Counter[int]] = {
            k: Counter() for k in range(max_depth + 1)
        }
        for row in pool:
            season, team, opponent = _season(row), row["team"], row["opponent"]
            prior = seen[(season, team)]
            for k in range(max_depth + 1):
                if prior >= k:
                    by_depth[k][split_of(row)] += 1
                    by_depth_season[k][season] += 1
            seen[(season, team)] += 1
            if mode == "symmetric":
                seen[(season, opponent)] += 1
        out[mode] = {
            str(k): {
                "rows": sum(by_depth[k].values()),
                "by_split": {s: by_depth[k].get(s, 0) for s in cal.DATA_SPLITS},
                "by_season": {str(s): by_depth_season[k].get(s, 0) for s in ALL_SEASONS},
                "holdout_usable_for_selection": False,
            }
            for k in range(max_depth + 1)
        }
    return out


#: Prior-game strata. The first stratum is the regime sample-size regularization
#: exists for, and it is the one the evidence does not reach.
PRIOR_GAME_STRATA: tuple[tuple[str, int, int | None], ...] = (
    ("0-2", 0, 2),
    ("3-5", 3, 5),
    ("6-8", 6, 8),
    ("9-11", 9, 11),
    ("12+", 12, None),
)


def prior_game_stratum(count: int) -> str:
    for label, low, high in PRIOR_GAME_STRATA:
        if count >= low and (high is None or count <= high):
            return label
    raise InputValidationError(f"Prior-game count {count} falls in no stratum")


def sample_size_stratum_census(observations: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """Recorded prior-game counts, by stratum and by split.

    Reads ``prior_rating_state.games_played_to_date`` exactly as the governed
    source recorded it. A row without one is counted as missing, never as zero.
    """
    by_stratum: Counter[str] = Counter()
    by_split: dict[str, Counter[str]] = {s: Counter() for s in cal.DATA_SPLITS}
    missing = 0
    observed_min: int | None = None
    observed_max: int | None = None
    for row in observations:
        try:
            state = json.loads(row["prior_rating_state"])
        except (ValueError, KeyError):
            state = {}
        raw = state.get("games_played_to_date")
        if raw is None:
            missing += 1
            continue
        count = int(float(raw))
        observed_min = count if observed_min is None else min(observed_min, count)
        observed_max = count if observed_max is None else max(observed_max, count)
        label = prior_game_stratum(count)
        by_stratum[label] += 1
        by_split[str(row["split"]).strip().lower()][label] += 1
    return {
        "field": "prior_rating_state.games_played_to_date",
        "field_admission_status": "REQUIRES_ADMISSION_RULING_NOT_ON_GOVERNED_ALLOWLIST",
        "rows_with_recorded_count": sum(by_stratum.values()),
        "rows_without_recorded_count": missing,
        "missing_count_imputed": False,
        "observed_minimum": observed_min,
        "observed_maximum": observed_max,
        "by_stratum": {
            label: {
                "rows": by_stratum.get(label, 0),
                "by_split": {s: by_split[s].get(label, 0) for s in cal.DATA_SPLITS},
                "holdout_usable_for_selection": False,
            }
            for label, _, _ in PRIOR_GAME_STRATA
        },
        "low_sample_regime_rows": by_stratum.get("0-2", 0),
        "finding": (
            "LOW_SAMPLE_REGIME_ABSENT_FROM_ADMITTED_EVIDENCE"
            if by_stratum.get("0-2", 0) == 0
            else "LOW_SAMPLE_REGIME_PRESENT"
        ),
        "finding_detail": (
            "The frozen BAXTER-MOV-v1.0-R control requires three prior games per team "
            "and marks rows below that ineligible, so no admitted observation carries a "
            "prior-game count under three. The regime sample_size_regularization exists "
            "to govern is therefore unrepresented, and it is reported as absent rather "
            "than extrapolated into."
        ),
    }


def low_sample_trace_census(records: Sequence[Mapping[str, str]]) -> dict[str, Any]:
    """The residual-eligible rows whose governed walk-forward eligibility is unset.

    These are the only trace the frozen corpus carries of the low-prior-game
    regime. They hold a residual and no admitted games-played count, so they
    locate the gap without filling it.
    """
    pool = [
        r
        for r in records
        if RESIDUAL_USE.test(r) and not _flag(r, "walkforward_eligibility_flag_set")
    ]
    return {
        "rows": len(pool),
        "by_season": {
            str(s): sum(1 for r in pool if _season(r) == s) for s in ALL_SEASONS
        },
        "by_split": {
            s: sum(1 for r in pool if split_of(r) == s) for s in cal.DATA_SPLITS
        },
        "carries_recorded_games_played_count": False,
        "note": (
            "The governed source's own eligibility flag is unset on these rows. The "
            "5,148 adapter's exclusion census attributes 1,223 corpus rows to the "
            "frozen minimum-three-prior-games control; these are the residual-eligible "
            "members of that population. They are corpus members under ruling R9 and "
            "are not deleted, but they carry no admitted prior-game count and their "
            "expected margins come from predictions the source control itself declared "
            "ineligible."
        ),
    }


# ---------------------------------------------------------------------------
# Metric policy
# ---------------------------------------------------------------------------

#: Attached per parameter above. Restated here as the policy the matrix obeys,
#: read from the harness rather than duplicated by hand.
METRIC_POLICY: dict[str, Any] = {
    "primary": cal.PRIMARY_CALIBRATION_METRIC,
    "primary_direction": cal.PRIMARY_CALIBRATION_DIRECTION,
    "primary_ruling": "R2-CAL-OBJECTIVE",
    "witnesses_reported_independently": list(cal.INDEPENDENT_WITNESSES),
    "witness_hierarchy": [
        "baxter (primary)",
        "colley_matrix (secondary witness)",
        "srs (third witness)",
    ],
    "weighted_witness_composite": "REFUSED",
    "weighted_witness_composite_gate": "calibration.reject_witness_composite",
    "supporting_diagnostics": list(cal.SUPPORTING_DIAGNOSTICS),
    "selection_split": cal.SELECTION_SPLIT,
    "holdout_use": cal.HOLDOUT_USE,
    "metrics_attached_only_where_mathematically_relevant": True,
    "parameter_values_chosen_in_this_lane": False,
}


# ---------------------------------------------------------------------------
# Chairman rulings this lane raises rather than answers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChairmanRuling:
    ruling_id: str
    parameter: str
    question: str
    alternatives: tuple[str, ...]
    consequence_of_not_ruling: str
    this_lane_decided_it: bool = False


CHAIRMAN_RULINGS_REQUIRED: tuple[ChairmanRuling, ...] = (
    ChairmanRuling(
        ruling_id="CAL-CAP-SEMANTICS",
        parameter="weekly_movement_cap_points",
        question=(
            "What does weekly_movement_cap_points bind: individual team rating "
            "movement, predicted matchup margin movement, the residual contribution, or "
            "nothing measurable because the cap is a selected hyperparameter?"
        ),
        alternatives=tuple(
            f"{a.option}: {a.binds} -- evidence population {a.population_id}"
            for a in MOVEMENT_CAP_ALTERNATIVES
        ),
        consequence_of_not_ruling=(
            "The evidence population is 1,014 rows under option A and 4,448 under "
            "options B, C and D, and option A has no validation rows at all, so the "
            "governed selection procedure is unavailable under it. No cap can be fitted "
            "until this is settled, and settling it by picking the larger population "
            "would be choosing a quantity by its sample size."
        ),
    ),
    ChairmanRuling(
        ruling_id="CAL-COEFFICIENT-NORMALISATION",
        parameter="weekly_performance_residual_coefficient",
        question=(
            "Under what normalisation are the residual coefficient and the recent-form "
            "weights jointly identified?"
        ),
        alternatives=(
            "recent-form weights constrained to sum to one, leaving the coefficient free",
            "the coefficient fixed and the weights left unnormalised",
            "the two fitted as one composite vector and never reported separately",
        ),
        consequence_of_not_ruling=(
            "Scaling the coefficient by c and every weight by 1/c is observationally "
            "identical, so the two parameters are not separately identified and any "
            "pair of promoted values would be one arbitrary point on a ridge."
        ),
    ),
    ChairmanRuling(
        ruling_id="CAL-ESTIMATION-MODE",
        parameter="weekly_performance_residual_coefficient",
        question=(
            "Are candidate estimates generated by direct regression on recorded rating "
            "movement, or by scoring candidate update rules under the governed "
            "objective?"
        ),
        alternatives=(
            "direct regression on observed movement -- needs component ratings, so "
            "2006 and 2007 only",
            "candidate update rules scored under the governed objective -- needs no "
            "recorded rating state",
            "both, with the first furnishing a prior and the second selecting",
        ),
        consequence_of_not_ruling=(
            "Ruling R2-CAL-OBJECTIVE governs selection and is silent on generation. "
            "Without this, the evidence a candidate rests on is decided by whoever runs "
            "the fit."
        ),
    ),
    ChairmanRuling(
        ruling_id="CAL-RECENT-FORM-WINDOW",
        parameter="recent_form_weights",
        question=(
            "How many prior games does the recent-form window span, and does a team's "
            "opponent-side corpus row count as its own form history?"
        ),
        alternatives=(
            "a stated window length with weights fitted at that depth",
            "window length itself selected under the governed objective on validation",
            "subject-side history only",
            "symmetric history, admitting the negated opponent-side residual",
        ),
        consequence_of_not_ruling=(
            "The supporting population falls from 2,833 training rows at one prior game "
            "to 1,696 at five under the symmetric reading, and from 2,547 to 483 under "
            "the subject-only reading. A window chosen after seeing which depth fits "
            "best has been selected on the same data it is scored on."
        ),
    ),
    ChairmanRuling(
        ruling_id="CAL-BLOWOUT-REGIME",
        parameter="blowout_treatment",
        question=(
            "Which blowout regime applies -- clipping, winsorisation, nonlinear "
            "damping, or none -- at what threshold, applied to the margin or to the "
            "residual, and are overtime games treated separately?"
        ),
        alternatives=(
            "no special treatment",
            "hard clipping at a governed threshold",
            "winsorisation at a governed quantile",
            "nonlinear damping with a governed shape",
        ),
        consequence_of_not_ruling=(
            "The descriptive population is 5,144 rows, the residual-based population "
            "4,643, and the overtime-sensitive population 931 with zero training rows. "
            "Without the ruling there is no way to say which of those three a blowout "
            "candidate is even entitled to read."
        ),
    ),
    ChairmanRuling(
        ruling_id="CAL-GAME-SD-OVERTIME-AND-SCALE",
        parameter="game_sd_points",
        question=(
            "Are overtime games excluded from the residual pool, and may the source "
            "model's conditional error SD stand as the V3 conditional error SD?"
        ),
        alternatives=(
            "overtime included, and the SD reported as a mixture over unknown overtime "
            "status",
            "overtime excluded, which is estimable on validation only because no "
            "training season records overtime status",
            "the source model's error SD adopted as the V3 value",
            "the source model's error SD treated as a prior only, pending a V3-scale "
            "measurement",
        ),
        consequence_of_not_ruling=(
            "3,783 of 4,643 residual rows carry overtime UNKNOWN and every "
            "overtime-known residual row is in 2024 or 2025. Any training-split SD is a "
            "mixture over an unknown overtime proportion, in the direction that "
            "produced the unexplained legacy 20.2."
        ),
    ),
    ChairmanRuling(
        ruling_id="CAL-GAMES-PLAYED-FIELD-ADMISSION",
        parameter="sample_size_regularization",
        question=(
            "Is games_played_to_date admitted as a governed observation field, and how "
            "is the regularization identified below three prior games where no admitted "
            "observation exists?"
        ),
        alternatives=(
            "admit the field and fit only at three or more prior games, leaving the low "
            "regime governed by an explicit stated policy rather than by evidence",
            "admit the field and reissue the data plane to carry the low-n rows with "
            "their source-recorded counts",
            "decline the field and identify the parameter some other way, which would "
            "have to be named",
        ),
        consequence_of_not_ruling=(
            "The parameter is a function of a count that is not on the governed "
            "observation allowlist, and the regime it exists to govern -- zero, one and "
            "two prior games -- has zero admitted observations."
        ),
    ),
)


# ---------------------------------------------------------------------------
# The FCS dependency
# ---------------------------------------------------------------------------

FCS_DEPENDENCY: dict[str, Any] = {
    "blocker": "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
    "policy": "FCS Elo = 1250, fixed, no toggle (ruling R2-FCS-ELO-1250)",
    "point_scale_mapping_status": "UNRESOLVED",
    "promoted_by_this_lane": False,
    "fcs_removed_from_canonical_corpus": False,
    "mapping_invented": False,
    "per_parameter": {
        spec.parameter_name: spec.fcs_disposition for spec in PARAMETER_SPECS
    },
    "mechanism": (
        "The EXPECTED_MARGIN_RESIDUAL and POINT_SCALE_DEPENDENT uses already refuse "
        "rows flagged cap_requires_unresolved_fcs_point_adapter, so every "
        "residual-based population in this matrix excludes the 69 FCS-participant rows "
        "without any exclusion being applied here. The outcome-only population does not "
        "refuse them, because a realised margin needs no rating scale."
    ),
    "resolve_adapter_before_fitting": [],
    "resolve_adapter_before_fitting_note": (
        "No parameter requires the adapter to be resolved first. Every residual-based "
        "parameter is estimable on FBS-versus-FBS evidence alone, at the cost of the 69 "
        "FCS rows, and the descriptive blowout domain can read them today. Resolving "
        "the adapter widens evidence; it does not unblock any of the six."
    ),
}


# ---------------------------------------------------------------------------
# Blocker census
# ---------------------------------------------------------------------------

AUTHORITATIVE_BLOCKERS: tuple[str, ...] = tuple(
    sorted(blocker_report.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED)
)


def blocker_census() -> dict[str, Any]:
    """The eight live blockers, computed from the register rather than restated."""
    return {
        "expected": list(AUTHORITATIVE_BLOCKERS),
        "count": len(AUTHORITATIVE_BLOCKERS),
        "retired_by_this_lane": [],
        "opened_by_this_lane": [],
        "classification": {
            b: blocker_report.R3_REMAINING_CLASSIFICATION[b]
            for b in AUTHORITATIVE_BLOCKERS
        },
    }


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MatrixResult:
    artifacts: dict[str, Any]
    populations: dict[str, Population]
    identifiability: dict[str, Any]
    depth_census: dict[str, Any]
    stratum_census: dict[str, Any]
    low_sample_trace: dict[str, Any]


def build(root: Path | None = None) -> MatrixResult:
    base = root or repository_root()
    artifacts = verify_frozen_artifacts(base)
    corpus = load_corpus(base)
    observations = load_observations(base)
    return MatrixResult(
        artifacts=artifacts,
        populations=named_populations(corpus),
        identifiability=weekly_identifiability_evidence(corpus),
        depth_census=recent_form_depth_census(corpus),
        stratum_census=sample_size_stratum_census(observations),
        low_sample_trace=low_sample_trace_census(corpus),
    )


def _parameter_record(spec: ParameterSpec, result: MatrixResult) -> dict[str, Any]:
    populations = result.populations
    referenced = [spec.primary_population, *spec.alternative_populations]
    resolved = {
        name: populations[name].as_dict()
        for name in referenced
        if name in populations
    }
    if spec.primary_population in populations:
        primary = populations[spec.primary_population]
        training = primary.training_rows
        validation = primary.validation_rows
        holdout = primary.holdout_rows
        per_season = {str(k): v for k, v in sorted(primary.by_season.items())}
        domains = dict(sorted(primary.by_evidence_domain.items()))
        divisions = {
            "fbs_rows": primary.fbs_rows,
            "fcs_rows": primary.fcs_rows,
            "other_or_unknown_classification_rows": primary.other_or_unknown_division_rows,
        }
        overtime = {
            "ot_known_rows": primary.overtime_known_rows,
            "ot_unknown_rows": primary.overtime_unknown_rows,
        }
    else:
        training = validation = holdout = None
        per_season = {}
        domains = {}
        divisions = {}
        overtime = {}

    record: dict[str, Any] = {
        "parameter_name": spec.parameter_name,
        "blocker_id": spec.blocker_id,
        "mathematical_target": spec.mathematical_target,
        "mathematical_target_settled": spec.mathematical_target_settled,
        "required_fields": list(spec.required_fields),
        "required_fields_awaiting_admission_ruling": [
            name
            for name in spec.required_fields
            if name in FIELDS_AWAITING_ADMISSION_RULING
        ],
        "optional_fields": list(spec.optional_fields),
        "optional_fields_awaiting_admission_ruling": [
            name
            for name in spec.optional_fields
            if name in FIELDS_AWAITING_ADMISSION_RULING
        ],
        "prohibited_imputations": list(spec.prohibited_imputations),
        "primary_population": spec.primary_population,
        "alternative_populations": list(spec.alternative_populations),
        "populations": resolved,
        "training_eligible_rows": training,
        "validation_eligible_rows": validation,
        "holdout_available_rows": holdout,
        "holdout_usable_for_selection": False,
        # Exact populations exist for every parameter. For a parameter whose
        # mathematical target is unsettled they exist per alternative rather
        # than as one number, and reporting a single number would be the
        # silent resolution this lane exists to avoid.
        "populations_exact": bool(resolved),
        "populations_exact_per_alternative": spec.primary_population not in populations,
        "per_season_eligibility": per_season,
        "evidence_domain_census": domains,
        "division_census": divisions,
        "overtime_census": overtime,
        "requires_expected_margin": spec.requires_expected_margin,
        "requires_component_ratings": spec.requires_component_ratings,
        "requires_individual_team_state": spec.requires_individual_team_state,
        "requires_FCS_point_adapter": spec.requires_fcs_point_adapter,
        "fcs_disposition": spec.fcs_disposition,
        "requires_OT_status": spec.requires_ot_status,
        "candidate_metrics": list(spec.candidate_metrics),
        "selection_metric": spec.selection_metric,
        "selection_split": cal.SELECTION_SPLIT,
        "stability_checks": list(spec.stability_checks),
        "open_methodology_questions": list(spec.open_methodology_questions),
        "chairman_ruling_required": spec.chairman_ruling_required,
        "chairman_rulings": [
            r.ruling_id
            for r in CHAIRMAN_RULINGS_REQUIRED
            if r.parameter == spec.parameter_name
        ],
        "notes": list(spec.notes),
        "fitted": False,
        "promoted": False,
    }
    if spec.parameter_name == "weekly_movement_cap_points":
        record["population_alternatives"] = [
            {
                "option": a.option,
                "binds": a.binds,
                "identifiable_from": a.identifiable_from,
                "population_id": a.population_id,
                "rows": populations[a.population_id].rows,
                "training_eligible_rows": populations[a.population_id].training_rows,
                "validation_eligible_rows": populations[a.population_id].validation_rows,
                "holdout_available_rows": populations[a.population_id].holdout_rows,
                "consequence": a.consequence,
            }
            for a in MOVEMENT_CAP_ALTERNATIVES
        ]
        record["identifiability_finding"] = result.identifiability
        record["training_eligible_rows_by_alternative"] = {
            a.option: populations[a.population_id].training_rows
            for a in MOVEMENT_CAP_ALTERNATIVES
        }
        record["validation_eligible_rows_by_alternative"] = {
            a.option: populations[a.population_id].validation_rows
            for a in MOVEMENT_CAP_ALTERNATIVES
        }
        record["holdout_available_rows_by_alternative"] = {
            a.option: populations[a.population_id].holdout_rows
            for a in MOVEMENT_CAP_ALTERNATIVES
        }
        record["per_season_eligibility_by_alternative"] = {
            a.option: {
                str(k): v
                for k, v in sorted(populations[a.population_id].by_season.items())
            }
            for a in MOVEMENT_CAP_ALTERNATIVES
        }
        record["selection_available_under_alternative"] = {
            a.option: populations[a.population_id].validation_rows > 0
            for a in MOVEMENT_CAP_ALTERNATIVES
        }
    if spec.parameter_name == "recent_form_weights":
        record["history_depth_census"] = result.depth_census
        record["governed_preseason_prior_decay_is_separate"] = True
        record["governed_preseason_prior_decay"] = WEEKLY_UPDATE_ARCHITECTURE[
            "governed_preseason_prior_decay"
        ]
    if spec.parameter_name == "sample_size_regularization":
        record["prior_game_stratum_census"] = result.stratum_census
        record["low_sample_regime_trace"] = result.low_sample_trace
    if spec.parameter_name == "blowout_treatment":
        record["evidence_domains_of_the_question"] = {
            "A_outcome_only_blowout_frequency": populations["ACTUAL_MARGIN_ONLY"].rows,
            "B_residual_based_rerating_influence": populations["RESIDUAL_ONLY"].rows,
            "C_overtime_sensitive": populations["OVERTIME_KNOWN_OUTCOMES"].rows,
            "B_and_C_combined": populations["RESIDUAL_AND_OVERTIME_KNOWN"].rows,
        }
        record["threshold_conditioned_tail_census_published"] = False
    if spec.parameter_name == "game_sd_points":
        record["definition_census"] = {
            "A_sd_of_raw_actual_margins": populations["ACTUAL_MARGIN_ONLY"].rows,
            "B_sd_of_prediction_residuals": populations["RESIDUAL_ONLY"].rows,
            "C_model_conditional_error_sd": (
                "Same population as B. C is the quantity; B is its estimator."
            ),
            "D_definition_specified_by_v3": (
                "game.simulate_game consumes game_sd_points as the SD of the margin "
                "draw about the V3 expected margin, which is C."
            ),
            "ot_known_eligible_rows": populations["RESIDUAL_AND_OVERTIME_KNOWN"].rows,
            "ot_unknown_eligible_rows": populations["RESIDUAL_AND_OVERTIME_UNKNOWN"].rows,
            "ot_known_training_rows": populations[
                "RESIDUAL_AND_OVERTIME_KNOWN"
            ].training_rows,
        }
        record["legacy_margin_sd_20_2_status"] = "UNAPPROVED_HISTORICAL_EVIDENCE"
        record["legacy_margin_sd_20_2_used"] = False
        record["separate_governance_blocker"] = "governance.GAME_SD_CALIBRATION_OPEN"
        record["separate_chairman_promotion_required_after_evidence"] = True
    return record


def status_document(result: MatrixResult) -> dict[str, Any]:
    records = [_parameter_record(spec, result) for spec in PARAMETER_SPECS]
    unresolved = [r for r in records if r["chairman_ruling_required"]]
    # Readiness is about whether the matrix is complete and honest, not about
    # whether every question is answered. An ambiguity that is surfaced with its
    # exact alternative populations is a delivered finding; one that is silently
    # resolved to keep a single number in the column would not be.
    ready = (
        len(records) == len(cal.CALIBRATION_FIELDS)
        and all(r["required_fields"] for r in records)
        and all(r["populations_exact"] for r in records)
        and all(r["candidate_metrics"] and r["selection_metric"] for r in records)
        and all(not r["fitted"] and not r["promoted"] for r in records)
        and not LANE_FITS_PARAMETERS
        and not LANE_PROMOTES_PARAMETERS
        and not LANE_SCORES_HOLDOUT
        and len(AUTHORITATIVE_BLOCKERS) == 8
    )
    return {
        "matrix_id": MATRIX_ID,
        "matrix_version": MATRIX_VERSION,
        "matrix_lane": MATRIX_LANE,
        "frozen_artifacts": result.artifacts,
        "canonical_corpus_rows": CANONICAL_CORPUS_ROWS,
        "fully_paired_walkforward_rows": PAIRED_OBSERVATION_ROWS,
        "limited_capability_corpus_members": LIMITED_CAPABILITY_CORPUS_MEMBERS,
        "corpus_rebuilt_by_this_lane": LANE_REBUILDS_CORPUS,
        "corpus_ruling": cal.CORPUS_RULING,
        "partition_policy": {
            "training": list(TRAINING_SEASONS),
            "validation": list(VALIDATION_SEASONS),
            "holdout": list(HOLDOUT_SEASONS),
            "split_policy": dict(sorted(SPLIT_POLICY.items())),
            "assignment": cal.TEMPORAL_SPLIT_ASSIGNMENT,
            "holdout_prohibited_decisions": list(HOLDOUT_PROHIBITED_DECISIONS),
            "holdout_scored_in_this_lane": LANE_SCORES_HOLDOUT,
            "population_census_of_holdout_permitted": True,
            "model_selection_statistics_on_holdout_permitted": False,
        },
        "weekly_update_architecture": WEEKLY_UPDATE_ARCHITECTURE,
        "row_eligibility_principle": {
            "ruling": cal.CORPUS_RULING,
            "membership_basis": cal.CORPUS_MEMBERSHIP_BASIS,
            "membership_is_separate_from_use_specific_eligibility": True,
            "universal_exclusion_mask_applied": False,
            "largest_population": max(p.rows for p in result.populations.values()),
            "smallest_population": min(p.rows for p in result.populations.values()),
            "distinct_population_sizes": len(
                {p.rows for p in result.populations.values()}
            ),
        },
        "populations": {
            name: population.as_dict()
            for name, population in sorted(result.populations.items())
        },
        "parameters": records,
        "movement_cap_identifiability": result.identifiability,
        "movement_cap_alternatives": [
            {
                "option": a.option,
                "binds": a.binds,
                "identifiable_from": a.identifiable_from,
                "population_id": a.population_id,
                "rows": result.populations[a.population_id].rows,
                "consequence": a.consequence,
            }
            for a in MOVEMENT_CAP_ALTERNATIVES
        ],
        "metric_policy": METRIC_POLICY,
        "fcs_dependency": FCS_DEPENDENCY,
        "chairman_rulings_required": [
            {
                "ruling_id": r.ruling_id,
                "parameter": r.parameter,
                "question": r.question,
                "alternatives": list(r.alternatives),
                "consequence_of_not_ruling": r.consequence_of_not_ruling,
                "decided_by_this_lane": r.this_lane_decided_it,
            }
            for r in CHAIRMAN_RULINGS_REQUIRED
        ],
        "blockers": blocker_census(),
        "parameters_fitted_by_this_lane": [],
        "parameters_promoted_by_this_lane": [],
        "fitted": LANE_FITS_PARAMETERS,
        "promoted": LANE_PROMOTES_PARAMETERS,
        "unresolved_parameter_count": len(unresolved),
        "handoff": (
            "V3_PARAMETER_EVIDENCE_MATRIX_READY"
            if ready
            else "V3_PARAMETER_EVIDENCE_MATRIX_BLOCKED"
        ),
    }


def status_bytes(result: MatrixResult) -> bytes:
    """The status artifact's exact bytes. Sorted keys, LF endings, trailing newline."""
    return (json.dumps(status_document(result), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


DEFAULT_STATUS_PATH = Path(
    "reference/dynamic_weekly_mc_v3/V3_PARAMETER_EVIDENCE_MATRIX_R1.json"
)


def write_status(result: MatrixResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(status_bytes(result))
    return path


def main(root: Path | None = None) -> int:  # pragma: no cover - operator entrypoint
    base = root or repository_root()
    result = build(base)
    write_status(result, base / DEFAULT_STATUS_PATH)
    document = status_document(result)
    print(json.dumps(document["movement_cap_identifiability"], indent=2, sort_keys=True))
    print(document["handoff"])
    return 0


if __name__ == "__main__":  # pragma: no cover - operator entrypoint
    raise SystemExit(main())
