"""Construction of the R6 governed historical observation corpus.

R5 searched the filesystem for an admissible historical result set and found
none: the one real subset it located covered a single season, carried no kickoff
instants, and keyed games on a team pair that collided the moment two teams met
twice. This module builds the corpus R5 could not find, from bytes retrieved
from the NCAA's own scoreboard feed by
``scripts/acquire_ncaa_scoreboard_r6.py``.

What this module is *not* is as load-bearing as what it is. It derives no
rating, fits no parameter, and writes no configuration. It turns raw bytes into
observed facts, refuses everything it cannot ground in those bytes, and records
the refusals with reasons that reconcile against the input row for row.

The pipeline, in the order the gates actually run::

    raw bytes  ->  custody re-verification
               ->  canonical team identity
               ->  observed division (FBS / FCS), read from the source
               ->  unique game identity
               ->  chronological order
               ->  admission
               ->  team-season coverage
               ->  temporal split

Six decisions in here are governance decisions rather than engineering ones, and
each is made the conservative way:

*Division is read, not guessed.* The NCAA publishes an ``fbs`` scoreboard and an
``fcs`` scoreboard as distinct game sets. A game appears in both exactly when it
crosses divisions, so membership follows from set intersection rather than from
a conference-name allowlist someone would have had to author. That matters
because a hand-written allowlist is an assumption wearing a lookup table.

*FBS-versus-FCS observations are identified and then excluded.* The data
contract asks for ``opponent_division`` precisely so that "FCS games must be
identifiable so they can be excluded rather than silently fitted on an
unresolved scale", the scale in question being the still-open blocker
``model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER``. The field is not on the
governed allowlist, so it is not emitted; it is used as an admission gate and
the excluded games are inventoried in full, so a later FCS-scale lane inherits a
reconciled sample instead of starting over.

*Venue is refused outright.* The contract wants ``HOME|AWAY|NEUTRAL`` from the
source. The feed designates a home and an away side but publishes nothing that
distinguishes a neutral site from a true home game. Emitting ``HOME`` for every
designated home team would assert that no game in four seasons was played at a
neutral site, which is false, so ``venue`` is classified BLOCKED and left out.
The consequence is recorded rather than buried: ``actual_margin`` is signed from
the *designated home* team's perspective, so any downstream use that ignores
that will misattribute home-field advantage.

*Overtime is visible and still not admitted.* ``finalMessage`` carries
``FINAL (2OT)``, which is the field the contract wanted and could not get.
``overtime_periods`` is nonetheless not on the governed allowlist, so it is
counted in the reports and kept out of the corpus. Availability is not
admission, and this lane has no authority to widen the allowlist.

*Repeat matchups are distinguished by the source's own week.* Two teams may meet
twice in a season — a regular-season game and a conference championship — and
R5's team-pair key collided on exactly that. They never meet twice in the same
week, so two records sharing a season, a canonical pair and a source week are
one game published twice, not two games. Those are refused rather than
de-duplicated by picking one, because picking one is choosing which of two
disagreeing records is true.

*The corpus stops at observed facts.* ``pregame_team_rating``,
``expected_margin`` and ``prior_rating_state`` are model outputs. No V3 run ever
produced them for a 2021 game, and reconstructing them from a rating fitted on
the same season is the specific leak the contract names. They stay BLOCKED, and
:func:`register_dataset` therefore refuses this corpus. That refusal is asserted
in the test suite rather than worked around: the corpus is an observation set,
and calling it a calibration dataset would be the whole failure this lane exists
to avoid.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import io
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .calibration import require_temporal_split_integrity
from .calibration import CALIBRATION_OBSERVATION_COLUMNS
from .calibration_evidence import (
    ADMISSIBLE_SOURCE_AUTHORITY_CLASSES,
    SYNTHETIC_PROVENANCE_PATTERNS,
    require_minimum_volume,
)
from .errors import GovernanceBlock, InputValidationError

__all__ = [
    "ADMITTED_SEASONS",
    "CORPUS_COLUMNS",
    "CORPUS_ID",
    "CanonicalEntity",
    "CanonicalIdentityAuthority",
    "CorpusBuild",
    "EXCLUSION_REASONS",
    "FIELD_CLASSIFICATION",
    "MINIMUM_GAMES_PER_TEAM_SEASON",
    "NCAA_ABBREVIATION_EXPANSIONS",
    "ObservationRow",
    "RawSourceRecord",
    "SEASON_SPLIT_ASSIGNMENT",
    "TeamResolution",
    "build_observation_corpus",
    "corpus_registration_receipt",
    "derive_subsequent_outcomes",
    "load_acquisition_manifest",
    "load_canonical_identity_authority",
    "render_corpus_csv",
    "resolve_source_team",
    "verify_raw_custody",
]

CORPUS_ID = "V3_R6_HISTORICAL_OBSERVATION_CORPUS"

#: Seasons admitted to the corpus. 2025 was retrieved and is *not* here: the
#: feed's 2025 week files were last updated before those games were played and
#: every game in them still reads ``pre`` with blank scores. The bytes are kept
#: as the evidence for that finding and the season is refused as unfinalised.
ADMITTED_SEASONS = (2021, 2022, 2023, 2024)

#: Whole-season split boundaries. Season granularity is chosen over any finer
#: cut because it is the only boundary that needs no argument: the gap between
#: the last game of one season and the first of the next is months wide, so the
#: ordering requirement holds with room to spare rather than by a few hours.
SEASON_SPLIT_ASSIGNMENT: Mapping[int, str] = {
    2021: "training",
    2022: "training",
    2023: "validation",
    2024: "holdout",
}

#: Emitted columns. Every one of these is on the contract's governed allowlist.
#: The corpus is a strict subset of that allowlist, never an extension of it.
CORPUS_COLUMNS = (
    "game_id",
    "season",
    "week",
    "event_time",
    "team",
    "opponent",
    "actual_margin",
    "game_result",
    "source_provenance",
    "recorded_at",
    "split",
)

#: The contract's per-team floor, restated here because it is enforced by
#: pruning rather than only reported.
MINIMUM_GAMES_PER_TEAM_SEASON = 8

EXCLUSION_REASONS = (
    "SOURCE_SEASON_NOT_FINALISED",
    "MISSING_SOURCE_GAME_IDENTIFIER",
    "GAME_NOT_FINAL",
    "MISSING_REQUIRED_SCORE",
    "CHRONOLOGY_UNRESOLVED",
    "UNRESOLVED_TEAM_IDENTITY",
    "AMBIGUOUS_TEAM_IDENTITY",
    "SELF_MATCHUP",
    "UNRESOLVED_OPPONENT_DIVISION",
    "FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED",
    "OUTSIDE_GOVERNED_SCOPE_FCS_VS_FCS",
    "DUPLICATE_OR_AMBIGUOUS_GAME_ID",
    "INSUFFICIENT_TEAM_SEASON_COVERAGE",
)

#: How each contract field stands in this corpus. Emitted verbatim into the R6
#: documentation and the discovery record so the classification is one artifact
#: rather than a claim repeated in three places that can drift apart.
FIELD_CLASSIFICATION: Mapping[str, Mapping[str, str]] = {
    "game_id": {
        "class": "DERIVED",
        "basis": "NCAA gameID namespaced by season: NCAA-<season>-<gameID>.",
    },
    "season": {"class": "FACT", "basis": "Season path segment of the source URL."},
    "week": {"class": "FACT", "basis": "Week path segment of the source URL."},
    "event_time": {
        "class": "FACT",
        "basis": (
            "startTimeEpoch, a Unix instant, rendered UTC. Source-scheduled "
            "start, not an observed kickoff; the distinction is recorded in the "
            "chronology report and never smoothed over."
        ),
    },
    "team": {
        "class": "DERIVED",
        "basis": (
            "NCAA-designated home side resolved to a canonical schedule_id "
            "through the 2026 canonical master."
        ),
    },
    "opponent": {
        "class": "DERIVED",
        "basis": "NCAA-designated away side, resolved the same way.",
    },
    "actual_margin": {
        "class": "DERIVED",
        "basis": (
            "home score minus away score, signed from the designated home "
            "team's perspective because venue is BLOCKED."
        ),
    },
    "game_result": {
        "class": "DERIVED",
        "basis": "W/L/T from the subject team's margin.",
    },
    "source_provenance": {
        "class": "FACT",
        "basis": "Source authority and the exact URL the row was retrieved from.",
    },
    "recorded_at": {
        "class": "FACT",
        "basis": "UTC instant the raw file was retrieved, from the acquisition manifest.",
    },
    "split": {
        "class": "DERIVED",
        "basis": "Whole-season temporal assignment; see SEASON_SPLIT_ASSIGNMENT.",
    },
    "venue": {
        "class": "BLOCKED",
        "basis": (
            "The feed designates home and away but publishes no neutral-site "
            "indicator, and none was found on any NCAA endpoint. Emitting HOME "
            "for every designated home team would assert that no game was "
            "played at a neutral site."
        ),
    },
    "observed_at": {
        "class": "BLOCKED",
        "basis": (
            "No per-row observability instant. The payload's updated_at carries "
            "no zone and the HTTP Last-Modified header is a CDN stamp identical "
            "across every season."
        ),
    },
    "pregame_team_rating": {
        "class": "BLOCKED",
        "basis": "Model output. No V3 run produced a pregame rating for these games.",
    },
    "pregame_opponent_rating": {"class": "BLOCKED", "basis": "Model output, as above."},
    "expected_margin": {
        "class": "BLOCKED",
        "basis": (
            "Model output, and doubly blocked: the rating-to-margin transform it "
            "would be expressed through is itself unratified."
        ),
    },
    "prior_rating_state": {
        "class": "BLOCKED",
        "basis": "Model output. No V3 week-open state was ever serialised for these games.",
    },
    "subsequent_outcomes": {
        "class": "DERIVED_AVAILABLE_NOT_EMITTED",
        "basis": (
            "Reconstructible from the corpus by derive_subsequent_outcomes, "
            "which orders each team's games by event_time. Not emitted: a "
            "denormalised copy of facts already in the corpus is a second place "
            "for them to be wrong."
        ),
    },
    "model_version": {
        "class": "BLOCKED",
        "basis": "No model produced these rows; they are observations.",
    },
    "configuration_version": {"class": "BLOCKED", "basis": "As model_version."},
    "games_played_to_date": {
        "class": "NOT_GOVERNED_DERIVABLE",
        "basis": (
            "Walk-forward countable from the corpus. Still absent from the "
            "governed allowlist, so not emitted and no ruling is claimed."
        ),
    },
    "game_type": {
        "class": "NOT_GOVERNED_UNAVAILABLE",
        "basis": (
            "contestName and bracketRound are blank on every retrieved row. The "
            "feed carries no postseason games at all, so regular season and "
            "conference championships are present and indistinguishable."
        ),
    },
    "overtime_periods": {
        "class": "NOT_GOVERNED_AVAILABLE",
        "basis": (
            "finalMessage carries FINAL (OT) through FINAL (4OT). Counted in the "
            "reports; not admitted, because availability is not admission."
        ),
    },
    "opponent_division": {
        "class": "NOT_GOVERNED_AVAILABLE_USED_AS_GATE",
        "basis": (
            "Determined by fbs/fcs feed intersection. Used to exclude "
            "cross-division games; not emitted."
        ),
    },
}

#: NCAA renders school names in its own abbreviated house style. Each entry
#: expands one of those abbreviations to the long form; a resolution is only
#: accepted when the expansion lands on an *exact* canonical key, so a wrong
#: expansion produces no match rather than a wrong match.
NCAA_ABBREVIATION_EXPANSIONS: Mapping[str, str] = {
    "ala.": "Alabama",
    "ariz.": "Arizona",
    "ark.": "Arkansas",
    "caro.": "Carolina",
    "cent.": "Central",
    "colo.": "Colorado",
    "conn.": "Connecticut",
    "fla.": "Florida",
    "ga.": "Georgia",
    "ill.": "Illinois",
    "ky.": "Kentucky",
    "la.": "Louisiana",
    "md.": "Maryland",
    "mich.": "Michigan",
    "minn.": "Minnesota",
    "miss.": "Mississippi",
    "mo.": "Missouri",
    "neb.": "Nebraska",
    "nor.": "Northern",
    "okla.": "Oklahoma",
    "ore.": "Oregon",
    "sou.": "Southern",
    "st.": "State",
    "tenn.": "Tennessee",
    "tex.": "Texas",
    "va.": "Virginia",
    "wash.": "Washington",
    "wis.": "Wisconsin",
}

_OVERTIME = re.compile(r"FINAL \((\d*)OT\)")
_INDEX_ROW = re.compile(
    r"^\|\s*(\d+)\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|\s*`([^`]+)`\s*\|"
    r"\s*`([^`]+)`\s*\|\s*`([^`]+)`\s*\|",
    re.M,
)
_AKA = re.compile(r"### \d+ — .*?\(`([^`]+)`\)\n(?:.*?\n)*?- `aka_name`: `([^`]*)`")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _normalise_name(value: str) -> str:
    """Fold a team name to a comparison key.

    Case, whitespace runs, the curly apostrophe and a trailing period are
    presentation. Nothing else is touched — in particular a parenthetical
    qualifier on the *source* side is left alone, because ``Miami (FL)`` and
    ``Miami (OH)`` are two schools and dropping the qualifier to force a match
    is exactly the silent mis-mapping this resolver exists to prevent.
    """
    folded = value.strip().casefold().replace("’", "'")
    return re.sub(r"\s+", " ", folded).rstrip(".")


def _expand_abbreviations(name: str) -> str:
    parts = re.split(r"(\s+|-)", name)
    return "".join(
        NCAA_ABBREVIATION_EXPANSIONS.get(part.strip().casefold(), part) for part in parts
    )


@dataclass(frozen=True)
class RawSourceRecord:
    """One retrieved file, bound to the bytes it was retrieved as.

    Two digests, deliberately. ``stored_sha256`` covers the gzip container git
    holds; ``raw_sha256`` covers the response body inside it and is the digest
    custody is asserted over. Checking only the container would pass a file
    whose container was rebuilt around different content, and checking only the
    content would miss a container that no longer decompresses to it.
    """

    url: str
    season: int
    division: str
    week: int
    stored_path: str
    raw_sha256: str
    raw_byte_length: int
    stored_sha256: str
    stored_byte_length: int
    source_authority: str
    source_authority_class: str
    retrieval_method: str
    retrieved_at: str
    game_count: int

    def __post_init__(self) -> None:
        if self.source_authority_class not in ADMISSIBLE_SOURCE_AUTHORITY_CLASSES:
            raise GovernanceBlock(
                f"Raw source {self.url} is classified "
                f"{self.source_authority_class!r}. Only "
                f"{list(ADMISSIBLE_SOURCE_AUTHORITY_CLASSES)} may be admitted as "
                "governed observation evidence."
            )
        lowered = f"{self.source_authority} {self.retrieval_method}".casefold()
        hits = sorted(p for p in SYNTHETIC_PROVENANCE_PATTERNS if p in lowered)
        if hits:
            raise GovernanceBlock(
                f"Raw source {self.url} declares provenance matching {hits}. The "
                "calibration data contract refuses synthetic and simulated "
                "observation sets outright."
            )
        for name, digest in (("raw_sha256", self.raw_sha256), ("stored_sha256", self.stored_sha256)):
            if len(digest) != 64:
                raise InputValidationError(f"{name} {digest!r} is not a SHA-256.")

    def read(self, repo_root: Path) -> bytes:
        """Re-read and re-verify, returning the decompressed response body."""
        target = repo_root / self.stored_path
        if not target.exists():
            raise GovernanceBlock(
                f"Raw source {self.url} was captured to {self.stored_path}, which is "
                "no longer present. Evidence that cannot be re-read is not evidence."
            )
        container = target.read_bytes()
        if _sha256(container) != self.stored_sha256:
            raise GovernanceBlock(
                f"Raw source {self.stored_path} hashes to {_sha256(container)}, not "
                f"the registered {self.stored_sha256}. The cited bytes are not the "
                "present bytes."
            )
        if len(container) != self.stored_byte_length:
            raise GovernanceBlock(
                f"Raw source {self.stored_path} holds {len(container)} bytes, not "
                f"the registered {self.stored_byte_length}."
            )
        try:
            body = gzip.decompress(container)
        except OSError as exc:  # pragma: no cover - a corrupt container fails the digest first
            raise GovernanceBlock(
                f"Raw source {self.stored_path} did not decompress: {exc}"
            ) from exc
        if _sha256(body) != self.raw_sha256:
            raise GovernanceBlock(
                f"Raw source {self.stored_path} decompresses to {_sha256(body)}, not "
                f"the registered response digest {self.raw_sha256}."
            )
        if len(body) != self.raw_byte_length:
            raise GovernanceBlock(
                f"Raw source {self.stored_path} decompresses to {len(body)} bytes, "
                f"not the registered {self.raw_byte_length}."
            )
        return body

    def as_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "season": self.season,
            "division": self.division,
            "week": self.week,
            "stored_path": self.stored_path,
            "raw_sha256": self.raw_sha256,
            "raw_byte_length": self.raw_byte_length,
            "stored_sha256": self.stored_sha256,
            "stored_byte_length": self.stored_byte_length,
            "source_authority": self.source_authority,
            "source_authority_class": self.source_authority_class,
            "retrieval_method": self.retrieval_method,
            "retrieved_at": self.retrieved_at,
            "game_count": self.game_count,
        }


def load_acquisition_manifest(path: Path) -> tuple[RawSourceRecord, ...]:
    """Read the acquisition manifest into records, refusing an empty one."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    captured = manifest.get("captured_files") or []
    if not captured:
        raise GovernanceBlock(
            f"Acquisition manifest {path} records no captured files. A manifest "
            "over nothing is a schema, not custody."
        )
    records = tuple(
        RawSourceRecord(
            url=entry["url"],
            season=int(entry["season"]),
            division=entry["division"],
            week=int(entry["week"]),
            stored_path=entry["stored_path"],
            raw_sha256=entry["raw_sha256"],
            raw_byte_length=int(entry["raw_byte_length"]),
            stored_sha256=entry["stored_sha256"],
            stored_byte_length=int(entry["stored_byte_length"]),
            source_authority=entry["source_authority"],
            source_authority_class=entry["source_authority_class"],
            retrieval_method=entry["retrieval_method"],
            retrieved_at=entry["retrieved_at"],
            game_count=int(entry["game_count"]),
        )
        for entry in captured
    )
    return tuple(sorted(records, key=lambda r: (r.season, r.division, r.week)))


