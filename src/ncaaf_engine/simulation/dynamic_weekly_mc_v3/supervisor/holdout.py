"""Holdout custody: sealed before selection, released once, scored once.

The holdout is the only measurement in the whole run that is out-of-sample by
construction, and it stops being that the moment anyone looks at it early. Two
distinct failures do it, and each gets its own mechanism here.

**Looking during selection.** If a candidate-generation worker can score against
the holdout, the holdout has entered the selection loop and its later RMSE is an
in-sample number wearing an out-of-sample label. :class:`HoldoutGuard` wraps the
scoring oracle so a holdout call *raises* while the seal is locked. It is a
refusal at the call, not a review-time note, because by review the number
already exists and the harm is done.

**Editing what it was sealed against.** A holdout scored against a different
dataset, a different split, a different experiment configuration, a different
candidate universe or a different scoring function than the one selection ran
under is not evidence about that selection. :class:`HoldoutSeal` binds all five
digests before release and re-derives them at release; any drift refuses.

Release is one-way within a run, and scoring happens once. A run that could
release twice could score twice and keep the better number, which is selection
on the holdout by a slower route. :meth:`HoldoutGuard.release` and
:meth:`HoldoutGuard.record_score` therefore refuse a second call rather than
overwriting, and the refusal names the earlier outcome so nobody has to wonder
whether it was lost.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping

from ..errors import GovernanceBlock, InputValidationError
from . import states as S
from .digests import digest_mapping
from .search import ScoringOracle

__all__ = [
    "HOLDOUT_SPLIT",
    "HoldoutGuard",
    "HoldoutSeal",
    "guarded_oracle",
    "require_release_state",
]

#: The split name the guard refuses. Matched case-insensitively after stripping,
#: because "Holdout" and " holdout " are the same partition and a guard that can
#: be stepped around by capitalisation is decoration.
HOLDOUT_SPLIT = "holdout"


@dataclass(frozen=True)
class HoldoutSeal:
    """The five bindings that must hold from selection through release.

    All five are digests of things that were fixed *before* any candidate was
    generated. Recomputing them at release and comparing is the whole mechanism:
    equality means the holdout is being scored against exactly the experiment
    that selection ran, and inequality means it is not, whatever the intent.
    """

    dataset_sha256: str
    split_sha256: str
    experiment_config_sha256: str
    candidate_universe_digest: str
    scoring_oracle_digest: str

    def __post_init__(self) -> None:
        blank = sorted(
            name
            for name, value in self.as_dict().items()
            if not str(value).strip()
        )
        if blank:
            raise InputValidationError(
                f"Holdout seal has empty bindings: {blank}. An empty digest binds "
                "nothing and would make the release check unconditionally pass."
            )

    @property
    def seal_digest(self) -> str:
        return digest_mapping(self.as_dict())

    def as_dict(self) -> dict[str, str]:
        return {
            "dataset_sha256": self.dataset_sha256,
            "split_sha256": self.split_sha256,
            "experiment_config_sha256": self.experiment_config_sha256,
            "candidate_universe_digest": self.candidate_universe_digest,
            "scoring_oracle_digest": self.scoring_oracle_digest,
        }

    def require_matches(self, observed: "HoldoutSeal") -> None:
        """Refuse unless every binding still holds.

        Every difference is reported, not just the first. An operator fixing one
        drift at a time is an operator who does not yet know how far the run has
        moved from what it sealed.
        """
        mine, theirs = self.as_dict(), observed.as_dict()
        drift = {
            name: {"sealed": mine[name], "observed": theirs[name]}
            for name in mine
            if mine[name] != theirs[name]
        }
        if drift:
            named = ", ".join(sorted(drift))
            raise GovernanceBlock(
                f"Holdout release refused: {named} changed since the holdout was "
                "sealed. A holdout scored against a different dataset, split, "
                "experiment configuration, candidate universe or scoring oracle than "
                f"the one selection ran under is not out-of-sample evidence. Drift: "
                f"{drift}"
            )


def require_release_state(current_state: str) -> None:
    """Refuse a holdout release from any state but :data:`states.HOLDOUT_LOCKED`.

    The state check is separate from the seal check because they refuse
    different mistakes: the seal catches an edited experiment, and this catches
    a release attempted before validation froze -- which is the case where
    nothing has drifted yet precisely because nothing has happened yet.
    """
    if current_state != S.HOLDOUT_LOCKED:
        try:
            early = S.state_index(current_state) < S.state_index(S.HOLDOUT_LOCKED)
        except ValueError:
            early = False
        reason = (
            "the prior stages are not yet frozen"
            if early
            else "the holdout has already left the locked state"
        )
        raise GovernanceBlock(
            f"Holdout release refused from {current_state}: {reason}. Release is legal "
            f"only from {S.HOLDOUT_LOCKED}."
        )


@dataclass
class HoldoutGuard:
    """Custody of one run's holdout. Mutable, deliberately, and one-way.

    This is the only mutable object in the supervisor's evidence path. It has to
    be: "has the holdout been released" is a fact that changes exactly once
    during a run, and modelling it as an immutable value would mean a caller
    holding a stale copy could believe the holdout was still sealed. The
    mutations it permits are one-directional -- sealed to released, unscored to
    scored -- and each refuses its second invocation.
    """

    seal: HoldoutSeal
    released: bool = False
    scored: bool = False
    outcome: dict[str, Any] | None = None
    release_record: dict[str, Any] = field(default_factory=dict)

    # -- access ---------------------------------------------------------------

    def require_not_inspectable(self, split: str) -> None:
        """Refuse a holdout read while the seal is locked."""
        if split.strip().lower() != HOLDOUT_SPLIT:
            return
        if not self.released:
            raise GovernanceBlock(
                "Holdout access refused during candidate generation. The holdout is "
                "sealed until validation is frozen and the seal is verified; a "
                "candidate scored against it has already entered the selection loop, "
                "and its later out-of-sample claim would be false."
            )

    # -- release --------------------------------------------------------------

    def release(
        self,
        *,
        current_state: str,
        observed: HoldoutSeal,
        released_at: str,
    ) -> dict[str, Any]:
        """One-way release. Refuses a second attempt, and refuses drift."""
        if self.released:
            raise GovernanceBlock(
                "Holdout has already been released in this run "
                f"(at {self.release_record.get('released_at')!r}). Release is one-way: "
                "a run that could release twice could score twice and keep the better "
                "number, which is selection on the holdout by a slower route."
            )
        require_release_state(current_state)
        self.seal.require_matches(observed)
        self.released = True
        self.release_record = {
            "released_at": released_at,
            "released_from_state": current_state,
            "seal_digest": self.seal.seal_digest,
            "seal": self.seal.as_dict(),
        }
        return dict(self.release_record)

    # -- scoring --------------------------------------------------------------

    def record_score(self, outcome: Mapping[str, Any]) -> dict[str, Any]:
        """Record the single holdout result. Refuses a second."""
        if not self.released:
            raise GovernanceBlock(
                "Holdout cannot be scored before it is released."
            )
        if self.scored:
            raise GovernanceBlock(
                "Holdout has already been scored in this run. Scoring it again would "
                "produce a second outcome to choose between, and choosing between "
                f"holdout outcomes is selection. Recorded outcome: {self.outcome}"
            )
        self.scored = True
        self.outcome = dict(outcome)
        return dict(self.outcome)

    def as_dict(self) -> dict[str, Any]:
        return {
            "seal": self.seal.as_dict(),
            "seal_digest": self.seal.seal_digest,
            "released": self.released,
            "scored": self.scored,
            "release_record": dict(self.release_record),
            "outcome": None if self.outcome is None else dict(self.outcome),
        }


def guarded_oracle(oracle: ScoringOracle, guard: HoldoutGuard) -> ScoringOracle:
    """Wrap ``oracle`` so holdout reads are refused while the seal is locked.

    ``implementation_digest`` is carried through unchanged, so the wrapped
    oracle has the *same* :attr:`ScoringOracle.digest` as the one the seal was
    taken against. That is intended: custody is not part of the scoring
    mathematics, and if wrapping changed the digest then sealing against the
    guarded oracle and scoring through it would be the only combination that
    ever verified, which would make the binding vacuous.
    """

    def _fn(candidate: Mapping[str, Any], split: str) -> float:
        guard.require_not_inspectable(split)
        return oracle.fn(candidate, split)

    return replace(oracle, fn=_fn)
