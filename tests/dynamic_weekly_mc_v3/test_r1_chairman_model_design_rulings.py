"""Chairman V3 model-design rulings R1.

Each test below pins one thing the instruction asked to be provable rather than
asserted. The two shapes that recur are worth naming, because a reader should be
able to tell at a glance which kind of claim a test is making:

*Behavioural* tests exercise the mechanism — the cap really clips, the decay
really has a floor, the most recent game really carries the most weight.

*Refusal* tests prove a closed route stays closed. A refusal test that starts
passing because someone supplied a number has not been fixed, it has been
defeated. That is deliberate: the FCS adapter, the coefficient universe and the
game-SD substitution are all cases where a plausible number is available and
using it would be the failure.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import chairman_model_design_r1 as mdr1
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import fcs, hfa
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import rulings as governance_rulings
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "dynamic_weekly_mc_v3" / "v3_experimental.json"
ARTIFACT = ROOT / "reference" / "dynamic_weekly_mc_v3" / mdr1.MDR1_ARTIFACT


@pytest.fixture(scope="module")
def artifact() -> dict:
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# 1-3. Blowout treatment caps the update margin and nothing else
# ---------------------------------------------------------------------------

def test_a_plus_26_blowout_becomes_plus_25_for_update_purposes():
    assert mdr1.update_driving_margin(26.0) == 25.0


def test_a_minus_31_blowout_becomes_minus_25():
    assert mdr1.update_driving_margin(-31.0) == -25.0


@pytest.mark.parametrize(
    ("actual", "expected"),
    [(42.0, 25.0), (-38.0, -25.0), (13.0, 13.0), (-13.0, -13.0), (25.0, 25.0), (0.0, 0.0)],
)
def test_the_ruled_worked_examples_reproduce(actual, expected):
    assert mdr1.update_driving_margin(actual) == expected


def test_the_actual_game_score_and_margin_are_left_unchanged():
    """The cap lives inside the update calculation, not in the result record.

    A scoreline is passed through the residual path and then re-read. If the cap
    ever wrote back, the recorded game would silently become a 25-point win.
    """
    game = {"home_score": 59, "away_score": 17, "actual_margin": 42.0}
    snapshot = dict(game)

    update_margin = mdr1.update_driving_margin(game["actual_margin"])
    residual = mdr1.residual_from_game(game["actual_margin"], expected_margin=10.0)

    assert update_margin == 25.0
    assert residual == 15.0
    assert game == snapshot
    assert game["home_score"] - game["away_score"] == 42
    assert mdr1.blowout_cap_hit(game["actual_margin"]) is True
    assert mdr1.blowout_cap_hit(13.0) is False


def test_the_cap_is_reported_as_hit_only_when_it_actually_bound():
    assert mdr1.blowout_cap_hit(25.0) is False
    assert mdr1.blowout_cap_hit(25.5) is True
    assert mdr1.blowout_cap_hit(-25.5) is True


def test_a_non_numeric_margin_fails_closed():
    with pytest.raises(InputValidationError):
        mdr1.update_driving_margin(float("nan"))


# ---------------------------------------------------------------------------
# 4. The ten-slot rule is advisory only
# ---------------------------------------------------------------------------

def test_the_ten_slot_rule_is_advisory_and_never_a_cap():
    """A 40-slot move is reported in full, not clipped to eleven.

    The advisory records the move; it does not bound it. ``new_rank`` coming back
    as anything other than 62 would mean the reporting rule had become a cap.
    """
    move = mdr1.rank_move_advisory(
        team="TEX",
        prior_rank=102,
        new_rank=62,
        underlying_point_change=9.4,
        performance_residual=18.2,
        cap_hit=False,
    )
    assert move is not None
    assert move.signal == mdr1.LARGE_WEEKLY_RANK_MOVE
    assert move.new_rank == 62
    assert move.slot_change == -40
    assert mdr1.rank_movement_is_capped() is False
    assert mdr1.WEEKLY_RANK_MOVEMENT_STATUS == "ADVISORY_ONLY"


def test_exactly_ten_slots_is_not_an_advisory_and_eleven_is():
    assert mdr1.rank_move_advisory(
        team="A", prior_rank=20, new_rank=30,
        underlying_point_change=1.0, performance_residual=1.0, cap_hit=False,
    ) is None
    assert mdr1.rank_move_advisory(
        team="A", prior_rank=20, new_rank=31,
        underlying_point_change=1.0, performance_residual=1.0, cap_hit=False,
    ) is not None


def test_every_advisory_carries_the_full_recorded_field_set():
    move = mdr1.rank_move_advisory(
        team="MIA", prior_rank=5, new_rank=27,
        underlying_point_change=-6.1, performance_residual=-14.0, cap_hit=True,
    )
    assert move is not None
    emitted = move.as_dict()
    for field in mdr1.LARGE_WEEKLY_RANK_MOVE_FIELDS:
        assert field in emitted, field


# ---------------------------------------------------------------------------
# 5-6. Point scale is a convention, and says so
# ---------------------------------------------------------------------------

def test_the_point_scale_is_exactly_14_point_0():
    assert mdr1.V3_POINT_SCALE == 14.0
    assert mdr1.v3_neutral_field_points(1.0) == 14.0
    assert mdr1.v3_neutral_field_points(-0.5) == -7.0


def test_the_point_scale_matches_the_mounted_unified_axis():
    """Consistency with the artifact the axis is defined over.

    The ruling is the authority for 14.0, not this equality — but a V3 point
    scale that disagreed with the unified neutral-field scale would mean two
    different point axes were in play under one name.
    """
    assert mdr1.V3_POINT_SCALE == fcs.UNIFIED_NEUTRAL_POINTS_PER_SD


def test_the_point_scale_status_says_not_empirically_identified():
    assert mdr1.V3_POINT_SCALE_IDENTIFICATION == "NOT_EMPIRICALLY_IDENTIFIED"
    assert mdr1.V3_POINT_SCALE_STATUS == "FIXED_V3_SYNTHETIC_SCALE"


def test_the_artifact_records_the_point_scale_as_a_convention(artifact):
    row = next(
        r for r in artifact["parameter_register"] if r["parameter"] == "point_scale"
    )
    assert row["value"] == 14.0
    assert row["identification"] == "NOT_EMPIRICALLY_IDENTIFIED"
    assert row["empirically_identified"] is False


# ---------------------------------------------------------------------------
# 7-11. Recent form is residual-driven
# ---------------------------------------------------------------------------

def test_the_recent_form_lambda_candidates_are_exactly_0_60_0_75_0_90():
    assert mdr1.RECENT_FORM_LAMBDA_CANDIDATES == {
        "FAST": 0.60,
        "MEDIUM": 0.75,
        "SLOW": 0.90,
    }
    assert sorted(mdr1.RECENT_FORM_LAMBDA_CANDIDATES.values()) == [0.60, 0.75, 0.90]


@pytest.mark.parametrize("lam", [0.60, 0.75, 0.90])
def test_the_most_recent_game_receives_the_greatest_recent_form_weight(lam):
    weights = [mdr1.recent_form_weight(k, lam) for k in range(6)]
    assert weights[0] == 1.0
    assert weights == sorted(weights, reverse=True)
    assert all(a > b for a, b in zip(weights, weights[1:]))


@pytest.mark.parametrize("lam", [0.60, 0.75, 0.90])
def test_a_positive_residual_streak_produces_a_positive_recent_form_signal(lam):
    signal = mdr1.recent_form_signal([6.0, 5.0, 7.0, 6.5], lam)
    assert signal > 0.0


@pytest.mark.parametrize("lam", [0.60, 0.75, 0.90])
def test_a_negative_residual_streak_produces_a_negative_recent_form_signal(lam):
    signal = mdr1.recent_form_signal([-6.0, -5.0, -7.0, -6.5], lam)
    assert signal < 0.0


def test_sustained_pressure_persists_and_a_faster_lambda_reacts_harder():
    """A turn in form moves the fast decay further than the slow one.

    Same history, three decays. If FAST did not respond more sharply than SLOW,
    the lambda axis would not be separating anything and the sweep over it would
    be measuring noise.
    """
    turnaround = [9.0, 8.0, -7.0, -8.0, -7.5]
    fast = mdr1.recent_form_signal(turnaround, 0.60)
    medium = mdr1.recent_form_signal(turnaround, 0.75)
    slow = mdr1.recent_form_signal(turnaround, 0.90)
    assert fast > medium > slow


def test_raw_win_loss_alone_cannot_substitute_for_a_residual():
    for token in mdr1.WIN_LOSS_TOKENS:
        with pytest.raises(GovernanceBlock):
            mdr1.reject_win_loss_as_residual(token)
    with pytest.raises(GovernanceBlock):
        mdr1.reject_win_loss_as_residual(True)
    with pytest.raises(GovernanceBlock):
        mdr1.recent_form_signal(["W", "W", "W"], 0.75)
    with pytest.raises(GovernanceBlock):
        mdr1.performance_residual("W", 0.0)


def test_a_win_over_a_weak_opponent_does_not_create_a_positive_signal():
    """Beating a 30-point underdog by 3 is a large negative residual.

    This is the case the ruling names: the result is a win, the performance is
    far below expectation, and recent form must follow the performance.
    """
    residual = mdr1.residual_from_game(actual_margin=3.0, expected_margin=30.0)
    assert residual == -27.0
    assert mdr1.recent_form_signal([residual, residual, residual], 0.75) < 0.0


def test_a_narrow_loss_while_outperforming_does_not_create_a_negative_signal():
    """Losing by 2 as a 21-point underdog is a large positive residual."""
    residual = mdr1.residual_from_game(actual_margin=-2.0, expected_margin=-21.0)
    assert residual == 19.0
    assert mdr1.recent_form_signal([residual, residual, residual], 0.75) > 0.0


def test_the_residual_is_computed_from_the_capped_margin_not_the_raw_one():
    """Cap first, then subtract. Skipping the cap overstates a blowout by 17."""
    assert mdr1.residual_from_game(actual_margin=42.0, expected_margin=10.0) == 15.0
    assert mdr1.performance_residual(42.0, 10.0) == 32.0


def test_an_out_of_range_lambda_is_refused():
    for bad in (0.0, 1.0, 1.5, -0.2):
        with pytest.raises(InputValidationError):
            mdr1.recent_form_weight(1, bad)
    with pytest.raises(InputValidationError):
        mdr1.recent_form_weight(-1, 0.75)


def test_an_empty_residual_history_is_neutral_rather_than_an_error():
    assert mdr1.recent_form_signal([], 0.75) == 0.0


# ---------------------------------------------------------------------------
# 12-13. Preseason prior decay and its floor
# ---------------------------------------------------------------------------

def test_the_preseason_weights_are_exactly_the_ruled_schedule():
    assert mdr1.MDR1_PRESEASON_PRIOR_DECAY == {
        0: 1.00, 1: 0.80, 2: 0.60, 3: 0.50,
        4: 0.40, 5: 0.30, 6: 0.20, 7: 0.15,
    }
    assert [mdr1.preseason_prior_weight(w) for w in range(8)] == [
        1.00, 0.80, 0.60, 0.50, 0.40, 0.30, 0.20, 0.15
    ]


def test_the_prior_floor_remains_0_15_and_never_reaches_zero():
    for week in range(7, 17):
        assert mdr1.preseason_prior_weight(week) == 0.15
    assert mdr1.PRESEASON_PRIOR_FLOOR == 0.15
    assert all(mdr1.preseason_prior_weight(w) > 0.0 for w in range(0, 17))


def test_the_decay_is_monotone_and_the_complement_is_the_evolved_state():
    weights = [mdr1.preseason_prior_weight(w) for w in range(0, 17)]
    assert all(a >= b for a, b in zip(weights, weights[1:]))
    assert mdr1.evolved_state_weight(2) == pytest.approx(0.40)
    assert mdr1.evolved_state_weight(9) == pytest.approx(0.85)


def test_the_w1_and_w2_prior_weights_preserve_the_existing_first_rerating_design():
    assert mdr1.preseason_prior_weight(1) == 0.80
    assert mdr1.preseason_prior_weight(2) == 0.60
    assert mdr1.FIRST_PROMOTED_RERATING_AFTER_WEEK == 2
    assert mdr1.SWEEP_ORIGIN_STATE == "FROZEN_POST_WEEK_2_STATE"


def test_the_conflict_with_the_mounted_placeholder_decay_is_recorded_not_hidden(artifact):
    """The lane promotes nothing, so the disagreement is written down instead.

    The mounted configuration still decays to 0.00 after Week 5. Leaving that
    silently in place would let a runtime contradict a ruling; recording the
    required alignment keeps the contradiction visible and attributable.
    """
    cfg = V3Config.from_json(CONFIG)
    assert cfg.prior_decay != mdr1.MDR1_PRESEASON_PRIOR_DECAY
    alignment = artifact["config_alignment_required"]
    assert alignment, "a live disagreement must be recorded"
    assert all(item["promoted_by_this_lane"] is False for item in alignment)
    targets = " ".join(item["target"] for item in alignment)
    assert "v3_experimental.json" in targets
    assert "config.py" in targets


# ---------------------------------------------------------------------------
# 14. Monte Carlo feedback firewall
# ---------------------------------------------------------------------------

def test_simulated_mc_results_cannot_mutate_the_governed_weekly_state():
    state = mdr1.FrozenWeeklyState(week=4, strength_points={"TEX": 21.0})
    with pytest.raises(GovernanceBlock) as excinfo:
        state.advanced_by(
            week=5,
            strength_points={"TEX": 99.0},
            origin=mdr1.SIMULATED_RESULT,
        )
    assert mdr1.MC_FEEDBACK_FIREWALL in str(excinfo.value)
    assert state.strength_points["TEX"] == 21.0


def test_only_realized_synthetic_results_advance_the_state():
    state = mdr1.FrozenWeeklyState(week=4, strength_points={"TEX": 21.0})
    nxt = state.advanced_by(
        week=5, strength_points={"TEX": 23.5}, origin=mdr1.REALIZED_RESULT
    )
    assert nxt.week == 5
    assert nxt.strength_points["TEX"] == 23.5
    assert state.strength_points["TEX"] == 21.0


def test_a_frozen_state_cannot_be_edited_through_the_mapping_it_was_built_from():
    """The caller's dict is copied in, so it is not a back door into the state."""
    live = {"TEX": 21.0}
    state = mdr1.FrozenWeeklyState(week=4, strength_points=live)
    live["TEX"] = 99.0
    assert state.strength_points["TEX"] == 21.0


