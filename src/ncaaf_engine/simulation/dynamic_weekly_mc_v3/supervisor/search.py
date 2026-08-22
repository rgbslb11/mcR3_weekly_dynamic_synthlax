"""Deterministic candidate search, refinement and identification.

The optimization loop lives here, in Python, and it is a loop over a declared
grid rather than a judgement call. Nothing in this module asks a model, an
operator or an assistant which value looks right; given the same axis, the same
oracle and the same expansion budget it returns the same answer on every machine
and in every run.

Boundary optima are the reason this module is not ten lines
------------------------------------------------------------

A grid search always returns a best point. When that point is the edge of the
declared range, "best on this grid" and "best" are different claims, and the
difference is invisible in the number itself: the objective may still be falling
off the end. Accepting it records the range-writer's guess as a measurement.

So a boundary optimum is not a result. :func:`identify_parameter` widens the
range on the side that bound and searches again, up to a finite declared budget.
If the optimum is still on a boundary when the budget is spent, the outcome is
:data:`BOUNDARY_BOUND_AT_MAX_EXPANSION` and the parameter is reported
:data:`PARAMETER_UNIDENTIFIED` for human review -- which is a smaller claim than
a number, and a true one.

The budget is finite and declared for the same reason: an unbounded expansion
loop would eventually terminate on floating-point nonsense and report it, and a
search that can run forever is not deterministic in any useful sense.

Non-binding constraints are the second way to record a guess
-------------------------------------------------------------

``weekly_movement_cap_points`` is a cap. If none of the statistically
equivalent finalists ever hit it, every value above the largest observed
movement scores identically, and whichever one the tie-break happens to return
is an artifact of the tie-break. :func:`classify_movement_cap` says so: among
the equivalent finalists, a cap that never binds is
:data:`UNIDENTIFIED_NONBINDING`, not measured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping, Sequence

from ..calibration import PRIMARY_CALIBRATION_DIRECTION, PRIMARY_CALIBRATION_METRIC
from ..errors import InputValidationError
from .digests import digest_mapping

__all__ = [
    "BOUNDARY_BOUND_AT_MAX_EXPANSION",
    "BOUNDARY_EXPANDED_THEN_INTERIOR",
    "FinalistObservation",
    "IDENTIFIED",
    "INTERIOR_OPTIMUM",
    "PARAMETER_UNIDENTIFIED",
    "SearchAxis",
    "SearchOutcome",
    "ScoringOracle",
    "UNIDENTIFIED_NONBINDING",
    "candidate_universe_digest",
    "classify_movement_cap",
    "coarse_search",
    "grid_for",
    "identify_parameter",
    "refine",
]


#: Rounding applied to every grid value. Twelve decimals is far finer than any
#: parameter this model carries and coarse enough that the same range produces
#: the same points whatever order the arithmetic happened in.
_GRID_DECIMALS = 12

# --- boundary status ---------------------------------------------------------

#: The optimum sat strictly inside the declared range. The range was adequate.
INTERIOR_OPTIMUM = "INTERIOR_OPTIMUM"

#: The optimum was initially on a boundary; the range was widened and the
#: optimum then landed inside. A real result, with its history recorded.
BOUNDARY_EXPANDED_THEN_INTERIOR = "BOUNDARY_EXPANDED_THEN_INTERIOR"

#: Still on a boundary after the declared expansion budget was spent.
BOUNDARY_BOUND_AT_MAX_EXPANSION = "BOUNDARY_BOUND_AT_MAX_EXPANSION"

#: Still on a boundary, and the boundary is a declared physical limit that must
#: not be crossed. Distinct from the budget case: no amount of further searching
#: would help, because the range is not the constraint.
BOUNDARY_BOUND_AT_DECLARED_LIMIT = "BOUNDARY_BOUND_AT_DECLARED_LIMIT"

# --- identification status ---------------------------------------------------

#: A value was measured.
IDENTIFIED = "IDENTIFIED"

#: No value was measured. Reported instead of a number.
PARAMETER_UNIDENTIFIED = "PARAMETER_UNIDENTIFIED"

#: The parameter is a constraint that never bound among equivalent finalists.
UNIDENTIFIED_NONBINDING = "UNIDENTIFIED_NONBINDING"

#: The constraint bound for at least one equivalent finalist, so its value has
#: an effect that the objective can see.
IDENTIFIED_BINDING = "IDENTIFIED_BINDING"


@dataclass(frozen=True)
class ScoringOracle:
    """The deterministic scoring interface a search is run against.

    The supervisor does not implement model mathematics. It is handed one of
    these -- backed by whatever governed calibration interface actually scores a
    candidate -- and calls it. ``implementation_digest`` is supplied by the
    caller and is what the holdout seal binds, so a run cannot change the
    scoring function between sealing candidates and releasing the holdout.

    ``split`` is a required keyword at every call, never a default. A scoring
    call that does not say which partition it is reading cannot be refused by
    the holdout guard, and a guard that can be bypassed by omission is not one.
    """

    oracle_id: str
    fn: Callable[[Mapping[str, Any], str], float]
    implementation_digest: str
    metric: str = PRIMARY_CALIBRATION_METRIC
    direction: str = PRIMARY_CALIBRATION_DIRECTION

    def __post_init__(self) -> None:
        if self.direction not in ("minimize", "maximize"):
            raise InputValidationError(
                f"Scoring oracle direction must be minimize or maximize, got "
                f"{self.direction!r}."
            )
        if not self.implementation_digest.strip():
            raise InputValidationError(
                f"Scoring oracle {self.oracle_id} carries no implementation digest. "
                "The holdout seal binds this value; an empty one binds nothing."
            )

    @property
    def digest(self) -> str:
        """Identity of the oracle, as the holdout seal records it."""
        return digest_mapping(
            {
                "oracle_id": self.oracle_id,
                "implementation_digest": self.implementation_digest,
                "metric": self.metric,
                "direction": self.direction,
            }
        )

    def score(self, candidate: Mapping[str, Any], *, split: str) -> float:
        """Score ``candidate`` on ``split``. Returns a comparable float.

        Direction is normalised away: a maximizing objective is negated so every
        caller in this module can minimize. Doing it once here means no search
        loop carries a direction branch that could be got wrong on one path.
        """
        raw = float(self.fn(dict(candidate), split))
        return raw if self.direction == "minimize" else -raw

    def raw_score(self, candidate: Mapping[str, Any], *, split: str) -> float:
        """The objective as reported, in its own direction, for the record."""
        return float(self.fn(dict(candidate), split))


@dataclass(frozen=True)
class SearchAxis:
    """One declared, expandable search range for one parameter.

    ``hard_lower`` / ``hard_upper`` are physical or governed limits -- a
    variance that cannot be negative, a cap that cannot exceed the rating scale.
    Expansion stops at them and says so, which is a different outcome from
    exhausting the expansion budget and must not be reported as the same one.
    """

    parameter: str
    lower: float
    upper: float
    points: int
    max_expansions: int
    expansion_factor: float = 2.0
    hard_lower: float | None = None
    hard_upper: float | None = None
    refinement_rounds: int = 2
    refinement_points: int = 5

    def __post_init__(self) -> None:
        if self.points < 3:
            raise InputValidationError(
                f"Axis {self.parameter} declares {self.points} grid points; at least 3 "
                "are needed for an interior point to exist at all."
            )
        if not self.upper > self.lower:
            raise InputValidationError(
                f"Axis {self.parameter} has upper {self.upper} <= lower {self.lower}."
            )
        if self.max_expansions < 0:
            raise InputValidationError(
                f"Axis {self.parameter} declares a negative expansion budget."
            )
        if self.expansion_factor <= 1.0:
            raise InputValidationError(
                f"Axis {self.parameter} declares expansion factor "
                f"{self.expansion_factor}; an expansion must widen the range."
            )
        if self.refinement_rounds < 0:
            raise InputValidationError(
                f"Axis {self.parameter} declares a negative refinement round count."
            )
        if self.refinement_points < 3:
            raise InputValidationError(
                f"Axis {self.parameter} declares {self.refinement_points} refinement "
                "points; at least 3 are needed."
            )
        if self.hard_lower is not None and self.lower < self.hard_lower:
            raise InputValidationError(
                f"Axis {self.parameter} starts below its declared hard lower limit."
            )
        if self.hard_upper is not None and self.upper > self.hard_upper:
            raise InputValidationError(
                f"Axis {self.parameter} starts above its declared hard upper limit."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "lower": self.lower,
            "upper": self.upper,
            "points": self.points,
            "max_expansions": self.max_expansions,
            "expansion_factor": self.expansion_factor,
            "hard_lower": self.hard_lower,
            "hard_upper": self.hard_upper,
            "refinement_rounds": self.refinement_rounds,
            "refinement_points": self.refinement_points,
        }

    @classmethod
    def from_search_space(cls, parameter: str, space: Mapping[str, Any]) -> "SearchAxis":
        """Build an axis from a frozen manifest's declared search space."""
        try:
            return cls(
                parameter=parameter,
                lower=float(space["lower"]),
                upper=float(space["upper"]),
                points=int(space["points"]),
                max_expansions=int(space["max_expansions"]),
                expansion_factor=float(space.get("expansion_factor", 2.0)),
                hard_lower=(
                    None if space.get("hard_lower") is None else float(space["hard_lower"])
                ),
                hard_upper=(
                    None if space.get("hard_upper") is None else float(space["hard_upper"])
                ),
                refinement_rounds=int(space.get("refinement_rounds", 2)),
                refinement_points=int(space.get("refinement_points", 5)),
            )
        except KeyError as exc:
            raise InputValidationError(
                f"Search space for {parameter} is missing required key {exc.args[0]!r}. "
                "A declared range needs lower, upper, points and max_expansions."
            ) from None


