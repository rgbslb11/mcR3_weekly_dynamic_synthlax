"""Wave-1 synthetic continuity calibration: field admissions, and what stopped it.

This lane was asked to fit exactly two parameter families -- ``blowout_treatment``
and ``sample_size_regularization`` -- against a frozen synthetic 2024+2025 corpus,
under three narrowly scoped experimental field admissions. It fits neither, and
the two reasons are recorded here rather than worked around.

The module is deliberately shaped so that both refusals are *computed*.

Evidence resolution fails closed, it does not default
    :func:`resolve_synthetic_evidence` is handed the seven digests the wave is
    required to record. It refuses when any is absent. There is no path through
    it that substitutes the real 2021-2024 corpus, a sibling working tree, or an
    empty table, because each of those would let a wave that measured nothing
    report a winner.

The arithmetic dependency is derived from the update step, not asserted
    :func:`update_equation_dependencies` reads
    :func:`calibration_scoring._walk_forward` and reports which parameter
    families the eligible experiments actually multiply against. Writing the
    dependency out as prose would let it rot silently the first time the update
    step was rearranged; deriving it means the finding tracks the code.

Nothing here promotes a parameter, writes canonical configuration, widens an
allowlist, or retires a blocker. The field admissions are scoped to the
non-promoting synthetic experimental path and leave the governed allowlist in
:mod:`.calibration_contract` exactly as it stands.
"""

from __future__ import annotations

import hashlib
import inspect
import re
from pathlib import Path
from typing import Any, Mapping

from . import calibration as cal
from . import calibration_scoring as scoring
from . import calibration_search as search
from .errors import GovernanceBlock
from .textio import write_json_lf

__all__ = [
    "ADMITTED_FIELDS",
    "ELIGIBLE_FAMILIES",
    "FIELD_ADMISSION_ID",
    "NON_FIT_FAMILIES",
    "REQUIRED_EVIDENCE_DIGESTS",
    "UNRESOLVED_EVIDENCE",
    "WAVE_ID",
    "candidate_universe",
    "field_admissions_record",
    "field_admissions_sha",
    "non_fit_matrix",
    "resolve_synthetic_evidence",
    "update_equation_dependencies",
    "wave1_record",
    "write_field_admissions_record",
    "write_wave1_record",
]

FIELD_ADMISSION_ID = "V3-SYNTHETIC-CALIBRATION-FIELD-ADMISSIONS-R1"
WAVE_ID = "V3-SYNTHETIC-CALIBRATION-WAVE1-R1"

#: The two families the R2 eligibility reconciliation left open to fitting.
ELIGIBLE_FAMILIES = ("blowout_treatment", "sample_size_regularization")

#: Everything the reconciliation closed, with the exact state it closed it in.
#: These strings are the epistemic record and are not paraphrased downstream.
NON_FIT_FAMILIES: dict[str, dict[str, str]] = {
    "point_scale": {
        "eligibility": "CIRCULAR_NOT_IDENTIFIABLE",
        "disposition": "DO_NOT_FIT",
        "reason": (
            "The synthetic corpus was generated on a point axis; recovering that "
            "axis from it measures the generator rather than the sport."
        ),
    },
    "weekly_performance_residual_coefficient": {
        "eligibility": "CIRCULAR_NOT_IDENTIFIABLE",
        "disposition": "DO_NOT_FIT",
        "reason": (
            "Same circularity. The coefficient that produced the synthetic "
            "week-to-week movement cannot be re-estimated from that movement."
        ),
    },
    "weekly_movement_cap_points": {
        "eligibility": "CIRCULAR_NOT_IDENTIFIABLE",
        "disposition": "DO_NOT_FIT",
        "reason": (
            "Same circularity, compounded by the historical finding that the cap "
            "did not bind, so its level was not identified even on real data."
        ),
    },
    "recent_form_weights": {
        "eligibility": "RECENT_FORM_UNIDENTIFIED_FROM_SYNTHETIC_EVIDENCE",
        "disposition": "DO_NOT_FIT",
        "reason": (
            "The synthetic evidence does not carry a recoverable recent-form "
            "signal, so depth and decay are unidentified rather than merely noisy."
        ),
    },
    "game_sd_points": {
        "eligibility": "CIRCULAR_NOT_IDENTIFIABLE_UNDER_CURRENT_SYNTHETIC_EVIDENCE",
        "disposition": "DO_NOT_FIT_IN_THIS_WAVE",
        "reason": (
            "Dispersion read off synthetic residuals is the generator's dispersion. "
            "The family stays open; this wave is not the wave that closes it."
        ),
    },
    "FCS_adapter": {
        "eligibility": "MISSING",
        "disposition": "FCS_GAMES_MUST_FAIL_CLOSED",
        "reason": (
            "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER is absent, so an "
            "FCS row has no admissible translation onto the V3 point axis."
        ),
    },
}

