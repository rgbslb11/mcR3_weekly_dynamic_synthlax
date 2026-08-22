"""Calibration orchestrator — candidate universe, walk-forward scorer, aggregator.

The tests here are chosen for one property: each one fails if a specific way of
producing a confident wrong calibration answer is reintroduced. A search harness
that leaks the future, merges mismatched shards, or reports a tie-break as a
discovery does not raise — it returns a better number. So the guards are asserted
against inputs that would exploit them rather than against inputs that work.

Three of them target the identification defects that disqualified the prior
9,600-candidate experiment by name: a cap that never bound, a depth optimum on
the search boundary, and a ``game_sd_points`` that measured the sport rather than
the model.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_aggregate as agg
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_fixture as fixture
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_scoring as scoring
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_search as search
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_stage0 as stage0
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

MODEL_VERSION = "V3-EXPERIMENTAL-ORCHESTRATOR"


# --- shared fixtures ---------------------------------------------------------


@pytest.fixture(scope="module")
def observations() -> scoring.ObservationSet:
    return fixture.fixture_observations()


@pytest.fixture(scope="module")
def authority() -> scoring.ExpectedMarginAuthority:
    return fixture.fixture_authority()


@pytest.fixture(scope="module")
def space() -> search.SearchSpace:
    return search.coarse_space()


@pytest.fixture(scope="module")
def universe(space: search.SearchSpace) -> tuple[search.CalibrationCandidate, ...]:
    return space.enumerate()


def _candidate(
    *,
    coefficient: float = 0.25,
    cap: float = 4.0,
    form: search.RecentFormPolicy | None = None,
    blowout: search.BlowoutPolicy | None = None,
    regularization: search.RegularizationPolicy | None = None,
) -> search.CalibrationCandidate:
    return search.CalibrationCandidate(
        coefficient=coefficient,
        movement_cap_points=cap,
        recent_form=form or search.RecentFormPolicy(search.RECENT_FORM_UNIFORM, 4),
        blowout=blowout or search.BlowoutPolicy(search.BLOWOUT_NONE),
        regularization=regularization
        or search.RegularizationPolicy(search.REGULARIZATION_NONE),
    )


# --- candidate identity ------------------------------------------------------


def test_candidate_id_is_a_pure_function_of_the_parameter_vector() -> None:
    """Two independently built candidates with one vector share one identity."""
    left = _candidate()
    right = _candidate()
    assert left is not right
    assert left.candidate_key == right.candidate_key
    assert left.candidate_id == right.candidate_id
    assert left.candidate_id >= 0

    assert _candidate(coefficient=0.35).candidate_id != left.candidate_id
    assert _candidate(cap=8.0).candidate_id != left.candidate_id


def test_serialization_is_stable_and_separates_values_that_nearly_agree() -> None:
    """A content-addressed id may never merge two vectors that differ at all."""
    assert _candidate().canonical_serialization == _candidate().canonical_serialization
    near = _candidate(coefficient=0.25 + 1e-12)
    assert near.canonical_serialization != _candidate().canonical_serialization
    assert near.candidate_id != _candidate().candidate_id

    # An integer-valued float must not collapse onto the integer beside it, or a
    # depth and a threshold could collide across families.
    assert search.canonical_json({"x": 6.0}) != search.canonical_json({"x": 6})


def test_candidate_ids_survive_widening_an_axis(
    space: search.SearchSpace, universe: tuple[search.CalibrationCandidate, ...]
) -> None:
    """Refinement adds candidates; it must not renumber the ones already scored.

    This is the whole reason the id is a digest rather than an enumeration index.
    A Stage-1 result table stays joinable to a Stage-2 table.
    """
    leader = next(
        c
        for c in universe
        if c.coefficient == 0.45 and c.recent_form.depth == 8 and c.movement_cap_points == 8.0
    )
    refined = search.refine_space(space, [leader])
    matching = [c for c in refined.enumerate() if c.candidate_key == leader.candidate_key]
    assert len(matching) == 1
    assert matching[0].candidate_id == leader.candidate_id
    assert refined.size > 0
    assert refined.parent_config_sha == space.config_sha


# --- sharding ----------------------------------------------------------------


@pytest.mark.parametrize("shard_count", search.SUPPORTED_SHARD_COUNTS)
def test_shards_are_complete_and_disjoint(
    universe: tuple[search.CalibrationCandidate, ...], shard_count: int
) -> None:
    """Union of shards equals the universe exactly: missing 0, duplicates 0."""
    proof = search.prove_shard_partition(universe, shard_count)
    assert proof["missing"] == 0
    assert proof["duplicates"] == 0
    assert proof["unexpected"] == 0
    assert proof["union_size"] == len(universe)
    assert sum(proof["per_shard_sizes"].values()) == len(universe)

    seen: set[int] = set()
    for index in range(shard_count):
        member = {
            c.candidate_id for c in search.shard_candidates(universe, shard_count, index)
        }
        assert not (member & seen), "a candidate was assigned to two shards"
        seen |= member
    assert seen == {c.candidate_id for c in universe}


def test_shard_membership_needs_no_coordination(
    universe: tuple[search.CalibrationCandidate, ...]
) -> None:
    """A worker decides ownership by arithmetic on the id, and nothing else."""
    for candidate in universe[:50]:
        owner = search.shard_of(candidate.candidate_id, 4)
        assert candidate in search.shard_candidates(universe, 4, owner)


def test_unsupported_shard_geometry_is_refused(
    universe: tuple[search.CalibrationCandidate, ...]
) -> None:
    with pytest.raises(InputValidationError):
        search.shard_candidates(universe, 3, 0)
    with pytest.raises(InputValidationError):
        search.shard_candidates(universe, 4, 4)


# --- space governance --------------------------------------------------------


def test_game_sd_is_never_a_searched_axis() -> None:
    """It is a property of the residuals, so it cannot be one of the axes."""
    search.assert_families_match_calibration()
    assert search.DISPERSION_FAMILY == "game_sd_points"
    assert search.DISPERSION_FAMILY not in search.MEAN_MODEL_FAMILIES
    assert set(search.MEAN_MODEL_FAMILIES) | {search.DISPERSION_FAMILY} == set(
        cal.CALIBRATION_FIELDS
    )
    with pytest.raises(InputValidationError):
        search.SearchAxis(
            family="game_sd_points",
            levels=(16.0, 18.0),
            evidence_status=search.EVIDENCE_PENDING,
            boundary_expandable=False,
            rationale="not permitted",
        )


def test_predeclared_hash_bound_ranges_execute_without_a_named_authority(
    space: search.SearchSpace,
) -> None:
    """The correction, asserted directly.

    Choosing which numbers to *try* and choosing which number becomes *canonical*
    are different acts. Only the second needs an authority, and this proves the
    first no longer waits on one.
    """
    assert all(a.evidence_status == search.EVIDENCE_PREDECLARED for a in space.axes)
    assert search.range_status(space) == search.EVIDENCE_PREDECLARED

    declaration = search.predeclare(space, experiment_id="TEST-COARSE")
    gate = search.require_executable_ranges(space, predeclaration=declaration)
    assert gate["range_status"] == search.EVIDENCE_PREDECLARED
    assert gate["ruling_required"] is False
    assert gate["confers_promotion_authority"] is False
    assert gate["obligations"]["boundary_optimum_must_expand"] is True
    assert gate["obligations"]["holdout_sealed_until_final_evaluation"] is True
    assert gate["obligations"]["automatic_promotion"] is False

    # Executing a research search still confers nothing toward a promotion: the
    # promotion-grade gate is untouched and still refuses.
    with pytest.raises(GovernanceBlock):
        search.require_range_authority(space)


def test_the_experiment_digest_is_what_binds_the_declared_ranges(
    space: search.SearchSpace, universe: tuple[search.CalibrationCandidate, ...]
) -> None:
    """Narrowing a range after seeing results changes the digest, so peeking shows."""
    declaration = search.predeclare(space, experiment_id="TEST-COARSE")
    assert declaration.config_sha == space.config_sha

    narrowed = search.refine_space(space, [universe[0]])
    with pytest.raises(GovernanceBlock, match="not the ranges that were declared"):
        search.require_executable_ranges(narrowed, predeclaration=declaration)

    # And a declaration is required at all; a bare space is not self-authorising.
    with pytest.raises(GovernanceBlock, match="no predeclaration was supplied"):
        search.require_executable_ranges(space)

    # A fixture-marked space is refused on both paths, always.
    with pytest.raises(GovernanceBlock):
        search.require_executable_ranges(
            search.coarse_space(range_authority=search.FIXTURE_RANGE_AUTHORITY),
            predeclaration=declaration,
        )


def test_a_range_too_narrow_to_test_anything_is_refused(
    space: search.SearchSpace,
) -> None:
    """A one-point "range" would satisfy every other predeclaration condition."""
    assert search.require_predeclared_breadth(space)["broad_enough"] is True

    axes = tuple(
        search.SearchAxis(
            family=axis.family,
            levels=axis.levels[:1],
            evidence_status=search.EVIDENCE_PREDECLARED,
            boundary_expandable=axis.boundary_expandable,
            rationale="deliberately degenerate",
        )
        if axis.family == "weekly_performance_residual_coefficient"
        else axis
        for axis in space.axes
    )
    degenerate = search.SearchSpace(
        space_id="TOO-NARROW", stage=search.STAGE_COARSE, axes=axes
    )
    with pytest.raises(GovernanceBlock, match="too narrow"):
        search.require_predeclared_breadth(degenerate)
    with pytest.raises(GovernanceBlock, match="too narrow"):
        search.predeclare(degenerate, experiment_id="TEST-NARROW")


def test_an_undeclared_axis_is_still_refused() -> None:
    """The relaxation is to *predeclared*, not to anything at all."""
    base = search.coarse_space()
    axes = tuple(
        search.SearchAxis(
            family=axis.family,
            levels=axis.levels,
            evidence_status=search.EVIDENCE_PENDING,
            boundary_expandable=axis.boundary_expandable,
            rationale=axis.rationale,
        )
        if axis.family == "blowout_treatment"
        else axis
        for axis in base.axes
    )
    undeclared = search.SearchSpace(
        space_id="UNDECLARED", stage=search.STAGE_COARSE, axes=axes
    )
    assert search.range_status(undeclared) == search.EVIDENCE_PENDING
    with pytest.raises(GovernanceBlock, match="undeclared axes"):
        search.require_executable_ranges(undeclared)


def test_ranges_may_never_be_selected_against_the_holdout(
    space: search.SearchSpace,
) -> None:
    with pytest.raises(GovernanceBlock, match="holdout"):
        search.predeclare(space, experiment_id="TEST", scored_split="holdout")
    with pytest.raises(GovernanceBlock, match="not a predeclaration"):
        search.ExperimentPredeclaration(
            experiment_id="TEST",
            config_sha=space.config_sha,
            stage=search.STAGE_COARSE,
            declared_scored_split="validation",
            declared_before_results=False,
        )


def test_prior_experiment_is_context_and_not_an_anchor(space: search.SearchSpace) -> None:
    """0.18 / depth 6 / cap 6.0 must not appear as a level of the coarse grid."""
    assert search.HISTORICAL_RESEARCH_CONTEXT["usable_as_anchor"] is False
    coefficients = space.axis("weekly_performance_residual_coefficient").levels
    caps = space.axis("weekly_movement_cap_points").levels
    assert 0.18 not in coefficients
    assert 6.0 not in caps


# --- temporal integrity ------------------------------------------------------


def _row(**overrides) -> scoring.ObservationRow:
    base = dict(
        game_id="G1",
        season=2021,
        week=1,
        event_time="2021-09-04T12:00:00+00:00",
        team="TA",
        opponent="TB",
        venue="HOME",
        pregame_team_points=3.0,
        pregame_opponent_points=1.0,
        governed_expected_margin=4.5,
        actual_margin=7.0,
        split="training",
        provenance="TEST",
    )
    base.update(overrides)
    return scoring.ObservationRow(**base)


def test_week_running_backwards_against_the_clock_is_refused() -> None:
    """Week and event_time must agree, or the rerating boundary lands wrong."""
    with pytest.raises(InputValidationError, match="week"):
        scoring.ObservationSet(
            rows=(
                _row(game_id="G1", week=3, event_time="2021-09-04T12:00:00+00:00"),
                _row(game_id="G2", week=2, event_time="2021-09-11T12:00:00+00:00"),
            ),
            dataset_sha="X",
            provenance="TEST",
        )


def test_timestamps_that_do_not_sort_chronologically_are_refused() -> None:
    """The leakage proof compares these strings; the format has to make that valid."""
    with pytest.raises(InputValidationError, match="event_time"):
        _row(event_time="2021-9-4T12:00:00+00:00")
    with pytest.raises(InputValidationError, match="event_time"):
        _row(event_time="2021-09-04 12:00:00")
    with pytest.raises(InputValidationError, match="uniform format"):
        scoring.ObservationSet(
            rows=(
                _row(game_id="G1", event_time="2021-09-04T12:00:00+00:00"),
                _row(game_id="G2", event_time="2021-09-11T12:00:00-05:00"),
            ),
            dataset_sha="X",
            provenance="TEST",
        )


def test_a_mirrored_corpus_is_refused_rather_than_double_counted() -> None:
    with pytest.raises(InputValidationError, match="repeats game ids"):
        scoring.ObservationSet(
            rows=(_row(game_id="G1"), _row(game_id="G1", team="TB", opponent="TA")),
            dataset_sha="X",
            provenance="TEST",
        )


def test_weeks_one_and_two_keep_opening_strength_semantics_exactly(
    observations: scoring.ObservationSet, authority: scoring.ExpectedMarginAuthority
) -> None:
    """Nothing is promoted before Week 2 closes, so Weeks 1-2 predict from opening.

    Asserted numerically rather than structurally: every Week 1 and Week 2
    prediction must equal the corpus's own governed expected margin, which is by
    construction the transform applied to opening strengths.
    """
    score = scoring.score_candidate(_candidate(coefficient=0.45), observations, authority)
    governed = {r.game_id: r.require_expected_margin() for r in observations.ordered_rows}
    early = [p for p in score.predictions if p.week <= 2]
    assert early
    for prediction in early:
        assert prediction.information_cutoff is None
        assert prediction.predicted_margin == pytest.approx(
            governed[prediction.game_id], abs=1e-9
        )


def test_first_promoted_rerating_lands_after_week_two(
    observations: scoring.ObservationSet, authority: scoring.ExpectedMarginAuthority
) -> None:
    """Week 3 is the first week predicting from a promoted rating, not Week 2."""
    assert scoring.FIRST_PROMOTED_RERATING_AFTER_WEEK == 2
    score = scoring.score_candidate(_candidate(coefficient=0.45), observations, authority)
    governed = {r.game_id: r.require_expected_margin() for r in observations.ordered_rows}
    week_three = [p for p in score.predictions if p.week == 3 and p.season == 2021]
    assert week_three
    assert all(p.information_cutoff is not None for p in week_three)
    assert any(
        abs(p.predicted_margin - governed[p.game_id]) > 1e-9 for p in week_three
    ), "Week 3 still predicts from opening strength; nothing was promoted"


def test_walk_forward_never_predicts_from_its_own_future(
    observations: scoring.ObservationSet, authority: scoring.ExpectedMarginAuthority
) -> None:
    score = scoring.score_candidate(_candidate(), observations, authority)
    proof = score.leakage_proof
    assert proof["leak_free"] is True
    assert proof["violations"] == 0
    assert proof["predictions_checked"] == len(observations.calibration_rows)
    for prediction in score.predictions:
        if prediction.information_cutoff is not None:
            assert prediction.information_cutoff < prediction.event_time


def test_future_leakage_is_refused_when_it_is_present() -> None:
    """The proof has to fail on a leak, or it is proving nothing."""
    leaking = scoring.Prediction(
        game_id="G9",
        season=2021,
        week=5,
        event_time="2021-10-02T12:00:00+00:00",
        split="validation",
        predicted_margin=3.0,
        actual_margin=10.0,
        information_cutoff="2021-10-09T12:00:00+00:00",
    )
    with pytest.raises(GovernanceBlock, match="Future leakage"):
        scoring.require_no_future_leakage([leaking])


# --- expected-margin boundary ------------------------------------------------


def test_missing_expected_margin_fails_closed_and_never_becomes_zero() -> None:
    row = _row(governed_expected_margin=None)
    with pytest.raises(GovernanceBlock, match="no governed expected margin"):
        row.require_expected_margin()


def test_fixture_authority_may_never_produce_a_citable_result(
    authority: scoring.ExpectedMarginAuthority,
) -> None:
    with pytest.raises(GovernanceBlock):
        scoring.require_governed_authority(authority)
    with pytest.raises(GovernanceBlock, match="No expected-margin authority"):
        scoring.require_governed_authority(None)


def test_a_transform_that_disagrees_with_the_corpus_is_refused(
    observations: scoring.ObservationSet,
) -> None:
    """Residuals measured against a predictor the corpus never used are not evidence."""
    wrong = fixture.fixture_authority(hfa_points=9.0)
    with pytest.raises(GovernanceBlock, match="does not reproduce"):
        observations.require_authority_agreement(wrong)


def test_the_benchmark_fixture_cannot_be_mounted_as_governed_evidence() -> None:
    """The refusal is executed against the real pattern list, not described."""
    report = fixture.assert_refused_as_governed_source()
    assert report["admissible_as_governed_source"] is False
    assert report["matched_synthetic_patterns"]


def test_venue_is_never_inferred() -> None:
    authority = fixture.fixture_authority(hfa_points=2.5)
    assert authority.signed_hfa("HOME") == 2.5
    assert authority.signed_hfa("AWAY") == -2.5
    assert authority.signed_hfa("NEUTRAL") == 0.0
    with pytest.raises(InputValidationError, match="venue"):
        authority.signed_hfa("H")


# --- identification ----------------------------------------------------------


def test_cap_statistics_distinguish_a_binding_cap_from_an_inert_one(
    observations: scoring.ObservationSet, authority: scoring.ExpectedMarginAuthority
) -> None:
    """A cap that never binds must be reported as unidentified, not as a finding."""
    inert = scoring.score_candidate(
        _candidate(coefficient=0.05, cap=16.0), observations, authority
    ).cap
    binding = scoring.score_candidate(
        _candidate(coefficient=0.45, cap=2.0), observations, authority
    ).cap

    assert inert.cap_hit_count == 0
    assert inert.cap_hit_rate == 0.0
    assert inert.identified is False
    assert "not identified" in inert.as_dict()["identification_note"]
    assert inert.max_uncapped_update == pytest.approx(inert.max_capped_update)

    assert binding.cap_hit_count > 0
    assert 0.0 < binding.cap_hit_rate <= 1.0
    assert binding.identified is True
    assert binding.max_uncapped_update > binding.max_capped_update
    assert binding.max_capped_update <= 2.0 + 1e-12


def test_boundary_optimum_is_marked_and_refinement_widens_the_ladder(
    space: search.SearchSpace, universe: tuple[search.CalibrationCandidate, ...]
) -> None:
    """A winner at the edge of the grid is the grid running out, not an optimum."""
    edge = next(
        c
        for c in universe
        if c.coefficient == 0.45
        and c.recent_form.depth == 8
        and c.movement_cap_points == 16.0
    )
    report = search.boundary_report(space, edge)
    assert report["identified"] is False
    assert "recent_form_weights" in report["boundary_families"]
    assert "weekly_performance_residual_coefficient" in report["boundary_families"]
    assert report["families"]["recent_form_weights"]["edge"] == "high"
    assert report["recent_form_tail_mass"] > 0.0

    refined = search.refine_space(space, [edge])
    depths = {int(level.depth) for level in refined.axis("recent_form_weights").levels}
    coefficients = set(refined.axis("weekly_performance_residual_coefficient").levels)
    assert max(depths) > 8, "the depth ladder must reach past the boundary optimum"
    assert max(coefficients) > 0.45

    interior = next(
        c
        for c in universe
        if c.coefficient == 0.25
        and c.recent_form.depth == 4
        and c.movement_cap_points == 4.0
        and c.regularization.prior_games == 2.0
    )
    assert search.boundary_report(space, interior)["identified"] is True


def test_refinement_is_a_pure_function_of_the_leaders(
    space: search.SearchSpace, universe: tuple[search.CalibrationCandidate, ...]
) -> None:
    """Two operators handed one ranking must build byte-identical Stage-2 universes."""
    leaders = [universe[7], universe[900]]
    first = search.refine_space(space, leaders)
    second = search.refine_space(space, list(leaders))
    assert first.config_sha == second.config_sha
    assert search.refine_space(space, leaders[:1]).config_sha != first.config_sha
    with pytest.raises(InputValidationError):
        search.refine_space(space, [])


def test_regularization_is_explicit_and_its_impact_is_reported() -> None:
    """No implicit shrinkage: the schedule is a policy and reports both regimes."""
    none = search.RegularizationPolicy(search.REGULARIZATION_NONE)
    assert none.shrinkage(1) == 1.0
    assert none.regularization_amount(11) == 0.0
    assert none.effective_sample_count(4) == 4.0

    shrunk = search.RegularizationPolicy(search.REGULARIZATION_GAMES_PLAYED_SHRINKAGE, 5.0)
    report = shrunk.report()
    assert report["early_season_regularization_amount"] > report[
        "late_season_regularization_amount"
    ]
    assert shrunk.shrinkage(0) == 0.0
    assert shrunk.effective_sample_count(1) == 6.0
    with pytest.raises(InputValidationError):
        search.RegularizationPolicy(search.REGULARIZATION_NONE, 3.0)


def test_recent_form_reports_each_update_contribution() -> None:
    """R13: the effective contribution of each historical update is recorded."""
    policy = search.RecentFormPolicy(search.RECENT_FORM_GEOMETRIC, 4, 0.5)
    weights = policy.weights()
    assert sum(weights) == pytest.approx(1.0)
    assert weights[0] > weights[-1]
    assert policy.tail_mass == weights[-1]
    # A window deeper than the history contributes nothing past it, rather than
    # re-normalizing and quietly behaving like a shallower policy.
    assert policy.effective_contributions(2) == weights[:2]
    assert policy.effective_contributions(99) == weights


def test_blowout_treatment_is_a_named_serializable_policy() -> None:
    """Not a magic clip inside the update step: it is in the id and in the table."""
    assert search.BlowoutPolicy(search.BLOWOUT_NONE).apply(-40.0) == -40.0
    clip = search.BlowoutPolicy(search.BLOWOUT_RESIDUAL_CLIP, 21.0)
    assert clip.apply(40.0) == 21.0
    assert clip.apply(-40.0) == -21.0
    smooth = search.BlowoutPolicy(search.BLOWOUT_SMOOTH_SATURATION, 24.0)
    assert 0 < smooth.apply(40.0) < 24.0
    # Every policy is odd, which is what lets one row update both sides of a game.
    for policy in (search.BlowoutPolicy(search.BLOWOUT_NONE), clip, smooth):
        assert policy.apply(-13.0) == pytest.approx(-policy.apply(13.0))
    with pytest.raises(InputValidationError):
        search.BlowoutPolicy("CLIP_EVERYTHING", 10.0)
    with pytest.raises(InputValidationError):
        search.BlowoutPolicy(search.BLOWOUT_RESIDUAL_CLIP)


# --- game_sd_points ----------------------------------------------------------


def test_game_sd_from_residuals_is_admissible_and_from_actual_margins_is_not() -> None:
    """The two answer different questions and are never interchangeable."""
    residuals = [3.0, -2.0, 5.0, -4.0, 1.0, -1.0]
    margins = [30.0, -21.0, 45.0, -14.0, 7.0, -3.0]

    good = scoring.estimate_game_sd_points(residuals, split="validation")
    assert good.method == scoring.GAME_SD_METHOD_RESIDUAL
    assert scoring.require_residual_based_game_sd(good) is good
    assert good.as_dict()["admissible_for_game_sd_points"] is True

    bad = scoring.game_sd_from_actual_margins(margins, split="validation")
    assert bad.method == scoring.GAME_SD_METHOD_ACTUAL_MARGIN
    assert bad.value > good.value
    assert bad.as_dict()["admissible_for_game_sd_points"] is False
    with pytest.raises(GovernanceBlock, match="not admissible"):
        scoring.require_residual_based_game_sd(bad)


def test_game_sd_may_not_be_read_off_the_training_split() -> None:
    with pytest.raises(GovernanceBlock, match="training split"):
        scoring.estimate_game_sd_points([1.0, -1.0, 2.0], split="training")
    with pytest.raises(InputValidationError):
        scoring.estimate_game_sd_points([1.0], split="validation")


def test_dispersion_cannot_change_which_mean_model_wins(
    observations: scoring.ObservationSet, authority: scoring.ExpectedMarginAuthority
) -> None:
    """Selection is on RMSE, so game_sd_points cannot contaminate the choice."""
    candidate = _candidate()
    natural = scoring.score_candidate(candidate, observations, authority)
    forced = scoring.score_candidate(
        candidate,
        observations,
        authority,
        sd_override=scoring.estimate_game_sd_points(
            [40.0, -40.0, 35.0, -35.0], split="validation"
        ),
    )
    assert natural.metrics["baxter_rmse"] == forced.metrics["baxter_rmse"]
    assert natural.metrics["baxter_mae"] == forced.metrics["baxter_mae"]
    assert natural.metrics["winner_accuracy"] == forced.metrics["winner_accuracy"]
    # Only the probabilistic diagnostics move, and the record says the dispersion
    # came from somewhere other than the split being scored.
    assert natural.metrics["brier_score"] != forced.metrics["brier_score"]
    assert forced.metrics["dispersion_independent_of_scored_split"] is True
    assert natural.metrics["dispersion_independent_of_scored_split"] is False


def test_probabilistic_metrics_report_absence_rather_than_a_number(
    observations: scoring.ObservationSet, authority: scoring.ExpectedMarginAuthority
) -> None:
    """Brier and log loss are ``None`` where they are not mathematically valid."""
    degenerate = scoring._probabilistic_diagnostics([], 0.0)
    assert degenerate["brier_score"] is None
    assert degenerate["log_loss"] is None
    assert degenerate["status"] == scoring.FAILURE_DEGENERATE

    real = scoring.score_candidate(_candidate(), observations, authority)
    assert 0.0 <= real.metrics["brier_score"] <= 1.0
    assert real.metrics["log_loss"] > 0.0
    assert real.metrics["calibration_bins"]


# --- witnesses ---------------------------------------------------------------


def test_witnesses_are_reported_independently_and_never_blended(
    observations: scoring.ObservationSet, authority: scoring.ExpectedMarginAuthority
) -> None:
    score = scoring.score_candidate(_candidate(), observations, authority)
    fields = score.witness_fields
    assert fields["blended_into_primary_criterion"] is False
    assert fields["scales_converted_to_v3_points"] is False
    assert -1.0 <= fields["colley_rank_correlation"] <= 1.0
    assert -1.0 <= fields["srs_rank_correlation"] <= 1.0
    assert isinstance(fields["colley_directionally_coherent"], bool)

    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import colley

    with pytest.raises(GovernanceBlock):
        colley.reject_witness_composite(["COLLEY", "BAXTER_RATING"])
    with pytest.raises(GovernanceBlock):
        colley.reject_colley_as("BAXTER_RATING")
    with pytest.raises(GovernanceBlock):
        cal.reject_witness_composite(["colley_matrix", "baxter_rating"])


def test_spearman_reports_undefined_rather_than_zero() -> None:
    """A witness that returns 0.0 for "undefined" is indistinguishable from one
    reporting genuine independence."""
    assert scoring.spearman_rank_correlation({"a": 1.0}, {"a": 2.0}) is None
    assert scoring.spearman_rank_correlation({"a": 1.0, "b": 1.0}, {"a": 2.0, "b": 3.0}) is None
    assert scoring.spearman_rank_correlation(
        {"a": 1.0, "b": 2.0, "c": 3.0}, {"a": 5.0, "b": 6.0, "c": 7.0}
    ) == pytest.approx(1.0)


# --- shard emission and aggregation -----------------------------------------


def _shard_row(candidate_id: int, **overrides) -> dict:
    row = {
        "candidate_id": candidate_id,
        "candidate_key": f"key-{candidate_id}",
        "parameters": {
            "weekly_performance_residual_coefficient": 0.25,
            "weekly_movement_cap_points": 4.0,
            "recent_form_weights": {"scheme": "UNIFORM", "depth": 4, "decay": None},
            "blowout_treatment": {"policy_id": "NO_SPECIAL_TREATMENT", "threshold_points": None},
            "sample_size_regularization": {"policy_id": "NONE", "prior_games": None},
        },
        "scored_split": "validation",
        "baxter_rmse": 18.0,
        "baxter_mae": 14.0,
        "movement_p95": 1.0,
        "cap_identified": True,
        "cap_hit_rate": 0.1,
        "max_uncapped_update": 5.0,
        "failure_status": scoring.FAILURE_NONE,
        "failure_reason": None,
    }
    row.update(overrides)
    return row


def _table(rows: list[dict], **overrides) -> dict:
    table = {
        "stage": "coarse",
        "shard_index": 0,
        "shard_count": 1,
        "input_dataset_sha": "DATASET-A",
        "split_sha": "SPLIT-A",
        "experiment_config_sha": "CONFIG-A",
        "expected_margin_authority_id": "AUTH-A",
        "model_version": MODEL_VERSION,
        "rows": rows,
        "_source_file": "SHARD.json",
    }
    table.update(overrides)
    return table


def test_aggregate_refuses_a_missing_candidate() -> None:
    """The best of what came back is not the best of what was searched."""
    tables = [_table([_shard_row(1), _shard_row(2)])]
    with pytest.raises(GovernanceBlock, match="absent from the merged shards"):
        agg.aggregate(tables, expected_ids=[1, 2, 3])


def test_aggregate_refuses_a_duplicated_candidate() -> None:
    tables = [
        _table([_shard_row(1)], shard_index=0, shard_count=2),
        _table([_shard_row(1)], shard_index=1, shard_count=2, _source_file="B.json"),
    ]
    with pytest.raises(GovernanceBlock, match="more than once"):
        agg.aggregate(tables, expected_ids=[1])


def test_aggregate_refuses_a_candidate_nobody_asked_for() -> None:
    tables = [_table([_shard_row(1), _shard_row(99)])]
    with pytest.raises(GovernanceBlock, match="not in the search universe"):
        agg.aggregate(tables, expected_ids=[1])


@pytest.mark.parametrize(
    "key,other",
    [
        ("input_dataset_sha", "DATASET-B"),
        ("split_sha", "SPLIT-B"),
        ("experiment_config_sha", "CONFIG-B"),
        ("expected_margin_authority_id", "AUTH-B"),
        ("model_version", "OTHER-MODEL"),
        ("stage", "refinement"),
    ],
)
def test_aggregate_refuses_shards_that_were_not_scoring_the_same_thing(
    key: str, other: str
) -> None:
    tables = [
        _table([_shard_row(1)], shard_index=0, shard_count=2),
        _table([_shard_row(2)], shard_index=1, shard_count=2, **{key: other}),
    ]
    with pytest.raises(GovernanceBlock, match=key):
        agg.aggregate(tables, expected_ids=[1, 2])


def test_aggregate_refuses_mixed_scored_splits() -> None:
    tables = [
        _table(
            [_shard_row(1), _shard_row(2, scored_split="holdout")],
        )
    ]
    with pytest.raises(GovernanceBlock, match="mixed scored splits"):
        agg.aggregate(tables, expected_ids=[1, 2])


def test_aggregate_refuses_a_row_that_contradicts_its_own_header() -> None:
    tables = [_table([_shard_row(1, input_dataset_sha="DATASET-Z")])]
    with pytest.raises(GovernanceBlock, match="disagree with their own headers"):
        agg.aggregate(tables, expected_ids=[1])


def test_aggregate_refuses_two_files_claiming_one_shard() -> None:
    tables = [
        _table([_shard_row(1)], shard_index=0, shard_count=2),
        _table([_shard_row(2)], shard_index=0, shard_count=2, _source_file="B.json"),
    ]
    with pytest.raises(GovernanceBlock, match="appears more than once"):
        agg.aggregate(tables, expected_ids=[1, 2])


def test_ranking_is_deterministic_and_its_tie_break_is_declared_in_source() -> None:
    """The order is fixed before any table exists, and applied in that order."""
    assert agg.RANKING_POLICY["declared_before_results"] is True
    assert agg.RANKING_POLICY["primary"]["governed_metric"] == cal.PRIMARY_CALIBRATION_METRIC
    assert agg.RANKING_POLICY["winner_accuracy_may_override_primary"] is False
    assert [t["key"] for t in agg.RANKING_POLICY["tie_breaks"]] == [
        "baxter_mae",
        "movement_p95",
        "candidate_id",
    ]

    rows = [
        _shard_row(30, baxter_rmse=18.0, baxter_mae=14.0, movement_p95=1.0),
        _shard_row(10, baxter_rmse=18.0, baxter_mae=14.0, movement_p95=1.0),
        _shard_row(20, baxter_rmse=18.0, baxter_mae=14.0, movement_p95=0.5),
        _shard_row(40, baxter_rmse=17.0, baxter_mae=99.0, movement_p95=9.0),
        _shard_row(50, baxter_rmse=18.0, baxter_mae=13.0, movement_p95=9.0),
    ]
    ranked = agg.rank_rows(rows)
    assert [r["candidate_id"] for r in ranked] == [40, 50, 20, 10, 30]
    assert agg.rank_rows(list(reversed(rows))) == ranked
    # Winner accuracy is reported and may never reorder the table.
    shuffled = [dict(r, winner_accuracy=1.0 - i / 10) for i, r in enumerate(rows)]
    assert [r["candidate_id"] for r in agg.rank_rows(shuffled)] == [40, 50, 20, 10, 30]


def test_a_tie_between_inert_parameters_is_reported_not_resolved_silently() -> None:
    """The prior experiment's headline finding was a cap that never bound."""
    def cap_row(candidate_id: int, cap: float) -> dict:
        row = _shard_row(candidate_id, cap_identified=False, cap_hit_rate=0.0)
        row["parameters"] = dict(row["parameters"], weekly_movement_cap_points=cap)
        return row

    rows = [cap_row(1, 8.0), cap_row(2, 16.0)]
    ranked = agg.rank_rows(rows)
    classes = agg.equivalence_classes(ranked)
    assert len(classes) == 1
    assert classes[0]["status"] == agg.UNIDENTIFIED_EQUIVALENCE_CLASS
    assert "weekly_movement_cap_points" in classes[0]["unidentified_families"]
    assert classes[0]["movement_cap_never_binds_in_class"] is True

    identification = agg.cap_identification(rows)
    assert identification["all_levels_identified"] is False
    assert sorted(identification["levels_never_binding"]) == [8.0, 16.0]


