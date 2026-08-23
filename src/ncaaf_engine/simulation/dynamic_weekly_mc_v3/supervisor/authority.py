"""Resolving frozen evidence to an exact commit, and ranking who supersedes whom.

Two problems live here, and they are the same problem seen from two sides: which
bytes are the current authority, and what happens when an older artifact
disagrees with them.

Reading evidence without reading a working tree
------------------------------------------------

The Agent-12 R2 evidence manifest is produced on another branch. The obvious way
to read it -- open the sibling worktree's file -- is exactly the way that must
not be used: a worktree is a mutable checkout, so a manifest read from one is a
manifest whose content depends on when it was read and on whether anything was
mid-edit. :func:`read_blob` therefore reads the *object store*: the ref is
resolved to a commit, and the blob is read out of that commit's tree. Every
function in this module takes a repository handle purely as a ``git -C`` target;
none of them opens a path inside another worktree, and none of them can, because
none of them builds a filesystem path from a branch name.

:func:`resolve_authority` pins that resolution. A configuration may name a
commit, and if it does, the ref must still resolve to it -- so a branch that has
moved since the pin is a refusal rather than a silent upgrade to whatever the
branch means today. A configuration that names no commit resolves the ref and
records what it found, which is enough for a plan and never enough for a run.

Supersession
------------

Evidence accumulates and older evidence goes stale. The R5 discovery record
concluded, correctly for its own moment, that particular parameters were blocked
on an unratified rating-to-margin transform and on an absent FCS observation
set. Agent-12 R2 is a later authority over the same questions. Deleting the R5
record to make the disagreement go away would destroy the history that explains
why R2 exists, so instead :data:`AUTHORITY_GENERATIONS` ranks them and
:func:`resolve_claim` picks the highest-ranked claim about each question.
:func:`require_current_authority` refuses a superseded artifact that tries to act
as the authority. The stale record stays exactly where it is and stops being
able to decide anything.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from ..errors import GovernanceBlock, InputValidationError

__all__ = [
    "AUTHORITY_GENERATIONS",
    "COMMIT_SHA",
    "AuthorityBinding",
    "CURRENT_AUTHORITY_GENERATION",
    "EligibilityClaim",
    "ResolvedAuthority",
    "authority_rank",
    "read_blob",
    "require_current_authority",
    "resolve_authority",
    "resolve_claim",
    "resolve_ref",
]

#: Shape of a git commit SHA. One definition, so a caller that pins a commit and
#: a caller that reads a blob at one agree on what a commit identifier looks like.
COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")
_COMMIT = COMMIT_SHA

#: Evidence generations that have spoken about V3 parameter eligibility, oldest
#: authority first. Rank is position in this tuple; nothing else confers
#: authority, and a generation absent from it has none at all.
#:
#: ``AGENT12_R2`` is last because it is the current authority. When a later
#: generation arrives it is appended here, in one place, rather than by editing
#: the artifacts the new generation supersedes.
AUTHORITY_GENERATIONS: tuple[str, ...] = (
    "AGENT12_R1",
    "AGENT12_R5_DISCOVERY",
    "AGENT12_R2",
)

#: The generation whose claims win today.
CURRENT_AUTHORITY_GENERATION = AUTHORITY_GENERATIONS[-1]


def authority_rank(generation: str) -> int:
    """Position of ``generation`` in the supersession order.

    Refuses an unknown generation rather than ranking it lowest. An artifact
    claiming an authority nobody recognises is not weak evidence; it is
    unattributed evidence, and treating it as merely outranked would let it win
    the moment it was the only claim about some question.
    """
    try:
        return AUTHORITY_GENERATIONS.index(generation)
    except ValueError:
        raise GovernanceBlock(
            f"Unknown evidence authority generation {generation!r}. Recognised "
            f"generations, in supersession order, are {list(AUTHORITY_GENERATIONS)}."
        ) from None


# --- git object-store access -------------------------------------------------


def _git(repo: Path, *args: str, binary: bool = False) -> Any:
    """Run one read-only git command against ``repo``'s object store."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            check=False,
        )
    except (OSError, ValueError) as exc:  # pragma: no cover - git absent
        raise InputValidationError(f"git could not be invoked in {repo}: {exc}") from None
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", "replace").strip()
        raise GovernanceBlock(
            f"git {' '.join(args)} failed in {repo}: {message or 'no detail reported'}"
        )
    return completed.stdout if binary else completed.stdout.decode("utf-8").strip()


