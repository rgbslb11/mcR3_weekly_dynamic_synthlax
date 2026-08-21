"""C3: the Colley witness, the preserved SRS witness, and the harness over both.

Ruling R2-CAL-OBJECTIVE keeps Baxter Rating RMSE primary and reports Colley and
SRS independently. These tests hold three things: that Colley is the
parameter-free named method and nothing else, that the SRS witness is unchanged
by sharing a solver with it, and that the harness over the pair reports
disagreement without ever blending it away.
"""

import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import calibration as cal
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import colley, linalg, srs, witnesses
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)


def _round_robin():
    """A 3-team round robin: A beats B and C, B beats C."""
    return [
        colley.ColleyGame("g1", "A", "B", True), colley.ColleyGame("g1", "B", "A", False),
        colley.ColleyGame("g2", "A", "C", True), colley.ColleyGame("g2", "C", "A", False),
        colley.ColleyGame("g3", "B", "C", True), colley.ColleyGame("g3", "C", "B", False),
    ]


# --- Colley: the named method, solved exactly --------------------------------


def test_colley_reproduces_the_hand_solvable_round_robin():
    # C = [[4,-1,-1],[-1,4,-1],[-1,-1,4]], b = [2, 1, 0]; sum r = 1.5 gives
    # 5*r = b + 1.5 exactly, so the answer is 0.7 / 0.5 / 0.3 with no tuning.
    ratings = colley.compute_colley(_round_robin())
    assert ratings["A"] == pytest.approx(0.7, abs=1e-12)
    assert ratings["B"] == pytest.approx(0.5, abs=1e-12)
    assert ratings["C"] == pytest.approx(0.3, abs=1e-12)
    assert colley.colley_ordering(ratings) == ["A", "B", "C"]


def test_colley_ratings_always_average_exactly_one_half():
    for games in (_round_robin(), _round_robin()[:4]):
        ratings = colley.compute_colley(games)
        mean = sum(ratings.values()) / len(ratings)
        assert mean == pytest.approx(colley.COLLEY_MEAN_RATING, abs=1e-12)


def test_colley_residuals_vanish_and_the_matrix_is_positive_definite():
    properties = colley.assert_colley_properties(_round_robin())
    assert properties["worst_residual"] < 1e-9
    assert properties["mean_rating"] == pytest.approx(0.5, abs=1e-12)
    assert properties["matrix_symmetric"] is True
    assert properties["matrix_strictly_diagonally_dominant"] is True


def test_colley_is_deterministic_regardless_of_input_order():
    games = _round_robin()
    assert colley.compute_colley(list(reversed(games))) == colley.compute_colley(games)


def test_colley_solves_a_disconnected_schedule_where_srs_needs_components():
    """C = 2I + D - A is positive definite whatever the schedule graph does."""
    disconnected = [
        colley.ColleyGame("g1", "A", "B", True), colley.ColleyGame("g1", "B", "A", False),
        colley.ColleyGame("g2", "C", "D", True), colley.ColleyGame("g2", "D", "C", False),
    ]
    ratings = colley.compute_colley(disconnected)
    assert sorted(ratings) == ["A", "B", "C", "D"]
    assert ratings["A"] == pytest.approx(ratings["C"], abs=1e-12)
    assert sum(ratings.values()) / 4 == pytest.approx(0.5, abs=1e-12)
    # SRS reaches the same schedule through per-component centring instead.
    assert len(srs.srs_components([
        srs.SrsGame("g1", "A", "B", 7.0), srs.SrsGame("g1", "B", "A", -7.0),
        srs.SrsGame("g2", "C", "D", 7.0), srs.SrsGame("g2", "D", "C", -7.0),
    ])) == 2


