"""The opening source-recovery artifacts are deterministic and self-consistent.

These tests do not re-derive the lane's findings — the evidence for those lives
in workbooks outside the repository and is cited in
``docs/v3_opening_source_recovery_r1.md``. What they hold is the part a later
reader can be misled by: that the committed bytes are exactly what the emitter
produces, that no artifact silently claims a recovered source, and that the
conclusion recorded in the status artifact still follows from the matrix rows
underneath it.

A finding that is edited in one artifact and not the others is the specific
failure these guard against.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = (
    REPO_ROOT / "reference" / "dynamic_weekly_mc_v3" / "opening_source_recovery_r1"
)
EMITTER = REPO_ROOT / "scripts" / "build_opening_source_recovery_r1.py"

SEASONS = (2021, 2022, 2023, 2024)


def _emitter():
    spec = importlib.util.spec_from_file_location("_opening_source_recovery_r1", EMITTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load(name: str) -> dict:
    return json.loads((ARTIFACT_DIR / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def emitter():
    return _emitter()


def test_committed_artifacts_are_byte_identical_to_the_emitter(emitter) -> None:
    """Every committed file is exactly what ``build`` writes today.

    Hand-editing an artifact is the cheapest way to make this lane say something
    it did not find, so the emitter is the single source of the bytes.
    """
    for name, payload in emitter.ARTIFACTS.items():
        expected = emitter.render(payload)
        actual = (ARTIFACT_DIR / name).read_text(encoding="utf-8")
        assert actual == expected, f"{name} differs from its emitter output"


def test_artifact_bytes_carry_lf_endings_and_no_embedded_timestamp() -> None:
    """LF is repository policy for ``*.json`` and byte identity depends on it.

    A ``generated_at`` field would make the second run differ from the first,
    which is why provenance travels in git rather than inside the hashed bytes.
    """
    for path in sorted(ARTIFACT_DIR.iterdir()):
        raw = path.read_bytes()
        assert b"\r\n" not in raw, f"{path.name} carries CRLF"
        assert b"generated_at" not in raw, f"{path.name} embeds a timestamp"


def test_rebuilding_twice_produces_the_same_digests(emitter, tmp_path) -> None:
    first = emitter.build(tmp_path / "one")
    second = emitter.build(tmp_path / "two")
    assert first == second
    assert set(first) == set(emitter.ARTIFACTS)


def test_no_component_season_claims_an_exact_recovered_source() -> None:
    """The headline negative result, asserted where it cannot drift unnoticed."""
    matrix = _load("V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json")
    assert matrix["exact_source_recovered_count"] == 0
    recovered = [
        row for row in matrix["rows"] if row["classification"] == "EXACT_SOURCE_RECOVERED"
    ]
    assert recovered == []
    assert all(row["team_count"] in (0, None) or row["family"] == "SHARED_PREREQUISITE"
               for row in matrix["rows"])


def test_every_row_carries_a_classification_from_the_declared_vocabulary() -> None:
    matrix = _load("V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json")
    vocabulary = set(matrix["classification_vocabulary"])
    seasons_seen = {row["season"] for row in matrix["rows"]}
    assert seasons_seen == set(SEASONS)
    for row in matrix["rows"]:
        assert row["classification"] in vocabulary
        assert row["missing_reason"], f"{row['component']} {row['season']} has no reason"
        assert row["leakage_status"]


def test_no_row_is_admitted_on_same_season_or_postseason_information() -> None:
    """The one rule the lane must not break, checked against the emitted rows.

    A component may be reconstructable only from information that predates the
    target season. Every refused candidate is registered with its disposition
    rather than dropped, so that a later lane cannot rediscover it and assume it
    was never considered.
    """
    matrix = _load("V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json")
    for row in matrix["rows"]:
        assert "SAME_SEASON" not in row["leakage_status"]
        assert "POSTSEASON" not in row["leakage_status"]
    dispositions = {c["disposition"] for c in matrix["refused_candidates"]}
    assert "POSTSEASON_ONLY" in dispositions
    assert "SYNTHETIC_ONLY" in dispositions


def test_the_board_family_is_unreconstructable_and_litkenhous_depends_on_it() -> None:
    """The finding that decides the lane, held in both artifacts at once.

    Board I-H and Board J-B never existed before 2026 and their component
    scoring manual is not written down anywhere. Litkenhous is described in the
    ensemble parameters as an independent family, and its Layer 2 offseason
    composite is the Board component vector; so the Board blocker reaches half
    the Unified Master Z weight, not a quarter.
    """
    matrix = _load("V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json")
    inventory = _load("V3_OPENING_FAMILY_INVENTORY_R1.json")

    board_rows = [row for row in matrix["rows"] if row["family"] == "BOARD_FAMILY"]
    assert len(board_rows) == 2 * len(SEASONS)
    for row in board_rows:
        assert row["reconstructable"] is False
        assert row["reconstruction_gate"] == "NONE_EXISTS"

    litkenhous_input = [
        row for row in matrix["rows"] if row["component"] == "LITKENHOUS_ADJUSTED_POWER"
    ]
    assert len(litkenhous_input) == len(SEASONS)
    for row in litkenhous_input:
        assert row["reconstructable"] is False
        assert row["reconstruction_gate"] == "BOARD_COMPONENT_VECTOR"

    dependency = inventory["the_board_dependency"]
    assert dependency["board_dependent_weight"] == 0.5
    assert sorted(dependency["board_dependent_families"]) == [
        "BOARD_FAMILY",
        "LITKENHOUS",
    ]
    assert sorted(dependency["board_free_families"]) == ["PURE_BAXTER", "TRUESKILL"]


def test_the_two_board_members_are_recorded_as_one_component_vector() -> None:
    """Weighting the same vector twice is not two independent measurements."""
    inventory = _load("V3_OPENING_FAMILY_INVENTORY_R1.json")
    board = next(
        family
        for family in inventory["families"]
        if family["family_id"] == "BOARD_FAMILY"
    )
    independence = board["member_independence"]
    assert independence["component_vectors_identical"] is True
    assert independence["distinct_component_rows"] == 0
    assert independence["pearson_r_between_member_power_series"] > 0.99


def test_family_weights_sum_to_one_and_the_board_splits_evenly() -> None:
    inventory = _load("V3_OPENING_FAMILY_INVENTORY_R1.json")
    assert sum(family["weight"] for family in inventory["families"]) == 1.0
    board = next(
        family
        for family in inventory["families"]
        if family["family_id"] == "BOARD_FAMILY"
    )
    assert [member["weight"] for member in board["members"]] == [0.125, 0.125]
    assert sum(member["weight"] for member in board["members"]) == board["weight"]


def test_no_missing_family_renormalization_rule_is_invented() -> None:
    """Two of four families is not two-thirds of a Unified Z. It is nothing."""
    coverage = _load("V3_OPENING_COVERAGE_MATRIX_R1.json")
    inventory = _load("V3_OPENING_FAMILY_INVENTORY_R1.json")
    rule = coverage["missing_family_renormalization"]
    assert rule["existing_v3_rule"] is None
    assert rule["invented_here"] is False
    assert coverage["all_four_families_required"] is True
    assert inventory["family_count_rule"]["renormalization_rule_exists"] is False
    assert inventory["family_count_rule"]["value"] == 4
    for season in SEASONS:
        assert coverage["matrix"][str(season)]["unified_z_constructible"] is False


def test_the_population_reconciliation_resolves_without_requesting_a_ruling() -> None:
    """The 2024 disagreement is two objects, not two accounts of one object.

    133 counts real membership over a roster frozen before Kennesaw State was an
    FBS program; 118 is the size of a synthetic universe carrying eight Ivy and
    Patriot League schools as FBS. Evidence separates them, so no ruling is
    requested.
    """
    population = _load("V3_OPENING_POPULATION_RECONCILIATION_R1.json")
    assert population["ruling_required"] is False
    assert population["ruling_requested"] is False
    assert population["real_fbs_counts"] == {
        "2021": 130,
        "2022": 131,
        "2023": 133,
        "2024": 134,
    }
    programs = {entry["program"] for entry in population["disputed_programs"]}
    assert "Kennesaw State" in programs
    assert "North Dakota State" in programs
    kennesaw = next(
        entry
        for entry in population["disputed_programs"]
        if entry["program"] == "Kennesaw State"
    )
    assert kennesaw["resolution"] == "ADD_TO_2024_POPULATION_ON_EVIDENCE"
    assert population["brief_figure_correction"]["figure_in_evidence"] == 118


def test_the_coverage_matrix_population_matches_the_reconciled_counts() -> None:
    """One reconciled population, quoted in both places rather than twice-derived."""
    coverage = _load("V3_OPENING_COVERAGE_MATRIX_R1.json")
    population = _load("V3_OPENING_POPULATION_RECONCILIATION_R1.json")
    for season in SEASONS:
        assert (
            coverage["matrix"][str(season)]["population_required"]
            == population["real_fbs_counts"][str(season)]
        )


def test_the_terminal_status_follows_from_the_rows_beneath_it() -> None:
    """The conclusion is re-derived from the matrix, not merely asserted."""
    status = _load("V3_OPENING_SOURCE_RECOVERY_STATUS_R1.json")
    matrix = _load("V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json")
    coverage = _load("V3_OPENING_COVERAGE_MATRIX_R1.json")

    reconstructable_families = {
        family
        for family, entry in (
            (family_id, coverage["matrix"]["2021"][family_id])
            for family_id in coverage["families"]
        )
        if entry["status"] == "ALGORITHMICALLY_RECONSTRUCTABLE"
    }
    assert len(reconstructable_families) == status["families_algorithmically_reconstructable"]
    assert status["families_required_for_unified_z"] == len(coverage["families"])
    assert reconstructable_families < set(coverage["families"])

    assert status["terminal_status"] == "OPENING_SOURCE_RECOVERY_EXACT_NOT_POSSIBLE"
    assert status["decisions"]["A_exact_reconstruction_possible"]["answer"] == "NO"
    assert status["decisions"]["D_impossible_because_a_family_did_not_exist"]["answer"] == "YES"
    assert matrix["exact_source_recovered_count"] == 0


def test_the_lane_emits_no_football_point_and_fits_no_parameter() -> None:
    status = _load("V3_OPENING_SOURCE_RECOVERY_STATUS_R1.json")
    matrix = _load("V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json")
    assert status["v3_point_values_emitted"] == 0
    assert matrix["v3_point_values_emitted"] == 0
    assert status["parameters_fitted"] == 0
    assert status["monte_carlo_runs"] == 0
    assert status["blockers_retired"] == 0
    assert status["blockers_opened"] == 0


def test_board_substitutes_are_reported_but_never_adopted() -> None:
    """Reported for adjudication. Adopting one is a Chairman decision, not this lane's."""
    matrix = _load("V3_OPENING_SOURCE_RECOVERY_MATRIX_R1.json")
    substitutes = matrix["board_substitute_candidates"]
    assert substitutes["candidates"]
    assert "None is adopted" in substitutes["adjudication_note"]
    for candidate in substitutes["candidates"]:
        assert candidate["seasons_available"]
        assert candidate["board_component_addressed"]
    board_rows = [row for row in matrix["rows"] if row["family"] == "BOARD_FAMILY"]
    assert all(row["source"] == "NONE_LOCATED" for row in board_rows)