def test_failed_rows_are_carried_not_ranked() -> None:
    """A shard that lost a candidate says why, instead of leaving a silent gap."""
    rows = [
        _shard_row(1),
        _shard_row(
            2,
            failure_status=scoring.FAILURE_INPUT,
            failure_reason="degenerate",
            baxter_rmse=None,
            baxter_mae=None,
            movement_p95=None,
        ),
    ]
    report = agg.aggregate([_table(rows)], expected_ids=[1, 2])
    assert report["coverage"]["complete"] is True
    assert report["failure_count"] == 1
    assert report["failures"][0]["failure_reason"] == "degenerate"
    assert report["ranked_count"] == 1
    assert report["winner"]["candidate_id"] == 1


# --- staged flow, end to end -------------------------------------------------


def test_four_workers_reconstruct_one_search_exactly(
    observations: scoring.ObservationSet,
    authority: scoring.ExpectedMarginAuthority,
    universe: tuple[search.CalibrationCandidate, ...],
    tmp_path: Path,
) -> None:
    """The whole point: disjoint workers, one universe, one verified aggregate."""
    subset = search.explicit_space(
        universe[:32], space_id="E2E", stage=search.STAGE_COARSE
    )
    candidates = subset.enumerate()

    for index in range(4):
        shard = search.shard_candidates(candidates, 4, index)
        rows = scoring.score_shard(
            shard,
            observations,
            authority,
            stage=search.STAGE_COARSE,
            shard_index=index,
            shard_count=4,
            config_sha=subset.config_sha,
            model_version=MODEL_VERSION,
        )
        assert len(rows) == len(shard)
        table = scoring.shard_table_as_dict(
            rows,
            stage=search.STAGE_COARSE,
            shard_index=index,
            shard_count=4,
            observations=observations,
            authority=authority,
            config_sha=subset.config_sha,
            model_version=MODEL_VERSION,
        )
        assert table["parameters_promoted"] == 0
        assert table["writes_canonical_config"] is False
        (tmp_path / f"SHARD_{index}.json").write_text(
            json.dumps(table), encoding="utf-8"
        )

    tables = agg.load_shard_tables(tmp_path)
    report = agg.aggregate(
        tables,
        expected_ids=[c.candidate_id for c in candidates],
        holdout_shortlist_limit=4,
    )
    assert report["coverage"] == {
        "expected": 32,
        "received": 32,
        "missing": 0,
        "duplicates": 0,
        "unexpected": 0,
        "complete": True,
    }
    assert report["failure_count"] == 0
    assert report["shard_indices"] == [0, 1, 2, 3]
    assert report["parameters_promoted"] == 0
    assert report["writes_canonical_config"] is False
    assert report["promotion_authority_conferred"] is None
    assert len(report["holdout_shortlist"]) == 4
    assert report["winner"]["game_sd_method"] == scoring.GAME_SD_METHOD_RESIDUAL
    assert report["ranking_policy_sha"] == agg.ranking_policy_sha()

    # Every required shard-output field is present on every emitted row.
    required = {
        "candidate_id", "parameters", "stage", "shard_index", "train_count",
        "validation_count", "baxter_rmse", "baxter_mae", "brier_score", "log_loss",
        "winner_accuracy", "cap_hit_count", "cap_hit_rate", "movement_mean",
        "movement_sd", "movement_p95", "movement_max", "colley_rank_correlation",
        "srs_rank_correlation", "failure_status", "failure_reason",
        "input_dataset_sha", "split_sha", "expected_margin_authority_id",
        "experiment_config_sha",
    }
    for table in tables:
        for row in table["rows"]:
            assert required <= set(row)


