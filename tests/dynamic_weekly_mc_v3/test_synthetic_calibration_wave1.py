"""Wave-1 synthetic continuity calibration: the admissions, and the two stops.

The point of these tests is that neither refusal can be quietly undone. An
evidence resolver that grows a permissive branch, an update step rearranged so
the dependency claim stops matching the code, or a field admission that widens
into the governed allowlist would each turn a stopped wave into a wave that
reports numbers. Each of those is a failure here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_contract as contract
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import synthetic_calibration_wave1 as wave
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock

REFERENCE = Path(__file__).resolve().parents[2] / "reference" / "dynamic_weekly_mc_v3"
FIELD_ADMISSIONS = REFERENCE / "V3_SYNTHETIC_CALIBRATION_FIELD_ADMISSIONS_R1.json"
WAVE1 = REFERENCE / "V3_SYNTHETIC_CALIBRATION_WAVE1_R1.json"


# --- evidence resolution -----------------------------------------------------


def test_evidence_resolution_refuses_an_absent_source() -> None:
    """No digests means no wave. There is no empty-table fallback."""
    with pytest.raises(GovernanceBlock, match="No synthetic evidence resolved"):
        wave.resolve_synthetic_evidence(None)
    with pytest.raises(GovernanceBlock, match="No synthetic evidence resolved"):
        wave.resolve_synthetic_evidence({})


def test_evidence_resolution_refuses_a_partially_pinned_source() -> None:
    """Six of seven digests is not "nearly reproducible", it is unpinned."""
    partial = {key: "0" * 64 for key in wave.REQUIRED_EVIDENCE_DIGESTS[:-1]}
    with pytest.raises(GovernanceBlock, match="not fully pinned"):
        wave.resolve_synthetic_evidence(partial)


def test_evidence_resolution_reverifies_rather_than_trusts_the_manifest() -> None:
    """The 18 reported source digests are re-checked, and their absence is drift."""
    full = {key: "0" * 64 for key in wave.REQUIRED_EVIDENCE_DIGESTS}
    with pytest.raises(GovernanceBlock, match="cannot be re-verified"):
        wave.resolve_synthetic_evidence(full)
    with pytest.raises(GovernanceBlock, match="Byte drift"):
        wave.resolve_synthetic_evidence(full, source_digests={"one": "0" * 64})
    resolved = wave.resolve_synthetic_evidence(
        full, source_digests={str(i): "0" * 64 for i in range(18)}
    )
    assert set(resolved) == set(wave.REQUIRED_EVIDENCE_DIGESTS)


def test_this_wave_resolved_nothing_and_says_so() -> None:
    """The recorded finding is an unresolved input, not a thin one."""
    assert wave.UNRESOLVED_EVIDENCE["remote_ref_present"] is False
    assert wave.UNRESOLVED_EVIDENCE["synthetic_rows_available"] == 0
    assert wave.UNRESOLVED_EVIDENCE["sibling_worktree_read"] is False
    assert all(
        wave.UNRESOLVED_EVIDENCE[key] is None for key in wave.REQUIRED_EVIDENCE_DIGESTS
    )


# --- the arithmetic dependency ----------------------------------------------


def test_the_dependency_is_read_out_of_the_update_step() -> None:
    """Both eligible families are scored through three DO_NOT_FIT families.

    This is the finding that stops the experiments even if the corpus arrives, so
    it is derived from :func:`calibration_scoring._walk_forward` rather than
    restated. If the update step is rearranged, this test changes with it instead
    of leaving a stale claim in the artifact.
    """
    report = wave.update_equation_dependencies()
    assert report["disposition"] == "STOPPED_ARITHMETIC_DEPENDENCY_ON_NON_FIT_PARAMETERS"
    assert report["non_fit_families_required"] == [
        "recent_form_weights",
        "weekly_movement_cap_points",
        "weekly_performance_residual_coefficient",
    ]
    # Both eligible families sit inside the same product, so neither escapes.
    assert report["blocks_blowout_treatment"] == report["non_fit_families_required"]
    assert report["blocks_sample_size_regularization"] == report["non_fit_families_required"]
    assert report["substitution_permitted"] is False
    # And the families this wave may fit are genuinely read there too, so the
    # equation being reported is the one the two experiments would have run in.
    for family in wave.ELIGIBLE_FAMILIES:
        assert family in report["families_read_by_update_step"]


def test_every_non_fit_family_is_named_in_the_dependency_vocabulary() -> None:
    """A family cannot be dropped from the matrix and stay invisible."""
    report = wave.update_equation_dependencies()
    for family in report["non_fit_families_required"]:
        assert family in wave.NON_FIT_FAMILIES


# --- field admissions --------------------------------------------------------


def test_admissions_are_scoped_to_one_experiment_each_and_promote_nothing() -> None:
    admitted = wave.ADMITTED_FIELDS
    assert set(admitted) == {"games_played_to_date", "game_type", "overtime_periods"}
    assert admitted["games_played_to_date"]["admitted_for"] == (
        "sample_size_regularization",
    )
    assert admitted["game_type"]["admitted_for"] == ("blowout_treatment",)
    assert admitted["overtime_periods"]["admitted_for"] == ("blowout_treatment",)
    for spec in admitted.values():
        assert spec["confers_promotion"] is False
        assert spec["restrictions"]


def test_overtime_is_postgame_and_the_other_two_are_not() -> None:
    """Ruling 3's whole content is the information class, so it is asserted."""
    assert wave.ADMITTED_FIELDS["overtime_periods"]["information_class"] == "POSTGAME"
    assert wave.ADMITTED_FIELDS["game_type"]["information_class"] == "PREGAME"
    assert wave.ADMITTED_FIELDS["games_played_to_date"]["information_class"] == "PREGAME"


