"""Lane C calibration hardening and the ingestion contract.

Every test here corresponds to a path that was reachable before hardening and by
which an ungoverned number could have acquired the appearance of calibration
evidence. They are written as refusals rather than as behaviour, because the
harness has no data to behave on: the point is what it declines to accept.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_contract as contract
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import rulings
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

ROOT = Path(__file__).resolve().parents[2]
REFERENCE = ROOT / "reference" / "dynamic_weekly_mc_v3"
CONTRACT_ARTIFACT = REFERENCE / "V3_CALIBRATION_DATA_CONTRACT.json"
SUCCESSOR_STATUS = REFERENCE / "V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1.json"

HEADER = (
    "game_id,season,week,team,opponent,expected_margin,actual_margin,observed_at,recorded_at"
)
ROW = "G1,2025,1,ARK,GAST,3.5,7,2025-08-30T00:00:00Z,2025-08-31T00:00:00Z\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# --- shared fixtures: the smallest observation set the successor admits ------
#
# Test-only digests, and test-only ordering evidence in the shapes the staged
# corpus actually carries: a 2006 source sequence and a 2024/2025 resolved game
# date. Nothing here is calibration evidence and nothing here is scored; it
# exists so a fixture can reach the admission gate honestly rather than by
# carrying a schema the successor contract no longer accepts.

SEQ_SHA = "1" * 64
DATE_SHA = "2" * 64
WEEK_SHA = "3" * 64

TEMPORAL_HEADER = (
    "game_id,season,week,team,opponent,expected_margin,actual_margin,observed_at,"
    "recorded_at,split,temporal_order_basis,temporal_order_key,temporal_order_source,"
    "temporal_order_source_sha256"
)


def _observation(game_id, season, split, basis, key, *, sha=SEQ_SHA, source="corpus.csv"):
    return (
        f"{game_id},{season},1,ARK,GAST,3.5,7,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,"
        f"{split},{basis},\"{key}\",{source},{sha}"
    )


def _admissible_dataset(tmp_path, name="admissible.csv", extra_rows=()):
    rows = [
        _observation("G1", 2006, "training", cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "1"),
        _observation("G2", 2006, "training", cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "2"),
        _observation(
            "G3", 2024, "validation", cal.BASIS_EXACT_GAME_DATE, "2024-11-30", sha=DATE_SHA
        ),
        _observation(
            "G4", 2025, "holdout", cal.BASIS_EXACT_GAME_DATE, "2025-11-29", sha=DATE_SHA
        ),
        *extra_rows,
    ]
    return _write(tmp_path, name, TEMPORAL_HEADER + "\n" + "\n".join(rows) + "\n")


# --- dataset registration hardening -----------------------------------------


def test_rows_counts_records_not_lines(tmp_path):
    """A quoted embedded newline is one observation, not two.

    ``rows`` is recorded as dataset provenance and cited in experiment records, so
    counting physical lines overstates the size of a governed dataset.
    """
    dataset = _write(
        tmp_path,
        "embedded.csv",
        HEADER + '\n"G1\nCONTINUED",2025,1,ARK,GAST,3.5,7,2025-08-30T00:00:00Z,2025-08-31T00:00:00Z\n',
    )
    assert cal.register_dataset(dataset, "DS").rows == 1


def test_a_ragged_observation_row_is_refused(tmp_path):
    dataset = _write(tmp_path, "ragged.csv", HEADER + "\nG1,2025\n" + ROW)
    with pytest.raises(GovernanceBlock, match="do not match its header"):
        cal.register_dataset(dataset, "DS")


def test_a_header_with_no_observations_is_not_a_mounted_dataset(tmp_path):
    dataset = _write(tmp_path, "empty.csv", HEADER + "\n")
    with pytest.raises(GovernanceBlock, match=cal.BLOCKED_ON_CALIBRATION_DATA):
        cal.register_dataset(dataset, "DS")


def test_duplicate_observation_columns_are_refused(tmp_path):
    dataset = _write(
        tmp_path,
        "dup.csv",
        HEADER + ",game_id\n" + ROW.rstrip("\n") + ",G1\n",
    )
    with pytest.raises(GovernanceBlock, match="duplicate columns"):
        cal.register_dataset(dataset, "DS")


def test_blank_trailing_lines_do_not_inflate_the_record_count(tmp_path):
    dataset = _write(tmp_path, "trailing.csv", HEADER + "\n" + ROW + "\n\n")
    assert cal.register_dataset(dataset, "DS").rows == 1


def test_an_admissible_dataset_still_registers_with_its_sha256(tmp_path):
    dataset = _write(tmp_path, "ok.csv", HEADER + "\n" + ROW)
    registered = cal.register_dataset(dataset, "DS")
    assert registered.rows == 1
    assert len(registered.sha256) == 64


# --- governed ranking --------------------------------------------------------


def _record(experiment_id, value, *, split="holdout", regime_id="R1", metric=None):
    return cal.ExperimentRecord(
        experiment_id=experiment_id,
        model_version="3.0.0-experimental-harness",
        configuration_version="V3-PLACEHOLDER-2026-08-21-R2-001",
        seed=20260803,
        regime_id=regime_id,
        candidate_values={"game_sd_points": 17.0},
        dataset_id="DS",
        dataset_sha256="0" * 64,
        objective_id=cal.PRIMARY_OBJECTIVE.objective_id,
        run_timestamp="2026-08-21T00:00:00Z",
        metrics={metric or cal.PRIMARY_CALIBRATION_METRIC: value},
        v2_1_control_comparison={},
        split=split,
    )


def test_the_governed_ranking_refuses_a_non_governed_objective():
    """A named objective is not automatically the governed one."""
    vanity = cal.EvaluationObjective("OBJ-V", "my_metric", "maximize", "chosen after the fact")
    records = [_record("E1", 9.0, metric="my_metric"), _record("E2", 1.0, metric="my_metric")]
    with pytest.raises(GovernanceBlock, match="primary calibration criterion"):
        cal.rank_experiments_governed(records, vanity)


def test_the_governed_ranking_refuses_records_that_do_not_declare_a_split():
    records = [_record("E1", 11.0, split=None), _record("E2", 12.0)]
    with pytest.raises(GovernanceBlock, match="do not declare which split"):
        cal.rank_experiments_governed(records, cal.PRIMARY_OBJECTIVE)


def test_the_governed_ranking_refuses_to_compare_across_splits():
    records = [_record("E1", 11.0, split="training"), _record("E2", 12.0, split="holdout")]
    with pytest.raises(GovernanceBlock, match="mixed splits"):
        cal.rank_experiments_governed(records, cal.PRIMARY_OBJECTIVE)


def test_the_governed_ranking_minimises_the_primary_criterion():
    records = [_record("E1", 12.5), _record("E2", 11.5, regime_id="R2")]
    ranked = cal.rank_experiments_governed(records, cal.PRIMARY_OBJECTIVE)
    assert [r.experiment_id for r in ranked] == ["E2", "E1"]


def test_an_experiment_cannot_declare_an_unknown_split():
    with pytest.raises(InputValidationError, match="expected one of"):
        _record("E1", 11.0, split="test")


# --- promotion evidence binding ----------------------------------------------


def _dataset(tmp_path, name="bound.csv") -> cal.CalibrationDataset:
    """A registered dataset whose rows can actually pass temporal admission.

    The old fixture carried no temporal columns at all. That shape predates
    ruling R6-CAL-TEMPORAL-ORDER and is no longer admissible, so it is replaced
    rather than kept working: a fixture that can only be bound by skipping the
    gate is a fixture that documents the bypass.
    """
    return cal.register_dataset(_admissible_dataset(tmp_path, name), "DS-B")


def _admitted(tmp_path, name="bound.csv"):
    return cal.load_admitted_observations(_dataset(tmp_path, name))


def test_a_hand_written_evidence_dict_is_stamped_unbound():
    """The R2 gate is satisfied by a typed number; the record has to say so."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    record = cal.promote_regime_r2(
        regime,
        authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
        approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
        evidence={cal.PRIMARY_CALIBRATION_METRIC: 0.0001, "split": "holdout"},
    )
    assert record["evidence_bound"] is False
    assert record["evidence_binding"] == cal.EVIDENCE_UNBOUND
    assert record["writes_canonical_config"] is False


def test_bound_evidence_must_cite_the_regime_it_scored(tmp_path):
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    other = cal.ExperimentRecord(
        experiment_id="E9", model_version="m", configuration_version="c", seed=1,
        regime_id="R-OTHER", candidate_values={}, dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256, objective_id="O", run_timestamp="t",
        metrics={cal.PRIMARY_CALIBRATION_METRIC: 11.3}, v2_1_control_comparison={},
        split="holdout",
    )
    with pytest.raises(GovernanceBlock, match="which scored regime"):
        cal.promote_regime_r2(
            regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
            approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
            evidence={cal.PRIMARY_CALIBRATION_METRIC: 11.3, "split": "holdout"},
            experiment=other, dataset=dataset,
        )