def test_the_holdout_is_scored_once_and_then_sealed() -> None:
    ledger = search.HoldoutLedger(split_sha="SPLIT-A", dataset_sha="DATASET-A")
    receipt = ledger.consume(config_sha="CONFIG-A", candidate_ids=[7, 3, 3])
    assert receipt["status"] == search.HOLDOUT_SEALED
    assert receipt["candidate_ids"] == [3, 7]
    with pytest.raises(GovernanceBlock, match=search.HOLDOUT_REFUSED_SECOND_LOOK):
        ledger.consume(config_sha="CONFIG-B", candidate_ids=[7])


def test_the_holdout_shortlist_is_capped(
    space: search.SearchSpace, universe: tuple[search.CalibrationCandidate, ...]
) -> None:
    """Scoring a wide field against the holdout and taking the best is selection."""
    shortlist = search.holdout_space(universe[:4], parent=space)
    assert shortlist.stage == search.STAGE_HOLDOUT
    assert shortlist.size == 4
    assert shortlist.parent_config_sha == space.config_sha
    with pytest.raises(GovernanceBlock, match="exceeds the maximum"):
        search.holdout_space(universe[:50], parent=space)
    ledger = search.HoldoutLedger(split_sha="S", dataset_sha="D")
    with pytest.raises(GovernanceBlock, match="maximum"):
        ledger.consume(config_sha="C", candidate_ids=range(50))


