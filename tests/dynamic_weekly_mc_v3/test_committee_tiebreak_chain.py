"""COMMITTEE TIEBREAK EXECUTION REMEDIATION R1 — the governed chain, executed.

An independent audit of candidate 754f87c found that the per-path committee
board reached TB1, then TB3, then the terminal ``schedule_id`` ordering, never
evaluating COMMITTEE-TB2 or COMMITTEE-TB4. The omission was measured as
reachable and material at the CFP field boundary.

What this suite pins down is *precedence*, not arithmetic. The common-opponent
formula is unchanged and belongs to ``test_r4_common_opponent_authority``; the
SOS formula is unchanged and belongs to ``test_r2_sos_and_common_opponents``.
What is asserted here is that each governed criterion is actually evaluated in
its own order, that an advance is always caused by an evaluated TIED or
UNAVAILABLE result rather than by omission, and that UNAVAILABLE never becomes a
number.

The stage a pair was decided by is read from the chain's own outcome record, so
these are assertions about what executed and not about what the answer happened
to be.
"""

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
    committee,
    common_opponents,
    season_run,
    sos,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock

TB1, TB2, TB3, TB4 = committee.COMMITTEE_TIEBREAK_STAGES
TERMINAL = committee.COMMITTEE_TERMINAL_ORDERING


def _inputs(**sos_by_team):
    """Teams identical on every criterion preceding the chain, differing only on TB3."""
    return {
        team: committee.CommitteeInputs(
            wins=9,
            losses=3,
            opponent_win_pct=0.5,
            conference_champion=False,
            strength_tiebreak=value,
        )
        for team, value in sos_by_team.items()
    }


def _decide(a, b, inputs, head_to_head=None, tiebreaks=None):
    order, stage, outcomes = committee.governed_pair_order(
        a,
        b,
        inputs,
        head_to_head or {},
        tiebreaks or committee.CommitteeTiebreakInputs(),
    )
    return order, stage, {o.stage: o.status for o in outcomes}


def _resolver(mapping):
    """A TB2 resolver over an explicit ``frozenset(pair) -> (status, winner)`` table."""

    def resolve(team, other):
        entry = mapping.get(frozenset((team, other)))
        if entry is None:
            return committee.TB_UNAVAILABLE, 0
        status, winner = entry
        if status != committee.TB_RESOLVED:
            return status, 0
        return status, -1 if winner == team else 1

    return resolve


# ---------------------------------------------------------------------------
# A-B: TB1 precedence, and TB2 reached only when TB1 does not resolve.
# ---------------------------------------------------------------------------


def test_a_tb1_resolves_and_no_later_criterion_is_consulted():
    inputs = _inputs(A=0.10, B=0.90)  # TB3 would strongly prefer B
    tb2_calls = []

    def resolver(team, other):
        tb2_calls.append((team, other))
        return committee.TB_RESOLVED, 1  # TB2 would prefer the second team

    order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        head_to_head={frozenset(("A", "B")): "A"},
        tiebreaks=committee.CommitteeTiebreakInputs(common_opponent_order=resolver),
    )
    assert stage == TB1
    assert order < 0  # A, the head-to-head winner, ranks ahead
    assert tb2_calls == []  # TB2 was not consulted unnecessarily
    assert set(statuses) == {TB1}  # no later stage was even evaluated


def test_b_tb1_unresolved_causes_tb2_to_be_evaluated():
    inputs = _inputs(A=0.50, B=0.50)
    seen = []

    def resolver(team, other):
        seen.append(frozenset((team, other)))
        return committee.TB_TIED, 0

    _order, _stage, statuses = _decide(
        "A",
        "B",
        inputs,
        head_to_head={},  # never met
        tiebreaks=committee.CommitteeTiebreakInputs(common_opponent_order=resolver),
    )
    assert statuses[TB1] == committee.TB_NOT_APPLICABLE
    assert seen == [frozenset(("A", "B"))]
    assert TB2 in statuses


# ---------------------------------------------------------------------------
# C-E: TB2 outcomes drive whether TB3 is reached.
# ---------------------------------------------------------------------------


def test_c_tb2_decisive_means_tb3_is_not_used():
    inputs = _inputs(A=0.10, B=0.90)  # TB3 would prefer B
    order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(
            common_opponent_order=_resolver(
                {frozenset(("A", "B")): (committee.TB_RESOLVED, "A")}
            )
        ),
    )
    assert stage == TB2
    assert order < 0  # A wins on TB2 despite a far worse TB3
    assert TB3 not in statuses


def test_d_tb2_unavailable_reaches_tb3():
    inputs = _inputs(A=0.10, B=0.90)
    order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(common_opponent_order=_resolver({})),
    )
    assert statuses[TB2] == committee.TB_UNAVAILABLE
    assert stage == TB3
    assert order > 0  # B, with the stronger schedule, ranks ahead


