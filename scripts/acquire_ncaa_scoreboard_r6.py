"""Acquire the NCAA official scoreboard feed for the R6 observation corpus.

One job: pull raw bytes from a named authority and write them down unchanged,
with enough recorded about the pull that a reviewer can repeat it and compare.
Nothing here parses football. Normalisation, identity resolution and admission
all happen later, in
:mod:`ncaaf_engine.simulation.dynamic_weekly_mc_v3.observation_corpus`, against
the files this script writes.

The source is ``data.ncaa.com/casablanca``, the feed behind the NCAA's own
published scoreboard. It is the NCAA publishing its own results, which is tier 1
of the lane's source hierarchy, and it is addressable per season, per division
and per week, so a retrieval is a list of URLs rather than a crawl.

Two properties are load-bearing and are enforced here rather than described:

*Immutability.* A raw file is written once. Re-running against an existing
capture refuses instead of overwriting, because a raw source that can be
silently replaced cannot anchor a digest recorded against it.

*Byte fidelity.* Responses are stored gzipped, and the manifest records the
digest of the *decompressed* bytes alongside the digest of the container. The
container is what git stores; the decompressed digest is what custody is
asserted over. Gzip is not compression for its own sake: ``.gitattributes``
normalises ``*.json`` to LF on checkout, and a raw capture that a checkout can
rewrite is not a raw capture. ``.json.gz`` falls under the ``* -text`` rule and
is preserved byte for byte. ``mtime=0`` keeps the container itself
reproducible, so the same response gzips to the same file on any machine.

Both scoreboards are pulled for every week. The ``fbs`` and ``fcs`` feeds are
distinct game sets that overlap exactly on cross-division games, which is what
lets division be *read* from the source rather than inferred from a conference
name the author picked. That determination needs both sides, so both are
retrieved even though only one carries the FBS-versus-FBS games.

Usage::

    python scripts/acquire_ncaa_scoreboard_r6.py
    python scripts/acquire_ncaa_scoreboard_r6.py --seasons 2021 2022 --dry-run
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
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS_ROOT = (
    REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "observation_corpus_r6"
)
RAW_ROOT = CORPUS_ROOT / "raw" / "ncaa_scoreboard"
MANIFEST_PATH = CORPUS_ROOT / "V3_R6_SOURCE_ACQUISITION_MANIFEST.json"

SOURCE_AUTHORITY = "NCAA_OFFICIAL_SCOREBOARD_FEED"
SOURCE_AUTHORITY_CLASS = "GOVERNED_RESULT_SOURCE"
SOURCE_AUTHORITY_TIER = "TIER_1_NCAA_OFFICIAL"
BASE = "https://data.ncaa.com/casablanca/scoreboard/football"
USER_AGENT = "SYTHALAX-V3-R6-observation-corpus/1.0 (governed research retrieval)"

DEFAULT_SEASONS = (2021, 2022, 2023, 2024, 2025)
DIVISIONS = ("fbs", "fcs")
WEEKS = tuple(range(1, 20))

#: Politeness delay between requests, in seconds. The feed is a public CDN
#: object and this is a bounded sweep, but a governed retrieval should not look
#: like a scrape from the far end either.
REQUEST_DELAY_SECONDS = 0.25


def url_for(season: int, division: str, week: int) -> str:
    return f"{BASE}/{division}/{season}/{week:02d}/scoreboard.json"


def raw_path_for(season: int, division: str, week: int) -> Path:
    return RAW_ROOT / str(season) / division / f"wk{week:02d}.json.gz"


def gzip_deterministic(data: bytes) -> bytes:
    """Gzip ``data`` so the container is a function of the content alone."""
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as handle:
        handle.write(data)
    return buf.getvalue()


def fetch(url: str) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, b"", dict(exc.headers or {})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Acquire NCAA scoreboard raw sources.")
    parser.add_argument("--seasons", type=int, nargs="+", default=list(DEFAULT_SEASONS))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    records: list[dict[str, object]] = []
    absent: list[dict[str, object]] = []

    for season in args.seasons:
        for division in DIVISIONS:
            for week in WEEKS:
                url = url_for(season, division, week)
                target = raw_path_for(season, division, week)
                if target.exists():
                    print(f"  exists, not overwritten: {target.name} {season}/{division}")
                    continue
                status, body, headers = fetch(url)
                time.sleep(REQUEST_DELAY_SECONDS)
                if status != 200:
                    absent.append(
                        {
                            "url": url,
                            "season": season,
                            "division": division,
                            "week": week,
                            "http_status": status,
                            "disposition": "HTTP_NON_200_NOT_CAPTURED",
                        }
                    )
                    continue

                games = json.loads(body).get("games", [])
                container = gzip_deterministic(body)
                records.append(
                    {
                        "url": url,
                        "season": season,
                        "division": division,
                        "week": week,
                        "stored_path": str(target.relative_to(REPO_ROOT)).replace(
                            "\\", "/"
                        ),
                        "raw_sha256": hashlib.sha256(body).hexdigest(),
                        "raw_byte_length": len(body),
                        "stored_sha256": hashlib.sha256(container).hexdigest(),
                        "stored_byte_length": len(container),
                        "stored_encoding": "gzip",
                        "http_status": status,
                        "http_etag": headers.get("ETag", ""),
                        "http_last_modified": headers.get("Last-Modified", ""),
                        "http_content_type": headers.get("Content-Type", ""),
                        "retrieved_at": datetime.now(timezone.utc)
                        .replace(microsecond=0)
                        .isoformat(),
                        "source_authority": SOURCE_AUTHORITY,
                        "source_authority_class": SOURCE_AUTHORITY_CLASS,
                        "source_authority_tier": SOURCE_AUTHORITY_TIER,
                        "retrieval_method": "HTTP GET, urllib.request, no query parameters",
                        "retrieval_tool": f"python {sys.version.split()[0]} urllib.request",
                        "game_count": len(games),
                    }
                )
                if not args.dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(container)
                print(
                    f"  {season} {division} wk{week:02d}: {len(games):3d} games "
                    f"{len(body):7d} raw -> {len(container):6d} stored"
                )

    manifest = {
        "artifact": "V3_R6_SOURCE_ACQUISITION_MANIFEST.json",
        "artifact_status": "RAW_SOURCE_ACQUISITION_RECORD",
        "authority": "EXPERIMENTAL / NOT CANONICAL / NO PARAMETER PROMOTED",
        "source_authority": SOURCE_AUTHORITY,
        "source_authority_class": SOURCE_AUTHORITY_CLASS,
        "source_authority_tier": SOURCE_AUTHORITY_TIER,
        "source_base_url": BASE,
        "source_description": (
            "NCAA official scoreboard feed at data.ncaa.com/casablanca, the feed "
            "behind the NCAA's published scoreboard. Final scores, participants, "
            "scheduled start instants and NCAA game identifiers, published by the "
            "NCAA for its own site."
        ),
        "seasons": sorted(args.seasons),
        "divisions": list(DIVISIONS),
        "weeks_probed": list(WEEKS),
        "captured_files": sorted(
            records, key=lambda r: (r["season"], r["division"], r["week"])
        ),
        "absent_urls": sorted(
            absent, key=lambda r: (r["season"], r["division"], r["week"])
        ),
        "captured_file_count": len(records),
        "absent_url_count": len(absent),
        "immutability_rule": (
            "A captured raw file is never overwritten. This script refuses a "
            "target that already exists."
        ),
        "storage_rule": (
            "Responses are stored gzip-wrapped with mtime=0. raw_sha256 is the "
            "digest of the decompressed response body and is the digest custody "
            "is asserted over; stored_sha256 is the digest of the container git "
            "holds. .json.gz is byte-preserved by .gitattributes; .json is not."
        ),
    }
    if not args.dry_run:
        MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        MANIFEST_PATH.write_bytes(text.encode("utf-8"))
    print(f"\ncaptured {len(records)} files, {len(absent)} URLs absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
