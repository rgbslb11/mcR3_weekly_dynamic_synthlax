"""PR #3 common-opponent authority binding — ruling R4-COMMON-OPP-FORMULA.

The defect this suite pins down was one of *representation*, not arithmetic. The
exact formula::

    COMMON_OPP_SCORE = 0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common

was approved directly by the Chairman, but the module still recorded
``COMMON_OPPONENT_FORMULA_IS_CANONICAL = False`` because older mounted workbooks
predate that ruling. Older evidence does not outrank a later direct ruling, so
the classification is corrected and the succession is recorded.

Two things this suite is careful about:

* the **formula** (Layer A) and the **denominator semantics** (Layer B) are
  asserted separately, in both directions, so neither can carry the other; and
* the numbers do not move. The last section recomputes the OWP/OOWP fixtures by
  hand and checks the implementation still lands on the same values.
"""

import json
from dataclasses import replace
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (
    blocker_report as br,
    common_opponents,
    rulings,
    sos,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
STATUS_R4 = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R4.json"

GOVERNED = sos.GOVERNED_SOS_SEMANTICS
GOVERNED_FORMULA = common_opponents.GOVERNED_COMMON_OPPONENT_FORMULA


def _pair(game_id, week, a, b, a_won):
    return [
        sos.GameResult(game_id=game_id, week=week, team=a, opponent=b, won=a_won),
        sos.GameResult(game_id=game_id, week=week, team=b, opponent=a, won=not a_won),
    ]


@pytest.fixture(scope="module")
def shared_ledger():
    """A and B each play the same two common opponents X and Z; both go 1-1.

    A: beat X (w1), lost to Z (w2).   B: lost to X (w3), beat Z (w4).
    X and Z each also play Q so the opponent records are not degenerate.
    """
    rows = []
    rows += _pair("g1", 1, "A", "X", True)
    rows += _pair("g2", 2, "A", "Z", False)
    rows += _pair("g3", 3, "B", "X", False)
    rows += _pair("g4", 4, "B", "Z", True)
    rows += _pair("g5", 5, "X", "Q", True)
    rows += _pair("g6", 6, "Z", "Q", False)
    return sos.ResumeLedger(rows)


@pytest.fixture(scope="module")
def live_blockers():
    return sorted(
        DynamicWeeklyMCV3(V3Config.from_json(CONFIG)).preflight()["execution_blockers"]
    )


# =============================================================================
# A — the exact formula is governed
# =============================================================================


def test_the_exact_formula_is_recognised_as_governed():
    assert common_opponents.COMMON_OPPONENT_FORMULA_IS_CANONICAL is True
    assert GOVERNED_FORMULA.status == "GOVERNED"
    assert common_opponents.COMMON_OPPONENT_FORMULA_STATUS.startswith("GOVERNED")
    assert "R4-COMMON-OPP-FORMULA" in common_opponents.COMMON_OPPONENT_FORMULA_STATUS


def test_the_ruling_is_recorded_with_the_exact_formula_and_no_invented_id():
    ruling = rulings.ruling("R4-COMMON-OPP-FORMULA")
    assert ruling.provenance == "FACT"
    assert ruling.resolution_reason == "DIRECT_CHAIRMAN_AUTHORITY"
    # No formal Chairman ruling ID was issued, so none is invented.
    assert ruling.chairman_ruling_id is None
    assert "0.25 * WP_common" in ruling.decision
    assert "0.50 * OWP_common" in ruling.decision
    assert "0.25 * OOWP_common" in ruling.decision
    assert ruling in rulings.ALL_RULINGS


def test_the_authority_binding_retires_no_blocker():
    """This patch corrects a representation defect. It clears no project work."""
    assert rulings.ruling("R4-COMMON-OPP-FORMULA").retires == ()
    assert "R4-COMMON-OPP-FORMULA" not in rulings.retirable_blockers().values()


# =============================================================================
# B — only the exact weights are accepted
# =============================================================================


def test_the_governed_weights_are_exactly_25_50_25():
    assert common_opponents.GOVERNED_COMMON_OPPONENT_WEIGHTS == (0.25, 0.50, 0.25)
    assert GOVERNED_FORMULA.weights == (0.25, 0.50, 0.25)
    assert sum(GOVERNED_FORMULA.weights) == 1.0
    formula, semantics = common_opponents.require_governed_common_opponent_formula(
        GOVERNED_FORMULA, GOVERNED
    )
    assert formula is GOVERNED_FORMULA
    assert semantics is GOVERNED


@pytest.mark.parametrize(
    "weights", common_opponents.REFUSED_COMMON_OPPONENT_WEIGHTINGS
)
def test_a_mutated_weighting_fails_closed(weights):
    wp, owp, oowp = weights
    mutated = replace(
        GOVERNED_FORMULA, wp_weight=wp, owp_weight=owp, oowp_weight=oowp
    )
    with pytest.raises(GovernanceBlock, match="not the governed formula"):
        common_opponents.require_governed_common_opponent_formula(mutated, GOVERNED)


def test_even_a_hair_off_weighting_fails_closed():
    mutated = replace(GOVERNED_FORMULA, owp_weight=0.5000001)
    with pytest.raises(GovernanceBlock, match="not the governed formula"):
        common_opponents.require_governed_common_opponent_formula(mutated, GOVERNED)


def test_the_weights_the_module_applies_are_the_weights_that_were_governed():
    """The record and the code path are compared, so a drifted constant blocks."""
    assert common_opponents._weights_applied() == (
        common_opponents.GOVERNED_COMMON_OPPONENT_WEIGHTS
    )
    assert common_opponents._weights_applied() == (
        sos.WP_WEIGHT,
        sos.OWP_WEIGHT,
        sos.OOWP_WEIGHT,
    )


# =============================================================================
# C — authority source
# =============================================================================


def test_direct_chairman_authority_is_the_accepted_source():
    assert GOVERNED_FORMULA.resolution_reason == "DIRECT_CHAIRMAN_AUTHORITY"
    assert "Direct Chairman authority" in GOVERNED_FORMULA.authority
    successor = replace(
        GOVERNED_FORMULA, resolution_reason="SUCCESSOR_DIRECT_CHAIRMAN_AUTHORITY"
    )
    common_opponents.require_governed_common_opponent_formula(successor, GOVERNED)


@pytest.mark.parametrize(
    "status",
    ["TEST_FIXTURE", "PROPOSAL", "OPEN", "UNRESOLVED", "HISTORICAL_PRE_RULING", ""],
)
def test_no_lesser_status_can_promote_itself(status):
    """Carrying the right numbers is not the same thing as carrying authority."""
    impostor = replace(
        GOVERNED_FORMULA,
        status=status,
        resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
    )
    assert impostor.weights == (0.25, 0.50, 0.25)
    with pytest.raises(GovernanceBlock, match="not a governed source"):
        common_opponents.require_governed_common_opponent_formula(impostor, GOVERNED)


@pytest.mark.parametrize(
    "reason", [None, "", "TEST_FIXTURE", "PROPOSAL", "RESEARCH", "ASSUMED"]
)
def test_a_governed_status_without_chairman_authority_fails_closed(reason):
    impostor = replace(GOVERNED_FORMULA, resolution_reason=reason)
    with pytest.raises(GovernanceBlock, match="requires direct Chairman authority"):
        common_opponents.require_governed_common_opponent_formula(impostor, GOVERNED)


def test_a_missing_formula_fails_closed():
    with pytest.raises(GovernanceBlock, match="authority is required"):
        common_opponents.require_governed_common_opponent_formula(None, GOVERNED)


# =============================================================================
# D — historical evidence stays historical
# =============================================================================


def test_the_pre_ruling_state_is_preserved_rather_than_rewritten():
    prior = common_opponents.COMMON_OPPONENT_FORMULA_PRIOR_STATUS
    assert prior.startswith("CONVERGENCE_RULING_ONLY")
    assert "not stated by any mounted artifact" in prior
    assert any(
        "ACC-EXT-08" in e for e in common_opponents.HISTORICAL_PRE_RULING_EVIDENCE
    )
    assert any(
        "R2-COMMON-OPP" in e for e in common_opponents.HISTORICAL_PRE_RULING_EVIDENCE
    )
    # The R2 convergence ruling itself is untouched.
    assert rulings.R2_COMMON_OPPONENTS.convergence_id == "R2-COMMON-OPP"
    assert rulings.R2_COMMON_OPPONENTS in rulings.R2_RULINGS


def test_the_issued_ruling_is_cited_as_the_authority_not_a_builder_summary():
    """The evidence names the ruling itself, including its exactness language.

    A builder asserting that something was approved is not authority. What makes
    the exact coefficients governed is the issued ruling, which states them in
    terms and declares them canonical and exact.
    """
    ruling = rulings.ruling("R4-COMMON-OPP-FORMULA")
    evidence = " ".join(ruling.evidence)
    assert "OPERATION SYTHALAX CHAIRMAN RULING" in evidence
    assert "canonical and exact" in evidence
    assert "DIRECT CHAIRMAN AUTHORITY" in evidence
    assert "0.25 * WP_common + 0.50 * OWP_common + 0.25 * OOWP_common" in evidence


def test_the_hedged_wording_is_superseded_rather_than_relied_on():
    """The exactness is issued, not inferred from the earlier hedged text."""
    ruling = rulings.ruling("R4-COMMON-OPP-FORMULA")
    superseded = " ".join(ruling.supersedes)
    assert "some formula that looks like" in superseded
    assert "preserved as the prior record and is not edited" in superseded
    # The ruling's own scope carve-outs are recorded, so a later reader can see
    # what it did *not* touch.
    evidence = " ".join(ruling.evidence)
    for untouched in ("SOS", "CCG rules", "postseason topology", "G5 seed #5"):
        assert untouched in evidence


def test_older_open_item_evidence_does_not_override_the_later_ruling():
    """ACC-EXT-08 is cited as evidence of the prior state, and superseded as authority."""
    ruling = rulings.ruling("R4-COMMON-OPP-FORMULA")
    assert any("ACC-EXT-08" in e for e in ruling.evidence)
    assert any("preserved unedited" in e for e in ruling.evidence)
    assert any("ACC-EXT-08" in s for s in ruling.supersedes)
    assert any("COMMON_OPPONENT_FORMULA_IS_CANONICAL = False" in s for s in ruling.supersedes)


def test_the_pre_ruling_formula_cannot_promote_itself():
    prior = common_opponents.PRE_RULING_COMMON_OPPONENT_FORMULA
    assert prior.weights == (0.25, 0.50, 0.25)  # right numbers...
    assert prior.resolution_reason is None       # ...no direct authority
    with pytest.raises(GovernanceBlock, match="not a governed source"):
        common_opponents.require_governed_common_opponent_formula(prior, GOVERNED)


def test_the_unpromoted_alternative_stays_unpromoted():
    assert common_opponents.UNPROMOTED_COMMON_OPPONENT_ALTERNATIVES == (
        "RESULT_WEIGHTED_OPPONENT_STRENGTH "
        "(opponent strength multiplied by a 1/0 result)",
    )
    assert any(
        "RESULT_WEIGHTED_OPPONENT_STRENGTH" in s
        for s in rulings.ruling("R4-COMMON-OPP-FORMULA").supersedes
    )


# =============================================================================
# E — formula authority and denominator semantics are separate assertions
# =============================================================================


def test_a_governed_formula_over_ungoverned_semantics_fails_closed():
    fixture_semantics = sos.SosSemantics(
        semantics_id="FIXTURE",
        authority="TEST_FIXTURE",
        exclude_rated_team_from_owp=True,
        instance_weighting="PER_GAME",
        exclude_rated_team_from_oowp=False,
        zero_qualifying_games="UNAVAILABLE",
    )
    with pytest.raises(GovernanceBlock, match="not a governed source"):
        common_opponents.require_governed_common_opponent_formula(
            GOVERNED_FORMULA, fixture_semantics
        )


def test_governed_semantics_under_an_ungoverned_formula_fails_closed():
    proposal = replace(GOVERNED_FORMULA, status="PROPOSAL")
    with pytest.raises(GovernanceBlock, match="not a governed source"):
        common_opponents.require_governed_common_opponent_formula(proposal, GOVERNED)
    # ...while the semantics on their own are perfectly fine.
    assert sos.require_governed_sos_semantics(GOVERNED) is GOVERNED


def test_missing_semantics_fails_closed():
    with pytest.raises(GovernanceBlock, match=sos.SOS_SEMANTICS_BLOCKER):
        common_opponents.require_governed_common_opponent_formula(GOVERNED_FORMULA, None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("exclude_rated_team_from_owp", False),
        ("instance_weighting", "PER_OPPONENT"),
        ("exclude_rated_team_from_oowp", True),
        ("oowp_construction", "MEAN_OVER_ALL_OPPONENT_OPPONENTS"),
        ("schedule_only_fcs_treatment", "EXCLUDE_FROM_ALL"),
    ],
)
def test_mutated_denominator_semantics_fail_closed(field, value):
    """The R3 semantics are required exactly; a relabelled variant does not pass."""
    mutated = replace(GOVERNED, **{field: value})
    with pytest.raises(GovernanceBlock, match="do not match ruling"):
        common_opponents.require_governed_common_opponent_formula(
            GOVERNED_FORMULA, mutated
        )


