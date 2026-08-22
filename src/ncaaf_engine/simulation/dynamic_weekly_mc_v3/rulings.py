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
The R2, R3 and R4 governance instructions issued their rulings but did **not**
supply Chairman ruling IDs. Each of those entries therefore carries a locally
assigned ``convergence_id`` (DERIVED, stable, prefixed by its round) *and* a
``chairman_ruling_id`` that stays ``None``. The local identifier is a handle for
code and tests; it is not a governance ID and must never be cited as one.

R6 is the first round whose instruction supplied a real identifier. Its
``chairman_ruling_id`` is that issued ID, recorded verbatim, and its
``approval_token`` is the approval token the instruction carried. The two are
kept in separate fields on purpose: a token authorises an instruction and an ID
names a ruling, and using one where the other belongs would make an
authorisation look like a governance record.
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
    #: Why the blockers in ``retires`` may be retired. ``DIRECT_CHAIRMAN_AUTHORITY``
    #: means the Chairman issued the rule itself; ``SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY``
    #: means a later authority filled a gap the mounted source genuinely never stated.
    #: It is never ``SOURCE_WORKBOOK_CONTAINED_MAPPING`` — no workbook was reinterpreted.
    resolution_reason: str | None = None
    #: The approval token the instruction carried, recorded verbatim. ``None`` where
    #: the instruction supplied none. A token is the authorisation an instruction
    #: arrived with; it is not a ruling ID and is never used as one.
    approval_token: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "convergence_id": self.convergence_id,
            "chairman_ruling_id": self.chairman_ruling_id,
            "approval_token": self.approval_token,
            "subject": self.subject,
            "decision": self.decision,
            "evidence": list(self.evidence),
            "retires": list(self.retires),
            "supersedes": list(self.supersedes),
            "provenance": self.provenance,
            "instruction": self.instruction,
            "resolution_reason": self.resolution_reason,
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


#: Issued as one instruction for the PR #3 final convergence.
R3_INSTRUCTION = "OPERATION SYTHALAX — PR #3 FINAL CONVERGENCE"


R3_SOS_SEMANTICS = ChairmanRuling(
    convergence_id="R3-SOS-OWP-OOWP-SEMANTICS",
    subject="Committee SOS — OWP / OOWP denominator and exclusion semantics",
    decision=(
        "SOS(T) = 0.25*WP(T) + 0.50*OWP(T) + 0.25*OOWP(T), unchanged. "
        "WP(T) = wins by T / completed qualifying games played by T, through the "
        "applicable week only. "
        "OWP(T): for every completed qualifying schedule instance T-vs-O, take O's "
        "qualifying completed-game record through that week, EXCLUDE all completed "
        "games O played against T, and include the resulting winning percentage once "
        "for EACH actual completed meeting between T and O; OWP(T) is the arithmetic "
        "mean of those schedule-instance values. "
        "OOWP(T): for every completed qualifying schedule instance T-vs-O, take O's own "
        "governed OWP under the same exclusion and schedule-instance rules and include "
        "it once for that schedule instance; OOWP(T) is the arithmetic mean of those "
        "schedule-instance OWP(O) values. "
        "OWP and OOWP are schedule-instance weighted: a repeated opponent counts once "
        "per meeting, two meetings contribute twice, and unique-opponent averaging is "
        "not substituted. Future games are excluded. "
        "Schedule-only FCS entities contribute only governed available qualifying "
        "completed-game records; where sufficient governed record data does not exist "
        "the required component is UNAVAILABLE, never invented as a win, a loss, .500 "
        "or 0. A component with zero qualifying observations is UNAVAILABLE / NULL, "
        "never 0, 0.0 or 0.500. For reporting, unavailability is stamped with "
        "provenance; for tiebreaks, a criterion that cannot be evaluated because a "
        "required governed component is unavailable does not resolve the tie and "
        "processing advances to the next already-governed tiebreak stage."
    ),
    evidence=(
        "Direct Chairman authority, OPERATION SYTHALAX PR #3 FINAL CONVERGENCE B1.",
        "Weights unchanged from ruling R2-SOS (0.25 WP / 0.50 OWP / 0.25 OOWP).",
    ),
    retires=("governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED",),
    supersedes=(),
    provenance="FACT",
    instruction=R3_INSTRUCTION,
    resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
)

