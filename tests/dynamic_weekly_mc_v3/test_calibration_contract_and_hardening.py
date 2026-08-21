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
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

ROOT = Path(__file__).resolve().parents[2]

HEADER = (
    "game_id,season,week,team,opponent,expected_margin,actual_margin,observed_at,recorded_at"
)
ROW = "G1,2025,1,ARK,GAST,3.5,7,2025-08-30T00:00:00Z,2025-08-31T00:00:00Z\n"


def _write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


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


def _dataset(tmp_path) -> cal.CalibrationDataset:
    return cal.register_dataset(_write(tmp_path, "bound.csv", HEADER + "\n" + ROW), "DS-B")


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
    regime = cal.CandidateRegime("R1", {"game_sd_points": 17.0}, "probe")
    dataset = _dataset(tmp_path)
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
        experiment=measured, dataset=dataset,
    )
    assert record["evidence_bound"] is True
    assert record["evidence_binding"] == cal.EVIDENCE_BOUND
    assert record["bound_dataset_sha256"] == dataset.sha256
    assert record["measured_primary_metric"] == 11.3
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