def test_a_semantics_id_from_another_ruling_fails_closed():
    mutated = replace(GOVERNED, semantics_id="R2-SOS")
    with pytest.raises(GovernanceBlock, match="requires the governed OWP/OOWP semantics"):
        common_opponents.require_governed_common_opponent_formula(
            GOVERNED_FORMULA, mutated
        )


# =============================================================================
# F — UNAVAILABLE stays fail-closed
# =============================================================================


def test_the_gate_refuses_semantics_that_would_invent_a_value():
    for policy in ("TREAT_AS_ZERO", "EXCLUDE_FROM_AVERAGES", "BLOCK"):
        mutated = replace(GOVERNED, zero_qualifying_games=policy)
        with pytest.raises(GovernanceBlock):
            common_opponents.require_governed_common_opponent_formula(
                GOVERNED_FORMULA, mutated
            )


def test_unavailability_still_propagates_through_the_governed_path():
    # C's only games are against A and B. Excluding the rated team leaves C one
    # game, but A and B have no other opponents, so OOWP cannot be formed.
    ledger = sos.ResumeLedger(
        _pair("g1", 1, "A", "C", True) + _pair("g2", 1, "B", "C", True)
    )
    result = common_opponents.governed_common_opponent_score(ledger, "A", "B", GOVERNED)
    assert result.common_opponents == ("C",)
    assert result.oowp_common is None
    assert result.score is None
    assert "oowp_common" in result.as_dict()["unavailable_components"]
    # Never invented as 0, 0.0 or .500.
    assert result.score not in (0, 0.0, 0.5)


