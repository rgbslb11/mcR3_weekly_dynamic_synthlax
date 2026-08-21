"""Board of Record custody, identity and row exposure for V3.

Ruling R2-BOARD-OF-RECORD names
``2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx`` as the Board of Record and
forbids substituting Board I-H for it.

Custody here is decided by **content identity, never by filename**. The approved
artifact reaches operators through channels that rename it freely — browser
download de-duplication alone produces ``...REISSUE(3).xlsx``,
``...REISSUE(3)(1).xlsx`` and ``...REISSUE (1).xlsx`` for the same bytes — so a
name test is a routing hint and nothing more. Two independent digests decide:

``binary``
    SHA-256 of the ``.xlsx`` file itself, as registered for this artifact in
    ``Board_I-K_Artifact_Register_R1-R3_FINAL.xlsx`` with status
    ``APPROVED CANONICAL - CURRENT``. This certifies the exact distributed file.

``content``
    SHA-256 of worksheet ``Board I-K`` range ``A3:Q124`` serialized by
    HASH-SPEC-V1 (named-sheet RFC 4180 CSV, UTF-8 without BOM, LF line endings,
    one trailing LF, nulls as the empty string, numerics at round-trip
    precision). This certifies the governed *rows* independently of workbook
    packaging, so a re-save that preserves the table is distinguishable from an
    edit that does not.

A re-saved workbook keeps its content hash and loses its binary hash; the
converse cannot happen. Both must verify before any Board row is exposed. The
loader fails closed on every other outcome, and a mismatching artifact is
classified positively — "Board I-H", "superseded predecessor", "unapproved
candidate", "not a workbook" — rather than reported as a generic failure, so a
reviewer can tell substitution from corruption.

Board I-H v2 remains mounted as sheet ``08_BOARD_IH_TOP25`` of Model Parameters
v2.5 and stays exactly where it is, as historical/superseded evidence only.

Scope note: this module establishes custody and exposes validated rows. It does
**not** designate Board I-K as the COMMITTEE-TB4 first-November fallback. No
governed authority does, and ``committee_policy.FIRST_BOARD_TB4_BLOCKER`` stays
open on its own terms.
"""

from __future__ import annotations

import csv
import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_BOARD_OF_RECORD

#: The artifact filename as registered in the R1-R3 FINAL artifact register.
#: Retained as the canonical *label*; it is never the authority (see
#: :data:`BOARD_OF_RECORD_APPROVED_SHA256`).
BOARD_OF_RECORD_FILENAME = "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx"
BOARD_OF_RECORD_PACKAGE = "Board I-K R1-R3 FINAL / re-issued governance lineage"

#: FACT — the approved binary digest. Registered in
#: Board_I-K_Artifact_Register_R1-R3_FINAL.xlsx as "APPROVED CANONICAL — CURRENT",
#: and independently carried in
#: reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R3.json as required_sha256.
#: This constant, not the filename, is the custody authority.
BOARD_OF_RECORD_APPROVED_SHA256 = (
    "6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a"
)

#: FACT — the approved artifact's exact byte size, from the same register row.
BOARD_OF_RECORD_APPROVED_BYTES = 57179

#: FACT — HASH-SPEC-V1 content digest of 'Board I-K'!A3:Q124, same register row.
BOARD_OF_RECORD_CONTENT_SHA256 = (
    "23f83a347582655986f59d69e0205349996d1c0f9db294701e8112e49a11ecde"
)

#: The governed table. HASH-SPEC-V1 requires a named worksheet and range; a
#: content hash without both is invalid by that specification.
BOARD_SHEET = "Board I-K"
BOARD_CONTENT_RANGE = "A3:Q124"
BOARD_HEADER_ROW = 3
BOARD_FIRST_DATA_ROW = 4
BOARD_LAST_DATA_ROW = 124
BOARD_FIRST_COL = 1
BOARD_LAST_COL = 17

