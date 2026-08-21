-- NCAAF Synthetic Market Engine v0.1.0
-- Rendered PostgreSQL schema snapshot. Historical artifact: do not edit after release.


CREATE TABLE audit_events (
	audit_event_id VARCHAR(36) NOT NULL, 
	actor VARCHAR(160) NOT NULL, 
	action VARCHAR(120) NOT NULL, 
	target_type VARCHAR(80) NOT NULL, 
	target_id VARCHAR(240) NOT NULL, 
	allowed BOOLEAN NOT NULL, 
	reason TEXT, 
	evidence JSON NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (audit_event_id)
)

;


CREATE TABLE cappers (
	capper_id VARCHAR(36) NOT NULL, 
	handle VARCHAR(120) NOT NULL, 
	source VARCHAR(80) NOT NULL, 
	source_profile_id VARCHAR(120), 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (capper_id), 
	UNIQUE (handle)
)

;


CREATE TABLE evidence_artifacts (
	evidence_artifact_id VARCHAR(36) NOT NULL, 
	source_type VARCHAR(24) NOT NULL, 
	source_name VARCHAR(160) NOT NULL, 
	source_reference TEXT, 
	content_hash VARCHAR(128) NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	immutable BOOLEAN NOT NULL, 
	PRIMARY KEY (evidence_artifact_id)
)

;


CREATE TABLE ledger_transactions (
	transaction_id VARCHAR(36) NOT NULL, 
	reference_type VARCHAR(24) NOT NULL, 
	reference_id VARCHAR(120) NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (transaction_id)
)

;


CREATE TABLE model_versions (
	model_version VARCHAR(80) NOT NULL, 
	belief_model_version VARCHAR(80) NOT NULL, 
	public_signal_version VARCHAR(80) NOT NULL, 
	participant_model_version VARCHAR(80) NOT NULL, 
	amm_version VARCHAR(80) NOT NULL, 
	settlement_rules_version VARCHAR(80) NOT NULL, 
	configuration_hash VARCHAR(128) NOT NULL, 
	effective_from TIMESTAMP WITH TIME ZONE NOT NULL, 
	retired_at TIMESTAMP WITH TIME ZONE, 
	approved_by VARCHAR(160) NOT NULL, 
	PRIMARY KEY (model_version)
)

;


CREATE TABLE outbox_events (
	event_id VARCHAR(36) NOT NULL, 
	event_type VARCHAR(120) NOT NULL, 
	event_version INTEGER NOT NULL, 
	event_time TIMESTAMP WITH TIME ZONE NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	producer VARCHAR(120) NOT NULL, 
	correlation_id VARCHAR(36) NOT NULL, 
	causation_id VARCHAR(36), 
	payload JSON NOT NULL, 
	published_at TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (event_id)
)

;


CREATE TABLE participants (
	participant_id VARCHAR(36) NOT NULL, 
	name VARCHAR(160) NOT NULL, 
	participant_type VARCHAR(40) NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	PRIMARY KEY (participant_id)
)

;


CREATE TABLE teams (
	team_id VARCHAR(36) NOT NULL, 
	sport VARCHAR(16) NOT NULL, 
	school_name VARCHAR(160) NOT NULL, 
	nickname VARCHAR(120), 
	abbreviations JSON NOT NULL, 
	covers_team_uuid VARCHAR(80), 
	covers_team_slug VARCHAR(200), 
	identity_status VARCHAR(24) NOT NULL, 
	valid_from TIMESTAMP WITH TIME ZONE, 
	valid_to TIMESTAMP WITH TIME ZONE, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (team_id), 
	UNIQUE (covers_team_uuid), 
	UNIQUE (covers_team_slug)
)

;


