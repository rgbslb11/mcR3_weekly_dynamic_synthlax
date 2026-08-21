"""Performance against common opponents (COMMITTEE-TB2 / A8-ECL-TB2).

Ruling R2-COMMON-OPP reuses the approved SOS shape, restricted to the opponents
two teams have in common::

    COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common

This is "performance against common opponents **based on strength**". The prior
ad hoc reading — multiplying an opponent strength by a 1/0 result — is not used;
no governed source requires it.

What ruling R3-SOS-OWP-OOWP-SEMANTICS did and did not change
------------------------------------------------------------
R3 governs the **denominator and exclusion semantics** of WP/OWP/OOWP, and those
now apply here: instance weighting, the opponent-versus-evaluated-team
exclusion, and UNAVAILABLE propagation all flow through from :mod:`sos`.

R3 did **not** govern the common-opponent *formula*. The 0.25 / 0.50 / 0.25
shape below rests on the R2 convergence ruling R2-COMMON-OPP, whose nearest
repository evidence — ``18_ACC_POLICY_REFERENCE`` ACC-EXT-08 — records the
common-opponent question as OPEN / REQUIRES RULING rather than stating a
formula. So the settled conceptual rule remains "performance against common
opponents based on strength", and this module records itself as
:data:`COMMON_OPPONENT_FORMULA_STATUS` rather than claiming canonical authority
it does not have. A result-weighted alternative is equally unpromoted; neither
is silently adopted on the strength of the R3 ruling.

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

from dataclasses import dataclass

from .errors import InputValidationError
from .rulings import R2_COMMON_OPPONENTS, R3_SOS_SEMANTICS
from .sos import (
    OOWP_WEIGHT,
    OWP_WEIGHT,
    UNAVAILABLE,
    WP_WEIGHT,
    ResumeLedger,
    SosSemantics,
    _mean_or_unavailable,
    _unavailable,
    win_pct,
)

#: The exact common-opponent formula is NOT canonically governed. It is carried
#: forward from convergence ruling R2-COMMON-OPP; no mounted artifact states it.
COMMON_OPPONENT_FORMULA_AUTHORITY = R2_COMMON_OPPONENTS.convergence_id
COMMON_OPPONENT_FORMULA_IS_CANONICAL = False
COMMON_OPPONENT_FORMULA_STATUS = (
    "CONVERGENCE_RULING_ONLY — the 0.25/0.50/0.25 common-opponent shape is not "
    "stated by any mounted artifact. Ruling R3-SOS-OWP-OOWP-SEMANTICS governs the "
    "OWP/OOWP denominator semantics applied here and did not govern this formula."
)

#: The alternative that is equally unpromoted. Named so neither can drift in.
UNPROMOTED_COMMON_OPPONENT_ALTERNATIVES = (
    "RESULT_WEIGHTED_OPPONENT_STRENGTH (opponent strength multiplied by a 1/0 result)",
)


@dataclass(frozen=True)
class CommonOpponentResult:
    team: str
    other: str
    common_opponents: tuple[str, ...]
    wins: int
    losses: int
    wp_common: float | None
    owp_common: float | None
    oowp_common: float | None
    score: float | None

    def as_dict(self) -> dict[str, object]:
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
            "formula_authority": COMMON_OPPONENT_FORMULA_AUTHORITY,
            "formula_is_canonical": COMMON_OPPONENT_FORMULA_IS_CANONICAL,
            "semantics_ruling": R3_SOS_SEMANTICS.convergence_id,
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
    )


def compare_common_opponents(
    ledger: ResumeLedger, team: str, other: str, semantics: SosSemantics
) -> tuple[CommonOpponentResult, CommonOpponentResult]:
    """Both sides of one comparison, computed against the same shared opponent set."""
    return (
        common_opponent_score(ledger, team, other, semantics),
        common_opponent_score(ledger, other, team, semantics),
    )
