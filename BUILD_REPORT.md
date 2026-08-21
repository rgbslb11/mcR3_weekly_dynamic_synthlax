# Build Report - NCAAF Synthetic Market Engine v0.1.0

## Classification

- Mode: Design
- Criticality: internal-operational / synthetic-only
- Maturity: build-ready reference implementation
- Real-money execution: disabled / out of scope

## Implemented

- Pydantic canonical domain schemas
- SQLAlchemy persistence model (25 tables)
- Alembic bootstrap migration
- rendered PostgreSQL DDL snapshot
- deterministic binary LMSR pricing module
- belief/public-flow isolation rules
- public-money recent-concentration and crowding calculations
- market-specific weighted capper consensus calculation
- no-guess team identity resolver
- deterministic contract factory with immutable strike identity
- contract state-machine guards
- synthetic Retail Crowd, Momentum Retail, and Contrarian intent rules
- order execution and expected-edge calculation
- double-entry ledger validation primitive
- SIDE/TOTAL settlement rules including PUSH
- typed FastAPI request/response schemas
- discriminated typed domain-event schemas
- generated OpenAPI JSON
- generated domain-event JSON Schema
- Week 1 sample seed fixture from the supplied Covers board
- traceability matrix and explicit blocker register

## Verification

- pytest: 59 passed
- Python compileall: passed
- Alembic upgrade head: passed
- Alembic downgrade base: passed
- SQLite metadata create/drop smoke test: passed

## Explicitly blocked / disabled

- independent 2026 power model
- historical line movement
- multi-book pricing
- sharp-consensus -> belief probability calibration
- ATS sharp-follower panel
- real-money execution

## Important v0 semantics

`last_30_days_money / season_to_date_money` is named `recent_money_ratio` / recent concentration. It is not represented as a true time-series velocity measurement.

Public money changes synthetic participant order propensity and therefore AMM market price. It does not directly modify belief probability.

Historical capper skill cannot instantiate a `CapperPick`.