def test_colley_ignores_margin_entirely_where_srs_does_not():
    """Same win/loss, different margins: Colley identical, SRS not."""
    assert not hasattr(colley.ColleyGame("g", "A", "B", True), "margin")
    close = [srs.SrsGame("g1", "A", "B", 1.0), srs.SrsGame("g1", "B", "A", -1.0)]
    blowout = [srs.SrsGame("g1", "A", "B", 21.0), srs.SrsGame("g1", "B", "A", -21.0)]
    assert srs.compute_srs(close) != srs.compute_srs(blowout)
    same_wl = [
        colley.ColleyGame("g1", "A", "B", True), colley.ColleyGame("g1", "B", "A", False),
    ]
    assert colley.compute_colley(same_wl) == colley.compute_colley(list(same_wl))


def test_colley_records_the_wins_and_losses_it_used():
    assert colley.colley_records(_round_robin()) == {
        "A": (2, 0), "B": (1, 1), "C": (0, 2)
    }


# --- Colley: what it refuses --------------------------------------------------


def test_a_half_recorded_or_self_contradictory_game_is_refused():
    with pytest.raises(InputValidationError, match="exactly one row per side"):
        colley.compute_colley([colley.ColleyGame("g1", "A", "B", True)])
    with pytest.raises(InputValidationError, match="both sides as winners"):
        colley.compute_colley([
            colley.ColleyGame("g1", "A", "B", True),
            colley.ColleyGame("g1", "B", "A", True),
        ])
    with pytest.raises(InputValidationError, match="both sides as losers"):
        colley.compute_colley([
            colley.ColleyGame("g1", "A", "B", False),
            colley.ColleyGame("g1", "B", "A", False),
        ])
    with pytest.raises(InputValidationError, match="playing itself"):
        colley.ColleyGame("g1", "A", "A", True)
    with pytest.raises(InputValidationError, match="at least one game"):
        colley.compute_colley([])


def test_a_tie_fails_closed_rather_than_scoring_half_a_win():
    assert colley.COLLEY_TIE_POLICY is None
    with pytest.raises(GovernanceBlock, match="not governed here"):
        colley.require_colley_tie_policy()
    with pytest.raises(InputValidationError, match="win or a loss"):
        colley.ColleyGame("g1", "A", "B", 0.5)


def test_the_colley_witness_carries_no_free_parameter_to_promote():
    assert colley.COLLEY_FREE_PARAMETERS == ()
    assert colley.witness_as_dict(colley.compute_colley(_round_robin()))[
        "free_parameters"
    ] == []
    for variant in (
        "colley_with_margin",
        "MARGIN_WEIGHTED_COLLEY",
        "weighted_colley",
        "COLLEY_WITH_PRIOR_WEIGHT",
        "recency_weighted_colley",
    ):
        with pytest.raises(GovernanceBlock, match="no free parameters"):
            colley.reject_parameterised_colley(variant)
    # The named method itself is not a parameterised variant.
    colley.reject_parameterised_colley("COLLEY_MATRIX")


def test_no_canonical_colley_validation_is_claimed():
    assert colley.CANONICAL_COLLEY_SPEC_MOUNTED is False
    assert colley.CANONICAL_VALIDATION_ANCHORS == ()
    assert colley.CANONICAL_COLLEY_REFERENCE_IMPLEMENTATION is None
    with pytest.raises(GovernanceBlock, match="no canonical Colley Matrix specification"):
        colley.require_canonical_validated_colley()
    payload = colley.witness_as_dict(colley.compute_colley(_round_robin()))
    assert payload["canonical_validation_status"] == "NOT_VALIDATED_AGAINST_CANONICAL_ANCHORS"


def test_colley_is_not_the_primary_criterion_nor_sos_nor_sor_nor_srs():
    payload = colley.witness_as_dict(colley.compute_colley(_round_robin()))
    assert payload["role"] == "CALIBRATION_VALIDATION_WITNESS"
    assert payload["is_committee_sos"] is False
    assert payload["is_sor"] is False
    assert payload["is_primary_criterion"] is False
    for name in ("SOS", "committee_sos", "SOR", "sor_b", "baxter_rating", "SRS"):
        with pytest.raises(GovernanceBlock, match="separate"):
            colley.reject_colley_as(name)
    with pytest.raises(GovernanceBlock, match="NOT ADOPTED"):
        colley.reject_witness_composite(["COLLEY_MATRIX", "SRS"])
    colley.reject_witness_composite(["COLLEY_MATRIX"])


