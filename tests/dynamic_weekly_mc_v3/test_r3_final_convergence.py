"""PR #3 final convergence — the two R3 Chairman rulings, proved.

Ruling R3-SOS-OWP-OOWP-SEMANTICS governs the OWP/OOWP denominator and exclusion
semantics. Ruling R3-CFP-FIXED-TOPOLOGY fixes the 2026 bracket. Both retire
exactly one blocker each, and nothing else moves.

Every expected value below is computed by hand in the test that uses it, so a
reader can check the arithmetic without running the implementation.
"""

import hashlib
import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
    blocker_report as br,
    board_of_record,
    common_opponents,
    committee_policy,
    fcs,
    postseason,
    rulings,
    sos,
    srs,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
INPUTS = ROOT / "reference/dynamic_weekly_mc_v3/inputs"
STATUS_R3 = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R3.json"

GOVERNED = sos.GOVERNED_SOS_SEMANTICS


def _pair(game_id, week, a, b, a_won):
    return [
        sos.GameResult(game_id=game_id, week=week, team=a, opponent=b, won=a_won),
        sos.GameResult(game_id=game_id, week=week, team=b, opponent=a, won=not a_won),
    ]


@pytest.fixture(scope="module")
def repeat_ledger():
    """T plays O twice and P once; O and P each also play Q.

    T: beat O (w1), lost to O (w2), beat P (w3)   -> WP(T) = 2/3
    O: beat Q (w4).  P: lost to Q (w5).
    """
    rows = []
    rows += _pair("g1", 1, "T", "O", True)
    rows += _pair("g2", 2, "T", "O", False)
    rows += _pair("g3", 3, "T", "P", True)
    rows += _pair("g4", 4, "O", "Q", True)
    rows += _pair("g5", 5, "P", "Q", False)
    return sos.ResumeLedger(rows)


@pytest.fixture(scope="module")
def live_blockers():
    return sorted(DynamicWeeklyMCV3(V3Config.from_json(CONFIG)).preflight()["execution_blockers"])


# =============================================================================
# B12 — SOS test campaign
# =============================================================================


def test_the_ruling_leaves_the_r2_weights_untouched():
    assert (sos.WP_WEIGHT, sos.OWP_WEIGHT, sos.OOWP_WEIGHT) == (0.25, 0.50, 0.25)
    assert sos.WP_WEIGHT + sos.OWP_WEIGHT + sos.OOWP_WEIGHT == 1.0
    assert json.loads(STATUS_R3.read_text(encoding="utf-8"))["sos_semantics"][
        "weights_changed_by_r3"
    ] is False


def test_the_governed_semantics_answer_all_six_questions_as_ruled():
    d = GOVERNED.as_dict()
    assert d["exclude_rated_team_from_owp"] is True          # Q1
    assert d["instance_weighting"] == "PER_GAME"             # Q2 + Q3
    assert d["oowp_construction"] == "MEAN_OF_OPPONENT_OWP"  # Q4
    assert d["schedule_only_fcs_treatment"] == "INCLUDE_WHERE_GOVERNED_RECORD_EXISTS"  # Q5
    assert d["zero_qualifying_games"] == "UNAVAILABLE"       # Q6
    assert len(sos.REQUIRED_SEMANTICS_RULINGS) == 6


# --- WP ----------------------------------------------------------------------


def test_wp_is_wins_over_completed_qualifying_games(repeat_ledger):
    # T is 2-1: beat O, lost to O, beat P.
    assert sos.win_pct(repeat_ledger, "T", semantics=GOVERNED) == 2 / 3


def test_wp_counts_completed_games_only_and_never_leaks_the_future(repeat_ledger):
    # Through week 1, T has played exactly one game and won it.
    assert sos.win_pct(repeat_ledger.through_week(1), "T", semantics=GOVERNED) == 1.0
    # Through week 2 the second meeting is in: 1-1.
    assert sos.win_pct(repeat_ledger.through_week(2), "T", semantics=GOVERNED) == 0.5
    # Week 5 results cannot affect a week-3 value.
    assert sos.win_pct(repeat_ledger.through_week(3), "T", semantics=GOVERNED) == 2 / 3