def test_a_derived_stage_universe_may_not_be_invented_by_a_worker() -> None:
    """Refinement and holdout grids come from an earlier ranking, never from a worker."""
    assert search.space_for_stage(search.STAGE_COARSE).stage == search.STAGE_COARSE
    for stage in (search.STAGE_REFINEMENT, search.STAGE_HOLDOUT):
        with pytest.raises(GovernanceBlock, match="no standing space definition"):
            search.space_for_stage(stage)


# --- operator interface ------------------------------------------------------


def test_search_cli_plans_without_inputs_and_refuses_to_score(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = search.main(
        [
            "--stage", "coarse",
            "--shard-count", "4",
            "--shard-index", "0",
            "--plan",
            "--output-dir", str(tmp_path),
        ]
    )
    assert code == 0
    written = json.loads(
        (tmp_path / "PLAN_coarse_shard0of4.json").read_text(encoding="utf-8")
    )
    assert written["candidate_count"] == search.coarse_space().size
    assert written["parameters_promoted"] == 0
    assert written["shard_partition_proofs"]["4"]["missing"] == 0
    assert written["shard_partition_proofs"]["8"]["duplicates"] == 0
    assert written["historical_research_context"]["usable_as_anchor"] is False
    capsys.readouterr()

    assert search.main(["--stage", "coarse", "--shard-count", "4", "--shard-index", "0"]) == 2
    blocked = json.loads(capsys.readouterr().err)
    assert blocked["status"] == "BLOCKED"
    assert blocked["parameters_promoted"] == 0

    assert (
        search.main(
            ["--plan", "--expect-config-sha", "not-the-space", "--output-dir", str(tmp_path)]
        )
        == 2
    )
    assert "Refusing to search a universe" in capsys.readouterr().err


def test_aggregate_cli_refuses_results_from_a_universe_it_cannot_enumerate(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "SHARD_0.json").write_text(
        json.dumps(_table([_shard_row(1)])), encoding="utf-8"
    )
    assert agg.main(["--input", str(tmp_path)]) == 2
    assert "is not the universe this process can enumerate" in capsys.readouterr().err

    (tmp_path / "SHARD_0.json").write_text(
        json.dumps(_table([_shard_row(1)], stage="refinement")), encoding="utf-8"
    )
    assert agg.main(["--input", str(tmp_path)]) == 2
    assert "coarse stage" in capsys.readouterr().err


# --- nothing is promoted -----------------------------------------------------


def test_the_orchestrator_promotes_nothing_and_writes_no_canonical_config() -> None:
    """The strongest output of this whole lane is a ranked table."""
    config_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "dynamic_weekly_mc_v3"
        / "v3_experimental.json"
    )
    canonical = json.loads(config_path.read_text(encoding="utf-8"))
    assert all(canonical["calibration"][f] is None for f in cal.CALIBRATION_FIELDS)

    space = search.coarse_space()
    assert space.as_dict()["range_authority"] is None
    plan = search.plan_as_dict(space)
    assert plan["parameters_promoted"] == 0
    assert plan["writes_canonical_config"] is False

    # The only promotion path in the repository still refuses without a token.
    regime = cal.CandidateRegime(
        regime_id="ORCHESTRATOR-DOES-NOT-PROMOTE", values={}, rationale="test"
    )
    with pytest.raises(GovernanceBlock):
        cal.promote_regime(regime, ranked_first=True)


