"""Acquire season-specific subdivision membership declarations for 2020-2025.

Membership is a separate acquisition from results, and the separation is not
tidiness. A result feed can only ever show which teams *played*; it cannot show
which teams were *members*, and in 2020 those are demonstrably different sets --
Connecticut was an FBS member that played no game at all. Deriving membership
from participation would delete that team and report the deletion as a count.

So membership is retrieved as a declaration: ESPN publishes, per season, the set
of conferences that are children of a subdivision group -- 80 for FBS, 81 for
FCS -- and the set of teams that are members of each conference. The membership
of the subdivision is the union over those conferences. The roll-up is used
rather than the flat ``groups/80/teams`` list, because the flat list is not a
season membership: for 2024 it returns 144 entries where the conference roll-up
returns 134, and the extra entries are teams associated with the subdivision
across the surrounding seasons rather than members of that one.

Both subdivisions are retrieved because a game's division fields need two
statements, not one. Knowing a participant is not in the FBS set does not say it
is FCS; it says nothing at all about it. Retrieving the FCS set turns the second
half of every cross-division row from an absence into a declaration.

The URL list is retrieved in three phases, and only the first is static:

1. ``groups/{80,81}/children`` per season -- the conference set. Static.
2. one request per conference returned by phase 1, for the conference object
   (its name) and one for its member list. **Derived from phase 1's bytes.**
3. one request per member team id that phase 2 returned and that no retrieved
   scoreboard capture names, for the season-scoped team object. **Derived from
   phase 2's bytes and from the results acquisition.**

That the plan is derived rather than static is recorded in the manifest rather
than smoothed over, because a reviewer repeating this needs to know that phase 2
is reproducible only against the phase-1 bytes committed here.

Phase 3 exists because a team id is not a team. Names for teams that played are
already carried by the scoreboard captures; phase 3 covers exactly the members
that did not play, which is the case membership exists to make visible. It runs
for FBS only -- see the note at its call site.

Custody is identical to the results acquisition: write once, refuse to
overwrite, gzip with ``mtime=0``, and record both the container digest and the
digest of the decompressed response.

Usage::

    python scripts/acquire_membership_bridge_r1.py
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "historical_bridge_r1"
RAW_ROOT = BRIDGE_ROOT / "raw" / "espn_membership"
RESULTS_RAW_ROOT = BRIDGE_ROOT / "raw" / "espn_scoreboard"
MANIFEST_PATH = BRIDGE_ROOT / "V3_BRIDGE_MEMBERSHIP_ACQUISITION_MANIFEST.json"

AUTHORITY = "ESPN_SEASON_STRUCTURE_API"
TIER = "TIER_2_MEDIA_AGGREGATOR"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/college-football"
FBS_GROUP = "80"
FCS_GROUP = "81"
#: Both subdivisions are retrieved. FBS answers the population question; FCS is
#: what makes "this participant was not FBS" a *declaration* rather than the
#: absence of a declaration, which is the difference between a division field
#: and a guess dressed as one.
SUBDIVISION_GROUPS = ((FBS_GROUP, "FBS"), (FCS_GROUP, "FCS"))
SEASONS = (2020, 2021, 2022, 2023, 2024, 2025)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
REQUEST_DELAY_SECONDS = 0.25

#: The core API answers on http:// inside its own ``$ref`` values and on
#: https:// when asked. Requests are issued over https and the id is taken from
#: the ref rather than the scheme, so the transport never enters the identity.
REF_GROUP_ID = re.compile(r"/groups/(\d+)")
REF_TEAM_ID = re.compile(r"/teams/(\d+)")


def children_url(season: int, subdivision_group: str) -> str:
    return (
        f"{CORE}/seasons/{season}/types/2/groups/{subdivision_group}"
        "/children?limit=100"
    )


def group_url(season: int, group_id: str) -> str:
    return f"{CORE}/seasons/{season}/types/2/groups/{group_id}"


def group_teams_url(season: int, group_id: str) -> str:
    return f"{CORE}/seasons/{season}/types/2/groups/{group_id}/teams?limit=200"


def team_url(season: int, team_id: str) -> str:
    return f"{CORE}/seasons/{season}/teams/{team_id}"


def gzip_deterministic(data: bytes) -> bytes:
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(data)
    return buf.getvalue()


def fetch(url: str) -> tuple[int, bytes]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b""


def capture(
    url: str, target: Path, phase: str, season: int, records: list, absent: list
) -> dict | None:
    """Retrieve ``url`` once, or read back the capture already held."""
    if target.exists():
        return json.loads(gzip.open(target, "rb").read())

    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    status, body = fetch(url)
    time.sleep(REQUEST_DELAY_SECONDS)
    if status != 200 or not body:
        absent.append(
            {
                "source_authority": AUTHORITY,
                "phase": phase,
                "season": season,
                "url": url,
                "http_status": status,
                "retrieved_at": retrieved_at,
            }
        )
        print(f"  absent ({status}): {url}")
        return None

    container = gzip_deterministic(body)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(container)
    records.append(
        {
            "source_authority": AUTHORITY,
            "source_authority_tier": TIER,
            "phase": phase,
            "season": season,
            "url": url,
            "http_status": status,
            "retrieved_at": retrieved_at,
            "stored_path": str(target.relative_to(REPO_ROOT)).replace("\\", "/"),
            "raw_bytes": len(body),
            "raw_sha256": hashlib.sha256(body).hexdigest(),
            "stored_bytes": len(container),
            "stored_sha256": hashlib.sha256(container).hexdigest(),
        }
    )
    print(f"  captured {len(body):>7,} bytes: {target.relative_to(RAW_ROOT)}")
    return json.loads(body)


def team_ids_named_by_scoreboards() -> set[str]:
    """Every ESPN team id any retrieved scoreboard capture carries a name for."""
    named: set[str] = set()
    if not RESULTS_RAW_ROOT.exists():
        return named
    for path in sorted(RESULTS_RAW_ROOT.rglob("*.json.gz")):
        payload = json.loads(gzip.open(path, "rb").read())
        for event in payload.get("events", []):
            for competition in event.get("competitions", []):
                for competitor in competition.get("competitors", []):
                    team = competitor.get("team") or {}
                    if team.get("id") and team.get("displayName"):
                        named.add(str(team["id"]))
    return named


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Acquire season subdivision membership declarations, 2020-2025."
    )
    parser.add_argument("--seasons", type=int, nargs="+", default=list(SEASONS))
    args = parser.parse_args(argv)

    records: list[dict] = []
    absent: list[dict] = []
    already_named = team_ids_named_by_scoreboards()
    print(f"team ids already named by retrieved scoreboards: {len(already_named)}")

    for season in args.seasons:
        print(f"season {season}")
        season_root = RAW_ROOT / str(season)

        for subdivision_group, subdivision in SUBDIVISION_GROUPS:
            children = capture(
                children_url(season, subdivision_group),
                season_root / f"groups_{subdivision_group}_children.json.gz",
                "1_CONFERENCE_SET",
                season,
                records,
                absent,
            )
            if children is None:
                continue

            group_ids: list[str] = []
            for item in children.get("items", []):
                match = REF_GROUP_ID.search(item.get("$ref", ""))
                if match:
                    group_ids.append(match.group(1))

            member_ids: set[str] = set()
            for group_id in sorted(group_ids, key=int):
                capture(
                    group_url(season, group_id),
                    season_root / f"group_{group_id}.json.gz",
                    "2_CONFERENCE_OBJECT",
                    season,
                    records,
                    absent,
                )
                teams = capture(
                    group_teams_url(season, group_id),
                    season_root / f"group_{group_id}_teams.json.gz",
                    "2_CONFERENCE_MEMBERS",
                    season,
                    records,
                    absent,
                )
                if teams is None:
                    continue
                for item in teams.get("items", []):
                    match = REF_TEAM_ID.search(item.get("$ref", ""))
                    if match:
                        member_ids.add(match.group(1))

            unnamed = sorted(member_ids - already_named, key=int)
            print(
                f"  {subdivision}: members {len(member_ids)},"
                f" unnamed by scoreboards {len(unnamed)}"
            )
            # Phase 3 runs for FBS only. It exists to keep a *member* visible
            # when that member played no retrieved game, and the population
            # question this lane answers is an FBS one. Running it for FCS would
            # pull several hundred programs that never met an FBS opponent, none
            # of which any count here depends on.
            if subdivision_group != FBS_GROUP:
                continue
            for team_id in unnamed:
                capture(
                    team_url(season, team_id),
                    season_root / "teams" / f"{team_id}.json.gz",
                    "3_UNPLAYED_MEMBER_IDENTITY",
                    season,
                    records,
                    absent,
                )

    captured: list[dict] = records
    missing: list[dict] = absent
    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        captured = existing["captured"] + records
        missing = existing["absent"] + absent
    captured.sort(key=lambda row: (row["season"], row["stored_path"]))
    missing.sort(key=lambda row: (row["season"], row["url"]))

    manifest = {
        "artifact": "V3_BRIDGE_MEMBERSHIP_ACQUISITION_MANIFEST",
        "artifact_version": "V3-HISTORICAL-BRIDGE-CORPUS-R1",
        "source_authority": AUTHORITY,
        "source_authority_tier": TIER,
        "seasons": list(args.seasons),
        "subdivision_groups": [
            {"group_id": group_id, "subdivision": subdivision}
            for group_id, subdivision in SUBDIVISION_GROUPS
        ],
        "membership_rule": (
            "Subdivision membership for a season is the union of the member team "
            "ids of every conference that is a child of that subdivision's group "
            "in that season - 80 for FBS, 81 for FCS. The flat groups/80/teams "
            "listing is NOT used: it is not a season membership and returns a "
            "superset."
        ),
        "phases": [
            {
                "phase": "1_CONFERENCE_SET",
                "static": True,
                "url_pattern": (
                    f"{CORE}/seasons/{{season}}/types/2/groups/"
                    "{subdivision_group}/children?limit=100"
                ),
            },
            {
                "phase": "2_CONFERENCE_OBJECT",
                "static": False,
                "derived_from": "1_CONFERENCE_SET",
                "url_pattern": f"{CORE}/seasons/{{season}}/types/2/groups/{{group_id}}",
            },
            {
                "phase": "2_CONFERENCE_MEMBERS",
                "static": False,
                "derived_from": "1_CONFERENCE_SET",
                "url_pattern": (
                    f"{CORE}/seasons/{{season}}/types/2/groups/{{group_id}}"
                    "/teams?limit=200"
                ),
            },
            {
                "phase": "3_UNPLAYED_MEMBER_IDENTITY",
                "static": False,
                "applies_to_subdivision": "FBS",
                "derived_from": "2_CONFERENCE_MEMBERS and the scoreboard captures",
                "url_pattern": f"{CORE}/seasons/{{season}}/teams/{{team_id}}",
            },
        ],
        "captured_count": len(captured),
        "absent_count": len(missing),
        "captured": captured,
        "absent": missing,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"\ncaptured {manifest['captured_count']}, absent {manifest['absent_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