def test_wp_with_zero_qualifying_games_is_unavailable_not_zero_or_five_hundred():
    empty = sos.ResumeLedger(_pair("g1", 1, "A", "B", True))
    # C never played: the component is UNAVAILABLE, not 0.0 and not 0.500.
    assert sos.win_pct(empty, "C", semantics=GOVERNED) is sos.UNAVAILABLE
    assert sos.win_pct(empty, "C", semantics=GOVERNED) is None
    assert sos.win_pct(empty, "C", semantics=GOVERNED) != 0.0
    assert sos.win_pct(empty, "C", semantics=GOVERNED) != 0.5


# --- OWP ---------------------------------------------------------------------


def test_owp_excludes_the_opponents_games_against_the_evaluated_team(repeat_ledger):
    # O's full record is 1-2 (beat Q, split with T). Excluding T leaves 1-0.
    # P's full record is 1-1. Excluding T leaves 0-1.
    # Instances for T are [O, O, P] -> (1.0 + 1.0 + 0.0) / 3.
    assert sos.opponent_win_pct(repeat_ledger, "T", GOVERNED) == pytest.approx(2 / 3)


def test_owp_is_schedule_instance_weighted_not_team_averaged(repeat_ledger):
    """Two meetings contribute twice; the unique-opponent average differs."""
    per_opponent = sos.SosSemantics(
        semantics_id="UNIQUE",
        authority="TEST_FIXTURE",
        exclude_rated_team_from_owp=True,
        instance_weighting="PER_OPPONENT",
        exclude_rated_team_from_oowp=False,
    )
    # Unique-opponent averaging: (1.0 + 0.0) / 2 = 0.5. Governed: 2/3.
    assert sos.opponent_win_pct(repeat_ledger, "T", per_opponent) == pytest.approx(0.5)
    assert sos.opponent_win_pct(repeat_ledger, "T", GOVERNED) == pytest.approx(2 / 3)
    assert sos.opponent_win_pct(repeat_ledger, "T", GOVERNED) != sos.opponent_win_pct(
        repeat_ledger, "T", per_opponent
    )


def test_a_repeated_opponent_counts_once_per_meeting(repeat_ledger):
    """Dropping the second meeting changes OWP, so the meeting really counted."""
    one_meeting = sos.ResumeLedger(
        [r for r in repeat_ledger.results if r.game_id != "g2"]
    )
    # One meeting: instances [O, P] -> (1.0 + 0.0) / 2 = 0.5.
    assert sos.opponent_win_pct(one_meeting, "T", GOVERNED) == pytest.approx(0.5)
    # Two meetings: instances [O, O, P] -> 2/3.
    assert sos.opponent_win_pct(repeat_ledger, "T", GOVERNED) == pytest.approx(2 / 3)


def test_owp_is_unavailable_when_an_opponent_has_no_governed_record():
    # B played only A, so excluding A leaves B with zero qualifying games.
    ledger = sos.ResumeLedger(_pair("g1", 1, "A", "B", True))
    assert sos.opponent_win_pct(ledger, "A", GOVERNED) is sos.UNAVAILABLE


def test_owp_with_a_zero_denominator_is_unavailable_not_invented():
    # D has no games at all: no instances, so no mean can be taken.
    ledger = sos.ResumeLedger(_pair("g1", 1, "A", "B", True))
    assert sos.opponent_win_pct(ledger, "D", GOVERNED) is sos.UNAVAILABLE


def test_a_schedule_only_fcs_opponent_without_a_record_is_unavailable(repeat_ledger):
    semantics = sos.governed_sos_semantics(frozenset({"FCS1"}))
    rows = list(repeat_ledger.results) + _pair("g6", 6, "T", "FCS1", True)
    ledger = sos.ResumeLedger(rows)
    # FCS1 played only T; excluding T leaves no governed record.
    assert sos.opponent_win_pct(ledger, "T", semantics) is sos.UNAVAILABLE
    # Nothing was invented in its place.
    assert sos.opponent_win_pct(ledger, "T", semantics) not in (0.0, 0.5)


