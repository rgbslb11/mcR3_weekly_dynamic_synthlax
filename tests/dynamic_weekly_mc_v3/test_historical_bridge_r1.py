"""R1 — the 2020 and 2025 historical results bridge.

These tests assert the lane's *findings*, not merely that its code runs. Where a
number is load-bearing it is pinned here, so a later change that quietly moves
it fails rather than being reported as a new result.

Two of them exist because the corresponding defect actually occurred during this
lane and was caught late:

``test_the_2025_season_is_complete_for_every_declared_fbs_member`` guards the
silent page truncation that made a 25-event day look like a whole Saturday, and
``test_the_srs_feed_is_two_sided`` guards the one-sided SRS feed that presented
as a singular system on a graph the same module called connected.
"""

from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import historical_bridge as hb
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import srs
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "historical_bridge_r1"
RESULTS_MANIFEST = BRIDGE / "V3_BRIDGE_SOURCE_ACQUISITION_MANIFEST.json"
MEMBERSHIP_MANIFEST = BRIDGE / "V3_BRIDGE_MEMBERSHIP_ACQUISITION_MANIFEST.json"


def _json(name: str) -> dict:
    return json.loads((BRIDGE / name).read_text(encoding="utf-8"))


def _rows(season: int) -> list[dict]:
    path = BRIDGE / f"V3_BRIDGE_{season}_RESULTS.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------------------
# Custody
# --------------------------------------------------------------------------


def test_every_declared_capture_reverifies_against_its_bytes():
    captures = hb.load_captures(RESULTS_MANIFEST, REPO_ROOT)
    assert captures, "no captures declared"
    assert all(capture.custody_verified for capture in captures)
    membership = hb.load_captures(MEMBERSHIP_MANIFEST, REPO_ROOT)
    assert all(capture.custody_verified for capture in membership)

    custody = _json("V3_BRIDGE_SOURCE_CUSTODY_MANIFEST.json")
    assert custody["captures_failing_reverification"] == 0
    assert custody["captures_reverified"] == len(captures) + len(membership)


