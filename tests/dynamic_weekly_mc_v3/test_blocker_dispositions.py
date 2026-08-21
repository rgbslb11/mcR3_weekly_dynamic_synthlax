from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report as br
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"

#: The authoritative starting blocker set carried by the tested V3 baseline.
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
    assert covered == BASELINE_BLOCKERS
    assert len(br.dispositions()) == 18


def test_every_disposition_is_from_the_governed_vocabulary():
    assert all(d.disposition in br.DISPOSITIONS for d in br.dispositions())


def test_only_the_schedule_content_hash_is_claimed_resolved():
    """`RESOLVED` is reserved for results execution can consume without inference."""
    resolved = {d.blocker_id for d in br.dispositions() if d.resolved}
    assert resolved == {"provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH"}


def test_no_governed_field_blocker_is_marked_resolved():
    for d in br.dispositions():
        if d.blocker_id.startswith(("calibration.", "hfa_", "fcs_", "committee_", "inputs.")):
            assert not d.resolved, f"{d.blocker_id} must not claim resolution"


def test_summary_counts_are_consistent():
    s = br.summary()
    assert s["total"] == 18
    assert s["resolved_count"] == 1
    assert s["remaining_count"] == 17
    assert s["resolved_count"] + s["remaining_count"] == s["total"]


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
