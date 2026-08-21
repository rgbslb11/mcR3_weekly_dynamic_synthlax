"""B1 — Board-of-Record artifact custody.

The blocker ``inputs.board_of_record_i_k`` was never a policy question. R2 named
one artifact; R3 and R4 recorded the SHA-256 that artifact must have, and both
recorded that no file with that digest was reachable. The approved binary has now
been delivered and mounted, so the gate closes on custody evidence alone.

What these tests pin is that the gate is a *digest* gate. The previous
implementation cleared on filename and on mere existence, which meant a 49-byte
pytest fixture carrying the right name satisfied production authority. Every
rejection case below would have passed that older gate.
"""

import hashlib
import json
from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import blocker_report as br
from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import board_of_record as bor
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/dynamic_weekly_mc_v3/v3_experimental.json"
GOVERNED_DIR = ROOT / "config/dynamic_weekly_mc_v3/governed"
MOUNT = GOVERNED_DIR / bor.BOARD_OF_RECORD_FILENAME
PROVENANCE = GOVERNED_DIR / "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.provenance.json"
INPUTS = ROOT / "reference/dynamic_weekly_mc_v3/inputs"
STATUS_R3 = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R3.json"
STATUS_R4 = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_R4.json"

REQUIRED_SHA256 = "6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a"

#: The 49-byte harness stand-in R4 recorded finding under the board's own name.
FIXTURE_BYTES = b"harness stand-in for the Board of Record artifact"
FIXTURE_SHA256 = "f20b2fa5cd69598935c5d3e4b8323ffdf6ba3eebc8349991182719fbd378ebbc"


@pytest.fixture(scope="module")
def live_blockers() -> list[str]:
    return sorted(
        DynamicWeeklyMCV3(V3Config.from_json(CONFIG)).preflight()["execution_blockers"]
    )


# =============================================================================
# The digest was required before the artifact arrived
# =============================================================================


def test_the_required_digest_predates_the_delivery():
    """The expectation was not written to match whatever showed up.

    R3 and R4 both recorded ``required_sha256`` while recording that no such file
    was reachable. The constant the loader enforces is that same value.
    """
    r3 = json.loads(STATUS_R3.read_text(encoding="utf-8"))["board_of_record"]
    r4 = json.loads(STATUS_R4.read_text(encoding="utf-8"))["board_of_record"]
    assert r3["required_sha256"] == REQUIRED_SHA256
    assert r4["required_sha256"] == REQUIRED_SHA256
    assert bor.BOARD_OF_RECORD_SHA256 == REQUIRED_SHA256
    # Both recorded the artifact as absent at the time they were written.
    assert r3["mounted"] is False
    assert r4["mounted"] is False


def test_the_prior_records_are_not_rewritten():
    """R3 and R4 are history. The mount does not edit them."""
    for status in (STATUS_R3, STATUS_R4):
        record = json.loads(status.read_text(encoding="utf-8"))["board_of_record"]
        assert record["mounted"] is False
        assert record["mount_result"] == "BOARD_IK_ARTIFACT_NOT_ACCESSIBLE_TO_AGENT"
        assert record["historical_board_substituted"] is False
    # R4's nine-blocker record stands unedited too.
    assert json.loads(STATUS_R4.read_text(encoding="utf-8"))["live_blocker_count"] == 9


# =============================================================================
# The mounted artifact is the approved one
# =============================================================================


def test_the_mounted_artifact_hashes_to_the_required_digest():
    assert MOUNT.exists()
    digest = hashlib.sha256(MOUNT.read_bytes()).hexdigest()
    assert digest == REQUIRED_SHA256
    assert MOUNT.stat().st_size == bor.BOARD_OF_RECORD_BYTES == 57179


def test_the_mount_carries_the_controlled_identity():
    assert MOUNT.name == bor.BOARD_OF_RECORD_FILENAME
    assert "(3)" not in MOUNT.name


def test_require_board_of_record_accepts_the_mount():
    board = bor.require_board_of_record(MOUNT)
    assert board.identity == bor.BOARD_OF_RECORD_FILENAME
    assert board.sha256 == REQUIRED_SHA256
    assert board.source_filename == bor.BOARD_OF_RECORD_SOURCE_FILENAME
    # Custody only: rows are not read into any decision here.
    assert board.rows == 0


