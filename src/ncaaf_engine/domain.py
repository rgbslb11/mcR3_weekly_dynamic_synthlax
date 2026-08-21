from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import (
    CapperMarket,
    ContractState,
    Direction,
    GameStatus,
    IdentityStatus,
    MarketType,
    OrderStatus,
    ParticipantType,
    ReliabilityStatus,
    SettlementResult,
    SignalEffect,
    SignalType,
    SkillTier,
)


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Team(FrozenModel):
    team_id: UUID = Field(default_factory=uuid4)
    sport: Literal["NCAAF"] = "NCAAF"
    school_name: str
    nickname: str | None = None
    abbreviations: tuple[str, ...] = ()
    covers_team_uuid: str | None = None
    covers_team_slug: str | None = None
    identity_status: IdentityStatus = IdentityStatus.PROVISIONAL
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def verified_requires_stable_id(self):
        if self.identity_status == IdentityStatus.VERIFIED and not (
            self.covers_team_uuid or self.covers_team_slug
        ):
            raise ValueError("VERIFIED team requires stable external identifier")
        return self


class Game(FrozenModel):
    game_id: UUID = Field(default_factory=uuid4)
    covers_game_id: str | None = None
    season: int
    week: int
    away_team_id: UUID
    home_team_id: UUID
    neutral_site: bool = False
    scheduled_start: datetime
    timezone: str
    status: GameStatus = GameStatus.SCHEDULED
    final_away_score: int | None = Field(default=None, ge=0)
    final_home_score: int | None = Field(default=None, ge=0)
    event_time: datetime | None = None
    observed_at: datetime
    recorded_at: datetime
    evidence_artifact_ids: tuple[UUID, ...] = ()


class MarketObservation(FrozenModel):
    observation_id: UUID = Field(default_factory=uuid4)
    game_id: UUID
    source: str
    market_type: MarketType
    side_team_id: UUID | None = None
    side_points: Decimal | None = None
    total_points: Decimal | None = None
    american_odds: int | None = None
    source_game_id: str | None = None
    source_url: str | None = None
    source_event_time: datetime | None = None
    observed_at: datetime
    recorded_at: datetime
    raw_evidence_artifact_id: UUID
    supersedes_observation_id: UUID | None = None

    @model_validator(mode="after")
    def validate_strike(self):
        if self.market_type == MarketType.SIDE:
            if self.side_team_id is None or self.side_points is None:
                raise ValueError("SIDE observation requires side_team_id and side_points")
            if self.total_points is not None:
                raise ValueError("SIDE observation must not contain total_points")
        elif self.market_type == MarketType.TOTAL:
            if self.total_points is None:
                raise ValueError("TOTAL observation requires total_points")
            if self.side_team_id is not None or self.side_points is not None:
                raise ValueError("TOTAL observation must not contain side strike")
        return self


class Contract(FrozenModel):
    contract_id: str
    game_id: UUID
    market_type: MarketType
    subject_team_id: UUID | None = None
    side_points: Decimal | None = None
    total_points: Decimal | None = None
    yes_definition: str
    no_definition: str
    push_definition: str | None = None
    source_observation_id: UUID
    state: ContractState = ContractState.CREATED
    opens_at: datetime
    locks_at: datetime
    belief_model_version: str
    market_model_version: str
    created_at: datetime

    @model_validator(mode="after")
    def validate_contract(self):
        if self.opens_at >= self.locks_at:
            raise ValueError("opens_at must precede locks_at")
        if self.market_type == MarketType.SIDE and (
            self.subject_team_id is None or self.side_points is None
        ):
            raise ValueError("SIDE contract requires team and side strike")
        if self.market_type == MarketType.TOTAL and self.total_points is None:
            raise ValueError("TOTAL contract requires total strike")
        return self


class PublicMoneySnapshot(FrozenModel):
    snapshot_id: UUID = Field(default_factory=uuid4)
    team_id: UUID | None = None
    source_team_uuid: str | None = None
    source_team_label: str
    season_to_date_money: Decimal = Field(ge=0)
    last_30_days_money: Decimal = Field(ge=0)
    recent_money_ratio: float | None = Field(default=None, ge=0)
    season_money_percentile: float | None = Field(default=None, ge=0, le=1)
    recent_money_percentile: float | None = Field(default=None, ge=0, le=1)
    recent_ratio_percentile: float | None = Field(default=None, ge=0, le=1)
    public_crowding_score: float | None = Field(default=None, ge=0, le=1)
    identity_status: IdentityStatus
    source_snapshot_at: datetime | None = None
    observed_at: datetime
    recorded_at: datetime
    evidence_artifact_id: UUID


class Capper(FrozenModel):
    capper_id: UUID = Field(default_factory=uuid4)
    handle: str
    source: str
    source_profile_id: str | None = None
    active: bool = True
    created_at: datetime