# --- SRS is preserved, not redefined -----------------------------------------


def _srs_games():
    return [
        srs.SrsGame("g1", "A", "B", 30.0), srs.SrsGame("g1", "B", "A", -30.0),
        srs.SrsGame("g2", "A", "C", 7.0), srs.SrsGame("g2", "C", "A", -7.0),
    ]


def test_srs_remains_the_capped_margin_opponent_adjusted_witness():
    ratings = srs.compute_srs(_srs_games())
    assert srs.SRS_MARGIN_CAP == 24.0
    assert ratings["A"] == pytest.approx(31 / 3, abs=1e-9)
    assert sum(ratings.values()) == pytest.approx(0.0, abs=1e-9)
    equivalence = srs.assert_solver_equivalence(_srs_games())
    assert equivalence["worst_residual"] < 1e-9
    assert equivalence["iterative_converged"] is True
    assert equivalence["orderings_match"] is True
    assert equivalence["margin_cap"] == 24.0


def test_the_shared_solver_keeps_the_srs_singularity_message_its_own():
    with pytest.raises(InputValidationError, match="schedule graph is"):
        srs._solve([[1.0, 1.0], [1.0, 1.0]], [1.0, 1.0])
    with pytest.raises(InputValidationError, match="Colley matrix is singular"):
        linalg.solve_exact(
            [[1.0, 1.0], [1.0, 1.0]], [1.0, 1.0],
            singular_message="Colley matrix is singular, which it cannot be",
        )


def test_no_canonical_srs_anchor_validation_and_no_srs_over_40_authority():
    assert srs.CANONICAL_SRS_SPEC_MOUNTED is False
    assert srs.CANONICAL_VALIDATION_ANCHORS == ()
    assert srs.SRS_OVER_40_SEMANTICS is None
    with pytest.raises(GovernanceBlock, match="no canonical SRS specification"):
        srs.require_canonical_validated_srs()
    with pytest.raises(GovernanceBlock, match="not defined in any mounted artifact"):
        srs.require_srs_over_40(41.0)


# --- the harness over both witnesses -----------------------------------------

FIXTURE_AUTHORITY = "TEST_FIXTURE"


def _schedule(authority=FIXTURE_AUTHORITY, *, margins=True):
    games = (
        witnesses.WitnessGame("g1", "A", "B", True, 10.0 if margins else None),
        witnesses.WitnessGame("g2", "A", "C", True, 3.0 if margins else None),
        witnesses.WitnessGame("g3", "B", "C", True, 40.0 if margins else None),
    )
    return witnesses.WitnessSchedule("SCH-C3-FIXTURE", authority, games, as_of_week=3)


def test_the_report_matches_the_published_interface_and_is_serialisable():
    report = witnesses.witness_report(_schedule())
    assert tuple(report) == witnesses.WITNESS_REPORT_FIELDS
    assert report["interface_version"] == witnesses.WITNESS_INTERFACE_VERSION
    contract = witnesses.witness_interface_as_dict()
    assert contract["report_fields"] == list(witnesses.WITNESS_REPORT_FIELDS)
    assert contract["witnesses"] == ["colley_matrix", "srs"]
    assert contract["srs_requires_margins"] is True
    assert contract["colley_requires_margins"] is False
    json.dumps(report)  # C2 consumes this payload; it must round-trip.


