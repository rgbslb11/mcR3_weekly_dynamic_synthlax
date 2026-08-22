"""The committee board and the governed committee tiebreak chain.

Ruling R2-COMMITTEE-TB defines one ordered chain and this module executes all of
it::

    COMMITTEE-TB1  head-to-head
    COMMITTEE-TB2  performance against common opponents (R2-COMMON-OPP,
                   formula issued exactly by R4-COMMON-OPP-FORMULA)
    COMMITTEE-TB3  strength of schedule (R2-SOS)
    COMMITTEE-TB4  previous week's committee board

Two properties are load-bearing and are the reason the previous implementation
was wrong rather than merely incomplete.

**Precedence is per pair, not per board.** A criterion is skipped only when it
has been *evaluated* for that pair and came back TIED or UNAVAILABLE. A board
that reaches a total order by some later criterion has not thereby earned the
right to skip an earlier one: ruling R4-COMMON-OPP-FORMULA directs that an
unavailable component "makes the score UNAVAILABLE and the tiebreak advances to
the next already-governed criterion rather than inventing 0, 0.0 or 0.500", and
an advance that was never caused by an evaluated result is exactly that
invention. The prior implementation pre-sorted on TB3 and then applied TB1 as an
adjacent correction, so TB2 and TB4 were never evaluated at all.

**UNAVAILABLE is not a value.** It never becomes 0, 0.0 or .500 anywhere in this
module. :func:`sos.criterion_resolves` is the single shared predicate for "did
this criterion actually separate these two teams", and it is imported rather than
restated.

The board's two criteria above the chain — opponent win percentage and conference
champion status — are evaluated the same way and for the same reason. Ruling
R-V3-COMMITTEE-OWP-UNAVAILABLE-01 holds that an UNAVAILABLE OWP stays
UNAVAILABLE: it is never 0, 0.0, .500, a league average, or the worst or best
available value, it never ranks a team automatically last or first, and it never
excludes a team from the board. So the full pairwise sequence is::

    COMMITTEE-OPPONENT_WIN_PCT
    COMMITTEE-CONFERENCE_CHAMPION
    COMMITTEE-TB1 … COMMITTEE-TB4
    CANONICAL_SCHEDULE_ID_ASCENDING

with the team's own win percentage partitioning the board before any of it.

The terminal ``schedule_id`` ordering survives, but only as what it is: a
deterministic total-order fallback reached after all four governed criteria have
been evaluated and none resolved. It is not a football tiebreak and is not a
governed substitute for TB2 or TB4.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from .errors import GovernanceBlock
from .rulings import R5_COMMITTEE_OWP_UNAVAILABLE
from .sos import criterion_resolves

#: The governed chain, in precedence order. Mirrors
#: ``committee_policy.COMMITTEE_TIEBREAK_CHAIN`` and is checked against it by test.
COMMITTEE_TIEBREAK_STAGES: tuple[str, ...] = (
    "COMMITTEE-TB1_HEAD_TO_HEAD",
    "COMMITTEE-TB2_COMMON_OPPONENT_PERFORMANCE",
    "COMMITTEE-TB3_STRENGTH_OF_SCHEDULE",
    "COMMITTEE-TB4_PREVIOUS_WEEK_BOARD",
)

#: The two board criteria that rank ahead of the whole tiebreak chain and below
#: the team's own record. They are *criteria*, evaluated per pair like every other
#: one, not sort keys — which is what ruling R-V3-COMMITTEE-OWP-UNAVAILABLE-01
#: requires, because an UNAVAILABLE OWP has no position on a numeric axis and
#: putting it on one is the coercion the ruling forbids.
COMMITTEE_OWP_CRITERION = "COMMITTEE-OPPONENT_WIN_PCT"
COMMITTEE_CHAMPION_CRITERION = "COMMITTEE-CONFERENCE_CHAMPION"

#: Every criterion evaluated pairwise, in governed precedence order. The team's own
#: win percentage is not here: it is always available and is what partitions the
#: board into the groups this sequence then orders.
COMMITTEE_RANKING_CRITERIA: tuple[str, ...] = (
    COMMITTEE_OWP_CRITERION,
    COMMITTEE_CHAMPION_CRITERION,
) + COMMITTEE_TIEBREAK_STAGES

#: The authority for the UNAVAILABLE-OWP handling below.
COMMITTEE_OWP_UNAVAILABLE_RULING = R5_COMMITTEE_OWP_UNAVAILABLE.convergence_id
COMMITTEE_OWP_UNAVAILABLE_TOKEN = (
    "APPROVE_V3_COMMITTEE_OWP_UNAVAILABLE::R-V3-COMMITTEE-OWP-UNAVAILABLE-01"
)

#: Reached only after every stage above has been evaluated without resolving.
#: Named so no reader mistakes it for a governed criterion.
COMMITTEE_TERMINAL_ORDERING = "CANONICAL_SCHEDULE_ID_ASCENDING"

#: Outcome vocabulary. ``NOT_APPLICABLE`` is distinguished from ``UNAVAILABLE``
#: because they are different facts: the first means the criterion has no meaning
#: for this pair (the two never met), the second means its governed inputs could
#: not be computed. Both advance the chain; only one is a data gap.
TB_RESOLVED = "RESOLVED"
TB_TIED = "TIED"
TB_UNAVAILABLE = "UNAVAILABLE"
TB_NOT_APPLICABLE = "NOT_APPLICABLE"

#: Values a governed criterion may never be silently replaced by.
REFUSED_UNAVAILABLE_SUBSTITUTES: tuple[float, ...] = (0.0, 0.5)


@dataclass(frozen=True)
class CommitteeInputs:
    wins: int
    losses: int
    #: The board's second ranking criterion. ``None`` is UNAVAILABLE and stays
    #: UNAVAILABLE under ruling R-V3-COMMITTEE-OWP-UNAVAILABLE-01: never 0, 0.0,
    #: .500, a league average, or the worst or best available value.
    opponent_win_pct: float | None
    conference_champion: bool
    #: COMMITTEE-TB3. ``None`` is UNAVAILABLE and stays UNAVAILABLE: it is never
    #: coerced to 0.0, which would let an absent schedule decide a tie.
    strength_tiebreak: float | None

    @property
    def win_pct(self) -> float:
        """The team's own record. Always available — it is a count, not an estimate."""
        n = self.wins + self.losses
        return self.wins / n if n else 0.0