def grid_for(lower: float, upper: float, points: int) -> tuple[float, ...]:
    """Evenly spaced, deterministically rounded grid values.

    Computed as ``lower + i * (upper - lower) / (points - 1)`` rather than by
    repeated addition, so accumulated float error cannot make the last point
    miss ``upper`` -- which would silently move a boundary the expansion logic
    is about to test against.
    """
    span = upper - lower
    return tuple(
        round(lower + i * span / (points - 1), _GRID_DECIMALS) for i in range(points)
    )


def _argmin(scores: Sequence[float]) -> int:
    """Index of the smallest score; ties resolve to the lowest index.

    Deterministic tie-breaking is the point. ``min`` over an unordered structure
    would leave the winner dependent on iteration order, and two runs of the
    same search must not disagree about which of two identical scores won.
    """
    best = 0
    for i in range(1, len(scores)):
        if scores[i] < scores[best]:
            best = i
    return best


@dataclass(frozen=True)
class SearchOutcome:
    """The full record of one parameter's identification attempt.

    Every evaluation is kept, not just the winner. A recommendation that cites a
    value has to be able to show the curve it came off, and a boundary claim is
    only checkable against the points that were actually scored.
    """

    parameter: str
    best_value: float | None
    best_score: float | None
    boundary_status: str
    identification_status: str
    expansions_used: int
    max_expansions: int
    declared_lower: float
    declared_upper: float
    final_lower: float
    final_upper: float
    evaluations: tuple[tuple[float, float], ...] = ()
    refinement_rounds_used: int = 0
    notes: tuple[str, ...] = ()

    @property
    def identified(self) -> bool:
        return self.identification_status == IDENTIFIED

    @property
    def range_was_expanded(self) -> bool:
        return self.expansions_used > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "best_value": self.best_value,
            "best_score": self.best_score,
            "boundary_status": self.boundary_status,
            "identification_status": self.identification_status,
            "expansions_used": self.expansions_used,
            "max_expansions": self.max_expansions,
            "declared_lower": self.declared_lower,
            "declared_upper": self.declared_upper,
            "final_lower": self.final_lower,
            "final_upper": self.final_upper,
            "evaluations": [[v, s] for v, s in self.evaluations],
            "refinement_rounds_used": self.refinement_rounds_used,
            "notes": list(self.notes),
        }


