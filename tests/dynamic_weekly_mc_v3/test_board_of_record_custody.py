from __future__ import annotations

from pathlib import Path

import pytest

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import board_of_record
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.errors import GovernanceBlock


EXPECTED_FILENAME = "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE.xlsx"
EXPECTED_SHA256 = (
    "6b4cec1e48b34cb9eca5c224f5ef8750cca5acc40ecfd0bc42ed62976cbd4c9a"
)


def test_board_identity_constants_are_exact():
    assert board_of_record.BOARD_OF_RECORD_FILENAME == EXPECTED_FILENAME
    assert board_of_record.BOARD_OF_RECORD_SHA256 == EXPECTED_SHA256


def test_missing_board_remains_blocked():
    status = board_of_record.board_of_record_status(None)

    assert status["mounted"] is False
    assert status["exists"] is False
    assert status["blocker"] == "inputs.board_of_record_i_k"
    assert status["required_sha256"] == EXPECTED_SHA256

    with pytest.raises(GovernanceBlock):
        board_of_record.require_board_of_record(None)


def test_correct_filename_with_wrong_bytes_is_refused(tmp_path: Path):
    candidate = tmp_path / EXPECTED_FILENAME
    candidate.write_bytes(b"not the governed Board I-K workbook")

    status = board_of_record.board_of_record_status(candidate)

    assert status["exists"] is True
    assert status["canonical_filename_matches"] is True
    assert status["approved_digest_matches"] is False
    assert status["mounted"] is False
    assert status["blocker"] == "inputs.board_of_record_i_k"

    with pytest.raises(GovernanceBlock, match="sha256"):
        board_of_record.require_board_of_record(candidate)


def test_wrong_filename_is_refused(tmp_path: Path):
    candidate = (
        tmp_path
        / "2026_Board_I-K_CANONICAL_APPROVED_R1_REISSUE(3).xlsx"
    )
    candidate.write_bytes(b"duplicate-download-name")

    status = board_of_record.board_of_record_status(candidate)

    assert status["exists"] is True
    assert status["canonical_filename_matches"] is False
    assert status["mounted"] is False
    assert status["blocker"] == "inputs.board_of_record_i_k"

    with pytest.raises(GovernanceBlock, match="canonical mount name"):
        board_of_record.require_board_of_record(candidate)


def test_filename_alone_never_clears_custody(tmp_path: Path):
    candidate = tmp_path / EXPECTED_FILENAME
    candidate.write_bytes(b"synthetic pytest workbook")

    status = board_of_record.board_of_record_status(candidate)

    assert candidate.exists()
    assert status["canonical_filename_matches"] is True
    assert status["approved_digest_matches"] is False
    assert status["mounted"] is False
    assert status["blocker"] == board_of_record.BOARD_OF_RECORD_BLOCKER


def test_board_i_h_cannot_be_substituted():
    with pytest.raises(GovernanceBlock):
        board_of_record.reject_historical_board_substitution("Board I-H v2")