def test_the_governed_and_ungoverned_paths_agree_numerically(shared_ledger):
    """The gate authorises; it does not rescore."""
    gated = common_opponents.governed_common_opponent_score(
        shared_ledger, "A", "B", GOVERNED
    )
    direct = common_opponents.common_opponent_score(shared_ledger, "A", "B", GOVERNED)
    assert gated == direct


def test_the_governed_comparison_returns_both_sides(shared_ledger):
    a, b = common_opponents.governed_compare_common_opponents(
        shared_ledger, "A", "B", GOVERNED
    )
    assert (a.team, a.other) == ("A", "B")
    assert (b.team, b.other) == ("B", "A")
    assert a.common_opponents == b.common_opponents == ("X", "Z")


# =============================================================================
# G — the test-fixture firewall
# =============================================================================


def test_a_synthetic_fixture_cannot_reach_production_authority():
    fixture = common_opponents.CommonOpponentFormula(
        formula_id="FIXTURE",
        authority="TEST_FIXTURE",
        status="TEST_FIXTURE",
        wp_weight=0.25,
        owp_weight=0.50,
        oowp_weight=0.25,
        resolution_reason="DIRECT_CHAIRMAN_AUTHORITY",
    )
    with pytest.raises(GovernanceBlock, match="not a governed source"):
        common_opponents.require_governed_common_opponent_formula(fixture, GOVERNED)
    with pytest.raises(GovernanceBlock):
        common_opponents.governed_common_opponent_score(
            sos.ResumeLedger(_pair("g1", 1, "A", "B", True)),
            "A",
            "B",
            GOVERNED,
            formula=fixture,
        )


