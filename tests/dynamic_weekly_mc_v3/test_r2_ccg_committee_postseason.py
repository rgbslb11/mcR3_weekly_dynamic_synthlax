"""R2 convergence: seven CCGs, committee product and tiebreak, playoff topology."""

from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import ccg, committee_policy, ordering, postseason
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.inputs import load_schedule
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.postseason import (
    CFPSelection,
    select_governed_14_team_cfp,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"


def _schedule():
    return load_schedule(V3Config.from_json(CONFIG).inputs.schedule_xlsx)


def _inputs(h2h=None, rr=None, board=None) -> ccg.CcgTiebreakInputs:
    return ccg.CcgTiebreakInputs(
        head_to_head=h2h or (lambda a, b: None),
        mini_round_robin=rr or (lambda ids: list(ids)),
        last_board_before_championship_saturday=board,
    )


def _rec(sid, w, losses, division=None):
    return ccg.ConferenceRecord(sid, w, losses, division)


# --- seven CCGs --------------------------------------------------------------


def test_schedule_carries_exactly_seven_governed_ccgs():
    report = ccg.verify_seven_ccgs(_schedule())
    assert report["ccg_count"] == 7
    assert report["conferences"] == [
        "ACC", "American", "Big 12", "Big Ten", "Mountain West", "Pac-12", "SEC",
    ]


def test_atlantic_eight_and_ecl_play_no_ccg():
    assert ccg.NO_CCG_CONFERENCES == ("Atlantic-8", "ECL")
    for conf in ccg.NO_CCG_CONFERENCES:
        assert conf not in ccg.CCG_CONFERENCES
        with pytest.raises(GovernanceBlock, match="no conference championship game"):
            ccg.select_ccg_participants(conf, [_rec("A", 8, 0), _rec("B", 7, 1)], _inputs())


# --- CCG participant selection ----------------------------------------------


def test_participants_are_the_two_best_conference_win_percentage_teams():
    records = [_rec("A", 8, 1), _rec("B", 7, 2), _rec("C", 6, 3)]
    result = ccg.select_ccg_participants("SEC", records, _inputs())
    assert (result.seat_1, result.seat_2) == ("A", "B")


def test_conference_win_percentage_is_used_not_overall_record():
    """B has the better conference rate; a team with more total wins does not qualify."""
    records = [_rec("A", 6, 0), _rec("B", 8, 1), _rec("C", 5, 4)]
    result = ccg.select_ccg_participants("ACC", records, _inputs())
    assert result.seat_1 == "A"  # 1.000 conference beats .889 conference
    assert result.seat_2 == "B"


def test_ccg_tb1_head_to_head_resolves_a_two_team_band():
    records = [_rec("A", 7, 1), _rec("B", 7, 1), _rec("C", 5, 3)]
    result = ccg.select_ccg_participants(
        "Big Ten", records, _inputs(h2h=lambda a, b: "B" if {a, b} == {"A", "B"} else None)
    )
    assert result.seat_1 == "B"
    assert result.steps[0] == "seat_1:CCG-TB1_HEAD_TO_HEAD"


def test_ccg_tb2_mini_round_robin_resolves_a_three_team_band():
    records = [_rec("A", 7, 1), _rec("B", 7, 1), _rec("C", 7, 1)]
    result = ccg.select_ccg_participants(
        "Big 12", records,
        _inputs(
            rr=lambda ids: ["C"] if len(ids) == 3 else list(ids),
            h2h=lambda a, b: "A" if {a, b} == {"A", "B"} else None,
        ),
    )
    assert result.seat_1 == "C"
    assert result.steps[0] == "seat_1:CCG-TB2_MINI_ROUND_ROBIN"
    # The chain runs again for the second seat rather than once at the top.
    assert result.seat_2 == "A"
    assert result.steps[1] == "seat_2:CCG-TB1_HEAD_TO_HEAD"


def test_ccg_tb3_uses_the_last_board_before_championship_saturday():
    records = [_rec("A", 7, 1), _rec("B", 7, 1), _rec("C", 7, 1)]
    result = ccg.select_ccg_participants(
        "Pac-12", records, _inputs(board=("B", "A", "C"))
    )
    assert result.seat_1 == "B"
    assert result.steps[0] == "seat_1:CCG-TB3_LAST_BOARD_BEFORE_CHAMPIONSHIP_SATURDAY"


def test_the_chain_is_applied_again_to_fill_the_second_seat():
    records = [_rec("A", 8, 0), _rec("B", 6, 2), _rec("C", 6, 2)]
    result = ccg.select_ccg_participants(
        "Mountain West", records,
        _inputs(h2h=lambda a, b: "C" if {a, b} == {"B", "C"} else None),
    )
    assert result.seat_1 == "A"
    assert result.seat_2 == "C"
    assert result.steps == ("seat_1:NO_TIE", "seat_2:CCG-TB1_HEAD_TO_HEAD")


def test_ccg_tb3_fails_closed_without_a_board():
    records = [_rec("A", 7, 1), _rec("B", 7, 1), _rec("C", 7, 1)]
    with pytest.raises(GovernanceBlock, match="Championship Saturday"):
        ccg.select_ccg_participants("SEC", records, _inputs())


# --- AAC division carve-out --------------------------------------------------


def test_aac_participants_are_the_two_division_winners():
    records = [
        _rec("NAVY", 7, 1, "American"), _rec("ARMY", 6, 2, "American"),
        _rec("TLN", 7, 1, "Athletic"), _rec("MEM", 6, 2, "Athletic"),
    ]
    result = ccg.select_aac_ccg_participants(records, _inputs(), {})
    assert (result.seat_1, result.seat_2) == ("NAVY", "TLN")
    assert result.conference == "American"


def test_aac_division_ties_use_the_same_ccg_chain():
    records = [
        _rec("NAVY", 7, 1, "American"), _rec("ARMY", 7, 1, "American"),
        _rec("TLN", 7, 1, "Athletic"), _rec("MEM", 5, 3, "Athletic"),
    ]
    result = ccg.select_aac_ccg_participants(
        records, _inputs(h2h=lambda a, b: "ARMY" if {a, b} == {"NAVY", "ARMY"} else None), {}
    )
    assert result.seat_1 == "ARMY"
    assert result.steps[0] == "American:CCG-TB1_HEAD_TO_HEAD"


def test_the_aac_may_not_be_selected_through_the_non_division_path():
    with pytest.raises(GovernanceBlock, match="division carve-out"):
        ccg.select_ccg_participants("American", [_rec("A", 8, 0), _rec("B", 7, 1)], _inputs())


def test_an_aac_team_without_a_governed_division_is_rejected():
    with pytest.raises(InputValidationError, match="no governed division"):
        ccg.select_aac_ccg_participants([_rec("NAVY", 7, 1)], _inputs(), {})


# --- committee product and tiebreak -----------------------------------------


def test_committee_tiebreak_policy_replaces_the_retired_strength_source():
    assert committee_policy.require_committee_tiebreak_policy(
        "DETERMINISTIC_COMMITTEE_TIEBREAK_CHAIN_R2"
    )
    for retired in committee_policy.RETIRED_STRENGTH_SOURCE_VALUES:
        with pytest.raises(GovernanceBlock):
            committee_policy.require_committee_tiebreak_policy(retired)
        with pytest.raises(GovernanceBlock, match="retired concept"):
            committee_policy.reject_retired_strength_source(retired)
    committee_policy.reject_retired_strength_source(None)


def _tb(h2h=None, common=None, sos_fn=None, previous=None):
    return committee_policy.CommitteeTiebreakInputs(
        head_to_head=h2h or (lambda a, b: None),
        common_opponent_score=common or (lambda a, b: (0.0, 0.0)),
        strength_of_schedule=sos_fn or (lambda t: 0.0),
        previous_board=previous,
    )


def test_committee_tiebreak_walks_tb1_to_tb4_in_order():
    assert committee_policy.break_committee_tie(
        "A", "B", _tb(h2h=lambda a, b: "B")
    ) == ("B", "COMMITTEE-TB1_HEAD_TO_HEAD")
    assert committee_policy.break_committee_tie(
        "A", "B", _tb(common=lambda a, b: (0.9, 0.4))
    ) == ("A", "COMMITTEE-TB2_COMMON_OPPONENT_PERFORMANCE")
    assert committee_policy.break_committee_tie(
        "A", "B", _tb(sos_fn=lambda t: 0.7 if t == "B" else 0.2)
    ) == ("B", "COMMITTEE-TB3_STRENGTH_OF_SCHEDULE")
    assert committee_policy.break_committee_tie(
        "A", "B", _tb(previous=("B", "A"))
    ) == ("B", "COMMITTEE-TB4_PREVIOUS_WEEK_BOARD")


def test_first_november_board_tb4_fallback_is_the_only_edge_case_left_open():
    with pytest.raises(GovernanceBlock, match=committee_policy.FIRST_BOARD_TB4_BLOCKER):
        committee_policy.break_committee_tie("A", "B", _tb(), is_first_november_board=True)
    # Any other week without a board is a plain missing-input error, not that gate.
    with pytest.raises(GovernanceBlock, match="none was supplied"):
        committee_policy.break_committee_tie("A", "B", _tb())


def test_weekly_product_publishes_a_top_25_and_a_bracket_only():
    ordering_list = [f"T{i:02d}" for i in range(1, 31)]
    product = committee_policy.weekly_committee_product(
        as_of_week=10,
        published_on="2026-11-03",
        ordering=ordering_list,
        bracket={"BYE_1": "T01", "PLAYIN_G1": ("T12", "T13")},
    )
    assert len(product.top_25) == 25
    payload = product.as_dict()
    assert set(payload) == {"as_of_week", "published_on", "top_25", "bracket"}
    committee_policy.assert_no_hidden_numbers(payload)


def test_weekly_product_refuses_a_raw_strength_or_score_leak():
    for leaked in ("strength_points", "committee_score", "power_index", "sos"):
        with pytest.raises(GovernanceBlock, match="raw numeric"):
            committee_policy.assert_no_hidden_numbers({"top_25": [], leaked: 0.9})


def test_weekly_product_does_not_publish_before_november_first():
    with pytest.raises(GovernanceBlock, match="2026-11-01"):
        committee_policy.weekly_committee_product(
            as_of_week=5, published_on="2026-10-25",
            ordering=[f"T{i:02d}" for i in range(1, 31)], bracket={},
        )


# --- A8 / ECL ----------------------------------------------------------------


def _board(order, ccgs=True, seeded=False):
    return ordering.PostCcgBoard(order=tuple(order), ccgs_complete=ccgs, g5_seeding_applied=seeded)


def test_a8_and_ecl_champions_are_determined_independently():
    assert ordering.a8_ecl_ordering_resolved() is True
    champ, step = ordering.resolve_standings_champion(
        "Atlantic-8", ["A8_X"],
        head_to_head=lambda a, b: None,
        common_opponent_score=lambda a, b: (0.0, 0.0),
        post_ccg_board=None,
    )
    assert (champ, step) == ("A8_X", "NO_TIE")


def test_a8_ecl_tb1_then_tb2_then_tb3():
    h2h = lambda a, b: "P" if {a, b} == {"P", "Q"} else None  # noqa: E731
    assert ordering.resolve_standings_champion(
        "ECL", ["P", "Q"], head_to_head=h2h,
        common_opponent_score=lambda a, b: (0.0, 0.0), post_ccg_board=None,
    ) == ("P", "A8_ECL-TB1_HEAD_TO_HEAD")

    assert ordering.resolve_standings_champion(
        "ECL", ["P", "Q"], head_to_head=lambda a, b: None,
        common_opponent_score=lambda a, b: (0.8, 0.1) if a == "Q" else (0.1, 0.8),
        post_ccg_board=None,
    ) == ("Q", "A8_ECL-TB2_COMMON_OPPONENT_PERFORMANCE")

    assert ordering.resolve_standings_champion(
        "Atlantic-8", ["P", "Q"], head_to_head=lambda a, b: None,
        common_opponent_score=lambda a, b: (0.5, 0.5),
        post_ccg_board=_board(["Q", "P"]),
    ) == ("Q", "A8_ECL-TB3_POST_CCG_BOARD_BEFORE_G5_SEEDING")


def test_tb3_board_must_be_post_ccg_and_pre_g5_seeding():
    with pytest.raises(GovernanceBlock, match="after the seven CCGs"):
        ordering.require_post_ccg_board(_board(["A"], ccgs=False))
    with pytest.raises(GovernanceBlock, match="before G5 automatic-bid seeding"):
        ordering.require_post_ccg_board(_board(["A"], seeded=True))


def test_a8_and_ecl_are_never_compared_with_each_other():
    with pytest.raises(GovernanceBlock, match="not a standings-only conference"):
        ordering.resolve_standings_champion(
            "SEC", ["A", "B"], head_to_head=lambda a, b: None,
            common_opponent_score=lambda a, b: (0.0, 0.0), post_ccg_board=None,
        )
    assert ordering.resolution_as_dict()["cross_conference_comparison_permitted"] is False


def test_the_historical_circular_reading_is_preserved_as_superseded():
    resolution = ordering.resolution_as_dict()
    assert resolution["historical_cycle_status"] == "SUPERSEDED_BY_R2_CAUSAL_SEQUENCING"
    assert resolution["historical_cycle_path"][0] == "A8_ECL_CHAMPION"
    assert resolution["causal_sequence"].index("COMPUTE_POST_CCG_COMMITTEE_BOARD") < (
        resolution["causal_sequence"].index("APPLY_G5_AUTOMATIC_BID_SEEDING")
    )


# --- playoff topology --------------------------------------------------------

ORDER = [
    "SEC_C", "B10_C", "B12_C", "ACC_C", "X1", "ND", "P12_C", "X2", "X3", "X4",
    "X5", "X6", "X7", "X8", "X9", "MW_C", "AAC_C", "A8_C", "ECL_C", "X10",
]
CHAMPS = {
    "SEC": "SEC_C", "Big Ten": "B10_C", "Big 12": "B12_C", "ACC": "ACC_C",
    "Pac-12": "P12_C", "Mountain West": "MW_C", "American": "AAC_C",
    "Atlantic-8": "A8_C", "ECL": "ECL_C",
}


def _r2_selection() -> CFPSelection:
    base = select_governed_14_team_cfp(ORDER, {t: "Other" for t in ORDER}, CHAMPS)
    return postseason.apply_g5_automatic_bid_seed(base, ORDER, CHAMPS)


def test_g5_pool_is_exactly_five_conferences():
    assert postseason.G5_CONFERENCES == ("AAC", "Atlantic-8", "ECL", "Mountain West", "Pac-12")
    assert len(postseason.G5_CONFERENCES) == 5


def test_only_one_g5_automatic_bid_is_issued():
    selection = _r2_selection()
    audit = postseason.g5_automatic_bid_audit(selection, {t: "Other" for t in ORDER})
    assert audit["automatic_bids"] == 1
    assert audit["champion"] == "P12_C"


def test_the_g5_automatic_bid_champion_is_seeded_exactly_five():
    selection = _r2_selection()
    assert selection.seeds[5] == "P12_C"
    assert postseason.g5_automatic_bid_audit(selection, {})["seed"] == 5


def test_the_g5_automatic_bid_champion_never_appears_in_a_play_in_game():
    selection = _r2_selection()
    play_in = {selection.seeds[s] for s in postseason.PLAY_IN_SEEDS}
    assert "P12_C" not in play_in
    assert postseason.g5_automatic_bid_audit(selection, {})["in_play_in"] is False


def test_a_higher_ranked_non_champion_does_not_take_the_g5_bid():
    order = [
        "SEC_C", "B10_C", "B12_C", "ACC_C", "G5_NONCHAMP", "P12_C",
        "MW_C", "AAC_C", "A8_C", "ECL_C",
    ] + [f"X{i}" for i in range(1, 11)]
    assert postseason.g5_automatic_bid_champion(order, CHAMPS) == "P12_C"


@pytest.mark.parametrize("natural_rank", [1, 3, 5, 8, 14])
def test_the_g5_champion_lands_on_seed_five_from_every_natural_position(natural_rank):
    """Seed 5 exactly: not a floor, not a ceiling.

    A champion ranked 1st is displaced *down* to 5 and one ranked 14th is pulled
    *up* to 5. Bracket Regime S2's top-4-overall bye language is superseded to
    exactly that extent -- the bye seeds stay 1-4 and the next team moves up.
    """
    others = ["SEC_C", "B10_C", "B12_C", "ACC_C", "ND"]
    tail = ["MW_C", "AAC_C", "A8_C", "ECL_C"]
    filler = [f"X{i:02d}" for i in range(1, 40)]
    body, fi = [], 0
    while len(body) < natural_rank - 1:
        if others:
            body.append(others.pop(0))
        else:
            body.append(filler[fi])
            fi += 1
    order = body + ["P12_C"] + others + tail
    while len(order) < 24:
        order.append(filler[fi])
        fi += 1
    assert order.index("P12_C") + 1 == natural_rank

    base = select_governed_14_team_cfp(order, {t: "Other" for t in order}, CHAMPS)
    out = postseason.apply_g5_automatic_bid_seed(base, order, CHAMPS)

    assert out.seeds[5] == "P12_C"
    audit = postseason.g5_automatic_bid_audit(out, {t: "Other" for t in order})
    assert audit["seed"] == 5 and audit["automatic_bids"] == 1
    assert "P12_C" not in {out.seeds[n] for n in postseason.PLAY_IN_SEEDS}

    # Deterministic displacement: a permutation of the same field, no duplication
    # or omission, every other qualifier still in committee-rank order.
    assert sorted(out.seeds) == list(range(1, 15))
    assert len(set(out.seeds.values())) == 14
    assert set(out.seeds.values()) == set(base.seeds.values())
    rank = {t: i for i, t in enumerate(order)}
    others_in_order = [out.seeds[n] for n in sorted(out.seeds) if n != 5]
    assert others_in_order == sorted(others_in_order, key=lambda t: rank[t])


def test_reseeding_is_forbidden():
    assert postseason.RESEEDING_PERMITTED is False
    postseason.require_no_reseeding(False)
    with pytest.raises(GovernanceBlock, match="Reseeding between rounds is forbidden"):
        postseason.require_no_reseeding(True)


def test_every_bracket_edge_the_official_artifact_states_is_bound():
    edges = postseason.governed_bracket_edges(_r2_selection())
    selection = _r2_selection()
    assert edges["PLAYIN_G1"] == (selection.seeds[12], selection.seeds[13])
    assert edges["PLAYIN_G2"] == (selection.seeds[11], selection.seeds[14])
    assert edges["R1_C_7_10"] == (selection.seeds[7], selection.seeds[10])
    assert edges["QF_E"] == selection.seeds[1]
    assert edges["SEMI_A"] == ("QF_E", "QF_H")
    assert edges["SEMI_B"] == ("QF_F", "QF_G")
    assert edges["reseeding_permitted"] is False


def test_the_unstated_quarterfinal_slot_edges_are_still_refused():
    assert postseason.QUARTERFINAL_SLOT_EDGES_STATED_IN_ARTIFACT is False
    with pytest.raises(GovernanceBlock, match="never states which first-round winner"):
        postseason.require_governed_quarterfinal_slot_edges(None)
    with pytest.raises(GovernanceBlock, match="bijection"):
        postseason.require_governed_quarterfinal_slot_edges(
            {"QF_E": "R1_A_5_12", "QF_F": "R1_A_5_12", "QF_G": "R1_C_7_10", "QF_H": "R1_D_8_9"}
        )
    bound = postseason.require_governed_quarterfinal_slot_edges(
        {"QF_E": "R1_D_8_9", "QF_F": "R1_C_7_10", "QF_G": "R1_B_6_11", "QF_H": "R1_A_5_12"}
    )
    assert len(set(bound.values())) == 4
