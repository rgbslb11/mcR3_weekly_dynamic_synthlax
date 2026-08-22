"""Build the V3 historical venue/competition enrichment artifacts.

Reads the raw bytes acquired by :mod:`scripts.acquire_venue_sources_r1`,
re-verifies every digest against those bytes, and writes the enrichment table
and its reports. Nothing here retrieves anything; a build is a pure function of
what is in custody, which is what makes it repeatable and what makes a digest
recorded against it mean something.

The corpus join is optional and read-only. Historical Observation Corpus R6 is
another lane's artifact living on another branch: it is never copied into this
one, never rewritten, and never consulted to decide which games this enrichment
covers. When a path to it is supplied the build reports how much of it this
enrichment can answer the venue question for, and records the corpus digest so a
later reader can tell which corpus the answer was computed against::

    git show origin/claude/v3-historical-observation-corpus-r6:\
reference/dynamic_weekly_mc_v3/observation_corpus_r6/V3_R6_OBSERVATION_CORPUS.csv \
> corpus.csv
    python scripts/build_venue_enrichment_r1.py --corpus-csv corpus.csv

Usage::

    python scripts/build_venue_enrichment_r1.py
    python scripts/build_venue_enrichment_r1.py --corpus-csv <path>
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.venue_enrichment import (  # noqa: E402
    ENRICHMENT_COLUMNS,
    ENRICHMENT_ID,
    ESPN_AUTHORITY,
    ESPN_AUTHORITY_TIER,
    LANE_ID,
    NCAA_AUTHORITY,
    NCAA_AUTHORITY_TIER,
    build_venue_enrichment,
    conflict_report,
    corpus_join_report,
    coverage_report,
    render_enrichment_csv,
)

LANE_ROOT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "venue_enrichment_r1"

AUTHORITY_BANNER = (
    "EXPERIMENTAL / NOT CANONICAL / NO PARAMETER PROMOTED / NO BLOCKER RETIRED"
)


def _write_json(path: Path, payload: dict[str, Any]) -> str:
    data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _envelope(name: str, status: str, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact": name,
        "artifact_status": status,
        "lane": LANE_ID,
        "enrichment_id": ENRICHMENT_ID,
        "authority": AUTHORITY_BANNER,
        **body,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build venue enrichment artifacts.")
    parser.add_argument("--corpus-csv", type=Path, default=None)
    parser.add_argument("--corpus-exclusion-report", type=Path, default=None)
    args = parser.parse_args(argv)

    result = build_venue_enrichment(REPO_ROOT)
    coverage = coverage_report(result.rows)
    conflicts = conflict_report(result.rows)

    LANE_ROOT.mkdir(parents=True, exist_ok=True)

    csv_bytes = render_enrichment_csv(result.rows)
    csv_path = LANE_ROOT / "V3_VENUE_R1_ENRICHMENT.csv"
    csv_path.write_bytes(csv_bytes)
    csv_sha = hashlib.sha256(csv_bytes).hexdigest()

    _write_json(
        LANE_ROOT / "V3_VENUE_R1_MATCH_REPORT.json",
        _envelope(
            "V3_VENUE_R1_MATCH_REPORT.json",
            "DETERMINISTIC_MATCH_REPORT",
            {
                "match": result.match_report,
                "ncaa_source_report": result.source_reports["ncaa"]
                | {"division_membership": "see V3_VENUE_R1_TEAM_IDENTITY_MAP.json"},
                "espn_source_report": result.source_reports["espn"],
            },
        ),
    )

    _write_json(
        LANE_ROOT / "V3_VENUE_R1_COVERAGE_REPORT.json",
        _envelope("V3_VENUE_R1_COVERAGE_REPORT.json", "COVERAGE_REPORT", coverage),
    )

    _write_json(
        LANE_ROOT / "V3_VENUE_R1_CONFLICT_REPORT.json",
        _envelope(
            "V3_VENUE_R1_CONFLICT_REPORT.json",
            "SOURCE_CONFLICT_REPORT",
            {
                "conflict_resolution_policy": (
                    "Both evidence records are preserved on every conflicting game and "
                    "neither source is selected. No authority ranking is applied to a "
                    "fact one of the sources does not carry."
                ),
                **conflicts,
            },
        ),
    )

    _write_json(
        LANE_ROOT / "V3_VENUE_R1_TEAM_IDENTITY_MAP.json",
        _envelope(
            "V3_VENUE_R1_TEAM_IDENTITY_MAP.json",
            "TEAM_IDENTITY_RECONCILIATION",
            {
                "derivation": (
                    "Harvested from unambiguous date-and-score matches by aligning the "
                    "two feeds' scores within a game. Not hand-authored. A name "
                    "observed against more than one ESPN team id is dropped rather "
                    "than decided by majority."
                ),
                "entries": len(result.team_identity),
                "ncaa_seo_to_espn_team_id": dict(sorted(result.team_identity.items())),
                "division_membership": result.source_reports["ncaa"][
                    "division_membership"
                ],
                "division_membership_counts": result.source_reports["ncaa"][
                    "division_membership_counts"
                ],
            },
        ),
    )

    _write_json(
        LANE_ROOT / "V3_VENUE_R1_SOURCE_CUSTODY_MANIFEST.json",
        _envelope(
            "V3_VENUE_R1_SOURCE_CUSTODY_MANIFEST.json",
            "SOURCE_CUSTODY_MANIFEST",
            {
                "source_authorities": [
                    {
                        "source_authority": NCAA_AUTHORITY,
                        "source_authority_tier": NCAA_AUTHORITY_TIER,
                        "role": "GAME_IDENTITY_AND_SOURCE_ORIENTATION",
                        "carries_venue": False,
                    },
                    {
                        "source_authority": ESPN_AUTHORITY,
                        "source_authority_tier": ESPN_AUTHORITY_TIER,
                        "role": "VENUE_GAME_TYPE_AND_KICKOFF_EVIDENCE",
                        "carries_venue": True,
                    },
                ],
                **result.custody,
            },
        ),
    )

    join: dict[str, Any] | None = None
    if args.corpus_csv is not None:
        exclusions = (
            args.corpus_exclusion_report.read_bytes()
            if args.corpus_exclusion_report is not None
            else None
        )
        join = corpus_join_report(
            result.rows, args.corpus_csv.read_bytes(), exclusions
        )
        _write_json(
            LANE_ROOT / "V3_VENUE_R1_CORPUS_JOIN_REPORT.json",
            _envelope(
                "V3_VENUE_R1_CORPUS_JOIN_REPORT.json",
                "CORPUS_JOIN_REPORT",
                {
                    "corpus_access": "READ_ONLY_NOT_COPIED_NOT_MODIFIED",
                    "corpus_branch": "claude/v3-historical-observation-corpus-r6",
                    **join,
                },
            ),
        )

    _write_json(
        LANE_ROOT / "V3_VENUE_R1_REGISTRATION_RECEIPT.json",
        _envelope(
            "V3_VENUE_R1_REGISTRATION_RECEIPT.json",
            "ENRICHMENT_REGISTRATION_RECEIPT",
            {
                "enrichment_path": csv_path.relative_to(REPO_ROOT).as_posix(),
                "enrichment_sha256": csv_sha,
                "enrichment_byte_length": len(csv_bytes),
                "rows": len(result.rows),
                "columns": list(ENRICHMENT_COLUMNS),
                "bytes_reverified_at_build": True,
                "raw_sources_verified": result.custody["sources_verified"],
                "parameters_promoted": [],
                "blockers_retired": [],
                "monte_carlo_executed": False,
                "corpus_join_computed": join is not None,
                "corpus_sha256": (join or {}).get("corpus_sha256", ""),
                "headline": {
                    "games_considered": coverage["games_considered"],
                    "venue_resolved_count": coverage["venue_resolved_count"],
                    "venue_unresolved_count": coverage["venue_unresolved_count"],
                    "neutral_count": coverage["neutral_count"],
                    "home_field_count": coverage["home_field_count"],
                    "conference_championship_count": coverage[
                        "conference_championship_count"
                    ],
                    "conference_championship_neutral": coverage[
                        "conference_championship_neutral"
                    ],
                    "expected_margin_venue_ready": coverage[
                        "expected_margin_venue_ready"
                    ],
                },
            },
        ),
    )

    print(f"enrichment rows        : {len(result.rows)}")
    print(f"enrichment sha256      : {csv_sha}")
    print(f"venue resolved         : {coverage['venue_resolved_count']}")
    print(f"venue unresolved       : {coverage['venue_unresolved_count']}")
    print(f"neutral sites          : {coverage['neutral_count']}")
    print(f"conference championships: {coverage['conference_championship_count']}")
    print(f"source conflicts       : {coverage['source_conflict_count']}")
    if join is not None:
        print(f"corpus rows joined     : {join['joined_rows']} of {join['corpus_rows']}")
        print(
            "corpus venue resolved  : "
            f"{join['coverage']['venue_resolved_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