def test_an_unrecognised_update_origin_is_refused_rather_than_assumed_realized():
    with pytest.raises(GovernanceBlock):
        mdr1.require_realized_origin("PROJECTED_RESULT")
    with pytest.raises(GovernanceBlock):
        mdr1.reject_simulated_state_update()


def test_a_design_sweep_cell_never_feeds_the_frozen_state_or_another_cell(artifact):
    sweep = artifact["design_sweep"]
    assert sweep["origin_state"] == "FROZEN_POST_WEEK_2_STATE"
    assert "never feed" in sweep["cell_isolation"]
    assert artifact["mc_feedback_firewall"]["simulated_outcomes_may_update_state"] is False


# ---------------------------------------------------------------------------
# 15-17. FCS home-field advantage
# ---------------------------------------------------------------------------

def test_the_fcs_home_side_receives_exactly_plus_3_point_5():
    assert mdr1.venue_adjustment_points(neutral=False) == 3.5
    assert mdr1.GLOBAL_HOME_FIELD_ADVANTAGE_POINTS == 3.5
    assert mdr1.GLOBAL_HOME_FIELD_ADVANTAGE_POINTS == hfa.V3_FOOTBALL_POINT_HFA


def test_a_neutral_game_carries_a_zero_venue_adjustment():
    assert mdr1.venue_adjustment_points(neutral=True) == 0.0


