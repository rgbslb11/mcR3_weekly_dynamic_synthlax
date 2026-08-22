"""The 2020 and 2025 historical results bridge.

This module turns the raw captures written by
``scripts/acquire_historical_bridge_r1.py`` and
``scripts/acquire_membership_bridge_r1.py`` into scored-game records, a
season-specific subdivision membership record, and the reconciliations that say
how far either can be trusted. It calibrates nothing, fits nothing, promotes
nothing and emits no rating.

Three things here are different from the R6 observation corpus, and each is a
decision rather than an accident.

**Identity is source-native first.** R6 resolved every participant through the
2026 canonical master and excluded the row when that failed, which cost it 934
rows across four seasons -- almost all of them real programs the *synthetic*
2026 universe does not carry. That is the right trade for a corpus destined for
a governed fit. It is the wrong trade for an evidence record whose whole purpose
is to say what really happened in 2020 and 2025: a real game between two real
programs is not less real because a synthetic 2026 master omits one of them.
So the key here is the source's own identifier, canonical binding is carried as
an *additional* column, and an unbound participant costs the row nothing.
:func:`canonical_binding_report` states the binding rate so the next lane knows
exactly how much of this corpus a canonical-only consumer can see.

**Division is a declaration, not an inference.** R6 read division from the
intersection of the NCAA's ``fbs`` and ``fcs`` scoreboards, which is sound where
both are served. It is unavailable for 2025, where the NCAA serves a stale
pre-season snapshot. Both seasons therefore take division from ESPN's per-season
subdivision membership -- the union of the member teams of every conference that
is a child of group 80 (FBS) or 81 (FCS) in that season. The 2020 season is
scored *both* ways and the two are compared, so the substitution is measured
rather than asserted.

**Cross-division games are admitted and flagged, not dropped.** The FCS point
scale is an open blocker and no fit may run over these rows; that is a
consumer's obligation and ``cross_division`` is the column that discharges it.
Deleting real observations from an evidence record to enforce a downstream rule
would make the record disagree with the season it describes.

The 2025 season has one further property that governs everything said about it:
the tier-1 NCAA feed does not serve it. :func:`ncaa_season_staleness_report`
establishes that from the bytes rather than from a claim, and every 2025 row
carries ``TIER_1_SOURCE_STALE_FOR_SEASON`` in its corroboration field, so no
consumer can read a 2025 row as tier-1 corroborated by forgetting to check.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Sequence

from .errors import InputValidationError

ARTIFACT_VERSION = "V3-HISTORICAL-BRIDGE-CORPUS-R1"

NCAA_AUTHORITY = "NCAA_OFFICIAL_SCOREBOARD_FEED"
NCAA_TIER = "TIER_1_NCAA_OFFICIAL"
ESPN_RESULTS_AUTHORITY = "ESPN_PUBLIC_SCOREBOARD_API"
ESPN_STRUCTURE_AUTHORITY = "ESPN_SEASON_STRUCTURE_API"
ESPN_TIER = "TIER_2_MEDIA_AGGREGATOR"

SEASONS = (2020, 2025)
MEMBERSHIP_SEASONS = (2020, 2021, 2022, 2023, 2024, 2025)

#: Corroboration states a bridge row can carry. They are three different facts
#: and collapsing them would be the whole failure this lane exists to avoid.
CORROBORATED = "CORROBORATED_BY_TIER_1"
NOT_CARRIED_BY_TIER_1 = "NOT_CARRIED_BY_TIER_1_FEED"
DISAGREES_WITH_TIER_1 = "DISAGREES_WITH_TIER_1"
TIER_1_STALE = "TIER_1_SOURCE_STALE_FOR_SEASON"

#: Exclusion reason codes. Every raw row not admitted carries exactly one, and
#: the counts reconcile against the raw total.
GAME_NOT_FINAL = "GAME_NOT_FINAL"
MISSING_SOURCE_GAME_IDENTIFIER = "MISSING_SOURCE_GAME_IDENTIFIER"
DUPLICATE_SOURCE_GAME_IDENTIFIER = "DUPLICATE_SOURCE_GAME_IDENTIFIER"
MISSING_SCORE = "MISSING_SCORE"
MISSING_PARTICIPANT = "MISSING_PARTICIPANT"
NO_FBS_PARTICIPANT = "NO_FBS_PARTICIPANT"
SEASON_OUT_OF_SCOPE = "SEASON_OUT_OF_SCOPE"

SUBDIVISION_FBS = "FBS"
SUBDIVISION_FCS = "FCS"
#: A participant in neither subdivision declaration. It is *not* rewritten to
#: FCS: the declarations cover Division I only, and a Division II or NAIA
#: opponent is a real thing an FBS team plays. Naming the state is the point.
SUBDIVISION_UNDECLARED = "NOT_IN_ANY_DIVISION_I_DECLARATION"


# --------------------------------------------------------------------------
# Raw custody
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RawCapture:
    """One retrieved response, re-derived from the bytes on disk."""

    source_authority: str
    source_authority_tier: str
    stored_path: str
    url: str
    season: int
    declared_raw_sha256: str
    observed_raw_sha256: str
    declared_stored_sha256: str
    observed_stored_sha256: str
    raw_bytes: int
    payload: dict
    descriptor: dict = field(default_factory=dict, repr=False)

    @property
    def custody_verified(self) -> bool:
        return (
            self.declared_raw_sha256 == self.observed_raw_sha256
            and self.declared_stored_sha256 == self.observed_stored_sha256
        )


def load_captures(manifest_path: Path, repo_root: Path) -> list[RawCapture]:
    """Re-read every capture the manifest declares and re-hash it.

    The manifest is not trusted as a record of what is on disk. Both digests are
    recomputed -- the container git holds and the response body inside it -- and
    a mismatch on either is raised rather than reported, because a custody chain
    that continues past a broken link is not a custody chain.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    captures: list[RawCapture] = []
    for row in manifest["captured"]:
        path = repo_root / row["stored_path"]
        if not path.exists():
            raise InputValidationError(
                f"declared capture is absent from disk: {row['stored_path']}"
            )
        container = path.read_bytes()
        body = gzip.decompress(container)
        capture = RawCapture(
            source_authority=row["source_authority"],
            source_authority_tier=row["source_authority_tier"],
            stored_path=row["stored_path"],
            url=row["url"],
            season=int(row["season"]),
            declared_raw_sha256=row["raw_sha256"],
            observed_raw_sha256=hashlib.sha256(body).hexdigest(),
            declared_stored_sha256=row["stored_sha256"],
            observed_stored_sha256=hashlib.sha256(container).hexdigest(),
            raw_bytes=len(body),
            payload=json.loads(body),
            descriptor=row,
        )
        if not capture.custody_verified:
            raise InputValidationError(
                "custody re-verification failed for "
                f"{row['stored_path']}: declared raw sha256 "
                f"{capture.declared_raw_sha256}, observed "
                f"{capture.observed_raw_sha256}"
            )
        captures.append(capture)
    return captures


# --------------------------------------------------------------------------
# Subdivision membership
# --------------------------------------------------------------------------

_REF_GROUP_ID = re.compile(r"/groups/(\d+)")
_REF_TEAM_ID = re.compile(r"/teams/(\d+)")

FBS_GROUP_ID = "80"
FCS_GROUP_ID = "81"
_SUBDIVISION_BY_GROUP = {FBS_GROUP_ID: SUBDIVISION_FBS, FCS_GROUP_ID: SUBDIVISION_FCS}


@dataclass(frozen=True)
class SeasonMembership:
    """Which teams a season's subdivision declarations name as members."""

    season: int
    subdivision_by_team: dict[str, str]
    conference_by_team: dict[str, str]
    conference_names: dict[str, str]
    members: dict[str, tuple[str, ...]]

    def subdivision(self, team_id: str) -> str:
        return self.subdivision_by_team.get(str(team_id), SUBDIVISION_UNDECLARED)

    def conference(self, team_id: str) -> str:
        return self.conference_by_team.get(str(team_id), "")

    def count(self, subdivision: str) -> int:
        return len(self.members.get(subdivision, ()))


