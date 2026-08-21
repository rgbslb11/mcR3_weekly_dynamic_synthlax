"""Deterministic AAC division-membership resolution for Dynamic Weekly MC V3.

R-CCG-05 makes AAC championship participants the American Division winner versus
the Athletic Division winner, and R-CCG-07 records the 8/8 membership as
RATIFIED. The ratified artifact itself — ``aac_divisions_2026_RATIFIED.csv``,
577 bytes, sha256 ``e0f674b4…`` — is registered in the Model Parameters source
register and artifact lineage but is **not mounted in this repository**.

The membership rows are independently recoverable: the governed canonical team
master carries a ``2026_conference_division`` field that assigns exactly 8 AAC
teams to ``American`` and exactly 8 to ``Athletic``, matching the ratified
count. This module extracts that assignment deterministically and validates it.

What this module deliberately does **not** do is clear the
``inputs.aac_divisions_csv`` blocker on its own. Serializing the extracted rows
produces a file whose digest does not equal the registered ratified digest,
because the ratified CSV's exact column set, ordering and formatting are not
recorded anywhere in the repository. Substituting a locally minted artifact for
a registered ratified one would manufacture precisely the class of provenance
mismatch this codebase exists to detect. The gate therefore fails closed until
either the ratified artifact is supplied or a human explicitly rules that the
canonical-master-derived membership may stand in for it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import GovernanceBlock, InputValidationError

# Registered in Model Parameters v2.5 sheets 01_SOURCE_REGISTER and
# 10_ARTIFACT_LINEAGE for aac_divisions_2026_RATIFIED.csv.
RATIFIED_AAC_CSV_SHA256 = "e0f674b4d0bab13ff943d0ced6364c70df40d4e4a1f1a2cde2a4479a13b2cd0f"
RATIFIED_AAC_CSV_BYTES = 577

AAC_CONFERENCE_LABEL = "American"
AMERICAN_DIVISION = "American"
ATHLETIC_DIVISION = "Athletic"
EXPECTED_PER_DIVISION = 8

_FIELD = "2026_conference_division"


@dataclass(frozen=True)
class AACDivisionRow:
    schedule_id: str
    team_name: str
    conference: str
    division: str


def extract_aac_divisions(canonical_master_md: Path) -> list[AACDivisionRow]:
    """Extract AAC division membership from the governed canonical team master.

    Returns rows sorted by ``(division, schedule_id)`` so the result is stable
    regardless of document ordering.
    """
    text = canonical_master_md.read_text(encoding="utf-8")
    rows: list[AACDivisionRow] = []
    for block in re.split(r"\n(?=### )", text):
        if _FIELD not in block:
            continue

        def field(name: str) -> str | None:
            match = re.search(rf"^- `{name}`: `(.*?)`\s*$", block, re.M)
            if match is None:
                return None
            value = match.group(1).strip()
            return None if value in ("", "<blank>") else value

        division = field(_FIELD)
        if division not in (AMERICAN_DIVISION, ATHLETIC_DIVISION):
            continue
        schedule_id = field("schedule_id")
        team_name = field("team_name")
        conference = field("2026_conference")
        if not schedule_id or not team_name:
            raise InputValidationError(
                f"Canonical master AAC row missing schedule_id/team_name: {block.splitlines()[0]!r}"
            )
        rows.append(
            AACDivisionRow(
                schedule_id=schedule_id,
                team_name=team_name,
                conference=conference or "",
                division=division,
            )
        )
    return sorted(rows, key=lambda r: (r.division, r.schedule_id))


def validate_aac_divisions(rows: list[AACDivisionRow]) -> dict[str, object]:
    """Validate the extracted membership against R-CCG-07's ratified structure."""
    american = [r for r in rows if r.division == AMERICAN_DIVISION]
    athletic = [r for r in rows if r.division == ATHLETIC_DIVISION]

    if len(american) != EXPECTED_PER_DIVISION or len(athletic) != EXPECTED_PER_DIVISION:
        raise InputValidationError(
            "R-CCG-07 ratifies an 8/8 AAC split; canonical master yields "
            f"{len(american)} American / {len(athletic)} Athletic"
        )

    ids = [r.schedule_id for r in rows]
    if len(set(ids)) != len(ids):
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        raise InputValidationError(f"Duplicate AAC schedule_id rows: {duplicates}")

    off_conference = sorted(r.schedule_id for r in rows if r.conference != AAC_CONFERENCE_LABEL)
    if off_conference:
        raise InputValidationError(
            f"AAC division rows reference non-American conference teams: {off_conference}"
        )

    return {
        "total": len(rows),
        "american": [r.schedule_id for r in american],
        "athletic": [r.schedule_id for r in athletic],
        "split_matches_r_ccg_07": True,
    }


