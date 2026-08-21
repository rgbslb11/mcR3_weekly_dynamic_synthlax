"""Performance against common opponents (COMMITTEE-TB2 / A8-ECL-TB2).

Ruling R2-COMMON-OPP reuses the approved SOS shape, restricted to the opponents
two teams have in common::

    COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common

This is "performance against common opponents **based on strength**". The prior
ad hoc reading — multiplying an opponent strength by a 1/0 result — is not used;
no governed source requires it.

Two layers, governed separately
-------------------------------
**Layer A — the formula.** Ruling R4-COMMON-OPP-FORMULA is direct Chairman
authority and approves the exact shape above. The three weights are the governed
rule itself, not a production parameter: 0.20/0.60/0.20, 0.25/0.25/0.50 and
every other weighting are refused for governed use, and the result-weighted
alternative stays unpromoted.

**Layer B — the denominators.** Ruling R3-SOS-OWP-OOWP-SEMANTICS governs the
denominator and exclusion semantics of WP/OWP/OOWP, and those apply here:
instance weighting, the opponent-versus-evaluated-team exclusion, and
UNAVAILABLE propagation all flow through from :mod:`sos`. R4 does not reopen or
alter any of it. The two layers are asserted separately — a governed formula
over ungoverned semantics fails closed, and so does governed semantics under an
ungoverned formula.

Succession, not rewriting
-------------------------
``18_ACC_POLICY_REFERENCE`` ACC-EXT-08 records the common-opponent question as
OPEN / REQUIRES RULING, and convergence ruling R2-COMMON-OPP carried the shape
forward before any direct approval existed. Both predate R4 and are preserved
unedited as evidence of the prior state; neither is authority against the later
ruling. :data:`PRE_RULING_COMMON_OPPONENT_FORMULA` keeps that prior state
constructible so a test can prove it cannot promote itself.

Nothing inspects a boolean and hopes
------------------------------------
:func:`require_governed_common_opponent_formula` is the affirmative gate. It
checks the formula's status, its authority source, its exact weights, that the
weights this module actually applies still match them, that the bound semantics
are the governed ones, and that UNAVAILABLE stays fail-closed. Governed use goes
through :func:`governed_common_opponent_score`, never around it.

Serialization may not claim what the gate did not grant
-------------------------------------------------------
:func:`common_opponent_score` is deliberately ungated, so pre-ruling and
alternative semantics stay testable. Its results therefore carry no formula
authority, and :meth:`CommonOpponentResult.as_dict` must not stamp one on them:
a row that was never gated reports ``governed: False`` and leaves every
``formula_*`` claim ``None``. Only the governed entry points attach the formula
the gate actually authorised, and only such a row may serialize the R4
authority. The arithmetic is identical on both paths — the difference is
entirely in what the row is allowed to say about itself.

Why the exclusion rule carries the whole comparison
---------------------------------------------------
The Chairman's example is two 11-1 teams that are each 2-1 against the same
three opponents. Their common-opponent *records* are identical, and so is the
opponent set, so ``WP_common`` alone can never separate them. What separates
them is how those three opponents fared once the rated team's own result is
removed from their records: beating a team drops that team's WP for you and
raises it for the other. That is precisely the semantics question
:mod:`sos` refuses to invent, and it is why this module takes an explicit
:class:`~.sos.SosSemantics` rather than assuming one.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .errors import GovernanceBlock, InputValidationError
from .rulings import (
    R2_COMMON_OPPONENTS,
    R3_SOS_SEMANTICS,
    R4_COMMON_OPPONENT_FORMULA,
)
from .sos import (
    OOWP_WEIGHT,
    OWP_WEIGHT,
    UNAVAILABLE,
    WP_WEIGHT,
    ResumeLedger,
    SosSemantics,
    _mean_or_unavailable,
    _unavailable,
    governed_sos_semantics,
    require_governed_sos_semantics,
    win_pct,
)

#: FACT — ruling R4-COMMON-OPP-FORMULA approved the exact formula directly, so it
#: is governed. The three weights below are the rule, not a tunable parameter.
COMMON_OPPONENT_FORMULA_AUTHORITY = R4_COMMON_OPPONENT_FORMULA.convergence_id
COMMON_OPPONENT_FORMULA_IS_CANONICAL = True
COMMON_OPPONENT_FORMULA_RESOLUTION_REASON = "DIRECT_CHAIRMAN_AUTHORITY"
COMMON_OPPONENT_FORMULA_STATUS = (
    "GOVERNED — COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + "
    "0.25 * OOWP_common, approved directly by the Chairman under ruling "
    f"{R4_COMMON_OPPONENT_FORMULA.convergence_id}. Ruling "
    f"{R3_SOS_SEMANTICS.convergence_id} separately governs the OWP/OOWP "
    "denominator semantics applied underneath it."
)

#: The status this module carried *before* the direct ruling. Preserved verbatim
#: so the succession is readable and the prior state is not rewritten away.
COMMON_OPPONENT_FORMULA_PRIOR_STATUS = (
    "CONVERGENCE_RULING_ONLY — the 0.25/0.50/0.25 common-opponent shape is not "
    "stated by any mounted artifact. Ruling R3-SOS-OWP-OOWP-SEMANTICS governs the "
    "OWP/OOWP denominator semantics applied here and did not govern this formula."
)

#: Historical evidence of the pre-ruling state. Preserved, never edited, and
#: never authority against the later direct ruling.
HISTORICAL_PRE_RULING_EVIDENCE = (
    "Model_Parameters_v2_5_APPROVED.xlsx!18_ACC_POLICY_REFERENCE ACC-EXT-08 — "
    "common-opponent question recorded OPEN / REQUIRES RULING (pre-ruling).",
    f"Convergence ruling {R2_COMMON_OPPONENTS.convergence_id} — carried the shape "
    "forward before any direct approval existed (pre-ruling).",
)

#: The alternative that stays unpromoted. Named so it cannot drift in.
UNPROMOTED_COMMON_OPPONENT_ALTERNATIVES = (
    "RESULT_WEIGHTED_OPPONENT_STRENGTH (opponent strength multiplied by a 1/0 result)",
)

#: Weightings that must never be substituted for the governed ones.
REFUSED_COMMON_OPPONENT_WEIGHTINGS = (
    (0.20, 0.60, 0.20),
    (0.25, 0.25, 0.50),
    (0.50, 0.25, 0.25),
    (1.0, 0.0, 0.0),
)

#: Statuses that are explicitly not governance. None of them can self-promote.
NON_GOVERNING_FORMULA_STATUSES = (
    "TEST_FIXTURE",
    "PROPOSAL",
    "PROPOSED",
    "OPEN",
    "UNRESOLVED",
    "HISTORICAL_PRE_RULING",
    "CONVERGENCE_RULING_ONLY",
    "RESEARCH",
    "ASSUMED",
    "",
)

#: The only resolution reasons that establish governed formula authority.
GOVERNING_RESOLUTION_REASONS = (
    "DIRECT_CHAIRMAN_AUTHORITY",
    "SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY",
)

#: What a serialized result is allowed to say about how it was produced.
GOVERNED_RESULT_PROVENANCE = (
    "GOVERNED — produced through require_governed_common_opponent_formula(): the "
    f"{R4_COMMON_OPPONENT_FORMULA.convergence_id} formula authority and the "
    f"{R3_SOS_SEMANTICS.convergence_id} denominator semantics were both verified "
    "before anything was computed."
)
UNGATED_RESULT_PROVENANCE = (
    "UNGATED_HELPER_RESULT — produced by common_opponent_score() without passing "
    "require_governed_common_opponent_formula(). The arithmetic is the same, but "
    "no formula authority was established and the OWP/OOWP semantics were not "
    "verified as the governed ones. This row claims no governance."
)


@dataclass(frozen=True)
class CommonOpponentFormula:
    """The common-opponent scoring formula, with the authority that binds it.

    The weights travel with the authority deliberately. A caller cannot hand the
    governed authority a different weighting, and cannot hand the governed
    weighting a different authority — :func:`require_governed_common_opponent_formula`
    refuses both.
    """

    formula_id: str
    authority: str
    status: str
    wp_weight: float
    owp_weight: float
    oowp_weight: float
    resolution_reason: str | None = None

    @property
    def weights(self) -> tuple[float, float, float]:
        return (self.wp_weight, self.owp_weight, self.oowp_weight)

    def as_dict(self) -> dict[str, object]:
        return {
            "formula_id": self.formula_id,
            "authority": self.authority,
            "status": self.status,
            "resolution_reason": self.resolution_reason,
            "wp_weight": self.wp_weight,
            "owp_weight": self.owp_weight,
            "oowp_weight": self.oowp_weight,
        }


#: FACT — the exact weights ruling R4-COMMON-OPP-FORMULA approved.
GOVERNED_COMMON_OPPONENT_WEIGHTS: tuple[float, float, float] = (0.25, 0.50, 0.25)

GOVERNED_COMMON_OPPONENT_FORMULA = CommonOpponentFormula(
    formula_id=R4_COMMON_OPPONENT_FORMULA.convergence_id,
    authority=(
        "Direct Chairman authority, ruling "
        f"{R4_COMMON_OPPONENT_FORMULA.convergence_id} "
        f"({R4_COMMON_OPPONENT_FORMULA.instruction})"
    ),
    status="GOVERNED",
    wp_weight=0.25,
    owp_weight=0.50,
    oowp_weight=0.25,
    resolution_reason=COMMON_OPPONENT_FORMULA_RESOLUTION_REASON,
)

#: The pre-ruling state, kept constructible so a test can prove that carrying the
#: right numbers is not the same thing as carrying authority for them.
PRE_RULING_COMMON_OPPONENT_FORMULA = CommonOpponentFormula(
    formula_id=R2_COMMON_OPPONENTS.convergence_id,
    authority=(
        f"Convergence ruling {R2_COMMON_OPPONENTS.convergence_id}, recorded before "
        "the direct Chairman approval of the exact formula"
    ),
    status="CONVERGENCE_RULING_ONLY",
    wp_weight=0.25,
    owp_weight=0.50,
    oowp_weight=0.25,
    resolution_reason=None,
)


@dataclass(frozen=True)
class CommonOpponentResult:
    """One scored comparison, plus an honest record of how it was produced.

    The two provenance fields are not inputs to the arithmetic. They exist so a
    serialized row cannot claim authority the gate never granted: an ungated
    helper result reports the semantics it happened to be handed and nothing
    more, while a gated result carries the formula the gate returned.
    """

    team: str
    other: str
    common_opponents: tuple[str, ...]
    wins: int
    losses: int
    wp_common: float | None
    owp_common: float | None
    oowp_common: float | None
    score: float | None
    #: The id of the semantics actually applied. A statement of what was used,
    #: not a claim that it was verified — an impostor carrying the governed id
    #: reports that id here and is still ``governed: False``.
    semantics_id: str | None = None
    #: The formula the gate authorised. ``None`` means no gate ran, and no
    #: formula authority may be serialized for this row.
    governed_formula: CommonOpponentFormula | None = None

    @property
    def is_governed(self) -> bool:
        """True only for results issued through the governed entry points."""
        return self.governed_formula is not None

    def as_dict(self) -> dict[str, object]:
        governed = self.is_governed
        formula = self.governed_formula
        return {
            "ruling": R2_COMMON_OPPONENTS.convergence_id,
            "team": self.team,
            "compared_with": self.other,
            "common_opponents": list(self.common_opponents),
            "wins": self.wins,
            "losses": self.losses,
            "wp_common": self.wp_common,
            "owp_common": self.owp_common,
            "oowp_common": self.oowp_common,
            "common_opponent_score": self.score,
            # --- provenance. Every claim below is conditioned on the gate. ---
            "governed": governed,
            "provenance": (
                GOVERNED_RESULT_PROVENANCE if governed else UNGATED_RESULT_PROVENANCE
            ),
            "formula_authority": formula.formula_id if governed else None,
            "formula_authority_source": formula.authority if governed else None,
            "formula_is_canonical": (
                COMMON_OPPONENT_FORMULA_IS_CANONICAL if governed else None
            ),
            "formula_resolution_reason": (
                formula.resolution_reason if governed else None
            ),
            "formula_weights": list(formula.weights) if governed else None,
            # A fact about the code path either way: these are the weights the
            # arithmetic above applied. Carrying the governed values does not
            # make an ungated row governed, which is why it is a separate key.
            "weights_applied": list(_weights_applied()),
            "semantics_ruling": self.semantics_id,
            "semantics_are_governed": governed,
            "unavailable_components": sorted(
                name
                for name, value in (
                    ("wp_common", self.wp_common),
                    ("owp_common", self.owp_common),
                    ("oowp_common", self.oowp_common),
                )
                if value is None
            ),
        }


def common_opponents(ledger: ResumeLedger, team: str, other: str) -> tuple[str, ...]:
    a = {r.opponent for r in ledger.games_for(team)}
    b = {r.opponent for r in ledger.games_for(other)}
    return tuple(sorted((a & b) - {team, other}))


def common_opponent_score(
    ledger: ResumeLedger, team: str, other: str, semantics: SosSemantics
) -> CommonOpponentResult:
    """Score one team's performance against the opponents it shares with another."""
    if team == other:
        raise InputValidationError("Common-opponent comparison requires two distinct teams")
    shared = common_opponents(ledger, team, other)

    instances = [r for r in ledger.games_for(team) if r.opponent in shared]
    if semantics.instance_weighting == "PER_OPPONENT":
        seen: set[str] = set()
        deduped = []
        for r in sorted(instances, key=lambda x: (x.opponent, x.game_id)):
            if r.opponent not in seen:
                seen.add(r.opponent)
                deduped.append(r)
        instances = deduped
    elif semantics.instance_weighting != "PER_GAME":
        raise InputValidationError(f"Unknown instance weighting {semantics.instance_weighting!r}")

    wins = sum(1 for r in instances if r.won)
    losses = sum(1 for r in instances if not r.won)
    played = wins + losses
    if played:
        wp_common: float | None = wins / played
    else:
        wp_common = UNAVAILABLE if _unavailable(semantics) else 0.0

    exclude = team if semantics.exclude_rated_team_from_owp else None
    owp_common = _mean_or_unavailable(
        [
            win_pct(ledger, r.opponent, excluding_opponent=exclude, semantics=semantics)
            for r in instances
        ],
        semantics,
    )

    oowp_values: list[float | None] = []
    for r in instances:
        opp = r.opponent
        opp_opponents = [x.opponent for x in ledger.games_for(opp)]
        if semantics.instance_weighting == "PER_OPPONENT":
            opp_opponents = sorted(set(opp_opponents))
        else:
            opp_opponents = sorted(opp_opponents)
        if semantics.exclude_rated_team_from_oowp:
            opp_opponents = [o for o in opp_opponents if o != team]
        inner_exclude = opp if semantics.exclude_rated_team_from_owp else None
        oowp_values.append(
            _mean_or_unavailable(
                [
                    win_pct(ledger, o, excluding_opponent=inner_exclude, semantics=semantics)
                    for o in opp_opponents
                ],
                semantics,
            )
        )
    oowp_common = _mean_or_unavailable(oowp_values, semantics)

    # The weighting is R2-COMMON-OPP's and is deliberately unchanged. Only the
    # denominator semantics underneath it come from the R3 ruling.
    if _unavailable(semantics) and (
        wp_common is None or owp_common is None or oowp_common is None
    ):
        score: float | None = UNAVAILABLE
    else:
        score = (
            WP_WEIGHT * float(wp_common or 0.0)
            + OWP_WEIGHT * float(owp_common or 0.0)
            + OOWP_WEIGHT * float(oowp_common or 0.0)
        )
    return CommonOpponentResult(
        team=team,
        other=other,
        common_opponents=shared,
        wins=wins,
        losses=losses,
        wp_common=wp_common,
        owp_common=owp_common,
        oowp_common=oowp_common,
        score=score,
        # What was used, recorded as such. No formula authority is attached:
        # this helper is ungated and has none to give.
        semantics_id=semantics.semantics_id,
        governed_formula=None,
    )