def resolve_ref(repo: Path, ref: str) -> str:
    """The exact commit ``ref`` names, as a 40-character SHA.

    ``^{commit}`` is appended so an annotated tag or any other object resolves to
    the commit it points at rather than to itself; a run pinned to a tag object
    and a run pinned to its commit must not be two different runs.
    """
    commit = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not _COMMIT.match(commit):
        raise GovernanceBlock(
            f"Ref {ref!r} resolved to {commit!r}, which is not a commit SHA."
        )
    return commit


def read_blob(repo: Path, commit: str, path: str) -> bytes:
    """The bytes of ``path`` in ``commit``'s tree.

    Reads the object store. Nothing here touches a checked-out file, so the
    result does not depend on which worktree exists, what is checked out in it,
    or whether something is mid-edit there.
    """
    if not _COMMIT.match(commit):
        raise InputValidationError(
            f"{commit!r} is not a 40-character commit SHA; evidence is read from a "
            "pinned commit, never from a branch name resolved at read time."
        )
    return _git(repo, "cat-file", "blob", f"{commit}:{path}", binary=True)


@dataclass(frozen=True)
class AuthorityBinding:
    """Where a frozen evidence artifact lives, as configuration declares it.

    ``commit`` is the pin. Empty means "resolve the ref and report what you
    found", which is a legitimate state for ``plan`` and never a legitimate one
    for a run: an unpinned authority is whatever the branch means at the moment
    somebody looked.
    """

    ref: str
    path: str
    generation: str = CURRENT_AUTHORITY_GENERATION
    commit: str = ""
    repo: Path | None = None

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise InputValidationError("Evidence authority names no ref.")
        if not self.path.strip():
            raise InputValidationError(
                f"Evidence authority {self.ref} names no path within the tree."
            )
        authority_rank(self.generation)
        if self.commit and not _COMMIT.match(self.commit):
            raise InputValidationError(
                f"Pinned authority commit {self.commit!r} is not a 40-character SHA."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "path": self.path,
            "generation": self.generation,
            "pinned_commit": self.commit,
            "repo": None if self.repo is None else str(self.repo),
        }


@dataclass(frozen=True)
class ResolvedAuthority:
    """A binding resolved against a real object store.

    ``present`` is false when the ref resolves but the tree holds nothing at
    ``path``. That is not an error here -- it is the honest state of a branch
    whose evidence has not been committed yet -- and it is the caller's job to
    fail closed on it. Recording it as a value rather than an exception is what
    lets ``plan`` report "the authority exists, the manifest does not".
    """

    binding: AuthorityBinding
    commit: str
    present: bool
    content: bytes = b""
    absence_reason: str = ""

    @property
    def sha256(self) -> str:
        from .digests import sha256_bytes

        return sha256_bytes(self.content) if self.present else ""

    def require_present(self) -> bytes:
        if not self.present:
            raise GovernanceBlock(
                f"Evidence authority {self.binding.generation} resolves to commit "
                f"{self.commit}, and that commit's tree holds nothing at "
                f"{self.binding.path}. {self.absence_reason} The primary-domain gate "
                "reads this manifest, so its absence fails closed: no source is "
                "classified, and therefore no source is admitted to primary "
                "estimation."
            )
        return self.content

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.binding.as_dict(),
            "resolved_commit": self.commit,
            "present": self.present,
            "sha256": self.sha256,
            "absence_reason": self.absence_reason,
        }


