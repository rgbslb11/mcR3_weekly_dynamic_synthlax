"""Performance against common opponents (COMMITTEE-TB2 / A8-ECL-TB2).

Ruling R2-COMMON-OPP reuses the approved SOS shape, restricted to the opponents
two teams have in common::

    COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common

This is "performance against common opponents **based on strength**". The prior
ad hoc reading — multiplying an opponent strength by a 1/0 result — is not used;
no governed source requires it.

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
from .rulings import R2_COMMON_OPPONENTS
from .sos import (
    OOWP_WEIGHT,
    OWP_WEIGHT,
    WP_WEIGHT,
    ResumeLedger,
    SosSemantics,
    win_pct,
)


@dataclass(frozen=True)
class CommonOpponentResult:
    team: str
    other: str
    common_opponents: tuple[str, ...]
    wins: int
    losses: int
    wp_common: float
    owp_common: float
    oowp_common: float
    score: float

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
        }


def common_opponents(ledger: ResumeLedger, team: str, other: str) -> tuple[str, ...]:
    a = {r.opponent for r in ledger.games_for(team)}
    b = {r.opponent for r in ledger.games_for(other)}
    return tuple(sorted((a & b) - {team, other}))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


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
    wp_common = wins / played if played else 0.0

    exclude = team if semantics.exclude_rated_team_from_owp else None
    owp_common = _mean([win_pct(ledger, r.opponent, excluding_opponent=exclude) for r in instances])

    oowp_values: list[float] = []
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
            _mean([win_pct(ledger, o, excluding_opponent=inner_exclude) for o in opp_opponents])
        )
    oowp_common = _mean(oowp_values)

    score = WP_WEIGHT * wp_common + OWP_WEIGHT * owp_common + OOWP_WEIGHT * oowp_common
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