CREATE TABLE capper_skill_profiles (
	skill_profile_id VARCHAR(36) NOT NULL, 
	capper_id VARCHAR(36) NOT NULL, 
	sport VARCHAR(16) NOT NULL, 
	season_scope VARCHAR(80) NOT NULL, 
	market VARCHAR(16) NOT NULL, 
	wins INTEGER NOT NULL, 
	losses INTEGER NOT NULL, 
	pushes INTEGER NOT NULL, 
	graded_sample_size INTEGER NOT NULL, 
	win_pct NUMERIC(12, 10) NOT NULL, 
	net_units NUMERIC(20, 6) NOT NULL, 
	source_rank INTEGER, 
	source_population INTEGER, 
	skill_tier VARCHAR(32) NOT NULL, 
	reliability_weight NUMERIC(12, 10), 
	reliability_status VARCHAR(24) NOT NULL, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	evidence_artifact_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (skill_profile_id), 
	CONSTRAINT uq_capper_skill_scope_market UNIQUE (capper_id, season_scope, market), 
	FOREIGN KEY(capper_id) REFERENCES cappers (capper_id), 
	FOREIGN KEY(evidence_artifact_id) REFERENCES evidence_artifacts (evidence_artifact_id)
)

;


CREATE TABLE games (
	game_id VARCHAR(36) NOT NULL, 
	covers_game_id VARCHAR(80), 
	season INTEGER NOT NULL, 
	week INTEGER NOT NULL, 
	away_team_id VARCHAR(36) NOT NULL, 
	home_team_id VARCHAR(36) NOT NULL, 
	neutral_site BOOLEAN NOT NULL, 
	scheduled_start TIMESTAMP WITH TIME ZONE NOT NULL, 
	timezone VARCHAR(64) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	final_away_score INTEGER, 
	final_home_score INTEGER, 
	event_time TIMESTAMP WITH TIME ZONE, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (game_id), 
	UNIQUE (covers_game_id), 
	FOREIGN KEY(away_team_id) REFERENCES teams (team_id), 
	FOREIGN KEY(home_team_id) REFERENCES teams (team_id)
)

;


CREATE TABLE ledger_entries (
	ledger_entry_id VARCHAR(36) NOT NULL, 
	transaction_id VARCHAR(36) NOT NULL, 
	account_id VARCHAR(36) NOT NULL, 
	debit NUMERIC(20, 6) NOT NULL, 
	credit NUMERIC(20, 6) NOT NULL, 
	currency VARCHAR(16) NOT NULL, 
	reference_type VARCHAR(24) NOT NULL, 
	reference_id VARCHAR(120) NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (ledger_entry_id), 
	FOREIGN KEY(transaction_id) REFERENCES ledger_transactions (transaction_id)
)

;


CREATE TABLE public_money_snapshots (
	snapshot_id VARCHAR(36) NOT NULL, 
	team_id VARCHAR(36), 
	source_team_uuid VARCHAR(80), 
	source_team_label VARCHAR(160) NOT NULL, 
	season_to_date_money NUMERIC(20, 6) NOT NULL, 
	last_30_days_money NUMERIC(20, 6) NOT NULL, 
	recent_money_ratio NUMERIC(12, 10), 
	season_money_percentile NUMERIC(12, 10), 
	recent_money_percentile NUMERIC(12, 10), 
	recent_ratio_percentile NUMERIC(12, 10), 
	public_crowding_score NUMERIC(12, 10), 
	identity_status VARCHAR(24) NOT NULL, 
	source_snapshot_at TIMESTAMP WITH TIME ZONE, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	evidence_artifact_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (snapshot_id), 
	FOREIGN KEY(team_id) REFERENCES teams (team_id), 
	FOREIGN KEY(evidence_artifact_id) REFERENCES evidence_artifacts (evidence_artifact_id)
)

;


CREATE TABLE market_observations (
	observation_id VARCHAR(36) NOT NULL, 
	game_id VARCHAR(36) NOT NULL, 
	source VARCHAR(80) NOT NULL, 
	market_type VARCHAR(16) NOT NULL, 
	side_team_id VARCHAR(36), 
	side_points NUMERIC(8, 2), 
	total_points NUMERIC(8, 2), 
	american_odds INTEGER, 
	source_game_id VARCHAR(80), 
	source_url TEXT, 
	source_event_time TIMESTAMP WITH TIME ZONE, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	raw_evidence_artifact_id VARCHAR(36) NOT NULL, 
	supersedes_observation_id VARCHAR(36), 
	PRIMARY KEY (observation_id), 
	CONSTRAINT uq_market_observation_source UNIQUE (source, source_game_id, market_type, observed_at, raw_evidence_artifact_id), 
	FOREIGN KEY(game_id) REFERENCES games (game_id), 
	FOREIGN KEY(side_team_id) REFERENCES teams (team_id), 
	FOREIGN KEY(raw_evidence_artifact_id) REFERENCES evidence_artifacts (evidence_artifact_id), 
	FOREIGN KEY(supersedes_observation_id) REFERENCES market_observations (observation_id)
)