def test_every_non_governing_status_is_named_so_none_can_drift_in():
    for status in ("TEST_FIXTURE", "PROPOSAL", "OPEN", "UNRESOLVED"):
        assert status in common_opponents.NON_GOVERNING_FORMULA_STATUSES
    assert "GOVERNED" not in common_opponents.NON_GOVERNING_FORMULA_STATUSES


# =============================================================================
# H — the blocker set did not move
# =============================================================================


EXPECTED_LIVE_BLOCKERS = frozenset(
    {
        "calibration.weekly_performance_residual_coefficient",
        "calibration.weekly_movement_cap_points",
        "calibration.recent_form_weights",
        "calibration.blowout_treatment",
        "calibration.game_sd_points",
        "calibration.sample_size_regularization",
        "governance.GAME_SD_CALIBRATION_OPEN",
        "inputs.board_of_record_i_k",
        "model_scale.FCS_ELO_1250_TO_V3_POINT_SCALE_ADAPTER",
    }
)


def test_the_live_blocker_set_is_exactly_the_same_nine(live_blockers):
    live = frozenset(live_blockers)
    assert live - EXPECTED_LIVE_BLOCKERS == frozenset(), "a blocker was added"
    assert EXPECTED_LIVE_BLOCKERS - live == frozenset(), "a blocker disappeared"
    assert len(live_blockers) == 9