@dataclass(frozen=True)
class CriterionOutcome:
    """What one governed criterion actually did for one ordered pair."""

    stage: str
    status: str
    #: -1 when the first team of the pair ranks ahead, +1 when the second does,
    #: 0 when the criterion did not resolve.
    order: int = 0

    @property
    def resolved(self) -> bool:
        return self.status == TB_RESOLVED


@dataclass(frozen=True)
class CommitteeTiebreakInputs:
    """The governed inputs the chain needs beyond the board keys themselves.

    Deliberately shaped like :class:`ccg.CcgTiebreakInputs`: the criteria that
    need state from outside the board carry that state in explicitly, so a caller
    that has not supplied it gets UNAVAILABLE rather than an invented answer.

    ``common_opponent_order`` is a resolver for COMMITTEE-TB2. It must delegate to
    the governed common-opponent implementation — this module deliberately holds
    no second copy of that arithmetic. It returns ``(status, order)`` where status
    is one of :data:`TB_RESOLVED`, :data:`TB_TIED`, :data:`TB_UNAVAILABLE`.

    ``previous_board`` is COMMITTEE-TB4: the previous committee board, best first.
    ``None`` means no previous board exists in this ranking context, which is
    UNAVAILABLE — not an excuse to omit the stage.
    """

    common_opponent_order: Callable[[str, str], tuple[str, int]] | None = None
    previous_board: Sequence[str] | None = None


#: An observer may watch the chain for diagnostics. It is passed the ordered pair
#: and the outcome of every stage evaluated for it, in precedence order. It can
#: never change an ordering: the chain ignores whatever it returns.
ChainObserver = Callable[[str, str, Sequence[CriterionOutcome]], None]


def _owp(
    team: str, other: str, inputs: Mapping[str, CommitteeInputs]
) -> CriterionOutcome:
    """The board's opponent-win-percentage criterion, under R-V3-COMMITTEE-OWP-UNAVAILABLE-01.

    An UNAVAILABLE OWP on either side does not resolve the pair and does not place
    the team anywhere: the comparison advances, and where the team ends up is
    decided by the criteria that follow. That is the whole of the difference
    between this and reading the missing value as 0.0, which ranked such a team
    below every team with any opponent record at all.
    """
    stage = COMMITTEE_OWP_CRITERION
    a = inputs[team].opponent_win_pct
    b = inputs[other].opponent_win_pct
    if a is None or b is None:
        return CriterionOutcome(stage, TB_UNAVAILABLE)
    if not criterion_resolves(a, b):
        return CriterionOutcome(stage, TB_TIED)
    return CriterionOutcome(stage, TB_RESOLVED, -1 if a > b else 1)


def _champion(
    team: str, other: str, inputs: Mapping[str, CommitteeInputs]
) -> CriterionOutcome:
    stage = COMMITTEE_CHAMPION_CRITERION
    a = inputs[team].conference_champion
    b = inputs[other].conference_champion
    if a == b:
        return CriterionOutcome(stage, TB_TIED)
    return CriterionOutcome(stage, TB_RESOLVED, -1 if a else 1)