;


CREATE TABLE oracle_packets (
	oracle_packet_id VARCHAR(36) NOT NULL, 
	game_id VARCHAR(36) NOT NULL, 
	evidence_agrees BOOLEAN NOT NULL, 
	adjudication_status VARCHAR(24) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (oracle_packet_id), 
	FOREIGN KEY(game_id) REFERENCES games (game_id)
)

;


CREATE TABLE contracts (
	contract_id VARCHAR(240) NOT NULL, 
	game_id VARCHAR(36) NOT NULL, 
	market_type VARCHAR(16) NOT NULL, 
	subject_team_id VARCHAR(36), 
	side_points NUMERIC(8, 2), 
	total_points NUMERIC(8, 2), 
	yes_definition TEXT NOT NULL, 
	no_definition TEXT NOT NULL, 
	push_definition TEXT, 
	source_observation_id VARCHAR(36) NOT NULL, 
	state VARCHAR(24) NOT NULL, 
	opens_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	locks_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	belief_model_version VARCHAR(80) NOT NULL, 
	market_model_version VARCHAR(80) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (contract_id), 
	FOREIGN KEY(game_id) REFERENCES games (game_id), 
	FOREIGN KEY(subject_team_id) REFERENCES teams (team_id), 
	FOREIGN KEY(source_observation_id) REFERENCES market_observations (observation_id)
)

;


CREATE TABLE oracle_evidence (
	evidence_id VARCHAR(36) NOT NULL, 
	oracle_packet_id VARCHAR(36) NOT NULL, 
	source VARCHAR(120) NOT NULL, 
	source_reference TEXT NOT NULL, 
	away_score INTEGER, 
	home_score INTEGER, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (evidence_id), 
	FOREIGN KEY(oracle_packet_id) REFERENCES oracle_packets (oracle_packet_id)
)

;


CREATE TABLE amm_state_history (
	history_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240) NOT NULL, 
	q_yes NUMERIC(24, 10) NOT NULL, 
	q_no NUMERIC(24, 10) NOT NULL, 
	liquidity_b NUMERIC(24, 10) NOT NULL, 
	reason VARCHAR(40) NOT NULL, 
	reference_id VARCHAR(80), 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (history_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id)
)

;


CREATE TABLE amm_states (
	contract_id VARCHAR(240) NOT NULL, 
	q_yes NUMERIC(24, 10) NOT NULL, 
	q_no NUMERIC(24, 10) NOT NULL, 
	liquidity_b NUMERIC(24, 10) NOT NULL, 
	version INTEGER NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (contract_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id)
)

;


CREATE TABLE capper_picks (
	pick_id VARCHAR(36) NOT NULL, 
	capper_id VARCHAR(36) NOT NULL, 
	game_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240), 
	market VARCHAR(16) NOT NULL, 
	direction VARCHAR(8) NOT NULL, 
	selected_team_id VARCHAR(36), 
	selected_total_direction VARCHAR(8), 
	observed_strike NUMERIC(8, 2) NOT NULL, 
	source_posted_at TIMESTAMP WITH TIME ZONE, 
	observed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	pick_status VARCHAR(16) NOT NULL, 
	evidence_artifact_id VARCHAR(36) NOT NULL, 
	PRIMARY KEY (pick_id), 
	FOREIGN KEY(capper_id) REFERENCES cappers (capper_id), 
	FOREIGN KEY(game_id) REFERENCES games (game_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id), 
	FOREIGN KEY(selected_team_id) REFERENCES teams (team_id), 
	FOREIGN KEY(evidence_artifact_id) REFERENCES evidence_artifacts (evidence_artifact_id)
)

;


CREATE TABLE contract_state_history (
	history_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240) NOT NULL, 
	from_state VARCHAR(24), 
	to_state VARCHAR(24) NOT NULL, 
	reason TEXT, 
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (history_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id)
)