R3_CFP_FIXED_TOPOLOGY = ChairmanRuling(
    convergence_id="R3-CFP-FIXED-TOPOLOGY",
    subject="2026 synthetic 14-team CFP bracket topology",
    decision=(
        "PI-A = seed 12 v seed 13; PI-B = seed 11 v seed 14. "
        "R1-A = seed 7 v seed 10; R1-B = seed 8 v seed 9; "
        "R1-C = seed 6 v Winner(PI-B); R1-D = seed 5 v Winner(PI-A). "
        "QF-E = seed 1 v Winner(R1-B); QF-F = seed 2 v Winner(R1-A); "
        "QF-G = seed 3 v Winner(R1-C); QF-H = seed 4 v Winner(R1-D). "
        "SF-A = Winner(QF-E) v Winner(QF-H); SF-B = Winner(QF-F) v Winner(QF-G). "
        "There is no reseeding. The bracket consumes final assigned seeds, not natural "
        "committee ranks, and an upset never alters future slot topology."
    ),
    evidence=(
        "Direct Chairman authority, OPERATION SYTHALAX PR #3 FINAL CONVERGENCE B4.",
        "2026 Playoff Calendar OFFICIAL 2.xlsx!Bracket_Flow supplied prior structural "
        "evidence only: 'E = 1 v W(R1); F = 2 v W(R1); G = 3 v W(R1); H = 4 v W(R1)'. "
        "Those generic W(R1) labels never bound the four Round-1 winners to E/F/G/H.",
    ),
    retires=("governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",),
    supersedes=(
        "2026 Bracket Regime LOCKED.xlsx!S4 'First Round 5v12, 6v11, 7v10, 8v9' read as "
        "fixed seed-versus-seed Round-1 pairings — superseded to exactly the extent that "
        "seeds 5 and 6 meet play-in winners in a 14-team field.",
    ),
    provenance="FACT",
    instruction=R3_INSTRUCTION,
    resolution_reason="SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY",
)


#: Issued as one instruction for the PR #3 final common-opponent authority binding.
R4_INSTRUCTION = "OPERATION SYTHALAX — PR #3 FINAL COMMON-OPPONENT AUTHORITY BINDING"


R4_COMMON_OPPONENT_FORMULA = ChairmanRuling(
    convergence_id="R4-COMMON-OPP-FORMULA",
    subject="Performance against common opponents — the exact scoring formula",
    decision=(
        "COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common. "
        "These exact weights are the governed rule, not a configurable production "
        "parameter: 0.20/0.60/0.20, 0.25/0.25/0.50 and every other weighting are "
        "refused for governed use. The formula is applied to the common-opponent "
        "subset under the OWP/OOWP denominator and exclusion semantics already "
        "governed by ruling R3-SOS-OWP-OOWP-SEMANTICS, which this ruling does not "
        "reopen or alter. UNAVAILABLE propagation stays fail-closed: an unavailable "
        "WP_common, OWP_common or OOWP_common makes the score UNAVAILABLE and the "
        "tiebreak advances to the next already-governed criterion rather than "
        "inventing 0, 0.0 or 0.500."
    ),
    evidence=(
        "OPERATION SYTHALAX CHAIRMAN RULING — COMMON-OPPONENT PERFORMANCE FORMULA. "
        "Issued APPROVED: 'For all governed common-opponent performance comparisons, "
        "use exactly: COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + "
        "0.25 * OOWP_common.' The ruling states in terms that 'the coefficients "
        "0.25 / 0.50 / 0.25 are canonical and exact', and carries the human "
        "authorization line 'DIRECT CHAIRMAN AUTHORITY'.",
        "The same ruling states that it supersedes any earlier wording describing the "
        "formula as 'some formula that looks like' this structure. The exactness of "
        "the coefficients is therefore issued, not inferred from the earlier text.",
        "The same ruling holds the separately governed OWP/OOWP construction "
        "semantics unchanged, keeps UNAVAILABLE inputs fail-closed and advancing to "
        "the next governed tiebreak criterion, and states that it changes none of "
        "SOS, CCG rules, postseason topology, G5 seed #5, FCS Elo policy, "
        "calibration parameters, Board authority, SOR or SRS.",
        "Weights are the SOS shape of ruling R2-SOS (0.25 WP / 0.50 OWP / 0.25 OOWP), "
        "restricted to the common-opponent subset; convergence ruling R2-COMMON-OPP "
        "carried the same shape forward before this direct approval was issued.",
        "Model_Parameters_v2_5_APPROVED.xlsx!18_ACC_POLICY_REFERENCE ACC-EXT-08 "
        "records the common-opponent question as OPEN / REQUIRES RULING. That entry "
        "predates this ruling and is preserved unedited as evidence of the prior "
        "state; it is not authority against the later direct approval.",
    ),
    # Authority representation only. The nine live project execution blockers are
    # calibration, artifact-custody and model-scale work that no ruling can close.
    retires=(),
    supersedes=(
        "18_ACC_POLICY_REFERENCE ACC-EXT-08 read as leaving the common-opponent "
        "formula OPEN / REQUIRES RULING — superseded to exactly the extent that the "
        "exact 0.25/0.50/0.25 formula is now directly approved. The workbook row "
        "itself is preserved unedited.",
        "COMMON_OPPONENT_FORMULA_IS_CANONICAL = False and the "
        "CONVERGENCE_RULING_ONLY status carried under ruling R2-COMMON-OPP, which "
        "predate this direct approval.",
        "Earlier Chairman wording describing the common-opponent formula as 'some "
        "formula that looks like the following' — superseded by the issued ruling, "
        "which states the coefficients are canonical and exact. The earlier wording "
        "is preserved as the prior record and is not edited.",
        "RESULT_WEIGHTED_OPPONENT_STRENGTH as a candidate common-opponent formula.",
    ),
    provenance="FACT",
    instruction=R4_INSTRUCTION,
    resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
)


