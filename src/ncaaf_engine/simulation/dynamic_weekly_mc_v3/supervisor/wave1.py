"""Ingesting the Wave-1 calibration result, when there is one.

Agent 3 is producing the V3 synthetic calibration Wave 1 for
``blowout_treatment`` and ``sample_size_regularization`` on
``origin/claude/v3-calibration-orchestrator-r1``. This module is the interface
that will accept it. It is built now and it does not require the result to exist
now, which are both deliberate: an interface written after the artifact arrives
is an interface shaped by that artifact, and a supervisor that refuses to plan
until a result exists cannot be used to decide whether to produce it.

Absence is therefore a state, not an error. :func:`ingest` returns
:data:`WAVE1_NOT_PRESENT` when the ref resolves and the tree holds nothing at
the declared path, and ``plan`` reports that verbatim. What absence never does is
authorise anything: the two Wave-1 parameters keep whatever disposition the
evidence manifest gives them, and no stage reads a value that was not ingested.

Ten bindings, all verified, none self-attested
-----------------------------------------------

A result package that says "I was produced correctly" is not evidence that it
was. So every binding is compared against what the *supervisor* independently
holds -- the dataset and split it registered, the candidate universe it
enumerated, the oracle digest it computed, the evidence manifest it resolved
from the object store -- rather than against another field of the same package.
The ten are: execution commit, execution tree, evidence manifest, dataset,
split, candidate universe, scoring oracle, experiment config, field admission
artifact, and the per-parameter result status.

The package is read out of the git object store at a pinned commit, exactly as
the evidence manifest is, and for the same reason: a result read from a
checked-out worktree is a result whose content depends on when somebody looked.
No path inside the orchestrator's worktree is constructed anywhere in this
module.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import GovernanceBlock, InputValidationError
from .authority import COMMIT_SHA, resolve_ref
from .digests import sha256_bytes

__all__ = [
    "WAVE1_ACCEPTED",
    "WAVE1_NOT_PRESENT",
    "WAVE1_PARAMETERS",
    "WAVE1_REF",
    "Wave1Binding",
    "Wave1Expectation",
    "Wave1Package",
    "ingest",
    "parse_package",
]

#: The lane that produces the result. Recorded so the supervisor's report names
#: the source rather than leaving it to the run manifest's configuration dump.
WAVE1_REF = "origin/claude/v3-calibration-orchestrator-r1"

#: What Wave 1 is entitled to settle. A package claiming a result for anything
#: else is refused; Wave 1 is a scoped experiment, not a channel.
WAVE1_PARAMETERS: tuple[str, ...] = ("blowout_treatment", "sample_size_regularization")

#: The ref resolves and its tree holds no package. Not an error.
WAVE1_NOT_PRESENT = "WAVE1_NOT_PRESENT"

#: A package was found and every binding matched.
WAVE1_ACCEPTED = "WAVE1_ACCEPTED"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: Statuses a Wave-1 package may report per parameter. ``FIT_RESULT`` is the
#: only one that carries a value, and it is checked rather than assumed.
_RESULT_STATUSES: tuple[str, ...] = (
    "FIT_RESULT",
    "UNIDENTIFIED",
    "CIRCULAR_NOT_IDENTIFIABLE",
    "MISSING_FAIL_CLOSED",
)


@dataclass(frozen=True)
class Wave1Binding:
    """Where the Wave-1 package lives, as configuration declares it."""

    ref: str = WAVE1_REF
    path: str = ""
    commit: str = ""
    repo: Path | None = None

    def __post_init__(self) -> None:
        if not self.ref.strip():
            raise InputValidationError("Wave-1 binding names no ref.")
        if self.commit and not COMMIT_SHA.match(self.commit):
            raise InputValidationError(
                f"Pinned Wave-1 commit {self.commit!r} is not a 40-character SHA."
            )

    @property
    def declared(self) -> bool:
        """Whether configuration asked for Wave-1 ingestion at all."""
        return bool(self.path.strip())

    def as_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "path": self.path,
            "pinned_commit": self.commit,
            "repo": None if self.repo is None else str(self.repo),
            "parameters": list(WAVE1_PARAMETERS),
        }


@dataclass(frozen=True)
class Wave1Expectation:
    """What the supervisor independently holds, to compare the package against.

    Every field here is derived by this run. None of it is read out of the
    package, which is what makes the comparison evidence rather than a checksum
    of the package against itself.
    """

    execution_commit: str
    execution_tree: str
    evidence_manifest_sha256: str
    dataset_sha256: str
    split_sha256: str
    candidate_universe_digest: str
    scoring_oracle_digest: str
    experiment_config_sha256: str
    field_admission_sha256: str

    def as_dict(self) -> dict[str, str]:
        return {
            "execution_commit": self.execution_commit,
            "execution_tree": self.execution_tree,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "dataset_sha256": self.dataset_sha256,
            "split_sha256": self.split_sha256,
            "candidate_universe_digest": self.candidate_universe_digest,
            "scoring_oracle_digest": self.scoring_oracle_digest,
            "experiment_config_sha256": self.experiment_config_sha256,
            "field_admission_sha256": self.field_admission_sha256,
        }


@dataclass(frozen=True)
class Wave1Package:
    """A SHA-bound Wave-1 result, as read from the object store."""

    package_id: str
    execution_commit: str
    execution_tree: str
    evidence_manifest_sha256: str
    dataset_sha256: str
    split_sha256: str
    candidate_universe_digest: str
    scoring_oracle_digest: str
    experiment_config_sha256: str
    field_admission_sha256: str
    results: dict[str, dict[str, Any]] = field(default_factory=dict)
    package_sha256: str = ""
    read_from_commit: str = ""

    def __post_init__(self) -> None:
        if not COMMIT_SHA.match(self.execution_commit.lower()):
            raise InputValidationError(
                f"Wave-1 package declares execution_commit "
                f"{self.execution_commit!r}, which is not a 40-character commit SHA."
            )
        unknown = sorted(set(self.results) - set(WAVE1_PARAMETERS))
        if unknown:
            raise GovernanceBlock(
                f"Wave-1 package reports results for {unknown}, which Wave 1 is not "
                f"scoped to settle. Its scope is {list(WAVE1_PARAMETERS)}."
            )
        for name, entry in sorted(self.results.items()):
            status = str(entry.get("status", ""))
            if status not in _RESULT_STATUSES:
                raise InputValidationError(
                    f"Wave-1 result for {name} declares status {status!r}; expected one "
                    f"of {list(_RESULT_STATUSES)}."
                )
            if status == "FIT_RESULT" and entry.get("value") is None:
                raise GovernanceBlock(
                    f"Wave-1 reports {name} as FIT_RESULT with no value. A fit result "
                    "is a measurement, and a measurement has a number."
                )
            if status != "FIT_RESULT" and entry.get("value") is not None:
                raise GovernanceBlock(
                    f"Wave-1 reports {name} as {status} yet carries the value "
                    f"{entry.get('value')!r}. A non-fit status must not also report a "
                    "measurement."
                )

    def bindings(self) -> dict[str, str]:
        return {
            "execution_commit": self.execution_commit.lower(),
            "execution_tree": self.execution_tree,
            "evidence_manifest_sha256": self.evidence_manifest_sha256,
            "dataset_sha256": self.dataset_sha256,
            "split_sha256": self.split_sha256,
            "candidate_universe_digest": self.candidate_universe_digest,
            "scoring_oracle_digest": self.scoring_oracle_digest,
            "experiment_config_sha256": self.experiment_config_sha256,
            "field_admission_sha256": self.field_admission_sha256,
        }

    def verify(self, expected: Wave1Expectation) -> dict[str, Any]:
        """Compare all nine bindings and the result statuses, or refuse.

        The drift report names both sides of every mismatch. "Refused" without
        the two values is a dead end for whoever has to decide whether the
        package or the run is the thing that moved.
        """
        mine, theirs = self.bindings(), expected.as_dict()
        drift = {
            name: {"package": mine[name], "run": theirs[name]}
            for name in sorted(theirs)
            if mine[name].lower() != theirs[name].lower()
        }
        if drift:
            raise GovernanceBlock(
                f"Wave-1 package {self.package_id} is bound to a different world than "
                f"this run. Drift: {drift}. A calibration result produced against "
                "another dataset, split, candidate universe, oracle or code tree is a "
                "result about another experiment."
            )
        return {
            "status": WAVE1_ACCEPTED,
            "package_id": self.package_id,
            "package_sha256": self.package_sha256,
            "read_from_commit": self.read_from_commit,
            "bindings": mine,
            "results": {
                name: dict(entry) for name, entry in sorted(self.results.items())
            },
            "parameters_reported": sorted(self.results),
            "parameters_absent": sorted(set(WAVE1_PARAMETERS) - set(self.results)),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "package_id": self.package_id,
            **self.bindings(),
            "results": {name: dict(e) for name, e in sorted(self.results.items())},
            "package_sha256": self.package_sha256,
            "read_from_commit": self.read_from_commit,
        }


def parse_package(data: bytes, *, read_from_commit: str = "") -> Wave1Package:
    """Parse package bytes and digest them.

    ``package_sha256`` is computed here from the bytes read, never taken from a
    field inside the package. A package that carried and was trusted for its own
    digest would be self-attesting.
    """
    raw = json.loads(data.decode("utf-8"))
    bindings = raw.get("bindings", raw)
    declared = str(raw.get("package_sha256", "")).lower()
    digest = sha256_bytes(data)
    if declared and _SHA256.match(declared) and declared != digest:
        raise GovernanceBlock(
            f"Wave-1 package declares package_sha256 {declared} and its bytes digest to "
            f"{digest}. The declaration describes a different artifact."
        )
    return Wave1Package(
        package_id=str(raw.get("package_id", "")),
        execution_commit=str(bindings.get("execution_commit", "")).lower(),
        execution_tree=str(bindings.get("execution_tree", "")),
        evidence_manifest_sha256=str(bindings.get("evidence_manifest_sha256", "")),
        dataset_sha256=str(bindings.get("dataset_sha256", "")),
        split_sha256=str(bindings.get("split_sha256", "")),
        candidate_universe_digest=str(bindings.get("candidate_universe_digest", "")),
        scoring_oracle_digest=str(bindings.get("scoring_oracle_digest", "")),
        experiment_config_sha256=str(bindings.get("experiment_config_sha256", "")),
        field_admission_sha256=str(bindings.get("field_admission_sha256", "")),
        results={
            str(k): dict(v) for k, v in sorted(dict(raw.get("results", {})).items())
        },
        package_sha256=digest,
        read_from_commit=read_from_commit,
    )


def ingest(
    binding: Wave1Binding,
    expected: Wave1Expectation | None = None,
    *,
    repo: Path | None = None,
) -> dict[str, Any]:
    """Read and verify the Wave-1 package, or report that there is none.

    ``expected`` may be ``None`` in plan mode, where the run has not registered a
    dataset or enumerated a candidate universe and therefore has nothing
    truthful to compare against. In that mode a present package is reported as
    found and explicitly *not* verified, so a plan can never read as an
    acceptance.
    """
    if not binding.declared:
        return {
            "status": WAVE1_NOT_PRESENT,
            "verified": False,
            "reason": (
                "No Wave-1 package path is declared in configuration. The interface "
                "exists and is unused; the two Wave-1 parameters keep the disposition "
                "the evidence manifest gives them."
            ),
            **binding.as_dict(),
        }

    from .authority import read_blob

    target = Path(repo or binding.repo or Path.cwd())
    commit = resolve_ref(target, binding.ref)
    if binding.commit and binding.commit != commit:
        raise GovernanceBlock(
            f"Wave-1 ref {binding.ref} is pinned to {binding.commit} and now resolves "
            f"to {commit}. A result package is ingested from the commit it was pinned "
            "to, not from wherever the branch has since moved."
        )
    try:
        content = read_blob(target, commit, binding.path)
    except GovernanceBlock as exc:
        return {
            "status": WAVE1_NOT_PRESENT,
            "verified": False,
            "resolved_commit": commit,
            "reason": (
                f"{binding.ref} resolves to {commit} and that commit's tree holds "
                f"nothing at {binding.path}. Wave 1 has not published a result yet. "
                f"Detail: {exc}"
            ),
            **binding.as_dict(),
        }

    package = parse_package(content, read_from_commit=commit)
    if expected is None:
        return {
            "status": "WAVE1_PRESENT_NOT_VERIFIED",
            "verified": False,
            "resolved_commit": commit,
            "reason": (
                "A package was found. Plan mode registers no dataset and enumerates no "
                "candidate universe, so there is nothing to verify it against and it is "
                "reported unverified rather than accepted."
            ),
            "package": package.as_dict(),
            **binding.as_dict(),
        }
    return {**package.verify(expected), "verified": True, **binding.as_dict()}
