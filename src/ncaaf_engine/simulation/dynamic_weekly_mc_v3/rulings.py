"""Chairman governance rulings converged into the V3 EXPERIMENTAL layer (R2).

Every blocker this convergence retires is retired *because a ruling was issued*,
never because analysis found the question tractable. This module is the single
place those rulings are written down, so a reviewer can read the authority and
the code that consumes it side by side.

Three provenance classes are kept distinct and must not be collapsed:

``FACT``
    Reproduced from a mounted repository artifact. The evidence field names the
    artifact, sheet and row.
``DERIVED``
    Computed deterministically from FACT by code in this package.
``ASSUMPTION``
    Not present here. A ruling with no mounted evidence stays fail-closed
    instead of being recorded as an assumption.

Ruling identifiers
------------------
The R2 governance instruction issued the rulings below but did **not** supply
Chairman ruling IDs. Each entry therefore carries a locally assigned
``convergence_id`` (DERIVED, stable, prefixed ``R2-``) *and* a
``chairman_ruling_id`` that is ``None`` until a real identifier is issued. The
local identifier is a handle for code and tests; it is not a governance ID and
must never be cited as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .errors import GovernanceBlock

Provenance = Literal["FACT", "DERIVED", "ASSUMPTION", "BLOCKED"]

#: Issued together as one instruction; recorded once so every ruling shares it.
R2_INSTRUCTION = "OPERATION SYTHALAX — V3 GOVERNANCE CONVERGENCE R2"


@dataclass(frozen=True)
class ChairmanRuling:
    """One issued ruling, with the evidence it is checked against."""

    convergence_id: str
    subject: str
    decision: str
    #: Repository evidence a reader can verify the ruling against. Never the
    #: authority for the ruling itself — the Chairman is.
    evidence: tuple[str, ...] = ()
    #: Blocker IDs this ruling is capable of retiring, *if* the accompanying
    #: deterministic validation also passes. Naming a blocker here never clears
    #: it on its own.
    retires: tuple[str, ...] = ()
    #: Historical records this ruling supersedes. They are preserved, not edited.
    supersedes: tuple[str, ...] = ()
    provenance: Provenance = "FACT"
    chairman_ruling_id: str | None = None
    instruction: str = R2_INSTRUCTION

    def as_dict(self) -> dict[str, object]:
        return {
            "convergence_id": self.convergence_id,
            "chairman_ruling_id": self.chairman_ruling_id,
            "subject": self.subject,
            "decision": self.decision,
            "evidence": list(self.evidence),
            "retires": list(self.retires),
            "supersedes": list(self.supersedes),
            "provenance": self.provenance,
            "instruction": self.instruction,
        }


R2_SCHEDULE_V5_AUTHORITY = ChairmanRuling(
    convergence_id="R2-SCHED-V5-AUTH",
    subject="2026 Schedule v5 authority and binary source-copy identity",
    decision=(
        "Schedule v5 is authoritative. A binary-copy identity difference does not block V3 "
        "when the source is the verified v5 schedule and its certified Games content "
        "reproduces exactly. All historical binary hashes are preserved unedited."
    ),
    evidence=(
        "2026_FBS_Schedule_LOCKED_v5.xlsx!Certification integrity_sha256=bd8089f7…",
        "2026_FBS_Schedule_LOCKED_v5.xlsx!Certification integrity_method (canonical CSV serialization)",
        "Model_Parameters_v2_5_APPROVED.xlsx!19_SCHEDULE_V5_CHANGE schedule_binary_sha256=db26c3ff…",
        "Model_Parameters_v2_5_APPROVED.xlsx!01_SOURCE_REGISTER schedule_v5",
    ),
    retires=("provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5",),
    supersedes=(),
)

R2_THIRTEEN_GAME_EXCEPTIONS = ChairmanRuling(
    convergence_id="R2-SCHED-13GAME",
    subject="Five 13-game regular-season schedules",
    decision=(
        "ARK, GAST, UK, VAN and WVU are approved to play 13 regular-season games, "
        "subject to deterministic validation of each schedule."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!12_OPEN_ITEMS OI-SCHED-13 (ARK, GAST, UK, VAN, WVU)",
        "Model_Parameters_v2_5_APPROVED.xlsx!14_RATIFICATION RAT-002",
    ),
    retires=("governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED",),
    supersedes=("RAT-002 safe_default_if_deferred 'Block final season run'",),
)

R2_BOARD_OF_RECORD = ChairmanRuling(
    convergence_id="R2-BOARD-OF-RECORD",
    subject="Board of Record",
    decision=(
        "Board of Record is 2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx "
        "(Board I-K R1-R3 FINAL / re-issued governance lineage). Board I-H is retained "
        "as historical/superseded evidence only and must not be substituted for it."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!08_BOARD_IH_TOP25 (Board I-H v2, historical)",
    ),
    retires=(),
    supersedes=("Board I-H v2 as Board of Record",),
)

R2_HFA = ChairmanRuling(
    convergence_id="R2-HFA-3P5",
    subject="V3 football-point home-field advantage",
    decision=(
        "V3 football-point HFA = 3.5 points. Legacy 4.0 is preserved as HISTORICAL / "
        "NOT CURRENT. Separately governed Elo-layer HFA stays a separate parameter. "
        "V2.1 is unchanged."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER SCHED-HFA-BASE=3.5 (LOCKED)",
        "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER ENG-HOME-FIELD=4.0 (HISTORICAL / NOT CURRENT)",
        "Model_Parameters_v2_5_APPROVED.xlsx!ENGINE_PARAMS HOME_FIELD_PTS=4 (VERIFIED, cfb_sim.py)",
        "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER CCG-HFA_ELO=65 (separate Elo parameter)",
    ),
    retires=("hfa_baseline_points", "governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5"),
    supersedes=("ENG-HOME-FIELD 4.0 as a V3 candidate baseline",),
)

R2_FCS = ChairmanRuling(
    convergence_id="R2-FCS-ELO-1250",
    subject="Schedule-only FCS opponent treatment",
    decision=(
        "FCS Elo = 1250, fixed, as the current V3 treatment for schedule-only FCS "
        "opponents. It requires no later toggle. No Board equivalent (.294/.297) and no "
        "inverted Elo/Board transform may be used as an FCS conversion rule."
    ),
    evidence=(
        "POWER_CRUNCH_2026_Team_Reconciled_Master_134_v2_2.xlsx!Build Manifest "
        "'Model use authorized: FALSE' (superseded by this ruling)",
        "POWER_CRUNCH_2026_Team_Reconciled_Master_134_v2_2.xlsx!Build Manifest "
        "'Board columns for FCS: BLANK — Board-equivalent recorded not issued'",
    ),
    retires=("fcs_translation_policy", "governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE"),
    supersedes=("POWER_CRUNCH Build Manifest 'Model use authorized: FALSE' for V3 use",),
)

R2_AAC_SUCCESSOR = ChairmanRuling(
    convergence_id="R2-AAC-SUCCESSOR",
    subject="AAC division membership artifact",
    decision=(
        "R-CCG-07 is authoritative. The missing 577-byte ratified CSV must not be faked. "
        "A NEW governed successor artifact is issued, derived from R-CCG-07 and the "
        "canonical team master, carrying a new identity, new SHA and full provenance. "
        "The legacy artifact's lineage is preserved as missing."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!04_CCG_RULES R-CCG-07 (RATIFIED, 8 American / 8 Athletic)",
        "Model_Parameters_v2_5_APPROVED.xlsx!01_SOURCE_REGISTER aac_divisions 577 B e0f674b4… (not mounted)",
        "Model_Parameters_v2_5_APPROVED.xlsx!13_SUPERSESSION_LOG SUP-010",
        "2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md 2026_conference_division (8/8)",
    ),
    retires=("inputs.aac_divisions_csv",),
    supersedes=(),
)

R2_SEVEN_CCGS = ChairmanRuling(
    convergence_id="R2-CCG-SEVEN",
    subject="Conference championship games and participant selection",
    decision=(
        "Exactly seven CCGs: SEC, Big Ten, Big 12, ACC, Pac-12, Mountain West, AAC. "
        "Atlantic-8 and ECL play none. Six conferences select the two best CONFERENCE "
        "win-percentage teams; AAC selects one winner per division. Ties are resolved by "
        "the CCG participant chain CCG-TB1 head-to-head, CCG-TB2 mini round-robin, "
        "CCG-TB3 last committee board published before Championship Saturday."
    ),
    evidence=(
        "2026_FBS_Schedule_LOCKED_v5.xlsx!Games seven W15 CCG template rows",
        "Model_Parameters_v2_5_APPROVED.xlsx!04_CCG_RULES R-CCG-01, R-CCG-05, R-CCG-07",
        "2026_FBS_Schedule_LOCKED_v5.xlsx!Certification ccg_count "
        "'7 — … NONE for Atlantic-8, ECL, Independent.'",
    ),
)

R2_COMMITTEE_TIEBREAK = ChairmanRuling(
    convergence_id="R2-COMMITTEE-TB",
    subject="Weekly committee product and general ranking tiebreak",
    decision=(
        "From Nov 1 through the board following the seven CCGs, publish a Top 25 ordering "
        "and the current playoff bracket only — never a raw strength number, committee "
        "score or hidden power value. General committee ranking ties resolve by "
        "COMMITTEE-TB1 head-to-head, TB2 performance against common opponents, TB3 SOS, "
        "TB4 previous week's committee board. The "
        "PRESEASON_STRENGTH / FINAL_WEEKLY_FOOTBALL_STRENGTH framing is retired."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!COMMITTEE (UNPATCHED, D-09 'No deterministic tiebreak rule')",
    ),
    retires=("committee_tiebreak_strength_source",),
    supersedes=(
        "committee_tiebreak_strength_source = PRESEASON_STRENGTH | FINAL_WEEKLY_FOOTBALL_STRENGTH",
    ),
)

R2_SOS = ChairmanRuling(
    convergence_id="R2-SOS",
    subject="Committee strength of schedule",
    decision="SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP. One quantity, one direction, one definition.",
    evidence=(
        "2026 Bracket Regime LOCKED.xlsx!Deferred Register DEF-2 sos_index 'REPORTED, never scored'",
        "2026 Bracket Regime LOCKED.xlsx!Deferred Register DEF-1, DEF-4 (RETIRED, no double counting)",
    ),
)

R2_COMMON_OPPONENTS = ChairmanRuling(
    convergence_id="R2-COMMON-OPP",
    subject="Performance against common opponents",
    decision=(
        "COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common, "
        "using the same WP/OWP/OOWP semantics as approved SOS, restricted to the "
        "common-opponent subset."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!18_ACC_POLICY_REFERENCE ACC-EXT-08 (common-opponent gap)",
    ),
)

R2_A8_ECL = ChairmanRuling(
    convergence_id="R2-A8-ECL-ORDER",
    subject="Atlantic-8 and ECL champion determination",
    decision=(
        "A8 and ECL play no CCG and each determines its own champion independently. "
        "Intra-conference championship ties resolve by A8/ECL-TB1 head-to-head, "
        "A8/ECL-TB2 approved common-opponent performance, A8/ECL-TB3 the post-CCG "
        "committee board computed before any G5 automatic-bid seeding is applied. "
        "This is not an A8-versus-ECL comparison."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!04_CCG_RULES R-CCG-08, TB-ECL/A8",
    ),
    retires=("governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT",),
    supersedes=("TB-ECL/A8 read as a bracket-dependent terminal tiebreak",),
)

R2_G5_AUTO_BID = ChairmanRuling(
    convergence_id="R2-G5-SEED5",
    subject="Group-of-5 automatic bid",
    decision=(
        "G5 = AAC, Mountain West, Pac-12, Atlantic-8, ECL. Exactly one G5 team receives an "
        "automatic bid: the highest-ranked G5 CONFERENCE CHAMPION, seeded exactly #5. "
        "That team therefore never appears in a play-in game."
    ),
    evidence=(
        "2026 Bracket Regime LOCKED.xlsx!Bracket Regime LOCKED AB2 (highest-ranked G5, champion status irrelevant)",
        "2026 Playoff Calendar OFFICIAL 2.xlsx!Playoff_Calendar 'G5 auto-bid = seed 14 (academy game)' (superseded)",
    ),
    supersedes=(
        "Playoff Calendar PLAY-IN G2 note 'G5 auto-bid = seed 14 (academy game)'",
        "Bracket Regime AB2 read as conferring no seed constraint",
        "Bracket Regime S2 'FOUR HIGHEST-RANKED TEAMS OVERALL receive a first-round bye', "
        "to the extent it would keep a top-4-ranked G5 automatic-bid champion out of seed 5",
    ),
)

R2_NO_RESEEDING = ChairmanRuling(
    convergence_id="R2-NO-RESEED",
    subject="Playoff topology",
    decision=(
        "There is no reseeding. The fixed bracket topology of the official 2026 Playoff "
        "Calendar governs. Only edges the official artifact actually states may be bound."
    ),
    evidence=(
        "2026 Playoff Calendar OFFICIAL 2.xlsx!Bracket_Flow (byes, play-in, R1, QF slots, semifinals, P-3)",
        "2026 Bracket Regime LOCKED.xlsx!Bracket Regime LOCKED S4 (R1 5v12, 6v11, 7v10, 8v9)",
        "2026 Playoff Calendar OFFICIAL 2.xlsx!Rulings_Register P-2, P-3",
    ),
    supersedes=("RESEED_BY_ORIGINAL_SEED as a candidate quarterfinal mapping",),
)

R2_SOR = ChairmanRuling(
    convergence_id="R2-SOR-REPORT",
    subject="Weekly SOR report",
    decision=(
        "Produce a weekly SOR report as its own named resume metric using the SOR-B / "
        "record-strength methodology. SOR is an output and never replaces committee SOS. "
        "The stale compute_sor_b.py default R_ref=1684.9 may never silently control a run: "
        "an explicit governed season R_ref is required. The MC-domain R_ref namespace "
        "stays separate."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER CCG-R_REF=1893.3 (MC/CCG domain, LOCKED)",
        "Model_Parameters_v2_5_APPROVED.xlsx!16_REJECTED_ITEMS REJ-012 ('Keep domains separate')",
        "Model_Parameters_v2_5_APPROVED.xlsx!18_ACC_POLICY_REFERENCE ACC-EXT-12 (BWI PROPOSAL ONLY / NOT ADOPTED)",
    ),
)

R2_SRS = ChairmanRuling(
    convergence_id="R2-SRS-WITNESS",
    subject="SRS",
    decision=(
        "SRS remains a separate deterministic opponent-adjusted capped-margin model "
        "(per-game margin cap +/-24, opponent schedule adjustment, centered field rating). "
        "It is a calibration/validation witness alongside Baxter Rating and Colley Matrix, "
        "and is never committee SOS and never SOR."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!18_ACC_POLICY_REFERENCE ACC-EXT-12 (z(SRS capped +/-24), NOT ADOPTED as BWI)",
    ),
)

R2_CALIBRATION = ChairmanRuling(
    convergence_id="R2-CAL-OBJECTIVE",
    subject="Calibration governance",
    decision=(
        "Primary mathematical calibration criterion is Baxter Rating RMSE, minimised "
        "out-of-sample. Colley Matrix and SRS are independent witnesses reported "
        "separately; no weighted composite of the three is authorised. Training, "
        "validation and holdout stay separated. Promotion requires either governed "
        "mathematical justification or explicit Chairman justification, and the "
        "provenance record must name which. Public betting flow is never belief evidence."
    ),
    evidence=(
        "Model_Parameters_v2_5_APPROVED.xlsx!12_OPEN_ITEMS ENG-CAL-MARGIN (OPEN)",
        "Model_Parameters_v2_5_APPROVED.xlsx!CALIBRATION ('Do not tune the committee engine "
        "against an unvalidated stat universe')",
    ),
)


R2_RULINGS: tuple[ChairmanRuling, ...] = (
    R2_SCHEDULE_V5_AUTHORITY,
    R2_THIRTEEN_GAME_EXCEPTIONS,
    R2_BOARD_OF_RECORD,
    R2_HFA,
    R2_FCS,
    R2_AAC_SUCCESSOR,
    R2_SEVEN_CCGS,
    R2_COMMITTEE_TIEBREAK,
    R2_SOS,
    R2_COMMON_OPPONENTS,
    R2_A8_ECL,
    R2_G5_AUTO_BID,
    R2_NO_RESEEDING,
    R2_SOR,
    R2_SRS,
    R2_CALIBRATION,
)

_BY_ID = {r.convergence_id: r for r in R2_RULINGS}


def ruling(convergence_id: str) -> ChairmanRuling:
    try:
        return _BY_ID[convergence_id]
    except KeyError:
        raise GovernanceBlock(f"No such governance ruling: {convergence_id!r}") from None


def retirable_blockers() -> dict[str, str]:
    """Map blocker ID -> convergence_id of the ruling capable of retiring it.

    Capability is not clearance. Each consuming module still requires its own
    deterministic validation to pass before the blocker actually goes away.
    """
    out: dict[str, str] = {}
    for r in R2_RULINGS:
        for blocker in r.retires:
            if blocker in out:
                raise GovernanceBlock(
                    f"Blocker {blocker} is claimed by two rulings: {out[blocker]} and {r.convergence_id}"
                )
            out[blocker] = r.convergence_id
    return out


def as_dicts() -> list[dict[str, object]]:
    return [r.as_dict() for r in R2_RULINGS]