#: Issued as one instruction for the V3 calibration temporal-order successor.
#: The round is numbered R6 rather than R5 because the R5 lane -- the FCS Elo to
#: V3 point scale adapter -- issued no ruling and already owns that label in
#: ``tests/dynamic_weekly_mc_v3/test_r5_fcs_scale_adapter.py``. Reusing it would
#: put two unrelated things under one round number.
R6_INSTRUCTION = "OPERATION SYTHALAX — V3 CALIBRATION TEMPORAL-ORDER SUCCESSOR R1"


R6_CALIBRATION_TEMPORAL_ORDER = ChairmanRuling(
    convergence_id="R6-CAL-TEMPORAL-ORDER",
    subject=(
        "Temporal ordering evidence for calibration observations that carry no "
        "authentic kickoff timestamp"
    ),
    decision=(
        "Where an authentic kickoff or event timestamp exists, event_time remains "
        "authoritative. Where one does not exist, event_time MUST remain null and a "
        "synthetic noon, midnight or other default time-of-day value MUST NOT be "
        "generated; such an observation may instead be admitted on "
        "governed_temporal_order. Temporal evidence precedence is exactly "
        "EXACT_EVENT_TIME, EXACT_GAME_DATE, WEEK_STAGE_DATE, "
        "GOVERNED_SOURCE_SEQUENCE. Any observation admitted without event_time must "
        "carry temporal_order_basis, temporal_order_key, temporal_order_source and "
        "temporal_order_source_sha256, so the ordering claim is re-checkable against "
        "pinned bytes. GOVERNED_SOURCE_SEQUENCE establishes relative causal order "
        "only and must never be serialized or represented as an inferred kickoff "
        "timestamp. Training, validation and holdout partitions remain forward-only "
        "and temporally disjoint; the holdout remains "
        "SCORED_ONCE_AT_THE_END_NEVER_FOR_SELECTION; random split remains "
        "prohibited. Missing chronology may never be fabricated to make an "
        "observation pass contract admission."
    ),
    evidence=(
        "OPERATION SYTHALAX — V3 CALIBRATION TEMPORAL-ORDER SUCCESSOR R1, issued "
        "with approval token APPROVE_V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1 and "
        "Ruling ID V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1.",
        "The instruction records the evidence established before it was issued: the "
        "historical/modern calibration corpus contains date, stage, week and/or "
        "governed source-sequence ordering, and zero authentic time-of-day values "
        "were found in the staged calibration evidence census.",
        "The historical source packages state explicitly that chronology was not "
        "invented. 2006 and 2007 rely on canonical source-row sequence; later "
        "historical seasons preserve date/week/source-order evidence as available; "
        "modern 2024/2025 walk-forward evidence uses date/stage ordering.",
        "V3_CALIBRATION_DATA_CONTRACT.json first issue — event_time recorded as "
        "unconditionally required. That issue predates this ruling, is preserved "
        "unedited in repository history, and is reissued as contract revision "
        "R1-TEMPORAL-ORDER-SUCCESSOR rather than rewritten.",
    ),
    # Authority representation and contract semantics only. The eight live
    # execution blockers are calibration, governance and model-scale work that no
    # ruling can close, and this ruling closes none of them.
    retires=(),
    supersedes=(
        "V3-CALIBRATION-DATA-CONTRACT-001 read as requiring event_time of every "
        "observation — superseded to exactly the extent that a governed source "
        "recorded no kickoff timestamp. event_time is not made globally optional and "
        "its causal-order guarantee is replaced, not dropped.",
        "Any reading under which an observation lacking a kickoff time could be "
        "admitted by supplying a default time-of-day value.",
    ),
    provenance="FACT",
    chairman_ruling_id="V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1",
    instruction=R6_INSTRUCTION,
    resolution_reason="SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY",
    approval_token="APPROVE_V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1",
)