def compare_common_opponents(
    ledger: ResumeLedger, team: str, other: str, semantics: SosSemantics
) -> tuple[CommonOpponentResult, CommonOpponentResult]:
    """Both sides of one comparison, computed against the same shared opponent set."""
    return (
        common_opponent_score(ledger, team, other, semantics),
        common_opponent_score(ledger, other, team, semantics),
    )


def _issue_governed(
    result: CommonOpponentResult, formula: CommonOpponentFormula
) -> CommonOpponentResult:
    """Attach the gate-authorised formula to a result the gate just produced.

    The only way ``governed_formula`` is ever set. Nothing is recomputed and no
    component value is touched — this stamps provenance onto arithmetic that
    already happened, under semantics the gate verified first.
    """
    return replace(result, governed_formula=formula)


def _weights_applied() -> tuple[float, float, float]:
    """The weights this module actually applies, read back from the code path.

    Kept separate from the formula record on purpose: the gate compares the two,
    so a drifted constant fails closed instead of silently rescoring.
    """
    return (WP_WEIGHT, OWP_WEIGHT, OOWP_WEIGHT)


def require_governed_common_opponent_formula(
    formula: CommonOpponentFormula | None,
    semantics: SosSemantics | None,
) -> tuple[CommonOpponentFormula, SosSemantics]:
    """Affirmatively authorise one governed common-opponent evaluation.

    Both layers are checked, and they are checked independently:

    * **Layer A — formula.** Status is GOVERNED, the authority source is the
      direct Chairman ruling (or a successor to it), and the weights are exactly
      0.25 / 0.50 / 0.25. TEST_FIXTURE, PROPOSAL, OPEN, UNRESOLVED and
      pre-ruling historical evidence cannot promote themselves, whatever numbers
      they carry.
    * **Layer B — denominators.** The semantics are the governed
      R3-SOS-OWP-OOWP-SEMANTICS ones, and their zero-observation policy is still
      UNAVAILABLE so the fail-closed behaviour survives.

    Returns the authorised pair so a caller cannot claim to have gated without
    using what the gate handed back.
    """
    if formula is None:
        raise GovernanceBlock(
            "Common-opponent formula authority is required for governed use. "
            f"Ruling {R4_COMMON_OPPONENT_FORMULA.convergence_id} governs "
            "COMMON_OPP_SCORE = 0.25*WP_common + 0.50*OWP_common + 0.25*OOWP_common."
        )

    status = formula.status.strip().upper()
    if status != "GOVERNED":
        raise GovernanceBlock(
            f"Common-opponent formula {formula.formula_id!r} carries status "
            f"{formula.status!r}, which is not a governed source. "
            f"Ruling {R4_COMMON_OPPONENT_FORMULA.convergence_id} is the authority; "
            "test fixtures, proposals and pre-ruling historical evidence cannot "
            "promote themselves."
        )
    if status in NON_GOVERNING_FORMULA_STATUSES:  # pragma: no cover - defensive
        raise GovernanceBlock(
            f"Status {formula.status!r} is listed as non-governing and cannot be GOVERNED."
        )

    reason = (formula.resolution_reason or "").strip().upper()
    if reason not in GOVERNING_RESOLUTION_REASONS:
        raise GovernanceBlock(
            f"Common-opponent formula {formula.formula_id!r} names resolution reason "
            f"{formula.resolution_reason!r}. Governed use requires direct Chairman "
            f"authority — one of {list(GOVERNING_RESOLUTION_REASONS)}."
        )
    if not formula.authority.strip():
        raise GovernanceBlock(
            f"Common-opponent formula {formula.formula_id!r} names no authority source."
        )

    if formula.weights != GOVERNED_COMMON_OPPONENT_WEIGHTS:
        raise GovernanceBlock(
            f"Common-opponent weights {formula.weights} are not the governed formula. "
            f"Ruling {R4_COMMON_OPPONENT_FORMULA.convergence_id} binds exactly "
            f"{GOVERNED_COMMON_OPPONENT_WEIGHTS} (WP_common / OWP_common / OOWP_common); "
            "no other weighting may be substituted."
        )
    if _weights_applied() != GOVERNED_COMMON_OPPONENT_WEIGHTS:
        raise GovernanceBlock(
            f"Applied common-opponent weights {_weights_applied()} have drifted from the "
            f"governed {GOVERNED_COMMON_OPPONENT_WEIGHTS} under ruling "
            f"{R4_COMMON_OPPONENT_FORMULA.convergence_id}."
        )

    # Layer B. The denominator semantics are governed separately and are not
    # reopened here; they are only required to be the governed ones.
    checked = require_governed_sos_semantics(semantics)
    if checked.semantics_id != R3_SOS_SEMANTICS.convergence_id:
        raise GovernanceBlock(
            f"Common-opponent scoring requires the governed OWP/OOWP semantics "
            f"{R3_SOS_SEMANTICS.convergence_id}; got {checked.semantics_id!r}."
        )
    expected = governed_sos_semantics(checked.schedule_only_fcs_ids)
    if checked != expected:
        raise GovernanceBlock(
            f"OWP/OOWP semantics {checked.semantics_id!r} do not match ruling "
            f"{R3_SOS_SEMANTICS.convergence_id}: {checked.as_dict()} != {expected.as_dict()}."
        )
    if checked.zero_qualifying_games != "UNAVAILABLE":
        raise GovernanceBlock(
            "Governed common-opponent scoring requires UNAVAILABLE to stay fail-closed; "
            f"zero_qualifying_games is {checked.zero_qualifying_games!r}."
        )
    return formula, checked


