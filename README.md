# NCAAF Synthetic Market Engine v0

Runnable reference implementation for a **synthetic-only** NCAAF binary market engine. It preserves the session's core doctrine:

- `belief_probability` and `synthetic_market_probability` are independent.
- public money creates **flow**, not direct predictive belief;
- historical capper performance is market-specific and cannot create a pick;
- ambiguous nickname identity blocks instead of guessing;
- source strikes are immutable observations;
- missing lines do not create contracts;
- deterministic LMSR order flow determines synthetic market price;
- realized outcome and decision quality are measured separately;
- disputed settlement requires a human adjudication boundary.

## Stack

- Python 3.12+
- Pydantic 2
- SQLAlchemy 2
- FastAPI
- Alembic
- pytest

SQLite is supported for local tests. A rendered PostgreSQL DDL snapshot is included under `migrations/`.

## Quick start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
pytest
```

Run API:

```bash
uvicorn ncaaf_engine.api.app:app --reload
```

Useful endpoints:

```text
GET  /health
GET  /api/v0/amm/probability?q_yes=0&q_no=0
POST /api/v0/amm/quote
```

Example quote body:

```json
{"direction":"YES","quantity":25}
```

## Migrations

Local SQLite bootstrap:

```bash
alembic upgrade head
```

Reviewable PostgreSQL schema:

```text
migrations/0001_initial_postgresql.sql
```

The v0 bootstrap Alembic revision intentionally creates the immutable v0 metadata snapshot. Future revisions must use explicit additive/transformative Alembic operations rather than editing `0001_initial`.

## Package layout

```text
src/ncaaf_engine/
  api/                 typed REST and event contracts
  contracts/           deterministic contract factory
  pricing/             binary LMSR
  settlement/          SIDE/TOTAL settlement rules
  signals/             public-money and capper signals
  simulation/          synthetic participant rules
  belief.py            belief isolation controls
  config.py            versioned/tunable v0 parameters
  domain.py            typed canonical domain schemas
  identity.py          no-guess identity controls
  ledger.py            double-entry invariant
  market.py            order execution and entry-edge logic
  models.py            SQLAlchemy persistence models
  state_machine.py     legal contract transitions
```

## Intentionally blocked capabilities

These are feature flags, not TODO logic filled with guesses:

- independent 2026 power model;
- historical line-movement model;
- multi-book pricing;
- sharp-consensus -> probability calibration;
- ATS sharp-follower panel.

## Public-money terminology

The source provides season-to-date and last-30-days aggregates. v0 therefore uses:

```text
recent_money_ratio = last_30_days_money / season_to_date_money
```

as a **recent concentration ratio**, not a literal time-series velocity measurement.

The provisional crowding function remains configurable:

```text
crowding = 0.40*season_percentile
         + 0.35*recent_percentile
         + 0.25*recent_concentration_percentile
```

## AMM

Binary LMSR:

```text
C(qY,qN) = b * ln(exp(qY/b) + exp(qN/b))
```

with initial `q_yes=q_no=0`, producing a synthetic market probability of `0.5`. The default `b=1000` is a simulation parameter, not an empirically calibrated sports-market liquidity estimate.

## Evidence and time

Any productionized ingest must retain:

- `event_time`
- `observed_at`
- `recorded_at`

and must preserve immutable source/evidence references so every fill can be reconstructed without hindsight leakage.

## Release status

**Build-ready reference implementation; not production-ready.** A Harden-mode review is required before consequential or real-money use.
