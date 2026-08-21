from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from ..domain import Contract, Game, MarketObservation, Team
from ..enums import ContractState, IdentityStatus, MarketType


def _format_strike(value: Decimal) -> str:
    sign = "P" if value > 0 else "M" if value < 0 else "Z"
    return f"{sign}{abs(value):f}".rstrip("0").rstrip(".")


def build_contract(
    game: Game,
    observation: MarketObservation,
    teams: dict,
    opens_at: datetime,
    belief_model_version: str = "belief-v0",
    market_model_version: str = "lmsr-v0",
    created_at: datetime | None = None,
) -> Contract:
    if observation.game_id != game.game_id:
        raise ValueError("observation does not belong to game")
    away: Team = teams[game.away_team_id]
    home: Team = teams[game.home_team_id]
    if away.identity_status != IdentityStatus.VERIFIED or home.identity_status != IdentityStatus.VERIFIED:
        raise ValueError("both team identities must be VERIFIED")
    created_at = created_at or opens_at
    away_code = away.abbreviations[0] if away.abbreviations else away.school_name.upper().replace(" ", "")
    home_code = home.abbreviations[0] if home.abbreviations else home.school_name.upper().replace(" ", "")

    if observation.market_type == MarketType.SIDE:
        team = teams[observation.side_team_id]
        strike = observation.side_points
        assert strike is not None
        team_code = team.abbreviations[0] if team.abbreviations else team.school_name.upper().replace(" ", "")
        contract_id = (
            f"NCAAF-{game.season}-W{game.week}-{away_code}-{home_code}-SIDE-"
            f"{team_code}-{_format_strike(strike)}"
        )
        yes = f"{team.school_name} covers {strike:+f}".rstrip("0").rstrip(".")
        no = f"{team.school_name} does not cover {strike:+f}".rstrip("0").rstrip(".")
        return Contract(
            contract_id=contract_id,
            game_id=game.game_id,
            market_type=MarketType.SIDE,
            subject_team_id=team.team_id,
            side_points=strike,
            yes_definition=yes,
            no_definition=no,
            push_definition="Adjusted scores are equal for an integer strike",
            source_observation_id=observation.observation_id,
            state=ContractState.CREATED,
            opens_at=opens_at,
            locks_at=game.scheduled_start,
            belief_model_version=belief_model_version,
            market_model_version=market_model_version,
            created_at=created_at,
        )

    strike = observation.total_points
    assert strike is not None
    strike_text = f"{strike:f}".rstrip("0").rstrip(".")
    contract_id = f"NCAAF-{game.season}-W{game.week}-{away_code}-{home_code}-TOTAL-O{strike_text}"
    return Contract(
        contract_id=contract_id,
        game_id=game.game_id,
        market_type=MarketType.TOTAL,
        total_points=strike,
        yes_definition=f"Final combined score is over {strike_text}",
        no_definition=f"Final combined score is under {strike_text}",
        push_definition="Final combined score equals an integer total strike",
        source_observation_id=observation.observation_id,
        state=ContractState.CREATED,
        opens_at=opens_at,
        locks_at=game.scheduled_start,
        belief_model_version=belief_model_version,
        market_model_version=market_model_version,
        created_at=created_at,
    )