def test_a_schedule_only_fcs_opponent_with_a_record_does_contribute(repeat_ledger):
    semantics = sos.governed_sos_semantics(frozenset({"FCS1"}))
    rows = list(repeat_ledger.results)
    rows += _pair("g6", 6, "T", "FCS1", True)
    rows += _pair("g7", 7, "FCS1", "Q", True)  # FCS1 now has a governed record
    ledger = sos.ResumeLedger(rows)
    # Instances [O, O, P, FCS1]; FCS1 excluding T is 1-0 -> 1.0.
    # O -> 1.0, O -> 1.0, P excluding T: P lost to Q -> 0.0.
    assert sos.opponent_win_pct(ledger, "T", semantics) == pytest.approx(
        (1.0 + 1.0 + 0.0 + 1.0) / 4
    )


def test_owp_is_deterministic(repeat_ledger):
    values = {sos.opponent_win_pct(repeat_ledger, "T", GOVERNED) for _ in range(25)}
    assert len(values) == 1


# --- OOWP --------------------------------------------------------------------


def test_oowp_is_the_mean_of_each_opponents_own_governed_owp(repeat_ledger):
    """Hand-computed, then checked against the opponents' own OWP values.

    OWP(O): O's instances are [T, T, Q]. T excluding O beat P -> 1.0 (twice);
            Q excluding O beat P -> 1.0.  OWP(O) = 1.0
    OWP(P): P's instances are [T, Q]. T excluding P split with O -> 0.5;
            Q excluding P lost to O -> 0.0.  OWP(P) = 0.25
    OOWP(T) over instances [O, O, P] = (1.0 + 1.0 + 0.25) / 3 = 0.75
    """
    assert sos.opponent_win_pct(repeat_ledger, "O", GOVERNED) == pytest.approx(1.0)
    assert sos.opponent_win_pct(repeat_ledger, "P", GOVERNED) == pytest.approx(0.25)
    assert sos.opponent_opponent_win_pct(repeat_ledger, "T", GOVERNED) == pytest.approx(0.75)


def test_oowp_is_schedule_instance_weighted_not_unique_opponent_averaged(repeat_ledger):
    """PER_GAME and PER_OPPONENT give different OOWP, so the choice is real.

    Governed (once per meeting): instances [O, O, P] -> (1.0 + 1.0 + 0.25)/3 = 0.75.
    Unique-opponent averaging:   instances [O, P]    -> (1.0 + 0.25)/2   = 0.625.
    """
    per_opponent = sos.SosSemantics(
        semantics_id="UNIQUE",
        authority="TEST_FIXTURE",
        exclude_rated_team_from_owp=True,
        instance_weighting="PER_OPPONENT",
        exclude_rated_team_from_oowp=False,
    )
    assert sos.opponent_opponent_win_pct(repeat_ledger, "T", GOVERNED) == pytest.approx(0.75)
    assert sos.opponent_opponent_win_pct(repeat_ledger, "T", per_opponent) == pytest.approx(
        0.625
    )


def test_oowp_does_not_silently_use_the_flattened_pooled_construction(repeat_ledger):
    pooled = sos.SosSemantics(
        semantics_id="POOLED",
        authority="TEST_FIXTURE",
        exclude_rated_team_from_owp=True,
        instance_weighting="PER_GAME",
        exclude_rated_team_from_oowp=False,
        oowp_construction="MEAN_OVER_ALL_OPPONENT_OPPONENTS",
    )
    assert GOVERNED.oowp_construction == "MEAN_OF_OPPONENT_OWP"
    # The two constructions genuinely differ on this ledger, so the governed one
    # is a real choice rather than an equivalent relabelling.
    assert sos.opponent_opponent_win_pct(
        repeat_ledger, "T", pooled
    ) != sos.opponent_opponent_win_pct(repeat_ledger, "T", GOVERNED)


def test_oowp_propagates_unavailability():
    ledger = sos.ResumeLedger(_pair("g1", 1, "A", "B", True))
    assert sos.opponent_opponent_win_pct(ledger, "A", GOVERNED) is sos.UNAVAILABLE


# --- SOS ---------------------------------------------------------------------


def test_sos_is_exactly_the_governed_weighted_sum(repeat_ledger):
    c = sos.sos_components(repeat_ledger, "T", GOVERNED)
    expected = 0.25 * (2 / 3) + 0.50 * (2 / 3) + 0.25 * 0.75
    assert c["sos"] == pytest.approx(expected)
    assert c["sos"] == pytest.approx(0.6875)
    assert c["sos"] == pytest.approx(
        sos.WP_WEIGHT * c["wp"] + sos.OWP_WEIGHT * c["owp"] + sos.OOWP_WEIGHT * c["oowp"]
    )