def test_there_is_no_fcs_specific_hfa_fallback():
    """Refused for any modifier, including one that would change nothing.

    ``1.0`` is the value POWER_CRUNCH carries for every FBS team, so it is the
    most plausible thing to reach for. It is refused too: the point is that no
    per-team FCS modifier exists to be applied, not that its value is wrong.
    """
    for modifier in (1.0, 1.15, 0.85, 0.0):
        with pytest.raises(GovernanceBlock):
            mdr1.reject_fcs_specific_hfa(modifier)
    mdr1.reject_fcs_specific_hfa(None)
    assert mdr1.FCS_TEAM_SPECIFIC_HFA_PERMITTED is False


def test_the_venue_adjustment_signature_admits_no_team_argument():
    """A per-team argument is the seam a per-team modifier would enter through."""
    import inspect

    params = list(inspect.signature(mdr1.venue_adjustment_points).parameters)
    assert params == ["neutral"]


# ---------------------------------------------------------------------------
# 18-20. The FCS Elo -> points adapter
# ---------------------------------------------------------------------------

def test_fcs_elo_1250_cannot_be_used_directly_as_points():
    with pytest.raises(GovernanceBlock) as excinfo:
        mdr1.reject_elo_as_v3_points(1250.0)
    assert "cannot be used directly as V3 football points" in str(excinfo.value)
    assert mdr1.FCS_ELO == fcs.FCS_FIXED_ELO


