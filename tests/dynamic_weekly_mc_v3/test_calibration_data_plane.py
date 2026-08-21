"""Lane C1 — historical calibration data plane.

Every observation used here is synthetic and stamped TEST_FIXTURE. The point of
the suite is that the plumbing works *and* that working plumbing changes nothing
about the evidence position: no blocker retires, no coefficient is proposed and
no synthetic row can present itself as governed calibration evidence.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration_data as cd
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

ROOT = Path(__file__).resolve().parents[2]
CANONICAL_MD = (
    ROOT / "reference/dynamic_weekly_mc_v3/inputs/2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md"
)
MANIFEST = ROOT / "reference/dynamic_weekly_mc_v3/MISSING_CALIBRATION_EVIDENCE.json"

#: Real canonical schedule_ids, so the identity check is exercised against the
#: governed universe rather than a convenient stand-in.
PAIRS = [
    ("ARK", "GAST"),
    ("UK", "VAN"),
    ("FSU", "NMSU"),
    ("UVA", "NCSU"),
    ("ALA", "AF"),
    ("BC", "CAL"),
    ("ARIZ", "WVU"),
]

HEADER = list(cd.REQUIRED_DATA_PLANE_COLUMNS) + ["subsequent_outcomes"]


def _fixture_row(index, team, opponent, *, week=None, event_day=None, **overrides):
    week = week if week is not None else index + 1
    day = event_day if event_day is not None else 1 + index
    event_time = f"2025-09-{day:02d}T18:00:00Z"
    row = {
        "game_id": f"TF{index:04d}",
        "season": "2025",
        "week": str(week),
        "event_time": event_time,
        "team": team,
        "opponent": opponent,
        "venue": "HOME",
        "pregame_team_rating": f"{100.0 + index:.4f}",
        "pregame_opponent_rating": f"{95.0 + index:.4f}",
        "expected_margin": f"{3.5 + index:.2f}",
        "actual_margin": f"{7.0 + index:.2f}",
        "game_result": "WIN",
        "prior_rating_state": f"TF-STATE-{index}@2025-09-{day:02d}T00:00:00Z",
        "source_provenance": f"{cd.TEST_FIXTURE_STAMP}synthetic-lane-c1#{index}",
        "observed_at": f"2025-09-{day:02d}T22:00:00Z",
        "recorded_at": f"2025-09-{day + 1:02d}T02:00:00Z",
        "model_version": "3.0.0-experimental-harness",
        "configuration_version": "V3-PLACEHOLDER-2026-08-21-R2-001",
        "subsequent_outcomes": "",
    }
    row.update({k: str(v) for k, v in overrides.items()})
    return row


def _fixture_rows(count=len(PAIRS), **overrides):
    return [
        _fixture_row(i, *PAIRS[i % len(PAIRS)], **overrides) for i in range(count)
    ]


def _write_csv(tmp_path, rows, name="obs.csv"):
    path = tmp_path / name
    lines = [",".join(HEADER)]
    lines.extend(",".join(row[column] for column in HEADER) for row in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _observations(rows):
    return [cd.normalize_row(row) for row in rows]


@pytest.fixture(scope="module")
def universe():
    return cd.canonical_team_universe(CANONICAL_MD)


# --- 1. inventory of what is actually mounted --------------------------------


def test_every_registered_historical_source_is_mounted_and_hashed():
    inventory = cd.inventory_historical_sources(ROOT)
    unmounted = [s["relative_path"] for s in inventory if not s["mounted"]]
    assert unmounted == []
    assert all(len(s["sha256"]) == 64 for s in inventory)


def test_no_mounted_source_supplies_game_level_observations():
    """The central finding of the lane: fixtures, fitted ratings and simulated
    output are three different things, and none of them is an observation."""
    inventory = cd.inventory_historical_sources(ROOT)
    supplying = [s["relative_path"] for s in inventory if s["supplies_game_level_observations"]]
    assert supplying == []


def test_source_hashes_match_the_governance_record():
    recorded = json.loads(
        (ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R4.json").read_text(
            encoding="utf-8"
        )
    )["artifact_hashes"]
    inventory = {s["relative_path"]: s["sha256"] for s in cd.inventory_historical_sources(ROOT)}
    for relative_path, sha in inventory.items():
        name = Path(relative_path).name
        if name in recorded:
            assert sha == recorded[name], name


def test_the_2025_ratings_are_fitted_on_games_that_are_not_mounted():
    summary = cd.summarize_absent_prior_season_games(
        ROOT / "reference/dynamic_weekly_mc_v3/inputs/"
        "2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx"
    )
    assert summary["teams_with_fitted_2025_rating"] == 119
    assert summary["team_game_sides_recorded"] == 1514
    assert summary["per_game_rows_mounted"] == 0


# --- 2. flow exclusion -------------------------------------------------------


def test_market_flow_sources_are_excluded_from_belief_calibration():
    assert "examples/week1_sample_seed.json" in cd.FLOW_EXCLUDED_SOURCES
    with pytest.raises(GovernanceBlock, match="flow, not belief"):
        cd.assert_flow_source_excluded("examples/week1_sample_seed.json")


def test_simulated_control_output_is_not_belief_evidence():
    control = next(
        s for s in cd.HISTORICAL_SOURCE_REGISTER if "V2_1_STATIC_CONTROL" in s.relative_path
    )
    assert control.admissible_for_belief_calibration is False
    assert control.supplies_game_level_observations is False


def test_public_money_column_is_refused_by_the_loader(tmp_path):
    rows = _fixture_rows(3)
    path = tmp_path / "obs.csv"
    header = HEADER + ["public_money_pct"]
    lines = [",".join(header)]
    lines.extend(",".join(list(r[c] for c in HEADER) + ["61"]) for r in rows)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="non-admissible"):
        cd.load_observations(path, "DS-FLOW")


# --- 3. deterministic loading and normalization ------------------------------


def test_fixture_set_loads_with_provenance(tmp_path):
    path = _write_csv(tmp_path, _fixture_rows())
    observations, provenance = cd.load_observations(path, "DS-TF")
    assert len(observations) == len(PAIRS)
    assert provenance["observation_count"] == len(PAIRS)
    assert provenance["contains_test_fixture_rows"] is True
    assert len(provenance["sha256"]) == 64


def test_loading_is_deterministic(tmp_path):
    path = _write_csv(tmp_path, _fixture_rows())
    first, _ = cd.load_observations(path, "DS-TF")
    second, _ = cd.load_observations(path, "DS-TF")
    assert [o.as_dict() for o in first] == [o.as_dict() for o in second]


def test_dataset_missing_a_data_plane_column_is_refused(tmp_path):
    path = tmp_path / "obs.csv"
    path.write_text(
        "game_id,season,week,team,opponent,expected_margin,actual_margin,observed_at,recorded_at\n"
        "TF1,2025,1,ARK,GAST,3.5,7,2025-09-01T22:00:00Z,2025-09-02T02:00:00Z\n",
        encoding="utf-8",
    )
    with pytest.raises(GovernanceBlock, match="MISSING_CALIBRATION_EVIDENCE"):
        cd.load_observations(path, "DS-THIN")


def test_naive_timestamp_is_refused():
    row = _fixture_row(0, "ARK", "GAST", observed_at="2025-09-01T22:00:00")
    with pytest.raises(InputValidationError, match="naive"):
        cd.normalize_row(row)


def test_unparseable_timestamp_is_refused():
    row = _fixture_row(0, "ARK", "GAST", event_time="last Saturday")
    with pytest.raises(InputValidationError, match="unparseable"):
        cd.normalize_row(row)


def test_unknown_site_is_refused():
    row = _fixture_row(0, "ARK", "GAST", venue="DOME")
    with pytest.raises(InputValidationError, match="site"):
        cd.normalize_row(row)


def test_blank_required_value_is_not_completed_by_default():
    row = _fixture_row(0, "ARK", "GAST", prior_rating_state="")
    with pytest.raises(InputValidationError, match="missing required values"):
        cd.normalize_row(row)


def test_every_mission_schema_field_maps_to_a_governed_column():
    governed = {c.lower() for c in cal.CALIBRATION_OBSERVATION_COLUMNS}
    assert set(cd.MISSION_FIELD_TO_GOVERNED_COLUMN.values()) <= governed


# --- 4. identity checks ------------------------------------------------------


def test_unknown_team_identifier_blocks_and_is_never_guessed(universe):
    observations = _observations(_fixture_rows(1))
    observations[0] = cd.normalize_row(_fixture_row(0, "ARKANSAS", "GAST"))
    findings = cd.check_identity(observations, universe)
    codes = {f.code for f in findings}
    assert "UNRESOLVED_TEAM_IDENTIFIER" in codes
    assert all(f.severity == cd.BLOCK for f in findings)


def test_self_opponent_blocks(universe):
    observations = [cd.normalize_row(_fixture_row(0, "ARK", "ARK"))]
    codes = {f.code for f in cd.check_identity(observations, universe)}
    assert "SELF_OPPONENT" in codes


def test_result_must_agree_with_actual_margin(universe):
    observations = [
        cd.normalize_row(_fixture_row(0, "ARK", "GAST", actual_margin="-7", game_result="WIN"))
    ]
    codes = {f.code for f in cd.check_identity(observations, universe)}
    assert "RESULT_MARGIN_DISAGREEMENT" in codes


def test_clean_fixture_set_passes_identity(universe):
    assert cd.check_identity(_observations(_fixture_rows()), universe) == []


# --- 5. chronology -----------------------------------------------------------


def test_outcome_observed_before_kickoff_blocks():
    observations = [
        cd.normalize_row(
            _fixture_row(0, "ARK", "GAST", observed_at="2025-09-01T10:00:00Z")
        )
    ]
    codes = {f.code for f in cd.check_chronology(observations)}
    assert "OBSERVED_BEFORE_EVENT" in codes


def test_recorded_before_observed_blocks():
    observations = [
        cd.normalize_row(
            _fixture_row(0, "ARK", "GAST", recorded_at="2025-09-01T19:00:00Z")
        )
    ]
    codes = {f.code for f in cd.check_chronology(observations)}
    assert "RECORDED_BEFORE_OBSERVED" in codes


def test_week_numbering_must_not_run_backwards_in_time():
    rows = [
        _fixture_row(0, "ARK", "GAST", week=1, event_day=10),
        _fixture_row(1, "UK", "VAN", week=2, event_day=2),
    ]
    codes = {f.code for f in cd.check_chronology(_observations(rows))}
    assert "WEEK_EVENT_TIME_INVERSION" in codes


def test_clean_fixture_set_passes_chronology():
    assert cd.check_chronology(_observations(_fixture_rows())) == []


# --- 6. duplicates -----------------------------------------------------------


def test_repeated_game_id_blocks():
    rows = _fixture_rows(2)
    rows[1]["game_id"] = rows[0]["game_id"]
    codes = {f.code for f in cd.check_duplicates(_observations(rows))}
    assert "DUPLICATE_GAME_ID" in codes


def test_both_perspectives_of_one_fixture_are_a_duplicate():
    rows = [
        _fixture_row(0, "ARK", "GAST", week=1, event_day=1),
        _fixture_row(1, "GAST", "ARK", week=1, event_day=1),
    ]
    codes = {f.code for f in cd.check_duplicates(_observations(rows))}
    assert "MIRRORED_OBSERVATION" in codes


def test_clean_fixture_set_has_no_duplicates():
    assert cd.check_duplicates(_observations(_fixture_rows())) == []


# --- 7. leakage --------------------------------------------------------------


def test_prior_rating_state_dated_after_kickoff_blocks():
    row = _fixture_row(0, "ARK", "GAST")
    row["prior_rating_state"] = "TF-STATE-0@2025-09-02T00:00:00Z"
    findings = cd.check_leakage([cd.normalize_row(row)])
    assert any(
        f.code == "PRIOR_RATING_STATE_AFTER_EVENT" and f.severity == cd.BLOCK for f in findings
    )


def test_prior_rating_state_without_an_as_of_stamp_is_reported_not_assumed_clean():
    row = _fixture_row(0, "ARK", "GAST")
    row["prior_rating_state"] = "TF-STATE-0"
    findings = cd.check_leakage([cd.normalize_row(row)])
    assert [f.code for f in findings] == ["UNVERIFIABLE_PRIOR_RATING_STATE"]
    assert findings[0].severity == cd.WARN


def test_subsequent_outcomes_are_never_a_pregame_feature():
    assert "subsequent_outcomes" in cd.NON_FEATURE_COLUMNS
    row = _fixture_row(0, "ARK", "GAST", subsequent_outcomes="W,W,L", split="training")
    findings = cd.check_leakage([cd.normalize_row(row)])
    assert any(f.code == "SUBSEQUENT_OUTCOMES_IN_TRAINING_ROW" for f in findings)


def test_clean_fixture_set_has_no_blocking_leakage():
    findings = cd.check_leakage(_observations(_fixture_rows()))
    assert [f for f in findings if f.severity == cd.BLOCK] == []


# --- 8. deterministic split --------------------------------------------------


def test_split_is_deterministic_and_reproducible():
    observations = _observations(_fixture_rows())
    first = cd.assign_deterministic_splits(observations)
    second = cd.assign_deterministic_splits(list(reversed(observations)))
    assert {o.game_id: o.split for o in first} == {o.game_id: o.split for o in second}


def test_split_fills_all_three_buckets():
    assigned = cd.assign_deterministic_splits(_observations(_fixture_rows()))
    assert {o.split for o in assigned} == set(cal.DATA_SPLITS)


def test_split_is_chronological_so_no_later_game_trains_an_earlier_one():
    assigned = cd.assign_deterministic_splits(_observations(_fixture_rows()))
    assert cd.check_split_separation(assigned) == []
    latest_training = max(o.event_time for o in assigned if o.split == "training")
    earliest_holdout = min(o.event_time for o in assigned if o.split == "holdout")
    assert latest_training < earliest_holdout


def test_split_separation_detects_a_chronological_overlap():
    """Move one early game into holdout: training then runs past holdout's start."""
    assigned = cd.assign_deterministic_splits(_observations(_fixture_rows()))
    earliest = min(assigned, key=lambda o: (o.event_time, o.game_id))
    tampered = [
        replace(o, split="holdout") if o.game_id == earliest.game_id else o for o in assigned
    ]
    codes = {f.code for f in cd.check_split_separation(tampered)}
    assert "SPLIT_CHRONOLOGY_OVERLAP" in codes