#: The digests the wave must record before it may consume a single byte. Absence
#: of any one of them is a stop, not a warning: the wave's whole claim to being
#: reproducible is that these pin the input.
REQUIRED_EVIDENCE_DIGESTS = (
    "synthetic_evidence_commit_sha",
    "synthetic_evidence_tree_sha",
    "synthetic_evidence_manifest_sha",
    "field_classification_sha",
    "parameter_eligibility_sha",
    "split_manifest_sha",
    "forbidden_field_manifest_sha",
)

#: Source digests the evidence lane reported and this lane must re-verify.
EXPECTED_SOURCE_DIGEST_COUNT = 18

#: What resolving the frozen synthetic evidence actually found. This is a finding,
#: not a configuration knob: the evidence lane's branch was never pushed to the
#: remote, and the local ref it left behind points at a tree byte-identical to
#: ``main``, so there are no synthetic corpus bytes at any commit to consume. It
#: lives in the module rather than in a caller's script so the Wave-1 artifact is
#: emitted deterministically and can be compared against its committed copy.
UNRESOLVED_EVIDENCE: dict[str, Any] = {
    "requested_ref": "origin/claude/v3-synthetic-2024-2025-calibration-corpus-r1",
    "resolution_status": "UNRESOLVABLE_REMOTE_REF_ABSENT",
    "remote": "https://github.com/rgbslb11/mcR3_weekly_dynamic_synthlax.git",
    "remote_ref_present": False,
    "local_ref_present": True,
    "local_ref_commit_sha": "5479f2ae7687c36c0ed4117334171289693dd5c9",
    "local_ref_tree_sha": "32078871363ea2537347aec32e39b6b80ccec086",
    "local_ref_equals_main": True,
    "local_ref_diff_vs_main": "EMPTY",
    "sibling_worktree_read": False,
    "sibling_worktree_read_reason": (
        "The directive forbids reading the sibling working tree. Only committed "
        "bytes at a resolved commit are admissible evidence, and uncommitted work "
        "in another lane's tree is exactly what freezing by commit exists to refuse."
    ),
    "synthetic_rows_available": 0,
    "source_digests_reverified": 0,
    "source_digests_expected": EXPECTED_SOURCE_DIGEST_COUNT,
    "finding": (
        "The evidence lane never committed synthetic corpus bytes. Its branch is "
        "byte-identical to main and was never pushed to origin, so none of the "
        "seven required digests exists to record or re-verify."
    ),
    **{key: None for key in REQUIRED_EVIDENCE_DIGESTS},
}


# --- field admissions --------------------------------------------------------
#
# Three fields are admitted for synthetic continuity calibration only. Each
# admission is narrow in the same three ways: it names the single family it
# serves, it states the leakage it must not commit, and it confers no promotion.
# The governed allowlist in calibration_contract is untouched; a field admitted
# here is admitted to an experiment, not to the model.