def test_bound_evidence_must_have_been_measured_on_the_scored_bytes(tmp_path):
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    stale = cal.ExperimentRecord(
        experiment_id="E9", model_version="m", configuration_version="c", seed=1,
        regime_id="R1", candidate_values={}, dataset_id=dataset.dataset_id,
        dataset_sha256="f" * 64, objective_id="O", run_timestamp="t",
        metrics={cal.PRIMARY_CALIBRATION_METRIC: 11.3}, v2_1_control_comparison={},
        split="holdout",
    )
    with pytest.raises(GovernanceBlock, match="not the scored bytes"):
        cal.promote_regime_r2(
            regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
            approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
            evidence={cal.PRIMARY_CALIBRATION_METRIC: 11.3, "split": "holdout"},
            experiment=stale, dataset=dataset,
        )


def test_bound_evidence_must_come_from_the_holdout_split(tmp_path):
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    trained = cal.ExperimentRecord(
        experiment_id="E9", model_version="m", configuration_version="c", seed=1,
        regime_id="R1", candidate_values={}, dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256, objective_id="O", run_timestamp="t",
        metrics={cal.PRIMARY_CALIBRATION_METRIC: 11.3}, v2_1_control_comparison={},
        split="training",
    )
    with pytest.raises(GovernanceBlock, match="must be measured on"):
        cal.promote_regime_r2(
            regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
            approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
            evidence={cal.PRIMARY_CALIBRATION_METRIC: 11.3, "split": "holdout"},
            experiment=trained, dataset=dataset,
        )


def test_a_promotion_may_not_cite_a_number_the_experiment_did_not_measure(tmp_path):
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    measured = cal.ExperimentRecord(
        experiment_id="E9", model_version="m", configuration_version="c", seed=1,
        regime_id="R1", candidate_values={}, dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256, objective_id="O", run_timestamp="t",
        metrics={cal.PRIMARY_CALIBRATION_METRIC: 11.3}, v2_1_control_comparison={},
        split="holdout",
    )
    with pytest.raises(GovernanceBlock, match="but experiment"):
        cal.promote_regime_r2(
            regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
            approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
            evidence={cal.PRIMARY_CALIBRATION_METRIC: 0.0001, "split": "holdout"},
            experiment=measured, dataset=dataset,
        )


