from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report as br
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"

#: The authoritative starting blocker set carried by the tested V3 baseline.
#: Preserved verbatim: R2 convergence must not be able to rewrite what the
#: audited R1 state was.
BASELINE_BLOCKERS = frozenset(
    {
        "calibration.weekly_performance_residual_coefficient",
        "calibration.weekly_movement_cap_points",
        "calibration.recent_form_weights",
        "calibration.blowout_treatment",
        "calibration.game_sd_points",
        "calibration.sample_size_regularization",
        "hfa_baseline_points",
        "fcs_translation_policy",
        "committee_tiebreak_strength_source",
        "inputs.aac_divisions_csv",
        "provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH",
        "provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5",
        "governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5",
        "governance.GAME_SD_CALIBRATION_OPEN",
        "governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED",
        "governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE",
        "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",
        "governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT",
    }
)


def test_register_covers_all_eighteen_baseline_blockers():
    covered = {d.blocker_id for d in br.dispositions()}
    assert BASELINE_BLOCKERS <= covered
    assert br.R1_BASELINE_BLOCKERS == BASELINE_BLOCKERS
    assert len(br.R1_BASELINE_BLOCKERS) == 18
    assert len(br.R1_AUDITED_LIVE_BLOCKERS) == 17


def test_register_also_covers_every_blocker_opened_by_r2():
    covered = {d.blocker_id for d in br.dispositions()}
    assert covered == BASELINE_BLOCKERS | br.R2_OPENED_BLOCKERS
    assert len(br.dispositions()) == 21


def test_every_disposition_is_from_the_governed_vocabulary():
    assert all(d.disposition in br.DISPOSITIONS for d in br.dispositions())


def test_resolved_is_exactly_the_reconciliation_plus_the_r2_rulings():
    """`RESOLVED` stays reserved: one reconciliation, nine rulings, nothing inferred."""
    resolved = {d.blocker_id for d in br.dispositions() if d.resolved}
    assert resolved == {
        "provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH"
    } | br.R2_RETIRED_BLOCKERS


def test_every_ruling_resolution_names_its_ruling():
    for d in br.dispositions():
        if d.disposition == "RESOLVED_BY_CHAIRMAN_RULING":
            assert d.ruling, f"{d.blocker_id} claims a ruling resolution without naming one"
            assert d.blocker_id in br.R2_RETIRED_BLOCKERS


def test_a_ruling_resolution_cannot_omit_its_ruling():
    with pytest.raises(ValueError, match="names no ruling"):
        br.BlockerDisposition(
            blocker_id="x", disposition="RESOLVED_BY_CHAIRMAN_RULING",
            evidence="", required_to_clear="", governance_group="G",
        )


def test_no_calibration_blocker_is_marked_resolved():
    """No ruling substitutes for calibration evidence that does not exist."""
    for d in br.dispositions():
        if d.blocker_id.startswith("calibration.") or d.blocker_id.endswith(
            "GAME_SD_CALIBRATION_OPEN"
        ):
            assert not d.resolved, f"{d.blocker_id} must not claim resolution"


def test_governed_field_blockers_resolve_only_by_named_ruling():
    for d in br.dispositions():
        if d.blocker_id.startswith(("hfa_", "fcs_", "committee_", "inputs.")) and d.resolved:
            assert d.disposition == "RESOLVED_BY_CHAIRMAN_RULING"
            assert d.ruling


def test_summary_counts_are_consistent():
    s = br.summary()
    assert s["total"] == 21
    assert s["resolved_count"] == 10
    assert s["remaining_count"] == 11
    assert s["resolved_count"] + s["remaining_count"] == s["total"]


def test_convergence_delta_accounts_for_every_blocker_exactly_once():
    delta = br.convergence_delta()
    assert delta["r1_baseline_count"] == 18
    assert delta["r1_audited_live_count"] == 17
    assert delta["r2_expected_live_count"] == 11
    assert len(delta["retired_by_r2"]) == 9
    assert len(delta["opened_by_r2"]) == 3
    # Nothing appears in two categories.
    assert not (br.R2_RETIRED_BLOCKERS & br.R2_OPENED_BLOCKERS)
    assert br.R2_RETIRED_BLOCKERS <= br.R1_AUDITED_LIVE_BLOCKERS
    assert not (br.R2_OPENED_BLOCKERS & br.R1_BASELINE_BLOCKERS)


def test_paired_blockers_share_one_governance_group():
    groups = br.summary()["governance_groups"]
    assert set(groups[br.GROUP_HFA]) == {
        "hfa_baseline_points",
        "governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5",
    }
    assert set(groups[br.GROUP_GAME_SD]) == {
        "calibration.game_sd_points",
        "governance.GAME_SD_CALIBRATION_OPEN",
    }
    assert set(groups[br.GROUP_FCS]) == {
        "fcs_translation_policy",
        "governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE",
    }


def test_seventeen_remaining_blockers_collapse_to_fewer_distinct_rulings():
    rulings = br.summary()["distinct_remaining_rulings"]
    assert len(rulings) < 17
    assert br.GROUP_CALIBRATION in rulings


def test_unknown_disposition_is_rejected():
    with pytest.raises(ValueError, match="Unknown disposition"):
        br.BlockerDisposition(
            blocker_id="x", disposition="RESOLVED_BECAUSE_I_SAID_SO",
            evidence="", required_to_clear="", governance_group="G",
        )


def test_live_config_still_blocks_and_v3_remains_experimental():
    cfg = V3Config.from_json(CONFIG)
    assert cfg.model_name.endswith("_EXPERIMENTAL")
    assert cfg.configuration_version.startswith("V3-PLACEHOLDER")
    report = DynamicWeeklyMCV3(cfg).preflight()
    assert report["status"] == "STRUCTURAL_PREFLIGHT_PASS"
    assert len(report["execution_blockers"]) > 0
