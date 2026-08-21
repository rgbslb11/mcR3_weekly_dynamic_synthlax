"""R2 convergence: approved SOS and performance against common opponents.

The semantics these tests run under are a FIXTURE, not governance. That is the
point: the repository defines no OWP/OOWP denominator or exclusion rule, and
:func:`sos.require_governed_sos_semantics` refuses this very fixture. The tests
exercise the arithmetic the Chairman's weights describe while the production
path stays fail-closed.
"""

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import sos
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.common_opponents import (
    common_opponent_score,
    common_opponents,
    compare_common_opponents,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.sos import (
    GameResult,
    ResumeLedger,
    SosSemantics,
)

#: RPI-style: opponent records exclude the rated team's own result.
FIXTURE_SEMANTICS = SosSemantics(
    semantics_id="FIXTURE_RPI_STYLE",
    authority="TEST_FIXTURE",
    exclude_rated_team_from_owp=True,
    instance_weighting="PER_GAME",
    exclude_rated_team_from_oowp=True,
)

#: The same weights with the exclusion switched off, used to show that the
#: unresolved semantics question is load-bearing rather than cosmetic.
FIXTURE_NO_EXCLUSION = SosSemantics(
    semantics_id="FIXTURE_NO_EXCLUSION",
    authority="TEST_FIXTURE",
    exclude_rated_team_from_owp=False,
    instance_weighting="PER_GAME",
    exclude_rated_team_from_oowp=False,
)


def _chairman_ledger() -> ResumeLedger:
    """Deterministic fixture reproducing the Chairman's common-opponent example.

    Lehigh 11-1 and USF 11-1 are each 2-1 against Harvard 7-5, Rice 4-8 and
    UCF 9-2, having beaten and lost to different members of that set. Filler
    opponents each play exactly one game so every record in the ledger is fully
    determined by the ledger itself. These are TEST FIXTURE records, not
    production results.
    """
    rows: list[GameResult] = []
    counter = [0]

    def game(week: int, winner: str, loser: str) -> None:
        counter[0] += 1
        gid = f"F{counter[0]:04d}"
        rows.append(GameResult(gid, week, winner, loser, True))
        rows.append(GameResult(gid, week, loser, winner, False))

    game(1, "LEH", "HARV")
    game(2, "LEH", "RICE")
    game(3, "UCF", "LEH")
    game(4, "USF", "UCF")
    game(5, "USF", "RICE")
    game(6, "HARV", "USF")

    filler = [0]

    def fillers(team: str, wins: int, losses: int) -> None:
        for _ in range(wins):
            filler[0] += 1
            game(7, team, f"FIL{filler[0]:02d}")
        for _ in range(losses):
            filler[0] += 1
            game(7, f"FIL{filler[0]:02d}", team)

    fillers("LEH", 9, 0)
    fillers("USF", 9, 0)
    fillers("HARV", 6, 4)
    fillers("RICE", 4, 6)
    fillers("UCF", 8, 1)
    return ResumeLedger(rows)


# --- governance gate ---------------------------------------------------------


def test_sos_weights_are_the_ruled_weights():
    assert (sos.WP_WEIGHT, sos.OWP_WEIGHT, sos.OOWP_WEIGHT) == (0.25, 0.50, 0.25)
    assert sos.WP_WEIGHT + sos.OWP_WEIGHT + sos.OOWP_WEIGHT == 1.0


def test_sos_semantics_are_now_governed_and_a_fixture_still_cannot_pass():
    """R3-SOS-OWP-OOWP-SEMANTICS governs the semantics; fixtures still cannot.

    The gate that used to refuse everything now accepts exactly the governed
    instance. A test fixture's authority is still not a governed source, so a
    fixture can never be promoted to production authority.
    """
    governed = sos.GOVERNED_SOS_SEMANTICS
    assert governed is not None
    assert sos.require_governed_sos_semantics(governed) is governed
    with pytest.raises(GovernanceBlock, match=sos.SOS_SEMANTICS_BLOCKER):
        sos.require_governed_sos_semantics(None)
    with pytest.raises(GovernanceBlock, match="not a governed source"):
        sos.require_governed_sos_semantics(FIXTURE_SEMANTICS)


# --- WP / OWP / OOWP / SOS ---------------------------------------------------


def test_win_pct_is_wins_over_games_played():
    ledger = _chairman_ledger()
    assert ledger.record("LEH") == (11, 1)
    assert sos.win_pct(ledger, "LEH") == 11 / 12
    assert sos.win_pct(ledger, "RICE") == 4 / 12


def test_owp_excludes_the_rated_team_under_the_fixture_semantics():
    ledger = _chairman_ledger()
    # HARV is 7-5 overall; with LEH's win over HARV removed HARV is 7-4.
    assert sos.win_pct(ledger, "HARV", excluding_opponent="LEH") == 7 / 11
    assert sos.win_pct(ledger, "HARV") == 7 / 12


def test_oowp_is_the_mean_of_opponent_owp():
    ledger = _chairman_ledger()
    components = sos.sos_components(ledger, "LEH", FIXTURE_SEMANTICS)
    assert components["wp"] == 11 / 12
    assert 0.0 <= components["owp"] <= 1.0
    assert 0.0 <= components["oowp"] <= 1.0


def test_full_sos_formula_matches_the_weighted_components():
    ledger = _chairman_ledger()
    for team in ("LEH", "USF", "HARV", "RICE", "UCF"):
        c = sos.sos_components(ledger, team, FIXTURE_SEMANTICS)
        assert c["sos"] == pytest.approx(
            0.25 * c["wp"] + 0.50 * c["owp"] + 0.25 * c["oowp"], abs=1e-15
        )


def test_sos_ordering_is_total_and_hardest_first():
    ledger = _chairman_ledger()
    teams = ["LEH", "USF", "HARV", "RICE", "UCF"]
    order = sos.rank_by_sos(ledger, teams, FIXTURE_SEMANTICS)
    assert sorted(order) == sorted(teams)
    values = [sos.strength_of_schedule(ledger, t, FIXTURE_SEMANTICS) for t in order]
    assert values == sorted(values, reverse=True)


def test_identical_input_is_byte_deterministic_regardless_of_row_order():
    rows = list(_chairman_ledger().results)
    forward = ResumeLedger(rows)
    reversed_ledger = ResumeLedger(list(reversed(rows)))
    for team in ("LEH", "USF", "HARV"):
        assert repr(sos.sos_components(forward, team, FIXTURE_SEMANTICS)) == repr(
            sos.sos_components(reversed_ledger, team, FIXTURE_SEMANTICS)
        )


def test_no_future_week_leakage():
    ledger = _chairman_ledger()
    early = ledger.through_week(3)
    assert all(r.week <= 3 for r in early.results)
    assert early.record("LEH") == (2, 1)
    # The week-3 view cannot see the filler games played in week 7.
    assert sos.win_pct(early, "LEH") == 2 / 3
    assert sos.win_pct(ledger, "LEH") == 11 / 12


def test_duplicate_ledger_rows_are_rejected():
    row = GameResult("G1", 1, "A", "B", True)
    with pytest.raises(InputValidationError, match="Duplicate ledger row"):
        ResumeLedger([row, row])


# --- performance against common opponents -----------------------------------


def test_chairman_fixture_reproduces_the_stated_records():
    ledger = _chairman_ledger()
    assert ledger.record("LEH") == (11, 1)
    assert ledger.record("USF") == (11, 1)
    assert ledger.record("HARV") == (7, 5)
    assert ledger.record("RICE") == (4, 8)
    assert ledger.record("UCF") == (9, 2)


def test_both_teams_are_two_and_one_against_the_same_common_opponents():
    ledger = _chairman_ledger()
    assert common_opponents(ledger, "LEH", "USF") == ("HARV", "RICE", "UCF")
    left, right = compare_common_opponents(ledger, "LEH", "USF", FIXTURE_SEMANTICS)
    assert (left.wins, left.losses) == (2, 1)
    assert (right.wins, right.losses) == (2, 1)
    assert left.wp_common == right.wp_common == 2 / 3


def test_owp_oowp_depth_separates_two_identical_two_and_one_resumes():
    """The whole point of the formula: record alone cannot break this tie."""
    ledger = _chairman_ledger()
    leh, usf = compare_common_opponents(ledger, "LEH", "USF", FIXTURE_SEMANTICS)
    assert leh.wp_common == usf.wp_common
    assert leh.owp_common != usf.owp_common
    assert leh.score != usf.score
    assert usf.score > leh.score


def test_without_the_exclusion_rule_the_two_resumes_are_indistinguishable():
    """Why the missing semantics are a blocker and not a detail."""
    ledger = _chairman_ledger()
    leh, usf = compare_common_opponents(ledger, "LEH", "USF", FIXTURE_NO_EXCLUSION)
    assert leh.score == usf.score


def test_common_opponent_score_uses_the_same_weights_as_sos():
    ledger = _chairman_ledger()
    result = common_opponent_score(ledger, "LEH", "USF", FIXTURE_SEMANTICS)
    assert result.score == pytest.approx(
        0.25 * result.wp_common + 0.50 * result.owp_common + 0.25 * result.oowp_common,
        abs=1e-15,
    )


def test_common_opponent_comparison_requires_two_distinct_teams():
    ledger = _chairman_ledger()
    with pytest.raises(InputValidationError, match="two distinct teams"):
        common_opponent_score(ledger, "LEH", "LEH", FIXTURE_SEMANTICS)


def test_common_opponent_set_excludes_the_two_teams_themselves():
    ledger = _chairman_ledger()
    shared = common_opponents(ledger, "HARV", "UCF")
    assert "HARV" not in shared and "UCF" not in shared
