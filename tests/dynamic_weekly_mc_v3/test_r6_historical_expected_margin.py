"""Historical expected-margin authority and fail-closed behaviour.

The load-bearing test in this file is
:func:`test_historical_path_reproduces_production_simulate_game_exactly`. Every
other guarantee here is worth nothing if the historical reconstruction and the
production simulator disagree about what the expected margin is, so that
agreement is asserted against ``game.simulate_game`` itself rather than against a
transcription of its formula.
"""

from __future__ import annotations

import json

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report, fcs, hfa
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import expected_margin as em
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.game import simulate_game
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.models import ScheduledGame, TeamPathState

ANCHOR = "TEST-ONLY axis anchor; not a governed authority"


def _state(
    team: str,
    points: float,
    *,
    week_through: int = 0,
    origin: str = em.ORIGIN_PRESEASON_OPENING,
    domain: str = em.V3_POINT_DOMAIN,
) -> em.PregameTeamPoints:
    return em.PregameTeamPoints(
        schedule_id=team,
        points=points,
        domain=domain,
        state_effective_through_week=week_through,
        origin=origin,
        source="test fixture",
    )


def _context(
    *,
    week: int = 1,
    venue: str = "HOME",
    modifier: float | None = 1.0,
    subject: str = "ALPHA",
    opponent: str = "BETA",
) -> em.HistoricalGameContext:
    return em.HistoricalGameContext(
        game_id=f"G-{week:02d}-{venue}",
        season=2024,
        week=week,
        subject_team=subject,
        opponent_team=opponent,
        venue=venue,
        home_field_modifier=modifier,
        source="test fixture",
    )


def _construct(**kwargs):
    params = {
        "context": _context(),
        "subject_state": _state("ALPHA", 20.0),
        "opponent_state": _state("BETA", 6.0),
        "hfa_baseline_points": hfa.V3_FOOTBALL_POINT_HFA,
        "axis_anchor_authority": ANCHOR,
    }
    params.update(kwargs)
    return em.construct_historical_expected_margin(**params)


# ---------------------------------------------------------------------------
# The formula is the production formula
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("venue", ["HOME", "NEUTRAL"])
def test_historical_path_reproduces_production_simulate_game_exactly(venue: str) -> None:
    """The reconstruction must equal ``simulate_game``'s deterministic mean, bitwise.

    If these two ever drift, every residual computed from the historical path is
    measured against a different model than the one V3 runs.
    """
    home = TeamPathState("ALPHA", 20.0, 20.0, 20.0)
    away = TeamPathState("BETA", 6.0, 6.0, 6.0)
    game = ScheduledGame(
        game_id="G0001",
        week=1,
        date="2026-08-29",
        game_type="REG",
        home_team="ALPHA",
        away_team="BETA",
        home_conf="X",
        away_conf="Y",
        venue=venue,
        conference_game=False,
        fcs_game=False,
        flex_rematch=False,
    )
    observation = simulate_game(
        base_seed=1,
        path_id=1,
        game=game,
        home=home,
        away=away,
        hfa_baseline_points=hfa.V3_FOOTBALL_POINT_HFA,
        home_hfa_modifier=1.0,
        game_sd_points=13.0,
        rating_state_version="test",
    )

    standalone = em.v3_expected_home_margin(
        home_strength_points=20.0,
        away_strength_points=6.0,
        venue=venue,
        hfa_baseline_points=hfa.V3_FOOTBALL_POINT_HFA,
        home_hfa_modifier=1.0,
    )
    assert standalone == observation.expected_home_margin

    subject_view = _construct(context=_context(venue="HOME" if venue == "HOME" else "NEUTRAL"))
    assert subject_view.status == em.STATUS_AUTHORIZED
    assert subject_view.expected_margin_points == observation.expected_home_margin


def test_home_and_away_views_of_one_game_are_exact_negations() -> None:
    """Re-orientation is arithmetic on one governed term, so it must be exact."""
    home_view = _construct(context=_context(venue="HOME"))
    away_view = _construct(
        context=_context(venue="AWAY", subject="BETA", opponent="ALPHA"),
        subject_state=_state("BETA", 6.0),
        opponent_state=_state("ALPHA", 20.0),
    )
    assert home_view.expected_margin_points == pytest.approx(17.5)
    assert away_view.expected_margin_points == pytest.approx(-17.5)
    assert home_view.expected_margin_points == -away_view.expected_margin_points


def test_home_sign_and_venue_term_carry_the_governed_hfa() -> None:
    result = _construct(context=_context(venue="HOME"))
    assert result.venue_adjustment_points == hfa.V3_FOOTBALL_POINT_HFA
    assert result.expected_margin_points > 20.0 - 6.0


