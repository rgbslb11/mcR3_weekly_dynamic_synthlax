"""R6 governed historical observation corpus.

Two kinds of test live here and they answer different questions.

The *committed-corpus* tests read the artifacts actually in the repository and
assert the properties an auditor would check: the raw bytes still hash to what
the manifest says, every raw row is either admitted or refused with a reason,
game identity is unique, the split is temporal, and regenerating the corpus
reproduces the committed bytes exactly.

The *fabricated-source* tests build a tiny NCAA-shaped feed in a temp directory
so each refusal can be triggered on purpose. A gate that only ever fires on real
data is a gate nobody has aimed at; these aim at each one individually and check
it refuses for the stated reason rather than for some incidental reason that
happens to reach the same verdict.

Nothing here fits a parameter, and one test exists specifically to confirm that
the corpus is still refused by ``calibration.register_dataset``. That refusal is
the boundary this lane is built around: an observation corpus that quietly
became registerable as calibration data would be the exact failure the whole
evidence contract is written to prevent.
"""

from __future__ import annotations

import csv
import gzip
import io
import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import observation_corpus as oc
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "observation_corpus_r6"
ACQUISITION_MANIFEST = CORPUS_DIR / "V3_R6_SOURCE_ACQUISITION_MANIFEST.json"
CORPUS_CSV = CORPUS_DIR / "V3_R6_OBSERVATION_CORPUS.csv"
AUTHORITY_PATH = (
    REPO_ROOT
    / "reference"
    / "dynamic_weekly_mc_v3"
    / "inputs"
    / "2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md"
)


# --------------------------------------------------------------------------
# committed corpus
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def records():
    return oc.load_acquisition_manifest(ACQUISITION_MANIFEST)


@pytest.fixture(scope="module")
def authority():
    return oc.load_canonical_identity_authority(AUTHORITY_PATH)


@pytest.fixture(scope="module")
def build(records, authority):
    return oc.build_observation_corpus(records, authority, REPO_ROOT)


def test_raw_source_byte_custody_reverifies(records):
    """Every captured file still hashes to both registered digests."""
    report = oc.verify_raw_custody(records, REPO_ROOT)
    assert report["bytes_reverified"] is True
    assert report["sources_verified"] == len(records) > 0
    assert report["source_authority_classes"] == ["GOVERNED_RESULT_SOURCE"]
    assert report["source_authorities"] == ["NCAA_OFFICIAL_SCOREBOARD_FEED"]


def test_every_source_declares_a_tier_one_authority(records):
    for record in records:
        assert record.source_authority_class == "GOVERNED_RESULT_SOURCE"
        assert record.url.startswith("https://data.ncaa.com/casablanca/")
        assert record.retrieved_at.endswith("+00:00")


def test_counts_reconcile_raw_equals_admitted_plus_excluded(build):
    assert build.reconciles()
    assert build.raw_row_count == len(build.rows) + len(build.exclusions)
    assert len(build.rows) > 0
    assert len(build.exclusions) > 0


def test_every_exclusion_carries_a_declared_reason_code(build):
    for excluded in build.exclusions:
        assert excluded["reason"] in oc.EXCLUSION_REASONS
        assert excluded["detail"]


def test_corpus_columns_are_a_subset_of_the_governed_allowlist(build):
    allowlist = {c.lower() for c in calibration.CALIBRATION_OBSERVATION_COLUMNS}
    assert set(c.lower() for c in oc.CORPUS_COLUMNS) <= allowlist
    # The lane widens nothing: the corpus is strictly smaller than the allowlist.
    assert set(oc.CORPUS_COLUMNS) != allowlist


def test_game_identity_is_unique_across_the_corpus(build):
    game_ids = [row.game_id for row in build.rows]
    assert len(game_ids) == len(set(game_ids))
    assert build.game_identity_report["duplicate_game_id_count"] == 0


def test_repeat_matchups_receive_distinct_game_ids(build):
    """The R5 failure: a team-pair key collides when two teams meet twice."""
    repeats = build.game_identity_report["repeat_matchups"]
    assert repeats, "the corpus must contain at least one repeat matchup to test"
    for entry in repeats:
        assert len(set(entry["game_ids"])) == len(entry["game_ids"]) > 1
        assert len(set(entry["weeks"])) == len(entry["weeks"])
        assert len(set(entry["event_times"])) == len(entry["event_times"])
        # A team-pair key would have collapsed these into one row.
        assert len(entry["pair"]) == 2


def test_every_observation_carries_a_start_instant(build):
    assert build.chronology_report["start_instant_absent"] == 0
    assert build.chronology_report["with_start_instant"] == len(build.rows)
    for row in build.rows:
        assert row.event_time.endswith("+00:00")


def test_no_team_plays_two_admitted_games_at_one_instant(build):
    """Chronology ambiguity: simultaneous games for one team cannot be ordered."""
    assert build.chronology_report["team_seasons_with_tied_instants"] == 0


def test_temporal_split_is_ordered_and_leak_free(build):
    split = oc.build_temporal_split(build.rows)
    assert split["leak_free"] is True
    assert split["assignment"] == "TEMPORAL_ONLY"
    assert split["random_assignment_permitted"] is False
    training_end = split["boundaries"]["training"][1]
    validation_start = split["boundaries"]["validation"][0]
    validation_end = split["boundaries"]["validation"][1]
    holdout_start = split["boundaries"]["holdout"][0]
    assert training_end < validation_start
    assert validation_end < holdout_start


def test_no_holdout_observation_predates_any_training_observation(build):
    """Future leakage: the holdout must sit entirely after the training data."""
    training = [r.event_time for r in build.rows if r.split == "training"]
    validation = [r.event_time for r in build.rows if r.split == "validation"]
    holdout = [r.event_time for r in build.rows if r.split == "holdout"]
    assert training and validation and holdout
    assert max(training) < min(validation)
    assert max(validation) < min(holdout)
    # And no season straddles a split boundary.
    for name, rows in (
        ("training", training),
        ("validation", validation),
        ("holdout", holdout),
    ):
        seasons = {r.season for r in build.rows if r.split == name}
        assert all(oc.SEASON_SPLIT_ASSIGNMENT[s] == name for s in seasons)