def verify_raw_custody(
    records: Sequence[RawSourceRecord], repo_root: Path
) -> dict[str, Any]:
    """Re-read every captured file and confirm it is still what was registered."""
    if not records:
        raise GovernanceBlock("Raw custody verification requires at least one source.")
    total_raw = 0
    total_stored = 0
    for record in records:
        body = record.read(repo_root)
        total_raw += len(body)
        total_stored += record.stored_byte_length
    return {
        "sources_verified": len(records),
        "raw_bytes_verified": total_raw,
        "stored_bytes_verified": total_stored,
        "bytes_reverified": True,
        "source_authorities": sorted({r.source_authority for r in records}),
        "source_authority_classes": sorted({r.source_authority_class for r in records}),
        "seasons": sorted({r.season for r in records}),
    }


@dataclass(frozen=True)
class CanonicalEntity:
    """One row of the 2026 canonical team master."""

    schedule_id: str
    team_name: str
    abbreviated_name: str
    entity_scope: str
    canonical_division: str


@dataclass(frozen=True)
class CanonicalIdentityAuthority:
    """The canonical master, pinned by the digest of the file it was read from.

    ``canonical_division`` is carried but never reported as a historical fact.
    The 2026 universe is a synthetic one whose membership is not the real-world
    membership of any season — it classifies Toledo and Western Michigan as
    schedule-only FCS and Colgate and Yale as FBS members. Observed division in
    this corpus always comes from the NCAA feed, never from here.
    """

    path: Path
    sha256: str
    entities: Mapping[str, CanonicalEntity]
    keys: Mapping[str, str]

    @property
    def fbs_member_count(self) -> int:
        return sum(1 for e in self.entities.values() if e.entity_scope == "FBS_MEMBER")


