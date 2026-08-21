"""Committee strength of schedule for V3.

Ruling R2-SOS fixes one quantity, one direction, one definition::

    SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP

Higher is a harder schedule. There is no second SOS, no mean-opponent-Elo
variant, and no revival of ``schedule_path_score`` + ``resume_ceiling_index``
double counting (both RETIRED in the Bracket Regime Deferred Register; DEF-2
records ``sos_index`` as "REPORTED, never scored").

The weights are governed. The *semantics* underneath them are not
-------------------------------------------------------------------
Six questions decide what WP/OWP/OOWP actually mean, and no mounted artifact
answers any of them:

1. are an opponent's games **against the evaluated team** removed from that
   opponent's record when computing OWP?
2. is OWP **team-averaged** or **schedule-instance-weighted**?
3. how is a **repeated opponent** treated — once, or once per meeting?
4. how is **OOWP constructed** — the mean of each opponent's OWP, or the mean
   over every opponent-of-opponent directly?
5. how do **schedule-only FCS opponent records** enter WP, OWP and OOWP?
6. what happens to a team with **zero qualifying games**?

The closest thing to authority in the repository is
``V2_1_STATIC_CONTROL…xlsx!Methodology!A11``, which records V2.1's committee
chain as "Winning percentage -> average opponents winning percentage ->
conference champion -> head-to-head -> unified preseason power". It names an
OWP-like quantity, defines none of the six, contains no OOWP at all, and belongs
to a chain that ruling R2-COMMITTEE-TB has since replaced.
``18_ACC_POLICY_REFERENCE`` records ACC-EXT-03, ACC-EXT-08 and ACC-EXT-09 — the
nearest tied-set and common-opponent questions — as **OPEN — REQUIRES RULING**,
and ACC-EXT-10 notes the external ranking the ACC policy names "does not
disclose variables, weights, or formula".

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
OowpConstruction = Literal["MEAN_OF_OPPONENT_OWP", "MEAN_OVER_ALL_OPPONENT_OPPONENTS"]
FcsTreatment = Literal["INCLUDE", "EXCLUDE_FROM_ALL", "COUNT_IN_WP_ONLY"]
ZeroGamesPolicy = Literal["TREAT_AS_ZERO", "EXCLUDE_FROM_AVERAGES", "BLOCK"]

#: The six semantics questions a governed ruling must answer, in order.
REQUIRED_SEMANTICS_RULINGS = (
    "Are an opponent's games against the evaluated team removed from that opponent's "
    "record when computing OWP?",
    "Is OWP team-averaged or schedule-instance-weighted?",
    "How is a repeated opponent treated - once, or once per meeting?",
    "How is OOWP constructed - the mean of each opponent's OWP, or the mean over every "
    "opponent-of-opponent directly?",
    "How do schedule-only FCS opponent records enter WP, OWP and OOWP?",
    "What happens to a team with zero qualifying games?",
)


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
    #: How OOWP is assembled from the opponent set.
    oowp_construction: OowpConstruction = "MEAN_OF_OPPONENT_OWP"
    #: How schedule-only FCS opponents enter WP / OWP / OOWP.
    schedule_only_fcs_treatment: FcsTreatment = "INCLUDE"
    #: What a team with no qualifying games contributes to an average.
    zero_qualifying_games: ZeroGamesPolicy = "TREAT_AS_ZERO"
    #: Schedule IDs to treat as schedule-only FCS entities.
    schedule_only_fcs_ids: frozenset[str] = frozenset()

    def as_dict(self) -> dict[str, object]:
        return {
            "semantics_id": self.semantics_id,
            "authority": self.authority,
            "exclude_rated_team_from_owp": self.exclude_rated_team_from_owp,
            "instance_weighting": self.instance_weighting,
            "exclude_rated_team_from_oowp": self.exclude_rated_team_from_oowp,
            "oowp_construction": self.oowp_construction,
            "schedule_only_fcs_treatment": self.schedule_only_fcs_treatment,
            "zero_qualifying_games": self.zero_qualifying_games,
        }


#: No governed semantics exist in this repository. Deliberately ``None``.
GOVERNED_SOS_SEMANTICS: SosSemantics | None = None

#: Authorities that are explicitly not governance. Named so the gate can say why.
NON_GOVERNED_AUTHORITIES = ("TEST_FIXTURE", "RESEARCH", "PROPOSED", "ASSUMED", "")


def required_ruling_text() -> str:
    """The precise mathematical ruling this blocker is waiting on."""
    numbered = "\n".join(
        f"  {i}. {q}" for i, q in enumerate(REQUIRED_SEMANTICS_RULINGS, 1)
    )
    return (
        f"Ruling {R2_SOS.convergence_id} fixes the SOS weights "
        "(0.25 WP / 0.50 OWP / 0.25 OOWP). A governed ruling must additionally answer, "
        "for both SOS and the common-opponent comparison that shares these semantics:\n"
        f"{numbered}"
    )


def require_governed_sos_semantics(semantics: SosSemantics | None) -> SosSemantics:
    """Fail closed until all six OWP/OOWP semantics questions are governed."""
    if semantics is None:
        raise GovernanceBlock(f"{SOS_SEMANTICS_BLOCKER}: {required_ruling_text()}")
    if semantics.authority.upper() in NON_GOVERNED_AUTHORITIES:
        raise GovernanceBlock(
            f"{SOS_SEMANTICS_BLOCKER}: SOS semantics {semantics.semantics_id!r} carries "
            f"authority {semantics.authority!r}, which is not a governed source.\n"
            f"{required_ruling_text()}"
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


def win_pct(
    ledger: ResumeLedger,
    team: str,
    *,
    excluding_opponent: str | None = None,
    semantics: SosSemantics | None = None,
) -> float:
    """WP under the configured zero-qualifying-games policy.

    With no semantics supplied the historical default applies (zero games reads
    0.0). Which of the three policies is correct is one of the six questions the
    governed ruling must answer, so a caller that supplies semantics gets that
    policy and ``BLOCK`` raises rather than inventing a value.
    """
    wins, losses = ledger.record(team, excluding_opponent=excluding_opponent)
    played = wins + losses
    if played:
        return wins / played
    policy = semantics.zero_qualifying_games if semantics else "TREAT_AS_ZERO"
    if policy == "BLOCK":
        raise GovernanceBlock(
            f"{team} has zero qualifying games and the governed zero-games policy is BLOCK."
        )
    return 0.0


def _counts_toward(opponent: str, semantics: SosSemantics, stage: str) -> bool:
    """Whether a schedule-only FCS opponent enters this stage of the calculation."""
    if opponent not in semantics.schedule_only_fcs_ids:
        return True
    if semantics.schedule_only_fcs_treatment == "INCLUDE":
        return True
    if semantics.schedule_only_fcs_treatment == "EXCLUDE_FROM_ALL":
        return False
    return stage == "WP"


def _opponent_instances(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> list[str]:
    opponents = [
        r.opponent for r in ledger.games_for(team)
        if _counts_toward(r.opponent, semantics, "OWP")
    ]
    if semantics.instance_weighting == "PER_OPPONENT":
        return sorted(set(opponents))
    if semantics.instance_weighting != "PER_GAME":
        raise InputValidationError(f"Unknown instance weighting {semantics.instance_weighting!r}")
    return sorted(opponents)


def opponent_win_pct(ledger: ResumeLedger, team: str, semantics: SosSemantics) -> float:
    """OWP: mean opponent WP, under the configured exclusion and weighting."""
    exclude = team if semantics.exclude_rated_team_from_owp else None
    values = []
    for opp in _opponent_instances(ledger, team, semantics):
        if semantics.zero_qualifying_games == "EXCLUDE_FROM_AVERAGES":
            wins, losses = ledger.record(opp, excluding_opponent=exclude)
            if wins + losses == 0:
                continue
        values.append(win_pct(ledger, opp, excluding_opponent=exclude, semantics=semantics))
    return _mean(values)


def opponent_opponent_win_pct(ledger: ResumeLedger, team: str, semantics: SosSemantics) -> float:
    """OOWP under the configured construction.

    ``MEAN_OF_OPPONENT_OWP`` averages each opponent's own OWP.
    ``MEAN_OVER_ALL_OPPONENT_OPPONENTS`` pools every opponent-of-opponent into a
    single average instead. The two differ whenever opponents played unequal
    numbers of games, which is most of a real season.
    """
    per_opponent: list[float] = []
    pooled: list[float] = []
    for opp in _opponent_instances(ledger, team, semantics):
        opp_opponents = _opponent_instances(ledger, opp, semantics)
        if semantics.exclude_rated_team_from_oowp:
            opp_opponents = [o for o in opp_opponents if o != team]
        exclude = opp if semantics.exclude_rated_team_from_owp else None
        inner = [
            win_pct(ledger, o, excluding_opponent=exclude, semantics=semantics)
            for o in opp_opponents
        ]
        per_opponent.append(_mean(inner))
        pooled.extend(inner)
    if semantics.oowp_construction == "MEAN_OVER_ALL_OPPONENT_OPPONENTS":
        return _mean(pooled)
    return _mean(per_opponent)


def strength_of_schedule(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> float:
    """SOS = 0.25 * WP + 0.50 * OWP + 0.25 * OOWP (ruling R2-SOS)."""
    return (
        WP_WEIGHT * win_pct(ledger, team, semantics=semantics)
        + OWP_WEIGHT * opponent_win_pct(ledger, team, semantics)
        + OOWP_WEIGHT * opponent_opponent_win_pct(ledger, team, semantics)
    )


def sos_components(
    ledger: ResumeLedger, team: str, semantics: SosSemantics
) -> dict[str, float]:
    return {
        "wp": win_pct(ledger, team, semantics=semantics),
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
