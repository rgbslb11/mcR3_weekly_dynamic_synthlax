"""The FCS point-scale research harness, and the refusals that keep it honest.

Every observation in this file is a **fixture**. Not one of them is evidence,
none is offered toward the adapter, and the FCS baselines that appear in the
recovery tests are values the fixtures were built around, not measurements. The
distinction is the whole reason the harness refuses an unbound corpus: a
harness that could be satisfied by numbers a test invented would prove only that
it can be satisfied.

What is under test, then, is the machinery and its refusals — that the search is
deterministic and coarse-to-fine, that a boundary optimum is reported as one
rather than returned as an answer, that a missing venue or a missing pregame FBS
point state stops the fit instead of being defaulted, and that no path through
the module promotes anything.
"""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import fcs
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import fcs_scale_research as research
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.hfa import V3_FOOTBALL_POINT_HFA

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = (
    ROOT / "reference" / "dynamic_weekly_mc_v3" / research.RESULT_ARTIFACT_NAME
)

#: The baseline the recovery fixtures are constructed around. A fixture
#: constant, deliberately not a round number and deliberately not a candidate.
FIXTURE_BASELINE = -18.0


def observation(
    index: int,
    *,
    season: int = 2021,
    week: int = 1,
    venue: str | None = "HOME",
    fbs_points: float | None = 0.0,
    margin: int = 20,
    **overrides: object,
) -> research.FbsVsFcsObservation:
    """One fixture observation, with every governed field supplied by default."""
    fields: dict[str, object] = {
        "game_id": f"FIXTURE-{index:04d}",
        "season": season,
        "week": week,
        "order_key": f"{season}-09-{week:02d}T18:00:00+00:00",
        "fbs_team": f"FBS{index % 11}",
        "fcs_team": f"FCS{index % 5}",
        "fbs_score": 21 + margin,
        "fcs_score": 21,
        "source_provenance": "FIXTURE_NOT_EVIDENCE",
        "fbs_pregame_points": fbs_points,
        "strength_domain": research.GOVERNED_STRENGTH_DOMAIN,
        "venue": venue,
        "venue_classification_source": "FIXTURE_VENUE_AUTHORITY",
        "hfa_baseline_points": V3_FOOTBALL_POINT_HFA,
        "home_hfa_modifier": 1.0,
    }
    fields.update(overrides)
    return research.FbsVsFcsObservation(**fields)  # type: ignore[arg-type]


def recovery_fixture() -> list[research.FbsVsFcsObservation]:
    """Twenty-four fixture games built exactly around :data:`FIXTURE_BASELINE`.

    The residuals are a fixed, zero-sum pattern rather than a draw, so the whole
    fixture is reproducible without an RNG — this lane runs no sampling of any
    kind and its tests should not either.
    """
    pattern = (3, -5, 2, 0, -2, 7, -4, 1, 6, -3, -1, -4)
    rows: list[research.FbsVsFcsObservation] = []
    for i in range(24):
        venue = ("HOME", "HOME", "AWAY", "NEUTRAL", "HOME", "HOME")[i % 6]
        fbs_points = -10.0 + 2.0 * (i % 11)
        sign = research.VENUE_SIGN[venue]
        expected = fbs_points - FIXTURE_BASELINE + sign * V3_FOOTBALL_POINT_HFA
        rows.append(
            observation(
                i,
                season=2021 + i // 6,
                week=1 + (i % 3),
                venue=venue,
                fbs_points=fbs_points,
                margin=int(round(expected)) + pattern[i % 12],
            )
        )
    return rows


# ---------------------------------------------------------------------------
# The invariants this lane must not move.
# ---------------------------------------------------------------------------

def test_the_fixed_fcs_elo_is_1250_and_is_read_from_the_governed_module():
    assert research.assert_fcs_elo_invariant() == 1250.0
    assert fcs.FCS_FIXED_ELO == 1250.0
    # Read, not restated. A second literal here would let the two drift apart.
    source = inspect.getsource(research)
    assert "FCS_FIXED_ELO = " not in source


def test_the_research_result_records_the_elo_as_unchanged():
    payload = research.fcs_scale_research_result()
    assert payload["governance"]["fcs_elo"] == 1250.0
    assert payload["governance"]["fcs_elo_changed"] is False
    assert payload["governance"]["fcs_translation_policy"] == "FIXED_ELO_1250"


@pytest.mark.parametrize("forbidden", [0.294, 0.297, 0.297514])
def test_the_rejected_board_equivalents_cannot_become_the_fcs_translation(forbidden):
    with pytest.raises(GovernanceBlock, match="Board equivalent"):
        research.assert_no_legacy_board_substitution(forbidden)