def load_canonical_identity_authority(path: Path) -> CanonicalIdentityAuthority:
    """Parse the canonical master grounding file and index its resolution keys.

    Keys come only from fields the grounding file names as resolution keys:
    ``schedule_id``, ``team_name``, ``abbreviated_name`` and ``aka_name``, plus
    the head of a parenthetically qualified ``team_name`` — ``Louisiana (UL
    Lafayette)`` also answers to ``Louisiana``. A key that would resolve to more
    than one entity is dropped rather than resolved by precedence.
    """
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    aka = dict(_AKA.findall(text))
    entities: dict[str, CanonicalEntity] = {}
    candidates: dict[str, set[str]] = {}
    for _, schedule_id, team_name, abbreviated, scope, division in _INDEX_ROW.findall(text):
        entity = CanonicalEntity(
            schedule_id=schedule_id,
            team_name=team_name.strip(),
            abbreviated_name=abbreviated,
            entity_scope=scope,
            canonical_division=division,
        )
        entities[schedule_id] = entity
        keys = [entity.team_name, entity.abbreviated_name, schedule_id]
        alias = aka.get(schedule_id, "")
        if alias and alias != "<blank>":
            keys.append(alias)
        head = entity.team_name.split(" (")[0].strip()
        if head != entity.team_name:
            keys.append(head)
        for key in keys:
            candidates.setdefault(_normalise_name(key), set()).add(schedule_id)
    if not entities:
        raise GovernanceBlock(
            f"Canonical identity authority {path} yielded no entities. Identity "
            "cannot be reconciled against an empty authority."
        )
    resolved_keys = {k: next(iter(v)) for k, v in candidates.items() if len(v) == 1}
    return CanonicalIdentityAuthority(
        path=path,
        sha256=_sha256(raw),
        entities=entities,
        keys=resolved_keys,
    )


