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

The bare-float callable boundary
--------------------------------
:class:`SorReferenceElo` performs those refusals at construction, but
:func:`p_reference_at_least_w` is a public callable that also accepts a plain
number. A caller reaching it directly would otherwise skip the dataclass
entirely and compute against whatever float it was handed. Both routes now run
:func:`check_r_ref_value`, so the refusals are properties of the boundary rather
than of one convenient wrapper, and the governed 1893.3 passes through both
unchanged.

What *is* governed, and what is not
-----------------------------------
The 2026 reference Elo **is governed**: ``CCG-R_REF`` = 1893.3, LOCKED and
SOURCE-VERIFIED in ``02_PARAMETER_REGISTER!E25``, noted "SOR reference Elo". The
earlier 1901 is its superseded predecessor, not an alternative:
``20_CANON_MANIFEST_INGEST!C15`` records the artifact carrying it as SUPERSEDED
with "R_ref 1901 now stale ... Retain for audit; do not use for decisions", and
the change log at ``B24`` records "R_ref 1901->1893.3" under ruling R-MC-V2 on
2026-07-14. Both 1901 and the stale library default 1684.9 are refused by name.

Two SOR-B questions *do* remain unratified and are narrower than the reference
Elo: the **P-to-strength transform** and the **reference HFA**. ``compute_sor_b.py``
is not mounted here, so neither can be verified; both are stamped on every row.

``16_REJECTED_ITEMS`` REJ-012 requires the Monte Carlo and SOR-report domains stay
separate. One ratified value serves both, tagged by namespace, and neither may
write the other.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_SOR

#: FACT — the stale library default named in ruling R2-SOR-REPORT. Refused.
STALE_COMPUTE_SOR_B_DEFAULT_R_REF = 1684.9

#: FACT — the governed 2026 SOR reference Elo.
#:
#: Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER!E25, parameter
#: CCG-R_REF, current_value 1893.3, status LOCKED, validation SOURCE-VERIFIED,
#: note "SOR reference Elo (unchanged)". Confirmed in
#: 11_VALIDATION_REGISTER!D15 ("8000 / 20260714 / 0.85 / 68 / 65 / 1893.3").
#:
#: This value is *not* missing governance. It is the ratified successor to 1901.
GOVERNED_2026_SOR_R_REF = 1893.3
GOVERNED_2026_SOR_R_REF_PARAMETER_ID = "CCG-R_REF"
GOVERNED_2026_SOR_R_REF_AUTHORITY = (
    "Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER!E25 (CCG-R_REF, LOCKED, "
    "SOURCE-VERIFIED); ruling R-MC-V2"
)

#: FACT — the superseded predecessor, refused by name.
#:
#: 20_CANON_MANIFEST_INGEST!C15: "2026_HARDENED_Canonical_Run.xlsx | SUPERSEDED |
#: ... R_ref 1901 now stale" superseded "by 2026_Board_I-H_v2 +
#: 2026_HARDENED_Run_v2_IH (R-MC-V2)", disposition "ACCEPT AS SUPERSEDED HISTORY",
#: note "Retain for audit; do not use for decisions."
#: 20_CANON_MANIFEST_INGEST!B24 change log: "2026-07-14: ... R_ref 1901->1893.3".
SUPERSEDED_2026_SOR_R_REF = 1901.0
SUPERSEDED_2026_SOR_R_REF_SUPERSEDED_BY = "R-MC-V2 (2026-07-14): R_ref 1901 -> 1893.3"

#: Alias retained for the MC/CCG chain. Same registered parameter; the SOR report
#: and the Monte Carlo consume it in separate namespaces and neither writes the other.
MC_DOMAIN_R_REF = GOVERNED_2026_SOR_R_REF
MC_DOMAIN_R_REF_PARAMETER_ID = GOVERNED_2026_SOR_R_REF_PARAMETER_ID

