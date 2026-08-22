"""Historical opening-state reconstruction, R1.

Two things are being protected here and they pull in opposite directions.

The first is that the construction is an exact mirror of the 2026 one. That is
checked against the governed workbook itself rather than against numbers copied
into this file, so the test fails if the workbook is ever replaced with one that
builds its Unified Master Z differently -- which is precisely when a historical
reconstruction built on the old rule would start being quietly wrong.

The second is that every refusal is real. A lane whose result is "no evidence
exists" is only worth anything if the machinery would have said something
different had evidence existed, so the refusals are tested by constructing the
admissible case and watching it succeed, then removing exactly one thing and
watching it fail.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import replace
from pathlib import Path

import pytest
from openpyxl import load_workbook

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import historical_opening_state as hos
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import (
    GovernanceBlock,
    InputValidationError,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.inputs import load_canonical_team_index

REPO_ROOT = Path(__file__).resolve().parents[2]
RATINGS_XLSX = (
    REPO_ROOT
    / "reference/dynamic_weekly_mc_v3/inputs/2026_CFB_2026_Preseason_Unified_Power_Ratings.xlsx"
)
CANONICAL_MD = (
    REPO_ROOT
    / "reference/dynamic_weekly_mc_v3/inputs/2026_TEAM_CANONICAL_MASTER_v2_LLM_GROUNDING.md"
)
ARTIFACT_DIR = REPO_ROOT / hos.OPENING_STATE_REFERENCE_DIR


@pytest.fixture(scope="module")
def workbook_rows():
    """The 121 published 2026 rows, keyed by column name."""
    wb = load_workbook(RATINGS_XLSX, read_only=True, data_only=True)
    ws = wb["Master Ratings"]
    rows = list(ws.iter_rows(min_row=4, values_only=True))
    header = [str(x) for x in rows[0]]
    index = {name: i for i, name in enumerate(header)}
    data = [r for r in rows[1:] if r[index["Schedule ID"]] is not None]
    assert len(data) == 121
    return index, data


def _column(index, data, name):
    return {str(r[index["Schedule ID"]]): float(r[index[name]]) for r in data}


# ---------------------------------------------------------------------------
# The 2026 construction, mirrored exactly
# ---------------------------------------------------------------------------


def test_the_four_governed_families_and_weights_are_what_the_workbook_states():
    assert [f.family_id for f in hos.V3_PRESEASON_FAMILIES] == [
        "TRUESKILL",
        "LITKENHOUS",
        "PURE_BAXTER",
        "BOARD_FAMILY",
    ]
    assert all(f.weight == 0.25 for f in hos.V3_PRESEASON_FAMILIES)
    assert sum(f.weight for f in hos.V3_PRESEASON_FAMILIES) == 1.0
    assert hos.BOARD_FAMILY_MEMBERS == ("BOARD_I_H", "BOARD_J_B")


@pytest.mark.parametrize(
    "native_column,z_column,family_id",
    [
        ("TrueSkill 2026 Preseason μ", "TrueSkill Z", "TRUESKILL"),
        ("Litkenhous Adjusted Power", "Litkenhous Z", "LITKENHOUS"),
        ("2026 Pure Baxter Rating", "Pure Baxter Z", "PURE_BAXTER"),
        ("Board I-H Power Rating (power_H)", "Board I-H Z", "BOARD_I_H"),
        ("Board J-B Run2 Power Rating (power_Run2)", "Board J-B Z", "BOARD_J_B"),
    ],
)
def test_standardize_family_reproduces_the_published_2026_z_scores(
    workbook_rows, native_column, z_column, family_id
):
    """The whole mirror rests on this: same inputs, same published outputs."""
    index, data = workbook_rows
    natives = _column(index, data, native_column)
    published = _column(index, data, z_column)
    _, computed = hos.standardize_family(
        family_id, 2026, "FBS_2026", natives, native_field=native_column
    )
    assert set(computed) == set(published)
    for team, value in computed.items():
        assert value == pytest.approx(published[team], abs=1e-12)


def test_the_divisor_is_the_sample_deviation_and_the_population_one_would_be_wrong(
    workbook_rows,
):
    """ddof is measured, not read off the sheet's 'Population Statistics' label.

    Both deviations are computed here so the test records the size of the error
    the documented reading would have introduced, rather than merely asserting
    the right answer.
    """
    index, data = workbook_rows
    natives = _column(index, data, "TrueSkill 2026 Preseason μ")
    values = list(natives.values())
    record, _ = hos.standardize_family(
        "TRUESKILL", 2026, "FBS_2026", natives, native_field="mu"
    )
    assert hos.STANDARDIZATION_DDOF == 1
    assert record.ddof == 1
    assert record.n == 121
    assert record.standard_deviation == pytest.approx(statistics.stdev(values), abs=1e-15)
    assert record.standard_deviation != pytest.approx(
        statistics.pstdev(values), abs=1e-9
    )
    assert record.standard_deviation == pytest.approx(4.35928836282486, abs=1e-12)


def test_board_family_is_the_mean_of_two_separately_standardized_members(workbook_rows):
    index, data = workbook_rows
    published = _column(index, data, "Board Family Z")
    _, ih = hos.standardize_family(
        "BOARD_I_H",
        2026,
        "FBS_2026",
        _column(index, data, "Board I-H Power Rating (power_H)"),
        native_field="power_H",
    )
    _, jb = hos.standardize_family(
        "BOARD_J_B",
        2026,
        "FBS_2026",
        _column(index, data, "Board J-B Run2 Power Rating (power_Run2)"),
        native_field="power_Run2",
    )
    for team, expected in published.items():
        got = hos.board_family_z({"BOARD_I_H": ih[team], "BOARD_J_B": jb[team]})
        assert got == pytest.approx(expected, abs=1e-12)


def test_combine_unified_z_reproduces_every_published_unified_master_z(workbook_rows):
    index, data = workbook_rows
    published = _column(index, data, "Unified Master Z")
    families = {}
    for family_id, column in (
        ("TRUESKILL", "TrueSkill 2026 Preseason μ"),
        ("LITKENHOUS", "Litkenhous Adjusted Power"),
        ("PURE_BAXTER", "2026 Pure Baxter Rating"),
        ("BOARD_I_H", "Board I-H Power Rating (power_H)"),
        ("BOARD_J_B", "Board J-B Run2 Power Rating (power_Run2)"),
    ):
        _, z = hos.standardize_family(
            family_id, 2026, "FBS_2026", _column(index, data, column), native_field=column
        )
        families[family_id] = z
    for team, expected in published.items():
        unified = hos.combine_unified_z(
            {
                "TRUESKILL": families["TRUESKILL"][team],
                "LITKENHOUS": families["LITKENHOUS"][team],
                "PURE_BAXTER": families["PURE_BAXTER"][team],
                "BOARD_FAMILY": hos.board_family_z(
                    {
                        "BOARD_I_H": families["BOARD_I_H"][team],
                        "BOARD_J_B": families["BOARD_J_B"][team],
                    }
                ),
            }
        )
        assert unified == pytest.approx(expected, abs=1e-12)


def test_the_index_transform_reproduces_the_published_power_index(workbook_rows):
    index, data = workbook_rows
    for row in data:
        z = float(row[index["Unified Master Z"]])
        published = float(row[index["Unified Master Power Index"]])
        assert hos.unified_power_index(z) == pytest.approx(published, abs=1e-9)


def test_the_workbooks_own_points_are_14x_z_and_the_module_still_refuses_to_emit_them(
    workbook_rows,
):
    """The transform is known and reproducible. That is not authority to use it."""
    index, data = workbook_rows
    row = data[0]
    z = float(row[index["Unified Master Z"]])
    published_points = float(row[index["Unified Neutral-Field Points"]])
    assert published_points == pytest.approx(
        hos.V3_NEUTRAL_FIELD_POINT_SCALE * z, abs=1e-9
    )
    with pytest.raises(GovernanceBlock, match="research-only"):
        hos.candidate_points_if_14x_z(z)
    stamped = hos.candidate_points_if_14x_z(z, research_only=True)
    assert stamped["status"] == "NON_AUTHORIZED_RESEARCH_ONLY"
    assert stamped["usable_as_v3_football_points"] is False
    assert stamped["authority"] == "UNRATIFIED_FOR_HISTORICAL_REUSE"


# ---------------------------------------------------------------------------
# Z-score and population determinism
# ---------------------------------------------------------------------------


def test_standardization_is_deterministic_under_input_ordering():
    """Dict insertion order must not reach the mean, the SD or any Z score."""
    forward = {"AAA": 1.0, "BBB": 5.0, "CCC": 9.0, "DDD": 2.0}
    reversed_order = dict(reversed(list(forward.items())))
    first, z_first = hos.standardize_family(
        "TRUESKILL", 2021, "P", forward, native_field="x"
    )
    second, z_second = hos.standardize_family(
        "TRUESKILL", 2021, "P", reversed_order, native_field="x"
    )
    assert first == second
    assert z_first == z_second


def test_mean_and_sd_use_the_governed_divisor_and_refuse_degenerate_populations():
    mean, sd = hos.population_mean_sd([1.0, 2.0, 3.0, 4.0])
    assert mean == pytest.approx(2.5)
    assert sd == pytest.approx(statistics.stdev([1.0, 2.0, 3.0, 4.0]))
    with pytest.raises(InputValidationError, match="at least 2"):
        hos.population_mean_sd([1.0])
    with pytest.raises(InputValidationError, match="zero dispersion"):
        hos.population_mean_sd([1500.0] * 40)


def test_the_flat_1500_opening_elo_actually_on_disk_is_what_zero_dispersion_refuses():
    """The refusal above is not hypothetical.

    The one leak-free season-opening rating state found anywhere on this
    filesystem is a research Elo of exactly 1500.0 for every team, recorded in
    the register. Standardizing it is the concrete mistake this guard prevents,
    and the alternative -- returning zeros -- would read as 'every team is
    exactly average' rather than as 'this source says nothing'.
    """
    source = next(
        s
        for s in hos.HISTORICAL_OPENING_STATE_SOURCE_REGISTER
        if s.source_id == "POWER_CRUNCH_PREGAME_STATES_2024_2025"
    )
    assert source.disposition == "REFUSED_DEGENERATE_AND_FOREIGN_SCALE"
    assert any("1500.0" in line for line in source.evidence)
    with pytest.raises(InputValidationError, match="zero dispersion"):
        hos.population_mean_sd([1500.0, 1500.0, 1500.0])


def test_lower_is_stronger_directionality_flips_the_sign_and_is_recorded():
    natives = {"A": 1.0, "B": 3.0, "C": 5.0}
    record, z = hos.standardize_family(
        "TRUESKILL",
        2021,
        "P",
        natives,
        native_field="x",
        directionality="LOWER_IS_STRONGER",
    )
    assert record.directionality == "LOWER_IS_STRONGER"
    assert record.formula == "z = -(x - mean) / sd"
    assert z["A"] > 0 and z["C"] < 0
    with pytest.raises(InputValidationError, match="directionality"):
        hos.standardize_family(
            "TRUESKILL", 2021, "P", natives, native_field="x", directionality="SIDEWAYS"
        )


def test_a_missing_native_is_excluded_rather_than_imputed():
    record, z = hos.standardize_family(
        "TRUESKILL", 2021, "P", {"A": 1.0, "B": 3.0, "C": 5.0}, native_field="x"
    )
    assert record.n == 3
    assert "NOT_IMPUTED" in record.missing_value_handling
    assert "D" not in z


# ---------------------------------------------------------------------------
# Leakage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("refused_class", hos.LEAKAGE_REFUSED_CLASSES)
def test_no_source_that_postdates_kickoff_may_supply_an_opening_state(refused_class):
    source = hos.RegisteredSource(
        source_id="PROBE",
        location="probe",
        sha256="0" * 64,
        size_bytes=1,
        seasons_declared=(2024,),
        source_class=refused_class,
        provides_families=("TRUESKILL",),
        admissible=False,
        disposition="probe",
    )
    with pytest.raises(hos.FutureLeakageRefused):
        hos.require_preseason_source(source, 2024)


def test_a_source_cannot_declare_itself_admissible_while_carrying_a_refused_class():
    with pytest.raises(GovernanceBlock, match="never admissible"):
        hos.RegisteredSource(
            source_id="PROBE",
            location="probe",
            sha256="0" * 64,
            size_bytes=1,
            seasons_declared=(2024,),
            source_class="SEASON_FINAL_RATING",
            provides_families=("PURE_BAXTER",),
            admissible=True,
            disposition="probe",
        )


def test_a_preseason_source_is_admitted_only_for_the_seasons_it_declares():
    source = hos.RegisteredSource(
        source_id="PROBE",
        location="probe",
        sha256="0" * 64,
        size_bytes=1,
        seasons_declared=(2022,),
        source_class="PRESEASON_SOURCE",
        provides_families=("TRUESKILL",),
        admissible=True,
        disposition="probe",
    )
    assert hos.require_preseason_source(source, 2022) is source
    with pytest.raises(InputValidationError, match="does not declare season"):
        hos.require_preseason_source(source, 2023)


def test_membership_declarations_may_scope_a_population_but_never_carry_a_strength():
    source = next(
        s
        for s in hos.HISTORICAL_OPENING_STATE_SOURCE_REGISTER
        if s.source_id == "SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026"
    )
    assert source.source_class == "MEMBERSHIP_DECLARATION"
    assert source.provides_families == ()
    assert "MEMBERSHIP_DECLARATION" not in hos.ADMISSIBLE_SOURCE_CLASSES
    with pytest.raises(GovernanceBlock, match="may not"):
        hos.require_preseason_source(source, 2021)


def test_no_registered_source_is_admissible_and_the_baxter_2024_case_says_why():
    """The lane result, asserted rather than narrated."""
    admissible = [
        s for s in hos.HISTORICAL_OPENING_STATE_SOURCE_REGISTER if s.admissible
    ]
    assert admissible == []
    baxter = next(
        s
        for s in hos.HISTORICAL_OPENING_STATE_SOURCE_REGISTER
        if s.source_id == "BAXTER_RATINGS_2024_SEASON_FINAL"
    )
    assert baxter.seasons_declared == (2024,)
    assert baxter.source_class == "SEASON_FINAL_RATING"
    assert any("games" in line for line in baxter.evidence)
    with pytest.raises(hos.FutureLeakageRefused):
        hos.require_preseason_source(baxter, 2024)


# ---------------------------------------------------------------------------
# Component completeness
# ---------------------------------------------------------------------------


def test_a_complete_family_set_combines_and_any_missing_one_refuses():
    complete = {
        "TRUESKILL": 1.0,
        "LITKENHOUS": -1.0,
        "PURE_BAXTER": 0.5,
        "BOARD_FAMILY": -0.5,
    }
    assert hos.combine_unified_z(complete) == pytest.approx(0.0)
    for dropped in hos.REQUIRED_FAMILY_IDS:
        partial = {k: v for k, v in complete.items() if k != dropped}
        with pytest.raises(hos.ComponentUnavailable, match=dropped):
            hos.combine_unified_z(partial)


def test_a_partial_set_is_never_renormalized_into_a_plausible_number():
    """Three families averaged look exactly like four families averaged."""
    three = {"TRUESKILL": 2.0, "LITKENHOUS": 2.0, "PURE_BAXTER": 2.0}
    with pytest.raises(hos.ComponentUnavailable):
        hos.combine_unified_z(three)
    assert hos.combine_unified_z({**three, "BOARD_FAMILY": 2.0}) == pytest.approx(2.0)


def test_an_unknown_family_is_refused_rather_than_silently_ignored():
    with pytest.raises(InputValidationError, match="unknown families"):
        hos.combine_unified_z(
            {
                "TRUESKILL": 1.0,
                "LITKENHOUS": 1.0,
                "PURE_BAXTER": 1.0,
                "BOARD_FAMILY": 1.0,
                "SP_PLUS": 1.0,
            }
        )


def test_half_a_board_family_is_refused():
    assert hos.board_family_z({"BOARD_I_H": 1.0, "BOARD_J_B": 3.0}) == pytest.approx(2.0)
    with pytest.raises(hos.ComponentUnavailable, match="BOARD_J_B"):
        hos.board_family_z({"BOARD_I_H": 1.0})


def test_a_state_cannot_claim_full_reconstruction_without_a_unified_z():
    identity = hos.HistoricalTeamIdentity(
        season=2021, historical_key="X", historical_name="X", division="FBS"
    )
    with pytest.raises(InputValidationError, match="FULLY_RECONSTRUCTED without"):
        hos.TeamSeasonOpeningState(
            season=2021,
            team_key="X",
            identity=identity,
            native_inputs=(),
            standardized_components=(),
            board_family_z=None,
            opening_unified_z=None,
            included_family_count=4,
            status=hos.OpeningStatus.FULLY_RECONSTRUCTED,
            missing_reasons=(),
            population_id="P",
            confidence="HIGH",
        )
    with pytest.raises(InputValidationError, match="without\\s+a complete"):
        hos.TeamSeasonOpeningState(
            season=2021,
            team_key="X",
            identity=identity,
            native_inputs=(),
            standardized_components=(),
            board_family_z=None,
            opening_unified_z=0.4,
            included_family_count=2,
            status=hos.OpeningStatus.PARTIALLY_RECONSTRUCTED,
            missing_reasons=(),
            population_id="P",
            confidence="NONE",
        )


def test_every_missing_reason_comes_from_the_governed_vocabulary():
    identity = hos.HistoricalTeamIdentity(
        season=2021, historical_key="X", historical_name="X", division="FBS"
    )
    with pytest.raises(InputValidationError, match="unknown missing reason"):
        hos.TeamSeasonOpeningState(
            season=2021,
            team_key="X",
            identity=identity,
            native_inputs=(),
            standardized_components=(),
            board_family_z=None,
            opening_unified_z=None,
            included_family_count=0,
            status=hos.OpeningStatus.UNAVAILABLE,
            missing_reasons=(("BECAUSE", "no"),),
            population_id="P",
            confidence="NONE",
        )


# ---------------------------------------------------------------------------
# Population
# ---------------------------------------------------------------------------


def test_a_lone_unmounted_candidate_does_not_resolve_a_population():
    for season in (2021, 2022, 2023):
        population = hos.resolve_population(
            season, hos.HISTORICAL_POPULATION_CANDIDATES, scope="FBS"
        )
        assert population.status == "UNRESOLVED_SOURCE_NOT_MOUNTED"
        assert len(population.candidates) == 1
        with pytest.raises(GovernanceBlock):
            population.require_resolved()


def test_2024_is_unresolved_because_two_sources_disagree_by_fifteen_teams():
    population = hos.resolve_population(
        2024, hos.HISTORICAL_POPULATION_CANDIDATES, scope="FBS"
    )
    assert population.status == "UNRESOLVED_CONFLICTING_CANDIDATES"
    counts = sorted(c.count for c in population.candidates)
    assert counts == [118, 133]


def test_mounting_the_single_candidate_is_what_resolves_a_season():
    """The refusal is about mounting, not about counting candidates."""
    population = hos.resolve_population(
        2021,
        hos.HISTORICAL_POPULATION_CANDIDATES,
        scope="FBS",
        mounted_source_ids=("SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026",),
    )
    assert population.status == "RESOLVED"
    assert population.require_resolved() is population
    still_conflicting = hos.resolve_population(
        2024,
        hos.HISTORICAL_POPULATION_CANDIDATES,
        scope="FBS",
        mounted_source_ids=("SYNTHETIC_NCAA_CONFERENCE_DISTRIBUTION_2021_2026",),
    )
    assert still_conflicting.status == "UNRESOLVED_CONFLICTING_CANDIDATES"


def test_population_resolution_is_deterministic_under_candidate_ordering():
    forward = hos.HISTORICAL_POPULATION_CANDIDATES
    backward = tuple(reversed(forward))
    for season in hos.HISTORICAL_SEASONS:
        a = hos.resolve_population(season, forward, scope="FBS")
        b = hos.resolve_population(season, backward, scope="FBS")
        assert a.status == b.status
        assert sorted(c.population_id for c in a.candidates) == sorted(
            c.population_id for c in b.candidates
        )


def test_a_season_with_no_candidate_is_distinguished_from_one_with_a_bad_candidate():
    empty = hos.resolve_population(2019, hos.HISTORICAL_POPULATION_CANDIDATES, scope="FBS")
    assert empty.status == "UNRESOLVED_NO_CANDIDATE"
    assert empty.candidates == ()


# ---------------------------------------------------------------------------
# The historical population is not the synthetic 2026 scope
# ---------------------------------------------------------------------------


def test_the_historical_frame_is_not_the_2026_canonical_universe():
    """134 synthetic 2026 entities against 251 historical ones, per season."""
    identities = hos.load_membership_frame(
        REPO_ROOT / hos.OPENING_STATE_REFERENCE_DIR / hos.MEMBERSHIP_FRAME_FILENAME
    )
    canonical = load_canonical_team_index(CANONICAL_MD)
    assert len(canonical) == 134
    for season in hos.HISTORICAL_SEASONS:
        rows = [i for i in identities if i.season == season]
        assert len(rows) == 251
        assert len(rows) != len(canonical)
    fbs_counts = {
        season: sum(
            1
            for i in identities
            if i.season == season and i.division == hos.FBS_DIVISION_LABEL
        )
        for season in hos.HISTORICAL_SEASONS
    }
    assert fbs_counts == {2021: 130, 2022: 131, 2023: 133, 2024: 133}
    assert 121 not in set(fbs_counts.values())


def test_the_2026_canonical_division_is_never_used_as_a_historical_division():
    """The two axes disagree in both directions, and the frame follows the season.

    North Dakota State is an ``FBS_MEMBER`` in the synthetic 2026 master and was
    FCS in these seasons. Arkansas State is ``SCHEDULE_ONLY_FCS`` there and was
    FBS in these seasons. If the canonical scope were leaking into the frame,
    one of these two would be wrong.
    """
    identities = {
        (i.season, i.historical_key): i
        for i in hos.load_membership_frame(
            REPO_ROOT / hos.OPENING_STATE_REFERENCE_DIR / hos.MEMBERSHIP_FRAME_FILENAME
        )
    }
    canonical = load_canonical_team_index(CANONICAL_MD)
    assert canonical["NDSU"]["entity_scope"] == "FBS_MEMBER"
    assert canonical["ARST"]["entity_scope"] == "SCHEDULE_ONLY_FCS"
    for season in hos.HISTORICAL_SEASONS:
        assert identities[(season, "North Dakota St.")].division == "FCS"
        assert identities[(season, "Arkansas St.")].division == "FBS"


def test_the_canonical_master_is_registered_as_refused_for_historical_population():
    source = next(
        s
        for s in hos.HISTORICAL_OPENING_STATE_SOURCE_REGISTER
        if s.source_id == "V3_CANONICAL_TEAM_MASTER_2026"
    )
    assert source.disposition == "REFUSED_AS_HISTORICAL_POPULATION"
    assert source.admissible is False


# ---------------------------------------------------------------------------
# Identity and alias reconciliation
# ---------------------------------------------------------------------------


def test_exact_canonical_keys_bind_and_near_misses_do_not():
    canonical = load_canonical_team_index(CANONICAL_MD)
    bound = hos.bind_canonical_identity(
        hos.HistoricalTeamIdentity(
            season=2021, historical_key="Clemson", historical_name="Clemson", division="FBS"
        ),
        canonical,
    )
    assert bound.canonical_binding == "EXACT_CANONICAL_KEY"
    assert bound.canonical_schedule_id is not None
    unbound = hos.bind_canonical_identity(
        hos.HistoricalTeamIdentity(
            season=2021,
            historical_key="NC St.",
            historical_name="NC St.",
            division="FBS",
        ),
        canonical,
    )
    assert unbound.canonical_binding == "UNBOUND_HISTORICAL_ENTITY"
    assert unbound.canonical_schedule_id is None


def test_an_unbound_historical_entity_is_preserved_not_dropped():
    """Dropping one would change every mean a later lane computes."""
    canonical = load_canonical_team_index(CANONICAL_MD)
    identities = hos.load_membership_frame(
        REPO_ROOT / hos.OPENING_STATE_REFERENCE_DIR / hos.MEMBERSHIP_FRAME_FILENAME
    )
    bound = hos.bind_frame_identities(identities, canonical)
    assert len(bound) == len(identities)
    unbound = [i for i in bound if i.canonical_binding == "UNBOUND_HISTORICAL_ENTITY"]
    assert unbound, "the historical universe is larger than the canonical one"
    assert all(i.division for i in unbound)


def test_two_historical_entities_may_not_collapse_onto_one_canonical_id():
    canonical = {
        "DUP": {
            "schedule_id": "DUP",
            "team_name": "Duplicate",
            "abbreviated_name": "DUP",
        }
    }
    frame = (
        hos.HistoricalTeamIdentity(
            season=2021, historical_key="DUP", historical_name="DUP", division="FBS"
        ),
        hos.HistoricalTeamIdentity(
            season=2021,
            historical_key="Duplicate",
            historical_name="Duplicate",
            division="FBS",
        ),
    )
    bound = hos.bind_frame_identities(frame, canonical)
    assert all(i.canonical_binding == "UNBOUND_HISTORICAL_ENTITY" for i in bound)
    assert all(i.canonical_schedule_id is None for i in bound)


def test_the_same_canonical_id_may_recur_across_seasons():
    canonical = {
        "AAA": {"schedule_id": "AAA", "team_name": "Alpha", "abbreviated_name": "AAA"}
    }
    frame = tuple(
        hos.HistoricalTeamIdentity(
            season=season, historical_key="AAA", historical_name="Alpha", division="FBS"
        )
        for season in hos.HISTORICAL_SEASONS
    )
    bound = hos.bind_frame_identities(frame, canonical)
    assert all(i.canonical_binding == "EXACT_CANONICAL_KEY" for i in bound)


def test_an_identity_cannot_claim_a_binding_without_an_id():
    with pytest.raises(InputValidationError, match="claims a canonical id"):
        hos.HistoricalTeamIdentity(
            season=2021,
            historical_key="X",
            historical_name="X",
            division="FBS",
            canonical_schedule_id=None,
            canonical_binding="EXACT_CANONICAL_KEY",
        )


# ---------------------------------------------------------------------------
# FCS
# ---------------------------------------------------------------------------


def test_fcs_opening_points_are_refused_from_elo_1250():
    with pytest.raises(GovernanceBlock, match="1250"):
        hos.refuse_fcs_opening_points("SAC")
    with pytest.raises(GovernanceBlock, match="adapter is unresolved"):
        hos.refuse_fcs_opening_points("SAC", elo=1250.0)


def test_fcs_entities_are_preserved_with_a_reason_and_no_strength():
    states = _reconstruction()
    fcs = [s for s in states if s.identity.division == "FCS"]
    assert len(fcs) == 118 + 117 + 115 + 115
    for state in fcs:
        assert state.opening_unified_z is None
        assert state.status == hos.OpeningStatus.UNAVAILABLE
        assert [r for r, _ in state.missing_reasons] == ["OUTSIDE_POPULATION"]


def test_no_artifact_carries_a_point_value_for_any_team():
    unified = json.loads(
        (ARTIFACT_DIR / "historical_opening_state_unified_z_table.json").read_text(
            encoding="utf-8"
        )
    )
    assert unified["point_transform_status"] == "UNRATIFIED_FOR_HISTORICAL_REUSE"
    assert unified["rows_with_unified_z"] == 0
    for row in unified["rows"]:
        assert row["opening_unified_z"] is None
        assert "points" not in row
        assert "candidate_points_if_14xZ" not in row


# ---------------------------------------------------------------------------
# The reconstruction against the real evidence
# ---------------------------------------------------------------------------


def _reconstruction():
    identities = hos.load_membership_frame(
        REPO_ROOT / hos.OPENING_STATE_REFERENCE_DIR / hos.MEMBERSHIP_FRAME_FILENAME
    )
    bound = hos.bind_frame_identities(identities, load_canonical_team_index(CANONICAL_MD))
    populations = tuple(
        hos.resolve_population(season, hos.HISTORICAL_POPULATION_CANDIDATES, scope="FBS")
        for season in hos.HISTORICAL_SEASONS
    )
    return hos.build_reconstruction(bound, populations)


def test_the_frame_digest_is_checked_and_a_mutated_frame_is_refused(tmp_path):
    source = REPO_ROOT / hos.OPENING_STATE_REFERENCE_DIR / hos.MEMBERSHIP_FRAME_FILENAME
    mutant = tmp_path / hos.MEMBERSHIP_FRAME_FILENAME
    text = source.read_text(encoding="utf-8")
    mutant.write_bytes(text.replace("Clemson", "Clemsen", 1).encode("utf-8"))
    with pytest.raises(InputValidationError, match="digest mismatch"):
        hos.load_membership_frame(mutant)
    with pytest.raises(InputValidationError, match="not found"):
        hos.load_membership_frame(tmp_path / "absent.csv")


def test_every_team_season_is_unavailable_and_every_gap_carries_a_reason():
    states = _reconstruction()
    assert len(states) == 251 * len(hos.HISTORICAL_SEASONS)
    assert all(s.status == hos.OpeningStatus.UNAVAILABLE for s in states)
    assert all(s.opening_unified_z is None for s in states)
    assert all(s.missing_reasons for s in states)
    assert all(
        reason in hos.MISSING_REASONS for s in states for reason, _ in s.missing_reasons
    )


def test_an_fbs_team_season_reports_missing_source_and_an_unresolved_population():
    states = {(s.season, s.team_key): s for s in _reconstruction()}
    clemson = states[(2021, "Clemson")]
    reasons = dict(clemson.missing_reasons)
    assert "MISSING_SOURCE" in reasons
    assert "TRUESKILL" in reasons["MISSING_SOURCE"]
    assert "OTHER_EXPLICIT_REASON" in reasons
    assert "UNRESOLVED" in reasons["OTHER_EXPLICIT_REASON"]
    assert clemson.included_family_count == 0


def test_the_component_table_names_all_four_absent_families_per_team_season():
    table = json.loads(
        (ARTIFACT_DIR / "historical_opening_state_component_table.json").read_text(
            encoding="utf-8"
        )
    )
    assert table["required_families"] == list(hos.REQUIRED_FAMILY_IDS)
    for row in table["rows"]:
        assert set(row["standardized_components"]) == set(hos.REQUIRED_FAMILY_IDS)
        assert all(v is None for v in row["standardized_components"].values())


def test_the_standardization_manifest_is_empty_and_says_so_rather_than_inventing_one():
    manifest = json.loads(
        (
            ARTIFACT_DIR / "historical_opening_state_standardization_manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["records"] == []
    assert manifest["records_present"] == 0
    assert manifest["ddof_convention"] == 1
    assert [f["family_id"] for f in manifest["families"]] == list(hos.REQUIRED_FAMILY_IDS)


def test_a_season_mismatch_between_frame_and_population_is_refused():
    identity = hos.HistoricalTeamIdentity(
        season=2022, historical_key="X", historical_name="X", division="FBS"
    )
    population = hos.resolve_population(
        2021, hos.HISTORICAL_POPULATION_CANDIDATES, scope="FBS"
    )
    with pytest.raises(InputValidationError, match="no population record"):
        hos.build_reconstruction((identity,), (population,))


# ---------------------------------------------------------------------------
# Week 1 / Week 2 readiness
# ---------------------------------------------------------------------------


def test_week1_2_counts_only_pairs_where_both_sides_are_fully_reconstructed():
    identity = hos.HistoricalTeamIdentity(
        season=2021, historical_key="A", historical_name="A", division="FBS"
    )
    ready = hos.TeamSeasonOpeningState(
        season=2021,
        team_key="A",
        identity=identity,
        native_inputs=(),
        standardized_components=(),
        board_family_z=0.0,
        opening_unified_z=0.5,
        included_family_count=4,
        status=hos.OpeningStatus.FULLY_RECONSTRUCTED,
        missing_reasons=(),
        population_id="P",
        confidence="HIGH",
    )
    other = replace(
        ready, team_key="B", identity=replace(identity, historical_key="B")
    )
    absent = hos.TeamSeasonOpeningState(
        season=2021,
        team_key="C",
        identity=replace(identity, historical_key="C"),
        native_inputs=(),
        standardized_components=(),
        board_family_z=None,
        opening_unified_z=None,
        included_family_count=0,
        status=hos.OpeningStatus.UNAVAILABLE,
        missing_reasons=(("MISSING_SOURCE", "none"),),
        population_id="P",
        confidence="NONE",
    )
    games = [
        {"week": 1, "home_team": "A", "away_team": "B"},
        {"week": 2, "home_team": "A", "away_team": "C"},
        {"week": 2, "home_team": "C", "away_team": "C"},
        {"week": 3, "home_team": "A", "away_team": "B"},
    ]
    counts = hos.week1_2_opening_state_availability([ready, other, absent], games)
    assert counts["games_in_window"] == 3
    assert counts["both_states"] == 1
    assert counts["exactly_one_state"] == 1
    assert counts["neither_state"] == 1
    assert counts["teams_with_opening_state"] == 2


def test_week1_2_availability_is_zero_for_every_season_in_scope():
    coverage = json.loads(
        (ARTIFACT_DIR / "historical_opening_state_coverage_report.json").read_text(
            encoding="utf-8"
        )
    )
    seasons = {row["season"]: row for row in coverage["per_season"]}
    assert set(seasons) == set(hos.HISTORICAL_SEASONS)
    for season in hos.HISTORICAL_SEASONS:
        window = seasons[season]["week1_2"]
        assert window["both_states"] == 0
        assert window["teams_with_opening_state"] == 0
        assert window["schedule_mounted"] is False
        assert "regardless of schedule" in window["schedule_status"]


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------


def test_all_seven_artifacts_are_committed_and_hash_to_their_committed_bytes():
    for filename in hos.ARTIFACT_FILENAMES:
        path = ARTIFACT_DIR / filename
        assert path.exists(), filename
        assert b"\r\n" not in path.read_bytes(), f"{filename} carries CRLF"


def test_regeneration_is_byte_identical(tmp_path):
    """Repeat generation, not merely repeat values."""
    first = hos.generate_opening_state_artifacts(
        REPO_ROOT, tmp_path / "one", terminal_status="HISTORICAL_OPENING_STATE_BLOCKED"
    )
    second = hos.generate_opening_state_artifacts(
        REPO_ROOT, tmp_path / "two", terminal_status="HISTORICAL_OPENING_STATE_BLOCKED"
    )
    assert first["artifact_sha256"] == second["artifact_sha256"]
    for filename, digest in first["artifact_sha256"].items():
        committed = (ARTIFACT_DIR / filename).read_bytes()
        assert hashlib.sha256(committed).hexdigest() == digest, filename


def test_no_artifact_carries_a_timestamp_that_would_break_reproduction():
    for filename in hos.ARTIFACT_FILENAMES:
        text = (ARTIFACT_DIR / filename).read_text(encoding="utf-8")
        assert "generated_at" not in text, filename
        assert "recorded_at" not in text, filename


def test_the_status_record_promotes_nothing_and_reports_the_terminal_disposition():
    status = json.loads(
        (ARTIFACT_DIR / "historical_opening_state_status.json").read_text(
            encoding="utf-8"
        )
    )
    assert status["terminal_status"] == "HISTORICAL_OPENING_STATE_BLOCKED"
    assert status["component_families_available"] == []
    assert status["component_families_required"] == list(hos.REQUIRED_FAMILY_IDS)
    assert status["opening_unified_z_status"] == "NOT_PRODUCED_FOR_ANY_TEAM_SEASON"
    assert status["parameters_promoted"] == 0
    assert status["blockers_retired"] == 0
    assert status["simulations_run"] == 0
    assert status["writes_canonical_config"] is False
    assert status["fcs_opening_point_status"].startswith("REFUSED")
    assert set(status["population_status"]) == {"2021", "2022", "2023", "2024"}


def test_the_source_manifest_records_a_digest_and_a_disposition_for_every_candidate():
    manifest = json.loads(
        (ARTIFACT_DIR / "historical_opening_state_source_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["admissible_source_count"] == 0
    assert manifest["refused_source_count"] == len(
        hos.HISTORICAL_OPENING_STATE_SOURCE_REGISTER
    )
    ids = [s["source_id"] for s in manifest["sources"]]
    assert ids == sorted(ids), "source manifest must be deterministically ordered"
    for source in manifest["sources"]:
        assert len(source["sha256"]) == 64
        assert source["disposition"]
        assert source["evidence"]


def test_the_population_manifest_carries_both_2024_candidates_and_neither_is_chosen():
    manifest = json.loads(
        (ARTIFACT_DIR / "historical_opening_state_population_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    by_season = {row["season"]: row for row in manifest["seasons"]}
    assert by_season[2024]["status"] == "UNRESOLVED_CONFLICTING_CANDIDATES"
    assert by_season[2024]["resolved_count"] is None
    assert sorted(c["count"] for c in by_season[2024]["candidates"]) == [118, 133]
    for season in (2021, 2022, 2023):
        assert by_season[season]["status"] == "UNRESOLVED_SOURCE_NOT_MOUNTED"
        assert by_season[season]["resolved_count"] is None


def test_registered_bytes_verify_where_present_and_report_honestly_where_absent(tmp_path):
    in_repo = next(
        s
        for s in hos.HISTORICAL_OPENING_STATE_SOURCE_REGISTER
        if s.source_id == "V3_CANONICAL_TEAM_MASTER_2026"
    )
    result = hos.verify_registered_source_bytes(
        replace(in_repo, location=str(CANONICAL_MD))
    )
    assert result["verification"] == "BYTES_MATCH"
    assert result["observed_sha256"] == in_repo.sha256

    missing = hos.verify_registered_source_bytes(
        replace(in_repo, location=str(tmp_path / "nowhere.md"))
    )
    assert missing["verification"] == "BYTES_NOT_PRESENT"
    assert missing["observed_sha256"] is None

    decoy = tmp_path / "decoy.md"
    decoy.write_bytes(b"not the canonical master")
    differs = hos.verify_registered_source_bytes(replace(in_repo, location=str(decoy)))
    assert differs["verification"] == "BYTES_DIFFER"