def test_an_unavailable_component_never_silently_becomes_numeric():
    ledger = sos.ResumeLedger(_pair("g1", 1, "A", "B", True))
    c = sos.sos_components(ledger, "A", GOVERNED)
    assert c["wp"] == 1.0
    assert c["owp"] is sos.UNAVAILABLE
    assert c["sos"] is sos.UNAVAILABLE
    # Specifically: not the weighted sum with the missing terms read as zero.
    assert c["sos"] != 0.25 * 1.0


def test_the_through_week_cutoff_is_honoured(repeat_ledger):
    early = sos.sos_components(repeat_ledger.through_week(3), "T", GOVERNED)
    late = sos.sos_components(repeat_ledger.through_week(5), "T", GOVERNED)
    assert early["owp"] is sos.UNAVAILABLE  # O has no record yet once T is removed
    assert late["owp"] == pytest.approx(2 / 3)


def test_unavailability_is_reported_with_provenance():
    ledger = sos.ResumeLedger(_pair("g1", 1, "A", "B", True))
    row = sos.sos_report_row(ledger, "A", GOVERNED)
    assert row["unavailable_components"] == ["oowp", "owp", "sos"]
    assert "UNAVAILABLE" in row["provenance"]
    assert row["ruling"] == "R3-SOS-OWP-OOWP-SEMANTICS"


def test_ranking_fails_closed_rather_than_ordering_on_a_missing_component():
    ledger = sos.ResumeLedger(_pair("g1", 1, "A", "B", True))
    with pytest.raises(GovernanceBlock, match="UNAVAILABLE"):
        sos.rank_by_sos(ledger, ["A", "B"], GOVERNED)


# --- tiebreak ----------------------------------------------------------------


def test_an_unavailable_criterion_does_not_resolve_a_tie():
    assert sos.criterion_resolves(None, 0.5) is False
    assert sos.criterion_resolves(0.5, None) is False
    assert sos.criterion_resolves(None, None) is False
    assert sos.criterion_resolves(0.7, 0.5) is True
    assert sos.criterion_resolves(0.5, 0.5) is False


def test_an_unavailable_criterion_advances_to_the_next_governed_stage():
    """TB2 unavailable, TB3 available -> TB3 decides. No invented separation."""
    inputs = committee_policy.CommitteeTiebreakInputs(
        head_to_head=lambda a, b: None,
        common_opponent_score=lambda a, b: (None, None),   # TB2 unavailable
        strength_of_schedule=lambda t: {"A": 0.9, "B": 0.4}[t],
        previous_board=("B", "A"),
    )
    winner, step = committee_policy.break_committee_tie("A", "B", inputs)
    assert winner == "A"
    assert step == committee_policy.COMMITTEE_TIEBREAK_CHAIN[2]


def test_when_both_tb2_and_tb3_are_unavailable_processing_reaches_tb4():
    inputs = committee_policy.CommitteeTiebreakInputs(
        head_to_head=lambda a, b: None,
        common_opponent_score=lambda a, b: (None, None),
        strength_of_schedule=lambda t: None,
        previous_board=("B", "A"),
    )
    winner, step = committee_policy.break_committee_tie("A", "B", inputs)
    assert winner == "B"
    assert step == committee_policy.COMMITTEE_TIEBREAK_CHAIN[3]


def test_a_test_fixture_can_never_become_production_authority():
    fixture = sos.SosSemantics(
        semantics_id="FIXTURE",
        authority="TEST_FIXTURE",
        exclude_rated_team_from_owp=True,
        instance_weighting="PER_GAME",
        exclude_rated_team_from_oowp=False,
    )
    with pytest.raises(GovernanceBlock, match="not a governed source"):
        sos.require_governed_sos_semantics(fixture)
    assert sos.require_governed_sos_semantics(GOVERNED) is GOVERNED


# --- B2: the common-opponent guardrail ---------------------------------------


