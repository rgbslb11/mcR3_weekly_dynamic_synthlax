"""The calibration orchestrator, stated as one reviewable record.

:mod:`.calibration_stage0`, :mod:`.calibration_search`, :mod:`.calibration_scoring`
and :mod:`.calibration_aggregate` are four parts of one thing. This composes them
into the artifact a reviewer reads and an operator runs from, and it exists as a
separate module for a boring reason: the record needs the ranking policy, the
input contract, the Stage 0 plan and the candidate universe together, and the
modules that own them are layered so that none of them can import the others.

Three properties are deliberate.

The record carries no timestamp, no commit and no timing
    It is emitted deterministically and compared byte-for-byte against the
    committed copy, the same way the calibration contract is. A ``recorded_at``
    field would make that comparison fail every time it was regenerated, and the
    first fix anyone reaches for is to stop comparing.

Readiness is computed, not asserted
    :func:`readiness` reports what is missing by asking the gates against the
    objects it is handed. Nothing flips because a constant was edited.

Governance gates and research gates are different gates
    Two preconditions this lane originally carried were too strong for an
    experimental, non-promoting search, and both are corrected here. Exploring a
    predeclared, hash-bound parameter range needs no ruling; identifying an
    empirically calibratable point scale needs no ruling either. What still needs
    one is promoting a value out of either, and that gate is untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import calibration as cal
from . import calibration_aggregate as aggregate
from . import calibration_scoring as scoring
from . import calibration_search as search
from . import calibration_stage0 as stage0
from .errors import GovernanceBlock, InputValidationError
from .textio import write_json_lf

__all__ = [
    "OPERATOR_INTERFACE",
    "ORCHESTRATOR_ID",
    "REAL_EXECUTION_DEPENDENCIES",
    "STAGE_PLAN",
    "TERMINAL_BLOCKED",
    "TERMINAL_READY_FOR_AUDIT",
    "TERMINAL_READY_FOR_INPUTS",
    "orchestrator_record",
    "readiness",
    "terminal_status",
    "write_orchestrator_record",
]

ORCHESTRATOR_ID = "V3-CALIBRATION-ORCHESTRATOR-R1"

TERMINAL_READY_FOR_AUDIT = "CALIBRATION_ORCHESTRATOR_READY_FOR_AUDIT"
TERMINAL_READY_FOR_INPUTS = "CALIBRATION_ORCHESTRATOR_READY_FOR_INPUTS"
TERMINAL_BLOCKED = "CALIBRATION_ORCHESTRATOR_BLOCKED"


#: The staged plan. Stage 0 runs first, because a scale identified after the
#: rerating parameters have been chosen is confounded with them: a large scale and
#: a small coefficient buy much the same thing, and no later stage separates them.
STAGE_PLAN: dict[str, Any] = {
    search.STAGE_POINT_SCALE: {
        "purpose": "Identify the historical V3 point scale from Weeks 1-2.",
        "window": list(stage0.stage0_weeks),
        "universe": "One broad, predeclared, hash-bound scale axis.",
        "scored_split": "validation",
        "why_first": (
            "Weeks 1-2 promote nothing, so every prediction in that window comes from "
            "opening strength alone and the scale is the only unknown. Running it "
            "after Stage 1 would confound the scale with the rerating coefficient."
        ),
        "rerating_parameters_used": 0,
        "definition": "calibration_stage0.identify_point_scale()",
    },
    search.STAGE_COARSE: {
        "purpose": "Locate useful regions of the later-season parameter space.",
        "universe": "Cross product of the five mean-model families.",
        "scored_split": "validation",
        "precision_policy": (
            "Deliberately coarse. Resolving a third decimal place here costs the "
            "same compute as covering twice the space, and Stage 2 resolves it "
            "anyway over a region Stage 1 has already justified."
        ),
        "definition": "calibration_search.coarse_space()",
    },
    search.STAGE_REFINEMENT: {
        "purpose": "Resolve the leading regions, and widen any that hit a boundary.",
        "universe": (
            "A pure function of the coarse space and the ordered Stage-1 leaders, so "
            "two operators build byte-identical Stage-2 universes."
        ),
        "scored_split": "validation",
        "boundary_policy": (
            "A family whose leader sat on an edge of an expandable ladder is extended "
            "one full step past it. The search grows rather than reporting the edge."
        ),
        "definition": "calibration_search.refine_space(base, winners)",
    },
    search.STAGE_HOLDOUT: {
        "purpose": "Score a shortlist once against a split nothing has touched.",
        "universe": (
            f"An explicit shortlist, capped at {search.MAX_HOLDOUT_SHORTLIST} "
            "candidates."
        ),
        "scored_split": "holdout",
        "dispersion_policy": (
            "game_sd_points is carried in from validation rather than re-estimated "
            "here, so the holdout does not inform its own diagnostics."
        ),
        "custody": (
            "calibration_search.HoldoutLedger records the single consumption and "
            "refuses a second. Iterative tuning against the holdout is not "
            "discouraged; it is unavailable."
        ),
        "definition": "calibration_search.holdout_space(shortlist, parent=...)",
    },
    "final_residual": {
        "purpose": "Estimate game_sd_points from out-of-sample residuals.",
        "method": scoring.GAME_SD_METHOD_RESIDUAL,
        "refused_method": scoring.GAME_SD_METHOD_ACTUAL_MARGIN,
        "runs_after": "mean-model selection, so dispersion cannot influence it",
        "definition": "calibration_scoring.estimate_game_sd_points(...)",
    },
}


#: The three inputs that actually block a real research run, after correction.
#: The expected-margin *structure* is not among them: it is supplied by the
#: audited model layer rather than owed by any of these lanes, and the gate that
#: enforces it is reported separately rather than dropped.
REAL_EXECUTION_DEPENDENCIES = (
    "AUDITED_HISTORICAL_OBSERVATION_CORPUS",
    "HISTORICAL_OPENING_STANDARDIZED_STATE",
    "DEFENSIBLE_VENUE_HFA_CLASSIFICATION",
)


#: The operator interface. Four workers evaluate disjoint pieces of one universe
#: by running the same command with a different ``--shard-index``.
OPERATOR_INTERFACE: dict[str, Any] = {
    "module_prefix": "ncaaf_engine.simulation.dynamic_weekly_mc_v3",
    "plan_one_shard": (
        "python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_search "
        "--stage coarse --shard-count 4 --shard-index 0 --plan"
    ),
    "score_one_shard": (
        "python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_search "
        "--stage coarse --shard-count 4 --shard-index 0 "
        "--experiment-id <experiment-id> "
        "--observations <audited-corpus> --expected-margin-authority <structure-id>"
    ),
    "aggregate": (
        "python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration_aggregate "
        "--input <result-directory>"
    ),
    "benchmark": "python scripts/benchmark_calibration_search.py",
    "fan_out": (
        "Run score_one_shard once per shard index with the same --shard-count and the "
        "same --expect-config-sha. Membership is candidate_id % shard_count, so the "
        "workers need no coordination and cannot overlap."
    ),
    "range_authority_flag_required": False,
    "worker_may_write_canonical_config": False,
    "worker_may_choose_its_own_grid": False,
}


def readiness(
    *,
    space: search.SearchSpace | None = None,
    predeclaration: search.ExperimentPredeclaration | None = None,
    structure: scoring.ExpectedMarginAuthority | None = None,
    observations: scoring.ObservationSet | None = None,
    opening_state: stage0.SealedInput | None = None,
    venue_classification: stage0.SealedInput | None = None,
) -> dict[str, Any]:
    """What is missing before a real research run, established by asking the gates.

    Every input is a parameter rather than a lookup because there is no registry to
    look them up in: an audited corpus, an opening standardized state and a venue
    classification are things other lanes will *hand* to this one. Passing them
    here runs the real refusals against the real objects, so readiness flips when
    the inputs are genuinely admissible and not when a constant is edited.
    """
    grid = space if space is not None else search.coarse_space()
    declaration = (
        predeclaration
        if predeclaration is not None
        else search.predeclare(grid, experiment_id=f"{ORCHESTRATOR_ID}-COARSE")
    )

    ranges_reason: str | None = None
    try:
        range_gate = search.require_executable_ranges(grid, predeclaration=declaration)
        ranges_ready = True
    except GovernanceBlock as exc:
        range_gate = {"range_status": search.range_status(grid)}
        ranges_ready = False
        ranges_reason = str(exc)

    structure_reason: str | None = None
    try:
        scoring.require_governed_structure(structure)
        structure_ready = True
    except GovernanceBlock as exc:
        structure_ready = False
        structure_reason = str(exc)

    corpus_reason: str | None = None
    if observations is None:
        corpus_ready = cal.calibration_governance_as_dict()["dataset_mounted"] is True
        if not corpus_ready:
            corpus_reason = (
                f"{cal.BLOCKED_ON_CALIBRATION_DATA}: no audited historical observation "
                "set is mounted, and none was supplied."
            )
    else:
        try:
            observations.require_temporal_split_integrity()
            if structure is not None:
                observations.require_authority_agreement(structure)
            corpus_ready = True
        except (GovernanceBlock, InputValidationError) as exc:
            corpus_ready = False
            corpus_reason = str(exc)

    def _sealed(
        supplied: stage0.SealedInput | None, producer: str
    ) -> tuple[bool, str | None]:
        try:
            stage0.require_sealed(supplied, producer=producer)
            return True, None
        except GovernanceBlock as exc:
            return False, str(exc)

    opening_ready, opening_reason = _sealed(opening_state, stage0.PRODUCER_OPENING_STATE)
    venue_ready, venue_reason = _sealed(
        venue_classification, stage0.PRODUCER_VENUE_CLASSIFICATION
    )

    supplied = {
        "AUDITED_HISTORICAL_OBSERVATION_CORPUS": (
            corpus_ready,
            corpus_reason,
            "this lane",
        ),
        "HISTORICAL_OPENING_STANDARDIZED_STATE": (
            opening_ready,
            opening_reason,
            stage0.PRODUCER_OPENING_STATE,
        ),
        "DEFENSIBLE_VENUE_HFA_CLASSIFICATION": (
            venue_ready,
            venue_reason,
            stage0.PRODUCER_VENUE_CLASSIFICATION,
        ),
    }
    blocking = [
        {
            "input": name,
            "producer": supplied[name][2],
            "supplied_as": (
                "A sealed, digest-bound payload; never a path into another lane's "
                "working tree."
            ),
            "reason": supplied[name][1],
        }
        for name in REAL_EXECUTION_DEPENDENCIES
        if not supplied[name][0]
    ]

    return {
        "machinery_complete": True,
        "search_ranges_executable": ranges_ready,
        "search_range_status": range_gate.get("range_status"),
        "search_range_ruling_required": False,
        "search_range_reason": ranges_reason,
        "governed_model_structure": {
            "mounted": structure_ready,
            "supplied_by": "AUDITED_MODEL_LAYER",
            "counts_as_lane_dependency": False,
            "reason": structure_reason,
            "note": (
                "The arithmetic, orientation, point domain and venue semantics are "
                "governed structure and are refused if absent. They are not owed by "
                "the corpus or enrichment lanes, so they are reported here rather "
                "than counted among this lane's blocking inputs."
            ),
        },
        "historical_point_scale": {
            "status": scoring.SCALE_EXPERIMENT_BOUND,
            "ruling_required": False,
            "identified_by": stage0.STAGE0_ID,
            "note": (
                "Empirically calibratable from Weeks 1-2, not a prerequisite governed "
                "value. Canonical promotion of a scale remains separately governed."
            ),
        },
        "corpus_mounted": corpus_ready,
        "opening_standardized_state_mounted": opening_ready,
        "venue_classification_mounted": venue_ready,
        "blocking_inputs": blocking,
        "real_calibration_executable": (
            not blocking and ranges_ready and structure_ready
        ),
    }


def terminal_status() -> str:
    """The lane's disposition, derived from :func:`readiness`."""
    state = readiness()
    if not state["machinery_complete"]:
        return TERMINAL_BLOCKED
    if state["real_calibration_executable"]:
        return TERMINAL_READY_FOR_AUDIT
    return TERMINAL_READY_FOR_INPUTS