def load_membership(manifest_path: Path, repo_root: Path) -> dict[int, SeasonMembership]:
    """Build per-season subdivision membership from the retrieved declarations.

    Membership is the union over the conferences that are *children of the
    subdivision group in that season*. The flat ``groups/80/teams`` listing is
    never consulted; it is not a season membership and returns a superset.
    """
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    by_path = {row["stored_path"]: row for row in manifest["captured"]}
    payloads: dict[str, dict] = {}
    for stored_path in by_path:
        path = repo_root / stored_path
        body = gzip.decompress(path.read_bytes())
        if hashlib.sha256(body).hexdigest() != by_path[stored_path]["raw_sha256"]:
            raise InputValidationError(
                f"custody re-verification failed for {stored_path}"
            )
        payloads[stored_path] = json.loads(body)

    seasons: dict[int, SeasonMembership] = {}
    for season in sorted({int(row["season"]) for row in manifest["captured"]}):
        prefix = (
            "reference/dynamic_weekly_mc_v3/historical_bridge_r1/raw/"
            f"espn_membership/{season}/"
        )
        subdivision_by_team: dict[str, str] = {}
        conference_by_team: dict[str, str] = {}
        conference_names: dict[str, str] = {}
        members: dict[str, list[str]] = {}

        for group_id, subdivision in _SUBDIVISION_BY_GROUP.items():
            children_path = f"{prefix}groups_{group_id}_children.json.gz"
            if children_path not in payloads:
                continue
            conference_ids = [
                match.group(1)
                for item in payloads[children_path].get("items", [])
                if (match := _REF_GROUP_ID.search(item.get("$ref", "")))
            ]
            for conference_id in sorted(conference_ids, key=int):
                conference_object = payloads.get(f"{prefix}group_{conference_id}.json.gz")
                if conference_object is not None:
                    conference_names[conference_id] = conference_object.get("name", "")
                teams = payloads.get(f"{prefix}group_{conference_id}_teams.json.gz")
                if teams is None:
                    continue
                for item in teams.get("items", []):
                    match = _REF_TEAM_ID.search(item.get("$ref", ""))
                    if not match:
                        continue
                    team_id = match.group(1)
                    if team_id in subdivision_by_team:
                        # One team, two subdivisions in one season is not a
                        # thing the source may assert without someone deciding
                        # which is true, and nothing here is entitled to decide.
                        if subdivision_by_team[team_id] != subdivision:
                            raise InputValidationError(
                                f"team {team_id} is declared in both "
                                f"{subdivision_by_team[team_id]} and {subdivision} "
                                f"for season {season}"
                            )
                        continue
                    subdivision_by_team[team_id] = subdivision
                    conference_by_team[team_id] = conference_names.get(
                        conference_id, conference_id
                    )
                    members.setdefault(subdivision, []).append(team_id)

        seasons[season] = SeasonMembership(
            season=season,
            subdivision_by_team=subdivision_by_team,
            conference_by_team=conference_by_team,
            conference_names=conference_names,
            members={
                key: tuple(sorted(value, key=int)) for key, value in members.items()
            },
        )
    return seasons


def membership_team_names(captures: Iterable[RawCapture]) -> dict[str, str]:
    """Team id to display name, from whichever captures name the team.

    Scoreboard captures name every team that played. The season-scoped team
    objects retrieved in acquisition phase 3 name the FBS members that did not,
    which for 2020 is the case that matters: a member with no game is still a
    member and must not vanish from a population count.
    """
    names: dict[str, str] = {}
    for capture in captures:
        payload = capture.payload
        for event in payload.get("events", []):
            for competition in event.get("competitions", []):
                for competitor in competition.get("competitors", []):
                    team = competitor.get("team") or {}
                    if team.get("id") and team.get("displayName"):
                        names.setdefault(str(team["id"]), team["displayName"])
        if payload.get("id") and payload.get("displayName") and "items" not in payload:
            names.setdefault(str(payload["id"]), payload["displayName"])
    return names


# --------------------------------------------------------------------------
# Normalisation: ESPN
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BridgeGame:
    """One real scored game, in the fields this lane is asked to establish."""

    game_id: str
    season: int
    season_type: str
    week: int
    kickoff_utc: str
    kickoff_epoch: int
    home_team_id: str
    home_team_name: str
    home_team_school: str
    away_team_id: str
    away_team_name: str
    away_team_school: str
    home_points: int
    away_points: int
    home_margin: int
    home_division: str
    away_division: str
    home_conference: str
    away_conference: str
    cross_division: bool
    neutral_site: bool
    venue_name: str
    venue_city: str
    venue_state: str
    competition_type: str
    conference_competition: bool
    overtime: bool
    source_authority: str
    source_authority_tier: str
    source_url: str
    source_raw_sha256: str
    tier_1_corroboration: str

    def as_row(self) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "season": self.season,
            "season_type": self.season_type,
            "week": self.week,
            "kickoff_utc": self.kickoff_utc,
            "kickoff_epoch": self.kickoff_epoch,
            "home_team_id": self.home_team_id,
            "home_team_name": self.home_team_name,
            "home_team_school": self.home_team_school,
            "away_team_id": self.away_team_id,
            "away_team_name": self.away_team_name,
            "away_team_school": self.away_team_school,
            "home_points": self.home_points,
            "away_points": self.away_points,
            "home_margin": self.home_margin,
            "home_division": self.home_division,
            "away_division": self.away_division,
            "home_conference": self.home_conference,
            "away_conference": self.away_conference,
            "cross_division": self.cross_division,
            "neutral_site": self.neutral_site,
            "venue_name": self.venue_name,
            "venue_city": self.venue_city,
            "venue_state": self.venue_state,
            "competition_type": self.competition_type,
            "conference_competition": self.conference_competition,
            "overtime": self.overtime,
            "source_authority": self.source_authority,
            "source_authority_tier": self.source_authority_tier,
            "source_url": self.source_url,
            "source_raw_sha256": self.source_raw_sha256,
            "tier_1_corroboration": self.tier_1_corroboration,
        }


BRIDGE_COLUMNS: tuple[str, ...] = (
    "game_id",
    "season",
    "season_type",
    "week",
    "kickoff_utc",
    "kickoff_epoch",
    "home_team_id",
    "home_team_name",
    "home_team_school",
    "away_team_id",
    "away_team_name",
    "away_team_school",
    "home_points",
    "away_points",
    "home_margin",
    "home_division",
    "away_division",
    "home_conference",
    "away_conference",
    "cross_division",
    "neutral_site",
    "venue_name",
    "venue_city",
    "venue_state",
    "competition_type",
    "conference_competition",
    "overtime",
    "source_authority",
    "source_authority_tier",
    "source_url",
    "source_raw_sha256",
    "tier_1_corroboration",
)

_SEASON_TYPE_NAMES = {1: "PRESEASON", 2: "REGULAR_SEASON", 3: "POSTSEASON", 4: "OFF_SEASON"}


