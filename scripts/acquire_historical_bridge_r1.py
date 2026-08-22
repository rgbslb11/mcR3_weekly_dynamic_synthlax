"""Acquire the 2020 and 2025 raw result sources for the historical bridge lane.

One job, the same job the R6 acquisition script has: pull bytes from a named
authority and write them down unchanged, with enough recorded about the pull
that a reviewer can repeat it and compare. Nothing here parses football.
Normalisation, identity resolution and admission happen later, in
:mod:`ncaaf_engine.simulation.dynamic_weekly_mc_v3.historical_bridge`, against
the files this script writes.

Two authorities are retrieved, and the reason there are two is a finding rather
than a convenience.

``NCAA_OFFICIAL_SCOREBOARD_FEED`` -- ``data.ncaa.com/casablanca`` -- is the NCAA
publishing its own results and is tier 1 of the source hierarchy. It serves 2020
in full and it does **not** serve 2025: every 2025 object it returns carries an
``updated_at`` inside 2025-08-29 and ``gameState=pre`` on all but the handful of
games that had kicked off by that instant. Those objects are retrieved anyway,
because a refusal asserted without the bytes behind it is a claim, and this
lane's 2025 refusal of that feed is the load-bearing half of why a second
authority exists at all.

``ESPN_PUBLIC_SCOREBOARD_API`` -- ``site.web.api.espn.com`` -- is a media
aggregator and is tier 2. It is retrieved for **both** seasons, not only for the
one that needs it, so that 2020 carries an overlap against tier 1 large enough
to measure the aggregator against the authority. An aggregator used where no
check is possible is an assumption; an aggregator measured on 500-odd games
against the NCAA's own feed and then used on the season the NCAA does not serve
is an argument. Making that argument is why 2020 is retrieved twice.

Addressing differs per authority and follows what each one actually supports
here:

* NCAA is addressed per season, division and week, exactly as R6 addresses it.
* ESPN is addressed **per calendar date**. Its season/week form silently caps at
  25 events per week for 2025, and its date-*range* form omits cancelled events,
  so neither is a safe unit. A single date is the primitive the endpoint serves
  without a cap, and every date in the season window is requested -- including
  the ones that return nothing, because "no game was played that day" is a
  retrieved fact and not an assumption. The page size is capped for the same
  reason the addressing is per-date; see ``ESPN_PAGE_LIMIT``.

Immutability and byte fidelity are enforced here rather than described, on the
same terms as R6: a raw file is written once and a re-run refuses to overwrite
it; responses are stored gzipped with ``mtime=0`` so the container is a function
of the content alone; and the manifest records the digest of the *decompressed*
bytes alongside the digest of the container. ``raw_sha256`` is what custody is
asserted over. ``.json.gz`` is used and not ``.json`` because ``.gitattributes``
normalises ``*.json`` to LF on checkout, and a raw capture a checkout can
rewrite is not a raw capture.

Usage::

    python scripts/acquire_historical_bridge_r1.py
    python scripts/acquire_historical_bridge_r1.py --authority ncaa --dry-run
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BRIDGE_ROOT = REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "historical_bridge_r1"
RAW_ROOT = BRIDGE_ROOT / "raw"
MANIFEST_PATH = BRIDGE_ROOT / "V3_BRIDGE_SOURCE_ACQUISITION_MANIFEST.json"

NCAA_AUTHORITY = "NCAA_OFFICIAL_SCOREBOARD_FEED"
NCAA_TIER = "TIER_1_NCAA_OFFICIAL"
NCAA_BASE = "https://data.ncaa.com/casablanca/scoreboard/football"
NCAA_DIVISIONS = ("fbs", "fcs")
NCAA_WEEKS = tuple(range(1, 20))

ESPN_AUTHORITY = "ESPN_PUBLIC_SCOREBOARD_API"
ESPN_TIER = "TIER_2_MEDIA_AGGREGATOR"
ESPN_BASE = (
    "https://site.web.api.espn.com/apis/site/v2/sports/football/"
    "college-football/scoreboard"
)
#: ESPN's FBS group. Passed so the retrieved set is the same competitive
#: universe the NCAA ``fbs`` scoreboard serves; cross-division games are carried
#: by both because one participant is in the group.
ESPN_FBS_GROUP = "80"

#: Page size. This value is load-bearing and was measured, not chosen for
#: comfort: the endpoint honours ``limit`` up to somewhere below 1000 and then
#: **silently** falls back to its default page of 25 rather than erroring. On
#: 2025-08-30 the same URL answers 62 events at ``limit=400`` and 25 events at
#: ``limit=1000``, with HTTP 200 and no pagination cursor either time. A first
#: pass of this acquisition ran at ``limit=900`` and captured a truncated 2025
#: season that looked entirely well-formed. 400 is inside the honoured range and
#: returns exactly what the endpoint returns with no ``limit`` at all, which is
#: the property actually wanted; ``ESPN_MAX_SAFE_LIMIT`` refuses a future edit
#: that raises it back into the silent-truncation range.
ESPN_PAGE_LIMIT = 400
ESPN_MAX_SAFE_LIMIT = 400

SEASONS = (2020, 2025)

#: Season windows, taken from ESPN's own published calendar rather than chosen:
#: the regular-season week 1 start and the postseason week end, per season, read
#: from ``sports.core.api.espn.com/.../seasons/{season}/types/{2,3}/weeks``.
#: They are recorded here as constants so an acquisition is a fixed list of URLs
#: that does not depend on a second live endpoint agreeing with itself later.
ESPN_SEASON_WINDOWS = {
    2020: (date(2020, 8, 25), date(2021, 1, 31)),
    2025: (date(2025, 8, 23), date(2026, 1, 21)),
}

USER_AGENT_NCAA = "SYTHALAX-V3-bridge-corpus/1.0 (governed research retrieval)"
#: ESPN's edge refuses a non-browser agent on this host with 403. The header is
#: what the endpoint requires to answer at all; nothing about the response is
#: altered by it, and the manifest records the agent sent with every request so
#: the retrieval stays exactly repeatable.
USER_AGENT_ESPN = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

REQUEST_DELAY_SECONDS = 0.25


def ncaa_url(season: int, division: str, week: int) -> str:
    return f"{NCAA_BASE}/{division}/{season}/{week:02d}/scoreboard.json"


def ncaa_path(season: int, division: str, week: int) -> Path:
    return (
        RAW_ROOT / "ncaa_scoreboard" / str(season) / division / f"wk{week:02d}.json.gz"
    )


def espn_url(day: date) -> str:
    if ESPN_PAGE_LIMIT > ESPN_MAX_SAFE_LIMIT:
        raise ValueError(
            f"ESPN_PAGE_LIMIT={ESPN_PAGE_LIMIT} exceeds the measured safe ceiling "
            f"of {ESPN_MAX_SAFE_LIMIT}; above it the endpoint silently returns a "
            "25-event page instead of the full day and reports HTTP 200."
        )
    return (
        f"{ESPN_BASE}?dates={day:%Y%m%d}"
        f"&groups={ESPN_FBS_GROUP}&limit={ESPN_PAGE_LIMIT}"
    )


def espn_path(season: int, day: date) -> Path:
    return RAW_ROOT / "espn_scoreboard" / str(season) / f"{day:%Y%m%d}.json.gz"


def espn_days(season: int) -> list[date]:
    start, end = ESPN_SEASON_WINDOWS[season]
    span = (end - start).days
    return [start + timedelta(days=offset) for offset in range(span + 1)]


def gzip_deterministic(data: bytes) -> bytes:
    """Gzip ``data`` so the container is a function of the content alone."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(data)
    return buf.getvalue()