def cross_check_against_schedule(
    rows: list[AACDivisionRow], teams: dict[str, object], conference_of: dict[str, str]
) -> dict[str, object]:
    """Confirm the extracted membership covers exactly the AAC teams in play.

    A membership file that omits an AAC team, or names a team that is not in the
    conference, would silently corrupt CCG participant selection.
    """
    assigned = {r.schedule_id for r in rows}
    actual = {sid for sid, conf in conference_of.items() if conf == AAC_CONFERENCE_LABEL and sid in teams}
    missing = sorted(actual - assigned)
    extra = sorted(assigned - actual)
    if missing or extra:
        raise InputValidationError(
            f"AAC division membership does not cover the conference exactly: "
            f"missing={missing} unexpected={extra}"
        )
    return {"covered_teams": len(actual), "missing": missing, "unexpected": extra}


def serialize_candidate_csv(rows: list[AACDivisionRow]) -> str:
    """Serialize extracted membership as a candidate CSV (LF, blank for null)."""
    sio = io.StringIO(newline="")
    writer = csv.writer(sio, lineterminator="\n")
    writer.writerow(["schedule_id", "team_name", "conference", "division"])
    for row in rows:
        writer.writerow([row.schedule_id, row.team_name, row.conference, row.division])
    return sio.getvalue()


def candidate_csv_digest(rows: list[AACDivisionRow]) -> str:
    return hashlib.sha256(serialize_candidate_csv(rows).encode("utf-8")).hexdigest()