#: FACT — the declared column order of 'Board I-K'!A3:Q3. Validated exactly: a
#: reordered or renamed header is a schema failure, not a tolerable variant,
#: because the content digest is computed over the declared order.
BOARD_COLUMNS: tuple[str, ...] = (
    "Rank I-K",
    "Team",
    "Short",
    "Conference",
    "Committee",
    "Power",
    "Baseline",
    "Returning",
    "Movement",
    "Talent",
    "Coaching",
    "Market (Schedule-Neutral)",
    "Futures Overlay (Context Only)",
    "Market Status",
    "Prior Rank I-I",
    "Shift",
    "Master Team ID",
)

#: The governed FBS population. The Board ranks exactly the 121 FBS members and
#: no schedule-only FCS entity — those carry no master_team_id at all.
BOARD_EXPECTED_ROWS = 121

#: Historical board, retained as evidence and never substituted for I-K.
HISTORICAL_BOARD_SHEET = "08_BOARD_IH_TOP25"
HISTORICAL_BOARD_LABEL = "Board I-H v2"

BOARD_OF_RECORD_BLOCKER = "inputs.board_of_record_i_k"

#: Digests of artifacts that have been offered as, or could be mistaken for, the
#: Board of Record. Recorded so a mismatching mount is named rather than merely
#: refused — "you mounted the superseded predecessor" is actionable, "hash
#: mismatch" is not. Every one of these is refused.
KNOWN_NON_APPROVED_SHA256: dict[str, str] = {
    "8a41ac166782e8a26fdfa277408389f4e7e239d0a2a80a76ea0978fe22c23c95": (
        "2026_Board_I-K_CANONICAL_APPROVED.xlsx — superseded numerically "
        "equivalent predecessor, replaced by the R1 reissue"
    ),
    "ec45fe1be1275dd19000b254e1d35e5d6c07c02cda818e436afdf26079ce49e6": (
        "2026_Board_I-K_CANONICAL_CANDIDATE.xlsx — unapproved candidate"
    ),
    "6101dcd94d807b66a86a5282ada7b9751e23c19cb009d0e7d5a4fb8e523e272e": (
        "2026_Board_I-K_CANONICAL_CANDIDATE variant — unapproved candidate"
    ),
    "f53dc2c1c141027e05f76b421f9cfc5720a6dcca846ffad4de527311b802370b": (
        "2026_Board_I-I_CANONICAL_CANDIDATE_SCHEDULE_NEUTRAL_BLOCKED.xlsx — "
        "superseded predecessor board"
    ),
}

# --- custody classifications -------------------------------------------------

