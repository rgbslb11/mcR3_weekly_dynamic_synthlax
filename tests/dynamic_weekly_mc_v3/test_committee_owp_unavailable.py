"""COMMITTEE OWP UNAVAILABLE REMEDIATION R1 — ruling R-V3-COMMITTEE-OWP-UNAVAILABLE-01.

An independent re-audit of candidate b22f178 observed that the per-path committee
board still carried ``opponent_win_pct=float(owp or 0.0)``. Forty of 121 FBS
teams reach the board with an UNAVAILABLE governed SOS and eight with an
UNAVAILABLE governed OWP, so that coercion was letting an absent value act as
numeric evidence in the board's second ranking criterion — and act as the *worst*
possible one, since 0.0 is the floor of a win percentage.

The ruling holds that an UNAVAILABLE OWP stays UNAVAILABLE: never 0, 0.0, .500, a
league average, or the worst or best available value; never an automatic last or
first place; never an exclusion from the board. It does not resolve the pair, and
the comparison advances to the next already-governed criterion.

What this suite pins down is that "does not resolve" is genuinely different from
"resolves badly". The distinction is asserted from both directions — a team with
no governed OWP must not be pushed down by an opponent with a high OWP, and must
not be pulled up by an opponent with a low one — because a coercion in either
direction would satisfy a one-sided test.
"""

import inspect

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import committee, rulings, season_run

TB1, TB2, TB3, TB4 = committee.COMMITTEE_TIEBREAK_STAGES
OWP = committee.COMMITTEE_OWP_CRITERION
CHAMPION = committee.COMMITTEE_CHAMPION_CRITERION
TERMINAL = committee.COMMITTEE_TERMINAL_ORDERING


def _team(owp, *, champion=False, sos=0.5, wins=9, losses=3):
    return committee.CommitteeInputs(
        wins=wins,
        losses=losses,
        opponent_win_pct=owp,
        conference_champion=champion,
        strength_tiebreak=sos,
    )


def _decide(inputs, head_to_head=None, tiebreaks=None):
    order, stage, outcomes = committee.governed_pair_order(
        "A",
        "B",
        inputs,
        head_to_head or {},
        tiebreaks or committee.CommitteeTiebreakInputs(),
    )
    return order, stage, {o.stage: o.status for o in outcomes}


# ---------------------------------------------------------------------------
# 1-2: available OWP behaves exactly as before.
# ---------------------------------------------------------------------------


def test_1_numeric_versus_numeric_resolves_normally():
    order, stage, statuses = _decide({"A": _team(0.62), "B": _team(0.48)})
    assert statuses[OWP] == committee.TB_RESOLVED
    assert stage == OWP
    assert order < 0  # the higher opponent win percentage ranks ahead

    order, stage, _ = _decide({"A": _team(0.48), "B": _team(0.62)})
    assert stage == OWP
    assert order > 0


def test_2_equal_numeric_owp_does_not_resolve_and_advances():
    _order, stage, statuses = _decide({"A": _team(0.55), "B": _team(0.55)})
    assert statuses[OWP] == committee.TB_TIED
    assert stage != OWP
    assert CHAMPION in statuses  # the comparison advanced to the next criterion


# ---------------------------------------------------------------------------
# 3-5: UNAVAILABLE on either side, or both, does not resolve.
# ---------------------------------------------------------------------------


def test_3_left_numeric_right_unavailable_does_not_resolve():
    _order, stage, statuses = _decide({"A": _team(0.62), "B": _team(None)})
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert stage != OWP


def test_4_left_unavailable_right_numeric_does_not_resolve():
    _order, stage, statuses = _decide({"A": _team(None), "B": _team(0.62)})
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert stage != OWP


def test_5_both_unavailable_does_not_resolve():
    _order, stage, statuses = _decide({"A": _team(None), "B": _team(None)})
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert stage != OWP


# ---------------------------------------------------------------------------
# 6: None is never transformed into a number.
# ---------------------------------------------------------------------------


def test_6_none_is_never_transformed_into_zero_point_zero():
    """The dataclass stores UNAVAILABLE, and the board never manufactures one."""
    team = _team(None)
    assert team.opponent_win_pct is None
    for forbidden in committee.REFUSED_UNAVAILABLE_SUBSTITUTES:
        assert team.opponent_win_pct != forbidden

    # An UNAVAILABLE OWP and a 0.0 OWP must not reach the same criterion outcome.
    _o1, _s1, unavailable = _decide({"A": _team(None), "B": _team(0.0)})
    _o2, _s2, numeric = _decide({"A": _team(0.0), "B": _team(0.0)})
    assert unavailable[OWP] == committee.TB_UNAVAILABLE
    assert numeric[OWP] == committee.TB_TIED


