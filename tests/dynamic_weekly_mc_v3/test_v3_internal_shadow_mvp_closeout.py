"""V3 INTERNAL / SHADOW / TEST_ONLY MVP model closeout.

What these tests are for is narrow: to prove that the three things the closeout
actually changed are what they claim to be, and that the two things it must not
have changed are unchanged.

Changed, and pinned here:

* FCS Elo 1250 maps to exactly -31.0 unified neutral-field points, through the
  fail-closed adapter and no other route.
* The six calibration values are promoted from bound control evidence, and the
  control corpus behind them is the byte-verified 757-game 2025 synthetic season.
* The INTERNAL_SHADOW_MVP configuration reaches zero execution blockers, and the
  pre-ruling configuration still reaches exactly eight.

Unchanged, and pinned here too:

* No artifact may claim real-world calibration. The MVP is
  SYNTHETIC_CONTROL_CALIBRATED and POST_MVP_REAL_WORLD_VALIDATION_REQUIRED stays
  in force.
* Weeks 1 and 2 still open on preseason strength, HFA is still exactly 3.5 at a
  home venue and exactly 0.0 at a neutral one, and no future information reaches
  a pregame prediction.

A test here that starts passing because a number was written into a config file
has been defeated rather than fixed: every gate below reads the registry that
checks evidence, not the field that records a result.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
    blocker_report,
    fcs,
    mvp_control,
    season_run,
    sos,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import DEFAULT_PRIOR_DECAY, V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.game import simulate_game
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.hfa import V3_FOOTBALL_POINT_HFA
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.models import ScheduledGame, TeamPathState
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.rerating import PromotedRegimeRerater
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.rulings import (
    R5_FCS_SCALE,
    R5_MVP_CONTROL_CORPUS,
    R5_POST_MVP_REAL_VALIDATION,
)

ROOT = Path(__file__).resolve().parents[2]
BASELINE_CONFIG = ROOT / "config" / "dynamic_weekly_mc_v3" / "v3_experimental.json"
MVP_CONFIG = ROOT / "config" / "dynamic_weekly_mc_v3" / "v3_internal_shadow_mvp.json"


@pytest.fixture(autouse=True)
def _no_governance_leaks():
    """No test may leave R5 governance installed for the next one."""
    fcs.clear_fcs_scale_adapter()
    fcs.clear_fcs_hfa_modifier()
    mvp_control.clear_calibration_promotion()
    yield
    fcs.clear_fcs_scale_adapter()
    fcs.clear_fcs_hfa_modifier()
    mvp_control.clear_calibration_promotion()


@pytest.fixture(scope="module")
def corpus():
    return mvp_control.load_control_corpus(ROOT)


@pytest.fixture(scope="module")
def calibration():
    """One full calibration pass, shared. Emitted artifacts go to a scratch path."""
    fcs.clear_fcs_scale_adapter()
    mvp_control.clear_calibration_promotion()
    return mvp_control.run_control_calibration(ROOT)


# ---------------------------------------------------------------------------
# Control-corpus provenance.
# ---------------------------------------------------------------------------


def test_control_corpus_is_the_byte_verified_authorised_artifact(corpus):
    source = corpus.source["corpus"]
    assert source["member_sha256"] == mvp_control.CONTROL_CORPUS_MEMBER[2]
    assert source["package_sha256"] == mvp_control.CONTROL_SOURCE_PACKAGES[source["package"]]
    assert source["bytes"] == 116602


def test_control_corpus_matches_every_authorised_declared_property(corpus):
    assert corpus.declared["total_games"] == 757
    assert corpus.declared["overtime_games"] == 13
    assert corpus.declared["phase_counts"] == {
        "Bowl": 21,
        "Conference Championship": 9,
        "Playoff": 13,
        "Regular Season": 714,
    }
    assert corpus.total_source_games == 757


def test_control_corpus_self_declaration_is_preserved_verbatim(corpus):
    assert corpus.declared["self_declaration"] == (
        "SCHEDULE SYNTHETIC. SCORES SIMULATED. NCG result user-specified. "
        "Bowl names fictional."
    )


def test_a_source_whose_bytes_moved_is_refused_at_mount(tmp_path):
    (tmp_path / mvp_control.CALIBRATION_SOURCES_DIR).mkdir(parents=True)
    package = (
        tmp_path
        / mvp_control.CALIBRATION_SOURCES_DIR
        / mvp_control.CONTROL_CORPUS_MEMBER[0]
    )
    package.write_bytes(b"not the audited bytes")
    with pytest.raises(GovernanceBlock, match="not the audited bytes|hashes to"):
        mvp_control.mount_member(mvp_control.CONTROL_CORPUS_MEMBER, root=tmp_path)


def test_an_absent_source_is_refused_rather_than_reconstructed(tmp_path):
    with pytest.raises(GovernanceBlock, match="does not reconstruct a corpus"):
        mvp_control.mount_member(mvp_control.CONTROL_CORPUS_MEMBER, root=tmp_path)


def test_games_without_a_preceding_season_rating_are_excluded_not_invented(corpus):
    assert corpus.excluded
    assert all(
        row["reason"] == "NO_PRECEDING_SEASON_RATING_FOR_PARTICIPANT"
        for row in corpus.excluded
    )
    excluded_ids = {row["game_id"] for row in corpus.excluded}
    assert not excluded_ids & {game.game_id for game in corpus.games}


# ---------------------------------------------------------------------------
# Expected margin: orientation, venue, domain.
# ---------------------------------------------------------------------------


def _state(points: float) -> TeamPathState:
    return TeamPathState(
        schedule_id="X",
        preseason_strength_points=points,
        current_strength_points=points,
        promoted_strength_points=points,
    )


def _game(venue: str) -> ScheduledGame:
    return ScheduledGame(
        game_id="G-TEST",
        week=3,
        date="2026-09-12",
        game_type="REG",
        home_team="H",
        away_team="A",
        home_conf="SEC",
        away_conf="SEC",
        venue=venue,
        conference_game=True,
        fcs_game=False,
        flex_rematch=False,
    )


@pytest.mark.parametrize(
    "venue,expected_venue_points",
    [("HOME", V3_FOOTBALL_POINT_HFA), ("NEUTRAL", 0.0)],
)
def test_expected_margin_is_strength_difference_plus_governed_venue_term(
    venue, expected_venue_points
):
    observation = simulate_game(
        base_seed=1,
        path_id=1,
        game=_game(venue),
        home=_state(12.0),
        away=_state(4.0),
        hfa_baseline_points=V3_FOOTBALL_POINT_HFA,
        home_hfa_modifier=1.0,
        game_sd_points=16.75,
        rating_state_version="v",
    )
    assert observation.home_field_points == pytest.approx(expected_venue_points)
    assert observation.expected_home_margin == pytest.approx(
        12.0 - 4.0 + expected_venue_points
    )


def test_neutral_venue_adjustment_is_exactly_zero_not_a_small_number():
    observation = simulate_game(
        base_seed=1,
        path_id=1,
        game=_game("NEUTRAL"),
        home=_state(0.0),
        away=_state(0.0),
        hfa_baseline_points=V3_FOOTBALL_POINT_HFA,
        home_hfa_modifier=1.0,
        game_sd_points=16.75,
        rating_state_version="v",
    )
    assert observation.home_field_points == 0.0


def test_subject_orientation_is_antisymmetric():
    """The away side's expected margin is the negation of the home side's."""
    observation = simulate_game(
        base_seed=7,
        path_id=2,
        game=_game("HOME"),
        home=_state(20.0),
        away=_state(-5.0),
        hfa_baseline_points=V3_FOOTBALL_POINT_HFA,
        home_hfa_modifier=1.0,
        game_sd_points=16.75,
        rating_state_version="v",
    )
    assert observation.performance_residual_away == pytest.approx(
        -observation.performance_residual_home
    )


def test_control_lane_expected_margin_matches_production_formula(corpus):
    """The calibration's predictor is the production one, checked game by game."""
    points_per_sd = mvp_control.fit_points_per_sd(corpus, mvp_control.TRAINING_STAGES)
    opening = mvp_control.opening_strength_for(corpus, points_per_sd)
    run = mvp_control.run_control_model(
        corpus,
        mvp_control.selected_regime(),
        opening,
        prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    for prediction in run.predictions[:200]:
        venue = 0.0 if prediction.neutral else V3_FOOTBALL_POINT_HFA
        assert prediction.venue_points == pytest.approx(venue)
        assert prediction.expected_home_margin == pytest.approx(
            prediction.home_strength - prediction.away_strength + venue
        )


def test_no_elo_magnitude_is_used_as_a_point_value():
    for magnitude in (fcs.FCS_FIXED_ELO, fcs.SUPERSEDED_OPERATOR_COMPOSITE_ELO):
        with pytest.raises(GovernanceBlock, match="different axis"):
            fcs.reject_elo_as_points(magnitude)


# ---------------------------------------------------------------------------
# Weeks 1-2, walk-forward, no leakage.
# ---------------------------------------------------------------------------


def test_weeks_one_and_two_are_predicted_from_opening_strength(corpus):
    points_per_sd = mvp_control.fit_points_per_sd(corpus, mvp_control.TRAINING_STAGES)
    opening = mvp_control.opening_strength_for(corpus, points_per_sd)
    run = mvp_control.run_control_model(
        corpus,
        mvp_control.selected_regime(),
        opening,
        prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    for prediction in run.predictions:
        if prediction.stage > 2:
            continue
        assert prediction.home_strength == pytest.approx(opening[prediction.home_team])
        assert prediction.away_strength == pytest.approx(opening[prediction.away_team])


def test_strength_moves_only_after_the_first_promoted_rerating(corpus):
    points_per_sd = mvp_control.fit_points_per_sd(corpus, mvp_control.TRAINING_STAGES)
    opening = mvp_control.opening_strength_for(corpus, points_per_sd)
    run = mvp_control.run_control_model(
        corpus,
        mvp_control.selected_regime(),
        opening,
        prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    moved = {
        prediction.home_team
        for prediction in run.predictions
        if prediction.stage == 3
        and prediction.home_strength != pytest.approx(opening[prediction.home_team])
    }
    assert moved, "no team's strength moved by week 3"


def test_strength_is_frozen_after_championship_saturday(corpus):
    """Post-selection games consume the frozen state and produce no movement."""
    points_per_sd = mvp_control.fit_points_per_sd(corpus, mvp_control.TRAINING_STAGES)
    opening = mvp_control.opening_strength_for(corpus, points_per_sd)
    regime = mvp_control.selected_regime()
    run = mvp_control.run_control_model(
        corpus,
        regime,
        opening,
        prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    postseason_stage = mvp_control.POSTSEASON_STAGE
    by_team: dict[str, set[float]] = {}
    for prediction in run.predictions:
        if prediction.stage != postseason_stage:
            continue
        by_team.setdefault(prediction.home_team, set()).add(prediction.home_strength)
        by_team.setdefault(prediction.away_team, set()).add(prediction.away_strength)
    assert by_team
    assert all(len(values) == 1 for values in by_team.values())


def test_a_prediction_never_consumes_its_own_or_a_later_result(corpus):
    """Re-running with every result after a stage negated leaves that stage's
    predictions bit-identical. A predictor that read the future could not."""
    points_per_sd = mvp_control.fit_points_per_sd(corpus, mvp_control.TRAINING_STAGES)
    opening = mvp_control.opening_strength_for(corpus, points_per_sd)
    regime = mvp_control.selected_regime()
    baseline = mvp_control.run_control_model(
        corpus,
        regime,
        opening,
        prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    tampered_games = tuple(
        game
        if game.stage <= 6
        else replace(game, home_points=game.away_points, away_points=game.home_points)
        for game in corpus.games
    )
    tampered = mvp_control.run_control_model(
        replace(corpus, games=tampered_games),
        regime,
        opening,
        prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    before = [p for p in baseline.predictions if p.stage <= 6]
    after = [p for p in tampered.predictions if p.stage <= 6]
    assert [p.expected_home_margin for p in before] == [
        p.expected_home_margin for p in after
    ]


def test_the_control_season_final_rating_layer_is_never_a_pregame_feature(corpus):
    """Perturbing the 2025 witness layer cannot move a single prediction."""
    points_per_sd = mvp_control.fit_points_per_sd(corpus, mvp_control.TRAINING_STAGES)
    opening = mvp_control.opening_strength_for(corpus, points_per_sd)
    regime = mvp_control.selected_regime()
    baseline = mvp_control.run_control_model(
        corpus, regime, opening, prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    perturbed = mvp_control.run_control_model(
        replace(corpus, witness_ratings={k: v * 3.0 for k, v in corpus.witness_ratings.items()}),
        regime, opening, prior_decay=DEFAULT_PRIOR_DECAY,
        first_promoted_rerating_after_week=2,
    )
    assert [p.expected_home_margin for p in baseline.predictions] == [
        p.expected_home_margin for p in perturbed.predictions
    ]


def test_splits_are_temporally_ordered_and_never_randomly_assigned(calibration):
    integrity = calibration.report["splits"]["temporal_integrity"]
    assert integrity["assignment"] == "TEMPORAL_ONLY"
    assert integrity["leak_free"] is True
    assert calibration.report["splits"]["random_assignment_used"] is False


# ---------------------------------------------------------------------------
# Determinism.
# ---------------------------------------------------------------------------


def test_the_control_calibration_is_deterministic(corpus):
    regime = mvp_control.selected_regime()
    points_per_sd = mvp_control.fit_points_per_sd(corpus, mvp_control.TRAINING_STAGES)
    opening = mvp_control.opening_strength_for(corpus, points_per_sd)
    runs = [
        mvp_control.run_control_model(
            corpus, regime, opening, prior_decay=DEFAULT_PRIOR_DECAY,
            first_promoted_rerating_after_week=2,
        )
        for _ in range(2)
    ]
    assert runs[0].final_strength == runs[1].final_strength
    assert [p.residual for p in runs[0].predictions] == [
        p.residual for p in runs[1].predictions
    ]


def test_the_promoted_rerater_reproduces_the_calibrated_update():
    """Production and calibration read one definition of the weekly delta."""
    config = V3Config.from_json(MVP_CONFIG)
    rerater = PromotedRegimeRerater.from_config(config)
    regime = mvp_control.selected_regime()
    state = TeamPathState(
        schedule_id="T",
        preseason_strength_points=5.0,
        current_strength_points=5.0,
        promoted_strength_points=5.0,
        games_played=6,
        residual_history=[8.0, -3.0, 40.0, 1.5],
    )
    produced = rerater.rerate(week_completed=7, states={"T": state}, config=config)["T"]
    _uncapped, delta = mvp_control.weekly_delta(
        regime, residual_history=state.residual_history, games_played=state.games_played
    )
    assert produced == pytest.approx(5.0 + delta)


def test_the_promoted_rerater_refuses_an_uncalibrated_configuration():
    config = V3Config.from_json(BASELINE_CONFIG)
    with pytest.raises(GovernanceBlock, match="unresolved calibration values"):
        PromotedRegimeRerater.from_config(config)


# ---------------------------------------------------------------------------
# The FCS scale adapter.
# ---------------------------------------------------------------------------


def test_fcs_elo_1250_returns_exactly_minus_thirty_one():
    fcs.install_governed_fcs_scale_adapter()
    assert fcs.require_fcs_unified_points() == -31.0
    assert fcs.active_fcs_scale_adapter().source_elo == 1250.0


def test_the_adapter_is_bound_to_the_ruling_that_issued_it():
    adapter = fcs.install_governed_fcs_scale_adapter()
    assert adapter.derivation == "DIRECT_CHAIRMAN_AUTHORITY"
    assert adapter.provenance.issued is True
    assert R5_FCS_SCALE.convergence_id in adapter.provenance.locator


def test_a_missing_adapter_still_fails_closed():
    assert fcs.active_fcs_scale_adapter() is None
    with pytest.raises(GovernanceBlock, match="model-scale adapter"):
        fcs.require_fcs_unified_points()


def test_registration_without_the_approval_token_is_refused():
    with pytest.raises(GovernanceBlock, match="no human approval token"):
        fcs.register_fcs_scale_adapter(fcs.GOVERNED_FCS_SCALE_ADAPTER, approval_token=None)


def test_a_malformed_approval_token_is_refused():
    with pytest.raises(GovernanceBlock, match="malformed"):
        fcs.install_governed_fcs_scale_adapter(approval_token="APPROVED")


@pytest.mark.parametrize(
    "derivation",
    ["BOARD_IH_INVERSE", "BOARD_EQUIVALENT", "ELO_AS_POINTS", "V2_1_BRIDGE_REPLAY", "AD_HOC"],
)
def test_the_previously_refused_routes_are_still_refused(derivation):
    candidate = replace(fcs.GOVERNED_FCS_SCALE_ADAPTER, derivation=derivation)
    with pytest.raises(GovernanceBlock, match="refused as a"):
        fcs.register_fcs_scale_adapter(
            candidate, approval_token=fcs.FCS_SCALE_APPROVAL_TOKEN
        )


def test_the_ruled_value_is_not_a_board_inversion_or_an_elo():
    fcs.reject_board_derived_conversion(-31.0)
    fcs.reject_elo_as_points(-31.0)


def test_a_neutral_fcs_matchup_uses_minus_thirty_one_before_any_venue_handling():
    fcs.install_governed_fcs_scale_adapter()
    points = fcs.require_fcs_unified_points()
    observation = simulate_game(
        base_seed=3,
        path_id=1,
        game=_game("NEUTRAL"),
        home=_state(10.0),
        away=_state(points),
        hfa_baseline_points=V3_FOOTBALL_POINT_HFA,
        home_hfa_modifier=1.0,
        game_sd_points=16.75,
        rating_state_version="v",
    )
    assert observation.away_strength_points == -31.0
    assert observation.home_field_points == 0.0
    assert observation.expected_home_margin == pytest.approx(10.0 - (-31.0))


def test_the_adapter_embeds_no_home_field_advantage():
    """Home and away differ by exactly twice the governed HFA, never more."""
    fcs.install_governed_fcs_scale_adapter()
    fcs.install_governed_fcs_hfa_modifier()
    points = fcs.require_fcs_unified_points()
    at_home = simulate_game(
        base_seed=3, path_id=1, game=_game("HOME"), home=_state(points), away=_state(10.0),
        hfa_baseline_points=V3_FOOTBALL_POINT_HFA, home_hfa_modifier=1.0,
        game_sd_points=16.75, rating_state_version="v",
    )
    on_the_road = simulate_game(
        base_seed=3, path_id=1, game=_game("HOME"), home=_state(10.0), away=_state(points),
        hfa_baseline_points=V3_FOOTBALL_POINT_HFA, home_hfa_modifier=1.0,
        game_sd_points=16.75, rating_state_version="v",
    )
    fcs_relative_at_home = at_home.expected_home_margin
    fcs_relative_on_road = -on_the_road.expected_home_margin
    assert fcs_relative_at_home - fcs_relative_on_road == pytest.approx(
        2 * V3_FOOTBALL_POINT_HFA
    )


def test_the_venue_clause_refuses_a_bespoke_fcs_home_field_advantage():
    with pytest.raises(GovernanceBlock, match="does not authorise a bespoke"):
        fcs.install_governed_fcs_hfa_modifier(modifier=1.5)


def test_the_fcs_home_field_modifier_still_fails_closed_until_installed():
    with pytest.raises(GovernanceBlock, match="no governed home-field modifier"):
        fcs.require_fcs_hfa_modifier(None, "EMU")


def test_the_fbs_path_is_unchanged_by_the_adapter():
    """An FBS team's strength and venue term do not depend on the adapter."""
    def margin() -> float:
        return simulate_game(
            base_seed=5, path_id=1, game=_game("HOME"), home=_state(18.0), away=_state(2.0),
            hfa_baseline_points=V3_FOOTBALL_POINT_HFA, home_hfa_modifier=1.0,
            game_sd_points=16.75, rating_state_version="v",
        ).expected_home_margin

    before = margin()
    fcs.install_governed_fcs_scale_adapter()
    assert margin() == before


# ---------------------------------------------------------------------------
# Promotion and the game-SD gate.
# ---------------------------------------------------------------------------


def test_the_promotion_is_bound_to_registered_bytes_and_a_measured_experiment(calibration):
    assert calibration.promotion["evidence_bound"] is True
    assert calibration.promotion["bound_dataset_sha256"] == calibration.dataset.sha256
    assert calibration.promotion["evidence"]["split"] == "holdout"
    assert calibration.promotion["promotion_authority"] == "GOVERNED_CALIBRATION_EVIDENCE"
    assert calibration.promotion["writes_canonical_config"] is False


def test_the_promotion_names_both_the_criterion_ruling_and_the_corpus_ruling(calibration):
    assert calibration.promotion["ruling"] == "R2-CAL-OBJECTIVE"
    assert calibration.promotion["mvp_ruling"] == R5_MVP_CONTROL_CORPUS.convergence_id
    assert calibration.promotion["post_mvp_ruling"] == (
        R5_POST_MVP_REAL_VALIDATION.convergence_id
    )


def test_the_game_sd_gate_is_closed_until_a_promotion_is_installed():
    assert mvp_control.game_sd_calibration_governed() is False


def test_the_game_sd_gate_opens_only_for_a_bound_mvp_promotion(calibration):
    mvp_control.install_calibration_promotion(calibration.promotion)
    assert mvp_control.game_sd_calibration_governed() is True


def test_an_unbound_promotion_record_cannot_open_the_game_sd_gate(calibration):
    record = dict(calibration.promotion)
    record["evidence_bound"] = False
    with pytest.raises(GovernanceBlock, match="not bound"):
        mvp_control.install_calibration_promotion(record)


def test_a_promotion_measured_off_the_holdout_cannot_open_the_gate(calibration):
    record = dict(calibration.promotion)
    record["evidence"] = dict(record["evidence"], split="validation")
    with pytest.raises(GovernanceBlock, match="holdout split"):
        mvp_control.install_calibration_promotion(record)


def test_a_promotion_that_drops_the_post_mvp_requirement_is_refused(calibration):
    record = dict(calibration.promotion)
    record["real_world_validation"] = "SATISFIED"
    with pytest.raises(GovernanceBlock, match="POST_MVP_REAL_WORLD_VALIDATION_REQUIRED"):
        mvp_control.install_calibration_promotion(record)


def test_game_sd_is_the_measured_residual_dispersion_not_the_unconditional_spread(
    calibration,
):
    report = calibration.report["game_sd"]
    unconditional = calibration.report["diagnostics"]["unconditional_margin_dispersion"]
    assert report["selected_points"] == pytest.approx(
        report["measured_holdout_rms_points"], abs=0.01
    )
    assert unconditional["is_game_sd_points"] is False
    assert report["selected_points"] < unconditional[
        "control_corpus_signed_margin_sd_points"
    ]
    assert report["legacy_recorded_value_promoted"] is False


def test_the_promoted_values_are_exactly_what_the_mvp_configuration_carries(calibration):
    config = json.loads(MVP_CONFIG.read_text(encoding="utf-8"))
    assert config["calibration"] == calibration.regime.values()


def test_the_baseline_configuration_still_carries_no_calibration_values():
    config = json.loads(BASELINE_CONFIG.read_text(encoding="utf-8"))
    assert all(value is None for value in config["calibration"].values())


# ---------------------------------------------------------------------------
# Labelling.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("label", mvp_control.FORBIDDEN_CALIBRATION_LABELS)
def test_no_artifact_may_claim_real_world_calibration(label):
    with pytest.raises(GovernanceBlock, match="authorises"):
        mvp_control.assert_not_real_world_labelled({"status": label})


def test_the_calibration_record_carries_the_mvp_scope_and_nothing_stronger(calibration):
    governance = calibration.report["governance"]
    assert governance["scope"] == "INTERNAL_SHADOW_TEST_ONLY_MVP"
    assert governance["calibration_evidence"] == "SYNTHETIC_CONTROL_CALIBRATED"
    assert governance["real_world_validation"] == "POST_MVP_REAL_WORLD_VALIDATION_REQUIRED"
    mvp_control.assert_not_real_world_labelled(calibration.report)


def test_the_post_mvp_ruling_retires_no_blocker():
    assert R5_POST_MVP_REAL_VALIDATION.retires == ()


def test_the_real_world_contract_is_left_unedited():
    """The historical-corpus contract still refuses synthetic content."""
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_contract

    assert calibration_contract.DATASET_PROVENANCE_REQUIREMENTS["synthetic_content"].startswith(
        "REFUSED"
    )
    assert calibration_contract.MINIMUM_VOLUME_REQUIREMENTS["minimum_distinct_seasons"] == 3


def test_no_market_or_public_money_signal_enters_the_control_corpus(calibration):
    columns = {c.lower() for c in calibration.dataset.columns}
    assert not columns & set(mvp_control.cal.FORBIDDEN_DATASET_SIGNALS)
    assert calibration.report["objective"]["market_or_public_money_inputs"] is False


def test_the_witnesses_are_reported_independently_and_never_blended(calibration):
    witnesses = calibration.report["witnesses"]
    assert witnesses["colley_matrix"]["blended_into_primary_criterion"] is False
    assert witnesses["srs"]["blended_into_primary_criterion"] is False
    with pytest.raises(GovernanceBlock):
        mvp_control.cal.reject_witness_composite(["baxter", "srs"])


def test_the_witnesses_do_not_materially_conflict_with_the_selected_ratings(calibration):
    witnesses = calibration.report["witnesses"]
    for name in ("colley_matrix", "srs", "external_rating_layer_2025"):
        correlation = witnesses[name]["rank_correlation_with_selected_control_ratings"]
        assert correlation > 0.75, f"{name} rank correlation {correlation}"


# ---------------------------------------------------------------------------
# Blocker state.
# ---------------------------------------------------------------------------


def test_the_pre_ruling_configuration_still_carries_exactly_eight_blockers():
    report = DynamicWeeklyMCV3(V3Config.from_json(BASELINE_CONFIG)).preflight()
    assert set(report["execution_blockers"]) == set(
        blocker_report.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    )
    assert len(report["execution_blockers"]) == 8


def test_the_mvp_configuration_reaches_zero_blockers_once_governance_is_installed(
    calibration,
):
    fcs.install_governed_fcs_scale_adapter()
    fcs.install_governed_fcs_hfa_modifier()
    mvp_control.install_calibration_promotion(calibration.promotion)
    report = DynamicWeeklyMCV3(V3Config.from_json(MVP_CONFIG)).preflight()
    assert report["execution_blockers"] == []


def test_the_mvp_configuration_is_still_blocked_without_the_installed_governance():
    """Writing the six values into a config file clears nothing on its own."""
    report = DynamicWeeklyMCV3(V3Config.from_json(MVP_CONFIG)).preflight()
    assert set(report["execution_blockers"]) == {
        "governance.GAME_SD_CALIBRATION_OPEN",
        "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
    }


def test_every_retired_blocker_names_the_ruling_that_retired_it():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import rulings

    mapping = rulings.retirable_blockers()
    for blocker in R5_MVP_CONTROL_CORPUS.retires:
        assert mapping[blocker] == R5_MVP_CONTROL_CORPUS.convergence_id
    for blocker in R5_FCS_SCALE.retires:
        assert mapping[blocker] == R5_FCS_SCALE.convergence_id


def test_the_mvp_blocker_delta_is_computed_and_internally_consistent():
    delta = blocker_report.internal_shadow_mvp_delta()
    assert delta["scope"] == "INTERNAL_SHADOW_TEST_ONLY_MVP"
    assert delta["before_count"] == 8
    assert delta["after_count"] == 0
    assert delta["retired_count"] == 8
    assert delta["opened"] == []
    assert delta["set_equality_before_equals_retired_plus_after"] is True
    assert set(delta["difference"]) == set(delta["retired"])
    # The formal global register is untouched: global closure still needs the
    # real-world validation ruling R-V3-POST-MVP-REAL-VALIDATION-01 keeps open.
    assert delta["formal_global_scope"]["live_count"] == 8
    assert delta["formal_global_scope"]["unchanged_by_r5"] is True
    assert "POST_MVP_REAL_WORLD_VALIDATION_REQUIRED" in delta["carried_forward"]


# ---------------------------------------------------------------------------
# Season execution.
# ---------------------------------------------------------------------------


def test_the_indexed_ledger_agrees_exactly_with_the_governed_one():
    """The fast accessors must not become a second SOS implementation."""
    rows = [
        sos.GameResult(game_id=f"G{i}", week=(i % 5) + 1, team=f"T{i % 7}",
                       opponent=f"T{(i + 3) % 7}", won=(i % 3 == 0))
        for i in range(60)
    ]
    rows += [
        sos.GameResult(game_id=r.game_id, week=r.week, team=r.opponent,
                       opponent=r.team, won=not r.won)
        for r in rows
    ]
    semantics = sos.governed_sos_semantics(frozenset())
    slow = sos.ResumeLedger(rows)
    fast = season_run.IndexedResumeLedger(rows)
    for team in slow.teams():
        assert fast.record(team) == slow.record(team)
        assert sos.strength_of_schedule(fast, team, semantics) == pytest.approx(
            sos.strength_of_schedule(slow, team, semantics)
        )


def test_the_committee_board_consults_no_football_strength_value():
    """The fourth board key is the governed SOS, never a rating."""
    import inspect

    source = inspect.getsource(season_run.build_board)
    assert "strength_of_schedule" in source
    assert "final_strength" not in source
    assert "current_strength_points" not in source
    assert "COMMITTEE-TB3_STRENGTH_OF_SCHEDULE" in season_run.BOARD_TIEBREAKS_CONSULTED


def test_the_tier_register_is_unchanged_by_the_closeout():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import run_tier as tier_policy

    assert tier_policy.APPROVED_PATH_COUNTS == (500, 2000, 10000)
    assert tier_policy.PUBLISH.publish_freeze is True
    assert tier_policy.DEV.publish_freeze is False
    assert tier_policy.ANALYSIS.publish_freeze is False


def test_the_parameter_set_hash_ignores_the_path_count(calibration):
    """DEV and PUBLISH must share a model; only the sample size differs."""
    fcs.install_governed_fcs_scale_adapter()
    mvp_control.install_calibration_promotion(calibration.promotion)
    config = V3Config.from_json(MVP_CONFIG)
    assert season_run.parameter_set_hash(
        replace(config, paths=500)
    ) == season_run.parameter_set_hash(replace(config, paths=10000))


def test_one_season_path_is_deterministic_and_structurally_governed(calibration):
    fcs.install_governed_fcs_scale_adapter()
    fcs.install_governed_fcs_hfa_modifier()
    mvp_control.install_calibration_promotion(calibration.promotion)
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3.inputs import (
        load_schedule,
        load_teams,
    )

    config = V3Config.from_json(MVP_CONFIG)
    engine = DynamicWeeklyMCV3(config, rerater=PromotedRegimeRerater.from_config(config))
    teams = load_teams(
        config.inputs.canonical_master_md, config.inputs.unified_preseason_ratings_xlsx
    )
    schedule = load_schedule(config.inputs.schedule_xlsx)
    divisions = season_run._aac_divisions(config)
    semantics = sos.governed_sos_semantics(
        frozenset(s for s, t in teams.items() if t.entity_scope == "SCHEDULE_ONLY_FCS")
    )
    runs = [
        season_run.simulate_season_path(
            engine, path_id=4, teams=teams, schedule=schedule,
            division_of=divisions, semantics=semantics,
        )
        for _ in range(2)
    ]
    assert runs[0].national_champion == runs[1].national_champion
    assert runs[0].cfp_seeds == runs[1].cfp_seeds
    assert sorted(runs[0].cfp_seeds) == list(range(1, 15))
    assert len(set(runs[0].cfp_seeds.values())) == 14
    fcs_entities = {s for s, t in teams.items() if t.entity_scope == "SCHEDULE_ONLY_FCS"}
    assert not set(runs[0].cfp_seeds.values()) & fcs_entities
    assert runs[0].national_champion in set(runs[0].cfp_seeds.values())


# ---------------------------------------------------------------------------
# The executed run record.
# ---------------------------------------------------------------------------

RUN_RECORD = (
    ROOT
    / "reference"
    / "dynamic_weekly_mc_v3"
    / "mvp_control"
    / "V3_MVP_SIMULATION_RUNS_R1.json"
)


@pytest.fixture(scope="module")
def run_record():
    return json.loads(RUN_RECORD.read_text(encoding="utf-8"))


def test_all_three_governed_tiers_completed_in_ascending_order(run_record):
    tiers = run_record["tiers"]
    assert [t["tier"] for t in tiers] == ["DEV", "ANALYSIS", "PUBLISH"]
    assert [t["paths"] for t in tiers] == [500, 2000, 10000]
    assert all(t["status"] == "COMPLETE" for t in tiers)
    assert all(t["validation"]["passed"] for t in tiers)


def test_only_the_publish_tier_is_publish_or_freeze_eligible(run_record):
    assert run_record["publish_freeze_eligible_tiers"] == ["PUBLISH"]


def test_the_three_tiers_ran_one_model_and_differ_only_in_sample_size(run_record):
    assert run_record["same_model_semantics_across_tiers"] is True
    assert len(run_record["shared_parameter_set_hash"]) == 1
    hashes = {t["parameter_set_hash"] for t in run_record["tiers"]}
    assert len(hashes) == 1
    assert len({t["input_manifest_hash"] for t in run_record["tiers"]}) == 1
    assert len({t["output_hash"] for t in run_record["tiers"]}) == 3


def test_every_tier_reconciles_its_structural_column_totals(run_record):
    for tier in run_record["tiers"]:
        validation = tier["validation"]
        assert validation["governed_column_totals_reconcile"] is True
        assert validation["probability_columns_within_unit_interval"] is True
        assert validation["championship_probability_total"] == pytest.approx(1.0)
        assert validation["cfp_field_size_invariant"] == 14
        assert validation["fbs_members"] == 121
        assert validation["schedule_only_fcs"] == 13
        assert validation["schedule_entities"] == 134
        assert validation["schedule_only_fcs_remained_non_fbs"] is True


def test_the_run_record_takes_no_value_bearing_action(run_record):
    assert run_record["value_bearing"] is False
    assert run_record["market_action_taken"] is False
    assert run_record["deployment_performed"] is False
    assert run_record["scope"] == "INTERNAL_SHADOW_TEST_ONLY_MVP"
    assert run_record["calibration_evidence"] == "SYNTHETIC_CONTROL_CALIBRATED"
    assert run_record["real_world_validation"] == (
        "POST_MVP_REAL_WORLD_VALIDATION_REQUIRED"
    )
    mvp_control.assert_not_real_world_labelled(run_record)


def test_the_fcs_adapter_in_the_run_record_carries_the_ruled_value(run_record):
    scale = run_record["fcs_scale"]
    assert scale["unified_neutral_field_points"] == -31.0
    assert scale["fcs_elo"] == 1250.0
    assert scale["embeds_home_field_advantage"] is False
    assert run_record["fcs_venue_clause"]["double_hfa"] is False
    assert run_record["fcs_venue_clause"]["applied_at_neutral_venue"] is False


def test_a_path_result_does_not_depend_on_the_tier_it_was_drawn_in(calibration):
    """Path 17 must be identical whether 500 or 10,000 paths accompany it."""
    fcs.install_governed_fcs_scale_adapter()
    fcs.install_governed_fcs_hfa_modifier()
    mvp_control.install_calibration_promotion(calibration.promotion)
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3.inputs import (
        load_schedule,
        load_teams,
    )

    base = V3Config.from_json(MVP_CONFIG)
    teams = load_teams(
        base.inputs.canonical_master_md, base.inputs.unified_preseason_ratings_xlsx
    )
    schedule = load_schedule(base.inputs.schedule_xlsx)
    divisions = season_run._aac_divisions(base)
    semantics = sos.governed_sos_semantics(
        frozenset(s for s, t in teams.items() if t.entity_scope == "SCHEDULE_ONLY_FCS")
    )
    produced = []
    for path_count in (500, 10000):
        config = replace(base, paths=path_count)
        engine = DynamicWeeklyMCV3(
            config, rerater=PromotedRegimeRerater.from_config(config)
        )
        produced.append(
            season_run.simulate_season_path(
                engine, path_id=17, teams=teams, schedule=schedule,
                division_of=divisions, semantics=semantics,
            )
        )
    assert produced[0].national_champion == produced[1].national_champion
    assert produced[0].cfp_seeds == produced[1].cfp_seeds
    assert [o.simulated_home_margin for o in produced[0].observations] == [
        o.simulated_home_margin for o in produced[1].observations
    ]


def test_the_blocker_state_record_matches_the_computed_register():
    record = json.loads(
        (
            ROOT / "reference" / "dynamic_weekly_mc_v3" / "mvp_control"
            / "V3_MVP_BLOCKER_STATE_R1.json"
        ).read_text(encoding="utf-8")
    )
    assert record["measured_matches_register"] is True
    assert len(record["measured_before"]) == 8
    assert record["measured_after"] == []
    assert len(record["measured_retired"]) == 8
    assert record["formal_global_scope_blockers"]["live_count"] == 8
    assert record["real_world_validation"] == "POST_MVP_REAL_WORLD_VALIDATION_REQUIRED"