def test_one_schedule_feeds_both_witnesses_from_the_same_games():
    schedule = _schedule()
    assert len(witnesses.colley_games(schedule)) == 2 * len(schedule.games)
    assert len(witnesses.srs_games(schedule)) == 2 * len(schedule.games)
    assert schedule.teams == ["A", "B", "C"]


def test_disagreement_is_flagged_rather_than_averaged_away():
    """B's 40-point win caps to 24 and still outranks A on SRS; Colley says A."""
    report = witnesses.witness_report(_schedule())
    assert report["witnesses"]["colley_matrix"]["ordering"] == ["A", "B", "C"]
    assert report["witnesses"]["srs"]["ordering"] == ["B", "A", "C"]
    flags = report["disagreement"]
    assert flags["available"] is True
    assert flags["orderings_identical"] is False
    assert flags["pairs_compared"] == 3
    assert flags["pairs_disagreeing"] == 1
    pair = flags["disagreeing_pairs"][0]
    assert pair["pair"] == ["A", "B"]
    assert pair["colley_prefers"] == "A" and pair["srs_prefers"] == "B"
    assert flags["max_abs_rank_displacement"] == 1
    assert flags["is_composite"] is False
    assert report["witnesses"]["weighted_composite_authorised"] is False


def test_agreeing_witnesses_report_no_disagreement():
    agreeing = witnesses.WitnessSchedule(
        "SCH-AGREE",
        FIXTURE_AUTHORITY,
        (
            witnesses.WitnessGame("g1", "A", "B", True, 10.0),
            witnesses.WitnessGame("g2", "A", "C", True, 10.0),
            witnesses.WitnessGame("g3", "B", "C", True, 10.0),
        ),
    )
    flags = witnesses.witness_report(agreeing)["disagreement"]
    assert flags["pairs_disagreeing"] == 0
    assert flags["orderings_identical"] is True
    assert flags["max_abs_rank_displacement"] == 0


def test_a_schedule_without_margins_makes_srs_unavailable_not_zero():
    report = witnesses.witness_report(_schedule(margins=False))
    assert report["witnesses"]["colley_matrix"]["ordering"] == ["A", "B", "C"]
    srs_payload = report["witnesses"]["srs"]
    assert srs_payload["available"] is False
    assert srs_payload["ratings"] is None and srs_payload["ordering"] is None
    assert "No margin was inferred" in srs_payload["unavailable_reason"]
    flags = report["disagreement"]
    assert flags["available"] is False
    assert flags["pairs_disagreeing"] is None
    assert flags["orderings_identical"] is None
    with pytest.raises(InputValidationError, match="governed margin"):
        witnesses.srs_games(_schedule(margins=False))


def test_a_result_that_contradicts_its_margin_is_refused():
    with pytest.raises(InputValidationError, match="disagree"):
        witnesses.WitnessGame("g1", "A", "B", True, -10.0)
    with pytest.raises(InputValidationError, match="no governed treatment"):
        witnesses.WitnessGame("g1", "A", "B", True, 0.0)
    with pytest.raises(InputValidationError, match="more than once"):
        witnesses.witness_report(
            witnesses.WitnessSchedule(
                "SCH-DUP",
                FIXTURE_AUTHORITY,
                (
                    witnesses.WitnessGame("g1", "A", "B", True, 10.0),
                    witnesses.WitnessGame("g1", "A", "C", True, 10.0),
                ),
            )
        )
    with pytest.raises(InputValidationError, match="no completed games"):
        witnesses.WitnessSchedule("SCH-EMPTY", FIXTURE_AUTHORITY, ())


# --- synthetic fixtures stay fixtures; nothing is promoted --------------------


def test_a_synthetic_fixture_report_may_not_be_cited_as_calibration_evidence():
    report = witnesses.witness_report(_schedule())
    assert report["authority"] == "TEST_FIXTURE"
    assert report["evidence_class"] == witnesses.EVIDENCE_NOT_GOVERNED
    assert report["governance"]["is_governed_evidence"] is False
    with pytest.raises(GovernanceBlock, match="not governance"):
        witnesses.require_governed_witness_evidence(report)
    for authority in ("TEST_FIXTURE", "RESEARCH", "PROPOSED", "ASSUMED", ""):
        assert _schedule(authority).evidence_class == witnesses.EVIDENCE_NOT_GOVERNED


