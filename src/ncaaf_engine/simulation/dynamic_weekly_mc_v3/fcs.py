"""Governed treatment of schedule-only FCS opponents for V3.

Ruling R2-FCS-ELO-1250 fixes the FCS treatment at **Elo 1250**. That closes two
questions and deliberately leaves a third open:

closed
    Whether the POWER_CRUNCH source may be used at all. The Build Manifest
    records ``Model use authorized: FALSE``; the ruling supersedes that for V3.
    The manifest itself is not edited.
closed
    What value FCS opponents carry. A fixed Elo, with no toggle and no schedule
    of future changes.
open — but not a policy question
    The FCS *rating policy* is settled and is not reopened here. What is missing
    is a **model-scale adapter**: the V3 simulation layer rates teams in unified
    neutral points (observed FBS range roughly -17.5 to +32.9), the ruling fixes
    an Elo, and no mounted register bridges the two axes.

    The bridge is genuinely required, not hypothetical. All 13 schedule-only FCS
    entities carry ``preseason_strength_points = None``, they appear in 15
    regular-season games across weeks 2, 3, 4, 5 and 12, and
    ``engine._initialize_states`` raises on the first of them today.

    The bridge V2.1 used is precisely the route now closed. Its Methodology sheet
    (``V2_1_STATIC_CONTROL…xlsx!Methodology!A8``) records: "13 schedule-only
    opponents use the canonical R-FCS-RATING-01 operator composite *translated
    from Board I-H equivalent to unified points*." That is the Board equivalent,
    and ruling R2-FCS-ELO-1250 forbids using it as a conversion rule.

    So the gap is surfaced as one narrow **model-scale / calibration** blocker.
    The FCS rating policy itself is not in question.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import GovernanceBlock
from .rulings import R2_FCS

#: FACT — ruling R2-FCS-ELO-1250.
FCS_FIXED_ELO = 1250.0

#: The governed policy token written into the V3 configuration.
FCS_FIXED_ELO_POLICY = "FIXED_ELO_1250"

#: Values that have been proposed as FCS conversion routes and are refused.
#: Recorded so a reviewer can see they were considered and rejected, not missed.
FORBIDDEN_BOARD_EQUIVALENTS = (0.294, 0.297, 0.297514)

#: FACT — POWER_CRUNCH Build Manifest. Present so the refusal can name it.
POWER_CRUNCH_ELO_BOARD_SLOPE = 999.986237
POWER_CRUNCH_ELO_BOARD_INTERCEPT = 1099.999878

#: Blocker for the one thing the ruling does not settle. Namespaced
#: ``model_scale.`` rather than ``governance.`` so it cannot be read as
#: reopening the FCS rating policy: the policy is settled, the adapter is missing.
FCS_UNIFIED_SCALE_BLOCKER = "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER"

#: The rating policy is closed. Recorded so the two are never conflated.
FCS_RATING_POLICY_RESOLVED = True

#: FACT — V2_1_STATIC_CONTROL…xlsx!Methodology!A8. The adapter V2.1 used, now closed.
V2_1_FCS_BRIDGE = (
    "13 schedule-only opponents use the canonical R-FCS-RATING-01 operator composite "
    "translated from Board I-H equivalent to unified points."
)


@dataclass(frozen=True)
class FcsPolicy:
    policy: str
    fixed_elo: float
    layer: str = "ELO"
    #: No governed Elo -> unified-neutral-points mapping exists. Never guessed.
    unified_points_equivalent: float | None = None
    model_use_authorized_by_ruling: bool = True
    requires_future_toggle: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "ruling": R2_FCS.convergence_id,
            "policy": self.policy,
            "fixed_elo": self.fixed_elo,
            "layer": self.layer,
            "unified_points_equivalent": self.unified_points_equivalent,
            "model_use_authorized_by_ruling": self.model_use_authorized_by_ruling,
            "requires_future_toggle": self.requires_future_toggle,
            "rating_policy_resolved": FCS_RATING_POLICY_RESOLVED,
            "model_scale_adapter_blocker": FCS_UNIFIED_SCALE_BLOCKER,
            "superseded_v2_1_bridge": V2_1_FCS_BRIDGE,
            "supersedes": list(R2_FCS.supersedes),
        }


GOVERNED_FCS_POLICY = FcsPolicy(policy=FCS_FIXED_ELO_POLICY, fixed_elo=FCS_FIXED_ELO)


def require_governed_fcs_policy(policy: str | None) -> FcsPolicy:
    """Fail closed unless the configured FCS policy is the ruled fixed-Elo policy."""
    if policy is None or policy == "":
        raise GovernanceBlock(
            "FCS treatment is not configured. Ruling "
            f"{R2_FCS.convergence_id} sets it to {FCS_FIXED_ELO_POLICY} (Elo {FCS_FIXED_ELO})."
        )
    if policy != FCS_FIXED_ELO_POLICY:
        raise GovernanceBlock(
            f"Unknown FCS policy {policy!r}; the governed policy is {FCS_FIXED_ELO_POLICY} "
            f"(ruling {R2_FCS.convergence_id})."
        )
    return GOVERNED_FCS_POLICY


def reject_board_derived_conversion(candidate: float) -> None:
    """Refuse any attempt to convert FCS through a Board equivalent.

    The Board-equivalent figures are *recorded not issued*; inverting the
    Elo/Board transform manufactures a rule no source ever issued.
    """
    if round(float(candidate), 6) in {round(v, 6) for v in FORBIDDEN_BOARD_EQUIVALENTS}:
        raise GovernanceBlock(
            f"Board equivalent {candidate} may not be used as an FCS conversion rule. "
            "The POWER_CRUNCH Build Manifest records the Board equivalent as "
            "'recorded not issued', and inverting the Elo/Board transform is an ad hoc "
            f"conversion (ruling {R2_FCS.convergence_id})."
        )


def invert_board_transform(_elo: float) -> float:
    """Never implemented. Present so the refusal is explicit rather than absent."""
    raise GovernanceBlock(
        "Inverting the POWER_CRUNCH Elo/Board transform "
        f"(primary_elo = {POWER_CRUNCH_ELO_BOARD_SLOPE} * board_power_H + "
        f"{POWER_CRUNCH_ELO_BOARD_INTERCEPT}) to manufacture an FCS translation is "
        f"forbidden by ruling {R2_FCS.convergence_id}."
    )


def require_fcs_unified_points(policy: FcsPolicy | None = None) -> float:
    """Fail closed on the one FCS question the ruling does not answer.

    V3 rates teams in unified neutral points. Ruling R2-FCS-ELO-1250 fixes an
    Elo, and no governed register maps that Elo onto the points axis.
    """
    active = policy or GOVERNED_FCS_POLICY
    if active.unified_points_equivalent is None:
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: the FCS rating policy is settled — ruling "
            f"{R2_FCS.convergence_id} fixes FCS at Elo {active.fixed_elo} and that is not "
            "reopened. What is missing is a model-scale adapter onto the unified "
            "neutral-points axis the V3 engine rates on. V2.1 bridged this through the "
            "Board I-H equivalent, which the same ruling forbids. Issue an explicit "
            "Elo-to-points scale rule; do not invert the Elo/Board transform."
        )
    return active.unified_points_equivalent