def test_the_old_board_equivalents_are_refused_as_points():
    for equivalent in (0.294, 0.297, 0.297514):
        with pytest.raises(GovernanceBlock):
            mdr1.reject_elo_as_v3_points(equivalent)


def test_the_board_inverse_route_is_refused():
    with pytest.raises(GovernanceBlock) as excinfo:
        mdr1.reject_board_inverse_route()
    assert "refused" in str(excinfo.value)
    with pytest.raises(GovernanceBlock):
        mdr1.reject_forbidden_elo_population_source("BOARD_IH_PARTIAL_AXIS_INVERSION")


@pytest.mark.parametrize(
    "source",
    [
        "BOARD_IH_PARTIAL_AXIS_INVERSION",
        "HISTORICAL_2025_ELO",
        "REAL_WORLD_NCAA_DATA",
        "FABRICATED_ELO_BRIDGE",
        "PYTEST_FIXTURE",
    ],
)
def test_every_forbidden_elo_population_source_is_refused_by_name(source):
    with pytest.raises(GovernanceBlock):
        mdr1.reject_forbidden_elo_population_source(source)


def test_the_adapter_formula_uses_point_scale_14_point_0():
    """Verified by computing it, not by reading the string.

    A synthetic population with mean 1500 and population SD 176.7767 puts Elo
    1250 at z = -1.41421, so the adapter must return 14.0 * that. The source is
    named as a permitted one so the refusal path is not what is under test here.
    """
    population = [1250.0, 1375.0, 1500.0, 1625.0, 1750.0]
    result = mdr1.compute_fcs_adapter(
        population,
        sd_convention="POPULATION_SD_DDOF0",
        source="TEST_SYNTHETIC_POPULATION_NOT_A_GOVERNED_SOURCE",
    )
    assert result.fbs_elo_count == 5
    assert result.fbs_elo_mean == pytest.approx(1500.0)
    assert result.fbs_elo_sd == pytest.approx(176.7766952966369)
    assert result.point_scale == 14.0
    assert result.fcs_v3_points == pytest.approx(14.0 * result.fcs_elo_z)
    assert result.fcs_v3_points == pytest.approx(-19.79898987322333)