def test_status_reports_a_verified_mount_and_no_blocker():
    status = bor.board_of_record_status(MOUNT)
    assert status["mounted"] is True
    assert status["digest_verified"] is True
    assert status["digest_mismatch"] is False
    assert status["authority"] == "SHA256_DIGEST_EQUALITY"
    assert status["sha256"] == status["expected_sha256"] == REQUIRED_SHA256
    assert status["blocker"] is None
    assert status["historical_board_substitutable"] is False


# =============================================================================
# Rejections — every one of these passed the old filename/existence gate
# =============================================================================


def test_the_49_byte_pytest_fixture_is_refused_under_the_correct_name(tmp_path):
    """The exact stand-in R4 found, named exactly right. Digest refuses it."""
    impostor = tmp_path / bor.BOARD_OF_RECORD_FILENAME
    impostor.write_bytes(FIXTURE_BYTES)
    assert hashlib.sha256(FIXTURE_BYTES).hexdigest() == FIXTURE_SHA256
    assert impostor.name == bor.BOARD_OF_RECORD_FILENAME  # the old gate's only check
    assert impostor.exists()                              # the config gate's only check
    assert bor.is_governed_board_of_record(impostor) is False
    with pytest.raises(GovernanceBlock, match="not the approved Board of Record"):
        bor.require_board_of_record(impostor)


def test_a_regenerated_workbook_is_refused(tmp_path):
    """Re-saving the real board reproduces its content but not its bytes."""
    from openpyxl import load_workbook

    regenerated = tmp_path / bor.BOARD_OF_RECORD_FILENAME
    load_workbook(MOUNT).save(regenerated)
    assert regenerated.exists()
    assert hashlib.sha256(regenerated.read_bytes()).hexdigest() != REQUIRED_SHA256
    assert bor.is_governed_board_of_record(regenerated) is False
    with pytest.raises(GovernanceBlock):
        bor.require_board_of_record(regenerated)


def test_a_single_flipped_byte_is_refused(tmp_path):
    mutant = tmp_path / bor.BOARD_OF_RECORD_FILENAME
    data = bytearray(MOUNT.read_bytes())
    data[-1] ^= 0x01
    mutant.write_bytes(bytes(data))
    assert len(data) == bor.BOARD_OF_RECORD_BYTES  # same size, wrong bytes
    assert bor.is_governed_board_of_record(mutant) is False
    with pytest.raises(GovernanceBlock):
        bor.require_board_of_record(mutant)


def test_board_i_h_is_refused_even_though_it_is_a_real_governed_workbook(tmp_path):
    """Model Parameters v2.5 carries Board I-H as sheet 08_BOARD_IH_TOP25.

    It is a genuine, governed, mounted artifact — and still not the Board of
    Record. Offered under the board's name, digest refuses it.
    """
    source = INPUTS / "Model_Parameters_v2_5_APPROVED.xlsx"
    assert source.exists()
    impostor = tmp_path / bor.BOARD_OF_RECORD_FILENAME
    impostor.write_bytes(source.read_bytes())
    assert bor.is_governed_board_of_record(impostor) is False
    with pytest.raises(GovernanceBlock):
        bor.require_board_of_record(impostor)


def test_the_historical_board_may_never_be_named_as_the_board_of_record():
    with pytest.raises(GovernanceBlock):
        bor.reject_historical_board_substitution(bor.HISTORICAL_BOARD_LABEL)
    with pytest.raises(GovernanceBlock):
        bor.reject_historical_board_substitution("Board I-H v2 TOP25")
    # The historical board stays exactly where it is.
    assert bor.HISTORICAL_BOARD_SHEET == "08_BOARD_IH_TOP25"


def test_an_unconfigured_or_missing_board_still_fails_closed(tmp_path):
    with pytest.raises(GovernanceBlock):
        bor.require_board_of_record(None)
    with pytest.raises(GovernanceBlock):
        bor.require_board_of_record(tmp_path / "nothing-here.xlsx")
    assert bor.board_of_record_status(None)["mounted"] is False
    assert bor.board_of_record_status(None)["blocker"] == bor.BOARD_OF_RECORD_BLOCKER


def test_correct_bytes_under_a_foreign_name_are_still_refused(tmp_path):
    """Digest is necessary, and the controlled identity is still required."""
    renamed = tmp_path / "board.xlsx"
    renamed.write_bytes(MOUNT.read_bytes())
    with pytest.raises(GovernanceBlock, match="controlled identity"):
        bor.require_board_of_record(renamed)


