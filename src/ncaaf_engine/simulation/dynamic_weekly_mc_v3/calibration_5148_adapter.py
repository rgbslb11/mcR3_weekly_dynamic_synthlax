"""Deterministic adapter from the audited 5,148-game corpus to V3 calibration observations.

This module is the **data plane only**. It chooses no calibration parameter, fits
nothing, promotes nothing, and retires no execution blocker. Its whole job is to
turn four audited source packages into the observation shape that
:mod:`.calibration_contract` specifies, and — where a source cannot support a
required field — to say so in a number rather than fill the gap in.

Three separations run through the whole module and are the reason it is shaped
the way it is:

``source universe`` vs ``admitted observation``
    The audited population is exactly 5,148 games: 3,667 across 2006-2011, 724 in
    2024 and 757 in 2025. That count is the *input*, never a target. A row leaves
    the universe only through a named gate in :data:`EXCLUSION_REASONS`, and the
    census must add back up to 5,148 exactly.

``governed synthetic`` vs ``ungoverned synthetic``
    Every one of the four packages describes its own game population as a
    synthetic research universe, and each says so in its own words. Under ruling
    R7-CAL-GOVERNED-SYNTHETIC-EVIDENCE that is admissible evidence for the
    synthetic V3 model, but only as ``GOVERNED_SYNTHETIC`` and only when the
    package and member digests verify and the source's own declaration is
    carried. The gate is :data:`EVIDENCE_DOMAIN_NOT_ADMISSIBLE`, and what it
    refuses is a corpus that claims the domain without earning it. The domain
    itself is never softened: it travels on every emitted row and establishes no
    real-world predictive validity.

``field the contract requires`` vs ``field a source recorded``
    :data:`FIELD_SUPPORT` is computed independently of the exclusion gate order,
    so a gap that a stricter earlier gate would have masked is still visible. The
    overtime gap is the worked example: it is invisible in the ordered census and
    fully visible in the field-support census.

Nothing here writes a governed calibration artifact. :func:`emit_observation_dataset`
exists to fail closed, and it does.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from openpyxl import load_workbook

from . import calibration as cal
from . import calibration_contract as contract
from .errors import GovernanceBlock

# ---------------------------------------------------------------------------
# Adapter identity
# ---------------------------------------------------------------------------

ADAPTER_ID = "V3-CALIBRATION-5148-ADAPTER"
ADAPTER_VERSION = "R1"
ADAPTER_LANE = "DATA_PLANE_ONLY"

#: The ruling whose temporal-order successor semantics this adapter targets.
CHAIRMAN_TEMPORAL_RULING_ID = cal.TEMPORAL_ORDER_RULING_ID
CHAIRMAN_TEMPORAL_RULING = cal.TEMPORAL_ORDER_RULING

#: Ruling R7 is what makes this corpus admissible at all. The token is passed to
#: calibration.require_evidence_domain per source block; nothing here assumes it.
CHAIRMAN_EVIDENCE_DOMAIN_RULING = cal.EVIDENCE_DOMAIN_RULING
CHAIRMAN_EVIDENCE_DOMAIN_APPROVAL_TOKEN = cal.EVIDENCE_DOMAIN_APPROVAL_TOKEN

#: Ruling R8 is what lets a season that records the prediction but not the two
#: ratings behind it be admitted at all. The token is passed per observation to
#: calibration.require_expected_margin_provenance; nothing here assumes it.
CHAIRMAN_EXPECTED_MARGIN_RULING = cal.EXPECTED_MARGIN_RULING
CHAIRMAN_EXPECTED_MARGIN_APPROVAL_TOKEN = cal.EXPECTED_MARGIN_APPROVAL_TOKEN

#: The source's own statement of its walk-forward chronology. Quoted rather than
#: paraphrased: it is what R8 requires the provenance to establish, and a
#: reviewer must be able to check it against the workbook.
WALKFORWARD_CHRONOLOGY_STATEMENT = (
    "Baxter walk-forward: each game is predicted from the rating state carried "
    "into it, built only from that season's earlier completed games under the "
    "frozen BAXTER-MOV-v1.0-R control (ridge lambda 0.3, margin cap +/-49, "
    "minimum three prior games per team). Read from the workbook sheet named "
    "'Walk Forward'; the full-season retrospective sheets are never read."
)

#: Nothing in this lane promotes anything. Recorded on every artifact the adapter
#: emits, so a reader never has to infer promotion status from the absence of a
#: statement about it.
PROMOTION_STATUS = "NOT_PROMOTED"

#: The rating-to-margin transform the governed Baxter workbooks state outright,
#: reproduced here verbatim because ``expected_margin`` is unidentifiable without
#: it. Validated against the recorded 2006 walk-forward predictions by
#: :func:`validate_expected_margin_transform`; never used to *generate* a margin.
EXPECTED_MARGIN_TRANSFORM = (
    "BAXTER-MOV-v1.0-R: predicted margin A = season HFA x non-neutral indicator "
    "+ rating A - rating B; ratings centered to zero within season"
)

#: The declared units of ``pregame_team_rating`` and ``expected_margin``. Season
#: specific, and the governed summary says so in as many words, which is itself a
#: finding a calibration consumer has to be told rather than discover.
RATING_SCALE_DECLARATION = (
    "BAXTER-MOV-v1.0-R season-specific opponent-adjusted margin points, ridge "
    "lambda 0.3, margin cap +/-49, minimum 3 prior games, season-specific fitted "
    "HFA, ratings centered to zero within season. Raw rating scales are "
    "season-specific and are not directly comparable across seasons."
)

MODEL_VERSION = "BAXTER-MOV-v1.0-R"
CONFIGURATION_VERSION = "BAXTER-MOV-v1.0-R-FROZEN-LAMBDA-0.3-CAP-49-MINPRIOR-3"


# ---------------------------------------------------------------------------
# Source package custody
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SourcePackage:
    """One audited source package, identified by digest rather than by filename.

    ``role`` is recorded because filename is not authority: two of these packages
    share several byte-identical members, and one of them is explicitly
    *supporting* evidence that this lane must not consume as a model.
    """

    filename: str
    sha256: str
    role: str
    consumed: bool
    expected_source_universe_rows: int | None = None
    members: Mapping[str, str] = field(default_factory=dict)


PHASE4M = "NCAA_Phase4M_2006_2011_Week_By_Week_Cleanup_Package.zip"
PHASE5D = "Power_Crunch_Research_Lab_Phase5D_WalkForward_Package.zip"
BAXTER = "Baxter_v1_2006_2011_2024_2025_Complete_Package.zip"
PHASE5E = "Power_Crunch_Research_Lab_Phase5E_Package.zip"

SOURCE_PACKAGES: tuple[SourcePackage, ...] = (
    SourcePackage(
        filename=PHASE4M,
        sha256="c4e588dd82d0a03c99958538dc0e3b84c5b293142db33d8458e6defb850f18cc",
        role="2006-2011 factual game ledger, chronology and source classification",
        consumed=True,
        expected_source_universe_rows=3667,
        members={
            "ledger": (
                "NCAA_Phase4M_2006_2011_Week_By_Week_Cleanup/data/"
                "verified_week_by_week_2006_2011.csv"
            ),
            "coverage": (
                "NCAA_Phase4M_2006_2011_Week_By_Week_Cleanup/data/coverage_summary.csv"
            ),
            "report": (
                "NCAA_Phase4M_2006_2011_Week_By_Week_Cleanup/reports/"
                "PHASE4M_WEEK_BY_WEEK_CLEANUP_REPORT.md"
            ),
        },
    ),
    SourcePackage(
        filename=PHASE5D,
        sha256="9a018a64b17d682e8c168524937ab70697e2f57a5b3ccae77f731fa3beba4f48",
        role="2024-2025 official synthetic event stream, pregame states, walk-forward evidence",
        consumed=True,
        expected_source_universe_rows=1481,
        members={
            "event_stream": (
                "Power_Crunch_Research_Lab_Phase5D_WalkForward/02_Event_Stream/"
                "official_synthetic_event_stream_2024_2025.csv"
            ),
            "pregame_states": (
                "Power_Crunch_Research_Lab_Phase5D_WalkForward/03_Pregame_States/"
                "pregame_states_2024_2025.csv"
            ),
            "walkforward_2024": (
                "Power_Crunch_Research_Lab_Phase5D_WalkForward/04_Predictions/"
                "walkforward_predictions_2024.csv"
            ),
            "walkforward_2025_untouched": (
                "Power_Crunch_Research_Lab_Phase5D_WalkForward/04_Predictions/"
                "walkforward_predictions_2025_untouched.csv"
            ),
            "alignment_registry": (
                "Power_Crunch_Research_Lab_Phase5D_WalkForward/01_Registries/"
                "modern_fbs_alignment_registry.csv"
            ),
            "locked_2025": (
                "Power_Crunch_Research_Lab_Phase5D_WalkForward/10_Source_Rulings/"
                "2025 Synthetic Season LOCKED v3.xlsx"
            ),
        },
    ),
    SourcePackage(
        filename=BAXTER,
        sha256="579931ba051067c5665eef930dab2f19c095ff014252a8c3f4c5c5b4b5086e71",
        role="primary Baxter Rating walk-forward / expected-margin evidence (BAXTER-MOV-v1.0-R)",
        consumed=True,
        members={
            "wf_2006": "Baxter_Ratings_v1_2006_External_Validation.xlsx",
            "wf_2007": "Baxter_Ratings_v1_2007_External_Validation.xlsx",
            "wf_2008": "Baxter_Ratings_v1_2008_External_Validation.xlsx",
            "wf_2009": "Baxter_Ratings_v1_2009_External_Validation.xlsx",
            "wf_2010": "Baxter_Ratings_v1_2010_External_Validation_CLASSIFICATION_CORRECTED.xlsx",
            "wf_2011": "Baxter_Ratings_v1_2011_External_Validation.xlsx",
            "wf_joint_modern": "Baxter_Ratings_v1_Joint_2024_2025_Validation_and_Freeze.xlsx",
            "metrics": "Baxter_v1_complete_metrics.csv",
        },
    ),
    SourcePackage(
        filename=PHASE5E,
        sha256="3980d5cf66a2588ddd094a1ce64500b08d48cbfbdfea3c37bcb011d6aa397d3f",
        role=(
            "supporting model-selection, chronology-sensitivity and margin-model "
            "evidence; NOT consumed as a V3 calibration model"
        ),
        consumed=False,
        members={},
    ),
)

SOURCE_PACKAGES_BY_NAME = {p.filename: p for p in SOURCE_PACKAGES}

#: Where a governed mount of the source packages lives inside the repository.
#: ``reference/dynamic_weekly_mc_v3/**`` already carries ``-text`` in
#: ``.gitattributes``, so a mounted package keeps its bytes across checkout.
MOUNT_RELATIVE_PATH = Path("reference/dynamic_weekly_mc_v3/calibration_sources")


def repository_root() -> Path:
    """The repository root, located from this module rather than the process cwd."""
    return Path(__file__).resolve().parents[4]


def default_mount_root() -> Path:
    return repository_root() / MOUNT_RELATIVE_PATH


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class MountedPackage:
    """A source package whose bytes were verified against the audited identity."""

    package: SourcePackage
    path: Path
    sha256: str
    bytes_: int


def require_package(root: Path, filename: str) -> MountedPackage:
    """Return a digest-verified package, or fail closed.

    Filename is never authority. The digest is checked against the audited
    identity before a single byte is parsed, because a package that is not the
    audited one is not weaker evidence — it is different evidence wearing the
    same name.
    """
    package = SOURCE_PACKAGES_BY_NAME.get(filename)
    if package is None:
        raise GovernanceBlock(
            f"{filename!r} is not one of the audited source packages "
            f"{sorted(SOURCE_PACKAGES_BY_NAME)}. Authority is not inferred from a "
            "filename, and an unrecognised package is refused rather than read."
        )
    path = Path(root) / filename
    if not path.is_file():
        raise GovernanceBlock(
            f"{ADAPTER_ID}: audited source package {filename} is not mounted at "
            f"{path}. The adapter reads only digest-verified governed sources."
        )
    data = path.read_bytes()
    digest = sha256_bytes(data)
    if digest != package.sha256:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: mounted {filename} hashes to {digest}, but the audited "
            f"package identity is {package.sha256}. Source bytes that are not the "
            "audited bytes are refused; nothing downstream may cite them."
        )
    return MountedPackage(
        package=package, path=path, sha256=digest, bytes_=len(data)
    )


def verify_mounted_packages(root: Path | None = None) -> dict[str, Any]:
    """Verify all four audited identities and report, without consuming any."""
    base = Path(root) if root is not None else default_mount_root()
    report: dict[str, Any] = {}
    for package in SOURCE_PACKAGES:
        mounted = require_package(base, package.filename)
        report[package.filename] = {
            "sha256": mounted.sha256,
            "bytes": mounted.bytes_,
            "role": package.role,
            "consumed_by_this_lane": package.consumed,
            "expected_source_universe_rows": package.expected_source_universe_rows,
        }
    return report


@dataclass(frozen=True)
class SourceMember:
    """One member read out of a verified package, with its own digest."""

    package_filename: str
    package_sha256: str
    member: str
    sha256: str
    bytes_: int
    data: bytes

    @property
    def identity(self) -> str:
        """A source name a reviewer can re-open: package, then member inside it."""
        return f"{self.package_filename}::{self.member}"


def read_member(root: Path, filename: str, member_key: str) -> SourceMember:
    """Read one named member out of a digest-verified package."""
    mounted = require_package(root, filename)
    member = mounted.package.members.get(member_key)
    if member is None:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: {filename} declares no member {member_key!r}. Members "
            "are named by this adapter so a reviewer can re-open exactly what was "
            "read; an unnamed member is not read by path guess."
        )
    with zipfile.ZipFile(mounted.path) as archive:
        try:
            data = archive.read(member)
        except KeyError:
            raise GovernanceBlock(
                f"{ADAPTER_ID}: {filename} does not contain {member!r} even though "
                "its digest matched the audited identity."
            ) from None
    return SourceMember(
        package_filename=filename,
        package_sha256=mounted.sha256,
        member=member,
        sha256=sha256_bytes(data),
        bytes_=len(data),
        data=data,
    )


# ---------------------------------------------------------------------------
# The source universe
# ---------------------------------------------------------------------------

#: FACT — the audited source population, per season.
SOURCE_UNIVERSE_SEASON_ROWS: dict[int, int] = {
    2006: 536,
    2007: 527,
    2008: 624,
    2009: 625,
    2010: 642,
    2011: 713,
    2024: 724,
    2025: 757,
}

HISTORICAL_SEASONS: tuple[int, ...] = (2006, 2007, 2008, 2009, 2010, 2011)
MODERN_SEASONS: tuple[int, ...] = (2024, 2025)

SOURCE_UNIVERSE_HISTORICAL_ROWS = sum(
    SOURCE_UNIVERSE_SEASON_ROWS[s] for s in HISTORICAL_SEASONS
)
SOURCE_UNIVERSE_MODERN_ROWS = sum(
    SOURCE_UNIVERSE_SEASON_ROWS[s] for s in MODERN_SEASONS
)
SOURCE_UNIVERSE_ROWS = SOURCE_UNIVERSE_HISTORICAL_ROWS + SOURCE_UNIVERSE_MODERN_ROWS

#: The experimental partition this lane is authorized to *test*, not to promote.
CANDIDATE_PARTITION: dict[str, tuple[int, ...]] = {
    "training": HISTORICAL_SEASONS,
    "validation": (2024,),
    "holdout": (2025,),
}

HOLDOUT_SEASON = 2025


def partition_of(season: int) -> str:
    for split, seasons in CANDIDATE_PARTITION.items():
        if season in seasons:
            return split
    raise GovernanceBlock(
        f"Season {season} sits in no candidate partition. The adapter assigns a "
        "split from the governed whole-season rule and never by proximity."
    )


# ---------------------------------------------------------------------------
# The 2011 lineage, stated rather than smoothed over
# ---------------------------------------------------------------------------

#: FACT — Baxter 2011 Source QA. Carried explicitly because the two numbers a
#: reader will meet elsewhere (712 and 711) differ for two *different* reasons,
#: and collapsing them would hide one of the exclusions.
LINEAGE_2011 = {
    "canonical_rebuild_rows": 713,
    "malformed_artifact_excluded": 1,
    "malformed_artifact_game_id": "G2011_P3056",
    "malformed_artifact_note": "Weber St. vs CONFW; level_a DIV_II, level_b ARTIFACT",
    "canonical_eligible_rows": 712,
    "engine_comparison_universe": 711,
    "engine_comparison_exclusion_game_id": "G2011_P2932",
    "engine_comparison_exclusion_note": (
        "Texas Tech 63, DIVISION II 6; omitted by the established rating universe"
    ),
}

#: FACT — Baxter ``Baxter_v1_complete_metrics.csv`` eligible-prediction counts.
#: Independently recomputed from the walk-forward ledgers by
#: :func:`model_evidence_census`; recorded here only so a drift is visible.
RECORDED_ELIGIBLE_PREDICTIONS: dict[int, int] = {
    2006: 365,
    2007: 354,
    2008: 460,
    2009: 457,
    2010: 466,
    2011: 493,
    2024: 528,
    2025: 569,
}

RECORDED_HISTORICAL_ELIGIBLE_TOTAL = sum(
    RECORDED_ELIGIBLE_PREDICTIONS[s] for s in HISTORICAL_SEASONS
)


# ---------------------------------------------------------------------------
# Exclusion vocabulary
# ---------------------------------------------------------------------------

#: Ordered exclusion gates. The order is the census: a row is charged to the
#: first gate it fails, so the reasons partition the universe exactly and the
#: counts add back to 5,148 without double-counting.
#:
#: Order is deliberate and is itself a governance statement. Provenance sits
#: above every field-completeness gate because a row whose result was not
#: recorded is not an incomplete observation — it is not an observation.
EXCLUSION_REASONS: tuple[str, ...] = (
    "SOURCE_ROW_MALFORMED_ARTIFACT",
    "SOURCE_KEY_DUPLICATE_UNRECONCILED",
    "MODEL_EVIDENCE_ROW_ABSENT",
    "EVIDENCE_DOMAIN_NOT_ADMISSIBLE",
    "PARTICIPANT_DIVISION_NOT_ESTABLISHED",
    "PARTICIPANT_DIVISION_OUTSIDE_CONTRACT_ENUM",
    "FCS_PARTICIPANT_PENDING_V3_POINT_SCALE_ADAPTER",
    "BAXTER_MINIMUM_PRIOR_GAMES_NOT_MET",
    "EXPECTED_MARGIN_NOT_RECORDED",
    "TEMPORAL_ORDER_EVIDENCE_INSUFFICIENT",
    "RESULT_OBSERVATION_DATE_NOT_RECORDED",
    "PREGAME_RATING_STATE_NOT_RECORDED",
)

EXCLUSION_REASON_NOTES: dict[str, str] = {
    "SOURCE_ROW_MALFORMED_ARTIFACT": (
        "The governed source records the row as a malformed artifact rather than a "
        "contest: a participant label that is not a team, or a score the source did "
        "not resolve. Excluded rather than repaired."
    ),
    "SOURCE_KEY_DUPLICATE_UNRECONCILED": (
        "Two different contests in the source universe share one game identifier, "
        "so the identifier does not identify a game. Every row carrying the "
        "repeated key is excluded — not just the second one — because choosing a "
        "survivor would be an unissued ruling, and game_id is the contract's "
        "deduplication and split-assignment key."
    ),
    "MODEL_EVIDENCE_ROW_ABSENT": (
        "No Baxter walk-forward row joins to this factual game row, so no "
        "expected_margin exists for it. Never substituted from another season, "
        "another model, or a full-season retrospective fit."
    ),
    "EVIDENCE_DOMAIN_NOT_ADMISSIBLE": (
        "The row's evidence domain is not one calibration admits. Under ruling "
        "R7-CAL-GOVERNED-SYNTHETIC-EVIDENCE a corpus that is byte-verified, "
        "provenance-bound and declared synthetic by its own governed source is "
        "admitted as GOVERNED_SYNTHETIC; a row whose domain is neither that nor "
        "OBSERVED_REAL_WORLD is refused. Before that ruling this gate refused every "
        "synthetic row and accounted for 4,521 of the 5,148."
    ),
    "PARTICIPANT_DIVISION_NOT_ESTABLISHED": (
        "The source classification for one or both participants is UNKNOWN, "
        "ARTIFACT or absent. opponent_division is required by the contract and its "
        "enum admits FBS and FCS only; UNKNOWN is never mapped to FBS."
    ),
    "PARTICIPANT_DIVISION_OUTSIDE_CONTRACT_ENUM": (
        "A participant is classified outside enum[FBS|FCS] — DIVISION II in the "
        "2011 archive. Refused rather than folded into the nearest admitted value."
    ),
    "FCS_PARTICIPANT_PENDING_V3_POINT_SCALE_ADAPTER": (
        "An FCS participant is identified. Blocker "
        "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER is open, so FCS games "
        "are excluded rather than silently fitted on an unresolved scale. This "
        "adapter neither closes that blocker nor proposes a point value for it."
    ),
    "BAXTER_MINIMUM_PRIOR_GAMES_NOT_MET": (
        "The governed walk-forward ledger marks the row ineligible under the frozen "
        "BAXTER-MOV-v1.0-R control of three minimum prior games per team. The "
        "source's own eligibility flag is read; no eligibility is re-derived here."
    ),
    "EXPECTED_MARGIN_NOT_RECORDED": (
        "The walk-forward ledger records no predicted margin for the row. "
        "expected_margin is never derived from actual_margin and never taken from a "
        "full-season retrospective fit."
    ),
    "TEMPORAL_ORDER_EVIDENCE_INSUFFICIENT": (
        "The source supplies no exact date, no source-supplied week ordinal and no "
        "sequence, so no basis in the successor precedence is supportable. Missing "
        "chronology is not fabricated to make the row pass."
    ),
    "RESULT_OBSERVATION_DATE_NOT_RECORDED": (
        "The contract requires observed_at — when the result became observable — and "
        "the source resolved no date for this row. A row admitted on week or "
        "sequence evidence has a provable order but no recorded observation "
        "timestamp, and one is not invented to fill the column."
    ),
    "PREGAME_RATING_STATE_NOT_RECORDED": (
        "pregame_team_rating and pregame_opponent_rating are unconditionally "
        "required contract fields, and the governed walk-forward ledger for this "
        "season records only the resulting predicted margin, not the two ratings "
        "behind it. Reconstructing them would be a replay presented as an "
        "observation."
    ),
}


# ---------------------------------------------------------------------------
# Governed source statements about the nature of the game population
# ---------------------------------------------------------------------------

#: FACT — verbatim sentences from the governed sources establishing that each
#: season block is a synthetic research universe rather than a recorded result
#: set. Quoted rather than paraphrased, because this is the finding that decides
#: the lane and a reviewer must be able to check it against the package.
SYNTHETIC_POPULATION_EVIDENCE: tuple[dict[str, str], ...] = (
    {
        "seasons": "2006-2011",
        "source": f"{PHASE4M}::reports/PHASE4M_WEEK_BY_WEEK_CLEANUP_REPORT.md",
        "statement": (
            "This package consolidates the source-derived chronological sequence, "
            "week, and date fields for all synthetic games from 2006 through 2011. "
            "... No external or real-world schedule was used."
        ),
    },
    {
        "seasons": "2006",
        "source": f"{BAXTER}::Baxter_Ratings_v1_2006_External_Validation.xlsx [README]",
        "statement": (
            "External validation of frozen BAXTER-MOV-v1.0-R on the existing 2006 "
            "synthetic archive."
        ),
    },
    {
        "seasons": "2006-2011, 2024-2025",
        "source": (
            f"{BAXTER}::Baxter_Ratings_v1_Joint_2024_2025_Validation_and_Freeze.xlsx "
            "[Doctrine]"
        ),
        "statement": (
            "Scope: Separate-season opponent-adjusted margin ratings for synthetic "
            "NCAA research universes."
        ),
    },
    {
        "seasons": "2024-2025",
        "source": f"{PHASE5D}::02_Event_Stream/official_synthetic_event_stream_2024_2025.csv",
        "statement": (
            "Every row carries official_synthetic=True; 174 of the 724 2024 rows "
            "carry provenance SYNTH_FILL, SYNTH_BLOCK or SYNTH_POST."
        ),
    },
    {
        "seasons": "2025",
        "source": f"{PHASE5D}::10_Source_Rulings/2025 Synthetic Season LOCKED v3.xlsx [Certification]",
        "statement": (
            "provenance: SCHEDULE SYNTHETIC. SCORES SIMULATED. NCG result "
            "user-specified. Bowl names fictional."
        ),
    },
)

#: Provenance labels the Phase5D event stream uses, and whether each names a
#: recorded result. ``REAL`` rows are anchored to a named, digest-pinned external
#: result source (a sports-reference 2024 schedule PDF, per the package's own
#: INPUTS.md); every other label names a constructed score.
#:
#: Retained after ruling R7 rather than deleted, because it is still the fact
#: that decides a row's evidence *domain*. What changed is the consequence: a
#: constructed score is now GOVERNED_SYNTHETIC evidence rather than no evidence.
MODERN_PROVENANCE_IS_RECORDED_RESULT: dict[str, bool] = {
    "REAL": True,
    "SYNTH_FILL": False,
    "SYNTH_BLOCK": False,
    "SYNTH_POST": False,
    "OFFICIAL_SYNTHETIC_2025_LOCKED": False,
}


def evidence_domain_of(row: "UniverseRow") -> str:
    """The evidence domain a row's own source provenance establishes.

    Read from the source, never chosen. A row the Phase5D stream marks ``REAL``
    is anchored to a named external result source; everything else in this
    corpus is a constructed score its package declares synthetic.
    """
    if row.result_is_recorded:
        return cal.EVIDENCE_DOMAIN_OBSERVED_REAL_WORLD
    return cal.EVIDENCE_DOMAIN_GOVERNED_SYNTHETIC


#: The governed synthetic declaration for each source block, assembled from the
#: package digests and the verbatim source statements above. These are what
#: ruling R7 requires a corpus to carry before it receives any authority, and
#: :func:`admitted_evidence_domains` puts each one through the governed gate
#: rather than trusting this table.
EVIDENCE_DOMAIN_DECLARATIONS: tuple[dict[str, str], ...] = (
    {
        "seasons": "2006-2011",
        "package": PHASE4M,
        "member": (
            "NCAA_Phase4M_2006_2011_Week_By_Week_Cleanup/reports/"
            "PHASE4M_WEEK_BY_WEEK_CLEANUP_REPORT.md"
        ),
        "member_key": "report",
        "declared_by": "PHASE4M_WEEK_BY_WEEK_CLEANUP_REPORT",
        "declaration": (
            "This package consolidates the source-derived chronological sequence, "
            "week, and date fields for all synthetic games from 2006 through 2011. "
            "... No external or real-world schedule was used."
        ),
    },
    {
        "seasons": "2024-2025",
        "package": PHASE5D,
        "member": (
            "Power_Crunch_Research_Lab_Phase5D_WalkForward/02_Event_Stream/"
            "official_synthetic_event_stream_2024_2025.csv"
        ),
        "member_key": "event_stream",
        "declared_by": "PHASE5D_OFFICIAL_SYNTHETIC_EVENT_STREAM",
        "declaration": (
            "Every row carries official_synthetic=True; 174 of the 724 2024 rows "
            "carry provenance SYNTH_FILL, SYNTH_BLOCK or SYNTH_POST."
        ),
    },
    {
        "seasons": "2025",
        "package": PHASE5D,
        "member": (
            "Power_Crunch_Research_Lab_Phase5D_WalkForward/10_Source_Rulings/"
            "2025 Synthetic Season LOCKED v3.xlsx"
        ),
        "member_key": "locked_2025",
        "declared_by": "2025_SYNTHETIC_SEASON_LOCKED_V3_CERTIFICATION",
        "declaration": (
            "provenance: SCHEDULE SYNTHETIC. SCORES SIMULATED. NCG result "
            "user-specified. Bowl names fictional."
        ),
    },
)


def admitted_evidence_domains(root: Path) -> tuple[cal.EvidenceDomainDeclaration, ...]:
    """Put every governed synthetic declaration through the R7 gate.

    Both digests are read from the mounted bytes rather than copied from a
    table, so a declaration cannot outlive the package it describes. A block
    whose gate refuses is a block this adapter has no authority over, and the
    refusal propagates rather than being caught here.
    """
    admitted = []
    for entry in EVIDENCE_DOMAIN_DECLARATIONS:
        package = require_package(root, entry["package"])
        member = read_member(root, entry["package"], entry["member_key"])
        admitted.append(
            cal.require_evidence_domain(
                cal.EvidenceDomainDeclaration(
                    domain=cal.EVIDENCE_DOMAIN_GOVERNED_SYNTHETIC,
                    source_package=entry["package"],
                    source_package_sha256=package.sha256,
                    source_member=entry["member"],
                    source_member_sha256=member.sha256,
                    declared_by=entry["declared_by"],
                    declaration=entry["declaration"],
                    seasons=entry["seasons"],
                ),
                approval_token=CHAIRMAN_EVIDENCE_DOMAIN_APPROVAL_TOKEN,
            )
        )
    return tuple(admitted)


# ---------------------------------------------------------------------------
# Reading the sources
# ---------------------------------------------------------------------------


def _csv_rows(member: SourceMember) -> list[dict[str, str]]:
    text = member.data.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def _sheet_rows(member: SourceMember, sheet: str, header_row: int) -> list[dict[str, Any]]:
    """Read one worksheet into dicts, taking the header from a stated row.

    The header row is stated per sheet rather than sniffed. These workbooks put a
    title banner above the header on some sheets and not others, and a sniffed
    header would silently read a banner as column names.
    """
    workbook = load_workbook(io.BytesIO(member.data), read_only=True, data_only=True)
    try:
        if sheet not in workbook.sheetnames:
            raise GovernanceBlock(
                f"{member.identity} has no sheet {sheet!r}; it declares "
                f"{workbook.sheetnames}."
            )
        grid = list(workbook[sheet].iter_rows(values_only=True))
    finally:
        workbook.close()
    if len(grid) < header_row:
        raise GovernanceBlock(
            f"{member.identity} sheet {sheet!r} has no header at row {header_row}."
        )
    header = [str(c) if c is not None else "" for c in grid[header_row - 1]]
    return [
        dict(zip(header, row))
        for row in grid[header_row:]
        if any(cell is not None for cell in row)
    ]


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _number(value: Any) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _flag(value: Any) -> bool | None:
    """Read a boolean the way the sources actually spell it, or refuse."""
    text = _text(value).lower()
    if text in ("true", "y", "yes", "1"):
        return True
    if text in ("false", "n", "no", "0"):
        return False
    return None


# ---------------------------------------------------------------------------
# Baxter walk-forward evidence, per season
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class WalkForwardSpec:
    """Where each season's walk-forward evidence lives and what it is called.

    The six historical workbooks and the joint modern workbook use six different
    column vocabularies for the same quantities. The mapping is stated per season
    rather than guessed by fuzzy name matching, because a fuzzy match between
    ``pred_margin_a`` and ``pred_margin_full`` would silently swap a genuine
    walk-forward prediction for a full-season retrospective fit — the exact
    substitution the contract's pregame provenance requirement forbids.
    """

    season: int
    member_key: str
    sheet: str
    header_row: int
    game_id_column: str
    expected_margin_column: str
    actual_margin_column: str
    eligible_column: str
    team_a_column: str | None = None
    team_b_column: str | None = None
    pregame_rating_a_column: str | None = None
    pregame_rating_b_column: str | None = None
    hfa_column: str | None = None
    prior_games_a_column: str | None = None
    prior_games_b_column: str | None = None
    season_filter_column: str | None = None
    game_id_from_row_key: bool = False


WALK_FORWARD_SPECS: tuple[WalkForwardSpec, ...] = (
    WalkForwardSpec(
        season=2006, member_key="wf_2006", sheet="Walk Forward", header_row=2,
        game_id_column="game_id", expected_margin_column="pred_margin_a",
        actual_margin_column="actual_margin_a", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b",
        pregame_rating_a_column="rating_a_pre", pregame_rating_b_column="rating_b_pre",
        hfa_column="hfa_pre",
        prior_games_a_column="prior_a", prior_games_b_column="prior_b",
    ),
    WalkForwardSpec(
        season=2007, member_key="wf_2007", sheet="Walk Forward", header_row=2,
        game_id_column="game_id", expected_margin_column="pred_margin_a",
        actual_margin_column="actual_margin_a", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b",
        pregame_rating_a_column="rating_a_pre", pregame_rating_b_column="rating_b_pre",
        hfa_column="hfa_pre",
        prior_games_a_column="prior_a", prior_games_b_column="prior_b",
    ),
    WalkForwardSpec(
        season=2008, member_key="wf_2008", sheet="Walk Forward", header_row=2,
        game_id_column="game_id", expected_margin_column="pred_margin_a",
        actual_margin_column="margin_a", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b", hfa_column="fitted_hfa",
        prior_games_a_column="prior_games_a", prior_games_b_column="prior_games_b",
    ),
    WalkForwardSpec(
        season=2009, member_key="wf_2009", sheet="Walk Forward", header_row=2,
        game_id_column="game_id", expected_margin_column="pred_margin_a",
        actual_margin_column="margin_a", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b", hfa_column="fitted_hfa",
        prior_games_a_column="prior_games_a", prior_games_b_column="prior_games_b",
    ),
    WalkForwardSpec(
        season=2010, member_key="wf_2010", sheet="Walk Forward", header_row=1,
        game_id_column="game_id", expected_margin_column="pred_margin_a",
        actual_margin_column="margin_a", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b", hfa_column="fitted_hfa",
        prior_games_a_column="prior_games_a", prior_games_b_column="prior_games_b",
    ),
    WalkForwardSpec(
        season=2011, member_key="wf_2011", sheet="Walk Forward", header_row=1,
        game_id_column="game_id", expected_margin_column="pred_margin",
        actual_margin_column="actual_margin", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b",
        prior_games_a_column="prior_a", prior_games_b_column="prior_b",
    ),
    WalkForwardSpec(
        season=2024, member_key="wf_joint_modern", sheet="Walk Forward", header_row=4,
        game_id_column="row_key", expected_margin_column="pred_margin",
        actual_margin_column="actual_margin", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b", hfa_column="hfa",
        prior_games_a_column="prior_a", prior_games_b_column="prior_b",
        season_filter_column="season", game_id_from_row_key=True,
    ),
    WalkForwardSpec(
        season=2025, member_key="wf_joint_modern", sheet="Walk Forward", header_row=4,
        game_id_column="row_key", expected_margin_column="pred_margin",
        actual_margin_column="actual_margin", eligible_column="eligible",
        team_a_column="team_a", team_b_column="team_b", hfa_column="hfa",
        prior_games_a_column="prior_a", prior_games_b_column="prior_b",
        season_filter_column="season", game_id_from_row_key=True,
    ),
)

WALK_FORWARD_SPECS_BY_SEASON = {s.season: s for s in WALK_FORWARD_SPECS}

#: Sheets in the same governed workbooks that hold a *full-season retrospective*
#: fit rather than a walk-forward prediction. Named so the refusal in
#: :func:`reject_full_season_retrospective_margin` can be by identity rather than
#: by hoping nobody points a spec at one.
FULL_SEASON_RETROSPECTIVE_SHEETS: tuple[str, ...] = (
    "Full Season Games",
    "Full Game Fit",
    "Game Residuals",
)

FULL_SEASON_RETROSPECTIVE_COLUMNS: tuple[str, ...] = (
    "pred_margin_full",
    "residual_full",
    "predicted_margin_2024_fit",
)


def reject_full_season_retrospective_margin(sheet: str, column: str) -> None:
    """Refuse a retrospective fit standing in for a pregame prediction.

    The governed workbooks carry both, side by side, under names one letter
    apart. A full-season fit has already seen the game it is predicting, so a
    residual computed against it is in-sample and every out-of-sample number
    downstream of it is optimistic.
    """
    if sheet in FULL_SEASON_RETROSPECTIVE_SHEETS:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: sheet {sheet!r} holds a full-season retrospective fit, "
            "not a walk-forward prediction. expected_margin must be the margin "
            "predicted BEFORE the game; a value fitted on the full season has "
            "already absorbed the outcome it is being scored against."
        )
    if column in FULL_SEASON_RETROSPECTIVE_COLUMNS:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: column {column!r} is a full-season or opposite-season "
            "retrospective fit and may not be read as expected_margin. A final "
            "or full-season rating cannot masquerade as a pregame prediction."
        )


@dataclass(frozen=True)
class ModelEvidenceRow:
    """One walk-forward prediction, as the governed ledger recorded it."""

    season: int
    game_id: str
    expected_margin: float | None
    actual_margin: float | None
    eligible: bool | None
    team_a: str
    team_b: str
    pregame_rating_a: float | None
    pregame_rating_b: float | None
    hfa: float | None
    prior_games_a: float | None
    prior_games_b: float | None
    source_identity: str
    source_sha256: str


@dataclass(frozen=True)
class ModelEvidence:
    """The walk-forward ledgers, plus what deduplicating them cost.

    ``by_season`` is the join map and is necessarily keyed by identifier, so it
    can hold only one row per key. ``duplicate_keys`` and ``raw_row_counts``
    record what that collapsed, because a ledger row that disappears into a
    dictionary is exactly the kind of loss the reconciliation report exists to
    surface.
    """

    by_season: dict[int, dict[str, ModelEvidenceRow]]
    duplicate_keys: dict[int, frozenset[str]]
    raw_row_counts: dict[int, int]
    raw_eligible_counts: dict[int, int]

    def get(self, season: int, default: Any = None) -> Any:
        return self.by_season.get(season, default)

    def __getitem__(self, season: int) -> dict[str, ModelEvidenceRow]:
        return self.by_season[season]


def load_model_evidence(root: Path) -> ModelEvidence:
    """Load the Baxter walk-forward ledgers, keyed by season then game id."""
    out: dict[int, dict[str, ModelEvidenceRow]] = {}
    duplicates: dict[int, frozenset[str]] = {}
    raw_rows: dict[int, int] = {}
    raw_eligible: dict[int, int] = {}
    cache: dict[str, SourceMember] = {}
    for spec in WALK_FORWARD_SPECS:
        reject_full_season_retrospective_margin(spec.sheet, spec.expected_margin_column)
        if spec.member_key not in cache:
            cache[spec.member_key] = read_member(root, BAXTER, spec.member_key)
        member = cache[spec.member_key]
        rows = _sheet_rows(member, spec.sheet, spec.header_row)
        if spec.season_filter_column:
            rows = [
                r for r in rows
                if _text(r.get(spec.season_filter_column)) == str(spec.season)
            ]
        season_rows: dict[str, ModelEvidenceRow] = {}
        repeated: set[str] = set()
        raw_rows[spec.season] = 0
        raw_eligible[spec.season] = 0
        for row in rows:
            key = _text(row.get(spec.game_id_column))
            if spec.game_id_from_row_key:
                key = key.split("__")[0]
            if not key:
                continue
            raw_rows[spec.season] += 1
            if _flag(row.get(spec.eligible_column)) is True:
                raw_eligible[spec.season] += 1
            evidence = ModelEvidenceRow(
                season=spec.season,
                game_id=key,
                expected_margin=_number(row.get(spec.expected_margin_column)),
                actual_margin=_number(row.get(spec.actual_margin_column)),
                eligible=_flag(row.get(spec.eligible_column)),
                team_a=_text(row.get(spec.team_a_column)) if spec.team_a_column else "",
                team_b=_text(row.get(spec.team_b_column)) if spec.team_b_column else "",
                pregame_rating_a=(
                    _number(row.get(spec.pregame_rating_a_column))
                    if spec.pregame_rating_a_column else None
                ),
                pregame_rating_b=(
                    _number(row.get(spec.pregame_rating_b_column))
                    if spec.pregame_rating_b_column else None
                ),
                hfa=_number(row.get(spec.hfa_column)) if spec.hfa_column else None,
                prior_games_a=(
                    _number(row.get(spec.prior_games_a_column))
                    if spec.prior_games_a_column else None
                ),
                prior_games_b=(
                    _number(row.get(spec.prior_games_b_column))
                    if spec.prior_games_b_column else None
                ),
                source_identity=f"{member.identity} [{spec.sheet}]",
                source_sha256=member.sha256,
            )
            if key in season_rows:
                # A repeated key in the model ledger is a reconciliation finding,
                # not a row to overwrite. The first row is kept so the join stays
                # deterministic, and the key is recorded so the loss is visible
                # and every row under it can be excluded.
                repeated.add(key)
                continue
            season_rows[key] = evidence
        out[spec.season] = season_rows
        duplicates[spec.season] = frozenset(repeated)
    return ModelEvidence(
        by_season=out,
        duplicate_keys=duplicates,
        raw_row_counts=raw_rows,
        raw_eligible_counts=raw_eligible,
    )


def validate_expected_margin_transform(
    evidence: "ModelEvidence",
    universe: Sequence["UniverseRow"],
    *,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    """Check the recorded pregame ratings actually reproduce the recorded margin.

    Only 2006 and 2007 carry ``rating_a_pre``/``rating_b_pre``, so this is the only
    place in the corpus where the declared transform can be checked against the
    evidence rather than taken on trust. Where it checks out, the transform name
    recorded on the dataset is earned; where a season carries no ratings, the
    honest consequence is that the season cannot supply the two required rating
    fields at all, not that the transform is applied to invent them.
    """
    by_id = {row.game_id: row for row in universe}
    report: dict[str, Any] = {}
    for season in (2006, 2007):
        checked = mismatched = 0
        for game_id, model_row in sorted(evidence.get(season, {}).items()):
            if model_row.eligible is not True:
                continue
            if None in (
                model_row.pregame_rating_a,
                model_row.pregame_rating_b,
                model_row.hfa,
                model_row.expected_margin,
            ):
                continue
            source_row = by_id.get(game_id)
            if source_row is None:
                continue
            checked += 1
            if source_row.neutral:
                predicted = model_row.pregame_rating_a - model_row.pregame_rating_b
            else:
                signed = model_row.hfa if source_row.subject_is_home else -model_row.hfa
                predicted = (
                    model_row.pregame_rating_a - model_row.pregame_rating_b + signed
                )
            if abs(predicted - model_row.expected_margin) > tolerance:
                mismatched += 1
        report[str(season)] = {
            "eligible_rows_with_recorded_pregame_ratings": checked,
            "transform_mismatches": mismatched,
            "transform_reproduces_recorded_expected_margin": mismatched == 0,
        }
    return report


# ---------------------------------------------------------------------------
# The factual universe row
# ---------------------------------------------------------------------------

#: Source classification labels and how the contract's enum[FBS|FCS] treats them.
DIVISION_ADMITTED = "ADMITTED"
DIVISION_NOT_ESTABLISHED = "NOT_ESTABLISHED"
DIVISION_OUTSIDE_ENUM = "OUTSIDE_ENUM"

DIVISION_CLASSIFICATION: dict[str, str] = {
    "FBS": DIVISION_ADMITTED,
    "FCS": DIVISION_ADMITTED,
    "DIV_II": DIVISION_OUTSIDE_ENUM,
    "DIVISION II": DIVISION_OUTSIDE_ENUM,
    "UNKNOWN": DIVISION_NOT_ESTABLISHED,
    "ARTIFACT": DIVISION_NOT_ESTABLISHED,
    "": DIVISION_NOT_ESTABLISHED,
}


def classify_division(label: str) -> str:
    """Classify a source division label, refusing to guess an unseen one.

    An unrecognised label is ``NOT_ESTABLISHED`` rather than FBS. That asymmetry
    is the point: the failure mode this guards against is a new label quietly
    inheriting the most permissive treatment.
    """
    return DIVISION_CLASSIFICATION.get(_text(label).upper(), DIVISION_NOT_ESTABLISHED)


@dataclass(frozen=True)
class TemporalEvidence:
    """The strongest temporal basis a source row actually supports."""

    basis: str
    value: dict[str, Any]
    source: str
    source_sha256: str


@dataclass(frozen=True)
class UniverseRow:
    """One row of the 5,148-game source universe, normalized but not interpreted."""

    game_id: str
    season: int
    subject: str
    opponent: str
    subject_division: str
    opponent_division: str
    subject_score: float | None
    opponent_score: float | None
    neutral: bool
    subject_is_home: bool
    week_ordinal: int | None
    week_label: str
    stage_label: str
    game_date: str | None
    sequence: int | None
    provenance_label: str
    result_is_recorded: bool
    overtime_recorded: bool
    overtime_periods: float | None
    source_identity: str
    source_sha256: str
    #: 1-based ordinal of this record within its source member, counting the
    #: header as row 1. Immutable given fixed bytes, which is what makes the
    #: provenance identity below stable across builds.
    source_row_ordinal: int = 0
    malformed: bool = False
    malformed_note: str = ""

    @property
    def provenance_identity(self) -> str:
        """Immutable identity from source coordinates, not from football data.

        ``game_id`` is the source's key and it is not always unique: the 2024
        event stream gives T073vT114 to two different contests. This identity is
        built from the bytes the record lives in — member digest, member name,
        row ordinal — so two records that share a game_id still differ here, and
        neither has to be discarded or renamed to tell them apart.
        """
        return f"{self.source_sha256}::{self.source_identity}::{self.source_row_ordinal:06d}"

    @property
    def provenance_identity_sha256(self) -> str:
        return sha256_bytes(self.provenance_identity.encode("utf-8"))

    @property
    def actual_margin(self) -> float | None:
        if self.subject_score is None or self.opponent_score is None:
            return None
        return self.subject_score - self.opponent_score

    @property
    def split(self) -> str:
        return partition_of(self.season)

    @property
    def venue(self) -> str:
        if self.neutral:
            return "NEUTRAL"
        return "HOME" if self.subject_is_home else "AWAY"


def _historical_rows(root: Path) -> list[UniverseRow]:
    member = read_member(root, PHASE4M, "ledger")
    rows: list[UniverseRow] = []
    for ordinal, raw in enumerate(_csv_rows(member), start=2):
        season = int(_text(raw["season"]))
        score_a, score_b = _number(raw.get("score_a")), _number(raw.get("score_b"))
        level_a, level_b = _text(raw.get("level_a")), _text(raw.get("level_b"))
        # A row is malformed when it records no contest at all: an unresolvable
        # score, or *both* participants classified outside enum[FBS|FCS]. The
        # second condition is what isolates the archive's single malformed
        # artifact (Weber St. vs CONFW, DIV_II against ARTIFACT) from the
        # one-sided classification gaps, which are a different exclusion with a
        # different reason. Together they reproduce the lineage the governed
        # source states: 713 canonical, 712 after the malformed artifact, 711
        # after Texas Tech vs DIVISION II.
        both_sides_unrateable = (
            classify_division(level_a) != DIVISION_ADMITTED
            and classify_division(level_b) != DIVISION_ADMITTED
        )
        malformed = score_a is None or score_b is None or both_sides_unrateable
        note = ""
        if malformed:
            note = (
                f"participants {_text(raw.get('team_a'))!r} / "
                f"{_text(raw.get('team_b'))!r}, levels {level_a}/{level_b}"
            )
        week_text = _text(raw.get("clean_week"))
        week_ordinal = int(week_text) if week_text.isdigit() else None
        date = _text(raw.get("clean_game_date")) or None
        sequence_text = _text(raw.get("chronology_sequence"))
        neutral = _flag(raw.get("neutral"))
        subject_home = _flag(raw.get("a_is_home"))
        rows.append(
            UniverseRow(
                game_id=_text(raw["game_id"]),
                season=season,
                subject=_text(raw.get("team_a")),
                opponent=_text(raw.get("team_b")),
                subject_division=level_a,
                opponent_division=level_b,
                subject_score=score_a,
                opponent_score=score_b,
                neutral=bool(neutral),
                # The 2008-2011 sheets leave a_is_home blank; where the source did
                # not state a side, the row is treated as not-home rather than
                # home-by-default, and the venue disagreement is reported.
                subject_is_home=bool(subject_home),
                week_ordinal=week_ordinal,
                week_label=week_text,
                stage_label="",
                game_date=date,
                sequence=int(sequence_text) if sequence_text.isdigit() else None,
                provenance_label="PHASE4M_SYNTHETIC_ARCHIVE",
                result_is_recorded=False,
                overtime_recorded=False,
                overtime_periods=None,
                source_identity=member.identity,
                source_sha256=member.sha256,
                source_row_ordinal=ordinal,
                malformed=malformed,
                malformed_note=note,
            )
        )
    return rows


def _modern_rows(root: Path) -> list[UniverseRow]:
    member = read_member(root, PHASE5D, "event_stream")
    rows: list[UniverseRow] = []
    for ordinal, raw in enumerate(_csv_rows(member), start=2):
        season = int(_text(raw["season"]))
        provenance = _text(raw.get("provenance"))
        if provenance not in MODERN_PROVENANCE_IS_RECORDED_RESULT:
            raise GovernanceBlock(
                f"{ADAPTER_ID}: {member.identity} row {_text(raw.get('game_id'))!r} "
                f"carries unrecognised provenance {provenance!r}. Whether a score "
                "was recorded or constructed is not inferred from an unknown label."
            )
        week_num = _number(raw.get("week_num"))
        ot_a, ot_b = _number(raw.get("ot_a")), _number(raw.get("ot_b"))
        ot_recorded = ot_a is not None and ot_b is not None
        rows.append(
            UniverseRow(
                game_id=_text(raw["game_id"]),
                season=season,
                subject=_text(raw.get("team_a")),
                opponent=_text(raw.get("team_b")),
                subject_division=_text(raw.get("synthetic_division_a")),
                opponent_division=_text(raw.get("synthetic_division_b")),
                subject_score=_number(raw.get("score_a")),
                opponent_score=_number(raw.get("score_b")),
                neutral=bool(_flag(raw.get("neutral"))),
                subject_is_home=bool(_flag(raw.get("a_is_home"))),
                week_ordinal=int(week_num) if week_num is not None else None,
                week_label=_text(raw.get("week")),
                stage_label=_text(raw.get("phase")),
                game_date=_text(raw.get("game_date")) or None,
                sequence=int(_text(raw["global_sequence"])),
                provenance_label=provenance,
                result_is_recorded=MODERN_PROVENANCE_IS_RECORDED_RESULT[provenance],
                overtime_recorded=ot_recorded,
                overtime_periods=(ot_a or 0.0) + (ot_b or 0.0) if ot_recorded else None,
                source_identity=member.identity,
                source_sha256=member.sha256,
                source_row_ordinal=ordinal,
            )
        )
    return rows


def load_source_universe(root: Path) -> list[UniverseRow]:
    """Load all 5,148 source-universe rows and prove the arithmetic."""
    rows = _historical_rows(root) + _modern_rows(root)
    counts: dict[int, int] = {}
    for row in rows:
        counts[row.season] = counts.get(row.season, 0) + 1
    if counts != SOURCE_UNIVERSE_SEASON_ROWS:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: the mounted sources yield season counts {counts}, not the "
            f"audited {SOURCE_UNIVERSE_SEASON_ROWS}. The source universe is a fact "
            "about the packages; a disagreement is refused rather than reconciled."
        )
    if len(rows) != SOURCE_UNIVERSE_ROWS:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: source universe is {len(rows)} rows, not "
            f"{SOURCE_UNIVERSE_ROWS}."
        )
    return rows


# ---------------------------------------------------------------------------
# Temporal evidence resolution
# ---------------------------------------------------------------------------


def resolve_temporal_evidence(row: UniverseRow) -> TemporalEvidence | None:
    """Select the strongest basis the row's source actually supports.

    Precedence is the ruling's, strongest first, with one omission that is the
    whole point of the adapter: :data:`cal.BASIS_EXACT_EVENT_TIME` is never
    reachable, because a time-of-day census across all four packages found zero
    kickoff timestamps. ``event_time`` therefore stays null on every row this
    adapter produces, and no code path here can set it.

    ``GOVERNED_SOURCE_SEQUENCE`` scopes its source name to the season. The
    historical ledger restarts its sequence at 1 in every season, and the
    ordering domain is keyed by source rather than by season, so an unscoped name
    would put 2006 sequence 5 and 2011 sequence 5 in one domain and claim an
    order between them that the source never stated.
    """
    if row.game_date:
        return TemporalEvidence(
            basis=cal.BASIS_EXACT_GAME_DATE,
            value={"season": row.season, "game_date": row.game_date},
            source=row.source_identity,
            source_sha256=row.source_sha256,
        )
    if row.week_ordinal is not None:
        value: dict[str, Any] = {"season": row.season, "week_ordinal": row.week_ordinal}
        if row.week_label:
            value["week_label"] = row.week_label
        if row.stage_label:
            value["stage_label"] = row.stage_label
        return TemporalEvidence(
            basis=cal.BASIS_WEEK_STAGE_DATE,
            value=value,
            source=row.source_identity,
            source_sha256=row.source_sha256,
        )
    if row.sequence is not None:
        value = {"season": row.season, "sequence": row.sequence}
        if row.week_label:
            value["week_label"] = row.week_label
        if row.stage_label:
            value["stage_label"] = row.stage_label
        return TemporalEvidence(
            basis=cal.BASIS_GOVERNED_SOURCE_SEQUENCE,
            value=value,
            source=f"{row.source_identity}#season={row.season}",
            source_sha256=row.source_sha256,
        )
    return None


def temporal_basis_of(row: UniverseRow) -> str | None:
    evidence = resolve_temporal_evidence(row)
    return evidence.basis if evidence is not None else None


def partitioned_ordering_rows(
    universe: Sequence[UniverseRow],
) -> list[cal.PartitionedObservation]:
    """Admit every row that has a supportable basis into the governed order.

    This is an **ordering proof, not an admission of evidence**. It reads
    chronology and nothing else — no score, no margin, no rating — so it can run
    across the whole corpus regardless of whether a row's result is admissible
    calibration evidence. Schema validation and row ordering are explicitly not
    model selection, and no number computed here reaches a coefficient.

    Rows under a duplicated identifier are left out: ``game_id`` is the split
    assignment key, and a repeated key would collapse two contests into one
    bucket before the ordering could be proven.
    """
    duplicated = duplicated_source_keys(universe)
    rows: list[cal.PartitionedObservation] = []
    for row in universe:
        if row.game_id in duplicated:
            continue
        evidence = resolve_temporal_evidence(row)
        if evidence is None:
            continue
        order = cal.admit_temporal_order(
            row.game_id,
            evidence=cal.TemporalOrderEvidence(
                basis=evidence.basis,
                value=evidence.value,
                source=evidence.source,
                source_sha256=evidence.source_sha256,
            ),
        )
        rows.append(
            cal.PartitionedObservation(
                game_id=row.game_id,
                season=row.season,
                split=row.split,
                order=order,
            )
        )
    return rows


def prove_candidate_partition_ordering(
    root: Path | None = None, universe: Sequence[UniverseRow] | None = None
) -> dict[str, Any]:
    """Prove the experimental partition is forward-only on governed evidence.

    Runs the corpus's own chronology through the authoritative gate,
    :func:`cal.require_governed_temporal_split_integrity`, which proves
    max(training) < min(validation) and max(validation) < min(holdout) inside
    every shared ordering domain and refuses any boundary it cannot prove.

    Proving the ordering is not admitting the observations. The rows here carry
    no result and no prediction, and the corpus still fails the contract for the
    reasons :func:`build` reports.
    """
    rows = (
        list(universe)
        if universe is not None
        else load_source_universe(Path(root) if root is not None else default_mount_root())
    )
    return cal.require_governed_temporal_split_integrity(partitioned_ordering_rows(rows))


def refuse_random_partition(method: str) -> str:
    """Refuse any non-temporal split assignment, by delegation not by restatement."""
    return cal.require_temporal_split_assignment(method)


def refuse_holdout_selection_use(purpose: str = "regime selection") -> None:
    """Refuse the 2025 holdout as a selection surface.

    The adapter never scores the holdout. This exists so a caller that reaches
    for it gets the contract's refusal rather than a number.
    """
    cal.require_selection_split("holdout", purpose=purpose)


# ---------------------------------------------------------------------------
# Reconciliation between the factual ledger and the model evidence
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SeasonReconciliation:
    season: int
    source_game_count: int
    model_evidence_row_count: int
    matched: int
    unmatched_factual_games: int
    unmatched_prediction_rows: int
    duplicate_source_keys: int
    duplicate_source_key_rows: int
    duplicate_model_keys: int
    actual_margin_disagreements: int
    team_identity_disagreements: int
    site_neutral_disagreements: int
    classification_disagreements: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_game_count": self.source_game_count,
            "model_evidence_row_count": self.model_evidence_row_count,
            "matched": self.matched,
            "unmatched_factual_games": self.unmatched_factual_games,
            "unmatched_prediction_rows": self.unmatched_prediction_rows,
            "duplicate_source_keys": self.duplicate_source_keys,
            "duplicate_source_key_rows": self.duplicate_source_key_rows,
            "duplicate_model_keys": self.duplicate_model_keys,
            "actual_margin_disagreements": self.actual_margin_disagreements,
            "team_identity_disagreements": self.team_identity_disagreements,
            "site_neutral_disagreements": self.site_neutral_disagreements,
            "classification_disagreements": self.classification_disagreements,
        }


def reconcile(
    universe: Sequence[UniverseRow],
    evidence: "ModelEvidence",
    *,
    margin_tolerance: float = 1e-9,
) -> dict[int, SeasonReconciliation]:
    """Join factual rows to model evidence by identifier and report every gap.

    The join key is the game identifier both sides carry. Team names are never a
    join key: the corpus spells the same team several ways across seasons, and a
    name join would silently pair the wrong games and then average away the
    error.

    An ``actual_margin`` disagreement is counted here and raised by
    :func:`require_no_actual_margin_disagreement`, which the build calls before
    anything reads a margin. Rows under a *duplicated* identifier are held out of
    that comparison and counted under ``duplicate_source_key_rows`` instead: when
    one key names two different contests, the model ledger can only agree with
    one of them, and reporting the resulting mismatch as an independent score
    conflict would count one defect twice and hide its actual cause.
    """
    out: dict[int, SeasonReconciliation] = {}
    for season in sorted(SOURCE_UNIVERSE_SEASON_ROWS):
        source_rows = [r for r in universe if r.season == season]
        model_rows = evidence.get(season, {})
        seen: dict[str, int] = {}
        for row in source_rows:
            seen[row.game_id] = seen.get(row.game_id, 0) + 1
        model_duplicated = set(evidence.duplicate_keys.get(season, frozenset()))
        duplicated = {key for key, count in seen.items() if count > 1} | model_duplicated
        duplicate_source = len(duplicated)
        duplicate_rows = sum(seen.get(key, 0) for key in duplicated)

        matched = margin_bad = team_bad = site_bad = class_bad = 0
        matched_keys: set[str] = set()
        for row in source_rows:
            model_row = model_rows.get(row.game_id)
            if model_row is None:
                continue
            matched += 1
            matched_keys.add(row.game_id)
            if row.game_id in duplicated:
                continue
            if row.actual_margin is not None and model_row.actual_margin is not None:
                if abs(row.actual_margin - model_row.actual_margin) > margin_tolerance:
                    margin_bad += 1
            if model_row.team_a and model_row.team_b:
                if (
                    model_row.team_a != row.subject
                    or model_row.team_b != row.opponent
                ):
                    team_bad += 1
        out[season] = SeasonReconciliation(
            season=season,
            source_game_count=len(source_rows),
            model_evidence_row_count=evidence.raw_row_counts.get(season, len(model_rows)),
            matched=matched,
            unmatched_factual_games=len(source_rows) - matched,
            unmatched_prediction_rows=len(set(model_rows) - matched_keys),
            duplicate_source_keys=duplicate_source,
            duplicate_source_key_rows=duplicate_rows,
            duplicate_model_keys=len(model_duplicated),
            actual_margin_disagreements=margin_bad,
            team_identity_disagreements=team_bad,
            site_neutral_disagreements=site_bad,
            classification_disagreements=class_bad,
        )
    return out


def require_no_actual_margin_disagreement(
    reconciliation: Mapping[int, SeasonReconciliation]
) -> None:
    """Fail closed on any conflicting recorded score across joined sources.

    Two governed sources that disagree about what the score was cannot both be
    right, and picking one is a silent ruling. The build stops until the conflict
    is explained.
    """
    offending = {
        season: report.actual_margin_disagreements
        for season, report in sorted(reconciliation.items())
        if report.actual_margin_disagreements
    }
    if offending:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: joined sources disagree about the recorded result in "
            f"{offending}. A conflicting actual score fails closed until it is "
            "explained; it is not resolved by preferring one source."
        )


def require_reconciled_source_keys(
    reconciliation: Mapping[int, SeasonReconciliation]
) -> None:
    """Fail closed on a duplicated source key rather than let a row vanish.

    A repeated identifier collapses two games into one bucket. Whichever one
    survives does so by dictionary insertion order, which is not a governance
    rule anyone issued.
    """
    offending = {
        season: report.duplicate_source_keys
        for season, report in sorted(reconciliation.items())
        if report.duplicate_source_keys
    }
    if offending:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: the source universe repeats a game identifier in "
            f"{offending}. A duplicated key silently discards one of the two rows "
            "it collapses, so it is refused rather than deduplicated by convention."
        )


def require_no_duplicate_emitted_keys(
    observations: Sequence[Mapping[str, Any]]
) -> None:
    """Fail closed if any *emitted* observation repeats a game identifier.

    Distinct from :func:`require_reconciled_source_keys`, which asks the same
    question of the whole source universe. The universe legitimately contains an
    unreconciled duplicate — 2024 T073vT114 names two different contests — and
    both of its rows are excluded by the gate chain and preserved in the census.
    Refusing the entire dataset for a duplicate that no admitted row carries
    would discard 3,259 sound observations over two the adapter already refused.

    What must never happen is a duplicated key inside the emitted file, where
    game_id is the contract's deduplication and split-assignment key and the
    survivor would be chosen by dictionary insertion order.
    """
    seen: dict[str, int] = {}
    for observation in observations:
        key = str(observation["game_id"])
        seen[key] = seen.get(key, 0) + 1
    repeated = sorted(k for k, n in seen.items() if n > 1)
    if repeated:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: the derived dataset repeats a game identifier "
            f"{repeated}. game_id is the contract's deduplication and split-assignment "
            "key, so a repeat is refused rather than resolved by insertion order."
        )


# ---------------------------------------------------------------------------
# The exclusion gate chain
# ---------------------------------------------------------------------------


def duplicated_source_keys(
    universe: Sequence[UniverseRow], evidence: "ModelEvidence | None" = None
) -> frozenset[str]:
    """Identifiers that name more than one contest, on either side of the join.

    A key repeated in the *model* ledger is just as disqualifying as one repeated
    in the factual ledger: either way the identifier does not identify a game, and
    the join silently keeps one row and drops the other.
    """
    seen: dict[str, int] = {}
    for row in universe:
        seen[row.game_id] = seen.get(row.game_id, 0) + 1
    repeated = {key for key, count in seen.items() if count > 1}
    if evidence is not None:
        for keys in evidence.duplicate_keys.values():
            repeated |= set(keys)
    return frozenset(repeated)


def classify_row(
    row: UniverseRow,
    model_row: ModelEvidenceRow | None,
    duplicated: frozenset[str] = frozenset(),
) -> str | None:
    """Return the first exclusion gate this row fails, or None if it survives.

    The chain is ordered and total: every row either names one reason or is
    admitted, so the census partitions the 5,148 exactly.
    """
    if row.malformed:
        return "SOURCE_ROW_MALFORMED_ARTIFACT"
    if row.game_id in duplicated:
        return "SOURCE_KEY_DUPLICATE_UNRECONCILED"
    if model_row is None:
        return "MODEL_EVIDENCE_ROW_ABSENT"
    if evidence_domain_of(row) not in cal.ADMISSIBLE_EVIDENCE_DOMAINS:
        return "EVIDENCE_DOMAIN_NOT_ADMISSIBLE"

    subject = classify_division(row.subject_division)
    opponent = classify_division(row.opponent_division)
    if DIVISION_NOT_ESTABLISHED in (subject, opponent):
        return "PARTICIPANT_DIVISION_NOT_ESTABLISHED"
    if DIVISION_OUTSIDE_ENUM in (subject, opponent):
        return "PARTICIPANT_DIVISION_OUTSIDE_CONTRACT_ENUM"
    if "FCS" in (
        _text(row.subject_division).upper(),
        _text(row.opponent_division).upper(),
    ):
        return "FCS_PARTICIPANT_PENDING_V3_POINT_SCALE_ADAPTER"

    if model_row.eligible is not True:
        return "BAXTER_MINIMUM_PRIOR_GAMES_NOT_MET"
    if model_row.expected_margin is None:
        return "EXPECTED_MARGIN_NOT_RECORDED"
    if resolve_temporal_evidence(row) is None:
        return "TEMPORAL_ORDER_EVIDENCE_INSUFFICIENT"
    if not row.game_date:
        return "RESULT_OBSERVATION_DATE_NOT_RECORDED"
    if model_row.pregame_rating_a is None or model_row.pregame_rating_b is None:
        # Ruling R8: a season that records the prediction but not the two ratings
        # behind it is admitted under SOURCE_RECORDED_WALKFORWARD, if and only if
        # the source-bound provenance actually proves the mode. The gate is the
        # authority, so it is called rather than assumed.
        try:
            admit_expected_margin(row, model_row, resolve_temporal_evidence(row))
        except GovernanceBlock:
            return "PREGAME_RATING_STATE_NOT_RECORDED"
    return None


#: The one gate that is a statement about the *nature* of the corpus rather than
#: about a field. Before ruling R7 it refused every synthetic row and accounted
#: for 4,521 of the 5,148; it now refuses only a corpus whose domain is not
#: admissible at all, which in this mount is none of them. The counterfactual
#: subset below still names it, because a reader comparing the two runs needs the
#: same handle in both.
PROVENANCE_GATE = "EVIDENCE_DOMAIN_NOT_ADMISSIBLE"


def independent_gate_census(
    universe: Sequence[UniverseRow], evidence: "ModelEvidence"
) -> dict[str, dict[str, int]]:
    """Per gate, how many rows fail it *considered on its own*.

    The ordered census is authoritative but it is also lossy in one direction: a
    row charged to an early gate never reaches a later one, so a field gap
    affecting thousands of rows can show a count of zero. This census re-asks
    every gate independently, so a reviewer sees the size of each defect rather
    than only the size of the first one encountered.
    """
    duplicated = duplicated_source_keys(universe, evidence)
    census: dict[str, dict[str, int]] = {
        reason: {str(s): 0 for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)}
        for reason in EXCLUSION_REASONS
    }
    for row in universe:
        model_row = evidence.get(row.season, {}).get(row.game_id)
        for reason in EXCLUSION_REASONS:
            if _fails_gate(row, model_row, reason, duplicated):
                census[reason][str(row.season)] += 1
    return census


def _fails_gate(
    row: UniverseRow,
    model_row: ModelEvidenceRow | None,
    reason: str,
    duplicated: frozenset[str],
) -> bool:
    """Whether one row fails one named gate, independently of the others."""
    if reason == "SOURCE_ROW_MALFORMED_ARTIFACT":
        return row.malformed
    if reason == "SOURCE_KEY_DUPLICATE_UNRECONCILED":
        return row.game_id in duplicated
    if reason == "MODEL_EVIDENCE_ROW_ABSENT":
        return model_row is None
    if reason == PROVENANCE_GATE:
        return evidence_domain_of(row) not in cal.ADMISSIBLE_EVIDENCE_DOMAINS
    subject = classify_division(row.subject_division)
    opponent = classify_division(row.opponent_division)
    if reason == "PARTICIPANT_DIVISION_NOT_ESTABLISHED":
        return DIVISION_NOT_ESTABLISHED in (subject, opponent)
    if reason == "PARTICIPANT_DIVISION_OUTSIDE_CONTRACT_ENUM":
        return DIVISION_OUTSIDE_ENUM in (subject, opponent)
    if reason == "FCS_PARTICIPANT_PENDING_V3_POINT_SCALE_ADAPTER":
        return "FCS" in (
            _text(row.subject_division).upper(),
            _text(row.opponent_division).upper(),
        )
    if reason == "BAXTER_MINIMUM_PRIOR_GAMES_NOT_MET":
        return model_row is not None and model_row.eligible is not True
    if reason == "EXPECTED_MARGIN_NOT_RECORDED":
        return model_row is not None and model_row.expected_margin is None
    if reason == "TEMPORAL_ORDER_EVIDENCE_INSUFFICIENT":
        return resolve_temporal_evidence(row) is None
    if reason == "RESULT_OBSERVATION_DATE_NOT_RECORDED":
        return not row.game_date
    if reason == "PREGAME_RATING_STATE_NOT_RECORDED":
        if model_row is None:
            return False
        if (
            model_row.pregame_rating_a is not None
            and model_row.pregame_rating_b is not None
        ):
            return False
        try:
            admit_expected_margin(row, model_row, resolve_temporal_evidence(row))
        except GovernanceBlock:
            return True
        return False
    raise GovernanceBlock(f"{ADAPTER_ID}: unknown exclusion gate {reason!r}.")


def maximum_admissible_subset(
    universe: Sequence[UniverseRow], evidence: "ModelEvidence"
) -> dict[str, Any]:
    """The population that would survive if the provenance gate were suspended.

    This is a **counterfactual diagnostic and nothing else**. It answers the
    question a reviewer will ask next — how much of the corpus is blocked by the
    synthetic-population finding alone, and how much by field gaps that would
    survive it — and it admits nothing. The provenance gate is not suspended
    anywhere in the authoritative path, and the rows counted here are still
    excluded.
    """
    duplicated = duplicated_source_keys(universe, evidence)
    surviving_all: dict[str, int] = {}
    surviving_without_ratings: dict[str, int] = {}
    for row in universe:
        model_row = evidence.get(row.season, {}).get(row.game_id)
        gates = [r for r in EXCLUSION_REASONS if r != PROVENANCE_GATE]
        failed = [g for g in gates if _fails_gate(row, model_row, g, duplicated)]
        key = str(row.season)
        surviving_all.setdefault(key, 0)
        surviving_without_ratings.setdefault(key, 0)
        if not failed:
            surviving_all[key] += 1
        if failed == ["PREGAME_RATING_STATE_NOT_RECORDED"]:
            surviving_without_ratings[key] += 1
    by_split: dict[str, int] = {split: 0 for split in cal.DATA_SPLITS}
    for season, count in surviving_all.items():
        by_split[partition_of(int(season))] += count
    return {
        "definition": (
            "Counterfactual only: the rows that would clear every gate except "
            f"{PROVENANCE_GATE}. Nothing here is admitted, and the provenance "
            "gate is not suspended in the authoritative census."
        ),
        "surviving_every_other_gate_by_season": {
            k: v for k, v in sorted(surviving_all.items())
        },
        "surviving_every_other_gate_by_split": {
            k: v for k, v in sorted(by_split.items())
        },
        "surviving_every_other_gate_total": sum(surviving_all.values()),
        "blocked_only_by_absent_pregame_ratings_by_season": {
            k: v for k, v in sorted(surviving_without_ratings.items())
        },
        "blocked_only_by_absent_pregame_ratings_total": sum(
            surviving_without_ratings.values()
        ),
    }


# ---------------------------------------------------------------------------
# Independent per-field support census
# ---------------------------------------------------------------------------

#: Contract-required fields whose support this adapter measures directly against
#: the sources, independently of the exclusion gate order. A field that an
#: earlier, stricter gate would have masked is still counted here — which is how
#: the overtime gap stays visible even though no row ever reaches an overtime
#: gate.
FIELD_SUPPORT: tuple[str, ...] = (
    "actual_margin_is_a_recorded_result",
    "expected_margin",
    "pregame_team_rating",
    "pregame_opponent_rating",
    "opponent_division",
    "week",
    "event_time",
    "observed_at",
    "overtime_periods",
    "games_played_to_date",
)


def field_support_census(
    universe: Sequence[UniverseRow], evidence: "ModelEvidence"
) -> dict[str, dict[str, int]]:
    """Per season, how many of the source rows each required field is supported on."""
    census: dict[str, dict[str, int]] = {name: {} for name in FIELD_SUPPORT}
    for season in sorted(SOURCE_UNIVERSE_SEASON_ROWS):
        rows = [r for r in universe if r.season == season]
        model_rows = evidence.get(season, {})
        supported = {name: 0 for name in FIELD_SUPPORT}
        for row in rows:
            model_row = model_rows.get(row.game_id)
            if row.result_is_recorded and row.actual_margin is not None:
                supported["actual_margin_is_a_recorded_result"] += 1
            if model_row is not None and model_row.expected_margin is not None:
                supported["expected_margin"] += 1
            if model_row is not None and model_row.pregame_rating_a is not None:
                supported["pregame_team_rating"] += 1
            if model_row is not None and model_row.pregame_rating_b is not None:
                supported["pregame_opponent_rating"] += 1
            if classify_division(row.opponent_division) != DIVISION_NOT_ESTABLISHED:
                supported["opponent_division"] += 1
            if row.week_ordinal is not None:
                supported["week"] += 1
            # event_time is never supported: the corpus records no kickoff time.
            if row.game_date:
                supported["observed_at"] += 1
            if row.overtime_recorded:
                supported["overtime_periods"] += 1
            if model_row is not None and model_row.prior_games_a is not None:
                supported["games_played_to_date"] += 1
        for name in FIELD_SUPPORT:
            census[name][str(season)] = supported[name]
    return census


# ---------------------------------------------------------------------------
# Contract-shaped observation rows
# ---------------------------------------------------------------------------

#: The only columns an emitted observation may carry. Taken from the governed
#: allowlist rather than restated, so widening the allowlist by ruling widens
#: this and widening this alone cannot widen the allowlist.
OBSERVATION_COLUMNS: tuple[str, ...] = cal.CALIBRATION_OBSERVATION_COLUMNS


def expected_margin_provenance_of(
    row: UniverseRow, model_row: ModelEvidenceRow
) -> cal.ExpectedMarginProvenance:
    """Which provenance mode this observation is admitted under, and its evidence.

    The mode is read from the evidence, never chosen: a season whose governed
    ledger records both component ratings is DERIVED_AT_INGESTION and emits them;
    a season that records only the prediction is SOURCE_RECORDED_WALKFORWARD.
    Ruling R8 permits the second, and permits it only where the components are
    genuinely absent — so 2006 and 2007 stay in the first mode with their
    recorded ratings intact rather than being nulled to reach the weaker one.
    """
    artifact, _, member_and_sheet = model_row.source_identity.partition("::")
    member = member_and_sheet.split(" [", 1)[0]
    if model_row.pregame_rating_a is not None and model_row.pregame_rating_b is not None:
        return cal.ExpectedMarginProvenance(
            source_type=cal.EXPECTED_MARGIN_MODE_DERIVED,
            model_id=MODEL_VERSION,
            transform=EXPECTED_MARGIN_TRANSFORM,
            rating_scale=RATING_SCALE_DECLARATION,
        )
    return cal.ExpectedMarginProvenance(
        source_type=cal.EXPECTED_MARGIN_MODE_SOURCE_RECORDED,
        model_id=MODEL_VERSION,
        transform=EXPECTED_MARGIN_TRANSFORM,
        rating_scale=RATING_SCALE_DECLARATION,
        source_artifact=artifact or BAXTER,
        source_artifact_sha256=SOURCE_PACKAGES_BY_NAME[BAXTER].sha256,
        source_member=member,
        source_member_sha256=model_row.source_sha256,
        source_row=model_row.source_identity,
        source_game_id=model_row.game_id,
        walkforward_chronology=WALKFORWARD_CHRONOLOGY_STATEMENT,
        derived_from_actual_result=False,
        retrospective_full_season=False,
    )


def admit_expected_margin(
    row: UniverseRow, model_row: ModelEvidenceRow, temporal_order: Any
) -> cal.ExpectedMarginProvenance:
    """Put one observation's expected_margin through the governed R8 gate.

    The digests are handed in from the package register and the member bytes the
    reader actually hashed, so the declaration is checked against something
    rather than against itself.
    """
    provenance = expected_margin_provenance_of(row, model_row)
    return cal.require_expected_margin_provenance(
        row.game_id,
        expected_margin=model_row.expected_margin,
        provenance=provenance,
        pregame_team_rating=model_row.pregame_rating_a,
        pregame_opponent_rating=model_row.pregame_rating_b,
        evidence_domain=evidence_domain_of(row),
        temporal_order=temporal_order,
        approval_token=CHAIRMAN_EXPECTED_MARGIN_APPROVAL_TOKEN,
        verified_artifact_sha256=SOURCE_PACKAGES_BY_NAME[BAXTER].sha256,
        verified_member_sha256=model_row.source_sha256,
    )


def observation_row(
    row: UniverseRow, model_row: ModelEvidenceRow, subsequent: Sequence[str]
) -> dict[str, Any]:
    """Build one contract-shaped observation from reconciled governed evidence.

    ``event_time`` is emitted as the empty string and the four ``temporal_order_*``
    columns carry the governed alternative, because the corpus records no kickoff
    instant anywhere. There is no branch in this function that can produce a
    time of day.

    ``evidence_domain`` is read from the row's own source provenance. There is
    likewise no branch here that can turn a governed synthetic row into an
    observed one.
    """
    evidence = resolve_temporal_evidence(row)
    if evidence is None:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: observation {row.game_id} has no supportable temporal "
            "basis and must not be emitted."
        )
    margin = row.actual_margin
    if margin is None:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: observation {row.game_id} has no recorded result."
        )
    provenance = admit_expected_margin(row, model_row, evidence)
    prior_state = {
        "games_played_to_date": model_row.prior_games_a,
        "opponent_games_played_to_date": model_row.prior_games_b,
        "season_hfa_at_fit": model_row.hfa,
        "rating_scale": RATING_SCALE_DECLARATION,
    }
    return {
        "game_id": row.game_id,
        "season": row.season,
        "week": row.week_ordinal,
        # Read from the row's own source provenance, never chosen here. Ruling
        # R7 requires the domain to travel with every derived evidence object,
        # so a later reader cannot receive the evidence without its limits.
        "evidence_domain": evidence_domain_of(row),
        "event_time": "",
        "temporal_order_basis": evidence.basis,
        "temporal_order_key": json.dumps(
            evidence.value, sort_keys=True, separators=(",", ":")
        ),
        "temporal_order_source": evidence.source,
        "temporal_order_source_sha256": evidence.source_sha256,
        "team": row.subject,
        "opponent": row.opponent,
        "venue": row.venue,
        # Emitted where the governed source records them and left null where it
        # does not. Ruling R8 permits the null; it does not permit nulling a
        # component the source did record.
        "pregame_team_rating": model_row.pregame_rating_a,
        "pregame_opponent_rating": model_row.pregame_rating_b,
        "expected_margin_source_type": provenance.source_type,
        "expected_margin_provenance": provenance.canonical(),
        "expected_margin": model_row.expected_margin,
        "actual_margin": margin,
        "game_result": "W" if margin > 0 else ("L" if margin < 0 else "T"),
        "prior_rating_state": json.dumps(prior_state, sort_keys=True, separators=(",", ":")),
        "subsequent_outcomes": json.dumps(
            {"scored_against_game_ids": list(subsequent)},
            sort_keys=True, separators=(",", ":"),
        ),
        "source_provenance": f"{row.source_identity} | {model_row.source_identity}",
        "observed_at": row.game_date or "",
        "recorded_at": row.game_date or "",
        "model_version": MODEL_VERSION,
        "configuration_version": CONFIGURATION_VERSION,
        "split": row.split,
    }


def _subsequent_outcomes(
    admitted: Sequence[tuple[UniverseRow, ModelEvidenceRow]]
) -> dict[str, list[str]]:
    """The later games in the dataset each subject team is scored against.

    Derived from the dataset itself so leakage is checkable rather than asserted,
    and confined to the same season because the governed ratings are centered
    within a season and are not comparable across one.
    """
    by_team: dict[tuple[int, str], list[tuple[str, str]]] = {}
    for row, _ in admitted:
        key = (row.season, row.subject)
        by_team.setdefault(key, []).append((row.game_date or "", row.game_id))
    out: dict[str, list[str]] = {}
    for row, _ in admitted:
        ordered = sorted(by_team[(row.season, row.subject)])
        here = (row.game_date or "", row.game_id)
        out[row.game_id] = [gid for stamp, gid in ordered if (stamp, gid) > here]
    return out


# ---------------------------------------------------------------------------
# Canonical corpus membership and use-specific eligibility (ruling R9)
# ---------------------------------------------------------------------------


def row_capabilities(
    row: UniverseRow,
    model_row: ModelEvidenceRow | None,
    duplicated: frozenset[str] = frozenset(),
) -> dict[str, bool]:
    """What one source record's evidence actually supports.

    Facts about the source, not verdicts about the row. Every one is read from
    what the governed member recorded; none is inferred from another, and a
    capability that is false means the source recorded nothing — never that the
    underlying fact is false. ``overtime_status_known`` is the one to watch:
    false there means unknown, and unknown is never read as no-overtime.
    """
    subject = classify_division(row.subject_division)
    opponent = classify_division(row.opponent_division)
    divisions_supported = (
        subject == DIVISION_ADMITTED and opponent == DIVISION_ADMITTED
    )
    fcs = "FCS" in (
        _text(row.subject_division).upper(),
        _text(row.opponent_division).upper(),
    )
    expected_margin_available = False
    if model_row is not None and model_row.expected_margin is not None:
        try:
            admit_expected_margin(row, model_row, resolve_temporal_evidence(row))
            expected_margin_available = True
        except GovernanceBlock:
            expected_margin_available = False
    return {
        "actual_margin_available": row.actual_margin is not None and not row.malformed,
        "expected_margin_available": expected_margin_available,
        "component_ratings_available": (
            model_row is not None
            and model_row.pregame_rating_a is not None
            and model_row.pregame_rating_b is not None
        ),
        "temporal_order_supported": resolve_temporal_evidence(row) is not None,
        "participant_division_supported": divisions_supported,
        "overtime_status_known": row.overtime_recorded,
        "fcs_participant": fcs,
        "requires_unresolved_fcs_point_adapter": fcs,
        "source_game_id_unique": row.game_id not in duplicated,
        "source_row_provenance_identity_available": bool(row.provenance_identity),
        "malformed_source_fields": row.malformed,
        "walkforward_evidence_present": model_row is not None,
        "walkforward_eligibility_flag_set": (
            model_row is not None and model_row.eligible is True
        ),
        "observation_date_recorded": bool(row.game_date),
    }


#: How each pre-R9 exclusion reason reads as a capability. The reasons are not
#: deleted: they still name exactly why a record cannot enter the full contract.
#: What changed is that a false capability no longer removes the record from
#: every other use.
EXCLUSION_REASON_CAPABILITY_MAP: dict[str, str] = {
    "SOURCE_ROW_MALFORMED_ARTIFACT": "malformed_source_fields = true",
    "SOURCE_KEY_DUPLICATE_UNRECONCILED": "source_game_id_unique = false",
    "MODEL_EVIDENCE_ROW_ABSENT": "walkforward_evidence_present = false",
    "EVIDENCE_DOMAIN_NOT_ADMISSIBLE": (
        "evidence_domain outside the admitted set; no record in this mount"
    ),
    "PARTICIPANT_DIVISION_NOT_ESTABLISHED": "participant_division_supported = false",
    "PARTICIPANT_DIVISION_OUTSIDE_CONTRACT_ENUM": (
        "participant_division_supported = false"
    ),
    "FCS_PARTICIPANT_PENDING_V3_POINT_SCALE_ADAPTER": (
        "fcs_participant = true and requires_unresolved_fcs_point_adapter = true"
    ),
    "BAXTER_MINIMUM_PRIOR_GAMES_NOT_MET": "walkforward_eligibility_flag_set = false",
    "EXPECTED_MARGIN_NOT_RECORDED": "expected_margin_available = false",
    "TEMPORAL_ORDER_EVIDENCE_INSUFFICIENT": "temporal_order_supported = false",
    "RESULT_OBSERVATION_DATE_NOT_RECORDED": "observation_date_recorded = false",
    "PREGAME_RATING_STATE_NOT_RECORDED": (
        "component_ratings_available = false; expected_margin_available may still be "
        "true under SOURCE_RECORDED_WALKFORWARD"
    ),
}


#: The 2011 engine-comparison universe, expressed as a use-specific mask rather
#: than as a rewritten row count. The canonical 2011 corpus stays at 713.
ENGINE_COMPARISON_EXCLUDED_2011 = (
    LINEAGE_2011["malformed_artifact_game_id"],
    LINEAGE_2011["engine_comparison_exclusion_game_id"],
)


def corpus_record(
    row: UniverseRow,
    model_row: ModelEvidenceRow | None,
    duplicated: frozenset[str],
) -> dict[str, Any]:
    """One canonical corpus record: the source facts plus what they support.

    Every field here is either recorded by the source or derived from what the
    source recorded. Nothing is filled in. A value the source did not record is
    emitted empty, and the capability flag beside it says so.
    """
    capabilities = row_capabilities(row, model_row, duplicated)
    evidence = resolve_temporal_evidence(row)
    provenance = (
        expected_margin_provenance_of(row, model_row)
        if model_row is not None and capabilities["expected_margin_available"]
        else None
    )
    record = {
        "provenance_identity_sha256": row.provenance_identity_sha256,
        "provenance_identity": row.provenance_identity,
        "source_game_id": row.game_id,
        "source_member": row.source_identity,
        "source_member_sha256": row.source_sha256,
        "source_row_ordinal": row.source_row_ordinal,
        "season": row.season,
        "split": row.split,
        "evidence_domain": evidence_domain_of(row),
        "team": row.subject,
        "opponent": row.opponent,
        "team_division": row.subject_division,
        "opponent_division": row.opponent_division,
        "venue": row.venue,
        "week": "" if row.week_ordinal is None else row.week_ordinal,
        "week_label": row.week_label,
        "stage_label": row.stage_label,
        "game_date": row.game_date or "",
        "source_sequence": "" if row.sequence is None else row.sequence,
        "temporal_order_basis": evidence.basis if evidence else "",
        "temporal_order_key": (
            json.dumps(evidence.value, sort_keys=True, separators=(",", ":"))
            if evidence
            else ""
        ),
        "actual_margin": "" if row.actual_margin is None else row.actual_margin,
        "expected_margin": (
            ""
            if model_row is None or model_row.expected_margin is None
            else model_row.expected_margin
        ),
        "expected_margin_source_type": provenance.source_type if provenance else "",
        "pregame_team_rating": (
            "" if model_row is None or model_row.pregame_rating_a is None
            else model_row.pregame_rating_a
        ),
        "pregame_opponent_rating": (
            "" if model_row is None or model_row.pregame_rating_b is None
            else model_row.pregame_rating_b
        ),
        "overtime_status": "KNOWN" if row.overtime_recorded else "UNKNOWN",
        "overtime_periods": (
            "" if row.overtime_periods is None else row.overtime_periods
        ),
        "source_provenance_label": row.provenance_label,
        "malformed_note": row.malformed_note,
        "lineage_flags": "|".join(_lineage_flags(row)),
    }
    record.update({f"cap_{name}": capabilities[name] for name in cal.EVIDENCE_CAPABILITIES})
    record["eligible_uses"] = "|".join(cal.eligible_uses(capabilities))
    return record


def _lineage_flags(row: UniverseRow) -> tuple[str, ...]:
    """Named lineage facts a reviewer would otherwise have to rediscover."""
    flags: list[str] = []
    if row.malformed:
        flags.append("MALFORMED_SOURCE_ARTIFACT")
    if row.game_id == LINEAGE_2011["malformed_artifact_game_id"]:
        flags.append("LINEAGE_2011_MALFORMED_ARTIFACT")
    if row.game_id == LINEAGE_2011["engine_comparison_exclusion_game_id"]:
        flags.append("LINEAGE_2011_ENGINE_COMPARISON_EXCLUSION")
    if row.season == 2011 and row.game_id in ENGINE_COMPARISON_EXCLUDED_2011:
        flags.append("OUTSIDE_2011_ENGINE_COMPARISON_UNIVERSE")
    if row.season == cal.HOLDOUT_SEASON:
        flags.append("HOLDOUT_SEASON_NOT_FOR_MODEL_SELECTION")
    return tuple(flags)


CORPUS_COLUMNS: tuple[str, ...] = (
    "provenance_identity_sha256",
    "provenance_identity",
    "source_game_id",
    "source_member",
    "source_member_sha256",
    "source_row_ordinal",
    "season",
    "split",
    "evidence_domain",
    "team",
    "opponent",
    "team_division",
    "opponent_division",
    "venue",
    "week",
    "week_label",
    "stage_label",
    "game_date",
    "source_sequence",
    "temporal_order_basis",
    "temporal_order_key",
    "actual_margin",
    "expected_margin",
    "expected_margin_source_type",
    "pregame_team_rating",
    "pregame_opponent_rating",
    "overtime_status",
    "overtime_periods",
    "source_provenance_label",
    "malformed_note",
    "lineage_flags",
) + tuple(f"cap_{name}" for name in cal.EVIDENCE_CAPABILITIES) + ("eligible_uses",)


def require_canonical_corpus_integrity(
    records: Sequence[Mapping[str, Any]]
) -> None:
    """Fail closed if the canonical corpus lost or duplicated a source record.

    Membership is the one thing ruling R9 makes unconditional, so it is checked
    rather than assumed. The provenance identity must be unique even though
    ``source_game_id`` is not: that asymmetry is the whole reason the identity
    exists.
    """
    if len(records) != SOURCE_UNIVERSE_ROWS:
        raise GovernanceBlock(
            f"{ADAPTER_ID}: the canonical calibration corpus holds {len(records)} "
            f"records, not {SOURCE_UNIVERSE_ROWS}. Ruling {cal.CORPUS_RULING} makes "
            "membership unconditional; a record may be ineligible for a use, never "
            "absent from the corpus."
        )
    by_season: dict[int, int] = {}
    for record in records:
        by_season[int(record["season"])] = by_season.get(int(record["season"]), 0) + 1
    if by_season != dict(SOURCE_UNIVERSE_SEASON_ROWS):
        raise GovernanceBlock(
            f"{ADAPTER_ID}: canonical corpus season counts {by_season} do not "
            f"reproduce the audited universe {dict(SOURCE_UNIVERSE_SEASON_ROWS)}."
        )
    identities = [str(r["provenance_identity"]) for r in records]
    if len(set(identities)) != len(identities):
        repeated = sorted({i for i in identities if identities.count(i) > 1})
        raise GovernanceBlock(
            f"{ADAPTER_ID}: provenance identity is not unique across the canonical "
            f"corpus: {repeated[:5]}. The identity is built from source coordinates "
            "precisely so that it distinguishes records a shared game_id does not."
        )


def corpus_csv(records: Sequence[Mapping[str, Any]]) -> str:
    """Serialize the canonical corpus deterministically.

    Ordered by provenance identity rather than by game_id, because game_id is not
    unique and ordering by a non-unique key is not an ordering.
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(CORPUS_COLUMNS), lineterminator="\n"
    )
    writer.writeheader()
    for record in sorted(records, key=lambda r: str(r["provenance_identity"])):
        writer.writerow({c: record.get(c, "") for c in CORPUS_COLUMNS})
    return buffer.getvalue()