def test_fully_bound_evidence_records_what_it_was_bound_to(tmp_path):
    """The whole chain, end to end: registered, admitted, partitioned, bound."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    admitted = cal.load_admitted_observations(dataset)
    measured = cal.ExperimentRecord(
        experiment_id="E9", model_version="m", configuration_version="c", seed=1,
        regime_id="R1", candidate_values={}, dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256, objective_id="O", run_timestamp="t",
        metrics={cal.PRIMARY_CALIBRATION_METRIC: 11.3}, v2_1_control_comparison={},
        split="holdout",
    )
    record = cal.promote_regime_r2(
        regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
        approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
        evidence={cal.PRIMARY_CALIBRATION_METRIC: 11.3, "split": "holdout"},
        experiment=measured, dataset=dataset, observations=admitted,
    )
    assert record["evidence_bound"] is True
    assert record["evidence_binding"] == cal.EVIDENCE_BOUND
    assert record["bound_dataset_sha256"] == dataset.sha256
    assert record["measured_primary_metric"] == 11.3
    assert record["observations_admitted"] is True
    assert record["admitted_observation_count"] == 4
    assert record["admission_gate"] == "calibration.load_admitted_observations"
    assert record["admitted_split_report"]["leak_free"] is True
    assert record["promotion_eligible"] is True
    # Binding raises the quality of the evidence. It still does not write config.
    assert record["writes_canonical_config"] is False


# --- temporal split integrity ------------------------------------------------


def test_a_temporally_ordered_partition_passes():
    report = cal.require_temporal_split_integrity(
        {
            "G1": ("training", "2023-09-02T00:00:00Z"),
            "G2": ("training", "2023-09-09T00:00:00Z"),
            "G3": ("validation", "2024-09-07T00:00:00Z"),
            "G4": ("holdout", "2025-09-06T00:00:00Z"),
        }
    )
    assert report["leak_free"] is True
    assert report["assignment"] == "TEMPORAL_ONLY"
    assert report["splits"] == {"training": 2, "validation": 1, "holdout": 1}


def test_a_holdout_that_precedes_training_is_refused():
    """A random split of sequential rating data is not out-of-sample."""
    with pytest.raises(GovernanceBlock, match="not temporally ordered"):
        cal.require_temporal_split_integrity(
            {
                "G1": ("training", "2025-11-01T00:00:00Z"),
                "G2": ("validation", "2024-09-07T00:00:00Z"),
                "G3": ("holdout", "2023-09-02T00:00:00Z"),
            }
        )


def test_an_unpopulated_split_is_refused():
    with pytest.raises(GovernanceBlock, match="populated"):
        cal.require_temporal_split_integrity(
            {
                "G1": ("training", "2023-09-02T00:00:00Z"),
                "G2": ("holdout", "2025-09-06T00:00:00Z"),
            }
        )


# --- the ingestion contract --------------------------------------------------


def test_the_contract_states_the_governed_primary_objective():
    payload = contract.contract_as_dict()
    assert payload["primary_objective"]["metric"] == "out_of_sample_baxter_rating_rmse"
    assert payload["primary_objective"]["direction"] == "minimize"
    assert payload["independent_witnesses"] == ["colley_matrix", "srs"]
    assert payload["witness_composite_authorised"] is False
    assert payload["automatic_promotion"] is False


def test_every_required_field_names_the_coefficient_that_needs_it():
    for field in contract.REQUIRED_CONTRACT_FIELDS:
        assert field.needed_by, field.name
        assert field.definition.strip()
        assert field.provenance_requirement.strip()
        for coefficient in field.needed_by:
            assert coefficient == "all" or coefficient in cal.CALIBRATION_FIELDS


def test_the_contract_covers_every_required_observation_column():
    named = {f.name for f in contract.REQUIRED_CONTRACT_FIELDS}
    assert set(cal.REQUIRED_OBSERVATION_COLUMNS) <= named


def test_fields_the_allowlist_does_not_admit_are_ruling_requests_not_additions():
    """The contract may not widen the governed allowlist by asserting a need."""
    unadmitted = contract.unadmitted_required_fields()
    assert unadmitted, "the gap this module exists to report has disappeared"
    admitted = {c.lower() for c in cal.CALIBRATION_OBSERVATION_COLUMNS}
    for name in unadmitted:
        assert name not in admitted
    # And they are exactly the ones flagged for a ruling.
    assert unadmitted == sorted(f.name for f in contract.FIELDS_REQUIRING_ADMISSION_RULING)


def test_the_split_policy_refuses_random_assignment():
    policy = contract.SPLIT_POLICY
    assert policy["assignment"] == "TEMPORAL_ONLY"
    assert policy["random_assignment_permitted"] is False
    assert policy["holdout_use"] == "SCORED_ONCE_AT_THE_END_NEVER_FOR_SELECTION"


def test_the_contract_refuses_synthetic_and_simulated_observations():
    requirements = contract.DATASET_PROVENANCE_REQUIREMENTS
    assert "REFUSED" in requirements["synthetic_content"]
    missing = contract.missing_required_data()
    control = "V2_1_STATIC_CONTROL_2026_CFB_10000_Season_Monte_Carlo.xlsx"
    assert control in missing["why_no_repository_artifact_substitutes"]


def test_the_contract_reports_the_dataset_as_absent():
    missing = contract.missing_required_data()
    assert missing["status"] == "NOT_PRESENT_IN_REPOSITORY"
    assert set(cal.CALIBRATION_FIELDS) <= set(missing["blocks"])
    assert "governance.GAME_SD_CALIBRATION_OPEN" in missing["blocks"]


def test_no_governed_calibration_artifact_has_appeared_in_the_repository():
    contract.assert_contract_not_satisfied_by_repository(ROOT)


def test_the_contract_serialises_to_reviewable_json(tmp_path):
    path = contract.write_contract(tmp_path / "contract.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["contract_id"] == contract.CONTRACT_ID
    assert payload["status"] == "SPECIFICATION_ONLY_NO_DATASET_MOUNTED"


# --- the 20.2 observation stays unpromotable ---------------------------------


def test_the_recorded_20_2_margin_sd_is_never_admitted_by_this_lane():
    """20.2 is an achieved engine value above its own 16-18 band, not a target."""
    status = cal.calibration_status({name: None for name in cal.CALIBRATION_FIELDS})
    assert status["recorded_legacy_margin_sd"] == 20.2
    assert status["legacy_margin_sd_within_band"] is False
    assert status["legacy_margin_sd_approved"] is False
    governance = cal.calibration_governance_as_dict()
    assert governance["legacy_margin_sd_20_2_promotable"] is False
    assert governance["synthetic_calibration_data_admissible"] is False
    assert governance["random_split_permitted"] is False
    assert governance["ranking_requires_primary_objective"] is True


def test_all_seven_lane_c_blockers_remain_open():
    payload = contract.contract_as_dict()
    assert sorted(payload["blockers_open"]) == sorted(
        [
            "blowout_treatment",
            "game_sd_points",
            "governance.GAME_SD_CALIBRATION_OPEN",
            "recent_form_weights",
            "sample_size_regularization",
            "weekly_movement_cap_points",
            "weekly_performance_residual_coefficient",
        ]
    )

# =============================================================================
# The temporal-order successor — ruling R6-CAL-TEMPORAL-ORDER
# =============================================================================
#
# The governed corpus holds no authentic kickoff time for a large part of its
# span, so the contract's unconditional event_time requirement offered a supplier
# a choice between withholding real evidence and inventing a kickoff time. These
# tests pin down the third answer: admit the observation on the ordering evidence
# that genuinely exists, at the granularity it genuinely proves, and refuse
# everything that would let a manufactured instant through instead.
#
# The fixtures below use the *shapes* the staged calibration corpus actually
# carries, and no data from it. Those shapes are the reason the ordering value is
# a named-field structure rather than a packed string:
#
#   2006-2011  chronology_sequence, a clean_week that is sometimes "1" and
#              sometimes "P1", a clean_game_date that is sometimes absent, and a
#              quality flag saying which of those the source resolved
#   2024-2025  game_date, event_order/global_sequence, week labels "0".."15" and
#              "PS", phase labels "regular"/"CCG"/"Bowl"/"QF"/"R1"
#
# No packed positional key appears anywhere in that corpus, several incompatible
# week and stage label sets do, and the 2024 championship rows carry a stage
# label and a sequence with no date at all.

def _evidence(basis, value, source="phase4m_2006_2011_week_by_week.csv", sha=SEQ_SHA):
    return cal.TemporalOrderEvidence(
        basis=basis, value=value, source=source, source_sha256=sha
    )


def _row(game_id, season, split, **extra):
    row = {"game_id": game_id, "season": season, "split": split}
    row.update(extra)
    return row


# --- A: an authentic timestamp is accepted and preferred ---------------------


def test_an_authentic_event_time_is_accepted_and_is_authoritative():
    order = cal.admit_temporal_order("G1", event_time="2025-09-06T19:30:00Z")
    assert order.basis == cal.BASIS_EXACT_EVENT_TIME
    assert order.granularity == "INSTANT"
    assert order.has_authentic_event_time is True
    assert order.event_time == "2025-09-06T19:30:00Z"
    assert order.precedence_rank == 0
    # Precedence is a real ordering, not a list of equals.
    assert cal.TEMPORAL_EVIDENCE_PRECEDENCE == (
        "EXACT_EVENT_TIME",
        "EXACT_GAME_DATE",
        "WEEK_STAGE_DATE",
        "GOVERNED_SOURCE_SEQUENCE",
    )


def test_an_unparseable_event_time_is_refused_rather_than_coerced():
    with pytest.raises(GovernanceBlock, match="not a well-formed ISO-8601 instant"):
        cal.admit_temporal_order("G1", event_time="2025-09-06 19:30")


# --- B, C, D: the three alternate bases are admissible -----------------------


def test_an_exact_game_date_admits_an_observation_with_no_event_time():
    """The 2006 shape: a resolved source date, no time of day anywhere."""
    order = cal.admit_temporal_order(
        "G2006_P1731",
        evidence=_evidence(
            cal.BASIS_EXACT_GAME_DATE,
            {"season": 2006, "game_date": "2006-08-31", "week_ordinal": 1},
            sha=DATE_SHA,
        ),
    )
    assert order.basis == cal.BASIS_EXACT_GAME_DATE
    assert order.granularity == "DAY"
    assert order.calendar_date == "2006-08-31"
    assert order.domain == cal.CALENDAR_DOMAIN
    assert order.event_time is None
    assert order.has_authentic_event_time is False
    assert order.source_sha256 == DATE_SHA


def test_a_bare_iso_date_is_accepted_because_it_directly_is_the_evidence():
    order = cal.admit_temporal_order(
        "G2", evidence=_evidence(cal.BASIS_EXACT_GAME_DATE, "2019-11-30", sha=DATE_SHA)
    )
    assert order.value == cal.TemporalOrderValue(game_date="2019-11-30")


def test_week_stage_date_evidence_admits_an_observation_with_no_event_time():
    """The 2008 shape: a week the source resolved, a date it did not.

    G2006_P1732 in the staged corpus is exactly this row: clean_week 1,
    clean_game_date empty, usable_for_exact_date NO. Under a format that required
    an anchor date it could not have been represented without inventing one.
    """
    order = cal.admit_temporal_order(
        "G2008_P0004",
        evidence=_evidence(
            cal.BASIS_WEEK_STAGE_DATE,
            {"season": 2008, "week_ordinal": 1, "week_label": "1"},
            source="phase4m_2008_week_by_week.csv",
            sha=WEEK_SHA,
        ),
    )
    assert order.basis == cal.BASIS_WEEK_STAGE_DATE
    assert order.granularity == "WEEK"
    assert order.calendar_date is None
    assert order.value.season == 2008
    assert order.value.week_ordinal == 1
    assert order.domain.startswith(cal.SEASON_WEEK_DOMAIN)
    assert order.event_time is None


def test_week_stage_date_evidence_with_a_resolved_date_orders_on_the_calendar():
    """The 2011 shape: a pipeline-resolved date carrying week-level authority."""
    order = cal.admit_temporal_order(
        "G2011_P2885",
        evidence=_evidence(
            cal.BASIS_WEEK_STAGE_DATE,
            {"season": 2011, "game_date": "2011-08-28", "week_label": "P1"},
            source="phase4m_2011_week_by_week.csv",
            sha=WEEK_SHA,
        ),
    )
    assert order.granularity == "WEEK"
    assert order.domain == cal.CALENDAR_DOMAIN
    assert order.calendar_date == "2011-08-28"
    assert order.value.week_label == "P1"


def test_governed_source_sequence_admits_an_observation_with_no_event_time():
    """2006 and 2007 survive only as canonical source-row order. That is enough."""
    order = cal.admit_temporal_order(
        "G2006_P1784", evidence=_evidence(cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "54")
    )
    assert order.basis == cal.BASIS_GOVERNED_SOURCE_SEQUENCE
    assert order.granularity == "RELATIVE_SEQUENCE"
    assert order.sequence_ordinal == 54
    assert order.calendar_date is None
    assert order.event_time is None


def test_an_undated_postseason_row_is_admissible_on_its_sequence():
    """The 2024 CCG shape: stage label PS/CCG, a global sequence, no date."""
    order = cal.admit_temporal_order(
        "CCG_SEC",
        evidence=_evidence(
            cal.BASIS_GOVERNED_SOURCE_SEQUENCE,
            {"season": 2024, "sequence": 710, "week_label": "PS", "stage_label": "CCG"},
            source="official_synthetic_event_stream_2024_2025.csv",
        ),
    )
    assert order.sequence_ordinal == 710
    assert order.value.stage_label == "CCG"
    assert order.calendar_date is None


# --- R1: no invented positional grammar, no invented label precedence --------


def test_a_positional_packed_key_is_refused_rather_than_parsed():
    """A grammar no governed source states must not become a governance rule."""
    with pytest.raises(GovernanceBlock, match="positional packed string is refused"):
        cal.admit_temporal_order(
            "G1",
            evidence=_evidence(
                cal.BASIS_WEEK_STAGE_DATE, "2011-08-28|REG|05", sha=WEEK_SHA
            ),
        )


def test_the_ordering_value_serialises_as_a_self_describing_object():
    value = cal.TemporalOrderValue(season=2008, week_ordinal=3, week_label="3")
    assert value.canonical() == '{"season":2008,"week_label":"3","week_ordinal":3}'
    # Round-trips through the canonical text a CSV cell would carry.
    order = cal.admit_temporal_order(
        "G1",
        evidence=_evidence(cal.BASIS_WEEK_STAGE_DATE, value.canonical(), sha=WEEK_SHA),
    )
    assert order.value == value


def test_a_stage_or_week_label_alone_cannot_order_anything():
    """The corpus uses P1, PS, W1, CCG, Bowl, QF, R1. We rank none of them."""
    with pytest.raises(GovernanceBlock, match="never parsed for ordering"):
        cal.admit_temporal_order(
            "CCG_SEC",
            evidence=_evidence(
                cal.BASIS_WEEK_STAGE_DATE,
                {"season": 2024, "week_label": "PS", "stage_label": "CCG"},
                sha=WEEK_SHA,
            ),
        )


def test_week_stage_evidence_without_a_season_is_refused():
    with pytest.raises(GovernanceBlock, match="supplies no season"):
        cal.admit_temporal_order(
            "G1",
            evidence=_evidence(cal.BASIS_WEEK_STAGE_DATE, {"week_ordinal": 3}, sha=WEEK_SHA),
        )


def test_an_unrecognised_ordering_field_is_refused_rather_than_ignored():
    with pytest.raises(GovernanceBlock, match="outside the governed set"):
        cal.admit_temporal_order(
            "G1",
            evidence=_evidence(
                cal.BASIS_EXACT_GAME_DATE,
                {"game_date": "2006-08-31", "kickoff_hour": "12"},
                sha=DATE_SHA,
            ),
        )


def test_source_sequence_evidence_may_not_be_upgraded_to_date_evidence():
    with pytest.raises(GovernanceBlock, match="silently upgrade sequence evidence"):
        cal.admit_temporal_order(
            "G1",
            evidence=_evidence(
                cal.BASIS_GOVERNED_SOURCE_SEQUENCE,
                {"sequence": 54, "game_date": "2006-09-16"},
            ),
        )


def test_a_basis_that_disagrees_with_its_value_is_refused():
    with pytest.raises(GovernanceBlock, match="supplies no game_date"):
        cal.admit_temporal_order(
            "G1",
            evidence=_evidence(
                cal.BASIS_EXACT_GAME_DATE, {"season": 2006, "sequence": 54}, sha=DATE_SHA
            ),
        )
    with pytest.raises(GovernanceBlock, match="supplies no sequence"):
        cal.admit_temporal_order(
            "G1",
            evidence=_evidence(
                cal.BASIS_GOVERNED_SOURCE_SEQUENCE, {"season": 2006, "week_ordinal": 2}
            ),
        )


def test_an_unresolved_date_is_left_absent_rather_than_approximated():
    with pytest.raises(GovernanceBlock, match="expected a bare calendar date"):
        cal.admit_temporal_order(
            "G1",
            evidence=_evidence(
                cal.BASIS_EXACT_GAME_DATE, {"game_date": "Sept 2006"}, sha=DATE_SHA
            ),
        )


# --- E: no timestamp and no evidence fails closed ----------------------------


def test_no_event_time_and_no_temporal_evidence_fails_closed():
    with pytest.raises(GovernanceBlock, match="never fabricated"):
        cal.admit_temporal_order("G5")


def test_a_row_with_neither_a_timestamp_nor_provenance_fails_closed():
    with pytest.raises(GovernanceBlock, match="no governed temporal evidence"):
        cal.admit_observation_temporal_order(_row("G5", 2006, "training"))


# --- F / R3: anti-fabrication is structural, not heuristic -------------------


@pytest.mark.parametrize(
    "basis,value,sha",
    [
        (cal.BASIS_EXACT_GAME_DATE, {"game_date": "2006-09-02"}, DATE_SHA),
        (
            cal.BASIS_WEEK_STAGE_DATE,
            {"season": 2008, "week_ordinal": 1},
            WEEK_SHA,
        ),
        (cal.BASIS_GOVERNED_SOURCE_SEQUENCE, {"sequence": 54}, SEQ_SHA),
    ],
)
def test_one_fabricated_noon_cannot_give_a_coarse_source_an_event_time(basis, value, sha):
    """A single row, a unique timestamp, no repeated-fill pattern to lean on.

    The refusal is structural: a source that recorded a date, a week or a row
    number did not also record a kickoff instant, so the two claims cannot both
    be true and the row is refused rather than resolved by precedence.
    """
    with pytest.raises(GovernanceBlock, match="one of the two was manufactured"):
        cal.admit_temporal_order(
            "G6",
            event_time="2006-09-02T12:00:00Z",
            evidence=_evidence(basis, value, sha=sha),
        )


def test_a_coarse_basis_row_with_a_unique_plausible_timestamp_still_fails_closed():
    """13:07 is not a default fill and would trip no pattern detector."""
    with pytest.raises(GovernanceBlock, match="one of the two was manufactured"):
        cal.admit_observation_temporal_order(
            _row(
                "G2011_P2885",
                2011,
                "training",
                event_time="2011-08-28T13:07:00Z",
                temporal_order_basis=cal.BASIS_WEEK_STAGE_DATE,
                temporal_order_key='{"season":2011,"week_ordinal":0}',
                temporal_order_source="phase4m_2011_week_by_week.csv",
                temporal_order_source_sha256=WEEK_SHA,
            )
        )


def test_disabling_the_fill_detector_opens_no_admission_path(monkeypatch):
    """The heuristic is diagnostic. Neutralising it must change nothing structural."""
    monkeypatch.setattr(cal, "refuse_default_time_of_day_fill", lambda orders: None)
    assert cal.TIME_OF_DAY_FILL_DETECTOR_IS_DIAGNOSTIC_ONLY is True
    rows = [
        _row(
            "G1",
            2006,
            "training",
            event_time="2006-09-02T12:00:00Z",
            temporal_order_basis=cal.BASIS_EXACT_GAME_DATE,
            temporal_order_key="2006-09-02",
            temporal_order_source="phase4m_2006_week_by_week.csv",
            temporal_order_source_sha256=DATE_SHA,
        )
    ]
    with pytest.raises(GovernanceBlock, match="one of the two was manufactured"):
        cal.admit_observations(rows)
    # And a row with no evidence at all is still refused with the detector off.
    with pytest.raises(GovernanceBlock, match="never fabricated"):
        cal.admit_observations([_row("G2", 2006, "training")])


@pytest.mark.parametrize(
    "basis,raw,sha",
    [
        (cal.BASIS_EXACT_GAME_DATE, "2006-09-02T12:00:00Z", DATE_SHA),
        (cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "2006-09-02T12:00:00Z", SEQ_SHA),
    ],
)
def test_a_time_of_day_may_not_ride_inside_a_coarse_ordering_value(basis, raw, sha):
    with pytest.raises(GovernanceBlock, match="default noon or midnight value"):
        cal.admit_temporal_order("G6", evidence=_evidence(basis, raw, sha=sha))


def test_a_time_of_day_may_not_ride_inside_a_named_ordering_field():
    with pytest.raises(GovernanceBlock, match="carries a time of day in game_date"):
        cal.admit_temporal_order(
            "G6",
            evidence=_evidence(
                cal.BASIS_EXACT_GAME_DATE,
                {"game_date": "2006-09-02T12:00:00Z"},
                sha=DATE_SHA,
            ),
        )


def test_an_event_time_column_filled_with_one_default_time_is_reported():
    """The detector still earns its keep on the one shape structure cannot see."""
    rows = [
        _row("G1", 2006, "training", event_time="2006-09-02T12:00:00Z"),
        _row("G2", 2006, "training", event_time="2006-09-09T12:00:00Z"),
        _row("G3", 2006, "training", event_time="2006-09-16T12:00:00Z"),
    ]
    with pytest.raises(GovernanceBlock, match="default fill value"):
        cal.admit_observations(rows)


def test_genuinely_varying_kickoff_times_are_not_mistaken_for_a_fill():
    rows = [
        _row("G1", 2025, "training", event_time="2025-09-06T12:00:00Z"),
        _row("G2", 2025, "training", event_time="2025-09-13T19:30:00Z"),
    ]
    assert len(cal.admit_observations(rows)) == 2


def test_a_declared_exact_event_time_basis_cannot_conjure_the_missing_instant():
    with pytest.raises(GovernanceBlock, match="A declared basis is not a timestamp"):
        cal.admit_temporal_order(
            "G6", evidence=_evidence(cal.BASIS_EXACT_EVENT_TIME, "2006-09-02")
        )


def test_an_exact_event_time_row_may_not_claim_a_date_other_than_its_own():
    with pytest.raises(GovernanceBlock, match="date of its event"):
        cal.admit_temporal_order(
            "G1",
            event_time="2025-09-06T19:30:00Z",
            evidence=_evidence(
                cal.BASIS_EXACT_EVENT_TIME, {"game_date": "2025-09-07"}, sha=DATE_SHA
            ),
        )


# --- G: a malformed basis fails closed ---------------------------------------


def test_an_unrecognised_temporal_order_basis_is_refused():
    with pytest.raises(GovernanceBlock, match="not one of"):
        cal.admit_temporal_order(
            "G7", evidence=_evidence("APPROXIMATE_DATE", {"game_date": "2006-09-02"})
        )


def test_a_lowercase_basis_is_not_silently_normalised():
    """An unrecognised basis is refused, not mapped onto the nearest known one."""
    with pytest.raises(GovernanceBlock, match="refused rather than mapped"):
        cal.admit_temporal_order(
            "G7", evidence=_evidence("governed_source_sequence", {"sequence": 54})
        )


def test_a_malformed_ordinal_for_a_valid_basis_is_refused():
    with pytest.raises(GovernanceBlock, match="expected a non-negative integer"):
        cal.admit_temporal_order(
            "G7", evidence=_evidence(cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "row_412")
        )


# --- H: a missing source fails closed ----------------------------------------


def test_alternate_ordering_without_a_named_source_is_refused():
    with pytest.raises(GovernanceBlock, match="names no temporal_order_source"):
        cal.admit_temporal_order(
            "G8",
            evidence=_evidence(
                cal.BASIS_GOVERNED_SOURCE_SEQUENCE, {"sequence": 54}, source=" "
            ),
        )


def test_a_row_carrying_partial_temporal_provenance_is_refused():
    row = _row(
        "G8",
        2006,
        "training",
        temporal_order_basis=cal.BASIS_GOVERNED_SOURCE_SEQUENCE,
        temporal_order_key="54",
        temporal_order_source_sha256=SEQ_SHA,
    )
    with pytest.raises(GovernanceBlock, match="partial governed temporal provenance"):
        cal.admit_observation_temporal_order(row)


def test_a_dataset_carrying_partial_temporal_provenance_is_refused_at_registration(tmp_path):
    header = HEADER + ",temporal_order_basis,temporal_order_key"
    row = ROW.rstrip("\n") + ",GOVERNED_SOURCE_SEQUENCE,54\n"
    dataset = _write(tmp_path, "partial.csv", header + "\n" + row)
    with pytest.raises(GovernanceBlock, match="partial governed temporal provenance"):
        cal.register_dataset(dataset, "DS")


# --- I: a missing or invalid source digest fails closed ----------------------


def test_alternate_ordering_without_a_source_digest_is_refused():
    with pytest.raises(GovernanceBlock, match="not a 64-character lowercase SHA-256"):
        cal.admit_temporal_order(
            "G9",
            evidence=_evidence(cal.BASIS_GOVERNED_SOURCE_SEQUENCE, {"sequence": 54}, sha=""),
        )


def test_a_malformed_digest_is_refused_beside_an_authentic_timestamp_too():
    """The same field is validated on both paths, or it is relied on for nothing."""
    with pytest.raises(GovernanceBlock, match="not a 64-character lowercase SHA-256"):
        cal.admit_temporal_order(
            "G9",
            event_time="2025-09-06T19:30:00Z",
            evidence=_evidence(cal.BASIS_EXACT_EVENT_TIME, "", sha="deadbeef"),
        )


def test_alternate_ordering_with_a_malformed_source_digest_is_refused():
    for digest in ("deadbeef", "Z" * 64, "A" * 63):
        with pytest.raises(GovernanceBlock, match="cannot be re-checked"):
            cal.admit_temporal_order(
                "G9",
                evidence=_evidence(
                    cal.BASIS_GOVERNED_SOURCE_SEQUENCE, {"sequence": 54}, sha=digest
                ),
            )


# --- J: random split assignment remains refused ------------------------------


def test_random_split_assignment_is_refused():
    for method in ("RANDOM", "random_split", "KFOLD", "stratified_random", "bootstrap"):
        with pytest.raises(GovernanceBlock, match="is refused"):
            cal.require_temporal_split_assignment(method)


def test_an_unrecognised_split_assignment_is_not_assumed_temporal():
    with pytest.raises(GovernanceBlock, match="refused rather than assumed temporal"):
        cal.require_temporal_split_assignment("BY_CONFERENCE")


def test_the_only_admissible_split_assignment_is_temporal():
    assert cal.require_temporal_split_assignment("TEMPORAL_ONLY") == "TEMPORAL_ONLY"
    assert cal.temporal_order_governance_as_dict()["random_split_permitted"] is False


# --- K: temporal overlap between the partitions remains refused --------------


def _partition(rows):
    return cal.partition_observations(rows)


def _sequence_row(game_id, season, split, ordinal, source="phase4m_2006.csv", sha=SEQ_SHA):
    return _row(
        game_id,
        season,
        split,
        temporal_order_basis=cal.BASIS_GOVERNED_SOURCE_SEQUENCE,
        temporal_order_key=str(ordinal),
        temporal_order_source=source,
        temporal_order_source_sha256=sha,
    )


def _date_row(game_id, season, split, date, source="phase4m_dates.csv", sha=DATE_SHA):
    return _row(
        game_id,
        season,
        split,
        temporal_order_basis=cal.BASIS_EXACT_GAME_DATE,
        temporal_order_key=date,
        temporal_order_source=source,
        temporal_order_source_sha256=sha,
    )


def _week_row(game_id, season, split, week, source="phase4m_weeks.csv", sha=WEEK_SHA):
    return _row(
        game_id,
        season,
        split,
        temporal_order_basis=cal.BASIS_WEEK_STAGE_DATE,
        temporal_order_key=cal.TemporalOrderValue(
            season=season, week_ordinal=week, week_label=str(week)
        ).canonical(),
        temporal_order_source=source,
        temporal_order_source_sha256=sha,
    )


def test_a_forward_only_partition_of_mixed_granularities_passes():
    """2006 by source sequence, 2019 by date, 2025 by authentic kickoff time."""
    report = cal.require_governed_temporal_split_integrity(
        _partition(
            [
                _sequence_row("G1", 2006, "training", 1),
                _sequence_row("G2", 2006, "training", 2),
                _date_row("G3", 2019, "validation", "2019-11-30"),
                _row("G4", 2025, "holdout", event_time="2025-09-06T19:30:00Z"),
            ]
        )
    )
    assert report["leak_free"] is True
    assert report["assignment"] == "TEMPORAL_ONLY"
    assert report["splits"] == {"training": 2, "validation": 1, "holdout": 1}
    assert report["fabricated_timestamps"] == 0
    assert report["observations_with_authentic_event_time"] == 1
    assert report["observations_on_governed_temporal_order"] == 3
    assert report["holdout_use"] == "SCORED_ONCE_AT_THE_END_NEVER_FOR_SELECTION"


def test_the_whole_season_2006_2011_to_2024_to_2025_partition_is_representable():
    """The structural shape the corpus would be split into. Not a policy claim.

    Nothing here is promoted, no coefficient is scored and no adapter is built.
    The only assertion is that the successor contract can *represent* a
    forward-only whole-season partition whose training half mixes all three
    kinds of historical evidence, including seasons that carry no date at all.
    """
    rows = [
        # 2006-2007: canonical source-row sequence only.
        _sequence_row("G2006_P1731", 2006, "training", 1, source="phase4m_2006.csv"),
        _sequence_row("G2006_P1784", 2006, "training", 54, source="phase4m_2006.csv"),
        _sequence_row("G2007_P0100", 2007, "training", 100, source="phase4m_2007.csv"),
        # 2008-2010: week resolved, date not.
        _week_row("G2008_P0004", 2008, "training", 1),
        _week_row("G2009_P0210", 2009, "training", 6),
        _week_row("G2010_P0480", 2010, "training", 11),
        # 2011: dates resolved.
        _date_row("G2011_P2885", 2011, "training", "2011-08-28"),
        _date_row("G2011_P3000", 2011, "training", "2011-12-03"),
        # 2024 validation: dated regular season plus an undated championship row.
        _date_row("T031vT026", 2024, "validation", "2024-08-24"),
        _date_row("T060vT083", 2024, "validation", "2024-11-30"),
        _sequence_row("CCG_SEC", 2024, "validation", 710, source="event_stream_2024.csv"),
        # 2025 holdout: same shapes, one season later.
        _date_row("T012vT044", 2025, "holdout", "2025-08-30"),
        _date_row("T077vT002", 2025, "holdout", "2025-11-29"),
        _sequence_row("CCG_B1G_25", 2025, "holdout", 1420, source="event_stream_2025.csv"),
    ]
    report = cal.require_governed_temporal_split_integrity(_partition(rows))
    assert report["leak_free"] is True
    assert report["splits"] == {"training": 8, "validation": 3, "holdout": 3}
    assert report["season_ranges"] == {
        "training": (2006, 2011),
        "validation": (2024, 2024),
        "holdout": (2025, 2025),
    }
    assert report["observations_with_authentic_event_time"] == 0
    assert report["observations_on_governed_temporal_order"] == 14
    assert report["fabricated_timestamps"] == 0
    assert report["temporal_bases"] == {
        "EXACT_EVENT_TIME": 0,
        "EXACT_GAME_DATE": 6,
        "WEEK_STAGE_DATE": 3,
        "GOVERNED_SOURCE_SEQUENCE": 5,
    }
    # Six distinct ordering domains, and not one of them straddles a boundary in
    # a way that had to be assumed.
    assert len(report["ordering_domains"]) == 6


def test_a_holdout_that_precedes_training_in_source_sequence_is_refused():
    with pytest.raises(GovernanceBlock, match="not provably forward-only"):
        cal.require_governed_temporal_split_integrity(
            _partition(
                [
                    _sequence_row("G1", 2006, "training", 900),
                    _sequence_row("G2", 2006, "validation", 500),
                    _sequence_row("G3", 2006, "holdout", 100),
                ]
            )
        )


def test_a_holdout_week_that_precedes_a_training_week_is_refused():
    with pytest.raises(GovernanceBlock, match="not provably forward-only"):
        cal.require_governed_temporal_split_integrity(
            _partition(
                [
                    _week_row("G1", 2009, "training", 12),
                    _week_row("G2", 2009, "validation", 8),
                    _week_row("G3", 2009, "holdout", 3),
                ]
            )
        )


def test_same_day_ordering_is_not_claimed_under_day_granularity():
    """Two games on one date. Nothing in the evidence orders them."""
    with pytest.raises(GovernanceBlock, match="same-day ordering is not proven"):
        cal.require_governed_temporal_split_integrity(
            _partition(
                [
                    _date_row("G1", 2019, "training", "2019-09-07"),
                    _date_row("G2", 2019, "validation", "2019-11-30"),
                    _date_row("G3", 2019, "holdout", "2019-11-30"),
                ]
            )
        )


def test_an_unprovable_cross_domain_boundary_is_refused_rather_than_assumed():
    """A source-row ordinal and a calendar date are not comparable quantities."""
    with pytest.raises(GovernanceBlock, match="different ordering domains"):
        cal.require_governed_temporal_split_integrity(
            _partition(
                [
                    _sequence_row("G1", 2006, "training", 1),
                    _date_row("G2", 2006, "validation", "2006-11-30"),
                    _date_row("G3", 2007, "holdout", "2007-11-30"),
                ]
            )
        )


def test_an_unpopulated_split_is_still_refused_under_the_successor():
    with pytest.raises(GovernanceBlock, match="populated"):
        cal.require_governed_temporal_split_integrity(
            _partition(
                [
                    _sequence_row("G1", 2006, "training", 1),
                    _sequence_row("G2", 2006, "holdout", 2),
                ]
            )
        )


def test_a_repeated_game_id_cannot_hide_one_of_its_split_assignments():
    """Split assignment is keyed by game_id; a repeat would collapse silently."""
    with pytest.raises(GovernanceBlock, match="repeat a game_id"):
        cal.require_governed_temporal_split_integrity(
            _partition(
                [
                    _sequence_row("G1", 2006, "training", 1),
                    _sequence_row("G1", 2006, "holdout", 900),
                    _sequence_row("G2", 2006, "validation", 500),
                ]
            )
        )


def test_an_unknown_split_label_is_still_refused_under_the_successor():
    with pytest.raises(InputValidationError, match="expected one of"):
        cal.require_governed_temporal_split_integrity(
            _partition([_sequence_row("G1", 2006, "shuffled", 1)])
        )


# --- L: the holdout may not be used for selection ----------------------------


def test_the_holdout_may_not_be_read_for_regime_selection():
    with pytest.raises(GovernanceBlock, match="may not be read for regime selection"):
        cal.require_selection_split("holdout")


def test_the_holdout_may_not_be_read_for_a_hyperparameter_search():
    with pytest.raises(GovernanceBlock, match="SCORED_ONCE_AT_THE_END"):
        cal.require_selection_split("holdout", purpose="hyperparameter search")


def test_selection_reads_validation_and_not_training():
    assert cal.require_selection_split("validation") == "validation"
    with pytest.raises(GovernanceBlock, match="Training scores are in-sample"):
        cal.require_selection_split("training")


def test_the_governed_ranking_still_refuses_to_compare_across_splits_of_any_kind():
    records = [_record("E1", 11.0, split="validation"), _record("E2", 12.0, split="holdout")]
    with pytest.raises(GovernanceBlock, match="mixed splits"):
        cal.rank_experiments_governed(records, cal.PRIMARY_OBJECTIVE)


# --- M: source-sequence rows sort deterministically, and stay non-temporal ----


def test_source_sequence_rows_sort_by_their_supplied_governed_order():
    orders = [
        cal.admit_temporal_order(
            f"G{n}", evidence=_evidence(cal.BASIS_GOVERNED_SOURCE_SEQUENCE, key)
        )
        for n, key in ((3, "30"), (1, "10"), (2, "20"))
    ]
    assert [o.game_id for o in cal.governed_temporal_order(orders)] == ["G1", "G2", "G3"]
    # Deterministic: the same input in a different arrival order sorts the same.
    assert [o.game_id for o in cal.governed_temporal_order(reversed(orders))] == [
        "G1",
        "G2",
        "G3",
    ]


def test_two_source_sequences_from_different_sources_do_not_interleave():
    a = cal.admit_temporal_order(
        "A1",
        evidence=_evidence(
            cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "900", "phase4m_2006.csv", SEQ_SHA
        ),
    )
    b = cal.admit_temporal_order(
        "B1",
        evidence=_evidence(
            cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "100", "phase4m_2007.csv", WEEK_SHA
        ),
    )
    assert a.domain != b.domain
    # Ordinal 100 does not sort ahead of ordinal 900 across two unrelated sources;
    # each domain stays whole, because the two orders are not comparable.
    grouped = cal.governed_temporal_order([a, b])
    assert [o.domain for o in grouped] == sorted({a.domain, b.domain})


def test_a_source_sequence_never_serialises_as_a_timestamp():
    order = cal.admit_temporal_order(
        "G4", evidence=_evidence(cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "412")
    )
    payload = order.as_dict()
    assert payload["event_time"] is None
    assert payload["event_time_is_authentic"] is False
    assert payload["inferred_kickoff_time"] is None
    assert payload["serialized_as_timestamp"] is False
    assert payload["temporal_order_value"] == {"sequence": 412}
    # No value anywhere in the record is shaped like an instant or a date.
    flat = json.dumps(payload)
    assert not cal._TIME_OF_DAY_RE.search(flat)
    assert not cal._DATE_RE.search(flat)


def test_an_authentic_timestamp_still_serialises_as_itself():
    payload = cal.admit_temporal_order("G1", event_time="2025-09-06T19:30:00Z").as_dict()
    assert payload["event_time"] == "2025-09-06T19:30:00Z"
    assert payload["event_time_is_authentic"] is True
    assert payload["serialized_as_timestamp"] is True


# --- R2: no executable path bypasses row admission ---------------------------


def test_the_gate_admits_a_conforming_dataset_and_reports_its_partition(tmp_path):
    dataset = cal.register_dataset(_admissible_dataset(tmp_path), "DS-OK")
    admitted = cal.load_admitted_observations(dataset)
    assert admitted.dataset_sha256 == dataset.sha256
    assert admitted.admission_gate == "calibration.load_admitted_observations"
    assert len(admitted.observations) == 4
    assert admitted.split_report["leak_free"] is True
    assert [o.game_id for o in admitted.split("holdout")] == ["G4"]
    assert cal.require_admitted_observations(admitted) is admitted


def test_a_row_without_chronology_cannot_reach_executable_calibration_use(tmp_path):
    """The regression the audit asked for: registration passes, execution does not."""
    orphan = (
        "G5,2024,1,ARK,GAST,3.5,7,2026-01-01T00:00:00Z,2026-01-02T00:00:00Z,"
        "validation,,,,"
    )
    dataset = cal.register_dataset(
        _admissible_dataset(tmp_path, "orphan.csv", extra_rows=(orphan,)), "DS-ORPHAN"
    )
    # Registration is shape and identity only, and it accepted the file.
    assert dataset.rows == 5
    # Execution is where the missing chronology is caught, and there is no
    # supported route around it.
    with pytest.raises(GovernanceBlock, match="never fabricated"):
        cal.load_admitted_observations(dataset)


def test_a_canonical_ordering_value_survives_a_csv_round_trip(tmp_path):
    """The value has to be usable in the format the contract itself admits."""
    import csv as _csv

    path = tmp_path / "quoted.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = _csv.writer(fh)
        writer.writerow(TEMPORAL_HEADER.split(","))
        for game_id, season, split, value in (
            ("G1", 2008, "training", cal.TemporalOrderValue(season=2008, week_ordinal=1)),
            ("G2", 2009, "validation", cal.TemporalOrderValue(season=2009, week_ordinal=4)),
            ("G3", 2010, "holdout", cal.TemporalOrderValue(season=2010, week_ordinal=9)),
        ):
            writer.writerow(
                [
                    game_id, season, 1, "ARK", "GAST", 3.5, 7,
                    "2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", split,
                    cal.BASIS_WEEK_STAGE_DATE, value.canonical(), "phase4m.csv", WEEK_SHA,
                ]
            )
    admitted = cal.load_admitted_observations(cal.register_dataset(path, "DS-Q"))
    assert [o.order.value.week_ordinal for o in admitted.observations] == [1, 4, 9]
    assert all(o.order.calendar_date is None for o in admitted.observations)


def test_the_admission_gate_reads_the_format_registration_parsed(tmp_path):
    """A declared format overrides the suffix, and the gate must not re-guess."""
    path = tmp_path / "observations.dat"
    rows = [
        _observation("G1", 2006, "training", cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "1"),
        _observation("G3", 2024, "validation", cal.BASIS_EXACT_GAME_DATE, "2024-11-30", sha=DATE_SHA),
        _observation("G4", 2025, "holdout", cal.BASIS_EXACT_GAME_DATE, "2025-11-29", sha=DATE_SHA),
    ]
    text = (TEMPORAL_HEADER + "\n" + "\n".join(rows) + "\n").replace(",", "\t")
    path.write_text(text.replace('"', ""), encoding="utf-8")
    dataset = cal.register_dataset(path, "DS-TSV", fmt="tsv")
    assert dataset.fmt == "tsv"
    assert len(cal.load_admitted_observations(dataset).observations) == 3


def test_an_issued_receipt_does_not_hand_out_the_token_that_made_it(tmp_path):
    admitted = cal.load_admitted_observations(
        cal.register_dataset(_admissible_dataset(tmp_path), "DS-OK")
    )
    assert admitted.token is None
    with pytest.raises(GovernanceBlock, match="may only be constructed by"):
        cal.AdmittedObservationSet(
            dataset_id="DS",
            dataset_sha256="0" * 64,
            observations=admitted.observations,
            split_report={},
            token=admitted.token,
        )


def test_a_registered_dataset_is_not_an_admitted_one(tmp_path):
    dataset = cal.register_dataset(_admissible_dataset(tmp_path), "DS-OK")
    with pytest.raises(GovernanceBlock, match="registered, not admitted"):
        cal.require_admitted_observations(dataset)


def test_executable_use_refuses_anything_that_is_not_an_admitted_set():
    for candidate in ([], {"observations": []}, None, "DS"):
        with pytest.raises(GovernanceBlock, match="requires an AdmittedObservationSet"):
            cal.require_admitted_observations(candidate)


def test_an_admitted_observation_set_cannot_be_forged():
    """The type is the receipt, so it must not be constructible without the gate."""
    with pytest.raises(GovernanceBlock, match="may only be constructed by"):
        cal.AdmittedObservationSet(
            dataset_id="DS", dataset_sha256="0" * 64, observations=(), split_report={}
        )


def test_no_public_function_returns_raw_rows_from_a_registered_dataset():
    """The row reader is module-private on purpose; a public one would be the bypass."""
    public = [
        name
        for name in dir(cal)
        if not name.startswith("_") and callable(getattr(cal, name))
    ]
    for name in public:
        assert "observation_rows" not in name, name
    assert hasattr(cal, "_observation_rows")


def test_the_gate_refuses_a_dataset_whose_bytes_changed_after_registration(tmp_path):
    path = _admissible_dataset(tmp_path, "mutated.csv")
    dataset = cal.register_dataset(path, "DS-MUT")
    path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="bytes changed after registration"):
        cal.load_admitted_observations(dataset)


def test_the_gate_refuses_a_dataset_that_declares_no_partition(tmp_path):
    header = HEADER + ",temporal_order_basis,temporal_order_key,temporal_order_source,temporal_order_source_sha256"
    row = ROW.rstrip("\n") + f",GOVERNED_SOURCE_SEQUENCE,1,corpus.csv,{SEQ_SHA}\n"
    dataset = cal.register_dataset(
        _write(tmp_path, "nosplit.csv", header + "\n" + row), "DS-NOSPLIT"
    )
    with pytest.raises(GovernanceBlock, match="missing \\['split'\\]"):
        cal.load_admitted_observations(dataset)


# --- promotion binding terminates the admission chain ------------------------
#
# The chain the audit required, and where each link is proven:
#
#   registered source            register_dataset
#   digest verified              load_admitted_observations / _require_digest_continuity
#   rows temporally admitted     admit_observation_temporal_order
#   partition proven forward-only  require_governed_temporal_split_integrity
#   calibration result           ExperimentRecord
#   promotion evidence binding   bind_promotion_evidence
#
# There is no supported route from the first link to the last that skips the
# middle three.


def _experiment(dataset, *, regime_id="R1", value=11.3):
    return cal.ExperimentRecord(
        experiment_id="E9", model_version="m", configuration_version="c", seed=1,
        regime_id=regime_id, candidate_values={}, dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256, objective_id="O", run_timestamp="t",
        metrics={cal.PRIMARY_CALIBRATION_METRIC: value}, v2_1_control_comparison={},
        split="holdout",
    )


def _promote(regime, dataset, experiment, *, evidence=None, **kwargs):
    return cal.promote_regime_r2(
        regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
        approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
        evidence=evidence or {cal.PRIMARY_CALIBRATION_METRIC: 11.3, "split": "holdout"},
        experiment=experiment, dataset=dataset, **kwargs,
    )


def test_registered_but_unadmitted_observations_cannot_bind_promotion_evidence(tmp_path):
    """1. The headline invariant: registration is not admission, and it never was."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    with pytest.raises(GovernanceBlock, match="registered but not admitted"):
        _promote(regime, dataset, _experiment(dataset))