def _tb1(
    team: str, other: str, head_to_head_winner: Mapping[frozenset[str], str]
) -> CriterionOutcome:
    stage = COMMITTEE_TIEBREAK_STAGES[0]
    winner = head_to_head_winner.get(frozenset((team, other)))
    if winner is None:
        # The two never met, or met and split. Either way head-to-head has
        # nothing to say about this pair.
        return CriterionOutcome(stage, TB_NOT_APPLICABLE)
    return CriterionOutcome(stage, TB_RESOLVED, -1 if winner == team else 1)


def _tb2(
    team: str, other: str, tiebreaks: CommitteeTiebreakInputs
) -> CriterionOutcome:
    stage = COMMITTEE_TIEBREAK_STAGES[1]
    resolver = tiebreaks.common_opponent_order
    if resolver is None:
        return CriterionOutcome(stage, TB_UNAVAILABLE)
    status, order = resolver(team, other)
    if status not in (TB_RESOLVED, TB_TIED, TB_UNAVAILABLE):
        raise GovernanceBlock(
            f"COMMITTEE-TB2 resolver returned status {status!r}. The governed outcomes "
            f"are {TB_RESOLVED}, {TB_TIED} and {TB_UNAVAILABLE}."
        )
    if status != TB_RESOLVED:
        return CriterionOutcome(stage, status)
    return CriterionOutcome(stage, TB_RESOLVED, order)


def _tb3(
    team: str, other: str, inputs: Mapping[str, CommitteeInputs]
) -> CriterionOutcome:
    stage = COMMITTEE_TIEBREAK_STAGES[2]
    a = inputs[team].strength_tiebreak
    b = inputs[other].strength_tiebreak
    if a is None or b is None:
        return CriterionOutcome(stage, TB_UNAVAILABLE)
    if not criterion_resolves(a, b):
        return CriterionOutcome(stage, TB_TIED)
    return CriterionOutcome(stage, TB_RESOLVED, -1 if a > b else 1)


def _tb4(
    team: str, other: str, tiebreaks: CommitteeTiebreakInputs
) -> CriterionOutcome:
    stage = COMMITTEE_TIEBREAK_STAGES[3]
    board = tiebreaks.previous_board
    if board is None:
        return CriterionOutcome(stage, TB_UNAVAILABLE)
    position = {name: index for index, name in enumerate(board)}
    if team not in position or other not in position:
        # A team absent from the previous board cannot be placed against one that
        # is present without inventing a rank for it.
        return CriterionOutcome(stage, TB_UNAVAILABLE)
    if position[team] == position[other]:
        return CriterionOutcome(stage, TB_TIED)
    return CriterionOutcome(stage, TB_RESOLVED, -1 if position[team] < position[other] else 1)


def governed_pair_order(
    team: str,
    other: str,
    inputs: Mapping[str, CommitteeInputs],
    head_to_head_winner: Mapping[frozenset[str], str],
    tiebreaks: CommitteeTiebreakInputs,
    observer: ChainObserver | None = None,
) -> tuple[int, str, tuple[CriterionOutcome, ...]]:
    """Order one pair by the full governed sequence, evaluating criteria in order.

    Returns ``(order, deciding_stage, outcomes)``. Every criterion up to and
    including the deciding one is actually evaluated, so an advance is always
    caused by a measured TIED or UNAVAILABLE result rather than by omission.

    The sequence is opponent win percentage, conference champion status, then the
    four governed tiebreak stages. The pair's own records are equal by the time
    this is called — win percentage is what groups the board, not what this
    orders — so the first criterion here is the first one that can still separate
    them.
    """
    outcomes: list[CriterionOutcome] = []
    for evaluate in (
        lambda: _owp(team, other, inputs),
        lambda: _champion(team, other, inputs),
        lambda: _tb1(team, other, head_to_head_winner),
        lambda: _tb2(team, other, tiebreaks),
        lambda: _tb3(team, other, inputs),
        lambda: _tb4(team, other, tiebreaks),
    ):
        outcome = evaluate()
        outcomes.append(outcome)
        if outcome.resolved:
            if observer is not None:
                observer(team, other, tuple(outcomes))
            return outcome.order, outcome.stage, tuple(outcomes)
    if observer is not None:
        observer(team, other, tuple(outcomes))
    return (
        -1 if team < other else 1,
        COMMITTEE_TERMINAL_ORDERING,
        tuple(outcomes),
    )


