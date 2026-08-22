"""Tests for the leak-free historical opening backcast register (R1).

The two findings this lane rests on are asserted against the governed workbook
itself rather than against constants copied into the test, so a replacement
input that changes the rule fails here instead of silently changing the meaning
of every conclusion built on the old one.
"""

from __future__ import annotations

import statistics

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import opening_backcast as ob
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)

pytest.importorskip("openpyxl")

WORKBOOK = "reference/dynamic_weekly_mc_v3/inputs/2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx"

#: Master Ratings column offsets, zero-based, header on row 4.
COL_TEAM = 1
COL_BAXTER_2025 = 38
COL_PURE_BAXTER = 42
COL_TRUESKILL_Z = 64
COL_LITKENHOUS_Z = 65
COL_BOARD_FAMILY_Z = 68
COL_PURE_BAXTER_Z = 69
COL_UNIFIED_Z = 70


def _master_rows():
    import openpyxl

    book = openpyxl.load_workbook(WORKBOOK, data_only=True)
    return [row for row in book["Master Ratings"].iter_rows(min_row=5, values_only=True) if row[COL_TEAM]]


# --- the affine finding -------------------------------------------------------


def test_the_pure_baxter_carryover_slope_is_exactly_the_registered_one():
    """The 0.70 in the register is measured from the workbook, not quoted from it.

    The Data Dictionary states the rule in words; the Master Ratings sheet
    carries both sides of it. Deriving the slope from the two columns is what
    makes the affine argument a fact about the artifact rather than a reading of
    its prose.
    """
    rows = _master_rows()
    ratios = [row[COL_PURE_BAXTER] / row[COL_BAXTER_2025] for row in rows if row[COL_BAXTER_2025]]
    registered = {t.family: t for t in ob.GOVERNED_CARRYOVER_TRANSFORMS}["Pure Baxter"]
    assert len(ratios) == 121
    assert max(abs(r - registered.slope) for r in ratios) < 1e-12


def test_both_governed_carryovers_leave_the_standardized_state_unchanged():
    """Z invariance under a positive affine map, on the workbook's own field."""
    rows = _master_rows()
    field = {row[COL_TEAM]: float(row[COL_BAXTER_2025]) for row in rows}
    for transform in ob.GOVERNED_CARRYOVER_TRANSFORMS:
        witness = ob.affine_invariance_witness(field, transform)
        assert witness["z_invariant"] is True
        assert witness["max_abs_z_difference"] < 1e-9
        assert witness["population"] == 121


def test_a_carryover_with_a_non_positive_slope_is_refused():
    with pytest.raises(InputValidationError):
        ob.affine_invariance_witness(
            {"a": 1.0, "b": 2.0},
            ob.CarryoverTransform("bogus", "x -> -x", -1.0, 0.0, "none"),
        )


def test_a_transform_cannot_be_applied_to_a_team_value():
    with pytest.raises(GovernanceBlock):
        ob.GOVERNED_CARRYOVER_TRANSFORMS[0].apply(12.0)


# --- standardization ----------------------------------------------------------


def test_standardization_uses_the_sample_deviation_the_workbook_divides_by():
    rows = _master_rows()
    field = {row[COL_TEAM]: float(row[COL_PURE_BAXTER]) for row in rows}
    published = {row[COL_TEAM]: float(row[COL_PURE_BAXTER_Z]) for row in rows}
    recomputed = ob.standardize(field)
    assert max(abs(recomputed[t] - published[t]) for t in published) < 1e-12
    population_style = ob.standardize(field, ddof=0)
    assert max(abs(population_style[t] - published[t]) for t in published) > 1e-6


def test_a_population_with_no_dispersion_is_refused_rather_than_zeroed():
    with pytest.raises(InputValidationError):
        ob.standardize({"a": 1500.0, "b": 1500.0, "c": 1500.0})


def test_standardization_refuses_a_population_of_one():
    with pytest.raises(InputValidationError):
        ob.standardize({"a": 1.0})


# --- family coverage ----------------------------------------------------------


def test_exactly_one_of_the_four_v3_families_is_historically_reproducible():
    reproducible = [f.family for f in ob.V3_FAMILY_REPRODUCIBILITY if f.historically_reproducible]
    assert reproducible == ["Pure Baxter"]
    assert ob.REPRODUCIBLE_FAMILY_WEIGHT == pytest.approx(0.25)


def test_the_registered_weights_are_the_workbook_weights_and_sum_to_one():
    assert sum(f.weight for f in ob.V3_FAMILY_REPRODUCIBILITY) == pytest.approx(1.0)
    rows = _master_rows()
    rebuilt = [
        0.25 * (row[COL_TRUESKILL_Z] + row[COL_LITKENHOUS_Z] + row[COL_PURE_BAXTER_Z] + row[COL_BOARD_FAMILY_Z])
        for row in rows
    ]
    published = [row[COL_UNIFIED_Z] for row in rows]
    assert max(abs(a - b) for a, b in zip(rebuilt, published)) < 1e-12


