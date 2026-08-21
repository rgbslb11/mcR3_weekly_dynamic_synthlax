"""SRS — a separate deterministic opponent-adjusted capped-margin model.

Ruling R2-SRS-WITNESS keeps SRS exactly where the governed registers already put
it: its own model, with a per-game margin cap of +/-24, an opponent schedule
adjustment, and a centred field rating. It is a calibration/validation *witness*
alongside the Baxter Rating and the Colley Matrix.

It is never committee SOS and never SOR. ``18_ACC_POLICY_REFERENCE`` ACC-EXT-12
records a proposed Body-of-Work Index blending ``z(SRS capped +/-24)`` with
``z(SoR-B)`` and marks it PROPOSAL ONLY / NOT ADOPTED. That is the blend this
module refuses to participate in.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_SRS

#: FACT — ACC-EXT-12 records the cap as +/-24; ruling R2-SRS-WITNESS restates it.
SRS_MARGIN_CAP = 24.0

#: Singularity guard for the exact linear solve.
SRS_PIVOT_EPSILON = 1e-12

WITNESS_ROLE = "CALIBRATION_VALIDATION_WITNESS"


@dataclass(frozen=True)
class SrsGame:
    game_id: str
    team: str
    opponent: str
    #: Margin from ``team``'s point of view, before capping.
    margin: float


def cap_margin(margin: float, cap: float = SRS_MARGIN_CAP) -> float:
    """Clamp a single-game margin to +/-cap. Applied per game, never per season."""
    return max(-cap, min(cap, float(margin)))


def _solve(matrix: list[list[float]], rhs: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting, in fixed order.

    Written out rather than iterated to a fixed point: the Jacobi sweep the
    schedule-adjustment equations invite does not converge on small or
    lopsided schedules, and a solver that quietly returns its last oscillation
    would hand back a plausible ordering that is simply wrong.
    """
    n = len(rhs)
    aug = [row[:] + [rhs[i]] for i, row in enumerate(matrix)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[pivot][col]) < SRS_PIVOT_EPSILON:
            raise InputValidationError(
                "SRS schedule-adjustment system is singular; the schedule graph is "
                "disconnected or degenerate"
            )
        if pivot != col:
            aug[col], aug[pivot] = aug[pivot], aug[col]
        scale = aug[col][col]
        aug[col] = [v / scale for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            if factor:
                aug[row] = [v - factor * w for v, w in zip(aug[row], aug[col])]
    return [aug[i][n] for i in range(n)]


def compute_srs(games: Sequence[SrsGame]) -> dict[str, float]:
    """Opponent-adjusted capped-margin ratings, centred on zero.

    Solves the schedule-adjustment system exactly::

        n_i * r_i - sum_j m_ij * r_j = sum of team i's capped margins

    with the centring constraint ``sum r = 0`` replacing the redundant equation.
    Deterministic: teams are ordered by schedule_id and the elimination order is
    fixed, so identical input yields identical output.
    """
    if not games:
        raise InputValidationError("SRS requires at least one game")

    margins: dict[str, float] = {}
    counts: dict[str, int] = {}
    opponents: dict[str, dict[str, int]] = {}
    for game in games:
        margins.setdefault(game.team, 0.0)
        counts.setdefault(game.team, 0)
        opponents.setdefault(game.team, {})
        margins.setdefault(game.opponent, 0.0)
        counts.setdefault(game.opponent, 0)
        opponents.setdefault(game.opponent, {})
        margins[game.team] += cap_margin(game.margin)
        counts[game.team] += 1
        opponents[game.team][game.opponent] = opponents[game.team].get(game.opponent, 0) + 1

    teams = sorted(counts)
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    matrix = [[0.0] * n for _ in range(n)]
    rhs = [0.0] * n
    for team in teams:
        i = index[team]
        matrix[i][i] = float(counts[team])
        for opponent, played in opponents[team].items():
            matrix[i][index[opponent]] -= float(played)
        rhs[i] = margins[team]

    # Replace the redundant final equation with the centring constraint.
    matrix[n - 1] = [1.0] * n
    rhs[n - 1] = 0.0

    solved = _solve(matrix, rhs)
    return {team: solved[index[team]] for team in teams}


def srs_ordering(ratings: dict[str, float]) -> list[str]:
    """Best rating first; ties break on schedule_id so the order is total."""
    return sorted(ratings, key=lambda t: (-ratings[t], t))


def reject_srs_as(metric_name: str) -> None:
    """Refuse SRS standing in for committee SOS or for SOR."""
    banned = {
        "SOS": "committee SOS",
        "COMMITTEE_SOS": "committee SOS",
        "STRENGTH_OF_SCHEDULE": "committee SOS",
        "SOR": "SOR",
        "SOR_B": "SOR",
        "RECORD_STRENGTH": "SOR",
    }
    role = banned.get(metric_name.upper())
    if role:
        raise GovernanceBlock(
            f"SRS may not be used as {role}. Ruling {R2_SRS.convergence_id} keeps SRS a "
            f"separate {WITNESS_ROLE}."
        )


def reject_witness_composite(components: Iterable[str]) -> None:
    """Refuse a weighted composite of the calibration witnesses.

    Ruling R2-CAL-OBJECTIVE authorises Baxter Rating RMSE as the primary
    criterion with Colley and SRS reported independently. A blend of them is the
    unadopted BWI proposal.
    """
    named = {c.upper() for c in components}
    witnesses = {"SRS", "COLLEY", "BAXTER", "BAXTER_RATING", "SOR", "SOR_B"}
    overlap = sorted(named & witnesses)
    if len(overlap) > 1:
        raise GovernanceBlock(
            f"A weighted composite of {overlap} is not authorised. ACC-EXT-12 records the "
            "Body-of-Work Index blend as PROPOSAL ONLY / NOT ADOPTED; witnesses are reported "
            "independently."
        )


def witness_as_dict(ratings: dict[str, float]) -> dict[str, object]:
    return {
        "ruling": R2_SRS.convergence_id,
        "model": "SRS",
        "role": WITNESS_ROLE,
        "margin_cap": SRS_MARGIN_CAP,
        "is_committee_sos": False,
        "is_sor": False,
        "ordering": srs_ordering(ratings),
        "ratings": {t: ratings[t] for t in sorted(ratings)},
    }