def test_6_the_board_source_no_longer_coerces_owp():
    """Guard the exact expression the re-audit found, at its call site."""
    source = inspect.getsource(season_run.build_board)
    assert "float(owp or 0.0)" not in source
    assert "None if owp is None else float(owp)" in source


# ---------------------------------------------------------------------------
# 7-8: the asymmetry test. Unavailable must not be low *or* high.
# ---------------------------------------------------------------------------


def test_7_unavailable_owp_is_not_ranked_lower_for_facing_a_high_owp_opponent():
    """Under the old coercion this pair resolved at OWP against A. It must not now.

    A carries no governed OWP; B carries a high one. The pair advances, and the
    next criterion that can separate them decides — here TB3, where A has the
    stronger schedule and therefore ranks ahead. The point is not that A wins; it
    is that A's missing OWP did not lose it the pair.
    """
    inputs = {"A": _team(None, sos=0.90), "B": _team(0.95, sos=0.10)}
    order, stage, statuses = _decide(inputs)
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert stage == TB3
    assert order < 0  # A ranks ahead on the criterion that actually resolved


def test_8_unavailable_owp_is_not_ranked_higher_for_facing_a_low_owp_opponent():
    """The mirror image, so the fix cannot be a coercion in the other direction."""
    inputs = {"A": _team(None, sos=0.10), "B": _team(0.0, sos=0.90)}
    order, stage, statuses = _decide(inputs)
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert stage == TB3
    assert order > 0  # B ranks ahead; A was not promoted by having no OWP


def test_7_8_the_unavailable_team_is_never_excluded_from_the_board():
    inputs = {
        "A": _team(None),
        "B": _team(0.9),
        "C": _team(0.1),
    }
    board = committee.rank_committee_results_first(inputs, {})
    assert sorted(board) == ["A", "B", "C"]
    assert len(board) == 3


def test_7_8_an_unavailable_owp_does_not_force_last_or_first_place():
    """Position is decided by the criteria that follow, not by the gap itself."""
    # A's schedule is the strongest, so once OWP declines to resolve, A leads.
    leading = committee.rank_committee_results_first(
        {"A": _team(None, sos=0.90), "B": _team(0.9, sos=0.50), "C": _team(0.1, sos=0.10)},
        {},
    )
    assert leading[0] == "A"

    # Same missing OWP, weakest schedule: A trails. Neither place is automatic.
    trailing = committee.rank_committee_results_first(
        {"A": _team(None, sos=0.05), "B": _team(0.9, sos=0.50), "C": _team(0.1, sos=0.10)},
        {},
    )
    assert trailing[-1] == "A"


# ---------------------------------------------------------------------------
# 9-10: the rest of the governed sequence still runs, in order.
# ---------------------------------------------------------------------------


def test_9_the_next_governed_criterion_resolves_after_owp_is_unavailable():
    """Champion status sits directly below OWP and gets its chance first."""
    inputs = {"A": _team(None, champion=False), "B": _team(0.9, champion=True)}
    order, stage, statuses = _decide(inputs)
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert stage == CHAMPION
    assert order > 0  # the conference champion ranks ahead
    assert TB1 not in statuses  # nothing below the deciding criterion was consulted


def test_9_tb1_resolves_after_owp_and_champion_both_decline():
    inputs = {"A": _team(None), "B": _team(0.9)}
    order, stage, statuses = _decide(inputs, head_to_head={frozenset(("A", "B")): "A"})
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert statuses[CHAMPION] == committee.TB_TIED
    assert stage == TB1
    assert order < 0


def test_10_terminal_ordering_only_after_the_whole_governed_sequence():
    inputs = {"A": _team(None, sos=None), "B": _team(None, sos=None)}
    _order, stage, statuses = _decide(inputs)
    assert stage == TERMINAL
    assert set(statuses) == set(committee.COMMITTEE_RANKING_CRITERIA)
    assert statuses[OWP] == committee.TB_UNAVAILABLE
    assert statuses[TB3] == committee.TB_UNAVAILABLE
    assert statuses[TB4] == committee.TB_UNAVAILABLE


