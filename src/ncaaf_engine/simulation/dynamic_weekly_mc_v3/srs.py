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
from .linalg import solve_exact
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
    """Exact solve of the schedule-adjustment system.

    Written out rather than iterated to a fixed point: the Jacobi sweep the
    schedule-adjustment equations invite does not converge on small or
    lopsided schedules, and a solver that quietly returns its last oscillation
    would hand back a plausible ordering that is simply wrong. The arithmetic
    itself lives in :mod:`linalg`, shared with the Colley witness, so the two
    witnesses cannot disagree about linear algebra while appearing to disagree
    about football.
    """
    return solve_exact(
        matrix,
        rhs,
        singular_message=(
            "SRS schedule-adjustment system is singular; the schedule graph is "
            "disconnected or degenerate"
        ),
        pivot_epsilon=SRS_PIVOT_EPSILON,
    )


def _components(adjacency: dict[str, set[str]], teams: list[str]) -> list[list[str]]:
    """Connected components of the schedule graph, each in sorted order."""
    seen: set[str] = set()
    out: list[list[str]] = []
    for start in teams:
        if start in seen:
            continue
        stack, group = [start], []
        seen.add(start)
        while stack:
            node = stack.pop()
            group.append(node)
            for nxt in sorted(adjacency[node]):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        out.append(sorted(group))
    return sorted(out, key=lambda g: g[0])


def _build_system(games: Sequence[SrsGame]):
    margins: dict[str, float] = {}
    counts: dict[str, int] = {}
    opponents: dict[str, dict[str, int]] = {}
    adjacency: dict[str, set[str]] = {}
    for game in games:
        for side in (game.team, game.opponent):
            margins.setdefault(side, 0.0)
            counts.setdefault(side, 0)
            opponents.setdefault(side, {})
            adjacency.setdefault(side, set())
        margins[game.team] += cap_margin(game.margin)
        counts[game.team] += 1
        opponents[game.team][game.opponent] = opponents[game.team].get(game.opponent, 0) + 1
        adjacency[game.team].add(game.opponent)
        adjacency[game.opponent].add(game.team)
    return margins, counts, opponents, adjacency


def compute_srs(games: Sequence[SrsGame]) -> dict[str, float]:
    """Opponent-adjusted capped-margin ratings, centred on zero.

    Solves the governed schedule-adjustment system exactly, per connected
    component::

        n_i * r_i - sum_j m_ij * r_j = sum of team i's capped margins

    subject to ``sum r = 0`` over the component.

    Two implementation notes, both deliberate and both testable:

    *Exact rather than iterated.* The equations invite a Jacobi sweep, and a
    Jacobi sweep does not converge on small or lopsided schedules — it
    oscillates, and an implementation that stops at a max-iteration count
    returns its last oscillation as though it were a solution. The fixed point
    of a *converged* iteration is precisely the solution of this linear system,
    so the two agree wherever the iteration is legitimate;
    :func:`assert_solver_equivalence` checks exactly that.

    *Per component.* Before the schedule graph connects — which in practice
    means the opening weeks — the global system is singular with one degree of
    freedom per component, and a single global centring constraint cannot fix
    it. Each component is therefore centred on its own zero. Ratings are only
    comparable within a component, which was already true of the mathematics.
    On a connected graph this is identical to global centring.
    """
    if not games:
        raise InputValidationError("SRS requires at least one game")

    margins, counts, opponents, adjacency = _build_system(games)
    teams = sorted(counts)
    ratings: dict[str, float] = {}

    for component in _components(adjacency, teams):
        index = {t: i for i, t in enumerate(component)}
        n = len(component)
        matrix = [[0.0] * n for _ in range(n)]
        rhs = [0.0] * n
        for team in component:
            i = index[team]
            matrix[i][i] = float(counts[team])
            for opponent, played in opponents[team].items():
                matrix[i][index[opponent]] -= float(played)
            rhs[i] = margins[team]
        matrix[n - 1] = [1.0] * n
        rhs[n - 1] = 0.0
        solved = _solve(matrix, rhs)
        for team in component:
            ratings[team] = solved[index[team]]
    return ratings


def srs_components(games: Sequence[SrsGame]) -> list[list[str]]:
    """The connected components the ratings are centred within."""
    _, counts, _, adjacency = _build_system(games)
    return _components(adjacency, sorted(counts))


def compute_srs_iterative(
    games: Sequence[SrsGame],
    *,
    max_iterations: int = 100_000,
    tolerance: float = 1e-12,
) -> tuple[dict[str, float], bool, int]:
    """Gauss-Seidel reference implementation, kept for cross-checking only.

    Returns ``(ratings, converged, iterations)``. ``converged`` is False when the
    sweep hit the iteration ceiling — the case a naive implementation would
    silently return as a result.
    """
    if not games:
        raise InputValidationError("SRS requires at least one game")
    margins, counts, opponents, adjacency = _build_system(games)
    teams = sorted(counts)
    ratings = {t: 0.0 for t in teams}
    components = _components(adjacency, teams)

    for iteration in range(1, max_iterations + 1):
        delta = 0.0
        for team in teams:
            total = margins[team] + sum(
                played * ratings[opponent] for opponent, played in opponents[team].items()
            )
            updated = total / counts[team]
            delta = max(delta, abs(updated - ratings[team]))
            ratings[team] = updated
        for component in components:
            mean = sum(ratings[t] for t in component) / len(component)
            for t in component:
                ratings[t] -= mean
        if delta < tolerance:
            return ratings, True, iteration
    return ratings, False, max_iterations