def test_the_delivery_filename_is_also_accepted(tmp_path):
    """The '(3)' delivery name denotes the same binary, so it is recognised."""
    delivered = tmp_path / bor.BOARD_OF_RECORD_SOURCE_FILENAME
    delivered.write_bytes(MOUNT.read_bytes())
    board = bor.require_board_of_record(delivered)
    assert board.sha256 == REQUIRED_SHA256
    assert bor.BOARD_OF_RECORD_ACCEPTED_FILENAMES == {
        bor.BOARD_OF_RECORD_FILENAME,
        bor.BOARD_OF_RECORD_SOURCE_FILENAME,
    }


# =============================================================================
# Identity reconciliation, recorded rather than resolved by fiat
# =============================================================================


def test_the_controlled_identity_and_the_delivery_name_are_reconciled_by_digest():
    assert bor.BOARD_OF_RECORD_FILENAME == (
        "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx"
    )
    assert bor.BOARD_OF_RECORD_SOURCE_FILENAME == (
        "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE(3).xlsx"
    )
    # R3 and R4 recorded the delivery spelling; the R2 ruling names the
    # controlled one. Neither record was edited to agree with the other.
    for status in (STATUS_R3, STATUS_R4):
        record = json.loads(status.read_text(encoding="utf-8"))["board_of_record"]
        assert record["required_filename"] == bor.BOARD_OF_RECORD_SOURCE_FILENAME
    prov = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert prov["filename_reconciliation"]["reconciled_by"] == "SHA256_DIGEST_EQUALITY"
    assert prov["filename_reconciliation"]["history_rewritten"] is False


def test_the_provenance_record_preserves_source_hash_and_recorded_at():
    prov = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert prov["sha256"] == REQUIRED_SHA256
    assert prov["bytes"] == 57179
    assert prov["recorded_at"] == "2026-08-21T00:00:00+00:00"
    assert prov["provenance_class"] == "FACT"
    assert prov["custody_status"] == "MOUNTED_IN_REPOSITORY"
    assert prov["identity_authority"] == "SHA256_DIGEST_EQUALITY"
    assert prov["issued_under_ruling"] == "R2-BOARD-OF-RECORD"
    source = prov["source"]
    assert source["source_filename"] == bor.BOARD_OF_RECORD_SOURCE_FILENAME
    assert source["source_sha256"] == REQUIRED_SHA256
    assert source["transfer"] == "BYTE_IDENTICAL_COPY"
    assert source["bytes_altered_on_mount"] is False


def test_the_provenance_digest_matches_the_file_it_describes():
    prov = json.loads(PROVENANCE.read_text(encoding="utf-8"))
    assert prov["sha256"] == hashlib.sha256(MOUNT.read_bytes()).hexdigest()
    assert prov["bytes"] == MOUNT.stat().st_size


def test_the_mount_lives_in_the_governed_location_not_the_reference_tree():
    """The governed-artifact pattern is config/.../governed/ + a provenance
    sibling, exactly as the R2 AAC successor established."""
    assert MOUNT.parent == GOVERNED_DIR
    assert PROVENANCE.exists()
    assert (GOVERNED_DIR / "aac_divisions_2026_R2_SUCCESSOR.provenance.json").exists()
    # The frozen reference input tree is untouched.
    names = {p.name for p in INPUTS.iterdir()}
    assert len(names) == 8
    assert not any("Board_I-K" in n for n in names)


# =============================================================================
# The blocker transition: nine to eight
# =============================================================================


def test_the_board_blocker_is_retired(live_blockers):
    assert "inputs.board_of_record_i_k" not in live_blockers
    assert br.B1_RETIRED_BLOCKERS == frozenset({"inputs.board_of_record_i_k"})


def test_the_transition_is_exactly_nine_to_eight(live_blockers):
    delta = br.board_mount_delta()
    assert delta["count_before"] == 9
    assert delta["count_after"] == 8
    assert delta["retired"] == ["inputs.board_of_record_i_k"]
    assert delta["opened"] == []
    assert set(live_blockers) == set(delta["set_after"])
    assert len(live_blockers) == 8


def test_no_unrelated_blocker_vanished(live_blockers):
    """The audit that matters. Everything R3 left live is still live, bar one."""
    delta = br.board_mount_delta()
    assert delta["unrelated_vanished"] == []
    assert delta["vanished"] == ["inputs.board_of_record_i_k"]
    for blocker in br.R3_EXPECTED_LIVE_BLOCKERS - br.B1_RETIRED_BLOCKERS:
        assert blocker in live_blockers, blocker