def _expand(
    axis: SearchAxis, lower: float, upper: float, at_lower: bool
) -> tuple[float, float, bool]:
    """Widen the range on the side that bound.

    Returns ``(lower, upper, gained_ground)``. ``gained_ground`` is False when a
    declared hard limit stopped the widening, which the caller reports as
    :data:`BOUNDARY_BOUND_AT_DECLARED_LIMIT` rather than as budget exhaustion:
    the two look identical in the optimum and mean opposite things about whether
    more searching would help.
    """
    width = upper - lower
    growth = width * (axis.expansion_factor - 1.0)
    if at_lower:
        candidate = round(lower - growth, _GRID_DECIMALS)
        if axis.hard_lower is not None:
            candidate = max(candidate, axis.hard_lower)
        return candidate, upper, candidate < lower
    candidate = round(upper + growth, _GRID_DECIMALS)
    if axis.hard_upper is not None:
        candidate = min(candidate, axis.hard_upper)
    return lower, candidate, candidate > upper


def coarse_search(
    axis: SearchAxis,
    oracle: ScoringOracle,
    *,
    split: str,
    context: Mapping[str, Any] | None = None,
) -> SearchOutcome:
    """Grid-search ``axis``, expanding the range off any boundary optimum.

    ``context`` is the rest of the candidate vector -- fixed values, values
    already identified by earlier axes -- held constant while this axis moves.
    """
    base = dict(context or {})
    lower, upper = axis.lower, axis.upper
    evaluations: list[tuple[float, float]] = []
    seen: dict[float, float] = {}
    expansions = 0
    notes: list[str] = []

    while True:
        values = grid_for(lower, upper, axis.points)
        scores: list[float] = []
        for value in values:
            if value not in seen:
                # Re-scoring a point an earlier expansion already covered would
                # waste a model evaluation and, worse, would let a
                # non-deterministic oracle disagree with itself inside one search.
                seen[value] = oracle.score({**base, axis.parameter: value}, split=split)
                evaluations.append((value, seen[value]))
            scores.append(seen[value])

        best = _argmin(scores)
        on_boundary = best in (0, len(values) - 1)
        if not on_boundary:
            status = (
                BOUNDARY_EXPANDED_THEN_INTERIOR if expansions else INTERIOR_OPTIMUM
            )
            return SearchOutcome(
                parameter=axis.parameter,
                best_value=values[best],
                best_score=scores[best],
                boundary_status=status,
                identification_status=IDENTIFIED,
                expansions_used=expansions,
                max_expansions=axis.max_expansions,
                declared_lower=axis.lower,
                declared_upper=axis.upper,
                final_lower=lower,
                final_upper=upper,
                evaluations=tuple(sorted(evaluations)),
                notes=tuple(notes),
            )

        at_lower = best == 0
        if expansions >= axis.max_expansions:
            notes.append(
                f"Optimum remained on the "
                f"{'lower' if at_lower else 'upper'} boundary after "
                f"{expansions} expansion(s); the declared budget is "
                f"{axis.max_expansions}."
            )
            return SearchOutcome(
                parameter=axis.parameter,
                best_value=None,
                best_score=scores[best],
                boundary_status=BOUNDARY_BOUND_AT_MAX_EXPANSION,
                identification_status=PARAMETER_UNIDENTIFIED,
                expansions_used=expansions,
                max_expansions=axis.max_expansions,
                declared_lower=axis.lower,
                declared_upper=axis.upper,
                final_lower=lower,
                final_upper=upper,
                evaluations=tuple(sorted(evaluations)),
                notes=tuple(notes),
            )

        lower, upper, gained = _expand(axis, lower, upper, at_lower)
        if not gained:
            notes.append(
                f"Optimum sits on the declared hard "
                f"{'lower' if at_lower else 'upper'} limit; the range cannot be "
                "widened further and the limit, not the grid, is the constraint."
            )
            return SearchOutcome(
                parameter=axis.parameter,
                best_value=None,
                best_score=scores[best],
                boundary_status=BOUNDARY_BOUND_AT_DECLARED_LIMIT,
                identification_status=PARAMETER_UNIDENTIFIED,
                expansions_used=expansions,
                max_expansions=axis.max_expansions,
                declared_lower=axis.lower,
                declared_upper=axis.upper,
                final_lower=lower,
                final_upper=upper,
                evaluations=tuple(sorted(evaluations)),
                notes=tuple(notes),
            )
        expansions += 1


