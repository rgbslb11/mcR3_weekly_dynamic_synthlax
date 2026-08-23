"""The single human gate, and what an approval is bound to.

There is exactly one normal stop in this run, and this is it. Everything before
it is deterministic and everything after it is deterministic; the judgement
happens here, once, and the whole point of the module is that the judgement
cannot be reused for a different question than the one it answered.

An approval covers two things: the value and the confidence
------------------------------------------------------------

The R2 evidence guarantees a mixed vector -- some parameters fitted, some
circular, one unidentified from synthetic evidence, one missing outright. So an
approval that recorded only numbers would be approving half of what the
recommendation says. ``approve`` therefore binds an *approved vector* and an
*approved disposition vector*, both inside the approval digest, and every
question the recommendation raises under
:meth:`~.recommendation.RecommendationPackage.human_disposition_requests` must be
answered before the approval is granted. Answering may mean supplying a value,
and it may mean approving the absence -- ``fcs_point_adapter`` left
:data:`~.dispositions.MISSING_FAIL_CLOSED` is a legitimate answer, and it is
recorded as an answer rather than as an oversight.

Approving an absence is not the same as authorising execution.
:func:`require_approval_for_execution` re-derives the execution obstacles from
the approved vector, so a parameter production reads on every path and still has
no value stops the tiers even though its epistemic status was approved. That is
the fail-closed half of the doctrine, and it lives here rather than in the tier
gates because the approved vector is the last place the two facts are together.

An approval names a digest, not a run
--------------------------------------

``APPROVE_V3_CALIBRATION_R1`` on its own approves nothing. The action must
arrive with the recommendation's SHA-256, and that SHA-256 must be the digest of
the package the run is currently holding. Because
:attr:`RecommendationPackage.recommendation_sha256` covers the recommended
values, every piece of evidence behind them, and the input, dataset, split,
oracle, candidate-universe and code digests, matching it means the approver and
the supervisor are looking at the same artifact in the same world.

Five refusals fall out of that, and they are listed in the lane instruction
because each is a real way an approval gets reused: the wrong SHA, a stale
recommendation that a newer one has superseded, changed inputs, changed code,
and a changed dataset or scoring oracle. Every one is a digest comparison here,
performed against values re-derived at approval time rather than read back out
of the artifact that is being checked.

Nothing in this module can construct an approval on its own behalf. There is no
default approver, no "auto" action, and no path that reaches
:class:`ApprovalRecord` without an explicit caller supplying an action, a SHA
and an identity. That is deliberate: the supervisor is autonomous everywhere
else precisely so this one step can be the thing a person actually does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dcfield
from typing import Any

from typing import Mapping

from ..errors import GovernanceBlock, InputValidationError
from . import dispositions as D
from . import states as S
from .digests import digest_mapping
from .recommendation import RecommendationPackage, RunBindings

__all__ = [
    "APPROVAL_ACTION",
    "ApprovalRecord",
    "approve",
    "require_approval_for_execution",
    "resolve_dispositions",
]

#: The explicit action this lane recognises.
APPROVAL_ACTION = "APPROVE_V3_CALIBRATION_R1"

#: Shape of a recommendation digest. Checked before comparison so a truncated or
#: mistyped SHA is refused as malformed rather than reported as a mismatch --
#: the operator needs to know which of the two happened.
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class ApprovalRecord:
    """A granted approval, bound to one recommendation digest.

    Frozen and digested. The record is itself evidence -- the execution tiers
    refuse to start without one -- so it must not be editable after the fact any
    more than the recommendation it approves.
    """

    run_id: str
    action: str
    recommendation_sha256: str
    approver: str
    approved_at: str
    bindings: RunBindings
    #: The values production will run with, after the human answered every
    #: question the recommendation raised.
    approved_vector: dict[str, Any] = dcfield(default_factory=dict)
    #: The epistemic status approved for each of those values. Approving a
    #: number without approving how confidently it is held would approve half a
    #: claim.
    approved_dispositions: dict[str, str] = dcfield(default_factory=dict)
    #: What the human decided about each question raised, kept verbatim.
    human_answers: dict[str, Any] = dcfield(default_factory=dict)
    note: str = ""

    @property
    def approval_digest(self) -> str:
        return digest_mapping(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact": "V3_PARAMETER_APPROVAL",
            "run_id": self.run_id,
            "action": self.action,
            "recommendation_sha256": self.recommendation_sha256,
            "approver": self.approver,
            "approved_at": self.approved_at,
            "bindings": self.bindings.as_dict(),
            "approved_vector": dict(sorted(self.approved_vector.items())),
            "approved_dispositions": dict(sorted(self.approved_dispositions.items())),
            "human_answers": dict(sorted(self.human_answers.items())),
            "note": self.note,
            "writes_canonical_config": False,
        }

    def as_artifact(self) -> dict[str, Any]:
        payload = self.as_dict()
        return {**payload, "approval_digest": self.approval_digest}


def resolve_dispositions(
    package: RecommendationPackage,
    answers: Mapping[str, Mapping[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    """Fold the human answers into the recommended vector, or refuse.

    Returns the approved value vector, the approved disposition vector, and the
    answers as given. Four things are refused rather than absorbed:

    * an answer for a parameter the recommendation did not ask about -- that
      would silently overwrite a measured value at the approval gate, which is
      the one place nobody is watching for a substitution;
    * an unrecognised epistemic status;
    * a value under a status that cannot carry one, or a missing value under a
      status that must;
    * any question left unanswered.

    The last is the important one. A recommendation that raised a question and an
    approval that ignored it would leave the run to discover the hole in the
    execution tiers, which is exactly where the doctrine says it must not stop.
    """
    supplied = {str(k): dict(v) for k, v in dict(answers or {}).items()}
    requests = {r.parameter: r for r in package.human_disposition_requests()}

    unrequested = sorted(set(supplied) - set(requests))
    if unrequested:
        raise GovernanceBlock(
            f"The approval answers for {unrequested}, which the recommendation did not "
            "ask about. Those parameters already carry a value produced by this run; "
            "the approval gate approves them or refuses them, and does not replace them."
        )

    vector = dict(package.recommended_vector())
    statuses = dict(package.disposition_vector())
    for name, answer in sorted(supplied.items()):
        status = str(answer.get("status", "")).strip()
        if not status:
            raise GovernanceBlock(
                f"The approval supplies a value for {name} without an epistemic status. "
                "An approved number whose standing nobody stated is an unapproved claim."
            )
        D.require_known_disposition(name, status)
        value = answer.get("value")
        D.require_value_consistent(name, status, value)
        vector[name] = value
        statuses[name] = status

    unanswered = sorted(set(requests) - set(supplied))
    if unanswered:
        detail = "; ".join(
            f"{name}: {requests[name].disposition} ({requests[name].production_semantics})"
            for name in unanswered
        )
        raise GovernanceBlock(
            "Approval refused: the recommendation asks for a human disposition on "
            f"{unanswered} and the approval answers none of them. {detail}. This is the "
            "one gate in the run where those questions can be answered; leaving them "
            "open would push the decision into the execution tiers, which have no "
            "human to ask."
        )
    return vector, statuses, supplied


def approve(
    package: RecommendationPackage,
    *,
    action: str,
    recommendation_sha256: str,
    approver: str,
    approved_at: str,
    current_state: str,
    active_recommendation_sha256: str,
    observed_bindings: RunBindings,
    dispositions: Mapping[str, Mapping[str, Any]] | None = None,
    note: str = "",
) -> ApprovalRecord:
    """Grant approval, or refuse and say which binding failed.

    ``active_recommendation_sha256`` is what the run currently holds, and
    ``package`` is the artifact being approved. They are separate arguments on
    purpose: an approval submitted against a recommendation that a later
    regeneration has superseded is *stale*, and staleness is invisible if the
    only thing checked is that the submitted SHA matches the artifact submitted
    alongside it.
    """
    if action != APPROVAL_ACTION:
        raise GovernanceBlock(
            f"Unknown approval action {action!r}. This lane recognises exactly "
            f"{APPROVAL_ACTION}."
        )
    if not approver.strip():
        raise GovernanceBlock(
            "Approval requires a named approver. The parameter gate is the one step in "
            "this run that a person performs, and an unattributed approval records that "
            "nobody did."
        )
    if not approved_at.strip():
        raise InputValidationError("Approval requires an approval timestamp.")
    if current_state != S.AWAITING_HUMAN_APPROVAL:
        raise GovernanceBlock(
            f"Approval refused from state {current_state}. Parameters may be approved "
            f"only from {S.AWAITING_HUMAN_APPROVAL}; a run that is not waiting on a "
            "human has either not produced a recommendation yet or has already been "
            "approved."
        )

    submitted = recommendation_sha256.strip().lower()
    if not _SHA256.match(submitted):
        raise InputValidationError(
            f"Recommendation SHA {recommendation_sha256!r} is not a 64-character "
            "hexadecimal SHA-256."
        )

    actual = package.recommendation_sha256
    if submitted != actual:
        raise GovernanceBlock(
            "Approval refused: recommendation SHA mismatch. The approval names "
            f"{submitted}, and the recommendation artifact digests to {actual}. An "
            "approval binds to the exact artifact it was granted against."
        )
    if actual != active_recommendation_sha256:
        raise GovernanceBlock(
            "Approval refused: stale recommendation. The run currently holds "
            f"{active_recommendation_sha256}, and this approval is against {actual}. "
            "A recommendation that has been superseded describes evidence the run no "
            "longer stands on."
        )

    drift = package.bindings.drift_against(observed_bindings)
    if drift:
        raise GovernanceBlock(
            "Approval refused: the world moved under the recommendation. "
            f"{sorted(drift)} no longer match what the recommendation was produced "
            f"against. Drift: {drift}"
        )

    vector, statuses, answers = resolve_dispositions(package, dispositions)
    return ApprovalRecord(
        run_id=package.run_id,
        action=action,
        recommendation_sha256=actual,
        approver=approver,
        approved_at=approved_at,
        bindings=package.bindings,
        approved_vector=vector,
        approved_dispositions=statuses,
        human_answers=answers,
        note=note,
    )


def require_approval_for_execution(
    approval: ApprovalRecord | None,
    *,
    recommendation_sha256: str,
    observed_bindings: RunBindings,
) -> ApprovalRecord:
    """Refuse to enter the execution tiers without a still-valid approval.

    Re-checked on entry rather than trusted from the state name alone, because a
    resumed run reads its state off disk and the disk is not the authority on
    whether the code and inputs are still the ones that were approved.
    """
    if approval is None:
        raise GovernanceBlock(
            "Execution refused: no parameter approval is recorded for this run. The "
            "500-path development tier is downstream of the human gate, not upstream "
            "of it."
        )
    if approval.recommendation_sha256 != recommendation_sha256:
        raise GovernanceBlock(
            "Execution refused: the recorded approval is for recommendation "
            f"{approval.recommendation_sha256}, and the run holds "
            f"{recommendation_sha256}."
        )
    drift = approval.bindings.drift_against(observed_bindings)
    if drift:
        raise GovernanceBlock(
            f"Execution refused: {sorted(drift)} changed after approval. Drift: {drift}"
        )
    obstacles = D.execution_obstacles(
        approval.approved_vector, approval.approved_dispositions
    )
    if obstacles:
        raise GovernanceBlock(
            "Execution refused: the approved vector has no value where production "
            "reads one on every path. "
            + " ".join(obstacles)
            + " The epistemic status was approved; that records what is known, and it "
            "does not manufacture the number production needs."
        )
    return approval
