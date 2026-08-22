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

Ruling R6-CAL-TEMPORAL-ORDER reissues one clause of this contract as revision
R1. ``event_time`` was unconditionally required, and the governed historical
corpus does not carry one for every observation, so the clause as written left a
supplier two options: withhold real evidence, or generate a kickoff time the
source never recorded. The second is the worse failure, because a fabricated
instant is indistinguishable from a measured one the moment it is written down.
So ``event_time`` becomes conditional -- required wherever a timestamp exists,
null and never synthesised where one does not -- and the causal-order guarantee
it carried is re-established at a declared weaker granularity by
:data:`TEMPORAL_ORDER_POLICY`. That is a substitution, not a relaxation: an
observation admitted without ``event_time`` must carry ordering provenance a
reviewer can re-open and re-hash.

Nothing here promotes a value, and nothing here mounts a dataset.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import calibration as cal
from .errors import GovernanceBlock

CONTRACT_ID = "V3-CALIBRATION-DATA-CONTRACT-001"
CONTRACT_STATUS = "SPECIFICATION_ONLY_NO_DATASET_MOUNTED"

#: The contract identity is stable; its revision is not. R1 narrows exactly one
#: clause -- the unconditional requirement for event_time -- and replaces it with
#: the governed temporal-order successor. Nothing else in the contract moved.
CONTRACT_REVISION = "R1-TEMPORAL-ORDER-SUCCESSOR"
CONTRACT_REVISION_SUPERSEDES = (
    "The first issue of this contract, in which event_time was unconditionally "
    "required of every observation. That clause is superseded to exactly the extent "
    "that a governed source recorded no kickoff timestamp. It is not relaxed: such "
    "an observation must keep event_time null and carry the temporal_order provenance "
    "ruling R6-CAL-TEMPORAL-ORDER requires. The first issue is preserved "
    "in the repository history and was not rewritten."
)


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
    #: Set where the field is required only under a stated condition. A field with
    #: ``required=False`` and no condition would read as optional; every field here
    #: that is not unconditionally required states the condition that makes it so.
    conditional_requirement: str | None = None

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