def refine(
    axis: SearchAxis,
    coarse: SearchOutcome,
    oracle: ScoringOracle,
    *,
    split: str,
    context: Mapping[str, Any] | None = None,
) -> SearchOutcome:
    """Tighten a coarse result, returning a new outcome that supersedes it.

    Refinement brackets the coarse winner between its immediate neighbours and
    subdivides, for a declared number of rounds. It never leaves the searched
    range, so it cannot introduce a new boundary condition -- the boundary
    question was already settled by :func:`coarse_search`, and re-opening it
    here would let a refinement round quietly extend a range the expansion
    budget had already closed.

    A coarse outcome that identified nothing is returned unchanged. There is no
    winner to bracket, and refining around a boundary the search already refused
    to accept would manufacture precision for a value that was never measured.
    """
    if not coarse.identified or axis.refinement_rounds == 0:
        return coarse

    base = dict(context or {})
    evaluations = list(coarse.evaluations)
    seen = {value: score for value, score in coarse.evaluations}
    best_value = coarse.best_value
    best_score = coarse.best_score
    assert best_value is not None and best_score is not None  # identified

    step = (coarse.final_upper - coarse.final_lower) / (axis.points - 1)
    rounds = 0
    for _ in range(axis.refinement_rounds):
        low = max(round(best_value - step, _GRID_DECIMALS), coarse.final_lower)
        high = min(round(best_value + step, _GRID_DECIMALS), coarse.final_upper)
        if not high > low:
            break
        values = grid_for(low, high, axis.refinement_points)
        scores = []
        for value in values:
            if value not in seen:
                seen[value] = oracle.score({**base, axis.parameter: value}, split=split)
                evaluations.append((value, seen[value]))
            scores.append(seen[value])
        index = _argmin(scores)
        best_value, best_score = values[index], scores[index]
        step = (high - low) / (axis.refinement_points - 1)
        rounds += 1

    return SearchOutcome(
        parameter=coarse.parameter,
        best_value=best_value,
        best_score=best_score,
        boundary_status=coarse.boundary_status,
        identification_status=IDENTIFIED,
        expansions_used=coarse.expansions_used,
        max_expansions=axis.max_expansions,
        declared_lower=axis.lower,
        declared_upper=axis.upper,
        final_lower=coarse.final_lower,
        final_upper=coarse.final_upper,
        evaluations=tuple(sorted(evaluations)),
        refinement_rounds_used=rounds,
        notes=coarse.notes,
    )


