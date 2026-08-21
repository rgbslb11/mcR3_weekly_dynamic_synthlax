"""Deterministic schedule-provenance reconciliation for Dynamic Weekly MC V3.

Two distinct provenance facts are tracked for the governed schedule artifact and
they must never be collapsed into one another:

``content``
    The SHA-256 of the ``Games`` sheet serialized by the canonical method
    recorded on the workbook's own Certification sheet. This certifies the
    *fixtures* — 743 rows of game data — independently of workbook packaging.

``binary``
    The SHA-256 of the ``.xlsx`` file itself, as registered in the Model
    Parameters v2.5 supersession row for schedule v5. This certifies the
    *artifact*, including zip container bytes and workbook metadata.

A re-saved workbook keeps its content hash and loses its binary hash. The
converse cannot happen. Classifying the two separately is therefore what lets a
reviewer tell "the fixtures were edited" (fatal) from "the file was re-saved"
(a custody question), and the engine must not treat them as interchangeable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Certified on the schedule workbook's Certification sheet (integrity_sha256)
# and cross-registered in Model Parameters v2.5 sheet 19_SCHEDULE_V5_CHANGE.
CERTIFIED_GAMES_CONTENT_SHA256 = "bd8089f70f6d483a75564e33438272c22daade8e53619fb21a915778975ff221"

# Registered in Model Parameters v2.5 sheet 19_SCHEDULE_V5_CHANGE as the v5
# schedule_binary_sha256. The repository copy does not carry these bytes.
GOVERNED_SCHEDULE_BINARY_SHA256 = "db26c3fff15a61ce8e7efa3b93100fa017e02248c96076d291495b55e855da12"

# The superseded v4 binary, recorded so a mismatching file can be positively
# identified as "stale v4" rather than "unknown artifact".
SUPERSEDED_V4_BINARY_SHA256 = "8d4d5112aa52cfb51895c95d104e3c5e1821813e3b481a4f1b3067668d0af57b"

CONTENT_MISMATCH = "SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH"
BINARY_MISMATCH = "SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5"


@dataclass(frozen=True)
class ScheduleProvenance:
    content_sha256_reproduced: str
    content_sha256_certified: str
    binary_sha256_actual: str
    binary_sha256_governed: str

    @property
    def content_verified(self) -> bool:
        return self.content_sha256_reproduced == self.content_sha256_certified

    @property
    def binary_verified(self) -> bool:
        return self.binary_sha256_actual == self.binary_sha256_governed

    @property
    def is_superseded_v4_binary(self) -> bool:
        return self.binary_sha256_actual == SUPERSEDED_V4_BINARY_SHA256

    def classification(self) -> str:
        """Classify the provenance state into exactly one governed category."""
        if self.content_verified and self.binary_verified:
            return "FULLY_VERIFIED"
        if not self.content_verified:
            # Fixture bytes differ from the certification. This is the fatal
            # case: the governed content itself is not what was certified.
            return "CANONICAL_CONTENT_MISMATCH"
        if self.is_superseded_v4_binary:
            return "SUPERSEDED_V4_ARTIFACT_MOUNTED"
        # Content certified, binary not the registered artifact: the fixtures are
        # provably intact but the file is not the registered v5 upload.
        return "CONTENT_VERIFIED_BINARY_SOURCE_COPY_MISMATCH"

    def anomalies(self) -> list[str]:
        out: list[str] = []
        if not self.content_verified:
            out.append(CONTENT_MISMATCH)
        if not self.binary_verified:
            out.append(BINARY_MISMATCH)
        return out

    def as_dict(self) -> dict[str, object]:
        return {
            "schedule_games_sha256_reproduced": self.content_sha256_reproduced,
            "schedule_games_sha256_certified": self.content_sha256_certified,
            "schedule_binary_sha256_actual": self.binary_sha256_actual,
            "schedule_binary_sha256_governed": self.binary_sha256_governed,
            "content_verified": self.content_verified,
            "binary_verified": self.binary_verified,
            "classification": self.classification(),
            "provenance_anomalies": self.anomalies(),
        }


def reconcile_schedule_provenance(schedule_xlsx: Path) -> ScheduleProvenance:
    """Reproduce both schedule hashes and classify the result deterministically."""
    # Imported here so :mod:`inputs` can import this module's constants.
    from .inputs import schedule_content_hash, sha256_file

    return ScheduleProvenance(
        content_sha256_reproduced=schedule_content_hash(schedule_xlsx),
        content_sha256_certified=CERTIFIED_GAMES_CONTENT_SHA256,
        binary_sha256_actual=sha256_file(schedule_xlsx),
        binary_sha256_governed=GOVERNED_SCHEDULE_BINARY_SHA256,
    )