ADMITTED_FIELDS: dict[str, dict[str, Any]] = {
    "games_played_to_date": {
        "admitted_by": "RULING_1",
        "admitted_for": ("sample_size_regularization",),
        "information_class": "PREGAME",
        "derivation": "CHRONOLOGY_DERIVED_MODEL_METADATA",
        "restrictions": (
            "Counted only from games completed strictly before the subject game's "
            "kickoff instant.",
            "The subject game never contributes to its own count.",
            "No game later in the chronology may contribute.",
            "Derived from the frozen chronology, never read from a supplied column "
            "that could have been computed with hindsight.",
        ),
        "confers_promotion": False,
    },
    "game_type": {
        "admitted_by": "RULING_2",
        "admitted_for": ("blowout_treatment",),
        "information_class": "PREGAME",
        "derivation": "FROZEN_SYNTHETIC_EVIDENCE_COLUMN",
        "restrictions": (
            "Value must be bound to the frozen synthetic evidence digest.",
            "No future result may reach a game's pregame expected margin through "
            "this field.",
            "Categories are taken as supplied; no undocumented category inference.",
        ),
        "confers_promotion": False,
    },
    "overtime_periods": {
        "admitted_by": "RULING_3",
        "admitted_for": ("blowout_treatment",),
        "information_class": "POSTGAME",
        "derivation": "FROZEN_SYNTHETIC_EVIDENCE_COLUMN",
        "restrictions": (
            "May affect only the update produced after the completed game.",
            "May never enter that same game's pregame expected margin.",
            "Value must be frozen and bound to the synthetic evidence digest.",
        ),
        "confers_promotion": False,
    },
}


def field_admissions_record() -> dict[str, Any]:
    """The three rulings as one deterministic, reviewable record."""
    return {
        "artifact": FIELD_ADMISSION_ID,
        "artifact_status": "EXPERIMENTAL_FIELD_ADMISSIONS_ACTIVE",
        "authority": "SUPERVISOR_FIELD_ADMISSION_AUTHORITY",
        "scope": (
            "Synthetic continuity calibration only. Each field is admitted to the "
            "named experiment and to nothing else. Canonical parameter governance "
            "and the governed allowlist in calibration_contract are unchanged."
        ),
        "admitted_fields": {
            name: {
                "admitted_by": spec["admitted_by"],
                "admitted_for": list(spec["admitted_for"]),
                "information_class": spec["information_class"],
                "derivation": spec["derivation"],
                "restrictions": list(spec["restrictions"]),
                "confers_promotion": spec["confers_promotion"],
            }
            for name, spec in sorted(ADMITTED_FIELDS.items())
        },
        "canonical_governance_modified": False,
        "governed_allowlist_widened": False,
        "parameters_promoted": 0,
        "postgame_field_rule": (
            "A postgame field may shape the update a completed game produces and "
            "may never shape that game's own prediction. The two are separated by "
            "the week boundary the walk-forward scorer already enforces, so the "
            "admission adds no new trust in the corpus."
        ),
        "supersedes": None,
        "terminal": "FIELD_ADMISSIONS_RECORDED",
    }


def field_admissions_sha() -> str:
    """SHA-256 over the canonical serialization of the admissions record."""
    return hashlib.sha256(
        search.canonical_json(field_admissions_record()).encode("utf-8")
    ).hexdigest()


def write_field_admissions_record(path: Path) -> Path:
    """Emit the admissions record with LF endings on every platform."""
    return write_json_lf(path, field_admissions_record(), trailing_newline=True)


# --- evidence resolution -----------------------------------------------------


