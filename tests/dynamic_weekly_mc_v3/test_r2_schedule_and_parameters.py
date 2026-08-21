"""R2 convergence: schedule authority, 13-game exceptions, HFA and FCS."""

from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import fcs, hfa, provenance
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import schedule_exceptions as se
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.inputs import load_schedule
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.models import ScheduledGame

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"


def _schedule():
    return load_schedule(V3Config.from_json(CONFIG).inputs.schedule_xlsx)


# --- schedule v5 source-copy governance -------------------------------------


def test_source_copy_binary_difference_no_longer_blocks_when_content_certifies():
    p = provenance.reconcile_schedule_provenance(V3Config.from_json(CONFIG).inputs.schedule_xlsx)
    assert p.content_verified is True
    assert p.binary_verified is False
    assert provenance.BINARY_MISMATCH in p.anomalies()
    assert p.blocking_anomalies() == []
    assert p.governed_binary_disposition() == "ACCEPTED_SOURCE_COPY_UNDER_R2_SCHED_V5_AUTH"


def test_all_three_historical_binary_hashes_are_preserved_unedited():
    assert provenance.GOVERNED_SCHEDULE_BINARY_SHA256 == (
        "db26c3fff15a61ce8e7efa3b93100fa017e02248c96076d291495b55e855da12"
    )
    assert provenance.SUPERSEDED_V4_BINARY_SHA256 == (
        "8d4d5112aa52cfb51895c95d104e3c5e1821813e3b481a4f1b3067668d0af57b"
    )
    assert provenance.CERTIFIED_GAMES_CONTENT_SHA256 == (
        "bd8089f70f6d483a75564e33438272c22daade8e53619fb21a915778975ff221"
    )


def test_content_failure_still_blocks_under_the_schedule_ruling():
    """The ruling accepts a source copy, never uncertified fixtures."""
    p = provenance.ScheduleProvenance(
        content_sha256_reproduced="deadbeef",
        content_sha256_certified=provenance.CERTIFIED_GAMES_CONTENT_SHA256,
        binary_sha256_actual="b0f2c2cd",
        binary_sha256_governed=provenance.GOVERNED_SCHEDULE_BINARY_SHA256,
    )
    assert provenance.CONTENT_MISMATCH in p.blocking_anomalies()
    assert provenance.BINARY_MISMATCH in p.blocking_anomalies()
    assert p.governed_binary_disposition() == "BLOCKED_CONTENT_NOT_CERTIFIED"


def test_a_mounted_superseded_v4_artifact_still_blocks():
    p = provenance.ScheduleProvenance(
        content_sha256_reproduced=provenance.CERTIFIED_GAMES_CONTENT_SHA256,
        content_sha256_certified=provenance.CERTIFIED_GAMES_CONTENT_SHA256,
        binary_sha256_actual=provenance.SUPERSEDED_V4_BINARY_SHA256,
        binary_sha256_governed=provenance.GOVERNED_SCHEDULE_BINARY_SHA256,
    )
    assert provenance.BINARY_MISMATCH in p.blocking_anomalies()
    assert p.governed_binary_disposition() == "BLOCKED_SUPERSEDED_V4_ARTIFACT"


# --- five approved 13-game schedules ----------------------------------------


def test_exactly_the_five_approved_teams_carry_thirteen_regular_season_games():
    report = se.validate_13_game_exceptions(_schedule())
    assert report["approved_teams"] == ["ARK", "GAST", "UK", "VAN", "WVU"]
    assert report["teams_at_thirteen_games"] == ["ARK", "GAST", "UK", "VAN", "WVU"]
    assert report["regular_season_games_each"] == 13
    assert report["validated"] is True


def test_ccg_template_rows_are_never_counted_as_regular_season_games():
    report = se.validate_13_game_exceptions(_schedule())
    assert report["ccg_template_rows_excluded"] == 7
    audits = se.audit_regular_season_counts(_schedule())
    assert all(a.regular_season_games <= 13 for a in audits.values())


def test_an_unapproved_team_reaching_thirteen_games_is_rejected():
    schedule = list(_schedule())
    extra = ScheduledGame(
        "G9001", 14, "2026-11-28", "REG", "UGA", "TEX", "SEC", "SEC", "HOME", True, False, False
    )
    with pytest.raises(InputValidationError, match="without an approved exception"):
        se.validate_13_game_exceptions(schedule + [extra])