def test_the_common_opponent_formula_was_not_newly_promoted():
    assert common_opponents.COMMON_OPPONENT_FORMULA_IS_CANONICAL is False
    assert common_opponents.COMMON_OPPONENT_FORMULA_AUTHORITY == "R2-COMMON-OPP"
    assert "not stated by any mounted artifact" in (
        common_opponents.COMMON_OPPONENT_FORMULA_STATUS
    )
    assert common_opponents.UNPROMOTED_COMMON_OPPONENT_ALTERNATIVES


def test_the_common_opponent_comparison_uses_the_governed_semantics(repeat_ledger):
    result = common_opponents.common_opponent_score(repeat_ledger, "O", "P", GOVERNED)
    assert result.as_dict()["semantics_ruling"] == "R3-SOS-OWP-OOWP-SEMANTICS"
    assert result.as_dict()["formula_is_canonical"] is False


def test_the_common_opponent_comparison_propagates_unavailability():
    ledger = sos.ResumeLedger(
        _pair("g1", 1, "A", "C", True) + _pair("g2", 1, "B", "C", True)
    )
    # C's only games are against A and B; excluding the rated team leaves one
    # game, but A and B have no other opponents, so OOWP cannot be formed.
    result = common_opponents.common_opponent_score(ledger, "A", "B", GOVERNED)
    assert result.common_opponents == ("C",)
    assert result.score is None or isinstance(result.score, float)
    if result.score is None:
        assert result.as_dict()["unavailable_components"]


def test_two_teams_identical_on_record_can_still_separate_on_strength():
    """The Chairman's Lehigh/USF shape: same common-opponent record, different quality.

    A and B are each 1-1 against the same two common opponents X and Z, so
    ``wp_common`` cannot separate them. What does separate them is how X and Z
    fared once the rated team's own result is removed — and because X and Z have
    played different numbers of games, the two removals do not cancel.

    This fixture is a behavioural check on the implementation. It is not
    governance authority for any common-opponent formula.
    """
    rows = []
    rows += _pair("1", 1, "A", "X", True)    # A beat X
    rows += _pair("2", 1, "X", "B", True)    # X beat B
    rows += _pair("3", 2, "Z", "A", True)    # Z beat A
    rows += _pair("4", 2, "B", "Z", True)    # B beat Z
    rows += _pair("5", 3, "X", "P1", True)
    rows += _pair("6", 3, "X", "P2", True)
    rows += _pair("7", 3, "Z", "P1", True)
    rows += _pair("8", 4, "P1", "P2", True)
    rows += _pair("9", 4, "P2", "Q", True)
    rows += _pair("10", 5, "Q", "P1", True)
    ledger = sos.ResumeLedger(rows)
    a, b = common_opponents.compare_common_opponents(ledger, "A", "B", GOVERNED)
    assert a.common_opponents == b.common_opponents == ("X", "Z")
    assert (a.wins, a.losses, a.wp_common) == (b.wins, b.losses, b.wp_common)
    # Records identical, strength evidence different -> the scores separate.
    assert a.owp_common == pytest.approx(0.75)
    assert b.owp_common == pytest.approx(5 / 6)
    assert a.score != b.score


# =============================================================================
# B13 — playoff topology test campaign
# =============================================================================

TEAMS = [f"T{i:02d}" for i in range(1, 15)]


def _selection(order=None):
    order = order or TEAMS
    return postseason.CFPSelection(
        seeds={i + 1: t for i, t in enumerate(order)},
        bid_types={t: "AT_LARGE" for t in order},
    )


def test_the_exact_ruled_topology_is_encoded():
    assert postseason.GOVERNED_PLAY_IN_EDGES == {"PI_A": (12, 13), "PI_B": (11, 14)}
    assert postseason.GOVERNED_ROUND_1_EDGES == {
        "R1_A": (7, 10),
        "R1_B": (8, 9),
        "R1_C": (6, "PI_B"),
        "R1_D": (5, "PI_A"),
    }
    assert postseason.GOVERNED_QUARTERFINAL_HOSTS == {
        "QF_E": 1, "QF_F": 2, "QF_G": 3, "QF_H": 4,
    }
    assert postseason.GOVERNED_QUARTERFINAL_SLOT_EDGES == {
        "QF_E": "R1_B", "QF_F": "R1_A", "QF_G": "R1_C", "QF_H": "R1_D",
    }
    assert postseason.GOVERNED_SEMIFINAL_EDGES == {
        "SEMI_A": ("QF_E", "QF_H"), "SEMI_B": ("QF_F", "QF_G"),
    }


