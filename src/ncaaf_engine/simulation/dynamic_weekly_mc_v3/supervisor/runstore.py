"""The run directory: atomic state, immutable stage results, one owner.

A supervisor that can be interrupted has to be able to say, on restart, exactly
what had already happened -- and to refuse to continue if the answer is no
longer trustworthy. Three mechanisms do that, and they are separate because they
fail separately.

**Atomic state.** :func:`atomic_write_json` writes a temporary file in the same
directory and then :func:`os.replace`\\ s it over the target. A reader therefore
sees the old state or the new one, never half of either. A crash between the two
writes loses the newer state, which is recoverable; a crash *during* a
non-atomic write loses the ability to know what state the run was in, which is
not.

**Immutable stage results.** :func:`write_stage_result` refuses to overwrite an
existing result with different content. A completed stage's result is the
evidence that its transition was earned, so a re-run that produced a different
answer must surface as a conflict rather than replace the record -- especially
the holdout, where quietly keeping the second answer is selection.

**One owner.** :class:`RunLock` is an exclusive-create lock file. Two supervisors
in one run directory would interleave state writes and each would resume from
the other's progress. Parallel deterministic scoring shards are fine -- they
compute, they do not mutate the run -- but a second *supervisor* is refused, and
a lock left behind by a crash is reported rather than silently stolen: deciding
that another process is dead is a judgement this module is not able to make
correctly.

Resume verifies before it continues
------------------------------------

:func:`RunState.require_resumable` re-derives the supervisor's code digest and
the run's input digest and compares them against what the run recorded. Half a
run under one set of rules and half under another is not a governed result, so
drift refuses rather than warns.
"""

from __future__ import annotations

import json
import os
import socket
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping

from ..errors import GovernanceBlock, InputValidationError
from ..textio import write_text_lf
from . import states as S
from .digests import canonical_json, code_tree_digest, digest_mapping

__all__ = [
    "RUN_SUBDIRECTORIES",
    "DEFAULT_RUN_ROOT",
    "RunLock",
    "RunState",
    "atomic_write_json",
    "new_run_id",
    "run_directory",
    "write_stage_result",
]

#: Where autonomous runs live. Under ``artifacts/`` rather than ``output/`` so a
#: run's governed record is not swept up by the output ignore rule -- and the
#: directory is ignored in turn, because a 10,000-path run's outputs are not
#: something to commit merely because the supervisor created them.
DEFAULT_RUN_ROOT = Path("artifacts/v3_autonomous_runs")

#: The fixed layout. Created up front, all of them, so a stage never has to
#: decide whether its own directory exists and two stages never race to make it.
RUN_SUBDIRECTORIES: tuple[str, ...] = (
    "inputs",
    "stage_results",
    "logs",
    "recommendation",
    "approval",
    "dev_500",
    "analysis_2000",
    "publish_10000",
    "freeze",
)

_STATE_FILENAME = "state.json"
_MANIFEST_FILENAME = "run_manifest.json"
_LOCK_FILENAME = "supervisor.lock"


def utc_now() -> str:
    """UTC timestamp in the format the rest of V3 records."""
    return datetime.now(timezone.utc).isoformat()


def new_run_id(now: str | None = None) -> str:
    """A run identifier derived from UTC time, matching the V3 CLI convention."""
    stamp = datetime.now(timezone.utc) if now is None else datetime.fromisoformat(now)
    return stamp.strftime("%Y%m%dT%H%M%SZ")


def run_directory(run_id: str, root: Path | None = None) -> Path:
    """Path to one run, without creating anything."""
    return (Path(root) if root is not None else DEFAULT_RUN_ROOT) / run_id


