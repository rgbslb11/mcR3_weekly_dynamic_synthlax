"""Colley Matrix — the deterministic win/loss-only calibration witness.

Ruling ``R2-CAL-OBJECTIVE`` names three things and keeps them apart: Baxter
Rating RMSE is the primary criterion, and the **Colley Matrix** and SRS are
independent witnesses reported separately. Ruling ``R2-SRS-WITNESS`` names the
Colley Matrix again, in the same role. This module is that witness.

Why implementing it promotes no parameter
-----------------------------------------
The Colley Matrix is a *named* method with no free parameters at all. There is
no weight to choose, no cap to set, no decay to fit, no margin to scale — the
system is fixed the moment the win/loss schedule is fixed::

    C_ii = 2 + t_i          C_ij = -n_ij          b_i = 1 + (w_i - l_i) / 2

That is the whole specification. Implementing it therefore adds nothing to the
six unresolved calibration fields and cannot be a back door to promoting one;
:data:`COLLEY_FREE_PARAMETERS` is empty and :func:`reject_parameterised_colley`
refuses the margin-weighted and bias-weighted variants that *do* carry
parameters. Those variants are different models wearing the same name, and none
of them is what the rulings name.

Where it is *not* validated
---------------------------
The rulings name the model. They do not mount a specification, a reference
implementation or a historical anchor, and none is present anywhere in this
repository. The arithmetic below is verifiable and verified; agreement with a
canonical Colley ordering is not, and :func:`require_canonical_validated_colley`
fails closed on any claim that it is. This mirrors the SRS witness exactly,
because the evidentiary position is exactly the same.

Two properties are worth stating because they differ from SRS and the tests
lean on both:

*Always solvable.* ``C = 2I + D - A`` is symmetric and strictly diagonally
dominant — the ``+2`` supplies the strictness — so it is positive definite for
any schedule whatsoever, including a disconnected one. Colley needs no
per-component treatment and no centring constraint, where SRS needs both.

*Self-centring.* Every row of ``C`` sums to 2 and every ``b_i`` sums to the team
count, so the ratings always average exactly 0.5 without being made to. A drift
away from 0.5 is a bug, not a modelling choice, which makes it a usable check.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .errors import GovernanceBlock, InputValidationError
from .linalg import solve_exact
from .rulings import R2_CALIBRATION, R2_SRS

#: Singularity guard. Unreachable for a well-formed Colley matrix, which is why
#: tripping it is reported as a defect rather than as a degenerate schedule.
COLLEY_PIVOT_EPSILON = 1e-12

#: FACT — the Colley Matrix has no tunable quantity. Deliberately empty.
COLLEY_FREE_PARAMETERS: tuple[str, ...] = ()

#: DERIVED — every rating set averages exactly this, by construction.
COLLEY_MEAN_RATING = 0.5

WITNESS_ROLE = "CALIBRATION_VALIDATION_WITNESS"

#: Parameterised variants that share the name and are not the named method.
PARAMETERISED_VARIANTS = {
    "COLLEY_MATRIX_WITH_MARGIN": "margin-of-victory weighting",
    "COLLEY_WITH_MARGIN": "margin-of-victory weighting",
    "MARGIN_WEIGHTED_COLLEY": "margin-of-victory weighting",
    "WEIGHTED_COLLEY": "per-game weighting",
    "COLLEY_BIAS_WEIGHTED": "a tunable prior weight in place of the fixed 2",
    "COLLEY_WITH_PRIOR_WEIGHT": "a tunable prior weight in place of the fixed 2",
    "RECENCY_WEIGHTED_COLLEY": "recency weighting",
}


@dataclass(frozen=True)
class ColleyGame:
    """One completed game from ``team``'s point of view.

    Colley consumes win/loss and nothing else. No margin field exists here on
    purpose: the method does not use one, and carrying a margin it ignores
    invites a later reader to believe it does.
    """

    game_id: str
    team: str
    opponent: str
    won: bool

    def __post_init__(self) -> None:
        if not self.game_id:
            raise InputValidationError("Colley game requires a game_id")
        if not self.team or not self.opponent:
            raise InputValidationError(f"Game {self.game_id} names an empty team or opponent")
        if self.team == self.opponent:
            raise InputValidationError(f"Game {self.game_id} has {self.team} playing itself")
        if not isinstance(self.won, bool):
            raise InputValidationError(
                f"Game {self.game_id} result for {self.team} is {self.won!r}; the governed "
                "Colley witness takes a win or a loss. See require_colley_tie_policy."
            )


#: No tie or half-win convention is issued by any mounted ruling. Colley's
#: published treatment of a tie as half a win is *his* convention, not governed
#: here, so a tie fails closed rather than being scored at 0.5 by inference.
COLLEY_TIE_POLICY = None
COLLEY_TIE_BLOCKER = "governance.COLLEY_TIE_POLICY_NOT_GOVERNED"


def require_colley_tie_policy() -> str:
    """Fail closed: no governed tie/half-win convention exists for this witness."""
    raise GovernanceBlock(
        f"{COLLEY_TIE_BLOCKER}: no mounted ruling issues a tie or half-win convention for "
        "the Colley witness. The published method scores a tie as half a win; that is the "
        "author's convention and is not governed here. Issue the policy; do not infer it."
    )


def _build_system(games: Sequence[ColleyGame]):
    """Wins, losses, totals and meeting counts, with the pairing validated.

    A Colley rating is driven by ``w_i - l_i``, so a schedule that records one
    side of a game and not the other, or records both sides as winners, does not
    merely bias the answer — it makes the answer meaningless. The pairing is
    therefore checked rather than assumed.
    """
    wins: dict[str, int] = {}
    losses: dict[str, int] = {}
    total: dict[str, int] = {}
    meetings: dict[str, dict[str, int]] = {}
    sides: dict[str, list[ColleyGame]] = {}

    for game in games:
        for side in (game.team, game.opponent):
            wins.setdefault(side, 0)
            losses.setdefault(side, 0)
            total.setdefault(side, 0)
            meetings.setdefault(side, {})
        sides.setdefault(game.game_id, []).append(game)
        if game.won:
            wins[game.team] += 1
        else:
            losses[game.team] += 1
        total[game.team] += 1
        meetings[game.team][game.opponent] = meetings[game.team].get(game.opponent, 0) + 1

    for game_id in sorted(sides):
        rows = sides[game_id]
        if len(rows) != 2:
            raise InputValidationError(
                f"Game {game_id} appears {len(rows)} time(s); the Colley witness requires "
                "exactly one row per side of each completed game"
            )
        first, second = rows
        if {first.team, first.opponent} != {second.team, second.opponent}:
            raise InputValidationError(
                f"Game {game_id} names inconsistent participants across its two rows"
            )
        if first.team == second.team:
            raise InputValidationError(
                f"Game {game_id} records {first.team} twice rather than both sides"
            )
        if first.won == second.won:
            outcome = "winners" if first.won else "losers"
            raise InputValidationError(
                f"Game {game_id} records both sides as {outcome}; a completed game has "
                "exactly one winner and one loser under the governed win/loss schedule"
            )
    return wins, losses, total, meetings


def compute_colley(games: Sequence[ColleyGame]) -> dict[str, float]:
    """Solve the Colley system exactly and return the ratings.

    ``(2 + t_i) r_i - sum_j n_ij r_j = 1 + (w_i - l_i)/2``, solved directly. No
    iteration, no tolerance, no per-component split — the matrix is positive
    definite for every schedule, so the exact solution always exists and the
    approximation questions SRS has to answer simply do not arise here.
    """
    if not games:
        raise InputValidationError("Colley requires at least one game")

    wins, losses, total, meetings = _build_system(games)
    teams = sorted(total)
    index = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    matrix = [[0.0] * n for _ in range(n)]
    rhs = [0.0] * n
    for team in teams:
        i = index[team]
        matrix[i][i] = 2.0 + float(total[team])
        for opponent, played in meetings[team].items():
            matrix[i][index[opponent]] -= float(played)
        rhs[i] = 1.0 + (wins[team] - losses[team]) / 2.0

    solved = solve_exact(
        matrix,
        rhs,
        singular_message=(
            "Colley matrix is singular, which it cannot be for a well-formed schedule "
            "(C = 2I + D - A is positive definite). Treat this as a defect in the "
            "assembled system rather than as a property of the schedule."
        ),
        pivot_epsilon=COLLEY_PIVOT_EPSILON,
    )
    return {team: solved[index[team]] for team in teams}


def colley_records(games: Sequence[ColleyGame]) -> dict[str, tuple[int, int]]:
    """The ``(wins, losses)`` the ratings were built from, for the audit row."""
    wins, losses, _, _ = _build_system(games)
    return {team: (wins[team], losses[team]) for team in sorted(wins)}


def colley_residuals(
    games: Sequence[ColleyGame], ratings: dict[str, float]
) -> dict[str, float]:
    """Per-team residual of the Colley equation. Zero means the system is solved."""
    wins, losses, total, meetings = _build_system(games)
    out: dict[str, float] = {}
    for team in sorted(total):
        lhs = (2.0 + total[team]) * ratings[team] - sum(
            played * ratings[opponent] for opponent, played in meetings[team].items()
        )
        out[team] = lhs - (1.0 + (wins[team] - losses[team]) / 2.0)
    return out


def colley_ordering(ratings: dict[str, float]) -> list[str]:
    """Best rating first; ties break on schedule_id so the order is total."""
    return sorted(ratings, key=lambda t: (-ratings[t], t))


def assert_colley_properties(
    games: Sequence[ColleyGame], *, tolerance: float = 1e-9
) -> dict[str, object]:
    """Check the three properties that make this solution demonstrably Colley's.

    Residuals vanish; the ratings average exactly 0.5; and the assembled matrix
    is symmetric and strictly diagonally dominant, which is what guarantees the
    first two for *any* schedule rather than merely for this one. Reported
    together because a witness that cannot show its own arithmetic is sound has
    nothing to witness with.
    """
    ratings = compute_colley(games)
    residuals = colley_residuals(games, ratings)
    worst_residual = max(abs(v) for v in residuals.values())
    if worst_residual > tolerance:
        raise InputValidationError(
            f"Colley solution does not satisfy its own system; worst residual {worst_residual}"
        )

    mean = sum(ratings.values()) / len(ratings)
    if abs(mean - COLLEY_MEAN_RATING) > tolerance:
        raise InputValidationError(
            f"Colley ratings average {mean}, not {COLLEY_MEAN_RATING}; the system was "
            "assembled wrongly"
        )

    _, _, total, meetings = _build_system(games)
    teams = sorted(total)
    symmetric = all(
        meetings[a].get(b, 0) == meetings[b].get(a, 0) for a in teams for b in teams
    )
    dominant = all(
        (2.0 + total[t]) - sum(meetings[t].values()) >= 2.0 - tolerance for t in teams
    )

    ordered = sorted(ratings.values())
    min_gap = min((b - a for a, b in zip(ordered, ordered[1:])), default=float("inf"))
    return {
        "teams": len(ratings),
        "worst_residual": worst_residual,
        "mean_rating": mean,
        "matrix_symmetric": symmetric,
        "matrix_strictly_diagonally_dominant": dominant,
        # Two ratings closer together than the tolerance can order either way.
        # Reporting the gap lets a caller tell a real ordering difference from
        # float noise at a near-exact tie.
        "min_rating_gap": min_gap,
        "free_parameters": list(COLLEY_FREE_PARAMETERS),
    }


#: No canonical Colley specification, reference implementation or historical
#: validation anchor is mounted in this repository. Searched: every governed
#: input under ``reference/dynamic_weekly_mc_v3/inputs``, the canonical team
#: master, the governance status artifacts and the whole working tree. The only
#: in-repo mentions of Colley are the two rulings that name it as a witness,
#: neither of which carries a formula, an implementation or an anchor row.
CANONICAL_VALIDATION_ANCHORS: tuple[tuple[str, float], ...] = ()
CANONICAL_COLLEY_SPEC_MOUNTED = False
CANONICAL_COLLEY_REFERENCE_IMPLEMENTATION = None
CANONICAL_VALIDATION_BLOCKER = "governance.COLLEY_CANONICAL_VALIDATION_ANCHORS_NOT_MOUNTED"


def require_canonical_validated_colley() -> None:
    """Fail closed on any claim that this Colley is the canonical validated model.

    The method has no free parameters, so what is implemented here cannot have
    been tuned. That is not the same as having been checked against a canonical
    ordering, and no artifact this repository holds could perform that check.
    """
    raise GovernanceBlock(
        f"{CANONICAL_VALIDATION_BLOCKER}: no canonical Colley Matrix specification, "
        "reference implementation or historical validation anchor is mounted. This module "
        "solves the parameter-free Colley system exactly and verifies its residuals, mean "
        "and matrix structure, but agreement with a canonical ordering cannot be "
        "demonstrated against artifacts that are not present. Mount the specification and "
        "anchors."
    )


def reject_parameterised_colley(variant: str) -> None:
    """Refuse the variants that carry parameters the rulings never issued."""
    described = PARAMETERISED_VARIANTS.get(variant.strip().upper())
    if described:
        raise GovernanceBlock(
            f"{variant!r} adds {described} to the Colley Matrix. Ruling "
            f"{R2_CALIBRATION.convergence_id} names the Colley Matrix, which has no free "
            "parameters; a parameterised variant is a different model and its parameters "
            "would need governing before use."
        )


def reject_colley_as(metric_name: str) -> None:
    """Refuse Colley standing in for the primary criterion, committee SOS or SOR."""
    banned = {
        "SOS": "committee SOS",
        "COMMITTEE_SOS": "committee SOS",
        "STRENGTH_OF_SCHEDULE": "committee SOS",
        "SOR": "SOR",
        "SOR_B": "SOR",
        "RECORD_STRENGTH": "SOR",
        "BAXTER": "the primary Baxter Rating criterion",
        "BAXTER_RATING": "the primary Baxter Rating criterion",
        "SRS": "the SRS witness",
    }
    role = banned.get(metric_name.upper())
    if role:
        raise GovernanceBlock(
            f"Colley may not be used as {role}. Rulings {R2_CALIBRATION.convergence_id} and "
            f"{R2_SRS.convergence_id} keep Colley a separate {WITNESS_ROLE}."
        )


def reject_witness_composite(components: Iterable[str]) -> None:
    """Refuse a weighted composite of the calibration witnesses.

    Ruling R2-CAL-OBJECTIVE authorises Baxter Rating RMSE as the primary
    criterion with Colley and SRS reported independently. A blend of them is the
    unadopted BWI proposal recorded in ``18_ACC_POLICY_REFERENCE`` ACC-EXT-12.
    """
    named = {c.upper() for c in components}
    witnesses = {
        "SRS",
        "COLLEY",
        "COLLEY_MATRIX",
        "BAXTER",
        "BAXTER_RATING",
        "SOR",
        "SOR_B",
    }
    overlap = sorted(named & witnesses)
    if len(overlap) > 1:
        raise GovernanceBlock(
            f"A weighted composite of {overlap} is not authorised. ACC-EXT-12 records the "
            "Body-of-Work Index blend as PROPOSAL ONLY / NOT ADOPTED; witnesses are reported "
            "independently."
        )


def witness_as_dict(
    ratings: dict[str, float], records: dict[str, tuple[int, int]] | None = None
) -> dict[str, object]:
    return {
        "ruling": R2_CALIBRATION.convergence_id,
        "model": "COLLEY_MATRIX",
        "role": WITNESS_ROLE,
        "free_parameters": list(COLLEY_FREE_PARAMETERS),
        "uses_margin_of_victory": False,
        "mean_rating": COLLEY_MEAN_RATING,
        "is_committee_sos": False,
        "is_sor": False,
        "is_primary_criterion": False,
        "tie_policy": COLLEY_TIE_POLICY,
        "tie_policy_blocker": COLLEY_TIE_BLOCKER,
        "canonical_spec_mounted": CANONICAL_COLLEY_SPEC_MOUNTED,
        "canonical_reference_implementation": CANONICAL_COLLEY_REFERENCE_IMPLEMENTATION,
        "canonical_validation_anchors": list(CANONICAL_VALIDATION_ANCHORS),
        "canonical_validation_status": "NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS",
        "canonical_validation_blocker": CANONICAL_VALIDATION_BLOCKER,
        "ordering": colley_ordering(ratings),
        "ratings": {t: ratings[t] for t in sorted(ratings)},
        "records": (
            {t: list(records[t]) for t in sorted(records)} if records is not None else None
        ),
    }
