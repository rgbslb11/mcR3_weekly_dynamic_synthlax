from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from ncaaf_engine.contracts.factory import build_contract
from ncaaf_engine.domain import MarketObservation, Team
from ncaaf_engine.enums import IdentityStatus, MarketType


def test_build_valid_side_contract(now, verified_teams, unc_tcu_game, tcu_side_observation):
    unc, tcu = verified_teams
    teams = {unc.team_id: unc, tcu.team_id: tcu}
    contract = build_contract(unc_tcu_game, tcu_side_observation, teams, now)
    assert contract.contract_id == "NCAAF-2026-W1-UNC-TCU-SIDE-TCU-M6.5"
    assert contract.side_points == Decimal("-6.5")


def test_build_valid_total_contract(now, verified_teams, unc_tcu_game, total_observation):
    unc, tcu = verified_teams
    contract = build_contract(unc_tcu_game, total_observation, {unc.team_id: unc, tcu.team_id: tcu}, now)
    assert contract.contract_id == "NCAAF-2026-W1-UNC-TCU-TOTAL-O49.5"


def test_unverified_team_blocks_contract(now, verified_teams, unc_tcu_game, tcu_side_observation):
    unc, tcu = verified_teams
    bad_unc = Team(
        team_id=unc.team_id,
        school_name=unc.school_name,
        nickname=unc.nickname,
        abbreviations=unc.abbreviations,
        identity_status=IdentityStatus.BLOCKED,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(ValueError, match="VERIFIED"):
        build_contract(unc_tcu_game, tcu_side_observation, {unc.team_id: bad_unc, tcu.team_id: tcu}, now)


def test_line_change_creates_distinct_contract(now, verified_teams, unc_tcu_game, tcu_side_observation):
    unc, tcu = verified_teams
    teams = {unc.team_id: unc, tcu.team_id: tcu}
    c65 = build_contract(unc_tcu_game, tcu_side_observation, teams, now)
    o75 = MarketObservation(
        game_id=unc_tcu_game.game_id,
        source="Covers",
        market_type=MarketType.SIDE,
        side_team_id=tcu.team_id,
        side_points=Decimal("-7.5"),
        source_game_id="377582",
        observed_at=now + timedelta(minutes=10),
        recorded_at=now + timedelta(minutes=10),
        raw_evidence_artifact_id=uuid4(),
        supersedes_observation_id=tcu_side_observation.observation_id,
    )
    c75 = build_contract(unc_tcu_game, o75, teams, now)
    assert c65.contract_id != c75.contract_id
    assert c65.side_points == Decimal("-6.5")
    assert c75.side_points == Decimal("-7.5")