def orchestrator_record() -> dict[str, Any]:
    """The whole lane as one deterministic, machine-readable payload."""
    space = search.coarse_space()
    universe = space.enumerate()
    declaration = search.predeclare(space, experiment_id=f"{ORCHESTRATOR_ID}-COARSE")
    return {
        "artifact": ORCHESTRATOR_ID,
        "artifact_status": "SEARCH_MACHINERY_COMPLETE_INPUTS_NOT_MOUNTED",
        "terminal": terminal_status(),
        "scope": (
            "Deterministic point-scale identification, candidate universe, temporal "
            "walk-forward scorer, shard protocol and aggregator for the V3 calibration "
            "families. No parameter is selected, promoted, or written to canonical "
            "configuration."
        ),
        "parameter_families": {
            "all": list(search.PARAMETER_FAMILIES),
            "searched_as_mean_model": list(search.MEAN_MODEL_FAMILIES),
            "estimated_from_residuals": search.DISPERSION_FAMILY,
            "identified_in_stage_0": "historical_points_per_standardized_unit",
            "separation_reason": (
                "game_sd_points is a property of the residuals a mean model leaves "
                "behind. Enumerating it as an axis would let a candidate choose the "
                "dispersion its own errors are scored against."
            ),
        },
        "governed_model_structure_fields": list(scoring.GOVERNED_STRUCTURE_FIELDS),
        "experimental_calibration_values": list(scoring.EXPERIMENTAL_CALIBRATION_VALUES),
        "search_ranges": {
            "status": search.range_status(space),
            "ruling_required": False,
            "predeclaration": declaration.as_dict(),
            "predeclaration_sha": declaration.predeclaration_sha,
            "breadth": search.require_predeclared_breadth(space),
            "promotion_grade_gate": "calibration_search.require_range_authority",
            "research_gate": "calibration_search.require_executable_ranges",
            "correction": (
                "Exploring an experimental range and promoting a value out of it are "
                "different acts. Only the second needs a named authority."
            ),
        },
        "coarse_universe": {
            "space_id": space.space_id,
            "config_sha": space.config_sha,
            "candidate_count": len(universe),
            "range_authority": space.range_authority,
            "axes": [
                {
                    "family": axis.family,
                    "level_count": len(axis.levels),
                    "evidence_status": axis.evidence_status,
                    "boundary_expandable": axis.boundary_expandable,
                }
                for axis in space.axes
            ],
        },
        "candidate_identity": {
            "scheme": "SHA256_OF_CANONICAL_PARAMETER_VECTOR",
            "id_bits": search.CANDIDATE_ID_BITS,
            "shard_rule": "candidate_id % shard_count == shard_index",
            "stable_under_axis_widening": True,
        },
        "shard_partition_proofs": {
            str(count): search.prove_shard_partition(universe, count)
            for count in search.SUPPORTED_SHARD_COUNTS
        },
        "stage_plan": dict(STAGE_PLAN),
        "stage0": stage0.stage0_plan(),
        "objective": {
            "primary_metric": cal.PRIMARY_CALIBRATION_METRIC,
            "direction": cal.PRIMARY_CALIBRATION_DIRECTION,
            "ruling": "R2-CAL-OBJECTIVE",
            "stage0_primary_metric": stage0.STAGE0_PRIMARY_OBJECTIVE,
            "secondary_metrics": [
                "baxter_mae",
                "winner_accuracy",
                "brier_score",
                "log_loss",
                "probability_calibration_bins",
                "week_to_week_movement_distribution",
                "cap_binding_statistics",
                "recent_form_effective_contributions",
                "regularization_early_and_late_season_impact",
            ],
            "winner_accuracy_may_override_primary": False,
            "witnesses": list(cal.INDEPENDENT_WITNESSES),
            "witness_composite_authorised": False,
            "witness_reporting": (
                "Colley and SRS are computed from outcomes alone and are "
                "candidate-independent. Each candidate reports a Spearman rank "
                "correlation against them as a coherence witness. Neither is "
                "converted onto the V3 point axis and neither enters the ranking."
            ),
        },
        "game_sd_points": {
            "admissible_method": scoring.GAME_SD_METHOD_RESIDUAL,
            "refused_method": scoring.GAME_SD_METHOD_ACTUAL_MARGIN,
            "estimated_on": (
                "validation or holdout residuals; the training split is refused"
            ),
            "influences_mean_model_selection": False,
            "reason": (
                "Selection is on RMSE, which needs no dispersion parameter, so the "
                "estimate cannot change which candidate wins. SD of actual margin "
                "measures the sport's variability rather than the model's error."
            ),
        },
        "identification_reporting": {
            "movement_cap": [
                "cap_hit_count",
                "cap_hit_rate",
                "max_uncapped_update",
                "max_capped_update",
                "cap_identified",
            ],
            "boundary_optimum": search.BOUNDARY_OPTIMUM,
            "ordered_families_tested_for_boundary": list(search.ORDERED_FAMILIES),
            "point_scale_boundary_expansion": (
                "calibration_stage0.expand_point_scale_space"
            ),
            "unidentified_tie_marker": aggregate.UNIDENTIFIED_EQUIVALENCE_CLASS,
            "policy": (
                "A cap that never binds is not identified and is never reported as a "
                "finding. Where candidates tie on the primary metric and differ only "
                "in a family the corpus cannot see, the aggregate reports an "
                "equivalence class rather than a discovery."
            ),
        },
        "ranking": {
            "policy": dict(aggregate.RANKING_POLICY),
            "policy_sha": aggregate.ranking_policy_sha(),
            "homogeneity_keys": list(aggregate.HOMOGENEITY_KEYS),
            "tie_tolerance": aggregate.PRIMARY_METRIC_TIE_TOLERANCE,
        },
        "expected_margin_input_contract": dict(scoring.EXPECTED_MARGIN_INPUT_CONTRACT),
        "fcs_policy": {
            "policy": scoring.FCS_FAIL_CLOSED,
            "blocker": "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
            "excluded_from": ["point_scale", "coarse", "refinement", "holdout"],
        },
        "temporal_controls": {
            "split_assignment": "TEMPORAL_ONLY",
            "random_split_permitted": False,
            "first_promoted_rerating_after_week": (
                scoring.FIRST_PROMOTED_RERATING_AFTER_WEEK
            ),
            "weeks_one_and_two": "OPENING_STRENGTH_EXACT_NOTHING_PROMOTED",
            "promotion_granularity": "WEEK_BOUNDARY_NEVER_PER_GAME",
            "leakage_proof": "calibration_scoring.require_no_future_leakage",
            "season_state": "RE_INITIALISED_PER_SEASON",
        },
        "operator_interface": dict(OPERATOR_INTERFACE),
        "real_execution_dependencies": list(REAL_EXECUTION_DEPENDENCIES),
        "readiness": readiness(),
        "historical_research_context": dict(search.HISTORICAL_RESEARCH_CONTEXT),
        "promotions": {
            "parameters_promoted": 0,
            "canonical_writer_created": False,
            "allowlist_widened": False,
            "blockers_retired": 0,
            "season_monte_carlo_executed": False,
            "real_calibration_executed": False,
            "point_scale_selected": False,
        },
    }


def write_orchestrator_record(path: Path) -> Path:
    """Emit the record with LF endings on every platform, like the contract."""
    return write_json_lf(path, orchestrator_record(), trailing_newline=True)