def use_specific_census(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Population sizes per named use, overall and per season."""
    seasons = [str(s) for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)]
    out: dict[str, Any] = {}
    for use in cal.CALIBRATION_USES:
        eligible = [r for r in records if use in str(r["eligible_uses"]).split("|")]
        out[use] = {
            "rows": len(eligible),
            "by_season": {
                season: sum(1 for r in eligible if str(r["season"]) == season)
                for season in seasons
            },
            "by_evidence_domain": {
                domain: sum(1 for r in eligible if r["evidence_domain"] == domain)
                for domain in sorted({str(r["evidence_domain"]) for r in records})
            },
            "requires": list(cal.CALIBRATION_USES[use]["requires"]),
            "refuses": list(cal.CALIBRATION_USES[use]["refuses"]),
        }
    return out


def capability_census(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Per capability, how many records support it, overall and per season."""
    seasons = [str(s) for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)]
    return {
        name: {
            "rows": sum(1 for r in records if r[f"cap_{name}"]),
            "by_season": {
                season: sum(
                    1
                    for r in records
                    if str(r["season"]) == season and r[f"cap_{name}"]
                )
                for season in seasons
            },
        }
        for name in cal.EVIDENCE_CAPABILITIES
    }


#: What each unresolved calibration parameter would need, and whether saying so
#: is itself a governance question. Where it is, the question is reported rather
#: than answered: choosing the evidence a parameter is fitted against is a ruling,
#: and making one here to produce a number would be the whole failure this lane
#: exists to avoid.
PARAMETER_EVIDENCE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "weekly_performance_residual_coefficient": {
        "use": "EXPECTED_MARGIN_RESIDUAL",
        "additional_capabilities": (),
        "additional_row_predicate": "week ordinal recorded",
        "open_governance_question": None,
    },
    "weekly_movement_cap_points": {
        "use": "EXPECTED_MARGIN_RESIDUAL",
        "additional_capabilities": ("component_ratings_available",),
        "additional_row_predicate": "week ordinal recorded",
        "open_governance_question": (
            "A cap on week-over-week rating movement is measured against rating "
            "states, so this reports the population that carries recorded component "
            "ratings. Whether the cap may instead be fitted against recorded "
            "predicted-margin movement alone is a governance question this lane does "
            "not answer."
        ),
    },
    "recent_form_weights": {
        "use": "EXPECTED_MARGIN_RESIDUAL",
        "additional_capabilities": (),
        "additional_row_predicate": "week ordinal recorded",
        "open_governance_question": None,
    },
    "blowout_treatment": {
        "use": "ACTUAL_MARGIN_DISTRIBUTION",
        "additional_capabilities": (),
        "additional_row_predicate": None,
        "open_governance_question": (
            "The blowout threshold itself is unresolved. This reports the "
            "outcome-only population a descriptive blowout-frequency analysis could "
            "read; the margin at which a game becomes a blowout, and whether the "
            "treatment is fitted on residuals rather than outcomes, both require a "
            "ruling."
        ),
    },
    "game_sd_points": {
        "use": "EXPECTED_MARGIN_RESIDUAL",
        "additional_capabilities": (),
        "additional_row_predicate": None,
        "open_governance_question": (
            "Whether overtime games are excluded from the residual pool is "
            "unresolved and materially affects the estimate, so the "
            "overtime-restricted population is reported alongside. College overtime "
            "manufactures margins no pregame model predicts, which is the direction "
            "of the unexplained 20.2 observation."
        ),
    },
    "sample_size_regularization": {
        "use": "EXPECTED_MARGIN_RESIDUAL",
        "additional_capabilities": (),
        "additional_row_predicate": "prior games-played count recorded",
        "open_governance_question": (
            "games_played_to_date is not on the governed observation allowlist and "
            "sits in calibration_contract.FIELDS_REQUIRING_ADMISSION_RULING. The "
            "count is recorded by the walk-forward ledger and reported here as a "
            "population, but admitting it as an observation field requires its own "
            "ruling."
        ),
    },
}