def test_the_governed_elo_inverted_through_the_board_transform_is_also_refused():
    # Not one of the three literals. It is the inversion of the *governed* 1250,
    # which a blacklist of three numbers would let through.
    with pytest.raises(GovernanceBlock):
        research.assert_no_legacy_board_substitution(fcs.board_inverse_of(1250.0))


@pytest.mark.parametrize("elo", [1250.0, 1397.51])
def test_an_elo_magnitude_is_refused_as_a_point_baseline(elo):
    with pytest.raises(GovernanceBlock, match="different axis"):
        research.assert_no_legacy_board_substitution(elo)


def test_a_search_cannot_report_a_forbidden_value_as_its_optimum():
    # The refusal is applied on every evaluation, not only at the end, so a
    # search cannot walk across a forbidden value on the way to reporting it.
    rows = [observation(0, fbs_points=0.0, margin=20)]
    with pytest.raises(GovernanceBlock):
        research.score(rows, 0.297514)


# ---------------------------------------------------------------------------
# The three orientations, against the production form.
# ---------------------------------------------------------------------------

def test_fbs_home_orientation_adds_the_hfa_to_the_fbs_side():
    obs = observation(1, venue="HOME", fbs_points=5.0)
    assert research.expected_fbs_margin(obs, -20.0) == pytest.approx(
        5.0 + 20.0 + V3_FOOTBALL_POINT_HFA
    )


def test_fcs_home_orientation_subtracts_the_hfa_from_the_fbs_side():
    # The 2026 schedule carries three rows placing an FCS entity at a HOME
    # venue, so this is a real orientation and not a hypothetical one.
    obs = observation(2, venue="AWAY", fbs_points=5.0)
    assert research.expected_fbs_margin(obs, -20.0) == pytest.approx(
        5.0 + 20.0 - V3_FOOTBALL_POINT_HFA
    )


def test_neutral_orientation_contributes_exactly_zero_not_a_small_hfa():
    obs = observation(3, venue="NEUTRAL", fbs_points=5.0)
    assert research.expected_fbs_margin(obs, -20.0) == pytest.approx(25.0)
    assert research.venue_term(
        venue="NEUTRAL", hfa_baseline_points=None, home_hfa_modifier=None
    ) == 0.0


def test_the_harness_form_matches_the_production_form_it_claims_to_re_orient():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import game

    source = inspect.getsource(game.simulate_game)
    assert "0.0 if game.venue == \"NEUTRAL\" else hfa_baseline_points * home_hfa_modifier" in source
    assert (
        "home.current_strength_points - away.current_strength_points + hfa" in source
    )


# ---------------------------------------------------------------------------
# Fail-closed refusals. Each one is a default a permissive harness would take.
# ---------------------------------------------------------------------------

def test_a_missing_pregame_fbs_point_state_refuses_and_is_not_invented():
    obs = observation(4, fbs_points=None)
    assert obs.readiness() == research.STRUCTURALLY_READY
    with pytest.raises(GovernanceBlock, match="no pregame FBS point state"):
        research.expected_fbs_margin(obs, -20.0)


def test_a_structurally_ready_observation_is_counted_not_discarded():
    # The distinction the observation contract exists for: a real game whose
    # predictor half does not exist yet is a different state from no game.
    rows = [observation(i, fbs_points=None) for i in range(5)]
    ledger = research.venue_ledger(rows)
    assert ledger.structurally_ready_no_point_state == 5
    assert ledger.total == 5
    assert ledger.as_dict()["numerically_usable"] == 0


def test_a_missing_venue_refuses_and_names_the_hfa_displacement():
    obs = observation(5, venue=None, venue_classification_source=None)
    assert obs.readiness() == research.VENUE_AMBIGUOUS
    with pytest.raises(GovernanceBlock, match="no venue classification"):
        research.expected_fbs_margin(obs, -20.0)


def test_a_venue_with_no_named_classification_source_is_an_assumption():
    obs = observation(6, venue="HOME", venue_classification_source="")
    with pytest.raises(GovernanceBlock, match="no classification source"):
        research.expected_fbs_margin(obs, -20.0)


def test_a_missing_home_field_modifier_is_never_defaulted_to_one():
    obs = observation(7, venue="HOME", home_hfa_modifier=None)
    with pytest.raises(GovernanceBlock, match="no home-field modifier"):
        research.expected_fbs_margin(obs, -20.0)


def test_an_fcs_home_game_routes_the_missing_modifier_through_the_fcs_refusal():
    # POWER_CRUNCH records the FCS home-field modifier as UNRESOLVED for all 13
    # entities, so this case must refuse with that reason, not a generic one.
    obs = observation(8, venue="AWAY", home_hfa_modifier=None)
    with pytest.raises(GovernanceBlock, match="no governed home-field modifier"):
        research.expected_fbs_margin(obs, -20.0)