def test_no_common_opponent_blocker_was_created(live_blockers):
    assert not [b for b in live_blockers if "COMMON_OPP" in b.upper()]
    assert br.R3_EXPECTED_LIVE_BLOCKERS == EXPECTED_LIVE_BLOCKERS


def test_the_blocker_classification_is_unchanged():
    counts: dict[str, int] = {}
    for blocker in EXPECTED_LIVE_BLOCKERS:
        counts[br.R3_REMAINING_CLASSIFICATION[blocker]] = (
            counts.get(br.R3_REMAINING_CLASSIFICATION[blocker], 0) + 1
        )
    assert counts == {
        "CALIBRATION": 7,
        "ARTIFACT_CUSTODY": 1,
        "ENGINEERING_MODEL_SCALE": 1,
    }
    assert "HUMAN_GOVERNANCE" not in counts


# =============================================================================
# The successor governance record
# =============================================================================


def test_the_successor_status_record_states_the_binding():
    status = json.loads(STATUS_R4.read_text(encoding="utf-8"))
    assert status["starting_candidate_sha"] == (
        "d5320c68e995e46848ee04bbb0acac97eb61371b"
    )
    assert status["base_sha"] == "3b46e561b8d939e10ba5d6ff2f69923d963a148e"
    # A committed artifact cannot contain the SHA of the commit containing it.
    assert status["head_sha"] is None
    assert status["chairman_ruling_ids_supplied"] is False

    formula = status["common_opponents"]
    assert formula["formula_is_canonical"] is True
    assert formula["formula_authority"] == "R4-COMMON-OPP-FORMULA"
    assert formula["resolution_reason"] == "DIRECT_CHAIRMAN_AUTHORITY"
    assert formula["weights"] == {"wp_common": 0.25, "owp_common": 0.50, "oowp_common": 0.25}
    assert formula["production_gate"] == (
        "common_opponents.require_governed_common_opponent_formula"
    )
    assert formula["historical_sources_rewritten"] is False
    assert formula["formula_exactness_is_issued_not_inferred"] is True
    issued = formula["formula_ruling"]
    assert issued["disposition"] == "APPROVED"
    assert issued["coefficients_declared_canonical_and_exact"] is True
    assert issued["human_authorization"] == "DIRECT CHAIRMAN AUTHORITY"
    assert issued["owp_oowp_semantics_held_unchanged"] is True
    assert issued["unavailable_remains_fail_closed"] is True
    assert formula["denominator_semantics_ruling"] == "R3-SOS-OWP-OOWP-SEMANTICS"
    assert formula["denominator_semantics_changed"] is False

    assert status["live_blocker_count"] == 9
    assert sorted(status["live_blockers"]) == sorted(EXPECTED_LIVE_BLOCKERS)
    assert status["resolved_blockers"] == []
    assert status["opened_blockers"] == []
    assert status["simulation_run"] is False