def test_a_duplicate_opponent_date_artifact_is_rejected():
    schedule = list(_schedule())
    original = next(g for g in schedule if g.game_type == "REG" and g.home_team == "ARK")
    twin = ScheduledGame(
        "G9002", original.week, original.date, "REG", original.home_team, original.away_team,
        original.home_conf, original.away_conf, "HOME", True, False, False,
    )
    with pytest.raises(InputValidationError, match="Duplicate opponent/date"):
        se.validate_13_game_exceptions(schedule + [twin])


def test_a_resolved_ccg_template_row_is_rejected():
    schedule = list(_schedule())
    ccg_row = next(g for g in schedule if g.game_type == "CCG")
    resolved = ScheduledGame(
        ccg_row.game_id, ccg_row.week, ccg_row.date, "CCG", "ARK", "UGA",
        "SEC", "SEC", "NEUTRAL", True, False, False,
    )
    schedule = [g for g in schedule if g.game_id != ccg_row.game_id] + [resolved]
    with pytest.raises(InputValidationError, match="template row"):
        se.validate_13_game_exceptions(schedule)


# --- HFA ---------------------------------------------------------------------


def test_v3_football_point_hfa_is_three_point_five():
    assert hfa.governed_v3_football_point_hfa() == 3.5
    assert hfa.require_governed_hfa(3.5) == 3.5
    assert V3Config.from_json(CONFIG).hfa_baseline_points == 3.5


def test_legacy_four_point_zero_is_preserved_as_historical_and_refused_for_v3():
    assert hfa.LEGACY_V2_DRIVE_ENGINE_HFA == 4.0
    assert hfa.LEGACY_V2_DRIVE_ENGINE_HFA_STATUS == "HISTORICAL"
    assert hfa.LEGACY_V2_DRIVE_ENGINE_HFA_VALIDATION == "NOT CURRENT"
    with pytest.raises(GovernanceBlock, match="HISTORICAL"):
        hfa.require_governed_hfa(4.0)


def test_elo_layer_hfa_remains_a_separate_parameter():
    assert hfa.CCG_ELO_HFA == 65.0
    elo = next(p for p in hfa.HFA_REGISTER if p.parameter_id == "CCG-HFA_ELO")
    assert elo.layer == "ELO"
    assert elo.governed_for_v3 is True
    points = [p for p in hfa.HFA_REGISTER if p.layer == "FOOTBALL_POINTS"]
    assert {p.value for p in points} == {3.5, 4.0}
    assert hfa.as_dict()["elo_layer_is_separate_parameter"] is True


def test_hfa_ruling_does_not_globally_replace_every_hfa_like_value():
    values = {p.parameter_id: p.value for p in hfa.HFA_REGISTER}
    assert values == {"SCHED-HFA-BASE": 3.5, "ENG-HOME-FIELD": 4.0, "CCG-HFA_ELO": 65.0}


def test_an_unruled_hfa_value_is_refused():
    for bad in (None, 3.0, 4.5):
        with pytest.raises(GovernanceBlock):
            hfa.require_governed_hfa(bad)


# --- FCS ---------------------------------------------------------------------


def test_fcs_elo_is_fixed_at_1250_with_no_toggle():
    policy = fcs.require_governed_fcs_policy("FIXED_ELO_1250")
    assert policy.fixed_elo == 1250.0
    assert policy.layer == "ELO"
    assert policy.requires_future_toggle is False
    assert policy.model_use_authorized_by_ruling is True
    assert V3Config.from_json(CONFIG).fcs_translation_policy == "FIXED_ELO_1250"


def test_board_equivalent_values_are_refused_as_an_fcs_conversion_rule():
    for value in (0.294, 0.297, 0.297514):
        with pytest.raises(GovernanceBlock, match="conversion rule"):
            fcs.reject_board_derived_conversion(value)


def test_inverting_the_elo_board_transform_is_refused():
    with pytest.raises(GovernanceBlock, match="forbidden"):
        fcs.invert_board_transform(1250.0)


def test_the_unified_points_scale_for_fcs_is_not_governed_and_fails_closed():
    assert fcs.GOVERNED_FCS_POLICY.unified_points_equivalent is None
    with pytest.raises(GovernanceBlock, match=fcs.FCS_UNIFIED_SCALE_BLOCKER):
        fcs.require_fcs_unified_points()


def test_an_invented_fcs_policy_is_refused():
    for bad in (None, "", "BOARD_EQUIVALENT", "FIXED_ELO_1300"):
        with pytest.raises(GovernanceBlock):
            fcs.require_governed_fcs_policy(bad)