def test_a_tampered_capture_is_refused_rather_than_reported(tmp_path):
    """Custody that continues past a broken digest is not custody."""
    manifest = json.loads(RESULTS_MANIFEST.read_text(encoding="utf-8"))
    first = manifest["captured"][0]

    target = tmp_path / first["stored_path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    original = (REPO_ROOT / first["stored_path"]).read_bytes()
    tampered = gzip.compress(gzip.decompress(original) + b" ")
    target.write_bytes(tampered)

    local = tmp_path / "manifest.json"
    local.write_text(
        json.dumps({"captured": [first]}), encoding="utf-8", newline="\n"
    )
    with pytest.raises(InputValidationError, match="custody re-verification failed"):
        hb.load_captures(local, tmp_path)


def test_raw_captures_are_stored_as_gz_so_a_checkout_cannot_rewrite_them():
    manifest = json.loads(RESULTS_MANIFEST.read_text(encoding="utf-8"))
    assert all(row["stored_path"].endswith(".json.gz") for row in manifest["captured"])
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "*.gz" in attributes and "binary" in attributes


# --------------------------------------------------------------------------
# Row reconciliation
# --------------------------------------------------------------------------


def test_every_retrieved_row_is_admitted_or_refused_with_a_reason():
    reconciliation = _json("V3_BRIDGE_ROW_RECONCILIATION.json")["per_season"]
    for season in ("2020", "2025"):
        record = reconciliation[season]
        assert record["reconciles"], season
        assert (
            record["raw_event_rows_retrieved"]
            == record["admitted"] + record["excluded"]
        )
        assert sum(record["exclusions_by_reason"].values()) == record["excluded"]


def test_the_admitted_counts_are_the_ones_this_lane_reports():
    assert len(_rows(2020)) == 568
    assert len(_rows(2025)) == 934


def test_no_row_carries_a_rating_of_any_kind():
    """The lane's hardest constraint, asserted against the emitted columns."""
    forbidden = ("rating", "elo", "power", "strength", "z_score", "mu", "sigma")
    for season in (2020, 2025):
        columns = [column.lower() for column in hb.BRIDGE_COLUMNS]
        assert all(
            not any(token in column for token in forbidden) for column in columns
        ), season
        assert set(_rows(season)[0]) == set(hb.BRIDGE_COLUMNS)


# --------------------------------------------------------------------------
# The tier-1 check that licenses a tier-2 season
# --------------------------------------------------------------------------


def test_the_two_authorities_agree_on_every_2020_score_they_both_publish():
    agreement = _json("V3_BRIDGE_CROSS_SOURCE_AGREEMENT_2020.json")["score_agreement"]
    assert agreement["tier_1_rows_matched"] == 553
    assert agreement["score_disagreements"] == 0
    assert agreement["score_agreement_rate"] == 1.0


def test_no_tier_1_game_is_missing_from_the_tier_2_corpus():
    """A tier-1 row with no tier-2 match would mean the corpus lost a game."""
    agreement = _json("V3_BRIDGE_CROSS_SOURCE_AGREEMENT_2020.json")["score_agreement"]
    assert agreement["tier_1_rows_missing_from_tier_2"] == 0
    for row in agreement["unmatched_tier_1_rows"]:
        assert row["reason"] in (
            "NCAA_NAME_NOT_BRIDGED",
            "OUT_OF_TIER_2_SCOPE_NO_FBS_PARTICIPANT",
        )


def test_the_division_declaration_agrees_with_the_tier_1_feed_on_2020():
    """This is what licenses using the declaration for 2025, where tier 1 is mute."""
    division = _json("V3_BRIDGE_CROSS_SOURCE_AGREEMENT_2020.json")["division_agreement"]
    assert division["disagreements"] == []
    assert division["agreement_rate"] == 1.0
    assert division["teams_compared"] >= 130


def test_every_2025_row_states_that_tier_1_could_not_corroborate_it():
    for row in _rows(2025):
        assert row["tier_1_corroboration"] == hb.TIER_1_STALE


def test_2020_rows_carry_one_of_the_two_states_tier_1_can_produce():
    states = {row["tier_1_corroboration"] for row in _rows(2020)}
    assert states <= {hb.CORROBORATED, hb.NOT_CARRIED_BY_TIER_1}
    assert hb.CORROBORATED in states


# --------------------------------------------------------------------------
# The 2025 tier-1 refusal, established from bytes
# --------------------------------------------------------------------------


def test_the_ncaa_feed_serves_2020_and_does_not_serve_2025():
    assessment = _json("V3_BRIDGE_TIER_1_FEED_ASSESSMENT.json")["per_season"]
    assert assessment["2020"]["serves_completed_season"] is True
    stale = assessment["2025"]
    assert stale["serves_completed_season"] is False
    assert stale["disposition"] == "TIER_1_FEED_STALE_REFUSED_AS_COMPLETED_HISTORY"
    # The figures the mission carries, reproduced from the retrieved bytes.
    fbs = stale["by_division_feed"]["fbs"]
    assert fbs["rows_published"] == 878
    assert fbs["game_state_counts"] == {"final": 22, "live": 4, "pre": 852}
    assert stale["rows_whose_feed_update_predates_kickoff"] > 1500
    assert assessment["2020"]["rows_whose_feed_update_predates_kickoff"] == 0
    assert all(
        value.startswith("08-") and "2025" in value
        for value in stale["feed_updated_at_values"]
    )


def test_the_stale_feed_is_refused_on_its_content_not_on_its_status_code():
    """It answers 200 with well-formed objects; that is the trap."""
    manifest = json.loads(RESULTS_MANIFEST.read_text(encoding="utf-8"))
    ncaa_2025 = [
        row
        for row in manifest["captured"]
        if row["source_authority"] == hb.NCAA_AUTHORITY and row["season"] == 2025
    ]
    assert ncaa_2025
    assert all(row["http_status"] == 200 for row in ncaa_2025)


# --------------------------------------------------------------------------
# Coverage — the regression guard for the silent page truncation
# --------------------------------------------------------------------------


def test_the_2025_season_is_complete_for_every_declared_fbs_member():
    coverage = _json("V3_BRIDGE_SEASON_COVERAGE.json")["per_season"]["2025"]
    assert coverage["fbs_members_declared"] == 136
    assert coverage["fbs_members_with_games"] == 136
    assert coverage["fbs_members_below_eight_games"] == []
    assert coverage["min_games"] >= 12


def test_the_acquisition_refuses_a_page_size_above_the_measured_ceiling():
    """Above it the endpoint returns a 25-event page and reports HTTP 200."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "acquire_historical_bridge_r1",
        REPO_ROOT / "scripts" / "acquire_historical_bridge_r1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    assert module.ESPN_PAGE_LIMIT <= module.ESPN_MAX_SAFE_LIMIT
    module.ESPN_PAGE_LIMIT = module.ESPN_MAX_SAFE_LIMIT + 1
    try:
        with pytest.raises(ValueError, match="silently"):
            module.espn_url(module.date(2025, 8, 30))
    finally:
        module.ESPN_PAGE_LIMIT = module.ESPN_MAX_SAFE_LIMIT


def test_the_three_2020_members_with_no_game_are_carried_not_dropped():
    """UConn, New Mexico State and Old Dominion cancelled their 2020 seasons."""
    coverage = _json("V3_BRIDGE_SEASON_COVERAGE.json")["per_season"]["2020"]
    assert coverage["fbs_members_declared"] == 130
    assert coverage["fbs_members_with_games"] == 127
    assert len(coverage["fbs_members_without_games"]) == 3


# --------------------------------------------------------------------------
# Identity
# --------------------------------------------------------------------------


def test_a_qualifier_is_never_folded_away():
    assert hb.normalise_name("Miami (FL)") != hb.normalise_name("Miami (OH)")
    assert hb.normalise_name("Ohio St.") == hb.normalise_name("Ohio State")
    assert hb.normalise_name("Ohio") != hb.normalise_name("Ohio State")


def test_a_key_two_teams_answer_to_resolves_to_neither():
    keys = {"1": ("miami(fl)", "mia"), "2": ("miami(oh)", "mia")}
    bridge = hb.build_name_bridge(keys, {"1": "Miami (FL)", "2": "Miami (OH)"}, [])
    assert bridge.resolve("Miami (FL)") == "1"
    assert bridge.resolve("Miami (OH)") == "2"
    assert bridge.resolve("MIA") is None
    assert "mia" in bridge.ambiguous_keys


def test_the_school_name_prefix_rule_that_unbridged_arizona_is_gone():
    """Regression: prefix keys made ``Arizona`` ambiguous with Arizona State."""
    keys = {
        "9": ("arizona", "arizonawildcats", "ariz"),
        "12": ("arizonastate", "arizonastatesundevils", "asu"),
    }
    bridge = hb.build_name_bridge(keys, {"9": "Arizona", "12": "Arizona State"}, [])
    assert bridge.resolve("Arizona") == "9"
    assert bridge.resolve("Arizona St.") == "12"


def test_canonical_binding_never_removes_a_game():
    """Unbound is a report about the 2026 master, not a filter on football."""
    identity = _json("V3_BRIDGE_TEAM_IDENTITY.json")
    assert identity["unbinding_is_not_exclusion"] is True
    for season in ("2020", "2025"):
        record = identity["per_season"][season]
        assert record["games"] == len(_rows(int(season)))
        assert record["participants_unbound"] > 0


# --------------------------------------------------------------------------
# Historical membership and the 2024 population question
# --------------------------------------------------------------------------


def test_season_membership_is_the_real_historical_series():
    membership = _json("V3_BRIDGE_HISTORICAL_MEMBERSHIP.json")["per_season"]
    assert [membership[str(year)]["fbs_members"] for year in range(2020, 2026)] == [
        130,
        130,
        131,
        133,
        134,
        136,
    ]


def test_the_2024_population_is_resolved_on_evidence_without_a_ruling():
    resolution = _json("V3_BRIDGE_HISTORICAL_MEMBERSHIP.json")[
        "population_resolution_2024"
    ]
    assert resolution["resolved"] is True
    assert resolution["resolution"] == 134
    assert resolution["requires_chairman_ruling"] is False


def test_the_conference_distribution_candidate_is_right_until_2024_and_then_is_not():
    comparisons = _json("V3_BRIDGE_HISTORICAL_MEMBERSHIP.json")["candidate_comparisons"]
    per_season = comparisons["SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026"][
        "per_season"
    ]
    for season in ("2021", "2022", "2023"):
        assert per_season[season]["difference"] == 0, season
        assert per_season[season]["in_candidate_only"] == []
        assert per_season[season]["in_derived_only"] == []

    assert per_season["2024"]["difference"] == -1
    assert per_season["2024"]["in_derived_only"] == ["Kennesaw State Owls"]

    # 2025 is where it parts company with football entirely.
    assert per_season["2025"]["difference"] == 7
    assert "Harvard" in per_season["2025"]["in_candidate_only"]


def test_the_candidate_alias_table_only_ever_compares_claims():
    """It must not be able to touch a corpus row."""
    source = (
        REPO_ROOT
        / "src"
        / "ncaaf_engine"
        / "simulation"
        / "dynamic_weekly_mc_v3"
        / "historical_bridge.py"
    ).read_text(encoding="utf-8")
    admission = source[source.index("def build_bridge_games") : source.index("# ---", source.index("def build_bridge_games"))]
    assert "CANDIDATE_NAME_ALIASES" not in admission
    assert "_candidate_keys" not in admission


# --------------------------------------------------------------------------
# The 2025 opening-state join test
# --------------------------------------------------------------------------


def test_no_2025_family_supplies_an_admissible_preseason_opening_state():
    join = _json("V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST.json")
    assert join["families_valid_for_a_join"] == []
    assert join["week_1_2_games_with_valid_opening_state_both_sides"] == 0
    assert join["disposition"] == "NO_ADMISSIBLE_2025_PRESEASON_OPENING_STATE"


def test_the_only_2025_preseason_state_found_has_no_dispersion():
    join = _json("V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST.json")
    assert join["families_with_a_preseason_2025_source"] == ["TRUESKILL"]
    assert join["trueskill_opening_distinct_values"] == 1
    assert join["trueskill_opening_standard_deviation"] == 0.0


def test_the_component_universe_shares_no_game_with_the_real_2025_season():
    overlap = _json("V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST.json")[
        "component_universe_overlap"
    ]
    assert overlap["component_universe_games"] == 757
    assert overlap["matched_on_pair_and_date"] == 0
    assert overlap["matched_on_pair_only"] == 0
    assert overlap["universe_joins_real_season"] is False


def test_coverage_and_validity_are_reported_as_different_facts():
    join = _json("V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST.json")
    assert join["week_1_2_games_with_component_coverage_both_sides"] > 0
    assert join["week_1_2_games_with_valid_opening_state_both_sides"] == 0


def test_the_component_extract_is_bound_to_the_synthetic_ledger_it_came_from():
    extract = json.loads(
        (
            BRIDGE / "mounted" / "V3_BRIDGE_2025_OPENING_COMPONENT_EXTRACT.json"
        ).read_text(encoding="utf-8")
    )
    trueskill = extract["families"]["TRUESKILL"]
    assert trueskill["ledger_digest_matches"] is True
    assert trueskill["declared_games_processed"] == "757"
    assert extract["artifact_class"].endswith("NOT_A_RATING_SOURCE")


# --------------------------------------------------------------------------
# 2020 backcast feasibility
# --------------------------------------------------------------------------


def test_a_2020_terminal_state_is_computable_and_is_a_witness_only():
    backcast = _json("V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json")
    assert backcast["srs_terminal_state_computable"] is True
    assert backcast["historical_metadata_required_and_absent"] == []
    assert backcast["srs_values_emitted"] is False
    assert backcast["disposition"] == "TERMINAL_STATE_COMPUTABLE_AS_WITNESS_ONLY"
    assert "SRS_CANONICAL_VALIDATION_ANCHORS_NOT_MOUNTED" in backcast["srs_governance"]


def test_the_governed_v3_rating_path_cannot_run_on_any_amount_of_2020_results():
    backcast = _json("V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json")
    assert backcast["v3_governed_rerating_runnable"] is False
    assert len(backcast["v3_governed_rerating_obstacles"]) == 3
    with pytest.raises(GovernanceBlock):
        srs.require_canonical_validated_srs()


def test_no_same_season_preseason_state_is_derived_from_2020_final():
    backcast = _json("V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json")
    assert backcast["same_season_preseason_derivation_attempted"] is False


def test_the_2020_schedule_graph_connects_only_through_the_postseason():
    """The tier-1 feed carries no postseason game, so tier 1 alone cannot do this."""
    backcast = _json("V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json")
    assert backcast["schedule_graph_components"] == 1
    assert backcast["regular_season_only_components"] == 4
    assert backcast["postseason_required_for_connectivity"] is True


def test_the_srs_feed_is_two_sided():
    """Regression: a one-sided feed is singular on a graph reported connected."""
    backcast = _json("V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json")
    assert backcast["srs_rows_supplied"] == 2 * backcast["same_division_games_used"]

    one_sided = [
        srs.SrsGame("g1", "A", "B", 10.0),
        srs.SrsGame("g2", "B", "C", 3.0),
        srs.SrsGame("g3", "C", "A", 7.0),
    ]
    two_sided = [
        row
        for game in one_sided
        for row in (
            game,
            srs.SrsGame(game.game_id, game.opponent, game.team, -game.margin),
        )
    ]
    # The one-sided feed solves, which is why it is dangerous: it returns a
    # plausible ordering computed over half the appearances.
    assert srs.compute_srs(one_sided) != srs.compute_srs(two_sided)


# --------------------------------------------------------------------------
# Determinism, and the lane's standing commitments
# --------------------------------------------------------------------------


def test_the_build_reproduces_every_artifact_byte_for_byte(tmp_path):
    import hashlib
    import importlib.util

    before = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(BRIDGE.glob("V3_BRIDGE_*"))
        if path.is_file()
    }
    spec = importlib.util.spec_from_file_location(
        "build_historical_bridge_r1",
        REPO_ROOT / "scripts" / "build_historical_bridge_r1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.main() == 0

    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(BRIDGE.glob("V3_BRIDGE_*"))
        if path.is_file()
    }
    assert after == before


def test_no_artifact_carries_a_generation_timestamp():
    """A timestamp inside the bytes would defeat the byte-identity requirement."""
    for path in sorted(BRIDGE.glob("V3_BRIDGE_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert "generated_at" not in payload, path.name


def test_the_status_record_promotes_nothing():
    status = _json("V3_BRIDGE_STATUS_R1.json")
    assert status["ratings_emitted"] is False
    assert status["parameters_promoted"] == 0
    assert status["blockers_retired"] == 0
    assert status["governed_allowlist_widened"] is False
    assert status["canonical_config_written"] is False
    assert status["safe_for_2025_stage0"] is False


def test_the_calibration_values_are_still_null():
    config = json.loads(
        (REPO_ROOT / "config" / "dynamic_weekly_mc_v3" / "v3_experimental.json").read_text(encoding="utf-8")
    )
    calibration = config.get("calibration", config)
    assert all(
        value is None
        for key, value in calibration.items()
        if isinstance(value, (int, float, type(None)))
    )
