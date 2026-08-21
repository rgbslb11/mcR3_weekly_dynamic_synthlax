"""Per-blocker disposition reporting for Dynamic Weekly MC V3.

The 18 execution blockers are not homogeneous. Some are implementation defects
that deterministic reconciliation can close outright; some await a human ruling
that no amount of analysis can substitute for; some are missing artifacts. A
flat count of "18 blockers" hides that distinction and makes the remaining work
look larger and less tractable than it is.

Each blocker carries exactly one disposition from :data:`DISPOSITIONS`. The word
``RESOLVED`` is reserved: it may be used only where execution can consume the
result without inference. A blocker whose *evidence* is fully understood but
whose *decision* is outstanding is not resolved.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

DISPOSITIONS = (
    "RESOLVED_BY_EXISTING_AUTHORITY",
    "RESOLVED_BY_DETERMINISTIC_RECONCILIATION",
    "RESOLVED_BY_CHAIRMAN_RULING",
    "HUMAN_RULING_REQUIRED",
    "MISSING_AUTHORITATIVE_DATA",
    "CALIBRATION_EXPERIMENT_REQUIRED",
    "MODEL_SCALE_ADAPTER_REQUIRED",
    "REMAINS_BLOCKED",
)

RESOLVED_DISPOSITIONS = (
    "RESOLVED_BY_EXISTING_AUTHORITY",
    "RESOLVED_BY_DETERMINISTIC_RECONCILIATION",
    "RESOLVED_BY_CHAIRMAN_RULING",
)


@dataclass(frozen=True)
class BlockerDisposition:
    blocker_id: str
    disposition: str
    evidence: str
    required_to_clear: str
    governance_group: str
    #: The R2 ruling that retired this blocker, when one did.
    ruling: str | None = None

    def __post_init__(self) -> None:
        if self.disposition not in DISPOSITIONS:
            raise ValueError(f"Unknown disposition {self.disposition!r} for {self.blocker_id}")
        if self.disposition == "RESOLVED_BY_CHAIRMAN_RULING" and not self.ruling:
            raise ValueError(
                f"{self.blocker_id} claims resolution by ruling but names no ruling"
            )

    @property
    def resolved(self) -> bool:
        return self.disposition in RESOLVED_DISPOSITIONS


#: Governance groups let blockers that are really one decision be ruled on once.
GROUP_HFA = "HFA_BASELINE_RULING"
GROUP_GAME_SD = "GAME_SD_CALIBRATION"
GROUP_FCS = "FCS_SOURCE_AUTHORITY"
GROUP_COMMITTEE = "COMMITTEE_STRENGTH_SOURCE"
GROUP_AAC = "AAC_DIVISION_ARTIFACT"
GROUP_SCHEDULE_PROV = "SCHEDULE_PROVENANCE"
GROUP_SCHEDULE_13 = "THIRTEEN_GAME_EXCEPTIONS"
GROUP_BRACKET = "POSTSEASON_BRACKET_MAPPING"
GROUP_A8_ECL = "A8_ECL_ORDERING"
GROUP_CALIBRATION = "RERATING_CALIBRATION_PROGRAM"
GROUP_BOARD_OF_RECORD = "BOARD_OF_RECORD_ARTIFACT"
GROUP_SOS_SEMANTICS = "SOS_DENOMINATOR_SEMANTICS"
GROUP_FCS_SCALE = "FCS_MODEL_SCALE_ADAPTER"


DISPOSITION_REGISTER: tuple[BlockerDisposition, ...] = (
    # --- calibration -------------------------------------------------------
    *[
        BlockerDisposition(
            blocker_id=f"calibration.{name}",
            disposition="CALIBRATION_EXPERIMENT_REQUIRED",
            evidence=(
                "Canonical value is null. No historical calibration observation set is "
                "mounted, so no experiment can be scored. Open item ENG-CAL-MARGIN."
            ),
            required_to_clear=(
                "Mount a governed calibration dataset, run the experimental harness "
                "against a named objective, then promote by explicit human ruling."
            ),
            governance_group=GROUP_CALIBRATION,
        )
        for name in (
            "weekly_performance_residual_coefficient",
            "weekly_movement_cap_points",
            "recent_form_weights",
            "blowout_treatment",
            "sample_size_regularization",
        )
    ],
    BlockerDisposition(
        blocker_id="calibration.game_sd_points",
        disposition="CALIBRATION_EXPERIMENT_REQUIRED",
        evidence=(
            "Canonical value is null. The only recorded figure, margin SD 20.2, sits "
            "above its own 16-18 harness band and open item ENG-CAL-MARGIN remains OPEN. "
            "V2 usage does not make it approved."
        ),
        required_to_clear=(
            "Rerun calibration and ratify a value, or explicitly ratify 20.2 despite the band."
        ),
        governance_group=GROUP_GAME_SD,
    ),
    # --- governed input / policy -------------------------------------------
    BlockerDisposition(
        blocker_id="hfa_baseline_points",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-HFA-3P5 sets the V3 football-point HFA to 3.5. ENG-HOME-FIELD 4.0 "
            "stays recorded HISTORICAL / NOT CURRENT and CCG-HFA_ELO 65 stays a separate Elo "
            "parameter; neither register row was edited. "
        ),
        required_to_clear=(
            "Cleared: config carries 3.5 and the legacy value is refused by name. "
        ),
        governance_group=GROUP_HFA,
        ruling="R2-HFA-3P5",
    ),
    BlockerDisposition(
        blocker_id="fcs_translation_policy",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-FCS-ELO-1250 fixes FCS at Elo 1250 with no toggle. No Board equivalent "
            "and no inverted Elo/Board transform is used. "
        ),
        required_to_clear=(
            "Cleared: config carries FIXED_ELO_1250. "
        ),
        governance_group=GROUP_FCS,
        ruling="R2-FCS-ELO-1250",
    ),
    BlockerDisposition(
        blocker_id="committee_tiebreak_strength_source",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-COMMITTEE-TB retires the PRESEASON_STRENGTH / "
            "FINAL_WEEKLY_FOOTBALL_STRENGTH framing outright and replaces it with the "
            "deterministic chain TB1 head-to-head, TB2 common-opponent performance, TB3 SOS, "
            "TB4 previous week's board. "
        ),
        required_to_clear=(
            "Cleared: the obsolete field stays null and is refused if populated; "
            "committee_tiebreak_policy carries the structured chain. "
        ),
        governance_group=GROUP_COMMITTEE,
        ruling="R2-COMMITTEE-TB",
    ),
    BlockerDisposition(
        blocker_id="inputs.aac_divisions_csv",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-AAC-SUCCESSOR issues aac_divisions_2026_R2_SUCCESSOR.csv (554 B, "
            "sha256 92fd7f78...) derived under R-CCG-07 from the hash-verified canonical "
            "master. The legacy 577-byte artifact is recorded NOT_MOUNTED_IN_REPOSITORY and "
            "was not reproduced. "
        ),
        required_to_clear=(
            "Cleared: a governed successor is mounted and digest-verified. "
        ),
        governance_group=GROUP_AAC,
        ruling="R2-AAC-SUCCESSOR",
    ),
    # --- provenance ---------------------------------------------------------
    BlockerDisposition(
        blocker_id="provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH",
        disposition="RESOLVED_BY_DETERMINISTIC_RECONCILIATION",
        evidence=(
            "Implementation defect, not a content defect. The canonical method serializes "
            "null cells as blanks; 735 of 743 data rows omit the trailing venue_rule cell "
            "and were written ragged. Padding rows to header width reproduces the certified "
            "digest bd8089f7... exactly. The certified hash was not altered."
        ),
        required_to_clear="Cleared: reproduction now matches certification.",
        governance_group=GROUP_SCHEDULE_PROV,
    ),
    BlockerDisposition(
        blocker_id="provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-SCHED-V5-AUTH accepts a binary source-copy difference when the "
            "certified Games content reproduces. It does. All three historical binary hashes "
            "(db26c3ff registered, b0f2c2cd mounted, 8d4d5112 superseded v4) are preserved "
            "and the observation is still reported in provenance_anomalies. "
        ),
        required_to_clear=(
            "Cleared by ruling; a content failure or a mounted v4 artifact still blocks. "
        ),
        governance_group=GROUP_SCHEDULE_PROV,
        ruling="R2-SCHED-V5-AUTH",
    ),
    # --- governance / rules -------------------------------------------------
    BlockerDisposition(
        blocker_id="governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Same ruling. The two register values still differ and are preserved; the ruling "
            "makes the difference non-blocking rather than editing either row. "
        ),
        required_to_clear=(
            "Cleared by the single HFA ruling. "
        ),
        governance_group=GROUP_HFA,
        ruling="R2-HFA-3P5",
    ),
    BlockerDisposition(
        blocker_id="governance.GAME_SD_CALIBRATION_OPEN",
        disposition="CALIBRATION_EXPERIMENT_REQUIRED",
        evidence="Open item ENG-CAL-MARGIN is OPEN: margin SD 20.2 exceeds the 16-18 band.",
        required_to_clear="Same calibration ruling as calibration.game_sd_points.",
        governance_group=GROUP_GAME_SD,
    ),
    BlockerDisposition(
        blocker_id="governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-SCHED-13GAME approves ARK, GAST, UK, VAN, WVU. Deterministic "
            "validation confirms exactly 13 W1-W14 REG rows each, no duplicate game_id, no "
            "duplicate opponent/date artefact, no CCG template counted, and no unapproved "
            "team above 12. "
        ),
        required_to_clear=(
            "Cleared: ruling plus passing validation. OI-SCHED-13 and RAT-002 are left "
            "unedited. "
        ),
        governance_group=GROUP_SCHEDULE_13,
        ruling="R2-SCHED-13GAME",
    ),
    BlockerDisposition(
        blocker_id="governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-FCS-ELO-1250 supersedes the POWER_CRUNCH Build Manifest 'Model use "
            "authorized: FALSE' for V3 use. The manifest is preserved unedited. "
        ),
        required_to_clear=(
            "Cleared by ruling; the superseded record remains visible. "
        ),
        governance_group=GROUP_FCS,
        ruling="R2-FCS-ELO-1250",
    ),
    BlockerDisposition(
        blocker_id="governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Bracket_Flow fixed quarterfinal slots as 'E = 1 v W(R1)' and never stated which "
            "first-round winner fills which slot — that remains true of the workbook, which is "
            "neither rewritten nor reinterpreted, and "
            "postseason.QUARTERFINAL_SLOT_EDGES_STATED_IN_ARTIFACT stays False. Ruling "
            "R3-CFP-FIXED-TOPOLOGY fills the gap by direct successor Chairman authority: "
            "QF-E = 1 v W(R1-B), QF-F = 2 v W(R1-A), QF-G = 3 v W(R1-C), QF-H = 4 v W(R1-D), "
            "with no reseeding and the bracket consuming final assigned seeds."
        ),
        required_to_clear=(
            "Cleared by SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY, not because the source workbook "
            "contained the mapping. "
        ),
        governance_group=GROUP_BRACKET,
        ruling="R3-CFP-FIXED-TOPOLOGY",
    ),
    BlockerDisposition(
        blocker_id="governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R2-A8-ECL-ORDER breaks the cycle causally: the TB-3 board is computed "
            "after the seven CCGs and before any G5 automatic-bid seeding, so it never "
            "consumes the champion flag it is resolving. The historical cycle is preserved in "
            "ordering.py as the superseded reading. "
        ),
        required_to_clear=(
            "Cleared by causal sequencing, not by choosing a tiebreak. "
        ),
        governance_group=GROUP_A8_ECL,
        ruling="R2-A8-ECL-ORDER",
    ),
    # --- opened by R2 convergence -------------------------------------------
    #
    # Newly issued governance names artifacts and mathematics this repository
    # does not hold. Each entry below is a gate that did not exist before,
    # surfaced narrowly rather than assumed away.
    BlockerDisposition(
        blocker_id="inputs.board_of_record_i_k",
        disposition="MISSING_AUTHORITATIVE_DATA",
        evidence=(
            "Ruling R2-BOARD-OF-RECORD names "
            "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx as Board of Record and forbids "
            "substituting Board I-H. That artifact is not mounted; Board I-H v2 is present "
            "only as sheet 08_BOARD_IH_TOP25 and stays historical evidence."
        ),
        required_to_clear=(
            "Mount the named Board-of-Record artifact. CCG-TB3, COMMITTEE-TB4, A8_ECL-TB3 and "
            "CFP selection all need real board rows."
        ),
        governance_group=GROUP_BOARD_OF_RECORD,
    ),
    BlockerDisposition(
        blocker_id="governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED",
        disposition="RESOLVED_BY_CHAIRMAN_RULING",
        evidence=(
            "Ruling R3-SOS-OWP-OOWP-SEMANTICS answers all six questions by direct Chairman "
            "authority, leaving the R2-SOS weights unchanged: opponent-versus-evaluated-team "
            "games are excluded from OWP; OWP and OOWP are schedule-instance weighted so a "
            "repeated opponent contributes once per completed meeting; OOWP is the mean of each "
            "opponent's own governed OWP; schedule-only FCS entities contribute only governed "
            "available records; and a component with zero qualifying observations is "
            "UNAVAILABLE / NULL rather than 0, 0.0 or 0.500."
        ),
        required_to_clear=(
            "Cleared by DIRECT_CHAIRMAN_AUTHORITY with a deterministic implementation and "
            "tests. "
        ),
        governance_group=GROUP_SOS_SEMANTICS,
        ruling="R3-SOS-OWP-OOWP-SEMANTICS",
    ),
    BlockerDisposition(
        blocker_id="model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
        disposition="MODEL_SCALE_ADAPTER_REQUIRED",
        evidence=(
            "The FCS rating policy is NOT in question: ruling R2-FCS-ELO-1250 fixes Elo 1250 "
            "and that stands. What is missing is a model-scale adapter. All 13 schedule-only "
            "FCS entities carry preseason_strength_points=None, they appear in 15 regular-season "
            "games across weeks 2-5 and 12, and engine._initialize_states raises on the first of "
            "them. V2.1 bridged this via the Board I-H equivalent "
            "(V2_1_STATIC_CONTROL!Methodology!A8), the exact route this ruling forbids."
        ),
        required_to_clear=(
            "Issue an Elo-to-unified-points scale rule, or calibrate one, for schedule-only FCS "
            "entities. This is a model-scale/calibration item, not an FCS policy question."
        ),
        governance_group=GROUP_FCS_SCALE,
    ),
)


def dispositions() -> tuple[BlockerDisposition, ...]:
    return DISPOSITION_REGISTER


def summary(register: Iterable[BlockerDisposition] | None = None) -> dict[str, object]:
    """Summarize dispositions, including which blockers share one ruling."""
    entries = tuple(register) if register is not None else DISPOSITION_REGISTER
    by_disposition: dict[str, list[str]] = {}
    by_group: dict[str, list[str]] = {}
    for entry in entries:
        by_disposition.setdefault(entry.disposition, []).append(entry.blocker_id)
        by_group.setdefault(entry.governance_group, []).append(entry.blocker_id)
    resolved = [e.blocker_id for e in entries if e.resolved]
    return {
        "total": len(entries),
        "resolved": sorted(resolved),
        "resolved_count": len(resolved),
        "remaining_count": len(entries) - len(resolved),
        "by_disposition": {k: sorted(v) for k, v in sorted(by_disposition.items())},
        "governance_groups": {k: sorted(v) for k, v in sorted(by_group.items())},
        "distinct_remaining_rulings": sorted(
            {e.governance_group for e in entries if not e.resolved}
        ),
    }


# --- historical blocker states, preserved -------------------------------------
#
# Counts move as governance advances. These two sets are what the record said at
# each checkpoint, and they are frozen so a regression test can prove exactly
# which blockers moved rather than trusting a total.

#: The 18 blockers carried by the tested V3 baseline (V3_BUILD_MANIFEST.json).
R1_BASELINE_BLOCKERS: frozenset[str] = frozenset(
    {
        "calibration.weekly_performance_residual_coefficient",
        "calibration.weekly_movement_cap_points",
        "calibration.recent_form_weights",
        "calibration.blowout_treatment",
        "calibration.game_sd_points",
        "calibration.sample_size_regularization",
        "hfa_baseline_points",
        "fcs_translation_policy",
        "committee_tiebreak_strength_source",
        "inputs.aac_divisions_csv",
        "provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH",
        "provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5",
        "governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5",
        "governance.GAME_SD_CALIBRATION_OPEN",
        "governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED",
        "governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE",
        "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",
        "governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT",
    }
)

#: The 17 live at the independently audited PR #3 head e3e1e41, after the
#: schedule content-hash reconciliation and before any R2 ruling.
R1_AUDITED_LIVE_BLOCKERS: frozenset[str] = R1_BASELINE_BLOCKERS - {
    "provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH"
}

#: Retired by the R2 rulings, each with its deterministic validation passing.
R2_RETIRED_BLOCKERS: frozenset[str] = frozenset(
    {
        "provenance.SCHEDULE_BINARY_HASH_MISMATCH_VS_MODEL_PARAMETERS_V2_5",
        "governance.FIVE_13_GAME_SCHEDULE_EXCEPTIONS_UNRATIFIED",
        "hfa_baseline_points",
        "governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5",
        "fcs_translation_policy",
        "governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE",
        "committee_tiebreak_strength_source",
        "inputs.aac_divisions_csv",
        "governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT",
    }
)

#: Opened by R2 because newly issued governance names evidence this repository
#: does not hold. Not a regression: each replaces an assumption with a gate.
R2_OPENED_BLOCKERS: frozenset[str] = frozenset(
    {
        "inputs.board_of_record_i_k",
        "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED",
        "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
    }
)

#: DERIVED — the exact live set expected after R2 convergence.
R2_EXPECTED_LIVE_BLOCKERS: frozenset[str] = (
    R1_AUDITED_LIVE_BLOCKERS - R2_RETIRED_BLOCKERS
) | R2_OPENED_BLOCKERS


#: Retired by the R3 final-convergence rulings, each with its deterministic
#: validation passing. Exactly two — both governance, neither calibration.
R3_RETIRED_BLOCKERS: frozenset[str] = frozenset(
    {
        "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED",
        "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",
    }
)

#: Why each R3 retirement is permitted. Recorded so an auditor never has to infer
#: that a source artifact was reinterpreted — it was not.
R3_RETIREMENT_REASONS: dict[str, str] = {
    "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED": "DIRECT_CHAIRMAN_AUTHORITY",
    "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT": (
        "SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY"
    ),
}

#: R3 opened nothing. Governance closure never invents a new gate.
R3_OPENED_BLOCKERS: frozenset[str] = frozenset()

#: DERIVED — the exact live set expected after R3 governance closure alone,
#: before any artifact mount. Nine.
R3_EXPECTED_LIVE_BLOCKERS: frozenset[str] = (
    R2_EXPECTED_LIVE_BLOCKERS - R3_RETIRED_BLOCKERS
) | R3_OPENED_BLOCKERS

#: Retired only if the exact approved Board-of-Record binary mounts and its
#: SHA-256 verifies. Custody, not policy.
R3_BOARD_OF_RECORD_MOUNT_BLOCKER = "inputs.board_of_record_i_k"

#: DERIVED — the eight that would remain if the Board-of-Record mount succeeded.
R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED: frozenset[str] = (
    R3_EXPECTED_LIVE_BLOCKERS - {R3_BOARD_OF_RECORD_MOUNT_BLOCKER}
)

#: The lanes the remaining work belongs to. No governance item is left.
R3_REMAINING_CLASSIFICATION: dict[str, str] = {
    "calibration.weekly_performance_residual_coefficient": "CALIBRATION",
    "calibration.weekly_movement_cap_points": "CALIBRATION",
    "calibration.recent_form_weights": "CALIBRATION",
    "calibration.blowout_treatment": "CALIBRATION",
    "calibration.game_sd_points": "CALIBRATION",
    "calibration.sample_size_regularization": "CALIBRATION",
    "governance.GAME_SD_CALIBRATION_OPEN": "CALIBRATION",
    "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER": "ENGINEERING_MODEL_SCALE",
    "inputs.board_of_record_i_k": "ARTIFACT_CUSTODY",
}


def convergence_delta() -> dict[str, object]:
    """The exact before/after blocker accounting, computed rather than asserted."""
    return {
        "r1_baseline_count": len(R1_BASELINE_BLOCKERS),
        "r1_audited_live_count": len(R1_AUDITED_LIVE_BLOCKERS),
        "r2_expected_live_count": len(R2_EXPECTED_LIVE_BLOCKERS),
        "retired_by_r2": sorted(R2_RETIRED_BLOCKERS),
        "opened_by_r2": sorted(R2_OPENED_BLOCKERS),
        "carried_forward": sorted(R1_AUDITED_LIVE_BLOCKERS - R2_RETIRED_BLOCKERS),
        "expected_live": sorted(R2_EXPECTED_LIVE_BLOCKERS),
        "retired_by_r3": sorted(R3_RETIRED_BLOCKERS),
        "opened_by_r3": sorted(R3_OPENED_BLOCKERS),
        "r3_expected_live_count": len(R3_EXPECTED_LIVE_BLOCKERS),
        "r3_expected_live": sorted(R3_EXPECTED_LIVE_BLOCKERS),
        "r3_expected_live_if_board_mounted": sorted(
            R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
        ),
        "r3_retirement_reasons": dict(sorted(R3_RETIREMENT_REASONS.items())),
    }