def test_e_tb2_tied_reaches_tb3():
    inputs = _inputs(A=0.10, B=0.90)
    order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(
            common_opponent_order=_resolver(
                {frozenset(("A", "B")): (committee.TB_TIED, None)}
            )
        ),
    )
    assert statuses[TB2] == committee.TB_TIED
    assert stage == TB3
    assert order > 0


def test_a_missing_tb2_resolver_is_unavailable_not_skipped():
    """No resolver supplied is UNAVAILABLE — a recorded stage, not an omission."""
    inputs = _inputs(A=0.10, B=0.90)
    _order, stage, statuses = _decide("A", "B", inputs)
    assert statuses[TB2] == committee.TB_UNAVAILABLE
    assert stage == TB3


# ---------------------------------------------------------------------------
# F-H: TB3 outcomes drive TB4, and TB4 drives the terminal ordering.
# ---------------------------------------------------------------------------


def test_f_tb3_tied_reaches_tb4():
    inputs = _inputs(A=0.50, B=0.50)
    _order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(previous_board=("B", "A")),
    )
    assert statuses[TB3] == committee.TB_TIED
    assert stage == TB4


def test_f_tb3_unavailable_reaches_tb4():
    inputs = _inputs(A=None, B=0.90)
    _order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(previous_board=("A", "B")),
    )
    assert statuses[TB3] == committee.TB_UNAVAILABLE
    assert stage == TB4


def test_g_tb4_decisive_means_terminal_ordering_is_not_used():
    inputs = _inputs(A=0.50, B=0.50)
    order, stage, _statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(previous_board=("B", "A")),
    )
    assert stage == TB4
    assert order > 0  # B ranked ahead on the previous board, and keeps that order
    assert stage != TERMINAL


def test_h_tb4_unavailable_permits_terminal_ordering():
    inputs = _inputs(A=0.50, B=0.50)
    order, stage, statuses = _decide("A", "B", inputs)
    assert statuses[TB4] == committee.TB_UNAVAILABLE
    assert stage == TERMINAL
    assert order < 0  # schedule_id ascending


def test_h_terminal_ordering_is_reached_only_after_all_four_stages():
    inputs = _inputs(A=0.50, B=0.50)
    _order, stage, statuses = _decide("A", "B", inputs)
    assert stage == TERMINAL
    assert set(statuses) == {TB1, TB2, TB3, TB4}


def test_h_a_team_absent_from_the_previous_board_is_unavailable_not_ranked_last():
    inputs = _inputs(A=0.50, B=0.50)
    _order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(previous_board=("B",)),
    )
    assert statuses[TB4] == committee.TB_UNAVAILABLE
    assert stage == TERMINAL


# ---------------------------------------------------------------------------
# I: UNAVAILABLE is never a number.
# ---------------------------------------------------------------------------


def test_i_unavailable_common_opponent_score_never_becomes_zero_or_point_five():
    """A pair with no common opponents is UNAVAILABLE through the governed path."""
    rows = []
    for game_id, week, a, b, a_won in (
        ("g1", 1, "A", "X", True),
        ("g2", 2, "B", "Z", True),
        ("g3", 3, "X", "Q", True),
        ("g4", 4, "Z", "Q", False),
    ):
        rows += [
            sos.GameResult(game_id=game_id, week=week, team=a, opponent=b, won=a_won),
            sos.GameResult(game_id=game_id, week=week, team=b, opponent=a, won=not a_won),
        ]
    ledger = sos.ResumeLedger(rows)
    semantics = sos.GOVERNED_SOS_SEMANTICS

    assert common_opponents.common_opponents(ledger, "A", "B") == ()
    left, right = common_opponents.governed_compare_common_opponents(
        ledger, "A", "B", semantics
    )
    assert left.score is None and right.score is None
    for forbidden in committee.REFUSED_UNAVAILABLE_SUBSTITUTES:
        assert left.score != forbidden and right.score != forbidden

    resolve = season_run.governed_common_opponent_resolver(ledger, semantics)
    assert resolve("A", "B") == (committee.TB_UNAVAILABLE, 0)


def test_i_tb3_unavailable_is_not_read_as_zero():
    """A None SOS must not sort as the worst schedule; it must advance the chain."""
    inputs = _inputs(A=None, B=0.0)
    _order, stage, statuses = _decide(
        "A",
        "B",
        inputs,
        tiebreaks=committee.CommitteeTiebreakInputs(previous_board=("A", "B")),
    )
    assert statuses[TB3] == committee.TB_UNAVAILABLE
    assert stage == TB4  # not decided by treating None as 0.0


