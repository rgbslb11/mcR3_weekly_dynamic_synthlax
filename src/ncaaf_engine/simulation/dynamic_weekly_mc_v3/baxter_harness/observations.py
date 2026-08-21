"""Typed loading and split assignment for Baxter calibration observations.

The governed column allowlist lives in :mod:`..calibration` and is enforced at
registration. This module turns registered rows into typed records, orders them
deterministically, and assigns each to exactly one of training / validation /
holdout under the contract's split policy.

Split assignment is where an out-of-sample number is won or lost, so two rules
are enforced rather than assumed:

* Every scored observation lands in exactly one split.
* The splits are blocks of whole ``(season, week)`` keys in strictly increasing
  time order. A week that straddles two splits, or a validation week that
  precedes a training week, is refused. The harness cannot certify a metric as
  out-of-sample if the model saw later weeks while producing it.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from typing import Any, Iterable, Sequence

from ..calibration import CalibrationDataset, DATA_SPLITS, require_split_separation
from ..errors import GovernanceBlock, InputValidationError
from .contract import BaxterDataContract

#: Team-relative venue values. Rows are directed: ``team`` is the subject and
#: ``actual_margin`` is signed from that team's point of view.
VENUES = ("HOME", "AWAY", "NEUTRAL")

#: Marker a synthetic fixture writes into ``source_provenance``. A dataset every
#: one of whose rows carries it is fixture data and can never be evidence.
SYNTHETIC_PROVENANCE_PREFIX = "SYNTHETIC_HARNESS_FIXTURE"

TRAINING, VALIDATION, HOLDOUT = DATA_SPLITS


@dataclass(frozen=True)
class Observation:
    """One directed, team-relative historical observation."""

    game_id: str
    season: int
    week: int
    team: str
    opponent: str
    venue: str
    actual_margin: float
    observed_at: str
    recorded_at: str
    expected_margin: float | None = None
    pregame_team_rating: float | None = None
    pregame_opponent_rating: float | None = None
    game_result: str | None = None
    declared_split: str | None = None
    source_provenance: str | None = None

    @property
    def time_key(self) -> tuple[int, int]:
        return (self.season, self.week)

    @property
    def order_key(self) -> tuple[int, int, str, str]:
        return (self.season, self.week, self.game_id, self.team)

    @property
    def actual_win(self) -> bool | None:
        """Observed result, from ``game_result`` when stated and margin otherwise.

        A zero margin yields ``None`` rather than an invented winner; such rows
        are excluded from probability diagnostics and counted in the report.
        """
        if self.game_result is not None:
            flat = self.game_result.strip().upper()
            if flat in ("W", "WIN", "1", "TRUE"):
                return True
            if flat in ("L", "LOSS", "LOSE", "0", "FALSE"):
                return False
            if flat in ("T", "TIE", "D", "DRAW"):
                return None
            raise InputValidationError(
                f"Observation {self.game_id}/{self.team} has unrecognised game_result "
                f"{self.game_result!r}."
            )
        if self.actual_margin > 0:
            return True
        if self.actual_margin < 0:
            return False
        return None


@dataclass(frozen=True)
class ObservationSet:
    """Ordered observations plus their split assignment and provenance class."""

    dataset_id: str
    sha256: str
    observations: tuple[Observation, ...]
    split_of: dict[str, str]
    split_counts: dict[str, int]
    synthetic: bool
    split_policy: dict[str, Any]

    def scored(self, split: str) -> tuple[Observation, ...]:
        return tuple(o for o in self.observations if self.split_of[_row_key(o)] == split)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "sha256": self.sha256,
            "rows": len(self.observations),
            "split_counts": dict(sorted(self.split_counts.items())),
            "synthetic": self.synthetic,
            "split_policy": dict(self.split_policy),
            "seasons": sorted({o.season for o in self.observations}),
            "weeks": sorted({o.week for o in self.observations}),
        }


def _row_key(observation: Observation) -> str:
    return f"{observation.season}|{observation.week}|{observation.game_id}|{observation.team}"


def _raw_rows(dataset: CalibrationDataset, fmt: str | None) -> list[dict[str, str]]:
    """Read rows using the format the contract declared, not the file extension."""
    text = dataset.path.read_text(encoding="utf-8")
    suffix = (fmt or dataset.path.suffix.lstrip(".")).strip().lower()
    if suffix == "json":
        payload = json.loads(text)
        rows = payload.get("observations") if isinstance(payload, dict) else payload
        return [{str(k): ("" if v is None else str(v)) for k, v in row.items()} for row in rows]
    delimiter = "\t" if suffix == "tsv" else ","
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()} for row in reader]


def _require(row: dict[str, str], column: str, index: int) -> str:
    value = row.get(column, "")
    if value == "":
        raise InputValidationError(
            f"Observation row {index} is missing required column {column!r}."
        )
    return value


def _optional_float(row: dict[str, str], column: str, index: int) -> float | None:
    value = row.get(column, "")
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        raise InputValidationError(
            f"Observation row {index} column {column!r} is not numeric: {value!r}."
        ) from None


def _parse_row(row: dict[str, str], index: int) -> Observation:
    try:
        season = int(_require(row, "season", index))
        week = int(_require(row, "week", index))
    except ValueError:
        raise InputValidationError(
            f"Observation row {index} has a non-integer season/week."
        ) from None
    try:
        actual_margin = float(_require(row, "actual_margin", index))
    except ValueError:
        raise InputValidationError(
            f"Observation row {index} has a non-numeric actual_margin."
        ) from None

    venue = (row.get("venue") or "").strip().upper() or "NEUTRAL"
    if venue not in VENUES:
        raise InputValidationError(
            f"Observation row {index} has venue {venue!r}; expected one of {list(VENUES)}."
        )

    team = _require(row, "team", index)
    opponent = _require(row, "opponent", index)
    if team == opponent:
        raise InputValidationError(
            f"Observation row {index} lists {team!r} as its own opponent."
        )

    return Observation(
        game_id=_require(row, "game_id", index),
        season=season,
        week=week,
        team=team,
        opponent=opponent,
        venue=venue,
        actual_margin=actual_margin,
        observed_at=_require(row, "observed_at", index),
        recorded_at=_require(row, "recorded_at", index),
        expected_margin=_optional_float(row, "expected_margin", index),
        pregame_team_rating=_optional_float(row, "pregame_team_rating", index),
        pregame_opponent_rating=_optional_float(row, "pregame_opponent_rating", index),
        game_result=(row.get("game_result") or "").strip() or None,
        declared_split=(row.get("split") or "").strip().lower() or None,
        source_provenance=(row.get("source_provenance") or "").strip() or None,
    )


def _assign_column(observations: Sequence[Observation]) -> dict[str, str]:
    missing = [o.game_id for o in observations if o.declared_split is None]
    if missing:
        raise GovernanceBlock(
            "Split policy 'column' requires every observation to declare a split; "
            f"{len(missing)} row(s) do not, first {missing[:5]}."
        )
    return {_row_key(o): o.declared_split for o in observations}


def _assign_temporal_week(
    observations: Sequence[Observation], policy: dict[str, Any]
) -> dict[str, str]:
    training_through = (policy["training_through"]["season"], policy["training_through"]["week"])
    validation_through = (
        policy["validation_through"]["season"],
        policy["validation_through"]["week"],
    )
    out: dict[str, str] = {}
    for o in observations:
        if o.time_key <= training_through:
            out[_row_key(o)] = TRAINING
        elif o.time_key <= validation_through:
            out[_row_key(o)] = VALIDATION
        else:
            out[_row_key(o)] = HOLDOUT
    return out


def _assign_temporal_season(
    observations: Sequence[Observation], policy: dict[str, Any]
) -> dict[str, str]:
    mapping: dict[int, str] = {}
    for season in policy.get("training_seasons", []):
        mapping[int(season)] = TRAINING
    for season in policy.get("validation_seasons", []):
        mapping[int(season)] = VALIDATION
    for season in policy.get("holdout_seasons", []):
        mapping[int(season)] = HOLDOUT
    unassigned = sorted({o.season for o in observations} - set(mapping))
    if unassigned:
        raise GovernanceBlock(
            f"Split policy temporal_season leaves seasons {unassigned} unassigned. An "
            "observation with no split cannot be silently dropped or silently trained on."
        )
    return {_row_key(o): mapping[o.season] for o in observations}


def _assert_time_ordered_blocks(
    observations: Sequence[Observation], split_of: dict[str, str]
) -> None:
    """Refuse any split arrangement that lets the model see the future."""
    weeks_by_split: dict[str, set[tuple[int, int]]] = {s: set() for s in DATA_SPLITS}
    for o in observations:
        weeks_by_split[split_of[_row_key(o)]].add(o.time_key)

    for earlier, later in ((TRAINING, VALIDATION), (VALIDATION, HOLDOUT), (TRAINING, HOLDOUT)):
        shared = sorted(weeks_by_split[earlier] & weeks_by_split[later])
        if shared:
            raise GovernanceBlock(
                f"Weeks {shared} appear in both the {earlier} and {later} splits. A week "
                "split across two sides of an out-of-sample boundary leaks the boundary."
            )
        if weeks_by_split[earlier] and weeks_by_split[later]:
            if max(weeks_by_split[earlier]) > min(weeks_by_split[later]):
                raise GovernanceBlock(
                    f"The {earlier} split contains week {max(weeks_by_split[earlier])}, which "
                    f"falls after the first {later} week {min(weeks_by_split[later])}. "
                    "Out-of-sample splits must run forward in time."
                )


def load_observation_set(
    dataset: CalibrationDataset, contract: BaxterDataContract
) -> ObservationSet:
    """Load, order, and split a registered observation set."""
    raw = _raw_rows(dataset, contract.observations_format)
    if not raw:
        raise GovernanceBlock(
            f"Observation set {dataset.dataset_id} registered but carries no rows."
        )

    observations = tuple(
        sorted((_parse_row(row, i + 1) for i, row in enumerate(raw)), key=lambda o: o.order_key)
    )

    keys = [_row_key(o) for o in observations]
    duplicates = sorted({k for k in keys if keys.count(k) > 1})
    if duplicates:
        raise InputValidationError(
            f"Observation set {dataset.dataset_id} repeats rows {duplicates[:5]}; a duplicated "
            "observation would be weighted twice by every metric."
        )

    mode = contract.split_policy["mode"]
    if mode == "column":
        split_of = _assign_column(observations)
    elif mode == "temporal_week":
        split_of = _assign_temporal_week(observations, contract.split_policy)
    else:
        split_of = _assign_temporal_season(observations, contract.split_policy)

    buckets = require_split_separation(split_of)
    _assert_time_ordered_blocks(observations, split_of)

    provenances = [o.source_provenance or "" for o in observations]
    synthetic = bool(provenances) and all(
        p.startswith(SYNTHETIC_PROVENANCE_PREFIX) for p in provenances
    )

    return ObservationSet(
        dataset_id=dataset.dataset_id,
        sha256=dataset.sha256,
        observations=observations,
        split_of=split_of,
        split_counts={split: len(rows) for split, rows in buckets.items()},
        synthetic=synthetic,
        split_policy=dict(contract.split_policy),
    )


def require_scorable(observation_set: ObservationSet, splits: Iterable[str]) -> None:
    """Refuse to report a metric for a split that has nothing in it."""
    empty = [s for s in splits if observation_set.split_counts.get(s, 0) == 0]
    if empty:
        raise GovernanceBlock(
            f"Cannot score splits {empty}: no observations were assigned to them. An empty "
            "split yields no metric, not a metric of zero."
        )
