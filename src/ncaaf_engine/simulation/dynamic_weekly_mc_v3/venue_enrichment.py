"""Venue and competition-type enrichment for the 2021-2024 historical universe.

The Historical Observation Corpus R6 admits 2,241 real observations and records
venue as ``BLOCKED``, for a reason that is a property of the source rather than
of the corpus: the NCAA scoreboard feed designates a home and an away
participant and carries no venue field at all. Not blank for postseason, not
inconsistent - absent, in every row of every week of every season retrieved. A
designated home team is therefore not evidence of home field, and the governed
V3 football-point HFA of 3.5 cannot be attached to one without saying something
the source never said.

This module is the enrichment layer that closes that gap where evidence permits.
It does not rewrite the corpus, does not re-decide which games belong in
calibration, and promotes no parameter. It produces one row per historical game
carrying what two sources actually state, and it says ``VENUE_UNRESOLVED``
wherever they do not state it.

Two sources, two jobs
---------------------

*NCAA official scoreboard* (``TIER_1_NCAA_OFFICIAL``) is the identity anchor. It
supplies the stable game identity ``NCAA-<season>-<gameID>`` that R6 is keyed on,
the designated home/away orientation, and the scheduled kickoff instant. This is
what makes the enrichment joinable rather than merely parallel.

*ESPN college-football scoreboard* (``TIER_5_REPRODUCIBLE_SECONDARY``) is the
venue evidence. It states ``neutralSite`` as an explicit boolean, names the venue
and city, names the contest, and separates regular season from postseason. It is
used only because tiers 1-4 were established as unavailable for the venue fact
specifically - the NCAA's own game-detail endpoints 404, and the gateway behind
the venue element on ncaa.com answers 403 at the edge. That reasoning and the
probes behind it are recorded in :mod:`scripts.acquire_venue_sources_r1`. The
tier is carried on every row that uses it and is never quietly promoted.

Why matching is score-blind first
---------------------------------

The two feeds share no identifier. Matching therefore runs on facts, in strength
order, and each pass refuses rather than guesses when more than one candidate
survives:

``IDENTITY_DATE``
    Both teams resolved to ESPN team ids and exactly one ESPN event on the
    calendar date (+/- one day) has that pair of participants. Deliberately does
    *not* consult the score, so a game the two sources disagree about the score
    of still matches - and is then reported as a score conflict instead of
    vanishing into the unmatched pile. That is not hypothetical: the NCAA feed
    records TCU 16 at Oklahoma State on 2021-11-13 where ESPN records 17.

``PARTIAL_IDENTITY_SCORE``
    One team resolves - typically the FBS side of an FBS-versus-FCS game, since
    the ESPN FBS grouping does not carry FCS teams as members - and the date and
    the score pair single out one event.

``DATE_SCORE``
    Neither team resolves, but the date and score pair are unique on both sides.

The team-identity map the first two passes need is not hand-authored. It is
harvested from the third pass's unambiguous matches by aligning the two feeds'
scores within a game, which pins each NCAA team to an ESPN team id without
anyone deciding that ``south-ala`` means "South Alabama". The passes then re-run
to a fixpoint, since each new match can teach the map a team. A name that would
resolve to two different ESPN ids is dropped from the map rather than resolved by
majority, and a game whose slot in the source carries more than one row - the
NCAA feed does this seven times across the four seasons, twice with disagreeing
scores - is refused as ``AMBIGUOUS_SOURCE_IDENTITY`` rather than bound to
whichever row sorts first.

Every ESPN event binds to at most one NCAA game. The bijection is what turns a
duplicated source row into a visible refusal instead of a silent double-count.

What is deliberately not produced
---------------------------------

* No completion instant and no observability instant. Neither source carries
  one. Deriving them from kickoff would be fabricating the exact fact the lane
  exists to stop fabricating, so both columns are empty on every row and both
  counts are reported as zero.
* No expected margin, no rating, no coefficient, no HFA arithmetic.
  :func:`venue_hfa_disposition` returns which side a home-field adjustment would
  attach to, as a token. It never returns a number, and it returns
  ``NO_HFA_APPLIES`` for a neutral site, which is the semantic this whole lane
  exists to make checkable.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

__all__ = [
    "ADMITTED_SEASONS",
    "CONFLICT_STATUSES",
    "DIVISION_MATCHUPS",
    "ENRICHMENT_COLUMNS",
    "ESPN_AUTHORITY",
    "ESPN_AUTHORITY_TIER",
    "EVIDENCE_STATUSES",
    "FEED_LOCAL_TIMEZONE",
    "GAME_TYPES",
    "LANE_ID",
    "MATCH_METHODS",
    "MATCH_STATUSES",
    "NCAA_AUTHORITY",
    "NCAA_AUTHORITY_TIER",
    "USABILITY_CLASSES",
    "VENUE_CLASSIFICATIONS",
    "SUBJECT_VENUES",
    "ENRICHMENT_ID",
    "EnrichmentResult",
    "EnrichmentRow",
    "EspnEvent",
    "NcaaGame",
    "VenueEnrichmentError",
    "build_venue_enrichment",
    "classify_game_type",
    "corpus_join_report",
    "conflict_report",
    "coverage_report",
    "load_espn_events",
    "load_ncaa_games",
    "match_games",
    "render_enrichment_csv",
    "team_identity_map",
    "venue_hfa_disposition",
    "verify_raw_custody",
]


class VenueEnrichmentError(RuntimeError):
    """Raised when the enrichment cannot be built from the bytes in custody."""


LANE_ID = "V3_HISTORICAL_VENUE_ENRICHMENT_R1"
ENRICHMENT_ID = "V3_R1_HISTORICAL_VENUE_ENRICHMENT"

ADMITTED_SEASONS: tuple[int, ...] = (2021, 2022, 2023, 2024)

NCAA_AUTHORITY = "NCAA_OFFICIAL_SCOREBOARD_FEED"
NCAA_AUTHORITY_TIER = "TIER_1_NCAA_OFFICIAL"
ESPN_AUTHORITY = "ESPN_COLLEGE_FOOTBALL_SCOREBOARD"
ESPN_AUTHORITY_TIER = "TIER_5_REPRODUCIBLE_SECONDARY"

#: The NCAA feed stamps ``startTime`` as Eastern ("01:00PM ET") and ``startDate``
#: as the Eastern calendar date. Both feeds' calendar dates are therefore
#: compared in this zone rather than in UTC, where a 8pm Pacific kickoff lands on
#: the following day and would block against the wrong slate.
FEED_LOCAL_TIMEZONE = "America/New_York"
_ET = ZoneInfo(FEED_LOCAL_TIMEZONE)

#: Game-level: was the game played at a site neutral to both participants.
VENUE_CLASSIFICATIONS: tuple[str, ...] = (
    "NEUTRAL_SITE",
    "HOME_AWAY_SITE",
    "VENUE_UNRESOLVED",
)

#: Subject-team perspective, which is the perspective the expected-margin
#: pipeline consumes. The subject is the NCAA-designated home participant,
#: matching the corpus ``team`` column - but *designated home* and *had home
#: field* are exactly the two things this vocabulary keeps apart.
SUBJECT_VENUES: tuple[str, ...] = (
    "HOME_FIELD",
    "AWAY_FIELD",
    "NEUTRAL_SITE",
    "VENUE_UNRESOLVED",
)

GAME_TYPES: tuple[str, ...] = (
    "REGULAR_SEASON",
    "CONFERENCE_CHAMPIONSHIP",
    "BOWL",
    "PLAYOFF",
    "OTHER_POSTSEASON",
    "UNKNOWN_GAME_TYPE",
)

MATCH_STATUSES: tuple[str, ...] = (
    "MATCHED_EXACT",
    "MULTIPLE_MATCH_REFUSED",
    "AMBIGUOUS_SOURCE_IDENTITY",
    "UNMATCHED",
)

MATCH_METHODS: tuple[str, ...] = (
    "IDENTITY_DATE",
    "PARTIAL_IDENTITY_SCORE",
    "DATE_SCORE",
)

EVIDENCE_STATUSES: tuple[str, ...] = (
    "VENUE_EVIDENCE_BOUND",
    "VENUE_EVIDENCE_ABSENT",
)

CONFLICT_STATUSES: tuple[str, ...] = (
    "NO_CONFLICT",
    "SOURCE_CONFLICT_ORIENTATION",
    "SOURCE_CONFLICT_SCORE",
    "SOURCE_CONFLICT_KICKOFF",
)

DIVISION_MATCHUPS: tuple[str, ...] = (
    "FBS_VS_FBS",
    "FBS_VS_FCS",
    "FCS_VS_FCS",
    "DIVISION_UNRESOLVED",
)

USABILITY_CLASSES: tuple[str, ...] = (
    "EXPECTED_MARGIN_VENUE_READY",
    "EXPECTED_MARGIN_VENUE_UNRESOLVED",
)

ENRICHMENT_COLUMNS: tuple[str, ...] = (
    "game_id",
    "season",
    "week",
    "subject_team",
    "opponent_team",
    "source_home_team",
    "source_away_team",
    "source_orientation",
    "orientation_cross_source",
    "subject_division",
    "opponent_division",
    "division_matchup",
    "venue_classification",
    "subject_venue",
    "game_type",
    "game_type_evidence",
    "venue_name",
    "venue_city",
    "venue_state",
    "neutral_site_flag",
    "kickoff_local",
    "kickoff_local_timezone",
    "kickoff_utc",
    "kickoff_utc_ncaa",
    "kickoff_utc_espn",
    "completion_utc",
    "observability_utc",
    "match_status",
    "match_method",
    "espn_event_id",
    "source_authority",
    "source_locator",
    "evidence_status",
    "conflict_status",
    "calibration_usability",
)

#: ESPN names the competition in ``competitions[0].type.abbreviation``. The
#: mapping is from the source's own vocabulary, not from a week number.
_ESPN_COMPETITION_TYPE = {
    "Conference Championship": "CONFERENCE_CHAMPIONSHIP",
    "Bowl Game": "BOWL",
    "Major Bowl": "BOWL",
    "Semifinal Bowl": "PLAYOFF",
}

_PLAYOFF_NOTE = re.compile(r"College Football Playoff|National Championship|Semifinal")
_BOWL_NOTE = re.compile(r"\bBowl\b")
_CHAMPIONSHIP_NOTE = re.compile(r"\bChampionship\b")

_TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})(AM|PM)\s+ET$")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# raw custody
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RawSource:
    """One acquired file, and the digest custody is asserted over.

    ``decompressed_sha256`` is the load-bearing one. The gzip container is what
    git stores, but a container digest only proves the container has not moved;
    the payload digest is what proves the bytes the enrichment reads are the
    bytes that were retrieved.
    """

    source_authority: str
    source_authority_tier: str
    source_locator: str
    raw_path: str
    season: int
    decompressed_sha256: str
    decompressed_byte_length: int
    retrieved_at_utc: str
    payload_row_count: int | None
    division: str | None = None
    espn_season_type: int | None = None
    week: int | None = None

    def read(self, repo_root: Path) -> bytes:
        target = repo_root / self.raw_path
        if not target.is_file():
            raise VenueEnrichmentError(f"raw source missing from custody: {self.raw_path}")
        data = gzip.decompress(target.read_bytes())
        actual = _sha256(data)
        if actual != self.decompressed_sha256:
            raise VenueEnrichmentError(
                f"raw source digest mismatch for {self.raw_path}: manifest records "
                f"{self.decompressed_sha256}, bytes hash to {actual}"
            )
        if len(data) != self.decompressed_byte_length:
            raise VenueEnrichmentError(
                f"raw source length mismatch for {self.raw_path}: manifest records "
                f"{self.decompressed_byte_length}, bytes measure {len(data)}"
            )
        return data


def load_acquisition_manifest(path: Path) -> tuple[RawSource, ...]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = []
    for record in payload.get("sources", []):
        sources.append(
            RawSource(
                source_authority=record["source_authority"],
                source_authority_tier=record["source_authority_tier"],
                source_locator=record["source_locator"],
                raw_path=record["raw_path"],
                season=int(record["season"]),
                decompressed_sha256=record["decompressed_sha256"],
                decompressed_byte_length=int(record["decompressed_byte_length"]),
                retrieved_at_utc=record["retrieved_at_utc"],
                payload_row_count=record.get("payload_row_count"),
                division=record.get("division"),
                espn_season_type=record.get("espn_season_type"),
                week=record.get("week"),
            )
        )
    if not sources:
        raise VenueEnrichmentError(f"acquisition manifest carries no sources: {path}")
    return tuple(sorted(sources, key=lambda s: s.raw_path))


def verify_raw_custody(
    sources: Sequence[RawSource], repo_root: Path
) -> dict[str, Any]:
    """Re-derive every digest from the bytes on disk.

    The manifest is not trusted to describe itself. Each file is decompressed
    and re-hashed; a source whose bytes have moved, changed or gone missing
    raises here rather than being noticed downstream as a strange row count.
    """
    verified = []
    for source in sources:
        data = source.read(repo_root)
        verified.append(
            {
                "raw_path": source.raw_path,
                "source_authority": source.source_authority,
                "decompressed_sha256": _sha256(data),
                "decompressed_byte_length": len(data),
            }
        )
    return {
        "sources_verified": len(verified),
        "bytes_reverified": True,
        "authorities": sorted({s.source_authority for s in sources}),
        "verified": verified,
    }


# ---------------------------------------------------------------------------
# source records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NcaaGame:
    """One row of the NCAA scoreboard feed, normalised but not interpreted."""

    game_id: str
    season: int
    week: int
    division_feed: str
    source_game_id: str
    home_char6: str
    home_seo: str
    home_short: str
    home_score: int
    away_char6: str
    away_seo: str
    away_short: str
    away_score: int
    start_epoch: int
    start_date_raw: str
    start_time_raw: str
    source_locator: str

    @property
    def kickoff_utc(self) -> datetime:
        return datetime.fromtimestamp(self.start_epoch, tz=timezone.utc)

    @property
    def local_date(self) -> date:
        return self.kickoff_utc.astimezone(_ET).date()

    @property
    def score_pair(self) -> tuple[int, int]:
        return tuple(sorted((self.home_score, self.away_score)))  # type: ignore[return-value]


@dataclass(frozen=True)
class EspnEvent:
    """One completed ESPN event, carrying the venue facts the NCAA feed lacks."""

    event_id: str
    season: int
    season_slug: str
    competition_type: str
    neutral_site: bool | None
    venue_name: str
    venue_city: str
    venue_state: str
    home_team_id: str
    home_score: int
    away_team_id: str
    away_score: int
    notes: tuple[str, ...]
    kickoff_utc: datetime
    source_locator: str

    @property
    def local_date(self) -> date:
        return self.kickoff_utc.astimezone(_ET).date()

    @property
    def team_ids(self) -> frozenset[str]:
        return frozenset({self.home_team_id, self.away_team_id})

    @property
    def score_pair(self) -> tuple[int, int]:
        return tuple(sorted((self.home_score, self.away_score)))  # type: ignore[return-value]


def _int_or_none(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def load_ncaa_games(
    sources: Sequence[RawSource],
    repo_root: Path,
    seasons: Sequence[int] = ADMITTED_SEASONS,
) -> tuple[tuple[NcaaGame, ...], dict[str, Any]]:
    """Read the NCAA feed into the enrichment universe.

    Admission here is narrow and mechanical, because the question of which games
    belong in *calibration* is R6's to answer, not this lane's. A row is taken
    when the source says the game finished, gives it an identifier, and gives
    both sides a score. Everything else is counted and set aside.
    """
    admitted: dict[str, NcaaGame] = {}
    fbs_ids: dict[int, set[str]] = defaultdict(set)
    fcs_ids: dict[int, set[str]] = defaultdict(set)
    #: (division, season, source game id) -> the two team slugs the feed names.
    #: Kept for both divisions because division membership is read from which
    #: feed carries a game, which needs the FCS side's rosters too.
    feed_participants: dict[tuple[str, int, str], tuple[str, str]] = {}
    setaside: Counter[str] = Counter()

    for source in sources:
        if source.source_authority != NCAA_AUTHORITY or source.season not in seasons:
            continue
        payload = json.loads(source.read(repo_root))
        for wrapper in payload.get("games", []):
            game = wrapper.get("game") or {}
            source_game_id = str(game.get("gameID", "")).strip()
            state = str(game.get("gameState", "")).strip()
            home = game.get("home") or {}
            away = game.get("away") or {}
            if state != "final":
                setaside[f"SOURCE_STATE_{state.upper() or 'BLANK'}"] += 1
                continue
            if not source_game_id:
                setaside["SOURCE_GAME_ID_BLANK"] += 1
                continue
            home_score = _int_or_none(home.get("score"))
            away_score = _int_or_none(away.get("score"))
            if home_score is None or away_score is None:
                setaside["SOURCE_SCORE_ABSENT"] += 1
                continue
            epoch = _int_or_none(game.get("startTimeEpoch"))
            if epoch is None:
                setaside["SOURCE_KICKOFF_EPOCH_ABSENT"] += 1
                continue

            (fbs_ids if source.division == "fbs" else fcs_ids)[source.season].add(
                source_game_id
            )
            feed_participants[(str(source.division), source.season, source_game_id)] = (
                str((home.get("names") or {}).get("seo", "")).strip(),
                str((away.get("names") or {}).get("seo", "")).strip(),
            )
            if source.division != "fbs":
                continue

            game_id = f"NCAA-{source.season}-{source_game_id}"
            if game_id in admitted:
                # The same identifier in two week files is the feed repeating
                # itself, not two games. Keep the first read; ordering over
                # raw_path makes "first" deterministic.
                setaside["SOURCE_GAME_ID_REPEATED_IN_FEED"] += 1
                continue
            admitted[game_id] = NcaaGame(
                game_id=game_id,
                season=source.season,
                week=int(source.week or 0),
                division_feed=str(source.division),
                source_game_id=source_game_id,
                home_char6=str((home.get("names") or {}).get("char6", "")).strip(),
                home_seo=str((home.get("names") or {}).get("seo", "")).strip(),
                home_short=str((home.get("names") or {}).get("short", "")).strip(),
                home_score=home_score,
                away_char6=str((away.get("names") or {}).get("char6", "")).strip(),
                away_seo=str((away.get("names") or {}).get("seo", "")).strip(),
                away_short=str((away.get("names") or {}).get("short", "")).strip(),
                away_score=away_score,
                start_epoch=epoch,
                start_date_raw=str(game.get("startDate", "")).strip(),
                start_time_raw=str(game.get("startTime", "")).strip(),
                source_locator=source.source_locator,
            )

    games = tuple(sorted(admitted.values(), key=lambda g: g.game_id))
    divisions = _division_membership(feed_participants, fbs_ids, fcs_ids)
    report = {
        "games_admitted": len(games),
        "rows_set_aside": dict(sorted(setaside.items())),
        "division_membership_counts": {
            season: dict(sorted(Counter(teams.values()).items()))
            for season, teams in sorted(divisions.items())
        },
        "division_membership": divisions,
    }
    return games, report


def _division_membership(
    feed_participants: Mapping[tuple[str, int, str], tuple[str, str]],
    fbs_ids: Mapping[int, set[str]],
    fcs_ids: Mapping[int, set[str]],
) -> dict[str, dict[str, str]]:
    """Read each team's division from which feeds carry its games.

    A cross-division game is carried by both scoreboards; a game between two
    teams of one division is carried only by that division's scoreboard. So a
    team that appears in a game the FBS scoreboard carries alone is an FBS team
    that season, and a team that appears in a game the FCS scoreboard carries
    alone is an FCS team. Division is thereby *read* from the source. Nothing
    here consults a conference name.

    Teams in transition are the reason this matters rather than being pedantry.
    Delaware and Missouri State play a 2024 schedule the FBS scoreboard carries
    while they are still FCS members, and James Madison crosses the other way in
    2022. A team the two feeds place on both sides in one season is left
    ``UNRESOLVED`` rather than assigned the more common answer.
    """
    claims: dict[int, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for (division, season, game_id), participants in feed_participants.items():
        shared = game_id in fbs_ids.get(season, set()) and game_id in fcs_ids.get(
            season, set()
        )
        if shared:
            continue
        label = "FBS" if division == "fbs" else "FCS"
        for seo in participants:
            if seo:
                claims[season][seo].add(label)

    membership: dict[str, dict[str, str]] = {}
    for season in sorted(claims):
        resolved: dict[str, str] = {}
        for seo in sorted(claims[season]):
            labels = claims[season][seo]
            resolved[seo] = next(iter(labels)) if len(labels) == 1 else "UNRESOLVED"
        membership[str(season)] = resolved
    return membership


def load_espn_events(
    sources: Sequence[RawSource],
    repo_root: Path,
    seasons: Sequence[int] = ADMITTED_SEASONS,
) -> tuple[tuple[EspnEvent, ...], dict[str, Any]]:
    """Read the ESPN feed, keeping only events the source calls completed."""
    events: dict[str, EspnEvent] = {}
    setaside: Counter[str] = Counter()

    for source in sources:
        if source.source_authority != ESPN_AUTHORITY or source.season not in seasons:
            continue
        payload = json.loads(source.read(repo_root))
        for event in payload.get("events", []):
            competitions = event.get("competitions") or []
            if not competitions:
                setaside["ESPN_COMPETITION_ABSENT"] += 1
                continue
            competition = competitions[0]
            status = ((competition.get("status") or {}).get("type") or {})
            if not status.get("completed"):
                setaside["ESPN_NOT_COMPLETED"] += 1
                continue
            competitors = competition.get("competitors") or []
            sides = {str(c.get("homeAway", "")): c for c in competitors}
            if len(competitors) != 2 or set(sides) != {"home", "away"}:
                setaside["ESPN_COMPETITOR_SHAPE_UNEXPECTED"] += 1
                continue
            home_score = _int_or_none(sides["home"].get("score"))
            away_score = _int_or_none(sides["away"].get("score"))
            if home_score is None or away_score is None:
                setaside["ESPN_SCORE_ABSENT"] += 1
                continue
            kickoff = _parse_espn_instant(str(event.get("date", "")))
            if kickoff is None:
                setaside["ESPN_KICKOFF_UNPARSEABLE"] += 1
                continue
            event_id = str(event.get("id", "")).strip()
            if not event_id or event_id in events:
                setaside["ESPN_EVENT_ID_BLANK_OR_REPEATED"] += 1
                continue
            venue = competition.get("venue") or {}
            address = venue.get("address") or {}
            neutral = competition.get("neutralSite")
            events[event_id] = EspnEvent(
                event_id=event_id,
                season=source.season,
                season_slug=str((event.get("season") or {}).get("slug", "")),
                competition_type=str((competition.get("type") or {}).get("abbreviation", "")),
                neutral_site=bool(neutral) if isinstance(neutral, bool) else None,
                venue_name=str(venue.get("fullName", "")).strip(),
                venue_city=str(address.get("city", "")).strip(),
                venue_state=str(address.get("state", "")).strip(),
                home_team_id=str((sides["home"].get("team") or {}).get("id", "")).strip(),
                home_score=home_score,
                away_team_id=str((sides["away"].get("team") or {}).get("id", "")).strip(),
                away_score=away_score,
                notes=tuple(
                    sorted(
                        {
                            str(note.get("headline", "")).strip()
                            for note in (competition.get("notes") or [])
                            if str(note.get("headline", "")).strip()
                        }
                    )
                ),
                kickoff_utc=kickoff,
                source_locator=source.source_locator,
            )

    ordered = tuple(sorted(events.values(), key=lambda e: e.event_id))
    return ordered, {
        "events_admitted": len(ordered),
        "rows_set_aside": dict(sorted(setaside.items())),
    }


def _parse_espn_instant(value: str) -> datetime | None:
    for fmt in ("%Y-%m-%dT%H:%MZ", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# deterministic matching
# ---------------------------------------------------------------------------


@dataclass
class _MatchState:
    bound: dict[str, EspnEvent] = field(default_factory=dict)
    method: dict[str, str] = field(default_factory=dict)
    claimed: dict[str, str] = field(default_factory=dict)
    refused: dict[str, str] = field(default_factory=dict)


def team_identity_map(votes: Mapping[str, Mapping[str, int]]) -> dict[str, str]:
    """Resolve harvested votes into a name-to-ESPN-id map.

    A name that has ever been observed against two different ESPN ids is
    dropped, not decided by majority. One bad harvest would otherwise become a
    permanent alias that silently mis-binds every later game for that team, and
    the cost of dropping it is only that those games fall through to a weaker
    pass that also has to agree on the date and the score.
    """
    resolved: dict[str, str] = {}
    for name in sorted(votes):
        counts = votes[name]
        if len(counts) == 1:
            resolved[name] = next(iter(counts))
    return resolved


def _harvest(game: NcaaGame, event: EspnEvent, votes: dict[str, Counter]) -> None:
    """Pin NCAA names to ESPN ids by aligning the two feeds' scores.

    Only usable when the two scores in the game differ; a tie carries no
    information about which side is which, and a match where the feeds disagree
    on a score would pin the wrong side, so both are skipped.
    """
    if game.home_score == game.away_score:
        return
    if game.score_pair != event.score_pair:
        return
    by_score = {event.home_score: event.home_team_id, event.away_score: event.away_team_id}
    if len(by_score) != 2:
        return
    if game.home_seo:
        votes[game.home_seo][by_score[game.home_score]] += 1
    if game.away_seo:
        votes[game.away_seo][by_score[game.away_score]] += 1


def match_games(
    games: Sequence[NcaaGame], events: Sequence[EspnEvent]
) -> dict[str, Any]:
    """Match NCAA games to ESPN events and report the outcome per game.

    The public shape of the matcher: a status for every input game, the ESPN
    event id where one was bound, and the diagnostics the match report carries.
    Refusals are outcomes here, not omissions - a caller can tell a game that
    found nothing apart from a game that found too much.
    """
    state, alias, diagnostics = _match_games(games, events)
    outcomes = {}
    for game in games:
        event = state.bound.get(game.game_id)
        if event is not None:
            outcomes[game.game_id] = {
                "match_status": "MATCHED_EXACT",
                "match_method": state.method[game.game_id],
                "espn_event_id": event.event_id,
            }
        else:
            outcomes[game.game_id] = {
                "match_status": state.refused.get(game.game_id, "UNMATCHED"),
                "match_method": "",
                "espn_event_id": "",
            }
    return {
        "outcomes": outcomes,
        "team_identity": dict(alias),
        "diagnostics": diagnostics,
    }


def _match_games(
    games: Sequence[NcaaGame], events: Sequence[EspnEvent]
) -> tuple[_MatchState, dict[str, str], dict[str, Any]]:
    events_by_date: dict[date, list[EspnEvent]] = defaultdict(list)
    for event in events:
        events_by_date[event.local_date].append(event)
    for bucket in events_by_date.values():
        bucket.sort(key=lambda e: e.event_id)

    # A source slot carrying more than one row is the feed contradicting itself
    # about how many games were played. Both rows are refused.
    slots: dict[tuple[int, date, tuple[str, str]], list[NcaaGame]] = defaultdict(list)
    for game in games:
        key = (game.season, game.local_date, tuple(sorted((game.home_seo, game.away_seo))))
        slots[key].append(game)  # type: ignore[index]

    state = _MatchState()
    for slot_games in slots.values():
        if len(slot_games) > 1:
            for game in slot_games:
                state.refused[game.game_id] = "AMBIGUOUS_SOURCE_IDENTITY"

    ncaa_score_blocks: Counter[tuple[int, date, tuple[int, int]]] = Counter()
    for game in games:
        ncaa_score_blocks[(game.season, game.local_date, game.score_pair)] += 1

    votes: dict[str, Counter] = defaultdict(Counter)
    for key, slot_games in sorted(slots.items(), key=lambda kv: kv[1][0].game_id):
        if len(slot_games) != 1:
            continue
        game = slot_games[0]
        candidates = [
            event
            for event in _near(events_by_date, game)
            if event.score_pair == game.score_pair
        ]
        if len(candidates) == 1 and ncaa_score_blocks[
            (game.season, game.local_date, game.score_pair)
        ] == 1:
            _harvest(game, candidates[0], votes)

    alias = team_identity_map(votes)

    def bind(game: NcaaGame, candidates: Sequence[EspnEvent], method: str) -> bool:
        free = [
            event
            for event in candidates
            if state.claimed.get(event.event_id, game.game_id) == game.game_id
        ]
        if len(free) == 1:
            state.bound[game.game_id] = free[0]
            state.method[game.game_id] = method
            state.claimed[free[0].event_id] = game.game_id
            return True
        if len(free) > 1:
            state.refused[game.game_id] = "MULTIPLE_MATCH_REFUSED"
        return False

    def pending() -> list[NcaaGame]:
        return [
            game
            for game in games
            if game.game_id not in state.bound and game.game_id not in state.refused
        ]

    rounds = 0
    for rounds in range(1, 9):
        changed = False

        for game in pending():
            home_id = alias.get(game.home_seo)
            away_id = alias.get(game.away_seo)
            if not home_id or not away_id or home_id == away_id:
                continue
            candidates = [
                event
                for event in _near(events_by_date, game)
                if event.team_ids == {home_id, away_id}
            ]
            if bind(game, candidates, "IDENTITY_DATE"):
                changed = True

        for game in pending():
            known = {alias.get(game.home_seo), alias.get(game.away_seo)} - {None}
            if len(known) != 1:
                continue
            known_id = next(iter(known))
            candidates = [
                event
                for event in _near(events_by_date, game)
                if known_id in event.team_ids and event.score_pair == game.score_pair
            ]
            if bind(game, candidates, "PARTIAL_IDENTITY_SCORE"):
                changed = True
                _harvest(game, state.bound[game.game_id], votes)

        for game in pending():
            if ncaa_score_blocks[(game.season, game.local_date, game.score_pair)] != 1:
                continue
            candidates = [
                event
                for event in _near(events_by_date, game)
                if event.score_pair == game.score_pair
            ]
            if bind(game, candidates, "DATE_SCORE"):
                changed = True
                _harvest(game, state.bound[game.game_id], votes)

        refreshed = team_identity_map(votes)
        if refreshed != alias:
            alias = refreshed
            changed = True
        if not changed:
            break

    diagnostics = {
        "fixpoint_rounds": rounds,
        "team_identity_entries": len(alias),
        "team_identity_ambiguous": sorted(
            name for name, counts in votes.items() if len(counts) > 1
        ),
        "match_methods": dict(sorted(Counter(state.method.values()).items())),
        "refusals": dict(sorted(Counter(state.refused.values()).items())),
    }
    return state, alias, diagnostics


def _near(
    events_by_date: Mapping[date, list[EspnEvent]], game: NcaaGame
) -> list[EspnEvent]:
    """Candidate events on the game's Eastern date, plus one day either side.

    The window is not a fudge factor for bad data. The two feeds stamp the same
    kickoff from different scheduling systems, and a late kickoff that one
    records against the calendar day it started and the other against the day it
    was scheduled for differs by exactly one day. Widening further would start
    admitting a different week's games, so it does not widen.
    """
    seen: set[str] = set()
    out: list[EspnEvent] = []
    base = game.local_date
    for offset in (0, -1, 1):
        for event in events_by_date.get(base + timedelta(days=offset), ()):
            if event.season == game.season and event.event_id not in seen:
                seen.add(event.event_id)
                out.append(event)
    out.sort(key=lambda e: e.event_id)
    return out


# ---------------------------------------------------------------------------
# classification
# ---------------------------------------------------------------------------


def classify_game_type(event: EspnEvent | None) -> tuple[str, str]:
    """Return ``(game_type, evidence)`` from what the source says the contest is.

    Three source facts are consulted, in decreasing specificity: the competition
    type ESPN names, the contest name it carries in ``notes``, and the season
    part it files the game under. No week number is consulted, because a week
    number is a position in a schedule and not a statement about what the
    competition was - the rule the lane instruction names explicitly.

    Conference championship games sit inside ESPN's *regular season*, so the
    season part alone would file all 39 of them as regular-season games. The
    contest name is the more specific fact and wins where it exists.
    """
    if event is None:
        return "UNKNOWN_GAME_TYPE", ""

    named = _ESPN_COMPETITION_TYPE.get(event.competition_type)
    if named:
        return named, f"espn.competition.type={event.competition_type}"
    if event.competition_type == "Championship" and event.season_slug == "post-season":
        return "PLAYOFF", "espn.competition.type=Championship;espn.season=post-season"

    joined = " | ".join(event.notes)
    if event.season_slug == "post-season":
        if _PLAYOFF_NOTE.search(joined):
            return "PLAYOFF", f"espn.season=post-season;espn.notes={joined}"
        if _BOWL_NOTE.search(joined):
            return "BOWL", f"espn.season=post-season;espn.notes={joined}"
        return "OTHER_POSTSEASON", f"espn.season=post-season;espn.notes={joined}"

    if event.season_slug == "regular-season":
        if _CHAMPIONSHIP_NOTE.search(joined):
            return "CONFERENCE_CHAMPIONSHIP", f"espn.notes={joined}"
        return "REGULAR_SEASON", "espn.season=regular-season"

    return "UNKNOWN_GAME_TYPE", f"espn.season={event.season_slug or 'absent'}"


def _classify_venue(
    game: NcaaGame, event: EspnEvent | None, alias: Mapping[str, str]
) -> tuple[str, str, str, str, list[str]]:
    """Return ``(venue_classification, subject_venue, orientation, evidence, conflicts)``.

    The subject is the NCAA-designated home participant. Whether that
    designation corresponds to home field is exactly the question, so it is
    never assumed: the answer comes from ESPN's ``neutralSite`` flag and, when
    the site is not neutral, from which side ESPN independently designates as
    home.

    When the two sources disagree about which team hosted, neither is preferred.
    Preferring the NCAA orientation because it is tier 1 would be defensible
    only if the NCAA feed said anything about venue, and it does not; preferring
    ESPN because it is the venue source would be preferring the convenient
    answer. The row is marked ``SOURCE_CONFLICT_ORIENTATION`` and left
    unresolved, with both orientations preserved in their own columns.
    """
    conflicts: list[str] = []
    if event is None or event.neutral_site is None:
        return (
            "VENUE_UNRESOLVED",
            "VENUE_UNRESOLVED",
            "NOT_CHECKABLE",
            "VENUE_EVIDENCE_ABSENT",
            conflicts,
        )

    subject_id = alias.get(game.home_seo)
    opponent_id = alias.get(game.away_seo)
    if subject_id and subject_id == event.home_team_id:
        orientation = "AGREED"
    elif opponent_id and opponent_id == event.away_team_id:
        orientation = "AGREED"
    elif subject_id and subject_id == event.away_team_id:
        orientation = "DISAGREED"
    elif opponent_id and opponent_id == event.home_team_id:
        orientation = "DISAGREED"
    else:
        orientation = "NOT_CHECKABLE"

    if event.neutral_site:
        # At a neutral site one source's home designation is a bookkeeping slot
        # rather than a claim about hosting, so a difference between the two is
        # not a conflict about anything. The comparison is still recorded.
        return (
            "NEUTRAL_SITE",
            "NEUTRAL_SITE",
            f"{orientation}_AT_NEUTRAL_SITE",
            "VENUE_EVIDENCE_BOUND",
            conflicts,
        )

    if orientation == "AGREED":
        return "HOME_AWAY_SITE", "HOME_FIELD", orientation, "VENUE_EVIDENCE_BOUND", conflicts
    if orientation == "DISAGREED":
        conflicts.append("SOURCE_CONFLICT_ORIENTATION")
        return (
            "HOME_AWAY_SITE",
            "VENUE_UNRESOLVED",
            orientation,
            "VENUE_EVIDENCE_BOUND",
            conflicts,
        )

    # The site is not neutral, but neither participant resolved to an ESPN id,
    # so which side hosted cannot be read back onto the subject. The game-level
    # fact survives; the subject-level one does not.
    return "HOME_AWAY_SITE", "VENUE_UNRESOLVED", orientation, "VENUE_EVIDENCE_BOUND", conflicts


def venue_hfa_disposition(subject_venue: str) -> str:
    """Which side a home-field adjustment attaches to, as a token.

    Deliberately returns no number. The governed V3 football-point HFA lives in
    :mod:`~.hfa` and this lane promotes nothing; what it can do is make the
    semantics checkable, and the semantics that matter are that a neutral site
    gives the adjustment to nobody and an unresolved venue gives it to nobody
    either - for opposite reasons, which is why they are different tokens.
    """
    if subject_venue == "HOME_FIELD":
        return "SUBJECT_RECEIVES_HFA"
    if subject_venue == "AWAY_FIELD":
        return "OPPONENT_RECEIVES_HFA"
    if subject_venue == "NEUTRAL_SITE":
        return "NO_HFA_APPLIES"
    return "HFA_NOT_DETERMINABLE"


# ---------------------------------------------------------------------------
# rows
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrichmentRow:
    values: tuple[tuple[str, str], ...]

    def __getitem__(self, key: str) -> str:
        return dict(self.values)[key]

    def as_dict(self) -> dict[str, str]:
        return dict(self.values)

    def as_row(self) -> tuple[str, ...]:
        mapping = dict(self.values)
        return tuple(mapping[column] for column in ENRICHMENT_COLUMNS)


def _local_kickoff(game: NcaaGame) -> tuple[str, str]:
    """Render the source's own local kickoff, or only the date if that is all.

    ``startTime`` is blank on a real minority of rows. The lane instruction is
    explicit that a known date with an unknown time is recorded as a date, so
    that is what happens - the time is not back-filled from the epoch, which
    would silently upgrade "the source did not say" into "the source said".
    """
    try:
        day = datetime.strptime(game.start_date_raw, "%m-%d-%Y").date()
    except ValueError:
        return "", ""
    match = _TIME_RE.match(game.start_time_raw)
    if not match:
        return day.isoformat(), ""
    hour = int(match.group(1)) % 12
    if match.group(3) == "PM":
        hour += 12
    return f"{day.isoformat()}T{hour:02d}:{int(match.group(2)):02d}:00", FEED_LOCAL_TIMEZONE


def _iso(instant: datetime) -> str:
    return instant.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "+00:00"
    )


def _division_of(
    membership: Mapping[str, Mapping[str, str]], season: int, seo: str
) -> str:
    return membership.get(str(season), {}).get(seo, "UNRESOLVED")


def _matchup(subject: str, opponent: str) -> str:
    pair = {subject, opponent}
    if pair == {"FBS"}:
        return "FBS_VS_FBS"
    if pair == {"FBS", "FCS"}:
        return "FBS_VS_FCS"
    if pair == {"FCS"}:
        return "FCS_VS_FCS"
    return "DIVISION_UNRESOLVED"


def _build_row(
    game: NcaaGame,
    event: EspnEvent | None,
    method: str,
    match_status: str,
    alias: Mapping[str, str],
    membership: Mapping[str, Mapping[str, str]],
) -> EnrichmentRow:
    (
        venue_classification,
        subject_venue,
        orientation_cross_source,
        evidence_status,
        conflicts,
    ) = _classify_venue(game, event, alias)
    game_type, game_type_evidence = classify_game_type(event)

    kickoff_ncaa = _iso(game.kickoff_utc)
    kickoff_espn = _iso(event.kickoff_utc) if event is not None else ""
    if event is None:
        kickoff_utc = kickoff_ncaa
    elif kickoff_ncaa == kickoff_espn:
        kickoff_utc = kickoff_ncaa
    else:
        # Two sources, two scheduled instants, no basis for preferring one. Both
        # are preserved in their own columns and the reconciled column is left
        # empty rather than filled with a coin toss.
        conflicts.append("SOURCE_CONFLICT_KICKOFF")
        kickoff_utc = ""

    if event is not None and event.score_pair != game.score_pair:
        conflicts.append("SOURCE_CONFLICT_SCORE")

    local_kickoff, local_zone = _local_kickoff(game)
    subject_division = _division_of(membership, game.season, game.home_seo)
    opponent_division = _division_of(membership, game.season, game.away_seo)

    authorities = [f"{NCAA_AUTHORITY}:{NCAA_AUTHORITY_TIER}"]
    locators = [game.source_locator]
    if event is not None:
        authorities.append(f"{ESPN_AUTHORITY}:{ESPN_AUTHORITY_TIER}")
        locators.append(event.source_locator)

    conflict_status = "|".join(sorted(set(conflicts))) or "NO_CONFLICT"
    usable = (
        subject_venue in {"HOME_FIELD", "AWAY_FIELD", "NEUTRAL_SITE"}
        and "SOURCE_CONFLICT_ORIENTATION" not in conflicts
    )

    values = {
        "game_id": game.game_id,
        "season": str(game.season),
        "week": str(game.week),
        "subject_team": game.home_char6,
        "opponent_team": game.away_char6,
        "source_home_team": game.home_short,
        "source_away_team": game.away_short,
        "source_orientation": "NCAA_DESIGNATED_HOME_IS_SUBJECT",
        "orientation_cross_source": orientation_cross_source,
        "subject_division": subject_division,
        "opponent_division": opponent_division,
        "division_matchup": _matchup(subject_division, opponent_division),
        "venue_classification": venue_classification,
        "subject_venue": subject_venue,
        "game_type": game_type,
        "game_type_evidence": game_type_evidence,
        "venue_name": event.venue_name if event else "",
        "venue_city": event.venue_city if event else "",
        "venue_state": event.venue_state if event else "",
        "neutral_site_flag": (
            "" if event is None or event.neutral_site is None else str(event.neutral_site).upper()
        ),
        "kickoff_local": local_kickoff,
        "kickoff_local_timezone": local_zone,
        "kickoff_utc": kickoff_utc,
        "kickoff_utc_ncaa": kickoff_ncaa,
        "kickoff_utc_espn": kickoff_espn,
        # Neither source carries a completion or observability instant. Empty on
        # every row, by construction, and asserted empty by the test suite.
        "completion_utc": "",
        "observability_utc": "",
        "match_status": match_status,
        "match_method": method,
        "espn_event_id": event.event_id if event else "",
        "source_authority": "|".join(authorities),
        "source_locator": " ".join(locators),
        "evidence_status": evidence_status,
        "conflict_status": conflict_status,
        "calibration_usability": (
            "EXPECTED_MARGIN_VENUE_READY" if usable else "EXPECTED_MARGIN_VENUE_UNRESOLVED"
        ),
    }
    return EnrichmentRow(tuple((column, values[column]) for column in ENRICHMENT_COLUMNS))


# ---------------------------------------------------------------------------
# build
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnrichmentResult:
    rows: tuple[EnrichmentRow, ...]
    match_report: dict[str, Any]
    custody: dict[str, Any]
    team_identity: dict[str, str]
    source_reports: dict[str, Any]

    def by_game_id(self) -> dict[str, EnrichmentRow]:
        return {row["game_id"]: row for row in self.rows}


def build_venue_enrichment(
    repo_root: Path, seasons: Sequence[int] = ADMITTED_SEASONS
) -> EnrichmentResult:
    """Build the enrichment layer from the raw bytes in custody."""
    lane_root = (
        repo_root / "reference" / "dynamic_weekly_mc_v3" / "venue_enrichment_r1"
    )
    manifest_path = lane_root / "V3_VENUE_R1_SOURCE_ACQUISITION_MANIFEST.json"
    if not manifest_path.is_file():
        raise VenueEnrichmentError(f"acquisition manifest not found: {manifest_path}")

    sources = load_acquisition_manifest(manifest_path)
    custody = verify_raw_custody(sources, repo_root)
    games, ncaa_report = load_ncaa_games(sources, repo_root, seasons)
    events, espn_report = load_espn_events(sources, repo_root, seasons)
    membership = ncaa_report["division_membership"]

    state, alias, diagnostics = _match_games(games, events)

    rows: list[EnrichmentRow] = []
    for game in games:
        event = state.bound.get(game.game_id)
        if event is not None:
            status, method = "MATCHED_EXACT", state.method[game.game_id]
        elif game.game_id in state.refused:
            status, method = state.refused[game.game_id], ""
        else:
            status, method = "UNMATCHED", ""
        rows.append(_build_row(game, event, method, status, alias, membership))

    ordered = tuple(sorted(rows, key=lambda r: r["game_id"]))
    _assert_join_uniqueness(ordered)

    statuses = Counter(row["match_status"] for row in ordered)
    match_report = {
        "games_considered": len(ordered),
        "espn_events_available": len(events),
        "matched_exactly": statuses.get("MATCHED_EXACT", 0),
        "multiple_match_refused": statuses.get("MULTIPLE_MATCH_REFUSED", 0),
        "ambiguous_source_identity": statuses.get("AMBIGUOUS_SOURCE_IDENTITY", 0),
        "unmatched": statuses.get("UNMATCHED", 0),
        "espn_events_bound": len(state.claimed),
        "espn_event_bound_at_most_once": len(state.claimed)
        == statuses.get("MATCHED_EXACT", 0),
        **diagnostics,
    }
    return EnrichmentResult(
        rows=ordered,
        match_report=match_report,
        custody=custody,
        team_identity=dict(alias),
        source_reports={"ncaa": ncaa_report, "espn": espn_report},
    )


def _assert_join_uniqueness(rows: Sequence[EnrichmentRow]) -> None:
    """Every enrichment row binds to one and only one historical game."""
    game_ids = Counter(row["game_id"] for row in rows)
    repeated = sorted(gid for gid, count in game_ids.items() if count > 1)
    if repeated:
        raise VenueEnrichmentError(
            f"enrichment join identity is not unique: {repeated[:5]}"
        )
    events = Counter(
        row["espn_event_id"] for row in rows if row["espn_event_id"]
    )
    shared = sorted(eid for eid, count in events.items() if count > 1)
    if shared:
        raise VenueEnrichmentError(
            f"ESPN event bound to more than one historical game: {shared[:5]}"
        )


def render_enrichment_csv(rows: Sequence[EnrichmentRow]) -> bytes:
    """Render the enrichment table as deterministic LF-terminated CSV bytes."""
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(ENRICHMENT_COLUMNS)
    for row in sorted(rows, key=lambda r: r["game_id"]):
        writer.writerow(row.as_row())
    return buffer.getvalue().encode("utf-8")


# ---------------------------------------------------------------------------
# reporting
# ---------------------------------------------------------------------------


def coverage_report(rows: Sequence[EnrichmentRow]) -> dict[str, Any]:
    """Count what was resolved, what was not, and over which subsets."""

    def count(predicate) -> int:
        return sum(1 for row in rows if predicate(row))

    resolved = lambda row: row["subject_venue"] != "VENUE_UNRESOLVED"  # noqa: E731
    ccg = lambda row: row["game_type"] == "CONFERENCE_CHAMPIONSHIP"  # noqa: E731
    bowl = lambda row: row["game_type"] == "BOWL"  # noqa: E731
    fbs_fcs = lambda row: row["division_matchup"] == "FBS_VS_FCS"  # noqa: E731

    fbs_fcs_rows = [row for row in rows if fbs_fcs(row)]
    return {
        "games_considered": len(rows),
        "venue_resolved_count": count(resolved),
        "venue_unresolved_count": count(lambda r: not resolved(r)),
        "neutral_count": count(lambda r: r["subject_venue"] == "NEUTRAL_SITE"),
        "home_field_count": count(lambda r: r["subject_venue"] == "HOME_FIELD"),
        "away_field_count": count(lambda r: r["subject_venue"] == "AWAY_FIELD"),
        "game_type_resolved_count": count(lambda r: r["game_type"] != "UNKNOWN_GAME_TYPE"),
        "game_type_unresolved_count": count(lambda r: r["game_type"] == "UNKNOWN_GAME_TYPE"),
        "game_type_breakdown": dict(sorted(Counter(r["game_type"] for r in rows).items())),
        # Reconciled: both sources state the same scheduled instant. The wider
        # count is every row where at least one source states one, which is
        # every row, since the NCAA feed always carries an epoch.
        "kickoff_timestamp_count": count(lambda r: bool(r["kickoff_utc"])),
        "kickoff_timestamp_any_source_count": count(
            lambda r: bool(r["kickoff_utc_ncaa"] or r["kickoff_utc_espn"])
        ),
        "kickoff_local_count": count(lambda r: bool(r["kickoff_local"])),
        "kickoff_local_time_of_day_count": count(lambda r: "T" in r["kickoff_local"]),
        "kickoff_local_date_only_count": count(
            lambda r: bool(r["kickoff_local"]) and "T" not in r["kickoff_local"]
        ),
        "orientation_cross_source_breakdown": dict(
            sorted(Counter(r["orientation_cross_source"] for r in rows).items())
        ),
        "orientation_cross_source_disagreements": count(
            lambda r: r["orientation_cross_source"].startswith("DISAGREED")
        ),
        "completion_timestamp_count": count(lambda r: bool(r["completion_utc"])),
        "observability_timestamp_count": count(lambda r: bool(r["observability_utc"])),
        "fbs_vs_fcs_total": len(fbs_fcs_rows),
        "fbs_vs_fcs_venue_resolved": sum(1 for r in fbs_fcs_rows if resolved(r)),
        "fbs_vs_fcs_venue_unresolved": sum(1 for r in fbs_fcs_rows if not resolved(r)),
        "fbs_vs_fcs_fbs_home": sum(
            1
            for r in fbs_fcs_rows
            if r["subject_division"] == "FBS" and r["subject_venue"] == "HOME_FIELD"
        ),
        "fbs_vs_fcs_fcs_home": sum(
            1
            for r in fbs_fcs_rows
            if r["subject_division"] == "FCS" and r["subject_venue"] == "HOME_FIELD"
        ),
        "fbs_vs_fcs_neutral": sum(
            1 for r in fbs_fcs_rows if r["subject_venue"] == "NEUTRAL_SITE"
        ),
        "fbs_vs_fcs_ambiguous": sum(1 for r in fbs_fcs_rows if not resolved(r)),
        "division_matchup_breakdown": dict(
            sorted(Counter(r["division_matchup"] for r in rows).items())
        ),
        "conference_championship_count": count(ccg),
        "conference_championship_venue_resolved": count(
            lambda r: ccg(r) and resolved(r)
        ),
        "conference_championship_neutral": count(
            lambda r: ccg(r) and r["subject_venue"] == "NEUTRAL_SITE"
        ),
        "conference_championship_home_field": count(
            lambda r: ccg(r) and r["subject_venue"] == "HOME_FIELD"
        ),
        "bowl_count": count(bowl),
        "bowl_venue_resolved": count(lambda r: bowl(r) and resolved(r)),
        "playoff_count": count(lambda r: r["game_type"] == "PLAYOFF"),
        "match_status_breakdown": dict(
            sorted(Counter(r["match_status"] for r in rows).items())
        ),
        "evidence_status_breakdown": dict(
            sorted(Counter(r["evidence_status"] for r in rows).items())
        ),
        "conflict_status_breakdown": dict(
            sorted(Counter(r["conflict_status"] for r in rows).items())
        ),
        "source_conflict_count": count(lambda r: r["conflict_status"] != "NO_CONFLICT"),
        "unmatched_count": count(lambda r: r["match_status"] != "MATCHED_EXACT"),
        "calibration_usability_breakdown": dict(
            sorted(Counter(r["calibration_usability"] for r in rows).items())
        ),
        "expected_margin_venue_ready": count(
            lambda r: r["calibration_usability"] == "EXPECTED_MARGIN_VENUE_READY"
        ),
        "season_breakdown": dict(sorted(Counter(r["season"] for r in rows).items())),
    }


def conflict_report(rows: Sequence[EnrichmentRow]) -> dict[str, Any]:
    """Preserve both evidence records for every game the sources disagree on.

    Nothing is resolved here. A conflict row carries what each source said, so a
    reader can see the disagreement rather than a winner - which is the whole
    requirement, since preferring the tier-1 source on a fact it does not carry
    or the tier-5 source because it is more convenient would both be the same
    mistake wearing different clothes.

    The kickoff distribution is published alongside because the shape of the
    disagreement is itself the finding: the offsets are dominated by a
    one-hour displacement concentrated in 2021, which is a property of that
    season's NCAA feed rather than noise spread evenly over four years.
    """
    conflicts = [row for row in rows if row["conflict_status"] != "NO_CONFLICT"]
    deltas: Counter[int] = Counter()
    by_season: Counter[str] = Counter()
    for row in conflicts:
        ncaa, espn = row["kickoff_utc_ncaa"], row["kickoff_utc_espn"]
        if "SOURCE_CONFLICT_KICKOFF" not in row["conflict_status"] or not (ncaa and espn):
            continue
        minutes = int(
            (datetime.fromisoformat(espn) - datetime.fromisoformat(ncaa)).total_seconds()
            // 60
        )
        deltas[minutes] += 1
        by_season[row["season"]] += 1

    return {
        "conflict_count": len(conflicts),
        "conflict_status_breakdown": dict(
            sorted(Counter(r["conflict_status"] for r in conflicts).items())
        ),
        "kickoff_delta_minutes_espn_minus_ncaa": dict(sorted(deltas.items())),
        "kickoff_conflicts_by_season": dict(sorted(by_season.items())),
        "conflict_blocks_venue_resolution": sum(
            1
            for r in conflicts
            if "SOURCE_CONFLICT_ORIENTATION" in r["conflict_status"]
        ),
        "records": [
            {
                "game_id": row["game_id"],
                "season": row["season"],
                "conflict_status": row["conflict_status"],
                "subject_team": row["subject_team"],
                "opponent_team": row["opponent_team"],
                "ncaa_evidence": {
                    "source_authority": NCAA_AUTHORITY,
                    "source_authority_tier": NCAA_AUTHORITY_TIER,
                    "kickoff_utc": row["kickoff_utc_ncaa"],
                    "designated_home": row["source_home_team"],
                    "designated_away": row["source_away_team"],
                },
                "espn_evidence": {
                    "source_authority": ESPN_AUTHORITY,
                    "source_authority_tier": ESPN_AUTHORITY_TIER,
                    "kickoff_utc": row["kickoff_utc_espn"],
                    "event_id": row["espn_event_id"],
                    "neutral_site_flag": row["neutral_site_flag"],
                    "venue_name": row["venue_name"],
                },
                "resolution": "BOTH_PRESERVED_NEITHER_SELECTED",
            }
            for row in conflicts
        ],
    }


def corpus_join_report(
    rows: Sequence[EnrichmentRow],
    corpus_csv: bytes,
    exclusion_report: bytes | None = None,
) -> dict[str, Any]:
    """Join the enrichment onto Historical Observation Corpus R6, read only.

    The corpus is another lane's artifact and is never copied here, rewritten or
    re-decided. It is read as bytes, digested, and used for exactly one purpose:
    to report how many of its 2,241 admitted observations this enrichment can
    actually answer the venue question for. The digest is recorded so a later
    reader can tell whether the join was computed against the corpus they hold.
    """
    text = corpus_csv.decode("utf-8")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    corpus_rows = list(reader)
    corpus_ids = [row["game_id"] for row in corpus_rows]
    unique_ids = set(corpus_ids)
    enrichment = {row["game_id"]: row for row in rows}

    joined = [enrichment[gid] for gid in sorted(unique_ids) if gid in enrichment]
    missing = sorted(unique_ids - set(enrichment))

    # The join is verified on the fact both artifacts derive from the same NCAA
    # bytes: the corpus's event_time and this lane's NCAA kickoff instant are
    # both that game's startTimeEpoch. Comparing team codes instead would prove
    # nothing, because the corpus renames teams through its own canonical
    # identity authority and this lane deliberately passes the source's names
    # through unrenamed.
    kickoff_checked = 0
    kickoff_agreements = 0
    kickoff_disagreements: list[str] = []
    for corpus_row in corpus_rows:
        row = enrichment.get(corpus_row["game_id"])
        if row is None:
            continue
        kickoff_checked += 1
        if corpus_row.get("event_time", "") == row["kickoff_utc_ncaa"]:
            kickoff_agreements += 1
        else:
            kickoff_disagreements.append(corpus_row["game_id"])

    coverage = coverage_report(joined)
    fbs_fcs = _fbs_fcs_inventory_coverage(rows, exclusion_report)
    return {
        "corpus_identified_fbs_vs_fcs": fbs_fcs,
        "corpus_id": "V3_R6_HISTORICAL_OBSERVATION_CORPUS",
        "corpus_sha256": _sha256(corpus_csv),
        "corpus_byte_length": len(corpus_csv),
        "corpus_rows": len(corpus_rows),
        "corpus_distinct_game_ids": len(unique_ids),
        "joined_rows": len(joined),
        "corpus_rows_not_enriched": len(missing),
        "corpus_rows_not_enriched_sample": missing[:20],
        "kickoff_identity_checked": kickoff_checked,
        "kickoff_identity_agreements": kickoff_agreements,
        "kickoff_identity_disagreements": kickoff_disagreements[:20],
        "join_is_one_to_one": len(joined) == len(set(r["game_id"] for r in joined)),
        "coverage": coverage,
    }


def _fbs_fcs_inventory_coverage(
    rows: Sequence[EnrichmentRow], exclusion_report: bytes | None
) -> dict[str, Any]:
    """Venue coverage over the FBS-versus-FCS games the corpus lane inventoried.

    Those 43 games are not corpus *rows*. R6 identified them and then excluded
    them, because ``opponent_division`` is off its governed allowlist and the
    FCS point-scale adapter is an open blocker. The lane instruction still asks
    for them, and the reason is worth stating: whoever eventually closes that
    adapter will need to know which side hosted, and finding that out is cheap
    now and expensive later. Nothing here estimates an FCS point scale.
    """
    if exclusion_report is None:
        return {"inventory_available": False}

    payload = json.loads(exclusion_report.decode("utf-8"))
    inventory = payload.get("fbs_vs_fcs_inventory") or []
    by_id = {row["game_id"]: row for row in rows}

    records = []
    for entry in inventory:
        game_id = f"NCAA-{entry['season']}-{entry['source_game_id']}"
        row = by_id.get(game_id)
        records.append(
            {
                "game_id": game_id,
                "fbs_side": entry.get("fbs_side", ""),
                "fcs_side": entry.get("fcs_side", ""),
                "source_home": entry.get("source_home", ""),
                "source_away": entry.get("source_away", ""),
                "enriched": row is not None,
                "subject_division": row["subject_division"] if row else "UNRESOLVED",
                "opponent_division": row["opponent_division"] if row else "UNRESOLVED",
                "subject_venue": row["subject_venue"] if row else "VENUE_UNRESOLVED",
                "venue_name": row["venue_name"] if row else "",
                "game_type": row["game_type"] if row else "UNKNOWN_GAME_TYPE",
                "match_status": row["match_status"] if row else "UNMATCHED",
            }
        )

    def tally(predicate) -> int:
        return sum(1 for record in records if predicate(record))

    # Which division hosted is read from the division this lane derived from the
    # two scoreboards, not from the inventory's own labels - the inventory names
    # sides by team code and names participants in full, and comparing the two
    # would be a string coincidence rather than a division fact.
    fbs_home = tally(
        lambda r: r["subject_venue"] == "HOME_FIELD" and r["subject_division"] == "FBS"
    )
    fcs_home = tally(
        lambda r: r["subject_venue"] == "HOME_FIELD" and r["subject_division"] == "FCS"
    )
    return {
        "inventory_available": True,
        "inventory_count": len(records),
        "enriched_count": tally(lambda r: r["enriched"]),
        "venue_resolved_count": tally(
            lambda r: r["subject_venue"] != "VENUE_UNRESOLVED"
        ),
        "venue_unresolved_count": tally(
            lambda r: r["subject_venue"] == "VENUE_UNRESOLVED"
        ),
        "fbs_home_vs_fcs": fbs_home,
        "fcs_home_vs_fbs": fcs_home,
        "neutral_fbs_vs_fcs": tally(lambda r: r["subject_venue"] == "NEUTRAL_SITE"),
        "ambiguous_fbs_vs_fcs": tally(
            lambda r: r["subject_venue"] == "VENUE_UNRESOLVED"
        ),
        "home_side_division_unresolved": tally(
            lambda r: r["subject_venue"] == "HOME_FIELD"
            and r["subject_division"] not in {"FBS", "FCS"}
        ),
        "fcs_point_scale_estimated": False,
        "records": records,
    }
