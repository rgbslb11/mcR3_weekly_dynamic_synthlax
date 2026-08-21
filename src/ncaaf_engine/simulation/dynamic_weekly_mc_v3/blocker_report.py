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
    "HUMAN_RULING_REQUIRED",
    "MISSING_AUTHORITATIVE_DATA",
    "CALIBRATION_EXPERIMENT_REQUIRED",
    "REMAINS_BLOCKED",
)

RESOLVED_DISPOSITIONS = (
    "RESOLVED_BY_EXISTING_AUTHORITY",
    "RESOLVED_BY_DETERMINISTIC_RECONCILIATION",
)


@dataclass(frozen=True)
class BlockerDisposition:
    blocker_id: str
    disposition: str
    evidence: str
    required_to_clear: str
    governance_group: str

    def __post_init__(self) -> None:
        if self.disposition not in DISPOSITIONS:
            raise ValueError(f"Unknown disposition {self.disposition!r} for {self.blocker_id}")

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
        disposition="HUMAN_RULING_REQUIRED",
        evidence=(
            "Two verified-but-conflicting values: ENG-HOME-FIELD 4.0 (cfb_sim.py, V2 "
            "legacy, calibrated up from 2.4) and SCHED-HFA-BASE 3.5 (current governed "
            "schedule/model parameter). No superseding ruling exists in 13_SUPERSESSION_LOG."
        ),
        required_to_clear="Chairman ruling selecting 4.0 or 3.5 as the V3 baseline.",
        governance_group=GROUP_HFA,
    ),
    BlockerDisposition(
        blocker_id="fcs_translation_policy",
        disposition="HUMAN_RULING_REQUIRED",
        evidence=(
            "R-FCS-RATING-01 fixes FCS sim_rating 1397.51 and records a board equivalent "
            "of 0.297514, but the POWER_CRUNCH Build Manifest states 'Board columns for "
            "FCS: BLANK - Board-equivalent recorded not issued'. No governed rule converts "
            "an FCS rating into unified neutral points."
        ),
        required_to_clear=(
            "An explicit translation rule, issued rather than merely recorded. "
            "Inverting the Elo/Board transform would be an ad hoc conversion."
        ),
        governance_group=GROUP_FCS,
    ),
    BlockerDisposition(
        blocker_id="committee_tiebreak_strength_source",
        disposition="HUMAN_RULING_REQUIRED",
        evidence=(
            "The COMMITTEE sheet is marked UNPATCHED with defect D-09 'No deterministic "
            "tiebreak rule', and instructs that it not be wired in until patched. Neither "
            "PRESEASON_STRENGTH nor FINAL_WEEKLY_FOOTBALL_STRENGTH is designated."
        ),
        required_to_clear="Ruling designating the final-strength tiebreak source.",
        governance_group=GROUP_COMMITTEE,
    ),
    BlockerDisposition(
        blocker_id="inputs.aac_divisions_csv",
        disposition="MISSING_AUTHORITATIVE_DATA",
        evidence=(
            "R-CCG-07 ratifies an 8/8 American/Athletic split and the canonical team "
            "master carries a matching membership (8 American, 8 Athletic, covering all "
            "16 AAC teams). The ratified artifact aac_divisions_2026_RATIFIED.csv "
            "(577 bytes, sha256 e0f674b4...) is registered but not mounted, and its exact "
            "column set and ordering are unrecorded, so its digest cannot be reproduced."
        ),
        required_to_clear=(
            "Supply the ratified CSV, or rule explicitly that the canonical-master-derived "
            "membership substitutes for it."
        ),
        governance_group=GROUP_AAC,
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
        disposition="MISSING_AUTHORITATIVE_DATA",
        evidence=(
            "Source-copy mismatch. The mounted workbook hashes to b0f2c2cd..., not the "
            "registered v5 binary db26c3ff..., and is not the superseded v4 binary either. "
            "Games-sheet content is provably certified, so the fixtures are intact and only "
            "the artifact custody chain is broken."
        ),
        required_to_clear=(
            "Supply the registered v5 workbook, or ratify the mounted copy as the "
            "authoritative binary and update the registered hash by ruling."
        ),
        governance_group=GROUP_SCHEDULE_PROV,
    ),
    # --- governance / rules -------------------------------------------------
    BlockerDisposition(
        blocker_id="governance.V3_HFA_BASELINE_CONFLICT_4P0_VS_3P5",
        disposition="HUMAN_RULING_REQUIRED",
        evidence="Same underlying decision as hfa_baseline_points; detected from the parameter register.",
        required_to_clear="Single HFA ruling clears both entries.",
        governance_group=GROUP_HFA,
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
        disposition="HUMAN_RULING_REQUIRED",
        evidence=(
            "Open item OI-SCHED-13 is OPEN for ARK, GAST, UK, VAN, WVU. Ratification packet "
            "RAT-002 carries no chairman_decision, and its recorded safe default if deferred "
            "is explicitly 'Block final season run'."
        ),
        required_to_clear="Chairman decision on RAT-002: correct the schedules or ratify the exceptions.",
        governance_group=GROUP_SCHEDULE_13,
    ),
    BlockerDisposition(
        blocker_id="governance.FCS_SOURCE_MODEL_USE_AUTHORIZED_FALSE",
        disposition="HUMAN_RULING_REQUIRED",
        evidence=(
            "POWER_CRUNCH Build Manifest records 'Model use authorized: FALSE'. No superseding "
            "authorization exists. This value must not be overridden."
        ),
        required_to_clear="Explicit superseding authorization for model use of the FCS source.",
        governance_group=GROUP_FCS,
    ),
    BlockerDisposition(
        blocker_id="governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",
        disposition="HUMAN_RULING_REQUIRED",
        evidence=(
            "Bracket_Flow fixes quarterfinal slots as 'E = 1 v W(R1)' and the semifinal "
            "pairing W(E)vW(H), W(F)vW(G), but never states which first-round winner fills "
            "which slot. Fixed-bracket and reseeding both satisfy every recorded constraint "
            "including integrity item P-3."
        ),
        required_to_clear="Ruling selecting FIXED_BRACKET_MAPPING or RESEED_BY_ORIGINAL_SEED.",
        governance_group=GROUP_BRACKET,
    ),
    BlockerDisposition(
        blocker_id="governance.A8_ECL_FINAL_BOARD_TIEBREAK_ORDERING_NOT_EXPLICIT",
        disposition="HUMAN_RULING_REQUIRED",
        evidence=(
            "TB-ECL/A8 resolves tied A8/ECL standings races via the FINAL committee board, "
            "while the board's ordering key includes conference_champion and CG-8 routes the "
            "G5 auto-bid through champion status. The cycle is structural; it binds only when "
            "a race survives TB-1 and TB-2."
        ),
        required_to_clear="Ruling selecting a deterministic ordering that breaks the cycle.",
        governance_group=GROUP_A8_ECL,
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