_TEMPORAL_SUCCESSOR = (
    "REQUIRED wherever the governed source recorded a kickoff or event timestamp. "
    "Where the source recorded none, this field MUST remain null and the observation "
    "may instead be admitted on governed_temporal_order under ruling "
    "R6-CAL-TEMPORAL-ORDER. It is not optional: the causal-order guarantee is "
    "replaced by temporal_order_* provenance, never dropped."
)
_TEMPORAL_PROVENANCE = (
    "REQUIRED for every observation admitted without an authentic event_time, under "
    "ruling R6-CAL-TEMPORAL-ORDER. All four temporal_order_* fields are required "
    "together; a partial set is refused, because a basis with no re-checkable source "
    "establishes nothing."
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
        "event_time", "iso8601|null", False,
        "Kickoff instant, where the source recorded one. Authoritative wherever it "
        "exists: it is the only field that can order two games inside a single day, "
        "and where present it is what proves a holdout game post-dates its training "
        "data.",
        ("all",),
        _OBSERVED + " A synthetic noon, midnight or other default time-of-day value is "
        "never an observation and is refused at admission.",
        conditional_requirement=_TEMPORAL_SUCCESSOR,
    ),
    ContractField(
        "temporal_order_basis", f"enum[{'|'.join(cal.TEMPORAL_EVIDENCE_PRECEDENCE)}]", False,
        "Which class of temporal evidence orders this observation. Precedence is "
        "exactly EXACT_EVENT_TIME, EXACT_GAME_DATE, WEEK_STAGE_DATE, "
        "GOVERNED_SOURCE_SEQUENCE, strongest first.",
        ("all",),
        "Must name the strongest basis the source actually supports and never a "
        "stronger one. GOVERNED_SOURCE_SEQUENCE establishes relative causal order "
        "only and is never serialized as an inferred kickoff timestamp.",
        conditional_requirement=_TEMPORAL_PROVENANCE,
    ),
    ContractField(
        "temporal_order_key", "named_fields_canonical_json", False,
        "The ordering value, carried as named source-derived fields: any of "
        f"{list(cal.TEMPORAL_ORDER_VALUE_FIELDS)}. Serialized as a self-describing "
        "canonical JSON object. A bare YYYY-MM-DD is also accepted under "
        "EXACT_GAME_DATE and a bare non-negative integer under "
        "GOVERNED_SOURCE_SEQUENCE, because each of those directly is the evidence.",
        ("all",),
        "Every field must be one the governed source actually recorded. A positional "
        "packed string is refused: no governed source states such a grammar, and "
        "reading one would make an implementation convenience into a rule. "
        "week_label and stage_label are verbatim provenance and are never parsed for "
        "ordering, because the corpus carries several incompatible label sets. No "
        "field may carry a time of day under any basis weaker than EXACT_EVENT_TIME.",
        conditional_requirement=_TEMPORAL_PROVENANCE,
    ),
    ContractField(
        "temporal_order_source", "string", False,
        "The governed source the ordering was read from.",
        ("all",),
        "Must name a source a reviewer can re-open. An ordering claim whose origin "
        "is unnamed is an assertion, not evidence.",
        conditional_requirement=_TEMPORAL_PROVENANCE,
    ),
    ContractField(
        "temporal_order_source_sha256", "sha256", False,
        "SHA-256 of the exact source bytes the ordering was read from.",
        ("all",),
        "Must be a 64-character lowercase digest. An ordering claim against unpinned "
        "bytes cannot be re-checked, so the order it asserts cannot be audited.",
        conditional_requirement=_TEMPORAL_PROVENANCE,
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

#: Temporal-order policy under ruling R6-CAL-TEMPORAL-ORDER.
#:
#: The governed corpus records no authentic time-of-day for a large part of its
#: span, so the contract has to choose between two failures. Requiring event_time
#: unconditionally pushes a supplier into generating a noon value that is
#: indistinguishable from a measurement once written down. Making event_time
#: simply optional drops the causal-order guarantee that makes the primary
#: objective out-of-sample at all. This policy does neither: the guarantee is
#: re-established at a weaker, declared granularity, bound to a source a reviewer
#: can re-open and a digest they can re-check.
TEMPORAL_ORDER_POLICY: dict[str, Any] = {
    "ruling": cal.TEMPORAL_ORDER_RULING,
    "chairman_ruling_id": cal.TEMPORAL_ORDER_RULING_ID,
    "approval_token": cal.TEMPORAL_ORDER_APPROVAL_TOKEN,
    "precedence": list(cal.TEMPORAL_EVIDENCE_PRECEDENCE),
    "granularity": dict(cal.TEMPORAL_ORDER_GRANULARITY),
    "event_time_authoritative_where_it_exists": True,
    "event_time_globally_optional": False,
    "event_time_when_source_recorded_none": "MUST_REMAIN_NULL",
    "synthetic_time_of_day_permitted": False,
    "synthetic_time_of_day_refusal_reason": (
        "The historical source packages state that chronology was not invented. A "
        "generated noon or midnight kickoff manufactures the evidence the source "
        "declined to invent, and once serialized it cannot be told apart from a "
        "measured instant by any reader downstream."
    ),
    "required_provenance_when_event_time_absent": list(
        cal.TEMPORAL_ORDER_PROVENANCE_COLUMNS
    ),
    "partial_provenance_permitted": False,
    "value_representation": "NAMED_FIELDS_CANONICAL_JSON",
    "value_fields": list(cal.TEMPORAL_ORDER_VALUE_FIELDS),
    "positional_packed_key_grammar_permitted": False,
    "positional_packed_key_refusal_reason": (
        "No governed source states a packed positional grammar, and several state "
        "incompatible week and stage label sets. A format invented to make "
        "serialization convenient would become a governance rule the Chairman never "
        "issued, and it would force a supplier to supply fields the source never "
        "recorded: the corpus holds week-ordered rows with no date at all, and "
        "undated postseason rows carrying only a stage label and a sequence."
    ),
    "stage_and_week_labels_parsed_for_ordering": False,
    "stage_and_week_label_reason": (
        "The corpus carries at least three incompatible label sets across its span. "
        "Ranking them would mean issuing a precedence no source states, so labels are "
        "carried verbatim as provenance and only a source-supplied week ordinal orders "
        "anything."
    ),
    "unresolved_date_treatment": "LEFT_ABSENT_NEVER_APPROXIMATED",
    "unresolved_week_treatment": "FALLS_BACK_TO_GOVERNED_SOURCE_SEQUENCE",
    "anti_fabrication_is_structural": True,
    "structural_anti_fabrication_rules": list(
        cal.temporal_order_governance_as_dict()["structural_anti_fabrication_rules"]
    ),
    "time_of_day_fill_detector_is_diagnostic_only": (
        cal.TIME_OF_DAY_FILL_DETECTOR_IS_DIAGNOSTIC_ONLY
    ),
    "executable_use_requires_admission": True,
    "promotion_binding_requires_admission_receipt": True,
    "promotion_binding_refusal_reason": (
        "A calibration result whose observations never passed the successor temporal "
        "contract is not promotion-eligible evidence. Binding refuses rather than "
        "returning a bound record with a caveat attached, because a caveat inside a "
        "promotion-eligible record is read by nobody at the moment it matters. The "
        "unbound path is preserved and is explicitly not promotion-eligible."
    ),
    "caller_asserted_admission_permitted": False,
    "admission_assertion_keys_refused": list(cal.ADMISSION_ASSERTION_KEYS),
    "digest_continuity_checked_at_binding": True,
    "executable_chain": list(
        cal.temporal_order_governance_as_dict()["executable_chain"]
    ),
    "registration_is_not_admission": (
        "calibration.register_dataset establishes identity, digest, record count, "
        "shape and column admissibility and reads no observation values. It is not "
        "admission, and calibration.require_admitted_observations refuses a registered "
        "dataset handed to a consumer in place of an admitted set."
    ),
    "governed_source_sequence_semantics": "RELATIVE_CAUSAL_ORDER_ONLY",
    "governed_source_sequence_serialized_as_timestamp": False,
    "cross_domain_ordering_proof": "SEASON_ONLY",
    "cross_domain_ordering_reason": (
        "A source-row ordinal and a calendar date are not comparable quantities. "
        "Where two splits hold same-season observations ordered in different domains, "
        "the boundary is unprovable and is refused rather than assumed."
    ),
    "same_day_ordering_under_day_granularity": "NOT_PROVEN",
    "missing_chronology_may_be_fabricated_to_pass_admission": False,
    "corpus_evidence": (
        "The staged calibration evidence census found zero authentic time-of-day "
        "values. 2006 and 2007 rely on canonical source-row sequence; later "
        "historical seasons preserve date/week/source-order evidence as available; "
        "modern 2024/2025 walk-forward evidence uses date/stage ordering."
    ),
    "observed_source_shapes": {
        "2006-2011": (
            "A per-season chronology sequence on every row; a week that is sometimes "
            "an ordinal and sometimes a label such as P1; a game date present on some "
            "rows and unresolved on others; and a quality flag recording which of "
            "those the source actually resolved."
        ),
        "2024-2025": (
            "A game date, an event order and a global sequence on regular-season "
            "rows; week labels spanning 0-15 and PS; phase labels including CCG, "
            "Bowl, QF and R1; and undated postseason rows carrying a stage label and "
            "a sequence and no date at all."
        ),
        "time_of_day_columns_found": 0,
    },
    "row_admission_gate": "calibration.admit_temporal_order",
    "split_gate": "calibration.require_governed_temporal_split_integrity",
    "exact_event_time_gate": "calibration.require_temporal_split_integrity",
    "admission_gate": cal.ADMISSION_GATE,
    "executable_use_guard": "calibration.require_admitted_observations",
    "executable_invariant": (
        "registered source -> digest verified -> rows temporally admitted -> partition "
        "proven forward-only -> calibration/scoring result -> promotion evidence binding"
    ),
    "promotion_binding_gate": "calibration.bind_promotion_evidence",
    "admission_receipt_type": "calibration.AdmittedObservationSet",
    "admission_receipt_boundary": (
        "The receipt cannot be constructed by the public API. The boundary is a Python "
        "one: it prevents a supported or accidental bypass, and it is not treated as a "
        "hostile-code security boundary."
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
        "max(governed temporal order) of training < min of validation, and max of "
        "validation < min of holdout, proven on the observations own ordering "
        "evidence. Where both sides of a boundary carry an authentic event_time the "
        "comparison is made on the instants. Where either side does not, it is made "
        "at the coarser granularity actually available and same-day ordering is not "
        "claimed. Observations in different ordering domains are separable only by "
        "season."
    ),
    "ordering_rule_exact_event_time_datasets": (
        "max(event_time) of training < min(event_time) of validation, and "
        "max(event_time) of validation < min(event_time) of holdout. Unchanged, and "
        "still enforced by calibration.require_temporal_split_integrity."
    ),
    "temporal_evidence_precedence": list(cal.TEMPORAL_EVIDENCE_PRECEDENCE),
    "refused_assignment_methods": list(cal.REFUSED_SPLIT_ASSIGNMENTS),
    "holdout_use": cal.HOLDOUT_USE,
    "holdout_selection_use_permitted": False,
    "selection_split": cal.SELECTION_SPLIT,
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
        "contract_revision": CONTRACT_REVISION,
        "contract_revision_supersedes": CONTRACT_REVISION_SUPERSEDES,
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
        "temporal_order_policy": dict(TEMPORAL_ORDER_POLICY),
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
    """Emit the contract as a reviewable JSON artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(contract_as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path