def resolve_synthetic_evidence(
    digests: Mapping[str, str] | None,
    *,
    source_digests: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Bind the wave to committed synthetic evidence, or refuse.

    ``digests`` carries the seven values in :data:`REQUIRED_EVIDENCE_DIGESTS`,
    read from committed bytes at a resolved commit. ``source_digests`` carries
    the per-file digests the evidence lane reported, which this lane re-verifies
    rather than trusts.

    There is no permissive branch. A wave whose input cannot be pinned cannot
    produce a result anybody is entitled to cite, so the refusal happens here,
    before a table is built, rather than as a caveat attached to a number.
    """
    if not digests:
        raise GovernanceBlock(
            "No synthetic evidence resolved. The wave requires committed bytes at a "
            f"resolved commit and all {len(REQUIRED_EVIDENCE_DIGESTS)} digests "
            f"{list(REQUIRED_EVIDENCE_DIGESTS)}; none were supplied. Substituting the "
            "real 2021-2024 corpus is refused: it is EXTERNAL_WITNESS_ONLY and real "
            "rows must equal zero in the primary fitting table."
        )
    missing = [key for key in REQUIRED_EVIDENCE_DIGESTS if not digests.get(key)]
    if missing:
        raise GovernanceBlock(
            f"Synthetic evidence is not fully pinned; missing {missing}. Fail closed "
            "rather than scoring against a partially identified input."
        )
    if source_digests is None:
        raise GovernanceBlock(
            "The evidence lane's per-source digests were not supplied, so the "
            f"{EXPECTED_SOURCE_DIGEST_COUNT} reported source digests cannot be "
            "re-verified. An unverified manifest is byte drift that has not been "
            "looked for."
        )
    if len(source_digests) != EXPECTED_SOURCE_DIGEST_COUNT:
        raise GovernanceBlock(
            f"Expected {EXPECTED_SOURCE_DIGEST_COUNT} source digests from the "
            f"evidence lane; got {len(source_digests)}. Byte drift."
        )
    return {key: str(digests[key]) for key in REQUIRED_EVIDENCE_DIGESTS}


# --- the arithmetic dependency ----------------------------------------------
#
# The update step the two eligible families live in is one expression. Both
# families enter it as factors of a product whose other factors are families the
# reconciliation marked DO_NOT_FIT, so neither eligible family can be scored
# without first assigning a value to something this wave may not assign.

#: Candidate attribute -> governed family name, for reading the update step.
_CANDIDATE_ATTRIBUTE_FAMILIES = {
    "coefficient": "weekly_performance_residual_coefficient",
    "movement_cap_points": "weekly_movement_cap_points",
    "recent_form": "recent_form_weights",
    "blowout": "blowout_treatment",
    "regularization": "sample_size_regularization",
}

#: The update step, in the governed family names, exactly as the code computes it.
UPDATE_EQUATION = (
    "treated = blowout_treatment.apply(residual); "
    "shrunk = weekly_performance_residual_coefficient * treated * "
    "sample_size_regularization.shrinkage(games_played); "
    "capped = clamp(shrunk, -weekly_movement_cap_points, +weekly_movement_cap_points); "
    "promoted = prior_weight(week) * opening_strength_points + "
    "(1 - prior_weight(week)) * weighted_mean(update_history, recent_form_weights)"
)


def _families_read_by_walk_forward() -> set[str]:
    """Which parameter families the scorer's update step actually reads.

    Derived by inspection rather than declared, so that rearranging the update
    step changes this answer instead of leaving a stale claim behind.
    """
    source = inspect.getsource(scoring._walk_forward)
    found: set[str] = set()
    for attribute, family in _CANDIDATE_ATTRIBUTE_FAMILIES.items():
        if re.search(rf"\bcandidate\.{attribute}\b", source):
            found.add(family)
    return found


def update_equation_dependencies() -> dict[str, Any]:
    """Report the non-fit families the eligible experiments depend on.

    A dependency here is not a nuisance to be defaulted away. Two of the three
    are worse than additive: ``weekly_performance_residual_coefficient``
    multiplies the shrinkage term, so a shrinkage schedule and a coefficient are
    the same quantity to the data; and ``weekly_movement_cap_points`` clips the
    product, so whether two blowout thresholds are even distinguishable depends
    on a level this wave may not choose.
    """
    read = _families_read_by_walk_forward()
    non_fit_read = sorted(read & set(NON_FIT_FAMILIES))
    return {
        "update_equation": UPDATE_EQUATION,
        "equation_source": (
            "ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_scoring."
            "_walk_forward"
        ),
        "families_read_by_update_step": sorted(read),
        "eligible_families": list(ELIGIBLE_FAMILIES),
        "non_fit_families_required": non_fit_read,
        "blocks_blowout_treatment": sorted(
            f for f in non_fit_read
            if f in {
                "weekly_performance_residual_coefficient",
                "weekly_movement_cap_points",
                "recent_form_weights",
            }
        ),
        "blocks_sample_size_regularization": sorted(
            f for f in non_fit_read
            if f in {
                "weekly_performance_residual_coefficient",
                "weekly_movement_cap_points",
                "recent_form_weights",
            }
        ),
        "confounds": [
            {
                "eligible_family": "sample_size_regularization",
                "with": "weekly_performance_residual_coefficient",
                "term": (
                    "weekly_performance_residual_coefficient * "
                    "sample_size_regularization.shrinkage(games_played)"
                ),
                "statement": (
                    "The two appear only as a product. A shrinkage schedule is "
                    "observationally a coefficient that varies with games played, "
                    "so only the curvature in games_played separates them, and the "
                    "level does not separate at all."
                ),
            },
            {
                "eligible_family": "blowout_treatment",
                "with": "weekly_movement_cap_points",
                "term": (
                    "clamp(coefficient * blowout_treatment.apply(residual) * "
                    "shrinkage, -cap, +cap)"
                ),
                "statement": (
                    "Both are clips, applied in series. When "
                    "coefficient * threshold exceeds cap, the cap binds first and "
                    "the blowout threshold stops being visible in the update, so "
                    "the identifiability of the family this wave may fit is a "
                    "function of two levels it may not assign."
                ),
            },
        ],
        "substitution_permitted": False,
        "disposition": (
            "STOPPED_ARITHMETIC_DEPENDENCY_ON_NON_FIT_PARAMETERS"
            if non_fit_read
            else "NO_NON_FIT_DEPENDENCY"
        ),
    }


# --- candidate universes -----------------------------------------------------


def candidate_universe(family: str) -> dict[str, Any]:
    """The declared, hash-bound level set for one eligible family.

    The universe is real and enumerable even though nothing can be scored against
    it. Publishing it keeps the wave's scope checkable: a later run cannot quietly
    fit a narrower set and call it the declared one.
    """
    if family not in ELIGIBLE_FAMILIES:
        raise GovernanceBlock(
            f"{family} is not an eligible family in this wave; expected one of "
            f"{list(ELIGIBLE_FAMILIES)}."
        )
    space = search.coarse_space()
    axis = space.axis(family)
    levels = [level.as_dict() for level in axis.levels]
    return {
        "family": family,
        "space_id": space.space_id,
        "level_count": len(levels),
        "levels": levels,
        "boundary_expandable": bool(axis.boundary_expandable),
        "evidence_status": axis.evidence_status,
        "universe_sha": hashlib.sha256(
            search.canonical_json({"family": family, "levels": levels}).encode("utf-8")
        ).hexdigest(),
        "scored": False,
        "scored_reason": "NO_SYNTHETIC_EVIDENCE_RESOLVED",
    }


def non_fit_matrix() -> dict[str, dict[str, str]]:
    """Every closed family, in the exact state the reconciliation left it."""
    return {
        name: dict(spec) for name, spec in sorted(NON_FIT_FAMILIES.items())
    }


# --- the wave record ---------------------------------------------------------


def _blocked_experiment(family: str, dependencies: Mapping[str, Any]) -> dict[str, Any]:
    """One experiment's result slot, with nothing invented to fill it."""
    return {
        "family": family,
        "candidate_universe": candidate_universe(family),
        "selected_candidate": None,
        "runner_up": None,
        "training_rmse": None,
        "evaluation_rmse": None,
        "rmse_delta": None,
        "mae_diagnostic": None,
        "sensitivity": None,
        "boundary_status": "NOT_REACHED_NO_SCORING_PERFORMED",
        "identification_status": "UNIDENTIFIED_NO_EVIDENCE_RESOLVED",
        "failure_status": "BLOCKED",
        "blocking_reasons": [
            "SYNTHETIC_EVIDENCE_UNRESOLVED",
            "ARITHMETIC_DEPENDENCY_ON_NON_FIT_PARAMETERS",
        ],
        "non_fit_dependencies": list(dependencies["non_fit_families_required"]),
    }


def wave1_record(
    *,
    execution_commit_sha: str,
    execution_tree_sha: str,
    evidence_resolution: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The Wave-1 result package, recording a stop rather than a result.

    ``evidence_resolution`` describes what the resolver found when asked for the
    frozen synthetic corpus. Its digests are ``None`` here because none exist;
    the field is kept rather than dropped so the supervisor reads an unresolved
    input in the slot where it expects a pinned one.
    """
    resolution = dict(
        UNRESOLVED_EVIDENCE if evidence_resolution is None else evidence_resolution
    )
    dependencies = update_equation_dependencies()
    return {
        "artifact": WAVE_ID,
        "artifact_status": "SYNTHETIC_CALIBRATION_WAVE1_BLOCKED",
        "wave": "WAVE_1",
        "execution_commit_sha": execution_commit_sha,
        "execution_tree_sha": execution_tree_sha,
        "evidence_resolution": resolution,
        "synthetic_evidence_commit_sha": resolution.get(
            "synthetic_evidence_commit_sha"
        ),
        "synthetic_evidence_manifest_sha": resolution.get(
            "synthetic_evidence_manifest_sha"
        ),
        "field_admission_sha": field_admissions_sha(),
        "dataset_sha": None,
        "split_sha": None,
        "candidate_universe_sha": hashlib.sha256(
            search.canonical_json(
                [candidate_universe(f)["universe_sha"] for f in ELIGIBLE_FAMILIES]
            ).encode("utf-8")
        ).hexdigest(),
        "scoring_oracle_sha": None,
        "experiment_config_sha": search.coarse_space().config_sha,
        "primary_objective": {
            "metric": cal.PRIMARY_CALIBRATION_METRIC,
            "direction": "minimize",
            "ruling": "R2-CAL-OBJECTIVE",
            "verified_against_frozen_authority": True,
            "mae_role": "DIAGNOSTIC_AND_TIE_BREAK_ONLY_NEVER_PRIMARY",
        },
        "primary_domain": {
            "fitting_seasons": ["SYNTHETIC_2024", "SYNTHETIC_2025"],
            "projection_season": "SYNTHETIC_2026",
            "real_corpus_role": "EXTERNAL_WITNESS_ONLY",
            "real_rows_in_primary_fit": 0,
        },
        "arithmetic_dependency": dependencies,
        "blowout_treatment": _blocked_experiment("blowout_treatment", dependencies),
        "sample_size_regularization": _blocked_experiment(
            "sample_size_regularization", dependencies
        ),
        "non_fit_matrix": non_fit_matrix(),
        "promotions": {
            "parameters_promoted": 0,
            "canonical_config_written": False,
            "allowlist_widened": False,
            "blockers_retired": 0,
            "season_simulation_run": False,
            "monte_carlo_tiers_run": [],
        },
        "safe_for_supervisor_composition": True,
        "terminal": "SYNTHETIC_CALIBRATION_WAVE1_BLOCKED",
    }


def write_wave1_record(
    path: Path,
    *,
    execution_commit_sha: str,
    execution_tree_sha: str,
    evidence_resolution: Mapping[str, Any] | None = None,
) -> Path:
    """Emit the Wave-1 record with LF endings on every platform."""
    return write_json_lf(
        path,
        wave1_record(
            execution_commit_sha=execution_commit_sha,
            execution_tree_sha=execution_tree_sha,
            evidence_resolution=evidence_resolution,
        ),
        trailing_newline=True,
    )
