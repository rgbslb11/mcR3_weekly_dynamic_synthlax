"""Acquire the raw sources the V3 historical venue/competition enrichment binds to.

Two feeds are pulled, and the split between them is the whole point of the lane.

*Identity anchor - NCAA official scoreboard.* ``data.ncaa.com/casablanca`` is the
NCAA publishing its own results. It is tier 1 of the lane's source hierarchy and
it is what the Historical Observation Corpus R6 is built from, so pulling it here
is what makes this enrichment joinable to that corpus on stable game identity
(``NCAA-<season>-<gameID>``) rather than on a name match. Both the ``fbs`` and
``fcs`` scoreboards are retrieved for every week because a game's division is
*read* from which feeds carry it, never guessed from a conference name.

*Venue evidence - ESPN college-football scoreboard.* The NCAA feed does not carry
venue. Not "carries it inconsistently": the field does not exist in the payload,
for any row, in any week of any season retrieved. That was established before
this script was written, and the sources above ESPN in the hierarchy were
established as unavailable rather than merely inconvenient:

* ``data.ncaa.com/casablanca/game/<id>/gameInfo.json`` - 404 for both identifier
  namespaces the scoreboard exposes (``gameID`` and the ``url`` contest id).
* ``www.ncaa.com/game/<id>`` - the venue element is present but empty in the
  served HTML; it is filled client-side.
* ``sdataprod.ncaa.com`` - the GraphQL gateway behind that fill. 403 Access
  Denied at the Akamai edge for any request this lane can make.
* ``stats.ncaa.org`` - 403 for the same reason.

So tiers 1 through 4 are exhausted for the venue fact specifically, which is the
condition the hierarchy attaches to using a tier-5 reproducible source. ESPN's
scoreboard states ``neutralSite`` as an explicit boolean and names the venue, the
city and the contest, and it is addressable per season/season-type/week, so a
retrieval is a list of URLs rather than a crawl. Its authority is recorded as
what it is - ``TIER_5_REPRODUCIBLE_SECONDARY`` - everywhere it is used, and
nothing in this lane promotes it above that.

The two immutability properties from the R6 acquisition are kept, for the same
reasons: a raw file is written once and re-running refuses rather than
overwrites, and responses are stored gzipped with ``mtime=0`` so the container is
a function of the content alone. The manifest records the digest of the
*decompressed* bytes next to the digest of the container; custody is asserted
over the former.

Usage::

    python scripts/acquire_venue_sources_r1.py
    python scripts/acquire_venue_sources_r1.py --seasons 2021 --dry-run
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LANE_ROOT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "venue_enrichment_r1"
RAW_ROOT = LANE_ROOT / "raw"
MANIFEST_PATH = LANE_ROOT / "V3_VENUE_R1_SOURCE_ACQUISITION_MANIFEST.json"

NCAA_AUTHORITY = "NCAA_OFFICIAL_SCOREBOARD_FEED"
NCAA_AUTHORITY_TIER = "TIER_1_NCAA_OFFICIAL"
NCAA_BASE = "https://data.ncaa.com/casablanca/scoreboard/football"

ESPN_AUTHORITY = "ESPN_COLLEGE_FOOTBALL_SCOREBOARD"
ESPN_AUTHORITY_TIER = "TIER_5_REPRODUCIBLE_SECONDARY"
ESPN_BASE = (
    "https://site.web.api.espn.com/apis/site/v2/sports/football/college-football/scoreboard"
)
#: ESPN group 80 is the FBS grouping. Recorded rather than inlined so the query
#: that produced the bytes is readable from the manifest alone.
ESPN_GROUP_FBS = "80"

USER_AGENT = "SYTHALAX-V3-venue-enrichment-r1/1.0 (governed research retrieval)"

DEFAULT_SEASONS = (2021, 2022, 2023, 2024)
NCAA_DIVISIONS = ("fbs", "fcs")
NCAA_WEEKS = tuple(range(1, 20))
#: ESPN season type 2 is the regular season - which is where ESPN's own model
#: puts conference championship games - and 3 is the postseason. Both are swept.
#: Which of them a matched game turns out to live in is a source fact the
#: enrichment reads, not an assumption made here.
ESPN_SEASON_TYPES = (2, 3)
ESPN_WEEKS = tuple(range(1, 18))

REQUEST_DELAY_SECONDS = 0.25


def ncaa_url(season: int, division: str, week: int) -> str:
    return f"{NCAA_BASE}/{division}/{season}/{week:02d}/scoreboard.json"


def ncaa_path(season: int, division: str, week: int) -> Path:
    return RAW_ROOT / "ncaa_scoreboard" / str(season) / division / f"wk{week:02d}.json.gz"


def espn_url(season: int, season_type: int, week: int) -> str:
    """Build the week query.

    No ``limit`` parameter, deliberately. Supplying one is not neutral: with
    ``limit=900`` the 2021-2023 weeks return their full slates but every 2024
    week returns exactly 25 events, silently truncated, while the identical
    query with the parameter removed returns 100. A parameter that is honoured
    for some seasons and swapped for a smaller default in others cannot anchor a
    capture, so it is not sent. Truncation is not merely avoided here, it is also
    detectable downstream: every NCAA game that fails to find an ESPN
    counterpart is reported as unmatched rather than dropped, so a short week
    would show up as a cluster of unmatched games rather than as silence.
    """
    return (
        f"{ESPN_BASE}?dates={season}&seasontype={season_type}"
        f"&week={week}&groups={ESPN_GROUP_FBS}"
    )


def espn_path(season: int, season_type: int, week: int) -> Path:
    return (
        RAW_ROOT / "espn_scoreboard" / str(season) / f"st{season_type}" / f"wk{week:02d}.json.gz"
    )


def gzip_deterministic(data: bytes) -> bytes:
    """Gzip ``data`` so the container is a function of the content alone."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(data)
    return buf.getvalue()


