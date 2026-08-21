"""Board of Record identity and mounting for V3.

Ruling R2-BOARD-OF-RECORD names
``2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx`` as the Board of Record and
forbids substituting Board I-H for it.

The approved binary is now mounted under governed custody. Its identity is
established by SHA-256 equality and by nothing else: the filename is a label,
the digest is the proof. Board I-H v2 remains exactly where it is — sheet
``08_BOARD_IH_TOP25`` of Model Parameters v2.5 — as historical/superseded
evidence, and is still never substitutable.

Custody here means custody only. This module proves *which* artifact is mounted;
it does not read Board rows into any decision. The operations that consume rows —
CCG-TB3, COMMITTEE-TB4, A8/ECL-TB3, CFP selection — stay governed separately and
still fail closed on their own authorities.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import GovernanceBlock
from .rulings import R2_BOARD_OF_RECORD

#: Controlled identity named by ruling R2-BOARD-OF-RECORD. Unchanged.
BOARD_OF_RECORD_FILENAME = "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx"
BOARD_OF_RECORD_PACKAGE = "Board I-K R1-R3 FINAL / re-issued governance lineage"

#: FACT — SHA-256 of the approved Board-of-Record binary. Recorded as the
#: required digest by V3_GOVERNANCE_STATUS_R3/R4 before the artifact was ever
#: available, so the mount is checked against a pre-existing expectation rather
#: than against a digest computed from whatever happened to arrive.
BOARD_OF_RECORD_SHA256 = "6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a"

#: FACT — size of that binary, in bytes.
BOARD_OF_RECORD_BYTES = 57179

#: FACT — the filename the approved binary was delivered under. The ``(3)``
#: suffix is a duplicate-download marker applied by the transferring client, not
#: a distinct artifact and not a revision: the delivered bytes hash to
#: :data:`BOARD_OF_RECORD_SHA256`, the digest the controlled identity already
#: required. The delivery name is preserved rather than erased, and the mount
#: carries the controlled identity. Neither record is rewritten to match the
#: other.
BOARD_OF_RECORD_SOURCE_FILENAME = "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE(3).xlsx"

#: Names under which the Board of Record may legitimately appear. Membership in
#: this set is *not* authority — :data:`BOARD_OF_RECORD_SHA256` is. A file
#: carrying an accepted name and the wrong bytes is refused, which is precisely
#: the case filename-only checking used to admit.
BOARD_OF_RECORD_ACCEPTED_FILENAMES = frozenset(
    {BOARD_OF_RECORD_FILENAME, BOARD_OF_RECORD_SOURCE_FILENAME}
)

#: Raised when a file is mounted whose digest is not the approved one.
BOARD_ARTIFACT_DIGEST_BLOCKER = "governance.BOARD_OF_RECORD_ARTIFACT_NOT_GOVERNED"

#: Historical board, retained as evidence and never substituted for I-K.
HISTORICAL_BOARD_SHEET = "08_BOARD_IH_TOP25"
HISTORICAL_BOARD_LABEL = "Board I-H v2"

BOARD_OF_RECORD_BLOCKER = "inputs.board_of_record_i_k"


@dataclass(frozen=True)
class BoardOfRecord:
    identity: str
    path: Path
    sha256: str
    #: Rows are deliberately not loaded here. Custody proves *which* artifact is
    #: mounted; consuming Board rows is a separate governed step.
    rows: int
    #: The filename the bytes were delivered under, preserved verbatim.
    source_filename: str = BOARD_OF_RECORD_SOURCE_FILENAME


def board_of_record_digest(path: Path | None) -> str | None:
    """SHA-256 of the file at ``path``, or ``None`` if there is nothing to hash."""
    if path is None or not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_governed_board_of_record(path: Path | None) -> bool:
    """True only when ``path`` holds the exact approved Board-of-Record bytes."""
    return board_of_record_digest(path) == BOARD_OF_RECORD_SHA256


def board_of_record_status(path: Path | None) -> dict[str, object]:
    """Report Board-of-Record custody.

    ``mounted`` means the approved artifact is present *and* verified. A file
    that merely exists at the configured path — a fixture, a regenerated
    look-alike, Board I-H under a borrowed name — leaves ``mounted`` false and
    the blocker live, and is reported as ``digest_mismatch``.
    """
    digest = board_of_record_digest(path)
    present = digest is not None
    verified = digest == BOARD_OF_RECORD_SHA256
    return {
        "ruling": R2_BOARD_OF_RECORD.convergence_id,
        "identity": BOARD_OF_RECORD_FILENAME,
        "package": BOARD_OF_RECORD_PACKAGE,
        "source_filename": BOARD_OF_RECORD_SOURCE_FILENAME,
        "present": present,
        "mounted": verified,
        "path": str(path) if path else None,
        "sha256": digest,
        "expected_sha256": BOARD_OF_RECORD_SHA256,
        "digest_verified": verified,
        "digest_mismatch": present and not verified,
        "authority": "SHA256_DIGEST_EQUALITY",
        "historical_board_retained": HISTORICAL_BOARD_LABEL,
        "historical_board_location": HISTORICAL_BOARD_SHEET,
        "historical_board_substitutable": False,
        "blocker": None if verified else BOARD_OF_RECORD_BLOCKER,
    }


def require_board_of_record(path: Path | None) -> BoardOfRecord:
    """Fail closed unless the exact approved Board-of-Record artifact is mounted.

    Digest equality is the authority. The filename is checked too, but only
    after the bytes have already proved themselves — a correct name can never
    admit incorrect bytes, which is the failure mode this gate exists to stop.
    """
    if path is None:
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: Board of Record {BOARD_OF_RECORD_FILENAME} "
            f"({BOARD_OF_RECORD_PACKAGE}) is not configured. Ruling "
            f"{R2_BOARD_OF_RECORD.convergence_id} forbids substituting "
            f"{HISTORICAL_BOARD_LABEL}."
        )
    if not path.exists():
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: Board of Record artifact is not mounted at {path}."
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != BOARD_OF_RECORD_SHA256:
        raise GovernanceBlock(
            f"{BOARD_ARTIFACT_DIGEST_BLOCKER}: the file mounted at {path} has sha256 "
            f"{digest}, which is not the approved Board of Record "
            f"({BOARD_OF_RECORD_SHA256}). A fixture, a regenerated workbook or another "
            f"board carrying the right filename is still not the approved artifact; "
            f"ruling {R2_BOARD_OF_RECORD.convergence_id} names one binary."
        )
    if path.name not in BOARD_OF_RECORD_ACCEPTED_FILENAMES:
        raise GovernanceBlock(
            f"Board of Record bytes verified at {path}, but the file is named "
            f"{path.name!r}. Governed custody requires the controlled identity "
            f"{BOARD_OF_RECORD_FILENAME} (delivery name "
            f"{BOARD_OF_RECORD_SOURCE_FILENAME} is also recognised)."
        )
    return BoardOfRecord(
        identity=BOARD_OF_RECORD_FILENAME,
        path=path,
        sha256=digest,
        rows=0,
        source_filename=BOARD_OF_RECORD_SOURCE_FILENAME,
    )


def reject_historical_board_substitution(label: str) -> None:
    """Refuse Board I-H (or any other board) standing in for the Board of Record."""
    if label != BOARD_OF_RECORD_FILENAME:
        raise GovernanceBlock(
            f"{label!r} may not serve as Board of Record. Ruling "
            f"{R2_BOARD_OF_RECORD.convergence_id} names {BOARD_OF_RECORD_FILENAME}; "
            f"{HISTORICAL_BOARD_LABEL} is retained as historical evidence only."
        )