def srs_residuals(games: Sequence[SrsGame], ratings: dict[str, float]) -> dict[str, float]:
    """Per-team residual of the governed equation. Zero means the system is solved."""
    margins, counts, opponents, _ = _build_system(games)
    out: dict[str, float] = {}
    for team in sorted(counts):
        lhs = counts[team] * ratings[team] - sum(
            played * ratings[opponent] for opponent, played in opponents[team].items()
        )
        out[team] = lhs - margins[team]
    return out


def assert_solver_equivalence(
    games: Sequence[SrsGame], *, tolerance: float = 1e-6
) -> dict[str, object]:
    """Prove the exact solver and a converged iteration solve the same system.

    Checks, in order: the exact solution's residuals are zero; each component is
    centred; and — only where the iteration actually converged — that the two
    orderings and values agree. If the iteration did not converge, that is
    reported rather than treated as disagreement, because a non-converged sweep
    has no solution to compare against.
    """
    exact = compute_srs(games)
    residuals = srs_residuals(games, exact)
    worst_residual = max(abs(v) for v in residuals.values())
    if worst_residual > tolerance:
        raise InputValidationError(
            f"Exact SRS solution does not satisfy the governed system; worst residual "
            f"{worst_residual}"
        )

    components = srs_components(games)
    worst_centring = max(
        abs(sum(exact[t] for t in component)) for component in components
    )
    if worst_centring > tolerance:
        raise InputValidationError(f"SRS components are not centred; worst |sum| {worst_centring}")

    iterative, converged, iterations = compute_srs_iterative(games)
    max_difference = (
        max(abs(exact[t] - iterative[t]) for t in exact) if converged else None
    )
    if converged and max_difference is not None and max_difference > tolerance:
        raise InputValidationError(
            f"Exact and converged-iterative SRS disagree by {max_difference}"
        )
    ordered_values = sorted(exact.values())
    min_gap = min(
        (b - a for a, b in zip(ordered_values, ordered_values[1:])), default=float("inf")
    )
    return {
        "teams": len(exact),
        "components": [list(c) for c in components],
        # Two ratings closer together than the solver-agreement tolerance can order
        # either way. Reporting the gap lets a caller distinguish a real ordering
        # disagreement from float noise at a near-exact tie.
        "min_rating_gap": min_gap,
        "worst_residual": worst_residual,
        "worst_component_centring": worst_centring,
        "iterative_converged": converged,
        "iterative_iterations": iterations,
        "max_abs_difference": max_difference,
        "orderings_match": (
            srs_ordering(exact) == srs_ordering(iterative) if converged else None
        ),
        "margin_cap": SRS_MARGIN_CAP,
    }


def srs_ordering(ratings: dict[str, float]) -> list[str]:
    """Best rating first; ties break on schedule_id so the order is total."""
    return sorted(ratings, key=lambda t: (-ratings[t], t))


#: No canonical SRS specification, reference implementation (``compute_srs.py``)
#: or historical validation anchor is mounted in this repository. Searched: every
#: workbook cell across all eight governed inputs, the canonical team master, and
#: the whole filesystem. The only in-repo mention of SRS as a model is
#: 18_ACC_POLICY_REFERENCE!C14, which records "z(SRS capped +/-24)" inside a
#: Body-of-Work Index proposal marked PROPOSAL ONLY / NOT ADOPTED.
CANONICAL_VALIDATION_ANCHORS: tuple[tuple[str, float], ...] = ()
CANONICAL_SRS_SPEC_MOUNTED = False
CANONICAL_SRS_REFERENCE_IMPLEMENTATION = None
CANONICAL_VALIDATION_BLOCKER = "governance.SRS_CANONICAL_VALIDATION_ANCHORS_NOT_MOUNTED"

#: ``srs_over_40`` appears in no mounted artifact. Its threshold, denominator and
#: direction are all undefined here, so it is not implemented.
SRS_OVER_40_SEMANTICS = None


def require_canonical_validated_srs() -> None:
    """Fail closed on any claim that this SRS is the canonical validated model.

    The mathematics below is verifiable and verified. What cannot be verified in
    this repository is agreement with a canonical implementation or its
    historical anchors, because neither is mounted. Treating a self-consistent
    solver as canonically validated would be exactly the silent redefinition
    this gate exists to prevent.
    """
    raise GovernanceBlock(
        f"{CANONICAL_VALIDATION_BLOCKER}: no canonical SRS specification, reference "
        "implementation or historical validation anchor is mounted. This module solves the "
        "governed capped-margin system exactly and cross-checks against a converged "
        "iteration, but agreement with the canonical ordering cannot be demonstrated "
        "against artifacts that are not present. Mount the specification and anchors."
    )


def require_srs_over_40(_value: float | None = None) -> float:
    """Fail closed: ``srs_over_40`` semantics are not defined in any mounted artifact."""
    raise GovernanceBlock(
        "srs_over_40 is not defined in any mounted artifact — no threshold, denominator or "
        "direction is recorded. Issue the semantics; do not infer them from the name."
    )


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
        "canonical_spec_mounted": CANONICAL_SRS_SPEC_MOUNTED,
        "canonical_reference_implementation": CANONICAL_SRS_REFERENCE_IMPLEMENTATION,
        "canonical_validation_anchors": list(CANONICAL_VALIDATION_ANCHORS),
        "canonical_validation_status": "NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS",
        "canonical_validation_blocker": CANONICAL_VALIDATION_BLOCKER,
        "srs_over_40_semantics": SRS_OVER_40_SEMANTICS,
        "ordering": srs_ordering(ratings),
        "ratings": {t: ratings[t] for t in sorted(ratings)},
    }