@dataclass(frozen=True)
class TeamResolution:
    """The outcome of reconciling one NCAA entity to canonical identity."""

    source_seo: str
    source_short: str
    source_char6: str
    schedule_id: str | None
    rule: str

    @property
    def resolved(self) -> bool:
        return self.schedule_id is not None


def resolve_source_team(
    *, seo: str, short: str, char6: str, authority: CanonicalIdentityAuthority
) -> TeamResolution:
    """Resolve one NCAA entity to a canonical ``schedule_id``, or refuse.

    Three rules, tried in order, each requiring an *exact* hit on a canonical
    key. Ordering is by directness rather than by yield: a name that already is
    a canonical key is preferred to the NCAA's six-character code, which is
    preferred to a name this module expanded. Nothing fuzzy is attempted at any
    step — an unresolved name stays unresolved and its games are excluded with a
    reason, which is the outcome the canonical master's own grounding contract
    demands of anything not present in it.
    """
    for rule, candidate in (
        ("EXACT_CANONICAL_KEY", short),
        ("NCAA_CHAR6_CANONICAL_KEY", char6),
        ("NCAA_ABBREVIATION_EXPANSION", _expand_abbreviations(short)),
    ):
        hit = authority.keys.get(_normalise_name(candidate))
        if hit is not None:
            return TeamResolution(
                source_seo=seo,
                source_short=short,
                source_char6=char6,
                schedule_id=hit,
                rule=rule,
            )
    return TeamResolution(
        source_seo=seo,
        source_short=short,
        source_char6=char6,
        schedule_id=None,
        rule="UNRESOLVED_ENTITY",
    )


@dataclass(frozen=True)
class ObservationRow:
    """One admitted observation. Only governed-allowlist fields."""

    game_id: str
    season: int
    week: int
    event_time: str
    team: str
    opponent: str
    actual_margin: int
    game_result: str
    source_provenance: str
    recorded_at: str
    split: str

    def as_row(self) -> tuple[str, ...]:
        return (
            self.game_id,
            str(self.season),
            str(self.week),
            self.event_time,
            self.team,
            self.opponent,
            str(self.actual_margin),
            self.game_result,
            self.source_provenance,
            self.recorded_at,
            self.split,
        )