#: Ratification items that remain genuinely open for SOR-B, distinct from R_ref.
#: ``compute_sor_b.py`` is not mounted in this repository, so neither can be
#: verified here and both are stamped on every row rather than assumed.
UNRATIFIED_SOR_B_ITEMS = (
    "P_TO_STRENGTH_TRANSFORM",
    "REFERENCE_HFA",
)

#: The SOR report is not a governed committee input.
REPORT_STATUS_RESEARCH = "RESEARCH_REPORT_ONLY"

#: Namespaces that must not be conflated.
SOR_REPORT_NAMESPACE = "SOR_B_REPORT"
MC_NAMESPACE = "MONTE_CARLO_CCG"

#: Absolute window used when matching a value against a refused reference Elo.
#:
#: Deliberately inclusive rather than exact. A refusal that only fired on ``==``
#: would let a rounded, reparsed or unit-shifted copy of a stale number through,
#: and the failure direction of a wider window is to refuse a value nobody
#: governs anyway. The governed 1893.3 sits 7.7 Elo points from the nearer
#: refused constant (1901.0), so a window this small cannot reach it.
REFUSED_R_REF_TOLERANCE = 1e-6


def _matches_refused_r_ref(value: float, refused: float) -> bool:
    return abs(value - refused) <= REFUSED_R_REF_TOLERANCE


