"""The V3 model-run state machine, and the status classes stages report in.

The supervisor exists so that the remaining V3 model run can be driven from
frozen evidence to final freeze without a human deciding, at each step, whether
the previous step earned the next one. That is only safe if "which step are we
on" is a value rather than a belief, so the machine is explicit here: a fixed
set of states, a fixed set of legal edges, and no way to reach a state except
along an edge that :data:`LEGAL_TRANSITIONS` names.

Three properties are load-bearing and are enforced rather than documented.

**The spine is linear and every stage is paired.** Each ``*_REQUIRED`` state has
exactly one successor, and it is the ``*_COMPLETE`` / ``*_PASS`` state for the
same stage. A stage cannot be skipped by writing a later state, because the only
edge into a later state departs from the completion of the one before it. This
is what makes "DEV failure blocks ANALYSIS" a structural fact rather than a
check somebody remembered to write.

**Halting is always available; un-halting never is.** Any live state may fail to
:data:`HALTED_FAILED` or stop at :data:`HALTED_FOR_HUMAN_REVIEW`, because an
unrecoverable error is not a stage-specific event. Neither halt state has an
outgoing edge. A halted run is re-entered by a human deciding what to do with
it, which in this repository means a new run bound to new evidence -- not by the
supervisor deciding the failure has aged out.

**The approval gate is an edge, not a flag.** ``AWAITING_HUMAN_APPROVAL ->
PARAMETERS_APPROVED`` is the only way into the execution tiers, and the only
caller that may traverse it is the approval module, which re-derives the
recommendation digest first. Nothing downstream re-checks approval, because
nothing downstream can be reached without having traversed that edge.

Advisories are deliberately *not* modelled as states. A stage that passes with
an advisory is in the same state as a stage that passes clean; the advisory
travels on the stage result. Making an advisory a state would make it a stop,
and the lane instruction is explicit that advisories must not halt a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..errors import GovernanceBlock

__all__ = [
    "ADVISORY_STATUSES",
    "CONTINUING_STATUSES",
    "FAIL",
    "HALTED_FAILED",
    "HALTED_FOR_HUMAN_REVIEW",
    "HALT_STATES",
    "HUMAN_REVIEW_REQUIRED",
    "LEGAL_TRANSITIONS",
    "PASS",
    "PASS_WITH_ADVISORY",
    "RETRY_AUTOMATICALLY",
    "SPINE",
    "STATES",
    "STATUS_CLASSES",
    "StageResult",
    "TERMINAL_STATES",
    "is_legal_transition",
    "require_legal_transition",
    "state_index",
    "transition_summary",
]


# --- status classes ----------------------------------------------------------
#
# What a stage reports, distinct from what state the run is in. The split
# matters: PASS and PASS_WITH_ADVISORY advance to the same state, and the
# difference is preserved on the result so an auditor can see it, not so the
# supervisor can stop on it.

#: The stage did what it was asked and raised nothing worth recording.
PASS = "PASS"

#: The stage succeeded and recorded something a human should read. It advances.
#: An advisory halts only where run policy has named that advisory required,
#: which is a policy decision made in :mod:`.policy`, never a decision made
#: here.
PASS_WITH_ADVISORY = "PASS_WITH_ADVISORY"

#: A narrowly recognised, self-correcting execution failure. The supervisor may
#: retry the stage once under :mod:`.retry`; it is not a result.
RETRY_AUTOMATICALLY = "RETRY_AUTOMATICALLY"

#: The stage reached a decision it is not entitled to make. Stops the run in
#: :data:`HALTED_FOR_HUMAN_REVIEW` with the question recorded.
HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"

#: Genuine evidence or model failure. Stops the run in :data:`HALTED_FAILED`.
FAIL = "FAIL"

STATUS_CLASSES: tuple[str, ...] = (
    PASS,
    PASS_WITH_ADVISORY,
    RETRY_AUTOMATICALLY,
    HUMAN_REVIEW_REQUIRED,
    FAIL,
)

#: The two statuses that advance the machine.
CONTINUING_STATUSES: tuple[str, ...] = (PASS, PASS_WITH_ADVISORY)

#: The status that carries advisories. Named so callers testing "did this record
#: an advisory" do not have to compare against a string literal.
ADVISORY_STATUSES: tuple[str, ...] = (PASS_WITH_ADVISORY,)


@dataclass(frozen=True)
class StageResult:
    """One stage's outcome, as the supervisor records it.

    Frozen because a stage result is the evidence that a state transition was
    earned. A mutable one could be edited after the transition it authorised,
    which would make the run directory a narrative rather than a record.

    ``advisories`` are notes that do not stop the run. ``detail`` carries
    whatever the stage measured -- parameter values, digests, gate outcomes --
    and is what lands in ``stage_results/`` on disk.
    """

    stage: str
    status: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    advisories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.status not in STATUS_CLASSES:
            raise GovernanceBlock(
                f"Stage {self.stage} reported unknown status {self.status!r}; "
                f"expected one of {list(STATUS_CLASSES)}."
            )
        if self.status == PASS and self.advisories:
            # PASS carrying advisories is PASS_WITH_ADVISORY that forgot to say
            # so. Refusing here keeps the two statuses meaning what they say, so
            # a reader can trust that a PASS row has nothing to read.
            raise GovernanceBlock(
                f"Stage {self.stage} reported {PASS} while carrying advisories "
                f"{list(self.advisories)}; report {PASS_WITH_ADVISORY} instead."
            )
        if self.status == PASS_WITH_ADVISORY and not self.advisories:
            raise GovernanceBlock(
                f"Stage {self.stage} reported {PASS_WITH_ADVISORY} with no advisory text."
            )

    @property
    def continues(self) -> bool:
        """Whether this result advances the machine."""
        return self.status in CONTINUING_STATUSES

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "status": self.status,
            "summary": self.summary,
            "detail": dict(self.detail),
            "advisories": list(self.advisories),
        }


# --- states ------------------------------------------------------------------

INITIALIZED = "INITIALIZED"

SYNTHETIC_EVIDENCE_REQUIRED = "SYNTHETIC_EVIDENCE_REQUIRED"
SYNTHETIC_EVIDENCE_ACCEPTED = "SYNTHETIC_EVIDENCE_ACCEPTED"

CALIBRATION_DATASET_REQUIRED = "CALIBRATION_DATASET_REQUIRED"
CALIBRATION_DATASET_READY = "CALIBRATION_DATASET_READY"

PREFLIGHT_REQUIRED = "PREFLIGHT_REQUIRED"
PREFLIGHT_PASS = "PREFLIGHT_PASS"

POINT_SCALE_DECISION_REQUIRED = "POINT_SCALE_DECISION_REQUIRED"
POINT_SCALE_READY_OR_FIXED = "POINT_SCALE_READY_OR_FIXED"

COARSE_SEARCH_REQUIRED = "COARSE_SEARCH_REQUIRED"
COARSE_SEARCH_COMPLETE = "COARSE_SEARCH_COMPLETE"

REFINEMENT_REQUIRED = "REFINEMENT_REQUIRED"
REFINEMENT_COMPLETE = "REFINEMENT_COMPLETE"

VALIDATION_REQUIRED = "VALIDATION_REQUIRED"
VALIDATION_COMPLETE = "VALIDATION_COMPLETE"

HOLDOUT_LOCKED = "HOLDOUT_LOCKED"
HOLDOUT_RELEASED = "HOLDOUT_RELEASED"
HOLDOUT_COMPLETE = "HOLDOUT_COMPLETE"

GAME_SD_REQUIRED = "GAME_SD_REQUIRED"
GAME_SD_COMPLETE = "GAME_SD_COMPLETE"

FCS_ADAPTER_REQUIRED = "FCS_ADAPTER_REQUIRED"
FCS_ADAPTER_COMPLETE_OR_EXPLICITLY_UNIDENTIFIED = (
    "FCS_ADAPTER_COMPLETE_OR_EXPLICITLY_UNIDENTIFIED"
)

REAL_WORLD_WITNESS_REQUIRED = "REAL_WORLD_WITNESS_REQUIRED"
REAL_WORLD_WITNESS_COMPLETE = "REAL_WORLD_WITNESS_COMPLETE"

PARAMETER_RECOMMENDATION_READY = "PARAMETER_RECOMMENDATION_READY"

AWAITING_HUMAN_APPROVAL = "AWAITING_HUMAN_APPROVAL"
PARAMETERS_APPROVED = "PARAMETERS_APPROVED"

DEV_500_REQUIRED = "DEV_500_REQUIRED"
DEV_500_PASS = "DEV_500_PASS"

ANALYSIS_2000_REQUIRED = "ANALYSIS_2000_REQUIRED"
ANALYSIS_2000_PASS = "ANALYSIS_2000_PASS"

PUBLISH_10000_REQUIRED = "PUBLISH_10000_REQUIRED"
PUBLISH_10000_PASS = "PUBLISH_10000_PASS"

FINAL_FREEZE_REQUIRED = "FINAL_FREEZE_REQUIRED"

COMPLETE = "COMPLETE"

#: Unrecoverable execution error, or a genuine evidence/model failure.
HALTED_FAILED = "HALTED_FAILED"

#: A decision the supervisor is not entitled to make. Distinct from
#: :data:`HALTED_FAILED` because nothing is necessarily wrong with the run -- it
#: has reached a question, and answering it is a human act.
HALTED_FOR_HUMAN_REVIEW = "HALTED_FOR_HUMAN_REVIEW"

#: The ordered linear spine, from initialization to freeze. Order is meaningful:
#: :func:`state_index` reads it to answer "is this state before that one", which
#: is how holdout access is refused during candidate generation.
SPINE: tuple[str, ...] = (
    INITIALIZED,
    SYNTHETIC_EVIDENCE_REQUIRED,
    SYNTHETIC_EVIDENCE_ACCEPTED,
    CALIBRATION_DATASET_REQUIRED,
    CALIBRATION_DATASET_READY,
    PREFLIGHT_REQUIRED,
    PREFLIGHT_PASS,
    POINT_SCALE_DECISION_REQUIRED,
    POINT_SCALE_READY_OR_FIXED,
    COARSE_SEARCH_REQUIRED,
    COARSE_SEARCH_COMPLETE,
    REFINEMENT_REQUIRED,
    REFINEMENT_COMPLETE,
    VALIDATION_REQUIRED,
    VALIDATION_COMPLETE,
    HOLDOUT_LOCKED,
    HOLDOUT_RELEASED,
    HOLDOUT_COMPLETE,
    GAME_SD_REQUIRED,
    GAME_SD_COMPLETE,
    FCS_ADAPTER_REQUIRED,
    FCS_ADAPTER_COMPLETE_OR_EXPLICITLY_UNIDENTIFIED,
    REAL_WORLD_WITNESS_REQUIRED,
    REAL_WORLD_WITNESS_COMPLETE,
    PARAMETER_RECOMMENDATION_READY,
    AWAITING_HUMAN_APPROVAL,
    PARAMETERS_APPROVED,
    DEV_500_REQUIRED,
    DEV_500_PASS,
    ANALYSIS_2000_REQUIRED,
    ANALYSIS_2000_PASS,
    PUBLISH_10000_REQUIRED,
    PUBLISH_10000_PASS,
    FINAL_FREEZE_REQUIRED,
    COMPLETE,
)

#: The two ways a run stops without completing.
HALT_STATES: tuple[str, ...] = (HALTED_FAILED, HALTED_FOR_HUMAN_REVIEW)

#: Every state the machine recognises.
STATES: tuple[str, ...] = SPINE + HALT_STATES

#: States with no outgoing edge.
TERMINAL_STATES: tuple[str, ...] = (COMPLETE,) + HALT_STATES

_SPINE_INDEX: dict[str, int] = {name: i for i, name in enumerate(SPINE)}


def _build_transitions() -> dict[str, frozenset[str]]:
    """Derive the edge set from the spine rather than restating it.

    Written once, from the ordering above, so the machine cannot drift from its
    own documentation: adding a state to :data:`SPINE` adds exactly the two
    edges that belong to it, and nothing else becomes reachable.
    """
    edges: dict[str, set[str]] = {name: set() for name in STATES}
    for current, following in zip(SPINE, SPINE[1:]):
        edges[current].add(following)
    for name in SPINE:
        if name in TERMINAL_STATES:
            continue
        # An unrecoverable error is not stage-specific, and neither is reaching
        # a question the supervisor may not answer.
        edges[name].update(HALT_STATES)
    return {name: frozenset(targets) for name, targets in edges.items()}


#: The complete edge set. A transition absent here is illegal, full stop.
LEGAL_TRANSITIONS: dict[str, frozenset[str]] = _build_transitions()


def state_index(state: str) -> int:
    """Position of ``state`` on the spine.

    Halt states are not on the spine and have no position; asking for one is a
    programming error rather than a governance refusal, so it raises
    :class:`ValueError`.
    """
    try:
        return _SPINE_INDEX[state]
    except KeyError:
        raise ValueError(f"{state!r} is not a spine state") from None


def is_legal_transition(current: str, target: str) -> bool:
    """Whether ``current -> target`` is an edge of this machine."""
    return target in LEGAL_TRANSITIONS.get(current, frozenset())


def require_legal_transition(current: str, target: str) -> str:
    """Assert the edge exists, or refuse.

    A :class:`GovernanceBlock` rather than a :class:`ValueError`: an attempt to
    jump the machine is a governance event -- it is how a stage would be skipped
    -- and it must read as one in the run log.
    """
    if current not in LEGAL_TRANSITIONS:
        raise GovernanceBlock(f"Unknown supervisor state {current!r}.")
    if target not in LEGAL_TRANSITIONS:
        raise GovernanceBlock(f"Unknown supervisor state {target!r}.")
    if current in TERMINAL_STATES:
        raise GovernanceBlock(
            f"{current} is terminal. A halted or completed run is not resumed by "
            "transition; it is re-entered by a human under new evidence."
        )
    if not is_legal_transition(current, target):
        allowed = ", ".join(sorted(LEGAL_TRANSITIONS[current]))
        raise GovernanceBlock(
            f"Illegal supervisor transition {current} -> {target}. "
            f"From {current} the machine may only reach: {allowed}."
        )
    return target


def transition_summary() -> dict[str, Any]:
    """The machine, as a manifest and report payload."""
    return {
        "state_count": len(STATES),
        "spine_state_count": len(SPINE),
        "halt_state_count": len(HALT_STATES),
        "transition_count": sum(len(t) for t in LEGAL_TRANSITIONS.values()),
        "spine_transition_count": len(SPINE) - 1,
        "states": list(STATES),
        "spine": list(SPINE),
        "terminal_states": list(TERMINAL_STATES),
        "halt_states": list(HALT_STATES),
        "status_classes": list(STATUS_CLASSES),
        "continuing_statuses": list(CONTINUING_STATUSES),
        "transitions": {name: sorted(t) for name, t in LEGAL_TRANSITIONS.items()},
    }