def test_away_sign_subtracts_the_home_sides_hfa() -> None:
    result = _construct(
        context=_context(venue="AWAY", subject="BETA", opponent="ALPHA"),
        subject_state=_state("BETA", 6.0),
        opponent_state=_state("ALPHA", 20.0),
    )
    assert result.venue_adjustment_points == -hfa.V3_FOOTBALL_POINT_HFA


def test_neutral_venue_term_is_exactly_zero_not_a_default() -> None:
    """Zero because the axis is defined at neutral field, so it must be exact."""
    result = _construct(context=_context(venue="NEUTRAL", modifier=None))
    assert result.venue_adjustment_points == 0.0
    assert result.expected_margin_points == 14.0


# ---------------------------------------------------------------------------
# Fail-closed refusals
# ---------------------------------------------------------------------------


def test_missing_point_strength_is_refused_at_construction_not_defaulted() -> None:
    with pytest.raises(TypeError):
        em.PregameTeamPoints(  # type: ignore[call-arg]
            schedule_id="ALPHA",
            domain=em.V3_POINT_DOMAIN,
            state_effective_through_week=0,
            origin=em.ORIGIN_PRESEASON_OPENING,
            source="test",
        )


def test_undeclared_domain_is_refused() -> None:
    with pytest.raises(InputValidationError, match="explicit domain"):
        _state("ALPHA", 20.0, domain="")


def test_wrong_domain_returns_unavailable_with_no_number() -> None:
    result = _construct(subject_state=_state("ALPHA", 1685.0, domain="ELO"))
    assert result.status == em.STATUS_UNAVAILABLE
    assert result.expected_margin_points is None
    assert "No conversion between axes is governed" in result.reason_if_unavailable


def test_missing_hfa_authority_returns_unavailable_with_no_number() -> None:
    result = _construct(hfa_baseline_points=None)
    assert result.status == em.STATUS_UNAVAILABLE
    assert result.expected_margin_points is None
    assert "no default" in result.reason_if_unavailable


def test_legacy_v2_hfa_is_refused_by_name() -> None:
    with pytest.raises(GovernanceBlock, match="ENG-HOME-FIELD"):
        _construct(hfa_baseline_points=hfa.LEGACY_V2_DRIVE_ENGINE_HFA)


def test_elo_layer_hfa_cannot_be_borrowed_as_a_point_hfa() -> None:
    with pytest.raises(GovernanceBlock):
        _construct(hfa_baseline_points=hfa.CCG_ELO_HFA)


def test_fcs_without_adapter_fails_closed_on_the_existing_blocker() -> None:
    """An unresolved home-field modifier must refuse, never default to 1.0."""
    result = _construct(context=_context(venue="HOME", modifier=None))
    assert result.status == em.STATUS_UNAVAILABLE
    assert result.expected_margin_points is None
    assert fcs.FCS_UNIFIED_SCALE_BLOCKER in result.reason_if_unavailable


def test_fcs_point_mapping_remains_absent() -> None:
    assert fcs.GOVERNED_FCS_POLICY.unified_points_equivalent is None
    assert fcs.FCS_FIXED_ELO == 1250.0
    matrix = em.authority_matrix_as_dict()
    assert matrix["fcs_expected_margin"]["point_mapping"] is None
    assert matrix["fcs_expected_margin"]["status"] == em.STATUS_UNAVAILABLE


def test_postgame_state_containing_its_own_game_is_refused() -> None:
    with pytest.raises(GovernanceBlock, match="leaks the outcome"):
        _construct(
            context=_context(week=4),
            subject_state=_state(
                "ALPHA", 20.0, week_through=4, origin=em.ORIGIN_PROMOTED_RERATING
            ),
            opponent_state=_state(
                "BETA", 6.0, week_through=3, origin=em.ORIGIN_PROMOTED_RERATING
            ),
        )


def test_future_state_is_refused() -> None:
    with pytest.raises(GovernanceBlock, match="leaks the outcome"):
        _construct(
            context=_context(week=3),
            subject_state=_state(
                "ALPHA", 20.0, week_through=9, origin=em.ORIGIN_PROMOTED_RERATING
            ),
            opponent_state=_state(
                "BETA", 6.0, week_through=2, origin=em.ORIGIN_PROMOTED_RERATING
            ),
        )


def test_state_identity_must_match_the_game_context() -> None:
    with pytest.raises(InputValidationError, match="subject state is for"):
        _construct(subject_state=_state("GAMMA", 20.0))


# ---------------------------------------------------------------------------
# Week structure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("week", [1, 2])
def test_opening_weeks_construct_from_preseason_strength_alone(week: int) -> None:
    """Weeks 1-2 consume no calibration coefficient. That is the identifiable subset."""
    result = _construct(context=_context(week=week))
    assert result.status == em.STATUS_AUTHORIZED
    assert result.expected_margin_points == pytest.approx(17.5)
    assert week in em.PRESEASON_OPENING_WEEKS


