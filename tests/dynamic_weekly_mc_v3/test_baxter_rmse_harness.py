"""C2 — Baxter Rating RMSE harness.

The tests are grouped by the property they defend. Every regime value that
appears here is authored *by the test*, not by the harness or by shipped
configuration: the repository's experimental regime file stays empty, and the
canonical V3 calibration values stay null.
"""

from __future__ import annotations

import json
import math
from dataclasses import replace
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.baxter_harness import (
    contract as contract_module,
    evaluate as evaluate_module,
    fixtures,
    interface as interface_module,
    metrics as metrics_module,
    model as model_module,
    observations as observations_module,
    regime as regime_module,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

ROOT = Path(__file__).resolve().parents[2]
V3_CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
SHIPPED_CONTRACT = ROOT / "config/dynamic_weekly_mc_v3/experimental/baxter_data_contract.json"
SHIPPED_REGIMES = ROOT / "config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json"

SEED = 20260803


def _values(
    *,
    coefficient=0.25,
    cap=4.0,
    weights=(0.6, 0.3, 0.1),
    blowout=None,
    game_sd=17.0,
    regularization=None,
):
    return fixtures.fixture_regime_values(
        coefficient=coefficient,
        movement_cap_points=cap,
        recent_form_weights=list(weights),
        blowout_treatment=blowout or {"mode": "cap_margin", "cap_points": 21.0},
        game_sd_points=game_sd,
        sample_size_regularization=regularization
        or {"mode": "games_played_shrink", "prior_games": 3.0},
    )


def _regime(regime_id="FX-A", **kwargs):
    return cal.CandidateRegime(
        regime_id=regime_id, values=_values(**kwargs), rationale="test-authored candidate"
    )


def _context(run_id="RUN-1"):
    return evaluate_module.RunContext(
        run_id=run_id,
        as_of="2026-08-21T00:00:00Z",
        model_version="3.0.0-experimental-harness",
        configuration_version="V3-PLACEHOLDER-2026-08-21-R2-001",
        seed=SEED,
    )


@pytest.fixture
def mounted(tmp_path):
    """A synthetic observation set mounted through a fixture contract."""
    spec = fixtures.FixtureSpec(seed=SEED, teams=12, weeks=9)
    observations = fixtures.write_fixture_csv(tmp_path / "obs.csv", spec)
    document = fixtures.write_fixture_contract(
        tmp_path / "contract.json", observations_path=observations
    )
    return contract_module.resolve_contract(contract_module.load_contract(document))


# --- the shipped contract points at nothing, on purpose ----------------------


def test_shipped_contract_declares_no_dataset_path():
    payload = json.loads(SHIPPED_CONTRACT.read_text(encoding="utf-8"))
    assert payload["observations"]["path"] is None
    assert payload["observations"]["sha256"] is None


def test_absent_data_returns_ready_for_data_not_a_metric():
    config = V3Config.from_json(V3_CONFIG)
    resolution = contract_module.resolve_contract(
        contract_module.load_contract(SHIPPED_CONTRACT),
        v3_hfa_baseline_points=config.hfa_baseline_points,
    )
    assert resolution.status == contract_module.READY_FOR_DATA

    payload = evaluate_module.evaluate_regimes(resolution, [_regime()], context=_context())
    assert payload["status"] == "READY_FOR_DATA"
    assert payload["results"] == []
    assert payload["ranking"] is None
    assert cal.BLOCKED_ON_CALIBRATION_DATA in payload["reasons"][0]


def test_home_field_is_read_from_governed_config_not_carried_by_the_harness():
    config = V3Config.from_json(V3_CONFIG)
    resolution = contract_module.resolve_contract(
        contract_module.load_contract(SHIPPED_CONTRACT),
        v3_hfa_baseline_points=config.hfa_baseline_points,
    )
    assert resolution.hfa_points == config.hfa_baseline_points

    unresolved = contract_module.resolve_contract(
        contract_module.load_contract(SHIPPED_CONTRACT), v3_hfa_baseline_points=None
    )
    assert any("home_field_points_unresolved" in r for r in unresolved.reasons)


def test_contract_must_not_restate_a_governed_value_as_a_literal(tmp_path):
    document = tmp_path / "contract.json"
    document.write_text(
        json.dumps(
            {
                "contract_id": "X",
                "contract_version": "1.0.0",
                "observations": {"path": None},
                "metric": {"baxter_rmse_definition_id": "BAXTER_MARGIN_PREDICTION_RMSE_V1"},
                "hfa": {"points": 3.5, "source": "V3_CONFIG_HFA_BASELINE_POINTS"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputValidationError, match="read from governed configuration"):
        contract_module.load_contract(document)


# --- contract versioning ----------------------------------------------------


def test_incompatible_major_contract_version_is_refused(tmp_path):
    document = tmp_path / "contract.json"
    document.write_text(
        json.dumps(
            {
                "contract_id": "X",
                "contract_version": "2.0.0",
                "observations": {"path": None},
                "metric": {"baxter_rmse_definition_id": "BAXTER_MARGIN_PREDICTION_RMSE_V1"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GovernanceBlock, match="renegotiation"):
        contract_module.load_contract(document)


def test_contract_must_name_a_metric_definition(tmp_path):
    document = tmp_path / "contract.json"
    document.write_text(
        json.dumps(
            {"contract_id": "X", "contract_version": "1.0.0", "observations": {"path": None}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(GovernanceBlock, match="baxter_rmse_definition_id"):
        contract_module.load_contract(document)


def test_unknown_metric_definition_is_refused(tmp_path):
    document = tmp_path / "contract.json"
    document.write_text(
        json.dumps(
            {
                "contract_id": "X",
                "contract_version": "1.0.0",
                "observations": {"path": None},
                "metric": {"baxter_rmse_definition_id": "SOMETHING_ELSE"},
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(GovernanceBlock, match="does not implement"):
        contract_module.resolve_contract(contract_module.load_contract(document))


def test_shipped_metric_definition_is_not_claimed_as_ruled():
    definition = contract_module.BAXTER_MARGIN_PREDICTION_RMSE_V1
    assert definition.provenance == "DERIVED"
    assert definition.governance_status == "OPERATIONAL_DEFINITION_NOT_YET_RULED"


def test_declared_hash_must_match_the_mounted_file(tmp_path):
    spec = fixtures.FixtureSpec(seed=SEED, teams=12, weeks=9)
    observations = fixtures.write_fixture_csv(tmp_path / "obs.csv", spec)
    document = tmp_path / "contract.json"
    fixtures.write_fixture_contract(document, observations_path=observations)
    payload = json.loads(document.read_text(encoding="utf-8"))
    payload["observations"]["sha256"] = "f" * 64
    document.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="not the file the contract was written against"):
        contract_module.resolve_contract(contract_module.load_contract(document))


def test_declared_path_that_is_not_mounted_is_ready_for_data_not_blocked(tmp_path):
    document = tmp_path / "contract.json"
    fixtures.write_fixture_contract(document, observations_path=tmp_path / "absent.csv")
    resolution = contract_module.resolve_contract(contract_module.load_contract(document))
    assert resolution.status == contract_module.READY_FOR_DATA
    assert resolution.dataset is None


# --- split separation and leakage -------------------------------------------


def test_random_split_policies_are_refused(tmp_path):
    document = tmp_path / "contract.json"
    fixtures.write_fixture_contract(
        document, observations_path=tmp_path / "obs.csv", split_policy={"mode": "random"}
    )
    with pytest.raises(GovernanceBlock, match="not out-of-sample"):
        contract_module.load_contract(document)


def test_splits_are_disjoint_and_cover_every_observation(mounted):
    observation_set = observations_module.load_observation_set(
        mounted.dataset, mounted.contract
    )
    counts = observation_set.split_counts
    assert sum(counts.values()) == len(observation_set.observations)
    keys = [
        observation_set.split_of[observations_module._row_key(o)]
        for o in observation_set.observations
    ]
    assert set(keys) == {"training", "validation", "holdout"}


def test_a_week_may_not_straddle_a_split_boundary(tmp_path):
    spec = fixtures.FixtureSpec(seed=SEED, teams=12, weeks=9)
    observations = fixtures.write_fixture_csv(tmp_path / "obs.csv", spec)
    text = observations.read_text(encoding="utf-8").splitlines()
    header = text[0].split(",")
    split_index = header.index("split")
    week_index = header.index("week")
    rewritten = [text[0]]
    flipped = False
    for line in text[1:]:
        cells = line.split(",")
        if cells[week_index] == "6" and not flipped:
            cells[split_index] = "training"
            flipped = True
        rewritten.append(",".join(cells))
    observations.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

    document = fixtures.write_fixture_contract(
        tmp_path / "contract.json", observations_path=observations
    )
    resolution = contract_module.resolve_contract(contract_module.load_contract(document))
    with pytest.raises(GovernanceBlock, match="leaks the boundary"):
        observations_module.load_observation_set(resolution.dataset, resolution.contract)


def test_temporal_week_policy_assigns_forward_in_time(tmp_path):
    spec = fixtures.FixtureSpec(seed=SEED, teams=12, weeks=9)
    observations = fixtures.write_fixture_csv(tmp_path / "obs.csv", spec)
    document = fixtures.write_fixture_contract(
        tmp_path / "contract.json",
        observations_path=observations,
        split_policy={
            "mode": "temporal_week",
            "training_through": {"season": 2026, "week": 4},
            "validation_through": {"season": 2026, "week": 6},
        },
    )
    resolution = contract_module.resolve_contract(contract_module.load_contract(document))
    observation_set = observations_module.load_observation_set(
        resolution.dataset, resolution.contract
    )
    training_weeks = {o.week for o in observation_set.scored("training")}
    holdout_weeks = {o.week for o in observation_set.scored("holdout")}
    assert max(training_weeks) < min(holdout_weeks)
    assert training_weeks == {1, 2, 3, 4}
    assert holdout_weeks == {7, 8, 9}


def test_temporal_week_policy_requires_training_to_precede_validation(tmp_path):
    document = tmp_path / "contract.json"
    fixtures.write_fixture_contract(
        document,
        observations_path=tmp_path / "obs.csv",
        split_policy={
            "mode": "temporal_week",
            "training_through": {"season": 2026, "week": 8},
            "validation_through": {"season": 2026, "week": 4},
        },
    )
    with pytest.raises(InputValidationError, match="precede"):
        contract_module.load_contract(document)


def test_an_empty_scored_split_yields_no_metric(tmp_path):
    spec = fixtures.FixtureSpec(seed=SEED, teams=12, weeks=9)
    observations = fixtures.write_fixture_csv(tmp_path / "obs.csv", spec)
    document = fixtures.write_fixture_contract(
        tmp_path / "contract.json",
        observations_path=observations,
        split_policy={
            "mode": "temporal_week",
            "training_through": {"season": 2026, "week": 8},
            "validation_through": {"season": 2026, "week": 9},
        },
    )
    resolution = contract_module.resolve_contract(contract_module.load_contract(document))
    with pytest.raises(GovernanceBlock, match="not a metric of zero"):
        evaluate_module.evaluate_regimes(
            resolution, [_regime()], context=_context(), include_holdout=True
        )


# --- holdout is not a sweep surface -----------------------------------------


def test_holdout_is_refused_for_more_than_one_regime(mounted):
    with pytest.raises(GovernanceBlock, match="not a sweep surface"):
        evaluate_module.evaluate_regimes(
            mounted,
            [_regime("FX-A"), _regime("FX-B", coefficient=0.4)],
            context=_context(),
            include_holdout=True,
        )


def test_a_sweep_reports_no_holdout_metrics(mounted):
    payload = evaluate_module.evaluate_regimes(
        mounted, [_regime("FX-A"), _regime("FX-B", coefficient=0.4)], context=_context()
    )
    assert payload["holdout_included"] is False
    for result in payload["results"]:
        assert "holdout" not in result["splits"]


def test_ranking_is_computed_on_validation(mounted):
    payload = evaluate_module.evaluate_regimes(
        mounted, [_regime("FX-A"), _regime("FX-B", coefficient=0.4)], context=_context()
    )
    assert payload["ranking"]["basis"] == "validation"
    assert payload["ranking"]["metric"] == cal.PRIMARY_CALIBRATION_METRIC
    ordered = [
        next(r for r in payload["results"] if r["experiment_id"] == experiment_id)
        for experiment_id in payload["ranking"]["order"]
    ]
    scores = [
        r["splits"]["validation"]["metrics"][cal.PRIMARY_CALIBRATION_METRIC] for r in ordered
    ]
    assert scores == sorted(scores)


# --- never promotes ---------------------------------------------------------


def test_evaluation_never_promotes_and_says_so(mounted):
    payload = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    assert payload["promotion"]["auto_promoted"] is False
    assert payload["promotion"]["harness_can_promote"] is False
    assert payload["promotion"]["canonical_values_written"] is False
    assert payload["ranking"]["advisory_only"] is True
    for result in payload["results"]:
        assert result["record"]["status"] == "EXPERIMENTAL_RESULT_NOT_PROMOTED"


def test_canonical_calibration_values_are_untouched_by_an_evaluation(mounted):
    before = V3_CONFIG.read_bytes()
    evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    assert V3_CONFIG.read_bytes() == before
    config = V3Config.from_json(V3_CONFIG)
    assert config.calibration.blockers() == list(cal.CALIBRATION_FIELDS)


def test_synthetic_results_are_not_admissible_promotion_evidence(mounted):
    payload = evaluate_module.evaluate_regimes(
        mounted, [_regime()], context=_context(), include_holdout=True
    )
    assert payload["observation_set"]["synthetic"] is True
    assert payload["results"][0]["evidence_admissible_for_promotion"] is False
    with pytest.raises(GovernanceBlock, match="harness validation only"):
        evaluate_module.assert_promotion_evidence_admissible(payload)


def test_validation_only_results_are_not_admissible_promotion_evidence(mounted):
    payload = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    payload["observation_set"]["synthetic"] = False
    with pytest.raises(GovernanceBlock, match="holdout"):
        evaluate_module.assert_promotion_evidence_admissible(payload)


def test_the_shipped_experimental_regime_file_is_still_empty():
    assert cal.load_candidate_regimes(SHIPPED_REGIMES) == []


# --- objective governance ---------------------------------------------------


def test_only_the_governed_primary_objective_is_accepted(mounted):
    wrong = cal.EvaluationObjective(
        objective_id="OBJ-X", metric="brier_score", direction="minimize", description="x"
    )
    with pytest.raises(GovernanceBlock, match="not the governed primary"):
        evaluate_module.evaluate_regimes(
            mounted, [_regime()], context=_context(), objective=wrong
        )


def test_witnesses_are_reported_but_never_blended(mounted):
    payload = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    reporting = payload["witness_reporting"]
    assert reporting["blended_into_primary_metric"] is False
    assert set(reporting["witnesses"]) == set(cal.INDEPENDENT_WITNESSES)
    assert all(status == "NOT_MOUNTED" for status in reporting["witnesses"].values())
    with pytest.raises(GovernanceBlock, match="not authorised"):
        cal.reject_witness_composite(["baxter_rating", "colley_matrix", "srs"])


# --- forbidden signals ------------------------------------------------------


@pytest.mark.parametrize(
    "column", ["public_money_percentage", "sharp_money_share", "injury_adjustment", "handle_pct"]
)
def test_flow_and_injury_signals_never_reach_the_harness(tmp_path, column):
    observations = tmp_path / "obs.csv"
    observations.write_text(
        "game_id,season,week,team,opponent,expected_margin,actual_margin,observed_at,"
        f"recorded_at,{column}\n"
        "G1,2026,1,A,B,3.5,7,2026-08-29T00:00:00Z,2026-08-30T00:00:00Z,62\n",
        encoding="utf-8",
    )
    document = fixtures.write_fixture_contract(
        tmp_path / "contract.json", observations_path=observations
    )
    with pytest.raises(GovernanceBlock):
        contract_module.resolve_contract(contract_module.load_contract(document))


# --- regime validation ------------------------------------------------------


def test_a_partial_regime_is_refused_rather_than_defaulted():
    values = _values()
    del values["game_sd_points"]
    with pytest.raises(GovernanceBlock, match="does not state"):
        regime_module.resolve_regime(
            cal.CandidateRegime(regime_id="P", values=values, rationale="partial")
        )


def test_out_of_band_values_are_refused_not_clipped():
    with pytest.raises(InputValidationError, match="refused, not clipped"):
        regime_module.resolve_regime(_regime(game_sd=0.5))


def test_blowout_exponent_may_not_amplify_large_margins():
    with pytest.raises(InputValidationError, match="count for more, not less"):
        regime_module.resolve_regime(
            _regime(blowout={"mode": "diminishing_returns", "threshold_points": 21.0, "exponent": 1.5})
        )


def test_recent_form_weights_may_not_sum_to_zero():
    with pytest.raises(InputValidationError, match="erases recent form"):
        regime_module.resolve_regime(_regime(weights=(0.0, 0.0)))


def test_duplicate_regime_ids_are_refused():
    with pytest.raises(InputValidationError, match="Duplicate regime ids"):
        regime_module.resolve_regimes([_regime("FX-A"), _regime("FX-A", coefficient=0.4)])


def test_a_grid_requires_the_caller_to_supply_every_axis():
    with pytest.raises(GovernanceBlock, match="does not author candidate calibration values"):
        regime_module.regime_grid("G", {"game_sd_points": [17.0]})


def test_a_full_grid_is_deterministic_and_complete():
    axes = {
        "weekly_performance_residual_coefficient": [0.2, 0.3],
        "weekly_movement_cap_points": [3.0, 5.0],
        "recent_form_weights": [[0.6, 0.4]],
        "blowout_treatment": [{"mode": "none"}],
        "game_sd_points": [17.0],
        "sample_size_regularization": [{"mode": "none"}],
    }
    first = regime_module.regime_grid("G", axes)
    second = regime_module.regime_grid("G", axes)
    assert len(first) == 4
    assert [r.regime_id for r in first] == [r.regime_id for r in second]
    assert [r.values for r in first] == [r.values for r in second]


# --- the six axes actually do something -------------------------------------


def _run(mounted, **kwargs):
    observation_set = observations_module.load_observation_set(
        mounted.dataset, mounted.contract
    )
    resolved = regime_module.resolve_regime(_regime(**kwargs))
    return observation_set, model_module.run_model(
        observation_set, resolved, home_field_points=float(mounted.hfa_points)
    )


def test_the_movement_cap_binds(mounted):
    _, run = _run(mounted, coefficient=2.0, cap=0.5)
    assert all(abs(m.delta) <= 0.5 + 1e-9 for m in run.movements)
    assert any(m.cap_binding for m in run.movements)


def test_a_zero_coefficient_leaves_ratings_where_they_started(mounted):
    _, run = _run(mounted, coefficient=0.0)
    assert all(m.delta == 0.0 for m in run.movements)


def test_sample_size_regularization_damps_early_movement(mounted):
    _, damped = _run(mounted, regularization={"mode": "games_played_shrink", "prior_games": 8.0})
    _, undamped = _run(mounted, regularization={"mode": "none"})
    first_damped = [m for m in damped.movements if (m.season, m.week) == (2026, 1)]
    first_undamped = [m for m in undamped.movements if (m.season, m.week) == (2026, 1)]
    assert sum(abs(m.delta) for m in first_damped) < sum(abs(m.delta) for m in first_undamped)


def test_blowout_treatment_limits_what_a_lopsided_game_can_move(mounted):
    _, capped = _run(mounted, blowout={"mode": "cap_margin", "cap_points": 3.0}, cap=50.0)
    _, uncapped = _run(mounted, blowout={"mode": "none"}, cap=50.0)
    assert max(abs(m.delta) for m in capped.movements) < max(
        abs(m.delta) for m in uncapped.movements
    )


def test_game_sd_changes_probabilities_but_not_the_primary_criterion(mounted):
    _, narrow = _run(mounted, game_sd=10.0)
    _, wide = _run(mounted, game_sd=30.0)
    assert metrics_module.baxter_rating_rmse(narrow.predictions) == pytest.approx(
        metrics_module.baxter_rating_rmse(wide.predictions)
    )
    assert narrow.predictions[0].win_probability != wide.predictions[0].win_probability


def test_recent_form_weights_change_the_rating_trajectory(mounted):
    _, sharp = _run(mounted, weights=(1.0,))
    _, smooth = _run(mounted, weights=(0.34, 0.33, 0.33))
    assert sharp.final_ratings != smooth.final_ratings


def _validation_scores(resolution, regimes):
    payload = evaluate_module.evaluate_regimes(resolution, regimes, context=_context())
    return {
        result["regime"]["regime_id"]: result["splits"]["validation"]["metrics"][
            cal.PRIMARY_CALIBRATION_METRIC
        ]
        for result in payload["results"]
    }


def _mounted_spec(tmp_path, spec):
    observations = fixtures.write_fixture_csv(tmp_path / "obs.csv", spec)
    document = fixtures.write_fixture_contract(
        tmp_path / "contract.json", observations_path=observations
    )
    return contract_module.resolve_contract(contract_module.load_contract(document))


def test_tracking_beats_freezing_when_the_generating_process_actually_drifts(tmp_path):
    """The instrument must be able to see a regime recovering real drift."""
    resolution = _mounted_spec(
        tmp_path,
        fixtures.FixtureSpec(
            seed=SEED, teams=12, weeks=11, drift_sd_points=6.0, game_sd_points=6.0
        ),
    )
    scores = _validation_scores(
        resolution,
        [
            _regime("TRACKS", coefficient=0.5, cap=6.0, blowout={"mode": "none"}, game_sd=6.0),
            _regime("FROZEN", coefficient=0.0, cap=6.0, blowout={"mode": "none"}, game_sd=6.0),
        ],
    )
    assert scores["TRACKS"] < scores["FROZEN"]


def test_chasing_noise_scores_worse_when_the_generating_process_is_static(tmp_path):
    """And it must penalise a regime that reads noise as signal.

    Latent strengths do not move here and the seed ratings are already correct,
    so every point of weekly movement is a response to game noise. A harness that
    could not tell this apart from the drifting case would rank on nothing.
    """
    resolution = _mounted_spec(
        tmp_path,
        fixtures.FixtureSpec(
            seed=SEED, teams=12, weeks=11, drift_sd_points=0.0, game_sd_points=17.0
        ),
    )
    scores = _validation_scores(
        resolution,
        [
            _regime("STEADY", coefficient=0.05, cap=10.0, blowout={"mode": "none"}),
            _regime("REACTIVE", coefficient=1.0, cap=10.0, blowout={"mode": "none"}),
        ],
    )
    assert scores["STEADY"] < scores["REACTIVE"]


# --- seeding is never invented ----------------------------------------------


def test_a_team_without_a_pregame_rating_blocks_rather_than_being_invented(tmp_path):
    spec = fixtures.FixtureSpec(seed=SEED, teams=12, weeks=9)
    observations = tmp_path / "obs.csv"
    fixtures.write_fixture_csv(observations, spec)
    lines = observations.read_text(encoding="utf-8").splitlines()
    header = lines[0].split(",")
    index = header.index("pregame_team_rating")
    rewritten = [lines[0]]
    for line in lines[1:]:
        cells = line.split(",")
        if cells[header.index("team")] == "SYN03":
            cells[index] = ""
        rewritten.append(",".join(cells))
    observations.write_text("\n".join(rewritten) + "\n", encoding="utf-8")

    document = fixtures.write_fixture_contract(
        tmp_path / "contract.json", observations_path=observations
    )
    resolution = contract_module.resolve_contract(contract_module.load_contract(document))
    with pytest.raises(GovernanceBlock, match="refused rather than partially reported"):
        evaluate_module.evaluate_regimes(resolution, [_regime()], context=_context())


# --- determinism ------------------------------------------------------------


def test_the_same_inputs_produce_byte_identical_payloads(mounted):
    first = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    second = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    assert evaluate_module.payload_digest(first) == evaluate_module.payload_digest(second)


def test_regime_order_does_not_change_a_regime_s_own_score(mounted):
    forward = evaluate_module.evaluate_regimes(
        mounted, [_regime("FX-A"), _regime("FX-B", coefficient=0.4)], context=_context()
    )
    reverse = evaluate_module.evaluate_regimes(
        mounted, [_regime("FX-B", coefficient=0.4), _regime("FX-A")], context=_context()
    )

    def scores(payload):
        return {
            r["regime"]["regime_id"]: r["splits"]["validation"]["metrics"][
                cal.PRIMARY_CALIBRATION_METRIC
            ]
            for r in payload["results"]
        }

    assert scores(forward) == scores(reverse)


def test_run_identity_must_be_supplied_rather_than_read_from_the_clock():
    with pytest.raises(InputValidationError, match="does not read the clock"):
        evaluate_module.RunContext(
            run_id="",
            as_of="2026-08-21T00:00:00Z",
            model_version="v",
            configuration_version="c",
            seed=0,
        )


def test_synthetic_fixtures_are_reproducible_from_their_seed(tmp_path):
    spec = fixtures.FixtureSpec(seed=SEED, teams=12, weeks=9)
    first = fixtures.write_fixture_csv(tmp_path / "a.csv", spec).read_bytes()
    second = fixtures.write_fixture_csv(tmp_path / "b.csv", spec).read_bytes()
    assert first == second
    other = fixtures.write_fixture_csv(
        tmp_path / "c.csv", fixtures.FixtureSpec(seed=SEED + 1, teams=12, weeks=9)
    ).read_bytes()
    assert other != first


# --- diagnostics ------------------------------------------------------------


def test_every_named_diagnostic_is_reported_where_supported(mounted):
    payload = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    diagnostics = payload["results"][0]["splits"]["validation"]["diagnostics"]
    names = [d["name"] for d in diagnostics]
    assert set(names) >= set(cal.SUPPORTING_DIAGNOSTICS)
    assert all(d["status"] == "SUPPORTED" for d in diagnostics)


def test_blowout_sensitivity_is_unsupported_when_the_regime_names_no_threshold(mounted):
    payload = evaluate_module.evaluate_regimes(
        mounted, [_regime(blowout={"mode": "none"})], context=_context()
    )
    diagnostics = {
        d["name"]: d for d in payload["results"][0]["splits"]["validation"]["diagnostics"]
    }
    entry = diagnostics["blowout_sensitivity"]
    assert entry["status"] == "UNSUPPORTED"
    assert entry["values"] is None
    assert "names no binding threshold" in entry["reason"]


def test_probability_diagnostics_are_unsupported_without_determinable_outcomes(mounted):
    observation_set = observations_module.load_observation_set(
        mounted.dataset, mounted.contract
    )
    resolved = regime_module.resolve_regime(_regime())
    run = model_module.run_model(
        observation_set, resolved, home_field_points=float(mounted.hfa_points)
    )
    undetermined = tuple(replace(p, actual_win=None) for p in run.predictions)
    for diagnostic in (
        metrics_module.brier_diagnostic(undetermined),
        metrics_module.log_loss_diagnostic(undetermined),
        metrics_module.calibration_diagnostic(undetermined),
    ):
        assert diagnostic.status == "UNSUPPORTED"
        assert "determinable win/loss outcome" in diagnostic.reason


def test_a_structurally_zero_residual_mean_is_not_reported_as_a_bias(mounted):
    payload = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    split = payload["results"][0]["splits"]["validation"]
    residuals = next(d for d in split["diagnostics"] if d["name"] == "residuals")
    assert residuals["values"]["two_sided_rows"] is True
    assert residuals["values"]["mean_bias_interpretable"] is False
    assert math.isclose(residuals["values"]["mean_bias_points"], 0.0, abs_tol=1e-9)
    assert "residual_bias_points" not in split["metrics"]


def test_the_primary_criterion_is_present_under_its_governed_name(mounted):
    payload = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    for split in ("training", "validation"):
        assert (
            cal.PRIMARY_CALIBRATION_METRIC
            in payload["results"][0]["splits"][split]["metrics"]
        )


def test_baseline_comparison_names_what_it_compared_against(mounted):
    payload = evaluate_module.evaluate_regimes(mounted, [_regime()], context=_context())
    comparison = payload["results"][0]["splits"]["validation"]["baseline_comparison"]
    assert comparison["baseline_source"] == "observation_set.expected_margin"
    assert comparison["v2_1_control_workbook_mounted"] is False


def test_rmse_matches_a_hand_computation(mounted):
    observation_set = observations_module.load_observation_set(
        mounted.dataset, mounted.contract
    )
    resolved = regime_module.resolve_regime(_regime())
    run = model_module.run_model(
        observation_set, resolved, home_field_points=float(mounted.hfa_points)
    )
    scored = run.for_split("validation")
    expected = math.sqrt(
        sum((p.predicted_margin - p.actual_margin) ** 2 for p in scored) / len(scored)
    )
    assert metrics_module.baxter_rating_rmse(scored) == pytest.approx(expected)


# --- interface contract -----------------------------------------------------


def test_interface_contract_states_what_c1_and_c3_must_deliver():
    interface = interface_module.interface_contract()
    assert interface["contract_schema_version"] == contract_module.CONTRACT_SCHEMA_VERSION
    assert interface["calibration_axes"] == list(cal.CALIBRATION_FIELDS)
    assert interface["from_c1_calibration_data"]["required_columns"] == list(
        cal.REQUIRED_OBSERVATION_COLUMNS
    )
    assert interface["from_c3_colley_srs"]["blocking"] is False
    assert interface["outputs"]["promotion"]["auto_promotion"] is False
    assert "run the 10,000-path Monte Carlo" in interface["c2_does_not"]
    assert json.loads(json.dumps(interface)) == interface


def test_production_rerating_stays_blocked_by_this_lane():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import rerating

    config = V3Config.from_json(V3_CONFIG)
    with pytest.raises(GovernanceBlock):
        rerating.BlockedGovernedRerater().rerate(week_completed=3, states={}, config=config)