;


CREATE TABLE orders (
	order_id VARCHAR(36) NOT NULL, 
	idempotency_key VARCHAR(160) NOT NULL, 
	participant_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240) NOT NULL, 
	direction VARCHAR(8) NOT NULL, 
	quantity NUMERIC(24, 10) NOT NULL, 
	maximum_cost NUMERIC(20, 6), 
	status VARCHAR(24) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	accepted_at TIMESTAMP WITH TIME ZONE, 
	rejected_reason TEXT, 
	PRIMARY KEY (order_id), 
	UNIQUE (idempotency_key), 
	FOREIGN KEY(participant_id) REFERENCES participants (participant_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id)
)

;


CREATE TABLE positions (
	position_id VARCHAR(36) NOT NULL, 
	participant_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240) NOT NULL, 
	yes_shares NUMERIC(24, 10) NOT NULL, 
	no_shares NUMERIC(24, 10) NOT NULL, 
	cumulative_cost NUMERIC(20, 6) NOT NULL, 
	realized_pnl NUMERIC(20, 6) NOT NULL, 
	unrealized_mark NUMERIC(20, 6), 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (position_id), 
	CONSTRAINT uq_position_participant_contract UNIQUE (participant_id, contract_id), 
	FOREIGN KEY(participant_id) REFERENCES participants (participant_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id)
)

;


CREATE TABLE settlements (
	settlement_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240) NOT NULL, 
	result VARCHAR(16) NOT NULL, 
	final_away_score INTEGER, 
	final_home_score INTEGER, 
	payout_yes_per_share NUMERIC(20, 6) NOT NULL, 
	payout_no_per_share NUMERIC(20, 6) NOT NULL, 
	oracle_packet_id VARCHAR(36) NOT NULL, 
	proposed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	finalized_at TIMESTAMP WITH TIME ZONE, 
	finalized_by VARCHAR(160), 
	PRIMARY KEY (settlement_id), 
	UNIQUE (contract_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id), 
	FOREIGN KEY(oracle_packet_id) REFERENCES oracle_packets (oracle_packet_id)
)

;


CREATE TABLE signals (
	signal_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240), 
	game_id VARCHAR(36), 
	team_id VARCHAR(36), 
	signal_type VARCHAR(48) NOT NULL, 
	effect VARCHAR(24) NOT NULL, 
	raw_value NUMERIC(20, 10), 
	normalized_value NUMERIC(20, 10), 
	confidence NUMERIC(12, 10), 
	model_version VARCHAR(80) NOT NULL, 
	evidence_artifact_ids JSON NOT NULL, 
	valid_from TIMESTAMP WITH TIME ZONE NOT NULL, 
	valid_until TIMESTAMP WITH TIME ZONE, 
	generated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (signal_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id), 
	FOREIGN KEY(game_id) REFERENCES games (game_id), 
	FOREIGN KEY(team_id) REFERENCES teams (team_id)
)

;


CREATE TABLE fills (
	fill_id VARCHAR(36) NOT NULL, 
	order_id VARCHAR(36) NOT NULL, 
	contract_id VARCHAR(240) NOT NULL, 
	participant_id VARCHAR(36) NOT NULL, 
	direction VARCHAR(8) NOT NULL, 
	quantity NUMERIC(24, 10) NOT NULL, 
	execution_cost NUMERIC(20, 6) NOT NULL, 
	average_execution_price NUMERIC(12, 10) NOT NULL, 
	market_probability_before NUMERIC(12, 10) NOT NULL, 
	market_probability_after NUMERIC(12, 10) NOT NULL, 
	belief_probability_at_execution NUMERIC(12, 10) NOT NULL, 
	expected_edge_at_entry NUMERIC(20, 10) NOT NULL, 
	signal_snapshot_id VARCHAR(36) NOT NULL, 
	model_version VARCHAR(80) NOT NULL, 
	executed_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (fill_id), 
	UNIQUE (order_id), 
	FOREIGN KEY(order_id) REFERENCES orders (order_id), 
	FOREIGN KEY(contract_id) REFERENCES contracts (contract_id), 
	FOREIGN KEY(participant_id) REFERENCES participants (participant_id)
)

;