def test_a_missing_hfa_baseline_is_never_defaulted():
    obs = observation(9, venue="HOME", hfa_baseline_points=None)
    with pytest.raises(GovernanceBlock, match="no HFA baseline"):
        research.expected_fbs_margin(obs, -20.0)


def test_a_point_state_on_another_axis_is_refused():
    obs = observation(10, strength_domain="SOME_OTHER_AXIS")
    with pytest.raises(GovernanceBlock, match="strength_domain"):
        research.expected_fbs_margin(obs, -20.0)


def test_an_unknown_venue_token_is_refused():
    with pytest.raises(GovernanceBlock, match="vocabulary"):
        observation(11, venue="ROAD")


def test_scoring_an_empty_observation_set_is_refused():
    with pytest.raises(GovernanceBlock, match="empty observation set"):
        research.score([], -20.0)


# ---------------------------------------------------------------------------
# The search.
# ---------------------------------------------------------------------------

def test_the_search_recovers_the_baseline_its_fixture_was_built_around():
    rows = recovery_fixture()
    result = research.search_fcs_point_baseline(rows)
    assert result.status == research.SEARCH_OPTIMUM_INTERIOR
    # The fixture residual pattern is not mean-zero over 24 rows, so the
    # recovered value is near the fixture constant rather than equal to it.
    assert result.best_baseline == pytest.approx(FIXTURE_BASELINE, abs=2.0)


def test_the_search_is_deterministic_across_repeated_runs():
    rows = recovery_fixture()
    first = research.search_fcs_point_baseline(rows)
    second = research.search_fcs_point_baseline(rows)
    assert first.as_dict() == second.as_dict()


def test_the_search_is_independent_of_observation_order():
    rows = recovery_fixture()
    forward = research.search_fcs_point_baseline(rows)
    reverse = research.search_fcs_point_baseline(list(reversed(rows)))
    assert forward.best_baseline == reverse.best_baseline
    assert forward.best_rmse == pytest.approx(reverse.best_rmse)


def test_the_search_is_coarse_to_fine_and_reaches_its_declared_final_step():
    rows = recovery_fixture()
    result = research.search_fcs_point_baseline(rows)
    expected_final = research.DEFAULT_COARSE_STEP / (
        research.DEFAULT_REFINEMENT_FACTOR**research.DEFAULT_REFINEMENTS
    )
    assert result.final_step == pytest.approx(expected_final)
    assert result.coarse_step == research.DEFAULT_COARSE_STEP
    assert result.refinements == research.DEFAULT_REFINEMENTS


def test_a_boundary_optimum_is_reported_as_one_rather_than_returned_as_an_answer():
    rows = recovery_fixture()
    result = research.search_fcs_point_baseline(
        rows, interval=(0.0, 50.0), coarse_step=5.0, max_expansions=0
    )
    assert result.status == research.SEARCH_OPTIMUM_ON_BOUNDARY
    assert result.best_baseline in result.interval


def test_a_boundary_optimum_expands_the_interval_and_then_lands_interior():
    rows = recovery_fixture()
    result = research.search_fcs_point_baseline(
        rows, interval=(0.0, 50.0), coarse_step=5.0, max_expansions=6
    )
    assert result.status == research.SEARCH_OPTIMUM_INTERIOR
    assert result.expansions >= 1
    assert result.interval != result.initial_interval
    assert result.interval[0] < result.best_baseline < result.interval[1]


def test_the_default_interval_is_wide_enough_not_to_force_the_answer():
    lo, hi = research.DEFAULT_SEARCH_INTERVAL
    observed_lo, observed_hi = fcs.UNIFIED_POINTS_OBSERVED_RANGE
    # Reaches well past both ends of the observed FBS range, in points/SD terms.
    assert (observed_lo - lo) / fcs.UNIFIED_NEUTRAL_POINTS_PER_SD > 5.0
    assert hi > observed_hi


def test_a_flat_surface_is_reported_and_never_yields_a_measured_optimum():
    rows = recovery_fixture()
    result = research.search_fcs_point_baseline(
        rows, interval=(-22.5, -22.5 + 1e-9), coarse_step=1e-10, refinements=0
    )
    assert result.status == research.SEARCH_FLAT_SURFACE
    assert result.refinements == 0


def test_a_flat_surface_makes_the_identification_verdict_not_identified():
    rows = recovery_fixture()
    flat = research.search_fcs_point_baseline(
        rows, interval=(-22.5, -22.5 + 1e-9), coarse_step=1e-10, refinements=0
    )
    verdict = research.identification_verdict(
        search=flat,
        interval=research.baseline_interval(rows, flat.best_baseline),
        season=research.season_sensitivity(rows),
        metrics=research.score(rows, flat.best_baseline),
    )
    assert verdict["identification_status"] == research.NOT_IDENTIFIED
    assert verdict["failing_conditions"]