def resolve_authority(binding: AuthorityBinding, repo: Path | None = None) -> ResolvedAuthority:
    """Resolve a binding to a commit and read its blob, or record why it could not.

    A ref that will not resolve is a refusal: the configuration names an
    authority that does not exist in this object store, and continuing would mean
    running against no authority at all. A ref that resolves to a commit whose
    tree lacks the artifact is recorded as absent, because that is a fact about
    the evidence rather than a fault in the configuration.
    """
    target = repo or binding.repo or Path.cwd()
    resolved = resolve_ref(Path(target), binding.ref)
    if binding.commit and binding.commit != resolved:
        raise GovernanceBlock(
            f"Evidence authority {binding.ref} is pinned to {binding.commit} and now "
            f"resolves to {resolved}. The branch moved after the pin was taken; a run "
            "bound to one commit must not silently continue against another."
        )
    try:
        content = read_blob(Path(target), resolved, binding.path)
    except GovernanceBlock as exc:
        return ResolvedAuthority(
            binding=binding,
            commit=resolved,
            present=False,
            absence_reason=str(exc),
        )
    return ResolvedAuthority(binding=binding, commit=resolved, present=True, content=content)


# --- supersession ------------------------------------------------------------


@dataclass(frozen=True)
class EligibilityClaim:
    """One artifact's claim about one question, and who made it."""

    generation: str
    subject: str
    claim: str
    source: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        authority_rank(self.generation)
        if not self.subject.strip():
            raise InputValidationError("An eligibility claim names no subject.")
        if not self.claim.strip():
            raise InputValidationError(
                f"Claim about {self.subject} from {self.generation} is empty."
            )

    @property
    def rank(self) -> int:
        return authority_rank(self.generation)

    def as_dict(self) -> dict[str, Any]:
        return {
            "generation": self.generation,
            "subject": self.subject,
            "claim": self.claim,
            "source": self.source,
            "rationale": self.rationale,
            "rank": self.rank,
        }


def resolve_claim(
    subject: str, claims: Iterable[EligibilityClaim]
) -> tuple[EligibilityClaim, list[EligibilityClaim]]:
    """The winning claim about ``subject``, and every claim it supersedes.

    Ties are impossible by construction where a generation makes one claim per
    subject, and where it makes two the later position in the input wins, which
    is deterministic. Nothing is deleted: the superseded claims come back with
    the winner so the record can show what was overridden and by whom.
    """
    about = [c for c in claims if c.subject == subject]
    if not about:
        raise GovernanceBlock(
            f"No evidence generation makes a claim about {subject!r}. An unclaimed "
            "question is not an implicitly permissive one."
        )
    winner = max(about, key=lambda c: c.rank)
    superseded = [c for c in about if c is not winner]
    return winner, superseded


def require_current_authority(generation: str, *, subject: str) -> None:
    """Refuse a superseded generation acting as the authority on ``subject``."""
    rank = authority_rank(generation)
    current = authority_rank(CURRENT_AUTHORITY_GENERATION)
    if rank < current:
        raise GovernanceBlock(
            f"{generation} is superseded by {CURRENT_AUTHORITY_GENERATION} and cannot "
            f"decide {subject}. The superseded record is retained as history -- it "
            "explains why the current authority exists -- but it no longer governs "
            "eligibility."
        )


def supersession_report(claims: Sequence[EligibilityClaim]) -> dict[str, Any]:
    """Every subject claimed, who won it, and what was overridden."""
    subjects = sorted({c.subject for c in claims})
    resolved: dict[str, Any] = {}
    for subject in subjects:
        winner, superseded = resolve_claim(subject, claims)
        resolved[subject] = {
            "authority": winner.generation,
            "claim": winner.claim,
            "superseded": [c.as_dict() for c in sorted(superseded, key=lambda c: c.rank)],
        }
    return {
        "current_authority": CURRENT_AUTHORITY_GENERATION,
        "generations": list(AUTHORITY_GENERATIONS),
        "subjects": resolved,
    }


def claims_from_mapping(payload: Mapping[str, Any]) -> list[EligibilityClaim]:
    """Build claims from an artifact's ``{generation, claims: {subject: claim}}`` form."""
    generation = str(payload.get("generation", ""))
    source = str(payload.get("source", ""))
    return [
        EligibilityClaim(
            generation=generation,
            subject=str(subject),
            claim=str(entry) if not isinstance(entry, Mapping) else str(entry.get("claim", "")),
            source=source,
            rationale=(
                "" if not isinstance(entry, Mapping) else str(entry.get("rationale", ""))
            ),
        )
        for subject, entry in sorted(dict(payload.get("claims", {})).items())
    ]
