from __future__ import annotations

from decimal import Decimal

from ..domain import Contract
from ..enums import MarketType, SettlementResult


def settle_contract(
    contract: Contract,
    away_team_id,
    home_team_id,
    away_score: int,
    home_score: int,
) -> SettlementResult:
    if away_score < 0 or home_score < 0:
        raise ValueError("scores must be nonnegative")

    if contract.market_type == MarketType.TOTAL:
        total = Decimal(away_score + home_score)
        strike = contract.total_points
        assert strike is not None
        if total > strike:
            return SettlementResult.YES
        if total < strike:
            return SettlementResult.NO
        return SettlementResult.PUSH

    if contract.market_type == MarketType.SIDE:
        strike = contract.side_points
        team_id = contract.subject_team_id
        assert strike is not None and team_id is not None
        if team_id == away_team_id:
            subject, opponent = Decimal(away_score), Decimal(home_score)
        elif team_id == home_team_id:
            subject, opponent = Decimal(home_score), Decimal(away_score)
        else:
            raise ValueError("subject team is not in game")
        adjusted_subject = subject + strike
        if adjusted_subject > opponent:
            return SettlementResult.YES
        if adjusted_subject < opponent:
            return SettlementResult.NO
        return SettlementResult.PUSH

    raise ValueError(f"unsupported market type: {contract.market_type}")