def atomic_write_json(path: Path, payload: Any) -> Path:
    """Write ``payload`` as deterministic JSON, atomically.

    The temporary file is created in the destination directory, not the system
    temp directory: :func:`os.replace` is only atomic within a filesystem, and a
    cross-device rename would silently degrade to a copy -- reintroducing exactly
    the torn-write window this exists to close.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    write_text_lf(tmp, json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, path)
    return path


class RunLock:
    """Exclusive ownership of one run directory.

    Used as a context manager. Acquisition is an exclusive file create, which is
    atomic on every platform this runs on; there is no check-then-create window
    for a second supervisor to slip through.
    """

    def __init__(self, run_dir: Path) -> None:
        self.run_dir = Path(run_dir)
        self.path = self.run_dir / _LOCK_FILENAME
        self._fd: int | None = None

    def acquire(self) -> "RunLock":
        self.run_dir.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = self._read_holder()
            raise GovernanceBlock(
                f"Run {self.run_dir.name} is already owned by another supervisor "
                f"({holder}). One supervisor owns a run directory at a time: two would "
                "interleave state writes and each would resume from the other's "
                "progress. If that process is gone, remove "
                f"{self.path} deliberately -- this lock is never stolen automatically, "
                "because deciding another process is dead is not a judgement that can "
                "be made from here."
            ) from None
        payload = canonical_json(
            {
                "pid": os.getpid(),
                "host": socket.gethostname(),
                "acquired_at": utc_now(),
                "run_id": self.run_dir.name,
            }
        )
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(payload)
        self._fd = 1
        return self

    def _read_holder(self) -> str:
        try:
            return self.path.read_text(encoding="utf-8").strip()
        except OSError:  # pragma: no cover - lock vanished between attempts
            return "<unreadable lock file>"

    def release(self) -> None:
        if self._fd is None:
            return
        self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:  # pragma: no cover - already cleaned
            pass

    def __enter__(self) -> "RunLock":
        return self.acquire()

    def __exit__(self, *exc: object) -> None:
        self.release()


@dataclass
class RunState:
    """The persisted state of one run.

    Mutable, and saved after every transition. The invariants that matter are
    enforced on the way through :meth:`advance` rather than by freezing the
    object: a state machine whose current state cannot change is not one.
    """

    run_id: str
    run_dir: Path
    state: str = S.INITIALIZED
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
    code_tree_digest: str = field(default_factory=code_tree_digest)
    input_digest: str = ""
    evidence_manifest_digest: str = ""
    history: list[dict[str, Any]] = field(default_factory=list)
    stage_digests: dict[str, str] = field(default_factory=dict)
    recommendation_sha256: str = ""
    approval_digest: str = ""
    holdout: dict[str, Any] = field(default_factory=dict)
    bindings: dict[str, str] = field(default_factory=dict)
    halt_reason: str = ""

    # -- persistence ----------------------------------------------------------

    @property
    def state_path(self) -> Path:
        return self.run_dir / _STATE_FILENAME

    def as_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "code_tree_digest": self.code_tree_digest,
            "input_digest": self.input_digest,
            "evidence_manifest_digest": self.evidence_manifest_digest,
            "history": [dict(h) for h in self.history],
            "stage_digests": dict(self.stage_digests),
            "recommendation_sha256": self.recommendation_sha256,
            "approval_digest": self.approval_digest,
            "holdout": dict(self.holdout),
            "bindings": dict(self.bindings),
            "halt_reason": self.halt_reason,
        }

    def save(self) -> Path:
        self.updated_at = utc_now()
        return atomic_write_json(self.state_path, self.as_dict())

    @classmethod
    def create(cls, run_id: str, run_dir: Path) -> "RunState":
        run_dir = Path(run_dir)
        for name in RUN_SUBDIRECTORIES:
            (run_dir / name).mkdir(parents=True, exist_ok=True)
        state = cls(run_id=run_id, run_dir=run_dir)
        state.save()
        return state

    @classmethod
    def load(cls, run_dir: Path) -> "RunState":
        run_dir = Path(run_dir)
        path = run_dir / _STATE_FILENAME
        if not path.exists():
            raise InputValidationError(f"No supervisor state at {path}.")
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("state") not in S.STATES:
            raise GovernanceBlock(
                f"Persisted state {raw.get('state')!r} is not a state this machine "
                "recognises. A run directory carrying an unknown state is not resumed."
            )
        return cls(
            run_id=raw["run_id"],
            run_dir=run_dir,
            state=raw["state"],
            created_at=raw.get("created_at", ""),
            updated_at=raw.get("updated_at", ""),
            code_tree_digest=raw.get("code_tree_digest", ""),
            input_digest=raw.get("input_digest", ""),
            evidence_manifest_digest=raw.get("evidence_manifest_digest", ""),
            history=list(raw.get("history", [])),
            stage_digests=dict(raw.get("stage_digests", {})),
            recommendation_sha256=raw.get("recommendation_sha256", ""),
            approval_digest=raw.get("approval_digest", ""),
            holdout=dict(raw.get("holdout", {})),
            bindings=dict(raw.get("bindings", {})),
            halt_reason=raw.get("halt_reason", ""),
        )

    # -- transitions ----------------------------------------------------------

    def advance(
        self,
        target: str,
        *,
        result: S.StageResult | None = None,
        reason: str = "",
    ) -> str:
        """Move to ``target`` along a legal edge, recording why, and persist.

        The legality check comes first and the state is written last, so a
        refused transition leaves nothing behind. A run whose state file
        advanced but whose stage result did not would be a run claiming
        progress it cannot show.
        """
        S.require_legal_transition(self.state, target)
        entry = {
            "from": self.state,
            "to": target,
            "at": utc_now(),
            "reason": reason,
            "stage": None if result is None else result.stage,
            "status": None if result is None else result.status,
            "advisories": [] if result is None else list(result.advisories),
        }
        self.state = target
        if target in S.HALT_STATES:
            self.halt_reason = reason or (
                "" if result is None else f"{result.stage}: {result.summary}"
            )
        self.history.append(entry)
        self.save()
        return self.state

    def record_stage(self, result: S.StageResult) -> Path:
        """Write a stage result immutably and remember its digest."""
        path = write_stage_result(self.run_dir, len(self.stage_digests), result)
        self.stage_digests[result.stage] = digest_mapping(result.as_dict())
        self.save()
        return path

    # -- resume ---------------------------------------------------------------

    def require_resumable(self, *, observed_input_digest: str | None = None) -> None:
        """Refuse to continue a run whose code or inputs have moved.

        ``observed_input_digest`` is passed by the caller that just re-derived it
        from the inputs on disk. It is a parameter rather than something this
        module recomputes because the run's inputs are defined by its
        configuration, and the state file is not the authority on what those
        inputs were meant to be.
        """
        if self.state in S.TERMINAL_STATES:
            raise GovernanceBlock(
                f"Run {self.run_id} is {self.state} and is not resumable. "
                + (f"Halt reason: {self.halt_reason}" if self.halt_reason else "")
            )
        observed_code = code_tree_digest()
        if self.code_tree_digest and observed_code != self.code_tree_digest:
            raise GovernanceBlock(
                f"Run {self.run_id} was started under supervisor code "
                f"{self.code_tree_digest} and the working tree now digests to "
                f"{observed_code}. Half a run under one set of rules and half under "
                "another is not a governed result."
            )
        if (
            observed_input_digest is not None
            and self.input_digest
            and observed_input_digest != self.input_digest
        ):
            raise GovernanceBlock(
                f"Run {self.run_id} was bound to inputs {self.input_digest} and the "
                f"inputs on disk now digest to {observed_input_digest}."
            )


def write_stage_result(run_dir: Path, ordinal: int, result: S.StageResult) -> Path:
    """Write one stage result, refusing to silently replace a different one.

    Identical content re-written is accepted -- that is an idempotent resume
    replaying a completed stage, and refusing it would make crash recovery
    impossible. Different content is a conflict and is raised, because the
    question "which of these two answers is the run's answer" is not one a file
    write should decide.
    """
    directory = Path(run_dir) / "stage_results"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{ordinal:03d}_{result.stage}.json"
    payload = result.as_dict()
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if digest_mapping(existing) != digest_mapping(payload):
            raise GovernanceBlock(
                f"Stage result {path.name} already exists with different content. A "
                "completed stage's result is the evidence its transition was earned; "
                "a re-run that disagrees is a conflict to resolve, not a file to "
                "overwrite."
            )
        return path
    return atomic_write_json(path, payload)


def write_run_manifest(run_dir: Path, payload: Mapping[str, Any]) -> Path:
    """Write the run manifest: what this run is, and what it is bound to."""
    return atomic_write_json(Path(run_dir) / _MANIFEST_FILENAME, dict(payload))


def iter_runs(root: Path | None = None) -> Iterator[Path]:
    """Every run directory under ``root`` that carries a state file."""
    base = Path(root) if root is not None else DEFAULT_RUN_ROOT
    if not base.exists():
        return
    for child in sorted(base.iterdir()):
        if (child / _STATE_FILENAME).exists():
            yield child
