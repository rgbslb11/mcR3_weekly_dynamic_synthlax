"""Ingestion contract for the V3 calibration observation set.

The seven remaining calibration blockers cannot be closed by choosing numbers.
They can only be closed by scoring candidate values against historical
observations that the repository does not currently hold. This module states
*exactly* what such an observation set must contain before it can be mounted, so
that the gap is a specification rather than an absence.

Three separations are load-bearing and are the reason this module exists at all:

``observation`` vs ``simulation output``
    ``V2_1_STATIC_CONTROL_...xlsx`` records 10,000 synthetic seasons. Those are
    the engine's own beliefs replayed, not events that happened. Scoring a
    coefficient against them measures self-consistency and reports it as
    accuracy. Every dataset registered here must be an observed result.

``observation`` vs ``schedule``
    ``2026_FBS_Schedule_LOCKED_v5.xlsx`` holds 743 fixtures and no scores. A
    fixture is the question, not the answer.

``required field`` vs ``admitted field``
    :data:`REQUIRED_CONTRACT_FIELDS` is what the six coefficients mathematically
    need. ``calibration.CALIBRATION_OBSERVATION_COLUMNS`` is what governance has
    admitted. Where the first exceeds the second the difference is reported as
    :data:`FIELDS_REQUIRING_ADMISSION_RULING` and is *not* silently added to the
    allowlist, because "the calibration needed it" is precisely the argument by
    which an unreviewed signal enters a governed model.

Nothing here promotes a value, and nothing here mounts a dataset.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import calibration as cal
from .errors import GovernanceBlock
from .textio import write_json_lf

CONTRACT_ID = "V3-CALIBRATION-DATA-CONTRACT-001"
CONTRACT_STATUS = "SPECIFICATION_ONLY_NO_DATASET_MOUNTED"


@dataclass(frozen=True)
class ContractField:
    """One field of the calibration observation contract."""

    name: str
    dtype: str
    required: bool
    definition: str
    #: Which of the six blocked coefficients cannot be estimated without it.
    needed_by: tuple[str, ...]
    #: What makes a value of this field admissible evidence rather than a guess.
    provenance_requirement: str

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["needed_by"] = list(self.needed_by)
        payload["admitted_by_governed_allowlist"] = self.name in {
            c.lower() for c in cal.CALIBRATION_OBSERVATION_COLUMNS
        }
        return payload


_OBSERVED = (
    "Recorded from a named result source with a retrieval timestamp. A value "
    "reconstructed by the engine, or inferred from a rating, is not an observation."
)
_IDENTITY = (
    "Must resolve through the canonical team identity authority "
    "(2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md). Free-text names are refused."
)
_PREGAME = (
    "Must be the rating as it stood BEFORE kickoff, carrying its own as-of stamp. "
    "A post-hoc rating recomputed from the full season leaks the outcome into its "
    "own predictor and makes every out-of-sample number optimistic."
)

#: The fields the six coefficients mathematically require, with the reason each
#: is required. Ordered identity -> context -> prediction -> outcome -> provenance.
REQUIRED_CONTRACT_FIELDS: tuple[ContractField, ...] = (
    ContractField(
        "game_id", "string", True,
        "Stable unique key for the observation. Deduplication and split assignment key.",
        ("all",),
        "Must be unique within the dataset and stable across re-ingestion.",
    ),
    ContractField(
        "season", "integer", True,
        "Season the game belongs to. Bounds the training/validation/holdout partition.",
        ("all",),
        _OBSERVED,
    ),
    ContractField(
        "week", "integer", True,
        "Ordinal week within the season. Establishes the sequence in which ratings update.",
        ("recent_form_weights", "weekly_movement_cap_points",
         "weekly_performance_residual_coefficient", "sample_size_regularization"),
        "Must be the week in which the game was PLAYED, not the week it was ingested.",
    ),
    ContractField(
        "event_time", "iso8601", True,
        "Kickoff instant. The only field that can order two games inside one week, "
        "and therefore the only field that can prove a holdout game post-dates its "
        "training data.",
        ("all",),
        _OBSERVED,
    ),
    ContractField(
        "team", "canonical_team_id", True,
        "Subject team of the observation row.",
        ("all",),
        _IDENTITY,
    ),
    ContractField(
        "opponent", "canonical_team_id", True,
        "Opposing team.",
        ("all",),
        _IDENTITY,
    ),
    ContractField(
        "venue", "enum[HOME|AWAY|NEUTRAL]", True,
        "Venue treatment from the subject team's perspective. Without it the "
        "home-field term contaminates the residual it is meant to be separated from.",
        ("weekly_performance_residual_coefficient", "game_sd_points"),
        "Must come from the governed schedule/result source, not inferred from team order.",
    ),
    ContractField(
        "pregame_team_rating", "float", True,
        "Subject team's strength immediately before kickoff, on a declared scale.",
        ("weekly_performance_residual_coefficient", "weekly_movement_cap_points",
         "sample_size_regularization"),
        _PREGAME,
    ),
    ContractField(
        "pregame_opponent_rating", "float", True,
        "Opponent's strength immediately before kickoff, on the same declared scale.",
        ("weekly_performance_residual_coefficient", "game_sd_points"),
        _PREGAME,
    ),
    ContractField(
        "expected_margin", "float_points", True,
        "Pregame predicted margin for the subject team. The predictor half of every "
        "residual.",
        ("weekly_performance_residual_coefficient", "game_sd_points", "blowout_treatment"),
        "Must be the margin that was predicted BEFORE the game, and the rating-to-margin "
        "transform used to produce it must be named.",
    ),
    ContractField(
        "actual_margin", "float_points", True,
        "Final scoring margin for the subject team. The outcome half of every residual "
        "and the target of the primary objective.",
        ("all",),
        _OBSERVED,
    ),
    ContractField(
        "game_result", "enum[W|L|T]", True,
        "Result from the subject team's perspective. Required for the Colley witness "
        "and for Brier/log-loss diagnostics, which are result-based, not margin-based.",
        ("blowout_treatment",),
        _OBSERVED,
    ),
    ContractField(
        "prior_rating_state", "json_object", True,
        "The rating state the week opened with, including the games-played count the "
        "subject team carried into the game. Without the count there is no low-n regime "
        "to fit, and sample_size_regularization has nothing to regularize against.",
        ("sample_size_regularization", "weekly_movement_cap_points", "recent_form_weights"),
        "Must be serialized as it stood at week open, from the same run that produced "
        "pregame_team_rating.",
    ),
    ContractField(
        "subsequent_outcomes", "json_object", True,
        "The forward results used to score a rating out-of-sample. The primary objective "
        "is out-of-sample error, so each observation must reference the future games it "
        "is scored against, and those games must not also be in its training split.",
        ("all",),
        "Must reference game_ids present in the same dataset, so leakage is checkable "
        "rather than asserted.",
    ),
    ContractField(
        "split", "enum[training|validation|holdout]", True,
        "Partition assignment. Must be present in the dataset rather than assigned at "
        "experiment time, so the partition is auditable and identical across runs.",
        ("all",),
        "Must be temporally ordered: every holdout observation post-dates every training "
        "observation. A random split of sequential rating data is refused.",
    ),
    ContractField(
        "source_provenance", "string", True,
        "Named origin of the result: source system, retrieval method, and version.",
        ("all",),
        "Must name a source that a reviewer can independently re-query.",
    ),
    ContractField(
        "observed_at", "iso8601", True,
        "When the result became observable.",
        ("all",),
        _OBSERVED,
    ),
    ContractField(
        "recorded_at", "iso8601", True,
        "When the row was ingested. Distinct from observed_at; collapsing the two hides "
        "backfill.",
        ("all",),
        "Ingest time. Never back-dated to match observed_at.",
    ),
    ContractField(
        "model_version", "string", True,
        "Version of the model that produced pregame_team_rating and expected_margin.",
        ("all",),
        "Must match a released model version, so a residual can be attributed.",
    ),
    ContractField(
        "configuration_version", "string", True,
        "Configuration version behind the same two fields.",
        ("all",),
        "Must match a released configuration version.",
    ),
)

#: Fields the coefficients require that the governed allowlist does not yet admit.
#: Each is a ruling request, not a proposal to widen the allowlist here.
FIELDS_REQUIRING_ADMISSION_RULING: tuple[ContractField, ...] = (
    ContractField(
        "games_played_to_date", "integer", True,
        "Subject team's completed-game count entering the observation.",
        ("sample_size_regularization",),
        "Currently only reachable inside the opaque prior_rating_state blob. "
        "sample_size_regularization is a function OF this count; leaving it unaddressed "
        "means the shrinkage schedule is fitted against a field no reviewer can see.",
    ),
    ContractField(
        "game_type", "enum[REG|CCG|BOWL|CFP]", True,
        "Competition type of the observation.",
        ("blowout_treatment", "game_sd_points", "recent_form_weights"),
        "V3 freezes strength after Selection Day, so postseason games must be "
        "separable from regular-season games. Without this field a bowl blowout is "
        "fitted as if it were a Week 4 result.",
    ),
    ContractField(
        "overtime_periods", "integer", True,
        "Number of overtime periods, 0 for regulation.",
        ("game_sd_points", "blowout_treatment"),
        "College overtime manufactures margins that no pregame model predicts. Folding "
        "them into an untagged residual pool inflates game_sd_points, which is the exact "
        "direction of the unexplained 20.2 observation.",
    ),
    ContractField(
        "opponent_division", "enum[FBS|FCS]", True,
        "Division of the opponent.",
        ("game_sd_points", "blowout_treatment", "sample_size_regularization"),
        "The FCS-to-V3 point scale is itself an open blocker "
        "(model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER). Until it is closed, FCS "
        "games must be identifiable so they can be excluded rather than silently fitted "
        "on an unresolved scale.",
    ),
)

#: Volume required before an experiment can be scored at all, with the reason.
#: These are structural minima, not statistical power claims.
MINIMUM_VOLUME_REQUIREMENTS: dict[str, Any] = {
    "minimum_distinct_seasons": 3,
    "minimum_distinct_seasons_reason": (
        "A temporal split needs at least one season each for training, validation and "
        "holdout. Two seasons cannot produce three ordered partitions."
    ),
    "minimum_observations_total": 1500,
    "minimum_observations_total_reason": (
        "recent_form_weights and sample_size_regularization are fitted per week-index "
        "regime, so the sample is divided before it is used. A single season of roughly "
        "750 games leaves each weekly regime too thin to separate from noise."
    ),
    "minimum_holdout_observations": 300,
    "minimum_holdout_observations_reason": (
        "The holdout is scored once. It must be large enough that its RMSE is not "
        "dominated by a handful of blowouts."
    ),
    "minimum_weeks_per_team_per_season": 8,
    "minimum_weeks_per_team_per_season_reason": (
        "recent_form_weights is a decay over prior weeks; a team with three observations "
        "cannot inform the tail of that decay."
    ),
}

#: Split policy. Stated separately from the field list because the split rule is
#: what makes the primary objective out-of-sample rather than in-sample.
SPLIT_POLICY: dict[str, Any] = {
    "splits": list(cal.DATA_SPLITS),
    "assignment": "TEMPORAL_ONLY",
    "random_assignment_permitted": False,
    "random_assignment_refusal_reason": (
        "Weekly ratings are a sequential process. A randomly assigned holdout game sits "
        "earlier in time than training games that already absorbed its result, so the "
        "measured out-of-sample error is not out-of-sample."
    ),
    "ordering_rule": (
        "max(event_time) of training < min(event_time) of validation, and "
        "max(event_time) of validation < min(event_time) of holdout."
    ),
    "holdout_use": "SCORED_ONCE_AT_THE_END_NEVER_FOR_SELECTION",
    "validation_use": "REGIME_SELECTION_AND_HYPERPARAMETER_SEARCH",
}

#: Provenance a dataset must carry as a whole, over and above its rows.
DATASET_PROVENANCE_REQUIREMENTS: dict[str, Any] = {
    "dataset_id": "Stable identifier recorded in the experiment record.",
    "sha256": "SHA-256 of the exact bytes scored, so a result can be re-tied to its input.",
    "source_authority": (
        "Named authority that certifies the results. Must be a result source, not the "
        "V2.1 static control workbook and not any engine output."
    ),
    "retrieval_method": "How the bytes were obtained, reproducibly.",
    "retrieved_at": "UTC timestamp of retrieval.",
    "rating_scale_declaration": (
        "The units of pregame_team_rating and expected_margin. A residual computed "
        "across two scales is arithmetic, not evidence."
    ),
    "expected_margin_transform": (
        "The named rating-to-margin transform used. Without it, "
        "weekly_performance_residual_coefficient is unidentifiable: any residual can be "
        "explained by re-scaling the transform instead."
    ),
    "forbidden_content": (
        "No public betting flow, handle, ticket or steam signal under any spelling, and "
        "no injury adjustment. Refused at registration by "
        "calibration.register_dataset, not by review."
    ),
    "synthetic_content": (
        "REFUSED. A synthetic or simulated observation set may never be registered as "
        "governed calibration data."
    ),
}


def missing_required_data() -> dict[str, Any]:
    """State what is absent, in the terms a supplier would need to close it."""
    return {
        "dataset": "HISTORICAL_GAME_RESULT_OBSERVATION_SET",
        "status": "NOT_PRESENT_IN_REPOSITORY",
        "why_no_repository_artifact_substitutes": {
            "2026_FBS_Schedule_LOCKED_v5.xlsx": (
                "743 fixtures, zero score columns. Fixtures without results."
            ),
            "V2_1_STATIC_CONTROL_2026_CFB_10000_Season_Monte_Carlo.xlsx": (
                "Simulation output over 10,000 synthetic seasons. Engine belief, not "
                "observation. Registering it would score the engine against itself."
            ),
            "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx": (
                "Preseason strength priors. Predictors with no outcomes attached."
            ),
            "POWER_CRUNCH_2026_Team_Reconciled_Master_134_v2_2.xlsx": (
                "Identity reconciliation for 134 entities. No games."
            ),
            "Model_Parameters_v2_5_APPROVED.xlsx": (
                "Parameter and governance registers. Records that margin-SD calibration "
                "is OPEN; contains no per-game observations."
            ),
        },
        "required_contract_fields": [f.name for f in REQUIRED_CONTRACT_FIELDS],
        "fields_requiring_admission_ruling": [
            f.name for f in FIELDS_REQUIRING_ADMISSION_RULING
        ],
        "minimum_volume": dict(MINIMUM_VOLUME_REQUIREMENTS),
        "blocks": list(cal.CALIBRATION_FIELDS) + ["governance.GAME_SD_CALIBRATION_OPEN"],
    }


def contract_as_dict() -> dict[str, Any]:
    """The full machine-readable ingestion contract."""
    return {
        "contract_id": CONTRACT_ID,
        "status": CONTRACT_STATUS,
        "primary_objective": {
            "metric": cal.PRIMARY_CALIBRATION_METRIC,
            "direction": cal.PRIMARY_CALIBRATION_DIRECTION,
            "ruling": cal.PRIMARY_OBJECTIVE.objective_id,
        },
        "independent_witnesses": list(cal.INDEPENDENT_WITNESSES),
        "witness_composite_authorised": False,
        "supporting_diagnostics": list(cal.SUPPORTING_DIAGNOSTICS),
        "required_fields": [f.as_dict() for f in REQUIRED_CONTRACT_FIELDS],
        "fields_requiring_admission_ruling": [
            f.as_dict() for f in FIELDS_REQUIRING_ADMISSION_RULING
        ],
        "governed_allowlist": list(cal.CALIBRATION_OBSERVATION_COLUMNS),
        "split_policy": dict(SPLIT_POLICY),
        "minimum_volume": dict(MINIMUM_VOLUME_REQUIREMENTS),
        "dataset_provenance_requirements": dict(DATASET_PROVENANCE_REQUIREMENTS),
        "supported_formats": list(cal.SUPPORTED_DATASET_FORMATS),
        "missing_required_data": missing_required_data(),
        "automatic_promotion": False,
        "promotion_authorities": list(cal.PROMOTION_AUTHORITIES),
        "blockers_open": list(cal.CALIBRATION_FIELDS)
        + ["governance.GAME_SD_CALIBRATION_OPEN"],
    }


def unadmitted_required_fields() -> list[str]:
    """Required contract fields the governed observation allowlist does not admit."""
    admitted = {c.lower() for c in cal.CALIBRATION_OBSERVATION_COLUMNS}
    everything = REQUIRED_CONTRACT_FIELDS + FIELDS_REQUIRING_ADMISSION_RULING
    return sorted(f.name for f in everything if f.name.lower() not in admitted)


def assert_contract_not_satisfied_by_repository(root: Path) -> None:
    """Fail closed if anything ever claims the contract is already satisfied.

    There is no mounted observation set. This exists so that a future change which
    *believes* it mounted one has to say where, rather than letting
    ``dataset_mounted: False`` drift out of agreement with reality.
    """
    mounted = sorted(
        p for p in (root / "config" / "dynamic_weekly_mc_v3" / "governed").glob("*")
        if p.is_file() and "calibration" in p.name.lower()
    )
    if mounted:
        raise GovernanceBlock(
            "A governed calibration observation artifact appeared at "
            f"{[str(p) for p in mounted]}. It must be registered through "
            "calibration.register_dataset and recorded in the contract before any "
            "experiment may cite it."
        )


def write_contract(path: Path) -> Path:
    """Emit the contract as a reviewable JSON artifact.

    LF is pinned rather than inherited: this artifact is compared by digest
    across machines, so a CRLF emission on Windows would read as a changed
    contract when nothing about the contract had changed.
    """
    return write_json_lf(path, contract_as_dict(), trailing_newline=True)
