from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


UUID_STR = String(36)
MONEY = Numeric(20, 6)
PROB = Numeric(12, 10)


class TeamRow(Base):
    __tablename__ = "teams"
    team_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    sport: Mapped[str] = mapped_column(String(16), nullable=False, default="NCAAF")
    school_name: Mapped[str] = mapped_column(String(160), nullable=False)
    nickname: Mapped[str | None] = mapped_column(String(120))
    abbreviations: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    covers_team_uuid: Mapped[str | None] = mapped_column(String(80), unique=True)
    covers_team_slug: Mapped[str | None] = mapped_column(String(200), unique=True)
    identity_status: Mapped[str] = mapped_column(String(24), nullable=False)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    valid_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameRow(Base):
    __tablename__ = "games"
    game_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    covers_game_id: Mapped[str | None] = mapped_column(String(80), unique=True)
    season: Mapped[int] = mapped_column(Integer, nullable=False)
    week: Mapped[int] = mapped_column(Integer, nullable=False)
    away_team_id: Mapped[str] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    home_team_id: Mapped[str] = mapped_column(ForeignKey("teams.team_id"), nullable=False)
    neutral_site: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    scheduled_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    final_away_score: Mapped[int | None] = mapped_column(Integer)
    final_home_score: Mapped[int | None] = mapped_column(Integer)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class EvidenceArtifactRow(Base):
    __tablename__ = "evidence_artifacts"
    evidence_artifact_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    source_name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class MarketObservationRow(Base):
    __tablename__ = "market_observations"
    __table_args__ = (
        UniqueConstraint("source", "source_game_id", "market_type", "observed_at", "raw_evidence_artifact_id", name="uq_market_observation_source"),
    )
    observation_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)
    side_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"))
    side_points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    total_points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    american_odds: Mapped[int | None] = mapped_column(Integer)
    source_game_id: Mapped[str | None] = mapped_column(String(80))
    source_url: Mapped[str | None] = mapped_column(Text)
    source_event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_evidence_artifact_id: Mapped[str] = mapped_column(ForeignKey("evidence_artifacts.evidence_artifact_id"), nullable=False)
    supersedes_observation_id: Mapped[str | None] = mapped_column(ForeignKey("market_observations.observation_id"))