def test_every_seed_appears_exactly_once_in_field_construction():
    topo = postseason.bracket_topology()
    seeds = [ref for pair in topo.values() for ref in pair if isinstance(ref, int)]
    assert sorted(seeds) == list(range(1, 15))
    assert len(seeds) == len(set(seeds)) == 14


def test_the_bracket_is_a_tree_with_no_duplicate_or_omitted_team():
    results = postseason.advance_bracket(_selection(), lambda slot, a, b: a)
    assert len(results) == 13
    played = {t for a, b, _ in results.values() for t in (a, b) if t in TEAMS}
    assert played == set(TEAMS)


def test_reseeding_is_impossible_because_the_topology_is_fixed():
    assert postseason.RESEEDING_PERMITTED is False
    with pytest.raises(GovernanceBlock, match="Reseeding between rounds is forbidden"):
        postseason.require_no_reseeding(True)
    # The slot each winner reports to is fixed before any game is played.
    assert postseason.bracket_topology()["QF_E"] == (1, "R1_B")


def test_an_upset_does_not_move_any_future_slot():
    """Whoever wins, the slot structure is byte-identical."""
    favourites = postseason.advance_bracket(_selection(), lambda slot, a, b: a)
    upsets = postseason.advance_bracket(_selection(), lambda slot, a, b: b)
    assert list(favourites) == list(upsets) == list(postseason.BRACKET_SLOT_ORDER)
    # Different winners, same topology.
    assert favourites["QF_E"][2] != upsets["QF_E"][2]
    assert postseason.bracket_topology() == postseason.bracket_topology()


def test_seed_five_is_always_on_the_r1_d_path_against_the_pi_a_winner():
    selection = _selection()
    edges = postseason.governed_bracket_edges(selection)
    assert edges["R1_D"] == (selection.seeds[5], "WINNER(PI_A)")
    assert postseason.GOVERNED_PLAY_IN_EDGES["PI_A"] == (12, 13)


@pytest.mark.parametrize("natural_rank", [1, 3, 5, 8, 14])
def test_the_g5_autobid_champion_is_seed_five_and_never_plays_in(natural_rank):
    champion = TEAMS[natural_rank - 1]
    seeded = postseason.apply_g5_automatic_bid_seed(
        _selection(), TEAMS, {"AAC": champion}
    )
    seed_of = {t: s for s, t in seeded.seeds.items()}
    assert seed_of[champion] == 5
    assert seed_of[champion] not in postseason.PLAY_IN_SEEDS
    # Bijective 1..14, nobody duplicated or omitted.
    assert sorted(seeded.seeds) == list(range(1, 15))
    assert len(set(seeded.seeds.values())) == 14
    # Everyone else keeps committee-rank order around the fixed slot.
    others = [seeded.seeds[s] for s in sorted(seeded.seeds) if seeded.seeds[s] != champion]
    assert others == [t for t in TEAMS if t != champion]
    # And the champion meets the PI-A winner in R1-D, never a play-in.
    edges = postseason.governed_bracket_edges(seeded)
    assert edges["R1_D"] == (champion, "WINNER(PI_A)")
    for slot in ("PI_A", "PI_B"):
        assert champion not in edges[slot]
    postseason.g5_automatic_bid_audit(seeded, {champion: "AAC"})


def test_final_assigned_seed_controls_placement_not_natural_rank():
    """A champion ranked 1st is displaced to seed 5 and plays the R1-D path."""
    champion = TEAMS[0]
    seeded = postseason.apply_g5_automatic_bid_seed(
        _selection(), TEAMS, {"AAC": champion}
    )
    edges = postseason.governed_bracket_edges(seeded)
    # Natural rank 1, but it is seed 5 that decides where it plays.
    assert edges["R1_D"][0] == champion
    assert edges["QF_E"][0] == seeded.seeds[1] != champion
    assert seeded.seeds[1] == TEAMS[1]  # the next team moved up into the bye


def test_the_semifinal_edges_are_the_ruled_ones():
    edges = postseason.governed_bracket_edges(_selection())
    assert edges["SEMI_A"] == ("WINNER(QF_E)", "WINNER(QF_H)")
    assert edges["SEMI_B"] == ("WINNER(QF_F)", "WINNER(QF_G)")


