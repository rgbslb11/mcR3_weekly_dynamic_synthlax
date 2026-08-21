from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ..enums import Direction, IdentityStatus, MarketType, SettlementResult


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EventBase(StrictModel):
    event_id: UUID = Field(default_factory=uuid4)
    event_version: int = Field(default=1, ge=1)
    event_time: datetime
    observed_at: datetime
    recorded_at: datetime
    producer: str
    correlation_id: UUID
    causation_id: UUID | None = None


class TeamIdentityBlockedPayload(StrictModel):
    source_team_label: str
    reason: Literal["AMBIGUOUS_NICKNAME_NO_STABLE_ID", "NO_STABLE_ID"]


class MarketObservationCreatedPayload(StrictModel):
    observation_id: UUID
    game_id: UUID
    market_type: MarketType


class PublicMoneySnapshotCreatedPayload(StrictModel):
    snapshot_id: UUID
    source_team_label: str
    team_id: UUID | None = None
    identity_status: IdentityStatus


class CapperPickObservedPayload(StrictModel):
    pick_id: UUID
    capper_id: UUID
    game_id: UUID
    market: Literal["ATS", "TOTAL"]


class ContractCreatedPayload(StrictModel):
    contract_id: str
    game_id: UUID
    market_type: MarketType
    source_observation_id: UUID


class OrderAcceptedPayload(StrictModel):
    order_id: UUID
    contract_id: str
    participant_id: UUID
    direction: Direction
    quantity: float = Field(gt=0)


class OrderRejectedPayload(StrictModel):
    order_id: UUID | None = None
    idempotency_key: str
    contract_id: str
    reason: str


class FillExecutedPayload(StrictModel):
    fill_id: UUID
    order_id: UUID
    contract_id: str
    market_probability_before: float = Field(gt=0, lt=1)
    market_probability_after: float = Field(gt=0, lt=1)
    belief_probability_at_execution: float = Field(gt=0, lt=1)
    expected_edge_at_entry: float


class OracleConflictDetectedPayload(StrictModel):
    oracle_packet_id: UUID
    game_id: UUID


class SettlementFinalizedPayload(StrictModel):
    settlement_id: UUID
    contract_id: str
    result: SettlementResult


class ModelVersionActivatedPayload(StrictModel):
    model_version: str
    configuration_hash: str


class TeamIdentityBlocked(EventBase):
    event_type: Literal["team.identity.blocked"] = "team.identity.blocked"
    payload: TeamIdentityBlockedPayload


class MarketObservationCreated(EventBase):
    event_type: Literal["market.observation.created"] = "market.observation.created"
    payload: MarketObservationCreatedPayload


class PublicMoneySnapshotCreated(EventBase):
    event_type: Literal["public_money.snapshot.created"] = "public_money.snapshot.created"
    payload: PublicMoneySnapshotCreatedPayload


class CapperPickObserved(EventBase):
    event_type: Literal["capper.pick.observed"] = "capper.pick.observed"
    payload: CapperPickObservedPayload


class ContractCreated(EventBase):
    event_type: Literal["contract.created"] = "contract.created"
    payload: ContractCreatedPayload


class OrderAccepted(EventBase):
    event_type: Literal["order.accepted"] = "order.accepted"
    payload: OrderAcceptedPayload


class OrderRejected(EventBase):
    event_type: Literal["order.rejected"] = "order.rejected"
    payload: OrderRejectedPayload


class FillExecuted(EventBase):
    event_type: Literal["fill.executed"] = "fill.executed"
    payload: FillExecutedPayload


class OracleConflictDetected(EventBase):
    event_type: Literal["oracle.conflict.detected"] = "oracle.conflict.detected"
    payload: OracleConflictDetectedPayload


class SettlementFinalized(EventBase):
    event_type: Literal["settlement.finalized"] = "settlement.finalized"
    payload: SettlementFinalizedPayload


class ModelVersionActivated(EventBase):
    event_type: Literal["model.version.activated"] = "model.version.activated"
    payload: ModelVersionActivatedPayload


DomainEvent = Annotated[
    Union[
        TeamIdentityBlocked,
        MarketObservationCreated,
        PublicMoneySnapshotCreated,
        CapperPickObserved,
        ContractCreated,
        OrderAccepted,
        OrderRejected,
        FillExecuted,
        OracleConflictDetected,
        SettlementFinalized,
        ModelVersionActivated,
    ],
    Field(discriminator="event_type"),
]

DOMAIN_EVENT_ADAPTER = TypeAdapter(DomainEvent)


def validate_event(data: dict) -> DomainEvent:
    return DOMAIN_EVENT_ADAPTER.validate_python(data)


def domain_event_json_schema() -> dict:
    return DOMAIN_EVENT_ADAPTER.json_schema()