def fetch(url: str) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, b"", dict(exc.headers or {})


def payload_row_count(authority: str, data: bytes) -> int | None:
    """Count the rows the payload carries, for the manifest only.

    Recording this at retrieval is what lets a later reader tell an empty week
    apart from a week that failed to parse, without re-opening the bytes.
    """
    try:
        parsed = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        return None
    if authority == NCAA_AUTHORITY:
        games = parsed.get("games")
        return len(games) if isinstance(games, list) else None
    events = parsed.get("events")
    return len(events) if isinstance(events, list) else None


def acquire(
    *,
    url: str,
    target: Path,
    authority: str,
    authority_tier: str,
    locator: dict[str, object],
    dry_run: bool,
    records: list[dict[str, object]],
    absent: list[dict[str, object]],
) -> None:
    if target.exists():
        print(f"  exists, not overwritten: {target.relative_to(LANE_ROOT).as_posix()}")
        return
    if dry_run:
        print(f"  would fetch: {url}")
        return

    retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    status, body, headers = fetch(url)
    time.sleep(REQUEST_DELAY_SECONDS)

    if status != 200 or not body:
        absent.append(
            {
                "source_authority": authority,
                "source_locator": url,
                **locator,
                "http_status": status,
                "retrieved_at_utc": retrieved_at,
                "disposition": "ABSENT_NOT_WRITTEN",
            }
        )
        print(f"  absent ({status}): {url}")
        return

    container = gzip_deterministic(body)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(container)
    records.append(
        {
            "source_authority": authority,
            "source_authority_tier": authority_tier,
            "source_locator": url,
            **locator,
            "raw_path": target.relative_to(REPO_ROOT).as_posix(),
            "http_status": status,
            "http_content_type": headers.get("Content-Type", ""),
            "retrieved_at_utc": retrieved_at,
            "decompressed_byte_length": len(body),
            "decompressed_sha256": hashlib.sha256(body).hexdigest(),
            "container_byte_length": len(container),
            "container_sha256": hashlib.sha256(container).hexdigest(),
            "payload_row_count": payload_row_count(authority, body),
        }
    )
    rows = records[-1]["payload_row_count"]
    print(f"  wrote {target.relative_to(LANE_ROOT).as_posix()} rows={rows} bytes={len(body)}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire venue-enrichment raw sources.")
    parser.add_argument("--seasons", type=int, nargs="+", default=list(DEFAULT_SEASONS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    records: list[dict[str, object]] = []
    absent: list[dict[str, object]] = []

    for season in args.seasons:
        print(f"NCAA identity anchor {season}")
        for division in NCAA_DIVISIONS:
            for week in NCAA_WEEKS:
                acquire(
                    url=ncaa_url(season, division, week),
                    target=ncaa_path(season, division, week),
                    authority=NCAA_AUTHORITY,
                    authority_tier=NCAA_AUTHORITY_TIER,
                    locator={"season": season, "division": division, "week": week},
                    dry_run=args.dry_run,
                    records=records,
                    absent=absent,
                )

    for season in args.seasons:
        print(f"ESPN venue evidence {season}")
        for season_type in ESPN_SEASON_TYPES:
            for week in ESPN_WEEKS:
                acquire(
                    url=espn_url(season, season_type, week),
                    target=espn_path(season, season_type, week),
                    authority=ESPN_AUTHORITY,
                    authority_tier=ESPN_AUTHORITY_TIER,
                    locator={
                        "season": season,
                        "espn_season_type": season_type,
                        "week": week,
                        "espn_group": ESPN_GROUP_FBS,
                    },
                    dry_run=args.dry_run,
                    records=records,
                    absent=absent,
                )

    if args.dry_run:
        return 0

    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        records = list(existing.get("sources", [])) + records
        absent = list(existing.get("absent", [])) + absent

    records.sort(key=lambda record: str(record["raw_path"]))
    absent.sort(key=lambda record: str(record["source_locator"]))
    manifest = {
        "artifact": MANIFEST_PATH.name,
        "artifact_status": "SOURCE_ACQUISITION_MANIFEST",
        "lane": "V3_HISTORICAL_VENUE_ENRICHMENT_R1",
        "authority": (
            "EXPERIMENTAL / NOT CANONICAL / NO PARAMETER PROMOTED / NO BLOCKER RETIRED"
        ),
        "source_authorities": [
            {
                "source_authority": NCAA_AUTHORITY,
                "source_authority_tier": NCAA_AUTHORITY_TIER,
                "role": "GAME_IDENTITY_AND_SOURCE_ORIENTATION",
                "base_locator": NCAA_BASE,
                "carries_venue": False,
            },
            {
                "source_authority": ESPN_AUTHORITY,
                "source_authority_tier": ESPN_AUTHORITY_TIER,
                "role": "VENUE_GAME_TYPE_AND_KICKOFF_EVIDENCE",
                "base_locator": ESPN_BASE,
                "carries_venue": True,
                "used_because": (
                    "NCAA official venue endpoints are unavailable to this lane: "
                    "casablanca game detail 404, www.ncaa.com venue element filled "
                    "client-side, sdataprod.ncaa.com and stats.ncaa.org 403."
                ),
            },
        ],
        "user_agent": USER_AGENT,
        "request_delay_seconds": REQUEST_DELAY_SECONDS,
        "source_count": len(records),
        "absent_count": len(absent),
        "sources": records,
        "absent": absent,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"\nmanifest: {MANIFEST_PATH.relative_to(REPO_ROOT).as_posix()}")
    print(f"sources written: {len(records)}  absent: {len(absent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