def _iso_utc(value: str) -> tuple[str, int]:
    """ESPN publishes ``2020-10-03T00:00Z``. Return it normalised, plus epoch."""
    text = value.replace("Z", "+00:00")
    moment = datetime.fromisoformat(text).astimezone(timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ"), int(moment.timestamp())


def parse_espn_capture(capture: RawCapture) -> list[dict]:
    """Flatten one ESPN scoreboard capture into per-event descriptors."""
    events: list[dict] = []
    for event in capture.payload.get("events", []):
        competitions = event.get("competitions") or []
        if not competitions:
            continue
        competition = competitions[0]
        competitors = {
            competitor.get("homeAway"): competitor
            for competitor in competition.get("competitors", [])
        }
        status = (competition.get("status") or {}).get("type") or {}
        venue = competition.get("venue") or {}
        address = venue.get("address") or {}
        notes = competition.get("notes") or []
        events.append(
            {
                "event_id": str(event.get("id") or ""),
                "season_year": int((event.get("season") or {}).get("year") or 0),
                "season_type": int((event.get("season") or {}).get("type") or 0),
                "week": int((event.get("week") or {}).get("number") or 0),
                "date": event.get("date") or "",
                "status_name": status.get("name") or "",
                "status_completed": bool(status.get("completed")),
                "status_detail": status.get("detail") or "",
                "period": (competition.get("status") or {}).get("period"),
                "home": competitors.get("home"),
                "away": competitors.get("away"),
                "neutral_site": bool(competition.get("neutralSite")),
                "conference_competition": bool(competition.get("conferenceCompetition")),
                "note_headline": (notes[0].get("headline") if notes else "") or "",
                "venue_name": venue.get("fullName") or "",
                "venue_city": address.get("city") or "",
                "venue_state": address.get("state") or "",
                "capture": capture,
            }
        )
    return events


def _competition_type(descriptor: dict) -> str:
    """What kind of game this is, in the source's own terms.

    ESPN states the season type and, for a postseason game, a headline naming
    the bowl or playoff round. Nothing is inferred beyond that: a regular-season
    game with a conference-championship headline would be reported with that
    headline, and a bare regular-season game is reported as one.
    """
    season_type = _SEASON_TYPE_NAMES.get(descriptor["season_type"], "UNKNOWN")
    headline = descriptor["note_headline"].strip()
    if headline:
        return f"{season_type}:{headline}"
    return season_type


def _is_overtime(descriptor: dict) -> bool:
    """Overtime is read from the source's period count, never from the margin."""
    period = descriptor.get("period")
    return isinstance(period, (int, float)) and int(period) > 4


def build_bridge_games(
    captures: Sequence[RawCapture],
    membership: dict[int, SeasonMembership],
    season: int,
) -> tuple[list[BridgeGame], list[dict]]:
    """Admit the real scored games of ``season``; refuse the rest with a reason."""
    season_membership = membership.get(season)
    if season_membership is None:
        raise InputValidationError(f"no membership declaration loaded for {season}")

    admitted: dict[str, BridgeGame] = {}
    exclusions: list[dict] = []
    seen: dict[str, str] = {}

    descriptors: list[dict] = []
    for capture in captures:
        if capture.source_authority != ESPN_RESULTS_AUTHORITY:
            continue
        if capture.season != season:
            continue
        descriptors.extend(parse_espn_capture(capture))

    def refuse(descriptor: dict, reason: str, detail: str = "") -> None:
        exclusions.append(
            {
                "season": season,
                "event_id": descriptor.get("event_id", ""),
                "date": descriptor.get("date", ""),
                "reason": reason,
                "detail": detail,
                "source_url": descriptor["capture"].url,
                "source_raw_sha256": descriptor["capture"].declared_raw_sha256,
            }
        )

    for descriptor in sorted(
        descriptors, key=lambda item: (item["date"], item["event_id"])
    ):
        if descriptor["season_year"] != season:
            refuse(descriptor, SEASON_OUT_OF_SCOPE, str(descriptor["season_year"]))
            continue
        if not descriptor["event_id"]:
            refuse(descriptor, MISSING_SOURCE_GAME_IDENTIFIER)
            continue
        if not (descriptor["status_name"] == "STATUS_FINAL" and descriptor["status_completed"]):
            refuse(descriptor, GAME_NOT_FINAL, descriptor["status_name"])
            continue

        home, away = descriptor["home"], descriptor["away"]
        if not home or not away:
            refuse(descriptor, MISSING_PARTICIPANT)
            continue
        home_team = home.get("team") or {}
        away_team = away.get("team") or {}
        if not home_team.get("id") or not away_team.get("id"):
            refuse(descriptor, MISSING_PARTICIPANT)
            continue
        try:
            home_points = int(home.get("score"))
            away_points = int(away.get("score"))
        except (TypeError, ValueError):
            refuse(descriptor, MISSING_SCORE)
            continue

        game_id = f"ESPN-{season}-{descriptor['event_id']}"
        if game_id in seen:
            # The same event id retrieved twice is one game published twice, not
            # two games. Both are refused rather than one silently kept: nothing
            # here can say which retrieval is the true one.
            refuse(descriptor, DUPLICATE_SOURCE_GAME_IDENTIFIER, seen[game_id])
            admitted.pop(game_id, None)
            continue
        seen[game_id] = descriptor["capture"].stored_path

        home_id = str(home_team["id"])
        away_id = str(away_team["id"])
        home_division = season_membership.subdivision(home_id)
        away_division = season_membership.subdivision(away_id)
        if SUBDIVISION_FBS not in (home_division, away_division):
            refuse(
                descriptor,
                NO_FBS_PARTICIPANT,
                f"{home_division}/{away_division}",
            )
            continue

        kickoff_utc, kickoff_epoch = _iso_utc(descriptor["date"])
        admitted[game_id] = BridgeGame(
            game_id=game_id,
            season=season,
            season_type=_SEASON_TYPE_NAMES.get(descriptor["season_type"], "UNKNOWN"),
            week=descriptor["week"],
            kickoff_utc=kickoff_utc,
            kickoff_epoch=kickoff_epoch,
            home_team_id=home_id,
            home_team_name=home_team.get("displayName") or "",
            home_team_school=home_team.get("location") or "",
            away_team_id=away_id,
            away_team_name=away_team.get("displayName") or "",
            away_team_school=away_team.get("location") or "",
            home_points=home_points,
            away_points=away_points,
            home_margin=home_points - away_points,
            home_division=home_division,
            away_division=away_division,
            home_conference=season_membership.conference(home_id),
            away_conference=season_membership.conference(away_id),
            cross_division=home_division != away_division,
            neutral_site=descriptor["neutral_site"],
            venue_name=descriptor["venue_name"],
            venue_city=descriptor["venue_city"],
            venue_state=descriptor["venue_state"],
            competition_type=_competition_type(descriptor),
            conference_competition=descriptor["conference_competition"],
            overtime=_is_overtime(descriptor),
            source_authority=ESPN_RESULTS_AUTHORITY,
            source_authority_tier=ESPN_TIER,
            source_url=descriptor["capture"].url,
            source_raw_sha256=descriptor["capture"].declared_raw_sha256,
            tier_1_corroboration=NOT_CARRIED_BY_TIER_1,
        )

    games = sorted(admitted.values(), key=lambda game: (game.kickoff_epoch, game.game_id))
    return games, exclusions


# --------------------------------------------------------------------------
# Normalisation: NCAA
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NcaaGame:
    """One row of the NCAA scoreboard, as the NCAA published it."""

    season: int
    division_feed: str
    week: int
    game_id: str
    start_date: str
    start_epoch: int
    game_state: str
    final_message: str
    home_name: str
    home_char6: str
    home_score: str
    away_name: str
    away_char6: str
    away_score: str
    source_url: str
    source_raw_sha256: str
    updated_at: str


def parse_ncaa_capture(capture: RawCapture) -> list[NcaaGame]:
    payload = capture.payload
    updated_at = payload.get("updated_at") or ""
    descriptor = capture.descriptor
    rows: list[NcaaGame] = []
    for wrapper in payload.get("games", []):
        game = wrapper.get("game") or {}
        home = game.get("home") or {}
        away = game.get("away") or {}
        try:
            start_epoch = int(game.get("startTimeEpoch") or 0)
        except (TypeError, ValueError):
            start_epoch = 0
        rows.append(
            NcaaGame(
                season=capture.season,
                division_feed=str(descriptor.get("division", "")),
                week=int(descriptor.get("week", 0) or 0),
                game_id=str(game.get("gameID") or ""),
                start_date=str(game.get("startDate") or ""),
                start_epoch=start_epoch,
                game_state=str(game.get("gameState") or ""),
                final_message=str(game.get("finalMessage") or ""),
                home_name=str((home.get("names") or {}).get("short") or ""),
                home_char6=str((home.get("names") or {}).get("char6") or ""),
                home_score=str(home.get("score") or ""),
                away_name=str((away.get("names") or {}).get("short") or ""),
                away_char6=str((away.get("names") or {}).get("char6") or ""),
                away_score=str(away.get("score") or ""),
                source_url=capture.url,
                source_raw_sha256=capture.declared_raw_sha256,
                updated_at=updated_at,
            )
        )
    return rows


def ncaa_season_staleness_report(
    captures: Sequence[RawCapture], season: int
) -> dict[str, object]:
    """Whether the tier-1 feed actually serves ``season``, measured from bytes.

    A feed that answers HTTP 200 with well-formed objects is not thereby serving
    the season: 2025 answers 878 games of which 852 carry ``gameState=pre`` and
    blank scores, in files whose own ``updated_at`` predates almost every game
    in them. That is a pre-season snapshot that was never refreshed, and reusing
    it as completed history is the specific error this report exists to prevent.
    """
    rows = [
        row
        for capture in captures
        if capture.source_authority == NCAA_AUTHORITY and capture.season == season
        for row in parse_ncaa_capture(capture)
    ]
    states: dict[str, int] = {}
    for row in rows:
        states[row.game_state] = states.get(row.game_state, 0) + 1
    updated = sorted({row.updated_at for row in rows if row.updated_at})
    scored = sum(1 for row in rows if row.game_state == "final" and row.home_score)
    total = len(rows)
    final_share = scored / total if total else 0.0

    # The diagnostic is not "how many rows are final". A COVID season is full of
    # postponements and a real feed still serves it. The diagnostic is whether
    # the feed's own last update predates the games it is publishing: a file
    # stamped 2025-08-29 cannot be reporting a game played in November, whatever
    # its status field says.
    stale_rows = sum(1 for row in rows if _update_predates_kickoff(row))
    stale_share = stale_rows / total if total else 0.0
    serves = total > 0 and stale_share < 0.5
    by_feed: dict[str, dict[str, object]] = {}
    for feed in sorted({row.division_feed for row in rows}):
        feed_rows = [row for row in rows if row.division_feed == feed]
        feed_states: dict[str, int] = {}
        for row in feed_rows:
            feed_states[row.game_state] = feed_states.get(row.game_state, 0) + 1
        by_feed[feed] = {
            "rows_published": len(feed_rows),
            "game_state_counts": dict(sorted(feed_states.items())),
            "rows_whose_feed_update_predates_kickoff": sum(
                1 for row in feed_rows if _update_predates_kickoff(row)
            ),
        }

    return {
        "season": season,
        "source_authority": NCAA_AUTHORITY,
        "source_authority_tier": NCAA_TIER,
        "rows_published": total,
        "by_division_feed": by_feed,
        "game_state_counts": dict(sorted(states.items())),
        "scored_final_rows": scored,
        "scored_share": round(final_share, 6),
        "rows_whose_feed_update_predates_kickoff": stale_rows,
        "stale_share": round(stale_share, 6),
        "feed_updated_at_values": updated,
        "serves_completed_season": serves,
        "disposition": (
            "TIER_1_SERVES_SEASON"
            if serves
            else "TIER_1_FEED_STALE_REFUSED_AS_COMPLETED_HISTORY"
        ),
    }


def _update_predates_kickoff(row: NcaaGame) -> bool:
    """Whether the file publishing this row was last written before it kicked off."""
    if not row.updated_at or not row.start_date:
        return False
    try:
        month, day, year_and_time = row.updated_at.split("-", 2)
        year = year_and_time.split(" ", 1)[0]
        updated = datetime(int(year), int(month), int(day), tzinfo=timezone.utc)
        start_month, start_day, start_year = row.start_date.split("-")
        started = datetime(
            int(start_year), int(start_month), int(start_day), tzinfo=timezone.utc
        )
    except (ValueError, IndexError):
        return False
    return updated < started


# --------------------------------------------------------------------------
# Name bridging between the two authorities
# --------------------------------------------------------------------------

#: NCAA house-style abbreviations, expanded so an NCAA short name can be
#: compared with an ESPN team location. Each entry is a whole-token rule: a
#: wrong expansion yields no match rather than a wrong match, which is the only
#: safe failure mode for a name bridge.
NCAA_TOKEN_EXPANSIONS: dict[str, str] = {
    "st.": "state",
    "st": "state",
    "ga.": "georgia",
    "fla.": "florida",
    "miss.": "mississippi",
    "ala.": "alabama",
    "ark.": "arkansas",
    "ariz.": "arizona",
    "calif.": "california",
    "colo.": "colorado",
    "conn.": "connecticut",
    "ill.": "illinois",
    "ind.": "indiana",
    "ky.": "kentucky",
    "la.": "louisiana",
    "mass.": "massachusetts",
    "md.": "maryland",
    "mich.": "michigan",
    "minn.": "minnesota",
    "mo.": "missouri",
    "n.c.": "north carolina",
    "n.m.": "new mexico",
    "neb.": "nebraska",
    "okla.": "oklahoma",
    "ore.": "oregon",
    "pa.": "pennsylvania",
    "s.c.": "south carolina",
    "tenn.": "tennessee",
    "tex.": "texas",
    "va.": "virginia",
    "wash.": "washington",
    "wis.": "wisconsin",
    "w.va.": "west virginia",
}


def normalise_name(text: str) -> str:
    """Fold a team name to a comparison key.

    Case, accents, punctuation and inter-word spacing are removed because they
    are typographic. Nothing that distinguishes two programs is removed: the
    parenthesised qualifier in ``Miami (FL)`` is kept, because a rule that drops
    it also folds ``Miami (OH)`` onto the same key.
    """
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.lower().strip()
    tokens = [NCAA_TOKEN_EXPANSIONS.get(token, token) for token in folded.split()]
    folded = " ".join(tokens)
    folded = re.sub(r"[^a-z0-9()]+", "", folded)
    return folded


@dataclass(frozen=True)
class NameBridge:
    """A mapping between NCAA team names and ESPN team ids, and its holes."""

    espn_id_by_key: dict[str, str]
    espn_name_by_id: dict[str, str]
    unmatched_ncaa_names: tuple[str, ...]
    ambiguous_keys: tuple[str, ...]

    def resolve(self, ncaa_name: str, ncaa_char6: str = "") -> str | None:
        """Resolve an NCAA participant, trying its name and then its own code."""
        for candidate in (ncaa_name, ncaa_char6):
            if not candidate:
                continue
            team_id = self.espn_id_by_key.get(normalise_name(candidate))
            if team_id is not None:
                return team_id
        return None


def espn_team_keys(captures: Sequence[RawCapture]) -> dict[str, tuple[str, ...]]:
    """Every name ESPN itself publishes for each team, folded to keys.

    The keys are the source's own fields -- ``displayName``, ``location``,
    ``shortDisplayName``, ``abbreviation``, ``name`` -- and nothing derived from
    them. An earlier revision of this function generated every proper prefix of
    the display name on the theory that the school part is a prefix. It is, and
    so is a *different school's* name: ``Arizona`` is a prefix of both
    ``Arizona Wildcats`` and ``Arizona State Sun Devils``, and the collision
    rule below then correctly discarded the key and silently unbridged Arizona,
    Michigan, Ohio, Oregon, Washington, Texas and a dozen more. Using the
    published ``location`` instead makes ``Arizona`` and ``Arizona State`` two
    keys that were never in conflict.
    """
    keys_by_team: dict[str, set[str]] = {}
    for capture in captures:
        for event in capture.payload.get("events", []):
            for competition in event.get("competitions", []):
                for competitor in competition.get("competitors", []):
                    team = competitor.get("team") or {}
                    team_id = str(team.get("id") or "")
                    if not team_id:
                        continue
                    bucket = keys_by_team.setdefault(team_id, set())
                    for field_name in (
                        "displayName",
                        "location",
                        "shortDisplayName",
                        "abbreviation",
                        "name",
                    ):
                        value = team.get(field_name)
                        if not value:
                            continue
                        folded = normalise_name(str(value))
                        if folded:
                            bucket.add(folded)
    return {
        team_id: tuple(sorted(keys)) for team_id, keys in sorted(keys_by_team.items())
    }


def build_name_bridge(
    keys_by_team: dict[str, tuple[str, ...]],
    names_by_team: dict[str, str],
    ncaa_rows: Sequence[NcaaGame],
) -> NameBridge:
    """Bridge the two authorities by exact match on a folded key.

    Exact-after-folding, and nothing else. No nearest match, no token subset, no
    edit distance: a fuzzy bridge between two lists of school names will always
    find something to pair, and the pairings it invents are indistinguishable
    from the ones it finds. An unmatched name is carried out as unmatched.

    A key two ESPN teams both answer to identifies neither and is discarded --
    ``MIA`` is published as the abbreviation of Miami (FL) and of Miami (OH),
    and resolving it to either would be a coin toss with a school's results on
    it.
    """
    espn_id_by_key: dict[str, str] = {}
    collisions: set[str] = set()
    for team_id, keys in sorted(keys_by_team.items()):
        for key in keys:
            held = espn_id_by_key.get(key)
            if held is not None and held != team_id:
                collisions.add(key)
            espn_id_by_key[key] = team_id
    for key in collisions:
        espn_id_by_key.pop(key, None)

    bridge = NameBridge(
        espn_id_by_key=espn_id_by_key,
        espn_name_by_id=dict(names_by_team),
        unmatched_ncaa_names=(),
        ambiguous_keys=tuple(sorted(collisions)),
    )

    unmatched: set[str] = set()
    for row in ncaa_rows:
        for name, char6 in (
            (row.home_name, row.home_char6),
            (row.away_name, row.away_char6),
        ):
            if not name:
                continue
            if bridge.resolve(name, char6) is None:
                unmatched.add(name)
    return NameBridge(
        espn_id_by_key=espn_id_by_key,
        espn_name_by_id=dict(names_by_team),
        unmatched_ncaa_names=tuple(sorted(unmatched)),
        ambiguous_keys=tuple(sorted(collisions)),
    )


# --------------------------------------------------------------------------
# Cross-source reconciliation
# --------------------------------------------------------------------------


def _ncaa_final_rows(rows: Sequence[NcaaGame]) -> list[NcaaGame]:
    return [row for row in rows if row.game_state == "final" and row.home_score != ""]


def _pair_key(first: str, second: str) -> tuple[str, str]:
    ordered = sorted((first, second))
    return ordered[0], ordered[1]


def _neighbouring_days(day: str) -> tuple[str, ...]:
    """The published day and its two neighbours, as ISO dates."""
    if not day:
        return ()
    moment = datetime.fromisoformat(day)
    return tuple(
        (moment + timedelta(days=offset)).strftime("%Y-%m-%d") for offset in (-1, 0, 1)
    )


def cross_source_agreement(
    games: Sequence[BridgeGame],
    ncaa_rows: Sequence[NcaaGame],
    bridge: NameBridge,
    membership: SeasonMembership,
) -> tuple[dict[str, object], dict[str, str]]:
    """Measure the tier-2 corpus against the tier-1 feed, game by game.

    This is the argument that lets 2025 be sourced from an aggregator at all.
    2025 cannot be checked against anything, because the NCAA does not serve it.
    2020 can be checked against the NCAA's own feed for every game the NCAA
    published, and the rate at which the two agree on the score is the only
    honest basis for extending trust to the season where no check is possible.

    Games are matched on calendar date and the unordered pair of ESPN team ids,
    the NCAA side having been mapped through the name bridge. Date rather than
    instant: the NCAA publishes an Eastern-time date and ESPN a UTC instant, and
    a night kickoff crosses midnight UTC, so an instant rule would refuse real
    matches for a timezone reason. A one-day window absorbs that without
    loosening the pair requirement, which is what actually identifies the game.

    Both directions are reported, because they answer different questions: a
    tier-1 row with no tier-2 match asks whether the corpus lost a game, and a
    score disagreement asks whether it has one wrong.
    """
    by_pair_date: dict[tuple[tuple[str, str], str], list[BridgeGame]] = {}
    for game in games:
        day = game.kickoff_utc[:10]
        key = _pair_key(game.home_team_id, game.away_team_id)
        by_pair_date.setdefault((key, day), []).append(game)

    verdicts: dict[str, str] = {}
    matched = 0
    score_agree = 0
    score_disagree = 0
    unresolved_identity = 0
    out_of_scope = 0
    unmatched_tier_1: list[dict[str, object]] = []
    disagreements: list[dict[str, object]] = []

    for row in _ncaa_final_rows(ncaa_rows):
        home_id = bridge.resolve(row.home_name, row.home_char6)
        away_id = bridge.resolve(row.away_name, row.away_char6)
        if home_id is None or away_id is None:
            unresolved_identity += 1
            unmatched_tier_1.append(
                {
                    "reason": "NCAA_NAME_NOT_BRIDGED",
                    "ncaa_game_id": row.game_id,
                    "start_date": row.start_date,
                    "home": row.home_name,
                    "away": row.away_name,
                }
            )
            continue

        parts = row.start_date.split("-")
        published = ""
        if len(parts) == 3:
            try:
                published = (
                    f"{int(parts[2]):04d}-{int(parts[0]):02d}-{int(parts[1]):02d}"
                )
            except ValueError:
                published = ""

        pair = _pair_key(home_id, away_id)
        candidates: list[BridgeGame] = []
        for candidate_day in _neighbouring_days(published):
            candidates.extend(by_pair_date.get((pair, candidate_day), []))
        if not candidates:
            in_scope = SUBDIVISION_FBS in (
                membership.subdivision(home_id),
                membership.subdivision(away_id),
            )
            if not in_scope:
                out_of_scope += 1
            unmatched_tier_1.append(
                {
                    "reason": (
                        "NOT_PRESENT_IN_TIER_2_CORPUS"
                        if in_scope
                        else "OUT_OF_TIER_2_SCOPE_NO_FBS_PARTICIPANT"
                    ),
                    "ncaa_game_id": row.game_id,
                    "start_date": row.start_date,
                    "home": row.home_name,
                    "away": row.away_name,
                }
            )
            continue

        game = candidates[0]
        matched += 1
        tier_1_score = {home_id: row.home_score, away_id: row.away_score}
        agrees = str(game.home_points) == tier_1_score[game.home_team_id] and str(
            game.away_points
        ) == tier_1_score[game.away_team_id]
        if agrees:
            score_agree += 1
            verdicts[game.game_id] = CORROBORATED
        else:
            score_disagree += 1
            verdicts[game.game_id] = DISAGREES_WITH_TIER_1
            disagreements.append(
                {
                    "game_id": game.game_id,
                    "ncaa_game_id": row.game_id,
                    "date": game.kickoff_utc[:10],
                    "tier_2_home": f"{game.home_team_name} {game.home_points}",
                    "tier_2_away": f"{game.away_team_name} {game.away_points}",
                    "tier_1_home": f"{row.home_name} {row.home_score}",
                    "tier_1_away": f"{row.away_name} {row.away_score}",
                }
            )

    tier_1_finals = len(_ncaa_final_rows(ncaa_rows))
    report = {
        "tier_1_authority": NCAA_AUTHORITY,
        "tier_2_authority": ESPN_RESULTS_AUTHORITY,
        "match_rule": (
            "unordered ESPN team-id pair, plus calendar date within one day of "
            "the NCAA published start date; NCAA names mapped through the exact "
            "folded-key name bridge"
        ),
        "tier_1_final_rows": tier_1_finals,
        "tier_1_rows_matched": matched,
        "tier_1_rows_unresolved_identity": unresolved_identity,
        "tier_1_rows_out_of_tier_2_scope": out_of_scope,
        "tier_1_rows_missing_from_tier_2": (
            len(unmatched_tier_1) - unresolved_identity - out_of_scope
        ),
        "score_agreements": score_agree,
        "score_disagreements": score_disagree,
        "score_agreement_rate": round(score_agree / matched, 6) if matched else None,
        "tier_2_games_total": len(games),
        "tier_2_games_corroborated": sum(
            1 for verdict in verdicts.values() if verdict == CORROBORATED
        ),
        "unmatched_tier_1_rows": unmatched_tier_1,
        "score_disagreement_detail": disagreements,
        "unbridged_ncaa_names": list(bridge.unmatched_ncaa_names),
    }
    return report, verdicts


def apply_corroboration(
    games: Sequence[BridgeGame], verdicts: dict[str, str], default: str
) -> list[BridgeGame]:
    """Stamp each game with what tier 1 said about it, or why it said nothing."""
    return [
        replace(game, tier_1_corroboration=verdicts.get(game.game_id, default))
        for game in games
    ]


# --------------------------------------------------------------------------
# Coverage: is the retrieved season actually the whole season?
# --------------------------------------------------------------------------


def _median(values: Sequence[int]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def team_season_coverage(
    games: Sequence[BridgeGame], membership: SeasonMembership
) -> dict[str, object]:
    """Games per FBS member, which is how a truncated retrieval shows itself.

    A date sweep that silently lost a page does not announce itself in a season
    total, because nobody knows what the total should be. It announces itself in
    a team that played seven games. Every FBS member of the season is listed,
    including members with no game at all, because that is a real state --
    Connecticut cancelled its 2020 season -- and a coverage report that omits it
    cannot tell that state apart from a lost page.

    This check is the reason the truncation in the first pass of this lane's
    acquisition was caught: ``limit=900`` returned a well-formed 25-event page
    per date, and the season it produced looked ordinary until the per-team
    counts were read.
    """
    played: dict[str, int] = {}
    for game in games:
        for team_id in (game.home_team_id, game.away_team_id):
            played[team_id] = played.get(team_id, 0) + 1

    fbs_members = membership.members.get(SUBDIVISION_FBS, ())
    counts = {team_id: played.get(team_id, 0) for team_id in fbs_members}
    zero = sorted((team for team, count in counts.items() if count == 0), key=int)
    below_eight = sorted(
        (team for team, count in counts.items() if 0 < count < 8), key=int
    )
    return {
        "season": membership.season,
        "fbs_members_declared": len(fbs_members),
        "fbs_members_with_games": sum(1 for count in counts.values() if count > 0),
        "fbs_members_without_games": zero,
        "fbs_members_below_eight_games": below_eight,
        "min_games": min(counts.values()) if counts else 0,
        "median_games": _median(list(counts.values())) if counts else 0,
        "max_games": max(counts.values()) if counts else 0,
        "games_by_team": {team: counts[team] for team in sorted(counts, key=int)},
    }


# --------------------------------------------------------------------------
# Canonical binding, carried alongside identity rather than instead of it
# --------------------------------------------------------------------------

_CANONICAL_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|"
    r"\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|"
)


@dataclass(frozen=True)
class CanonicalEntity:
    schedule_id: str
    team_name: str
    abbreviated_name: str
    entity_scope: str
    division_2026: str


def load_canonical_master(path: Path) -> tuple[list[CanonicalEntity], str]:
    """Parse the 134-row canonical table, and return the file's digest with it.

    The digest travels with the parse because every count downstream is a count
    over *this* master; a replaced master must invalidate the counts rather than
    quietly change them.
    """
    body = path.read_bytes()
    entities: list[CanonicalEntity] = []
    for line in body.decode("utf-8").splitlines():
        match = _CANONICAL_ROW.match(line)
        if not match:
            continue
        entities.append(
            CanonicalEntity(
                schedule_id=match.group(2),
                team_name=match.group(3),
                abbreviated_name=match.group(4),
                entity_scope=match.group(5),
                division_2026=match.group(6),
            )
        )
    if not entities:
        raise InputValidationError(f"no canonical rows parsed from {path}")
    return entities, hashlib.sha256(body).hexdigest()


def canonical_binding_report(
    games_by_season: dict[int, Sequence[BridgeGame]],
    entities: Sequence[CanonicalEntity],
    canonical_sha256: str,
    keys_by_team: dict[str, tuple[str, ...]],
) -> dict[str, object]:
    """How much of this corpus a canonical-only consumer can see.

    Binding is exact on a folded key against ``schedule_id``, ``team_name`` or
    ``abbreviated_name``, and a key two canonical entities both answer to binds
    neither. Nothing is dropped when binding fails: this is a report about the
    2026 master's reach, not a filter on real football.

    The two universes disagree in both directions and the disagreement is
    recorded rather than reconciled. The master is authoritative for a synthetic
    2026 season; it is not a statement about 2020 or 2025, and using its
    ``2026_division`` as a historical division would be exactly the substitution
    this lane refuses.
    """
    key_to_entity: dict[str, CanonicalEntity] = {}
    collisions: set[str] = set()
    for entity in entities:
        for raw_key in (entity.schedule_id, entity.team_name, entity.abbreviated_name):
            key = normalise_name(raw_key)
            if not key:
                continue
            held = key_to_entity.get(key)
            if held is not None and held.schedule_id != entity.schedule_id:
                collisions.add(key)
            key_to_entity[key] = entity
    for key in collisions:
        key_to_entity.pop(key, None)

    per_season: dict[str, object] = {}
    for season in sorted(games_by_season):
        games = games_by_season[season]
        participants: dict[str, str] = {}
        for game in games:
            participants[game.home_team_id] = game.home_team_name
            participants[game.away_team_id] = game.away_team_name

        bound: dict[str, str] = {}
        unbound: list[str] = []
        for team_id, name in sorted(participants.items(), key=lambda item: item[1]):
            entity = None
            for key in keys_by_team.get(team_id, (normalise_name(name),)):
                entity = key_to_entity.get(key)
                if entity is not None:
                    break
            if entity is None:
                unbound.append(name)
            else:
                bound[team_id] = entity.schedule_id

        both_bound = sum(
            1
            for game in games
            if game.home_team_id in bound and game.away_team_id in bound
        )
        per_season[str(season)] = {
            "participants": len(participants),
            "participants_bound": len(bound),
            "participants_unbound": len(unbound),
            "unbound_names": unbound,
            "games": len(games),
            "games_with_both_participants_bound": both_bound,
            "games_bound_share": (
                round(both_bound / len(games), 6) if games else None
            ),
            "binding_by_team_id": {team: bound[team] for team in sorted(bound, key=int)},
        }

    return {
        "canonical_master_sha256": canonical_sha256,
        "canonical_entities": len(entities),
        "binding_rule": (
            "exact match on a folded key against schedule_id, team_name or "
            "abbreviated_name; a key claimed by two entities binds neither"
        ),
        "unbinding_is_not_exclusion": True,
        "per_season": per_season,
    }


# --------------------------------------------------------------------------
# The 2025 opening-state join test
# --------------------------------------------------------------------------

#: The four families the V3 preseason unified construction combines. Named here
#: so "which families does 2025 have?" is answered against the construction's
#: own list rather than against whatever happened to be found.
V3_PRESEASON_FAMILIES = ("TRUESKILL", "LITKENHOUS", "PURE_BAXTER", "BOARD_FAMILY")

OPENING_WEEKS = (1, 2)


def opening_state_join_test(
    games: Sequence[BridgeGame],
    extract: dict,
    membership: SeasonMembership,
) -> dict[str, object]:
    """Can a real 2025 Week 1/2 game be given an opening state on both sides?

    Three separate things have to be true and they are tested separately,
    because collapsing them produces a number that looks like an answer and is
    not one:

    1. the component source must be **preseason** -- a measurement taken before
       the team played, not a fit over the season it is supposed to precede;
    2. the opening state must have **dispersion** -- a population where every
       team carries the same value has no standard deviation to divide by, so a
       Z score over it is undefined rather than zero;
    3. the component universe must **join** to the real game universe -- a
       rating for a team in a different season's schedule cannot inform a game
       it was not computed over.

    The count the mission asks for is the number of real Week 1/2 games with a
    *valid* opening state on both sides, and a state failing any of the three is
    not valid. Coverage is reported alongside it in every case, so a reader can
    see the difference between "no value was found" and "a value was found and
    refused".
    """
    opening_games = [
        game
        for game in games
        if game.season_type == "REGULAR_SEASON" and game.week in OPENING_WEEKS
    ]

    families: dict[str, object] = {}
    for family in V3_PRESEASON_FAMILIES:
        record = extract.get("families", {}).get(family)
        if record is None:
            families[family] = {
                "source_located": False,
                "is_preseason": False,
                "disposition": "NO_2025_SOURCE_LOCATED",
            }
            continue
        families[family] = record

    preseason_families = [
        name
        for name, record in families.items()
        if isinstance(record, dict) and record.get("is_preseason")
    ]

    truesk = families.get("TRUESKILL")
    dispersion = None
    distinct_values = None
    if isinstance(truesk, dict):
        dispersion = truesk.get("opening_value_standard_deviation")
        distinct_values = truesk.get("opening_distinct_values")

    covered = _both_sides_covered(opening_games, extract)

    valid_families = [
        name
        for name in preseason_families
        if isinstance(families[name], dict)
        and families[name].get("opening_distinct_values", 0) > 1
        and families[name].get("universe_joins_real_season")
    ]
    joinable = len(covered["game_ids"]) if valid_families else 0

    return {
        "season": 2025,
        "real_week_1_2_games": len(opening_games),
        "fbs_members_declared": membership.count(SUBDIVISION_FBS),
        "families_required": list(V3_PRESEASON_FAMILIES),
        "families": families,
        "families_with_a_preseason_2025_source": preseason_families,
        "families_valid_for_a_join": valid_families,
        "trueskill_opening_distinct_values": distinct_values,
        "trueskill_opening_standard_deviation": dispersion,
        "component_universe_overlap": extract.get("universe_overlap", {}),
        "week_1_2_games_with_component_coverage_both_sides": len(covered["game_ids"]),
        "week_1_2_games_with_valid_opening_state_both_sides": joinable,
        "disposition": (
            "STAGE_0_JOIN_AVAILABLE"
            if joinable
            else "NO_ADMISSIBLE_2025_PRESEASON_OPENING_STATE"
        ),
        "refusal_reasons": _join_refusal_reasons(families),
    }


def _both_sides_covered(
    games: Sequence[BridgeGame], extract: dict
) -> dict[str, object]:
    """Games whose two participants both appear in the component universe.

    Coverage, not validity. It is reported so that "the component table names
    both these teams" and "the component table says something usable about
    them" stay visibly different facts.
    """
    named = {normalise_name(name) for name in extract.get("component_team_names", [])}
    hit: list[str] = []
    for game in games:
        home_hit = any(
            key in named
            for key in (
                normalise_name(game.home_team_name),
                normalise_name(game.home_team_school),
            )
        )
        away_hit = any(
            key in named
            for key in (
                normalise_name(game.away_team_name),
                normalise_name(game.away_team_school),
            )
        )
        if home_hit and away_hit:
            hit.append(game.game_id)
    return {"game_ids": sorted(hit)}


def _join_refusal_reasons(families: dict[str, object]) -> list[str]:
    reasons: list[str] = []
    for name, record in sorted(families.items()):
        if not isinstance(record, dict):
            continue
        if not record.get("source_located"):
            reasons.append(f"{name}: no 2025 source located")
            continue
        if not record.get("is_preseason"):
            reasons.append(
                f"{name}: located 2025 source is {record.get('source_class', 'unknown')},"
                " not a preseason measurement"
            )
            continue
        if record.get("opening_distinct_values", 0) <= 1:
            reasons.append(
                f"{name}: opening state carries "
                f"{record.get('opening_distinct_values')} distinct value(s);"
                " a population with no dispersion has no deviation to divide by"
            )
        if not record.get("universe_joins_real_season"):
            reasons.append(
                f"{name}: component universe does not join the real 2025 game universe"
            )
    return reasons


# --------------------------------------------------------------------------
# 2020 backcast feasibility -- feasibility only, no rating is produced
# --------------------------------------------------------------------------


def _pairwise(rows: Sequence[object]) -> list[tuple[object, object]]:
    """Re-pair the two-sided SRS feed with the games that produced it."""
    return [(rows[index], rows[index + 1]) for index in range(0, len(rows), 2)]


def backcast_feasibility(games: Sequence[BridgeGame]) -> dict[str, object]:
    """Whether a 2020 terminal state is *computable* from these results.

    The question asked is narrow and is answered narrowly: does an algorithm
    already in this repository run to completion on the acquired 2020 rows
    without needing historical metadata that does not exist? It is not asked
    whether the result would be admissible, and no rating value is produced,
    returned or written. The solver is run, its solvability is recorded, and its
    output is discarded inside this function.

    Two different answers come out of that and both are reported:

    *SRS* -- ``srs.compute_srs`` -- needs a game identifier, two participants
    and a margin, all of which the corpus carries as facts. It is nonetheless a
    calibration/validation **witness** under ruling R2-SRS-WITNESS, and
    ``srs.require_canonical_validated_srs`` fails closed because no canonical
    specification or historical anchor is mounted. So it computes and it does
    not authorise.

    *The V3 governed path* -- ``rerating.BlockedGovernedRerater`` -- cannot run
    at all, and would not be unblocked by any amount of 2020 results. It raises
    ``GovernanceBlock`` unconditionally; it consumes a ``TeamPathState`` whose
    ``preseason_strength_points`` is exactly the 2020 opening state that does
    not exist; and its residual term needs ``expected_margin`` in V3 units,
    which needs the unratified ``P_TO_STRENGTH_TRANSFORM``.

    Connectivity is reported because 2020 is the season where it is genuinely in
    doubt: conferences played in isolation, and a schedule graph that does not
    connect yields ratings comparable only within a component. It is reported
    twice -- with and without the postseason -- because in 2020 that is the
    difference between one system and several, and the tier-1 feed carries no
    postseason game at all.
    """
    from . import srs

    scored = [game for game in games if not game.cross_division]
    # Each game is supplied twice, once from each participant's point of view.
    # ``srs._build_system`` credits margins and opponent counts to ``team``
    # only, so a one-sided feed leaves every away appearance uncounted and the
    # schedule-adjustment matrix asymmetric -- which presents as a singular
    # system on a schedule graph the same module reports as connected. The
    # two-sided form is what the module's own tests supply.
    srs_games: list[srs.SrsGame] = []
    for game in scored:
        srs_games.append(
            srs.SrsGame(
                game_id=game.game_id,
                team=game.home_team_id,
                opponent=game.away_team_id,
                margin=float(game.home_margin),
            )
        )
        srs_games.append(
            srs.SrsGame(
                game_id=game.game_id,
                team=game.away_team_id,
                opponent=game.home_team_id,
                margin=float(-game.home_margin),
            )
        )

    regular_only = [
        row
        for game, pair in zip(scored, _pairwise(srs_games))
        if game.season_type == "REGULAR_SEASON"
        for row in pair
    ]

    components: list[list[str]] = []
    solvable = False
    solver_error = ""
    if srs_games:
        components = srs.srs_components(srs_games)
        try:
            solved = srs.compute_srs(srs_games)
            solvable = len(solved) > 0
        except Exception as exc:  # noqa: BLE001 - the failure mode is the finding
            solvable = False
            solver_error = f"{type(exc).__name__}: {exc}"
        finally:
            solved = None  # noqa: F841 - discarded deliberately; see docstring

    governed_blocker = ""
    try:
        srs.require_canonical_validated_srs()
    except Exception as exc:  # noqa: BLE001
        governed_blocker = f"{type(exc).__name__}: {exc}"

    component_sizes = sorted((len(component) for component in components), reverse=True)
    regular_components = srs.srs_components(regular_only) if regular_only else []
    regular_sizes = sorted(
        (len(component) for component in regular_components), reverse=True
    )
    return {
        "season": 2020,
        "input_fields_required_by_srs": ["game_id", "team", "opponent", "margin"],
        "input_fields_available": True,
        "historical_metadata_required_and_absent": [],
        "same_division_games_used": len(scored),
        "srs_rows_supplied": len(srs_games),
        "cross_division_games_withheld": len(games) - len(scored),
        "teams_in_system": sum(component_sizes),
        "schedule_graph_components": len(components),
        "schedule_graph_component_sizes": component_sizes,
        "schedule_graph_connected": len(components) == 1,
        "regular_season_only_components": len(regular_components),
        "regular_season_only_component_sizes": regular_sizes,
        "postseason_required_for_connectivity": (
            len(components) == 1 and len(regular_components) > 1
        ),
        "srs_terminal_state_computable": solvable,
        "srs_solver_error": solver_error,
        "srs_values_emitted": False,
        "srs_governance": governed_blocker,
        "v3_governed_rerating_runnable": False,
        "v3_governed_rerating_obstacles": [
            "rerating.BlockedGovernedRerater raises GovernanceBlock unconditionally",
            "TeamPathState.preseason_strength_points requires a 2020 opening state,"
            " which no located source supplies",
            "the residual term requires expected_margin in V3 point units, which"
            " requires the unratified P_TO_STRENGTH_TRANSFORM and REFERENCE_HFA",
        ],
        "same_season_preseason_derivation_attempted": False,
        "disposition": (
            "TERMINAL_STATE_COMPUTABLE_AS_WITNESS_ONLY"
            if solvable
            else "TERMINAL_STATE_NOT_COMPUTABLE"
        ),
    }


# --------------------------------------------------------------------------
# Division: declaration versus the tier-1 feed's own intersection
# --------------------------------------------------------------------------


def ncaa_division_by_intersection(ncaa_rows: Sequence[NcaaGame]) -> dict[str, str]:
    """Division as the NCAA feed itself implies it, for a season it serves.

    The ``fbs`` and ``fcs`` scoreboards are distinct game sets that overlap
    exactly on cross-division games. A game published in ``fbs`` and not in
    ``fcs`` therefore has two FBS participants, and a team appearing in such a
    game is FBS. This is R6's rule and it is reimplemented here for one purpose:
    to check the subdivision *declaration* this lane uses instead, on the one
    season where both are available.
    """
    feeds_by_game: dict[str, set[str]] = {}
    names_by_game: dict[str, tuple[str, str]] = {}
    for row in ncaa_rows:
        if not row.game_id:
            continue
        feeds_by_game.setdefault(row.game_id, set()).add(row.division_feed)
        names_by_game[row.game_id] = (row.home_name, row.away_name)

    division: dict[str, str] = {}
    for game_id, feeds in feeds_by_game.items():
        home, away = names_by_game[game_id]
        if feeds == {"fbs"}:
            for name in (home, away):
                if name:
                    division[name] = SUBDIVISION_FBS
        elif feeds == {"fcs"}:
            for name in (home, away):
                if name:
                    division.setdefault(name, SUBDIVISION_FCS)
    # A team seen in an FBS-only game is FBS even if it also appears in the FCS
    # feed through a cross-division game, so the FBS pass above wins by writing
    # unconditionally while the FCS pass only fills gaps.
    return division


def division_cross_check(
    games: Sequence[BridgeGame],
    ncaa_rows: Sequence[NcaaGame],
    bridge: NameBridge,
    membership: SeasonMembership,
) -> dict[str, object]:
    """Compare the two ways of knowing a participant's division.

    2020 is the only season in scope where both are available, which makes it
    the only place the substitution used for 2025 can be tested at all. Each
    team the NCAA feed classifies is compared with the subdivision declaration;
    disagreements are listed in full rather than counted, because one
    disagreement in a division field is a different kind of problem from a low
    agreement rate and the reader needs to see which it is.
    """
    feed_division = ncaa_division_by_intersection(ncaa_rows)
    char6_by_name: dict[str, str] = {}
    for row in ncaa_rows:
        for name, char6 in (
            (row.home_name, row.home_char6),
            (row.away_name, row.away_char6),
        ):
            if name and char6:
                char6_by_name.setdefault(name, char6)
    agree = 0
    disagree: list[dict[str, str]] = []
    unbridged: list[str] = []
    for ncaa_name, feed_value in sorted(feed_division.items()):
        team_id = bridge.resolve(ncaa_name, char6_by_name.get(ncaa_name, ""))
        if team_id is None:
            unbridged.append(ncaa_name)
            continue
        declared = membership.subdivision(team_id)
        if declared == feed_value:
            agree += 1
        else:
            disagree.append(
                {
                    "ncaa_name": ncaa_name,
                    "espn_team_id": team_id,
                    "tier_1_feed_intersection": feed_value,
                    "subdivision_declaration": declared,
                }
            )
    compared = agree + len(disagree)
    return {
        "season": membership.season,
        "method_a": "NCAA fbs/fcs scoreboard intersection (tier 1)",
        "method_b": "ESPN per-season subdivision membership declaration (tier 2)",
        "teams_classified_by_tier_1": len(feed_division),
        "teams_compared": compared,
        "teams_unbridged": unbridged,
        "agreements": agree,
        "disagreements": disagree,
        "agreement_rate": round(agree / compared, 6) if compared else None,
    }


# --------------------------------------------------------------------------
# Historical membership, and the 2024 population question
# --------------------------------------------------------------------------


#: House-style aliases used by the located population candidates for programs
#: the season declaration names differently. Each entry is one program under two
#: naming conventions, and the table is used for **one** purpose: comparing two
#: claims about membership. It never admits, excludes or renames a game, and no
#: corpus row passes through it.
#:
#: The table is here because without it the comparison reports seven name
#: differences per season where the substantive difference is zero -- which
#: would bury the one season where it is not zero. An alias is applied only if
#: it resolves to exactly one team in the derived membership; if it resolves to
#: none or to several it is not applied and the name is reported as unmatched,
#: so a wrong entry cannot manufacture an agreement.
CANDIDATE_NAME_ALIASES: dict[str, str] = {
    "central florida": "UCF",
    "latech": "Louisiana Tech",
    "louisianamonroe": "UL Monroe",
    "middletennesseestate": "Middle Tennessee",
    "texassanantonio": "UTSA",
    "ullafayette": "Louisiana",
    "samhoustonstate": "Sam Houston",
}


def _candidate_keys(name: str) -> tuple[str, ...]:
    """Keys a candidate's team name may be compared under."""
    folded = normalise_name(name)
    alias = CANDIDATE_NAME_ALIASES.get(folded)
    if alias is None:
        # The raw, unfolded form is also tried: the alias table is keyed on the
        # folded name and one entry ("central florida") folds with a space.
        alias = CANDIDATE_NAME_ALIASES.get(name.strip().lower())
    if alias is None:
        return (folded,)
    return (folded, normalise_name(alias))


def membership_report(
    membership: dict[int, SeasonMembership],
    names: dict[str, str],
    candidates: dict,
    keys_by_team: dict[str, tuple[str, ...]],
) -> dict[str, object]:
    """Season-specific subdivision membership, next to every located claim.

    The derived membership is a roll-up of season conference rosters, which is a
    statement about the season it belongs to. The candidates are statements
    somebody made about seasons; they are reported beside it, with digests, and
    the comparison is by name because they carry no shared identifier.

    Names are compared on the same folded key the rest of this module uses, so
    ``Ohio St.`` and ``Ohio State`` are one team and ``Miami (FL)`` and
    ``Miami (OH)`` are two.
    """
    per_season: dict[str, object] = {}
    for season in sorted(membership):
        season_membership = membership[season]
        fbs = season_membership.members.get(SUBDIVISION_FBS, ())
        fcs = season_membership.members.get(SUBDIVISION_FCS, ())
        conferences: dict[str, list[str]] = {}
        for team_id in fbs:
            conferences.setdefault(season_membership.conference(team_id), []).append(
                names.get(team_id, f"ESPN_TEAM_{team_id}")
            )
        per_season[str(season)] = {
            "fbs_members": len(fbs),
            "fcs_members": len(fcs),
            "fbs_by_conference": {
                conference: sorted(members)
                for conference, members in sorted(conferences.items())
            },
            "fbs_member_names": sorted(
                names.get(team_id, f"ESPN_TEAM_{team_id}") for team_id in fbs
            ),
        }

    comparisons: dict[str, object] = {}
    for candidate_id, candidate in sorted(candidates.get("candidates", {}).items()):
        if not candidate.get("source_located"):
            comparisons[candidate_id] = {"source_located": False}
            continue
        seasons: dict[str, object] = {}
        for season_text, payload in sorted(candidate.get("by_season", {}).items()):
            season = int(season_text)
            declared = membership.get(season)
            claimed_names = payload.get("fbs_members", [])
            claimed_keys: dict[str, str] = {}
            for name in claimed_names:
                for key in _candidate_keys(name):
                    claimed_keys.setdefault(key, name)
            if declared is None:
                seasons[season_text] = {
                    "candidate_fbs_count": payload.get("fbs_count"),
                    "derived_fbs_count": None,
                    "difference": None,
                    "comparable": False,
                    "reason": "no derived membership for this season",
                }
                continue
            derived_names = {
                names.get(team_id, f"ESPN_TEAM_{team_id}")
                for team_id in declared.members.get(SUBDIVISION_FBS, ())
            }
            derived_keys: dict[str, str] = {}
            for team_id in declared.members.get(SUBDIVISION_FBS, ()):
                name = names.get(team_id, f"ESPN_TEAM_{team_id}")
                for key in keys_by_team.get(team_id, (normalise_name(name),)):
                    derived_keys.setdefault(key, name)
            unmatched_candidate = {
                name
                for key, name in claimed_keys.items()
                if key not in derived_keys
            }
            matched_candidate = {
                name for key, name in claimed_keys.items() if key in derived_keys
            }
            only_candidate = sorted(unmatched_candidate - matched_candidate)
            matched_keys = {
                key for key in claimed_keys if key in derived_keys
            }
            matched_derived = {derived_keys[key] for key in matched_keys}
            only_derived = sorted(derived_names - matched_derived)
            seasons[season_text] = {
                "candidate_fbs_count": payload.get("fbs_count"),
                "derived_fbs_count": declared.count(SUBDIVISION_FBS),
                "difference": (payload.get("fbs_count") or 0)
                - declared.count(SUBDIVISION_FBS),
                "in_candidate_only": only_candidate,
                "in_derived_only": only_derived,
            }
        comparisons[candidate_id] = {
            "source_located": True,
            "source_sha256": candidate.get("source_sha256")
            or candidate.get("member_sha256", ""),
            "universe_class": candidate.get("universe_class", ""),
            "per_season": seasons,
        }

    return {
        "derivation": (
            "union of the member teams of every conference declared a child of "
            "the subdivision group for that season"
        ),
        "source_authority": ESPN_STRUCTURE_AUTHORITY,
        "source_authority_tier": ESPN_TIER,
        "per_season": per_season,
        "candidate_comparisons": comparisons,
    }


def resolve_2024_population(report: dict) -> dict[str, object]:
    """State the 2024 FBS population and say what each rival number is.

    The evidence settles it, so it is settled here rather than escalated. The
    derived membership is a roll-up of the 2024 conference rosters and gives
    134. The candidates give 133, 118 and 121, and each of those is a count of
    something -- just not of 2024 FBS membership.
    """
    derived = report["per_season"].get("2024", {}).get("fbs_members")
    comparisons = report.get("candidate_comparisons", {})
    rivals: list[dict[str, object]] = []
    for candidate_id, candidate in sorted(comparisons.items()):
        if not candidate.get("source_located"):
            continue
        for season_text, payload in sorted(candidate.get("per_season", {}).items()):
            rivals.append(
                {
                    "candidate": candidate_id,
                    "season_claimed": int(season_text),
                    "count": payload.get("candidate_fbs_count"),
                    "universe_class": candidate.get("universe_class", ""),
                    "in_candidate_only": payload.get("in_candidate_only", []),
                    "in_derived_only": payload.get("in_derived_only", []),
                }
            )
    return {
        "question": "how many FBS members did the 2024 season have",
        "resolved": derived is not None,
        "resolution": derived,
        "resolution_basis": (
            "the 2024 conference roll-up from the season structure declaration, "
            "cross-checked for 2020 against the NCAA feed's own division "
            "intersection"
        ),
        "requires_chairman_ruling": False,
        "candidate_claims": rivals,
    }
