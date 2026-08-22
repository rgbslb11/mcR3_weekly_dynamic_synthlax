"""Tests for the V3 historical venue/competition enrichment (R7 lane).

Two kinds of test live here and they are doing different jobs.

The synthetic tests build ``NcaaGame`` and ``EspnEvent`` values by hand and drive
the classifier and the matcher directly. They exist to pin behaviour that the
real 2021-2024 data happens not to exercise - an orientation disagreement
between the two sources, a designated home team at a neutral site, an FCS team
hosting an FBS team - because "the current data does not contain this" is not
the same as "the code handles this", and the second is what a later reader needs
to be able to rely on.

The corpus tests run the real build over the bytes in custody. They are fast (a
build is about a second) and they are the ones that would notice if a raw file
were replaced, a digest drifted, or the enrichment stopped being reproducible.

Nothing here reaches the network. Retrieval is a separate script and its output
is committed; a test that needed a live feed would be testing ESPN's uptime.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.venue_enrichment import (
    ENRICHMENT_COLUMNS,
    ESPN_AUTHORITY_TIER,
    GAME_TYPES,
    NCAA_AUTHORITY_TIER,
    SUBJECT_VENUES,
    EnrichmentRow,
    EspnEvent,
    NcaaGame,
    VenueEnrichmentError,
    build_venue_enrichment,
    classify_game_type,
    conflict_report,
    corpus_join_report,
    coverage_report,
    load_acquisition_manifest,
    match_games,
    render_enrichment_csv,
    team_identity_map,
    venue_hfa_disposition,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
LANE_ROOT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "venue_enrichment_r1"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def enrichment():
    return build_venue_enrichment(REPO_ROOT)


@pytest.fixture(scope="module")
def rows(enrichment):
    return enrichment.rows


@pytest.fixture(scope="module")
def coverage(rows):
    return coverage_report(rows)


def _ncaa(
    game_id: str = "NCAA-2021-1",
    *,
    home_seo: str = "alpha",
    away_seo: str = "beta",
    home_score: int = 24,
    away_score: int = 17,
    epoch: int = 1630170000,
    start_date: str = "08-28-2021",
    start_time: str = "01:00PM ET",
) -> NcaaGame:
    return NcaaGame(
        game_id=game_id,
        season=2021,
        week=1,
        division_feed="fbs",
        source_game_id=game_id.rsplit("-", 1)[-1],
        home_char6=home_seo.upper()[:6],
        home_seo=home_seo,
        home_short=home_seo.title(),
        home_score=home_score,
        away_char6=away_seo.upper()[:6],
        away_seo=away_seo,
        away_short=away_seo.title(),
        away_score=away_score,
        start_epoch=epoch,
        start_date_raw=start_date,
        start_time_raw=start_time,
        source_locator="https://data.ncaa.com/ncaa-week",
    )


def _espn(
    event_id: str = "E1",
    *,
    home_team_id: str = "100",
    away_team_id: str = "200",
    home_score: int = 24,
    away_score: int = 17,
    neutral: bool | None = False,
    season_slug: str = "regular-season",
    competition_type: str = "STD",
    notes: tuple[str, ...] = (),
    kickoff: str = "2021-08-28T17:00Z",
    venue_name: str = "Test Field",
) -> EspnEvent:
    return EspnEvent(
        event_id=event_id,
        season=2021,
        season_slug=season_slug,
        competition_type=competition_type,
        neutral_site=neutral,
        venue_name=venue_name,
        venue_city="Testville",
        venue_state="TS",
        home_team_id=home_team_id,
        home_score=home_score,
        away_team_id=away_team_id,
        away_score=away_score,
        notes=notes,
        kickoff_utc=datetime.strptime(kickoff, "%Y-%m-%dT%H:%MZ").replace(
            tzinfo=timezone.utc
        ),
        source_locator="https://site.web.api.espn.com/espn-week",
    )


def _row_for(games, events) -> EnrichmentRow:
    """Run the real build path over a hand-built pair and return the row."""
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import venue_enrichment as module

    state, alias, _ = module._match_games(games, events)
    game = games[0]
    bound = state.bound.get(game.game_id)
    status = (
        "MATCHED_EXACT"
        if bound is not None
        else state.refused.get(game.game_id, "UNMATCHED")
    )
    membership = {"2021": {game.home_seo: "FBS", game.away_seo: "FBS"}}
    return module._build_row(
        game,
        bound,
        state.method.get(game.game_id, ""),
        status,
        alias,
        membership,
    )


# ---------------------------------------------------------------------------
# deterministic source matching
# ---------------------------------------------------------------------------


def test_matching_is_deterministic_across_input_orderings():
    """The same games and events match the same way whatever order they arrive in.

    A matcher that depends on iteration order produces a different enrichment
    every time the source files are re-read, which would make every digest
    recorded against it meaningless.
    """
    games = [_ncaa(f"NCAA-2021-{i}", home_seo=f"h{i}", away_seo=f"a{i}",
                   home_score=20 + i, away_score=10 + i) for i in range(1, 8)]
    events = [
        _espn(f"E{i}", home_team_id=f"1{i}", away_team_id=f"2{i}",
              home_score=20 + i, away_score=10 + i)
        for i in range(1, 8)
    ]
    forward = match_games(games, events)["outcomes"]
    backward = match_games(list(reversed(games)), list(reversed(events)))["outcomes"]
    assert forward == backward


def test_match_binds_on_identity_without_consulting_score():
    """A score disagreement must not stop two sources naming the same game.

    This is the Oklahoma State / TCU case from 2021: the NCAA feed records one
    score and ESPN records another. Binding on identity keeps the game and
    reports the disagreement; binding on score would have silently dropped it.
    """
    game = _ncaa(home_score=63, away_score=16)
    bootstrap_game = _ncaa("NCAA-2021-9", home_seo="alpha", away_seo="beta",
                           home_score=31, away_score=7, epoch=1630170000 + 604800,
                           start_date="09-04-2021")
    bootstrap_event = _espn("E9", home_score=31, away_score=7,
                            kickoff="2021-09-04T17:00Z")
    event = _espn("E1", home_score=63, away_score=17)

    outcomes = match_games([bootstrap_game, game], [bootstrap_event, event])["outcomes"]
    assert outcomes[game.game_id]["match_status"] == "MATCHED_EXACT"
    assert outcomes[game.game_id]["match_method"] == "IDENTITY_DATE"


def test_unmatched_game_is_reported_not_dropped():
    game = _ncaa()
    outcomes = match_games([game], [])["outcomes"]
    assert outcomes[game.game_id]["match_status"] == "UNMATCHED"
    assert outcomes[game.game_id]["espn_event_id"] == ""


# ---------------------------------------------------------------------------
# multiple-match refusal and ambiguous source identity
# ---------------------------------------------------------------------------


def test_two_candidate_events_are_refused_not_chosen():
    """Two events that fit equally well produce a refusal, never a pick."""
    game = _ncaa(home_seo="alpha", away_seo="beta", home_score=21, away_score=14)
    twin_a = _espn("E1", home_team_id="100", away_team_id="200",
                   home_score=21, away_score=14)
    twin_b = _espn("E2", home_team_id="300", away_team_id="400",
                   home_score=21, away_score=14)
    outcomes = match_games([game], [twin_a, twin_b])["outcomes"]
    assert outcomes[game.game_id]["match_status"] == "MULTIPLE_MATCH_REFUSED"
    assert outcomes[game.game_id]["espn_event_id"] == ""


def test_duplicated_source_slot_refuses_both_rows():
    """Two NCAA rows for one game bind to neither, rather than to whichever sorts first."""
    first = _ncaa("NCAA-2021-1")
    second = _ncaa("NCAA-2021-2")
    event = _espn("E1")
    outcomes = match_games([first, second], [event])["outcomes"]
    assert outcomes[first.game_id]["match_status"] == "AMBIGUOUS_SOURCE_IDENTITY"
    assert outcomes[second.game_id]["match_status"] == "AMBIGUOUS_SOURCE_IDENTITY"


def test_ambiguous_team_identity_is_dropped_not_majority_voted():
    votes = {"clean": {"100": 4}, "contested": {"100": 9, "200": 1}}
    resolved = team_identity_map(votes)
    assert resolved == {"clean": "100"}
    assert "contested" not in resolved


# ---------------------------------------------------------------------------
# venue classification
# ---------------------------------------------------------------------------


def test_neutral_site_classifies_as_neutral_for_the_subject():
    row = _row_for([_ncaa()], [_espn(neutral=True, venue_name="Mercedes-Benz Stadium")])
    assert row["venue_classification"] == "NEUTRAL_SITE"
    assert row["subject_venue"] == "NEUTRAL_SITE"
    assert row["venue_name"] == "Mercedes-Benz Stadium"
    assert row["calibration_usability"] == "EXPECTED_MARGIN_VENUE_READY"


def test_designated_home_at_a_neutral_site_is_not_home_field():
    """The distinction the whole lane exists for.

    The NCAA feed still names a home participant for a neutral-site game. That
    designation must not become home field, because the governed HFA would then
    be applied to a team that did not have one.
    """
    row = _row_for([_ncaa()], [_espn(neutral=True)])
    assert row["source_orientation"] == "NCAA_DESIGNATED_HOME_IS_SUBJECT"
    assert row["subject_venue"] != "HOME_FIELD"
    assert row["subject_venue"] == "NEUTRAL_SITE"
    assert venue_hfa_disposition(row["subject_venue"]) == "NO_HFA_APPLIES"


def test_true_home_is_classified_only_when_both_sources_agree():
    row = _row_for([_ncaa()], [_espn(neutral=False)])
    assert row["subject_venue"] == "HOME_FIELD"
    assert row["orientation_cross_source"] == "AGREED"
    assert row["conflict_status"] == "NO_CONFLICT"
    assert venue_hfa_disposition(row["subject_venue"]) == "SUBJECT_RECEIVES_HFA"


def test_absent_venue_evidence_yields_unresolved_not_home_field():
    """No designated-home-implies-home-field inference anywhere.

    With no ESPN counterpart there is no venue evidence at all, and the row must
    say so rather than fall back on the home/away designation.
    """
    row = _row_for([_ncaa()], [])
    assert row["match_status"] == "UNMATCHED"
    assert row["evidence_status"] == "VENUE_EVIDENCE_ABSENT"
    assert row["subject_venue"] == "VENUE_UNRESOLVED"
    assert row["neutral_site_flag"] == ""
    assert row["calibration_usability"] == "EXPECTED_MARGIN_VENUE_UNRESOLVED"
    assert venue_hfa_disposition(row["subject_venue"]) == "HFA_NOT_DETERMINABLE"


def test_fcs_home_orientation_survives_into_the_row():
    """An FCS team hosting an FBS team is home field for the FCS subject.

    Division is carried alongside venue precisely so this case is reportable
    rather than being flattened into "an FBS game".
    """
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import venue_enrichment as module

    game = _ncaa(home_seo="fcs-host", away_seo="fbs-visitor")
    event = _espn(neutral=False, home_team_id="100", away_team_id="200")
    state, alias, _ = module._match_games([game], [event])
    membership = {"2021": {"fcs-host": "FCS", "fbs-visitor": "FBS"}}
    row = module._build_row(
        game, state.bound.get(game.game_id), state.method.get(game.game_id, ""),
        "MATCHED_EXACT", alias, membership,
    )
    assert row["subject_division"] == "FCS"
    assert row["opponent_division"] == "FBS"
    assert row["division_matchup"] == "FBS_VS_FCS"
    assert row["subject_venue"] == "HOME_FIELD"


def test_orientation_disagreement_is_a_conflict_not_a_choice():
    """When the sources disagree on who hosted, neither is preferred.

    ESPN puts the NCAA-designated away team in the home slot. The venue fact
    (not neutral) survives; the subject-level fact does not, and the row is not
    usable for expected-margin calibration.
    """
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import venue_enrichment as module

    game = _ncaa(home_seo="alpha", away_seo="beta", home_score=24, away_score=17)
    event = _espn(neutral=False, home_team_id="200", away_team_id="100",
                  home_score=17, away_score=24)
    alias = {"alpha": "100", "beta": "200"}
    membership = {"2021": {"alpha": "FBS", "beta": "FBS"}}
    row = module._build_row(game, event, "IDENTITY_DATE", "MATCHED_EXACT", alias, membership)

    assert row["orientation_cross_source"] == "DISAGREED"
    assert "SOURCE_CONFLICT_ORIENTATION" in row["conflict_status"]
    assert row["subject_venue"] == "VENUE_UNRESOLVED"
    assert row["venue_classification"] == "HOME_AWAY_SITE"
    assert row["calibration_usability"] == "EXPECTED_MARGIN_VENUE_UNRESOLVED"


# ---------------------------------------------------------------------------
# source-conflict preservation
# ---------------------------------------------------------------------------


def test_kickoff_conflict_preserves_both_instants_and_reconciles_neither():
    row = _row_for([_ncaa(epoch=1630170000)], [_espn(kickoff="2021-08-28T18:00Z")])
    assert "SOURCE_CONFLICT_KICKOFF" in row["conflict_status"]
    assert row["kickoff_utc_ncaa"] == "2021-08-28T17:00:00+00:00"
    assert row["kickoff_utc_espn"] == "2021-08-28T18:00:00+00:00"
    assert row["kickoff_utc"] == ""


def test_score_conflict_is_recorded_without_editing_either_source():
    """Bound on identity, so the score disagreement is reported rather than fatal."""
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import venue_enrichment as module

    game = _ncaa(home_score=63, away_score=16)
    event = _espn(home_score=63, away_score=17)
    row = module._build_row(
        game,
        event,
        "IDENTITY_DATE",
        "MATCHED_EXACT",
        {"alpha": "100", "beta": "200"},
        {"2021": {"alpha": "FBS", "beta": "FBS"}},
    )
    assert "SOURCE_CONFLICT_SCORE" in row["conflict_status"]
    assert row["kickoff_utc_ncaa"] and row["kickoff_utc_espn"]
    # A score conflict says nothing about venue, so it must not block usability.
    assert row["subject_venue"] == "HOME_FIELD"
    assert row["calibration_usability"] == "EXPECTED_MARGIN_VENUE_READY"


def test_conflict_report_preserves_both_evidence_records(rows):
    report = conflict_report(rows)
    assert report["conflict_count"] > 0
    for record in report["records"]:
        assert record["resolution"] == "BOTH_PRESERVED_NEITHER_SELECTED"
        assert record["ncaa_evidence"]["source_authority_tier"] == NCAA_AUTHORITY_TIER
        assert record["espn_evidence"]["source_authority_tier"] == ESPN_AUTHORITY_TIER


# ---------------------------------------------------------------------------
# game type
# ---------------------------------------------------------------------------


def test_conference_championship_is_read_from_the_contest_name():
    event = _espn(notes=("SEC Championship Game",), season_slug="regular-season")
    game_type, evidence = classify_game_type(event)
    assert game_type == "CONFERENCE_CHAMPIONSHIP"
    assert "SEC Championship Game" in evidence


def test_bowl_and_playoff_are_read_from_the_postseason_contest_name():
    bowl = _espn(season_slug="post-season", notes=("Valero Alamo Bowl",))
    playoff = _espn(
        season_slug="post-season",
        notes=("College Football Playoff Semifinal",),
    )
    assert classify_game_type(bowl)[0] == "BOWL"
    assert classify_game_type(playoff)[0] == "PLAYOFF"


def test_unmatched_game_type_is_unknown_not_guessed():
    assert classify_game_type(None) == ("UNKNOWN_GAME_TYPE", "")


def test_game_type_never_consults_a_week_number():
    """Two games in the same source week classify differently on contest name alone."""
    plain = _espn("E1", season_slug="regular-season")
    titled = _espn("E2", season_slug="regular-season", notes=("MAC Championship",))
    assert classify_game_type(plain)[0] == "REGULAR_SEASON"
    assert classify_game_type(titled)[0] == "CONFERENCE_CHAMPIONSHIP"


# ---------------------------------------------------------------------------
# no invented timestamps
# ---------------------------------------------------------------------------


def test_completion_and_observability_are_never_invented(rows):
    """Neither source carries them, so neither column may carry anything."""
    assert all(row["completion_utc"] == "" for row in rows)
    assert all(row["observability_utc"] == "" for row in rows)
    coverage = coverage_report(rows)
    assert coverage["completion_timestamp_count"] == 0
    assert coverage["observability_timestamp_count"] == 0


def test_a_known_date_with_an_unknown_time_records_only_the_date():
    row = _row_for([_ncaa(start_time="")], [_espn()])
    assert row["kickoff_local"] == "2021-08-28"
    assert "T" not in row["kickoff_local"]
    assert row["kickoff_local_timezone"] == ""


def test_local_kickoff_is_the_sources_own_wall_clock():
    row = _row_for([_ncaa(start_time="01:00PM ET")], [_espn()])
    assert row["kickoff_local"] == "2021-08-28T13:00:00"
    assert row["kickoff_local_timezone"] == "America/New_York"


# ---------------------------------------------------------------------------
# deterministic output and join uniqueness
# ---------------------------------------------------------------------------


def test_enrichment_output_is_byte_identical_across_rebuilds():
    first = render_enrichment_csv(build_venue_enrichment(REPO_ROOT).rows)
    second = render_enrichment_csv(build_venue_enrichment(REPO_ROOT).rows)
    assert first == second


def test_committed_enrichment_matches_a_fresh_build(rows):
    committed = (LANE_ROOT / "V3_VENUE_R1_ENRICHMENT.csv").read_bytes()
    assert committed == render_enrichment_csv(rows)


def test_registration_receipt_digest_matches_the_committed_table():
    receipt = json.loads(
        (LANE_ROOT / "V3_VENUE_R1_REGISTRATION_RECEIPT.json").read_text(encoding="utf-8")
    )
    import hashlib

    committed = (LANE_ROOT / "V3_VENUE_R1_ENRICHMENT.csv").read_bytes()
    assert receipt["enrichment_sha256"] == hashlib.sha256(committed).hexdigest()
    assert receipt["enrichment_byte_length"] == len(committed)
    assert receipt["parameters_promoted"] == []
    assert receipt["blockers_retired"] == []
    assert receipt["monte_carlo_executed"] is False


def test_every_row_binds_to_exactly_one_game_and_one_event(rows):
    game_ids = [row["game_id"] for row in rows]
    assert len(game_ids) == len(set(game_ids))
    event_ids = [row["espn_event_id"] for row in rows if row["espn_event_id"]]
    assert len(event_ids) == len(set(event_ids))


def test_enrichment_csv_has_the_declared_columns_and_lf_endings(rows):
    data = render_enrichment_csv(rows)
    assert b"\r\n" not in data
    reader = csv.reader(io.StringIO(data.decode("utf-8"), newline=""))
    header = next(reader)
    assert tuple(header) == ENRICHMENT_COLUMNS
    assert len(list(reader)) == len(rows)


def test_every_row_uses_the_declared_vocabularies(rows):
    for row in rows:
        assert row["subject_venue"] in SUBJECT_VENUES
        assert row["game_type"] in GAME_TYPES
        assert row["calibration_usability"] in {
            "EXPECTED_MARGIN_VENUE_READY",
            "EXPECTED_MARGIN_VENUE_UNRESOLVED",
        }


# ---------------------------------------------------------------------------
# usability semantics
# ---------------------------------------------------------------------------


def test_usability_tracks_venue_resolution_exactly(rows, coverage):
    ready = {
        row["game_id"]
        for row in rows
        if row["calibration_usability"] == "EXPECTED_MARGIN_VENUE_READY"
    }
    resolved = {
        row["game_id"] for row in rows if row["subject_venue"] != "VENUE_UNRESOLVED"
    }
    assert ready == resolved
    assert coverage["expected_margin_venue_ready"] == coverage["venue_resolved_count"]


def test_hfa_disposition_never_returns_a_number():
    for venue in SUBJECT_VENUES:
        disposition = venue_hfa_disposition(venue)
        assert isinstance(disposition, str)
        assert not any(character.isdigit() for character in disposition)
    assert venue_hfa_disposition("NEUTRAL_SITE") == "NO_HFA_APPLIES"
    assert venue_hfa_disposition("VENUE_UNRESOLVED") == "HFA_NOT_DETERMINABLE"


# ---------------------------------------------------------------------------
# custody
# ---------------------------------------------------------------------------


def test_raw_custody_is_reverified_from_bytes(enrichment):
    assert enrichment.custody["bytes_reverified"] is True
    assert enrichment.custody["sources_verified"] > 0
    assert set(enrichment.custody["authorities"]) == {
        "ESPN_COLLEGE_FOOTBALL_SCOREBOARD",
        "NCAA_OFFICIAL_SCOREBOARD_FEED",
    }


def test_a_tampered_digest_is_refused_at_read():
    sources = load_acquisition_manifest(
        LANE_ROOT / "V3_VENUE_R1_SOURCE_ACQUISITION_MANIFEST.json"
    )
    from dataclasses import replace

    tampered = replace(sources[0], decompressed_sha256="00" * 32)
    with pytest.raises(VenueEnrichmentError, match="digest mismatch"):
        tampered.read(REPO_ROOT)


def test_a_missing_raw_file_is_refused_at_read():
    sources = load_acquisition_manifest(
        LANE_ROOT / "V3_VENUE_R1_SOURCE_ACQUISITION_MANIFEST.json"
    )
    from dataclasses import replace

    absent = replace(sources[0], raw_path="reference/does/not/exist.json.gz")
    with pytest.raises(VenueEnrichmentError, match="missing from custody"):
        absent.read(REPO_ROOT)


# ---------------------------------------------------------------------------
# the real corpus universe
# ---------------------------------------------------------------------------


def test_the_real_universe_resolves_venue_for_almost_every_game(coverage):
    assert coverage["games_considered"] == 3454
    assert coverage["venue_resolved_count"] == 3416
    assert coverage["venue_unresolved_count"] == 38
    assert coverage["neutral_count"] == 82
    assert coverage["home_field_count"] == 3334


def test_every_conference_championship_is_found_and_resolved(coverage):
    """All 39 across four seasons, and not all of them are neutral.

    The count is pinned because a silent drop would look like a clean result.
    The neutral split is pinned because assuming every conference championship
    is played at a neutral site is exactly the mistake available here: sixteen
    of these were hosted on a participant's own field.
    """
    assert coverage["conference_championship_count"] == 39
    assert coverage["conference_championship_venue_resolved"] == 39
    assert coverage["conference_championship_neutral"] == 23
    assert coverage["conference_championship_home_field"] == 16


def test_no_postseason_game_is_claimed_from_a_feed_that_carries_none(coverage):
    """The NCAA scoreboard carries no bowls or playoff games, so neither may appear."""
    assert coverage["bowl_count"] == 0
    assert coverage["playoff_count"] == 0
    assert coverage["game_type_breakdown"].get("OTHER_POSTSEASON", 0) == 0


def test_the_two_sources_never_disagree_about_who_hosted(coverage):
    """A tier-1 and a tier-5 source agreeing on orientation everywhere is a result.

    It is also the check that would catch the matcher binding games to the wrong
    events: a mis-binding would show up here as orientation noise long before it
    showed up as a wrong venue.
    """
    assert coverage["orientation_cross_source_disagreements"] == 0


def test_unresolved_rows_are_exactly_the_unmatched_ones(rows):
    unresolved = {
        row["game_id"] for row in rows if row["subject_venue"] == "VENUE_UNRESOLVED"
    }
    unmatched = {row["game_id"] for row in rows if row["match_status"] != "MATCHED_EXACT"}
    assert unresolved == unmatched


def test_corpus_join_is_one_to_one_and_complete(rows):
    """Every admitted corpus observation gets a venue answer.

    The corpus is read from the committed join report rather than from its own
    branch, so this test does not depend on another lane being fetched. The
    digest recorded there is what ties the numbers to a specific corpus.
    """
    report_path = LANE_ROOT / "V3_VENUE_R1_CORPUS_JOIN_REPORT.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["corpus_rows"] == 2241
    assert report["joined_rows"] == 2241
    assert report["corpus_rows_not_enriched"] == 0
    assert report["join_is_one_to_one"] is True
    # Both artifacts derive the instant from the same NCAA bytes.
    assert report["kickoff_identity_agreements"] == report["kickoff_identity_checked"]
    assert report["coverage"]["venue_resolved_count"] == 2241
    assert report["coverage"]["expected_margin_venue_ready"] == 2241


def test_the_corpus_identified_fbs_vs_fcs_games_are_all_resolved():
    report = json.loads(
        (LANE_ROOT / "V3_VENUE_R1_CORPUS_JOIN_REPORT.json").read_text(encoding="utf-8")
    )
    inventory = report["corpus_identified_fbs_vs_fcs"]
    assert inventory["inventory_count"] == 43
    assert inventory["venue_resolved_count"] == 43
    assert inventory["venue_unresolved_count"] == 0
    assert inventory["fbs_home_vs_fcs"] == 43
    assert inventory["fcs_home_vs_fbs"] == 0
    assert inventory["neutral_fbs_vs_fcs"] == 0
    assert inventory["fcs_point_scale_estimated"] is False


def test_corpus_join_refuses_to_invent_coverage_for_an_unknown_corpus(rows):
    """A corpus row this enrichment has no game for is reported, not skipped."""
    corpus = (
        "game_id,season,week,event_time,team,opponent,actual_margin,game_result,"
        "source_provenance,recorded_at,split\n"
        "NCAA-2021-000000,2021,1,2021-08-28T17:00:00+00:00,AAA,BBB,7,W,x,y,training\n"
    ).encode("utf-8")
    report = corpus_join_report(rows, corpus)
    assert report["corpus_rows"] == 1
    assert report["joined_rows"] == 0
    assert report["corpus_rows_not_enriched"] == 1
    assert report["corpus_rows_not_enriched_sample"] == ["NCAA-2021-000000"]
