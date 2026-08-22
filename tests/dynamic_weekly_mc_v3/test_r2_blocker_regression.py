"""Exact live blocker-set regression (audit finding B-3).

The previous audit found that nothing pinned the live blocker set — the only
assertion was ``len(blockers) > 0``, which would have passed had governance
convergence silently cleared something it had no authority to clear. These tests
assert set equality in both directions and account for every blocker that moved.
"""

import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report as br
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import rulings
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
MANIFEST = ROOT / "reference/dynamic_weekly_mc_v3/V3_BUILD_MANIFEST.json"
STATUS_R2 = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R2.json"
STATUS_R3 = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R3.json"


@pytest.fixture(scope="module")
def live_blockers() -> list[str]:
    return list(DynamicWeeklyMCV3(V3Config.from_json(CONFIG)).preflight()["execution_blockers"])


def test_live_blocker_set_is_exactly_the_post_board_mount_set(live_blockers):
    assert set(live_blockers) == set(
        br.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    )
    assert len(live_blockers) == 8


def test_live_blockers_carry_no_duplicates(live_blockers):
    assert len(live_blockers) == len(set(live_blockers))


def test_every_retired_blocker_is_actually_gone(live_blockers):
    retired = br.R2_RETIRED_BLOCKERS | br.R3_RETIRED_BLOCKERS
    assert sorted(retired & set(live_blockers)) == []


def test_no_unrelated_blocker_disappeared(live_blockers):
    """Everything the audited state carried is either retired by a named ruling
    or still live. Nothing may vanish without an entry in the delta."""
    retired = br.R2_RETIRED_BLOCKERS | br.R3_RETIRED_BLOCKERS
    for blocker in br.R1_AUDITED_LIVE_BLOCKERS:
        assert blocker in live_blockers or blocker in retired, blocker


def test_every_retirement_is_claimed_by_a_ruling():
    claimed = rulings.retirable_blockers()
    assert set(claimed) == set(br.R2_RETIRED_BLOCKERS | br.R3_RETIRED_BLOCKERS)
    for blocker, convergence_id in claimed.items():
        assert rulings.ruling(convergence_id).convergence_id == convergence_id


def test_calibration_blockers_are_untouched_by_governance(live_blockers):
    for blocker in br.R1_AUDITED_LIVE_BLOCKERS:
        if blocker.startswith("calibration.") or blocker.endswith("GAME_SD_CALIBRATION_OPEN"):
            assert blocker in live_blockers


def test_the_audited_r1_state_is_preserved_verbatim():
    assert len(br.R1_BASELINE_BLOCKERS) == 18
    assert len(br.R1_AUDITED_LIVE_BLOCKERS) == 17
    assert br.R1_BASELINE_BLOCKERS - br.R1_AUDITED_LIVE_BLOCKERS == {
        "provenance.SCHEDULE_GAMES_HASH_REPRODUCTION_MISMATCH"
    }


def test_the_frozen_build_manifest_is_not_rewritten():
    """R1's manifest is the record of the tested build and stays as it was."""
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["execution_blocker_count"] == 18
    assert manifest["test_count"] == 74
    assert set(manifest["execution_blockers"]) == set(br.R1_BASELINE_BLOCKERS)


def test_the_r3_successor_status_artifact_is_preserved_as_historical_record():
    status = json.loads(STATUS_R3.read_text(encoding="utf-8"))
    assert set(status["live_blockers"]) == set(br.R3_EXPECTED_LIVE_BLOCKERS)
    assert status["live_blocker_count"] == len(br.R3_EXPECTED_LIVE_BLOCKERS)
    assert set(status["resolved_blockers"]) == set(br.R3_RETIRED_BLOCKERS)
    assert set(status["blocker_set_before"]) == set(br.R2_EXPECTED_LIVE_BLOCKERS)
    assert status["parent_build_manifest"]["execution_blocker_count"] == 18
    assert status["parent_build_manifest"]["edited"] is False
    assert status["v2_1_static_control_sha256"] == (
        "39055662b819a3ff3e6e87ad53e28a15d0451a6b1e692e7770459e7a984c614a"
    )


def test_the_r2_status_artifact_is_preserved_as_the_r2_record():
    """R2's status artifact is history and stays exactly as it was."""
    status = json.loads(STATUS_R2.read_text(encoding="utf-8"))
    assert status["live_blocker_count"] == 11
    assert set(status["live_blockers"]) == set(br.R2_EXPECTED_LIVE_BLOCKERS)


def test_the_successor_artifact_is_not_self_referential():
    """A committed artifact cannot carry the SHA of the commit containing it."""
    status = json.loads(STATUS_R3.read_text(encoding="utf-8"))
    assert status["head_sha"] is None
    assert status["base_sha"] == "3b46e561b8d939e10ba5d6ff2f69923d963a148e"
    assert status["converged_from_head_sha"] == (
        "bbc353e823f8c5e49ee241d412a265481daf9cb0"
    )


def test_v3_remains_experimental_and_no_output_is_produced(live_blockers):
    cfg = V3Config.from_json(CONFIG)
    assert cfg.model_name.endswith("_EXPERIMENTAL")
    assert cfg.configuration_version.startswith("V3-PLACEHOLDER")
    assert live_blockers, "V3 execution must remain blocked"
    assert not (ROOT / "output").exists()


def test_every_ruling_is_recorded_with_its_provenance_class():
    for ruling in rulings.ALL_RULINGS:
        assert ruling.convergence_id.startswith(("R2-", "R3-", "R4-", "R6-"))
        assert ruling.decision
        assert ruling.provenance in ("FACT", "DERIVED")


def test_a_chairman_ruling_id_is_recorded_only_where_one_was_issued():
    """No ID is invented, and the one ID that was issued is not thrown away.

    R2, R3 and R4 arrived without Chairman ruling IDs, so theirs stay null. R6
    arrived with one, so it is recorded verbatim. The approval token is kept in
    its own field: it authorises an instruction and is not a ruling ID.
    """
    supplied = {
        "R6-CAL-TEMPORAL-ORDER": "V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1",
    }
    for ruling in rulings.ALL_RULINGS:
        assert ruling.chairman_ruling_id == supplied.get(ruling.convergence_id)
        if ruling.approval_token is not None:
            assert ruling.approval_token != ruling.chairman_ruling_id