def test_a_dataset_that_could_never_be_admitted_cannot_bind_either(tmp_path):
    """The pre-successor fixture shape, refused at both ends of the chain."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    legacy = cal.register_dataset(
        _write(tmp_path, "legacy.csv", HEADER + "\n" + ROW), "DS-LEGACY"
    )
    # It cannot reach admission at all: it declares no partition, and its rows
    # carry neither a kickoff time nor governed temporal evidence.
    with pytest.raises(GovernanceBlock, match="cannot be admitted for execution"):
        cal.load_admitted_observations(legacy)
    with pytest.raises(GovernanceBlock, match="registered but not admitted"):
        _promote(regime, legacy, _experiment(legacy))


def test_a_bare_dataset_is_not_an_admission_receipt(tmp_path):
    """2. Handing the registration object where the receipt belongs is refused."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    with pytest.raises(GovernanceBlock, match="registered, not admitted"):
        _promote(regime, dataset, _experiment(dataset), observations=dataset)


@pytest.mark.parametrize("forgery", [True, {"admitted": True}, 4, "ADMITTED"])
def test_no_stand_in_object_can_pass_for_an_admission_receipt(tmp_path, forgery):
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    with pytest.raises(GovernanceBlock, match="requires an AdmittedObservationSet"):
        _promote(regime, dataset, _experiment(dataset), observations=forgery)


