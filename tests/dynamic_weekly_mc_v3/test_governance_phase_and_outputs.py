from pathlib import Path

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.aggregate import (
    TEAM_SUMMARY_FIELDS,
    aggregate_team_outcomes,
    aggregate_weekly_strength,
    conference_team_probability_rows,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.models import TeamSeasonOutcome, WeeklyStrengthSnapshot
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.phase_plan import V3_INITIAL_PHASE_PLAN, validate_phase_plan

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"


def test_governance_inspections_are_fail_closed_and_visible():
    report = DynamicWeeklyMCV3(V3Config.from_json(CONFIG)).preflight()
    blockers = set(report["execution_blockers"])
    governed = report["governed_evidence"]

    assert governed["model_parameters"]["hfa_v2_legacy_points"] == 4.0
    assert governed["model_parameters"]["hfa_team_master_locked_points"] == 3.5
    assert governed["model_parameters"]["margin_sd_calibration_status"] == "OPEN"
    assert governed["model_parameters"]["schedule_13_game_exception_status"] == "OPEN"
    assert governed["fcs_authority"]["model_use_authorized"] is False
    assert governed["bracket"]["quarterfinal_opponent_mapping_explicit"] is False

    # The governed registers are unchanged: the register rows above still say
    # exactly what they said before R2. What changed is that rulings now make
    # four of them non-blocking, which is visible as an absence here.
    for retired in (
        "governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5",
        "governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED",
        "governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE",
        "governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT",
    ):
        assert retired not in blockers

    # Calibration evidence cannot be ruled away. It is still here.
    assert "governance.GAME_SD_CALIBRATION_OPEN" in blockers
    assert "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER" in blockers

    # Retired by the R3 final convergence. The register row above is unchanged --
    # quarterfinal_opponent_mapping_explicit is still False, because the workbook
    # still does not state the mapping. Successor Chairman authority does.
    for retired_by_r3 in (
        "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",
        "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED",
    ):
        assert retired_by_r3 not in blockers


def test_schedule_phase_partition_preserves_selection_freeze_boundary():
    report = DynamicWeeklyMCV3(V3Config.from_json(CONFIG)).preflight()
    assert report["schedule_phases"] == {
        "preselection_regular_w1_w14": 735,
        "conference_championship_templates_w15": 7,
        "postselection_regular_w16": 1,
    }
    validate_phase_plan()
    assert V3_INITIAL_PHASE_PLAN[0].weeks == tuple(range(1, 15))
    assert V3_INITIAL_PHASE_PLAN[1].weeks == (15,)
    assert V3_INITIAL_PHASE_PLAN[3].weeks == (16,)
    assert V3_INITIAL_PHASE_PLAN[3].strength_frozen is True
    assert V3_INITIAL_PHASE_PLAN[3].rerate_after_phase_week is False
    assert V3_INITIAL_PHASE_PLAN[4].strength_frozen is True


def test_required_team_and_conference_output_scaffolds_preserve_all_fields():
    outcomes = [
        TeamSeasonOutcome(0, "A", 10, True, True, True, True, True, True, True, True, 1, 12.0),
        TeamSeasonOutcome(1, "A", 8, False, False, True, False, True, False, False, False, 7, 10.0),
        TeamSeasonOutcome(0, "B", 7, False, False, False, False, False, False, False, False, 20, 2.0),
        TeamSeasonOutcome(1, "B", 9, True, True, True, False, True, True, False, False, 10, 4.0),
    ]
    summary = aggregate_team_outcomes(outcomes)
    assert len(summary) == 2
    assert set(summary[0]) == set(TEAM_SUMMARY_FIELDS)

    by_id = {r["schedule_id"]: r for r in summary}
    by_id["A"]["preseason_strength"] = 11.0
    by_id["B"]["preseason_strength"] = 3.0
    conf = conference_team_probability_rows(summary, {"A": "X", "B": "X"})
    assert len(conf) == 2
    assert sum(bool(x["favorite_to_reach_national_title_game"]) for x in conf) == 1
    assert sum(bool(x["favorite_to_win_national_title"]) for x in conf) == 1

    snapshots = [
        WeeklyStrengthSnapshot(0, 1, "A", 11.0, 10.0, False, 0.8, 1, True, "p0w1"),
        WeeklyStrengthSnapshot(1, 1, "A", 11.0, 12.0, False, 0.8, 1, True, "p1w1"),
    ]
    traj = aggregate_weekly_strength(snapshots)
    assert traj[0]["schedule_id"] == "A"
    assert traj[0]["week_completed"] == 1
    assert traj[0]["average_strength"] == 11.0
    assert traj[0]["paths"] == 2
