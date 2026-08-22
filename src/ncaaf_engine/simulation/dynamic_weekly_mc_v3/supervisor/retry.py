"""Automatic retries, kept deliberately narrow.

A supervisor that retries on failure stops being a validator. Every retry
policy is therefore written against one named, understood, environmental
failure, and the module refuses to grow a general one.

The only execution retry: the Windows temp-root race
-----------------------------------------------------

``conftest.py`` documents the two Windows failure modes this repository has
actually hit -- a stale ``pytest-of-<user>`` root that the current user cannot
write into, and MAX_PATH truncation under a deep default base temp. Both present
as a total failure before any test runs, and neither is a defect in the thing
being validated. A run that dies on one has measured nothing.

So: on a *matching* filesystem or temp-lock failure, create a fresh short
isolated base temporary directory and retry **once**. Once, not until it works:
a second identical failure is no longer a race, and the third attempt would be
the supervisor hoping rather than checking. Anything that does not match the
patterns propagates untouched, including every model failure.

The other automatic behaviours are not retries
-----------------------------------------------

They are classifications, and they live with the stages that make them:

* an optional witness whose data is unavailable records ``WITNESS_UNAVAILABLE``
  and continues -- :mod:`.witness`;
* a boundary optimum expands its declared range -- :mod:`.search`;
* an unidentifiable FCS adapter follows the manifest's eligibility policy --
  :mod:`.evidence`.

None of them re-runs anything, and none of them turns absent required evidence
into a pass. :data:`RETRY_POLICY` states all of that in the run manifest so the
policy is auditable without reading this file.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

__all__ = [
    "RETRY_POLICY",
    "RetryOutcome",
    "TEMP_ROOT_FAILURE_PATTERNS",
    "fresh_isolated_basetemp",
    "is_temp_root_failure",
    "run_with_temp_root_retry",
]

T = TypeVar("T")

#: Operator override for where isolated base temps are created.
SUPERVISOR_TEMP_ROOT_ENV_VAR = "SYTHALAX_SUPERVISOR_TMP"

#: Short by construction, for the MAX_PATH reason ``conftest.py`` records.
_PREFERRED_TEMP_ROOT = Path("C:/sxt")

#: Substrings and codes that identify the temp-root race. Matched case-folded
#: against the exception text, and deliberately specific: "permission denied"
#: alone would swallow a genuine access failure against a governed input, which
#: must never be retried into a pass.
TEMP_ROOT_FAILURE_PATTERNS: tuple[str, ...] = (
    "pytest-of-",
    "basetemp",
    "winerror 5",
    "winerror 32",
    "winerror 145",
    "winerror 206",
    "the process cannot access the file because it is being used by another process",
    "filename or extension is too long",
    "path too long",
)

_WINERROR_CODES = frozenset({5, 32, 145, 206})

_COUNTER = 0


def is_temp_root_failure(exc: BaseException) -> bool:
    """Whether ``exc`` is the recognised temp-root race.

    Two independent signals are accepted: a Windows error number this failure is
    known to raise, and the text patterns above. The numeric check is first
    because it is the unambiguous one -- a message can be localised, and a run on
    a non-English Windows must still recognise its own environment failure.
    """
    if not isinstance(exc, OSError):
        return False
    winerror = getattr(exc, "winerror", None)
    if isinstance(winerror, int) and winerror in _WINERROR_CODES:
        return True
    text = f"{exc} {getattr(exc, 'filename', '') or ''}".casefold()
    return any(pattern in text for pattern in TEMP_ROOT_FAILURE_PATTERNS)


def _usable(root: Path) -> bool:
    """Probe with a real file. Existence and permission bits both lie on Windows."""
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except (OSError, ValueError):
        return False


def fresh_isolated_basetemp(prefix: str = "sv") -> Path:
    """Create and return a new, empty, short base temporary directory.

    "Fresh" is the requirement, so the directory is created with ``exist_ok=False``
    and the name advances until one is actually new. Reusing a directory would
    reproduce the very condition being retried past -- the whole failure is that
    an existing root is unusable.
    """
    global _COUNTER
    candidates = []
    override = os.environ.get(SUPERVISOR_TEMP_ROOT_ENV_VAR)
    if override:
        candidates.append(Path(override))
    if os.name == "nt":
        candidates.append(_PREFERRED_TEMP_ROOT)
    candidates.append(Path(tempfile.gettempdir()))

    root = next((c for c in candidates if _usable(c)), None)
    if root is None:  # pragma: no cover - every candidate unwritable
        raise OSError(
            "No writable short temporary root is available; tried "
            f"{[str(c) for c in candidates]}."
        )
    while True:
        _COUNTER += 1
        candidate = root / f"{prefix}{os.getpid():x}{_COUNTER:x}"
        try:
            candidate.mkdir(parents=True, exist_ok=False)
            return candidate
        except FileExistsError:
            continue


@dataclass(frozen=True)
class RetryOutcome:
    """What happened, so the stage result can say so rather than imply it."""

    value: Any
    retried: bool
    basetemp: Path | None
    first_failure: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "retried": self.retried,
            "basetemp": None if self.basetemp is None else str(self.basetemp),
            "first_failure": self.first_failure,
        }


def run_with_temp_root_retry(
    fn: Callable[[Path | None], T], *, prefix: str = "sv"
) -> RetryOutcome:
    """Run ``fn``; on the recognised temp-root race, retry once on a fresh root.

    ``fn`` receives the base temporary directory to use, or ``None`` on the first
    attempt, where it should use its normal default. Passing it explicitly rather
    than mutating ``TMP``/``TEMP`` keeps the retry local: a concurrent stage in
    the same process does not silently get a different temporary directory
    because this one had a bad minute.
    """
    try:
        return RetryOutcome(value=fn(None), retried=False, basetemp=None, first_failure=None)
    except OSError as exc:
        if not is_temp_root_failure(exc):
            # Not the recognised race. Model failures, missing governed inputs and
            # ordinary I/O errors must reach the caller unchanged.
            raise
        first_failure = f"{type(exc).__name__}: {exc}"

    basetemp = fresh_isolated_basetemp(prefix)
    return RetryOutcome(
        value=fn(basetemp), retried=True, basetemp=basetemp, first_failure=first_failure
    )


#: The whole retry surface, for the run manifest.
RETRY_POLICY: dict[str, Any] = {
    "execution_retries": [
        {
            "name": "WINDOWS_TEMP_ROOT_RACE",
            "trigger": "Matching filesystem or temp-lock failure (see patterns).",
            "action": "Create a fresh short isolated basetemp and retry once.",
            "max_attempts": 2,
            "patterns": list(TEMP_ROOT_FAILURE_PATTERNS),
            "windows_error_codes": sorted(_WINERROR_CODES),
        }
    ],
    "non_retry_classifications": [
        {
            "name": "WITNESS_UNAVAILABLE",
            "action": (
                "Record and continue when the comparison is optional; stop when it is "
                "required. Never a silent downgrade of required evidence."
            ),
        },
        {
            "name": "BOUNDARY_OPTIMUM",
            "action": (
                "Deterministically expand the declared range and search again, up to "
                "the declared budget; then PARAMETER_UNIDENTIFIED for human review."
            ),
        },
        {
            "name": "FCS_ADAPTER_UNAVAILABLE",
            "action": "Follow the frozen manifest's declared eligibility policy.",
        },
    ],
    "never_retried": [
        "Model or calibration failures",
        "Governance refusals",
        "Missing or drifted governed inputs",
        "Holdout release refusals",
        "Approval binding failures",
    ],
}