def test_the_outcome_matches_what_r3_projected():
    """R3 wrote down which eight would remain if the board ever mounted."""
    assert br.B1_EXPECTED_LIVE_BLOCKERS == br.R3_EXPECTED_LIVE_BLOCKERS_IF_BOARD_MOUNTED
    assert br.board_mount_delta()["matches_r3_projection"] is True


def test_the_retirement_is_custody_not_governance():
    assert br.B1_RETIREMENT_REASONS == {
        "inputs.board_of_record_i_k": "EXACT_ARTIFACT_CUSTODY_SHA256_VERIFIED"
    }
    assert br.B1_OPENED_BLOCKERS == frozenset()
    assert br.R3_REMAINING_CLASSIFICATION["inputs.board_of_record_i_k"] == (
        "ARTIFACT_CUSTODY"
    )


def test_the_config_gate_is_a_digest_gate_not_an_existence_gate(tmp_path):
    """Swap the mount for a same-named impostor: the blocker comes straight back."""
    cfg = V3Config.from_json(CONFIG)
    assert "inputs.board_of_record_i_k" not in cfg.execution_blockers()

    impostor = tmp_path / bor.BOARD_OF_RECORD_FILENAME
    impostor.write_bytes(FIXTURE_BYTES)
    import dataclasses

    swapped = dataclasses.replace(
        cfg, inputs=dataclasses.replace(cfg.inputs, board_of_record_xlsx=impostor)
    )
    assert impostor.exists()
    assert "inputs.board_of_record_i_k" in swapped.execution_blockers()


# =============================================================================
# Lane boundaries
# =============================================================================


def test_nothing_outside_board_custody_moved(live_blockers):
    """Calibration stays null and unpromoted; no run, no probabilities."""
    cfg = V3Config.from_json(CONFIG)
    assert cfg.calibration.blockers() == [
        "weekly_performance_residual_coefficient",
        "weekly_movement_cap_points",
        "recent_form_weights",
        "blowout_treatment",
        "game_sd_points",
        "sample_size_regularization",
    ]
    assert cfg.model_name.endswith("_EXPERIMENTAL")
    assert cfg.configuration_version.startswith("V3-PLACEHOLDER")
    assert cfg.paths == 10_000  # architecture unchanged; no run performed
    assert not (ROOT / "output").exists()
    # Execution is still blocked — a mounted board is not a runnable model.
    with pytest.raises(GovernanceBlock):
        cfg.require_executable()


# =============================================================================
# The B1 status record
# =============================================================================


STATUS_B1 = ROOT / "reference/dynamic_weekly_mc_v3/V3_GOVERNANCE_STATUS_B1.json"


def test_the_b1_status_record_matches_the_live_state(live_blockers):
    status = json.loads(STATUS_B1.read_text(encoding="utf-8"))
    assert set(status["live_blockers"]) == set(live_blockers)
    assert status["live_blocker_count"] == len(live_blockers) == 8
    assert status["blocker_count_before"] == 9
    assert set(status["blocker_set_before"]) == set(br.R3_EXPECTED_LIVE_BLOCKERS)
    assert set(status["resolved_blockers"]) == set(br.B1_RETIRED_BLOCKERS)
    assert status["opened_blockers"] == []
    assert status["blocker_accounting"]["unrelated_vanished"] == []
    assert status["blocker_accounting"]["matches_r3_projection"] is True


def test_the_b1_status_record_is_not_self_referential():
    status = json.loads(STATUS_B1.read_text(encoding="utf-8"))
    assert status["head_sha"] is None
    assert status["base_sha"] == "eb5e3e7f546217809a94692bf0e502882b7d51c0"
    assert status["chairman_ruling_ids_supplied"] == []


def test_the_b1_status_record_claims_custody_authority_only():
    status = json.loads(STATUS_B1.read_text(encoding="utf-8"))
    assert status["authority"] == "ARTIFACT_CUSTODY_ONLY"
    assert status["provenance_class"] == "FACT"
    assert status["simulation_run"] is False
    assert status["output_probabilities_generated"] is False
    assert status["canonical_config"]["calibration_values_populated"] is False
    board = status["board_of_record"]
    assert board["digest_match"] is True
    assert board["mounted"] is True
    assert board["mount_result"] == "BOARD_IK_ARTIFACT_MOUNTED_AND_SHA256_VERIFIED"
    assert board["historical_board_substituted"] is False
    assert board["observed_sha256"] == board["required_sha256"] == REQUIRED_SHA256
