"""Home-field advantage parameters for Dynamic Weekly MC V3.

Three HFA-shaped values exist in the governed registers and they are *different
parameters*, not competing values of one parameter. Collapsing them is the
mistake the master parameter register warns against in as many words:

    "Legacy drive-engine HFA; do not conflate with schedule HFA or Elo HFA"
    -- Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER ENG-HOME-FIELD

Ruling R2-HFA-3P5 sets the V3 *football-point* baseline to 3.5. It says nothing
about the Elo-layer parameter, and it does not edit the legacy value: 4.0 stays
recorded exactly as the registers record it, HISTORICAL and NOT CURRENT.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import GovernanceBlock
from .rulings import R2_HFA

#: FACT — SCHED-HFA-BASE, status LOCKED, validation SOURCE-VERIFIED.
#: Ruling R2-HFA-3P5 adopts this as the V3 football-point baseline.
V3_FOOTBALL_POINT_HFA = 3.5

#: FACT — ENG-HOME-FIELD, current_value 4, status HISTORICAL,
#: implementation_status "conflicts with current HFA families",
#: validation_status "NOT CURRENT". Preserved, never applied by V3.
LEGACY_V2_DRIVE_ENGINE_HFA = 4.0
LEGACY_V2_DRIVE_ENGINE_HFA_STATUS = "HISTORICAL"
LEGACY_V2_DRIVE_ENGINE_HFA_VALIDATION = "NOT CURRENT"

#: FACT — CCG-HFA_ELO, LOCKED under R-CCG-06 / DEF-CCG-6. A separate Elo-layer
#: parameter in a separate namespace. R2-HFA-3P5 does not touch it.
CCG_ELO_HFA = 65.0


@dataclass(frozen=True)
class HfaParameter:
    parameter_id: str
    value: float
    layer: str
    status: str
    governed_for_v3: bool
    note: str


HFA_REGISTER: tuple[HfaParameter, ...] = (
    HfaParameter(
        parameter_id="SCHED-HFA-BASE",
        value=V3_FOOTBALL_POINT_HFA,
        layer="FOOTBALL_POINTS",
        status="LOCKED",
        governed_for_v3=True,
        note="V3 football-point HFA baseline adopted by ruling R2-HFA-3P5.",
    ),
    HfaParameter(
        parameter_id="ENG-HOME-FIELD",
        value=LEGACY_V2_DRIVE_ENGINE_HFA,
        layer="FOOTBALL_POINTS",
        status=LEGACY_V2_DRIVE_ENGINE_HFA_STATUS,
        governed_for_v3=False,
        note=(
            "Legacy V2 drive-engine constant, VERIFIED in ENGINE_PARAMS and HISTORICAL / "
            "NOT CURRENT in the master parameter register. Preserved unedited."
        ),
    ),
    HfaParameter(
        parameter_id="CCG-HFA_ELO",
        value=CCG_ELO_HFA,
        layer="ELO",
        status="LOCKED",
        governed_for_v3=True,
        note="Elo-layer home-field advantage. A separate parameter; not a V3 point baseline.",
    ),
)


def governed_v3_football_point_hfa() -> float:
    """The one football-point HFA V3 is authorised to apply."""
    return V3_FOOTBALL_POINT_HFA


def require_governed_hfa(hfa_baseline_points: float | None) -> float:
    """Fail closed unless the configured football-point HFA is the ruled value.

    A configuration carrying the legacy 4.0 is rejected with a message that names
    why, rather than being silently accepted because it is a plausible number.
    """
    if hfa_baseline_points is None:
        raise GovernanceBlock(
            "V3 football-point HFA is not configured. Ruling "
            f"{R2_HFA.convergence_id} sets it to {V3_FOOTBALL_POINT_HFA}."
        )
    if hfa_baseline_points == LEGACY_V2_DRIVE_ENGINE_HFA:
        raise GovernanceBlock(
            f"Configured HFA {hfa_baseline_points} is the legacy ENG-HOME-FIELD value, recorded "
            f"{LEGACY_V2_DRIVE_ENGINE_HFA_STATUS} / {LEGACY_V2_DRIVE_ENGINE_HFA_VALIDATION}. "
            f"Ruling {R2_HFA.convergence_id} sets the V3 football-point baseline to "
            f"{V3_FOOTBALL_POINT_HFA}."
        )
    if hfa_baseline_points != V3_FOOTBALL_POINT_HFA:
        raise GovernanceBlock(
            f"Configured HFA {hfa_baseline_points} is not the governed V3 baseline "
            f"{V3_FOOTBALL_POINT_HFA} (ruling {R2_HFA.convergence_id})."
        )
    return hfa_baseline_points


def hfa_conflict_resolved(hfa_baseline_points: float | None) -> bool:
    """True when the 4.0-vs-3.5 conflict is closed by the ruled value being set."""
    return hfa_baseline_points == V3_FOOTBALL_POINT_HFA


def as_dict() -> dict[str, object]:
    return {
        "ruling": R2_HFA.convergence_id,
        "v3_football_point_hfa": V3_FOOTBALL_POINT_HFA,
        "legacy_v2_drive_engine_hfa": LEGACY_V2_DRIVE_ENGINE_HFA,
        "legacy_status": LEGACY_V2_DRIVE_ENGINE_HFA_STATUS,
        "legacy_validation_status": LEGACY_V2_DRIVE_ENGINE_HFA_VALIDATION,
        "elo_layer_hfa": CCG_ELO_HFA,
        "elo_layer_is_separate_parameter": True,
        "register": [
            {
                "parameter_id": p.parameter_id,
                "value": p.value,
                "layer": p.layer,
                "status": p.status,
                "governed_for_v3": p.governed_for_v3,
                "note": p.note,
            }
            for p in HFA_REGISTER
        ],
    }