def parameter_candidate_populations(
    records: Sequence[Mapping[str, Any]],
    universe: Sequence[UniverseRow],
    evidence: "ModelEvidence",
) -> dict[str, Any]:
    """The largest presently evidence-supported population per open parameter.

    A population, never a fit. Nothing here estimates, scores, ranks or promotes
    anything: it answers "how much evidence exists" so a later governed
    experiment starts from a number a reviewer can check, and it says where
    answering that question at all would require a ruling this lane does not hold.
    """
    by_identity = {r.provenance_identity: r for r in universe}
    model_for = {
        r.provenance_identity: evidence.get(r.season, {}).get(r.game_id)
        for r in universe
    }
    out: dict[str, Any] = {}
    for parameter, spec in PARAMETER_EVIDENCE_REQUIREMENTS.items():
        use = spec["use"]
        pool = [r for r in records if use in str(r["eligible_uses"]).split("|")]
        for capability in spec["additional_capabilities"]:
            pool = [r for r in pool if r[f"cap_{capability}"]]
        predicate = spec["additional_row_predicate"]
        if predicate == "week ordinal recorded":
            pool = [r for r in pool if str(r["week"]).strip() != ""]
        elif predicate == "prior games-played count recorded":
            pool = [
                r
                for r in pool
                if (model_for.get(str(r["provenance_identity"])) is not None)
                and model_for[str(r["provenance_identity"])].prior_games_a is not None
            ]
        seasons = [str(s) for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)]
        entry: dict[str, Any] = {
            "base_use": use,
            "additional_capabilities": list(spec["additional_capabilities"]),
            "additional_row_predicate": predicate,
            "candidate_rows": len(pool),
            "candidate_rows_by_season": {
                season: sum(1 for r in pool if str(r["season"]) == season)
                for season in seasons
            },
            "candidate_rows_excluding_holdout": sum(
                1 for r in pool if int(r["season"]) != cal.HOLDOUT_SEASON
            ),
            "fitted": False,
            "promoted": False,
            "open_governance_question": spec["open_governance_question"],
        }
        if parameter == "game_sd_points":
            entry["candidate_rows_restricted_to_known_overtime"] = sum(
                1 for r in pool if r["cap_overtime_status_known"]
            )
        out[parameter] = entry
    return out


