"""Committee strength of schedule for V3.

Ruling R2-SOS fixes one quantity, one direction, one definition::

    SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP

Higher is a harder schedule. There is no second SOS, no mean-opponent-Elo
variant, and no revival of ``schedule_path_score`` + ``resume_ceiling_index``
double counting (both RETIRED in the Bracket Regime Deferred Register; DEF-2
records ``sos_index`` as "REPORTED, never scored").

The weights are governed. The *semantics* underneath them are not
-------------------------------------------------------------------
Three questions decide what WP/OWP/OOWP actually mean, and the repository
answers none of them:

1. does OWP exclude the rated team's own games from each opponent's record?
2. is an opponent played twice weighted once or twice?
3. does OOWP exclude the rated team when averaging each opponent's OWP?

They are not cosmetic. On the Chairman's own common-opponent example the two
resumes are numerically identical under question 1 answered "no" and separate
cleanly under "yes". Inventing an answer would silently pick a committee, so
:func:`require_governed_sos_semantics` fails closed and the gap is surfaced as
exactly one blocker.

Every function here takes an explicit :class:`SosSemantics`. Tests supply a
fixture instance whose ``authority`` is not a governed source; the production
gate rejects exactly that.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .errors import GovernanceBlock, InputValidationError
from .rulings import R2_SOS

#: FACT — ruling R2-SOS.
WP_WEIGHT = 0.25
OWP_WEIGHT = 0.50
OOWP_WEIGHT = 0.25

SOS_SEMANTICS_BLOCKER = "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED"

InstanceWeighting = Literal["PER_GAME", "PER_OPPONENT"]


@dataclass(frozen=True)
class GameResult:
    """One completed game from the rated team's point of view."""

    game_id: str
    week: int
    team: str
    opponent: str
    won: bool


@dataclass(frozen=True)
class SosSemantics:
    """The denominator and exclusion rules the governed weights are applied to."""

    semantics_id: str
    authority: str
    #: Exclude the rated team's games against an opponent from that opponent's WP.
    exclude_rated_team_from_owp: bool
    #: Weight an opponent once per game played, or once per distinct opponent.
    instance_weighting: InstanceWeighting
    #: Exclude the rated team when averaging each opponent's OWP into OOWP.
    exclude_rated_team_from_oowp: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "semantics_id": self.semantics_id,
            "authority": self.authority,
            "exclude_rated_team_from_owp": self.exclude_rated_team_from_owp,
            "instance_weighting": self.instance_weighting,
            "exclude_rated_team_from_oowp": self.exclude_rated_team_from_oowp,
        }


#: No governed semantics exist in this repository. Deliberately ``None``.
GOVERNED_SOS_SEMANTICS: SosSemantics | None = None

#: Authorities that are explicitly not governance. Named so the gate can say why.
NON_GOVERNED_AUTHORITIES = ("TEST_FIXTURE", "RESEARCH", "PROPOSED", "ASSUMED", "")


def require_governed_sos_semantics(semantics: SosSemantics | None) -> SosSemantics:
    """Fail closed until the OWP/OOWP denominator rules are governed."""
    if semantics is None:
        raise GovernanceBlock(
            f"{SOS_SEMANTICS_BLOCKER}: ruling {R2_SOS.convergence_id} fixes the SOS weights "
            "(0.25 WP / 0.50 OWP / 0.25 OOWP) but no repository authority defines the "
            "OWP/OOWP denominator, opponent-exclusion or schedule-instance weighting rules. "
            "Issue those semantics; do not infer them."
        )
    if semantics.authority.upper() in NON_GOVERNED_AUTHORITIES:
        raise GovernanceBlock(
            f"{SOS_SEMANTICS_BLOCKER}: SOS semantics {semantics.semantics_id!r} carries "
            f"authority {semantics.authority!r}, which is not a governed source."
        )
    return semantics