#: Issued as one instruction for the governed synthetic calibration evidence
#: ruling.
R7_INSTRUCTION = "OPERATION SYTHALAX — GOVERNED SYNTHETIC CALIBRATION EVIDENCE R1"


R7_GOVERNED_SYNTHETIC_EVIDENCE = ChairmanRuling(
    convergence_id="R7-CAL-GOVERNED-SYNTHETIC-EVIDENCE",
    subject="Governed synthetic season corpora as calibration evidence",
    decision=(
        "A byte-verified, provenance-bound GOVERNED SYNTHETIC season corpus may serve "
        "as calibration, validation and holdout evidence for the synthetic V3 model. "
        "The evidence domain must remain explicitly GOVERNED_SYNTHETIC and must never "
        "be relabeled or represented as OBSERVED_REAL_WORLD, EMPIRICAL_REAL_WORLD or "
        "REAL_WORLD_EXTERNAL_VALIDATION. Governed synthetic evidence may be used for "
        "calibration dataset construction, calibration parameter estimation, "
        "validation, untouched holdout scoring, and later human promotion "
        "consideration for the synthetic V3 model. It does NOT establish real-world "
        "predictive validity, sportsbook predictive validity, actual historical NCAA "
        "forecasting performance, or independent external empirical validation. Every "
        "derived dataset and evidence object must preserve source lineage. 2025 "
        "remains HOLDOUT and may not participate in model, hyperparameter, "
        "coefficient, exclusion-threshold, transform, game-SD or FCS mapping "
        "selection. Existing contract controls remain mandatory: temporal admission, "
        "digest continuity, expected-margin provenance, rating-scale declaration, "
        "opponent classification, split integrity and holdout isolation. This ruling "
        "does not authorize filling any missing source fact, does not authorize "
        "Phase5E FCS Elo = 1500 (governed V3 policy remains FCS Elo = 1250), and "
        "promotes no numerical coefficient."
    ),
    evidence=(
        "OPERATION SYTHALAX — GOVERNED SYNTHETIC CALIBRATION EVIDENCE R1, issued "
        "APPROVED under DIRECT_CHAIRMAN_AUTHORITY with approval token "
        "APPROVE_V3_GOVERNED_SYNTHETIC_CALIBRATION_EVIDENCE_R1 and RULING_ID "
        "R7-CAL-GOVERNED-SYNTHETIC-EVIDENCE.",
        "The ruling records its own necessity: the intended V3 calibration "
        "architecture itself uses the audited 2006-2011 and 2024-2025 synthetic "
        "universes, so a blanket refusal of synthetic corpora leaves the synthetic "
        "model uncalibrated without protecting anything.",
        "NCAA_Phase4M_2006_2011_Week_By_Week_Cleanup_Package.zip!reports/"
        "PHASE4M_WEEK_BY_WEEK_CLEANUP_REPORT.md — 'all synthetic games from 2006 "
        "through 2011. ... No external or real-world schedule was used.' The corpus "
        "declares its own domain; the ruling does not reinterpret it.",
        "Power_Crunch_Research_Lab_Phase5D_WalkForward_Package.zip!10_Source_Rulings/"
        "2025 Synthetic Season LOCKED v3.xlsx [Certification] — 'provenance: SCHEDULE "
        "SYNTHETIC. SCORES SIMULATED.'",
        "V3_CALIBRATION_DATA_CONTRACT.json revision R1-TEMPORAL-ORDER-SUCCESSOR — "
        "DATASET_PROVENANCE_REQUIREMENTS['synthetic_content'] recorded synthetic "
        "observation sets as REFUSED. That clause predates this ruling, is preserved "
        "in repository history, and is superseded only to the extent stated here.",
    ),
    # A data-domain ruling. The eight live execution blockers are calibration,
    # governance and model-scale work that no ruling can close.
    retires=(),
    supersedes=(
        "DATASET_PROVENANCE_REQUIREMENTS['synthetic_content'] read as refusing every "
        "synthetic observation set — superseded to exactly the extent that a corpus "
        "is byte-verified, provenance-bound and declared synthetic by its own "
        "governed source. An ungoverned synthetic or test fixture remains refused.",
        "Any reading under which governed synthetic evidence could be recorded, "
        "serialized or reported as observed, empirical or real-world evidence.",
    ),
    provenance="FACT",
    chairman_ruling_id="R7-CAL-GOVERNED-SYNTHETIC-EVIDENCE",
    instruction=R7_INSTRUCTION,
    resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
    approval_token="APPROVE_V3_GOVERNED_SYNTHETIC_CALIBRATION_EVIDENCE_R1",
)


