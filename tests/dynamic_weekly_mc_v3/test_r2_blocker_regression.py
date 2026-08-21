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
STATUS = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R2.json"


@pytest.fixture(scope="module")
def live_blockers() -> list[str]:
    return list(DynamicWeeklyMCV3(V3Config.from_json(CONFIG)).preflight()["execution_blockers"])


def test_live_blocker_set_is_exactly_the_expected_set(live_blockers):
    assert set(live_blockers) == set(br.R2_EXPECTED_LIVE_BLOCKERS)
    assert len(live_blockers) == 11


def test_live_blockers_carry_no_duplicates(live_blockers):
    assert len(live_blockers) == len(set(live_blockers))


def test_every_retired_blocker_is_actually_gone(live_blockers):
    still_present = sorted(br.R2_RETIRED_BLOCKERS & set(live_blockers))
    assert still_present == []


def test_no_unrelated_blocker_disappeared(live_blockers):
    """Everything the audited state carried is either retired by a named ruling
    or still live. Nothing may vanish without an entry in the delta."""
    for blocker in br.R1_AUDITED_LIVE_BLOCKERS:
        assert blocker in live_blockers or blocker in br.R2_RETIRED_BLOCKERS, blocker


def test_every_retirement_is_claimed_by_a_ruling():
    claimed = rulings.retirable_blockers()
    assert set(claimed) == set(br.R2_RETIRED_BLOCKERS)
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


def test_the_successor_status_artifact_matches_the_live_state(live_blockers):
    status = json.loads(STATUS.read_text(encoding="utf-8"))
    assert set(status["live_blockers"]) == set(live_blockers)
    assert status["live_blocker_count"] == len(live_blockers)
    assert set(status["resolved_blockers"]) == set(br.R2_RETIRED_BLOCKERS)
    assert status["parent_build_manifest"]["execution_blocker_count"] == 18
    assert status["v2_1_static_control_sha256"] == (
        "39055662b819a3ff3e6e87ad53e28a15d0451a6b1e692e7770459e7a984c614a"
    )


def test_v3_remains_experimental_and_no_output_is_produced(live_blockers):
    cfg = V3Config.from_json(CONFIG)
    assert cfg.model_name.endswith("_EXPERIMENTAL")
    assert cfg.configuration_version.startswith("V3-PLACEHOLDER")
    assert live_blockers, "V3 execution must remain blocked"
    assert not (ROOT / "output").exists()


def test_every_ruling_is_recorded_with_its_provenance_class():
    for ruling in rulings.R2_RULINGS:
        assert ruling.convergence_id.startswith("R2-")
        assert ruling.decision
        assert ruling.provenance in ("FACT", "DERIVED")
        # No Chairman ruling IDs were supplied; none is invented.
        assert ruling.chairman_ruling_id is None