def _order_tie_group(
    group: Sequence[str],
    inputs: Mapping[str, CommitteeInputs],
    head_to_head_winner: Mapping[frozenset[str], str],
    tiebreaks: CommitteeTiebreakInputs,
    observer: ChainObserver | None,
) -> list[str]:
    """Order one group of teams tied on their own win percentage.

    OWP, TB1 and TB2 are all *pairwise* criteria — head-to-head is a result between
    two teams, and a common-opponent score is computed over the opponent set the
    two teams share — so neither is a scalar the group can simply be sorted on,
    and a set of pairwise decisions can contain a cycle (A over B, B over C, C
    over A). Sorting with such a comparator is undefined behaviour in every
    standard library, so the group is ordered by Copeland count instead: every
    pair is decided by the full governed chain, each team is credited with the
    pairwise decisions it won, and the group is ordered on that count with the
    terminal ``schedule_id`` ordering settling equal counts.

    Two properties make this the right method here rather than a convenience.
    When the pairwise decisions are transitive — which is the ordinary case — the
    Copeland counts are a strict permutation of ``n-1 … 0`` and the result is
    exactly the comparator's own order, so nothing is approximated. When they are
    not transitive, the cycle is resolved without inventing a football result:
    every input to the count is a decision the governed chain actually made, in
    its own precedence order.

    An UNAVAILABLE OWP is a second, non-football source of the same shape: under
    ruling R-V3-COMMITTEE-OWP-UNAVAILABLE-01 such a pair is simply not separated
    by OWP, so a team with no governed OWP can sit unseparated from two teams OWP
    does separate. That is handled here rather than by giving the team a number.
    """
    members = sorted(group)
    if len(members) < 2:
        return members

    wins = {team: 0 for team in members}
    for i, team in enumerate(members):
        for other in members[i + 1 :]:
            order, _stage, _outcomes = governed_pair_order(
                team, other, inputs, head_to_head_winner, tiebreaks, observer
            )
            if order < 0:
                wins[team] += 1
            else:
                wins[other] += 1
    return sorted(members, key=lambda team: (-wins[team], team))


def _preceding_key(x: CommitteeInputs) -> tuple[float]:
    """The one criterion that partitions the board rather than ordering within it.

    Only the team's own win percentage. Opponent win percentage and champion
    status used to be part of this key, which worked only while every OWP was a
    number: ruling R-V3-COMMITTEE-OWP-UNAVAILABLE-01 makes an UNAVAILABLE OWP
    non-resolving rather than low, and "does not resolve" is not an equivalence
    relation — a team with no governed OWP is unseparated from two teams that are
    separated from each other. A partition cannot express that, so OWP moved into
    the pairwise sequence where it can.

    Where every OWP is available the two formulations agree exactly, because a
    pairwise sequence over scalar criteria in the same order reproduces the
    lexicographic sort it replaced.
    """
    return (-x.win_pct,)


def rank_committee_results_first(
    inputs: dict[str, CommitteeInputs],
    head_to_head_winner: dict[frozenset[str], str],
    tiebreaks: CommitteeTiebreakInputs | None = None,
    observer: ChainObserver | None = None,
) -> list[str]:
    """The deterministic results-first board, executing the governed chain in full.

    Teams are first partitioned by their own win percentage, which is a count and
    is always available. Inside a group every remaining criterion is evaluated
    pairwise in governed precedence order — opponent win percentage, conference
    champion status, then TB1 through TB4 — so each one gets the chance to
    separate a pair before the next is consulted.

    Supplying no :class:`CommitteeTiebreakInputs` does not skip TB2 and TB4: it
    makes them UNAVAILABLE, which is a different and honest thing. A caller that
    wants them evaluated supplies their governed inputs.
    """
    context = tiebreaks or CommitteeTiebreakInputs()
    grouped: dict[tuple[float, float, int], list[str]] = {}
    for team in sorted(inputs):
        grouped.setdefault(_preceding_key(inputs[team]), []).append(team)

    ordered: list[str] = []
    for key in sorted(grouped):
        ordered.extend(
            _order_tie_group(
                grouped[key], inputs, head_to_head_winner, context, observer
            )
        )
    return ordered


def require_v3_strength_tiebreak_policy(policy: str | None) -> str:
    """Retired by ruling R2-COMMITTEE-TB. Refuses every input, including the old ones.

    The question this asked — which hidden strength number breaks a committee
    tie — presumed a board that ranks on a number it never publishes. Both of
    its former answers are now refused by name so a caller cannot drift back to
    the retired framing, and the function is kept rather than deleted so that
    refusal is visible at the old call site.
    """
    from .committee_policy import COMMITTEE_TIEBREAK_POLICY, RETIRED_STRENGTH_SOURCE_VALUES

    if policy in RETIRED_STRENGTH_SOURCE_VALUES:
        raise GovernanceBlock(
            f"committee_tiebreak_strength_source={policy!r} is retired by ruling "
            f"R2-COMMITTEE-TB. Use the structured chain {COMMITTEE_TIEBREAK_POLICY} via "
            "committee_policy.require_committee_tiebreak_policy."
        )
    raise GovernanceBlock(
        "V3 committee final tiebreak strength source is a retired concept. Ruling "
        f"R2-COMMITTEE-TB replaces it with {COMMITTEE_TIEBREAK_POLICY}."
    )