@dataclass(frozen=True)
class CorpusBuild:
    """Everything the build produced, including everything it refused."""

    rows: tuple[ObservationRow, ...]
    exclusions: tuple[Mapping[str, Any], ...]
    fcs_inventory: tuple[Mapping[str, Any], ...]
    identity_report: Mapping[str, Any]
    game_identity_report: Mapping[str, Any]
    chronology_report: Mapping[str, Any]
    source_report: Mapping[str, Any]

    @property
    def raw_row_count(self) -> int:
        return int(self.source_report["raw_row_count"])

    def reconciles(self) -> bool:
        return self.raw_row_count == len(self.rows) + len(self.exclusions)


def _iso_utc(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def build_observation_corpus(
    records: Sequence[RawSourceRecord],
    authority: CanonicalIdentityAuthority,
    repo_root: Path,
    *,
    seasons: Sequence[int] = ADMITTED_SEASONS,
) -> CorpusBuild:
    """Build the corpus from verified raw bytes.

    Every row of every ``fbs`` file is accounted for: admitted, or excluded with
    one reason code. The counts reconcile by construction rather than by audit,
    because a row leaves the loop through exactly one of the two exits.
    """
    seasons = tuple(sorted(seasons))
    by_season: dict[int, dict[str, list]] = {}
    for record in records:
        bucket = by_season.setdefault(record.season, {"fbs": [], "fcs": []})
        bucket[record.division].append(record)

    rows: list[ObservationRow] = []
    exclusions: list[dict[str, Any]] = []
    fcs_inventory: list[dict[str, Any]] = []
    resolutions: dict[tuple[int, str], TeamResolution] = {}
    unresolved_names: dict[str, set[int]] = {}
    ambiguous_pairs: dict[int, list[str]] = {}
    raw_row_count = 0
    #: Keyed rather than counted, so overtime can be reported against the rows
    #: that actually survived admission instead of against everything staged.
    overtime_keys: set[tuple[int, str]] = set()
    non_admitted_seasons: dict[int, str] = {}

    for season in sorted(by_season):
        fbs_records = sorted(by_season[season]["fbs"], key=lambda r: r.week)
        fcs_records = sorted(by_season[season]["fcs"], key=lambda r: r.week)
        fbs_games: list[tuple[int, dict, RawSourceRecord]] = []
        for record in fbs_records:
            payload = json.loads(record.read(repo_root))
            for entry in payload.get("games", []):
                fbs_games.append((record.week, entry["game"], record))
        raw_row_count += len(fbs_games)

        if season not in seasons:
            non_admitted_seasons[season] = (
                "SOURCE_SEASON_NOT_FINALISED"
                if any(g.get("gameState") != "final" for _, g, _ in fbs_games)
                else "SEASON_NOT_SELECTED_FOR_ADMISSION"
            )
            for week, game, record in fbs_games:
                exclusions.append(
                    {
                        "season": season,
                        "week": week,
                        "source_game_id": game.get("gameID", ""),
                        "reason": "SOURCE_SEASON_NOT_FINALISED",
                        "detail": non_admitted_seasons[season],
                        "source_url": record.url,
                    }
                )
            continue

        cross_division_ids = {
            entry["game"]["gameID"].strip()
            for record in fcs_records
            for entry in json.loads(record.read(repo_root)).get("games", [])
            if entry["game"]["gameID"].strip()
        } & {g["gameID"].strip() for _, g, _ in fbs_games if g["gameID"].strip()}

        entities: dict[str, dict[str, str]] = {}
        for _, game, _ in fbs_games:
            for side in ("home", "away"):
                names = game[side]["names"]
                entities.setdefault(names["seo"], names)
        season_resolution = {
            seo: resolve_source_team(
                seo=seo, short=names["short"], char6=names["char6"], authority=authority
            )
            for seo, names in sorted(entities.items())
        }
        resolutions.update({(season, seo): r for seo, r in season_resolution.items()})
        for seo, resolution in season_resolution.items():
            if not resolution.resolved:
                unresolved_names.setdefault(resolution.source_short, set()).add(season)

        # Injective within a season: two distinct NCAA entities landing on one
        # canonical id means at least one of them is wrong, and there is no
        # source fact that says which.
        reverse: dict[str, list[str]] = {}
        for seo, resolution in season_resolution.items():
            if resolution.resolved:
                reverse.setdefault(resolution.schedule_id, []).append(seo)
        colliding = {sid for sid, seos in reverse.items() if len(seos) > 1}
        if colliding:
            ambiguous_pairs[season] = sorted(colliding)

        # Observed division, read from which feeds a game appeared in.
        division_of: dict[str, str] = {}
        for _, game, _ in fbs_games:
            game_id = game["gameID"].strip()
            if not game_id or game_id in cross_division_ids:
                continue
            for side in ("home", "away"):
                division_of[game[side]["names"]["seo"]] = "FBS"
        for _, game, _ in fbs_games:
            for side in ("home", "away"):
                division_of.setdefault(game[side]["names"]["seo"], "FCS")

        staged: list[dict[str, Any]] = []
        for week, game, record in fbs_games:
            home, away = game["home"], game["away"]
            home_seo = home["names"]["seo"]
            away_seo = away["names"]["seo"]
            source_game_id = game.get("gameID", "").strip()
            note = {
                "season": season,
                "week": week,
                "source_game_id": source_game_id,
                "source_home": home["names"]["short"],
                "source_away": away["names"]["short"],
                "source_url": record.url,
            }

            def refuse(reason: str, detail: str) -> None:
                exclusions.append({**note, "reason": reason, "detail": detail})

            if not source_game_id:
                refuse(
                    "MISSING_SOURCE_GAME_IDENTIFIER",
                    "The source published this game with an empty gameID; no "
                    "authoritative identifier exists to key it on.",
                )
                continue
            if game.get("gameState") != "final":
                refuse("GAME_NOT_FINAL", f"gameState={game.get('gameState')!r}")
                continue
            try:
                home_score = int(home["score"])
                away_score = int(away["score"])
            except (TypeError, ValueError):
                refuse(
                    "MISSING_REQUIRED_SCORE",
                    f"home={home['score']!r} away={away['score']!r}",
                )
                continue
            epoch_text = (game.get("startTimeEpoch") or "").strip()
            if not epoch_text.isdigit() or int(epoch_text) <= 0:
                refuse("CHRONOLOGY_UNRESOLVED", f"startTimeEpoch={epoch_text!r}")
                continue
            home_resolution = season_resolution[home_seo]
            away_resolution = season_resolution[away_seo]
            if not (home_resolution.resolved and away_resolution.resolved):
                unresolved = [
                    r.source_short
                    for r in (home_resolution, away_resolution)
                    if not r.resolved
                ]
                refuse(
                    "UNRESOLVED_TEAM_IDENTITY",
                    f"not present in the 2026 canonical master: {unresolved}",
                )
                continue
            if (
                home_resolution.schedule_id in colliding
                or away_resolution.schedule_id in colliding
            ):
                refuse(
                    "AMBIGUOUS_TEAM_IDENTITY",
                    "two NCAA entities resolve to one canonical schedule_id",
                )
                continue
            if home_resolution.schedule_id == away_resolution.schedule_id:
                refuse("SELF_MATCHUP", "both sides resolve to one canonical entity")
                continue
            home_division = division_of.get(home_seo)
            away_division = division_of.get(away_seo)
            if home_division is None or away_division is None:
                refuse("UNRESOLVED_OPPONENT_DIVISION", "division not determinable")
                continue
            if _OVERTIME.search(game.get("finalMessage", "")):
                overtime_keys.add((season, source_game_id))
            staged_row = {
                **note,
                "epoch": int(epoch_text),
                "start_date": game.get("startDate", ""),
                "team": home_resolution.schedule_id,
                "opponent": away_resolution.schedule_id,
                "home_division": home_division,
                "away_division": away_division,
                "margin": home_score - away_score,
                "final_message": game.get("finalMessage", ""),
                "recorded_at": record.retrieved_at,
                "source_provenance": f"{record.source_authority}|{record.url}",
            }
            if home_division != away_division:
                fcs_inventory.append(staged_row)
                refuse(
                    "FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED",
                    "cross-division observation; opponent_division is not on the "
                    "governed allowlist and the FCS point-scale adapter is an "
                    "open blocker",
                )
                continue
            if home_division != "FBS":
                refuse(
                    "OUTSIDE_GOVERNED_SCOPE_FCS_VS_FCS",
                    "both participants observed as FCS",
                )
                continue
            staged.append(staged_row)

        # Unique game identity. Two records sharing a season, a canonical pair
        # and a source week are one game published twice.
        buckets: dict[tuple[tuple[str, str], int], list[dict[str, Any]]] = {}
        for staged_row in staged:
            key = (
                tuple(sorted((staged_row["team"], staged_row["opponent"]))),
                staged_row["week"],
            )
            buckets.setdefault(key, []).append(staged_row)
        claimed: set[str] = set()
        for key in sorted(buckets, key=lambda k: (k[0], k[1])):
            group = buckets[key]
            if len(group) > 1:
                for staged_row in group:
                    exclusions.append(
                        {
                            **{
                                k: staged_row[k]
                                for k in (
                                    "season",
                                    "week",
                                    "source_game_id",
                                    "source_home",
                                    "source_away",
                                    "source_url",
                                )
                            },
                            "reason": "DUPLICATE_OR_AMBIGUOUS_GAME_ID",
                            "detail": (
                                f"{len(group)} records share season {key[0]} week "
                                f"{key[1]}; source ids "
                                f"{sorted(r['source_game_id'] for r in group)}"
                            ),
                        }
                    )
                continue
            staged_row = group[0]
            if staged_row["source_game_id"] in claimed:
                exclusions.append(
                    {
                        **{
                            k: staged_row[k]
                            for k in (
                                "season",
                                "week",
                                "source_game_id",
                                "source_home",
                                "source_away",
                                "source_url",
                            )
                        },
                        "reason": "DUPLICATE_OR_AMBIGUOUS_GAME_ID",
                        "detail": "source game id already claimed in this season",
                    }
                )
                continue
            claimed.add(staged_row["source_game_id"])
            margin = staged_row["margin"]
            rows.append(
                ObservationRow(
                    game_id=f"NCAA-{season}-{staged_row['source_game_id']}",
                    season=season,
                    week=staged_row["week"],
                    event_time=_iso_utc(staged_row["epoch"]),
                    team=staged_row["team"],
                    opponent=staged_row["opponent"],
                    actual_margin=margin,
                    game_result="W" if margin > 0 else "L" if margin < 0 else "T",
                    source_provenance=staged_row["source_provenance"],
                    recorded_at=staged_row["recorded_at"],
                    split=SEASON_SPLIT_ASSIGNMENT[season],
                )
            )

    rows, coverage_exclusions, coverage = _prune_to_coverage_floor(rows)
    exclusions.extend(coverage_exclusions)
    rows = tuple(sorted(rows, key=lambda r: (r.event_time, r.game_id)))

    identity_report = _identity_report(resolutions, unresolved_names, ambiguous_pairs, authority, rows)
    game_identity_report = _game_identity_report(rows)
    chronology_report = _chronology_report(rows)
    source_report = {
        "raw_row_count": raw_row_count,
        "source_files": len(records),
        "seasons_retrieved": sorted({r.season for r in records}),
        "seasons_admitted": list(seasons),
        "seasons_not_admitted": {str(k): v for k, v in sorted(non_admitted_seasons.items())},
        "overtime_games_staged": len(overtime_keys),
        "overtime_games_admitted": sum(
            1
            for row in rows
            if (row.season, row.game_id.split("-", 2)[2]) in overtime_keys
        ),
        "overtime_disposition": (
            "finalMessage carries FINAL (OT) through FINAL (4OT), so the count is "
            "observable. overtime_periods is not on the governed allowlist, so it "
            "is reported and not emitted."
        ),
        "team_season_coverage": coverage,
    }
    return CorpusBuild(
        rows=rows,
        exclusions=tuple(exclusions),
        fcs_inventory=tuple(fcs_inventory),
        identity_report=identity_report,
        game_identity_report=game_identity_report,
        chronology_report=chronology_report,
        source_report=source_report,
    )


def _prune_to_coverage_floor(
    rows: Sequence[ObservationRow],
) -> tuple[list[ObservationRow], list[dict[str, Any]], dict[str, Any]]:
    """Drop team-seasons below the contract's per-team floor, to a fixed point.

    Removing one team-season lowers its opponents' counts, which can push them
    below the floor in turn, so this iterates until nothing more falls out.
    Selection is on schedule structure alone and never on a result, so it cannot
    bias the corpus toward outcomes; what it does bias is composition, and the
    report says which team-seasons left and why.
    """
    kept = list(rows)
    dropped: list[dict[str, Any]] = []
    iterations = 0
    while True:
        counts: dict[tuple[int, str], int] = {}
        for row in kept:
            counts[(row.season, row.team)] = counts.get((row.season, row.team), 0) + 1
            counts[(row.season, row.opponent)] = (
                counts.get((row.season, row.opponent), 0) + 1
            )
        below = {k for k, v in counts.items() if v < MINIMUM_GAMES_PER_TEAM_SEASON}
        if not below:
            return kept, dropped, {
                "iterations": iterations,
                "team_seasons": len(counts),
                "minimum_games_per_team_season": min(counts.values()) if counts else 0,
                "rows_pruned": len(dropped),
            }
        iterations += 1
        survivors: list[ObservationRow] = []
        for row in kept:
            if (row.season, row.team) in below or (row.season, row.opponent) in below:
                dropped.append(
                    {
                        "season": row.season,
                        "week": row.week,
                        "source_game_id": row.game_id.rsplit("-", 1)[-1],
                        "source_home": row.team,
                        "source_away": row.opponent,
                        "source_url": row.source_provenance.split("|", 1)[-1],
                        "reason": "INSUFFICIENT_TEAM_SEASON_COVERAGE",
                        "detail": (
                            "a participant holds fewer than "
                            f"{MINIMUM_GAMES_PER_TEAM_SEASON} admitted observations "
                            "in this season"
                        ),
                    }
                )
            else:
                survivors.append(row)
        kept = survivors


def _identity_report(
    resolutions: Mapping[tuple[int, str], TeamResolution],
    unresolved_names: Mapping[str, set[int]],
    ambiguous_pairs: Mapping[int, list[str]],
    authority: CanonicalIdentityAuthority,
    rows: Sequence[ObservationRow],
) -> dict[str, Any]:
    outcomes: dict[str, int] = {}
    for resolution in resolutions.values():
        outcomes[resolution.rule] = outcomes.get(resolution.rule, 0) + 1
    admitted_ids = {r.team for r in rows} | {r.opponent for r in rows}
    return {
        "canonical_authority": str(authority.path).replace("\\", "/"),
        "canonical_authority_sha256": authority.sha256,
        "canonical_entities": len(authority.entities),
        "canonical_fbs_members": authority.fbs_member_count,
        "source_entities_seen": len({seo for _, seo in resolutions}),
        "resolution_rule_counts": dict(sorted(outcomes.items())),
        "unresolved_entity_names": sorted(unresolved_names),
        "unresolved_entity_count": len(unresolved_names),
        "unresolved_entity_seasons": {
            name: sorted(seasons) for name, seasons in sorted(unresolved_names.items())
        },
        "ambiguous_canonical_ids": {str(k): v for k, v in sorted(ambiguous_pairs.items())},
        "canonical_entities_in_corpus": sorted(admitted_ids),
        "canonical_entities_in_corpus_count": len(admitted_ids),
        "outcome_taxonomy": {
            "MATCHED_CANONICAL": "EXACT_CANONICAL_KEY",
            "HISTORICAL_ALIAS_MATCH": (
                "NCAA_CHAR6_CANONICAL_KEY or NCAA_ABBREVIATION_EXPANSION"
            ),
            "HISTORICAL_NON_2026_ENTITY": (
                "UNRESOLVED_ENTITY where the institution exists but the 2026 "
                "canonical master does not carry it"
            ),
            "FCS_ENTITY": (
                "resolved entities observed as FCS by the feed; excluded under "
                "FBS_VS_FCS_OPPONENT_DIVISION_NOT_GOVERNED and inventoried"
            ),
            "UNRESOLVED_ENTITY": "UNRESOLVED_ENTITY",
        },
        "note": (
            "canonical_division and entity_scope describe the synthetic 2026 "
            "universe and are never reported as the observed division of a "
            "historical game."
        ),
    }


def _game_identity_report(rows: Sequence[ObservationRow]) -> dict[str, Any]:
    game_ids = [r.game_id for r in rows]
    pairs: dict[tuple[int, tuple[str, str]], list[ObservationRow]] = {}
    for row in rows:
        pairs.setdefault(
            (row.season, tuple(sorted((row.team, row.opponent)))), []
        ).append(row)
    repeats = {k: v for k, v in pairs.items() if len(v) > 1}
    return {
        "scheme": "NCAA-<season>-<ncaa_game_id>",
        "scheme_basis": (
            "The NCAA's own game identifier, namespaced by season because the "
            "feed reuses identifier spaces across seasons."
        ),
        "game_id_count": len(game_ids),
        "distinct_game_id_count": len(set(game_ids)),
        "duplicate_game_id_count": len(game_ids) - len(set(game_ids)),
        "repeat_matchup_count": len(repeats),
        "repeat_matchups": [
            {
                "season": season,
                "pair": list(pair),
                "game_ids": sorted(r.game_id for r in group),
                "weeks": sorted(r.week for r in group),
                "event_times": sorted(r.event_time for r in group),
            }
            for (season, pair), group in sorted(repeats.items())
        ],
        "collision_rule": (
            "Within a season, records sharing a canonical team pair and a source "
            "week are refused as one game published twice."
        ),
    }


def _chronology_report(rows: Sequence[ObservationRow]) -> dict[str, Any]:
    per_team: dict[tuple[int, str], list[str]] = {}
    for row in rows:
        per_team.setdefault((row.season, row.team), []).append(row.event_time)
        per_team.setdefault((row.season, row.opponent), []).append(row.event_time)
    tied = sum(1 for times in per_team.values() if len(times) != len(set(times)))
    return {
        "scheme": "EXACT_SOURCE_START_INSTANT",
        "ordering_field": "event_time, from startTimeEpoch",
        "observations": len(rows),
        "with_start_instant": len(rows),
        "start_instant_absent": 0,
        "distinct_start_instants": len({r.event_time for r in rows}),
        "team_seasons_with_tied_instants": tied,
        "precision": (
            "Second-resolution Unix instants published by the source. These are "
            "scheduled starts, not observed kickoffs, and are not represented as "
            "observed kickoffs anywhere in this corpus."
        ),
        "walk_forward_rule": (
            "A game may be ordered before another only on a strictly earlier "
            "start instant. Games sharing an instant are simultaneous and neither "
            "may inform the other. Because a game's result is observable only "
            "after it ends and no end instant is published, a start-instant "
            "ordering is sufficient to order games but NOT sufficient to prove "
            "that an earlier-starting game had finished before a later-starting "
            "one began. Any walk-forward feature derivation must therefore key on "
            "a completed-game boundary the source does not currently supply, or "
            "restrict itself to whole-day or whole-week boundaries."
        ),
        "split_ordering": (
            "Splits are whole seasons, so every ordering comparison that the "
            "temporal-split gate makes is separated by months, not by hours."
        ),
        "postseason": (
            "The feed carries no bowl or College Football Playoff games. The "
            "corpus therefore contains no postseason observation, which removes "
            "the postseason leakage path rather than managing it."
        ),
    }


def derive_subsequent_outcomes(
    rows: Sequence[ObservationRow],
) -> dict[str, dict[str, list[str]]]:
    """Forward game_ids per team, proving the field is derivable, not missing.

    Included so ``subsequent_outcomes`` can be classified honestly. It is
    reconstructible from the corpus alone; it is simply not emitted, because a
    denormalised copy of information already present is a second thing to keep
    correct.
    """
    per_team: dict[str, list[ObservationRow]] = {}
    for row in rows:
        per_team.setdefault(row.team, []).append(row)
        per_team.setdefault(row.opponent, []).append(row)
    out: dict[str, dict[str, list[str]]] = {}
    for team, games in per_team.items():
        ordered = sorted(games, key=lambda r: (r.event_time, r.game_id))
        out[team] = {
            game.game_id: [g.game_id for g in ordered[index + 1 :]]
            for index, game in enumerate(ordered)
        }
    return out


def render_corpus_csv(rows: Sequence[ObservationRow]) -> bytes:
    """Render the corpus to CSV bytes, deterministically.

    LF endings and an explicit UTF-8 encode, so the bytes this returns are the
    bytes a digest is taken over on any platform. The same rows in the same
    order always render to the same bytes; that is what makes a re-run
    comparable to the committed artifact.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CORPUS_COLUMNS)
    for row in sorted(rows, key=lambda r: (r.event_time, r.game_id)):
        writer.writerow(row.as_row())
    return buffer.getvalue().encode("utf-8")


def corpus_registration_receipt(path: Path, rows: Sequence[ObservationRow]) -> dict[str, Any]:
    """Re-read the written corpus and confirm it is the corpus that was built.

    The digest is taken over bytes read back from disk, not over the bytes that
    were written. Those are the same value only when nothing rewrote the file in
    between, which is precisely the condition worth checking.
    """
    if not path.exists():
        raise GovernanceBlock(
            f"Corpus {CORPUS_ID} is not present at {path}. A registration receipt "
            "is a statement about bytes; there are none."
        )
    data = path.read_bytes()
    expected = render_corpus_csv(rows)
    if data != expected:
        raise GovernanceBlock(
            f"Corpus at {path} does not match the corpus built from source: "
            f"{len(data)} bytes on disk hashing {_sha256(data)}, against "
            f"{len(expected)} bytes hashing {_sha256(expected)}. The written "
            "corpus and the derived corpus must be the same bytes."
        )
    text = data.decode("utf-8")
    reader = csv.reader(io.StringIO(text))
    header = tuple(next(reader))
    body = list(reader)
    if header != CORPUS_COLUMNS:
        raise GovernanceBlock(
            f"Corpus header {list(header)} is not {list(CORPUS_COLUMNS)}."
        )
    outside = sorted(
        c
        for c in header
        if c.lower() not in {a.lower() for a in CALIBRATION_OBSERVATION_COLUMNS}
    )
    if outside:
        raise GovernanceBlock(
            f"Corpus carries columns outside the governed observation allowlist: "
            f"{outside}. This lane widens no allowlist."
        )
    splits = {row[header.index("split")] for row in body}
    return {
        "corpus_id": CORPUS_ID,
        "path": str(path).replace("\\", "/"),
        "sha256": _sha256(data),
        "byte_length": len(data),
        "row_count": len(body),
        "columns": list(header),
        "columns_within_governed_allowlist": True,
        "splits_present": sorted(splits),
        "bytes_reverified_at_registration": True,
        "newline_policy": "LF",
    }


def build_temporal_split(rows: Sequence[ObservationRow]) -> dict[str, Any]:
    """Prove the split is temporal, then digest it.

    Delegates ordering to :func:`calibration.require_temporal_split_integrity`
    rather than re-implementing it, so the corpus is held to the same gate a
    calibration dataset would be.
    """
    ordered = {r.game_id: (r.split, r.event_time) for r in rows}
    if len(ordered) != len(rows):  # pragma: no cover - uniqueness is gated earlier
        raise GovernanceBlock("Corpus contains duplicate game_ids; split is unsafe.")
    integrity = require_temporal_split_integrity(ordered)
    seasons: dict[str, set[int]] = {}
    for row in rows:
        seasons.setdefault(row.split, set()).add(row.season)
    payload = {
        "assignment": "TEMPORAL_ONLY",
        "granularity": "WHOLE_SEASON",
        "season_assignment": {str(k): v for k, v in sorted(SEASON_SPLIT_ASSIGNMENT.items())},
        "splits": integrity["splits"],
        "boundaries": {k: list(v) for k, v in integrity["boundaries"].items()},
        "seasons_per_split": {k: sorted(v) for k, v in sorted(seasons.items())},
        "leak_free": integrity["leak_free"],
        "random_assignment_permitted": False,
    }
    payload["split_digest"] = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def volume_assessment(rows: Sequence[ObservationRow], coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Run the contract's minimum-volume gate over the finished corpus."""
    split_counts: dict[str, int] = {}
    for row in rows:
        split_counts[row.split] = split_counts.get(row.split, 0) + 1
    return require_minimum_volume(
        distinct_seasons=len({r.season for r in rows}),
        total_observations=len(rows),
        holdout_observations=split_counts.get("holdout", 0),
        min_weeks_per_team_per_season=int(coverage["minimum_games_per_team_season"]),
    )