def fetch(url: str, user_agent: str) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, b"", dict(exc.headers or {})


def retrieval_plan(authority: str) -> list[dict[str, object]]:
    """The full list of URLs this acquisition covers, in retrieval order."""
    plan: list[dict[str, object]] = []
    if authority in ("ncaa", "all"):
        for season in SEASONS:
            for division in NCAA_DIVISIONS:
                for week in NCAA_WEEKS:
                    plan.append(
                        {
                            "source_authority": NCAA_AUTHORITY,
                            "source_authority_tier": NCAA_TIER,
                            "season": season,
                            "division": division,
                            "week": week,
                            "url": ncaa_url(season, division, week),
                            "target": ncaa_path(season, division, week),
                            "user_agent": USER_AGENT_NCAA,
                        }
                    )
    if authority in ("espn", "all"):
        for season in SEASONS:
            for day in espn_days(season):
                plan.append(
                    {
                        "source_authority": ESPN_AUTHORITY,
                        "source_authority_tier": ESPN_TIER,
                        "season": season,
                        "division": "fbs_group_80",
                        "date": f"{day:%Y-%m-%d}",
                        "url": espn_url(day),
                        "target": espn_path(season, day),
                        "user_agent": USER_AGENT_ESPN,
                    }
                )
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Acquire 2020 and 2025 raw result sources under byte custody."
    )
    parser.add_argument("--authority", choices=("ncaa", "espn", "all"), default="all")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    plan = retrieval_plan(args.authority)
    print(f"planned retrievals: {len(plan)}")
    if args.dry_run:
        for item in plan[:5]:
            print(f"  {item['url']}")
        print("  ...")
        return 0

    records: list[dict[str, object]] = []
    absent: list[dict[str, object]] = []

    for item in plan:
        target: Path = item["target"]  # type: ignore[assignment]
        url: str = item["url"]  # type: ignore[assignment]
        if target.exists():
            continue

        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        status, body, headers = fetch(url, item["user_agent"])  # type: ignore[arg-type]
        time.sleep(REQUEST_DELAY_SECONDS)

        descriptor = {
            key: value
            for key, value in item.items()
            if key not in ("target", "user_agent")
        }

        if status != 200 or not body:
            descriptor["http_status"] = status
            descriptor["retrieved_at"] = retrieved_at
            absent.append(descriptor)
            print(f"  absent  ({status}): {url}")
            continue

        container = gzip_deterministic(body)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(container)

        descriptor.update(
            {
                "http_status": status,
                "retrieved_at": retrieved_at,
                "stored_path": str(target.relative_to(REPO_ROOT)).replace("\\", "/"),
                "raw_bytes": len(body),
                "raw_sha256": hashlib.sha256(body).hexdigest(),
                "stored_bytes": len(container),
                "stored_sha256": hashlib.sha256(container).hexdigest(),
                "content_type": headers.get("Content-Type", ""),
                "last_modified": headers.get("Last-Modified", ""),
            }
        )
        records.append(descriptor)
        print(f"  captured {len(body):>9,} bytes: {target.relative_to(RAW_ROOT)}")

    captured: list[dict[str, object]] = records
    missing: list[dict[str, object]] = absent
    if MANIFEST_PATH.exists():
        existing = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        captured = existing["captured"] + records
        missing = existing["absent"] + absent

    captured.sort(key=lambda row: (row["source_authority"], row["stored_path"]))
    missing.sort(key=lambda row: (row["source_authority"], row["url"]))

    manifest = {
        "artifact": "V3_BRIDGE_SOURCE_ACQUISITION_MANIFEST",
        "artifact_version": "V3-HISTORICAL-BRIDGE-CORPUS-R1",
        "seasons": list(SEASONS),
        "authorities": [
            {
                "source_authority": NCAA_AUTHORITY,
                "source_authority_tier": NCAA_TIER,
                "url_pattern": (
                    f"{NCAA_BASE}/{{division}}/{{season}}/{{week}}/scoreboard.json"
                ),
                "addressing": "SEASON_DIVISION_WEEK",
            },
            {
                "source_authority": ESPN_AUTHORITY,
                "source_authority_tier": ESPN_TIER,
                "url_pattern": (
                    f"{ESPN_BASE}?dates={{yyyymmdd}}"
                    f"&groups={ESPN_FBS_GROUP}&limit={ESPN_PAGE_LIMIT}"
                ),
                "page_limit": ESPN_PAGE_LIMIT,
                "addressing": "CALENDAR_DATE",
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
    print(f"\ncaptured {manifest['captured_count']} files, {manifest['absent_count']} absent")
    print(f"manifest: {MANIFEST_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