def test_the_admissions_do_not_widen_the_governed_allowlist() -> None:
    """An experimental admission must stay outside canonical governance.

    The three fields are still listed by the data contract as requiring a ruling
    and are still absent from the governed allowlist. If a later change promotes
    one of them by editing the contract, this fails.
    """
    record = wave.field_admissions_record()
    assert record["canonical_governance_modified"] is False
    assert record["governed_allowlist_widened"] is False
    assert record["parameters_promoted"] == 0
    contract_record = contract.contract_as_dict()
    allowlisted = set(contract_record["governed_allowlist"])
    for name in wave.ADMITTED_FIELDS:
        assert name not in allowlisted


# --- the wave record ---------------------------------------------------------


def test_the_wave_invents_no_result_for_either_experiment() -> None:
    record = wave.wave1_record(
        execution_commit_sha="0" * 40,
        execution_tree_sha="1" * 40,
    )
    assert record["artifact_status"] == "SYNTHETIC_CALIBRATION_WAVE1_BLOCKED"
    for family in wave.ELIGIBLE_FAMILIES:
        experiment = record[family]
        assert experiment["failure_status"] == "BLOCKED"
        assert experiment["selected_candidate"] is None
        assert experiment["runner_up"] is None
        assert experiment["training_rmse"] is None
        assert experiment["evaluation_rmse"] is None
        assert experiment["identification_status"] == "UNIDENTIFIED_NO_EVIDENCE_RESOLVED"
        # The universe is still published, so a later run cannot fit a narrower
        # set and present it as the declared one.
        assert experiment["candidate_universe"]["levels"]
        assert experiment["candidate_universe"]["scored"] is False


def test_the_wave_promotes_nothing_and_runs_no_season() -> None:
    record = wave.wave1_record(
        execution_commit_sha="0" * 40,
        execution_tree_sha="1" * 40,
    )
    promotions = record["promotions"]
    assert promotions["parameters_promoted"] == 0
    assert promotions["canonical_config_written"] is False
    assert promotions["allowlist_widened"] is False
    assert promotions["blockers_retired"] == 0
    assert promotions["season_simulation_run"] is False
    assert promotions["monte_carlo_tiers_run"] == []
    assert record["primary_domain"]["real_rows_in_primary_fit"] == 0


def test_the_objective_is_rmse_and_mae_is_never_promoted_to_primary() -> None:
    """An older grid selected on average MAE; that must not leak back in."""
    record = wave.wave1_record(
        execution_commit_sha="0" * 40,
        execution_tree_sha="1" * 40,
    )
    objective = record["primary_objective"]
    assert objective["metric"] == cal.PRIMARY_CALIBRATION_METRIC
    assert objective["metric"] == "out_of_sample_baxter_rating_rmse"
    assert objective["direction"] == "minimize"
    assert objective["mae_role"] == "DIAGNOSTIC_AND_TIE_BREAK_ONLY_NEVER_PRIMARY"


def test_the_non_fit_matrix_carries_every_closed_family() -> None:
    matrix = wave.non_fit_matrix()
    assert set(matrix) == {
        "FCS_adapter",
        "game_sd_points",
        "point_scale",
        "recent_form_weights",
        "weekly_movement_cap_points",
        "weekly_performance_residual_coefficient",
    }
    assert matrix["FCS_adapter"]["disposition"] == "FCS_GAMES_MUST_FAIL_CLOSED"
    for family in wave.ELIGIBLE_FAMILIES:
        assert family not in matrix


def test_candidate_universe_refuses_a_family_this_wave_may_not_fit() -> None:
    with pytest.raises(GovernanceBlock, match="not an eligible family"):
        wave.candidate_universe("weekly_movement_cap_points")


def test_the_declared_universes_are_the_ones_the_orchestrator_declared() -> None:
    blowout = wave.candidate_universe("blowout_treatment")
    regularization = wave.candidate_universe("sample_size_regularization")
    assert blowout["level_count"] == 4
    assert regularization["level_count"] == 3
    assert {level["policy_id"] for level in blowout["levels"]} == {
        "NO_SPECIAL_TREATMENT",
        "RESIDUAL_CLIP",
        "SMOOTH_SATURATION",
    }
    assert {level["policy_id"] for level in regularization["levels"]} == {
        "NONE",
        "GAMES_PLAYED_SHRINKAGE",
    }


# --- committed artifacts -----------------------------------------------------


def test_field_admissions_artifact_matches_its_committed_copy(tmp_path: Path) -> None:
    emitted = wave.write_field_admissions_record(tmp_path / "admissions.json").read_bytes()
    assert emitted == FIELD_ADMISSIONS.read_bytes()
    assert b"\r" not in emitted
    assert emitted.endswith(b"}\n")


def test_wave1_artifact_matches_its_committed_copy(tmp_path: Path) -> None:
    committed = json.loads(WAVE1.read_text(encoding="utf-8"))
    emitted = wave.write_wave1_record(
        tmp_path / "wave1.json",
        execution_commit_sha=committed["execution_commit_sha"],
        execution_tree_sha=committed["execution_tree_sha"],
    ).read_bytes()
    assert emitted == WAVE1.read_bytes()
    assert b"\r" not in emitted
    assert emitted.endswith(b"}\n")


def test_the_committed_wave_record_binds_the_field_admissions_it_ran_under() -> None:
    committed = json.loads(WAVE1.read_text(encoding="utf-8"))
    assert committed["field_admission_sha"] == wave.field_admissions_sha()
    assert committed["terminal"] == "SYNTHETIC_CALIBRATION_WAVE1_BLOCKED"
    assert committed["safe_for_supervisor_composition"] is True