CUSTODY_VERIFIED = "BOARD_IK_APPROVED_ARTIFACT_VERIFIED"
CUSTODY_NOT_CONFIGURED = "BOARD_IK_NOT_CONFIGURED"
CUSTODY_NOT_MOUNTED = "BOARD_IK_ARTIFACT_NOT_MOUNTED"
CUSTODY_BINARY_MISMATCH = "BOARD_IK_BINARY_SHA256_MISMATCH"
CUSTODY_CONTENT_MISMATCH = "BOARD_IK_CONTENT_SHA256_MISMATCH"
CUSTODY_NOT_A_WORKBOOK = "BOARD_IK_ARTIFACT_IS_NOT_AN_XLSX_WORKBOOK"
CUSTODY_SCHEMA_INVALID = "BOARD_IK_SCHEMA_INVALID"
CUSTODY_IDENTITY_INVALID = "BOARD_IK_IDENTITY_INVALID"


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _hash_spec_v1_cell(value: object) -> str:
    """Serialize one cell under HASH-SPEC-V1.

    Nulls are the empty string with no placeholder token, booleans are TRUE or
    FALSE, and numerics use the exact stored value at round-trip precision
    rather than any displayed format. ``%.17g`` is what reproduces the
    registered digest; ``repr`` (shortest round-trip) does not, and the
    difference is silent, so the format is pinned here rather than defaulted.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return "%.17g" % value
    return str(value)


def _read_board_grid(path: Path) -> list[list[object]]:
    """Read 'Board I-K'!A3:Q124, or fail closed naming what was wrong."""
    from openpyxl import load_workbook

    if not zipfile.is_zipfile(path):
        raise InputValidationError(
            f"{CUSTODY_NOT_A_WORKBOOK}: {path.name} is not a readable .xlsx "
            "container (a truncated, corrupted, or plain-text stand-in)."
        )
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 — classified, then re-raised closed
        raise InputValidationError(
            f"{CUSTODY_NOT_A_WORKBOOK}: {path.name} could not be opened as a "
            f"workbook: {exc}"
        ) from exc
    try:
        if BOARD_SHEET not in wb.sheetnames:
            raise InputValidationError(
                f"{CUSTODY_SCHEMA_INVALID}: worksheet {BOARD_SHEET!r} is absent "
                f"from {path.name}; sheets present: {sorted(wb.sheetnames)}."
            )
        ws = wb[BOARD_SHEET]
        return [
            list(row)
            for row in ws.iter_rows(
                min_row=BOARD_HEADER_ROW,
                max_row=BOARD_LAST_DATA_ROW,
                min_col=BOARD_FIRST_COL,
                max_col=BOARD_LAST_COL,
                values_only=True,
            )
        ]
    finally:
        wb.close()


def board_content_sha256(path: Path) -> str:
    """Reproduce the HASH-SPEC-V1 content digest of the governed Board table."""
    grid = _read_board_grid(path)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    for row in grid:
        writer.writerow([_hash_spec_v1_cell(v) for v in row])
    return hashlib.sha256(buf.getvalue().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BoardRow:
    rank: int
    team_name: str
    short_name: str
    conference: str
    master_team_id: str
    committee: float
    power: float


@dataclass(frozen=True)
class BoardOfRecord:
    identity: str
    path: Path
    sha256: str
    content_sha256: str
    rows: tuple[BoardRow, ...]

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def order_by_master_team_id(self) -> tuple[str, ...]:
        """The Board ordering, rank 1 first, as governed master team ids."""
        return tuple(r.master_team_id for r in self.rows)

    def order_by_schedule_id(
        self, canonical_index: dict[str, dict[str, str | None]]
    ) -> tuple[str, ...]:
        """The Board ordering expressed in schedule ids.

        Downstream consumers (CCG-TB3, A8/ECL-TB3, CFP selection) rank on
        schedule ids, while the Board publishes master team ids. The mapping is
        taken from the canonical team index and never inferred from team names,
        which are not governed identifiers.
        """
        by_master = {
            str(row["master_team_id"]): sid
            for sid, row in canonical_index.items()
            if row["entity_scope"] == "FBS_MEMBER" and row["master_team_id"] is not None
        }
        missing = [r.master_team_id for r in self.rows if r.master_team_id not in by_master]
        if missing:
            raise InputValidationError(
                f"{CUSTODY_IDENTITY_INVALID}: Board master team ids {sorted(missing)} "
                "have no FBS_MEMBER in the canonical team index."
            )
        return tuple(by_master[r.master_team_id] for r in self.rows)


def _validate_schema(grid: list[list[object]], path: Path) -> list[list[object]]:
    header = [None if v is None else str(v).strip() for v in grid[0]]
    if tuple(header) != BOARD_COLUMNS:
        raise InputValidationError(
            f"{CUSTODY_SCHEMA_INVALID}: {path.name} worksheet {BOARD_SHEET!r} "
            f"header row {BOARD_HEADER_ROW} is {header!r}, expected "
            f"{list(BOARD_COLUMNS)!r}."
        )
    data = [row for row in grid[1:] if any(v is not None for v in row)]
    if len(data) != BOARD_EXPECTED_ROWS:
        raise InputValidationError(
            f"{CUSTODY_SCHEMA_INVALID}: {path.name} exposes {len(data)} Board rows, "
            f"expected exactly {BOARD_EXPECTED_ROWS} governed FBS members."
        )
    return data


def _validate_identity(data: list[list[object]], path: Path) -> tuple[BoardRow, ...]:
    rows: list[BoardRow] = []
    for row in data:
        rank, team, short, conf = row[0], row[1], row[2], row[3]
        committee, power, master = row[4], row[5], row[16]
        if rank is None or master is None or team is None:
            raise InputValidationError(
                f"{CUSTODY_IDENTITY_INVALID}: {path.name} carries a Board row with a "
                f"null Rank, Team or Master Team ID: {row!r}."
            )
        rows.append(
            BoardRow(
                rank=int(rank),
                team_name=str(team),
                short_name=str(short) if short is not None else "",
                conference=str(conf) if conf is not None else "",
                master_team_id=str(master),
                committee=float(committee) if committee is not None else float("nan"),
                power=float(power) if power is not None else float("nan"),
            )
        )
    ranks = [r.rank for r in rows]
    if ranks != list(range(1, BOARD_EXPECTED_ROWS + 1)):
        raise InputValidationError(
            f"{CUSTODY_IDENTITY_INVALID}: {path.name} Board ranks are not the "
            f"contiguous sequence 1..{BOARD_EXPECTED_ROWS}."
        )
    ids = [r.master_team_id for r in rows]
    if len(set(ids)) != len(ids):
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        raise InputValidationError(
            f"{CUSTODY_IDENTITY_INVALID}: {path.name} repeats master team ids "
            f"{duplicates}; the Board must rank each FBS member exactly once."
        )
    return tuple(rows)


def validate_against_canonical_universe(
    board: BoardOfRecord, canonical_index: dict[str, dict[str, str | None]]
) -> None:
    """Bind the Board to the governed 134-entity universe.

    The Board must rank the 121 FBS members exactly, and must not carry any
    schedule-only FCS entity. FCS entities hold no master_team_id in the
    canonical index, so an FCS row can only arrive as an id the FBS mapping does
    not contain — which is refused as an unexpected entity rather than silently
    dropped.
    """
    fbs_ids = {
        str(row["master_team_id"])
        for row in canonical_index.values()
        if row["entity_scope"] == "FBS_MEMBER" and row["master_team_id"] is not None
    }
    board_ids = set(board.order_by_master_team_id())
    unexpected = sorted(board_ids - fbs_ids)
    if unexpected:
        raise InputValidationError(
            f"{CUSTODY_IDENTITY_INVALID}: Board carries master team ids {unexpected} "
            "that are not governed FBS members (an FCS or otherwise ungoverned entity)."
        )
    missing = sorted(fbs_ids - board_ids)
    if missing:
        raise InputValidationError(
            f"{CUSTODY_IDENTITY_INVALID}: Board omits governed FBS master team ids "
            f"{missing}."
        )


def classify_board_artifact(path: Path | None) -> dict[str, object]:
    """Classify a candidate Board artifact without raising.

    Every state a mount can be in is named, so ``board_of_record_status`` and the
    blocker report can describe custody without a caller having to catch an
    exception to learn what is wrong.
    """
    if path is None:
        return {"custody": CUSTODY_NOT_CONFIGURED, "mounted": False}
    if not path.exists():
        return {"custody": CUSTODY_NOT_MOUNTED, "mounted": False}

    actual = _sha256_file(path)
    result: dict[str, object] = {
        "mounted": True,
        "path": str(path),
        "filename": path.name,
        "filename_is_canonical_label": path.name == BOARD_OF_RECORD_FILENAME,
        "sha256": actual,
        "bytes": path.stat().st_size,
    }
    if actual != BOARD_OF_RECORD_APPROVED_SHA256:
        result["custody"] = CUSTODY_BINARY_MISMATCH
        result["identified_as"] = KNOWN_NON_APPROVED_SHA256.get(
            actual, "UNKNOWN_ARTIFACT — not the approved Board of Record"
        )
        return result
    try:
        content = board_content_sha256(path)
    except InputValidationError as exc:
        result["custody"] = CUSTODY_NOT_A_WORKBOOK
        result["detail"] = str(exc)
        return result
    result["content_sha256"] = content
    if content != BOARD_OF_RECORD_CONTENT_SHA256:
        result["custody"] = CUSTODY_CONTENT_MISMATCH
        return result
    result["custody"] = CUSTODY_VERIFIED
    return result


def board_of_record_status(path: Path | None) -> dict[str, object]:
    """Custody status of the configured Board of Record. Never raises."""
    classification = classify_board_artifact(path)
    custody = classification["custody"]
    verified = custody == CUSTODY_VERIFIED
    return {
        "ruling": R2_BOARD_OF_RECORD.convergence_id,
        "identity": BOARD_OF_RECORD_FILENAME,
        "package": BOARD_OF_RECORD_PACKAGE,
        "mounted": bool(classification["mounted"]),
        "path": str(path) if path else None,
        "sha256": classification.get("sha256"),
        "expected_sha256": BOARD_OF_RECORD_APPROVED_SHA256,
        "content_sha256": classification.get("content_sha256"),
        "expected_content_sha256": BOARD_OF_RECORD_CONTENT_SHA256,
        "content_hash_method": f"HASH-SPEC-V1 {BOARD_SHEET}!{BOARD_CONTENT_RANGE}",
        "custody": custody,
        "verified": verified,
        "identified_as": classification.get("identified_as"),
        "historical_board_retained": HISTORICAL_BOARD_LABEL,
        "historical_board_location": HISTORICAL_BOARD_SHEET,
        "historical_board_substitutable": False,
        "blocker": None if verified else BOARD_OF_RECORD_BLOCKER,
    }


def board_of_record_blockers(path: Path | None) -> list[str]:
    """The Board-of-Record execution blocker, if custody does not verify.

    Board-owned so the configuration layer never re-implements the custody
    rule — and so a merely *present* file can never clear the gate.
    """
    status = board_of_record_status(path)
    return [] if status["verified"] else [BOARD_OF_RECORD_BLOCKER]


def require_board_of_record(
    path: Path | None,
    canonical_index: dict[str, dict[str, str | None]] | None = None,
) -> BoardOfRecord:
    """Fail closed unless the approved Board-of-Record artifact verifies.

    Ordered so the most specific refusal wins: configured, mounted, approved
    binary digest, readable workbook, reproduced content digest, schema,
    identity, and finally the governed universe when a canonical index is
    supplied. No Board row is exposed until every gate has passed.
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

    actual = _sha256_file(path)
    if actual != BOARD_OF_RECORD_APPROVED_SHA256:
        identified = KNOWN_NON_APPROVED_SHA256.get(actual)
        detail = f" Identified as: {identified}." if identified else ""
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: {CUSTODY_BINARY_MISMATCH}. {path.name!r} has "
            f"SHA-256 {actual}, but the approved Board of Record is "
            f"{BOARD_OF_RECORD_APPROVED_SHA256}.{detail} Ruling "
            f"{R2_BOARD_OF_RECORD.convergence_id} names one artifact by content; a "
            "matching filename is not authority."
        )

    content = board_content_sha256(path)
    if content != BOARD_OF_RECORD_CONTENT_SHA256:
        raise GovernanceBlock(
            f"{BOARD_OF_RECORD_BLOCKER}: {CUSTODY_CONTENT_MISMATCH}. "
            f"{BOARD_SHEET}!{BOARD_CONTENT_RANGE} serializes to {content}, expected "
            f"{BOARD_OF_RECORD_CONTENT_SHA256}."
        )

    grid = _read_board_grid(path)
    rows = _validate_identity(_validate_schema(grid, path), path)
    board = BoardOfRecord(
        identity=BOARD_OF_RECORD_FILENAME,
        path=path,
        sha256=actual,
        content_sha256=content,
        rows=rows,
    )
    if canonical_index is not None:
        validate_against_canonical_universe(board, canonical_index)
    return board


def reject_historical_board_substitution(label: str) -> None:
    """Refuse Board I-H (or any other board) standing in for the Board of Record."""
    if label != BOARD_OF_RECORD_FILENAME:
        raise GovernanceBlock(
            f"{label!r} may not serve as Board of Record. Ruling "
            f"{R2_BOARD_OF_RECORD.convergence_id} names {BOARD_OF_RECORD_FILENAME}; "
            f"{HISTORICAL_BOARD_LABEL} is retained as historical evidence only."
        )
