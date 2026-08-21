"""Board of Record identity and mounting for V3.

Ruling R2-BOARD-OF-RECORD names
``2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx`` as the Board of Record and
forbids substituting Board I-H for it.

Artifact custody is fail-closed. A candidate is governed only when both its
canonical mount name and its SHA-256 identity match the approved Board I-K
artifact. Mere file existence is never sufficient to clear the blocker.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import GovernanceBlock
from .rulings import R2_BOARD_OF_RECORD


BOARD_OF_RECORD_FILENAME = "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx"
BOARD_OF_RECORD_SHA256 = (
    "6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a"
)
BOARD_OF_RECORD_PACKAGE = "Board I-K R1-R3 FINAL / re-issued governance lineage"

#: Historical board, retained as evidence and never substituted for I-K.
HISTORICAL_BOARD_SHEET = "08_BOARD_IH_TOP25"
HISTORICAL_BOARD_LABEL = "Board I-H v2"

BOARD_OF_RECORD_BLOCKER = "inputs.board_of_record_i_k"


@dataclass(frozen=True)
class BoardOfRecord:
    identity: str
    path: Path
    sha256: str
    rows: int


def _sha256_file(path: Path) -> str:
    """Return the SHA-256 identity of the exact bytes on disk."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def board_of_record_status(path: Path | None) -> dict[str, object]:
    """Report custody status without treating existence as governance approval."""
    exists = bool(path is not None and path.is_file())
    name_matches = bool(exists and path is not None and path.name == BOARD_OF_RECORD_FILENAME)
    digest = _sha256_file(path) if exists and path is not None else None
    digest_matches = digest == BOARD_OF_RECORD_SHA256

    mounted = bool(exists and name_matches and digest_matches)

    return {
        "ruling": R2_BOARD_OF_RECORD.convergence_id,
        "identity": BOARD_OF_RECORD_FILENAME,
        "package": BOARD_OF_RECORD_PACKAGE,
        "required_sha256": BOARD_OF_RECORD_SHA256,
        "mounted": mounted,
        "path": str(path) if path else None,
        "sha256": digest,
        "exists": exists,
        "canonical_filename_matches": name_matches,
        "approved_digest_matches": digest_matches,
        "historical_board_retained": HISTORICAL_BOARD_LABEL,
        "historical_board_location": HISTORICAL_BOARD_SHEET,
        "historical_board_substitutable": False,
        "blocker": None if mounted else BOARD_OF_RECORD_BLOCKER,
    }


def require_board_of_record(path: Path | None) -> BoardOfRecord:
    """Fail closed unless the canonical, digest-verified Board I-K is mounted."""
    if path is None:
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: Board of Record {BOARD_OF_RECORD_FILENAME} "
            f"({BOARD_OF_RECORD_PACKAGE}) is not configured. Ruling "
            f"{R2_BOARD_OF_RECORD.convergence_id} forbids substituting "
            f"{HISTORICAL_BOARD_LABEL}."
        )

    if not path.is_file():
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: Board of Record artifact is not mounted at {path}."
        )

    if path.name != BOARD_OF_RECORD_FILENAME:
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: configured Board of Record {path.name!r} "
            f"is not the canonical mount name {BOARD_OF_RECORD_FILENAME!r}. "
            f"Ruling {R2_BOARD_OF_RECORD.convergence_id} forbids substitution."
        )

    digest = _sha256_file(path)

    if digest != BOARD_OF_RECORD_SHA256:
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: mounted Board of Record has sha256 "
            f"{digest}, but the approved {BOARD_OF_RECORD_FILENAME} requires "
            f"sha256 {BOARD_OF_RECORD_SHA256}."
        )

    return BoardOfRecord(
        identity=BOARD_OF_RECORD_FILENAME,
        path=path,
        sha256=digest,
        rows=0,
    )


def reject_historical_board_substitution(label: str) -> None:
    """Refuse Board I-H (or any other board) standing in for the Board of Record."""
    if label != BOARD_OF_RECORD_FILENAME:
        raise GovernanceBlock(
            f"{label!r} may not serve as Board of Record. Ruling "
            f"{R2_BOARD_OF_RECORD.convergence_id} names {BOARD_OF_RECORD_FILENAME}; "
            f"{HISTORICAL_BOARD_LABEL} is retained as historical evidence only."
        )
