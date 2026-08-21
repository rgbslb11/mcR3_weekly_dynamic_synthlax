"""Board of Record identity and mounting for V3.

Ruling R2-BOARD-OF-RECORD names
``2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx`` as the Board of Record and
forbids substituting Board I-H for it.

That artifact is **not mounted in this repository**. Board I-H v2 is, as sheet
``08_BOARD_IH_TOP25`` of Model Parameters v2.5, and it stays exactly where it is
as historical/superseded evidence. Any operation that needs actual Board rows —
CCG-TB3, COMMITTEE-TB4, A8/ECL-TB3, CFP selection — therefore fails closed on a
missing Board-of-Record artifact rather than silently ranking on the old board.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .errors import GovernanceBlock
from .rulings import R2_BOARD_OF_RECORD

BOARD_OF_RECORD_FILENAME = "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx"
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


def board_of_record_status(path: Path | None) -> dict[str, object]:
    mounted = bool(path and path.exists())
    return {
        "ruling": R2_BOARD_OF_RECORD.convergence_id,
        "identity": BOARD_OF_RECORD_FILENAME,
        "package": BOARD_OF_RECORD_PACKAGE,
        "mounted": mounted,
        "path": str(path) if path else None,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest() if mounted else None,
        "historical_board_retained": HISTORICAL_BOARD_LABEL,
        "historical_board_location": HISTORICAL_BOARD_SHEET,
        "historical_board_substitutable": False,
        "blocker": None if mounted else BOARD_OF_RECORD_BLOCKER,
    }


def require_board_of_record(path: Path | None) -> BoardOfRecord:
    """Fail closed unless the named Board-of-Record artifact is mounted."""
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
    if path.name != BOARD_OF_RECORD_FILENAME:
        raise GovernanceBlock(
            f"Configured Board of Record {path.name!r} is not {BOARD_OF_RECORD_FILENAME}. "
            f"Ruling {R2_BOARD_OF_RECORD.convergence_id} names one artifact and forbids "
            "substitution."
        )
    data = path.read_bytes()
    return BoardOfRecord(
        identity=BOARD_OF_RECORD_FILENAME,
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
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
