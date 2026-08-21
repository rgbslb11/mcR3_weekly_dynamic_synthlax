"""Weekly SOR report — a resume metric, and an output, never committee input.

Ruling R2-SOR-REPORT asks for a weekly SOR report on the SOR-B / record-strength
methodology, answering one question and only that one:

    How unlikely is it that a fixed elite-reference team would match this team's
    record against this same schedule?

SOR is not committee SOS (ruling R2-SOS), not SRS, not the Baxter Rating and not
Colley. Blending them is exactly the unadopted BWI proposal recorded in
``18_ACC_POLICY_REFERENCE`` ACC-EXT-12, and this module refuses to be part of one.

The stale reference-Elo hazard
------------------------------
``compute_sor_b.py`` carries a default ``R_ref=1684.9``. That default is stale
and is not mounted in this repository at all, so a weekly run that silently
inherited it would be computing against a number nobody governs. Every entry
point here requires an explicit :class:`SorReferenceElo` carrying its own
authority, and the stale value is refused by name.

The MC-domain reference Elo (``CCG-R_REF`` = 1893.3, LOCKED, paired with
kappa 0.85 and sigma 68) lives in a **separate namespace**. ``16_REJECTED_ITEMS``
REJ-012 says so in as many words: "Keep domains separate." It may be passed in
explicitly, with provenance, but it is never substituted by default and the
report never writes back into the MC parameter.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_SOR

#: FACT — the stale library default named in ruling R2-SOR-REPORT. Refused.
STALE_COMPUTE_SOR_B_DEFAULT_R_REF = 1684.9

#: FACT — 02_PARAMETER_REGISTER CCG-R_REF, LOCKED, "SOR reference Elo".
#: MC/CCG domain. Available for explicit use; never a default.
MC_DOMAIN_R_REF = 1893.3
MC_DOMAIN_R_REF_PARAMETER_ID = "CCG-R_REF"

#: The SOR report is not a governed committee input.
REPORT_STATUS_RESEARCH = "RESEARCH_REPORT_ONLY"

#: Namespaces that must not be conflated.
SOR_REPORT_NAMESPACE = "SOR_B_REPORT"
MC_NAMESPACE = "MONTE_CARLO_CCG"


@dataclass(frozen=True)
class SorReferenceElo:
    """An explicitly authorised reference Elo, with the namespace it belongs to."""

    value: float
    parameter_id: str
    authority: str
    source_artifact: str
    namespace: str = SOR_REPORT_NAMESPACE

    def __post_init__(self) -> None:
        if self.value == STALE_COMPUTE_SOR_B_DEFAULT_R_REF:
            raise GovernanceBlock(
                f"R_ref {self.value} is the stale compute_sor_b.py default. Ruling "
                f"{R2_SOR.convergence_id} forbids it silently controlling a weekly run; "
                "supply an explicit governed season reference Elo."
            )
        if not self.authority or not self.parameter_id:
            raise InputValidationError("SOR reference Elo requires a parameter_id and an authority")


def mc_domain_reference_elo() -> SorReferenceElo:
    """The MC-domain reference Elo, exposed read-only in its own namespace.

    Passing this into a SOR report is a deliberate, recorded act. It does not
    make the report canonical and it never writes back to the MC parameter.
    """
    return SorReferenceElo(
        value=MC_DOMAIN_R_REF,
        parameter_id=MC_DOMAIN_R_REF_PARAMETER_ID,
        authority="Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER (LOCKED)",
        source_artifact="Model_Parameters_v2_5_APPROVED.xlsx",
        namespace=MC_NAMESPACE,
    )


def require_sor_reference_elo(reference: SorReferenceElo | None) -> SorReferenceElo:
    if reference is None:
        raise GovernanceBlock(
            f"Weekly SOR report requires an explicit governed season R_ref (ruling "
            f"{R2_SOR.convergence_id}). The compute_sor_b.py default "
            f"{STALE_COMPUTE_SOR_B_DEFAULT_R_REF} is stale and must never silently control a run."
        )
    return reference


def reject_mc_r_ref_overwrite(target_namespace: str, source: SorReferenceElo) -> None:
    """Refuse writing a SOR-report reference Elo into the MC parameter namespace."""
    if target_namespace == MC_NAMESPACE and source.namespace != MC_NAMESPACE:
        raise GovernanceBlock(
            f"Refusing to write SOR-report reference Elo {source.value} into the "
            f"{MC_NAMESPACE} namespace. REJ-012: keep domains separate."
        )


@dataclass(frozen=True)
class SorOpponent:
    schedule_id: str
    rating_elo: float
    #: True when the rated team won this game.
    won: bool
    neutral_site: bool = False
    home: bool = True


def _reference_win_probability(r_ref: float, opponent_elo: float) -> float:
    """Logistic Elo expectation for the reference team against one opponent."""
    return 1.0 / (1.0 + 10.0 ** ((opponent_elo - r_ref) / 400.0))


def p_reference_at_least_w(r_ref: float, opponents: Sequence[SorOpponent], wins: int) -> float:
    """Poisson-binomial P(reference team wins >= ``wins`` of this same schedule)."""
    if wins < 0 or wins > len(opponents):
        raise InputValidationError(
            f"wins={wins} is outside 0..{len(opponents)} for this schedule"
        )
    dist = [1.0]
    for opponent in opponents:
        p = _reference_win_probability(r_ref, opponent.rating_elo)
        nxt = [0.0] * (len(dist) + 1)
        for k, mass in enumerate(dist):
            nxt[k] += mass * (1.0 - p)
            nxt[k + 1] += mass * p
        dist = nxt
    return sum(dist[wins:])


@dataclass(frozen=True)
class WeeklySorRow:
    week: int
    as_of: str
    team: str
    wins: int
    losses: int
    opponents_counted: int
    p_ref_ge_w: float
    raw_sor: float
    normalized_sor: float
    r_ref: float
    r_ref_parameter_id: str
    r_ref_namespace: str
    source_hashes: dict[str, str]
    model: str
    model_version: str
    configuration_version: str
    observed_at: str
    recorded_at: str
    report_status: str = REPORT_STATUS_RESEARCH
    provenance: dict[str, object] = field(default_factory=dict)
    is_committee_input: bool = False

    def as_dict(self) -> dict[str, object]:
        return {
            "week": self.week,
            "as_of": self.as_of,
            "team": self.team,
            "wins": self.wins,
            "losses": self.losses,
            "opponents_counted": self.opponents_counted,
            "p_ref_ge_w": self.p_ref_ge_w,
            "raw_sor": self.raw_sor,
            "normalized_sor": self.normalized_sor,
            "r_ref": self.r_ref,
            "r_ref_parameter_id": self.r_ref_parameter_id,
            "r_ref_namespace": self.r_ref_namespace,
            "source_hashes": dict(self.source_hashes),
            "model": self.model,
            "model_version": self.model_version,
            "configuration_version": self.configuration_version,
            "observed_at": self.observed_at,
            "recorded_at": self.recorded_at,
            "report_status": self.report_status,
            "provenance": dict(self.provenance),
            "is_committee_input": self.is_committee_input,
        }


def weekly_sor_row(
    *,
    week: int,
    as_of: str,
    team: str,
    opponents: Sequence[SorOpponent],
    reference: SorReferenceElo | None,
    source_hashes: dict[str, str],
    model: str,
    model_version: str,
    configuration_version: str,
    observed_at: str,
    recorded_at: str,
    unresolved_assumptions: Sequence[str] = (),
) -> WeeklySorRow:
    """One team's weekly SOR row, stamped REPORT_ONLY with its assumptions."""
    ref = require_sor_reference_elo(reference)
    if not opponents:
        raise InputValidationError(f"{team} has no counted opponents for week {week}")
    wins = sum(1 for o in opponents if o.won)
    losses = len(opponents) - wins
    p = p_reference_at_least_w(ref.value, opponents, wins)
    raw = -math.log(p) if p > 0 else float("inf")
    return WeeklySorRow(
        week=week,
        as_of=as_of,
        team=team,
        wins=wins,
        losses=losses,
        opponents_counted=len(opponents),
        p_ref_ge_w=p,
        raw_sor=raw,
        normalized_sor=1.0 - p,
        r_ref=ref.value,
        r_ref_parameter_id=ref.parameter_id,
        r_ref_namespace=ref.namespace,
        source_hashes=dict(source_hashes),
        model=model,
        model_version=model_version,
        configuration_version=configuration_version,
        observed_at=observed_at,
        recorded_at=recorded_at,
        provenance={
            "ruling": R2_SOR.convergence_id,
            "methodology": "SOR-B / record strength (Poisson-binomial vs fixed reference Elo)",
            "question": (
                "How unlikely is it that a fixed elite-reference team would match this "
                "team's record against the same schedule?"
            ),
            "r_ref_authority": ref.authority,
            "r_ref_source_artifact": ref.source_artifact,
            # The Poisson-binomial reference probability is the governed part
            # (20_CANON_MANIFEST_INGEST records "Poisson-binomial SOR"). The two
            # scalar presentations below are report conventions chosen here, not
            # governed transforms, and are labelled so no reader mistakes them.
            "raw_sor_transform": "-ln(p_ref_ge_w) — REPORT CONVENTION, not a governed transform",
            "normalized_sor_transform": "1 - p_ref_ge_w — REPORT CONVENTION, not a governed transform",
            "unresolved_assumptions": list(unresolved_assumptions) + [
                "compute_sor_b.py is not mounted in this repository; the SOR-B "
                "transform and its HFA treatment are unverified here",
                "raw/normalized SOR presentation is a report convention, not a governed transform",
            ],
            "not_committee_sos": True,
            "not_srs": True,
            "not_baxter_rating": True,
            "not_colley": True,
        },
    )


def reject_sor_as_committee_sos(metric_name: str) -> None:
    if metric_name.upper() in {"SOS", "COMMITTEE_SOS", "STRENGTH_OF_SCHEDULE"}:
        raise GovernanceBlock(
            "SOR is a resume output and may not be used as committee SOS "
            f"(rulings {R2_SOR.convergence_id} and R2-SOS)."
        )