def test_i_a_resolver_returning_a_foreign_status_is_refused():
    inputs = _inputs(A=0.5, B=0.5)
    with pytest.raises(GovernanceBlock):
        _decide(
            "A",
            "B",
            inputs,
            tiebreaks=committee.CommitteeTiebreakInputs(
                common_opponent_order=lambda a, b: ("ASSUMED_0_500", -1)
            ),
        )


# ---------------------------------------------------------------------------
# J: precedence proved where TB2 and TB3 disagree.
# ---------------------------------------------------------------------------


def test_j_tb2_beats_tb3_when_they_disagree():
    """The whole point of the remediation, stated as one assertion."""
    inputs = _inputs(A=0.10, B=0.90)  # TB3 prefers B by a wide margin
    tiebreaks = committee.CommitteeTiebreakInputs(
        common_opponent_order=_resolver(
            {frozenset(("A", "B")): (committee.TB_RESOLVED, "A")}  # TB2 prefers A
        )
    )
    board = committee.rank_committee_results_first(inputs, {}, tiebreaks)
    assert board == ["A", "B"]

    # And with TB2 removed, the same inputs order the other way — so the board
    # above is caused by TB2 having been evaluated, not by anything else.
    assert committee.rank_committee_results_first(inputs, {}) == ["B", "A"]


def test_j_tb1_beats_tb2_when_they_disagree():
    inputs = _inputs(A=0.5, B=0.5)
    tiebreaks = committee.CommitteeTiebreakInputs(
        common_opponent_order=_resolver(
            {frozenset(("A", "B")): (committee.TB_RESOLVED, "B")}
        )
    )
    board = committee.rank_committee_results_first(
        inputs, {frozenset(("A", "B")): "A"}, tiebreaks
    )
    assert board == ["A", "B"]


def test_j_tb3_beats_tb4_when_they_disagree():
    inputs = _inputs(A=0.90, B=0.10)
    board = committee.rank_committee_results_first(
        inputs, {}, committee.CommitteeTiebreakInputs(previous_board=("B", "A"))
    )
    assert board == ["A", "B"]


# ---------------------------------------------------------------------------
# K: the CFP field cut follows the full chain.
# ---------------------------------------------------------------------------


def _seam_inputs():
    """Thirteen clearly-separated teams, then two tied at the 14/15 seam.

    ``T01``-``T13`` are separated on win percentage alone. ``SEAMLO`` and
    ``SEAMHI`` tie on every criterion preceding the chain, so which of them takes
    rank 14 — the last place inside the governed 14-team field — is decided by
    the tiebreak chain and nothing else.
    """
    inputs = {
        f"T{i:02d}": committee.CommitteeInputs(
            wins=14 - i,
            losses=i - 1,
            opponent_win_pct=0.5,
            conference_champion=False,
            strength_tiebreak=0.5,
        )
        for i in range(1, 14)
    }
    # Both seam teams sit below every T-team on win percentage.
    inputs["SEAMHI"] = committee.CommitteeInputs(
        wins=0, losses=13, opponent_win_pct=0.5, conference_champion=False,
        strength_tiebreak=0.90,
    )
    inputs["SEAMLO"] = committee.CommitteeInputs(
        wins=0, losses=13, opponent_win_pct=0.5, conference_champion=False,
        strength_tiebreak=0.10,
    )
    return inputs


def test_k_cfp_seam_follows_tb2_over_tb3():
    inputs = _seam_inputs()
    field_size = 14

    # Without TB2 the seam is decided by TB3, and SEAMHI takes rank 14.
    without_tb2 = committee.rank_committee_results_first(inputs, {})
    assert without_tb2[field_size - 1] == "SEAMHI"
    assert "SEAMLO" not in without_tb2[:field_size]

    # With TB2 evaluated and decisive for SEAMLO, the field cut moves to SEAMLO.
    with_tb2 = committee.rank_committee_results_first(
        inputs,
        {},
        committee.CommitteeTiebreakInputs(
            common_opponent_order=_resolver(
                {frozenset(("SEAMHI", "SEAMLO")): (committee.TB_RESOLVED, "SEAMLO")}
            )
        ),
    )
    assert with_tb2[field_size - 1] == "SEAMLO"
    assert "SEAMHI" not in with_tb2[:field_size]
    assert with_tb2[:field_size - 1] == without_tb2[:field_size - 1]


def test_k_cfp_seam_follows_tb4_when_tb2_and_tb3_do_not_resolve():
    inputs = _seam_inputs()
    for team in ("SEAMHI", "SEAMLO"):
        inputs[team] = committee.CommitteeInputs(
            wins=0, losses=13, opponent_win_pct=0.5,
            conference_champion=False, strength_tiebreak=None,
        )
    board = committee.rank_committee_results_first(
        inputs, {}, committee.CommitteeTiebreakInputs(previous_board=("SEAMLO", "SEAMHI"))
    )
    assert board[13] == "SEAMLO"