#: Issued as one instruction for the source-recorded walk-forward margin
#: successor.
R8_INSTRUCTION = "OPERATION SYTHALAX — SOURCE-RECORDED WALK-FORWARD MARGIN SUCCESSOR R1"


R8_SOURCE_RECORDED_WALKFORWARD_MARGIN = ChairmanRuling(
    convergence_id="R8-CAL-SOURCE-RECORDED-WALKFORWARD-MARGIN",
    subject="Expected-margin provenance modes and the conditional pregame rating requirement",
    decision=(
        "The V3 calibration contract recognises two expected-margin provenance modes. "
        "MODE A, DERIVED_AT_INGESTION: where expected_margin is computed, "
        "reconstructed, transformed or otherwise derived by the V3 calibration adapter "
        "from underlying team rating states, pregame_team_rating and "
        "pregame_opponent_rating remain mandatory alongside expected_margin, "
        "expected_margin_transform, expected_margin_model_id, "
        "rating_scale_declaration and complete source provenance. Nothing about this "
        "mode changes. MODE B, SOURCE_RECORDED_WALKFORWARD: where a governed source "
        "artifact itself records the prediction generated before the target game, the "
        "observation requires expected_margin, expected_margin_source_type = "
        "SOURCE_RECORDED_WALKFORWARD, expected_margin_model_id, "
        "expected_margin_transform or sufficient source-bound model specification, "
        "rating_scale_declaration, source artifact identity, source artifact SHA256, "
        "source member identity, source row / game identity, temporal provenance "
        "proving the prediction belongs to the pregame walk-forward state, and "
        "evidence domain GOVERNED_SYNTHETIC for the current corpus; "
        "pregame_team_rating and pregame_opponent_rating may then be null ONLY where "
        "those component states are not recorded by the governed source. A generic "
        "expected-margin value is not sufficient and the mode may not be obtained by "
        "declaring it: SOURCE_RECORDED_WALKFORWARD fails closed unless the source "
        "provenance establishes that the prediction is present in the governed source "
        "artifact, is associated deterministically with the target game, was produced "
        "within the source's documented walk-forward chronology, is not a "
        "retrospective full-season prediction, is not calculated from the target "
        "game's actual result, has known model identity and scale, and rests on valid "
        "source digest continuity. Where the governed source does record component "
        "ratings — 2006 and 2007 — they are preserved and are never deliberately "
        "nulled. No Baxter replay may be constructed solely to populate component "
        "ratings, and reconstructed component states may never be represented as "
        "source observations. This ruling authorises no retrospective expected "
        "margins, no final-season ratings as pregame states, no fabricated ratings, "
        "event_time, overtime status or team classification, no actual-margin-derived "
        "predictions, no arbitrary synthetic inputs, no Phase5E FCS Elo 1500, no "
        "coefficient promotion and no FCS point-scale promotion. V3 FCS Elo remains "
        "1250."
    ),
    evidence=(
        "OPERATION SYTHALAX — SOURCE-RECORDED WALK-FORWARD MARGIN SUCCESSOR R1, "
        "issued APPROVED under DIRECT_CHAIRMAN_AUTHORITY with approval token "
        "APPROVE_V3_SOURCE_RECORDED_WALKFORWARD_MARGIN_R1 and RULING_ID "
        "R8-CAL-SOURCE-RECORDED-WALKFORWARD-MARGIN.",
        "The ruling records its own rationale: the governed Baxter historical and "
        "modern evidence frequently preserves the actual pregame walk-forward "
        "predicted margin but does not preserve both underlying pregame rating "
        "components, and a deterministic replay solely to manufacture missing "
        "observation fields would be weaker provenance than preserving the prediction "
        "the governed source actually recorded.",
        "Baxter_v1_2006_2011_2024_2025_Complete_Package.zip!Baxter_Ratings_v1_<season>"
        "_External_Validation.xlsx [Walk Forward] — every season's prediction is read "
        "from a sheet named Walk Forward. rating_a_pre and rating_b_pre exist for 2006 "
        "and 2007 and for no later season.",
        "V3_CALIBRATION_DATA_CONTRACT.json revision R1-TEMPORAL-ORDER-SUCCESSOR — "
        "pregame_team_rating and pregame_opponent_rating recorded as unconditionally "
        "required. That clause predates this ruling, is preserved in repository "
        "history, and is superseded only to the extent stated here.",
    ),
    # A contract-semantics ruling. The eight live execution blockers are
    # calibration, governance and model-scale work that no ruling can close.
    retires=(),
    supersedes=(
        "pregame_team_rating and pregame_opponent_rating read as unconditionally "
        "required of every observation — superseded to exactly the extent that a "
        "governed source artifact recorded the pregame walk-forward prediction and "
        "records no component states. They remain mandatory under "
        "DERIVED_AT_INGESTION, and they are never nulled where the source records "
        "them.",
        "Any reading under which a retrospective full-season fit, a final-season "
        "rating, or a value computed from the actual result could serve as a "
        "source-recorded walk-forward prediction.",
    ),
    provenance="FACT",
    chairman_ruling_id="R8-CAL-SOURCE-RECORDED-WALKFORWARD-MARGIN",
    instruction=R8_INSTRUCTION,
    resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
    approval_token="APPROVE_V3_SOURCE_RECORDED_WALKFORWARD_MARGIN_R1",
)