class CapperSkillProfile(FrozenModel):
    skill_profile_id: UUID = Field(default_factory=uuid4)
    capper_id: UUID
    sport: Literal["NCAAF"] = "NCAAF"
    season_scope: str
    market: CapperMarket
    wins: int = Field(ge=0)
    losses: int = Field(ge=0)
    pushes: int = Field(ge=0)
    graded_sample_size: int = Field(ge=0)
    win_pct: float = Field(ge=0, le=1)
    net_units: Decimal
    source_rank: int | None = Field(default=None, ge=1)
    source_population: int | None = Field(default=None, ge=1)
    skill_tier: SkillTier
    reliability_weight: float | None = Field(default=None, ge=0)
    reliability_status: ReliabilityStatus = ReliabilityStatus.PROVISIONAL
    observed_at: datetime
    evidence_artifact_id: UUID

    @model_validator(mode="after")
    def sample_size_matches(self):
        if self.wins + self.losses + self.pushes != self.graded_sample_size:
            raise ValueError("graded_sample_size must equal wins + losses + pushes")
        return self


class CapperPick(FrozenModel):
    pick_id: UUID = Field(default_factory=uuid4)
    capper_id: UUID
    game_id: UUID
    contract_id: str | None = None
    market: CapperMarket
    direction: Direction
    selected_team_id: UUID | None = None
    selected_total_direction: Literal["OVER", "UNDER"] | None = None
    observed_strike: Decimal
    source_posted_at: datetime | None = None
    observed_at: datetime
    recorded_at: datetime
    pick_status: Literal["PENDING", "GRADED", "VOID"] = "PENDING"
    evidence_artifact_id: UUID


class Signal(FrozenModel):
    signal_id: UUID = Field(default_factory=uuid4)
    contract_id: str | None = None
    game_id: UUID | None = None
    team_id: UUID | None = None
    signal_type: SignalType
    effect: SignalEffect
    raw_value: float | None = None
    normalized_value: float | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    model_version: str
    evidence_artifact_ids: tuple[UUID, ...] = ()
    valid_from: datetime
    valid_until: datetime | None = None
    generated_at: datetime


class AmmState(FrozenModel):
    q_yes: float = 0.0
    q_no: float = 0.0
    liquidity_b: float = Field(default=1000.0, gt=0)


class Quote(FrozenModel):
    quote_id: UUID = Field(default_factory=uuid4)
    contract_id: str
    belief_probability_yes: float = Field(gt=0, lt=1)
    synthetic_market_probability_yes: float = Field(gt=0, lt=1)
    amm: AmmState
    model_version: str
    generated_at: datetime


class Order(FrozenModel):
    order_id: UUID = Field(default_factory=uuid4)
    idempotency_key: str
    participant_id: UUID
    contract_id: str
    direction: Direction
    quantity: float = Field(gt=0)
    maximum_cost: float | None = Field(default=None, gt=0)
    status: OrderStatus = OrderStatus.RECEIVED
    created_at: datetime
    accepted_at: datetime | None = None
    rejected_reason: str | None = None


class Fill(FrozenModel):
    fill_id: UUID = Field(default_factory=uuid4)
    order_id: UUID
    contract_id: str
    participant_id: UUID
    direction: Direction
    quantity: float = Field(gt=0)
    execution_cost: float = Field(gt=0)
    average_execution_price: float = Field(gt=0, lt=1)
    market_probability_before: float = Field(gt=0, lt=1)
    market_probability_after: float = Field(gt=0, lt=1)
    belief_probability_at_execution: float = Field(gt=0, lt=1)
    expected_edge_at_entry: float
    signal_snapshot_id: UUID
    model_version: str
    executed_at: datetime


class Position(FrozenModel):
    position_id: UUID = Field(default_factory=uuid4)
    participant_id: UUID
    contract_id: str
    yes_shares: float = 0
    no_shares: float = 0
    cumulative_cost: float = 0
    realized_pnl: float = 0
    unrealized_mark: float | None = None
    updated_at: datetime


class Participant(FrozenModel):
    participant_id: UUID = Field(default_factory=uuid4)
    name: str
    participant_type: ParticipantType
    enabled: bool = True


class OracleEvidence(FrozenModel):
    source: str
    source_reference: str
    away_score: int | None = Field(default=None, ge=0)
    home_score: int | None = Field(default=None, ge=0)
    observed_at: datetime


class OraclePacket(FrozenModel):
    oracle_packet_id: UUID = Field(default_factory=uuid4)
    game_id: UUID
    evidence: tuple[OracleEvidence, ...]
    evidence_agrees: bool
    adjudication_status: Literal["COMPLETE", "CONFLICT", "INCOMPLETE"]
    created_at: datetime


class Settlement(FrozenModel):
    settlement_id: UUID = Field(default_factory=uuid4)
    contract_id: str
    result: SettlementResult
    final_away_score: int | None = Field(default=None, ge=0)
    final_home_score: int | None = Field(default=None, ge=0)
    payout_yes_per_share: float = Field(ge=0)
    payout_no_per_share: float = Field(ge=0)
    oracle_packet_id: UUID
    proposed_at: datetime
    finalized_at: datetime | None = None
    finalized_by: str | None = None


class SimulationIntent(FrozenModel):
    participant_type: ParticipantType
    direction: Direction
    quantity: float = Field(gt=0)
    reason: str
