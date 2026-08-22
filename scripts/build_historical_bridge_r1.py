"""Build every derived artifact of the historical bridge lane, from bytes.

The whole build is a function of committed bytes: the raw captures, the two
mounted evidence extracts, and the canonical master. It reads nothing live, and
re-running it reproduces every artifact byte for byte -- which is why no
artifact carries a generation timestamp. When something happened is recorded by
git and by the acquisition manifests, both of which are outside the bytes being
hashed.

Order matters in one place and is worth stating. Custody is re-verified before
anything is parsed, and a mismatch raises rather than being reported, so no
number downstream can be computed over bytes that failed their digest.

Usage::

    python scripts/build_historical_bridge_r1.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import historical_bridge as hb  # noqa: E402

BRIDGE_ROOT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "historical_bridge_r1"
MOUNTED = BRIDGE_ROOT / "mounted"
RESULTS_MANIFEST = BRIDGE_ROOT / "V3_BRIDGE_SOURCE_ACQUISITION_MANIFEST.json"
MEMBERSHIP_MANIFEST = BRIDGE_ROOT / "V3_BRIDGE_MEMBERSHIP_ACQUISITION_MANIFEST.json"
CANONICAL_MASTER = (
    REPO_ROOT
    / "reference"
    / "dynamic_weekly_mc_v3"
    / "inputs"
    / "2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md"
)


def write_json(path: Path, payload: object) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict]) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(columns), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(row)
    text = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def universe_overlap(games, extract) -> dict:
    """How much of the component universe is the real season.

    A component value can only inform a game its universe contains. The
    synthetic 2025 ledger and the real 2025 season are compared on the unordered
    pair of folded team names plus the calendar date, which is the loosest
    comparison that still identifies a game -- so a low overlap under this rule
    is a strong statement, not a matching artefact.
    """
    real: set[tuple[str, str, str]] = set()
    real_pairs: set[tuple[str, str]] = set()
    for game in games:
        home = hb.normalise_name(game.home_team_name)
        away = hb.normalise_name(game.away_team_name)
        pair = tuple(sorted((home, away)))
        real.add((pair[0], pair[1], game.kickoff_utc[:10]))
        real_pairs.add((pair[0], pair[1]))

    component = extract.get("component_universe_games", [])
    date_hits = 0
    pair_hits = 0
    for entry in component:
        home = hb.normalise_name(entry["home_team"])
        away = hb.normalise_name(entry["away_team"])
        pair = tuple(sorted((home, away)))
        if (pair[0], pair[1], entry["date"][:10]) in real:
            date_hits += 1
        if (pair[0], pair[1]) in real_pairs:
            pair_hits += 1
    return {
        "component_universe_games": len(component),
        "real_season_games": len(games),
        "matched_on_pair_and_date": date_hits,
        "matched_on_pair_only": pair_hits,
        "match_rule": (
            "unordered folded team-name pair, with and without the calendar date"
        ),
        "universe_joins_real_season": date_hits > 0,
    }


def main() -> int:
    print("re-verifying custody")
    captures = hb.load_captures(RESULTS_MANIFEST, REPO_ROOT)
    membership_captures = hb.load_captures(MEMBERSHIP_MANIFEST, REPO_ROOT)
    membership = hb.load_membership(MEMBERSHIP_MANIFEST, REPO_ROOT)
    names = hb.membership_team_names(list(captures) + list(membership_captures))
    print(f"  {len(captures)} result captures, {len(membership_captures)} structure captures")

    custody = {
        "artifact": "V3_BRIDGE_SOURCE_CUSTODY_MANIFEST",
        "artifact_version": hb.ARTIFACT_VERSION,
        "reverification": "every declared capture re-read and both digests recomputed",
        "captures_reverified": len(captures) + len(membership_captures),
        "captures_failing_reverification": 0,
        "total_raw_bytes": sum(
            capture.raw_bytes for capture in list(captures) + list(membership_captures)
        ),
        "captures": [
            {
                "stored_path": capture.stored_path,
                "source_authority": capture.source_authority,
                "source_authority_tier": capture.source_authority_tier,
                "url": capture.url,
                "raw_bytes": capture.raw_bytes,
                "raw_sha256": capture.observed_raw_sha256,
                "stored_sha256": capture.observed_stored_sha256,
                "custody_verified": capture.custody_verified,
            }
            for capture in sorted(
                list(captures) + list(membership_captures),
                key=lambda item: item.stored_path,
            )
        ],
    }

    ncaa_rows_by_season: dict[int, list[hb.NcaaGame]] = {}
    for season in hb.SEASONS:
        ncaa_rows_by_season[season] = [
            row
            for capture in captures
            if capture.source_authority == hb.NCAA_AUTHORITY
            and capture.season == season
            for row in hb.parse_ncaa_capture(capture)
        ]

    games_by_season: dict[int, list[hb.BridgeGame]] = {}
    exclusions_by_season: dict[int, list[dict]] = {}
    reconciliation: dict[str, object] = {}
    artifacts: dict[str, str] = {}

    staleness = {
        str(season): hb.ncaa_season_staleness_report(captures, season)
        for season in hb.SEASONS
    }

    for season in hb.SEASONS:
        games, exclusions = hb.build_bridge_games(captures, membership, season)
        games_by_season[season] = games
        exclusions_by_season[season] = exclusions
        print(f"  season {season}: {len(games)} admitted, {len(exclusions)} excluded")

    # 2020 is checked against the tier-1 feed; 2025 cannot be, and says so.
    keys_by_team = hb.espn_team_keys(list(captures) + list(membership_captures))
    bridge_2020 = hb.build_name_bridge(
        keys_by_team, names, ncaa_rows_by_season[2020]
    )
    agreement_2020, verdicts_2020 = hb.cross_source_agreement(
        games_by_season[2020],
        ncaa_rows_by_season[2020],
        bridge_2020,
        membership[2020],
    )
    games_by_season[2020] = hb.apply_corroboration(
        games_by_season[2020], verdicts_2020, hb.NOT_CARRIED_BY_TIER_1
    )
    games_by_season[2025] = hb.apply_corroboration(
        games_by_season[2025], {}, hb.TIER_1_STALE
    )

    division_check_2020 = hb.division_cross_check(
        games_by_season[2020], ncaa_rows_by_season[2020], bridge_2020, membership[2020]
    )

    coverage = {
        str(season): hb.team_season_coverage(games_by_season[season], membership[season])
        for season in hb.SEASONS
    }

    for season in hb.SEASONS:
        games = games_by_season[season]
        artifacts[f"V3_BRIDGE_{season}_RESULTS.csv"] = write_csv(
            BRIDGE_ROOT / f"V3_BRIDGE_{season}_RESULTS.csv",
            hb.BRIDGE_COLUMNS,
            [game.as_row() for game in games],
        )

    for season in hb.SEASONS:
        raw_rows = sum(
            len(hb.parse_espn_capture(capture))
            for capture in captures
            if capture.source_authority == hb.ESPN_RESULTS_AUTHORITY
            and capture.season == season
        )
        counts: dict[str, int] = {}
        for row in exclusions_by_season[season]:
            counts[row["reason"]] = counts.get(row["reason"], 0) + 1
        admitted = len(games_by_season[season])
        reconciliation[str(season)] = {
            "raw_event_rows_retrieved": raw_rows,
            "admitted": admitted,
            "excluded": len(exclusions_by_season[season]),
            "reconciles": raw_rows == admitted + len(exclusions_by_season[season]),
            "exclusions_by_reason": dict(sorted(counts.items())),
            "admitted_by_season_type": _count(
                games_by_season[season], lambda game: game.season_type
            ),
            "admitted_cross_division": sum(
                1 for game in games_by_season[season] if game.cross_division
            ),
            "admitted_neutral_site": sum(
                1 for game in games_by_season[season] if game.neutral_site
            ),
            "admitted_overtime": sum(
                1 for game in games_by_season[season] if game.overtime
            ),
            "corroboration": _count(
                games_by_season[season], lambda game: game.tier_1_corroboration
            ),
        }

    artifacts["V3_BRIDGE_ROW_RECONCILIATION.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_ROW_RECONCILIATION.json",
        {
            "artifact": "V3_BRIDGE_ROW_RECONCILIATION",
            "artifact_version": hb.ARTIFACT_VERSION,
            "per_season": reconciliation,
            "exclusions": {
                str(season): exclusions_by_season[season] for season in hb.SEASONS
            },
        },
    )

    artifacts["V3_BRIDGE_CROSS_SOURCE_AGREEMENT_2020.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_CROSS_SOURCE_AGREEMENT_2020.json",
        {
            "artifact": "V3_BRIDGE_CROSS_SOURCE_AGREEMENT_2020",
            "artifact_version": hb.ARTIFACT_VERSION,
            "score_agreement": agreement_2020,
            "division_agreement": division_check_2020,
        },
    )

    artifacts["V3_BRIDGE_TIER_1_FEED_ASSESSMENT.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_TIER_1_FEED_ASSESSMENT.json",
        {
            "artifact": "V3_BRIDGE_TIER_1_FEED_ASSESSMENT",
            "artifact_version": hb.ARTIFACT_VERSION,
            "per_season": staleness,
        },
    )

    artifacts["V3_BRIDGE_SEASON_COVERAGE.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_SEASON_COVERAGE.json",
        {
            "artifact": "V3_BRIDGE_SEASON_COVERAGE",
            "artifact_version": hb.ARTIFACT_VERSION,
            "per_season": coverage,
        },
    )

    candidates = json.loads(
        (MOUNTED / "V3_BRIDGE_POPULATION_CANDIDATE_EXTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    membership_record = hb.membership_report(membership, names, candidates, keys_by_team)
    membership_record["artifact"] = "V3_BRIDGE_HISTORICAL_MEMBERSHIP"
    membership_record["artifact_version"] = hb.ARTIFACT_VERSION
    membership_record["population_resolution_2024"] = hb.resolve_2024_population(
        membership_record
    )
    artifacts["V3_BRIDGE_HISTORICAL_MEMBERSHIP.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_HISTORICAL_MEMBERSHIP.json", membership_record
    )

    entities, canonical_sha = hb.load_canonical_master(CANONICAL_MASTER)
    binding = hb.canonical_binding_report(
        games_by_season, entities, canonical_sha, keys_by_team
    )
    binding["artifact"] = "V3_BRIDGE_TEAM_IDENTITY"
    binding["artifact_version"] = hb.ARTIFACT_VERSION
    artifacts["V3_BRIDGE_TEAM_IDENTITY.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_TEAM_IDENTITY.json", binding
    )

    extract = json.loads(
        (MOUNTED / "V3_BRIDGE_2025_OPENING_COMPONENT_EXTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    overlap = universe_overlap(games_by_season[2025], extract)
    extract["universe_overlap"] = overlap
    trueskill = extract["families"].get("TRUESKILL")
    if isinstance(trueskill, dict):
        trueskill["universe_joins_real_season"] = overlap["universe_joins_real_season"]
    join_test = hb.opening_state_join_test(
        games_by_season[2025], extract, membership[2025]
    )
    join_test["artifact"] = "V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST"
    join_test["artifact_version"] = hb.ARTIFACT_VERSION
    join_test["component_extract_sha256"] = hashlib.sha256(
        (MOUNTED / "V3_BRIDGE_2025_OPENING_COMPONENT_EXTRACT.json").read_bytes()
    ).hexdigest()
    artifacts["V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_2025_OPENING_STATE_JOIN_TEST.json", join_test
    )

    backcast = hb.backcast_feasibility(games_by_season[2020])
    backcast["artifact"] = "V3_BRIDGE_2020_BACKCAST_FEASIBILITY"
    backcast["artifact_version"] = hb.ARTIFACT_VERSION
    artifacts["V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_2020_BACKCAST_FEASIBILITY.json", backcast
    )

    artifacts["V3_BRIDGE_SOURCE_CUSTODY_MANIFEST.json"] = write_json(
        BRIDGE_ROOT / "V3_BRIDGE_SOURCE_CUSTODY_MANIFEST.json", custody
    )

    for name in (
        "V3_BRIDGE_2025_OPENING_COMPONENT_EXTRACT.json",
        "V3_BRIDGE_POPULATION_CANDIDATE_EXTRACT.json",
    ):
        artifacts[f"mounted/{name}"] = hashlib.sha256(
            (MOUNTED / name).read_bytes()
        ).hexdigest()

    status = {
        "artifact": "V3_BRIDGE_STATUS_R1",
        "artifact_version": hb.ARTIFACT_VERSION,
        "lane": "claude/v3-historical-bridge-corpus-r1",
        "seasons_in_scope": list(hb.SEASONS),
        "2020_real_results_status": "ACQUIRED_TIER_2_CORROBORATED_BY_TIER_1",
        "2020_game_count": len(games_by_season[2020]),
        "2020_source": [hb.ESPN_RESULTS_AUTHORITY, hb.NCAA_AUTHORITY],
        "2025_real_results_status": "ACQUIRED_TIER_2_UNCORROBORATED_TIER_1_STALE",
        "2025_game_count": len(games_by_season[2025]),
        "2025_source": [hb.ESPN_RESULTS_AUTHORITY],
        "2025_preseason_opening_source_status": join_test["disposition"],
        "2025_week1_2_joinable_games": join_test[
            "week_1_2_games_with_valid_opening_state_both_sides"
        ],
        "historical_membership_status": "DERIVED_FROM_SEASON_STRUCTURE_DECLARATION",
        "2024_population_resolution": membership_record["population_resolution_2024"][
            "resolution"
        ],
        "safe_for_opening_backcast": backcast["disposition"],
        "safe_for_2025_stage0": join_test["disposition"] == "STAGE_0_JOIN_AVAILABLE",
        "ratings_emitted": False,
        "parameters_promoted": 0,
        "blockers_retired": 0,
        "governed_allowlist_widened": False,
        "canonical_config_written": False,
        "artifact_sha256": dict(sorted(artifacts.items())),
    }
    write_json(BRIDGE_ROOT / "V3_BRIDGE_STATUS_R1.json", status)

    print("\nartifacts:")
    for name, sha in sorted(artifacts.items()):
        print(f"  {sha[:16]}  {name}")
    return 0


def _count(rows, key) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(key(row))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


if __name__ == "__main__":
    sys.exit(main())