#: Issued as one instruction for the full-corpus / use-specific eligibility
#: successor.
R9_INSTRUCTION = "OPERATION SYTHALAX — FULL 5,148 CORPUS / USE-SPECIFIC ELIGIBILITY R1"


R9_FULL_CORPUS_USE_SPECIFIC_ELIGIBILITY = ChairmanRuling(
    convergence_id="R9-CAL-FULL-CORPUS-USE-SPECIFIC-ELIGIBILITY",
    subject="Canonical 5,148-game calibration corpus and use-specific eligibility",
    decision=(
        "The complete audited 5,148-game corpus is the canonical historical "
        "calibration corpus. The prior treatment of 3,259 rows as the calibration "
        "dataset and 1,889 rows as globally excluded is superseded. A field missing "
        "for one calibration purpose must not globally discard a game that is valid "
        "evidence for other calibration purposes. The universal ADMITTED / EXCLUDED "
        "model is replaced by CORPUS MEMBERSHIP plus USE-SPECIFIC ELIGIBILITY: a game "
        "belongs to the canonical calibration corpus if its source row belongs to the "
        "verified 5,148-game source universe, and whether it may participate in a "
        "specific numerical procedure depends on the evidence that procedure requires. "
        "SOURCE_CORPUS_ROWS equals 5,148 and the canonical derived corpus carries all "
        "5,148 source-game records with provenance and field-availability metadata; no "
        "missing value is fabricated and no completeness is manufactured. Source "
        "provenance is preserved exactly: OBSERVED_REAL_WORLD and GOVERNED_SYNTHETIC "
        "are never relabeled, evidence domain is provenance metadata and does not by "
        "itself determine corpus membership, and both may participate where their "
        "required fields are supported. Any calculation of actual_margin minus "
        "expected_margin requires a legitimate pregame expected margin under R8 "
        "semantics; a row lacking one remains in the corpus but is ineligible for that "
        "residual calculation. Outcome-only analyses require no pregame prediction and "
        "must not be silently converted into model-residual analyses. Overtime UNKNOWN "
        "remains UNKNOWN and is never converted to False; a game with unknown overtime "
        "remains usable for procedures that do not require overtime classification, and "
        "an overtime-sensitive procedure requires known status. Every FCS game remains "
        "in the canonical corpus, FCS Elo remains 1250, the Elo-1250-to-V3-point-scale "
        "adapter remains unresolved, and an FCS game participates in calculations that "
        "do not depend on that unresolved mapping. Both T073vT114 contests remain in "
        "the corpus with source_game_id preserved, source_game_id_unique false, and a "
        "distinct deterministic provenance identity each; any calculation requiring a "
        "globally unique source_game_id must refuse that key and use the provenance "
        "identity. All 713 2011 source records remain, with lineage flags for "
        "G2011_P3056 and G2011_P2932; a procedure needing the historical 711-game "
        "engine-comparison universe expresses that as a use-specific eligibility mask. "
        "Malformed source rows remain represented and may be numerically ineligible "
        "where their factual fields cannot be established. All 757 2025 games remain in "
        "the corpus and 2025 remains HOLDOUT: corpus membership yes, model selection "
        "participation no."
    ),
    evidence=(
        "OPERATION SYTHALAX — FULL 5,148 CORPUS / USE-SPECIFIC ELIGIBILITY R1, issued "
        "APPROVED under DIRECT_CHAIRMAN_AUTHORITY with RULING_ID "
        "R9-CAL-FULL-CORPUS-USE-SPECIFIC-ELIGIBILITY.",
        "V3_CALIBRATION_5148_ADAPTER_STATUS_R1.json under rulings R6/R7/R8 recorded "
        "ADMITTED_ROWS 3,259 and EXCLUDED_ROWS 1,889 against a single universal "
        "observation contract. That accounting is preserved as the record of the "
        "prior run and is superseded as a description of the usable calibration "
        "population.",
        "The 1,889 rows carry real, byte-verified game results. 1,223 of them are "
        "excluded only by the walk-forward eligibility flag and 336 only by an "
        "unresolved observation date — neither of which is required by an "
        "outcome-only analysis.",
    ),
    # A corpus-architecture ruling. The eight live execution blockers are
    # calibration, governance and model-scale work that no ruling can close.
    retires=(),
    supersedes=(
        "The universal ADMITTED / EXCLUDED model in which a row failing the full "
        "walk-forward observation contract was reported as excluded from calibration "
        "altogether — superseded by corpus membership plus use-specific eligibility. "
        "The full contract itself is unchanged and is one use among several.",
        "The characterisation of 3,259 rows as the calibration dataset and 1,889 as "
        "globally excluded. The 3,259 are the fully paired, contract-complete "
        "walk-forward subset; the 1,889 remain corpus members.",
    ),
    provenance="FACT",
    chairman_ruling_id="R9-CAL-FULL-CORPUS-USE-SPECIFIC-ELIGIBILITY",
    instruction=R9_INSTRUCTION,
    resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
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

R3_RULINGS: tuple[ChairmanRuling, ...] = (
    R3_SOS_SEMANTICS,
    R3_CFP_FIXED_TOPOLOGY,
)

R4_RULINGS: tuple[ChairmanRuling, ...] = (R4_COMMON_OPPONENT_FORMULA,)

R6_RULINGS: tuple[ChairmanRuling, ...] = (R6_CALIBRATION_TEMPORAL_ORDER,)

R7_RULINGS: tuple[ChairmanRuling, ...] = (R7_GOVERNED_SYNTHETIC_EVIDENCE,)

R8_RULINGS: tuple[ChairmanRuling, ...] = (R8_SOURCE_RECORDED_WALKFORWARD_MARGIN,)

R9_RULINGS: tuple[ChairmanRuling, ...] = (R9_FULL_CORPUS_USE_SPECIFIC_ELIGIBILITY,)

#: Every ruling issued across every convergence round. R2_RULINGS, R3_RULINGS and
#: R4_RULINGS stay exactly as the audited records; each later round adds to them
#: rather than editing them, so the succession stays readable in one place.
ALL_RULINGS: tuple[ChairmanRuling, ...] = (
    R2_RULINGS
    + R3_RULINGS
    + R4_RULINGS
    + R6_RULINGS
    + R7_RULINGS
    + R8_RULINGS
    + R9_RULINGS
)

_BY_ID = {r.convergence_id: r for r in ALL_RULINGS}


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
    for r in ALL_RULINGS:
        for blocker in r.retires:
            if blocker in out:
                raise GovernanceBlock(
                    f"Blocker {blocker} is claimed by two rulings: {out[blocker]} and {r.convergence_id}"
                )
            out[blocker] = r.convergence_id
    return out


def as_dicts() -> list[dict[str, object]]:
    return [r.as_dict() for r in ALL_RULINGS]
