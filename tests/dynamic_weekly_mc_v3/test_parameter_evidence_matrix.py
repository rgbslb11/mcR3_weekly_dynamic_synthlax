"""Tests for the V3 parameter evidence matrix.

The matrix makes claims of three kinds and each kind is proved differently.
Claims about the frozen data plane are proved against the pinned digests.
Claims about populations are recomputed from the corpus by an independent path
in the test rather than read back out of the artifact. Claims about governance —
nothing fitted, nothing promoted, no holdout consulted, eight blockers — are
proved by exercising the refusals, not by asserting the flags they set.
"""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_contract as contract
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import config as v3_config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
    parameter_evidence_matrix as pem,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock

ROOT = pem.repository_root()


@pytest.fixture(scope="module")
def corpus_rows() -> list[dict[str, str]]:
    with (ROOT / pem.CORPUS_PATH).open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def result() -> pem.MatrixResult:
    return pem.build(ROOT)


@pytest.fixture(scope="module")
def document(result: pem.MatrixResult) -> dict:
    return pem.status_document(result)


# --- 1 & 2. the frozen data plane is exactly these bytes ---------------------


def test_corpus_sha256_is_exact() -> None:
    digest = hashlib.sha256((ROOT / pem.CORPUS_PATH).read_bytes()).hexdigest()
    assert digest == pem.CORPUS_SHA256
    assert digest == "1b91fe0ffc6e205243b88b996c3489735ea90cac1635126b487a11e5cec5f720"


def test_observation_subset_sha256_is_exact() -> None:
    digest = hashlib.sha256((ROOT / pem.OBSERVATIONS_PATH).read_bytes()).hexdigest()
    assert digest == pem.OBSERVATIONS_SHA256
    assert digest == "eb5179ef6e8b5379c96a1423c826af61876712d1f4138110d6a66bf81744ac43"