def test_unsplittably_small_set_is_refused():
    with pytest.raises(GovernanceBlock, match="not a split"):
        cd.assign_deterministic_splits(_observations(_fixture_rows(2)))


def test_empty_set_is_refused():
    with pytest.raises(GovernanceBlock, match="BLOCKED_ON_CALIBRATION_DATA"):
        cd.assign_deterministic_splits([])


def test_split_policy_does_not_claim_governance():
    policy = cd.DEFAULT_SPLIT_POLICY.as_dict()
    assert policy["governed"] is False
    assert policy["randomised"] is False
    assert policy["status"] == "NOT_GOVERNED_PENDING_RULING"


def test_split_fractions_must_leave_a_holdout():
    with pytest.raises(InputValidationError, match="no holdout"):
        cd.SplitPolicy(training_fraction=0.8, validation_fraction=0.3)


# --- 9. aggregate check run --------------------------------------------------


def test_clean_fixture_set_passes_every_check(universe):
    assigned = cd.assign_deterministic_splits(_observations(_fixture_rows()))
    report = cd.run_all_checks(assigned, universe)
    assert report["admissible"] is True
    assert report["blocking_findings"] == []
    assert report["disposition"] == "DATA_PLANE_CHECKS_PASSED"


def test_a_single_blocking_finding_fails_the_whole_run(universe):
    rows = _fixture_rows()
    rows[0]["team"] = "NOT_A_TEAM"
    assigned = cd.assign_deterministic_splits(_observations(rows))
    report = cd.run_all_checks(assigned, universe)
    assert report["admissible"] is False
    assert report["disposition"] == "DATA_PLANE_CHECKS_BLOCKED"


