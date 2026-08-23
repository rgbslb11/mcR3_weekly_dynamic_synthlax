"""The immutable parameter-recommendation artifact.

This is what a human approves. Everything the supervisor did upstream exists to
produce it, and everything downstream exists because it was approved, so it has
to be a complete and self-contained account: what is recommended, why, on what
evidence, against which inputs, under which code.

Two design choices carry most of the weight.

**A recommendation that cannot cite a measurement does not carry a number.** An
unidentified parameter, a non-binding constraint and a circular one all
recommend ``None``. It would be easy -- and much friendlier to read -- to put
the tie-break value in the ``recommended_value`` field with a note beside it
saying it is not measured. Nobody reads the note. :class:`ParameterRecommendation`
refuses the combination outright, so the artifact cannot be skimmed into a
number that was never measured.

**Its digest covers the evidence, not just the values.** ``recommendation_sha256``
is taken over the whole canonical package: recommended values, epistemic
dispositions, objective, validation and holdout evidence, sensitivity, boundary
and identification status, the witness result, and the input, dataset, split,
oracle, candidate-universe and code digests. Approval binds to that digest in
:mod:`.approval`. So an approval is an approval of *this* number, held with
*this* confidence, produced *this* way from *these* inputs -- and changing any of
them produces a different digest and an approval that no longer applies.

Mixed dispositions are the normal case
---------------------------------------

The R2 evidence settles that the final vector will not be uniformly fitted. Some
parameters are circular, one is unidentified from synthetic evidence, one is
missing outright, and one or two may carry a Wave-1 fit result. Every entry
therefore carries a :mod:`.dispositions` value alongside its number, the package
requires no particular disposition of anybody, and
:meth:`RecommendationPackage.human_disposition_requests` turns "production reads
this parameter and this run produced no value for it" into an explicit question
asked at the single approval gate. The alternative -- refusing to build a
recommendation until every parameter is fitted -- would mean this run could never
reach its human at all, which is not caution, it is a deadlock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import GovernanceBlock, InputValidationError
from . import dispositions as D
from .digests import digest_mapping
from .evidence import (
    BLOCKED,
    CARRY_FORWARD_ELIGIBILITY,
    CIRCULAR_NOT_IDENTIFIABLE,
    ELIGIBILITY_CLASSES,
    FIT_ALLOWED,
    GOVERNED_PARAMETERS,
    MISSING,
)
from .search import (
    IDENTIFIED,
    PARAMETER_UNIDENTIFIED,
    UNIDENTIFIED_NONBINDING,
)

__all__ = [
    "HumanDispositionRequest",
    "NON_MEASURING_IDENTIFICATION_STATUSES",
    "ParameterRecommendation",
    "RecommendationPackage",
    "RunBindings",
]


@dataclass(frozen=True)
class HumanDispositionRequest:
    """One question the recommendation puts to the approver.

    Raised wherever production reads a parameter and this run produced no value
    for it. The request carries the disposition that produced the hole and what
    production does about it, so the approver chooses with the reason in front of
    them rather than filling in a blank.
    """

    parameter: str
    disposition: str
    production_semantics: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "disposition": self.disposition,
            "production_semantics": self.production_semantics,
            "reason": self.reason,
        }

#: Identification outcomes under which no number may be recommended. Each is a
#: statement that the objective could not distinguish a value, and a
#: recommendation carrying a number would contradict it.
NON_MEASURING_IDENTIFICATION_STATUSES: tuple[str, ...] = (
    PARAMETER_UNIDENTIFIED,
    UNIDENTIFIED_NONBINDING,
)

#: Eligibility classes that likewise cannot produce a fitted value.
_NON_FITTING_ELIGIBILITY: tuple[str, ...] = (
    CIRCULAR_NOT_IDENTIFIABLE,
    MISSING,
    BLOCKED,
)


@dataclass(frozen=True)
class RunBindings:
    """Everything a recommendation is tied to, as digests.

    Re-derived at approval time and compared. These five plus the code and input
    digests are what "changed inputs", "changed code", "changed dataset" and
    "changed scoring oracle" mean concretely, and having them in one frozen
    object is what lets the approval gate check all of them rather than
    whichever ones a call site remembered.
    """

    evidence_manifest_digest: str
    dataset_sha256: str
    split_sha256: str
    experiment_config_sha256: str
    candidate_universe_digest: str
    scoring_oracle_digest: str
    input_manifest_digest: str
    code_tree_digest: str
    holdout_seal_digest: str

    def __post_init__(self) -> None:
        blank = sorted(name for name, value in self.as_dict().items() if not str(value).strip())
        if blank:
            raise InputValidationError(
                f"Run bindings are empty for: {blank}. An empty binding compares equal "
                "to the next empty binding and would make the approval check vacuous."
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "evidence_manifest_digest": self.evidence_manifest_digest,
            "dataset_sha256": self.dataset_sha256,
            "split_sha256": self.split_sha256,
            "experiment_config_sha256": self.experiment_config_sha256,
            "candidate_universe_digest": self.candidate_universe_digest,
            "scoring_oracle_digest": self.scoring_oracle_digest,
            "input_manifest_digest": self.input_manifest_digest,
            "code_tree_digest": self.code_tree_digest,
            "holdout_seal_digest": self.holdout_seal_digest,
        }

    def drift_against(self, observed: "RunBindings") -> dict[str, dict[str, str]]:
        """Every binding that moved, with both values."""
        mine, theirs = self.as_dict(), observed.as_dict()
        return {
            name: {"approved": mine[name], "observed": theirs[name]}
            for name in mine
            if mine[name] != theirs[name]
        }


@dataclass(frozen=True)
class ParameterRecommendation:
    """One parameter's recommendation and the evidence behind it."""

    parameter: str
    eligibility: str
    identification_status: str
    prior_value: Any
    current_value: Any
    recommended_value: Any
    boundary_status: str
    #: The epistemic class of the recommendation, from :mod:`.dispositions`.
    #: Distinct from ``eligibility``: eligibility is what the evidence permitted,
    #: disposition is what actually came out of the stage that used it.
    disposition: str = D.UNIDENTIFIED
    disposition_reason: str = ""
    objective_evidence: dict[str, Any] = field(default_factory=dict)
    validation_evidence: dict[str, Any] = field(default_factory=dict)
    holdout_evidence: dict[str, Any] = field(default_factory=dict)
    sensitivity: dict[str, Any] = field(default_factory=dict)
    synthetic_domain_evidence: dict[str, Any] = field(default_factory=dict)
    real_world_witness: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""

    def __post_init__(self) -> None:
        if self.parameter not in GOVERNED_PARAMETERS:
            raise InputValidationError(
                f"Recommendation names unknown parameter {self.parameter!r}."
            )
        if self.eligibility not in ELIGIBILITY_CLASSES:
            raise InputValidationError(
                f"Recommendation for {self.parameter} carries unknown eligibility "
                f"{self.eligibility!r}."
            )
        if not self.rationale.strip():
            raise InputValidationError(
                f"Recommendation for {self.parameter} carries no rationale."
            )
        if (
            self.identification_status in NON_MEASURING_IDENTIFICATION_STATUSES
            and self.recommended_value is not None
        ):
            raise GovernanceBlock(
                f"{self.parameter} is {self.identification_status} yet recommends "
                f"{self.recommended_value!r}. A value the objective could not "
                "distinguish must not be recommended as though it had been measured; "
                "the recommendation is the absence of a value."
            )
        if self.eligibility in _NON_FITTING_ELIGIBILITY and self.recommended_value is not None:
            raise GovernanceBlock(
                f"{self.parameter} is {self.eligibility} yet recommends "
                f"{self.recommended_value!r}. Nothing in this run was entitled to fit it."
            )
        if self.eligibility in CARRY_FORWARD_ELIGIBILITY:
            if self.recommended_value != self.current_value:
                raise GovernanceBlock(
                    f"{self.parameter} is {self.eligibility}, which carries the governed "
                    f"value {self.current_value!r} forward, but the recommendation is "
                    f"{self.recommended_value!r}. A fixed value that changed was not fixed."
                )
        if (
            self.eligibility == FIT_ALLOWED
            and self.identification_status == IDENTIFIED
            and self.recommended_value is None
        ):
            raise InputValidationError(
                f"{self.parameter} is {FIT_ALLOWED} and {IDENTIFIED} but recommends no "
                "value. An identified parameter has one."
            )
        D.require_known_disposition(self.parameter, self.disposition)
        D.require_value_consistent(
            self.parameter, self.disposition, self.recommended_value
        )
        if self.disposition == D.FIT_RESULT and self.eligibility != FIT_ALLOWED:
            raise GovernanceBlock(
                f"{self.parameter} reports disposition {D.FIT_RESULT} while its "
                f"eligibility is {self.eligibility}. A fit result requires permission "
                "to have fitted, so the two cannot disagree."
            )
        if (
            self.disposition in D.REQUIRES_HUMAN_DISPOSITION
            and not self.disposition_reason.strip()
        ):
            raise InputValidationError(
                f"{self.parameter} is {self.disposition}, which puts a question to a "
                "human, and records no reason for asking it."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "parameter": self.parameter,
            "eligibility": self.eligibility,
            "identification_status": self.identification_status,
            "disposition": self.disposition,
            "disposition_reason": self.disposition_reason,
            "boundary_status": self.boundary_status,
            "prior_value": self.prior_value,
            "current_value": self.current_value,
            "recommended_value": self.recommended_value,
            "objective_evidence": dict(self.objective_evidence),
            "validation_evidence": dict(self.validation_evidence),
            "holdout_evidence": dict(self.holdout_evidence),
            "sensitivity": dict(self.sensitivity),
            "synthetic_domain_evidence": dict(self.synthetic_domain_evidence),
            "real_world_witness": dict(self.real_world_witness),
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class RecommendationPackage:
    """The whole artifact, and the thing approval binds to.

    ``generated_at`` is part of the digested payload. Two identical
    recommendations generated at different times are therefore different
    artifacts with different digests, which is correct: an approval names one
    act of recommending, not a class of them.
    """

    run_id: str
    generated_at: str
    bindings: RunBindings
    parameters: tuple[ParameterRecommendation, ...]
    real_world_witness: dict[str, Any] = field(default_factory=dict)
    point_scale_resolution: dict[str, Any] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        named = [p.parameter for p in self.parameters]
        duplicates = sorted({n for n in named if named.count(n) > 1})
        if duplicates:
            raise InputValidationError(
                f"Recommendation package names parameters twice: {duplicates}."
            )
        missing = sorted(set(GOVERNED_PARAMETERS) - set(named))
        if missing:
            raise GovernanceBlock(
                f"Recommendation package omits governed parameters: {missing}. A "
                "parameter left out of the artifact is a parameter nobody approved, "
                "and the run would proceed as though it had been."
            )
        if self.real_world_witness.get("may_change_parameter_vector", False):
            raise GovernanceBlock(
                "Recommendation package records a witness result claiming authority to "
                "change the parameter vector. Real football is EXTERNAL_WITNESS_ONLY."
            )

    @property
    def recommendation_sha256(self) -> str:
        """The digest approval binds to."""
        return digest_mapping(self.as_dict())

    def parameter(self, name: str) -> ParameterRecommendation:
        for entry in self.parameters:
            if entry.parameter == name:
                return entry
        raise InputValidationError(f"{name!r} is not in this recommendation package.")

    def disposition_vector(self) -> dict[str, str]:
        """Every parameter's epistemic class, in canonical parameter order.

        Returned alongside the value vector rather than folded into it. An
        approver approves two things -- the number and the confidence -- and a
        structure that could express only one would make the second unapprovable.
        """
        return {name: self.parameter(name).disposition for name in GOVERNED_PARAMETERS}

    def human_disposition_requests(self) -> tuple[HumanDispositionRequest, ...]:
        """The questions this package puts to the approver.

        One per governed parameter that production reads and this run has no
        value for. Parameters whose semantics are
        :data:`~.dispositions.VALUE_REQUIRED_AT_USE_SITE` are included too: the
        approver may legitimately answer "leave it absent and fail closed", and
        they cannot answer a question nobody asked.
        """
        requests: list[HumanDispositionRequest] = []
        for name in GOVERNED_PARAMETERS:
            entry = self.parameter(name)
            if entry.recommended_value is not None:
                continue
            requests.append(
                HumanDispositionRequest(
                    parameter=name,
                    disposition=entry.disposition,
                    production_semantics=D.PRODUCTION_VALUE_SEMANTICS[name],
                    reason=(
                        entry.disposition_reason
                        or f"{name} is {entry.disposition} and carries no value."
                    ),
                )
            )
        return tuple(requests)

    def recommended_vector(self) -> dict[str, Any]:
        """The recommended values, including the explicit ``None`` entries.

        ``None`` is kept rather than filtered out. A vector that silently
        dropped its unidentified parameters would read as complete, and the
        first consumer to iterate it would conclude every parameter had a value.
        """
        return {p.parameter: p.recommended_value for p in sorted(
            self.parameters, key=lambda p: p.parameter
        )}

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact": "V3_PARAMETER_RECOMMENDATION",
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "bindings": self.bindings.as_dict(),
            "parameters": [
                p.as_dict() for p in sorted(self.parameters, key=lambda p: p.parameter)
            ],
            "recommended_vector": self.recommended_vector(),
            "disposition_vector": self.disposition_vector(),
            "human_disposition_requests": [
                r.as_dict() for r in self.human_disposition_requests()
            ],
            "real_world_witness": dict(self.real_world_witness),
            "point_scale_resolution": dict(self.point_scale_resolution),
            "notes": list(self.notes),
            "writes_canonical_config": False,
        }

    def as_artifact(self) -> dict[str, Any]:
        """The on-disk form, which carries its own digest alongside its content."""
        payload = self.as_dict()
        return {**payload, "recommendation_sha256": self.recommendation_sha256}
