import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock, InputValidationError

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
EXPERIMENTAL = ROOT / "config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json"


def _regime(regime_id="R1", **values):
    return cal.CandidateRegime(regime_id=regime_id, values=values or {"game_sd_points": 17.0}, rationale="test")


def _record(experiment_id, metric_value, regime_id="R1"):
    return cal.ExperimentRecord(
        experiment_id=experiment_id,
        model_version="3.0.0-experimental-harness",
        configuration_version="V3-PLACEHOLDER-2026-08-20-001",
        seed=20260803,
        regime_id=regime_id,
        candidate_values={"game_sd_points": 17.0},
        dataset_id="DS-TEST",
        dataset_sha256="0" * 64,
        objective_id="OBJ-1",
        run_timestamp="2026-08-21T00:00:00Z",
        metrics={"brier": metric_value},
        v2_1_control_comparison={"delta_vs_control": 0.0},
    )


# --- canonical isolation ----------------------------------------------------


def test_canonical_config_calibration_values_remain_null():
    cfg = V3Config.from_json(CONFIG)
    status = cal.calibration_status(
        {name: getattr(cfg.calibration, name) for name in cal.CALIBRATION_FIELDS}
    )
    assert status["all_canonical_values_null"] is True
    assert sorted(status["unresolved_fields"]) == sorted(cal.CALIBRATION_FIELDS)
    assert status["disposition"] == "CALIBRATION_EXPERIMENT_REQUIRED"


def test_shipped_experimental_config_authors_no_candidate_values():
    """The harness ships empty: authoring coefficients would invent calibration data."""
    payload = json.loads(EXPERIMENTAL.read_text(encoding="utf-8"))
    assert payload["regimes"] == []
    assert cal.load_candidate_regimes(EXPERIMENTAL) == []


def test_regimes_cannot_be_loaded_from_the_canonical_config():
    with pytest.raises(GovernanceBlock, match="canonical"):
        cal.load_candidate_regimes(CONFIG)


def test_regimes_must_live_under_an_experimental_path(tmp_path):
    stray = tmp_path / "regimes.json"
    stray.write_text(json.dumps({"regimes": []}), encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="experimental config path"):
        cal.load_candidate_regimes(stray)


def test_regime_cannot_declare_itself_canonical():
    with pytest.raises(GovernanceBlock, match="EXPERIMENTAL"):
        cal.CandidateRegime(regime_id="R1", values={}, rationale="x", status="CANONICAL")


def test_regime_rejects_unknown_calibration_fields():
    with pytest.raises(InputValidationError, match="unknown fields"):
        cal.CandidateRegime(regime_id="R1", values={"hfa_baseline_points": 4.0}, rationale="x")


# --- promotion gate ---------------------------------------------------------


def test_promotion_requires_explicit_human_approval():
    with pytest.raises(GovernanceBlock, match="no human approval token"):
        cal.promote_regime(_regime())


def test_winning_an_evaluation_is_not_authority_to_promote():
    with pytest.raises(GovernanceBlock, match="top-ranked"):
        cal.promote_regime(_regime(), ranked_first=True)


def test_malformed_approval_token_is_rejected():
    with pytest.raises(GovernanceBlock, match="Malformed"):
        cal.promote_regime(_regime(), approval_token="yes please")


def test_approved_promotion_still_does_not_write_canonical_config():
    result = cal.promote_regime(
        _regime(), approval_token="APPROVE_V3_CALIBRATION_PROMOTION::RUL-2026-001"
    )
    assert result["writes_canonical_config"] is False
    assert result["promoted_values"] == {"game_sd_points": 17.0}


# --- objectives and ranking -------------------------------------------------


def test_no_best_regime_without_an_explicit_objective():
    with pytest.raises(GovernanceBlock, match="explicit, named objective"):
        cal.rank_experiments([_record("E1", 0.20), _record("E2", 0.18)], None)


def test_ranking_follows_the_named_objective_direction():
    objective = cal.EvaluationObjective(
        objective_id="OBJ-1", metric="brier", direction="minimize", description="calibration loss"
    )
    ranked = cal.rank_experiments([_record("E1", 0.20), _record("E2", 0.18)], objective)
    assert [r.experiment_id for r in ranked] == ["E2", "E1"]


def test_objective_direction_must_be_valid():
    with pytest.raises(InputValidationError):
        cal.EvaluationObjective(
            objective_id="OBJ-X", metric="brier", direction="sideways", description="bad"
        )


def test_ranking_rejects_experiments_missing_the_objective_metric():
    objective = cal.EvaluationObjective(
        objective_id="OBJ-1", metric="log_loss", direction="minimize", description="x"
    )
    with pytest.raises(InputValidationError, match="missing objective metric"):
        cal.rank_experiments([_record("E1", 0.2)], objective)


# --- dataset admissibility --------------------------------------------------


def test_absent_dataset_reports_blocked_on_calibration_data(tmp_path):
    with pytest.raises(GovernanceBlock, match="BLOCKED_ON_CALIBRATION_DATA"):
        cal.register_dataset(tmp_path / "missing.csv", "DS-1")


def test_public_money_is_not_admissible_as_predictive_input(tmp_path):
    dataset = tmp_path / "obs.csv"
    dataset.write_text("game_id,margin,public_money_pct\nG1,7,62\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="non-admissible"):
        cal.register_dataset(dataset, "DS-1")


def test_injury_signals_remain_deferred(tmp_path):
    dataset = tmp_path / "obs.csv"
    dataset.write_text("game_id,margin,injury_adjustment\nG1,7,-1.5\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="deferred"):
        cal.register_dataset(dataset, "DS-1")


ADMISSIBLE_HEADER = (
    "game_id,season,week,team,opponent,expected_margin,actual_margin,observed_at,recorded_at"
)
ADMISSIBLE_ROWS = (
    "G1,2026,1,ARK,GAST,3.5,7,2026-08-29T00:00:00Z,2026-08-30T00:00:00Z\n"
    "G2,2026,1,UK,VAN,-1.5,-3,2026-08-29T00:00:00Z,2026-08-30T00:00:00Z\n"
)


def test_admissible_dataset_registers_with_provenance(tmp_path):
    dataset = tmp_path / "obs.csv"
    dataset.write_text(f"{ADMISSIBLE_HEADER}\n{ADMISSIBLE_ROWS}", encoding="utf-8")
    registered = cal.register_dataset(dataset, "DS-1")
    assert registered.rows == 2
    assert registered.dataset_id == "DS-1"
    assert len(registered.sha256) == 64


# --- legacy margin SD -------------------------------------------------------


def test_legacy_margin_sd_is_recorded_but_never_approved():
    status = cal.calibration_status({name: None for name in cal.CALIBRATION_FIELDS})
    assert status["recorded_legacy_margin_sd"] == 20.2
    assert status["legacy_margin_sd_within_band"] is False
    assert status["legacy_margin_sd_approved"] is False
    assert status["open_item"] == "ENG-CAL-MARGIN"


def test_experiment_record_carries_full_provenance():
    record = _record("E1", 0.2).as_dict()
    for key in (
        "experiment_id",
        "model_version",
        "configuration_version",
        "seed",
        "candidate_values",
        "dataset_id",
        "dataset_sha256",
        "objective_id",
        "run_timestamp",
        "metrics",
        "v2_1_control_comparison",
    ):
        assert key in record
    assert record["status"] == "EXPERIMENTAL_RESULT_NOT_PROMOTED"