def test_an_incoherent_search_grid_is_refused():
    rows = recovery_fixture()
    with pytest.raises(GovernanceBlock, match="converging grid"):
        research.search_fcs_point_baseline(rows, coarse_step=0.0)
    with pytest.raises(GovernanceBlock, match="empty or inverted"):
        research.search_fcs_point_baseline(rows, interval=(10.0, -10.0))


def test_a_tie_is_reported_as_a_range_and_not_only_as_a_tie_break():
    rows = recovery_fixture()
    result = research.search_fcs_point_baseline(rows)
    lo, hi = result.equivalence_range
    assert lo <= result.best_baseline <= hi
    assert result.as_dict()["rmse_equivalence_width"] >= 0.0


# ---------------------------------------------------------------------------
# Uncertainty.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "df,expected",
    [(1, 12.7062), (10, 2.2281), (42, 2.0181), (120, 1.9799)],
)
def test_the_t_quantile_matches_published_values(df, expected):
    assert research.student_t_two_sided_quantile(df) == pytest.approx(expected, abs=5e-4)


def test_a_single_observation_cannot_support_an_interval():
    with pytest.raises(GovernanceBlock, match="at least two observations"):
        research.baseline_interval([observation(0)], -20.0)


def test_the_interval_records_what_it_is_conditional_on():
    rows = recovery_fixture()
    interval = research.baseline_interval(rows, FIXTURE_BASELINE)
    assert interval.lower < interval.point_estimate < interval.upper
    conditions = " ".join(interval.conditional_on)
    assert "governed axis" in conditions
    assert "venue classification" in conditions


def test_the_required_sample_size_is_the_inverse_of_the_precision_envelope():
    # Whatever n the requirement returns must actually achieve the half-width,
    # and one fewer must not. Solved by walking n because the t quantile moves
    # with n too.
    n = research.observations_required_for_half_width(24.4831, 4.0)
    assert research.precision_envelope(24.4831, n)["half_width"] <= 4.0
    assert research.precision_envelope(24.4831, n - 1)["half_width"] > 4.0


def test_a_non_positive_target_half_width_is_refused():
    with pytest.raises(GovernanceBlock, match="must be positive"):
        research.observations_required_for_half_width(20.0, 0.0)


def test_the_precision_envelope_is_a_design_property_not_an_estimate():
    envelope = research.precision_envelope(24.4831, 43)
    assert envelope["half_width"] == pytest.approx(7.5348, abs=1e-3)
    # It consumes a dispersion and a count. No point state, no fitted value.
    signature = inspect.signature(research.precision_envelope)
    assert list(signature.parameters)[:2] == ["residual_sd", "n"]


# ---------------------------------------------------------------------------
# The two confounding statements. Both are algebra, and both must hold.
# ---------------------------------------------------------------------------

def test_shifting_every_fbs_point_state_shifts_the_fitted_baseline_one_for_one():
    # The claim anchor_confounding_statement makes, checked rather than asserted.
    rows = recovery_fixture()
    base = research.search_fcs_point_baseline(rows)
    shifted = [
        observation(
            i,
            season=o.season,
            week=o.week,
            venue=o.venue,
            fbs_points=float(o.fbs_pregame_points) + 7.0,
            margin=o.actual_margin_fbs,
        )
        for i, o in enumerate(rows)
    ]
    moved = research.search_fcs_point_baseline(shifted)
    assert moved.best_baseline - base.best_baseline == pytest.approx(7.0, abs=1e-6)
    assert moved.best_rmse == pytest.approx(base.best_rmse, abs=1e-9)
    assert research.anchor_confounding_statement()["detectable_by_more_data"] is False


def test_the_unit_slope_witness_reads_about_one_on_a_correctly_scaled_fixture():
    rows = recovery_fixture()
    witness = research.unit_slope_witness(rows)
    assert witness["slope"] == pytest.approx(1.0, abs=0.2)
    assert witness["role"] == "DIAGNOSTIC_ONLY_NOT_AN_ADAPTER_PARAMETER"


def test_a_mis_scaled_axis_shows_up_in_the_slope_witness():
    rows = recovery_fixture()
    stretched = [
        observation(
            i,
            season=o.season,
            week=o.week,
            venue=o.venue,
            fbs_points=float(o.fbs_pregame_points) * 2.0,
            margin=o.actual_margin_fbs,
        )
        for i, o in enumerate(rows)
    ]
    assert research.unit_slope_witness(stretched)["slope"] == pytest.approx(
        research.unit_slope_witness(rows)["slope"] / 2.0, abs=1e-6
    )


def test_the_venue_envelope_is_the_misclassified_share_times_the_hfa():
    envelope = research.venue_misclassification_envelope(fraction_misclassified=0.25)
    assert envelope["baseline_displacement_points"] == pytest.approx(
        0.25 * V3_FOOTBALL_POINT_HFA
    )
    with pytest.raises(GovernanceBlock, match=r"\[0, 1\]"):
        research.venue_misclassification_envelope(fraction_misclassified=1.5)