# ---------------------------------------------------------------------------
# 11: UNAVAILABLE and 0.0 are not semantically equivalent.
# ---------------------------------------------------------------------------


def test_11_owp_unavailable_and_owp_zero_are_not_semantically_equivalent():
    """One board, two teams that differ only in whether their OWP exists.

    ``ZERO`` genuinely carries OWP 0.0 — every opponent it played lost every other
    game — and belongs at the bottom on that evidence. ``GAP`` has no governed OWP
    at all. Under the old coercion the two were indistinguishable. They must now
    order differently, because only one of them has been measured.
    """
    inputs = {
        "GAP": _team(None, sos=0.80),
        "ZERO": _team(0.0, sos=0.80),
        "MID": _team(0.50, sos=0.10),
    }
    board = committee.rank_committee_results_first(inputs, {})

    # MID outranks ZERO on OWP, which resolves for that pair.
    assert board.index("MID") < board.index("ZERO")
    # GAP's pairs do not resolve on OWP at all, so its far stronger schedule
    # decides them and it leads the board — which the coerced reading could never
    # have produced, since 0.0 would have tied it with ZERO and sunk both.
    assert board[0] == "GAP"

    # Stated directly as criterion outcomes rather than only as an ordering.
    _o, _s, gap_vs_mid = _decide({"A": inputs["GAP"], "B": inputs["MID"]})
    _o2, _s2, zero_vs_mid = _decide({"A": inputs["ZERO"], "B": inputs["MID"]})
    assert gap_vs_mid[OWP] == committee.TB_UNAVAILABLE
    assert zero_vs_mid[OWP] == committee.TB_RESOLVED


def test_11_a_coerced_board_and_the_governed_board_actually_differ():
    """The regression this ruling exists to prevent, shown as two orderings."""
    governed = {
        "GAP": _team(None, sos=0.80),
        "HIGH": _team(0.90, sos=0.10),
    }
    coerced = {
        "GAP": _team(0.0, sos=0.80),  # the old float(owp or 0.0) reading
        "HIGH": _team(0.90, sos=0.10),
    }
    assert committee.rank_committee_results_first(governed, {}) == ["GAP", "HIGH"]
    assert committee.rank_committee_results_first(coerced, {}) == ["HIGH", "GAP"]


# ---------------------------------------------------------------------------
# Authority.
# ---------------------------------------------------------------------------


def test_the_ruling_and_token_are_bound_and_recorded():
    issued = rulings.ruling("R-V3-COMMITTEE-OWP-UNAVAILABLE-01")
    assert issued.chairman_ruling_id == "R-V3-COMMITTEE-OWP-UNAVAILABLE-01"
    assert issued.resolution_reason == "DIRECT_CHAIRMAN_AUTHORITY"
    assert issued.instruction == rulings.R5_OWP_INSTRUCTION
    assert committee.COMMITTEE_OWP_UNAVAILABLE_RULING == issued.convergence_id
    assert committee.COMMITTEE_OWP_UNAVAILABLE_TOKEN == (
        "APPROVE_V3_COMMITTEE_OWP_UNAVAILABLE::R-V3-COMMITTEE-OWP-UNAVAILABLE-01"
    )
    # The prior coercion is preserved as superseded history, not erased.
    assert any("float(owp or 0.0)" in text for text in issued.supersedes)


def test_the_ruling_retires_no_blocker():
    """It corrects a semantic; it does not clear governed work."""
    issued = rulings.ruling("R-V3-COMMITTEE-OWP-UNAVAILABLE-01")
    assert issued.retires == ()


def test_the_governed_criterion_order_is_unchanged_below_owp():
    """TB1/TB2/TB3/TB4 precedence is untouched by this ruling."""
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import committee_policy

    assert committee.COMMITTEE_TIEBREAK_STAGES == committee_policy.COMMITTEE_TIEBREAK_CHAIN
    assert committee.COMMITTEE_RANKING_CRITERIA == (
        OWP,
        CHAMPION,
    ) + committee_policy.COMMITTEE_TIEBREAK_CHAIN
    assert season_run.BOARD_TIEBREAKS_CONSULTED == committee_policy.COMMITTEE_TIEBREAK_CHAIN
    assert season_run.BOARD_TIEBREAKS_NOT_CONSULTED == ()