# ---------------------------------------------------------------------------
# The build
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AdapterResult:
    """Everything the adapter established, with nothing inferred at read time."""

    mount_root: Path
    packages: dict[str, Any]
    evidence_domains: tuple[dict[str, Any], ...]
    source_universe_rows: int
    season_counts: dict[int, int]
    reconciliation: dict[int, SeasonReconciliation]
    exclusion_census: dict[str, dict[str, int]]
    exclusion_totals: dict[str, int]
    independent_gate_census: dict[str, dict[str, int]]
    maximum_admissible_subset: dict[str, Any]
    field_support: dict[str, dict[str, int]]
    provenance_census: dict[str, dict[str, int]]
    temporal_basis_census: dict[str, dict[str, int]]
    overtime_census: dict[str, dict[str, int]]
    division_census: dict[str, dict[str, int]]
    transform_validation: dict[str, Any]
    partition_ordering_proof: dict[str, Any]
    matched_model_evidence_rows: int
    contract_candidate_rows: int
    admitted_rows: int
    excluded_rows: int
    observations: tuple[dict[str, Any], ...]
    admitted_split_counts: dict[str, int]
    blockers: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...] = ()
    population_reconciliation: dict[str, Any] = field(default_factory=dict)
    #: Ruling R9: every source record, with provenance identity and capability
    #: flags. Membership here is decided by provenance, never by completeness.
    corpus_records: tuple[dict[str, Any], ...] = ()
    capability_census: dict[str, Any] = field(default_factory=dict)
    use_specific_census: dict[str, Any] = field(default_factory=dict)
    parameter_candidate_populations: dict[str, Any] = field(default_factory=dict)

    @property
    def contract_satisfied(self) -> bool:
        """Only a stated contract requirement can make the contract unsatisfied.

        Findings do not enter here. They are real gaps in what the sources record
        and they are reported in full, but the issued contract does not condition
        admission on them, and treating a gap the contract does not name as a
        contract violation is as wrong in this direction as ignoring one.
        """
        return not self.blockers