def test_scoring_a_neutral_game_as_home_moves_the_baseline_by_the_full_hfa():
    # The venue envelope's claim, checked end to end on a fixture where every
    # game is truly neutral and every one is scored as a home game.
    truth = [
        observation(i, venue="NEUTRAL", fbs_points=float(i), margin=int(i) + 18)
        for i in range(12)
    ]
    mislabelled = [
        observation(i, venue="HOME", fbs_points=float(i), margin=int(i) + 18)
        for i in range(12)
    ]
    honest = research.search_fcs_point_baseline(truth)
    wrong = research.search_fcs_point_baseline(mislabelled)
    # To within one final grid tick, which is the resolution the search reports.
    assert wrong.best_baseline - honest.best_baseline == pytest.approx(
        V3_FOOTBALL_POINT_HFA, abs=honest.final_step
    )


# ---------------------------------------------------------------------------
# Validation and sensitivity.
# ---------------------------------------------------------------------------

def test_validation_is_by_whole_season_and_never_by_random_row():
    rows = recovery_fixture()
    report = research.leave_season_out(rows)
    assert report["method"] == research.VALIDATION_LEAVE_SEASON_OUT
    held = [fold["held_out_season"] for fold in report["folds"]]
    assert held == sorted(set(held))
    assert report["pooled_out_of_sample"]["n"] == len(rows)


def test_leave_season_out_needs_more_than_one_season():
    rows = [observation(i, season=2021, fbs_points=float(i)) for i in range(6)]
    with pytest.raises(GovernanceBlock, match="at least two seasons"):
        research.leave_season_out(rows)


def test_the_temporal_holdout_is_the_last_season_and_is_scored_once():
    rows = recovery_fixture()
    report = research.temporal_holdout(rows)
    assert report["holdout_season"] > max(report["train_seasons"])
    assert report["holdout_use"] == "SCORED_ONCE_NEVER_FOR_SELECTION"


def test_season_sensitivity_refits_with_each_season_removed():
    rows = recovery_fixture()
    report = research.season_sensitivity(rows)
    assert len(report["drops"]) == len({o.season for o in rows})
    assert report["max_absolute_shift"] >= 0.0


def test_venue_sensitivity_offers_no_designated_home_as_home_variant():
    # There is no such subset, because that is not a sensitivity — it is the
    # assumption this lane refuses.
    rows = recovery_fixture()
    report = research.venue_sensitivity(rows)
    assert set(report) == {
        "ALL_CLASSIFIED",
        "FBS_HOME_ONLY",
        "FCS_HOME_ONLY",
        "NEUTRAL_ONLY",
        "NEUTRAL_EXCLUDED",
    }
    assert report["FBS_HOME_ONLY"]["n"] + report["FCS_HOME_ONLY"]["n"] + report[
        "NEUTRAL_ONLY"
    ]["n"] == len(rows)


def test_the_venue_ledger_partitions_every_observation_exactly_once():
    rows = (
        recovery_fixture()
        + [observation(90 + i, venue=None, venue_classification_source=None) for i in range(3)]
        + [observation(95 + i, fbs_points=None) for i in range(2)]
    )
    ledger = research.venue_ledger(rows)
    assert ledger.venue_ambiguous_excluded == 3
    assert ledger.structurally_ready_no_point_state == 2
    assert (
        ledger.usable_home
        + ledger.usable_away
        + ledger.usable_neutral
        + ledger.venue_ambiguous_excluded
        + ledger.structurally_ready_no_point_state
        == ledger.total
        == len(rows)
    )


def test_winner_accuracy_is_reported_but_is_not_the_objective():
    rows = recovery_fixture()
    metrics = research.score(rows, FIXTURE_BASELINE)
    assert 0.0 <= metrics.winner_accuracy <= 1.0
    payload = research.fcs_scale_research_result()
    assert payload["design"]["objective"] == "OUT_OF_SAMPLE_EXPECTED_MARGIN_RMSE"
    assert payload["design"]["winner_accuracy_is_not_optimised"] is True
    assert payload["design"]["random_row_split_permitted"] is False


# ---------------------------------------------------------------------------
# Corpus binding.
# ---------------------------------------------------------------------------

def _bind(tmp_path: Path, **overrides: object) -> research.ResearchCorpus:
    path = tmp_path / "corpus.csv"
    path.write_bytes(b"game_id,season\nX,2021\n")
    kwargs: dict[str, object] = {
        "corpus_id": "FIXTURE_CORPUS",
        "path": path,
        "expected_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_authority": "FIXTURE",
        "source_authority_class": "GOVERNED_RESULT_SOURCE",
        "audit_token": research.CORPUS_AUDIT_TOKEN_PREFIX + "FIXTURE_AUDIT",
        "seasons": [2021],
        "rows": 1,
    }
    kwargs.update(overrides)
    return research.bind_research_corpus(**kwargs)  # type: ignore[arg-type]