def test_the_sd_convention_must_be_stated_and_changes_the_answer():
    population = [1250.0, 1375.0, 1500.0, 1625.0, 1750.0]
    with pytest.raises(GovernanceBlock):
        mdr1.compute_fcs_adapter(population, sd_convention=None, source="X")
    with pytest.raises(GovernanceBlock):
        mdr1.compute_fcs_adapter(population, sd_convention="STDEV_S", source="X")
    pop = mdr1.compute_fcs_adapter(
        population, sd_convention="POPULATION_SD_DDOF0", source="X"
    )
    sample = mdr1.compute_fcs_adapter(
        population, sd_convention="SAMPLE_SD_DDOF1", source="X"
    )
    assert pop.fbs_elo_sd != sample.fbs_elo_sd


def test_an_elo_vector_supplied_without_a_named_source_is_refused():
    with pytest.raises(GovernanceBlock):
        mdr1.compute_fcs_adapter(
            [1400.0, 1500.0, 1600.0], sd_convention="POPULATION_SD_DDOF0"
        )


def test_a_missing_authoritative_elo_vector_fails_the_adapter_cleanly():
    """The live case. It fails closed and names the dependency."""
    assert mdr1.locate_governed_2026_fbs_elo_vector() is None
    with pytest.raises(GovernanceBlock) as excinfo:
        mdr1.compute_fcs_adapter()
    message = str(excinfo.value)
    assert mdr1.FCS_ADAPTER_INPUT_MISSING in message
    assert "2026 FBS Elo vector" in message
    assert mdr1.FCS_ADAPTER_STATUS == "FCS_ADAPTER_INPUT_ELO_VECTOR_MISSING"


def test_a_degenerate_elo_population_is_refused_rather_than_standardized():
    with pytest.raises(InputValidationError):
        mdr1.compute_fcs_adapter(
            [1500.0], sd_convention="POPULATION_SD_DDOF0", source="X"
        )
    with pytest.raises(InputValidationError):
        mdr1.compute_fcs_adapter(
            [1500.0] * 5, sd_convention="POPULATION_SD_DDOF0", source="X"
        )


def test_the_missing_adapter_does_not_invalidate_the_other_rulings(artifact):
    adapter = artifact["fcs_adapter"]
    assert adapter["status"] == "FCS_ADAPTER_INPUT_ELO_VECTOR_MISSING"
    assert adapter["blocks_other_rulings"] is False
    assert adapter["fbs_elo_vector_source"] is None
    assert adapter["fcs_v3_points"] is None
    assert adapter["point_scale"] == 14.0
    # Every other fixed value is still present and usable.
    assert artifact["fixed_values"]["blowout_margin_cap_points"] == 25.0
    assert artifact["fixed_values"]["point_scale"] == 14.0
    assert artifact["fixed_values"]["global_home_field_advantage_points"] == 3.5


def test_the_elo_vector_search_is_recorded_and_finds_nothing_usable(artifact):
    search = artifact["fcs_adapter"]["search"]
    assert len(search) >= 4
    assert all(entry["usable"] is False for entry in search)
    locations = " ".join(entry["location"] for entry in search)
    assert "Master Ratings" in locations
    assert "scheme_master_primary_elo" in locations


# ---------------------------------------------------------------------------
# 21-23. Authority boundaries
# ---------------------------------------------------------------------------

def test_sample_regularization_authority_remains_external_to_this_ruling(artifact):
    mdr1.assert_sample_size_regularization_not_decided_here()
    assert mdr1.SAMPLE_SIZE_REGULARIZATION_DECIDED_HERE is False
    assert mdr1.SAMPLE_SIZE_REGULARIZATION_AUTHORITY == "AGENT_3_SYNTHETIC_DOMAIN_EXPERIMENT"
    assert mdr1.classify_sample_size_regularization_result(True) == "SYNTHETIC_FIT_RESULT"
    assert (
        mdr1.classify_sample_size_regularization_result(False)
        == "BOUNDARY_OR_UNIDENTIFIED"
    )
    block = artifact["sample_size_regularization"]
    assert block["decided_by_this_ruling"] is False
    assert block["overwrite_permitted"] is False