def governed_common_opponent_score(
    ledger: ResumeLedger,
    team: str,
    other: str,
    semantics: SosSemantics | None = None,
    formula: CommonOpponentFormula | None = GOVERNED_COMMON_OPPONENT_FORMULA,
) -> CommonOpponentResult:
    """One governed common-opponent score, gated before anything is computed.

    This is the entry point governed use must take. :func:`common_opponent_score`
    stays ungated so pre-ruling and alternative semantics remain testable; it
    carries no authority on its own.
    """
    authorised, checked = require_governed_common_opponent_formula(formula, semantics)
    return _issue_governed(
        common_opponent_score(ledger, team, other, checked), authorised
    )


def governed_compare_common_opponents(
    ledger: ResumeLedger,
    team: str,
    other: str,
    semantics: SosSemantics | None = None,
    formula: CommonOpponentFormula | None = GOVERNED_COMMON_OPPONENT_FORMULA,
) -> tuple[CommonOpponentResult, CommonOpponentResult]:
    """Both sides of one governed comparison, over the same shared opponent set."""
    authorised, checked = require_governed_common_opponent_formula(formula, semantics)
    return tuple(  # type: ignore[return-value]
        _issue_governed(result, authorised)
        for result in compare_common_opponents(ledger, team, other, checked)
    )