def test_a_corpus_binds_only_against_bytes_that_are_read_again(tmp_path):
    corpus = _bind(tmp_path)
    assert corpus.sha256 == hashlib.sha256(corpus.path.read_bytes()).hexdigest()


def test_a_corpus_whose_bytes_have_changed_fails_at_binding(tmp_path):
    path = tmp_path / "corpus.csv"
    with pytest.raises(GovernanceBlock, match="digest mismatch"):
        _bind(tmp_path, expected_sha256="00" * 32)
    assert path.exists()


def test_a_corpus_that_does_not_exist_cannot_be_bound(tmp_path):
    with pytest.raises(GovernanceBlock, match="not readable"):
        _bind(tmp_path, path=tmp_path / "absent.csv")


def test_an_unaudited_corpus_is_refused_however_well_formed(tmp_path):
    with pytest.raises(GovernanceBlock, match="no audit token"):
        _bind(tmp_path, audit_token="READY_FOR_AUDIT")


def test_a_non_result_source_authority_class_is_refused(tmp_path):
    with pytest.raises(GovernanceBlock, match="not admissible"):
        _bind(tmp_path, source_authority_class="ENGINE_OUTPUT")


def test_a_fit_without_a_bound_corpus_is_refused():
    rows = recovery_fixture()
    with pytest.raises(GovernanceBlock, match="bound by"):
        research.fit_fcs_point_baseline(rows, corpus=None)  # type: ignore[arg-type]


def test_a_fit_over_rows_with_no_point_state_names_the_ledger(tmp_path):
    corpus = _bind(tmp_path)
    rows = [observation(i, fbs_points=None) for i in range(4)]
    with pytest.raises(GovernanceBlock, match="structurally ready"):
        research.fit_fcs_point_baseline(rows, corpus=corpus)


def test_the_full_study_runs_end_to_end_against_a_bound_corpus(tmp_path):
    corpus = _bind(tmp_path)
    study = research.fit_fcs_point_baseline(recovery_fixture(), corpus=corpus)
    assert study["promotion_authorised"] is False
    assert study["canonical_config_written"] is False
    assert study["no_season_simulation"] is True
    assert study["identification"]["identification_status"] in {
        research.IDENTIFIED,
        research.WEAKLY_IDENTIFIED,
        research.NOT_IDENTIFIED,
    }
    for key in ("rmse", "mae", "bias", "median_residual", "residual_sd", "winner_accuracy"):
        assert key in study["metrics"]


def test_the_full_study_is_deterministic(tmp_path):
    corpus = _bind(tmp_path)
    rows = recovery_fixture()
    first = research.fit_fcs_point_baseline(rows, corpus=corpus)
    second = research.fit_fcs_point_baseline(rows, corpus=corpus)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


# ---------------------------------------------------------------------------
# The result artifact, and the promotion floor.
# ---------------------------------------------------------------------------

def test_the_result_reports_blocked_on_inputs_with_no_corpus_bound():
    payload = research.fcs_scale_research_result()
    assert payload["identification_status"] == research.BLOCKED_ON_INPUTS
    assert payload["terminal"] == research.READY_FOR_INPUTS
    assert payload["inputs"]["corpus_bound"] is False
    assert payload["inputs"]["corpus_sha"] is None
    assert payload["recommended_adapter_if_identified"] is None


def test_every_blocking_input_names_who_supplies_it():
    for entry in research.blocking_inputs():
        assert entry["blocking"] is True
        assert str(entry["supplied_by"]).strip()
        assert str(entry["why"]).strip()
    names = {entry["input"] for entry in research.blocking_inputs()}
    assert names == {
        "governed_pregame_fbs_point_state",
        "audited_fbs_vs_fcs_corpus",
        "venue_classification",
    }


def test_the_candidate_corpus_is_assessed_and_explicitly_not_bound():
    candidate = research.CANDIDATE_CORPUS_ASSESSMENT
    assert candidate["bound_by_this_lane"] is False
    assert candidate["audited"] is False
    assert candidate["merged_to_main"] is False
    assert candidate["fbs_vs_fcs_identified"] == 43
    assert sum(candidate["season_counts"].values()) == 43
    # Every one of the 43 places the FCS side on the designated-away side, so
    # the FCS-home orientation has no support in the candidate at all.
    assert candidate["designated_home_side"]["fcs_designated_home"] == 0
    assert candidate["designated_home_side"]["fbs_designated_home"] == 43