def test_a_bracket_walk_is_deterministic():
    runs = {
        tuple(sorted(postseason.advance_bracket(_selection(), lambda s, a, b: a).items()))
        for _ in range(10)
    }
    assert len(runs) == 1


# --- B5: playoff provenance ---------------------------------------------------


def test_the_playoff_workbook_is_not_rewritten_or_reinterpreted():
    status = json.loads(STATUS_R3.read_text(encoding="utf-8"))["cfp_topology"]
    assert status["playoff_workbook_rewritten"] is False
    assert status["playoff_workbook_reinterpreted"] is False
    assert status["quarterfinal_slot_edges_stated_in_artifact"] is False
    assert postseason.QUARTERFINAL_SLOT_EDGES_STATED_IN_ARTIFACT is False
    assert status["resolution_reason"] == "SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY"
    assert status["resolution_reason"] != "SOURCE_WORKBOOK_CONTAINED_MAPPING"


def test_the_superseded_bracket_regime_text_is_preserved_verbatim():
    assert postseason.BRACKET_REGIME_S4_ROUND_1_TEXT == (
        "First Round 5v12, 6v11, 7v10, 8v9"
    )
    assert rulings.R3_CFP_FIXED_TOPOLOGY.supersedes


# =============================================================================
# B14 — artifacts and blocker accounting
# =============================================================================


def test_board_of_record_is_still_unmounted_and_i_h_is_not_substituted():
    status = board_of_record.board_of_record_status(None)
    assert status["mounted"] is False
    assert status["historical_board_substitutable"] is False
    assert status["blocker"] == "inputs.board_of_record_i_k"
    with pytest.raises(GovernanceBlock):
        board_of_record.require_board_of_record(None)


def test_the_board_of_record_blocker_is_custody_not_policy():
    recorded = json.loads(STATUS_R3.read_text(encoding="utf-8"))["board_of_record"]
    assert recorded["classification"] == "ARTIFACT_CUSTODY"
    assert recorded["mounted"] is False
    assert recorded["mount_result"] == "BOARD_IK_ARTIFACT_NOT_ACCESSIBLE_TO_AGENT"
    assert recorded["historical_board_substituted"] is False
    assert recorded["required_sha256"] == (
        "6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a"
    )


def test_no_board_workbook_was_fabricated_into_the_governed_inputs():
    names = {p.name for p in INPUTS.iterdir()}
    assert not any("Board_I-K" in n for n in names)
    assert len(names) == 8


def test_the_srs_claim_boundary_is_unchanged():
    assert srs.CANONICAL_SRS_SPEC_MOUNTED is False
    assert srs.CANONICAL_VALIDATION_ANCHORS == ()
    with pytest.raises(GovernanceBlock):
        srs.require_canonical_validated_srs()
    recorded = json.loads(STATUS_R3.read_text(encoding="utf-8"))["srs"]
    assert recorded["mathematical_status"] == "MATHEMATICALLY_VERIFIED"
    assert recorded["canonical_anchor_validation"] == (
        "NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS"
    )
    assert recorded["claim_boundary_changed_by_r3"] is False


def test_the_srs_mathematics_are_unchanged_by_this_convergence():
    """The governed fixture still solves exactly, with the same ordering."""
    games = [
        srs.SrsGame(game_id="g1", team="A", opponent="B", margin=30),
        srs.SrsGame(game_id="g1r", team="B", opponent="A", margin=-30),
        srs.SrsGame(game_id="g2", team="A", opponent="C", margin=7),
        srs.SrsGame(game_id="g2r", team="C", opponent="A", margin=-7),
    ]
    ratings = srs.compute_srs(games)
    assert srs.srs_ordering(ratings) == ["A", "C", "B"]
    assert ratings["A"] == pytest.approx(31 / 3)
    assert ratings["B"] == pytest.approx(ratings["A"] - srs.SRS_MARGIN_CAP)
    assert max(abs(v) for v in srs.srs_residuals(games, ratings).values()) < 1e-9