# --- the lane record ---------------------------------------------------------


def test_the_orchestrator_record_is_byte_identical_to_the_committed_reference(
    tmp_path: Path,
) -> None:
    """Regenerating the record must reproduce the committed bytes exactly.

    This is what makes the reference artifact a measurement rather than a
    snapshot somebody took once: a change to the universe, the ranking policy or
    the input contract that is not reflected in the committed record fails here.
    """
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
        calibration_orchestrator as orch,
    )

    emitted = orch.write_orchestrator_record(tmp_path / "record.json").read_bytes()
    committed = (
        Path(__file__).resolve().parents[2]
        / "reference"
        / "dynamic_weekly_mc_v3"
        / "V3_CALIBRATION_ORCHESTRATOR_R1.json"
    )
    assert emitted == committed.read_bytes()
    assert b"\r" not in emitted
    assert emitted.endswith(b"}\n")
    assert orch.write_orchestrator_record(tmp_path / "again.json").read_bytes() == emitted


def test_readiness_is_computed_from_the_real_gates(
    observations: scoring.ObservationSet,
) -> None:
    """It must flip on admissible inputs, not on an edited constant.

    And it must report the three dependencies that actually block a research run.
    Neither a ruling on the search ranges nor a ruling on the historical point
    scale is among them any longer.
    """
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
        calibration_orchestrator as orch,
    )

    today = orch.readiness()
    assert today["machinery_complete"] is True
    assert today["real_calibration_executable"] is False
    assert {b["input"] for b in today["blocking_inputs"]} == set(
        orch.REAL_EXECUTION_DEPENDENCIES
    )
    assert len(orch.REAL_EXECUTION_DEPENDENCIES) == 3

    # The two corrected gates are open and neither asks for a ruling.
    assert today["search_ranges_executable"] is True
    assert today["search_range_status"] == search.EVIDENCE_PREDECLARED
    assert today["search_range_ruling_required"] is False
    assert today["historical_point_scale"]["ruling_required"] is False
    assert (
        today["historical_point_scale"]["status"] == scoring.SCALE_EXPERIMENT_BOUND
    )
    assert today["governed_model_structure"]["counts_as_lane_dependency"] is False
    assert orch.terminal_status() == orch.TERMINAL_READY_FOR_INPUTS

    # Supplying every real input clears every blocker; nothing else is waiting.
    ready = orch.readiness(
        observations=observations,
        structure=fixture.governed_structure_for_tests(),
        opening_state=fixture.fixture_opening_standardized_state(),
        venue_classification=fixture.fixture_venue_classification(),
    )
    assert ready["blocking_inputs"] == []
    assert ready["real_calibration_executable"] is True

    # A corpus whose transform disagrees still fails, so the gate is real.
    broken = orch.readiness(
        observations=observations,
        structure=fixture.governed_structure_for_tests(hfa_points=9.0),
        opening_state=fixture.fixture_opening_standardized_state(),
        venue_classification=fixture.fixture_venue_classification(),
    )
    assert broken["corpus_mounted"] is False


