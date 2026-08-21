"""Synthetic observation sets for validating the harness itself.

These fixtures exist to prove the harness computes what it says it computes:
that RMSE falls when a regime tracks a known generating process, that the cap
binds, that splits stay separated, that a payload is reproducible. They are not
data.

Two things keep them from ever being mistaken for data:

* Every row carries ``source_provenance`` beginning with
  ``SYNTHETIC_HARNESS_FIXTURE``, which :mod:`.observations` detects and
  :mod:`.evaluate` propagates into the payload as inadmissible evidence.
* They are generated only when a caller asks, into a caller-supplied path. No
  fixture is written into the repository's configuration or reference trees.

Generation is deterministic: draws come from the V3 stateless keyed normal in
:mod:`..rng`, so a given seed reproduces a given fixture exactly.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from ..rng import deterministic_normal, deterministic_standard_normal
from .observations import SYNTHETIC_PROVENANCE_PREFIX, TRAINING, VALIDATION, HOLDOUT

FIXTURE_COLUMNS = (
    "game_id",
    "season",
    "week",
    "team",
    "opponent",
    "venue",
    "pregame_team_rating",
    "pregame_opponent_rating",
    "expected_margin",
    "actual_margin",
    "game_result",
    "split",
    "source_provenance",
    "observed_at",
    "recorded_at",
)


@dataclass(frozen=True)
class FixtureSpec:
    """A synthetic season: teams, weeks, and where the split boundaries fall."""

    seed: int
    season: int = 2026
    teams: int = 12
    weeks: int = 9
    training_through_week: int = 5
    validation_through_week: int = 7
    home_field_points: float = 3.5
    game_sd_points: float = 17.0
    #: How strongly a team's latent strength drifts week to week. Zero makes the
    #: generating process static, which is the useful case for cap tests.
    drift_sd_points: float = 0.0

    def split_for(self, week: int) -> str:
        if week <= self.training_through_week:
            return TRAINING
        if week <= self.validation_through_week:
            return VALIDATION
        return HOLDOUT


def _team_id(index: int) -> str:
    return f"SYN{index:02d}"


def _latent_strengths(spec: FixtureSpec) -> list[float]:
    return [
        deterministic_normal(spec.seed, 0.0, 8.0, "latent_strength", _team_id(i))
        for i in range(spec.teams)
    ]


def _pairings(spec: FixtureSpec, week: int) -> list[tuple[int, int]]:
    """A deterministic round-robin rotation. Every team plays exactly once a week."""
    order = list(range(spec.teams))
    rotation = order[:1] + order[1:][week % (spec.teams - 1) :] + order[1:][: week % (spec.teams - 1)]
    half = spec.teams // 2
    pairs = [(rotation[i], rotation[-1 - i]) for i in range(half)]
    # Alternate which side hosts, so the fixed team in the rotation is not always home.
    return pairs if week % 2 == 1 else [(away, home) for home, away in pairs]


def synthetic_rows(spec: FixtureSpec) -> list[dict[str, object]]:
    """Generate directed observation rows for both sides of every game."""
    if spec.teams < 4 or spec.teams % 2 != 0:
        raise ValueError("FixtureSpec.teams must be an even number of at least 4.")
    if not (0 < spec.training_through_week < spec.validation_through_week < spec.weeks):
        raise ValueError(
            "FixtureSpec requires 0 < training_through_week < validation_through_week < weeks."
        )

    strengths = _latent_strengths(spec)
    rows: list[dict[str, object]] = []

    for week in range(1, spec.weeks + 1):
        if spec.drift_sd_points > 0.0:
            strengths = [
                strength
                + deterministic_normal(
                    spec.seed, 0.0, spec.drift_sd_points, "drift", week, _team_id(i)
                )
                for i, strength in enumerate(strengths)
            ]
        for home, away in _pairings(spec, week):
            game_id = f"SYN-{spec.season}-W{week:02d}-{_team_id(home)}-{_team_id(away)}"
            noise = spec.game_sd_points * deterministic_standard_normal(
                spec.seed, "game_noise", spec.season, week, game_id
            )
            true_margin = strengths[home] - strengths[away] + spec.home_field_points + noise
            home_margin = round(true_margin)
            if home_margin == 0:
                home_margin = 1
            expected_home = strengths[home] - strengths[away] + spec.home_field_points
            split = spec.split_for(week)
            observed_at = f"{spec.season}-09-{min(week, 28):02d}T00:00:00Z"
            recorded_at = f"{spec.season}-09-{min(week + 1, 29):02d}T00:00:00Z"

            for subject, other, venue, margin, expected in (
                (home, away, "HOME", home_margin, expected_home),
                (away, home, "AWAY", -home_margin, -expected_home),
            ):
                rows.append(
                    {
                        "game_id": game_id,
                        "season": spec.season,
                        "week": week,
                        "team": _team_id(subject),
                        "opponent": _team_id(other),
                        "venue": venue,
                        "pregame_team_rating": round(strengths[subject], 6),
                        "pregame_opponent_rating": round(strengths[other], 6),
                        "expected_margin": round(expected, 6),
                        "actual_margin": margin,
                        "game_result": "W" if margin > 0 else "L",
                        "split": split,
                        "source_provenance": (
                            f"{SYNTHETIC_PROVENANCE_PREFIX}::seed={spec.seed}"
                        ),
                        "observed_at": observed_at,
                        "recorded_at": recorded_at,
                    }
                )
    return rows


def write_fixture_csv(path: Path, spec: FixtureSpec) -> Path:
    """Write a synthetic observation set to a caller-chosen path."""
    rows = synthetic_rows(spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(FIXTURE_COLUMNS))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def write_fixture_contract(
    path: Path,
    *,
    observations_path: Path,
    contract_id: str = "SYNTHETIC-FIXTURE-CONTRACT",
    hfa_points: float = 3.5,
    split_policy: dict[str, object] | None = None,
    witnesses: dict[str, object] | None = None,
) -> Path:
    """Write a contract document pointing at a synthetic observation set."""
    import json

    payload = {
        "contract_id": contract_id,
        "contract_version": "1.0.0",
        "produced_by": "C2_HARNESS_SYNTHETIC_FIXTURE",
        "consumed_by": "LANE_C2_BAXTER_RMSE_HARNESS",
        "observations": {
            "path": observations_path.name
            if observations_path.parent == path.parent
            else str(observations_path),
            "format": "csv",
            "dataset_id": f"{contract_id}-OBSERVATIONS",
            "sha256": None,
        },
        "split_policy": split_policy or {"mode": "column"},
        "metric": {"baxter_rmse_definition_id": "BAXTER_MARGIN_PREDICTION_RMSE_V1"},
        "hfa": {"points": hfa_points, "source": "CONTRACT_LITERAL"},
        "witnesses": witnesses or {"colley_matrix": None, "srs": None},
        "notes": ["Synthetic fixture contract. Harness validation only."],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def fixture_regime_values(
    *,
    coefficient: float,
    movement_cap_points: float,
    recent_form_weights: Sequence[float],
    blowout_treatment: dict[str, object],
    game_sd_points: float,
    sample_size_regularization: dict[str, object],
) -> dict[str, object]:
    """Assemble a complete six-axis value set for a fixture regime.

    Every value is supplied by the caller. This helper only names the fields, so
    a test's candidate numbers stay visible in the test rather than hiding here.
    """
    return {
        "weekly_performance_residual_coefficient": coefficient,
        "weekly_movement_cap_points": movement_cap_points,
        "recent_form_weights": list(recent_form_weights),
        "blowout_treatment": dict(blowout_treatment),
        "game_sd_points": game_sd_points,
        "sample_size_regularization": dict(sample_size_regularization),
    }