def test_the_result_carries_every_metric_field_as_an_explicit_null():
    # An auditor reading for a number finds the field and finds it empty, with
    # the reason attached, rather than inferring anything from a missing key.
    results = research.fcs_scale_research_result()["results"]
    for key in (
        "best_point_baseline",
        "rmse",
        "mae",
        "bias",
        "median_residual",
        "residual_sd",
        "winner_accuracy",
        "baseline_interval",
        "season_sensitivity",
        "venue_sensitivity",
        "validation",
    ):
        assert results[key] is None
    assert str(results["not_computed_because"]).strip()


def test_the_result_is_populated_once_a_corpus_and_point_states_exist(tmp_path):
    corpus = _bind(tmp_path)
    payload = research.fcs_scale_research_result(
        corpus=corpus, observations=recovery_fixture()
    )
    results = payload["results"]
    for key in ("best_point_baseline", "rmse", "mae", "bias", "residual_sd"):
        assert isinstance(results[key], float)
    assert payload["terminal"] == research.READY_FOR_AUDIT
    assert payload["identification_status"] != research.BLOCKED_ON_INPUTS
    # Still no promotion, however clean the run.
    assert payload["promotion_authorised"] is False
    assert payload["governance"]["canonical_config_written"] is False


def test_the_candidate_venue_ledger_reports_all_43_as_ambiguous():
    ledger = research.fcs_scale_research_result()["candidate_venue_ledger"]
    assert ledger["venue_ambiguous_excluded"] == 43
    assert ledger["numerically_usable"] == 0
    assert ledger["usable_home"] == ledger["usable_away"] == ledger["usable_neutral"] == 0
    assert ledger["fcs_home_orientation_support"] == 0


def test_the_result_is_byte_deterministic(tmp_path):
    first = tmp_path / "a.json"
    second = tmp_path / "b.json"
    research.write_research_result(first)
    research.write_research_result(second)
    assert first.read_bytes() == second.read_bytes()
    assert b"\r\n" not in first.read_bytes()


def test_the_committed_artifact_matches_a_fresh_emission(tmp_path):
    assert ARTIFACT.is_file(), f"{ARTIFACT} is not committed"
    fresh = tmp_path / research.RESULT_ARTIFACT_NAME
    research.write_research_result(fresh)
    assert fresh.read_bytes() == ARTIFACT.read_bytes()


def test_the_committed_artifact_promotes_nothing():
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    governance = payload["governance"]
    assert governance["promotion_authorised"] is False
    assert governance["canonical_config_written"] is False
    assert governance["adapter_registered"] is False
    assert governance["blocker_retired"] is False
    assert governance["blocker_opened"] is False
    assert governance["team_specific_fcs_ratings"] is False
    assert governance["calibration_parameters_fitted"] == []
    assert governance["season_monte_carlo_run"] is False


def test_the_module_never_registers_an_adapter_or_writes_configuration():
    source = inspect.getsource(research)
    # The *call* is what must be absent. The name appears in the module
    # docstring, saying exactly this, and that mention is the point.
    assert "register_fcs_scale_adapter(" not in source
    assert "APPROVE_V3_FCS_SCALE_ADAPTER" not in source
    # One writer, and it emits deterministic JSON to a path the caller names.
    # No raw file handle, and nothing that could reach the configuration tree.
    for writer in (".write_text(", ".write_bytes(", "open(", "shutil"):
        assert writer not in source
    assert research.PROMOTION_AUTHORISED is False


def test_the_lane_leaves_the_adapter_registry_empty():
    # Importing and running the whole research path must not install anything.
    research.fcs_scale_research_result()
    assert fcs.active_fcs_scale_adapter() is None
    assert fcs.fcs_unified_scale_governed() is False


def test_the_lane_runs_no_sampling_of_any_kind():
    source = inspect.getsource(research)
    for forbidden in ("import random", "deterministic_normal", "from .rng", "n_paths"):
        assert forbidden not in source
    assert research.fcs_scale_research_result()["no_season_simulation"] is True
    assert research.fcs_scale_research_result()["no_probabilities_emitted"] is True


def test_the_studied_blocker_stays_live_and_the_count_is_unchanged():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report

    live = blocker_report.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    assert len(live) == 8
    assert research.STUDIED_BLOCKER in live
    # Research is not retirement. This lane studies the blocker and leaves it
    # exactly where it found it; only an accepted promotion can retire it.
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert payload["governance"]["blocker_retired"] is False
    assert payload["governance"]["blocker_opened"] is False
    assert payload["studied_blocker"] == research.STUDIED_BLOCKER


def test_the_terminal_is_ready_for_inputs_while_any_input_is_blocking():
    assert research.research_status() == research.READY_FOR_INPUTS
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert payload["terminal"] == research.READY_FOR_INPUTS
    assert payload["identification_status"] == research.BLOCKED_ON_INPUTS


# ---------------------------------------------------------------------------
# The freeze, and the cross-lane correction it carries.
# ---------------------------------------------------------------------------