def test_split_digest_is_stable_across_recomputation(build):
    first = oc.build_temporal_split(build.rows)
    second = oc.build_temporal_split(list(reversed(build.rows)))
    assert first["split_digest"] == second["split_digest"]


def test_minimum_volume_floors_are_satisfied(build):
    volume = oc.volume_assessment(
        build.rows, build.source_report["team_season_coverage"]
    )
    assert volume["minimum_volume_satisfied"] is True
    assert volume["distinct_seasons"] >= 3
    assert volume["total_observations"] >= 1500
    assert volume["holdout_observations"] >= 300
    assert volume["min_weeks_per_team_per_season"] >= oc.MINIMUM_GAMES_PER_TEAM_SEASON


def test_regeneration_reproduces_the_committed_corpus_byte_for_byte(build):
    assert oc.render_corpus_csv(build.rows) == CORPUS_CSV.read_bytes()


def test_render_is_deterministic_under_input_reordering(build):
    assert oc.render_corpus_csv(build.rows) == oc.render_corpus_csv(
        list(reversed(build.rows))
    )


def test_corpus_file_uses_lf_newlines_only():
    data = CORPUS_CSV.read_bytes()
    assert b"\r\n" not in data
    assert b"\r" not in data


def test_registration_receipt_reverifies_bytes(build):
    receipt = oc.corpus_registration_receipt(CORPUS_CSV, build.rows)
    assert receipt["bytes_reverified_at_registration"] is True
    assert receipt["row_count"] == len(build.rows)
    assert receipt["columns"] == list(oc.CORPUS_COLUMNS)
    assert receipt["columns_within_governed_allowlist"] is True
    assert sorted(receipt["splits_present"]) == ["holdout", "training", "validation"]


def test_post_registration_mutation_is_refused(build, tmp_path):
    """A corpus edited after registration must fail, not re-register."""
    target = tmp_path / "corpus.csv"
    target.write_bytes(oc.render_corpus_csv(build.rows))
    oc.corpus_registration_receipt(target, build.rows)  # clean

    mutated = target.read_bytes().replace(b",training", b",holdout", 1)
    assert mutated != target.read_bytes()
    target.write_bytes(mutated)
    with pytest.raises(GovernanceBlock, match="does not match the corpus built"):
        oc.corpus_registration_receipt(target, build.rows)


def test_dataset_substitution_is_refused(build, tmp_path):
    """Swapping the file for a different conforming corpus must fail."""
    target = tmp_path / "corpus.csv"
    target.write_bytes(oc.render_corpus_csv(build.rows[:-1]))
    with pytest.raises(GovernanceBlock, match="does not match the corpus built"):
        oc.corpus_registration_receipt(target, build.rows)


def test_missing_corpus_is_refused(build, tmp_path):
    with pytest.raises(GovernanceBlock, match="there are none"):
        oc.corpus_registration_receipt(tmp_path / "absent.csv", build.rows)


def test_corpus_is_still_refused_as_a_calibration_dataset():
    """The boundary this lane exists to hold.

    The corpus is real, provenance-bound and split, and it is still not
    calibration data: ``expected_margin`` and ``observed_at`` are model output
    and an unavailable timestamp respectively. If this test ever passes by
    registering successfully, something has synthesised a model output and
    called it an observation.
    """
    with pytest.raises(GovernanceBlock) as excinfo:
        calibration.register_dataset(CORPUS_CSV, oc.CORPUS_ID)
    message = str(excinfo.value)
    assert "missing required observation columns" in message
    assert "expected_margin" in message
    assert "observed_at" in message


def test_blocked_fields_are_declared_and_not_emitted():
    blocked = {
        name
        for name, entry in oc.FIELD_CLASSIFICATION.items()
        if entry["class"] == "BLOCKED"
    }
    assert {"venue", "expected_margin", "pregame_team_rating", "observed_at"} <= blocked
    assert not blocked & set(oc.CORPUS_COLUMNS)


def test_non_governed_fields_stay_non_governed():
    """R5's four fields awaiting a ruling are reported, never admitted."""
    for name in ("games_played_to_date", "game_type", "overtime_periods", "opponent_division"):
        entry = oc.FIELD_CLASSIFICATION[name]
        assert entry["class"].startswith("NOT_GOVERNED")
        assert name not in oc.CORPUS_COLUMNS
        assert name not in calibration.CALIBRATION_OBSERVATION_COLUMNS


def test_overtime_is_observed_but_not_admitted(build):
    """The contract wanted overtime_periods. The source has it. It stays out."""
    assert build.source_report["overtime_games_staged"] > 0
    assert build.source_report["overtime_games_admitted"] > 0
    assert "overtime_periods" not in oc.CORPUS_COLUMNS


def test_fbs_versus_fcs_observations_are_inventoried_not_silently_dropped(build):
    inventory = build.fcs_inventory
    assert len(inventory) > 0
    excluded_cross = [
        e
        for e in build.exclusions
        if e["reason"] == "FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED"
    ]
    assert len(excluded_cross) == len(inventory)
    for entry in inventory:
        assert {entry["home_division"], entry["away_division"]} == {"FBS", "FCS"}
    # None of them reached the corpus.
    admitted_ids = {r.game_id for r in build.rows}
    for entry in inventory:
        assert f"NCAA-{entry['season']}-{entry['source_game_id']}" not in admitted_ids


