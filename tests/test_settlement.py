from datetime import timedelta
from decimal import Decimal

from ncaaf_engine.contracts.factory import build_contract
from ncaaf_engine.enums import SettlementResult
from ncaaf_engine.settlement.rules import settle_contract


def test_side_yes(now, verified_teams, unc_tcu_game, tcu_side_observation):
    unc, tcu = verified_teams
    c = build_contract(unc_tcu_game, tcu_side_observation, {unc.team_id: unc, tcu.team_id: tcu}, now)
    assert settle_contract(c, unc.team_id, tcu.team_id, 20, 31) == SettlementResult.YES


def test_side_no(now, verified_teams, unc_tcu_game, tcu_side_observation):
    unc, tcu = verified_teams
    c = build_contract(unc_tcu_game, tcu_side_observation, {unc.team_id: unc, tcu.team_id: tcu}, now)
    assert settle_contract(c, unc.team_id, tcu.team_id, 24, 27) == SettlementResult.NO


def test_integer_spread_push(now, verified_teams, unc_tcu_game, tcu_side_observation):
    unc, tcu = verified_teams
    obs = tcu_side_observation.model_copy(update={"side_points": Decimal("-7")})
    c = build_contract(unc_tcu_game, obs, {unc.team_id: unc, tcu.team_id: tcu}, now)
    assert settle_contract(c, unc.team_id, tcu.team_id, 20, 27) == SettlementResult.PUSH


def test_total_yes(now, verified_teams, unc_tcu_game, total_observation):
    unc, tcu = verified_teams
    c = build_contract(unc_tcu_game, total_observation, {unc.team_id: unc, tcu.team_id: tcu}, now)
    assert settle_contract(c, unc.team_id, tcu.team_id, 24, 26) == SettlementResult.YES


def test_total_no(now, verified_teams, unc_tcu_game, total_observation):
    unc, tcu = verified_teams
    c = build_contract(unc_tcu_game, total_observation, {unc.team_id: unc, tcu.team_id: tcu}, now)
    assert settle_contract(c, unc.team_id, tcu.team_id, 24, 25) == SettlementResult.NO