# --- stage 0: historical point-scale identification --------------------------


@pytest.fixture(scope="module")
def structure() -> scoring.ExpectedMarginAuthority:
    return fixture.governed_structure_for_tests()


@pytest.fixture(scope="module")
def opening_state() -> stage0.SealedInput:
    return fixture.fixture_opening_standardized_state()


@pytest.fixture(scope="module")
def venue_classification() -> stage0.SealedInput:
    return fixture.fixture_venue_classification()


def test_the_point_scale_is_an_experimental_candidate_not_an_authority() -> None:
    """It is empirically calibratable, so it needs no ruling in order to be tried."""
    grid = stage0.default_point_scale_space()
    assert grid.evidence_status == search.EVIDENCE_PREDECLARED
    assert grid.as_dict()["confers_promotion_authority"] is False

    candidate = grid.enumerate()[0]
    assert candidate.status == scoring.SCALE_EXPERIMENT_BOUND
    assert candidate.as_dict()["confers_promotion_authority"] is False

    # An experiment-bound scale is admissible for research and refused for promotion.
    experimental = fixture.governed_structure_for_tests(
        points_per_standardized_unit=10.0
    )
    assert scoring.require_governed_structure(experimental) is experimental
    with pytest.raises(GovernanceBlock, match="canonical promotion requires"):
        scoring.require_canonical_scale(experimental)
    with pytest.raises(GovernanceBlock):
        scoring.require_governed_authority(experimental)

    # The scale is one of the experimental values, never one of the structure fields.
    assert (
        "historical_points_per_standardized_unit"
        in scoring.EXPERIMENTAL_CALIBRATION_VALUES
    )
    assert "historical_points_per_standardized_unit" not in (
        scoring.GOVERNED_STRUCTURE_FIELDS
    )