def test_unresolved_teams_are_named_not_dropped(build):
    report = build.identity_report
    assert report["unresolved_entity_count"] > 0
    assert len(report["unresolved_entity_names"]) == report["unresolved_entity_count"]
    refused = [e for e in build.exclusions if e["reason"] == "UNRESOLVED_TEAM_IDENTITY"]
    assert refused
    for entry in refused:
        assert "not present in the 2026 canonical master" in entry["detail"]


def test_identity_authority_is_pinned_by_digest(authority, build):
    assert len(authority.sha256) == 64
    assert build.identity_report["canonical_authority_sha256"] == authority.sha256
    assert build.identity_report["canonical_entities"] == 134
    assert build.identity_report["canonical_fbs_members"] == 121


def test_canonical_division_is_never_reported_as_observed_division(build, authority):
    """The 2026 universe is synthetic; its labels are not football history.

    The canonical master classifies Arkansas State and Western Kentucky as
    schedule-only FCS and Colgate and Yale as FBS members. Those are facts about
    a synthetic 2026 season, not about 2021-2024 football, so observed division
    comes from the NCAA feed and the canonical label is never substituted for
    it. Both directions are checked, because a corpus that had silently used the
    canonical label would fail one of them.
    """
    note = build.identity_report["note"]
    assert "synthetic 2026 universe" in note
    assert "never reported as the observed division" in note
    in_corpus = {r.team for r in build.rows} | {r.opponent for r in build.rows}

    # Canonically labelled FCS, observed FBS, and therefore admitted.
    for schedule_id in ("ARST", "WKU", "ULL"):
        entity = authority.entities[schedule_id]
        assert entity.entity_scope == "SCHEDULE_ONLY_FCS"
        assert entity.canonical_division == "FCS"
        assert schedule_id in in_corpus

    # Canonically labelled FBS_MEMBER, observed FCS, and therefore excluded as
    # cross-division and inventoried instead.
    inventoried_fcs_side = {
        entry["opponent"] if entry["home_division"] == "FBS" else entry["team"]
        for entry in build.fcs_inventory
    }
    for schedule_id in ("COLG", "YALE", "NDSU"):
        assert authority.entities[schedule_id].entity_scope == "FBS_MEMBER"
        assert schedule_id not in in_corpus
        assert schedule_id in inventoried_fcs_side


def test_no_forbidden_signal_reaches_the_corpus():
    header = CORPUS_CSV.read_bytes().split(b"\n", 1)[0].decode("utf-8")
    columns = header.split(",")
    assert not calibration._forbidden_columns(columns)


def test_subsequent_outcomes_is_derivable_from_the_corpus(build):
    derived = oc.derive_subsequent_outcomes(build.rows[:200])
    assert derived
    for team, per_game in derived.items():
        ordered = sorted(per_game, key=lambda gid: len(per_game[gid]), reverse=True)
        # The first game of a team has the most forward references; the last has none.
        assert len(per_game[ordered[-1]]) == 0
        # Forward references never point at the game itself.
        for game_id, forward in per_game.items():
            assert game_id not in forward


# --------------------------------------------------------------------------
# fabricated sources: one gate at a time
# --------------------------------------------------------------------------

_TEAMS = [
    ("alabama", "Alabama", "ALA"),
    ("arkansas", "Arkansas", "ARK"),
    ("auburn", "Auburn", "AUB"),
    ("florida", "Florida", "FLA"),
    ("georgia", "Georgia", "UGA"),
    ("kentucky", "Kentucky", "UK"),
    ("lsu", "LSU", "LSU"),
    ("missouri", "Missouri", "MIZ"),
    ("tennessee", "Tennessee", "TENN"),
    ("texas", "Texas", "TEX"),
]


def _game(game_id, home, away, epoch, home_score=21, away_score=14, **overrides):
    def side(team, score):
        seo, short, char6 = team
        return {
            "score": str(score),
            "names": {"char6": char6, "short": short, "seo": seo, "full": short},
            "winner": False,
            "conferences": [{"conferenceName": "SEC", "conferenceSeo": "sec"}],
        }

    game = {
        "gameID": game_id,
        "home": side(home, home_score),
        "away": side(away, away_score),
        "gameState": "final",
        "finalMessage": "FINAL",
        "startDate": "09-04-2021",
        "startTime": "12:00PM ET",
        "startTimeEpoch": str(epoch),
        "contestName": "",
        "bracketRound": "",
        "title": "",
        "url": "",
    }
    game.update(overrides)
    return {"game": game}


def _write_feed(root: Path, season: int, division: str, week: int, games: list) -> dict:
    body = json.dumps(
        {"inputMD5Sum": "x", "instanceId": "y", "updated_at": "01-01-2022 00:00:00", "games": games}
    ).encode("utf-8")
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(body)
    container = buf.getvalue()
    rel = f"raw/{season}/{division}/wk{week:02d}.json.gz"
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(container)
    import hashlib

    return {
        "url": f"https://data.ncaa.com/casablanca/scoreboard/football/{division}/{season}/{week:02d}/scoreboard.json",
        "season": season,
        "division": division,
        "week": week,
        "stored_path": rel,
        "raw_sha256": hashlib.sha256(body).hexdigest(),
        "raw_byte_length": len(body),
        "stored_sha256": hashlib.sha256(container).hexdigest(),
        "stored_byte_length": len(container),
        "source_authority": "NCAA_OFFICIAL_SCOREBOARD_FEED",
        "source_authority_class": "GOVERNED_RESULT_SOURCE",
        "retrieval_method": "HTTP GET, urllib.request, no query parameters",
        "retrieved_at": "2026-08-22T00:00:00+00:00",
        "game_count": len(games),
    }