@pytest.mark.parametrize("week", [1, 2])
def test_opening_weeks_refuse_a_promoted_state_they_could_not_have_held(week: int) -> None:
    with pytest.raises(GovernanceBlock, match="opens on preseason strength"):
        _construct(
            context=_context(week=week),
            subject_state=_state(
                "ALPHA", 20.0, week_through=0, origin=em.ORIGIN_PROMOTED_RERATING
            ),
        )


def test_week_three_refuses_preseason_strength_as_a_substitute() -> None:
    result = _construct(context=_context(week=3))
    assert result.status == em.STATUS_UNAVAILABLE
    assert result.expected_margin_points is None
    assert "silently reconstruct a different model" in result.reason_if_unavailable


def test_week_three_accepts_a_supplied_promoted_state() -> None:
    """V3 cannot reconstruct one, but a corpus may supply it from its own system."""
    result = _construct(
        context=_context(week=3),
        subject_state=_state(
            "ALPHA", 21.0, week_through=2, origin=em.ORIGIN_PROMOTED_RERATING
        ),
        opponent_state=_state(
            "BETA", 5.0, week_through=2, origin=em.ORIGIN_PROMOTED_RERATING
        ),
    )
    assert result.status == em.STATUS_AUTHORIZED
    assert result.expected_margin_points == pytest.approx(19.5)


# ---------------------------------------------------------------------------
# Authority
# ---------------------------------------------------------------------------


def test_absent_axis_anchor_yields_derivable_and_no_number() -> None:
    """The distinction the three statuses exist for: permitted vs computable."""
    result = _construct(axis_anchor_authority=None)
    assert result.status == em.STATUS_DERIVABLE
    assert result.expected_margin_points is None
    assert result.team_pregame_points is None
    assert result.formula_id == em.FORMULA_ID
    assert result.authority_bindings["axis_anchor"] == "ABSENT"
    assert "HISTORICAL_STRENGTH_AXIS_ANCHOR" in result.reason_if_unavailable


def test_authorized_result_binds_provenance_and_authority_deterministically() -> None:
    result = _construct()
    payload = result.as_dict()
    assert payload["formula_id"] == em.FORMULA_ID
    assert set(payload["source_bindings"]) == {"game", "subject_state", "opponent_state"}
    assert payload["authority_bindings"]["hfa"].startswith("R2-HFA-3P5")
    assert payload["reason_if_unavailable"] is None
    assert list(payload["source_bindings"]) == sorted(payload["source_bindings"])


def test_no_status_but_authorized_ever_carries_a_number() -> None:
    outcomes = [
        _construct(axis_anchor_authority=None),
        _construct(hfa_baseline_points=None),
        _construct(subject_state=_state("ALPHA", 1685.0, domain="ELO")),
        _construct(context=_context(venue="HOME", modifier=None)),
        _construct(context=_context(week=3)),
    ]
    for outcome in outcomes:
        assert outcome.status != em.STATUS_AUTHORIZED
        assert outcome.expected_margin_points is None
        assert outcome.venue_adjustment_points is None
        assert outcome.reason_if_unavailable


# ---------------------------------------------------------------------------
# The SOR-B scope correction
# ---------------------------------------------------------------------------


def test_sor_b_items_are_elo_domain_and_absent_from_the_point_path() -> None:
    """Neither unratified SOR-B label is read by any football-point code path."""
    from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import engine, game, sor

    assert sor.UNRATIFIED_SOR_B_ITEMS == ("P_TO_STRENGTH_TRANSFORM", "REFERENCE_HFA")
    for module in (game, engine):
        text = open(module.__file__, encoding="utf-8").read()
        for label in sor.UNRATIFIED_SOR_B_ITEMS:
            assert label not in text, f"{label} reached the point-domain path in {module}"

    # This module names both, and only to classify them out of scope.
    entries = {e["label"]: e for e in em.authority_matrix_as_dict()["entries"]}
    for label in sor.UNRATIFIED_SOR_B_ITEMS:
        assert entries[label]["status"] == "UNRATIFIED__SOR_B_SCOPE_ONLY"
        assert entries[label]["historical_calibration_usable"] is False
    assert entries["P_TO_STRENGTH_TRANSFORM"]["unit"].startswith("dimensionless")
    assert entries["REFERENCE_HFA"]["unit"] == "Elo points"


def test_expected_margin_does_not_consume_any_calibration_coefficient() -> None:
    matrix = em.authority_matrix_as_dict()
    assert matrix["formula"]["consumes_calibration_coefficients"] is False
    assert matrix["formula"]["free_parameters"] == []


