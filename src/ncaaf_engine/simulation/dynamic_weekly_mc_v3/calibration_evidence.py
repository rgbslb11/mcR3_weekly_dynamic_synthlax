"""Byte-bound evidence binding for the V3 calibration pipeline.

This module closes CAL-R2.

:func:`calibration.register_dataset` reads real bytes and records a real digest,
and :func:`calibration.bind_promotion_evidence` ties a promotion to an experiment
and a dataset. Between those two there is a gap: ``bind_promotion_evidence``
compares ``experiment.dataset_sha256`` against ``dataset.sha256``, and
:class:`~.calibration.CalibrationDataset` is an ordinary frozen dataclass. A
caller can construct one by hand::

    CalibrationDataset(
        dataset_id="HISTORICAL_GAME_RESULT_OBSERVATION_SET",
        path=Path("does/not/exist.csv"),
        sha256="00" * 32,
        rows=1500,
        columns=REQUIRED_OBSERVATION_COLUMNS,
    )

and pair it with an ``ExperimentRecord`` carrying the same string. Every equality
check passes and the promotion returns ``EVIDENCE_BOUND``. Nothing in that path
ever opened a file. The digest is a field that agrees with another field, which
is self-attestation, not evidence.

The fix is not a stronger equality check between two caller-supplied strings. It
is to re-derive the evidence from bytes at binding time. Every gate here reads
the file again and recomputes; a receipt whose bytes have moved, changed or never
existed fails, and it fails at the point of binding rather than at review.

Ten bindings are required before an envelope may be cited toward a future
canonical promotion, and they are exactly the ten the lane instruction names:
actual bytes, SHA-256, source authority, retrieval/mount record, schema, row
count, team identity reconciliation, temporal split, experiment input digest and
experiment output digest. An envelope missing any one of them is refused whole.

Two limits are deliberate:

* This module creates no canonical writer. The strongest result it can produce is
  :data:`EVIDENCE_BOUND_BYTE_VERIFIED`, which is a statement about the evidence,
  not an authorisation to write config. Promotion stays a human gate.
* A source that declares its own scores synthetic or simulated is refused at
  mount, under the contract's ``synthetic_content`` requirement. This is a
  registration-time refusal, not a review-time note, because a simulated
  observation set that reaches an experiment has already contaminated it.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .calibration import (
    CalibrationDataset,
    ExperimentRecord,
    CandidateRegime,
    PRIMARY_CALIBRATION_METRIC,
    bind_promotion_evidence,
    register_dataset,
    require_temporal_split_integrity,
)
from .calibration_contract import MINIMUM_VOLUME_REQUIREMENTS as MINIMUM_VOLUME
from .errors import GovernanceBlock, InputValidationError

__all__ = [
    "ADMISSIBLE_SOURCE_AUTHORITY_CLASSES",
    "EVIDENCE_BOUND_BYTE_VERIFIED",
    "EVIDENCE_REFUSED_NOT_BYTE_BOUND",
    "EvidenceEnvelope",
    "IdentityReconciliation",
    "MountReceipt",
    "MountedDataset",
    "REQUIRED_ENVELOPE_BINDINGS",
    "SOURCE_AUTHORITY_CLASSES",
    "SYNTHETIC_PROVENANCE_PATTERNS",
    "bind_canonical_promotion_evidence",
    "mount_raw_source",
    "register_governed_dataset",
    "require_byte_bound_dataset",
    "require_minimum_volume",
    "verify_mount_receipt",
]


#: How a named result source is classified. Only one class is admissible.
SOURCE_AUTHORITY_CLASSES = (
    "GOVERNED_RESULT_SOURCE",
    "RESEARCH_ONLY",
    "ENGINE_OUTPUT",
    "SIMULATED_OR_SYNTHETIC",
    "UNKNOWN",
)

#: The contract requires a *result* source. Research-only corpora, engine output
#: and simulated ledgers are all refused, and ``UNKNOWN`` is refused rather than
#: assumed benign: an unclassified source is the one nobody has checked.
ADMISSIBLE_SOURCE_AUTHORITY_CLASSES = ("GOVERNED_RESULT_SOURCE",)

#: Matched as case-folded substrings against the source's own declared provenance
#: text. Substring matching is deliberate, for the same reason the forbidden-signal
#: denylist uses it: "SCORES SIMULATED" and "scores were simulated" are the same
#: refusal, and a source that renames the sentence has not changed what it is.
SYNTHETIC_PROVENANCE_PATTERNS = (
    "synthetic",
    "simulated",
    "simulation",
    "monte carlo",
    "score_synth",
    "fabricated",
    "fictional",
    "user-specified",
    "engine output",
)

#: The ten bindings a promotable envelope must carry.
REQUIRED_ENVELOPE_BINDINGS = (
    "actual_bytes",
    "sha256",
    "source_authority",
    "retrieval_record",
    "schema",
    "row_count",
    "team_identity_reconciliation",
    "temporal_split",
    "experiment_input_digest",
    "experiment_output_digest",
)

EVIDENCE_BOUND_BYTE_VERIFIED = "EVIDENCE_BOUND_BYTES_REVERIFIED_AT_BINDING"
EVIDENCE_REFUSED_NOT_BYTE_BOUND = "EVIDENCE_REFUSED_NOT_BYTE_BOUND"

_ISO8601 = re.compile(
    r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_digest(payload: Mapping[str, Any]) -> str:
    """Digest a mapping deterministically.

    ``sort_keys`` plus a fixed separator set means the digest depends on the
    content and not on dictionary insertion order, so the same envelope digests
    the same way in a later process.
    """
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return _sha256_bytes(text.encode("utf-8"))


def _refuse_synthetic(declared_provenance: str, source_authority: str) -> None:
    lowered = declared_provenance.casefold()
    hits = sorted({p for p in SYNTHETIC_PROVENANCE_PATTERNS if p in lowered})
    if hits:
        raise GovernanceBlock(
            f"Source {source_authority!r} declares provenance "
            f"{declared_provenance!r}, which matches {hits}. The calibration data "
            "contract refuses synthetic and simulated observation sets outright: a "
            "simulated margin measures the generator that produced it, not football, "
            "and fitting game_sd_points to it would report the generator's variance "
            "as an observed one."
        )


@dataclass(frozen=True)
class MountReceipt:
    """Proof that named bytes were read from a named place at a named time.

    Built only by :func:`mount_raw_source`, which reads the file. Constructing one
    by hand is possible and pointless: every consumer re-reads ``path`` and
    recompares ``sha256`` before relying on it.
    """

    path: Path
    sha256: str
    byte_length: int
    source_authority: str
    source_authority_class: str
    retrieval_method: str
    retrieved_at: str
    declared_provenance: str

    def __post_init__(self) -> None:
        if self.source_authority_class not in SOURCE_AUTHORITY_CLASSES:
            raise InputValidationError(
                f"Unknown source authority class {self.source_authority_class!r}; "
                f"expected one of {list(SOURCE_AUTHORITY_CLASSES)}"
            )
        if not self.source_authority.strip():
            raise InputValidationError(
                "A mount receipt must name its source authority. An unnamed source "
                "cannot be independently re-queried, which is the whole point of "
                "recording it."
            )
        if not _ISO8601.match(self.retrieved_at.strip()):
            raise InputValidationError(
                f"retrieved_at {self.retrieved_at!r} is not an ISO-8601 instant with "
                "an explicit offset. A retrieval time without a zone cannot order a "
                "retrieval against an observation."
            )
        if not self.retrieval_method.strip():
            raise InputValidationError(
                "A mount receipt must record how the bytes were obtained, "
                "reproducibly."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "sha256": self.sha256,
            "byte_length": self.byte_length,
            "source_authority": self.source_authority,
            "source_authority_class": self.source_authority_class,
            "retrieval_method": self.retrieval_method,
            "retrieved_at": self.retrieved_at,
            "declared_provenance": self.declared_provenance,
        }


def mount_raw_source(
    path: Path,
    *,
    source_authority: str,
    source_authority_class: str,
    retrieval_method: str,
    retrieved_at: str,
    declared_provenance: str,
) -> MountReceipt:
    """Read a raw source file and issue a receipt bound to its bytes.

    Refuses before hashing when the authority class is inadmissible or the source
    declares itself synthetic, so a refused source never acquires a digest that
    could later be quoted as though it had been accepted.
    """
    if source_authority_class not in ADMISSIBLE_SOURCE_AUTHORITY_CLASSES:
        raise GovernanceBlock(
            f"Source {source_authority!r} is classified {source_authority_class!r}. "
            f"Only {list(ADMISSIBLE_SOURCE_AUTHORITY_CLASSES)} may be mounted as "
            "governed calibration evidence; research-only corpora, engine output and "
            "simulated ledgers are refused at mount, not at review."
        )
    _refuse_synthetic(declared_provenance, source_authority)

    if not path.exists():
        raise GovernanceBlock(
            f"Raw source for {source_authority!r} not found at {path}. A mount "
            "receipt is a statement about bytes; there are none."
        )
    data = path.read_bytes()
    if not data:
        raise GovernanceBlock(
            f"Raw source for {source_authority!r} at {path} is empty. An empty file "
            "has a valid digest and no evidence in it."
        )
    return MountReceipt(
        path=path,
        sha256=_sha256_bytes(data),
        byte_length=len(data),
        source_authority=source_authority,
        source_authority_class=source_authority_class,
        retrieval_method=retrieval_method,
        retrieved_at=retrieved_at,
        declared_provenance=declared_provenance,
    )


def verify_mount_receipt(receipt: MountReceipt) -> None:
    """Re-read the receipted bytes and refuse any drift.

    This is the gate that makes a receipt worth more than the string it carries.
    """
    if not receipt.path.exists():
        raise GovernanceBlock(
            f"Mount receipt for {receipt.source_authority!r} cites {receipt.path}, "
            "which no longer exists. Evidence that cannot be re-read is not evidence."
        )
    data = receipt.path.read_bytes()
    actual = _sha256_bytes(data)
    if actual != receipt.sha256:
        raise GovernanceBlock(
            f"Mount receipt for {receipt.source_authority!r} records sha256 "
            f"{receipt.sha256} but {receipt.path} now hashes to {actual}. The cited "
            "bytes are not the present bytes."
        )
    if len(data) != receipt.byte_length:
        raise GovernanceBlock(
            f"Mount receipt for {receipt.source_authority!r} records "
            f"{receipt.byte_length} bytes but {receipt.path} holds {len(data)}."
        )


@dataclass(frozen=True)
class MountedDataset:
    """A registered dataset paired with the receipt for the bytes behind it.

    :func:`calibration.register_dataset` returns a :class:`CalibrationDataset`,
    which is the schema-and-digest view. This pairs it with the provenance view.
    The strong promotion path accepts only this type, so a hand-built
    ``CalibrationDataset`` cannot enter it.
    """

    dataset: CalibrationDataset
    receipt: MountReceipt

    def __post_init__(self) -> None:
        if self.dataset.sha256 != self.receipt.sha256:
            raise GovernanceBlock(
                f"Dataset {self.dataset.dataset_id} registers sha256 "
                f"{self.dataset.sha256} but its mount receipt records "
                f"{self.receipt.sha256}. Two digests for one file means at least one "
                "of them describes something else."
            )


def register_governed_dataset(
    path: Path,
    dataset_id: str,
    *,
    source_authority: str,
    source_authority_class: str,
    retrieval_method: str,
    retrieved_at: str,
    declared_provenance: str,
    fmt: str | None = None,
) -> MountedDataset:
    """Mount a raw source and register it as a calibration dataset in one step.

    Mounting happens first. A source that fails the authority or synthetic gates
    is refused before the allowlist and schema checks run, so an inadmissible
    corpus never gets far enough to produce a partially-valid registration record.
    """
    receipt = mount_raw_source(
        path,
        source_authority=source_authority,
        source_authority_class=source_authority_class,
        retrieval_method=retrieval_method,
        retrieved_at=retrieved_at,
        declared_provenance=declared_provenance,
    )
    dataset = register_dataset(path, dataset_id, fmt=fmt)
    return MountedDataset(dataset=dataset, receipt=receipt)


def require_byte_bound_dataset(mounted: MountedDataset) -> dict[str, Any]:
    """Re-derive a registered dataset from disk and confirm it still matches.

    Re-registration, not just re-hashing: the schema and the row count are
    recomputed too. A file whose bytes are unchanged has an unchanged digest by
    construction, but re-registering also re-runs the allowlist, duplicate-column,
    ragged-row and forbidden-signal gates against the bytes actually present now.
    """
    if not isinstance(mounted, MountedDataset):  # pragma: no cover - defensive
        raise GovernanceBlock(
            f"{EVIDENCE_REFUSED_NOT_BYTE_BOUND}: expected a MountedDataset carrying a "
            "mount receipt, got a bare dataset object. CAL-R2: a CalibrationDataset "
            "whose digest is supplied by its caller attests to itself."
        )
    verify_mount_receipt(mounted.receipt)
    reread = register_dataset(mounted.dataset.path, mounted.dataset.dataset_id)
    if reread.sha256 != mounted.dataset.sha256:
        raise GovernanceBlock(
            f"Dataset {mounted.dataset.dataset_id} re-reads to sha256 {reread.sha256}, "
            f"not the registered {mounted.dataset.sha256}."
        )
    if reread.rows != mounted.dataset.rows:
        raise GovernanceBlock(
            f"Dataset {mounted.dataset.dataset_id} registered {mounted.dataset.rows} "
            f"observations but re-reads to {reread.rows}."
        )
    if tuple(reread.columns) != tuple(mounted.dataset.columns):
        raise GovernanceBlock(
            f"Dataset {mounted.dataset.dataset_id} registered schema "
            f"{list(mounted.dataset.columns)} but re-reads to {list(reread.columns)}."
        )
    return {
        "dataset_id": mounted.dataset.dataset_id,
        "sha256": reread.sha256,
        "rows": reread.rows,
        "schema": tuple(reread.columns),
        "bytes_reverified": True,
    }


@dataclass(frozen=True)
class IdentityReconciliation:
    """How free-text source names were resolved to canonical team identity.

    ``unresolved`` is carried rather than dropped. The contract refuses free-text
    names; a reconciliation that silently discarded the names it could not resolve
    would report a clean mapping over a quietly smaller universe.
    """

    authority: str
    authority_sha256: str
    source_names: int
    resolved: int
    unresolved: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.authority.strip():
            raise InputValidationError(
                "Identity reconciliation must name the canonical identity authority."
            )
        if len(self.authority_sha256) != 64:
            raise InputValidationError(
                f"Identity authority digest {self.authority_sha256!r} is not a "
                "SHA-256. The authority is an artifact; it is pinned by its bytes."
            )
        if self.resolved > self.source_names:
            raise InputValidationError(
                f"Identity reconciliation resolves {self.resolved} of "
                f"{self.source_names} source names, which is more than were offered."
            )

    @property
    def complete(self) -> bool:
        return not self.unresolved and self.resolved == self.source_names

    def as_dict(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "authority_sha256": self.authority_sha256,
            "source_names": self.source_names,
            "resolved": self.resolved,
            "unresolved": list(self.unresolved),
            "complete": self.complete,
        }


def require_minimum_volume(
    *,
    distinct_seasons: int,
    total_observations: int,
    holdout_observations: int,
    min_weeks_per_team_per_season: int,
) -> dict[str, Any]:
    """Enforce the contract's stated minimum volume.

    The contract states these minimums and gives a reason for each, but until now
    nothing refused a corpus that failed them. A single season cannot produce
    three temporally ordered partitions no matter how the split is written, and a
    holdout too small to survive a handful of blowouts reports noise as an
    out-of-sample result.
    """
    failures: list[str] = []
    if distinct_seasons < MINIMUM_VOLUME["minimum_distinct_seasons"]:
        failures.append(
            f"distinct_seasons={distinct_seasons} < "
            f"{MINIMUM_VOLUME['minimum_distinct_seasons']} "
            f"({MINIMUM_VOLUME['minimum_distinct_seasons_reason']})"
        )
    if total_observations < MINIMUM_VOLUME["minimum_observations_total"]:
        failures.append(
            f"total_observations={total_observations} < "
            f"{MINIMUM_VOLUME['minimum_observations_total']} "
            f"({MINIMUM_VOLUME['minimum_observations_total_reason']})"
        )
    if holdout_observations < MINIMUM_VOLUME["minimum_holdout_observations"]:
        failures.append(
            f"holdout_observations={holdout_observations} < "
            f"{MINIMUM_VOLUME['minimum_holdout_observations']} "
            f"({MINIMUM_VOLUME['minimum_holdout_observations_reason']})"
        )
    if min_weeks_per_team_per_season < MINIMUM_VOLUME["minimum_weeks_per_team_per_season"]:
        failures.append(
            f"min_weeks_per_team_per_season={min_weeks_per_team_per_season} < "
            f"{MINIMUM_VOLUME['minimum_weeks_per_team_per_season']} "
            f"({MINIMUM_VOLUME['minimum_weeks_per_team_per_season_reason']})"
        )
    if failures:
        raise GovernanceBlock(
            "Calibration corpus does not meet the contract's minimum volume: "
            + "; ".join(failures)
        )
    return {
        "distinct_seasons": distinct_seasons,
        "total_observations": total_observations,
        "holdout_observations": holdout_observations,
        "min_weeks_per_team_per_season": min_weeks_per_team_per_season,
        "minimum_volume_satisfied": True,
    }


@dataclass(frozen=True)
class EvidenceEnvelope:
    """All ten bindings, or nothing.

    ``digest()`` covers every binding, so an envelope quoted in a promotion record
    can be recomputed by a reviewer and compared. Changing any binding changes the
    digest; that is the point.
    """

    mounted: MountedDataset
    identity: IdentityReconciliation
    temporal_split: Mapping[str, Any]
    experiment_input_digest: str
    experiment_output_digest: str
    volume: Mapping[str, Any]
    bindings: tuple[str, ...] = field(default=REQUIRED_ENVELOPE_BINDINGS)

    def __post_init__(self) -> None:
        missing = [b for b in REQUIRED_ENVELOPE_BINDINGS if b not in self.bindings]
        if missing:
            raise GovernanceBlock(
                f"Evidence envelope is missing required bindings {missing}. An "
                "envelope is refused whole rather than accepted in part: a partial "
                "chain reads as a complete one once it is summarised."
            )
        for name, digest in (
            ("experiment_input_digest", self.experiment_input_digest),
            ("experiment_output_digest", self.experiment_output_digest),
        ):
            if len(digest) != 64:
                raise InputValidationError(
                    f"{name} {digest!r} is not a SHA-256."
                )
        if not self.temporal_split.get("leak_free"):
            raise GovernanceBlock(
                "Evidence envelope carries a temporal split that is not marked "
                "leak-free."
            )

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.mounted.dataset.dataset_id,
            "dataset_sha256": self.mounted.dataset.sha256,
            "dataset_rows": self.mounted.dataset.rows,
            "dataset_schema": list(self.mounted.dataset.columns),
            "mount_receipt": self.mounted.receipt.as_dict(),
            "identity_reconciliation": self.identity.as_dict(),
            "temporal_split": dict(self.temporal_split),
            "minimum_volume": dict(self.volume),
            "experiment_input_digest": self.experiment_input_digest,
            "experiment_output_digest": self.experiment_output_digest,
            "bindings": list(self.bindings),
        }

    def digest(self) -> str:
        return _canonical_digest(self.as_dict())


def bind_evidence_envelope(
    mounted: MountedDataset,
    *,
    identity: IdentityReconciliation,
    ordered_events: Mapping[str, tuple[str, str]],
    experiment_inputs: Mapping[str, Any],
    experiment_outputs: Mapping[str, Any],
    distinct_seasons: int,
    min_weeks_per_team_per_season: int,
) -> EvidenceEnvelope:
    """Assemble and validate the full ten-part envelope.

    Order matters. Bytes are re-verified first, because every later binding is a
    statement about those bytes; the temporal split is proved before volume is
    counted, because the holdout count is only meaningful once the holdout is
    known to be a holdout.
    """
    reread = require_byte_bound_dataset(mounted)
    if not identity.complete:
        raise GovernanceBlock(
            f"Identity reconciliation for {mounted.dataset.dataset_id} leaves "
            f"{len(identity.unresolved)} source name(s) unresolved: "
            f"{list(identity.unresolved)[:10]}. The contract refuses free-text team "
            "names, so an unresolved name is an unusable observation, not a warning."
        )
    split = require_temporal_split_integrity(dict(ordered_events))
    volume = require_minimum_volume(
        distinct_seasons=distinct_seasons,
        total_observations=reread["rows"],
        holdout_observations=split["splits"]["holdout"],
        min_weeks_per_team_per_season=min_weeks_per_team_per_season,
    )
    return EvidenceEnvelope(
        mounted=mounted,
        identity=identity,
        temporal_split=split,
        experiment_input_digest=_canonical_digest(dict(experiment_inputs)),
        experiment_output_digest=_canonical_digest(dict(experiment_outputs)),
        volume=volume,
    )


def bind_canonical_promotion_evidence(
    regime: CandidateRegime,
    *,
    experiment: ExperimentRecord,
    envelope: EvidenceEnvelope,
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """The strongest binding this lane can produce. It still promotes nothing.

    Runs the existing R2 checks — regime match, dataset match, holdout split,
    primary metric present and agreeing — and then adds what CAL-R2 was missing:
    the dataset behind those checks is re-read from disk, its schema and row count
    are recomputed, its source authority is re-asserted, and the envelope digest
    is recorded so the whole chain can be recomputed later.

    The return value carries :data:`EVIDENCE_BOUND_BYTE_VERIFIED`. That is a
    description of the evidence, not an approval. Writing canonical configuration
    remains outside this module, and outside this lane.
    """
    require_byte_bound_dataset(envelope.mounted)
    if envelope.mounted.receipt.source_authority_class not in (
        ADMISSIBLE_SOURCE_AUTHORITY_CLASSES
    ):  # pragma: no cover - unreachable while mount_raw_source is the only builder
        raise GovernanceBlock(
            "Envelope cites a source authority class that is not admissible."
        )

    base = bind_promotion_evidence(
        regime,
        evidence=dict(evidence or {}),
        experiment=experiment,
        dataset=envelope.mounted.dataset,
    )
    if not base.get("evidence_bound"):  # pragma: no cover - defensive
        raise GovernanceBlock(
            f"{EVIDENCE_REFUSED_NOT_BYTE_BOUND}: the R2 binding did not bind."
        )
    if experiment.metrics.get(PRIMARY_CALIBRATION_METRIC) is None:  # pragma: no cover
        raise GovernanceBlock(
            f"Experiment {experiment.experiment_id} carries no "
            f"{PRIMARY_CALIBRATION_METRIC}."
        )
    return {
        **base,
        "evidence_binding": EVIDENCE_BOUND_BYTE_VERIFIED,
        "bytes_reverified_at_binding": True,
        "envelope_digest": envelope.digest(),
        "source_authority": envelope.mounted.receipt.source_authority,
        "source_authority_class": envelope.mounted.receipt.source_authority_class,
        "retrieved_at": envelope.mounted.receipt.retrieved_at,
        "identity_reconciliation_complete": envelope.identity.complete,
        "temporal_split": dict(envelope.temporal_split),
        "minimum_volume": dict(envelope.volume),
        "bindings": list(REQUIRED_ENVELOPE_BINDINGS),
        "writes_canonical_config": False,
        "promotion_authorised": False,
    }
