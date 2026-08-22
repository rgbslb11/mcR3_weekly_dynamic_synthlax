"""Deterministic calibration metric package.

What this file proves, in the order the metric package can fail:

* the arithmetic is right, against hand-computed values rather than against
  itself;
* residual SD is not margin SD, which is the substitution that would corrupt a
  future ``game_sd_points`` determination while looking correct;
* holdout cannot be ranked without a deliberate, attributable release;
* the result of scoring a candidate does not depend on row order, candidate
  order, or how the candidate set was sharded -- the property the calibration
  search will rely on and cannot verify for itself;
* the two unavailable inputs (no governed probability conversion, no mounted
  Colley implementation) fail closed with named reasons rather than producing
  plausible numbers.

Values in the arithmetic tests are chosen so the expected answer is exact in
binary floating point, so an assertion failure means the formula is wrong and
never that the last bit moved.
"""

from __future__ import annotations

import dataclasses
import json
import math

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_metrics as cm
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration import (
    PRIMARY_CALIBRATION_DIRECTION,
    PRIMARY_CALIBRATION_METRIC,
    PRIMARY_OBJECTIVE,
    EvaluationObjective,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

RELEASE = "RELEASE_V3_CALIBRATION_HOLDOUT::LANE_TEST"


# --- fixtures -----------------------------------------------------------------


def _row(
    game_id: str,
    actual: float,
    predicted: float,
    *,
    candidate_id: str = "C1",
    season: int = 2022,
    order_index: int = 0,
    week: int | None = 1,
    split: str = "validation",
    probability: float | None = None,
    fold_id: str | None = None,
    team: str | None = None,
    opponent: str | None = None,
) -> cm.ReplayRow:
    return cm.ReplayRow(
        candidate_id=candidate_id,
        game_id=game_id,
        season=season,
        order_index=order_index,
        week=week,
        split=split,
        actual_margin=actual,
        predicted_margin=predicted,
        team=team or f"HOME_{game_id}",
        opponent=opponent or f"AWAY_{game_id}",
        predicted_win_probability=probability,
        fold_id=fold_id,
    )


def _replay(rows, *, candidate_id: str = "C1", **kwargs) -> cm.CandidateReplay:
    return cm.CandidateReplay(
        candidate_id=candidate_id,
        rows=tuple(rows),
        input_dataset_sha="DATASET_SHA_FIXTURE",
        split_sha="SPLIT_SHA_FIXTURE",
        experiment_config_sha="CONFIG_SHA_FIXTURE",
        **kwargs,
    )


def _three_split_rows(candidate_id: str = "C1", offset: float = 0.0):
    """Rows populating all three splits temporally, one candidate."""
    rows = []
    for i in range(9):
        split = "training" if i < 3 else ("validation" if i < 6 else "holdout")
        rows.append(
            _row(
                f"G{i}",
                actual=10.0 + i,
                predicted=10.0 + i + offset + (2.0 if i % 2 else -2.0),
                candidate_id=candidate_id,
                season=2020 + (i // 3),
                order_index=i,
                week=1 + i,
                split=split,
            )
        )
    return rows


# --- RMSE, MAE, bias: hand-computed ------------------------------------------


def test_rmse_matches_a_hand_computed_value():
    # residuals 3, -4, 0, 12 -> mean square (9+16+0+144)/4 = 42.25 -> 6.5
    assert cm.rmse([3.0, -4.0, 0.0, 12.0]) == 6.5


def test_mae_matches_a_hand_computed_value():
    # (3 + 4 + 0 + 12) / 4 = 4.75
    assert cm.mae([3.0, -4.0, 0.0, 12.0]) == 4.75


def test_bias_is_the_signed_mean_and_keeps_its_sign():
    # (3 - 4 + 0 + 12) / 4 = 2.75
    assert cm.bias([3.0, -4.0, 0.0, 12.0]) == 2.75
    assert cm.bias([-3.0, 4.0, 0.0, -12.0]) == -2.75


def test_median_absolute_error_interpolates_on_an_even_sample():
    # |r| sorted: 0, 3, 4, 12 -> median (3 + 4) / 2 = 3.5
    assert cm.median_absolute_error([3.0, -4.0, 0.0, 12.0]) == 3.5


def test_empty_samples_report_none_rather_than_zero():
    assert cm.rmse([]) is None
    assert cm.mae([]) is None
    assert cm.bias([]) is None
    assert cm.median_absolute_error([]) is None


def test_rmse_over_replay_rows_uses_actual_minus_predicted():
    rows = [_row("A", 20.0, 14.0), _row("B", -3.0, 5.0)]
    # residuals 6 and -8 -> sqrt((36 + 64) / 2) = sqrt(50)
    record = cm.evaluate_candidate(_replay(rows))
    assert record.primary_metric_value == pytest.approx(math.sqrt(50.0), abs=1e-12)
    assert record.out_of_sample_mae == 7.0
    assert record.bias == -1.0
    assert record.absolute_bias == 1.0


def test_the_primary_metric_is_the_governed_one_under_its_governed_key():
    record = cm.evaluate_candidate(_replay([_row("A", 10.0, 7.0)]))
    payload = record.as_dict()
    assert record.primary_metric == PRIMARY_CALIBRATION_METRIC
    assert payload[PRIMARY_CALIBRATION_METRIC] == 3.0
    assert payload["primary_direction"] == PRIMARY_CALIBRATION_DIRECTION


# --- in-sample substitution ---------------------------------------------------


def test_a_training_split_score_cannot_be_requested_as_the_primary_metric():
    replay = _replay(_three_split_rows())
    with pytest.raises(GovernanceBlock, match="out-of-sample"):
        cm.evaluate_candidate(replay, evaluation_split="training")


def test_training_metrics_remain_visible_for_diagnosis_under_by_split():
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    assert record.by_split["training"]["games"] == 3
    assert record.by_split["training"]["rmse"] is not None
    assert record.evaluation_split == "validation"


def test_the_headline_numbers_come_only_from_the_evaluation_split():
    rows = _three_split_rows()
    # Wreck training only. The validation score must not move.
    wrecked = [
        dataclasses.replace(r, predicted_margin=r.predicted_margin + 500.0)
        if r.split == "training"
        else r
        for r in rows
    ]
    assert (
        cm.evaluate_candidate(_replay(wrecked)).primary_metric_value
        == cm.evaluate_candidate(_replay(rows)).primary_metric_value
    )


# --- winner accuracy ----------------------------------------------------------


def test_winner_accuracy_counts_sign_agreement():
    rows = [
        _row("A", 10.0, 3.0),    # both positive  -> correct
        _row("B", -10.0, -3.0),  # both negative  -> correct
        _row("C", 10.0, -3.0),   # disagree       -> wrong
    ]
    assert cm.winner_accuracy(rows)["accuracy"] == pytest.approx(2 / 3, abs=1e-12)


def test_a_true_tie_leaves_the_denominator_and_a_declined_pick_does_not():
    rows = [
        _row("A", 10.0, 3.0),   # correct
        _row("B", 0.0, 3.0),    # true tie: excluded entirely
        _row("C", 10.0, 0.0),   # declined pick: scored incorrect, stays in denominator
    ]
    result = cm.winner_accuracy(rows)
    assert result["actual_ties_excluded"] == 1
    assert result["no_pick_scored_incorrect"] == 1
    assert result["decidable_games"] == 2
    assert result["accuracy"] == 0.5


def test_a_winner_contradicting_the_margin_is_refused_at_construction():
    with pytest.raises(InputValidationError, match="implies"):
        cm.ReplayRow(
            candidate_id="C1",
            game_id="G",
            season=2022,
            order_index=0,
            split="validation",
            actual_margin=7.0,
            predicted_margin=3.0,
            team="ALPHA",
            opponent="BETA",
            winner="BETA",
        )


# --- residual SD is not margin SD --------------------------------------------


def test_residual_sd_and_actual_margin_sd_are_different_quantities():
    """The substitution that would silently corrupt a game_sd_points fit.

    Margins here are widely spread and the candidate tracks them almost exactly,
    so SD(actual) is large while SD(residual) is small. A package that conflated
    them would report the same number twice.
    """
    rows = [
        _row("A", 42.0, 41.0),
        _row("B", -35.0, -36.0),
        _row("C", 3.0, 4.0),
        _row("D", -1.0, -2.0),
    ]
    package = cm.residual_package(rows)
    # residuals are 1, 1, -1, 1 -> sample SD exactly 1.0
    assert package["residual_sd"] == 1.0
    assert package["actual_margin_sd"] == pytest.approx(31.51058023373525, abs=1e-9)
    assert package["residual_sd"] < package["actual_margin_sd"]
    assert package["residual_sd_is_not_actual_margin_sd"] is True


def test_residual_sd_uses_ddof_one_and_abstains_on_a_single_observation():
    # residuals 1, 3 -> mean 2, sum sq dev 2, / (n-1) = 2 -> sqrt(2)
    two = cm.residual_package([_row("A", 11.0, 10.0), _row("B", 13.0, 10.0)])
    assert two["residual_sd"] == pytest.approx(math.sqrt(2.0), abs=1e-12)
    one = cm.residual_package([_row("A", 11.0, 10.0)])
    assert one["residual_sd"] is None
    assert one["count"] == 1


def test_naming_margin_sd_as_residual_sd_is_refused():
    for name in ("actual_margin_sd", "MARGIN_SD", "observed_margin_sd"):
        with pytest.raises(GovernanceBlock, match="spread of observed margins"):
            cm.reject_actual_margin_sd_as_residual_sd(name)
    # The legitimate name passes.
    assert cm.reject_actual_margin_sd_as_residual_sd("residual_sd") is None


def test_the_residual_package_does_not_determine_game_sd_points():
    package = cm.residual_package([_row("A", 11.0, 10.0), _row("B", 13.0, 10.0)])
    assert "game_sd_points" not in package
    assert "open blockers" in package["game_sd_points_note"]


def test_residual_quantiles_and_large_residual_count_are_reported():
    rows = [_row(f"G{i}", float(i), 0.0) for i in range(0, 41, 4)]
    package = cm.residual_package(rows)
    assert package["residual_quantiles"]["p50"] == 20.0
    assert package["large_residual_threshold_points"] == 21.0
    # residuals 0,4,...,40 -> those >= 21 are 24,28,32,36,40
    assert package["large_residual_count"] == 5
    assert package["quantile_method"] == cm.QUANTILE_METHOD


def test_skewness_abstains_on_a_constant_residual_stream():
    flat = [_row(f"G{i}", 10.0, 7.0, order_index=i) for i in range(5)]
    assert cm.residual_package(flat)["residual_skewness"] is None


# --- holdout isolation --------------------------------------------------------


def test_holdout_metrics_are_sealed_in_the_serialised_record():
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    payload = record.as_dict()
    assert payload["holdout"] == {"holdout": cm.SEALED, "release_required": True}
    assert cm.SEALED in json.dumps(payload)


def test_a_serialised_record_never_carries_a_holdout_score():
    """Serialisation is the leak path that a label would not close."""
    rows = _three_split_rows()
    # Make the holdout score unmistakable if it escapes.
    rows = [
        dataclasses.replace(r, predicted_margin=r.actual_margin - 777.0)
        if r.split == "holdout"
        else r
        for r in rows
    ]
    text = json.dumps(cm.evaluate_candidate(_replay(rows)).as_dict())
    assert "777" not in text
    assert "by_split" in text
    # by_split must not smuggle it either: the key is present, the score is not.
    by_split = cm.evaluate_candidate(_replay(rows)).as_dict()["by_split"]
    assert sorted(by_split) == ["holdout", "training", "validation"]
    assert by_split["holdout"] == {"holdout": cm.SEALED}
    assert by_split["validation"]["rmse"] is not None


def test_opening_the_seal_without_a_token_is_refused():
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    for bad in ("", "please", "RELEASE_V3_CALIBRATION_HOLDOUT::", None, 42):
        with pytest.raises(GovernanceBlock, match="release token"):
            record.sealed_holdout.open(bad)  # type: ignore[arg-type]


def test_opening_the_seal_with_the_token_yields_the_holdout_metrics():
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    payload = record.sealed_holdout.open(RELEASE)
    assert payload["split"] == "holdout"
    assert payload["games"] == 3
    assert payload["rmse"] is not None


@pytest.mark.parametrize("stage", [cm.STAGE_COARSE, cm.STAGE_REFINEMENT])
def test_coarse_and_refinement_stages_refuse_to_rank_holdout_scores(stage):
    records = [
        cm.evaluate_candidate(_replay(_three_split_rows(c), candidate_id=c), evaluation_split="holdout")
        for c in ("C1", "C2")
    ]
    with pytest.raises(GovernanceBlock, match="scored once"):
        cm.rank_candidates(records, stage=stage, objective=PRIMARY_OBJECTIVE)


def test_the_final_stage_ranks_holdout_only_against_a_release_token():
    records = [
        cm.evaluate_candidate(_replay(_three_split_rows(c), candidate_id=c), evaluation_split="holdout")
        for c in ("C1", "C2")
    ]
    with pytest.raises(GovernanceBlock, match="RELEASE_V3_CALIBRATION_HOLDOUT"):
        cm.rank_candidates(records, stage=cm.STAGE_FINAL_HOLDOUT, objective=PRIMARY_OBJECTIVE)
    ranked = cm.rank_candidates(
        records,
        stage=cm.STAGE_FINAL_HOLDOUT,
        objective=PRIMARY_OBJECTIVE,
        holdout_release_token=RELEASE,
    )
    assert len(ranked) == 2


def test_the_final_stage_refuses_validation_scores_presented_as_holdout():
    records = [
        cm.evaluate_candidate(_replay(_three_split_rows(c), candidate_id=c)) for c in ("C1", "C2")
    ]
    with pytest.raises(GovernanceBlock, match="ranks on the 'holdout' split"):
        cm.rank_candidates(
            records,
            stage=cm.STAGE_FINAL_HOLDOUT,
            objective=PRIMARY_OBJECTIVE,
            holdout_release_token=RELEASE,
        )


def test_mixed_split_records_are_never_ranked_together():
    validation = cm.evaluate_candidate(_replay(_three_split_rows("C1"), candidate_id="C1"))
    holdout = cm.evaluate_candidate(
        _replay(_three_split_rows("C2"), candidate_id="C2"), evaluation_split="holdout"
    )
    with pytest.raises(GovernanceBlock, match="mixed splits"):
        cm.rank_candidates(
            [validation, holdout], stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE
        )


# --- temporal partitioning ----------------------------------------------------


def test_metrics_are_reported_per_season():
    rows = [
        _row("A", 10.0, 8.0, season=2021, order_index=0),
        _row("B", 10.0, 8.0, season=2021, order_index=1),
        _row("C", 10.0, 4.0, season=2022, order_index=2),
    ]
    by_season = cm.evaluate_candidate(_replay(rows)).temporal["by_season"]
    assert sorted(by_season) == ["2021", "2022"]
    assert by_season["2021"]["games"] == 2
    assert by_season["2021"]["rmse"] == 2.0
    assert by_season["2022"]["rmse"] == 6.0
    assert sum(b["games"] for b in by_season.values()) == 3


def test_the_temporal_split_fixture_puts_one_season_in_each_partition():
    """Split policy is temporal only, so a partition does not straddle seasons."""
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    assert sorted(record.temporal["by_season"]) == ["2021"]


def test_metrics_are_reported_per_season_phase_on_the_declared_boundaries():
    rows = [
        _row("E", 10.0, 8.0, week=2, order_index=0),
        _row("M", 10.0, 8.0, week=7, order_index=1),
        _row("L", 10.0, 8.0, week=12, order_index=2),
    ]
    phases = cm.evaluate_candidate(_replay(rows)).temporal["by_phase"]
    assert phases["early_season"]["games"] == 1
    assert phases["midseason"]["games"] == 1
    assert phases["late_season"]["games"] == 1


def test_a_row_with_no_week_abstains_from_the_phase_diagnostic():
    """A postseason row has an order but not a week. It is not late season."""
    rows = [
        _row("R", 10.0, 8.0, week=12, order_index=0),
        _row("BOWL", 10.0, 8.0, week=None, order_index=1),
    ]
    temporal = cm.evaluate_candidate(_replay(rows)).temporal
    assert temporal["rows_without_week"] == 1
    assert temporal["by_phase"]["late_season"]["games"] == 1


def test_validation_folds_are_reported_when_supplied():
    rows = [
        _row("A", 10.0, 8.0, order_index=0, fold_id="F1"),
        _row("B", 10.0, 8.0, order_index=1, fold_id="F1"),
        _row("C", 10.0, 4.0, order_index=2, fold_id="F2"),
    ]
    folds = cm.evaluate_candidate(_replay(rows)).temporal["by_validation_fold"]
    assert sorted(folds) == ["F1", "F2"]
    assert folds["F1"]["rmse"] == 2.0
    assert folds["F2"]["rmse"] == 6.0


def test_season_instability_is_exposed_rather_than_pooled_away():
    """Two candidates with the same pooled RMSE, one stable and one not."""
    stable = [
        _row(f"S{i}", 10.0, 8.0, season=2020 + i // 2, order_index=i, candidate_id="STABLE")
        for i in range(4)
    ]
    swingy = [
        _row("W0", 10.0, 10.0, season=2020, order_index=0, candidate_id="SWINGY"),
        _row("W1", 10.0, 10.0, season=2020, order_index=1, candidate_id="SWINGY"),
        _row("W2", 10.0, 10.0 - math.sqrt(8.0), season=2021, order_index=2, candidate_id="SWINGY"),
        _row("W3", 10.0, 10.0 - math.sqrt(8.0), season=2021, order_index=3, candidate_id="SWINGY"),
    ]
    a = cm.evaluate_candidate(_replay(stable, candidate_id="STABLE"))
    b = cm.evaluate_candidate(_replay(swingy, candidate_id="SWINGY"))
    assert a.primary_metric_value == pytest.approx(b.primary_metric_value, abs=1e-12)
    assert a.season_rmse_sd == 0.0
    assert b.season_rmse_sd > 0.0
    assert b.temporal["season_rmse_spread"] > 0.0


# --- blowout sensitivity ------------------------------------------------------


def test_blowout_diagnostics_split_all_non_blowout_and_large_margin():
    rows = [
        _row("CLOSE", 3.0, 0.0, order_index=0),
        _row("MID", 14.0, 10.0, order_index=1),
        _row("BLOWOUT", 45.0, 15.0, order_index=2),
    ]
    diag = cm.evaluate_candidate(_replay(rows)).blowout
    assert diag["all_games"]["games"] == 3
    assert diag["non_blowout"]["games"] == 2
    assert diag["large_margin"]["games"] == 1
    assert diag["by_band"]["margin_00_07"]["games"] == 1
    assert diag["by_band"]["margin_08_14"]["games"] == 1
    assert diag["by_band"]["margin_29_plus"]["games"] == 1


def test_a_candidate_winning_only_on_blowouts_is_visible_as_such():
    """The whole purpose of the band report."""
    def _close(cid):
        return [_row(f"C{i}", 3.0, 3.0, order_index=i, candidate_id=cid) for i in range(4)]

    def _tail(cid):
        return [
            _row(f"B{i}", 40.0, 40.0, order_index=10 + i, candidate_id=cid) for i in range(4)
        ]

    # A: perfect on close games, thirty points out on every blowout.
    a_rows = _close("A") + [
        dataclasses.replace(r, predicted_margin=10.0) for r in _tail("A")
    ]
    # B: the mirror image.
    b_rows = [
        dataclasses.replace(r, predicted_margin=33.0) for r in _close("B")
    ] + _tail("B")
    a = cm.evaluate_candidate(_replay(a_rows, candidate_id="A"), evaluation_split="validation")
    b = cm.evaluate_candidate(_replay(b_rows, candidate_id="B"), evaluation_split="validation")
    assert a.primary_metric_value == pytest.approx(b.primary_metric_value, abs=1e-12)
    assert a.blowout["non_blowout"]["rmse"] == 0.0
    assert b.blowout["non_blowout"]["rmse"] == 30.0
    assert a.blowout["large_margin"]["rmse"] == 30.0
    assert b.blowout["large_margin"]["rmse"] == 0.0


def test_the_bands_are_negative_symmetric():
    """A 40-point loss and a 40-point win are the same magnitude band."""
    win = cm.evaluate_candidate(_replay([_row("W", 40.0, 30.0)])).blowout
    loss = cm.evaluate_candidate(_replay([_row("L", -40.0, -30.0)])).blowout
    assert win["by_band"]["margin_29_plus"]["games"] == 1
    assert loss["by_band"]["margin_29_plus"]["games"] == 1


def test_the_bands_are_not_a_blowout_policy():
    diag = cm.evaluate_candidate(_replay([_row("A", 3.0, 0.0)])).blowout
    assert diag["is_a_blowout_policy"] is False
    assert diag["blowout_policy_blocker"] == "calibration.blowout_treatment"
    with pytest.raises(GovernanceBlock, match="not a blowout treatment"):
        cm.reject_band_as_blowout_policy("adopt these bands as the blowout policy")


# --- movement diagnostics -----------------------------------------------------


def _moves(values, *, cap=None, flags=None, candidate_id="C1"):
    return tuple(
        cm.MovementRecord(
            candidate_id=candidate_id,
            team=f"T{i}",
            season=2022,
            order_index=i,
            week=1 + i,
            movement_points=v,
            cap_points=cap,
            cap_applied=None if flags is None else flags[i],
        )
        for i, v in enumerate(values)
    )


def test_movement_statistics_are_computed_over_absolute_movement():
    diag = cm.movement_diagnostics(_moves([2.0, -2.0, 4.0, -4.0]))
    assert diag["mean_abs_movement"] == 3.0
    assert diag["max_abs_movement"] == 4.0
    assert diag["median_abs_movement"] == 3.0
    # The signed mean is zero here; a cap diagnostic built on it would see nothing.
    assert diag["signed_mean_movement"] == 0.0


def test_movement_quantiles_cover_the_declared_set():
    diag = cm.movement_diagnostics(_moves([float(i) for i in range(1, 101)]))
    assert sorted(diag["abs_movement_quantiles"]) == ["p50", "p90", "p95", "p99"]
    assert diag["abs_movement_quantiles"]["p50"] == 50.5
    assert diag["abs_movement_quantiles"]["p99"] == pytest.approx(99.01, abs=1e-9)


def test_a_non_binding_cap_is_detected_and_reported():
    """The finding Agent 3 needs: a cap that never binds is not a parameter."""
    diag = cm.movement_diagnostics(_moves([1.0, -2.0, 3.0], cap=25.0))
    assert diag["cap_hit_count"] == 0
    assert diag["cap_hit_rate"] == 0.0
    assert diag["cap_is_binding"] is False
    assert diag["non_binding_cap_detected"] is True
    assert diag["cap_headroom_points"] == 22.0


def test_a_binding_cap_is_reported_as_binding():
    diag = cm.movement_diagnostics(_moves([1.0, -6.0, 6.0], cap=6.0))
    assert diag["cap_hit_count"] == 2
    assert diag["cap_hit_rate"] == pytest.approx(2 / 3, abs=1e-12)
    assert diag["cap_is_binding"] is True
    assert diag["non_binding_cap_detected"] is False


def test_a_producer_supplied_cap_flag_is_preferred_over_derivation():
    diag = cm.movement_diagnostics(
        _moves([1.0, 6.0, 6.0], cap=6.0, flags=[False, True, False])
    )
    assert diag["cap_hit_source"] == "OBSERVED_FROM_PRODUCER_FLAG"
    assert diag["cap_hit_count"] == 1


def test_movement_without_a_cap_reports_unavailable_rather_than_zero():
    diag = cm.movement_diagnostics(_moves([1.0, 2.0]))
    assert diag["cap_hit_count"] is None
    assert diag["cap_hit_rate"] is None
    assert diag["cap_is_binding"] is None
    assert diag["cap_hit_source"].startswith("UNAVAILABLE")


def test_absent_movement_records_fail_closed_with_a_named_reason():
    diag = cm.movement_diagnostics(())
    assert diag["available"] is False
    assert diag["unavailable_reason"] == cm.REASON_NO_MOVEMENT_RECORDS


def test_movement_diagnostics_are_order_invariant():
    values = [3.0, -1.0, 7.0, -7.0, 2.0]
    forward = cm.movement_diagnostics(_moves(values, cap=7.0))
    backward = cm.movement_diagnostics(tuple(reversed(_moves(values, cap=7.0))))
    assert forward == backward


# --- probability diagnostics: fail closed ------------------------------------


def test_brier_and_log_loss_are_withheld_without_a_governed_conversion():
    rows = [_row("A", 10.0, 7.0, probability=0.8), _row("B", -10.0, -7.0, probability=0.3)]
    diag = cm.evaluate_candidate(_replay(rows)).probability
    assert diag["available"] is False
    assert diag["brier_score"] is None
    assert diag["log_loss"] is None
    assert diag["unavailable_reason"] == cm.REASON_NO_PROBABILITY_CONVERSION
    assert diag["conversion_blocker"] == "calibration.game_sd_points"


def test_no_probabilities_at_all_is_a_distinguishable_reason():
    diag = cm.evaluate_candidate(_replay([_row("A", 10.0, 7.0)])).probability
    assert diag["unavailable_reason"] == cm.REASON_NO_PROBABILITIES_SUPPLIED


def test_the_module_exposes_no_margin_to_probability_conversion():
    """The fail-closed posture is structural: there is nothing here to call."""
    assert cm.PROBABILITY_CONVERSION_MOUNTED is False
    names = [n.lower() for n in dir(cm)]
    for forbidden in ("margin_to_probability", "spread_to_probability", "implied_probability"):
        assert forbidden not in names
    with pytest.raises(GovernanceBlock, match="game_sd_points"):
        cm.require_governed_probability_conversion(None)


def _authority():
    return cm.ProbabilityConversionAuthority(
        authority_id="FIXTURE_ONLY",
        transform_name="fixture_transform",
        evidence="test fixture; not a governed transform",
    )


def test_brier_and_log_loss_are_correct_once_an_authority_is_presented():
    # p=0.5 on both, outcomes 1 and 0 -> Brier 0.25, log loss -ln(0.5)
    rows = [
        _row("A", 10.0, 1.0, probability=0.5, order_index=0),
        _row("B", -10.0, -1.0, probability=0.5, order_index=1),
    ]
    diag = cm.evaluate_candidate(_replay(rows, probability_authority=_authority())).probability
    assert diag["available"] is True
    assert diag["brier_score"] == 0.25
    assert diag["log_loss"] == pytest.approx(math.log(2.0), abs=1e-12)
    assert diag["is_a_selection_criterion"] is False


def test_log_loss_survives_a_confidently_wrong_prediction():
    rows = [_row("A", 10.0, 1.0, probability=0.0)]
    diag = cm.evaluate_candidate(_replay(rows, probability_authority=_authority())).probability
    assert math.isfinite(diag["log_loss"])
    assert diag["log_loss"] > 30.0


def test_reliability_bins_and_ece_are_reported_where_probabilities_are_valid():
    rows = [
        _row(f"G{i}", 10.0 if i % 2 else -10.0, 1.0, probability=0.5, order_index=i)
        for i in range(10)
    ]
    diag = cm.evaluate_candidate(_replay(rows, probability_authority=_authority())).probability
    assert len(diag["reliability_bins"]) == cm.RELIABILITY_BIN_COUNT
    # Five wins out of ten at p=0.5 is perfectly calibrated.
    assert diag["expected_calibration_error"] == pytest.approx(0.0, abs=1e-12)
    populated = [b for b in diag["reliability_bins"] if b["count"]]
    assert len(populated) == 1
    assert populated[0]["mean_predicted"] == 0.5
    assert populated[0]["observed_rate"] == 0.5


def test_a_systematically_overconfident_candidate_shows_a_nonzero_ece():
    rows = [_row(f"G{i}", -10.0, 1.0, probability=0.9, order_index=i) for i in range(10)]
    diag = cm.evaluate_candidate(_replay(rows, probability_authority=_authority())).probability
    assert diag["expected_calibration_error"] == pytest.approx(0.9, abs=1e-12)
    assert diag["brier_score"] == pytest.approx(0.81, abs=1e-12)


def test_calibration_slope_and_intercept_abstain_on_a_constant_prediction():
    rows = [_row(f"G{i}", 10.0, 1.0, probability=0.6, order_index=i) for i in range(4)]
    diag = cm.evaluate_candidate(_replay(rows, probability_authority=_authority())).probability
    assert diag["calibration_slope"] is None
    assert diag["calibration_intercept"] is None


def test_an_out_of_range_probability_is_refused_at_construction():
    with pytest.raises(InputValidationError, match=r"outside \[0, 1\]"):
        _row("A", 10.0, 7.0, probability=1.4)


def test_calibration_diagnostics_stay_out_of_the_ranking():
    """Diagnostics are separate from primary model selection."""
    key_a = cm._rank_key(
        cm.evaluate_candidate(
            _replay(
                [_row("A", 10.0, 7.0, probability=0.99)],
                candidate_id="C1",
                probability_authority=_authority(),
            )
        )
    )
    key_b = cm._rank_key(
        cm.evaluate_candidate(
            _replay(
                [_row("A", 10.0, 7.0, probability=0.01)],
                candidate_id="C1",
                probability_authority=_authority(),
            )
        )
    )
    assert key_a == key_b


# --- Colley witness isolation -------------------------------------------------


def test_no_colley_implementation_is_mounted_and_none_is_written_here():
    assert cm.COLLEY_IMPLEMENTATION_MOUNTED is False
    names = [n.lower() for n in dir(cm)]
    assert "compute_colley" not in names
    assert "colley_matrix_ratings" not in names
    with pytest.raises(GovernanceBlock, match="COLLEY_MATRIX_IMPLEMENTATION_NOT_MOUNTED"):
        cm.require_no_colley_implementation_here()


def test_the_colley_witness_reports_unavailable_rather_than_a_number():
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    witness = record.colley_witness
    assert witness["available"] is False
    assert witness["unavailable_reason"] == cm.REASON_COLLEY_NOT_MOUNTED
    assert witness["blocker"] == cm.COLLEY_WITNESS_BLOCKER
    assert "spearman_rank_correlation" not in witness
    assert witness["witness_status"] == cm.WITNESS_UNAVAILABLE
    # Non-blocking: an absent witness is reported, never charged as a failure.
    assert cm.REASON_COLLEY_NOT_MOUNTED in record.non_blocking_reasons
    assert record.failure_reasons == ()


def test_a_supplied_colley_state_is_compared_but_marked_as_supplied():
    """The machinery is live; only the local implementation is refused."""
    snapshot = cm.WitnessSnapshot("colley_matrix", "2022-0005", {"A": 0.9, "B": 0.5, "C": 0.1})
    result = cm.colley_witness({"A": 30.0, "B": 10.0, "C": -5.0}, snapshot, "2022-0006")
    assert result["available"] is True
    assert result["state_source"] == "SUPPLIED_BY_CALLER_NOT_COMPUTED_HERE"
    assert result["spearman_rank_correlation"] == 1.0
    assert result["implementation_mounted"] is False


def test_the_colley_witness_never_becomes_point_strength():
    snapshot = cm.WitnessSnapshot("colley_matrix", "2022-0005", {"A": 0.9, "B": 0.5})
    result = cm.colley_witness({"A": 30.0, "B": 10.0}, snapshot, "2022-0006")
    assert result["is_blended_into_primary_criterion"] is False
    assert result["role"] == "INDEPENDENT_WITNESS"
    # Only correlations and agreement leave the witness block; no rating scalar.
    assert "points" not in json.dumps(result)


# --- SRS witness isolation ----------------------------------------------------


def test_the_srs_witness_carries_its_authority_boundary():
    snapshot = cm.WitnessSnapshot("srs", "2022-0005", {"A": 12.0, "B": 3.0, "C": -8.0})
    result = cm.srs_witness({"A": 30.0, "B": 10.0, "C": -5.0}, snapshot, "2022-0006")
    assert result["available"] is True
    assert result["canonical_spec_mounted"] is False
    assert result["canonical_validation_status"] == "NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS"
    assert (
        result["canonical_validation_blocker"]
        == "governance.SRS_CANONICAL_VALIDATION_ANCHORS_NOT_MOUNTED"
    )
    assert result["authority_boundary_preserved"] is True


def test_the_srs_witness_is_not_averaged_into_the_primary_metric():
    snapshot = cm.WitnessSnapshot("srs", "2021-0005", {"A": 12.0, "B": 3.0})
    replay = _replay(
        [_row("A", 10.0, 7.0)],
        witness_snapshots=(snapshot,),
        candidate_rating_states={"2022-0000": {"A": 30.0, "B": 10.0}},
    )
    with_witness = cm.evaluate_candidate(replay, evaluation_as_of="2022-0000")
    without = cm.evaluate_candidate(_replay([_row("A", 10.0, 7.0)]))
    assert with_witness.primary_metric_value == without.primary_metric_value
    assert with_witness.srs_witness["available"] is True
    assert with_witness.srs_witness["is_blended_into_primary_criterion"] is False


def test_a_witness_composite_is_refused():
    with pytest.raises(GovernanceBlock):
        cm.reject_witness_composite(["srs", "colley_matrix"])
    with pytest.raises(GovernanceBlock):
        cm.reject_witness_composite(["baxter", "srs"])


def test_the_ranking_interface_declares_no_composite():
    contract = cm.ranking_interface_as_dict()
    assert contract["witness_composite_authorised"] is False
    assert contract["witnesses_blended_into_primary"] is False
    assert contract["independent_witnesses"] == ["colley_matrix", "srs"]


# --- witness leakage ----------------------------------------------------------


def test_a_witness_state_after_the_evaluation_boundary_is_refused():
    late = cm.WitnessSnapshot("srs", "2022-9999", {"A": 1.0, "B": 2.0})
    with pytest.raises(GovernanceBlock, match="not a pregame witness"):
        cm.require_walk_forward_witness(late, "2022-0004")


def test_a_retrospective_comparison_is_permitted_but_labelled_as_one():
    late = cm.WitnessSnapshot("srs", "2022-9999", {"A": 1.0, "B": 2.0}, retrospective=True)
    assert (
        cm.require_walk_forward_witness(late, "2022-0004")
        == "RETROSPECTIVE_NOT_A_PREGAME_WITNESS"
    )
    result = cm.witness_comparison({"A": 5.0, "B": 9.0}, late, "2022-0004")
    assert result["temporal_validity"] == "RETROSPECTIVE_NOT_A_PREGAME_WITNESS"
    assert result["retrospective"] is True


def test_walk_forward_witness_state_is_labelled_walk_forward():
    early = cm.WitnessSnapshot("srs", "2022-0003", {"A": 1.0, "B": 2.0})
    result = cm.witness_comparison({"A": 5.0, "B": 9.0}, early, "2022-0004")
    assert result["temporal_validity"] == "WALK_FORWARD"
    assert result["retrospective"] is False


def test_a_witness_with_nothing_to_compare_against_reports_unavailable():
    """Null correlations must not read as an available witness that found nothing."""
    snapshot = cm.WitnessSnapshot("srs", "2021-0001", {"A": 12.0, "B": 3.0})
    replay = _replay([_row("A", 10.0, 7.0)], witness_snapshots=(snapshot,))
    record = cm.evaluate_candidate(replay)
    assert record.srs_witness["available"] is False
    assert record.srs_witness["unavailable_reason"] == cm.REASON_NO_CANDIDATE_RATING_STATE
    assert "spearman_rank_correlation" not in record.srs_witness
    with pytest.raises(InputValidationError, match="nothing to correlate"):
        cm.witness_comparison({}, snapshot, "2021-0002")


def test_an_unnamed_witness_is_refused():
    with pytest.raises(InputValidationError, match="governed independent"):
        cm.WitnessSnapshot("elo", "2022-0001", {"A": 1.0})


# --- witness arithmetic -------------------------------------------------------


def test_rank_correlation_is_one_for_an_identical_ordering():
    a = {"X": 10.0, "Y": 5.0, "Z": 1.0}
    b = {"X": 3.0, "Y": 2.0, "Z": 0.5}
    assert cm.spearman_rank_correlation(a, b) == 1.0
    assert cm.kendall_tau_b(a, b) == 1.0


def test_rank_correlation_is_minus_one_for_a_reversed_ordering():
    a = {"X": 10.0, "Y": 5.0, "Z": 1.0}
    b = {"X": 1.0, "Y": 5.0, "Z": 10.0}
    assert cm.spearman_rank_correlation(a, b) == -1.0
    assert cm.kendall_tau_b(a, b) == -1.0


def test_directional_agreement_excludes_tied_pairs_from_the_rate():
    a = {"X": 10.0, "Y": 10.0, "Z": 1.0}
    b = {"X": 3.0, "Y": 2.0, "Z": 0.5}
    result = cm.directional_agreement(a, b)
    assert result["pairs_tied_excluded"] == 1
    assert result["pairs_agreeing"] == 2
    assert result["agreement_rate"] == 1.0


def test_large_disagreements_are_flagged_above_the_declared_threshold():
    candidate = {f"T{i:03d}": float(100 - i) for i in range(60)}
    witness = dict(candidate)
    witness["T000"] = -999.0  # rank 1 -> rank 60
    flags = cm.large_disagreements(candidate, witness)
    assert [f["team"] for f in flags] == ["T000"]
    assert flags[0]["rank_delta"] >= cm.LARGE_RANK_DISAGREEMENT


def test_witness_comparison_abstains_rather_than_guessing_on_one_shared_team():
    a = {"X": 10.0}
    b = {"X": 3.0}
    assert cm.spearman_rank_correlation(a, b) is None
    assert cm.kendall_tau_b(a, b) is None


# --- ordering, sharding, determinism -----------------------------------------


def _shuffled(rows, seed):
    out = list(rows)
    # Deterministic permutation without touching the global RNG.
    state = seed
    for i in range(len(out) - 1, 0, -1):
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        j = state % (i + 1)
        out[i], out[j] = out[j], out[i]
    return out


def test_candidate_scoring_is_invariant_to_row_order():
    rows = _three_split_rows()
    baseline = cm.evaluate_candidate(_replay(rows)).digest()
    for seed in (1, 7, 99, 12345):
        assert cm.evaluate_candidate(_replay(_shuffled(rows, seed))).digest() == baseline


def test_batch_results_are_invariant_to_candidate_order():
    replays = [_replay(_three_split_rows(c), candidate_id=c) for c in ("C3", "C1", "C2")]
    forward = [r.digest() for r in cm.evaluate_candidates(replays)]
    backward = [r.digest() for r in cm.evaluate_candidates(list(reversed(replays)))]
    assert forward == backward
    assert [r.candidate_id for r in cm.evaluate_candidates(replays)] == ["C1", "C2", "C3"]


@pytest.mark.parametrize("shard_count", [1, 2, 3, 5, 7])
def test_results_are_identical_regardless_of_shard_count_and_index(shard_count):
    """The property the calibration search relies on and cannot check itself."""
    ids = [f"C{i:02d}" for i in range(10)]
    replays = [_replay(_three_split_rows(c), candidate_id=c) for c in ids]
    single = cm.evaluate_candidates(replays)

    shards = [
        [r for i, r in enumerate(replays) if i % shard_count == s] for s in range(shard_count)
    ]
    merged = cm.merge_shard_results(
        cm.evaluate_candidates(shard) for shard in shards if shard
    )
    assert [r.digest() for r in merged] == [r.digest() for r in single]


def test_a_candidate_appearing_in_two_shards_is_refused_rather_than_deduplicated():
    replay = _replay(_three_split_rows("C1"), candidate_id="C1")
    shard = cm.evaluate_candidates([replay])
    with pytest.raises(InputValidationError, match="more than one shard"):
        cm.merge_shard_results([shard, shard])


def test_evaluating_one_candidate_twice_in_a_batch_is_refused():
    replay = _replay(_three_split_rows("C1"), candidate_id="C1")
    with pytest.raises(InputValidationError, match="evaluated twice"):
        cm.evaluate_candidates([replay, replay])


def test_a_duplicated_game_within_a_split_is_refused():
    rows = [_row("G", 10.0, 7.0), _row("G", 10.0, 7.0, order_index=1)]
    with pytest.raises(InputValidationError, match="repeats game"):
        _replay(rows)


def test_rows_belonging_to_another_candidate_are_refused():
    with pytest.raises(InputValidationError, match="belonging to"):
        _replay([_row("G", 10.0, 7.0, candidate_id="OTHER")], candidate_id="C1")


# --- deterministic serialisation ---------------------------------------------


def test_serialisation_is_byte_stable_across_repeated_calls():
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    first = cm.canonical_json(record.as_dict())
    second = cm.canonical_json(record.as_dict())
    assert first == second
    assert record.digest() == record.digest()
    assert len(record.digest()) == 64


def test_the_serialised_record_is_json_native_and_sorted():
    payload = cm.evaluate_candidate(_replay(_three_split_rows())).as_dict()
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert json.loads(text) == json.loads(cm.canonical_json(payload))
    assert "\r" not in text


def test_two_different_candidates_digest_differently():
    a = cm.evaluate_candidate(_replay(_three_split_rows("C1"), candidate_id="C1"))
    b = cm.evaluate_candidate(_replay(_three_split_rows("C2", offset=1.0), candidate_id="C2"))
    assert a.digest() != b.digest()


def test_the_result_record_carries_its_full_provenance():
    payload = cm.evaluate_candidate(_replay(_three_split_rows())).as_dict()
    assert payload["input_dataset_sha"] == "DATASET_SHA_FIXTURE"
    assert payload["split_sha"] == "SPLIT_SHA_FIXTURE"
    assert payload["experiment_config_sha"] == "CONFIG_SHA_FIXTURE"
    assert payload["tie_break_policy_sha256"] == cm.TIE_BREAK_POLICY_SHA256
    assert payload["parameters_promoted"] is False


def test_a_replay_without_provenance_is_refused():
    for missing in ("input_dataset_sha", "split_sha", "experiment_config_sha"):
        kwargs = {
            "input_dataset_sha": "A",
            "split_sha": "B",
            "experiment_config_sha": "C",
            missing: "   ",
        }
        with pytest.raises(InputValidationError, match="carries no"):
            cm.CandidateReplay(
                candidate_id="C1", rows=(_row("G", 10.0, 7.0),), **kwargs
            )


def test_the_published_result_schema_matches_what_is_emitted():
    payload = cm.evaluate_candidate(_replay(_three_split_rows())).as_dict()
    assert sorted(payload) == list(cm.RESULT_SCHEMA_KEYS)
    assert PRIMARY_CALIBRATION_METRIC in cm.RESULT_SCHEMA_KEYS


def test_a_negative_zero_metric_serialises_as_zero():
    """Two arithmetically identical records must not digest differently."""
    rows = [_row("A", 10.0, 12.0, order_index=0), _row("B", 10.0, 8.0, order_index=1)]
    record = cm.evaluate_candidate(_replay(rows))
    assert record.bias == 0.0
    assert "-0.0" not in cm.canonical_json(record.as_dict())


# --- deterministic ranking ----------------------------------------------------


def test_ranking_is_by_lowest_primary_rmse():
    replays = [
        _replay([_row("A", 10.0, 10.0 - d, candidate_id=f"C{i}")], candidate_id=f"C{i}")
        for i, d in enumerate((5.0, 1.0, 3.0))
    ]
    ranked = cm.rank_candidates(
        cm.evaluate_candidates(replays), stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE
    )
    assert [r.candidate_id for r in ranked] == ["C1", "C2", "C0"]
    assert [r.primary_metric_value for r in ranked] == [1.0, 3.0, 5.0]


def test_ranking_requires_the_governed_objective():
    records = cm.evaluate_candidates([_replay(_three_split_rows())])
    with pytest.raises(GovernanceBlock, match="No evaluation objective"):
        cm.rank_candidates(records, stage=cm.STAGE_COARSE, objective=None)
    invented = EvaluationObjective(
        objective_id="MINE",
        metric="non_blowout_rmse",
        direction="minimize",
        description="a criterion chosen after seeing the results",
    )
    with pytest.raises(GovernanceBlock, match="not the governed primary"):
        cm.rank_candidates(records, stage=cm.STAGE_COARSE, objective=invented)


def test_the_tie_break_hierarchy_resolves_an_rmse_tie_on_mae():
    """Equal RMSE, different MAE: the candidate with the lower MAE wins."""
    # A: residuals +3, -3   -> RMSE 3, MAE 3
    # B: residuals +sqrt(18), 0 -> RMSE 3, MAE sqrt(18)/2 = 2.121...
    a = _replay(
        [
            _row("G0", 10.0, 7.0, candidate_id="A", order_index=0),
            _row("G1", 10.0, 13.0, candidate_id="A", order_index=1),
        ],
        candidate_id="A",
    )
    b = _replay(
        [
            _row("G0", 10.0, 10.0 - math.sqrt(18.0), candidate_id="B", order_index=0),
            _row("G1", 10.0, 10.0, candidate_id="B", order_index=1),
        ],
        candidate_id="B",
    )
    records = cm.evaluate_candidates([a, b])
    assert records[0].primary_metric_value == pytest.approx(
        records[1].primary_metric_value, abs=1e-12
    )
    ranked = cm.rank_candidates(records, stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE)
    assert [r.candidate_id for r in ranked] == ["B", "A"]


def test_an_exact_tie_falls_through_to_candidate_id_for_a_total_order():
    replays = [
        _replay([_row("G", 10.0, 7.0, candidate_id=c)], candidate_id=c)
        for c in ("ZULU", "ALPHA", "MIKE")
    ]
    records = cm.evaluate_candidates(replays)
    ranked = cm.rank_candidates(records, stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE)
    assert [r.candidate_id for r in ranked] == ["ALPHA", "MIKE", "ZULU"]


def test_ranking_is_invariant_to_the_order_records_arrive_in():
    replays = [
        _replay([_row("A", 10.0, 10.0 - d, candidate_id=f"C{i}")], candidate_id=f"C{i}")
        for i, d in enumerate((5.0, 1.0, 3.0, 1.0, 9.0))
    ]
    records = list(cm.evaluate_candidates(replays))
    forward = cm.rank_candidates(records, stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE)
    reverse = cm.rank_candidates(
        list(reversed(records)), stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE
    )
    shuffled = cm.rank_candidates(
        _shuffled(records, 4242), stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE
    )
    assert [r.candidate_id for r in forward] == [r.candidate_id for r in reverse]
    assert [r.candidate_id for r in forward] == [r.candidate_id for r in shuffled]


def test_an_unscored_candidate_sorts_last_without_an_infinity():
    scored = _replay([_row("A", 10.0, 7.0, candidate_id="AAA")], candidate_id="AAA")
    empty = cm.CandidateReplay(
        candidate_id="AAB",
        rows=(_row("A", 10.0, 7.0, candidate_id="AAB", split="training"),),
        input_dataset_sha="D",
        split_sha="S",
        experiment_config_sha="E",
    )
    records = cm.evaluate_candidates([scored, empty])
    ranked = cm.rank_candidates(records, stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE)
    assert [r.candidate_id for r in ranked] == ["AAA", "AAB"]
    unscored = ranked[-1]
    assert unscored.primary_metric_value is None
    assert unscored.status == cm.METRICS_UNAVAILABLE
    assert cm.REASON_NO_OUT_OF_SAMPLE_ROWS in unscored.failure_reasons


def test_the_tie_break_policy_is_fixed_and_digested():
    assert [t["tier"] for t in cm.TIE_BREAK_POLICY] == ["0", "1", "2", "3", "4"]
    assert cm.TIE_BREAK_POLICY[0]["field"] == PRIMARY_CALIBRATION_METRIC
    assert cm.TIE_BREAK_POLICY[0]["direction"] == PRIMARY_CALIBRATION_DIRECTION
    assert [t["field"] for t in cm.TIE_BREAK_POLICY[1:]] == [
        "out_of_sample_mae",
        "absolute_bias",
        "season_rmse_sd",
        "candidate_id",
    ]
    assert cm.TIE_BREAK_POLICY_SHA256 == cm.canonical_digest(
        [dict(t) for t in cm.TIE_BREAK_POLICY]
    )
    assert len(cm.TIE_BREAK_POLICY_SHA256) == 64


def test_an_empty_record_set_ranks_to_an_empty_result():
    assert cm.rank_candidates([], stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE) == ()


# --- package disposition ------------------------------------------------------


def test_the_package_promotes_nothing_and_recommends_nothing():
    contract = cm.ranking_interface_as_dict()
    assert contract["parameters_promoted"] is False
    assert contract["recommends_a_candidate"] is False
    status = cm.metrics_package_status()
    assert status["parameters_promoted"] is False
    assert status["candidates_generated"] is False
    assert status["season_monte_carlo_run"] is False
    assert status["governed_observation_dataset_mounted"] is False


def test_the_declared_conventions_are_not_model_parameters():
    conventions = cm.ranking_interface_as_dict()["diagnostic_conventions"]
    assert conventions["are_model_parameters"] is False
    assert conventions["are_policy_choices"] is False


def test_the_bands_tile_the_margin_line_without_a_gap():
    edges = [(lo, hi) for _, lo, hi in cm.BLOWOUT_BANDS]
    assert edges[0][0] == 0.0
    assert edges[-1][1] is None
    for (_, hi), (lo, _) in zip(edges, edges[1:]):
        assert hi == lo


def test_the_season_phases_tile_the_week_line_without_a_gap():
    edges = [(lo, hi) for _, lo, hi in cm.SEASON_PHASES]
    assert edges[0][0] == 1
    assert edges[-1][1] is None
    for (_, hi), (lo, _) in zip(edges, edges[1:]):
        assert hi == lo


def test_the_benchmark_fixture_is_marked_inadmissible():
    fixture = cm.synthetic_benchmark_fixture(candidates=2, rows_per_candidate=5)
    for replay in fixture:
        assert replay.input_dataset_sha == "SYNTHETIC_NOT_ADMISSIBLE"
        assert replay.split_sha == "SYNTHETIC_NOT_ADMISSIBLE"
        assert replay.experiment_config_sha == "SYNTHETIC_NOT_ADMISSIBLE"


def test_the_benchmark_fixture_is_reproducible_from_its_seed():
    a = cm.synthetic_benchmark_fixture(candidates=2, rows_per_candidate=20)
    b = cm.synthetic_benchmark_fixture(candidates=2, rows_per_candidate=20)
    assert [r.digest() for r in cm.evaluate_candidates(a)] == [
        r.digest() for r in cm.evaluate_candidates(b)
    ]


# --- CAL-METRICS-R1 freeze: witnesses and probabilities are non-blocking ------


def test_an_absent_witness_does_not_withhold_the_baxter_score():
    """The circularity this guards: a witness needs the mean model to exist."""
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    assert record.primary_metric_value is not None
    assert record.primary_selection_ready is True
    assert record.failure_reasons == ()
    assert record.status == cm.METRICS_PRIMARY_READY
    assert record.witness_status == {
        "colley_matrix": cm.WITNESS_UNAVAILABLE,
        "srs": cm.WITNESS_UNAVAILABLE,
    }


def test_an_absent_probability_conversion_does_not_withhold_the_baxter_score():
    record = cm.evaluate_candidate(_replay(_three_split_rows()))
    assert record.probability["brier_score"] is None
    assert record.probability["log_loss"] is None
    assert record.out_of_sample_mae is not None
    assert record.bias is not None
    assert record.winner_accuracy["accuracy"] is not None
    assert record.primary_selection_ready is True


def test_candidates_with_no_witnesses_still_rank():
    """Witness unavailability must not remove a candidate from the search."""
    replays = [
        _replay(
            [_row("A", 10.0, 10.0 - d, candidate_id=f"C{i}")],
            candidate_id=f"C{i}",
        )
        for i, d in enumerate((5.0, 1.0, 3.0))
    ]
    records = cm.evaluate_candidates(replays)
    assert all(r.witness_status["srs"] == cm.WITNESS_UNAVAILABLE for r in records)
    ranked = cm.rank_candidates(
        records, stage=cm.STAGE_COARSE, objective=PRIMARY_OBJECTIVE
    )
    assert [r.candidate_id for r in ranked] == ["C1", "C2", "C0"]


def test_a_leaking_witness_degrades_that_witness_and_not_the_candidate():
    """The gate stays hard when called directly; inside scoring it is contained."""
    late = cm.WitnessSnapshot("srs", "9999-9999", {"A": 1.0, "B": 2.0})
    replay = _replay(
        [_row("A", 10.0, 7.0)],
        witness_snapshots=(late,),
        candidate_rating_states={"2022-0000": {"A": 30.0, "B": 10.0}},
    )
    record = cm.evaluate_candidate(replay, evaluation_as_of="2022-0000")
    assert record.primary_metric_value == 3.0
    assert record.primary_selection_ready is True
    assert record.srs_witness["witness_status"] == cm.WITNESS_UNAVAILABLE
    assert record.srs_witness["blocked_primary_selection"] is False
    assert any("WITNESS_REFUSED" in r for r in record.non_blocking_reasons)
    # Called directly, the leakage gate still refuses outright.
    with pytest.raises(GovernanceBlock, match="not a pregame witness"):
        cm.require_walk_forward_witness(late, "2022-0000")


def test_only_a_missing_primary_input_is_charged_as_a_failure():
    empty = cm.CandidateReplay(
        candidate_id="C1",
        rows=(_row("A", 10.0, 7.0, split="training"),),
        input_dataset_sha="D",
        split_sha="S",
        experiment_config_sha="E",
    )
    record = cm.evaluate_candidate(empty)
    assert record.primary_selection_ready is False
    assert record.status == cm.METRICS_UNAVAILABLE
    assert record.failure_reasons == (cm.REASON_NO_OUT_OF_SAMPLE_ROWS,)


def test_the_input_classification_is_published_and_disjoint():
    contract = cm.ranking_interface_as_dict()
    assert contract["required_inputs"] == list(cm.REQUIRED_INPUTS)
    assert contract["witnesses_required_for_primary_selection"] is False
    for optional in ("brier_score", "log_loss", "colley_matrix_witness", "srs_witness"):
        assert optional in cm.OPTIONAL_DOWNSTREAM_INPUTS
    assert set(cm.REQUIRED_INPUTS) & set(cm.OPTIONAL_DOWNSTREAM_INPUTS) == set()
    assert (
        set(cm.SECONDARY_NON_BLOCKING_METRICS) & set(cm.OPTIONAL_DOWNSTREAM_INPUTS)
        == set()
    )


def test_game_sd_points_is_not_required_for_the_mean_model_metrics():
    status = cm.metrics_package_status()
    assert status["game_sd_points_required_for_primary_selection"] is False
    assert "out-of-sample model residuals" in status["game_sd_points_estimated_from"]
    # It does correctly gate the probability metrics.
    assert status["brier_and_log_loss_blocker"] == "calibration.game_sd_points"


# --- CAL-METRICS-R1 freeze: the oracle digest ---------------------------------


def test_the_frozen_oracle_digest_verifies_against_itself():
    verified = cm.require_frozen_oracle(cm.ORACLE_FREEZE_SHA256)
    assert verified["freeze_id"] == "CAL-METRICS-R1"
    assert verified["verified"] is True
    assert len(cm.ORACLE_FREEZE_SHA256) == 64
    assert cm.ORACLE_FREEZE_SHA256 == cm.canonical_digest(cm.ranking_interface_as_dict())


def test_a_mismatched_oracle_digest_is_refused():
    with pytest.raises(GovernanceBlock, match="digest mismatch"):
        cm.require_frozen_oracle("0" * 64)


def test_the_freeze_digest_covers_more_than_the_tie_breaks():
    """A worker keeping the tie-breaks but moving a band edge must be caught."""
    contract = cm.ranking_interface_as_dict()
    assert contract["tie_break_policy_sha256"] == cm.TIE_BREAK_POLICY_SHA256
    for key in (
        "stage_ranking_split",
        "diagnostic_conventions",
        "result_schema_keys",
        "independent_witnesses",
        "holdout_release_token_pattern",
    ):
        assert key in contract
    mutated = dict(contract)
    mutated["diagnostic_conventions"] = {"blowout_boundary_points": 14.0}
    assert cm.canonical_digest(mutated) != cm.ORACLE_FREEZE_SHA256


def test_the_composition_contract_keeps_ranking_central():
    contract = cm.ranking_interface_as_dict()
    assert contract["workers_score_only"] is True
    assert contract["ranking_is_central"] is True
    for key in (
        "worker_may_redefine_primary_objective",
        "worker_may_redefine_tie_breaks",
        "worker_may_redefine_holdout_policy",
        "worker_may_redefine_witness_role",
    ):
        assert contract[key] is False


# --- CAL-METRICS-R1 freeze: corpus binding ------------------------------------


def test_the_corpus_dependency_is_reported_as_a_pending_candidate():
    status = cm.metrics_package_status()
    assert status["corpus_input_status"] == (
        "AUDITED_HISTORICAL_CORPUS_CANDIDATE_PENDING_FINAL_ACCEPTANCE"
    )
    assert status["corpus_candidate_observations"] == 2241
    assert status["corpus_candidate_seasons"] == "2021-2024"
    assert status["corpus_worktree_read"] is False


def test_every_emitted_record_carries_the_corpus_dependency_state():
    payload = cm.evaluate_candidate(_replay(_three_split_rows())).as_dict()
    assert payload["corpus_input_status"] == cm.CORPUS_INPUT_STATUS
    assert payload["witnesses_required_for_primary_selection"] is False


def test_binding_requires_an_exact_digest_not_a_branch_or_a_placeholder():
    for bad in ("HEAD", "PENDING", "worktree", "abc123", "", "Z" * 64, "A" * 64):
        with pytest.raises(InputValidationError, match="exact SHA-256"):
            cm.bind_accepted_corpus(bad, accepted=True)


def test_binding_refuses_a_corpus_that_is_not_yet_accepted():
    with pytest.raises(GovernanceBlock, match="PENDING_FINAL_ACCEPTANCE"):
        cm.bind_accepted_corpus("b" * 64, accepted=False)


def test_an_accepted_corpus_binds_to_its_exact_digest():
    digest = "c" * 64
    bound = cm.bind_accepted_corpus(digest, accepted=True)
    assert bound["corpus_sha256"] == digest
    assert bound["binding"] == "EXACT_ACCEPTED_CORPUS_SHA256"
    assert bound["corpus_input_status"] == "ACCEPTED_AND_BOUND"
    assert bound["oracle_sha256"] == cm.ORACLE_FREEZE_SHA256


# --- CAL-METRICS-R1 freeze: holdout, restated as an explicit stage matrix ------


@pytest.mark.parametrize(
    "stage,permitted",
    [
        (cm.STAGE_COARSE, "validation"),
        (cm.STAGE_REFINEMENT, "validation"),
        (cm.STAGE_FINAL_HOLDOUT, "holdout"),
    ],
)
def test_the_stage_to_split_matrix_is_exactly_as_declared(stage, permitted):
    assert cm.STAGE_RANKING_SPLIT[stage] == permitted


def test_no_holdout_value_is_reachable_from_a_coarse_or_refinement_record():
    """Restated end to end: compute holdout, then try every read path."""
    rows = [
        dataclasses.replace(r, predicted_margin=r.actual_margin - 555.0)
        if r.split == "holdout"
        else r
        for r in _three_split_rows()
    ]
    record = cm.evaluate_candidate(_replay(rows))
    payload = record.as_dict()
    assert "555" not in json.dumps(payload)
    assert payload["holdout"]["holdout"] == cm.SEALED
    assert payload["by_split"]["holdout"] == {"holdout": cm.SEALED}
    assert "555" not in cm.canonical_json(payload)
    # The rank key cannot see it either.
    assert 555.0 not in cm._rank_key(record)[0]
    # And it is still there, behind the token.
    assert record.sealed_holdout.open(RELEASE)["rmse"] == 555.0