def test_sor_b_scope_finding_does_not_open_a_blocker_or_rewrite_history() -> None:
    finding = em.SOR_B_SCOPE_FINDING
    assert finding["opens_formal_blocker"] is False
    assert finding["rewrites_prior_artifact"] is False


# ---------------------------------------------------------------------------
# Identification
# ---------------------------------------------------------------------------


def test_recursion_is_classified_as_parameter_conditional_not_circular() -> None:
    structure = em.IDENTIFICATION_STRUCTURE
    assert structure["circularity"] == "NOT_CIRCULAR__PARAMETER_CONDITIONAL_RECURSION"
    assert "SCALE_COEFFICIENT_CONFOUNDING" == structure["genuine_identification_failure"]["id"]


def test_stage_a_depends_on_no_calibration_coefficient() -> None:
    stage_a = next(s for s in em.IDENTIFICATION_STAGES if s["stage"] == "A")
    assert stage_a["valid"] is True
    assert not any("calibration." in d for d in stage_a["depends_on"])
    assert any("residual_coefficient" in d for d in stage_a["does_not_depend_on"])


def test_unconditional_margin_sd_is_not_game_sd_points() -> None:
    sd = em.GAME_SD_IDENTIFICATION
    assert sd["unconditional_signed_margin_sd"]["observed_2024_corpus_value"] == 19.764
    assert sd["unconditional_signed_margin_sd"]["is_game_sd_points"] is False
    assert sd["residual_game_sd"]["is_game_sd_points"] is True


# ---------------------------------------------------------------------------
# Artifact
# ---------------------------------------------------------------------------


def test_authority_matrix_is_deterministic_and_lf_terminated(tmp_path) -> None:
    first = em.write_authority_matrix(tmp_path / "a.json").read_bytes()
    second = em.write_authority_matrix(tmp_path / "b.json").read_bytes()
    assert first == second
    assert b"\r\n" not in first
    assert first.endswith(b"\n")
    payload = json.loads(first.decode("utf-8"))
    assert payload["matrix_id"] == em.MATRIX_ID
    assert list(payload) == sorted(payload)


def test_authority_matrix_keeps_the_hfa_families_separate() -> None:
    entries = {e["label"]: e for e in em.authority_matrix_as_dict()["entries"]}
    assert entries["V3_HFA_3_5"]["unit"] == "football points"
    assert entries["CCG_MC_ELO_HFA_65"]["unit"] == "Elo points"
    assert entries["V2_1_HFA_4_0"]["status"] == "HISTORICAL / NOT CURRENT"
    assert entries["ELO_HFA_55"]["status"] == "NOT_PRESENT_IN_THIS_REPOSITORY"
    assert entries["ELO_HFA_55"]["governed"] is False


def test_authority_matrix_promotes_nothing() -> None:
    matrix = em.authority_matrix_as_dict()
    assert matrix["parameters_promoted"] == []
    assert matrix["canonical_config_written"] is False
    assert matrix["formal_blockers_opened"] == []
    assert matrix["formal_blockers_retired"] == []


def test_lane_opens_no_formal_blocker() -> None:
    """Eight formal blockers before, eight after. The dependency is not one of them."""
    live = blocker_report.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    assert len(live) == 8
    assert em.HISTORICAL_AXIS_ANCHOR_DEPENDENCY["is_formal_project_blocker"] is False
    assert em.HISTORICAL_AXIS_ANCHOR_DEPENDENCY["dependency_id"] not in live
    assert not any("EXPECTED_MARGIN" in b for b in live)


def test_matrix_covers_every_label_the_lane_was_asked_to_classify() -> None:
    required = {
        "CURRENT_V3_FOOTBALL_STRENGTH_DOMAIN",
        "PRESEASON_STRENGTH_TRANSFORM",
        "P_TO_STRENGTH_TRANSFORM",
        "REFERENCE_HFA",
        "V3_HFA_3_5",
        "V2_1_HFA_4_0",
        "ELO_HFA_55",
        "CCG_MC_ELO_HFA_65",
        "BAXTER_DOMAIN",
        "COLLEY_DOMAIN",
        "SRS_DOMAIN",
        "FCS_ELO_1250",
        "FCS_POINT_ADAPTER",
    }
    labels = {e["label"] for e in em.authority_matrix_as_dict()["entries"]}
    assert required <= labels


def test_pregame_contract_requires_no_future_or_postgame_field() -> None:
    contract = em.pregame_state_contract()
    required = set(contract["required_fields"])
    assert "actual_margin" not in required
    assert "final_committee_rank" not in required
    assert "game_sd_points" not in required
    assert "order_key" in required
    assert "strength_domain" in required
