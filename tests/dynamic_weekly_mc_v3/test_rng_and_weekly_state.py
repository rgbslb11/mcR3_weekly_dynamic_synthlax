from pathlib import Path

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import InputPaths, ReratingCalibration, V3Config, DEFAULT_PRIOR_DECAY
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.models import ScheduledGame, Team
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.rerating import FixtureResidualRerater
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.rng import deterministic_standard_normal


def _cfg(tmp_path: Path) -> V3Config:
    aac = tmp_path / "aac.csv"
    aac.write_text("schedule_id,division\nA,American\nB,Athletic\n", encoding="utf-8")
    dummy = tmp_path / "dummy"
    return V3Config(
        model_name="SYTHALAX_DYNAMIC_WEEKLY_MC_V3_EXPERIMENTAL",
        model_version="test",
        configuration_version="test",
        paths=10_000,
        base_seed=20260803,
        weeks=tuple(range(1, 17)),
        first_promoted_rerating_after_week=2,
        prior_decay=DEFAULT_PRIOR_DECAY.copy(),
        hfa_baseline_points=0.0,
        freeze_strength_after_selection=True,
        write_path_level_parquet=False,
        inputs=InputPaths(dummy, dummy, dummy, dummy, dummy, dummy, dummy, dummy, aac),
        calibration=ReratingCalibration(
            weekly_performance_residual_coefficient=0.1,
            weekly_movement_cap_points=2.0,
            recent_form_weights=(1.0,),
            blowout_treatment={"type": "TEST_ONLY_IDENTITY"},
            game_sd_points=1.0,
            sample_size_regularization={"type": "TEST_ONLY_NONE"},
        ),
        fcs_translation_policy="TEST_ONLY_NOT_USED",
        committee_tiebreak_strength_source="PRESEASON_STRENGTH",
    )


def test_rng_is_path_isolated_and_order_independent():
    a1 = deterministic_standard_normal(20260803, "REG", 1, 2, "G0010")
    a2 = deterministic_standard_normal(20260803, "REG", 1, 2, "G0010")
    b = deterministic_standard_normal(20260803, "REG", 2, 2, "G0010")
    assert a1 == a2
    assert a1 != b


def test_week1_candidate_is_audit_only_and_week2_is_first_promotion(tmp_path):
    cfg = _cfg(tmp_path)
    teams = {
        "A": Team("A", "Alpha", "Test", "FBS_MEMBER", True, 100.0, 10.0, 1.0),
        "B": Team("B", "Beta", "Test", "FBS_MEMBER", True, 100.0, 0.0, 1.0),
    }
    schedule = [
        ScheduledGame("G1", 1, "2026-08-29", "REG", "A", "B", "Test", "Test", "NEUTRAL", True, False, False),
        ScheduledGame("G2", 2, "2026-09-05", "REG", "A", "B", "Test", "Test", "NEUTRAL", True, False, False),
    ]
    engine = DynamicWeeklyMCV3(cfg, rerater=FixtureResidualRerater(0.1, 2.0))
    observations, snapshots = engine.simulate_regular_season_path(path_id=7, teams=teams, schedule=schedule)
    w1_a = next(s for s in snapshots if s.week_completed == 1 and s.schedule_id == "A")
    w2_a = next(s for s in snapshots if s.week_completed == 2 and s.schedule_id == "A")
    assert w1_a.audit_only is True and w1_a.promoted is False and w1_a.prior_weight == 0.8
    assert w2_a.audit_only is False and w2_a.promoted is True and w2_a.prior_weight == 0.6
    # Week 2 must open from preseason strength, not the W1 audit-only candidate.
    week2_obs = next(o for o in observations if o.week == 2)
    assert week2_obs.home_strength_points == 10.0
    assert week2_obs.away_strength_points == 0.0


def test_after_week5_prior_specific_weight_is_zero(tmp_path):
    cfg = _cfg(tmp_path)
    assert cfg.prior_weight_after_week(5) == 0.0
    assert cfg.prior_weight_after_week(6) == 0.0
    assert cfg.prior_weight_after_week(16) == 0.0
