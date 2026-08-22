"""The single human gate, and what an approval is bound to.

There is exactly one normal stop in this run, and this is it. Everything before
it is deterministic and everything after it is deterministic; the judgement
happens here, once, and the whole point of the module is that the judgement
cannot be reused for a different question than the one it answered.

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
from dataclasses import dataclass
from typing import Any

from ..errors import GovernanceBlock, InputValidationError
from . import states as S
from .digests import digest_mapping
from .recommendation import RecommendationPackage, RunBindings

__all__ = [
    "APPROVAL_ACTION",
    "ApprovalRecord",
    "approve",
    "require_approval_for_execution",
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
            "note": self.note,
            "writes_canonical_config": False,
        }

    def as_artifact(self) -> dict[str, Any]:
        payload = self.as_dict()
        return {**payload, "approval_digest": self.approval_digest}


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

    return ApprovalRecord(
        run_id=package.run_id,
        action=action,
        recommendation_sha256=actual,
        approver=approver,
        approved_at=approved_at,
        bindings=package.bindings,
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
    return approval