def test_a_partial_family_set_may_not_be_called_the_v3_ensemble():
    with pytest.raises(GovernanceBlock):
        ob.require_full_family_coverage(["Pure Baxter"])
    ob.require_full_family_coverage([f.family for f in ob.V3_FAMILY_REPRODUCIBILITY])


def test_the_natural_multi_family_proxy_ensemble_is_the_refused_bwi_blend():
    """The blend a Unified-Z-analogous proxy would need is already not adopted."""
    for blend in (["BAXTER", "SRS"], ["BAXTER", "COLLEY"], ["SRS", "COLLEY"]):
        with pytest.raises(GovernanceBlock):
            ob.refuse_multi_family_proxy_ensemble(blend)
    ob.refuse_multi_family_proxy_ensemble(["BAXTER"])


# --- the research-only gates --------------------------------------------------


def test_no_per_team_opening_value_may_be_emitted():
    with pytest.raises(GovernanceBlock):
        ob.require_no_canonical_opening_values()
    with pytest.raises(GovernanceBlock):
        ob.require_no_canonical_opening_values(values={"ALA": 1.9})


def test_the_proxy_and_the_exact_ensemble_stay_two_named_things():
    assert ob.classify("historical calibration proxy") == ob.PROXY_CLASS
    assert ob.classify(ob.NOT_PROXY_CLASS) == ob.NOT_PROXY_CLASS
    with pytest.raises(InputValidationError):
        ob.classify("opening strength")
    ob.require_proxy_not_presented_as_ensemble(ob.PROXY_CLASS)
    with pytest.raises(GovernanceBlock):
        ob.require_proxy_not_presented_as_ensemble(ob.NOT_PROXY_CLASS)


# --- calibration consequence --------------------------------------------------


def test_the_point_scale_is_the_parameter_the_proxy_may_not_touch():
    with pytest.raises(GovernanceBlock) as excinfo:
        ob.require_proxy_admissible_parameter("POINT_SCALE_IDENTIFICATION")
    assert "biased low" in str(excinfo.value)


def test_game_sd_is_admitted_as_a_bound_and_refused_as_a_value():
    entry = {p.parameter: p for p in ob.PROXY_CALIBRATION_SUPPORT}["GAME_SD"]
    assert entry.support == "BOUND_ONLY"
    assert entry.direction == "biased high"
    with pytest.raises(GovernanceBlock):
        ob.require_proxy_admissible_parameter("game_sd")


def test_the_three_research_supported_parameters_are_returned_not_refused():
    for name in ob.RESEARCH_SUPPORTED_BY_PROXY:
        assert ob.require_proxy_admissible_parameter(name).parameter == name
    assert set(ob.RESEARCH_SUPPORTED_BY_PROXY) == {
        "BLOWOUT_TREATMENT",
        "RECENT_FORM",
        "SAMPLE_SIZE_REGULARIZATION",
    }


def test_an_unregistered_parameter_is_an_input_error_not_a_silent_pass():
    with pytest.raises(InputValidationError):
        ob.require_proxy_admissible_parameter("HFA_BASELINE_POINTS")


def test_every_contaminated_parameter_carries_a_signed_direction():
    """The biases share one cause, so none of them is merely noise."""
    for entry in ob.PROXY_CALIBRATION_SUPPORT:
        if entry.support in ("REFUSED", "BOUND_ONLY"):
            assert entry.direction != "unquantified"
            assert entry.basis


# --- season coverage ----------------------------------------------------------


def test_three_of_the_four_requested_openings_are_constructible_and_2021_is_not():
    assert ob.CONSTRUCTIBLE_OPENINGS == (2022, 2023, 2024)
    blocked = [s for s in ob.SEASON_BACKCASTS if not s.constructible]
    assert [s.opening_season for s in blocked] == [2021]
    assert "2020" in blocked[0].reason


def test_each_backcast_names_the_prior_season_it_consumes():
    for season in ob.SEASON_BACKCASTS:
        assert season.prior_season == season.opening_season - 1


def test_the_witness_helper_is_stable_under_a_reordered_population():
    """Z scores are a property of the population, not of dict insertion order."""
    field = {"a": 3.0, "b": -1.0, "c": 8.0, "d": 0.5}
    reordered = {k: field[k] for k in reversed(list(field))}
    first = ob.standardize(field)
    second = ob.standardize(reordered)
    assert max(abs(first[k] - second[k]) for k in field) < 1e-15
    assert statistics.fmean(first.values()) == pytest.approx(0.0, abs=1e-12)