def test_no_chairman_ruling_is_a_prerequisite_for_fcs_scale_estimation():
    # The superseded HUMAN_GOVERNANCE_REQUIRED reading was refuted by an
    # independent audit. A stale copy of it anywhere in this lane would tell the
    # programme it is waiting on an authority when it is waiting on evidence.
    assert research.CHAIRMAN_RULING_REQUIRED is False
    availability = research.HISTORICAL_POINT_STATE_AVAILABILITY
    assert availability["classification"] == "EMPIRICALLY_CALIBRATABLE"
    assert availability["superseded_classification"] == "HUMAN_GOVERNANCE_REQUIRED"
    assert availability["chairman_ruling_required_for_fcs_scale_estimation"] is False
    for entry in research.blocking_inputs():
        assert "ruling" not in str(entry["supplied_by"]).lower()


def test_the_committed_artifact_claims_no_ruling_prerequisite():
    payload = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert payload["freeze"]["chairman_ruling_required"] is False
    assert payload["freeze"]["historical_axis_classification"] == "EMPIRICALLY_CALIBRATABLE"
    point_state = payload["inputs"]["historical_fbs_point_state"]
    assert point_state["classification"] == "EMPIRICALLY_CALIBRATABLE"


def test_the_harness_is_frozen_as_an_input_ready_tool():
    record = research.freeze_record()
    assert record["harness_frozen"] is True
    assert record["harness_status"] == "FROZEN_READY_FOR_INPUTS"
    # Freezing records that the harness phase is done. It does not advance the
    # research status, which still turns on inputs that do not exist.
    assert record["lane_terminal"] == research.READY_FOR_INPUTS
    assert record["freeze_terminal"] == research.FROZEN_READY_FOR_INPUTS
    for flag in (
        "research_mathematics_changed",
        "numerical_fitting_performed",
        "additional_observations_acquired",
        "fcs_elo_changed",
        "adapter_promoted",
        "season_monte_carlo_run",
    ):
        assert record[flag] is False


def test_the_three_required_numerical_inputs_are_stated_as_evidence():
    inputs = research.REQUIRED_NUMERICAL_INPUTS
    assert len(inputs) == 3
    assert "historical FBS pregame V3 point states" in inputs[0]
    assert "audited real FBS-vs-FCS observations" in inputs[1]
    assert "venue classification" in inputs[2]
    # And they line up one-for-one with what actually blocks a fit.
    assert len(research.blocking_inputs()) == 3


@pytest.mark.parametrize(
    "finding_id",
    [
        "F_HAT_IS_A_MEAN",
        "FCS_ELO_FIXED_AT_1250",
        "FORTY_THREE_GIVES_RANGE_ONLY",
        "ALL_FORTY_THREE_ARE_FBS_DESIGNATED_HOME",
        "AXIS_OFFSET_SHIFTS_F_HAT_ONE_FOR_ONE",
        "VENUE_MISCLASSIFICATION_BIASES_F_HAT",
    ],
)
def test_every_preserved_finding_is_pinned(finding_id):
    by_id = {f["id"]: f for f in research.PRESERVED_FINDINGS}
    assert finding_id in by_id
    assert str(by_id[finding_id]["finding"]).strip()
    assert str(by_id[finding_id]["why"]).strip()


def test_the_preserved_findings_still_hold_against_the_frozen_harness():
    # Each of the four checkable findings, re-derived rather than trusted.
    rows = recovery_fixture()

    # F_hat is the mean of (points + venue term - margin).
    fit = research.search_fcs_point_baseline(rows)
    closed_form = sum(
        float(o.fbs_pregame_points)
        + research.venue_term(
            venue=str(o.venue),
            hfa_baseline_points=o.hfa_baseline_points,
            home_hfa_modifier=o.home_hfa_modifier,
            game_id=o.game_id,
            fcs_is_home=o.venue == "AWAY",
        )
        - float(o.actual_margin_fbs)
        for o in rows
    ) / len(rows)
    assert fit.best_baseline == pytest.approx(closed_form, abs=fit.final_step)

    # Elo is still 1250.
    assert research.assert_fcs_elo_invariant() == 1250.0

    # 43 at the candidate dispersion is range-level only.
    assert research.precision_envelope(24.4831, 43)["half_width"] > (
        research.MATERIAL_HALF_WIDTH_POINTS
    )

    # Venue misclassification biases F_hat by share x HFA.
    assert research.venue_misclassification_envelope(fraction_misclassified=1.0)[
        "baseline_displacement_points"
    ] == pytest.approx(V3_FOOTBALL_POINT_HFA)


def test_no_calibration_parameter_is_touched_by_this_lane():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration

    source = inspect.getsource(research)
    for parameter in calibration.CALIBRATION_FIELDS:
        assert parameter not in source