class ContractRow(Base):
    __tablename__ = "contracts"
    contract_id: Mapped[str] = mapped_column(String(240), primary_key=True)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    market_type: Mapped[str] = mapped_column(String(16), nullable=False)
    subject_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"))
    side_points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    total_points: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    yes_definition: Mapped[str] = mapped_column(Text, nullable=False)
    no_definition: Mapped[str] = mapped_column(Text, nullable=False)
    push_definition: Mapped[str | None] = mapped_column(Text)
    source_observation_id: Mapped[str] = mapped_column(ForeignKey("market_observations.observation_id"), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False)
    opens_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    locks_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    belief_model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    market_model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ContractStateHistoryRow(Base):
    __tablename__ = "contract_state_history"
    history_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(24))
    to_state: Mapped[str] = mapped_column(String(24), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PublicMoneySnapshotRow(Base):
    __tablename__ = "public_money_snapshots"
    snapshot_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"))
    source_team_uuid: Mapped[str | None] = mapped_column(String(80))
    source_team_label: Mapped[str] = mapped_column(String(160), nullable=False)
    season_to_date_money: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    last_30_days_money: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    recent_money_ratio: Mapped[Decimal | None] = mapped_column(PROB)
    season_money_percentile: Mapped[Decimal | None] = mapped_column(PROB)
    recent_money_percentile: Mapped[Decimal | None] = mapped_column(PROB)
    recent_ratio_percentile: Mapped[Decimal | None] = mapped_column(PROB)
    public_crowding_score: Mapped[Decimal | None] = mapped_column(PROB)
    identity_status: Mapped[str] = mapped_column(String(24), nullable=False)
    source_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_artifact_id: Mapped[str] = mapped_column(ForeignKey("evidence_artifacts.evidence_artifact_id"), nullable=False)


class CapperRow(Base):
    __tablename__ = "cappers"
    capper_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    handle: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_profile_id: Mapped[str | None] = mapped_column(String(120))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CapperSkillProfileRow(Base):
    __tablename__ = "capper_skill_profiles"
    __table_args__ = (
        UniqueConstraint("capper_id", "season_scope", "market", name="uq_capper_skill_scope_market"),
    )
    skill_profile_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    capper_id: Mapped[str] = mapped_column(ForeignKey("cappers.capper_id"), nullable=False)
    sport: Mapped[str] = mapped_column(String(16), nullable=False, default="NCAAF")
    season_scope: Mapped[str] = mapped_column(String(80), nullable=False)
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    wins: Mapped[int] = mapped_column(Integer, nullable=False)
    losses: Mapped[int] = mapped_column(Integer, nullable=False)
    pushes: Mapped[int] = mapped_column(Integer, nullable=False)
    graded_sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    win_pct: Mapped[Decimal] = mapped_column(PROB, nullable=False)
    net_units: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    source_rank: Mapped[int | None] = mapped_column(Integer)
    source_population: Mapped[int | None] = mapped_column(Integer)
    skill_tier: Mapped[str] = mapped_column(String(32), nullable=False)
    reliability_weight: Mapped[Decimal | None] = mapped_column(PROB)
    reliability_status: Mapped[str] = mapped_column(String(24), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    evidence_artifact_id: Mapped[str] = mapped_column(ForeignKey("evidence_artifacts.evidence_artifact_id"), nullable=False)


class CapperPickRow(Base):
    __tablename__ = "capper_picks"
    pick_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    capper_id: Mapped[str] = mapped_column(ForeignKey("cappers.capper_id"), nullable=False)
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.contract_id"))
    market: Mapped[str] = mapped_column(String(16), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    selected_team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"))
    selected_total_direction: Mapped[str | None] = mapped_column(String(8))
    observed_strike: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    source_posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pick_status: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_artifact_id: Mapped[str] = mapped_column(ForeignKey("evidence_artifacts.evidence_artifact_id"), nullable=False)


class SignalRow(Base):
    __tablename__ = "signals"
    signal_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    contract_id: Mapped[str | None] = mapped_column(ForeignKey("contracts.contract_id"))
    game_id: Mapped[str | None] = mapped_column(ForeignKey("games.game_id"))
    team_id: Mapped[str | None] = mapped_column(ForeignKey("teams.team_id"))
    signal_type: Mapped[str] = mapped_column(String(48), nullable=False)
    effect: Mapped[str] = mapped_column(String(24), nullable=False)
    raw_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    normalized_value: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    confidence: Mapped[Decimal | None] = mapped_column(PROB)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_artifact_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ParticipantRow(Base):
    __tablename__ = "participants"
    participant_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    participant_type: Mapped[str] = mapped_column(String(40), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AmmStateRow(Base):
    __tablename__ = "amm_states"
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), primary_key=True)
    q_yes: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False, default=0)
    q_no: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False, default=0)
    liquidity_b: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AmmStateHistoryRow(Base):
    __tablename__ = "amm_state_history"
    history_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False)
    q_yes: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    q_no: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    liquidity_b: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(80))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OrderRow(Base):
    __tablename__ = "orders"
    order_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.participant_id"), nullable=False)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    maximum_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(Text)