def _round_robin(season: int, base_epoch: int) -> list[dict]:
    """Nine weeks in which each of ten teams plays every other exactly once."""
    weeks = []
    rotation = _TEAMS[1:]
    fixed = _TEAMS[0]
    for week in range(1, 10):
        order = [fixed] + rotation[week - 1 :] + rotation[: week - 1]
        games = []
        for index in range(len(order) // 2):
            home = order[index]
            away = order[len(order) - 1 - index]
            games.append(
                _game(
                    f"{season}{week:02d}{index:02d}",
                    home,
                    away,
                    base_epoch + week * 604800 + index * 3600,
                )
            )
        weeks.append({"week": week, "games": games})
    return weeks


def _fabricate(tmp_path: Path, seasons=(2021, 2022, 2023), mutate=None) -> tuple:
    entries = []
    for offset, season in enumerate(seasons):
        base = 1630000000 + offset * 31_536_000
        for block in _round_robin(season, base):
            games = block["games"]
            if mutate is not None:
                games = mutate(season, block["week"], games)
            entries.append(_write_feed(tmp_path, season, "fbs", block["week"], games))
            entries.append(_write_feed(tmp_path, season, "fcs", block["week"], []))
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(
        (json.dumps({"captured_files": entries}, indent=2) + "\n").encode("utf-8")
    )
    return oc.load_acquisition_manifest(manifest), manifest


def _split_for(seasons):
    return {s: oc.SEASON_SPLIT_ASSIGNMENT.get(s, "training") for s in seasons}


def test_fabricated_source_builds_and_reconciles(tmp_path, authority):
    records, _ = _fabricate(tmp_path)
    build = oc.build_observation_corpus(
        records, authority, tmp_path, seasons=(2021, 2022, 2023)
    )
    assert build.reconciles()
    assert len(build.rows) == 45 * 3
    assert not build.exclusions


def test_wrong_source_digest_is_refused(tmp_path, authority):
    records, manifest = _fabricate(tmp_path, seasons=(2021,))
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["captured_files"][0]["raw_sha256"] = "00" * 32
    manifest.write_bytes((json.dumps(payload) + "\n").encode("utf-8"))
    tampered = oc.load_acquisition_manifest(manifest)
    with pytest.raises(GovernanceBlock, match="decompresses to"):
        oc.verify_raw_custody(tampered, tmp_path)


def test_wrong_container_digest_is_refused(tmp_path, authority):
    records, manifest = _fabricate(tmp_path, seasons=(2021,))
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["captured_files"][0]["stored_sha256"] = "11" * 32
    manifest.write_bytes((json.dumps(payload) + "\n").encode("utf-8"))
    tampered = oc.load_acquisition_manifest(manifest)
    with pytest.raises(GovernanceBlock, match="not the registered"):
        oc.verify_raw_custody(tampered, tmp_path)


def test_mutated_raw_file_is_refused(tmp_path, authority):
    records, _ = _fabricate(tmp_path, seasons=(2021,))
    target = tmp_path / records[0].stored_path
    body = gzip.decompress(target.read_bytes()).replace(b'"score": "21"', b'"score": "99"')
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(body)
    target.write_bytes(buf.getvalue())
    with pytest.raises(GovernanceBlock, match="not the registered"):
        oc.verify_raw_custody(records, tmp_path)


def test_missing_source_is_refused(tmp_path, authority):
    records, _ = _fabricate(tmp_path, seasons=(2021,))
    (tmp_path / records[0].stored_path).unlink()
    with pytest.raises(GovernanceBlock, match="no longer present"):
        oc.verify_raw_custody(records, tmp_path)


def test_empty_manifest_is_refused(tmp_path):
    manifest = tmp_path / "empty.json"
    manifest.write_bytes(b'{"captured_files": []}\n')
    with pytest.raises(GovernanceBlock, match="records no captured files"):
        oc.load_acquisition_manifest(manifest)


def test_synthetic_source_authority_is_refused(tmp_path):
    with pytest.raises(GovernanceBlock, match="Only \\['GOVERNED_RESULT_SOURCE'\\]"):
        oc.RawSourceRecord(
            url="file:///simulated.json",
            season=2021,
            division="fbs",
            week=1,
            stored_path="raw/x.json.gz",
            raw_sha256="a" * 64,
            raw_byte_length=10,
            stored_sha256="b" * 64,
            stored_byte_length=10,
            source_authority="LOCAL_SEASON_LEDGER",
            source_authority_class="SIMULATED_OR_SYNTHETIC",
            retrieval_method="copied",
            retrieved_at="2026-08-22T00:00:00+00:00",
            game_count=1,
        )


def test_synthetic_declared_provenance_is_refused(tmp_path):
    """A source that calls its own scores simulated is refused at mount."""
    with pytest.raises(GovernanceBlock, match="synthetic and simulated"):
        oc.RawSourceRecord(
            url="file:///ledger.json",
            season=2021,
            division="fbs",
            week=1,
            stored_path="raw/x.json.gz",
            raw_sha256="a" * 64,
            raw_byte_length=10,
            stored_sha256="b" * 64,
            stored_byte_length=10,
            source_authority="PROJECT_SYNTHETIC_SEASON_LEDGER",
            source_authority_class="GOVERNED_RESULT_SOURCE",
            retrieval_method="local copy",
            retrieved_at="2026-08-22T00:00:00+00:00",
            game_count=1,
        )


def test_non_sha256_digest_is_refused():
    with pytest.raises(InputValidationError, match="not a SHA-256"):
        oc.RawSourceRecord(
            url="file:///x.json",
            season=2021,
            division="fbs",
            week=1,
            stored_path="raw/x.json.gz",
            raw_sha256="short",
            raw_byte_length=10,
            stored_sha256="b" * 64,
            stored_byte_length=10,
            source_authority="NCAA_OFFICIAL_SCOREBOARD_FEED",
            source_authority_class="GOVERNED_RESULT_SOURCE",
            retrieval_method="HTTP GET",
            retrieved_at="2026-08-22T00:00:00+00:00",
            game_count=1,
        )


@pytest.mark.parametrize(
    "override, reason",
    [
        ({"gameID": ""}, "MISSING_SOURCE_GAME_IDENTIFIER"),
        ({"gameState": "pre"}, "GAME_NOT_FINAL"),
        ({"startTimeEpoch": ""}, "CHRONOLOGY_UNRESOLVED"),
        ({"startTimeEpoch": "0"}, "CHRONOLOGY_UNRESOLVED"),
    ],
)
def test_single_row_gates_refuse_with_the_stated_reason(
    tmp_path, authority, override, reason
):
    def mutate(season, week, games):
        if season == 2021 and week == 1:
            first = json.loads(json.dumps(games[0]))
            first["game"].update(override)
            return [first] + games[1:]
        return games

    records, _ = _fabricate(tmp_path, seasons=(2021,), mutate=mutate)
    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    reasons = [e["reason"] for e in build.exclusions]
    assert reason in reasons
    assert build.reconciles()


def test_blank_score_is_refused_as_missing_score(tmp_path, authority):
    def mutate(season, week, games):
        if week == 1:
            first = json.loads(json.dumps(games[0]))
            first["game"]["home"]["score"] = ""
            return [first] + games[1:]
        return games

    records, _ = _fabricate(tmp_path, seasons=(2021,), mutate=mutate)
    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    assert "MISSING_REQUIRED_SCORE" in [e["reason"] for e in build.exclusions]
    assert build.reconciles()


def test_unresolved_team_is_refused_not_mapped_by_similarity(tmp_path, authority):
    """A school absent from the canonical master must not acquire an identity."""

    def mutate(season, week, games):
        if week == 1:
            first = json.loads(json.dumps(games[0]))
            first["game"]["away"]["names"] = {
                "char6": "MIA OH",
                "short": "Miami (OH)",
                "seo": "miami-oh",
                "full": "Miami University (Ohio)",
            }
            return [first] + games[1:]
        return games

    records, _ = _fabricate(tmp_path, seasons=(2021,), mutate=mutate)
    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    refused = [e for e in build.exclusions if e["reason"] == "UNRESOLVED_TEAM_IDENTITY"]
    assert refused
    assert "Miami (OH)" in build.identity_report["unresolved_entity_names"]
    # It must not have been folded into canonical Miami.
    assert "Miami (OH)" not in [r.opponent for r in build.rows]


def test_game_id_collision_is_refused(tmp_path, authority):
    """Two records for one game under different ids refuse rather than dedupe."""

    def mutate(season, week, games):
        if week == 1:
            twin = json.loads(json.dumps(games[0]))
            twin["game"]["gameID"] = "DUPLICATE-9999"
            twin["game"]["startTimeEpoch"] = str(
                int(games[0]["game"]["startTimeEpoch"]) + 7200
            )
            return games + [twin]
        return games

    records, _ = _fabricate(tmp_path, seasons=(2021,), mutate=mutate)
    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    duplicates = [
        e for e in build.exclusions if e["reason"] == "DUPLICATE_OR_AMBIGUOUS_GAME_ID"
    ]
    assert len(duplicates) == 2, "both records are refused, neither is chosen"
    assert build.reconciles()


def test_genuine_repeat_matchup_in_a_later_week_is_kept(tmp_path, authority):
    """The complement of the collision test: a real rematch must survive.

    Same two teams, same season, a later week — a conference championship
    rematch. R5's team-pair key collapsed exactly this into one colliding
    identifier; the source-keyed scheme must keep both.
    """
    entries = []
    base = 1630000000
    blocks = _round_robin(2021, base)
    for block in blocks:
        entries.append(_write_feed(tmp_path, 2021, "fbs", block["week"], block["games"]))
        entries.append(_write_feed(tmp_path, 2021, "fcs", block["week"], []))
    # A tenth week holding only the rematch of week 1's opening game.
    original = blocks[0]["games"][0]["game"]
    rematch = json.loads(json.dumps(blocks[0]["games"][0]))
    rematch["game"]["gameID"] = "REMATCH-1"
    rematch["game"]["startTimeEpoch"] = str(int(original["startTimeEpoch"]) + 9 * 604800)
    entries.append(_write_feed(tmp_path, 2021, "fbs", 10, [rematch]))
    entries.append(_write_feed(tmp_path, 2021, "fcs", 10, []))
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes((json.dumps({"captured_files": entries}) + "\n").encode("utf-8"))
    records = oc.load_acquisition_manifest(manifest)

    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    assert not [
        e for e in build.exclusions if e["reason"] == "DUPLICATE_OR_AMBIGUOUS_GAME_ID"
    ]
    ids = [r.game_id for r in build.rows]
    assert f"NCAA-2021-{original['gameID']}" in ids
    assert "NCAA-2021-REMATCH-1" in ids
    assert len(ids) == len(set(ids))
    repeats = build.game_identity_report["repeat_matchups"]
    assert len(repeats) == 1
    assert sorted(repeats[0]["weeks"]) == [1, 10]


def test_self_matchup_is_refused(tmp_path, authority):
    def mutate(season, week, games):
        if week == 1:
            first = json.loads(json.dumps(games[0]))
            first["game"]["away"]["names"] = dict(first["game"]["home"]["names"])
            first["game"]["away"]["names"]["seo"] = "alabama-alt"
            return [first] + games[1:]
        return games

    records, _ = _fabricate(tmp_path, seasons=(2021,), mutate=mutate)
    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    reasons = [e["reason"] for e in build.exclusions]
    assert "AMBIGUOUS_TEAM_IDENTITY" in reasons or "SELF_MATCHUP" in reasons


def test_team_season_below_the_coverage_floor_is_pruned(tmp_path, authority):
    def mutate(season, week, games):
        # Strip Texas from every week after the second, leaving it under the floor.
        if week > 2:
            return [
                g
                for g in games
                if "texas" not in (g["game"]["home"]["names"]["seo"], g["game"]["away"]["names"]["seo"])
            ]
        return games

    records, _ = _fabricate(tmp_path, seasons=(2021,), mutate=mutate)
    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    assert "TEX" not in {r.team for r in build.rows} | {r.opponent for r in build.rows}
    pruned = [
        e for e in build.exclusions if e["reason"] == "INSUFFICIENT_TEAM_SEASON_COVERAGE"
    ]
    assert pruned
    assert build.reconciles()
    coverage = build.source_report["team_season_coverage"]
    assert coverage["minimum_games_per_team_season"] >= oc.MINIMUM_GAMES_PER_TEAM_SEASON


def test_cross_division_game_is_excluded_and_inventoried(tmp_path, authority):
    """Division follows feed membership, and a cross-division game stays out.

    Cal Poly appears only in a game the ``fcs`` feed also carries, so it is
    never seen in an FBS-only game and is read as FCS. Its one game against
    Alabama is therefore cross-division: excluded, and inventoried rather than
    dropped, so a later FCS-scale lane inherits it.
    """
    entries = []
    base = 1630000000
    blocks = _round_robin(2021, base)
    for block in blocks:
        entries.append(_write_feed(tmp_path, 2021, "fbs", block["week"], block["games"]))
        entries.append(_write_feed(tmp_path, 2021, "fcs", block["week"], []))
    cross_game = _game(
        "CROSS-1",
        _TEAMS[0],
        ("cal-poly", "Cal Poly", "CALPLY"),
        base + 10 * 604800,
        home_score=49,
        away_score=7,
    )
    entries.append(_write_feed(tmp_path, 2021, "fbs", 10, [cross_game]))
    entries.append(_write_feed(tmp_path, 2021, "fcs", 10, [cross_game]))
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes((json.dumps({"captured_files": entries}) + "\n").encode("utf-8"))
    records = oc.load_acquisition_manifest(manifest)

    build = oc.build_observation_corpus(records, authority, tmp_path, seasons=(2021,))
    cross = [
        e
        for e in build.exclusions
        if e["reason"] == "FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED"
    ]
    assert len(cross) == 1
    assert len(build.fcs_inventory) == 1
    entry = build.fcs_inventory[0]
    assert entry["team"] == "ALA" and entry["opponent"] == "CP"
    assert {entry["home_division"], entry["away_division"]} == {"FBS", "FCS"}
    assert "NCAA-2021-CROSS-1" not in {r.game_id for r in build.rows}
    assert build.reconciles()


def test_split_leakage_is_refused_when_a_split_is_out_of_order(build):
    """The gate must reject a split whose holdout predates its training data."""
    rows = list(build.rows)
    swapped = [
        oc.ObservationRow(
            **{
                **row.__dict__,
                "split": "holdout" if row.split == "training" else "training",
            }
        )
        if row.split in ("training", "holdout")
        else row
        for row in rows
    ]
    with pytest.raises(GovernanceBlock, match="not temporally ordered"):
        oc.build_temporal_split(swapped)


def test_volume_gate_refuses_a_corpus_that_is_too_small(tmp_path, authority):
    records, _ = _fabricate(tmp_path, seasons=(2021, 2022, 2023))
    build = oc.build_observation_corpus(
        records, authority, tmp_path, seasons=(2021, 2022, 2023)
    )
    with pytest.raises(GovernanceBlock, match="minimum volume"):
        oc.volume_assessment(build.rows, build.source_report["team_season_coverage"])


def test_resolution_rules_are_deterministic(authority):
    for _ in range(3):
        assert (
            oc.resolve_source_team(
                seo="ohio-st", short="Ohio St.", char6="OHIOST", authority=authority
            ).schedule_id
            == "OSU"
        )
        assert (
            oc.resolve_source_team(
                seo="southern-california",
                short="Southern California",
                char6="USC",
                authority=authority,
            ).rule
            == "NCAA_CHAR6_CANONICAL_KEY"
        )
        assert (
            oc.resolve_source_team(
                seo="arizona-st", short="Arizona St.", char6="AZ ST", authority=authority
            ).rule
            == "NCAA_ABBREVIATION_EXPANSION"
        )
        assert (
            oc.resolve_source_team(
                seo="akron", short="Akron", char6="AKRON", authority=authority
            ).schedule_id
            is None
        )


def test_resolution_never_strips_a_source_side_qualifier(authority):
    """Miami (FL) and Miami (OH) must not collapse onto canonical Miami."""
    florida = oc.resolve_source_team(
        seo="miami-fl", short="Miami (FL)", char6="MIAMI", authority=authority
    )
    ohio = oc.resolve_source_team(
        seo="miami-oh", short="Miami (OH)", char6="MIA OH", authority=authority
    )
    assert florida.schedule_id == "MIA"  # via the NCAA's own char6 code
    assert ohio.schedule_id is None
    assert florida.schedule_id != ohio.schedule_id


def test_canonical_authority_rejects_an_empty_file(tmp_path):
    empty = tmp_path / "empty.md"
    empty.write_bytes(b"# nothing here\n")
    with pytest.raises(GovernanceBlock, match="yielded no entities"):
        oc.load_canonical_identity_authority(empty)


def test_no_parameter_is_promoted_by_this_module():
    """The module must expose nothing that writes a calibration value."""
    exported = set(oc.__all__)
    for forbidden in ("promote", "promote_regime", "write_config", "fit", "calibrate"):
        assert not any(forbidden in name for name in exported)
    for field in calibration.CALIBRATION_FIELDS:
        assert field not in oc.CORPUS_COLUMNS


# --------------------------------------------------------------------------
# audit remediation R1 — record accuracy
#
# The R6 audit passed the corpus and failed four *records*: a 2025 refusal
# described as something the bytes contradict, an overtime vocabulary stated
# short of what the feed publishes, a reconciliation rule claiming a wider
# universe than the code closes over, and builder-local absolute paths in
# machine-readable provenance. None of those touched an observation, which is
# exactly why none of the existing tests caught them: every test below asserts a
# property of a *description*, checked against the bytes it describes.
# --------------------------------------------------------------------------


def _artifact(name):
    return json.loads((CORPUS_DIR / name).read_text(encoding="utf-8"))


def _fbs_game_states(records, season):
    """gameState census for one season of the fbs feed, read from raw bytes."""
    census = {}
    for record in records:
        if record.division != "fbs" or record.season != season:
            continue
        for entry in json.loads(record.read(REPO_ROOT)).get("games", []):
            state = entry["game"].get("gameState", "")
            census[state] = census.get(state, 0) + 1
    return census


def test_refused_season_census_matches_the_bytes_it_describes(build, records):
    """A refused season is described by counting it, never by characterising it.

    The original record said every 2025 row read ``pre``. Twenty-two read
    ``final`` and four read ``live``. The refusal was right and the sentence was
    false, which is the failure mode this pins: the census is recomputed from
    the raw bytes here and must equal what the build published.
    """
    published = build.source_report["seasons_not_admitted_state_census"]
    assert "2025" in published
    observed = _fbs_game_states(records, 2025)
    assert published["2025"]["by_game_state"] == observed
    assert published["2025"]["total"] == sum(observed.values())
    # The exact counts the audit measured, so drift is loud rather than quiet.
    assert published["2025"] == {
        "total": 878,
        "by_game_state": {"final": 22, "live": 4, "pre": 852},
    }


def test_a_refused_season_may_hold_final_rows_and_still_refuses_all_of_them(build):
    """Source content fact and evidence admission decision stay separate.

    Twenty-two 2025 rows are ``final``. Admission is by whole finalised season,
    so those rows are refused with the rest. Admitting them would make the
    corpus depend on the minute the snapshot was taken.
    """
    census = build.source_report["seasons_not_admitted_state_census"]["2025"]
    assert census["by_game_state"]["final"] > 0

    assert build.source_report["seasons_not_admitted"]["2025"] == (
        "SOURCE_SEASON_NOT_FINALISED"
    )
    refused_2025 = [
        e
        for e in build.exclusions
        if e["season"] == 2025 and e["reason"] == "SOURCE_SEASON_NOT_FINALISED"
    ]
    assert len(refused_2025) == census["total"]
    assert 2025 not in {row.season for row in build.rows}
    assert 2025 not in oc.ADMITTED_SEASONS


def test_the_published_census_rule_names_both_halves():
    """The record must say which sentence is the fact and which is the decision."""
    rule = _artifact("V3_R6_CORPUS_REGISTRATION_RECEIPT.json")["source_report"][
        "seasons_not_admitted_census_rule"
    ]
    assert "SOURCE CONTENT FACT" in rule
    assert "EVIDENCE ADMISSION DECISION" in rule

    discovery = _artifact("V3_R6_OBSERVATION_CORPUS_DISCOVERY_R6.json")
    evidence = discovery["source_acquisition"]["seasons_refused_evidence"]
    assert "SOURCE CONTENT FACT" in evidence
    assert "EVIDENCE ADMISSION DECISION" in evidence
    # The false universal must not come back in any wording.
    assert "every game in them still reads" not in evidence
    assert discovery["source_acquisition"]["seasons_refused"] == {
        "2025": "SOURCE_SEASON_NOT_FINALISED"
    }


def test_overtime_vocabulary_is_read_from_the_bytes_not_asserted(build, records):
    """The stated overtime range must cover every label the feed actually uses.

    The original records stopped at ``FINAL (4OT)``. The fbs feed publishes
    ``FINAL (7OT)`` and the admitted corpus contains a ``FINAL (8OT)`` game, so
    the stated range fell short of the evidence beneath it.
    """
    observed = set()
    for record in records:
        if record.division != "fbs":
            continue
        for entry in json.loads(record.read(REPO_ROOT)).get("games", []):
            match = oc._OVERTIME.search(entry["game"].get("finalMessage", ""))
            if match:
                observed.add(match.group(0))

    published_feed = set(build.source_report["overtime_labels_source_feed"])
    assert published_feed == observed
    # Both labels the audit named are inside the published vocabulary.
    assert "FINAL (7OT)" in published_feed
    assert "FINAL (8OT)" in published_feed

    admitted = build.source_report["overtime_labels_admitted"]
    assert "FINAL (8OT)" in admitted
    assert build.source_report["overtime_maximum_periods_admitted"] == 8
    assert build.source_report["overtime_maximum_label_admitted"] == "FINAL (8OT)"

    # Every published label parses, and deeper labels sort later.
    periods = [oc._overtime_periods(label) for label in published_feed]
    assert max(periods) == 8
    assert sorted(admitted, key=oc._overtime_periods) == admitted


def test_no_record_caps_the_overtime_vocabulary_at_four_periods():
    """The specific understatement the audit found must not reappear."""
    receipt = _artifact("V3_R6_CORPUS_REGISTRATION_RECEIPT.json")
    basis = receipt["field_classification"]["overtime_periods"]["basis"]
    disposition = receipt["source_report"]["overtime_disposition"]
    for text in (basis, disposition):
        assert "through FINAL (4OT)" not in text
    docs = (REPO_ROOT / "docs" / "v3_historical_observation_corpus_r6.md").read_text(
        encoding="utf-8"
    )
    assert "through `FINAL (4OT)`" not in docs


def test_admitted_overtime_count_is_unchanged_by_the_record_correction(build):
    """Correcting a description must not move a single observation."""
    assert build.source_report["overtime_games_admitted"] == 91
    assert build.source_report["overtime_games_staged"] == 101
    assert "overtime_periods" not in oc.CORPUS_COLUMNS


def test_reconciliation_universe_is_the_fbs_feed_and_says_so(build, records):
    """The row equation closes over the fbs feed, and the record must scope it.

    The original rule said "for every source file", which is wider than the
    implemented universe. The fbs feed is the correct universe — an
    FBS-versus-FCS game is published in both feeds, so no in-scope game hides on
    the fcs side — but the sentence claimed more than the code does.
    """
    fbs_rows = sum(
        len(json.loads(r.read(REPO_ROOT)).get("games", []))
        for r in records
        if r.division == "fbs"
    )
    assert build.raw_row_count == fbs_rows == 4355
    assert build.raw_row_count == len(build.rows) + len(build.exclusions)

    reconciliation = _artifact("V3_R6_EXCLUSION_REPORT.json")["reconciliation"]
    assert reconciliation["reconciliation_universe"] == "NCAA_FBS_SCOREBOARD_FEED"
    assert reconciliation["fbs_feed_row_count"] == fbs_rows
    assert reconciliation["raw_row_count"] == fbs_rows
    assert "for every source file" not in reconciliation["rule"]
    assert "fbs-feed source file" in reconciliation["rule"]


def test_the_fcs_feed_is_declared_an_oracle_outside_the_row_equation(build, records):
    """The fcs rows are a division oracle: not admitted, not excluded, not raw."""
    fcs_rows = sum(
        len(json.loads(r.read(REPO_ROOT)).get("games", []))
        for r in records
        if r.division == "fcs"
    )
    assert build.source_report["fcs_oracle_row_count"] == fcs_rows == 4164
    assert build.source_report["fcs_oracle_files"] == len(
        [r for r in records if r.division == "fcs"]
    )
    assert (
        build.source_report["fcs_oracle_role"]
        == "DIVISION_CLASSIFICATION_ORACLE_OUTSIDE_ROW_RECONCILIATION"
    )

    # The oracle count is deliberately outside the equation, not folded into it.
    assert build.raw_row_count != fcs_rows
    assert build.raw_row_count + fcs_rows != len(build.rows) + len(build.exclusions)

    reconciliation = _artifact("V3_R6_EXCLUSION_REPORT.json")["reconciliation"]
    assert reconciliation["fcs_oracle_row_count"] == fcs_rows
    assert "NOT terms in the equation" in reconciliation["fcs_oracle_rule"]


def test_no_r6_artifact_carries_a_builder_local_absolute_path():
    """Provenance must read the same from any checkout.

    An absolute worktree path is not independently checkable: it names one
    machine. The digest beside it is the binding and stays the binding.
    """
    for artifact in sorted(CORPUS_DIR.glob("*.json")):
        text = artifact.read_text(encoding="utf-8")
        assert "CLAUDE-SYTHALAX-WORKTREES" not in text, artifact.name
        assert "C:/" not in text, artifact.name
        assert "C:\\" not in text, artifact.name


def test_provenance_paths_are_repository_relative_and_resolve():
    """The portable locators must actually resolve in this checkout."""
    receipt = _artifact("V3_R6_CORPUS_REGISTRATION_RECEIPT.json")
    assert receipt["path_class"] == "REPOSITORY_RELATIVE"
    assert not Path(receipt["path"]).is_absolute()
    assert (REPO_ROOT / receipt["path"]).resolve() == CORPUS_CSV.resolve()

    identity = _artifact("V3_R6_TEAM_IDENTITY_RECONCILIATION.json")
    assert identity["canonical_authority_path_class"] == "REPOSITORY_RELATIVE"
    assert not Path(identity["canonical_authority"]).is_absolute()
    resolved = (REPO_ROOT / identity["canonical_authority"]).resolve()
    assert resolved == AUTHORITY_PATH.resolve()


def test_portable_path_never_replaces_the_digest_binding(authority):
    """Weakening a digest to a path trades evidence for trust. It must not."""
    identity = _artifact("V3_R6_TEAM_IDENTITY_RECONCILIATION.json")
    assert identity["canonical_authority_sha256"] == authority.sha256
    assert identity["canonical_authority_sha256"] == oc._sha256(
        AUTHORITY_PATH.read_bytes()
    )

    receipt = _artifact("V3_R6_CORPUS_REGISTRATION_RECEIPT.json")
    assert receipt["sha256"] == oc._sha256(CORPUS_CSV.read_bytes())
    assert receipt["byte_length"] == len(CORPUS_CSV.read_bytes())
    assert receipt["bytes_reverified_at_registration"] is True


def test_a_path_outside_the_repository_degrades_to_a_name(tmp_path, build):
    """Portability must not become another route for leaking a build host."""
    outside = tmp_path / "elsewhere" / "V3_R6_OBSERVATION_CORPUS.csv"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(CORPUS_CSV.read_bytes())
    receipt = oc.corpus_registration_receipt(outside, build.rows, REPO_ROOT)
    assert receipt["path"] == "V3_R6_OBSERVATION_CORPUS.csv"
    assert str(tmp_path) not in receipt["path"]
    # The digest still binds the bytes, wherever they sit.
    assert receipt["sha256"] == oc._sha256(CORPUS_CSV.read_bytes())


def test_record_correction_left_the_observation_set_untouched(build):
    """The remediation is representation-only. This is what says so."""
    assert len(build.rows) == 2241
    assert len(build.exclusions) == 2114
    assert build.raw_row_count == 4355
    assert oc.render_corpus_csv(build.rows) == CORPUS_CSV.read_bytes()
    assert len(build.fcs_inventory) == 43

    split = oc.build_temporal_split(build.rows)
    assert split["splits"] == {"training": 1080, "validation": 598, "holdout": 563}
    assert (
        split["split_digest"]
        == "d0b84cc3da244ffbb5566bbf5c86fd07aed081ae48b01de293b79863503e3f5b"
    )
    coverage = build.source_report["team_season_coverage"]
    assert coverage["iterations"] == 5
    assert coverage["rows_pruned"] == 227
    assert coverage["minimum_games_per_team_season"] == 8