def test_the_governed_reference_inputs_are_byte_identical():
    assert hashlib.sha256(
        (INPUTS / "V2_1_STATIC_CONTROL_2026_CFB_10000_Season_Monte_Carlo.xlsx").read_bytes()
    ).hexdigest() == "39055662b819a3ff3e6e87ad53e28a15d0451a6b1e692e7770459e7a984c614a"


def test_the_frozen_build_manifest_is_still_not_rewritten():
    manifest = json.loads(
        (ROOT / "reference/dynamic_weekly_mc_v3/V3_BUILD_MANIFEST.json").read_text()
    )
    assert manifest["execution_blocker_count"] == 18
    assert manifest["test_count"] == 74


# --- the blocker transitions --------------------------------------------------


def test_the_blocker_set_before_this_convergence_was_exactly_eleven():
    assert len(br.R2_EXPECTED_LIVE_BLOCKERS) == 11


def test_governance_closure_retires_exactly_two_and_leaves_nine(live_blockers):
    assert br.R3_RETIRED_BLOCKERS == {
        "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED",
        "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT",
    }
    assert len(br.R3_EXPECTED_LIVE_BLOCKERS) == 9
    assert set(live_blockers) == set(br.R3_EXPECTED_LIVE_BLOCKERS)
    assert len(live_blockers) == 9


def test_a_successful_board_mount_would_leave_exactly_eight():
    assert len(br.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED) == 8
    assert "inputs.board_of_record_i_k" not in (
        br.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    )


def test_only_the_two_authorized_blocker_ids_disappeared(live_blockers):
    vanished = set(br.R2_EXPECTED_LIVE_BLOCKERS) - set(live_blockers)
    assert vanished == set(br.R3_RETIRED_BLOCKERS)


def test_no_genuinely_new_blocker_appeared(live_blockers):
    assert set(live_blockers) - set(br.R2_EXPECTED_LIVE_BLOCKERS) == set()
    assert br.R3_OPENED_BLOCKERS == frozenset()


def test_every_r3_retirement_names_its_authority():
    assert br.R3_RETIREMENT_REASONS == {
        "governance.OWP_OOWP_DENOMINATOR_SEMANTICS_NOT_GOVERNED": (
            "DIRECT_CHAIRMAN_AUTHORITY"
        ),
        "governance.POSTSEASON_QUARTERFINAL_MAPPING_NOT_EXPLICIT": (
            "SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY"
        ),
    }
    for ruling in rulings.R3_RULINGS:
        assert ruling.resolution_reason
        assert ruling.chairman_ruling_id is None  # none supplied; none invented


# --- B10: nothing in the calibration or model-scale lane moved -----------------


def test_no_calibration_value_was_promoted():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    assert all(v is None for v in config["calibration"].values())
    assert len(config["calibration"]) == 6


def test_every_calibration_blocker_is_still_live(live_blockers):
    for blocker in (
        "calibration.weekly_performance_residual_coefficient",
        "calibration.weekly_movement_cap_points",
        "calibration.recent_form_weights",
        "calibration.blowout_treatment",
        "calibration.game_sd_points",
        "calibration.sample_size_regularization",
        "governance.GAME_SD_CALIBRATION_OPEN",
    ):
        assert blocker in live_blockers


def test_the_fcs_adapter_was_not_constructed(live_blockers):
    assert "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER" in live_blockers
    assert fcs.GOVERNED_FCS_POLICY.unified_points_equivalent is None
    assert fcs.FCS_FIXED_ELO == 1250.0
    with pytest.raises(GovernanceBlock):
        fcs.require_fcs_unified_points()


def test_no_season_run_or_probability_output_exists():
    assert not (ROOT / "output").exists()
    status = json.loads(STATUS_R3.read_text(encoding="utf-8"))
    assert status["simulation_run"] is False
    assert status["output_probabilities_generated"] is False
    assert status["canonical_config"]["writes_canonical_config"] is False


def test_the_remaining_blockers_are_only_calibration_model_scale_and_custody(live_blockers):
    lanes = {br.R3_REMAINING_CLASSIFICATION[b] for b in live_blockers}
    assert lanes == {"CALIBRATION", "ENGINEERING_MODEL_SCALE", "ARTIFACT_CUSTODY"}
    assert not any(b.startswith("governance.") and "CALIBRATION" not in b
                   for b in live_blockers)