def test_an_experimental_blowout_result_cannot_override_the_chairman_cap():
    """A better-fitting experimental cap still does not move the governed one."""
    for experimental in (18.0, 21.0, 28.0, 35.0, None):
        recorded = mdr1.classify_experimental_blowout_result(experimental)
        assert recorded["governed_cap_points"] == 25.0
        assert recorded["experimental_result_class"] == "DIAGNOSTIC_WITNESS"
        assert recorded["overrides_chairman_ruling"] is False
        assert recorded["experimental_cap_points"] == experimental
    assert mdr1.governed_blowout_cap_points() == 25.0


def test_no_parameter_is_falsely_marked_empirically_identified(artifact):
    for row in artifact["parameter_register"]:
        assert row["empirically_identified"] is False, row["parameter"]
        assert row["status"] != "EMPIRICALLY_IDENTIFIED", row["parameter"]
    assert artifact["empirically_identified_claims"] == []
    for axis in artifact["design_sweep"]["axes"].values():
        assert axis["empirically_identified"] is False
    with pytest.raises(GovernanceBlock):
        mdr1.reject_empirical_identification_claim("EMPIRICALLY_IDENTIFIED")
    with pytest.raises(GovernanceBlock):
        mdr1.reject_empirical_identification_claim("PROBABLY_FINE")


def test_the_selected_statuses_are_design_statuses_not_identification_claims(artifact):
    assert mdr1.COEFFICIENT_STATUS_AFTER_SWEEP == "FIXED_BY_V3_RESPONSIVENESS_DESIGN"
    assert mdr1.GAME_SD_STATUS_AFTER_SWEEP == "FIXED_BY_V3_SENSITIVITY_DESIGN"
    assert mdr1.RECENT_FORM_STATUS_AFTER_SWEEP == "FIXED_BY_V3_RESPONSIVENESS_DESIGN"
    assert "EMPIRICALLY_IDENTIFIED" not in artifact["permitted_statuses"]


# ---------------------------------------------------------------------------
# 25. Historical evidence stays auditable
# ---------------------------------------------------------------------------

def test_formal_historical_evidence_remains_auditable():
    """The prior records are still on disk and still readable.

    This round supersedes no artifact. Superseding one would be recorded in
    ``supersedes_artifacts``; editing one would be a rewrite, which is refused
    outright.
    """
    reference = ROOT / "reference" / "dynamic_weekly_mc_v3"
    for name in (
        "V3_GOVERNANCE_STATUS_R2.json",
        "V3_GOVERNANCE_STATUS_R3.json",
        "V3_GOVERNANCE_STATUS_R4.json",
        "V3_CALIBRATION_DATA_CONTRACT.json",
        "V3_CALIBRATION_EVIDENCE_DISCOVERY_R5.json",
        "V3_BOARD_IK_CUSTODY.json",
        "V3_BUILD_MANIFEST.json",
    ):
        path = reference / name
        assert path.exists(), name
        json.loads(path.read_text(encoding="utf-8"))


def test_this_round_supersedes_no_artifact_and_edits_no_history(artifact):
    supersession = artifact["supersession"]
    assert supersession["supersedes_artifacts"] == []
    assert supersession["superseded_records_are_preserved_unedited"] is True
    assert artifact["lane_actions"]["historical_evidence_edited"] is False
    assert artifact["lane_actions"]["agent_3_results_overwritten"] is False


def test_real_football_stays_an_external_witness(artifact):
    assert artifact["real_football_status"] == "EXTERNAL_WITNESS_ONLY"
    assert artifact["governing_domain"] == (
        "SYNTHETIC_2024_2025_PRIOR_INFORMATION_TO_SYNTHETIC_2026"
    )
    assert any(
        "EXTERNAL_WITNESS_ONLY" in r["decision"] for r in artifact["rulings"]
    )


def test_the_r2_r3_r4_governance_lineage_is_left_intact():
    """The model-design rulings are a separate lineage, not an edit of that one."""
    ids = {r.convergence_id for r in governance_rulings.ALL_RULINGS}
    assert not any(i.startswith("MDR1-") for i in ids)
    assert all(
        r.convergence_id.startswith("MDR1-") for r in mdr1.MODEL_DESIGN_R1_RULINGS
    )


# ---------------------------------------------------------------------------
# Game SD: a result-dispersion axis, not a rating-uncertainty one
# ---------------------------------------------------------------------------

