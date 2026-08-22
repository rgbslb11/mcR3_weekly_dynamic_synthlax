"""Colley Matrix — the second independent calibration witness.

Ruling R2-CAL-OBJECTIVE names the Colley Matrix and SRS as witnesses reported
*alongside* the primary criterion and never blended into it. :mod:`.srs` already
carries the SRS half. This carries Colley, and it is deliberately built to be
useless as a target:

* It reads wins and losses only. Margin never enters, which is exactly why it is
  a useful witness against a margin-fitted rating — an agreement between the two
  is information precisely because they were not fitted to the same thing.
* It is candidate-independent. A calibration candidate cannot move a Colley
  rating, so a candidate that ranks well against Colley did not do so by fitting
  to it.
* :func:`reject_witness_composite` refuses to let it be averaged with the Baxter
  Rating, on the same grounds :mod:`.srs` refuses: ``18_ACC_POLICY_REFERENCE``
  ACC-EXT-12 records that blend as PROPOSAL ONLY / NOT ADOPTED.

The Colley system is
``(2 + n_i) r_i - sum_j n_ij r_j = 1 + (w_i - l_i) / 2``
where ``n_i`` is games played, ``n_ij`` the number of meetings with ``j``, and
``w_i``/``l_i`` wins and losses. It is strictly diagonally dominant by
construction, so the exact solve in :mod:`.srs` cannot hit its singularity guard
here for any non-empty schedule.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .errors import GovernanceBlock, InputValidationError
# One solver, one failure mode. SRS's Gaussian elimination is exact and fixed
# order; a second copy here would be a second place for a pivot rule to drift.
from .srs import _solve as _gaussian_solve

__all__ = [
    "COLLEY_NEUTRAL_RATING",
    "WITNESS_ROLE",
    "ColleyGame",
    "colley_ordering",
    "compute_colley",
    "reject_colley_as",
    "reject_witness_composite",
    "witness_as_dict",
]

WITNESS_ROLE = "CALIBRATION_VALIDATION_WITNESS"

#: The rating an unplayed team carries, and the mean the system centres on.
COLLEY_NEUTRAL_RATING = 0.5


@dataclass(frozen=True)
class ColleyGame:
    """One decided game. Margin is absent on purpose: Colley does not see it."""

    game_id: str
    team: str
    opponent: str
    #: True when ``team`` won. Ties are not representable, and are refused at
    #: construction rather than silently scored as half a win: college football
    #: has no ties, so a tie in a corpus is a data defect worth surfacing.
    team_won: bool


def _decided(games: Sequence[ColleyGame]) -> None:
    seen: set[str] = set()
    for game in games:
        if game.team == game.opponent:
            raise InputValidationError(
                f"Colley game {game.game_id} lists {game.team} against itself."
            )
        if game.game_id in seen:
            raise InputValidationError(
                f"Colley input repeats game_id {game.game_id}. A duplicated game counts "
                "twice in n_i and shifts the whole system."
            )
        seen.add(game.game_id)


def compute_colley(games: Sequence[ColleyGame]) -> dict[str, float]:
    """Exact Colley ratings for every team appearing in ``games``.

    Deterministic in team order: the system is built over the sorted team list, so
    the elimination visits the same pivots in the same order on every machine.
    """
    if not games:
        raise InputValidationError(
            "Colley witness requires at least one decided game; an empty schedule has "
            "no system to solve."
        )
    _decided(games)

    teams = sorted({g.team for g in games} | {g.opponent for g in games})
    index = {team: i for i, team in enumerate(teams)}
    size = len(teams)

    matrix = [[0.0] * size for _ in range(size)]
    rhs = [0.0] * size
    for i in range(size):
        matrix[i][i] = 2.0

    wins_minus_losses = [0.0] * size
    for game in games:
        i, j = index[game.team], index[game.opponent]
        matrix[i][i] += 1.0
        matrix[j][j] += 1.0
        matrix[i][j] -= 1.0
        matrix[j][i] -= 1.0
        if game.team_won:
            wins_minus_losses[i] += 1.0
            wins_minus_losses[j] -= 1.0
        else:
            wins_minus_losses[i] -= 1.0
            wins_minus_losses[j] += 1.0

    for i in range(size):
        rhs[i] = 1.0 + wins_minus_losses[i] / 2.0

    solution = _gaussian_solve(matrix, rhs)
    return {team: solution[index[team]] for team in teams}


def colley_ordering(ratings: dict[str, float]) -> list[str]:
    """Teams strongest first, ties broken by name so the order is total."""
    return [team for team, _ in sorted(ratings.items(), key=lambda kv: (-kv[1], kv[0]))]


def reject_colley_as(metric_name: str) -> None:
    """Refuse any attempt to use the Colley witness as a governed selection metric."""
    forbidden = {
        "SOS",
        "COMMITTEE_SOS",
        "STRENGTH_OF_SCHEDULE",
        "SOR",
        "SOR_B",
        "BAXTER",
        "BAXTER_RATING",
        "PRIMARY_CALIBRATION_METRIC",
    }
    if metric_name.upper() in forbidden:
        raise GovernanceBlock(
            f"Colley is a calibration witness and may not be used as {metric_name}. "
            "Ruling R2-CAL-OBJECTIVE keeps out-of-sample Baxter Rating RMSE primary and "
            "reports Colley independently."
        )


def reject_witness_composite(components: Iterable[str]) -> None:
    """Refuse a weighted blend of Colley with the primary criterion or SRS."""
    named = {c.strip().upper() for c in components}
    family = {"COLLEY", "SRS", "BAXTER", "BAXTER_RATING", "SOR", "SOR_B"}
    overlap = sorted(named & family)
    if len(overlap) > 1:
        raise GovernanceBlock(
            f"A weighted composite of {overlap} is not authorised. ACC-EXT-12 records "
            "the Body-of-Work Index blend as PROPOSAL ONLY / NOT ADOPTED."
        )


def witness_as_dict(ratings: dict[str, float]) -> dict[str, object]:
    return {
        "witness": "colley_matrix",
        "role": WITNESS_ROLE,
        "ruling": "R2-CAL-OBJECTIVE",
        "team_count": len(ratings),
        "ordering": colley_ordering(ratings),
        "ratings": {team: ratings[team] for team in sorted(ratings)},
        "uses_margin": False,
        "candidate_dependent": False,
        "blended_into_primary_criterion": False,
        "neutral_rating": COLLEY_NEUTRAL_RATING,
    }
