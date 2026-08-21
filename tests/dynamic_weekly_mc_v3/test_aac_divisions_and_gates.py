from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import aac_divisions as aac
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock, InputValidationError
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.ordering import (
    RESOLUTION_OPTIONS,
    TiedStandingsRace,
    cycle_path,
    diagnose_ordering,
    require_resolved_ordering,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.postseason import (
    QUARTERFINAL_MAPPING_OPTIONS,
    require_governed_quarterfinal_mapping,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.committee import require_v3_strength_tiebreak_policy

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"


def _rows():
    cfg = V3Config.from_json(CONFIG)
    return aac.extract_aac_divisions(cfg.inputs.canonical_master_md)


# --- AAC division membership ------------------------------------------------


def test_canonical_master_carries_ratified_8_8_split():
    rows = _rows()
    report = aac.validate_aac_divisions(rows)
    assert report["total"] == 16
    assert len(report["american"]) == 8
    assert len(report["athletic"]) == 8
    assert report["split_matches_r_ccg_07"] is True


def test_membership_covers_every_aac_team_exactly_once():
    rows = _rows()
    ids = [r.schedule_id for r in rows]
    assert len(set(ids)) == 16
    assert all(r.conference == aac.AAC_CONFERENCE_LABEL for r in rows)


def test_uneven_split_is_rejected():
    rows = _rows()
    tampered = list(rows[:-1]) + [
        aac.AACDivisionRow(
            schedule_id=rows[-1].schedule_id,
            team_name=rows[-1].team_name,
            conference=rows[-1].conference,
            division=aac.AMERICAN_DIVISION,
        )
    ]
    with pytest.raises(InputValidationError, match="8/8"):
        aac.validate_aac_divisions(tampered)


def test_duplicate_team_is_rejected():
    rows = _rows()
    dupe = list(rows) + [rows[0]]
    with pytest.raises(InputValidationError):
        aac.validate_aac_divisions(dupe)


def test_unmounted_ratified_csv_fails_closed():
    with pytest.raises(GovernanceBlock, match="not mounted"):
        aac.require_ratified_aac_divisions_csv(None)


def test_locally_generated_substitute_is_not_the_ratified_artifact(tmp_path):
    """A plausible, correct-looking CSV must still fail: only the digest proves identity."""
    rows = _rows()
    candidate = tmp_path / "aac_divisions_2026_RATIFIED.csv"
    candidate.write_text(aac.serialize_candidate_csv(rows), encoding="utf-8")
    with pytest.raises(GovernanceBlock, match="not the ratified artifact"):
        aac.require_ratified_aac_divisions_csv(candidate)


def test_candidate_csv_digest_does_not_equal_registered_digest():
    """Recorded explicitly: the ratified artifact cannot be reproduced from the master."""
    assert aac.candidate_csv_digest(_rows()) != aac.RATIFIED_AAC_CSV_SHA256


def test_config_still_blocks_on_aac_divisions():
    cfg = V3Config.from_json(CONFIG)
    assert cfg.inputs.aac_divisions_csv is None
    assert "inputs.aac_divisions_csv" in cfg.execution_blockers()


# --- A8/ECL ordering circularity -------------------------------------------


def test_ordering_cycle_is_structural_and_closes_on_itself():
    path = cycle_path()
    assert path[0] == path[-1] == "A8_ECL_CHAMPION"
    assert "FINAL_COMMITTEE_BOARD" in path
    assert "CONFERENCE_CHAMPION_FLAG" in path


def test_untied_races_do_not_bind_the_cycle():
    races = [TiedStandingsRace(conference="Atlantic-8", teams=("A", "B"), resolved_by_head_to_head=True)]
    diagnosis = diagnose_ordering(races)
    assert diagnosis.structurally_circular is True
    assert diagnosis.binds is False
    require_resolved_ordering(races)  # must not raise


def test_tied_race_surviving_tb1_and_tb2_fails_closed():
    races = [TiedStandingsRace(conference="ECL", teams=("A", "B"))]
    with pytest.raises(GovernanceBlock, match="circular"):
        require_resolved_ordering(races)


def test_ordering_ruling_must_be_a_known_option():
    races = [TiedStandingsRace(conference="Atlantic-8", teams=("A", "B", "C"))]
    with pytest.raises(GovernanceBlock, match="Unknown"):
        require_resolved_ordering(races, ordering_ruling="JUST_PICK_ONE")
    diagnosis = require_resolved_ordering(races, ordering_ruling=RESOLUTION_OPTIONS[0])
    assert diagnosis.binds is True


def test_ordering_diagnosis_reports_no_ruling_present():
    assert diagnose_ordering([]).as_dict()["resolution_ruling_present"] is False


# --- postseason and committee gates ----------------------------------------


def test_quarterfinal_mapping_is_not_inferred():
    with pytest.raises(GovernanceBlock, match="not explicit"):
        require_governed_quarterfinal_mapping(None)
    with pytest.raises(GovernanceBlock, match="Unknown"):
        require_governed_quarterfinal_mapping("SOMETHING_PLAUSIBLE")
    for option in QUARTERFINAL_MAPPING_OPTIONS:
        assert require_governed_quarterfinal_mapping(option) == option


def test_committee_strength_source_is_not_inferred():
    with pytest.raises(GovernanceBlock):
        require_v3_strength_tiebreak_policy(None)
    with pytest.raises(GovernanceBlock):
        require_v3_strength_tiebreak_policy("SOME_OTHER_STRENGTH")
    assert require_v3_strength_tiebreak_policy("PRESEASON_STRENGTH") == "PRESEASON_STRENGTH"