def test_sigma_elo_68_is_refused_as_game_sd_points():
    with pytest.raises(GovernanceBlock) as excinfo:
        mdr1.reject_rating_state_uncertainty_as_game_sd(68.0)
    assert "rating-state uncertainty" in str(excinfo.value)
    with pytest.raises(GovernanceBlock):
        mdr1.game_sd_candidates(68.0)


def test_the_fallback_game_sd_grid_is_the_ruled_16_20_24():
    assert mdr1.game_sd_candidates() == {"LOW": 16.0, "MIDDLE": 20.0, "HIGH": 24.0}
    assert mdr1.GENERATOR_GAME_SD_POINTS is None
    assert mdr1.GAME_SD_SOURCE == "CHAIRMAN_FALLBACK_SENSITIVITY_GRID"


def test_a_generator_sd_would_scale_the_grid_by_0_80_1_00_1_20():
    """The generator branch is specified, not merely mentioned."""
    grid = mdr1.game_sd_candidates(15.0)
    assert grid == {"LOW": 12.0, "MIDDLE": 15.0, "HIGH": 18.0}


def test_the_generator_search_is_recorded_and_found_no_generator_sd(artifact):
    axis = artifact["design_sweep"]["axes"]["game_sd_points"]
    assert axis["generator_game_sd_points"] is None
    assert axis["source"] == "CHAIRMAN_FALLBACK_SENSITIVITY_GRID"
    assert len(axis["generator_provenance_search"]) >= 3
    witness_values = [w["value"] for w in axis["witnesses"]]
    assert 20.2 in witness_values
    assert 68.0 in witness_values
    refused = next(w for w in axis["witnesses"] if w["value"] == 68.0)
    assert refused["class"] == "REFUSED_WRONG_AXIS"


# ---------------------------------------------------------------------------
# Coefficient axis: reserved, never invented
# ---------------------------------------------------------------------------

def test_no_coefficient_value_is_invented_when_no_universe_exists():
    with pytest.raises(GovernanceBlock) as excinfo:
        mdr1.coefficient_candidates()
    assert mdr1.COEFFICIENT_UNIVERSE_MISSING in str(excinfo.value)


def test_the_absent_coefficient_universe_is_recorded_with_where_it_was_sought(artifact):
    axis = artifact["design_sweep"]["axes"]["coefficient"]
    assert axis["candidates_bound"] is False
    assert axis["candidate_values"] is None
    assert axis["candidate_slots"] == ["LOW", "MIDDLE", "HIGH"]
    assert axis["refusal_token"] == "COEFFICIENT_SEARCH_UNIVERSE_SOURCE_MISSING"
    searched = " ".join(entry["location"] for entry in axis["source_universe_search"])
    assert "calibration_regimes.json" in searched
    assert "v3_experimental.json" in searched


def test_the_mounted_regime_file_really_is_empty():
    """The refusal above is a finding about the repository, not a hardcoded mood."""
    regimes = json.loads(
        (
            ROOT / "config" / "dynamic_weekly_mc_v3" / "experimental"
            / "calibration_regimes.json"
        ).read_text(encoding="utf-8")
    )
    assert regimes["regimes"] == []


def test_a_supplied_universe_is_refined_deterministically_and_travels_with_its_source():
    universe = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40]
    assert mdr1.coefficient_candidates(universe) == (0.05, 0.20, 0.40)
    assert mdr1.coefficient_candidates(list(reversed(universe))) == (0.05, 0.20, 0.40)
    axis = mdr1.coefficient_axis_as_dict(universe)
    assert axis["source_universe"] == universe
    assert axis["candidates_bound"] is True
    with pytest.raises(GovernanceBlock):
        mdr1.coefficient_candidates([0.1, 0.2])


def test_the_qualitative_selection_rule_is_not_turned_into_a_number(artifact):
    axis = artifact["design_sweep"]["axes"]["coefficient"]
    assert axis["selection_threshold_numeric"] is None
    assert "lowest coefficient" in axis["selection_preference"]


def test_every_declared_sweep_diagnostic_is_present(artifact):
    axis = artifact["design_sweep"]["axes"]["coefficient"]
    required = {
        "mean_absolute_weekly_v3_point_movement",
        "sd_of_weekly_point_movement",
        "maximum_weekly_point_movement",
        "ten_slot_advisory_frequency",
        "sign_reversals_or_oscillation",
        "repeated_reversal_frequency",
        "blowout_cap_hit_frequency",
        "favorite_win_rate",
        "upset_rate",
        "undefeated_team_frequency",
        "conference_title_concentration",
        "cfp_concentration",
        "national_title_concentration",
        "probability_volatility",
    }
    assert required == set(axis["diagnostics_required"])
    sd_axis = artifact["design_sweep"]["axes"]["game_sd_points"]
    assert "tail_frequency" in sd_axis["diagnostics_required"]
    assert "probability_dispersion" in sd_axis["diagnostics_required"]