def test_unassigned_splits_block_the_run(universe):
    report = cd.run_all_checks(_observations(_fixture_rows()), universe)
    codes = {f["code"] for f in report["blocking_findings"]}
    assert "UNASSIGNED_OBSERVATIONS" in codes


# --- 10. synthetic fixtures never become evidence ----------------------------


def test_test_fixture_rows_are_stamped_and_recognised():
    observations = _observations(_fixture_rows())
    assert all(o.is_test_fixture for o in observations)


def test_a_test_fixture_set_cannot_present_itself_as_evidence():
    observations = _observations(_fixture_rows())
    with pytest.raises(GovernanceBlock, match="never becomes evidence"):
        cd.assert_not_test_fixture(observations, "DS-TF")


def test_an_unstamped_set_passes_the_fixture_gate():
    rows = _fixture_rows()
    for row in rows:
        row["source_provenance"] = "governed-artifact@sha256:" + "0" * 64
    cd.assert_not_test_fixture(_observations(rows), "DS-REAL")


# --- 11. the manifest --------------------------------------------------------


def test_committed_manifest_reproduces_exactly():
    """Regeneration is a pure function of the repository, with no clock in it."""
    rebuilt = cd.build_missing_calibration_evidence_manifest(ROOT)
    committed = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert committed == rebuilt