def test_verification_refuses_bytes_that_are_not_the_frozen_ones(tmp_path: Path) -> None:
    """A matrix computed against other bytes is a statement about nothing."""
    fake = tmp_path / "reference" / "dynamic_weekly_mc_v3"
    fake.mkdir(parents=True)
    (fake / pem.CORPUS_PATH.name).write_text("season\n2006\n", encoding="utf-8")
    (fake / pem.OBSERVATIONS_PATH.name).write_text("season\n2006\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="expected"):
        pem.verify_frozen_artifacts(tmp_path)


def test_verification_refuses_absent_artifacts(tmp_path: Path) -> None:
    with pytest.raises(GovernanceBlock, match="not present"):
        pem.verify_frozen_artifacts(tmp_path)


# --- 3. the canonical corpus is still 5,148 ---------------------------------


def test_canonical_corpus_remains_5148_rows(corpus_rows: list[dict[str, str]]) -> None:
    assert len(corpus_rows) == 5148
    assert pem.CANONICAL_CORPUS_ROWS == 5148
    assert len({r["provenance_identity_sha256"] for r in corpus_rows}) == 5148


def test_paired_subset_and_limited_capability_members_reconcile(
    document: dict,
) -> None:
    assert document["fully_paired_walkforward_rows"] == 3259
    assert document["limited_capability_corpus_members"] == 1889
    assert (
        document["fully_paired_walkforward_rows"]
        + document["limited_capability_corpus_members"]
        == 5148
    )


def test_this_lane_does_not_rebuild_the_corpus(document: dict) -> None:
    assert document["corpus_rebuilt_by_this_lane"] is False
    for entry in document["frozen_artifacts"].values():
        assert entry["mutated_by_this_lane"] is False


# --- 4. populations come from capability requirements, not a universal mask --


def test_populations_are_not_a_single_universal_mask(result: pem.MatrixResult) -> None:
    """If one exclusion mask governed every parameter, every population would match."""
    sizes = {name: p.rows for name, p in result.populations.items()}
    assert len(set(sizes.values())) >= 6, sizes
    # The outcome-only question reaches rows the strictest contract refuses, which
    # is only possible if eligibility is decided per use.
    assert sizes["ACTUAL_MARGIN_ONLY"] == 5144
    assert sizes["FULL_WALKFORWARD_OBSERVATION_CONTRACT"] == 3259
    assert sizes["ACTUAL_MARGIN_ONLY"] > sizes["RESIDUAL_ONLY"] > sizes[
        "FULL_WALKFORWARD_OBSERVATION_CONTRACT"
    ]


def test_each_population_is_exactly_the_conjunction_of_its_own_requirements(
    corpus_rows: list[dict[str, str]], result: pem.MatrixResult
) -> None:
    for name, predicates in pem.POPULATION_DEFINITIONS.items():
        expected = sum(1 for row in corpus_rows if all(p.test(row) for p in predicates))
        assert result.populations[name].rows == expected, name


def test_a_parameter_is_not_charged_for_what_another_parameter_needs(
    result: pem.MatrixResult,
) -> None:
    """Blowout frequency needs no prediction; game SD does. Their populations differ."""
    blowout = pem.PARAMETER_SPECS_BY_NAME["blowout_treatment"]
    game_sd = pem.PARAMETER_SPECS_BY_NAME["game_sd_points"]
    assert blowout.primary_population == "ACTUAL_MARGIN_ONLY"
    assert game_sd.primary_population == "RESIDUAL_ONLY"
    assert (
        result.populations[blowout.primary_population].rows
        > result.populations[game_sd.primary_population].rows
    )
    # And no overtime requirement leaks into a parameter that has none.
    assert "overtime_status_known" not in {
        p.predicate_id for p in pem.POPULATION_DEFINITIONS[game_sd.primary_population]
    }


def test_every_requirement_names_the_mathematics_that_makes_it_one() -> None:
    for predicates in pem.POPULATION_DEFINITIONS.values():
        for predicate in predicates:
            assert predicate.reason.strip()
            assert predicate.kind in ("calibration_use", "capability", "recorded_field")


# --- 5. no missing field is fabricated --------------------------------------


def test_no_population_admits_a_row_on_a_field_the_source_left_empty(
    corpus_rows: list[dict[str, str]]
) -> None:
    residual = [
        r
        for r in corpus_rows
        if pem.RESIDUAL_USE.test(r) and pem.WEEK_ORDINAL_RECORDED.test(r)
    ]
    for row in residual:
        assert row["expected_margin"].strip() != ""
        assert row["actual_margin"].strip() != ""
        assert row["week"].strip() != ""


def test_component_rating_population_never_stands_in_for_an_unrecorded_rating(
    corpus_rows: list[dict[str, str]]
) -> None:
    pool = [
        r
        for r in corpus_rows
        if all(
            p.test(r)
            for p in pem.POPULATION_DEFINITIONS["RESIDUAL_WEEK_AND_COMPONENT_RATINGS"]
        )
    ]
    assert pool
    for row in pool:
        assert row["pregame_team_rating"].strip() != ""
        assert row["pregame_opponent_rating"].strip() != ""
    # And rows the source left without ratings are simply absent, not filled.
    assert {int(r["season"]) for r in pool} == {2006, 2007}


def test_prohibited_imputations_are_declared_for_every_parameter() -> None:
    for spec in pem.PARAMETER_SPECS:
        assert spec.prohibited_imputations
        joined = " ".join(spec.prohibited_imputations)
        assert "actual result" in joined
        assert "overtime UNKNOWN read as regulation" in joined


def test_prior_game_counts_are_read_never_imputed(result: pem.MatrixResult) -> None:
    census = result.stratum_census
    assert census["missing_count_imputed"] is False
    assert census["rows_without_recorded_count"] == 0
    assert census["field_admission_status"] == (
        "REQUIRES_ADMISSION_RULING_NOT_ON_GOVERNED_ALLOWLIST"
    )


def test_history_depth_census_counts_corpus_rows_not_games_played(
    result: pem.MatrixResult,
) -> None:
    assert result.depth_census["counts_corpus_rows_not_games_played"] is True


# --- 6. 2025 cannot influence method selection ------------------------------


def test_holdout_is_refused_as_a_selection_surface() -> None:
    with pytest.raises(GovernanceBlock, match="may not be read"):
        pem.require_selection_population("holdout")
    assert pem.require_selection_population("validation") == "validation"


def test_holdout_is_refused_as_a_source_of_candidate_estimates() -> None:
    with pytest.raises(GovernanceBlock, match="holdout"):
        pem.require_fitting_population("holdout")
    assert pem.require_fitting_population("training") == "training"
    with pytest.raises(GovernanceBlock):
        pem.require_fitting_population("validation")


@pytest.mark.parametrize("decision", pem.HOLDOUT_PROHIBITED_DECISIONS)
def test_every_named_selection_decision_refuses_the_holdout(decision: str) -> None:
    with pytest.raises(GovernanceBlock, match="2025 holdout"):
        pem.refuse_holdout_decision(decision)


def test_the_named_decisions_cover_all_six_parameters_and_the_fcs_mapping() -> None:
    joined = " ".join(pem.HOLDOUT_PROHIBITED_DECISIONS)
    for fragment in (
        "formula",
        "coefficient",
        "cap",
        "weights",
        "threshold",
        "regularization",
        "game SD",
        "FCS point mapping",
    ):
        assert fragment in joined


def test_no_matrix_record_marks_the_holdout_usable_for_selection(document: dict) -> None:
    payload = json.dumps(document)
    assert '"holdout_usable_for_selection": true' not in payload.lower()
    for record in document["parameters"]:
        assert record["holdout_usable_for_selection"] is False
        assert record["selection_split"] == cal.SELECTION_SPLIT == "validation"
    assert document["partition_policy"]["holdout_scored_in_this_lane"] is False
    assert (
        document["partition_policy"]["model_selection_statistics_on_holdout_permitted"]
        is False
    )


def test_holdout_appears_only_as_a_population_census(document: dict) -> None:
    """Counting rows is permitted; measuring them is not."""
    assert document["partition_policy"]["population_census_of_holdout_permitted"] is True
    for record in document["parameters"]:
        holdout = record["holdout_available_rows"]
        assert holdout is None or isinstance(holdout, int)


def test_no_module_routine_computes_a_statistic_of_a_holdout_row() -> None:
    """The matrix counts rows. It never reads a margin, a rating or a residual value.

    Proved against the module source rather than by inspection, so a later edit
    that starts averaging something has to break this test to land.
    """
    source = inspect.getsource(pem)
    for numeric_read in (
        'float(row["actual_margin"])',
        'float(row["expected_margin"])',
        'float(row["pregame_team_rating"])',
        'float(row["pregame_opponent_rating"])',
        "statistics.",
        "numpy",
    ):
        assert numeric_read not in source, numeric_read
    assert pem.LANE_SCORES_HOLDOUT is False


def test_holdout_rows_carry_the_corpus_lineage_flag(
    corpus_rows: list[dict[str, str]]
) -> None:
    holdout = [r for r in corpus_rows if pem.split_of(r) == "holdout"]
    assert len(holdout) == 757
    for row in holdout:
        assert "HOLDOUT_SEASON_NOT_FOR_MODEL_SELECTION" in row["lineage_flags"]


def test_partition_matches_the_governed_seasons(document: dict) -> None:
    policy = document["partition_policy"]
    assert policy["training"] == [2006, 2007, 2008, 2009, 2010, 2011]
    assert policy["validation"] == [2024]
    assert policy["holdout"] == [2025]
    assert policy["assignment"] == cal.TEMPORAL_SPLIT_ASSIGNMENT == "TEMPORAL_ONLY"
    assert policy["split_policy"]["holdout"] == cal.HOLDOUT_USE


# --- 7. FCS remains present, excluded only where the mapping is unresolved ---


def test_fcs_rows_remain_in_the_canonical_corpus(
    corpus_rows: list[dict[str, str]]
) -> None:
    fcs = [r for r in corpus_rows if r["cap_fcs_participant"].strip() == "True"]
    assert len(fcs) == 69
    assert len(corpus_rows) == 5148


def test_fcs_is_excluded_only_from_uses_needing_the_unresolved_point_scale(
    result: pem.MatrixResult,
) -> None:
    assert result.populations["ACTUAL_MARGIN_ONLY"].fcs_rows == 69
    for name in (
        "RESIDUAL_ONLY",
        "RESIDUAL_AND_WEEK_ORDINAL",
        "RESIDUAL_WEEK_AND_COMPONENT_RATINGS",
        "FULL_WALKFORWARD_OBSERVATION_CONTRACT",
    ):
        assert result.populations[name].fcs_rows == 0, name


def test_no_fcs_point_mapping_is_invented(document: dict) -> None:
    dependency = document["fcs_dependency"]
    assert dependency["point_scale_mapping_status"] == "UNRESOLVED"
    assert dependency["promoted_by_this_lane"] is False
    assert dependency["mapping_invented"] is False
    assert dependency["fcs_removed_from_canonical_corpus"] is False
    assert dependency["blocker"] in pem.AUTHORITATIVE_BLOCKERS


def test_every_parameter_states_its_fcs_disposition() -> None:
    for spec in pem.PARAMETER_SPECS:
        assert spec.requires_fcs_point_adapter is False
        assert spec.fcs_disposition


# --- 8. OT UNKNOWN remains UNKNOWN ------------------------------------------


def test_overtime_unknown_is_never_read_as_regulation(
    corpus_rows: list[dict[str, str]], result: pem.MatrixResult
) -> None:
    known = sum(1 for r in corpus_rows if r["overtime_status"] == "KNOWN")
    unknown = sum(1 for r in corpus_rows if r["overtime_status"] == "UNKNOWN")
    assert known == 931
    assert unknown == 4217
    assert known + unknown == 5148
    assert result.populations["OVERTIME_KNOWN_OUTCOMES"].rows == known
    assert result.populations["OVERTIME_KNOWN_OUTCOMES"].overtime_unknown_rows == 0


def test_overtime_unknown_rows_are_reported_not_dropped(
    result: pem.MatrixResult,
) -> None:
    """The residual population keeps them; a separate population isolates them."""
    residual = result.populations["RESIDUAL_ONLY"]
    assert residual.overtime_unknown_rows == 3783
    assert residual.overtime_known_rows == 860
    assert residual.rows == 4643
    assert result.populations["RESIDUAL_AND_OVERTIME_UNKNOWN"].rows == 3783
    assert result.populations["RESIDUAL_AND_OVERTIME_KNOWN"].rows == 860


def test_blowout_analysis_does_not_universally_exclude_overtime_unknown_games(
    document: dict,
) -> None:
    record = next(
        r for r in document["parameters"] if r["parameter_name"] == "blowout_treatment"
    )
    domains = record["evidence_domains_of_the_question"]
    assert domains["A_outcome_only_blowout_frequency"] == 5144
    assert domains["B_residual_based_rerating_influence"] == 4643
    assert domains["C_overtime_sensitive"] == 931
    assert record["requires_OT_status"] == "FALSE_FOR_DOMAINS_A_AND_B_TRUE_FOR_DOMAIN_C"
    assert record["overtime_census"]["ot_unknown_rows"] > 0


def test_no_overtime_conditioned_estimate_is_available_on_training(
    result: pem.MatrixResult,
) -> None:
    """The constraint that makes the overtime question a ruling rather than a fit."""
    assert result.populations["RESIDUAL_AND_OVERTIME_KNOWN"].training_rows == 0
    assert result.populations["OVERTIME_KNOWN_OUTCOMES"].training_rows == 0


# --- 9. the movement-cap alternatives are explicit --------------------------


def test_movement_cap_population_alternatives_are_named_with_exact_counts(
    document: dict,
) -> None:
    record = next(
        r
        for r in document["parameters"]
        if r["parameter_name"] == "weekly_movement_cap_points"
    )
    options = {a["option"]: a for a in record["population_alternatives"]}
    assert set(options) == {"A", "B", "C", "D"}
    assert options["A"]["rows"] == 1014
    assert options["B"]["rows"] == 4448
    assert options["C"]["rows"] == 4448
    assert options["D"]["rows"] == 4448
    assert record["training_eligible_rows_by_alternative"] == {
        "A": 1014,
        "B": 3120,
        "C": 3120,
        "D": 3120,
    }
    assert record["validation_eligible_rows_by_alternative"]["A"] == 0
    assert record["selection_available_under_alternative"] == {
        "A": False,
        "B": True,
        "C": True,
        "D": True,
    }


def test_the_1014_versus_4448_question_is_answered_mathematically_not_by_size(
    document: dict,
) -> None:
    finding = document["movement_cap_identifiability"]
    assert finding["finding"] == pem.MOVEMENT_CAP_FINDING
    assert finding["components_of_exactly_two_teams"] == 4418
    assert finding["weekly_opponent_graph_components"] == 4425
    assert finding["unknown_team_week_ratings"] == 8862
    assert finding["equations_available"] == 4448
    assert finding["system_is_rank_deficient"] is True
    assert finding["same_season_matchups_observed_more_than_once"] == 40


def test_identifiability_evidence_recomputes_from_the_corpus(
    corpus_rows: list[dict[str, str]], result: pem.MatrixResult
) -> None:
    recomputed = pem.weekly_identifiability_evidence(corpus_rows)
    assert recomputed == result.identifiability


def test_the_cap_target_is_reported_unresolved_rather_than_chosen() -> None:
    spec = pem.PARAMETER_SPECS_BY_NAME["weekly_movement_cap_points"]
    assert spec.mathematical_target_settled is False
    assert spec.primary_population == "UNRESOLVED_PENDING_RULING"
    assert spec.chairman_ruling_required is True
    assert spec.mathematical_target.startswith("UNRESOLVED")


def test_the_repository_genuinely_does_not_settle_the_cap_semantics() -> None:
    """The premise behind the referral, checked against the code it cites."""
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import rerating

    fixture_doc = rerating.FixtureResidualRerater.__doc__ or ""
    normalised = " ".join(fixture_doc.split())
    assert "Test-only" in normalised
    assert "Never loaded by the V3 CLI" in normalised
    assert "without asserting a canonical V3 calibration formula" in normalised
    blocked_doc = rerating.BlockedGovernedRerater.__doc__ or ""
    assert "guardrail" in blocked_doc
    assert (
        pem.WEEKLY_UPDATE_ARCHITECTURE[
            "canonical_v3_weekly_update_formula_defined_in_repository"
        ]
        is False
    )


# --- 10. an ambiguity is reported rather than silently decided ---------------


def test_every_chairman_ruling_names_alternatives_and_is_not_decided_here() -> None:
    assert pem.CHAIRMAN_RULINGS_REQUIRED
    for ruling in pem.CHAIRMAN_RULINGS_REQUIRED:
        assert ruling.this_lane_decided_it is False
        assert len(ruling.alternatives) >= 2
        assert ruling.question.strip().endswith("?")
        assert ruling.consequence_of_not_ruling.strip()
        assert ruling.parameter in pem.PARAMETER_SPECS_BY_NAME


def test_every_parameter_surfaces_its_open_methodology_questions() -> None:
    for spec in pem.PARAMETER_SPECS:
        assert spec.open_methodology_questions, spec.parameter_name
        assert spec.chairman_ruling_required is True


def test_each_chairman_ruling_reaches_its_parameter_record(document: dict) -> None:
    by_name = {r["parameter_name"]: r for r in document["parameters"]}
    for ruling in pem.CHAIRMAN_RULINGS_REQUIRED:
        assert ruling.ruling_id in by_name[ruling.parameter]["chairman_rulings"]


def test_no_blowout_threshold_is_published(document: dict) -> None:
    """Publishing a tail census would make an unissued threshold look settled."""
    record = next(
        r for r in document["parameters"] if r["parameter_name"] == "blowout_treatment"
    )
    assert record["threshold_conditioned_tail_census_published"] is False


def test_recent_form_weights_stay_separate_from_the_governed_prior_decay(
    document: dict,
) -> None:
    record = next(
        r for r in document["parameters"] if r["parameter_name"] == "recent_form_weights"
    )
    assert record["governed_preseason_prior_decay_is_separate"] is True
    assert record["governed_preseason_prior_decay"] == {
        str(k): v for k, v in sorted(v3_config.DEFAULT_PRIOR_DECAY.items())
    }
    assert record["governed_preseason_prior_decay"]["5"] == 0.00


def test_recent_form_depth_census_reports_both_history_readings(
    result: pem.MatrixResult,
) -> None:
    census = result.depth_census
    assert census["subject_only"]["0"]["rows"] == 4448
    assert census["symmetric"]["0"]["rows"] == 4448
    assert census["subject_only"]["1"]["by_split"]["training"] == 2547
    assert census["symmetric"]["1"]["by_split"]["training"] == 2833
    assert census["subject_only"]["5"]["by_split"]["training"] == 483
    assert census["symmetric"]["5"]["by_split"]["training"] == 1696
    for mode in ("subject_only", "symmetric"):
        depths = [census[mode][str(k)]["rows"] for k in range(7)]
        assert depths == sorted(depths, reverse=True)


def test_sample_size_low_regime_is_reported_absent_not_extrapolated(
    result: pem.MatrixResult,
) -> None:
    census = result.stratum_census
    assert census["by_stratum"]["0-2"]["rows"] == 0
    assert census["observed_minimum"] == 3
    assert census["finding"] == "LOW_SAMPLE_REGIME_ABSENT_FROM_ADMITTED_EVIDENCE"
    assert result.low_sample_trace["rows"] == 1046
    assert result.low_sample_trace["carries_recorded_games_played_count"] is False


def test_game_sd_definitions_are_distinguished(document: dict) -> None:
    record = next(
        r for r in document["parameters"] if r["parameter_name"] == "game_sd_points"
    )
    census = record["definition_census"]
    assert census["A_sd_of_raw_actual_margins"] == 5144
    assert census["B_sd_of_prediction_residuals"] == 4643
    assert census["ot_known_eligible_rows"] == 860
    assert census["ot_unknown_eligible_rows"] == 3783
    assert census["ot_known_training_rows"] == 0
    assert record["legacy_margin_sd_20_2_status"] == "UNAPPROVED_HISTORICAL_EVIDENCE"
    assert record["legacy_margin_sd_20_2_used"] is False
    assert record["separate_governance_blocker"] == "governance.GAME_SD_CALIBRATION_OPEN"
    assert record["separate_chairman_promotion_required_after_evidence"] is True


def test_legacy_margin_sd_is_not_silently_adopted(document: dict) -> None:
    """20.2 appears in the matrix only as a refusal, never as a value."""
    assert cal.RECORDED_LEGACY_MARGIN_SD == 20.2

    def numeric_values(node: object) -> list[float]:
        if isinstance(node, dict):
            return [v for child in node.values() for v in numeric_values(child)]
        if isinstance(node, list):
            return [v for child in node for v in numeric_values(child)]
        if isinstance(node, bool):
            return []
        if isinstance(node, (int, float)):
            return [float(node)]
        return []

    assert 20.2 not in numeric_values(document)
    record = next(
        r for r in document["parameters"] if r["parameter_name"] == "game_sd_points"
    )
    assert record["legacy_margin_sd_20_2_used"] is False
    assert any("20.2" in text for text in record["prohibited_imputations"])


# --- 11 & 12. nothing is fitted and nothing is promoted ---------------------


def test_no_parameter_receives_a_fitted_numerical_value(document: dict) -> None:
    for record in document["parameters"]:
        assert record["fitted"] is False
        assert record["promoted"] is False
        assert "fitted_value" not in record
        assert "candidate_value" not in record
    assert document["parameters_fitted_by_this_lane"] == []
    assert document["fitted"] is False
    assert pem.LANE_FITS_PARAMETERS is False


def test_no_parameter_is_promoted(document: dict) -> None:
    assert document["parameters_promoted_by_this_lane"] == []
    assert document["promoted"] is False
    assert pem.LANE_PROMOTES_PARAMETERS is False


def test_the_module_exposes_no_route_to_a_value() -> None:
    """There is no callable here that returns or writes a calibration value."""
    for name in dir(pem):
        if name.startswith("_"):
            continue
        assert not name.startswith("fit_")
        assert not name.startswith("promote")
        assert not name.startswith("estimate_")
        assert not name.startswith("rank_")
        assert not name.startswith("score_")


def test_every_matrix_record_carries_the_six_governed_parameter_names(
    document: dict,
) -> None:
    names = [r["parameter_name"] for r in document["parameters"]]
    assert names == list(cal.CALIBRATION_FIELDS)


def test_every_record_carries_the_full_matrix_schema(document: dict) -> None:
    required_keys = {
        "parameter_name",
        "mathematical_target",
        "required_fields",
        "optional_fields",
        "prohibited_imputations",
        "training_eligible_rows",
        "validation_eligible_rows",
        "holdout_available_rows",
        "per_season_eligibility",
        "evidence_domain_census",
        "division_census",
        "overtime_census",
        "requires_expected_margin",
        "requires_component_ratings",
        "requires_individual_team_state",
        "requires_FCS_point_adapter",
        "requires_OT_status",
        "candidate_metrics",
        "selection_metric",
        "stability_checks",
        "open_methodology_questions",
        "chairman_ruling_required",
        "fitted",
        "promoted",
    }
    for record in document["parameters"]:
        assert required_keys <= set(record), sorted(required_keys - set(record))


def test_no_required_field_is_invented(corpus_rows: list[dict[str, str]]) -> None:
    """Every field the matrix asks for already exists somewhere governed.

    A required field that is neither a contract field, nor a field already
    raised for an admission ruling, nor a column the frozen corpus carries,
    would be a requirement this lane made up.
    """
    known = {f.name for f in contract.REQUIRED_CONTRACT_FIELDS}
    ruling_pending = {f.name for f in contract.FIELDS_REQUIRING_ADMISSION_RULING}
    corpus_columns = set(corpus_rows[0])
    admissible = known | ruling_pending | corpus_columns
    for spec in pem.PARAMETER_SPECS:
        for name in spec.required_fields + spec.optional_fields:
            assert name in admissible, (spec.parameter_name, name)


def test_the_one_required_field_outside_the_corpus_is_the_one_awaiting_a_ruling(
    corpus_rows: list[dict[str, str]]
) -> None:
    corpus_columns = set(corpus_rows[0])
    contract_fields = {f.name for f in contract.REQUIRED_CONTRACT_FIELDS}
    outside = {
        name
        for spec in pem.PARAMETER_SPECS
        for name in spec.required_fields
        if name not in corpus_columns and name not in contract_fields
    }
    assert outside == {"games_played_to_date"}


def test_games_played_to_date_is_flagged_as_needing_its_own_ruling(
    document: dict,
) -> None:
    spec = pem.PARAMETER_SPECS_BY_NAME["sample_size_regularization"]
    assert "games_played_to_date" in spec.required_fields
    assert "games_played_to_date" in {
        f.name for f in contract.FIELDS_REQUIRING_ADMISSION_RULING
    }
    assert any("FIELD ADMISSION" in q for q in spec.open_methodology_questions)
    record = next(
        r
        for r in document["parameters"]
        if r["parameter_name"] == "sample_size_regularization"
    )
    assert record["required_fields_awaiting_admission_ruling"] == [
        "games_played_to_date"
    ]


def test_pending_admission_fields_are_read_from_the_contract() -> None:
    assert pem.FIELDS_AWAITING_ADMISSION_RULING == tuple(
        sorted(f.name for f in contract.FIELDS_REQUIRING_ADMISSION_RULING)
    )


def test_overtime_and_game_type_are_reported_as_pending_not_as_available(
    document: dict,
) -> None:
    """They are optional evidence awaiting a ruling, never quietly required."""
    for record in document["parameters"]:
        for name in record["required_fields_awaiting_admission_ruling"]:
            assert name in pem.FIELDS_AWAITING_ADMISSION_RULING
        for name in record["optional_fields_awaiting_admission_ruling"]:
            assert name in pem.FIELDS_AWAITING_ADMISSION_RULING
    game_sd = next(
        r for r in document["parameters"] if r["parameter_name"] == "game_sd_points"
    )
    assert "overtime_periods" in game_sd["optional_fields_awaiting_admission_ruling"]
    assert "overtime_periods" not in game_sd["required_fields"]


# --- metric policy -----------------------------------------------------------


def test_metric_policy_preserves_the_governed_hierarchy(document: dict) -> None:
    policy = document["metric_policy"]
    assert policy["primary"] == cal.PRIMARY_CALIBRATION_METRIC
    assert policy["witnesses_reported_independently"] == ["colley_matrix", "srs"]
    assert policy["weighted_witness_composite"] == "REFUSED"
    assert policy["parameter_values_chosen_in_this_lane"] is False


def test_no_weighted_witness_composite_is_constructible() -> None:
    with pytest.raises(GovernanceBlock):
        cal.reject_witness_composite(["baxter", "colley_matrix", "srs"])


def test_metrics_attach_only_where_mathematically_relevant() -> None:
    residual_only = {"brier_score", "log_loss", "probability_calibration"}
    cap = pem.PARAMETER_SPECS_BY_NAME["weekly_movement_cap_points"]
    assert not residual_only & set(cap.candidate_metrics)
    game_sd = pem.PARAMETER_SPECS_BY_NAME["game_sd_points"]
    assert residual_only & set(game_sd.candidate_metrics)
    for spec in pem.PARAMETER_SPECS:
        assert spec.selection_metric == cal.PRIMARY_CALIBRATION_METRIC
        assert spec.stability_checks


# --- 13. V3 configuration is unchanged with all six values null -------------


def test_canonical_v3_config_still_holds_six_nulls() -> None:
    raw = json.loads(
        (ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json").read_text(
            encoding="utf-8"
        )
    )
    calibration = raw["calibration"]
    for name in cal.CALIBRATION_FIELDS:
        assert calibration[name] is None, name


def test_config_still_reports_all_six_calibration_blockers() -> None:
    config = v3_config.V3Config.from_json(
        ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
    )
    assert sorted(config.calibration.blockers()) == sorted(cal.CALIBRATION_FIELDS)


def test_experimental_regime_file_still_ships_no_regimes() -> None:
    raw = json.loads(
        (
            ROOT / "config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json"
        ).read_text(encoding="utf-8")
    )
    assert raw.get("regimes", []) == []


# --- 14. global blockers remain exactly eight -------------------------------


def test_authoritative_blockers_remain_exactly_eight() -> None:
    assert pem.AUTHORITATIVE_BLOCKERS == (
        "calibration.blowout_treatment",
        "calibration.game_sd_points",
        "calibration.recent_form_weights",
        "calibration.sample_size_regularization",
        "calibration.weekly_movement_cap_points",
        "calibration.weekly_performance_residual_coefficient",
        "governance.GAME_SD_CALIBRATION_OPEN",
        "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
    )
    assert len(pem.AUTHORITATIVE_BLOCKERS) == 8
    assert set(pem.AUTHORITATIVE_BLOCKERS) == set(
        blocker_report.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    )


def test_this_lane_retires_and_opens_nothing(document: dict) -> None:
    census = document["blockers"]
    assert census["count"] == 8
    assert census["retired_by_this_lane"] == []
    assert census["opened_by_this_lane"] == []


def test_every_calibration_blocker_has_a_matrix_record(document: dict) -> None:
    recorded = {r["blocker_id"] for r in document["parameters"]}
    calibration_blockers = {
        b for b in pem.AUTHORITATIVE_BLOCKERS if b.startswith("calibration.")
    }
    assert recorded == calibration_blockers


# --- the artifact ------------------------------------------------------------


def test_status_artifact_matches_the_committed_bytes(result: pem.MatrixResult) -> None:
    path = ROOT / pem.DEFAULT_STATUS_PATH
    assert path.exists(), "status artifact is not emitted"
    assert path.read_bytes() == pem.status_bytes(result)


def test_status_artifact_is_deterministic(result: pem.MatrixResult) -> None:
    assert pem.status_bytes(result) == pem.status_bytes(pem.build(ROOT))


def test_handoff_is_ready(document: dict) -> None:
    assert document["handoff"] == "V3_PARAMETER_EVIDENCE_MATRIX_READY"
    assert document["unresolved_parameter_count"] == 6