class ResumeLedger:
    """Completed games, queryable as of a week so no future result can leak in."""

    def __init__(self, results: Iterable[GameResult]) -> None:
        self._results = tuple(sorted(results, key=lambda r: (r.week, r.game_id, r.team)))
        seen: set[tuple[str, str]] = set()
        for r in self._results:
            key = (r.game_id, r.team)
            if key in seen:
                raise InputValidationError(f"Duplicate ledger row for {r.team} in {r.game_id}")
            seen.add(key)

    @property
    def results(self) -> tuple[GameResult, ...]:
        return self._results

    def through_week(self, as_of_week: int) -> "ResumeLedger":
        return ResumeLedger(r for r in self._results if r.week <= as_of_week)

    def teams(self) -> tuple[str, ...]:
        return tuple(sorted({r.team for r in self._results}))

    def games_for(self, team: str) -> tuple[GameResult, ...]:
        return tuple(r for r in self._results if r.team == team)

    def record(self, team: str, *, excluding_opponent: str | None = None) -> tuple[int, int]:
        wins = losses = 0
        for r in self.games_for(team):
            if excluding_opponent is not None and r.opponent == excluding_opponent:
                continue
            if r.won:
                wins += 1
            else:
                losses += 1
        return wins, losses


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def win_pct(ledger: ResumeLedger, team: str, *, excluding_opponent: str | None = None) -> float:
    """WP. Zero games is 0.0, not an error: an unplayed team has no resume yet."""
    wins, losses = ledger.record(team, excluding_opponent=excluding_opponent)
    played = wins + losses
    return wins / played if played else 0.0


def _opponent_instances(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> list[str]:
    opponents = [r.opponent for r in ledger.games_for(team)]
    if semantics.instance_weighting == "PER_OPPONENT":
        return sorted(set(opponents))
    if semantics.instance_weighting != "PER_GAME":
        raise InputValidationError(f"Unknown instance weighting {semantics.instance_weighting!r}")
    return sorted(opponents)


def opponent_win_pct(ledger: ResumeLedger, team: str, semantics: SosSemantics) -> float:
    """OWP: mean opponent WP, under the configured exclusion and weighting."""
    exclude = team if semantics.exclude_rated_team_from_owp else None
    return _mean(
        [win_pct(ledger, opp, excluding_opponent=exclude)
         for opp in _opponent_instances(ledger, team, semantics)]
    )


def opponent_opponent_win_pct(ledger: ResumeLedger, team: str, semantics: SosSemantics) -> float:
    """OOWP: mean over the rated team's opponents of each opponent's OWP."""
    values: list[float] = []
    for opp in _opponent_instances(ledger, team, semantics):
        opp_opponents = _opponent_instances(ledger, opp, semantics)
        if semantics.exclude_rated_team_from_oowp:
            opp_opponents = [o for o in opp_opponents if o != team]
        exclude = opp if semantics.exclude_rated_team_from_owp else None
        values.append(
            _mean([win_pct(ledger, o, excluding_opponent=exclude) for o in opp_opponents])
        )
    return _mean(values)


def strength_of_schedule(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> float:
    """SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP (ruling R2-SOS)."""
    return (
        WP_WEIGHT * win_pct(ledger, team)
        + OWP_WEIGHT * opponent_win_pct(ledger, team, semantics)
        + OOWP_WEIGHT * opponent_opponent_win_pct(ledger, team, semantics)
    )


def sos_components(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> dict[str, float]:
    return {
        "wp": win_pct(ledger, team),
        "owp": opponent_win_pct(ledger, team, semantics),
        "oowp": opponent_opponent_win_pct(ledger, team, semantics),
        "sos": strength_of_schedule(ledger, team, semantics),
    }


def rank_by_sos(
    ledger: ResumeLedger, teams: Iterable[str], semantics: SosSemantics
) -> list[str]:
    """Hardest schedule first; ties break on schedule_id so the order is total."""
    listed = sorted(set(teams))
    return sorted(listed, key=lambda t: (-strength_of_schedule(ledger, t, semantics), t))