@pytest.mark.parametrize("key", cal.ADMISSION_ASSERTION_KEYS)
def test_a_caller_boolean_cannot_substitute_for_an_admission_receipt(tmp_path, key):
    """3. Asserting admission in the evidence payload is refused outright."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    with pytest.raises(GovernanceBlock, match="asserts .* in its own"):
        _promote(
            regime,
            dataset,
            _experiment(dataset),
            evidence={
                cal.PRIMARY_CALIBRATION_METRIC: 11.3,
                "split": "holdout",
                key: True,
            },
        )


def test_admission_is_reported_only_by_the_binding_never_by_the_caller(tmp_path):
    """The record's admission fields are outputs of the gate, not inputs to it."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
    record = _promote(
        regime,
        dataset,
        _experiment(dataset),
        observations=cal.load_admitted_observations(dataset),
    )
    for key in cal.ADMISSION_ASSERTION_KEYS:
        assert key not in record["evidence"]
    assert record["observations_admitted"] is True
    assert record["promotion_eligible"] is True


def test_admitted_observations_bind_promotion_evidence_normally(tmp_path):
    """4. The whole chain, walked once, in order."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = cal.register_dataset(_admissible_dataset(tmp_path), "DS-B")
    admitted = cal.load_admitted_observations(dataset)
    assert admitted.dataset_sha256 == dataset.sha256
    assert admitted.split_report["leak_free"] is True
    record = _promote(regime, dataset, _experiment(dataset), observations=admitted)
    assert record["evidence_binding"] == cal.EVIDENCE_BOUND
    assert record["promotion_eligible"] is True
    assert record["admitted_observation_count"] == 4
    assert record["writes_canonical_config"] is False


def test_a_promotion_may_not_cite_admitted_observations_from_other_bytes(tmp_path):
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path, "a.csv")
    other = cal.register_dataset(
        _admissible_dataset(
            tmp_path,
            "b.csv",
            extra_rows=(
                _observation("G5", 2006, "training", cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "3"),
            ),
        ),
        "DS-OTHER",
    )
    with pytest.raises(GovernanceBlock, match="admitted observations came from"):
        _promote(
            regime,
            dataset,
            _experiment(dataset),
            observations=cal.load_admitted_observations(other),
        )


def test_a_stale_admission_receipt_cannot_bind_after_the_bytes_change(tmp_path):
    """5. Digest continuity: a receipt describes bytes, not a filename."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    path = _admissible_dataset(tmp_path, "drifting.csv")
    dataset = cal.register_dataset(path, "DS-DRIFT")
    admitted = cal.load_admitted_observations(dataset)
    experiment = _experiment(dataset)
    # The file is edited after admission. Nothing re-registers, so the receipt
    # and the registration still agree with each other and only the disk moved.
    path.write_text(
        path.read_text(encoding="utf-8")
        + _observation("G9", 2006, "training", cal.BASIS_GOVERNED_SOURCE_SEQUENCE, "9")
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(GovernanceBlock, match="bytes changed after admission"):
        _promote(regime, dataset, experiment, observations=admitted)


def test_a_receipt_with_nothing_to_bind_to_is_refused(tmp_path):
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    admitted = _admitted(tmp_path)
    with pytest.raises(GovernanceBlock, match="attaches to nothing"):
        cal.promote_regime_r2(
            regime, authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
            approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
            evidence={cal.PRIMARY_CALIBRATION_METRIC: 11.3, "split": "holdout"},
            observations=admitted,
        )


def test_the_unbound_path_survives_and_is_explicitly_not_promotable():
    """Compatibility, but only for the path that claims nothing."""
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    record = cal.promote_regime_r2(
        regime,
        authority=cal.PROMOTION_AUTHORITY_MATHEMATICAL,
        approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RAT-999",
        evidence={cal.PRIMARY_CALIBRATION_METRIC: 0.0001, "split": "holdout"},
    )
    assert record["evidence_binding"] == cal.EVIDENCE_UNBOUND
    assert record["evidence_bound"] is False
    assert record["promotion_eligible"] is False
    assert record["observations_admitted"] is False
    assert record["admission_gate"] is None
    assert record["writes_canonical_config"] is False


def test_no_blocker_is_retired_by_the_promotion_binding_remediation():
    """7. This closes a bypass. It clears no project work."""
    assert rulings.ruling("R6-CAL-TEMPORAL-ORDER").retires == ()
    payload = contract.contract_as_dict()
    assert sorted(payload["blockers_open"]) == sorted(
        list(cal.CALIBRATION_FIELDS) + ["governance.GAME_SD_CALIBRATION_OPEN"]
    )
    assert payload["status"] == "SPECIFICATION_ONLY_NO_DATASET_MOUNTED"
    assert cal.calibration_governance_as_dict()["dataset_mounted"] is False


# --- compatibility: exact-event-time datasets are unchanged ------------------


def test_the_exact_event_time_split_gate_still_passes_a_valid_partition():
    report = cal.require_temporal_split_integrity(
        {
            "G1": ("training", "2023-09-02T00:00:00Z"),
            "G2": ("validation", "2024-09-07T00:00:00Z"),
            "G3": ("holdout", "2025-09-06T00:00:00Z"),
        }
    )
    assert report["leak_free"] is True
    assert report["assignment"] == "TEMPORAL_ONLY"


def test_the_exact_event_time_gate_now_refuses_a_value_the_successor_would():
    """Both gates run the same admission, so neither can admit what the other won't."""
    with pytest.raises(GovernanceBlock, match="not a well-formed ISO-8601 instant"):
        cal.require_temporal_split_integrity(
            {
                "G1": ("training", "2023-09-02"),
                "G2": ("validation", "2024-09-07T00:00:00Z"),
                "G3": ("holdout", "2025-09-06T00:00:00Z"),
            }
        )


def test_an_exact_event_time_dataset_still_registers(tmp_path):
    header = HEADER + ",event_time"
    row = ROW.rstrip("\n") + ",2025-08-30T19:00:00Z\n"
    registered = cal.register_dataset(_write(tmp_path, "exact.csv", header + "\n" + row), "DS")
    assert registered.rows == 1
    assert "event_time" in registered.columns


def test_a_dataset_carrying_all_four_temporal_columns_registers(tmp_path):
    header = HEADER + "," + ",".join(cal.TEMPORAL_ORDER_PROVENANCE_COLUMNS)
    row = ROW.rstrip("\n") + f",GOVERNED_SOURCE_SEQUENCE,54,corpus_2006.csv,{SEQ_SHA}\n"
    registered = cal.register_dataset(_write(tmp_path, "full.csv", header + "\n" + row), "DS")
    assert registered.rows == 1


def test_event_time_is_conditional_and_not_globally_optional():
    field = next(f for f in contract.REQUIRED_CONTRACT_FIELDS if f.name == "event_time")
    assert field.required is False
    assert field.conditional_requirement
    assert "MUST remain null" in field.conditional_requirement
    policy = contract.TEMPORAL_ORDER_POLICY
    assert policy["event_time_globally_optional"] is False
    assert policy["event_time_authoritative_where_it_exists"] is True
    assert policy["event_time_when_source_recorded_none"] == "MUST_REMAIN_NULL"
    assert policy["synthetic_time_of_day_permitted"] is False
    assert policy["missing_chronology_may_be_fabricated_to_pass_admission"] is False


def test_the_contract_states_that_the_value_is_named_fields_not_a_grammar():
    policy = contract.TEMPORAL_ORDER_POLICY
    assert policy["value_representation"] == "NAMED_FIELDS_CANONICAL_JSON"
    assert policy["positional_packed_key_grammar_permitted"] is False
    assert policy["stage_and_week_labels_parsed_for_ordering"] is False
    assert policy["value_fields"] == list(cal.TEMPORAL_ORDER_VALUE_FIELDS)
    assert policy["anti_fabrication_is_structural"] is True
    assert policy["time_of_day_fill_detector_is_diagnostic_only"] is True
    assert policy["executable_use_requires_admission"] is True
    assert policy["admission_gate"] == "calibration.load_admitted_observations"


def test_every_conditionally_required_field_states_its_condition():
    for f in contract.REQUIRED_CONTRACT_FIELDS:
        if not f.required:
            assert f.conditional_requirement, f.name
            assert "REQUIRED" in f.conditional_requirement


def test_the_four_temporal_provenance_fields_are_admitted_by_the_ruling():
    admitted = {c.lower() for c in cal.CALIBRATION_OBSERVATION_COLUMNS}
    for column in cal.TEMPORAL_ORDER_PROVENANCE_COLUMNS:
        assert column in admitted
    # Admitting these did not widen the allowlist for the fields still awaiting
    # their own ruling.
    assert contract.unadmitted_required_fields() == sorted(
        f.name for f in contract.FIELDS_REQUIRING_ADMISSION_RULING
    )


# --- the successor is recorded as a ruling, with its issued authority --------


def test_the_successor_ruling_is_recorded_with_its_exact_approval_token():
    ruling = rulings.ruling("R6-CAL-TEMPORAL-ORDER")
    assert ruling.approval_token == "APPROVE_V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1"
    assert ruling.chairman_ruling_id == "V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1"
    assert ruling.resolution_reason == "SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY"
    assert ruling.provenance == "FACT"
    assert ruling in rulings.ALL_RULINGS
    assert cal.TEMPORAL_ORDER_APPROVAL_TOKEN == ruling.approval_token
    assert cal.TEMPORAL_ORDER_RULING_ID == ruling.chairman_ruling_id


def test_the_successor_ruling_retires_no_blocker():
    assert rulings.ruling("R6-CAL-TEMPORAL-ORDER").retires == ()
    assert "R6-CAL-TEMPORAL-ORDER" not in rulings.retirable_blockers().values()


def test_the_approval_token_field_leaves_every_historical_ruling_unchanged():
    """The new field is additive and optional; the old records still read as before."""
    historical = rulings.R2_RULINGS + rulings.R3_RULINGS + rulings.R4_RULINGS
    for ruling in historical:
        assert ruling.approval_token is None
        payload = ruling.as_dict()
        assert payload["approval_token"] is None
        # Every key the record carried before is present and unchanged in value.
        legacy = {k: v for k, v in payload.items() if k != "approval_token"}
        assert set(legacy) == {
            "convergence_id",
            "chairman_ruling_id",
            "subject",
            "decision",
            "evidence",
            "retires",
            "supersedes",
            "provenance",
            "instruction",
            "resolution_reason",
        }
        assert legacy["decision"] == ruling.decision
        assert legacy["retires"] == list(ruling.retires)
    # Constructing a historical-style ruling without the field still works.
    assert rulings.ChairmanRuling("X-1", "s", "d").approval_token is None


def test_the_historical_r4_status_artifact_was_not_rewritten():
    """The additive field is why its embedded ruling record has no approval_token."""
    status = json.loads((REFERENCE / "V3_GOVERNANCE_STATUS_R4.json").read_text("utf-8"))
    recorded = status["chairman_rulings"][0]
    assert recorded["convergence_id"] == "R4-COMMON-OPP-FORMULA"
    assert "approval_token" not in recorded
    assert status["chairman_ruling_ids_supplied"] is False


def test_the_successor_status_artifact_records_what_it_did_not_change():
    status = json.loads(SUCCESSOR_STATUS.read_text(encoding="utf-8"))
    assert status["approval_token"] == "APPROVE_V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1"
    assert status["ruling_id"] == "V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1"
    assert status["live_blocker_count"] == 8
    assert status["resolved_blockers"] == []
    assert status["opened_blockers"] == []
    assert status["simulation_run"] is False
    assert status["calibration_values_promoted"] == []
    assert status["historical_status_records_rewritten"] is False
    assert status["fabricated_timestamps_permitted"] is False
    binding = status["audit_remediation_final_promotion_binding"]
    assert binding["bare_dataset_accepted_as_receipt"] is False
    assert binding["caller_asserted_admission_permitted"] is False
    assert binding["digest_continuity_checked_at_binding"] is True
    assert binding["blockers_retired_by_this_remediation"] == []
    assert binding["executable_chain"][0] == "registered source"
    assert binding["executable_chain"][-1] == "promotion evidence binding"
    assert set(status["live_blockers"]) == {
        "calibration.blowout_treatment",
        "calibration.game_sd_points",
        "calibration.recent_form_weights",
        "calibration.sample_size_regularization",
        "calibration.weekly_movement_cap_points",
        "calibration.weekly_performance_residual_coefficient",
        "governance.GAME_SD_CALIBRATION_OPEN",
        "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
    }


def test_the_preserved_governance_positions_did_not_move():
    governance = cal.calibration_governance_as_dict()
    assert governance["primary_metric"] == "out_of_sample_baxter_rating_rmse"
    assert governance["independent_witnesses"] == ["colley_matrix", "srs"]
    assert governance["weighted_composite_authorised"] is False
    assert governance["legacy_margin_sd_20_2_promotable"] is False
    assert governance["dataset_mounted"] is False
    assert governance["synthetic_calibration_data_admissible"] is False
    assert governance["temporal_order"]["synthetic_time_of_day_permitted"] is False
    # FLOW / public-money columns are still refused, temporal successor or not.
    assert "public_money" in cal.FORBIDDEN_SIGNAL_PATTERNS


def test_the_reissued_contract_records_its_revision_and_what_it_superseded():
    payload = contract.contract_as_dict()
    assert payload["contract_id"] == "V3-CALIBRATION-DATA-CONTRACT-001"
    assert payload["contract_revision"] == "R1-TEMPORAL-ORDER-SUCCESSOR"
    assert "event_time was unconditionally required" in payload["contract_revision_supersedes"]
    assert payload["temporal_order_policy"]["precedence"] == [
        "EXACT_EVENT_TIME",
        "EXACT_GAME_DATE",
        "WEEK_STAGE_DATE",
        "GOVERNED_SOURCE_SEQUENCE",
    ]
    assert payload["split_policy"]["holdout_selection_use_permitted"] is False
    assert payload["split_policy"]["random_assignment_permitted"] is False


def test_the_issued_contract_artifact_matches_the_module(tmp_path):
    """The committed artifact is the module's own output, not a hand-edited copy."""
    regenerated = json.loads(
        contract.write_contract(tmp_path / "contract.json").read_text(encoding="utf-8")
    )
    assert regenerated == json.loads(CONTRACT_ARTIFACT.read_text(encoding="utf-8"))
