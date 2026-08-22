r"""Windows test-execution hardening: short, controlled temporary roots.

Two failure modes on Windows are addressed here, both of which have actually
occurred against this repository and neither of which is a defect in any test.

WINDOWS-PYTEST-1. pytest's default base temporary directory is
``%TEMP%\pytest-of-<user>``. That directory outlives the session that made it,
and once a stale copy is left owned or locked such that the current user cannot
write into it, every subsequent session fails at startup with ``WinError 5``
before a single test is collected. The failure is environmental but presents as
a total suite failure.

WINDOWS-PATH-1. Windows refuses paths beyond MAX_PATH (260 characters) unless
long-path support is enabled process-wide. The default base temp is already
deep, this repository's test names are long, and a Board custody test failed at
exactly 260 characters and then passed unchanged under a shorter root. Any test
that builds a few directories under ``tmp_path`` can cross that line on one
machine and not another, which makes suite results depend on the length of a
user name.

Both are fixed by pointing pytest at a short root this repository controls.
``--basetemp`` is used rather than merely relocating ``%TEMP%``: it removes the
``pytest-of-<user>`` and ``pytest-<n>`` path segments altogether, so it is the
shorter of the two options as well as the one that never consults the stale
default. ``TMP`` and ``TEMP`` are pointed at the same root so that code calling
:mod:`tempfile` directly is kept short too.

Deliberately narrow:

* Nothing happens off Windows, where neither failure mode exists.
* An explicit ``--basetemp`` from the operator always wins. This never silently
  overrides a chosen location.
* Nothing outside the chosen root is created, moved or deleted. A stale,
  inaccessible default root is stepped around, never repaired — repairing it
  would need elevation, and this must run without it.
* Only the temp location changes. No test outcome is suppressed, no error is
  swallowed, and if a short root cannot be created the run continues on pytest's
  default with a warning rather than dying or, worse, quietly skipping.

``--basetemp`` is cleared by pytest at session start, which is why each root is
per-repository rather than shared: two suites run concurrently from the same
worktree would otherwise share one scratch directory.
"""

from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pytest

#: Operator override, honoured on any platform-appropriate run.
TEMP_ROOT_ENV_VAR = "SYTHALAX_TEST_TMP"

#: Preferred root. Short by construction: three characters of directory name at
#: the top of the drive leaves the whole MAX_PATH budget to the tests.
PREFERRED_TEMP_ROOT = Path("C:/sxt")

#: Repository-adjacent fallback, used when the drive root is not writable.
#: Longer, but still far shorter than the default, and always available to the
#: user who checked the repository out.
FALLBACK_TEMP_ROOT_NAME = ".sxt"


def _usable(root: Path) -> bool:
    """Whether ``root`` can be created and written to, without raising.

    Probes with a real file: existence and permission bits both lie on Windows,
    where a directory can be listed but not written into — which is exactly the
    stale-root condition being avoided.

    ``ValueError`` is caught alongside ``OSError`` because a malformed operator
    override (an embedded null, say) raises before the filesystem is ever
    consulted. An unusable candidate must send the resolver to the next one; it
    must never take the test session down with it.
    """
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".probe"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except (OSError, ValueError):
        return False


def resolve_short_temp_root(repo_root: Path, environ: dict | None = None) -> Path | None:
    """Choose the short temporary root, or ``None`` if no candidate is usable.

    Order is fixed so the answer is reproducible on a given machine: an explicit
    environment override, then the drive-root location, then a repository-
    adjacent directory. Each candidate is probed rather than assumed, because
    the whole point is that the obvious location is sometimes unusable.
    """
    environ = os.environ if environ is None else environ
    candidates: list[Path] = []
    override = environ.get(TEMP_ROOT_ENV_VAR)
    if override:
        candidates.append(Path(override))
    candidates.append(PREFERRED_TEMP_ROOT)
    candidates.append(repo_root / FALLBACK_TEMP_ROOT_NAME)
    for candidate in candidates:
        if _usable(candidate):
            return candidate
    return None


def pytest_configure(config: pytest.Config) -> None:
    if sys.platform != "win32":
        return
    if config.option.basetemp:
        # The operator named a location. Theirs, not ours.
        return

    repo_root = Path(str(config.rootpath))
    root = resolve_short_temp_root(repo_root)
    if root is None:
        warnings.warn(
            "No short temporary root could be created "
            f"({TEMP_ROOT_ENV_VAR}, {PREFERRED_TEMP_ROOT}, "
            f"{repo_root / FALLBACK_TEMP_ROOT_NAME} were all unwritable); "
            "continuing on pytest's default base temp, which on Windows may hit "
            "MAX_PATH or a stale pytest-of-<user> root.",
            stacklevel=1,
        )
        return

    config.option.basetemp = str(root / "bt")
    # Keep direct tempfile users short as well; pytest only governs its own
    # fixtures. Restored by process exit — nothing outside this run sees it.
    scratch = root / "t"
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ["TMP"] = str(scratch)
    os.environ["TEMP"] = str(scratch)


@pytest.fixture(scope="session")
def short_temp_root_resolver():
    """The resolver itself, so its behaviour can be tested directly."""
    return resolve_short_temp_root
