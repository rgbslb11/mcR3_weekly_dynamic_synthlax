"""A real frozen evidence authority for the supervisor tests to read.

The supervisor's primary-domain gate reads the Agent-12 R2 evidence manifest out
of a git object store at a pinned commit. Faking that -- handing the supervisor a
parsed manifest, or pointing it at a loose file -- would test everything except
the property the gate exists for, which is that the bytes it classifies are the
bytes somebody committed and not whatever is in a working directory right now.

So the tests publish real manifests into a real repository. :func:`publish`
writes a payload, commits it, and returns the commit and a binding pinned to it.
One repository is created per process and reused, because ``git init`` is the
expensive part and the commits are not; each payload lands at its own path, keyed
by its digest, so two tests never collide and a test that publishes the same
payload twice gets the same commit back.

Nothing here reads a sibling worktree, and nothing here builds a filesystem path
from a branch name -- the same constraint the production code is under.
"""

from __future__ import annotations

import atexit
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from ncaaf_engine.simulation.dynamic_weekly_mc_v3.calibration import (
    FORBIDDEN_DATASET_SIGNALS,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor import domain_manifest as DM
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor.authority import (
    AuthorityBinding,
    CURRENT_AUTHORITY_GENERATION,
)

#: Where the manifests are committed inside the test repository. Arbitrary, and
#: deliberately not named like the branch it stands in for: nothing in the
#: production path derives meaning from this string.
MANIFEST_DIR = "reference/evidence"

#: The dataset and split digests the fake executor registers. The manifest is
#: bound to them so the dataset gate has something true to check.
DATASET_SHA256 = "d" * 64
SPLIT_SHA256 = "s" * 64

_repo: Path | None = None
_published: dict[str, tuple[Path, str, str]] = {}


def _run(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=True,
    )
    return completed.stdout.decode("utf-8").strip()


def repo() -> Path:
    """The process-wide test repository, created on first use."""
    global _repo
    if _repo is None:
        root = Path(tempfile.mkdtemp(prefix="sxa-")).resolve()
        subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
        _run(root, "config", "user.email", "tests@example.invalid")
        _run(root, "config", "user.name", "Supervisor Tests")
        _run(root, "config", "commit.gpgsign", "false")
        (root / MANIFEST_DIR).mkdir(parents=True, exist_ok=True)
        _repo = root
        atexit.register(lambda: shutil.rmtree(root, ignore_errors=True))
    return _repo


def publish(
    payload: dict | None = None, *, generation: str = CURRENT_AUTHORITY_GENERATION
) -> tuple[Path, str, str]:
    """Commit ``payload`` and return ``(repo, commit, path)``.

    Cached on the payload's canonical bytes, so a test that publishes the
    standard manifest pays for one commit no matter how many times it asks.
    """
    body = payload if payload is not None else authority_manifest_payload()
    raw = json.dumps(body, sort_keys=True, indent=2).encode("utf-8")
    key = hashlib.sha256(raw).hexdigest()
    if key in _published:
        return _published[key]
    root = repo()
    relative = f"{MANIFEST_DIR}/{key[:16]}.json"
    (root / relative).write_bytes(raw)
    _run(root, "add", "--", relative)
    _run(root, "commit", "-q", "-m", f"Publish evidence manifest {key[:16]}")
    commit = _run(root, "rev-parse", "HEAD")
    _published[key] = (root, commit, relative)
    return _published[key]


def binding_for(
    payload: dict | None = None, *, generation: str = CURRENT_AUTHORITY_GENERATION
) -> tuple[Path, AuthorityBinding]:
    """A pinned :class:`AuthorityBinding` for ``payload``, and its repository."""
    root, commit, relative = publish(payload, generation=generation)
    return root, AuthorityBinding(
        ref=commit,
        path=relative,
        generation=generation,
        commit=commit,
        repo=root,
    )


def source(
    source_id: str,
    content: bytes,
    *,
    lineage: str = DM.SYNTHETIC_GENERATED,
    season: str = "SYNTHETIC_2024",
    domain: str = DM.PRIMARY_ESTIMATION,
    fields: dict[str, str] | None = None,
    split: str = "training",
    rationale: str = "Registered by the R2 evidence sweep.",
    sha256: str | None = None,
) -> dict:
    """One source entry, classified by the digest of ``content``.

    ``sha256`` overrides the computed digest, which is how a drifted manifest --
    one whose declaration no longer describes the bytes -- is built.
    """
    return {
        "source_id": source_id,
        "source_sha256": sha256 or hashlib.sha256(content).hexdigest(),
        "source_lineage": lineage,
        "season": season,
        "domain": domain,
        "fields": dict(fields or {"margin": DM.ADMITTED, "week": DM.ADMITTED}),
        "dataset_sha256": DATASET_SHA256,
        "split": split,
        "rationale": rationale,
    }


def authority_manifest_payload(**overrides) -> dict:
    """A valid Agent-12 R2 evidence manifest, as a plain dict for a test to edit.

    ``parameter_eligibility`` is empty by default. The manifest is the authority
    wherever it speaks, so a test that does not care about eligibility gets the
    run-local classification unchanged rather than having to restate all eight
    parameters to keep them where they were.
    """
    payload = {
        "manifest_id": "V3-AGENT12-R2-EVIDENCE-TEST",
        "generation": CURRENT_AUTHORITY_GENERATION,
        "supersedes": [],
        "sources": [],
        "forbidden_fields": list(FORBIDDEN_DATASET_SIGNALS),
        "parameter_eligibility": {},
        "dataset_binding": {
            "dataset_sha256": DATASET_SHA256,
            "split_sha256": SPLIT_SHA256,
        },
    }
    payload.update(overrides)
    return payload


def wave1_package_payload(**overrides) -> dict:
    """A Wave-1 result package, as a plain dict for a test to edit."""
    payload = {
        "package_id": "V3-WAVE1-TEST",
        "bindings": {
            "execution_commit": "0" * 40,
            "execution_tree": "tree" + "0" * 60,
            "evidence_manifest_sha256": "m" * 64,
            "dataset_sha256": DATASET_SHA256,
            "split_sha256": SPLIT_SHA256,
            "candidate_universe_digest": "u" * 64,
            "scoring_oracle_digest": "o" * 64,
            "experiment_config_sha256": "e" * 64,
            "field_admission_sha256": "f" * 64,
        },
        "results": {
            "blowout_treatment": {"status": "FIT_RESULT", "value": 0.42},
            "sample_size_regularization": {"status": "FIT_RESULT", "value": 0.31},
        },
    }
    payload.update(overrides)
    return payload


def publish_bytes(relative: str, content: bytes) -> tuple[Path, str]:
    """Commit arbitrary bytes at ``relative`` and return ``(repo, commit)``."""
    root = repo()
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    _run(root, "add", "--", relative)
    _run(root, "commit", "-q", "-m", f"Publish {relative}")
    return root, _run(root, "rev-parse", "HEAD")