def build(root: Path | None = None) -> AdapterResult:
    """Run the whole adapter: custody, universe, reconciliation, census, emission."""
    base = Path(root) if root is not None else default_mount_root()
    packages = verify_mounted_packages(base)
    # Ruling R7 is what gives this corpus any standing at all, so its gate runs
    # before a single observation row is read. A refusal here is not a census
    # entry; it means the adapter has no authority over these bytes.
    evidence_domains = admitted_evidence_domains(base)

    universe = load_source_universe(base)
    evidence = load_model_evidence(base)

    reconciliation = reconcile(universe, evidence)
    require_no_actual_margin_disagreement(reconciliation)
    # A duplicated identifier is not fatal to the *census* — it is one of the
    # things the census exists to report — but it is fatal to use, so it becomes
    # an exclusion gate here and a hard refusal at emission. Both sides of the
    # join are checked: the 2024 model ledger repeats a key the factual ledger
    # repeats too, and a dedup on either side would drop a row unrecorded.
    duplicated = duplicated_source_keys(universe, evidence)

    transform_validation = validate_expected_margin_transform(evidence, universe)

    # --- ordered exclusion census ---------------------------------------
    exclusion: dict[str, dict[str, int]] = {
        reason: {str(s): 0 for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)}
        for reason in EXCLUSION_REASONS
    }
    survivors: list[tuple[UniverseRow, ModelEvidenceRow]] = []
    matched = 0
    candidates = 0
    for row in universe:
        model_row = evidence.get(row.season, {}).get(row.game_id)
        if model_row is not None:
            matched += 1
        reason = classify_row(row, model_row, duplicated)
        if reason is None:
            candidates += 1
            assert model_row is not None  # classify_row proved it
            survivors.append((row, model_row))
            continue
        if reason in (
            "RESULT_OBSERVATION_DATE_NOT_RECORDED",
            "PREGAME_RATING_STATE_NOT_RECORDED",
        ):
            # These two gates sit past every semantic check, so a row reaching
            # them is a contract candidate that a *field* gap disqualifies. It is
            # counted as a candidate so the two numbers a reviewer compares —
            # candidates and admitted — differ by exactly the field shortfall.
            candidates += 1
        exclusion[reason][str(row.season)] += 1

    exclusion_totals = {
        reason: sum(by_season.values()) for reason, by_season in exclusion.items()
    }

    # Ruling R9: the canonical corpus is built from every source record, before
    # and independently of the observation subset. A row that cannot enter the
    # full walk-forward contract is still a member here.
    corpus = tuple(
        corpus_record(row, evidence.get(row.season, {}).get(row.game_id), duplicated)
        for row in universe
    )
    require_canonical_corpus_integrity(corpus)

    subsequent = _subsequent_outcomes(survivors)
    observations = tuple(
        observation_row(row, model_row, subsequent[row.game_id])
        for row, model_row in survivors
    )
    split_counts = {split: 0 for split in cal.DATA_SPLITS}
    for observation in observations:
        split_counts[observation["split"]] += 1

    blockers, findings = _blockers(
        observations=observations,
        split_counts=split_counts,
        exclusion_totals=exclusion_totals,
        field_support=field_support_census(universe, evidence),
    )

    return AdapterResult(
        mount_root=base,
        packages=packages,
        evidence_domains=tuple(d.as_dict() for d in evidence_domains),
        source_universe_rows=len(universe),
        season_counts={
            s: sum(1 for r in universe if r.season == s)
            for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)
        },
        reconciliation=reconciliation,
        exclusion_census=exclusion,
        exclusion_totals=exclusion_totals,
        independent_gate_census=independent_gate_census(universe, evidence),
        maximum_admissible_subset=maximum_admissible_subset(universe, evidence),
        field_support=field_support_census(universe, evidence),
        provenance_census=_provenance_census(universe),
        temporal_basis_census=_temporal_basis_census(universe),
        overtime_census=_overtime_census(universe),
        division_census=_division_census(universe),
        transform_validation=transform_validation,
        partition_ordering_proof=prove_candidate_partition_ordering(universe=universe),
        matched_model_evidence_rows=matched,
        contract_candidate_rows=candidates,
        admitted_rows=len(observations),
        excluded_rows=len(universe) - len(observations),
        observations=observations,
        admitted_split_counts=split_counts,
        blockers=blockers,
        findings=findings,
        population_reconciliation=population_reconciliation(universe, evidence),
        corpus_records=corpus,
        capability_census=capability_census(corpus),
        use_specific_census=use_specific_census(corpus),
        parameter_candidate_populations=parameter_candidate_populations(
            corpus, universe, evidence
        ),
    )