# ---------------------------------------------------------------------------
# L: determinism.
# ---------------------------------------------------------------------------


def test_l_repeat_ordering_is_deterministic():
    inputs = _seam_inputs()
    tiebreaks = committee.CommitteeTiebreakInputs(
        common_opponent_order=_resolver(
            {frozenset(("SEAMHI", "SEAMLO")): (committee.TB_RESOLVED, "SEAMLO")}
        ),
        previous_board=("SEAMHI", "SEAMLO"),
    )
    boards = {
        tuple(committee.rank_committee_results_first(inputs, {}, tiebreaks))
        for _ in range(25)
    }
    assert len(boards) == 1


def test_l_a_head_to_head_cycle_orders_deterministically_without_inventing_a_result():
    """Pairwise criteria can cycle; the group must still order, and always the same.

    A beat B, B beat C, C beat A. No pairwise decision is discarded and none is
    manufactured — the group is ordered on how many governed pairwise decisions
    each team won, with the terminal ordering settling the equal counts.
    """
    inputs = _inputs(A=0.5, B=0.5, C=0.5)
    head_to_head = {
        frozenset(("A", "B")): "A",
        frozenset(("B", "C")): "B",
        frozenset(("C", "A")): "C",
    }
    boards = {
        tuple(committee.rank_committee_results_first(inputs, head_to_head))
        for _ in range(25)
    }
    assert len(boards) == 1
    assert sorted(boards.pop()) == ["A", "B", "C"]


def test_l_a_transitive_group_orders_exactly_as_the_pairwise_chain_says():
    """Where the pairwise decisions are transitive, nothing is approximated."""
    inputs = _inputs(A=0.5, B=0.5, C=0.5)
    head_to_head = {
        frozenset(("A", "B")): "A",
        frozenset(("B", "C")): "B",
        frozenset(("A", "C")): "A",
    }
    assert committee.rank_committee_results_first(inputs, head_to_head) == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Wiring: the board executes the chain, and TB2 uses the governed implementation.
# ---------------------------------------------------------------------------


def test_the_board_declares_the_full_governed_chain_as_consulted():
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import committee_policy

    assert season_run.BOARD_TIEBREAKS_CONSULTED == committee_policy.COMMITTEE_TIEBREAK_CHAIN
    assert season_run.BOARD_TIEBREAKS_NOT_CONSULTED == ()
    assert season_run.BOARD_TERMINAL_ORDERING == TERMINAL


def test_the_prior_omission_is_preserved_as_history_not_erased():
    history = season_run.BOARD_TIEBREAK_EXECUTION_HISTORY
    assert "PRIOR_CANDIDATE_754F87C" in history
    assert "CURRENT_SUCCESSOR" in history
    assert "omitted" in history["PRIOR_CANDIDATE_754F87C"]


def test_tb2_delegates_to_the_governed_common_opponent_implementation():
    """The resolver must not carry its own copy of the formula."""
    rows = []
    for game_id, week, a, b, a_won in (
        ("g1", 1, "A", "X", True),
        ("g2", 2, "A", "Z", False),
        ("g3", 3, "B", "X", False),
        ("g4", 4, "B", "Z", True),
        ("g5", 5, "X", "Q", True),
        ("g6", 6, "Z", "Q", False),
    ):
        rows += [
            sos.GameResult(game_id=game_id, week=week, team=a, opponent=b, won=a_won),
            sos.GameResult(game_id=game_id, week=week, team=b, opponent=a, won=not a_won),
        ]
    ledger = sos.ResumeLedger(rows)
    semantics = sos.GOVERNED_SOS_SEMANTICS

    left, right = common_opponents.governed_compare_common_opponents(
        ledger, "A", "B", semantics
    )
    resolve = season_run.governed_common_opponent_resolver(ledger, semantics)
    status, order = resolve("A", "B")

    if left.score is None or right.score is None:
        assert status == committee.TB_UNAVAILABLE
    elif left.score == right.score:
        assert status == committee.TB_TIED
    else:
        assert status == committee.TB_RESOLVED
        assert order == (-1 if left.score > right.score else 1)
    # Orientation is symmetric: asking the other way round flips the sign only.
    assert resolve("B", "A") == (status, -order)


def test_the_governed_resolver_refuses_ungoverned_semantics():
    ledger = sos.ResumeLedger([])
    resolve = season_run.governed_common_opponent_resolver(ledger, None)
    with pytest.raises(GovernanceBlock):
        resolve("A", "B")
