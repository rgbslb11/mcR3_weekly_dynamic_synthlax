"""Digests the supervisor binds decisions to.

Every gate downstream of this module is an equality between two digests, so the
digests have to mean something on their own. Three rules make that true.

**One canonical form.** :func:`canonical_json` is the only serialization used
for a digested payload: sorted keys, no insignificant whitespace, UTF-8, LF.
Two structurally identical payloads therefore digest identically regardless of
which dict literal built them, and a payload that differs anywhere differs in
the digest. Without this the approval binding would depend on key insertion
order, which is not a property anyone intends to approve.

**Bytes, not fields.** :func:`sha256_file` reads the file. A digest that was
copied out of a manifest and compared against the same manifest is
self-attestation -- the same failure :mod:`..calibration_evidence` closed for
calibration datasets -- so nothing here accepts a caller-supplied digest as
evidence of anything.

**Code identity is derived from source.** :func:`code_tree_digest` hashes the
supervisor's own ``.py`` files. A resumed run re-derives it and refuses if it
moved, which is what stops a run from finishing under different logic than it
started under. It deliberately covers this package only: hashing the whole
repository would make an unrelated edit anywhere invalidate every in-flight
run, and hashing nothing would make "same code" an assumption.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

__all__ = [
    "SUPERVISOR_PACKAGE_ROOT",
    "canonical_json",
    "canonical_json_bytes",
    "code_tree_digest",
    "digest_mapping",
    "digest_of_paths",
    "sha256_bytes",
    "sha256_file",
]

#: This package. The unit of "did the supervisor's own logic change".
SUPERVISOR_PACKAGE_ROOT = Path(__file__).resolve().parent


def canonical_json(payload: Any) -> str:
    """Canonical JSON text: sorted keys, compact separators, ASCII-safe.

    ``ensure_ascii=True`` is kept (the default) so the byte sequence does not
    depend on the encoding of a team name that happens to carry a diacritic.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def canonical_json_bytes(payload: Any) -> bytes:
    """:func:`canonical_json` as UTF-8 bytes -- what actually gets hashed."""
    return canonical_json(payload).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """SHA-256 of the file's bytes, read in chunks.

    Chunked because a mounted observation corpus is not guaranteed small, and a
    digest helper that only works on small files invites a caller to skip it on
    the large one.
    """
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def digest_mapping(payload: Mapping[str, Any]) -> str:
    """SHA-256 over the canonical form of ``payload``."""
    return sha256_bytes(canonical_json_bytes(payload))


def digest_of_paths(paths: Iterable[Path]) -> str:
    """A single digest over a set of files, name and content both.

    Names are included and the set is sorted, so adding, removing or renaming a
    file changes the digest even when the total content is unchanged. A digest
    that only covered content would call a renamed file the same tree.
    """
    entries = []
    for path in sorted({Path(p).resolve() for p in paths}, key=lambda p: p.as_posix()):
        entries.append({"name": path.name, "sha256": sha256_file(path)})
    return digest_mapping({"files": entries})


def code_tree_digest(root: Path | None = None) -> str:
    """Digest of the supervisor's own source.

    Recomputed on every resume and compared against what the run recorded. A
    mismatch is refused rather than warned about: half a run under one set of
    rules and half under another is not a governed result, and the cheapest
    moment to notice is before the second half starts.
    """
    base = SUPERVISOR_PACKAGE_ROOT if root is None else Path(root).resolve()
    return digest_of_paths(sorted(base.rglob("*.py")))
