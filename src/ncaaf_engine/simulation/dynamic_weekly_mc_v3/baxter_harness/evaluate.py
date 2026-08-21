"""Deterministic candidate-regime evaluation for the Baxter RMSE harness.

What this module will and will not do:

* :func:`evaluate_regimes` scores candidate regimes on **validation** and ranks them there. Ranking is
  advisory and is labelled as such in the payload.
* It computes **holdout** only for a single named regime, in an explicit
  confirmation run. A holdout that can be swept is a second validation set with
  a more reassuring name, so it refuses ``include_holdout`` for a
  candidate set of more than one.
* It **never promotes**. There is no code path from a result to canonical
  configuration; promotion stays in :func:`..calibration.promote_regime_r2`,
  which requires a human approval token and a named authority.
* With no observation set mounted it returns ``READY_FOR_DATA`` and no metrics.
  A harness that returns numbers without data is worse than one that returns
  nothing, because the numbers get quoted.

Determinism is a property the module maintains deliberately: no wall clock, no
RNG, no set iteration into output. The run identity — run id, timestamp, seed,
versions — is supplied by the caller in a :class:`RunContext`, so two runs of the
same inputs produce byte-identical payloads.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from ..calibration import (
    CandidateRegime,
    EvaluationObjective,
    ExperimentRecord,
    PRIMARY_CALIBRATION_METRIC,
    PRIMARY_OBJECTIVE,
    INDEPENDENT_WITNESSES,
    rank_experiments,
    require_primary_objective,
)
from ..errors import GovernanceBlock, InputValidationError
from ..rulings import R2_CALIBRATION
from . import metrics as metrics_module
from .contract import (
    BLOCKED,
    ContractResolution,
    READY_FOR_DATA,
)
from .model import run_model
from .observations import (
    HOLDOUT,
    TRAINING,
    VALIDATION,
    ObservationSet,
    _row_key,
    load_observation_set,
    require_scorable,
)
from .regime import ResolvedRegime, resolve_regimes

EVALUATED = "EVALUATED"

#: Ranking basis. Holdout is never a ranking basis.
RANKING_BASIS = VALIDATION

EXPERIMENTAL_RESULT_STATUS = "EXPERIMENTAL_RESULT_NOT_PROMOTED"


@dataclass(frozen=True)
class RunContext:
    """Caller-supplied run identity. Nothing here is read from the clock."""

    run_id: str
    as_of: str
    model_version: str
    configuration_version: str
    seed: int

    def __post_init__(self) -> None:
        for name in ("run_id", "as_of", "model_version", "configuration_version"):
            if not str(getattr(self, name)).strip():
                raise InputValidationError(
                    f"RunContext.{name} must be supplied; the harness does not read the clock "
                    "or invent a version so that repeated runs stay byte-identical."
                )

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "as_of": self.as_of,
            "model_version": self.model_version,
            "configuration_version": self.configuration_version,
            "seed": self.seed,
        }


def _witness_report(resolution: ContractResolution) -> dict[str, Any]:
    """Witnesses are reported beside the primary criterion, never inside it."""
    declared = dict(resolution.witnesses)
    return {
        "witnesses": {name: declared.get(name, "NOT_DECLARED") for name in INDEPENDENT_WITNESSES},
        "reported_independently": True,
        "blended_into_primary_metric": False,
        "authority": R2_CALIBRATION.convergence_id,
    }


def _weeks_by_split(observation_set: ObservationSet) -> dict[str, set[tuple[int, int]]]:
    """Which ``(season, week)`` keys belong to each split.

    Movement is a property of the weeks a split covers, so a split's movement and
    stability diagnostics are computed over that split's own updates rather than
    over the whole run.
    """
    out: dict[str, set[tuple[int, int]]] = {}
    for observation in observation_set.observations:
        split = observation_set.split_of[_row_key(observation)]
        out.setdefault(split, set()).add(observation.time_key)
    return out


def _split_result(
    split: str,
    predictions: Sequence[Any],
    movements: Sequence[Any],
    regime: ResolvedRegime,
) -> dict[str, Any]:
    diagnostics = metrics_module.diagnostics_for(
        predictions,
        movements,
        blowout_threshold_points=regime.blowout_treatment.sensitivity_threshold,
    )
    return {
        "split": split,
        "scored_observations": len(predictions),
        "metrics": metrics_module.flat_metrics(predictions, diagnostics),
        "diagnostics": [d.as_dict() for d in diagnostics],
        "baseline_comparison": metrics_module.baseline_comparison(predictions),
    }


def evaluate_regimes(
    resolution: ContractResolution,
    regimes: Iterable[CandidateRegime],
    *,
    context: RunContext,
    objective: EvaluationObjective | None = PRIMARY_OBJECTIVE,
    include_holdout: bool = False,
) -> dict[str, Any]:
    """Evaluate candidate regimes against the contract's observation set.

    Returns a JSON-serialisable payload. Its ``status`` is ``READY_FOR_DATA``
    when nothing is mounted, ``BLOCKED`` when something is mounted but the
    contract cannot be honoured, and ``EVALUATED`` otherwise.
    """
    candidates = list(regimes)
    objective = require_primary_objective(objective)

    if resolution.status == READY_FOR_DATA:
        return {
            "status": READY_FOR_DATA,
            "harness": "C2_BAXTER_RMSE_HARNESS",
            "run": context.as_dict(),
            "contract": resolution.as_dict(),
            "objective": _objective_dict(objective),
            "candidate_regimes_supplied": len(candidates),
            "results": [],
            "ranking": None,
            "promotion": _promotion_block(),
            "witness_reporting": _witness_report(resolution),
            "reasons": list(resolution.reasons),
            "note": (
                "No historical observation set is mounted. No metric is reported, and none is "
                "implied. Supply the observation set through the data contract."
            ),
        }

    if resolution.status == BLOCKED or resolution.dataset is None:
        return {
            "status": BLOCKED,
            "harness": "C2_BAXTER_RMSE_HARNESS",
            "run": context.as_dict(),
            "contract": resolution.as_dict(),
            "objective": _objective_dict(objective),
            "candidate_regimes_supplied": len(candidates),
            "results": [],
            "ranking": None,
            "promotion": _promotion_block(),
            "witness_reporting": _witness_report(resolution),
            "reasons": list(resolution.reasons),
        }

    if not candidates:
        raise InputValidationError(
            "No candidate regimes supplied. The harness evaluates candidates authored "
            "elsewhere; it does not author them."
        )

    resolved = resolve_regimes(candidates)

    if include_holdout and len(resolved) != 1:
        raise GovernanceBlock(
            f"Holdout was requested for {len(resolved)} regimes. Holdout is a confirmation "
            "surface for one already-selected regime, not a sweep surface: scoring many "
            "candidates on it turns it into a second validation set."
        )

    observation_set = load_observation_set(resolution.dataset, resolution.contract)
    scored_splits = [VALIDATION] + ([HOLDOUT] if include_holdout else [])
    require_scorable(observation_set, scored_splits)

    if resolution.hfa_points is None:
        raise GovernanceBlock(
            "Home-field points are unresolved; the venue term of every prediction would be "
            "invented."
        )

    split_weeks = _weeks_by_split(observation_set)
    results: list[dict[str, Any]] = []
    records: list[ExperimentRecord] = []

    for regime in resolved:
        run = run_model(
            observation_set, regime, home_field_points=float(resolution.hfa_points)
        )
        per_split = {
            split: _split_result(
                split,
                run.for_split(split),
                [m for m in run.movements if (m.season, m.week) in split_weeks.get(split, set())],
                regime,
            )
            for split in ([TRAINING] + scored_splits)
        }
        record = ExperimentRecord(
            experiment_id=f"{context.run_id}::{regime.regime_id}",
            model_version=context.model_version,
            configuration_version=context.configuration_version,
            seed=context.seed,
            regime_id=regime.regime_id,
            candidate_values=regime.candidate_values(),
            dataset_id=observation_set.dataset_id,
            dataset_sha256=observation_set.sha256,
            objective_id=objective.objective_id,
            run_timestamp=context.as_of,
            metrics=per_split[RANKING_BASIS]["metrics"],
            v2_1_control_comparison=per_split[RANKING_BASIS]["baseline_comparison"],
        )
        records.append(record)
        results.append(
            {
                "experiment_id": record.experiment_id,
                "regime": regime.as_dict(),
                "record": record.as_dict(),
                "splits": {split: per_split[split] for split in sorted(per_split)},
                "run_shape": {
                    "seeded_teams": run.seeded_teams,
                    "weekly_updates": len(run.movements),
                    "directed_rows_per_game": run.directed_rows_per_game,
                    "home_field_points": run.home_field_points,
                },
                "evidence_admissible_for_promotion": not observation_set.synthetic,
            }
        )

    ranked = rank_experiments(records, objective)
    ranking = {
        "basis": RANKING_BASIS,
        "metric": PRIMARY_CALIBRATION_METRIC,
        "direction": objective.direction,
        "order": [r.experiment_id for r in ranked],
        "advisory_only": True,
        "note": (
            "Ranking is computed on the validation split and is advisory. Ordering first is "
            "not authority to become canonical."
        ),
    }
    if include_holdout:
        ranking["note"] += (
            " Holdout metrics in this payload are a confirmation of one already-selected "
            "regime and were not used to order anything."
        )

    return {
        "status": EVALUATED,
        "harness": "C2_BAXTER_RMSE_HARNESS",
        "run": context.as_dict(),
        "contract": resolution.as_dict(),
        "objective": _objective_dict(objective),
        "observation_set": observation_set.as_dict(),
        "candidate_regimes_supplied": len(resolved),
        "holdout_included": include_holdout,
        "results": results,
        "ranking": ranking,
        "promotion": _promotion_block(synthetic=observation_set.synthetic),
        "witness_reporting": _witness_report(resolution),
        "reasons": list(resolution.reasons),
    }


def _objective_dict(objective: EvaluationObjective) -> dict[str, Any]:
    return {
        "objective_id": objective.objective_id,
        "metric": objective.metric,
        "direction": objective.direction,
        "description": objective.description,
        "ruling": R2_CALIBRATION.convergence_id,
    }


def _promotion_block(*, synthetic: bool = False) -> dict[str, Any]:
    block = {
        "auto_promoted": False,
        "harness_can_promote": False,
        "canonical_values_written": False,
        "requires": [
            "explicit human approval token (APPROVE_V3_CALIBRATION_PROMOTION::<RULING_ID>)",
            "a named promotion authority",
            "holdout-split evidence when the authority is mathematical",
        ],
        "gate": "ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration.promote_regime_r2",
        "result_status": EXPERIMENTAL_RESULT_STATUS,
    }
    if synthetic:
        block["evidence_admissible"] = False
        block["evidence_note"] = (
            "This run scored a synthetic fixture. Fixture results validate the harness and are "
            "never admissible as calibration evidence."
        )
    return block


def assert_promotion_evidence_admissible(payload: dict[str, Any]) -> None:
    """Refuse a payload being carried toward promotion when it cannot support it."""
    if payload.get("status") != EVALUATED:
        raise GovernanceBlock(
            f"Evaluation payload has status {payload.get('status')!r} and carries no metrics to "
            "offer as promotion evidence."
        )
    if payload.get("observation_set", {}).get("synthetic"):
        raise GovernanceBlock(
            "Synthetic fixture results are harness validation only and are not admissible as "
            "calibration promotion evidence."
        )
    if not payload.get("holdout_included"):
        raise GovernanceBlock(
            "Promotion evidence must come from the holdout split; this payload reports "
            "validation only."
        )


def payload_digest(payload: dict[str, Any]) -> str:
    """Stable serialisation used to assert run-to-run determinism."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