def _provenance_census(universe: Sequence[UniverseRow]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in universe:
        by_season = out.setdefault(row.provenance_label, {})
        by_season[str(row.season)] = by_season.get(str(row.season), 0) + 1
    return out


def _temporal_basis_census(universe: Sequence[UniverseRow]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {
        basis: {str(s): 0 for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)}
        for basis in cal.TEMPORAL_EVIDENCE_PRECEDENCE
    }
    out["NO_SUPPORTABLE_BASIS"] = {
        str(s): 0 for s in sorted(SOURCE_UNIVERSE_SEASON_ROWS)
    }
    for row in universe:
        basis = temporal_basis_of(row) or "NO_SUPPORTABLE_BASIS"
        out[basis][str(row.season)] += 1
    return out


def _overtime_census(universe: Sequence[UniverseRow]) -> dict[str, dict[str, int]]:
    recorded: dict[str, int] = {}
    absent: dict[str, int] = {}
    for row in universe:
        key = str(row.season)
        if row.overtime_recorded:
            recorded[key] = recorded.get(key, 0) + 1
        else:
            absent[key] = absent.get(key, 0) + 1
    return {
        "overtime_status_recorded_by_source": recorded,
        "overtime_status_absent_from_source": absent,
    }


def _division_census(universe: Sequence[UniverseRow]) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for row in universe:
        for label in (row.subject_division, row.opponent_division):
            key = _text(label).upper() or "ABSENT"
            by_season = out.setdefault(key, {})
            by_season[str(row.season)] = by_season.get(str(row.season), 0) + 1
    return out


# ---------------------------------------------------------------------------
# Blockers this lane returns rather than works around
# ---------------------------------------------------------------------------


def _blockers(
    *,
    observations: Sequence[Mapping[str, Any]],
    split_counts: Mapping[str, int],
    exclusion_totals: Mapping[str, int],
    field_support: Mapping[str, Mapping[str, int]],
) -> tuple[dict[str, Any], ...]:
    """Separate what blocks the issued contract from what is merely reported.

    Two lists, because conflating them was itself a defect. A *blocker* is a
    requirement the issued contract states and this corpus does not meet; it
    stops emission. A *finding* is a real gap in what the sources record that the
    issued contract does not make a condition of admission; it is reported in
    full and does not stop emission.

    The overtime entry is the worked example: its own text said "It does not
    block admission" while it sat in the list that blocks it. Ruling R8 settles
    the other one — the component-rating gap is now a mode question, not a
    violation.

    Neither entry is softened by moving. Both keep their row counts, their
    per-season breakdown and their statement of what they restrict.
    """
    found: list[dict[str, Any]] = []
    reported: list[dict[str, Any]] = []
    mode_counts = {
        mode: sum(
            1 for o in observations if o.get("expected_margin_source_type") == mode
        )
        for mode in cal.EXPECTED_MARGIN_MODES
    }

    synthetic = exclusion_totals.get("EVIDENCE_DOMAIN_NOT_ADMISSIBLE", 0)
    if synthetic:
        found.append(
            {
                "blocker": "CALIBRATION_SOURCE_EVIDENCE_DOMAIN_NOT_ADMISSIBLE",
                "affects": "all calibration uses",
                "rows": synthetic,
                "detail": (
                    "Rows remain whose evidence domain is neither OBSERVED_REAL_WORLD "
                    "nor an admitted GOVERNED_SYNTHETIC declaration under ruling "
                    "R7-CAL-GOVERNED-SYNTHETIC-EVIDENCE. A corpus that claims the "
                    "domain without byte-verified package and member digests and its "
                    "source's own declaration receives no authority from the ruling."
                ),
                "evidence": [dict(item) for item in SYNTHETIC_POPULATION_EVIDENCE],
            }
        )

    pregame_gap = {
        season: SOURCE_UNIVERSE_SEASON_ROWS[int(season)] - count
        for season, count in sorted(field_support["pregame_team_rating"].items())
        if count < SOURCE_UNIVERSE_SEASON_ROWS[int(season)]
    }
    if pregame_gap:
        reported.append(
            {
                "finding": "PREGAME_RATING_STATE_NOT_RECORDED_BY_SOURCE",
                "classification": "SOURCE_GAP_RESOLVED_BY_PROVENANCE_MODE",
                "affects": (
                    "which expected-margin provenance mode a row is admitted under"
                ),
                "rows": sum(pregame_gap.values()),
                "rows_by_season": pregame_gap,
                "blocks_admission": False,
                "detail": (
                    "Only the 2006 and 2007 walk-forward workbooks record "
                    "rating_a_pre and rating_b_pre; every other season records the "
                    "resulting predicted margin alone. Under ruling "
                    "R8-CAL-SOURCE-RECORDED-WALKFORWARD-MARGIN that is no longer a "
                    "contract violation: those rows are admitted under "
                    "SOURCE_RECORDED_WALKFORWARD with source-bound provenance, and the "
                    "two component fields stay null because the source records none. "
                    "It remains reported because it is a real limit on the evidence. A "
                    "deterministic replay was not substituted: it could be validated "
                    "against the recorded predictions only for the two seasons that "
                    "already carry the ratings, and a reconstructed rating presented as "
                    "an observation is weaker provenance than the recorded prediction "
                    "it would be used to justify."
                ),
                "rows_by_provenance_mode": mode_counts,
                "component_ratings_preserved_where_recorded": True,
            }
        )

    overtime_absent = {
        season: SOURCE_UNIVERSE_SEASON_ROWS[int(season)] - count
        for season, count in sorted(field_support["overtime_periods"].items())
        if count < SOURCE_UNIVERSE_SEASON_ROWS[int(season)]
    }
    if overtime_absent:
        reported.append(
            {
                "finding": "OVERTIME_STATUS_NOT_RECORDED_BY_SOURCE",
                "classification": "SOURCE_GAP_RESTRICTING_TWO_COEFFICIENTS",
                "affects": "calibration.game_sd_points and calibration.blowout_treatment only",
                "blocks_admission": False,
                "restricts_calibration_fields": [
                    "calibration.game_sd_points",
                    "calibration.blowout_treatment",
                ],
                "unknown_converted_to_false": False,
                "rows": sum(overtime_absent.values()),
                "rows_by_season": overtime_absent,
                "detail": (
                    "No 2006-2011 source member carries an overtime column under any "
                    "spelling, and the 550 recorded-result 2024 rows leave ot_a and "
                    "ot_b empty. Overtime status was neither defaulted to False nor "
                    "inferred from the final score. It does not block admission: "
                    "overtime_periods sits in "
                    "calibration_contract.FIELDS_REQUIRING_ADMISSION_RULING and is not "
                    "on the governed observation allowlist, so no admitted observation "
                    "may carry it yet. It does restrict the two coefficients that are "
                    "functions of it, and UNKNOWN is never converted to False."
                ),
            }
        )

    empty = [split for split in cal.DATA_SPLITS if not split_counts.get(split)]
    if empty:
        found.append(
            {
                "blocker": "CANDIDATE_PARTITION_CANNOT_BE_POPULATED",
                "affects": "all calibration uses",
                "rows": 0,
                "detail": (
                    f"The experimental partition requires all of "
                    f"{list(cal.DATA_SPLITS)} to be populated; "
                    f"{empty} carry no admissible observation. "
                    "calibration.require_governed_temporal_split_integrity refuses an "
                    "empty split, so no forward-only ordering can be proven and no "
                    "out-of-sample number can be defined."
                ),
                "empty_splits": empty,
                "split_counts": dict(split_counts),
            }
        )

    if len(observations) < contract.MINIMUM_VOLUME_REQUIREMENTS[
        "minimum_observations_total"
    ]:
        found.append(
            {
                "blocker": "MINIMUM_OBSERVATION_VOLUME_NOT_MET",
                "affects": "all calibration uses",
                "rows": len(observations),
                "detail": (
                    "The contract's minimum volume is "
                    f"{contract.MINIMUM_VOLUME_REQUIREMENTS['minimum_observations_total']} "
                    "observations over at least "
                    f"{contract.MINIMUM_VOLUME_REQUIREMENTS['minimum_distinct_seasons']} "
                    "seasons with at least "
                    f"{contract.MINIMUM_VOLUME_REQUIREMENTS['minimum_holdout_observations']} "
                    "holdout observations."
                ),
            }
        )
    return tuple(found), tuple(reported)


# ---------------------------------------------------------------------------
# Emission
# ---------------------------------------------------------------------------


def observation_csv(observations: Sequence[Mapping[str, Any]]) -> str:
    """Serialize observations deterministically, in governed column order.

    Rows are ordered by ``(season, game_id)`` rather than by source order, so two
    builds from the same bytes produce the same file regardless of how the source
    members happened to iterate.
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(OBSERVATION_COLUMNS), lineterminator="\n"
    )
    writer.writeheader()
    for observation in sorted(
        observations, key=lambda o: (int(o["season"]), str(o["game_id"]))
    ):
        writer.writerow({c: observation.get(c, "") for c in OBSERVATION_COLUMNS})
    return buffer.getvalue()


def emit_observation_dataset(result: AdapterResult, path: Path) -> Path:
    """Write the derived calibration dataset, or fail closed.

    A derived dataset is produced only where the contract can actually be
    satisfied. Emitting one with a caveat attached would put the caveat inside an
    artifact that outlives the conversation that explained it, which is exactly
    how an unadmitted observation set becomes a cited one.
    """
    if not result.contract_satisfied:
        names = [b["blocker"] for b in result.blockers]
        raise GovernanceBlock(
            f"{ADAPTER_ID}: refusing to emit a derived calibration dataset. The "
            f"issued contract {contract.CONTRACT_ID} revision "
            f"{contract.CONTRACT_REVISION} cannot be satisfied by this corpus: "
            f"{names}. The contract is not weakened to obtain an artifact."
        )
    require_no_duplicate_emitted_keys(result.observations)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(observation_csv(result.observations), encoding="utf-8", newline="")
    return path


def population_reconciliation(
    universe: Sequence[UniverseRow], evidence: "ModelEvidence"
) -> dict[str, Any]:
    """One table, per season, that every other count in the record ties back to.

    This exists because three different populations were being quoted as though
    they were the same number. They are not, and the differences are exact:

    * the ordered exclusion census charges a row to the *first* gate it fails, so
      a field gap can show a small count simply because an earlier gate got there
      first;
    * the independent gate census re-asks each gate on its own, so it counts
      every row failing that gate whether or not something else already excluded
      it;
    * a field-support gap counts source rows for which the source records nothing,
      which includes rows that have no walk-forward evidence row at all.

    Each column below is defined once and the arithmetic between them is stated,
    so no reader has to guess which population a number came from.
    """
    duplicated = duplicated_source_keys(universe, evidence)
    seasons = sorted(SOURCE_UNIVERSE_SEASON_ROWS)
    table: dict[str, dict[str, int]] = {}
    for season in seasons:
        rows = [r for r in universe if r.season == season]
        model_rows = [evidence.get(season, {}).get(r.game_id) for r in rows]
        paired = list(zip(rows, model_rows))
        both = [
            m for m in model_rows
            if m is not None
            and m.pregame_rating_a is not None
            and m.pregame_rating_b is not None
        ]
        recorded_wf = [
            m for m in model_rows
            if m is not None
            and m.expected_margin is not None
            and (m.pregame_rating_a is None or m.pregame_rating_b is None)
        ]
        candidates = 0
        admitted = 0
        for row, model_row in paired:
            reason = classify_row(row, model_row, duplicated)
            if reason is None:
                candidates += 1
                admitted += 1
            elif reason in (
                "RESULT_OBSERVATION_DATE_NOT_RECORDED",
                "PREGAME_RATING_STATE_NOT_RECORDED",
            ):
                candidates += 1
        table[str(season)] = {
            "SOURCE_UNIVERSE_ROWS": len(rows),
            "WALKFORWARD_EVIDENCE_ROWS": sum(1 for m in model_rows if m is not None),
            "ELIGIBLE_WALKFORWARD_ROWS": sum(
                1 for m in model_rows if m is not None and m.eligible is True
            ),
            "ROWS_WITH_RECORDED_COMPONENT_RATINGS": len(both),
            "ROWS_WITH_SOURCE_RECORDED_WALKFORWARD_MARGIN": len(recorded_wf),
            "ROWS_MISSING_EXPECTED_MARGIN": sum(
                1 for m in model_rows if m is not None and m.expected_margin is None
            ),
            "CONTRACT_CANDIDATE_ROWS": candidates,
            "ADMITTED_ROWS": admitted,
            "EXCLUDED_ROWS": len(rows) - admitted,
        }
    totals = {
        column: sum(by_season[column] for by_season in table.values())
        for column in next(iter(table.values()))
    }
    return {
        "by_season": table,
        "totals": totals,
        "column_definitions": {
            "SOURCE_UNIVERSE_ROWS": (
                "Every row of the audited source population. The input, never a target."
            ),
            "WALKFORWARD_EVIDENCE_ROWS": (
                "Source rows that join by game identifier to a Baxter walk-forward row."
            ),
            "ELIGIBLE_WALKFORWARD_ROWS": (
                "Of those, the ones the governed ledger's own eligibility flag marks "
                "eligible under the frozen BAXTER-MOV-v1.0-R minimum of three prior "
                "games per team. The flag is read, never re-derived."
            ),
            "ROWS_WITH_RECORDED_COMPONENT_RATINGS": (
                "Rows whose walk-forward row records BOTH pregame component ratings. "
                "These are admitted under DERIVED_AT_INGESTION and emit the components."
            ),
            "ROWS_WITH_SOURCE_RECORDED_WALKFORWARD_MARGIN": (
                "Rows whose walk-forward row records a predicted margin but NOT both "
                "components. These are the SOURCE_RECORDED_WALKFORWARD candidates under "
                "ruling R8."
            ),
            "ROWS_MISSING_EXPECTED_MARGIN": (
                "Rows with a walk-forward row that records no predicted margin. Never "
                "filled from the result."
            ),
            "CONTRACT_CANDIDATE_ROWS": (
                "Rows that cleared every semantic gate and reached the field-completeness "
                "checks."
            ),
            "ADMITTED_ROWS": "Rows satisfying every required contract field.",
            "EXCLUDED_ROWS": "SOURCE_UNIVERSE_ROWS minus ADMITTED_ROWS, per season.",
        },
        "prior_count_discrepancy_resolved": {
            "question": (
                "A previous handoff quoted the pregame-rating gap as '2,596 in the "
                "ordered census; 4,087 counted independently'. Those are two different "
                "populations and neither number was wrong; quoting them side by side "
                "without their definitions was."
            ),
            "ordered_exclusion_census_2596": (
                "Rows charged to PREGAME_RATING_STATE_NOT_RECORDED as the FIRST gate "
                "they failed, under the pre-R8 contract. Rows already excluded by an "
                "earlier gate — eligibility, missing date, division, FCS — never "
                "reached it."
            ),
            "independent_gate_census_3989": (
                "Rows that have a walk-forward evidence row and lack at least one "
                "component rating, asked on its own gate regardless of what else "
                "excluded them. 3,989 rows: 5,050 with evidence minus 1,061 carrying "
                "both components."
            ),
            "field_support_gap_4087": (
                "Source rows for which the source records no pregame_team_rating at "
                "all, counted against the whole 5,148 universe. This is the number the "
                "prior handoff called 'independent', and it is not the independent gate "
                "census."
            ),
            "arithmetic": (
                "4,087 = 3,989 + 98. The 98 are source rows with no walk-forward "
                "evidence row at all, so they have no component rating either; 97 of "
                "them are charged to MODEL_EVIDENCE_ROW_ABSENT and the remaining one "
                "(G2011_P3056) is charged earlier to SOURCE_ROW_MALFORMED_ARTIFACT. "
                "5,148 - 5,050 = 98."
            ),
            "under_r8": (
                "All three populations are now historical accounting. The 2,596 rows "
                "the ordered census charged to the gate are admitted under "
                "SOURCE_RECORDED_WALKFORWARD, and the gate fires only where the "
                "source-bound provenance does not prove the mode."
            ),
        },
    }


def emit_canonical_corpus(result: AdapterResult, path: Path) -> Path:
    """Write the canonical 5,148-record corpus.

    Unlike the observation dataset, this is not gated on the full contract being
    satisfiable. That is the point of ruling R9: the corpus is a record of what
    the governed sources contain, and it is emitted whether or not every record
    can enter every calculation.
    """
    require_canonical_corpus_integrity(result.corpus_records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(corpus_csv(result.corpus_records), encoding="utf-8", newline="")
    return path


def status_document(result: AdapterResult) -> dict[str, Any]:
    """The reviewable adapter record. Deterministic: no clock, no environment.

    Absolute paths are deliberately absent. A build on another machine must
    produce the same bytes, and a mount path is a property of a machine rather
    than of the evidence.
    """
    return {
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "adapter_lane": ADAPTER_LANE,
        "contract_id": contract.CONTRACT_ID,
        "contract_revision": contract.CONTRACT_REVISION,
        "chairman_temporal_ruling_id": CHAIRMAN_TEMPORAL_RULING_ID,
        "chairman_expected_margin_ruling": CHAIRMAN_EXPECTED_MARGIN_RULING,
        "chairman_expected_margin_approval_token": (
            CHAIRMAN_EXPECTED_MARGIN_APPROVAL_TOKEN
        ),
        "rulings_applied": [
            CHAIRMAN_TEMPORAL_RULING,
            CHAIRMAN_EVIDENCE_DOMAIN_RULING,
            CHAIRMAN_EXPECTED_MARGIN_RULING,
        ],
        "expected_margin_provenance": {
            "modes": list(cal.EXPECTED_MARGIN_MODES),
            "mode_counts": {
                mode: sum(
                    1
                    for o in result.observations
                    if o.get("expected_margin_source_type") == mode
                )
                for mode in cal.EXPECTED_MARGIN_MODES
            },
            "mode_counts_by_season": {
                str(season): {
                    mode: sum(
                        1
                        for o in result.observations
                        if int(o["season"]) == season
                        and o.get("expected_margin_source_type") == mode
                    )
                    for mode in cal.EXPECTED_MARGIN_MODES
                }
                for season in sorted(SOURCE_UNIVERSE_SEASON_ROWS)
            },
            "component_ratings_emitted_where_recorded": sum(
                1
                for o in result.observations
                if o.get("pregame_team_rating") is not None
            ),
            "component_ratings_null_because_unrecorded": sum(
                1 for o in result.observations if o.get("pregame_team_rating") is None
            ),
            "walkforward_chronology": WALKFORWARD_CHRONOLOGY_STATEMENT,
            "replay_constructed": False,
            "semantics": cal.expected_margin_governance_as_dict(),
        },
        "population_reconciliation": result.population_reconciliation,
        "canonical_corpus": {
            "ruling": cal.CORPUS_RULING,
            "record_kind": cal.CANONICAL_CORPUS_RECORD,
            "membership_basis": cal.CORPUS_MEMBERSHIP_BASIS,
            "SOURCE_CORPUS_ROWS": len(result.corpus_records),
            "season_counts": {
                str(season): sum(
                    1 for r in result.corpus_records if int(r["season"]) == season
                )
                for season in sorted(SOURCE_UNIVERSE_SEASON_ROWS)
            },
            "path": str(DEFAULT_CORPUS_PATH).replace("\\", "/"),
            "columns": list(CORPUS_COLUMNS),
            "sha256": sha256_bytes(corpus_csv(result.corpus_records).encode("utf-8")),
            "unique_provenance_identities": len(
                {str(r["provenance_identity"]) for r in result.corpus_records}
            ),
            "unique_source_game_ids": len(
                {str(r["source_game_id"]) for r in result.corpus_records}
            ),
            "rows_globally_discarded": 0,
            "missing_values_fabricated": 0,
            "evidence_domain_counts": {
                domain: sum(
                    1 for r in result.corpus_records if r["evidence_domain"] == domain
                )
                for domain in sorted(
                    {str(r["evidence_domain"]) for r in result.corpus_records}
                )
            },
        },
        "capability_census": result.capability_census,
        "use_specific_census": result.use_specific_census,
        "parameter_candidate_populations": result.parameter_candidate_populations,
        "supersession": {
            "ruling": cal.CORPUS_RULING,
            "prior_model": "UNIVERSAL_ADMITTED_OR_EXCLUDED",
            "prior_admitted_rows": result.admitted_rows,
            "prior_excluded_rows": SOURCE_UNIVERSE_ROWS - result.admitted_rows,
            "reconciles": (
                f"{result.admitted_rows} + "
                f"{SOURCE_UNIVERSE_ROWS - result.admitted_rows} = "
                f"{SOURCE_UNIVERSE_ROWS}"
            ),
            "prior_admitted_rows_are_now": (
                "FULLY_PAIRED_CONTRACT_COMPLETE_WALKFORWARD_SUBSET"
            ),
            "prior_excluded_rows_are_now": "CANONICAL_CORPUS_MEMBERS",
            "prior_excluded_rows_globally_discarded": False,
            "exclusion_reason_to_capability_map": {
                reason: EXCLUSION_REASON_CAPABILITY_MAP[reason]
                for reason in EXCLUSION_REASONS
            },
            "note": (
                "The earlier accounting is preserved above under "
                "population_accounting and exclusion_census, unedited. What changed is "
                "what it is a statement about: the 3,259 are the subset that satisfies "
                "the full walk-forward observation contract, and the 1,889 are corpus "
                "members whose evidence supports fewer uses."
            ),
        },
        "findings": [dict(f) for f in result.findings],
        "findings_note": (
            "A finding is a real gap in what the governed sources record that the "
            "issued contract does not make a condition of admission. It is reported in "
            "full and does not stop emission. A blocker is a stated contract "
            "requirement this corpus does not meet, and it does."
        ),
        "chairman_evidence_domain_ruling": CHAIRMAN_EVIDENCE_DOMAIN_RULING,
        "chairman_evidence_domain_approval_token": (
            CHAIRMAN_EVIDENCE_DOMAIN_APPROVAL_TOKEN
        ),
        "admitted_evidence_domains": [dict(d) for d in result.evidence_domains],
        "evidence_domain": {
            "corpus_domain": cal.EVIDENCE_DOMAIN_GOVERNED_SYNTHETIC,
            "admitted_under": CHAIRMAN_EVIDENCE_DOMAIN_RULING,
            "establishes": list(cal.GOVERNED_SYNTHETIC_ESTABLISHES),
            "does_not_establish": list(cal.GOVERNED_SYNTHETIC_DOES_NOT_ESTABLISH),
            "may_be_represented_as_real_world": False,
            "ungoverned_synthetic_admissible": False,
            "emitted_row_domains": sorted(
                {str(o.get("evidence_domain", "")) for o in result.observations}
            ),
            "emitted_row_domain_counts": {
                domain: sum(
                    1 for o in result.observations if o.get("evidence_domain") == domain
                )
                for domain in sorted(
                    {str(o.get("evidence_domain", "")) for o in result.observations}
                )
            },
            "emitted_row_domain_counts_by_split": {
                split: {
                    domain: sum(
                        1
                        for o in result.observations
                        if o["split"] == split and o.get("evidence_domain") == domain
                    )
                    for domain in sorted(
                        {str(o.get("evidence_domain", "")) for o in result.observations}
                    )
                }
                for split in cal.DATA_SPLITS
            },
            "mixed_domain_note": (
                "The admitted population is not uniformly governed synthetic. The 404 "
                "admitted 2024 rows carry Phase5D provenance REAL, which the package's "
                "own INPUTS.md anchors to a named external result source, so they are "
                "OBSERVED_REAL_WORLD. The validation split is therefore real-world "
                "anchored and the training and holdout splits are governed synthetic. "
                "Nothing was relabeled in either direction: the domain is read from "
                "each row's own source provenance and travels with it."
            ),
            "note": (
                "Before ruling R7 the provenance gate refused every synthetic row and "
                "accounted for 4,521 of the 5,148. The ruling admits this corpus as "
                "GOVERNED_SYNTHETIC evidence for the synthetic V3 model. It establishes "
                "no real-world predictive validity, no sportsbook validity, no actual "
                "historical NCAA forecasting performance and no independent external "
                "empirical validation, and the domain travels on every emitted row."
            ),
        },
        "chairman_temporal_ruling": CHAIRMAN_TEMPORAL_RULING,
        "creation_command": (
            "python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3."
            "calibration_5148_adapter"
        ),
        "promotion_status": PROMOTION_STATUS,
        "source_packages": {
            name: {k: v for k, v in body.items()}
            for name, body in sorted(result.packages.items())
        },
        "source_members_consumed": sorted(
            f"{package.filename}::{member}"
            for package in SOURCE_PACKAGES
            for member in package.members.values()
            if package.consumed
        ),
        "source_universe": {
            "rows": result.source_universe_rows,
            "expected_rows": SOURCE_UNIVERSE_ROWS,
            "arithmetic": (
                f"{SOURCE_UNIVERSE_HISTORICAL_ROWS} + "
                f"{SOURCE_UNIVERSE_SEASON_ROWS[2024]} + "
                f"{SOURCE_UNIVERSE_SEASON_ROWS[2025]} = {SOURCE_UNIVERSE_ROWS}"
            ),
            "season_counts": {str(k): v for k, v in sorted(result.season_counts.items())},
        },
        "population_accounting": {
            "SOURCE_UNIVERSE_ROWS": result.source_universe_rows,
            "MATCHED_MODEL_EVIDENCE_ROWS": result.matched_model_evidence_rows,
            "CONTRACT_CANDIDATE_ROWS": result.contract_candidate_rows,
            "ADMITTED_ROWS": result.admitted_rows,
            "EXCLUDED_ROWS": result.excluded_rows,
            "definitions": {
                "SOURCE_UNIVERSE_ROWS": (
                    "Every row of the audited source population. The input, never a "
                    "target."
                ),
                "MATCHED_MODEL_EVIDENCE_ROWS": (
                    "Source rows that join by game identifier to a Baxter "
                    "walk-forward row, before any admissibility question is asked."
                ),
                "CONTRACT_CANDIDATE_ROWS": (
                    "Rows that cleared every semantic gate and reached the "
                    "contract's field-completeness checks. The difference between "
                    "this and ADMITTED_ROWS is exactly the field shortfall."
                ),
                "ADMITTED_ROWS": (
                    "Rows satisfying every required contract field, emitted only if "
                    "the contract as a whole can be satisfied."
                ),
                "EXCLUDED_ROWS": (
                    "SOURCE_UNIVERSE_ROWS minus ADMITTED_ROWS. The ordered "
                    "exclusion census partitions this exactly."
                ),
            },
        },
        "partition_ordering_proof": {
            "gate": "calibration.require_governed_temporal_split_integrity",
            "proves": (
                "max(training) < min(validation) and max(validation) < min(holdout) "
                "inside every shared ordering domain, on the corpus's own chronology"
            ),
            "is_admission_of_evidence": False,
            "is_model_selection": False,
            "report": result.partition_ordering_proof,
        },
        "exclusion_census": {
            reason: {
                "total": result.exclusion_totals[reason],
                "by_season": {k: v for k, v in sorted(by_season.items())},
                "note": EXCLUSION_REASON_NOTES[reason],
            }
            for reason, by_season in sorted(result.exclusion_census.items())
        },
        "independent_gate_census": {
            reason: {k: v for k, v in sorted(by_season.items())}
            for reason, by_season in sorted(result.independent_gate_census.items())
        },
        "maximum_admissible_subset": dict(result.maximum_admissible_subset),
        "reconciliation": {
            str(season): report.as_dict()
            for season, report in sorted(result.reconciliation.items())
        },
        "field_support_census": {
            name: {k: v for k, v in sorted(by_season.items())}
            for name, by_season in sorted(result.field_support.items())
        },
        "provenance_census": {
            label: {k: v for k, v in sorted(by_season.items())}
            for label, by_season in sorted(result.provenance_census.items())
        },
        "temporal_basis_census": {
            basis: {k: v for k, v in sorted(by_season.items())}
            for basis, by_season in sorted(result.temporal_basis_census.items())
        },
        "overtime_status_census": {
            key: {k: v for k, v in sorted(by_season.items())}
            for key, by_season in sorted(result.overtime_census.items())
        },
        "division_label_census": {
            label: {k: v for k, v in sorted(by_season.items())}
            for label, by_season in sorted(result.division_census.items())
        },
        "expected_margin_model_source": {
            "model_version": MODEL_VERSION,
            "configuration_version": CONFIGURATION_VERSION,
            "expected_margin_transform": EXPECTED_MARGIN_TRANSFORM,
            "rating_scale_declaration": RATING_SCALE_DECLARATION,
            "transform_validation": result.transform_validation,
            "recorded_eligible_predictions": {
                str(k): v for k, v in sorted(RECORDED_ELIGIBLE_PREDICTIONS.items())
            },
            "recorded_historical_eligible_total": RECORDED_HISTORICAL_ELIGIBLE_TOTAL,
        },
        "lineage_2011": dict(LINEAGE_2011),
        "candidate_partition": {
            split: list(seasons) for split, seasons in sorted(CANDIDATE_PARTITION.items())
        },
        "candidate_partition_counts": {
            k: v for k, v in sorted(result.admitted_split_counts.items())
        },
        "holdout": {
            "season": HOLDOUT_SEASON,
            "use": cal.HOLDOUT_USE,
            "scored_for_model_selection_in_this_lane": False,
            "selection_split": cal.SELECTION_SPLIT,
        },
        "derived_dataset": {
            "emitted": result.contract_satisfied,
            "path": str(DEFAULT_DATASET_PATH).replace("\\", "/"),
            "columns": list(OBSERVATION_COLUMNS),
            "season_counts": {
                str(season): sum(
                    1 for o in result.observations if int(o["season"]) == season
                )
                for season in sorted(SOURCE_UNIVERSE_SEASON_ROWS)
            },
            "partition_counts": dict(result.admitted_split_counts),
            "passes_authoritative_admission_loader": (
                "calibration.load_admitted_observations"
            ),
            "deterministic_rebuild": "BYTE_IDENTICAL",
            "sha256": (
                sha256_bytes(observation_csv(result.observations).encode("utf-8"))
                if result.contract_satisfied else None
            ),
            "rows": result.admitted_rows if result.contract_satisfied else 0,
        },
        "blockers": [dict(b) for b in result.blockers],
        "contract_satisfied": result.contract_satisfied,
        "handoff": (
            "CALIBRATION_5148_ADAPTER_READY"
            if result.contract_satisfied
            else "CALIBRATION_5148_ADAPTER_BLOCKED"
        ),
        "blockers_retired_by_this_lane": [],
        "coefficients_promoted_by_this_lane": [],
        "fcs_mapping_promoted_by_this_lane": None,
        "legacy_margin_sd_20_2_status": "UNAPPROVED_HISTORICAL_EVIDENCE",
    }


def status_bytes(result: AdapterResult) -> bytes:
    """The status artifact's exact bytes. Sorted keys, LF endings, trailing newline."""
    text = json.dumps(status_document(result), indent=2, sort_keys=True) + "\n"
    return text.encode("utf-8")


def write_status(result: AdapterResult, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(status_bytes(result))
    return path


DEFAULT_STATUS_PATH = Path(
    "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_5148_ADAPTER_STATUS_R1.json"
)

#: Where the derived observation dataset lands when the contract is satisfied.
#: ``reference/dynamic_weekly_mc_v3/**`` carries ``-text`` in ``.gitattributes``,
#: so the emitted bytes survive checkout unchanged and the recorded SHA-256 keeps
#: meaning something.
DEFAULT_DATASET_PATH = Path(
    "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_OBSERVATIONS_R8.csv"
)

#: Where the canonical 5,148-record corpus lands. Emitted unconditionally: it is
#: a record of the governed sources, not of one calculation's admissibility.
DEFAULT_CORPUS_PATH = Path(
    "reference/dynamic_weekly_mc_v3/V3_CALIBRATION_CORPUS_R9.csv"
)

SOURCE_MANIFEST_FILENAME = "V3_CALIBRATION_SOURCE_PACKAGE_MANIFEST_R1.json"


def source_manifest_document(root: Path | None = None) -> dict[str, Any]:
    """Custody record for the mounted packages, with per-member digests.

    Member digests are recorded so a reviewer can check an individual CSV or
    workbook without unpacking the archive, and so a repackaged zip that happens
    to contain the same members is still distinguishable from the audited one.

    Phase5E shares several byte-identical members with Phase5D. They are recorded
    as shared rather than copied out twice, which is why the mount holds four
    packages and no unpacked duplicates.
    """
    base = Path(root) if root is not None else default_mount_root()
    packages: dict[str, Any] = {}
    digests_by_member: dict[str, list[str]] = {}
    for package in SOURCE_PACKAGES:
        mounted = require_package(base, package.filename)
        members: dict[str, Any] = {}
        with zipfile.ZipFile(mounted.path) as archive:
            for info in sorted(archive.infolist(), key=lambda i: i.filename):
                if info.is_dir():
                    continue
                digest = sha256_bytes(archive.read(info.filename))
                members[info.filename] = {"bytes": info.file_size, "sha256": digest}
                digests_by_member.setdefault(digest, []).append(
                    f"{package.filename}::{info.filename}"
                )
        packages[package.filename] = {
            "sha256": mounted.sha256,
            "bytes": mounted.bytes_,
            "role": package.role,
            "consumed_by_this_lane": package.consumed,
            "expected_source_universe_rows": package.expected_source_universe_rows,
            "named_members": {k: v for k, v in sorted(package.members.items())},
            "members": {k: members[k] for k in sorted(members)},
        }
    shared = {
        digest: sorted(locations)
        for digest, locations in sorted(digests_by_member.items())
        if len({loc.split("::", 1)[0] for loc in locations}) > 1
    }
    return {
        "adapter_id": ADAPTER_ID,
        "adapter_version": ADAPTER_VERSION,
        "custody": (
            "Byte-exact mount of the audited source packages. Digests are verified "
            "against the audited identities before any member is read; a mismatch "
            "fails closed. Originals are never modified and nothing is repackaged."
        ),
        "promotion_status": PROMOTION_STATUS,
        "packages": packages,
        "byte_identical_members_shared_across_packages": shared,
    }


def write_source_manifest(root: Path | None = None) -> Path:
    base = Path(root) if root is not None else default_mount_root()
    path = base / SOURCE_MANIFEST_FILENAME
    text = json.dumps(source_manifest_document(base), indent=2, sort_keys=True) + "\n"
    path.write_bytes(text.encode("utf-8"))
    return path


def main(root: Path | None = None) -> int:
    result = build(root)
    write_source_manifest(root)
    emit_canonical_corpus(result, repository_root() / DEFAULT_CORPUS_PATH)
    if result.contract_satisfied:
        emit_observation_dataset(result, repository_root() / DEFAULT_DATASET_PATH)
    write_status(result, repository_root() / DEFAULT_STATUS_PATH)
    document = status_document(result)
    print(json.dumps(document["population_accounting"], indent=2, sort_keys=True))
    print(document["handoff"])
    return 0 if result.contract_satisfied else 1


if __name__ == "__main__":  # pragma: no cover - operator entrypoint
    raise SystemExit(main())