class FillRow(Base):
    __tablename__ = "fills"
    fill_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.order_id"), nullable=False, unique=True)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False)
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.participant_id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False)
    execution_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    average_execution_price: Mapped[Decimal] = mapped_column(PROB, nullable=False)
    market_probability_before: Mapped[Decimal] = mapped_column(PROB, nullable=False)
    market_probability_after: Mapped[Decimal] = mapped_column(PROB, nullable=False)
    belief_probability_at_execution: Mapped[Decimal] = mapped_column(PROB, nullable=False)
    expected_edge_at_entry: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    signal_snapshot_id: Mapped[str] = mapped_column(UUID_STR, nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PositionRow(Base):
    __tablename__ = "positions"
    __table_args__ = (UniqueConstraint("participant_id", "contract_id", name="uq_position_participant_contract"),)
    position_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    participant_id: Mapped[str] = mapped_column(ForeignKey("participants.participant_id"), nullable=False)
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False)
    yes_shares: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False, default=0)
    no_shares: Mapped[Decimal] = mapped_column(Numeric(24, 10), nullable=False, default=0)
    cumulative_cost: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    realized_pnl: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    unrealized_mark: Mapped[Decimal | None] = mapped_column(MONEY)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LedgerTransactionRow(Base):
    __tablename__ = "ledger_transactions"
    transaction_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    reference_type: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class LedgerEntryRow(Base):
    __tablename__ = "ledger_entries"
    ledger_entry_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str] = mapped_column(ForeignKey("ledger_transactions.transaction_id"), nullable=False)
    account_id: Mapped[str] = mapped_column(UUID_STR, nullable=False)
    debit: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    credit: Mapped[Decimal] = mapped_column(MONEY, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="SYNTH")
    reference_type: Mapped[str] = mapped_column(String(24), nullable=False)
    reference_id: Mapped[str] = mapped_column(String(120), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OraclePacketRow(Base):
    __tablename__ = "oracle_packets"
    oracle_packet_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    game_id: Mapped[str] = mapped_column(ForeignKey("games.game_id"), nullable=False)
    evidence_agrees: Mapped[bool] = mapped_column(Boolean, nullable=False)
    adjudication_status: Mapped[str] = mapped_column(String(24), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OracleEvidenceRow(Base):
    __tablename__ = "oracle_evidence"
    evidence_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    oracle_packet_id: Mapped[str] = mapped_column(ForeignKey("oracle_packets.oracle_packet_id"), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    source_reference: Mapped[str] = mapped_column(Text, nullable=False)
    away_score: Mapped[int | None] = mapped_column(Integer)
    home_score: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SettlementRow(Base):
    __tablename__ = "settlements"
    settlement_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    contract_id: Mapped[str] = mapped_column(ForeignKey("contracts.contract_id"), nullable=False, unique=True)
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    final_away_score: Mapped[int | None] = mapped_column(Integer)
    final_home_score: Mapped[int | None] = mapped_column(Integer)
    payout_yes_per_share: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    payout_no_per_share: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    oracle_packet_id: Mapped[str] = mapped_column(ForeignKey("oracle_packets.oracle_packet_id"), nullable=False)
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_by: Mapped[str | None] = mapped_column(String(160))


class ModelVersionRow(Base):
    __tablename__ = "model_versions"
    model_version: Mapped[str] = mapped_column(String(80), primary_key=True)
    belief_model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    public_signal_version: Mapped[str] = mapped_column(String(80), nullable=False)
    participant_model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    amm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    settlement_rules_version: Mapped[str] = mapped_column(String(80), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str] = mapped_column(String(160), nullable=False)


class OutboxEventRow(Base):
    __tablename__ = "outbox_events"
    event_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    producer: Mapped[str] = mapped_column(String(120), nullable=False)
    correlation_id: Mapped[str] = mapped_column(UUID_STR, nullable=False)
    causation_id: Mapped[str | None] = mapped_column(UUID_STR)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEventRow(Base):
    __tablename__ = "audit_events"
    audit_event_id: Mapped[str] = mapped_column(UUID_STR, primary_key=True, default=lambda: str(uuid4()))
    actor: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str] = mapped_column(String(80), nullable=False)
    target_id: Mapped[str] = mapped_column(String(240), nullable=False)
    allowed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