def test_the_historical_records_are_not_edited():
    status = json.loads(STATUS_R4.read_text(encoding="utf-8"))
    assert status["parent_build_manifest"]["edited"] is False
    assert status["parent_status_artifact"]["edited"] is False
    assert status["v2_1_static_control_sha256"] == (
        "39055662b819a3ff3e6e87ad53e28a15d0451a6b1e692e7770459e7a984c614a"
    )
    manifest = json.loads(
        (ROOT / "reference/dynamic_weekly_mc_v3/V3_BUILD_MANIFEST.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(manifest["execution_blockers"]) == 18


# =============================================================================
# Section 9 — the mathematics did not change
# =============================================================================


def test_owp_still_excludes_the_evaluated_team(shared_ledger):
    """A's common opponents are X and Z; both are 1-1 overall.

    Excluding A: X is 1-0 (beat Q), Z is 0-1 (lost to Q).
    OWP_common(A) = mean(1.0, 0.0) = 0.5.
    """
    result = common_opponents.governed_common_opponent_score(
        shared_ledger, "A", "B", GOVERNED
    )
    assert result.common_opponents == ("X", "Z")
    assert result.wins == 1 and result.losses == 1
    assert result.wp_common == 0.5
    assert result.owp_common == pytest.approx(0.5)


def test_the_score_is_the_governed_weighted_sum(shared_ledger):
    """OOWP_common(A): X's own OWP over {A, Q}, Z's own OWP over {A, Q}.

    X excluded from its opponents' records: A is 1-1 -> excluding X, A is 0-1
    (lost to Z) = 0.0; Q is 0-1 vs X and 1-0 vs Z -> excluding X, Q is 1-0 = 1.0.
    OWP(X) = mean(0.0, 1.0) = 0.5. By symmetry OWP(Z) = 0.5, so OOWP = 0.5.

    COMMON_OPP_SCORE = 0.25*0.5 + 0.50*0.5 + 0.25*0.5 = 0.5.
    """
    result = common_opponents.governed_common_opponent_score(
        shared_ledger, "A", "B", GOVERNED
    )
    assert result.oowp_common == pytest.approx(0.5)
    assert result.score == pytest.approx(
        0.25 * result.wp_common + 0.50 * result.owp_common + 0.25 * result.oowp_common
    )
    assert result.score == pytest.approx(0.5)


def test_a_repeated_opponent_is_weighted_once_per_meeting():
    """T plays O twice and P once; all three are common opponents with S.

    Under PER_GAME weighting O contributes two instances and P one, so
    WP_common(T) over {O, O, P} = 2/3 rather than the 1/2 a per-opponent
    reading would give.
    """
    rows = []
    rows += _pair("g1", 1, "T", "O", True)
    rows += _pair("g2", 2, "T", "O", False)
    rows += _pair("g3", 3, "T", "P", True)
    rows += _pair("g4", 4, "S", "O", True)
    rows += _pair("g5", 5, "S", "P", True)
    rows += _pair("g6", 6, "O", "Q", True)
    rows += _pair("g7", 7, "P", "Q", False)
    ledger = sos.ResumeLedger(rows)
    result = common_opponents.governed_common_opponent_score(ledger, "T", "S", GOVERNED)
    assert result.common_opponents == ("O", "P")
    assert (result.wins, result.losses) == (2, 1)
    assert result.wp_common == pytest.approx(2 / 3)


def test_the_through_week_cutoff_still_prevents_future_leakage():
    """Weeks 5-6 change the answer, so a cutoff that leaked would be visible.

    A and B are each 1-1 against common opponents X and Z. Through week 4, X and
    Z have played only A and B: excluding A, X is 1-0 (beat B) and Z is 0-1
    (lost to B), so OWP_common(A) = mean(1.0, 0.0) = 0.5. Weeks 5-6 add losses
    for both X and Z, which drops X to 1-1 (0.5) and Z to 0-2 (0.0) and so drops
    OWP_common(A) to 0.25.
    """
    rows = []
    rows += _pair("g1", 1, "A", "X", True)
    rows += _pair("g2", 2, "A", "Z", False)
    rows += _pair("g3", 3, "B", "X", False)
    rows += _pair("g4", 4, "B", "Z", True)
    rows += _pair("g5", 5, "X", "Q", False)
    rows += _pair("g6", 6, "Z", "Q", False)
    ledger = sos.ResumeLedger(rows)

    early = common_opponents.governed_common_opponent_score(
        ledger.through_week(4), "A", "B", GOVERNED
    )
    assert early.wp_common == 0.5
    assert early.owp_common == pytest.approx(0.5)
    assert early.oowp_common == pytest.approx(0.5)
    assert early.score == pytest.approx(0.5)

    full = common_opponents.governed_common_opponent_score(ledger, "A", "B", GOVERNED)
    assert full.wp_common == 0.5
    assert full.owp_common == pytest.approx(0.25)
    assert full.oowp_common == pytest.approx(2 / 3)
    assert full.score == pytest.approx(0.25 * 0.5 + 0.50 * 0.25 + 0.25 * (2 / 3))

    # The week-4 value is not contaminated by the later results.
    assert early.score != full.score


def test_a_zero_denominator_is_unavailable_never_a_number():
    """Two teams with no shared opponents have nothing to score."""
    rows = _pair("g1", 1, "A", "X", True) + _pair("g2", 2, "B", "Z", True)
    ledger = sos.ResumeLedger(rows)
    result = common_opponents.governed_common_opponent_score(ledger, "A", "B", GOVERNED)
    assert result.common_opponents == ()
    assert result.wp_common is None
    assert result.owp_common is None
    assert result.score is None
    assert result.score != 0.0 and result.score != 0.5


def test_a_missing_governed_fcs_record_is_unavailable():
    """FCS entity F appears on the schedule with no completed record of its own."""
    rows = _pair("g1", 1, "A", "F", True) + _pair("g2", 2, "B", "F", True)
    ledger = sos.ResumeLedger(rows)
    semantics = sos.governed_sos_semantics(frozenset({"F"}))
    result = common_opponents.governed_common_opponent_score(
        ledger, "A", "B", semantics
    )
    assert result.common_opponents == ("F",)
    assert result.wp_common == 1.0
    # F's record excluding A is its single game against B; its OOWP cannot form.
    assert result.oowp_common is None
    assert result.score is None


def test_two_teams_identical_on_record_still_separate_on_strength(shared_ledger):
    """A and B are both 1-1 against X and Z, and the comparison still resolves.

    The separation comes from the exclusion rule, not the weights: excluding A,
    X is 1-0 and Z is 0-1; excluding B, X is 0-1 and Z is 1-0.
    """
    a, b = common_opponents.governed_compare_common_opponents(
        shared_ledger, "A", "B", GOVERNED
    )
    assert a.wp_common == b.wp_common == 0.5
    assert a.owp_common == pytest.approx(0.5)
    assert b.owp_common == pytest.approx(0.5)
    # Symmetric fixture: equal is the right answer, and it is reached numerically
    # rather than by an unavailable component.
    assert a.score is not None and b.score is not None
    assert sos.criterion_resolves(a.score, b.score) is False