def test_week_1_2_scale_scoring_uses_no_rerating_parameter(
    observations: scoring.ObservationSet,
    structure: scoring.ExpectedMarginAuthority,
    opening_state: stage0.SealedInput,
) -> None:
    """The whole point of Stage 0: one unknown, so the scale is identified.

    If a coefficient, cap, recent-form weighting or regularization entered here,
    the scale would be confounded with it and no later stage could separate them.
    """
    window = stage0.weeks_1_2_rows(observations)
    assert window
    assert {int(r.week) for r in window} <= set(stage0.stage0_weeks)

    result = stage0.score_point_scale(
        stage0.PointScaleCandidate(12.0),
        observations=observations,
        structure=structure,
        opening_state=opening_state,
    )
    assert result.rerating_parameters_used == 0
    assert result.as_dict()["rerating_parameters_used"] == 0
    assert result.scored_count > 0
    assert result.rmse > 0.0


def test_week_1_2_expected_margin_moves_with_the_point_scale(
    observations: scoring.ObservationSet,
    structure: scoring.ExpectedMarginAuthority,
    opening_state: stage0.SealedInput,
) -> None:
    """A scale that changed nothing could not be identified by any amount of data."""
    scored = {
        k: stage0.score_point_scale(
            stage0.PointScaleCandidate(k),
            observations=observations,
            structure=structure,
            opening_state=opening_state,
        ).rmse
        for k in (4.0, 12.0, 40.0)
    }
    assert len({round(v, 9) for v in scored.values()}) == 3

    # And the arithmetic itself is the declared one: points are k * standardized.
    at_ten = structure.with_scale(10.0)
    at_twenty = structure.with_scale(20.0)
    assert at_ten.expected_margin_from_standardized(1.0, 0.0, "NEUTRAL") == pytest.approx(
        10.0
    )
    assert at_twenty.expected_margin_from_standardized(
        1.0, 0.0, "NEUTRAL"
    ) == pytest.approx(20.0)


def test_stage_0_recovers_the_scale_its_corpus_was_generated_at(
    structure: scoring.ExpectedMarginAuthority,
    opening_state: stage0.SealedInput,
    venue_classification: stage0.SealedInput,
) -> None:
    """Identifiability, demonstrated rather than assumed.

    Run against a low-noise corpus whose true scale is known, the ranked leader
    must be that scale. On the default noisy fixture the estimate is attenuated by
    sampling error, which is a property of 24 Weeks 1-2 games rather than of the
    estimator, so the instrument is quietened here instead of the claim weakened.
    """
    quiet = fixture.fixture_observations(noise_points=1.0)
    report = stage0.identify_point_scale(
        observations=quiet,
        structure=structure,
        opening_state=opening_state,
        venue_classification=venue_classification,
    )
    assert report["leader"]["points_per_standardized_unit"] == pytest.approx(
        fixture.TRUE_POINT_SCALE
    )
    assert report["boundary_report"]["status"] == search.INTERIOR_OPTIMUM
    assert report["expansion_required"] is False
    assert report["scale_selected"] is False
    assert report["parameters_promoted"] == 0
    assert report["writes_canonical_config"] is False
    assert report["primary_objective"] == stage0.STAGE0_PRIMARY_OBJECTIVE


def test_a_scale_optimum_on_the_boundary_expands_rather_than_concludes(
    structure: scoring.ExpectedMarginAuthority,
    opening_state: stage0.SealedInput,
    venue_classification: stage0.SealedInput,
) -> None:
    """The grid running out is not an optimum."""
    quiet = fixture.fixture_observations(noise_points=1.0)
    narrow = stage0.PointScaleSpace(space_id="NARROW", levels=(2.0, 4.0, 6.0, 8.0))
    report = stage0.identify_point_scale(
        observations=quiet,
        structure=structure,
        opening_state=opening_state,
        venue_classification=venue_classification,
        space=narrow,
    )
    assert report["boundary_report"]["status"] == search.BOUNDARY_OPTIMUM
    assert report["boundary_report"]["edge"] == "high"
    assert report["expansion_required"] is True

    widened = stage0.expand_point_scale_space(
        narrow, stage0.PointScaleCandidate(report["leader"]["points_per_standardized_unit"])
    )
    assert max(widened.levels) > max(narrow.levels)
    assert widened.parent_config_sha == narrow.config_sha
    assert widened.config_sha != narrow.config_sha

    # An interior optimum has no boundary to expand past, and says so.
    with pytest.raises(InputValidationError, match="interior"):
        stage0.expand_point_scale_space(widened, stage0.PointScaleCandidate(6.0))


def test_stage_0_refuses_to_select_a_scale_against_the_holdout(
    observations: scoring.ObservationSet,
    structure: scoring.ExpectedMarginAuthority,
    opening_state: stage0.SealedInput,
) -> None:
    with pytest.raises(GovernanceBlock, match="may not select a scale against the holdout"):
        stage0.score_point_scale(
            stage0.PointScaleCandidate(12.0),
            observations=observations,
            structure=structure,
            opening_state=opening_state,
            scored_split="holdout",
        )


def test_stage_0_refuses_without_its_real_inputs() -> None:
    """Called with nothing it names the three dependencies rather than estimating."""
    with pytest.raises(GovernanceBlock) as excinfo:
        stage0.identify_point_scale()
    message = str(excinfo.value)
    for dependency in (
        "AUDITED_HISTORICAL_OBSERVATION_CORPUS",
        "HISTORICAL_OPENING_STANDARDIZED_STATE",
        "DEFENSIBLE_VENUE_HFA_CLASSIFICATION",
    ):
        assert dependency in message

    plan = stage0.stage0_plan()
    assert plan["ruling_required"] is False
    assert plan["rerating_parameters_used"] == 0
    assert plan["scale_selected"] is False
    assert plan["window_weeks"] == [1, 2]


def test_stage_0_inputs_arrive_sealed_and_are_never_read_from_a_sibling_worktree(
    tmp_path: Path,
) -> None:
    """A digest-bound payload can be cited; a path into another lane cannot."""
    sealed = fixture.fixture_opening_standardized_state()
    assert sealed.verify() == sealed.sha256
    assert stage0.require_sealed(
        sealed, producer=stage0.PRODUCER_OPENING_STATE
    ) is sealed

    tampered = stage0.SealedInput(
        input_id=sealed.input_id,
        producer=sealed.producer,
        sha256=sealed.sha256,
        payload={**sealed.payload, "2021|T000": 999.0},
    )
    with pytest.raises(GovernanceBlock, match="not the bytes supplied"):
        tampered.verify()

    with pytest.raises(GovernanceBlock, match="expected"):
        stage0.require_sealed(sealed, producer=stage0.PRODUCER_VENUE_CLASSIFICATION)
    with pytest.raises(GovernanceBlock, match="none was supplied"):
        stage0.require_sealed(None, producer=stage0.PRODUCER_OPENING_STATE)
    with pytest.raises(GovernanceBlock, match="expects"):
        stage0.require_sealed(
            sealed, producer=stage0.PRODUCER_OPENING_STATE, expected_sha="00" * 32
        )

    repo_root = Path(__file__).resolve().parents[2]
    stage0.refuse_direct_worktree_read(repo_root / "src", repo_root=repo_root)
    with pytest.raises(GovernanceBlock, match="outside"):
        stage0.refuse_direct_worktree_read(tmp_path, repo_root=repo_root)