def require_ratified_aac_divisions_csv(path: Path | None) -> Path:
    """Fail closed unless the mounted CSV *is* the registered ratified artifact.

    Digest equality is the only accepted proof of identity. A file that merely
    parses, or that merely contains a plausible 8/8 split, is not the ratified
    artifact and must not be treated as one.
    """
    if path is None:
        raise GovernanceBlock(
            "inputs.aac_divisions_csv is not configured. R-CCG-07 ratified an 8/8 "
            "American/Athletic split and the canonical master carries a matching "
            "membership, but the ratified artifact aac_divisions_2026_RATIFIED.csv "
            f"(sha256 {RATIFIED_AAC_CSV_SHA256}) is not mounted. Supply it, or issue an "
            "explicit ruling that the canonical-master-derived membership substitutes."
        )
    if not path.exists():
        raise GovernanceBlock(f"Configured AAC divisions CSV does not exist: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != RATIFIED_AAC_CSV_SHA256:
        raise GovernanceBlock(
            "Mounted AAC divisions CSV is not the ratified artifact. "
            f"expected sha256 {RATIFIED_AAC_CSV_SHA256}, got {digest}. "
            "A locally generated substitute is not a ratified artifact."
        )
    return path


# --- R2 governed successor artifact -------------------------------------------
#
# Ruling R2-AAC-SUCCESSOR resolves the custody break without faking the missing
# file. The legacy 577-byte artifact stays recorded as missing — its digest is
# still the only thing that would prove *its* identity, and nothing here claims
# to reproduce it. What is issued instead is a NEW artifact with its own
# identity, its own digest and full derivation provenance, extracted from the
# hash-verified canonical master under R-CCG-07.

from .rulings import R2_AAC_SUCCESSOR  # noqa: E402

#: FACT — digest of the successor artifact issued under R2-AAC-SUCCESSOR.
SUCCESSOR_AAC_CSV_SHA256 = "92fd7f78fe3fa4cde75624a58efe2136e40e342439474435bf97c1f6b70e22ce"
SUCCESSOR_AAC_CSV_BYTES = 554
SUCCESSOR_AAC_CSV_FILENAME = "aac_divisions_2026_R2_SUCCESSOR.csv"
SUCCESSOR_AAC_CSV_STATUS = "GOVERNED_SUCCESSOR"

#: Legacy custody state. Preserved, never edited, never reproduced.
LEGACY_AAC_CSV_FILENAME = "aac_divisions_2026_RATIFIED.csv"
LEGACY_AAC_CSV_CUSTODY = "NOT_MOUNTED_IN_REPOSITORY"

#: Every digest that identifies a governed AAC divisions artifact.
GOVERNED_AAC_CSV_DIGESTS = {
    RATIFIED_AAC_CSV_SHA256: LEGACY_AAC_CSV_FILENAME,
    SUCCESSOR_AAC_CSV_SHA256: SUCCESSOR_AAC_CSV_FILENAME,
}

AAC_ARTIFACT_BLOCKER = "governance.AAC_DIVISIONS_ARTIFACT_NOT_GOVERNED"


def require_governed_aac_divisions_csv(path: Path | None) -> tuple[Path, str]:
    """Accept only a mounted file whose digest identifies a governed artifact.

    Either the original ratified CSV (if it is ever recovered) or the R2
    successor. A locally regenerated look-alike that is neither is still refused
    — digest equality remains the only proof of identity.
    """
    if path is None:
        raise GovernanceBlock(
            "inputs.aac_divisions_csv is not configured. Ruling "
            f"{R2_AAC_SUCCESSOR.convergence_id} issues {SUCCESSOR_AAC_CSV_FILENAME} "
            f"(sha256 {SUCCESSOR_AAC_CSV_SHA256}); mount it or the recovered "
            f"{LEGACY_AAC_CSV_FILENAME}."
        )
    if not path.exists():
        raise GovernanceBlock(f"Configured AAC divisions CSV does not exist: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    identity = GOVERNED_AAC_CSV_DIGESTS.get(digest)
    if identity is None:
        raise GovernanceBlock(
            f"{AAC_ARTIFACT_BLOCKER}: mounted AAC divisions CSV has sha256 {digest}, which "
            f"identifies neither {LEGACY_AAC_CSV_FILENAME} ({RATIFIED_AAC_CSV_SHA256}) nor "
            f"{SUCCESSOR_AAC_CSV_FILENAME} ({SUCCESSOR_AAC_CSV_SHA256})."
        )
    return path, identity


def aac_artifact_status(path: Path | None) -> dict[str, object]:
    """Report which governed AAC artifact is mounted, if any."""
    digest = (
        hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else None
    )
    return {
        "ruling": R2_AAC_SUCCESSOR.convergence_id,
        "mounted_path": str(path) if path else None,
        "mounted_sha256": digest,
        "identity": GOVERNED_AAC_CSV_DIGESTS.get(digest) if digest else None,
        "is_governed": digest in GOVERNED_AAC_CSV_DIGESTS if digest else False,
        "successor": {
            "filename": SUCCESSOR_AAC_CSV_FILENAME,
            "sha256": SUCCESSOR_AAC_CSV_SHA256,
            "bytes": SUCCESSOR_AAC_CSV_BYTES,
            "status": SUCCESSOR_AAC_CSV_STATUS,
            "source_rule": "R-CCG-07",
        },
        "legacy": {
            "filename": LEGACY_AAC_CSV_FILENAME,
            "sha256": RATIFIED_AAC_CSV_SHA256,
            "bytes": RATIFIED_AAC_CSV_BYTES,
            "custody": LEGACY_AAC_CSV_CUSTODY,
            "lineage_preserved": True,
            "reproduction_attempted": False,
        },
        "blocker": None if digest in GOVERNED_AAC_CSV_DIGESTS else AAC_ARTIFACT_BLOCKER,
    }
