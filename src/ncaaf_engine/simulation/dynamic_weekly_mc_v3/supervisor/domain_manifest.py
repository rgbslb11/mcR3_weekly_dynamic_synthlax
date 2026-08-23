"""The authoritative primary-domain gate: the Agent-12 R2 evidence manifest.

R1 decided what a file was by looking at what it was called. Four naming
patterns caught ``REAL_2023``, ``2023``, ``OBSERVED_2023`` and ``HISTORICAL_2023``,
and that was the whole of the domain check. It is a real check and it catches a
real class of mistake, but it is not a gate: renaming a file defeats it, and a
doctrine that a rename defeats is a convention.

So the authority moves here. The frozen Agent-12 R2 evidence manifest classifies
every admissible source **by the SHA-256 of its bytes**, and this module is the
only thing entitled to answer "may this source estimate the primary parameter
vector". The answer comes from manifest lineage and declared eligibility. It
never comes from a filename, and there is no code path by which it could: the
lookup key is a content digest computed from the bytes actually read, so a real
2023 observation corpus saved as ``synthetic_2025_estimation_table.json`` hashes
to exactly what it hashed to before and classifies exactly as it did before.

The naming patterns in :mod:`.evidence` stay, demoted to what they always
actually were -- defence in depth. They now run *after* the manifest decision
and can only add a refusal, never remove one. :data:`FILENAME_CHECKS_ROLE`
records that, so the next reader does not have to reconstruct which of the two
is load-bearing.

What the manifest must carry
-----------------------------

Eight things, all verified at load, because each is a distinct way a source can
be wrong while looking right:

``source_sha256``       the bytes, so a rename cannot change the classification
``source_lineage``      how the rows came to exist -- generated, observed, model output
``season``              which season the rows describe
``domain``              primary estimation, external witness, or inadmissible
``fields``              per-field admission, so a permitted source cannot smuggle a forbidden column
``forbidden_fields``    the manifest-level list, refused on every source regardless of its own claims
``parameter_eligibility`` which parameters this evidence is entitled to support
``dataset``/``split``   which registered dataset and split the source belongs to

Lineage and domain are cross-checked rather than trusted independently. A source
whose lineage is observed real football and whose domain claims primary
estimation does not load at all -- not "is refused at use", *does not load* --
because a manifest that can hold that combination is a manifest whose remaining
claims mean nothing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from ..calibration import FORBIDDEN_DATASET_SIGNALS
from ..errors import GovernanceBlock, InputValidationError
from . import evidence as EV
from .authority import (
    CURRENT_AUTHORITY_GENERATION,
    ResolvedAuthority,
    authority_rank,
    require_current_authority,
)
from .digests import digest_mapping, sha256_bytes, sha256_file

__all__ = [
    "ADMITTED",
    "DOMAIN_CLASSES",
    "EXTERNAL_WITNESS_ONLY",
    "EvidenceDomainManifest",
    "FIELD_CLASSES",
    "FILENAME_CHECKS_ROLE",
    "FORBIDDEN",
    "INADMISSIBLE",
    "LINEAGE_CLASSES",
    "PRIMARY_ESTIMATION",
    "REAL_OBSERVED",
    "SourceRecord",
    "SYNTHETIC_GENERATED",
    "load_domain_manifest",
    "load_domain_manifest_from_authority",
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

#: What the real/synthetic naming checks in :mod:`.evidence` are for, now that
#: the manifest decides. They run in addition to the manifest gate and may only
#: add a refusal.
FILENAME_CHECKS_ROLE = "DEFENSE_IN_DEPTH_SECONDARY_NEVER_AUTHORITATIVE"


# --- lineage -----------------------------------------------------------------

#: Rows produced by the synthetic generator for 2024/2025.
SYNTHETIC_GENERATED = "SYNTHETIC_GENERATED_2024_2025"

#: Rows observed from real football, 2021-2024.
REAL_OBSERVED = "REAL_OBSERVED_2021_2024"

#: Rows that are some model's output rather than any kind of observation.
ENGINE_OUTPUT = "ENGINE_OUTPUT"

#: Nobody classified the lineage. Refused, never assumed synthetic.
UNCLASSIFIED_LINEAGE = "UNCLASSIFIED"

LINEAGE_CLASSES: tuple[str, ...] = (
    SYNTHETIC_GENERATED,
    REAL_OBSERVED,
    ENGINE_OUTPUT,
    UNCLASSIFIED_LINEAGE,
)

#: The only lineage that may estimate the primary vector.
_PRIMARY_ELIGIBLE_LINEAGE: tuple[str, ...] = (SYNTHETIC_GENERATED,)


# --- domain ------------------------------------------------------------------

#: The source may estimate the primary synthetic parameter vector.
PRIMARY_ESTIMATION = "PRIMARY_ESTIMATION_DOMAIN"

#: The source may diagnose plausibility and may never select a value.
EXTERNAL_WITNESS_ONLY = EV.EXTERNAL_WITNESS_ONLY

#: The source may not be read for either purpose.
INADMISSIBLE = "INADMISSIBLE"

DOMAIN_CLASSES: tuple[str, ...] = (
    PRIMARY_ESTIMATION,
    EXTERNAL_WITNESS_ONLY,
    INADMISSIBLE,
)

#: Which domain each lineage may hold. Stated as the permitted set rather than
#: as a single mapping, because a synthetic source may legitimately be admitted
#: as a witness while a real one may never be admitted as primary.
_DOMAIN_PERMITTED_FOR_LINEAGE: dict[str, tuple[str, ...]] = {
    SYNTHETIC_GENERATED: (PRIMARY_ESTIMATION, EXTERNAL_WITNESS_ONLY, INADMISSIBLE),
    REAL_OBSERVED: (EXTERNAL_WITNESS_ONLY, INADMISSIBLE),
    ENGINE_OUTPUT: (INADMISSIBLE,),
    UNCLASSIFIED_LINEAGE: (INADMISSIBLE,),
}


# --- fields ------------------------------------------------------------------

#: The field may be read for the source's declared domain.
ADMITTED = "ADMITTED"

#: The field may never be read, whatever the source's domain.
FORBIDDEN = "FORBIDDEN"

#: The field may be read for diagnosis only, never to select a value.
WITNESS_FIELD = "WITNESS_ONLY"

FIELD_CLASSES: tuple[str, ...] = (ADMITTED, FORBIDDEN, WITNESS_FIELD)


@dataclass(frozen=True)
class SourceRecord:
    """One admissible source, classified by the bytes it is made of."""

    source_id: str
    source_sha256: str
    source_lineage: str
    season: str
    domain: str
    fields: dict[str, str] = field(default_factory=dict)
    dataset_sha256: str = ""
    split: str = ""
    rationale: str = ""

    def __post_init__(self) -> None:
        if not _SHA256.match(self.source_sha256.lower()):
            raise InputValidationError(
                f"Source {self.source_id} declares source_sha256 "
                f"{self.source_sha256!r}, which is not a 64-character SHA-256. A "
                "source classified by anything other than its bytes is classified by "
                "its name."
            )
        if self.source_lineage not in LINEAGE_CLASSES:
            raise InputValidationError(
                f"Source {self.source_id} declares unknown lineage "
                f"{self.source_lineage!r}; expected one of {list(LINEAGE_CLASSES)}."
            )
        if self.domain not in DOMAIN_CLASSES:
            raise InputValidationError(
                f"Source {self.source_id} declares unknown domain {self.domain!r}; "
                f"expected one of {list(DOMAIN_CLASSES)}."
            )
        permitted = _DOMAIN_PERMITTED_FOR_LINEAGE[self.source_lineage]
        if self.domain not in permitted:
            raise GovernanceBlock(
                f"Source {self.source_id} is lineage {self.source_lineage} and claims "
                f"domain {self.domain}. That lineage may only hold {list(permitted)}. "
                "Real observed football is EXTERNAL_WITNESS_ONLY under this calibration "
                "doctrine, and a manifest that can say otherwise is not a gate."
            )
        if not self.season.strip():
            raise InputValidationError(f"Source {self.source_id} names no season.")
        unknown = sorted(
            name for name, cls in self.fields.items() if cls not in FIELD_CLASSES
        )
        if unknown:
            raise InputValidationError(
                f"Source {self.source_id} classifies fields {unknown} with an unknown "
                f"class; expected one of {list(FIELD_CLASSES)}."
            )
        if self.domain == PRIMARY_ESTIMATION and not self.split.strip():
            raise GovernanceBlock(
                f"Source {self.source_id} is admitted to {PRIMARY_ESTIMATION} without a "
                "declared split. A source that estimates the vector must say which "
                "partition it belongs to, or temporal split integrity is unprovable."
            )

    @property
    def primary_eligible(self) -> bool:
        return (
            self.domain == PRIMARY_ESTIMATION
            and self.source_lineage in _PRIMARY_ELIGIBLE_LINEAGE
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_sha256": self.source_sha256.lower(),
            "source_lineage": self.source_lineage,
            "season": self.season,
            "domain": self.domain,
            "fields": dict(sorted(self.fields.items())),
            "dataset_sha256": self.dataset_sha256,
            "split": self.split,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class EvidenceDomainManifest:
    """The frozen Agent-12 R2 manifest, and the primary-domain gate itself."""

    manifest_id: str
    generation: str
    authority_commit: str
    sources: tuple[SourceRecord, ...]
    forbidden_fields: tuple[str, ...]
    parameter_eligibility: dict[str, str]
    dataset_sha256: str
    split_sha256: str
    source_bytes_sha256: str
    supersedes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        authority_rank(self.generation)
        require_current_authority(self.generation, subject="primary estimation domain")
        ids = [s.source_id for s in self.sources]
        duplicate_ids = sorted({i for i in ids if ids.count(i) > 1})
        if duplicate_ids:
            raise InputValidationError(
                f"Evidence manifest names sources twice: {duplicate_ids}."
            )
        digests = [s.source_sha256.lower() for s in self.sources]
        duplicate_digests = sorted({d for d in digests if digests.count(d) > 1})
        if duplicate_digests:
            raise GovernanceBlock(
                f"Evidence manifest classifies the same bytes twice: {duplicate_digests}. "
                "One byte sequence has one classification; two would let a caller pick."
            )
        unknown = sorted(set(self.parameter_eligibility) - set(EV.GOVERNED_PARAMETERS))
        if unknown:
            raise InputValidationError(
                f"Evidence manifest declares eligibility for unknown parameters: {unknown}."
            )
        bad = sorted(
            f"{name}={value}"
            for name, value in self.parameter_eligibility.items()
            if value not in EV.ELIGIBILITY_CLASSES
        )
        if bad:
            raise InputValidationError(
                f"Evidence manifest declares unknown eligibility classes: {bad}."
            )
        missing_forbidden = sorted(
            signal
            for signal in FORBIDDEN_DATASET_SIGNALS
            if not any(signal in name for name in self.forbidden_fields)
        )
        if missing_forbidden:
            raise GovernanceBlock(
                "Evidence manifest's forbidden-field list omits governed forbidden "
                f"signals {missing_forbidden}. The manifest may forbid more than the "
                "calibration contract does; it may not forbid less."
            )
        # A field the manifest forbids globally must not be admitted by any
        # source. Checked here rather than at read time so a contradiction is a
        # load failure, not a race between two gates.
        contradictions = sorted(
            f"{source.source_id}.{name}"
            for source in self.sources
            for name, cls in source.fields.items()
            if cls == ADMITTED and self._is_globally_forbidden(name)
        )
        if contradictions:
            raise GovernanceBlock(
                f"Sources admit globally forbidden fields: {contradictions}. The "
                "manifest-level forbidden list is not advisory to its own sources."
            )

    # -- queries ------------------------------------------------------------

    def _is_globally_forbidden(self, field_name: str) -> bool:
        lowered = field_name.lower()
        return any(pattern.lower() in lowered for pattern in self.forbidden_fields)

    def source_for_digest(self, digest: str) -> SourceRecord:
        """The classification of these exact bytes, or a fail-closed refusal.

        An unregistered digest is refused rather than defaulted. A source nobody
        classified is not a source that is probably fine; it is the state of the
        thing nobody checked, and admitting it would restore precisely the hole
        the filename check left.
        """
        key = digest.lower()
        for source in self.sources:
            if source.source_sha256.lower() == key:
                return source
        raise GovernanceBlock(
            f"No source in evidence manifest {self.manifest_id} classifies bytes with "
            f"digest {key}. An unregistered source has no domain, no lineage and no "
            "field admission, so it is refused for every purpose. Register it in the "
            f"{self.generation} manifest or do not read it."
        )

    def classify_path(self, path: str | Path) -> SourceRecord:
        """Classify a file by hashing what is actually on disk.

        The filename is not consulted, is not passed to the lookup, and is not
        recoverable from the key. Renaming the file changes nothing about the
        answer, which is the entire point.
        """
        resolved = Path(path).resolve()
        if not resolved.exists():
            raise InputValidationError(f"Source file not found: {resolved}")
        return self.source_for_digest(sha256_file(resolved))

    def classify_bytes(self, data: bytes) -> SourceRecord:
        return self.source_for_digest(sha256_bytes(data))

    # -- gates --------------------------------------------------------------

    def require_source_bytes_match(self, source_id: str, observed_sha256: str) -> SourceRecord:
        """Refuse a source whose bytes have drifted from what the manifest froze."""
        record = next((s for s in self.sources if s.source_id == source_id), None)
        if record is None:
            raise GovernanceBlock(
                f"Evidence manifest {self.manifest_id} does not classify source "
                f"{source_id!r}."
            )
        if record.source_sha256.lower() != observed_sha256.lower():
            raise GovernanceBlock(
                f"Source {source_id} has drifted. The frozen manifest declares "
                f"{record.source_sha256.lower()} and the bytes read digest to "
                f"{observed_sha256.lower()}. Evidence is the bytes, so a manifest "
                "entry that no longer describes them classifies nothing."
            )
        return record

    def require_primary_estimation_source(self, path: str | Path) -> SourceRecord:
        """Assert these bytes may estimate the primary vector, or refuse.

        Every refusal names the manifest fact that produced it -- lineage or
        declared domain -- so a reader can tell "this file is not admitted" from
        "this file is real football", which are different problems with different
        fixes.
        """
        record = self.classify_path(path)
        if record.source_lineage not in _PRIMARY_ELIGIBLE_LINEAGE:
            raise GovernanceBlock(
                f"Source {record.source_id} is lineage {record.source_lineage} and may "
                f"not estimate the primary parameter vector. Its declared role is "
                f"{record.domain}. This is decided by the manifest's lineage record for "
                "the source's byte digest; the filename it happens to carry is not "
                "consulted and cannot change it."
            )
        if record.domain != PRIMARY_ESTIMATION:
            raise GovernanceBlock(
                f"Source {record.source_id} is admitted as {record.domain}, not "
                f"{PRIMARY_ESTIMATION}. {record.rationale}"
            )
        # Defence in depth, second and never first: the season label the manifest
        # itself records must also survive the naming check. A manifest that
        # classified a real season as synthetic-generated would already have
        # failed the lineage/domain cross-check above; this catches the case
        # where the label and the lineage disagree.
        EV.require_synthetic_only_primary_estimation_domain((record.season,))
        return record

    def require_field_admitted(self, record: SourceRecord, field_name: str) -> None:
        """Refuse a forbidden field even on a source admitted to the primary domain."""
        if self._is_globally_forbidden(field_name):
            raise GovernanceBlock(
                f"Field {field_name!r} is on evidence manifest {self.manifest_id}'s "
                f"forbidden list and may not be read from any source, including "
                f"{record.source_id}, whose lineage is {record.source_lineage}. A "
                "forbidden field is forbidden by what it is, not by which file it "
                "arrived in."
            )
        declared = record.fields.get(field_name)
        if declared is None:
            raise GovernanceBlock(
                f"Field {field_name!r} is not classified on source {record.source_id}. "
                "An unclassified field is refused rather than assumed admitted."
            )
        if declared == FORBIDDEN:
            raise GovernanceBlock(
                f"Field {field_name!r} is {FORBIDDEN} on source {record.source_id}."
            )
        if declared == WITNESS_FIELD and record.domain == PRIMARY_ESTIMATION:
            raise GovernanceBlock(
                f"Field {field_name!r} is {WITNESS_FIELD} and cannot be read from a "
                f"source admitted to {PRIMARY_ESTIMATION}; witness fields diagnose and "
                "never select."
            )

    def require_dataset_binding(self, dataset_sha256: str, split_sha256: str) -> None:
        """Refuse a dataset or split the frozen manifest is not bound to."""
        drift = {}
        if self.dataset_sha256.lower() != dataset_sha256.lower():
            drift["dataset_sha256"] = {
                "manifest": self.dataset_sha256.lower(),
                "observed": dataset_sha256.lower(),
            }
        if self.split_sha256.lower() != split_sha256.lower():
            drift["split_sha256"] = {
                "manifest": self.split_sha256.lower(),
                "observed": split_sha256.lower(),
            }
        if drift:
            raise GovernanceBlock(
                f"The registered calibration dataset is not the one evidence manifest "
                f"{self.manifest_id} classifies its sources against. Drift: {drift}"
            )

    def eligibility(self, parameter: str) -> str:
        """What the current authority says this parameter's eligibility is."""
        try:
            return self.parameter_eligibility[parameter]
        except KeyError:
            raise GovernanceBlock(
                f"Evidence manifest {self.manifest_id} declares no eligibility for "
                f"{parameter!r}. An unclassified parameter is not an implicitly "
                "fittable one."
            ) from None

    def primary_sources(self) -> tuple[SourceRecord, ...]:
        return tuple(s for s in self.sources if s.primary_eligible)

    def witness_sources(self) -> tuple[SourceRecord, ...]:
        return tuple(s for s in self.sources if s.domain == EXTERNAL_WITNESS_ONLY)

    @property
    def manifest_digest(self) -> str:
        return digest_mapping(self.as_dict())

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "generation": self.generation,
            "authority_commit": self.authority_commit,
            "supersedes": list(self.supersedes),
            "sources": [s.as_dict() for s in sorted(self.sources, key=lambda s: s.source_id)],
            "forbidden_fields": sorted(self.forbidden_fields),
            "parameter_eligibility": dict(sorted(self.parameter_eligibility.items())),
            "dataset_sha256": self.dataset_sha256.lower(),
            "split_sha256": self.split_sha256.lower(),
            "source_bytes_sha256": self.source_bytes_sha256,
            "filename_checks_role": FILENAME_CHECKS_ROLE,
        }


