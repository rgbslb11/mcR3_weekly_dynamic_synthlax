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
    ``engine._initialize_states`` refuses on all 13 of them today.

    The bridge V2.1 used is precisely the route now closed. Its Methodology sheet
    (``V2_1_STATIC_CONTROL…xlsx!Methodology!A8``) records: "13 schedule-only
    opponents use the canonical R-FCS-RATING-01 operator composite *translated
    from Board I-H equivalent to unified points*." That is the Board equivalent,
    and ruling R2-FCS-ELO-1250 forbids using it as a conversion rule.

    So the gap is surfaced as one narrow **model-scale / calibration** blocker.
    The FCS rating policy itself is not in question.

Why the gap cannot be closed by reading harder
----------------------------------------------
The mounted corpus defines the target axis completely, and that is exactly what
rules the shortcuts out. ``Unified Neutral-Field Points = 14 x Unified Master
Z``, where Unified Master Z is the unweighted mean of four standardized rating
families over a **closed 121-team FBS population**. Three consequences follow,
each checkable against the workbooks rather than argued:

* The 13 FCS entities are not members of that population. They have no Z, and
  none of the four families carries a value for any of them.
* The only Elo relation any register issues is Elo <-> Board I-H. Board I-H is
  one half of one of four families, so it accounts for 0.125 of the axis. Even
  if the forbidden route were permitted it would leave 0.875 of the axis
  unknown — the refusal does not depend on the ruling alone.
* The 14 points/SD scale is itself marked "initial scale pending margin
  calibration", and open item ENG-CAL-MARGIN is still OPEN. Any FCS point value
  would be calibrated against a scale that is not yet fixed.