def test_a_governed_schedule_passes_the_evidence_gate():
    governed = _schedule("Model_Parameters_v2_5_APPROVED.xlsx!02_PARAMETER_REGISTER")
    report = witnesses.witness_report(governed)
    assert report["evidence_class"] == witnesses.EVIDENCE_GOVERNED
    assert witnesses.require_governed_witness_evidence(report) is report


def test_the_primary_criterion_stays_blocked_and_cannot_be_handed_in():
    report = witnesses.witness_report(_schedule())
    primary = report["primary_criterion"]
    assert primary["metric"] == cal.PRIMARY_CALIBRATION_METRIC
    assert primary["direction"] == "minimize"
    assert primary["value"] is None
    assert primary["status"] == cal.BLOCKED_ON_CALIBRATION_DATA
    with pytest.raises(GovernanceBlock, match="may not be supplied"):
        witnesses.witness_report(_schedule(), baxter_rmse=12.3)


def test_a_candidate_regime_is_stamped_but_never_promoted():
    regime = cal.CandidateRegime(
        regime_id="R-C3-FIXTURE",
        values={"game_sd_points": 17.0},
        rationale="TEST_FIXTURE candidate regime; never canonical",
    )
    report = witnesses.witness_report(_schedule(), regime=regime)
    assert report["regime"] == {
        "regime_id": "R-C3-FIXTURE",
        "status": "EXPERIMENTAL",
        "fields_set": ["game_sd_points"],
        "promotion_authorised": False,
    }
    assert report["governance"]["promotion_authorised"] is False
    assert report["governance"]["canonical_values_written"] is False
    with pytest.raises(GovernanceBlock, match="not a promotion authority"):
        witnesses.reject_witness_promotion(report)
    # The witness report is not an authority, and neither is a ranking.
    with pytest.raises(GovernanceBlock, match="no promotion authority named"):
        cal.promote_regime_r2(regime, ranked_first=True)
    with pytest.raises(InputValidationError, match="must be a CandidateRegime"):
        witnesses.witness_report(_schedule(), regime={"regime_id": "R-C3-FIXTURE"})


def test_the_harness_refuses_to_blend_the_witnesses():
    with pytest.raises(GovernanceBlock, match="NOT ADOPTED"):
        witnesses.reject_witness_composite(["COLLEY_MATRIX", "SRS"])
    with pytest.raises(GovernanceBlock, match="not authorised"):
        cal.reject_witness_composite(["baxter_rating", "colley_matrix", "srs"])
    report = witnesses.witness_report(_schedule())
    assert report["witnesses"]["reported_independently"] == ["colley_matrix", "srs"]
    assert report["disagreement"]["flags_are_diagnostic_only"] is True


def test_running_the_harness_writes_no_canonical_calibration_value():
    """The canonical config is read after the harness runs, not merely asserted about."""
    config_path = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "dynamic_weekly_mc_v3"
        / "v3_experimental.json"
    )
    before = json.loads(config_path.read_text())

    witnesses.witness_report(_schedule())

    after = json.loads(config_path.read_text())
    assert after == before
    values = after["calibration"]
    # Assert against the real block, not a .get() that would read None from an
    # absent key and pass however the values were actually set.
    assert sorted(values) == sorted(cal.CALIBRATION_FIELDS)
    assert all(values[field] is None for field in cal.CALIBRATION_FIELDS)
    status = cal.calibration_status(values)
    assert status["all_canonical_values_null"] is True
    assert status["unresolved_fields"] == list(cal.CALIBRATION_FIELDS)
    assert status["legacy_margin_sd_approved"] is False