def _source_from_raw(raw: Mapping[str, Any]) -> SourceRecord:
    return SourceRecord(
        source_id=str(raw["source_id"]),
        source_sha256=str(raw["source_sha256"]).lower(),
        source_lineage=str(raw.get("source_lineage", UNCLASSIFIED_LINEAGE)),
        season=str(raw.get("season", "")),
        domain=str(raw.get("domain", INADMISSIBLE)),
        fields={str(k): str(v) for k, v in dict(raw.get("fields", {})).items()},
        dataset_sha256=str(raw.get("dataset_sha256", "")),
        split=str(raw.get("split", "")),
        rationale=str(raw.get("rationale", "")),
    )


def parse_domain_manifest(
    data: bytes, *, authority_commit: str = ""
) -> EvidenceDomainManifest:
    """Parse and validate manifest bytes.

    ``source_bytes_sha256`` is taken over the bytes handed in rather than over
    the parsed content, so it describes the artifact that was actually read out
    of the object store.
    """
    raw = json.loads(data.decode("utf-8"))
    binding = raw.get("dataset_binding", {})
    return EvidenceDomainManifest(
        manifest_id=str(raw["manifest_id"]),
        generation=str(raw.get("generation", CURRENT_AUTHORITY_GENERATION)),
        authority_commit=authority_commit or str(raw.get("authority_commit", "")),
        sources=tuple(_source_from_raw(entry) for entry in raw.get("sources", [])),
        forbidden_fields=tuple(str(x) for x in raw.get("forbidden_fields", ())),
        parameter_eligibility={
            str(k): str(v) for k, v in dict(raw.get("parameter_eligibility", {})).items()
        },
        dataset_sha256=str(binding.get("dataset_sha256", "")),
        split_sha256=str(binding.get("split_sha256", "")),
        source_bytes_sha256=sha256_bytes(data),
        supersedes=tuple(str(x) for x in raw.get("supersedes", ())),
    )


def load_domain_manifest(path: str | Path) -> EvidenceDomainManifest:
    """Load a manifest from a file. Used by tooling and tests, not by a run."""
    resolved = Path(path).resolve()
    if not resolved.exists():
        raise InputValidationError(f"Evidence domain manifest not found: {resolved}")
    return parse_domain_manifest(resolved.read_bytes())


def load_domain_manifest_from_authority(
    resolved: ResolvedAuthority,
) -> EvidenceDomainManifest:
    """Load the manifest out of a resolved git object, failing closed if absent.

    This is the only loader a run uses. It reads the blob the authority resolved
    to -- object store, pinned commit -- so the manifest a run is governed by
    cannot depend on the state of any checked-out working tree.
    """
    content = resolved.require_present()
    manifest = parse_domain_manifest(content, authority_commit=resolved.commit)
    if manifest.generation != resolved.binding.generation:
        raise GovernanceBlock(
            f"Evidence authority {resolved.binding.ref} is configured as generation "
            f"{resolved.binding.generation} and the manifest it holds declares "
            f"{manifest.generation}. The two must agree or the run does not know which "
            "authority it is bound to."
        )
    return manifest