# ---------------------------------------------------------------------------
# The design matrix and the artifact itself
# ---------------------------------------------------------------------------

def test_the_design_matrix_is_3x3x3x500_and_is_not_a_production_run(artifact):
    sweep = artifact["design_sweep"]
    assert sweep["axis_sizes"] == {
        "coefficient": 3,
        "game_sd_points": 3,
        "recent_form_lambda": 3,
    }
    assert sweep["cells"] == 27
    assert sweep["paths_per_cell"] == 500
    assert sweep["total_simulated_paths"] == 13500
    assert sweep["workload_class"] == (
        "EXPERIMENT_WORKLOAD_NOT_A_PRODUCTION_SEASON_RUN"
    )
    assert sweep["random_number_policy"] == (
        "COMMON_RANDOM_NUMBERS_IDENTICAL_SEED_SCHEDULE"
    )
    assert sweep["executable_now"] is False
    assert mdr1.design_matrix_cells() == 13500


def test_this_lane_promoted_nothing_and_ran_nothing(artifact):
    actions = artifact["lane_actions"]
    assert actions["parameters_promoted"] == []
    assert actions["blockers_retired"] == []
    assert actions["blockers_opened"] == []
    assert actions["configuration_files_edited"] == []
    assert actions["season_simulation_run"] is False
    assert actions["dev_500_run"] is False
    assert actions["analysis_2000_run"] is False
    assert actions["publish_10000_run"] is False


def test_the_governed_configuration_is_untouched_by_this_lane():
    """The six calibration gates are still null and V3 is still blocked."""
    cfg = V3Config.from_json(CONFIG)
    assert cfg.calibration.blowout_treatment is None
    assert cfg.calibration.game_sd_points is None
    assert cfg.calibration.recent_form_weights is None
    assert cfg.calibration.weekly_performance_residual_coefficient is None
    assert cfg.calibration.sample_size_regularization is None
    assert cfg.calibration.weekly_movement_cap_points is None
    assert cfg.execution_blockers(), "V3 execution must remain blocked"


def test_the_artifact_carries_every_section_the_instruction_requires(artifact):
    for key in (
        "authority",
        "issued_by",
        "scope",
        "supersession",
        "fixed_values",
        "design_sweep",
        "parameter_register",
        "fcs_adapter",
        "fcs_hfa_policy",
        "preseason_decay_policy",
        "recent_form_policy",
        "mc_feedback_firewall",
        "weekly_loop",
        "prohibited_interpretations",
    ):
        assert key in artifact, key
    assert artifact["prohibited_interpretations"]
    assert artifact["weekly_loop"]["steady_state_first_week"] == 3
    assert artifact["weekly_loop"]["bootstrap"][0] == "PRESEASON_STATE"
    assert artifact["weekly_loop"]["steady_state"][-1] == "AWAIT_NEXT_REALIZED_RESULTS"


def test_the_artifact_does_not_self_reference_its_containing_commit(artifact):
    assert artifact["containing_commit_sha"] is None
    assert artifact["chairman_ruling_ids_supplied"] is False
    assert all(r["chairman_ruling_id"] is None for r in artifact["rulings"])


def test_the_committed_artifact_is_exactly_what_the_module_emits():
    """Bytes, not shape. The artifact and the code cannot drift apart."""
    with tempfile.TemporaryDirectory() as scratch:
        emitted = mdr1.write_rulings(Path(scratch) / "r1.json").read_bytes()
    assert emitted == ARTIFACT.read_bytes()
    assert b"\r" not in emitted


def test_repeated_artifact_emission_is_byte_stable(tmp_path):
    first = mdr1.write_rulings(tmp_path / "a.json").read_bytes()
    second = mdr1.write_rulings(tmp_path / "b.json").read_bytes()
    assert first == second


def test_every_ruling_carries_its_authority_and_no_invented_identifier():
    assert len(mdr1.MODEL_DESIGN_R1_RULINGS) == 17
    for ruling in mdr1.MODEL_DESIGN_R1_RULINGS:
        assert ruling.convergence_id.startswith("MDR1-")
        assert ruling.decision
        assert ruling.evidence
        assert ruling.provenance in ("FACT", "DERIVED")
        assert ruling.chairman_ruling_id is None
        assert ruling.instruction == mdr1.MDR1_INSTRUCTION
        assert ruling.resolution_reason == "DIRECT_CHAIRMAN_AUTHORITY"
        # This lane retires no blocker.
        assert ruling.retires == ()
    assert mdr1.ruling("MDR1-BLOWOUT-CAP-25").convergence_id == "MDR1-BLOWOUT-CAP-25"
    with pytest.raises(GovernanceBlock):
        mdr1.ruling("MDR1-NO-SUCH-RULING")