def identify_parameter(
    axis: SearchAxis,
    oracle: ScoringOracle,
    *,
    split: str,
    context: Mapping[str, Any] | None = None,
) -> SearchOutcome:
    """Coarse-search then refine, as one call, returning one record."""
    coarse = coarse_search(axis, oracle, split=split, context=context)
    return refine(axis, coarse, oracle, split=split, context=context)


@dataclass(frozen=True)
class FinalistObservation:
    """One finalist candidate, and how often a constraint bound under it.

    ``constraint_binding_events`` is counted by whatever ran the candidate, not
    inferred here. Inferring it would mean this module deciding what "the cap
    bound" means, which is model mathematics and belongs to the engine.
    """

    candidate_id: str
    score: float
    constraint_value: float
    constraint_binding_events: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "score": self.score,
            "constraint_value": self.constraint_value,
            "constraint_binding_events": self.constraint_binding_events,
        }


def classify_movement_cap(
    finalists: Sequence[FinalistObservation],
    *,
    equivalence_tolerance: float,
    parameter: str = "weekly_movement_cap_points",
) -> dict[str, Any]:
    """Decide whether a constraint was measured or merely tie-broken.

    Among the finalists within ``equivalence_tolerance`` of the best score, if
    the constraint never bound, then every value above the largest movement the
    data produced scores identically and the returned one is an artifact of the
    tie-break. That is reported as :data:`UNIDENTIFIED_NONBINDING` with no
    recommended value, because a recommendation carrying a number implies the
    number was measured.
    """
    if not finalists:
        raise InputValidationError(
            f"Cannot classify {parameter}: no finalists were supplied."
        )
    if equivalence_tolerance < 0:
        raise InputValidationError(
            f"Equivalence tolerance for {parameter} must not be negative."
        )
    best = min(f.score for f in finalists)
    equivalent = tuple(
        f for f in sorted(finalists, key=lambda f: (f.score, f.candidate_id))
        if f.score <= best + equivalence_tolerance
    )
    binding_events = sum(f.constraint_binding_events for f in equivalent)
    nonbinding = binding_events == 0
    return {
        "parameter": parameter,
        "identification_status": (
            UNIDENTIFIED_NONBINDING if nonbinding else IDENTIFIED_BINDING
        ),
        "recommended_value": (
            None if nonbinding else equivalent[0].constraint_value
        ),
        "best_score": best,
        "equivalence_tolerance": equivalence_tolerance,
        "equivalent_finalist_count": len(equivalent),
        "equivalent_finalists": [f.as_dict() for f in equivalent],
        "total_binding_events_among_equivalent_finalists": binding_events,
        "rationale": (
            f"{parameter} never bound across {len(equivalent)} evidentially "
            "equivalent finalists, so the objective cannot distinguish any value "
            "above the largest observed movement. The tie-break value is an "
            "artifact of the tie-break and is not reported as measured."
            if nonbinding
            else
            f"{parameter} bound {binding_events} time(s) among "
            f"{len(equivalent)} equivalent finalists, so the objective can see its "
            "value."
        ),
    }


def candidate_universe_digest(
    axes: Sequence[SearchAxis], fixed: Mapping[str, Any] | None = None
) -> str:
    """Digest of everything the search was allowed to consider.

    Bound into the holdout seal. If a later stage widened an axis, added one, or
    changed a value that was supposed to be held fixed, this digest moves and the
    seal refuses -- which is what stops the candidate universe from being edited
    after the holdout was locked against it.
    """
    return digest_mapping(
        {
            "axes": [axis.as_dict() for axis in sorted(axes, key=lambda a: a.parameter)],
            "fixed": dict(sorted((fixed or {}).items())),
        }
    )
