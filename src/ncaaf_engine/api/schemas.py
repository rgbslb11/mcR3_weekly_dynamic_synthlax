from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..enums import Direction, IdentityStatus, MarketType


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TeamCreate(ApiModel):
    school_name: str
    nickname: str | None = None
    abbreviations: list[str] = Field(default_factory=list)
    covers_team_uuid: str | None = None
    covers_team_slug: str | None = None
    identity_status: IdentityStatus = IdentityStatus.PROVISIONAL


class GameCreate(ApiModel):
    covers_game_id: str | None = None
    season: int
    week: int
    away_team_id: UUID
    home_team_id: UUID
    neutral_site: bool = False
    scheduled_start: datetime
    timezone: str


class MarketObservationCreate(ApiModel):
    game_id: UUID
    source: str
    market_type: MarketType
    side_team_id: UUID | None = None
    side_points: float | None = None
    total_points: float | None = None
    american_odds: int | None = None
    source_game_id: str | None = None
    source_url: str | None = None
    source_event_time: datetime | None = None
    observed_at: datetime
    raw_evidence_artifact_id: UUID


class ContractBuildRequest(ApiModel):
    game_id: UUID
    observation_id: UUID


class ContractBuildResponse(ApiModel):
    created_contract_ids: list[str]


class QuoteOrderRequest(ApiModel):
    direction: Direction
    quantity: float = Field(gt=0)


class QuoteOrderResponse(ApiModel):
    direction: Direction
    quantity: float
    quoted_cost: float
    average_price: float
    probability_before: float
    probability_after: float


class OrderCreate(ApiModel):
    participant_id: UUID
    contract_id: str
    direction: Direction
    quantity: float = Field(gt=0)
    maximum_cost: float | None = Field(default=None, gt=0)


class AuditFillResponse(ApiModel):
    fill_id: UUID
    reconstructable: bool
    missing_components: list[str]
    payload: dict
