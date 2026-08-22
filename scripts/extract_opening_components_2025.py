"""Extract the 2025 opening-component evidence the join test needs.

The four V3 preseason families live in staged workbooks outside the repository.
Reading them at build time would make the build depend on a filesystem that a
reviewer may not have, and committing the workbooks would mount a synthetic
rating universe into a governed repository. So this script does the reading once
and writes down exactly what the join test needs, with the upstream digest
attached to it: the extract is provenance-bound evidence *about* those sources,
not a mounted rating.

Nothing extracted here is a rating input. The extract carries opening-state
**shape** -- how many distinct values the 2025 opening state contains, what its
dispersion is, whose names are in it, which games its universe covers -- and the
digests that say which bytes those facts came from. No value is ever combined,
standardized, scaled or written into any configuration.

What is extracted, and why each is the thing that settles the family:

``TRUESKILL``
    The 2025 rating-history sheet carries every game's pregame state. Its Week 1
    rows are the 2025 opening state by construction, so the family *does* have a
    2025 preseason measurement -- and that measurement is an equal prior for
    every team. The distinct-value count is therefore the finding, not the mean.
    The sheet's canonical game list is extracted too, because a component
    universe that does not contain the real season's games cannot inform them,
    and the README's declared ledger digest is checked against the ledger file
    so the universe's synthetic provenance is established from bytes.

``LITKENHOUS``
    The only located 2025 artifact is a season-*final* rating. Final is
    same-season information; the extract records the workbook's own titling and
    columns rather than an opinion about them.

``PURE_BAXTER``
    The located 2025 artifact carries a ``games`` column. A count of games played
    is obtainable only after they are played.

``BOARD_FAMILY``
    Every located board artifact is 2026. The extract records the scan that
    establishes that, including the directories searched, so "none found" is a
    result with a method behind it rather than an absence of effort.

Usage::

    python scripts/extract_opening_components_2025.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import statistics
import sys
from pathlib import Path

import openpyxl

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "historical_bridge_r1"
EXTRACT_PATH = BRIDGE_ROOT / "mounted" / "V3_BRIDGE_2025_OPENING_COMPONENT_EXTRACT.json"

DOWNLOADS = Path("C:/Users/dbaxt/Downloads")
STAGING = Path("C:/Local-mcR3_calibration_staging")

TRUESKILL_PATH = DOWNLOADS / "Operation_Sythalax_TrueSkill_2025_2026_Thread_Consolidation.xlsx"
LITKENHOUS_PATH = DOWNLOADS / "2025_Synthetic_CFB_Litkenhous_Inspired_Final_Ratings.xlsx"
BAXTER_PATH = (
    STAGING
    / "Baxter_v1_2006_2011_2024_2025_Complete_Package"
    / "Baxter_Ratings_2025.csv"
)
SYNTHETIC_LEDGER_PATH = DOWNLOADS / "2025_Synthetic_Season_Games.csv"

SEARCH_ROOTS = (DOWNLOADS, STAGING)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _sheet_rows(workbook, name: str) -> list[tuple]:
    return list(workbook[name].iter_rows(values_only=True))


def extract_trueskill() -> dict:
    if not TRUESKILL_PATH.exists():
        return {"source_located": False, "disposition": "NO_2025_SOURCE_LOCATED"}

    workbook = openpyxl.load_workbook(TRUESKILL_PATH, read_only=True, data_only=True)
    history = _sheet_rows(workbook, "14 2025 Rating History")
    header = [str(cell) for cell in history[0]]
    index = {name: position for position, name in enumerate(header)}

    opening_values: list[float] = []
    opening_teams: set[str] = set()
    for row in history[1:]:
        if row[index["round"]] != "W1":
            continue
        team = row[index["team"]]
        value = row[index["pregame_mu"]]
        if team is None or value is None:
            continue
        opening_teams.add(str(team))
        opening_values.append(float(value))

    games = _sheet_rows(workbook, "19A Canonical Games")
    game_header = [str(cell) for cell in games[0]]
    game_index = {name: position for position, name in enumerate(game_header)}
    universe: list[dict[str, str]] = []
    component_names: set[str] = set(opening_teams)
    for row in games[1:]:
        if row[0] is None:
            continue
        home = str(row[game_index["home_team"]])
        away = str(row[game_index["away_team"]])
        component_names.update((home, away))
        universe.append(
            {
                "date": str(row[game_index["date"]]),
                "round": str(row[game_index["round"]]),
                "home_team": home,
                "away_team": away,
            }
        )

    readme = {}
    for row in _sheet_rows(workbook, "10 2025 README"):
        if row and row[0] is not None:
            readme[str(row[0])] = "" if len(row) < 2 or row[1] is None else str(row[1])

    declared_ledger_sha = readme.get("SHA-256 2025_Synthetic_Season_Games.csv", "")
    observed_ledger_sha = digest(SYNTHETIC_LEDGER_PATH)

    distinct = sorted(set(opening_values))
    return {
        "source_located": True,
        "source_path": str(TRUESKILL_PATH).replace("\\", "/"),
        "source_sha256": digest(TRUESKILL_PATH),
        "source_class": "SEASON_OPENING_PRIOR",
        "is_preseason": True,
        "opening_sheet": "14 2025 Rating History",
        "opening_teams": len(opening_teams),
        "opening_observations": len(opening_values),
        "opening_distinct_values": len(distinct),
        "opening_distinct_value_sample": distinct[:5],
        "opening_value_standard_deviation": (
            statistics.pstdev(opening_values) if len(opening_values) > 1 else 0.0
        ),
        "declared_initial_mu": readme.get("Initial mu", ""),
        "declared_initial_sigma": readme.get("Initial sigma", ""),
        "declared_games_processed": readme.get("Games processed", ""),
        "declared_teams_rated": readme.get("Teams rated", ""),
        "declared_ledger": "2025_Synthetic_Season_Games.csv",
        "declared_ledger_sha256": declared_ledger_sha,
        "observed_ledger_sha256": observed_ledger_sha,
        "ledger_digest_matches": bool(declared_ledger_sha)
        and declared_ledger_sha == observed_ledger_sha,
        "universe_games": len(universe),
        "universe": universe,
    }


def extract_litkenhous() -> dict:
    if not LITKENHOUS_PATH.exists():
        return {"source_located": False, "disposition": "NO_2025_SOURCE_LOCATED"}
    workbook = openpyxl.load_workbook(LITKENHOUS_PATH, read_only=True, data_only=True)
    sheets = list(workbook.sheetnames)
    first = _sheet_rows(workbook, sheets[0])
    return {
        "source_located": True,
        "source_path": str(LITKENHOUS_PATH).replace("\\", "/"),
        "source_sha256": digest(LITKENHOUS_PATH),
        "source_class": "SEASON_FINAL_RATING",
        "is_preseason": False,
        "artifact_title": LITKENHOUS_PATH.stem,
        "sheets": sheets,
        "first_sheet_header": [str(cell) for cell in first[0]] if first else [],
        "first_sheet_rows": max(len(first) - 1, 0),
        "refusal": (
            "The only located 2025 Litkenhous artifact is a season-final rating. "
            "A final rating is same-season information and cannot be an opening "
            "state for the season it summarises."
        ),
    }


def extract_baxter() -> dict:
    if not BAXTER_PATH.exists():
        return {"source_located": False, "disposition": "NO_2025_SOURCE_LOCATED"}
    with BAXTER_PATH.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    header = rows[0] if rows else []
    sample = rows[1:4]
    return {
        "source_located": True,
        "source_path": str(BAXTER_PATH).replace("\\", "/"),
        "source_sha256": digest(BAXTER_PATH),
        "source_class": "SAME_SEASON_FIT",
        "is_preseason": False,
        "header": header,
        "rows": max(len(rows) - 1, 0),
        "sample_rows": sample,
        "carries_games_played_column": any(
            column.strip().lower() == "games" for column in header
        ),
        "refusal": (
            "The located 2025 Pure Baxter artifact carries a games-played column. "
            "A count of games played is obtainable only after they are played, so "
            "the rating is a fit over the season it would have to precede."
        ),
    }


def extract_board_family() -> dict:
    """Scan the staged locations for any board artifact carrying a 2025 label."""
    scanned: list[str] = []
    board_files: list[dict[str, str]] = []
    for root in SEARCH_ROOTS:
        scanned.append(str(root).replace("\\", "/"))
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            name = path.name.lower()
            if "board" not in name:
                continue
            board_files.append(
                {
                    "path": str(path).replace("\\", "/"),
                    "season_label": (
                        "2025" if "2025" in name else "2026" if "2026" in name else "NONE"
                    ),
                }
            )
    labelled_2025 = [row for row in board_files if row["season_label"] == "2025"]
    return {
        "source_located": bool(labelled_2025),
        "is_preseason": False,
        "source_class": "NO_2025_ARTIFACT",
        "directories_scanned": scanned,
        "board_artifacts_found": len(board_files),
        "board_artifacts_labelled_2025": len(labelled_2025),
        "board_artifacts": board_files,
        "refusal": (
            "No located board artifact carries a 2025 label. The board series is "
            "2026-only across every file found in the scanned locations, so the "
            "board family has no 2025 opening value of any kind."
        ),
    }


def main() -> int:
    trueskill = extract_trueskill()
    families = {
        "TRUESKILL": trueskill,
        "LITKENHOUS": extract_litkenhous(),
        "PURE_BAXTER": extract_baxter(),
        "BOARD_FAMILY": extract_board_family(),
    }

    component_team_names: set[str] = set()
    universe = trueskill.get("universe", []) if isinstance(trueskill, dict) else []
    for game in universe:
        component_team_names.update((game["home_team"], game["away_team"]))

    extract = {
        "artifact": "V3_BRIDGE_2025_OPENING_COMPONENT_EXTRACT",
        "artifact_version": "V3-HISTORICAL-BRIDGE-CORPUS-R1",
        "artifact_class": "SYNTHETIC_UNIVERSE_EVIDENCE_EXTRACT_NOT_A_RATING_SOURCE",
        "families_required": [
            "TRUESKILL",
            "LITKENHOUS",
            "PURE_BAXTER",
            "BOARD_FAMILY",
        ],
        "families": families,
        "component_team_names": sorted(component_team_names),
        "component_universe_games": universe,
        "no_rating_value_is_promoted_by_this_extract": True,
    }
    EXTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXTRACT_PATH.write_text(
        json.dumps(extract, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"wrote {EXTRACT_PATH.relative_to(REPO_ROOT)}")
    for name, record in families.items():
        print(
            f"  {name:14s} located={record.get('source_located')}"
            f" preseason={record.get('is_preseason')}"
            f" distinct_opening_values={record.get('opening_distinct_values', '-')}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