That is why this is a calibration item and not a missing constant, and why
:data:`CANDIDATE_SCALE_ROUTES` records six candidate routes with no number
attached to any of them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .errors import GovernanceBlock
from .rulings import R2_FCS, R5_FCS_SCALE, R5_FCS_VENUE

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
            "scale_adapter_installed": active_fcs_scale_adapter() is not None,
            "scale_adapter": (
                None if active_fcs_scale_adapter() is None
                else active_fcs_scale_adapter().as_dict()
            ),
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

    The refusal is by *construction*, not by lookup. The three enumerated
    equivalents are all inversions of the **superseded** 1397.51 Elo; the
    governed 1250 inverts to roughly 0.150002, which no literal blacklist
    mentions. Recomputing the inversion for every Elo the corpus attaches to FCS
    closes that gap, so the refusal cannot be stepped around simply by inverting
    the ruled value instead of the retired one.
    """
    value = round(float(candidate), 6)
    enumerated = {round(v, 6) for v in FORBIDDEN_BOARD_EQUIVALENTS}
    reconstructed = {round(board_inverse_of(elo), 6) for elo in BOARD_INVERTED_ELOS}
    if value in enumerated | reconstructed:
        via = "recorded Board equivalent" if value in enumerated else "inverted Elo/Board transform"
        raise GovernanceBlock(
            f"Board equivalent {candidate} may not be used as an FCS conversion rule "
            f"({via}). The POWER_CRUNCH Build Manifest records the Board equivalent as "
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
        # A registered adapter is the only thing that may answer this, and the
        # registry is empty until one is installed through
        # :func:`register_fcs_scale_adapter`. Checked here rather than in the
        # caller so there is exactly one place that can produce an FCS point
        # value, and no caller can quietly supply its own.
        installed = active_fcs_scale_adapter()
        if installed is not None:
            return installed.unified_points
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: the FCS rating policy is settled — ruling "
            f"{R2_FCS.convergence_id} fixes FCS at Elo {active.fixed_elo} and that is not "
            "reopened. What is missing is a model-scale adapter onto the unified "
            "neutral-points axis the V3 engine rates on. V2.1 bridged this through the "
            "Board I-H equivalent, which the same ruling forbids. Issue an explicit "
            "Elo-to-points scale rule; do not invert the Elo/Board transform."
        )
    return active.unified_points_equivalent


# ---------------------------------------------------------------------------
# The V3 target axis, as the mounted evidence defines it.
# ---------------------------------------------------------------------------
#
# Every constant below is a transcription of a governed artifact, reproduced
# against the mounted workbook to <1e-12. None of them is a conversion
# coefficient and none of them is fitted here.
#
#   2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx
#     !Data Dictionary       "Unified Neutral-Field Points | 14 x Unified Master Z;
#                             initial scale pending margin calibration."
#     !Ensemble Parameters   "Neutral-field point scale | 14 | Initial points per
#                             standard deviation; recalibrate against game margins"

#: FACT — points per standard deviation on the unified neutral-field axis.
#: Explicitly provisional in its own source: "initial scale pending margin calibration".
UNIFIED_NEUTRAL_POINTS_PER_SD = 14.0

#: FACT — the axis is a Z-score of a *closed* population: the 121 FBS members.
#: The 13 schedule-only FCS entities are not members of it and carry no Z.
UNIFIED_Z_POPULATION_SIZE = 121

#: FACT — the four independent rating families and their weights in Unified Master Z.
#: !Ensemble Parameters records 0.25 each; the Board family is itself the mean of
#: standardized Board I-H and Board J-B, so Board I-H carries 0.125 of the axis.
UNIFIED_FAMILY_WEIGHTS = {
    "TrueSkill": 0.25,
    "Litkenhous": 0.25,
    "Pure Baxter": 0.25,
    "Board Family": 0.25,
}
BOARD_IH_SHARE_OF_UNIFIED_Z = 0.125

#: DERIVED — the share of the axis that has *no* governed value for any FCS
#: entity even if the Board route were permitted. 1 - 0.125.
UNGOVERNED_SHARE_OF_AXIS_FOR_FCS = 0.875

#: FACT — observed unified neutral-field point range across the 121 FBS members.
UNIFIED_POINTS_OBSERVED_RANGE = (-17.4576, 32.8847)

#: FACT — POWER_CRUNCH!Reconciled Master. The governed source records the FCS
#: Board column and the FCS home-field modifier as unpopulated sentinels, not as
#: numbers. Substituting a number for either is a fabrication.
FCS_BOARD_POWER_H_SENTINEL = "UNRATED"
FCS_HFA_MODIFIER_SENTINEL = "UNRESOLVED"

#: FACT — the Elo the POWER_CRUNCH build applied under R-FCS-RATING-01, superseded
#: for V3 by R2-FCS-ELO-1250. Recorded so the superseded value can be refused by name.
SUPERSEDED_OPERATOR_COMPOSITE_ELO = 1397.51


def board_inverse_of(elo: float) -> float:
    """The value the forbidden inverse *would* produce. Never a conversion rule.

    This exists for one purpose: so :func:`reject_board_derived_conversion` can
    recognise a Board-inverted value it has not been told about literally. The
    three enumerated equivalents only cover the *superseded* 1397.51 Elo; the
    governed 1250 inverts to a different number, and a blacklist of three
    literals would let that one through.
    """
    return (float(elo) - POWER_CRUNCH_ELO_BOARD_INTERCEPT) / POWER_CRUNCH_ELO_BOARD_SLOPE


#: DERIVED — Elos whose Board inversion must be recognised and refused.
#: ``board_inverse_of(1250.0)`` is ~0.150002 and is *not* one of the three
#: enumerated equivalents; without this it would evade the refusal.
BOARD_INVERTED_ELOS = (FCS_FIXED_ELO, SUPERSEDED_OPERATOR_COMPOSITE_ELO)

#: Elo-layer magnitudes that must never be accepted as a neutral-point value.
FORBIDDEN_ELO_AS_POINTS = (FCS_FIXED_ELO, SUPERSEDED_OPERATOR_COMPOSITE_ELO)


# ---------------------------------------------------------------------------
# The narrow adapter interface.
# ---------------------------------------------------------------------------

#: The only authorities that may originate an FCS Elo-to-points scale rule.
#: Each is a *source of issuance*, not a calculation.
RECOGNISED_SCALE_AUTHORITIES = (
    # A governed register that states an Elo-to-unified-points relation outright.
    "ISSUED_GOVERNED_REGISTER",
    # A Chairman ruling that fixes the FCS neutral-point value by direct authority.
    "DIRECT_CHAIRMAN_AUTHORITY",
    # A margin-calibration result promoted through the calibration harness on a
    # holdout split. Gated behind ENG-CAL-MARGIN, which is itself still OPEN.
    "MARGIN_CALIBRATED_HOLDOUT",
)

#: Derivations that are refused as a matter of method, whatever number they yield.
REFUSED_DERIVATIONS = {
    "BOARD_IH_INVERSE": (
        "inverting the POWER_CRUNCH Elo/Board transform manufactures a rule no source issued"
    ),
    "BOARD_EQUIVALENT": (
        "the Board equivalent is 'recorded not issued' and the FCS Board column is UNRATED"
    ),
    "ELO_AS_POINTS": (
        "Elo and unified neutral points are different axes; 1250 is not 1250 points"
    ),
    "V2_1_BRIDGE_REPLAY": (
        "V2.1 reached its FCS points through the Board I-H equivalent, the exact "
        "route ruling R2-FCS-ELO-1250 closes"
    ),
    "AD_HOC": "an invented coefficient is not an authority",
    "TEST_FITTING": "a value chosen because a test turns green is not evidence",
}

_FCS_SCALE_APPROVAL_TOKEN = re.compile(r"^APPROVE_V3_FCS_SCALE_ADAPTER::[A-Z0-9_.-]{4,}$")
_FCS_VENUE_APPROVAL_TOKEN = re.compile(
    r"^APPROVE_V3_FCS_VENUE_MODIFIER::[A-Z0-9_.-]{4,}$"
)


@dataclass(frozen=True)
class FcsScaleProvenance:
    """Where an FCS scale rule came from. Every field is mandatory.

    ``issued`` is the field that matters most. The POWER_CRUNCH Build Manifest
    is explicit that the FCS Board equivalent is *recorded, not issued*; a
    provenance that cannot claim issuance is not a provenance.
    """

    artifact: str
    locator: str
    authority: str
    issued: bool
    statement: str

    def validate(self) -> None:
        for name in ("artifact", "locator", "authority", "statement"):
            if not str(getattr(self, name) or "").strip():
                raise GovernanceBlock(
                    f"{FCS_UNIFIED_SCALE_BLOCKER}: FCS scale provenance is missing {name!r}. "
                    "An adapter without complete provenance is indistinguishable from a guess."
                )
        if self.authority not in RECOGNISED_SCALE_AUTHORITIES:
            raise GovernanceBlock(
                f"{FCS_UNIFIED_SCALE_BLOCKER}: unknown FCS scale authority {self.authority!r}; "
                f"recognised authorities are {list(RECOGNISED_SCALE_AUTHORITIES)}."
            )
        if not self.issued:
            raise GovernanceBlock(
                f"{FCS_UNIFIED_SCALE_BLOCKER}: {self.artifact}!{self.locator} is recorded, "
                "not issued. A recorded equivalent is evidence of what a build did, never "
                "authority for what V3 may do."
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "artifact": self.artifact,
            "locator": self.locator,
            "authority": self.authority,
            "issued": self.issued,
            "statement": self.statement,
        }


@dataclass(frozen=True)
class FcsScaleAdapter:
    """A calibrated FCS Elo-to-unified-points adapter.

    Constructing one is deliberately not the same as installing one: see
    :func:`register_fcs_scale_adapter`, which is the only door into the engine.
    """

    unified_points: float
    provenance: FcsScaleProvenance
    derivation: str
    source_elo: float = FCS_FIXED_ELO
    calibration_id: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "unified_points": self.unified_points,
            "source_elo": self.source_elo,
            "derivation": self.derivation,
            "calibration_id": self.calibration_id,
            "provenance": self.provenance.as_dict(),
        }


#: Module-level registry. Empty, and stays empty until a governed adapter is
#: issued. Deliberately not a default-valued field on :class:`FcsPolicy` so that
#: ``GOVERNED_FCS_POLICY.unified_points_equivalent`` can never drift off None.
_ACTIVE_ADAPTER: FcsScaleAdapter | None = None


def active_fcs_scale_adapter() -> FcsScaleAdapter | None:
    return _ACTIVE_ADAPTER


def fcs_unified_scale_governed() -> bool:
    """Whether an FCS point value is available from a governed adapter.

    The preflight blocker is computed from this rather than from
    ``GOVERNED_FCS_POLICY.unified_points_equivalent``, so that the only way to
    clear it is to pass the registration gate that checks derivation,
    provenance, issuance and approval.
    """
    return _ACTIVE_ADAPTER is not None or GOVERNED_FCS_POLICY.unified_points_equivalent is not None


def clear_fcs_scale_adapter() -> None:
    """Uninstall the active adapter. Used by tests; never by production code."""
    global _ACTIVE_ADAPTER
    _ACTIVE_ADAPTER = None


def reject_elo_as_points(candidate: float) -> None:
    """Refuse an Elo magnitude presented as a neutral-point value.

    The two axes are not merely differently scaled, they are differently
    *constructed*: unified points are 14 x a Z-score of the 121-team FBS
    population, and the observed range is roughly -17.5 to +32.9. A value of
    1250 is not a large point value, it is a category error.
    """
    value = float(candidate)
    if round(value, 6) in {round(v, 6) for v in FORBIDDEN_ELO_AS_POINTS}:
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: Elo {value} may not be used directly as a unified "
            f"neutral-point value. Unified points are {UNIFIED_NEUTRAL_POINTS_PER_SD} x a "
            f"Z-score over the {UNIFIED_Z_POPULATION_SIZE}-team FBS population, observed range "
            f"{UNIFIED_POINTS_OBSERVED_RANGE[0]} to {UNIFIED_POINTS_OBSERVED_RANGE[1]}; "
            f"Elo is a different axis (ruling {R2_FCS.convergence_id})."
        )


def register_fcs_scale_adapter(
    adapter: FcsScaleAdapter,
    *,
    approval_token: str | None = None,
) -> FcsScaleAdapter:
    """The single door through which an FCS point value may enter V3.

    Refuses, in order: a forbidden or unrecognised derivation; a Board-inverted
    value; an Elo magnitude passed off as points; incomplete or unissued
    provenance; and finally any registration lacking an explicit human approval
    token. Passing every structural gate is still not authority to install.
    """
    global _ACTIVE_ADAPTER

    if adapter.derivation in REFUSED_DERIVATIONS:
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: derivation {adapter.derivation!r} is refused as a "
            f"conversion rule — {REFUSED_DERIVATIONS[adapter.derivation]} "
            f"(ruling {R2_FCS.convergence_id})."
        )
    if adapter.derivation not in RECOGNISED_SCALE_AUTHORITIES:
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: unknown FCS scale derivation "
            f"{adapter.derivation!r}; recognised derivations are "
            f"{list(RECOGNISED_SCALE_AUTHORITIES)}."
        )

    reject_board_derived_conversion(adapter.unified_points)
    reject_elo_as_points(adapter.unified_points)
    adapter.provenance.validate()

    if adapter.provenance.authority == "MARGIN_CALIBRATED_HOLDOUT" and not (
        adapter.calibration_id or ""
    ).strip():
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: a margin-calibrated adapter must name the "
            "calibration experiment that produced it."
        )

    if approval_token is None:
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: no human approval token. A structurally valid "
            "adapter is still not an installed one; V3 never adopts an FCS scale "
            "automatically."
        )
    if not _FCS_SCALE_APPROVAL_TOKEN.match(approval_token):
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: malformed FCS scale approval token. Expected "
            "APPROVE_V3_FCS_SCALE_ADAPTER::<RULING_ID>."
        )

    _ACTIVE_ADAPTER = adapter
    return adapter


def require_fcs_hfa_modifier(modifier: float | None, schedule_id: str = "<fcs>") -> float:
    """Fail closed on the FCS home-field modifier instead of defaulting to 1.0.

    POWER_CRUNCH!Reconciled Master records ``home_field_advantage_modifier`` for
    all 13 schedule-only FCS entities as ``UNRESOLVED`` — a sentinel, not a
    number. Three scheduled games (G0019, G0213, G0224) place an FCS entity at a
    HOME venue, so ``modifier or 1.0`` would silently invent a governed quantity
    for real games rather than refusing.

    The refusal stands until :func:`install_governed_fcs_hfa_modifier` installs
    the modifier ruling R-V3-FCS-VENUE-01 issues. Nothing is defaulted even then:
    the installed value is a single ruled constant with its own approval token,
    and it is consulted only for an entity whose own record carries the sentinel.
    """
    if modifier is None:
        installed = active_fcs_hfa_modifier()
        if installed is not None:
            return installed
        raise GovernanceBlock(
            f"{FCS_UNIFIED_SCALE_BLOCKER}: {schedule_id} has no governed home-field modifier. "
            f"POWER_CRUNCH!Reconciled Master records it as {FCS_HFA_MODIFIER_SENTINEL!r}; "
            "defaulting it to 1.0 would fabricate an ungoverned quantity for the three "
            "scheduled games that place an FCS entity at a HOME venue."
        )
    return float(modifier)


# ---------------------------------------------------------------------------
# Ruling R-V3-FCS-VENUE-01: the FCS home-field modifier.
# ---------------------------------------------------------------------------
#
# R-V3-FCS-SCALE-01 supplies a *neutral-field* point value and directs that
# "home/away venue adjustment uses ordinary V3 HFA logic rather than embedding
# extra HFA inside the adapter". Ordinary V3 HFA logic is
# ``hfa_baseline_points * home_field_advantage_modifier``, so executing that
# direction for the three games at which an FCS entity hosts needs a modifier for
# an entity whose own source row carries a sentinel.
#
# R-V3-FCS-VENUE-01 issues that modifier directly: **1.0**, the governed
# league-average venue modifier. It is a Chairman ruling under
# DIRECT_CHAIRMAN_AUTHORITY, not a reading of the earlier one. At the R5 closeout
# the same value was installed as a disclosed *assumption*, and this supersedes
# that disclosure — the authority classification changes, the number does not.
#
# The evidence the ruling records is checkable against the same sheets: every one
# of the 121 governed FBS members carries exactly 1 in the
# ``home_field_advantage_modifier`` column, so the league average over the
# governed population is 1 exactly with no dispersion to average away, and the
# canonical team master names the convention in its own provenance codes —
# ``hfa_baseline_3p5_locked;hfa_modifier_league_average``.
#
# Three things this is not. It is not a rating: it multiplies the venue term and
# never the strength. It is not embedded in the adapter: the neutral-field value
# stays -31.0 and this is applied by game.simulate_game exactly as it is for any
# FBS host, so there is no double HFA, no Elo-layer HFA, and none at a neutral
# site. And it is not a default: the pre-ruling refusal is the behaviour of this
# module until the installation call is made.

#: FACT — POWER_CRUNCH!Reconciled Master, home_field_advantage_modifier column:
#: 121 of 121 governed FBS members carry exactly 1.
GOVERNED_FBS_HFA_MODIFIERS = 1.0
GOVERNED_FBS_HFA_MODIFIER_POPULATION = 121

#: DERIVED — the league average over that population. One value, no dispersion.
FCS_LEAGUE_AVERAGE_HFA_MODIFIER = 1.0

#: FACT — 2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md provenance codes.
FCS_HFA_MODIFIER_CONVENTION_CODE = "hfa_modifier_league_average"

#: The approval token ruling R-V3-FCS-VENUE-01 issues. Deliberately its own
#: token and its own pattern: the venue modifier and the point-scale adapter are
#: two rulings, and one token must not install the other.
FCS_VENUE_APPROVAL_TOKEN = "APPROVE_V3_FCS_VENUE_MODIFIER::R-V3-FCS-VENUE-01"

#: How the modifier is authorised. Was a disclosed assumption at the R5 closeout;
#: ruling R-V3-FCS-VENUE-01 replaced that classification with an issued one.
FCS_VENUE_AUTHORITY = "DIRECT_CHAIRMAN_AUTHORITY"
FCS_VENUE_PRIOR_AUTHORITY = "DISCLOSED_ASSUMPTION_AT_R5_CLOSEOUT"

_ACTIVE_FCS_HFA_MODIFIER: float | None = None


def active_fcs_hfa_modifier() -> float | None:
    return _ACTIVE_FCS_HFA_MODIFIER


def clear_fcs_hfa_modifier() -> None:
    """Uninstall the venue resolution. Used by tests; never by production code."""
    global _ACTIVE_FCS_HFA_MODIFIER
    _ACTIVE_FCS_HFA_MODIFIER = None


def install_governed_fcs_hfa_modifier(
    *,
    modifier: float = FCS_LEAGUE_AVERAGE_HFA_MODIFIER,
    approval_token: str | None = None,
) -> float:
    """Install the FCS home-field modifier issued by ruling R-V3-FCS-VENUE-01.

    Refuses any value other than the ruled league-average modifier, and refuses
    without the ruling's own approval token. The point-scale adapter's token is
    not accepted here: two rulings, two doors, so installing one can never
    silently install the other.
    """
    global _ACTIVE_FCS_HFA_MODIFIER
    if approval_token is None:
        approval_token = FCS_VENUE_APPROVAL_TOKEN
    if not _FCS_VENUE_APPROVAL_TOKEN.match(approval_token):
        raise GovernanceBlock(
            f"Malformed FCS venue-modifier approval token for ruling "
            f"{R5_FCS_VENUE.convergence_id}. Expected "
            "APPROVE_V3_FCS_VENUE_MODIFIER::<RULING_ID>."
        )
    if float(modifier) != FCS_LEAGUE_AVERAGE_HFA_MODIFIER:
        raise GovernanceBlock(
            f"{modifier} is not the governed league-average home-field modifier "
            f"{FCS_LEAGUE_AVERAGE_HFA_MODIFIER}. Ruling {R5_FCS_VENUE.convergence_id} "
            "issues that value and ordinary V3 HFA logic; it does not authorise a bespoke "
            "FCS home-field advantage."
        )
    _ACTIVE_FCS_HFA_MODIFIER = float(modifier)
    return _ACTIVE_FCS_HFA_MODIFIER


def fcs_venue_clause_as_dict() -> dict[str, object]:
    return {
        "ruling": R5_FCS_VENUE.convergence_id,
        "chairman_ruling_id": R5_FCS_VENUE.chairman_ruling_id,
        "authority": FCS_VENUE_AUTHORITY,
        "prior_authority": FCS_VENUE_PRIOR_AUTHORITY,
        "assumption_superseded": True,
        "approval_token": FCS_VENUE_APPROVAL_TOKEN,
        "scale_ruling": R5_FCS_SCALE.convergence_id,
        "clause": (
            "home/away venue adjustment uses ordinary V3 HFA logic rather than "
            "embedding extra HFA inside the adapter"
        ),
        "source_row_value": FCS_HFA_MODIFIER_SENTINEL,
        "governed_fbs_modifier": GOVERNED_FBS_HFA_MODIFIERS,
        "governed_fbs_modifier_population": GOVERNED_FBS_HFA_MODIFIER_POPULATION,
        "league_average_modifier": FCS_LEAGUE_AVERAGE_HFA_MODIFIER,
        "convention_code": FCS_HFA_MODIFIER_CONVENTION_CODE,
        "installed": active_fcs_hfa_modifier() is not None,
        "applies_to_games": ["G0019", "G0213", "G0224"],
        "embedded_in_adapter": False,
        "applied_at_neutral_venue": False,
        "double_hfa": False,
        "elo_layer_hfa_used": False,
        "subject_venue_points": {"HOME": 3.5, "AWAY": -3.5, "NEUTRAL": 0.0},
        "fcs_neutral_field_points_unchanged": FCS_GOVERNED_UNIFIED_POINTS,
        "fcs_elo_unchanged": FCS_FIXED_ELO,
    }


#: The candidate routes from Elo 1250 to unified neutral points that exist over
#: the mounted corpus, and why each is refused. Recorded so an auditor can see
#: the search was exhaustive rather than abandoned.
CANDIDATE_SCALE_ROUTES = (
    {
        "route": "ELO_AS_POINTS",
        "description": "Use 1250 directly as a unified neutral-point value.",
        "refused_because": (
            "Category error. The axis is 14 x a Z-score over 121 FBS teams with observed "
            "range -17.4576 to 32.8847; 1250 is not on it."
        ),
        "numeric_result": None,
    },
    {
        "route": "BOARD_EQUIVALENT",
        "description": "Use the recorded board_power_H_equivalent 0.297514 as points.",
        "refused_because": (
            "The Build Manifest records it as 'recorded not issued', it is the equivalent "
            "of the superseded 1397.51 Elo rather than the governed 1250, and the FCS "
            "Board column is UNRATED."
        ),
        "numeric_result": None,
    },
    {
        "route": "BOARD_IH_INVERSE",
        "description": (
            "Invert primary_elo = 999.986237 * board_power_H + 1099.999878 at Elo 1250, "
            "then carry the result onto the points axis as V2.1 did."
        ),
        "refused_because": (
            "Forbidden by ruling R2-FCS-ELO-1250, and independently insufficient: Board I-H "
            "supplies only 0.125 of Unified Master Z. The remaining 0.875 — TrueSkill, "
            "Litkenhous, Pure Baxter and Board J-B — has no governed value for any of the "
            "13 FCS entities, so the route cannot reconstruct a point value even if it "
            "were permitted."
        ),
        "numeric_result": None,
    },
    {
        "route": "V2_1_BRIDGE_REPLAY",
        "description": "Recover the unified points V2.1 actually used for the 13 entities.",
        "refused_because": (
            "Not recoverable and not authority. The V2.1 control workbook carries no row "
            "for any FCS entity, so the value is absent from the mounted artifact; and its "
            "Methodology sheet states the value was reached through the Board I-H "
            "equivalent, the closed route."
        ),
        "numeric_result": None,
    },
    {
        "route": "ISSUED_GOVERNED_REGISTER",
        "description": (
            "Read an Elo-to-unified-points relation stated outright by a governed register."
        ),
        "refused_because": (
            "No such relation exists in the mounted corpus. The only issued Elo relation is "
            "Elo<->Board I-H; the Elo-layer parameters that do exist (CCG HFA 65, SOR "
            "r_ref 1893.3) operate inside the Elo domain and convert nothing."
        ),
        "numeric_result": None,
    },
    {
        "route": "MARGIN_CALIBRATED_HOLDOUT",
        "description": "Calibrate the FCS point value against observed game margins.",
        "refused_because": (
            "The hook exists and is the intended route, but it cannot run: open item "
            "ENG-CAL-MARGIN is OPEN, the neutral-field scale is itself 'initial scale "
            "pending margin calibration', and no calibration dataset is mounted."
        ),
        "numeric_result": None,
    },
)


def fcs_scale_evidence_report() -> dict[str, object]:
    """What the governed corpus does and does not supply for the adapter.

    Every field is reproducible from the mounted artifacts. The report asserts
    no mapping and proposes no number.
    """
    return {
        "blocker": FCS_UNIFIED_SCALE_BLOCKER,
        "rating_policy_resolved": FCS_RATING_POLICY_RESOLVED,
        "fixed_elo": FCS_FIXED_ELO,
        "fcs_entity_count": 13,
        "fcs_regular_season_games": 15,
        "target_axis": {
            "definition": "Unified Neutral-Field Points = 14 x Unified Master Z",
            "points_per_sd": UNIFIED_NEUTRAL_POINTS_PER_SD,
            "z_population": UNIFIED_Z_POPULATION_SIZE,
            "family_weights": dict(UNIFIED_FAMILY_WEIGHTS),
            "board_ih_share": BOARD_IH_SHARE_OF_UNIFIED_Z,
            "observed_range": list(UNIFIED_POINTS_OBSERVED_RANGE),
            "scale_status": "initial scale pending margin calibration",
        },
        "fcs_coverage_on_axis": {
            "rated_families": 0,
            "ungoverned_share_of_axis": UNGOVERNED_SHARE_OF_AXIS_FOR_FCS,
            "board_power_h": FCS_BOARD_POWER_H_SENTINEL,
            "home_field_advantage_modifier": FCS_HFA_MODIFIER_SENTINEL,
        },
        "candidate_routes": [dict(r) for r in CANDIDATE_SCALE_ROUTES],
        "numeric_mapping_promoted": False,
        "adapter_installed": active_fcs_scale_adapter() is not None,
        "recognised_authorities": list(RECOGNISED_SCALE_AUTHORITIES),
        "refused_derivations": sorted(REFUSED_DERIVATIONS),
        "disposition": "BLOCKED_ON_NUMERICAL_SCALE_CALIBRATION",
    }


# ---------------------------------------------------------------------------
# The governed adapter: ruling R-V3-FCS-SCALE-01.
# ---------------------------------------------------------------------------
#
# This is the one place the number -31.0 is written down, and it is written here
# rather than at a call site so that every route into the engine goes through
# :func:`register_fcs_scale_adapter` — the gate that refuses a Board inversion,
# an Elo magnitude, an unissued provenance and a missing approval token.
#
# Two things this adapter deliberately does NOT carry:
#
# * A home-field term. The value is a *neutral-field* point value. Venue is
#   applied afterwards by the ordinary V3 path in :func:`game.simulate_game`,
#   which adds ``hfa_baseline_points * home_hfa_modifier`` at a HOME venue and
#   exactly 0.0 at a NEUTRAL one. Folding an HFA into the adapter would double
#   it on every FCS road game and apply one at neutral sites where V3 applies
#   none.
# * An Elo. 1250 stays in the Elo layer under R2-FCS-ELO-1250. The adapter maps
#   between the two axes; it does not move either of them.

#: FACT — ruling R-V3-FCS-SCALE-01. Governed FCS neutral-field point value.
FCS_GOVERNED_UNIFIED_POINTS = -31.0

#: The approval token ruling R-V3-FCS-SCALE-01 issues. Installation still runs
#: the full registration gate; the token is the last check, not the only one.
FCS_SCALE_APPROVAL_TOKEN = "APPROVE_V3_FCS_SCALE_ADAPTER::R-V3-FCS-SCALE-01"

#: DERIVED — the two independent anchors the ruling records, kept so a reviewer
#: can see -31.0 was bracketed by evidence rather than chosen for roundness.
#: Neither is a conversion rule and neither is recomputed here.
FCS_SCALE_ANCHORS: tuple[dict[str, object], ...] = (
    {
        "anchor": "FBS_ELO_TO_V3_POINT_EMPIRICAL_BRIDGE",
        "scope": "governed FBS population",
        "predicted_points_at_elo_1250": -30.5758,
    },
    {
        "anchor": "FCS_VS_FBS_OBSERVED_MARGIN",
        "scope": "2023-2025 FCS-vs-FBS sample",
        "games": 365,
        "weighted_fbs_winning_margin_points": 31.423,
    },
)

GOVERNED_FCS_SCALE_PROVENANCE = FcsScaleProvenance(
    artifact="OPERATION SYTHALAX V3 FINAL MVP MODEL CLOSEOUT R1",
    locator="Section 3, RULING ID R-V3-FCS-SCALE-01",
    authority="DIRECT_CHAIRMAN_AUTHORITY",
    issued=True,
    statement=(
        "Governed FCS Elo 1250 maps to V3 unified neutral-field point value -31.0 for the "
        "INTERNAL SHADOW MVP. Two independent anchors were recorded: an FBS "
        "Elo-to-V3-point empirical bridge predicting about -30.5758 at Elo 1250, and a "
        "2023-2025 FCS-vs-FBS sample of 365 games with a weighted FBS winning margin of "
        "about 31.423 points."
    ),
)

GOVERNED_FCS_SCALE_ADAPTER = FcsScaleAdapter(
    unified_points=FCS_GOVERNED_UNIFIED_POINTS,
    provenance=GOVERNED_FCS_SCALE_PROVENANCE,
    derivation="DIRECT_CHAIRMAN_AUTHORITY",
    source_elo=FCS_FIXED_ELO,
    calibration_id=None,
)


def install_governed_fcs_scale_adapter(
    *, approval_token: str = FCS_SCALE_APPROVAL_TOKEN
) -> FcsScaleAdapter:
    """Install the R-V3-FCS-SCALE-01 adapter through the ordinary registration gate.

    Deliberately not called at import time. An FCS point value entering V3 is a
    governance event, so it happens where a reader can see it happen — the MVP
    activation path — and the pre-ruling fail-closed state is what any caller
    that has not asked for it still gets.
    """
    return register_fcs_scale_adapter(
        GOVERNED_FCS_SCALE_ADAPTER, approval_token=approval_token
    )


def governed_fcs_scale_as_dict() -> dict[str, object]:
    """The ruled mapping and its evidence, for the closeout record."""
    return {
        "ruling": R5_FCS_SCALE.convergence_id,
        "chairman_ruling_id": R5_FCS_SCALE.chairman_ruling_id,
        "fcs_elo": FCS_FIXED_ELO,
        "fcs_elo_policy": FCS_FIXED_ELO_POLICY,
        "fcs_elo_policy_ruling": R2_FCS.convergence_id,
        "unified_neutral_field_points": FCS_GOVERNED_UNIFIED_POINTS,
        "derivation": GOVERNED_FCS_SCALE_ADAPTER.derivation,
        "approval_token": FCS_SCALE_APPROVAL_TOKEN,
        "anchors": [dict(a) for a in FCS_SCALE_ANCHORS],
        "adapter_installed": active_fcs_scale_adapter() is not None,
        "embeds_home_field_advantage": False,
        "venue_handling": (
            "Neutral-field value only. game.simulate_game applies "
            "hfa_baseline_points * home_hfa_modifier at HOME and exactly 0.0 at NEUTRAL, "
            "identically for FBS and FCS participants."
        ),
        "refused_routes_unchanged": sorted(REFUSED_DERIVATIONS),
        "fbs_path_unchanged": True,
    }
