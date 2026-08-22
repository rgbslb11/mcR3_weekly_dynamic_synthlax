"""The calibration orchestrator, stated as one reviewable record.

:mod:`.calibration_search`, :mod:`.calibration_scoring` and
:mod:`.calibration_aggregate` are three halves of one thing. This composes them
into the artifact a reviewer reads and an operator runs from, and it exists as a
separate module for a boring reason: the record needs the ranking policy, the
input contract and the candidate universe together, and the three modules that
own them are layered so that none of them can import the other two.

Two properties are deliberate.

The record carries no timestamp, no commit and no timing
    It is emitted deterministically and compared byte-for-byte against the
    committed copy, the same way the calibration contract is. A ``recorded_at``
    field would make that comparison fail every time it was regenerated, and the
    first fix anyone reaches for is to stop comparing.

Readiness is computed, not asserted
    :func:`readiness` reports what is missing by asking the gates. If a governed
    corpus and authority ever do arrive, the terminal status changes because the
    refusals stop firing — not because someone edited a constant that said
    ``BLOCKED``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import calibration as cal
from . import calibration_aggregate as aggregate
from . import calibration_scoring as scoring
from . import calibration_search as search
from .errors import GovernanceBlock, InputValidationError
from .textio import write_json_lf

__all__ = [
    "OPERATOR_INTERFACE",
    "ORCHESTRATOR_ID",
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


#: The staged plan. Speed first: Stage 1 locates regions, Stage 2 resolves them,
#: and Stage 3 is a single scoring of a split nothing else has touched.
STAGE_PLAN: dict[str, Any] = {
    search.STAGE_COARSE: {
        "purpose": "Locate useful regions of the parameter space.",
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
}


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
        "--observations <governed-corpus> --expected-margin-authority <authority-id> "
        "--range-authority <ruling-id>"
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
    "worker_may_write_canonical_config": False,
    "worker_may_choose_its_own_grid": False,
}


def readiness(
    *,
    space: search.SearchSpace | None = None,
    authority: scoring.ExpectedMarginAuthority | None = None,
    observations: scoring.ObservationSet | None = None,
) -> dict[str, Any]:
    """What is missing before a real search may run, established by asking the gates.

    The three inputs are parameters rather than lookups because there is no
    registry to look them up in: a governed corpus and a governed authority are
    things a future lane will *hand* to this one. Passing them here runs the real
    refusals against the real objects, so readiness flips when the inputs are
    genuinely admissible and not when a constant is edited. Called with nothing,
    it reports today's state, which is that nothing is mounted.
    """
    space = space if space is not None else search.coarse_space()

    range_authority_reason: str | None = None
    try:
        search.require_range_authority(space)
        ranges_ready = True
    except GovernanceBlock as exc:
        ranges_ready = False
        range_authority_reason = str(exc)

    authority_reason: str | None = None
    try:
        scoring.require_governed_authority(authority)
        authority_ready = True
    except GovernanceBlock as exc:
        authority_ready = False
        authority_reason = str(exc)

    corpus_reason: str | None = None
    if observations is None:
        corpus_ready = cal.calibration_governance_as_dict()["dataset_mounted"] is True
        if not corpus_ready:
            corpus_reason = (
                f"{cal.BLOCKED_ON_CALIBRATION_DATA}: no historical observation set is "
                "mounted, and none was supplied."
            )
    else:
        try:
            observations.require_temporal_split_integrity()
            if authority is not None:
                observations.require_authority_agreement(authority)
            corpus_ready = True
        except (GovernanceBlock, InputValidationError) as exc:
            corpus_ready = False
            corpus_reason = str(exc)

    blocking: list[dict[str, Any]] = []
    if not corpus_ready:
        blocking.append(
            {
                "input": "GOVERNED_HISTORICAL_OBSERVATION_CORPUS",
                "required_for": "Any scoring at all.",
                "supplied_as": "An exact dataset SHA-256, registered through "
                "calibration_evidence.register_governed_dataset.",
                "reason": corpus_reason,
            }
        )
    if not authority_ready:
        blocking.append(
            {
                "input": "GOVERNED_EXPECTED_MARGIN_AUTHORITY",
                "required_for": "Converting point strengths into a predicted margin.",
                "supplied_as": "An ExpectedMarginAuthority with status GOVERNED, "
                "naming its point axis and rating-to-margin transform.",
                "reason": authority_reason,
            }
        )
    if not ranges_ready:
        blocking.append(
            {
                "input": "SEARCH_RANGE_AUTHORITY",
                "required_for": "Turning the pending coarse axes into fixed ranges.",
                "supplied_as": "A named ruling that fixes each axis, flipping its "
                f"evidence status to {search.EVIDENCE_GOVERNED}.",
                "reason": range_authority_reason,
            }
        )
    return {
        "corpus_mounted": corpus_ready,
        "expected_margin_authority_mounted": authority_ready,
        "search_ranges_fixed": ranges_ready,
        "machinery_complete": True,
        "blocking_inputs": blocking,
        "real_calibration_executable": not blocking,
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
    return {
        "artifact": ORCHESTRATOR_ID,
        "artifact_status": "SEARCH_MACHINERY_COMPLETE_INPUTS_NOT_MOUNTED",
        "terminal": terminal_status(),
        "scope": (
            "Deterministic candidate universe, temporal walk-forward scorer, shard "
            "protocol and aggregator for the six V3 calibration families. No "
            "parameter is selected, promoted, or written to canonical configuration."
        ),
        "parameter_families": {
            "all": list(search.PARAMETER_FAMILIES),
            "searched_as_mean_model": list(search.MEAN_MODEL_FAMILIES),
            "estimated_from_residuals": search.DISPERSION_FAMILY,
            "separation_reason": (
                "game_sd_points is a property of the residuals a mean model leaves "
                "behind. Enumerating it as an axis would let a candidate choose the "
                "dispersion its own errors are scored against."
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
        "objective": {
            "primary_metric": cal.PRIMARY_CALIBRATION_METRIC,
            "direction": cal.PRIMARY_CALIBRATION_DIRECTION,
            "ruling": "R2-CAL-OBJECTIVE",
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
            "estimated_on": "validation or holdout residuals; the training split is refused",
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
        "readiness": readiness(),
        "historical_research_context": dict(search.HISTORICAL_RESEARCH_CONTEXT),
        "promotions": {
            "parameters_promoted": 0,
            "canonical_writer_created": False,
            "allowlist_widened": False,
            "blockers_retired": 0,
            "season_monte_carlo_executed": False,
            "real_calibration_executed": False,
        },
    }


def write_orchestrator_record(path: Path) -> Path:
    """Emit the record with LF endings on every platform, like the contract."""
    return write_json_lf(path, orchestrator_record(), trailing_newline=True)