def test_manifest_reports_missing_evidence_not_a_dataset():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["code"] == "MISSING_CALIBRATION_EVIDENCE"
    assert manifest["disposition"] == "BLOCKED_ON_CALIBRATION_DATA"
    assert manifest["observation_sets_mounted"] == 0
    assert manifest["sources_supplying_game_level_observations"] == 0


def test_manifest_names_exact_missing_files_and_fields():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    missing_file = manifest["missing_files"][0]
    assert missing_file["path"] == cd.EXPECTED_OBSERVATION_SET
    assert missing_file["exists"] is False
    assert set(missing_file["required_columns"]) == set(cd.REQUIRED_DATA_PLANE_COLUMNS)
    per_field = manifest["missing_fields"]["per_field"]
    assert set(per_field) == set(cd.MISSION_FIELD_TO_GOVERNED_COLUMN)
    assert all(entry["available_at_game_level"] is False for entry in per_field.values())


def test_manifest_retires_no_blocker_and_writes_no_coefficient():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["calibration_blockers_retired_by_this_lane"] == []
    assert manifest["canonical_values_written"] == []
    assert sorted(manifest["unresolved_calibration_fields"]) == sorted(cal.CALIBRATION_FIELDS)


def test_working_plumbing_is_not_evidence():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["data_plane_ready"] is True
    assert manifest["disposition"] == "BLOCKED_ON_CALIBRATION_DATA"


def test_lane_leaves_canonical_calibration_values_null():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config

    config = V3Config.from_json(ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json")
    status = cal.calibration_status(
        {name: getattr(config.calibration, name) for name in cal.CALIBRATION_FIELDS}
    )
    assert status["all_canonical_values_null"] is True


def test_shipped_regime_file_still_authors_no_candidate_values():
    payload = json.loads(
        (ROOT / "config/dynamic_weekly_mc_v3/experimental/calibration_regimes.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["regimes"] == []