def test_stage_0_fails_closed_on_a_game_with_no_opening_state(
    observations: scoring.ObservationSet,
    structure: scoring.ExpectedMarginAuthority,
) -> None:
    """A missing opening strength is refused, never treated as zero."""
    thin = stage0.SealedInput.seal(
        input_id="THIN",
        producer=stage0.PRODUCER_OPENING_STATE,
        payload={"2021|T000": 0.5},
    )
    with pytest.raises(GovernanceBlock, match="no opening standardized state"):
        stage0.score_point_scale(
            stage0.PointScaleCandidate(12.0),
            observations=observations,
            structure=structure,
            opening_state=thin,
        )


def test_stage_0_shards_by_the_same_arithmetic_as_stage_1() -> None:
    grid = stage0.default_point_scale_space()
    candidates = grid.enumerate()
    seen: set[int] = set()
    for index in range(4):
        member = {
            c.candidate_id for c in stage0.shard_point_scale(candidates, 4, index)
        }
        assert not (member & seen)
        seen |= member
    assert seen == {c.candidate_id for c in candidates}
    with pytest.raises(InputValidationError):
        stage0.shard_point_scale(candidates, 3, 0)


# --- FCS exclusion -----------------------------------------------------------


def test_fcs_games_are_excluded_from_every_calibration_path(
    observations: scoring.ObservationSet,
    structure: scoring.ExpectedMarginAuthority,
    opening_state: stage0.SealedInput,
) -> None:
    """Their point scale is a separate open blocker, so they are not fitted here."""
    report = observations.fcs_exclusion_report()
    assert report["excluded_count"] > 0
    assert report["policy"] == scoring.FCS_FAIL_CLOSED
    assert report["blocker"] == "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER"

    fcs_ids = {r.game_id for r in observations.ordered_rows if r.is_fcs}
    assert fcs_ids
    assert not fcs_ids & {r.game_id for r in observations.calibration_rows}

    # Stage 1 never predicts them.
    scored = scoring.score_candidate(_candidate(), observations, structure)
    assert not fcs_ids & {p.game_id for p in scored.predictions}

    # Stage 0 never scores them either - and their opponents deliberately carry no
    # opening state, so a regression that stopped excluding them fails loudly.
    assert not fcs_ids & {r.game_id for r in stage0.weeks_1_2_rows(observations)}
    stage0.score_point_scale(
        stage0.PointScaleCandidate(12.0),
        observations=observations,
        structure=structure,
        opening_state=opening_state,
    )

    # An unknown division is refused rather than assumed to be FBS.
    with pytest.raises(InputValidationError, match="opponent_division"):
        _row(opponent_division="FCS-AA")


def test_governed_structure_is_required_and_the_scale_is_not(
    observations: scoring.ObservationSet,
) -> None:
    """A. is demanded, B. is permitted - the correction in one assertion."""
    with pytest.raises(GovernanceBlock, match="No expected-margin authority"):
        scoring.require_governed_structure(None)
    with pytest.raises(GovernanceBlock, match="structure status"):
        scoring.require_governed_structure(fixture.fixture_authority())

    # Governed structure with no scale at all is fine for a Stage 1 walk, whose
    # corpus already carries points.
    no_scale = fixture.governed_structure_for_tests()
    assert no_scale.scale_status == scoring.SCALE_NOT_APPLICABLE
    assert scoring.score_candidate(_candidate(), observations, no_scale).metrics[
        "baxter_rmse"
    ] > 0.0

    # But asking it to convert a standardized state refuses, because that is a
    # structural input this particular computation needs and does not have.
    with pytest.raises(GovernanceBlock, match="no points_per_standardized_unit"):
        no_scale.expected_margin_from_standardized(1.0, 0.0, "NEUTRAL")


def test_the_governed_structure_states_the_semantics_it_governs() -> None:
    structure = fixture.governed_structure_for_tests(hfa_points=3.5)
    payload = structure.as_dict()
    assert payload["subject_orientation"] == "SUBJECT_TEAM_PERSPECTIVE"
    assert payload["point_domain"] == "V3_FOOTBALL_POINTS"
    assert payload["first_promoted_rerating_after_week"] == 2
    assert payload["fcs_policy"] == scoring.FCS_FAIL_CLOSED
    assert structure.signed_venue_adjustment("HOME") == 3.5
    assert structure.signed_venue_adjustment("AWAY") == -3.5
    assert structure.signed_venue_adjustment("NEUTRAL") == 0.0

    # The governed structure may not contradict V3's weekly rule or FCS policy.
    with pytest.raises(GovernanceBlock, match="first promoted rerating"):
        replace(structure, first_promoted_rerating_after_week=1)
    with pytest.raises(GovernanceBlock, match="FCS policy"):
        replace(structure, fcs_policy="FCS_INCLUDED")


def test_the_record_states_the_operator_interface_and_promotes_nothing() -> None:
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
        calibration_orchestrator as orch,
    )

    record = orch.orchestrator_record()
    assert record["terminal"] == orch.TERMINAL_READY_FOR_INPUTS
    assert record["promotions"]["parameters_promoted"] == 0
    assert record["promotions"]["canonical_writer_created"] is False
    assert record["promotions"]["blockers_retired"] == 0
    assert record["promotions"]["season_monte_carlo_executed"] is False
    assert record["promotions"]["real_calibration_executed"] is False

    assert record["objective"]["primary_metric"] == cal.PRIMARY_CALIBRATION_METRIC
    assert record["objective"]["witness_composite_authorised"] is False
    assert record["objective"]["winner_accuracy_may_override_primary"] is False
    assert (
        record["game_sd_points"]["admissible_method"] == scoring.GAME_SD_METHOD_RESIDUAL
    )
    assert record["game_sd_points"]["influences_mean_model_selection"] is False
    assert record["temporal_controls"]["first_promoted_rerating_after_week"] == 2
    assert record["temporal_controls"]["random_split_permitted"] is False
    assert record["operator_interface"]["worker_may_choose_its_own_grid"] is False
    assert record["operator_interface"]["range_authority_flag_required"] is False

    # The two corrected gates, as the record states them.
    assert record["search_ranges"]["status"] == search.EVIDENCE_PREDECLARED
    assert record["search_ranges"]["ruling_required"] is False
    assert record["search_ranges"]["breadth"]["broad_enough"] is True
    assert record["stage0"]["ruling_required"] is False
    assert record["stage0"]["rerating_parameters_used"] == 0
    assert record["promotions"]["point_scale_selected"] is False
    assert list(record["stage_plan"])[0] == search.STAGE_POINT_SCALE
    assert record["real_execution_dependencies"] == [
        "AUDITED_HISTORICAL_OBSERVATION_CORPUS",
        "HISTORICAL_OPENING_STANDARDIZED_STATE",
        "DEFENSIBLE_VENUE_HFA_CLASSIFICATION",
    ]
    assert record["fcs_policy"]["policy"] == scoring.FCS_FAIL_CLOSED

    for count in ("1", "2", "4", "8"):
        proof = record["shard_partition_proofs"][count]
        assert proof["missing"] == 0 and proof["duplicates"] == 0
        assert proof["union_size"] == record["coarse_universe"]["candidate_count"]


def test_the_formal_blocker_set_is_untouched_by_this_lane() -> None:
    """Building search machinery retires nothing, and adds no blocker of its own."""
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report as br

    live = br.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    assert len(live) == 8
    assert not any("orchestrator" in b.lower() or "search" in b.lower() for b in live)
