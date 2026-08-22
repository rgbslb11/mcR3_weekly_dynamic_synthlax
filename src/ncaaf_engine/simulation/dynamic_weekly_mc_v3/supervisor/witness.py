"""The real-football witness: it may diagnose, and it may never select.

Real 2021-2024 football is admissible under this calibration doctrine in exactly
one role. It can tell an operator that the synthetic-domain parameter vector
produces margins twice as dispersed as any season ever played, and that is worth
knowing. It cannot then adjust the vector, because the vector is estimated on
synthetic 2024/2025 for synthetic 2026 and a correction toward real football is
a correction toward a different target.

The distinction is easy to state and easy to lose, because the natural next line
of code after "the witness disagrees" is "so change it". Two things stop that
here:

* :func:`require_vector_unchanged` is called on the way out of the witness stage
  with the vector as it went in. Any difference raises. A witness that returned a
  modified vector cannot get it past this function, whatever it called it.
* Nothing in this module returns a parameter value at all. The richest thing it
  produces is a classification and the numbers behind it.

Failure is classified by a *declared* threshold, not by a judgement made when the
number arrives. Each comparison names its advisory band, its failure band, and
what a breach means -- advisory, human review, or hard failure. Declaring it in
advance is what stops the outcome from being chosen after the result is known.

A comparison whose data is unavailable records :data:`WITNESS_UNAVAILABLE` and,
if that comparison is optional, the run continues on an advisory. If it is
required, the run stops: a required witness that could not be run is missing
evidence, and downgrading it to "fine" is exactly the silent downgrade the lane
instruction forbids.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from ..errors import GovernanceBlock, InputValidationError
from . import states as S
from .evidence import EXTERNAL_WITNESS_ONLY, REAL_WITNESS_CORPUS_SHA256

__all__ = [
    "ON_FAILURE_CLASSES",
    "WITNESS_COMPARISONS",
    "WITNESS_UNAVAILABLE",
    "WitnessObservation",
    "WitnessThreshold",
    "classify_witness",
    "default_thresholds",
    "require_vector_unchanged",
    "require_witness_corpus",
]

#: The comparisons the witness may report. Every one is a diagnosis of the
#: synthetic vector against real play; none of them is a target to fit toward.
WITNESS_COMPARISONS: tuple[str, ...] = (
    "real_vs_synthetic_margin_dispersion",
    "movement_plausibility",
    "blowout_behavior",
    "venue_sensitivity",
    "fcs_witness",
    "residual_scale",
    "stability",
)

#: Recorded when a comparison could not be computed at all.
WITNESS_UNAVAILABLE = "WITNESS_UNAVAILABLE"

#: What a declared threshold breach means. Chosen when the threshold is written,
#: never when the result arrives.
ON_FAILURE_ADVISORY = S.PASS_WITH_ADVISORY
ON_FAILURE_HUMAN_REVIEW = S.HUMAN_REVIEW_REQUIRED
ON_FAILURE_FAIL = S.FAIL

ON_FAILURE_CLASSES: tuple[str, ...] = (
    ON_FAILURE_ADVISORY,
    ON_FAILURE_HUMAN_REVIEW,
    ON_FAILURE_FAIL,
)


@dataclass(frozen=True)
class WitnessThreshold:
    """A declared band for one comparison, and what breaching it means."""

    comparison: str
    advisory_at: float
    failure_at: float
    on_failure: str = ON_FAILURE_HUMAN_REVIEW
    required: bool = False
    units: str = "absolute_divergence"

    def __post_init__(self) -> None:
        if self.comparison not in WITNESS_COMPARISONS:
            raise InputValidationError(
                f"Unknown witness comparison {self.comparison!r}; expected one of "
                f"{list(WITNESS_COMPARISONS)}."
            )
        if self.advisory_at < 0 or self.failure_at < 0:
            raise InputValidationError(
                f"Witness thresholds for {self.comparison} must not be negative."
            )
        if self.failure_at < self.advisory_at:
            raise InputValidationError(
                f"Witness failure band for {self.comparison} sits below its advisory "
                "band; a result cannot fail before it is worth mentioning."
            )
        if self.on_failure not in ON_FAILURE_CLASSES:
            raise InputValidationError(
                f"Witness threshold for {self.comparison} declares unknown failure "
                f"handling {self.on_failure!r}; expected one of {list(ON_FAILURE_CLASSES)}."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "comparison": self.comparison,
            "advisory_at": self.advisory_at,
            "failure_at": self.failure_at,
            "on_failure": self.on_failure,
            "required": self.required,
            "units": self.units,
        }


@dataclass(frozen=True)
class WitnessObservation:
    """One measured comparison, or an explicit statement that it could not be.

    ``available=False`` carries no numbers, and the classifier refuses to invent
    a divergence for it. An unavailable comparison that quietly scored zero
    would be the strongest possible pass produced by the weakest possible
    evidence.
    """

    comparison: str
    synthetic_value: float | None = None
    real_value: float | None = None
    divergence: float | None = None
    available: bool = True
    note: str = ""

    def __post_init__(self) -> None:
        if self.comparison not in WITNESS_COMPARISONS:
            raise InputValidationError(
                f"Unknown witness comparison {self.comparison!r}; expected one of "
                f"{list(WITNESS_COMPARISONS)}."
            )
        if self.available and self.divergence is None:
            raise InputValidationError(
                f"Witness comparison {self.comparison} reports available data but no "
                "divergence. A comparison with no measured difference has not been made."
            )
        if not self.available and self.divergence is not None:
            raise InputValidationError(
                f"Witness comparison {self.comparison} is unavailable yet carries a "
                "divergence."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "comparison": self.comparison,
            "synthetic_value": self.synthetic_value,
            "real_value": self.real_value,
            "divergence": self.divergence,
            "available": self.available,
            "note": self.note,
        }


def default_thresholds() -> tuple[WitnessThreshold, ...]:
    """A conservative declared band for each comparison.

    Every band is optional and breaches route to human review rather than to
    failure. That is the correct default under this doctrine: the witness is not
    the objective, so a divergence is a question about plausibility, and the
    only person entitled to answer it is the one who can also decide the answer
    changes nothing about the synthetic vector.

    A run that needs stricter or required bands supplies its own; these are a
    starting point, not a governed constant, and they are deliberately not
    exported as one.
    """
    return tuple(
        WitnessThreshold(
            comparison=name,
            advisory_at=0.15,
            failure_at=0.40,
            on_failure=ON_FAILURE_HUMAN_REVIEW,
            required=False,
            units="relative_divergence",
        )
        for name in WITNESS_COMPARISONS
    )


def require_witness_corpus(sha256: str, role: str) -> None:
    """Refuse any corpus but the accepted one, in any role but witness."""
    if sha256.lower() != REAL_WITNESS_CORPUS_SHA256:
        raise GovernanceBlock(
            "Real witness corpus digest does not match the accepted historical "
            f"observation corpus. Expected {REAL_WITNESS_CORPUS_SHA256}, got {sha256}."
        )
    if role != EXTERNAL_WITNESS_ONLY:
        raise GovernanceBlock(
            f"Real historical football was offered in role {role!r}. Its only "
            f"admissible role under this calibration doctrine is {EXTERNAL_WITNESS_ONLY}."
        )


def require_vector_unchanged(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> None:
    """Refuse if the witness stage changed the selected parameter vector.

    Called on the way out of the witness stage with the vector as it went in.
    This is the enforcement point for the doctrine's second half: whatever the
    witness found, and whatever a stage implementation intended, a vector that
    is not byte-identical to the one selection produced does not leave the
    witness stage.
    """
    changed = sorted(
        name
        for name in set(before) | set(after)
        if before.get(name, _MISSING) != after.get(name, _MISSING)
    )
    if changed:
        detail = {
            name: {"selected": before.get(name), "after_witness": after.get(name)}
            for name in changed
        }
        raise GovernanceBlock(
            f"Real-world witness altered the selected parameter vector: {changed}. "
            "Real football is EXTERNAL_WITNESS_ONLY; it may diagnose plausibility and "
            "may never change the synthetic-domain parameter vector. "
            f"Attempted change: {detail}"
        )


class _Missing:
    """Sentinel distinct from ``None``.

    A parameter deliberately carried as ``None`` -- an unidentified non-binding
    cap, say -- must not compare equal to a parameter the witness dropped
    entirely. ``dict.get`` with a ``None`` default would make those two the same
    and let a silent deletion through.
    """

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<absent>"


_MISSING = _Missing()


def classify_witness(
    observations: Sequence[WitnessObservation],
    thresholds: Sequence[WitnessThreshold] | None = None,
) -> dict[str, Any]:
    """Classify the witness run against its declared thresholds.

    Returns the overall status alongside every per-comparison outcome. The
    overall status is the most severe individual outcome, in the fixed order
    PASS < PASS_WITH_ADVISORY < HUMAN_REVIEW_REQUIRED < FAIL, so a single
    required-and-breached comparison cannot be averaged away by six clean ones.
    """
    bands = {t.comparison: t for t in (thresholds or default_thresholds())}
    seen = [o.comparison for o in observations]
    duplicates = sorted({c for c in seen if seen.count(c) > 1})
    if duplicates:
        raise InputValidationError(
            f"Witness reported comparisons more than once: {duplicates}. Two answers "
            "to one comparison is a choice, and the witness does not get to make one."
        )

    outcomes: list[dict[str, Any]] = []
    for observation in sorted(observations, key=lambda o: o.comparison):
        band = bands.get(observation.comparison)
        if band is None:
            raise InputValidationError(
                f"Witness reported {observation.comparison} with no declared threshold. "
                "A comparison classified after its result is known is not classified "
                "by a declared threshold."
            )
        outcomes.append(_classify_one(observation, band))

    missing_required = sorted(
        band.comparison
        for band in bands.values()
        if band.required and band.comparison not in seen
    )
    for name in missing_required:
        outcomes.append(
            {
                "comparison": name,
                "status": S.FAIL,
                "classification": WITNESS_UNAVAILABLE,
                "detail": (
                    "Required witness comparison was not reported. Required evidence "
                    "that could not be produced is missing evidence, not a pass."
                ),
                "observation": None,
                "threshold": bands[name].as_dict(),
            }
        )

    status = _most_severe(o["status"] for o in outcomes)
    advisories = tuple(
        f"{o['comparison']}: {o['classification']} -- {o['detail']}"
        for o in outcomes
        if o["status"] != S.PASS
    )
    return {
        "status": status,
        "role": EXTERNAL_WITNESS_ONLY,
        "may_change_parameter_vector": False,
        "comparisons": outcomes,
        "advisories": list(advisories),
        "declared_thresholds": [bands[c].as_dict() for c in sorted(bands)],
    }


def _classify_one(
    observation: WitnessObservation, band: WitnessThreshold
) -> dict[str, Any]:
    if not observation.available:
        if band.required:
            return {
                "comparison": observation.comparison,
                "status": S.FAIL,
                "classification": WITNESS_UNAVAILABLE,
                "detail": (
                    "Required witness comparison is unavailable. A required witness "
                    "that could not be run is missing evidence and must not be "
                    "downgraded to a pass."
                ),
                "observation": observation.as_dict(),
                "threshold": band.as_dict(),
            }
        return {
            "comparison": observation.comparison,
            "status": S.PASS_WITH_ADVISORY,
            "classification": WITNESS_UNAVAILABLE,
            "detail": (
                "Optional witness comparison unavailable; recorded and the run "
                f"continues. {observation.note}".strip()
            ),
            "observation": observation.as_dict(),
            "threshold": band.as_dict(),
        }

    divergence = abs(float(observation.divergence))
    if divergence >= band.failure_at:
        return {
            "comparison": observation.comparison,
            "status": band.on_failure,
            "classification": "THRESHOLD_BREACH",
            "detail": (
                f"Divergence {divergence} reached the declared failure band "
                f"{band.failure_at} ({band.units}). Classified {band.on_failure} by the "
                "threshold declared before the result was known. The synthetic-domain "
                "parameter vector is not adjusted."
            ),
            "observation": observation.as_dict(),
            "threshold": band.as_dict(),
        }
    if divergence >= band.advisory_at:
        return {
            "comparison": observation.comparison,
            "status": S.PASS_WITH_ADVISORY,
            "classification": "ADVISORY_BAND",
            "detail": (
                f"Divergence {divergence} sits in the declared advisory band "
                f"[{band.advisory_at}, {band.failure_at}) ({band.units}). Recorded; the "
                "run continues and the parameter vector is unchanged."
            ),
            "observation": observation.as_dict(),
            "threshold": band.as_dict(),
        }
    return {
        "comparison": observation.comparison,
        "status": S.PASS,
        "classification": "WITHIN_DECLARED_BAND",
        "detail": f"Divergence {divergence} is below the advisory band {band.advisory_at}.",
        "observation": observation.as_dict(),
        "threshold": band.as_dict(),
    }


#: Severity order for combining per-comparison outcomes. Explicit rather than
#: derived from the status tuple, so re-ordering the status classes for any
#: other reason cannot silently change what "most severe" means.
_SEVERITY: dict[str, int] = {
    S.PASS: 0,
    S.PASS_WITH_ADVISORY: 1,
    S.RETRY_AUTOMATICALLY: 2,
    S.HUMAN_REVIEW_REQUIRED: 3,
    S.FAIL: 4,
}


def _most_severe(statuses) -> str:
    worst = S.PASS
    for status in statuses:
        if _SEVERITY[status] > _SEVERITY[worst]:
            worst = status
    return worst