def check_r_ref_value(value: object, *, where: str = "SOR reference Elo") -> float:
    """Refuse an ungoverned reference Elo at a bare-float callable boundary.

    The single place the refusals live. :class:`SorReferenceElo` calls it at
    construction and :func:`p_reference_at_least_w` calls it on a bare argument,
    so neither route can refuse less than the other.

    Returns the value as a ``float``; the governed
    :data:`GOVERNED_2026_SOR_R_REF` passes through unchanged.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputValidationError(
            f"{where} must be a real number; got {value!r}"
        )
    numeric = float(value)
    if not math.isfinite(numeric):
        raise InputValidationError(
            f"{where} must be finite; got {value!r}. A non-finite reference Elo "
            "would propagate silently through the Poisson-binomial into a "
            "published row."
        )
    if _matches_refused_r_ref(numeric, STALE_COMPUTE_SOR_B_DEFAULT_R_REF):
        raise GovernanceBlock(
            f"R_ref {value} is the stale compute_sor_b.py default. Ruling "
            f"{R2_SOR.convergence_id} forbids it silently controlling a weekly run; "
            f"the governed 2026 value is {GOVERNED_2026_SOR_R_REF}."
        )
    if _matches_refused_r_ref(numeric, SUPERSEDED_2026_SOR_R_REF):
        raise GovernanceBlock(
            f"R_ref {value} is superseded. {SUPERSEDED_2026_SOR_R_REF_SUPERSEDED_BY}; "
            "20_CANON_MANIFEST_INGEST records the artifact carrying it as SUPERSEDED "
            f"HISTORY, \"do not use for decisions\". Use {GOVERNED_2026_SOR_R_REF}."
        )
    return numeric


@dataclass(frozen=True)
class SorReferenceElo:
    """An explicitly authorised reference Elo, with the namespace it belongs to."""

    value: float
    parameter_id: str
    authority: str
    source_artifact: str
    namespace: str = SOR_REPORT_NAMESPACE

    def __post_init__(self) -> None:
        # Same boundary check the bare-float callables run, so constructing the
        # dataclass and calling straight into the Poisson-binomial refuse the
        # same set of values. The normalised float is written back so the
        # annotation is honest about what downstream arithmetic receives.
        object.__setattr__(self, "value", check_r_ref_value(self.value))
        if not self.authority or not self.parameter_id:
            raise InputValidationError("SOR reference Elo requires a parameter_id and an authority")


def governed_2026_sor_reference_elo() -> SorReferenceElo:
    """The governed 2026 SOR season reference Elo, in the SOR-report namespace.

    Read from the ratified parameter register rather than from a library default.
    It must still be passed explicitly, so a weekly run always records which
    reference it used.
    """
    return SorReferenceElo(
        value=GOVERNED_2026_SOR_R_REF,
        parameter_id=GOVERNED_2026_SOR_R_REF_PARAMETER_ID,
        authority=GOVERNED_2026_SOR_R_REF_AUTHORITY,
        source_artifact="Model_Parameters_v2_5_APPROVED.xlsx",
        namespace=SOR_REPORT_NAMESPACE,
    )


def mc_domain_reference_elo() -> SorReferenceElo:
    """The same registered parameter, tagged to the Monte Carlo namespace.

    One ratified value, two consumers. Tagging keeps REJ-012's "keep domains
    separate" enforceable: neither namespace may write the other.
    """
    return SorReferenceElo(
        value=MC_DOMAIN_R_REF,
        parameter_id=MC_DOMAIN_R_REF_PARAMETER_ID,
        authority=GOVERNED_2026_SOR_R_REF_AUTHORITY,
        source_artifact="Model_Parameters_v2_5_APPROVED.xlsx",
        namespace=MC_NAMESPACE,
    )


def require_sor_reference_elo(reference: SorReferenceElo | None) -> SorReferenceElo:
    if reference is None:
        raise GovernanceBlock(
            f"Weekly SOR report requires an explicit season R_ref (ruling "
            f"{R2_SOR.convergence_id}). The governed 2026 value is "
            f"{GOVERNED_2026_SOR_R_REF} ({GOVERNED_2026_SOR_R_REF_PARAMETER_ID}); the "
            f"compute_sor_b.py default {STALE_COMPUTE_SOR_B_DEFAULT_R_REF} is stale and "
            "must never silently control a run."
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


def p_reference_at_least_w(
    r_ref: SorReferenceElo | float,
    opponents: Sequence[SorOpponent],
    wins: int,
) -> float:
    """Poisson-binomial P(reference team wins >= ``wins`` of this same schedule).

    ``r_ref`` may be an authorised :class:`SorReferenceElo` or a bare number.
    Either way it crosses :func:`check_r_ref_value` first: this is a public
    callable, and reaching it directly must not be a way around the refusals
    :class:`SorReferenceElo` applies. The arithmetic below is unchanged.
    """
    if isinstance(r_ref, SorReferenceElo):
        reference_elo = r_ref.value
    else:
        reference_elo = check_r_ref_value(
            r_ref, where="p_reference_at_least_w() R_ref"
        )
    if wins < 0 or wins > len(opponents):
        raise InputValidationError(
            f"wins={wins} is outside 0..{len(opponents)} for this schedule"
        )
    for opponent in opponents:
        if isinstance(opponent.rating_elo, bool) or not isinstance(
            opponent.rating_elo, (int, float)
        ):
            raise InputValidationError(
                f"Opponent {opponent.schedule_id!r} carries a non-numeric rating_elo "
                f"{opponent.rating_elo!r}"
            )
        if not math.isfinite(float(opponent.rating_elo)):
            raise InputValidationError(
                f"Opponent {opponent.schedule_id!r} carries a non-finite rating_elo "
                f"{opponent.rating_elo!r}; it would propagate into the published row."
            )
    dist = [1.0]
    for opponent in opponents:
        p = _reference_win_probability(reference_elo, opponent.rating_elo)
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
    p = p_reference_at_least_w(ref, opponents, wins)
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
            # R_ref is governed and is NOT listed here. What remains unratified
            # for SOR-B is narrower than the reference Elo and is named exactly.
            "unratified_sor_b_items": list(UNRATIFIED_SOR_B_ITEMS),
            "unresolved_assumptions": list(unresolved_assumptions) + [
                "P_TO_STRENGTH_TRANSFORM: compute_sor_b.py is not mounted, so the mapping "
                "from reference win probability to a strength/resume scalar is unverified here",
                "REFERENCE_HFA: whether and how home-field advantage enters the reference "
                "team's per-game expectation is not recorded in any mounted artifact",
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
