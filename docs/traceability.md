# v0 Traceability Matrix

| Outcome | Requirement | Build item | Primary tests | Metric / gate |
|---|---|---|---|---|
| Separate evidence from popularity | Public money cannot directly alter belief | `belief.py`, `signals/public_money.py` | `test_belief.py`, golden B | belief unchanged under public flow |
| Deterministic synthetic price | Orders change market probability through LMSR | `pricing/lmsr.py`, `market.py` | `test_lmsr.py`, `test_market.py` | deterministic cost/probability |
| No false sharp picks | History alone never creates directional evidence | `signals/capper.py`, `domain.py` | `test_capper.py`, `test_belief.py` | no consensus without picks |
| Preserve specialization | ATS/TOTAL profiles remain distinct | `CapperSkillProfile` | `test_capper.py` | market-specific eligibility |
| No guessed identities | Ambiguous nickname joins block | `identity.py` | `test_identity.py`, golden E | zero guessed joins |
| Preserve strikes | New line creates new observation/contract | `MarketObservation`, `factory.py` | `test_contracts.py` | historical strike remains immutable |
| Safe trading lifecycle | Only OPEN contracts execute | `state_machine.py`, `market.py` | `test_state_machine.py`, `test_market.py` | post-lock trade rejected |
| Reconcile money movement | Every transaction balances | `ledger.py`, DB tables | `test_ledger.py` | debits == credits |
| Deterministic settlement | SIDE/TOTAL rules explicit | `settlement/rules.py` | `test_settlement.py` | exact YES/NO/PUSH |
| Machine contracts | REST/event schemas are typed | `api/schemas.py`, `api/events.py` | `test_api.py`, `test_events.py` | schema validation passes |
| Persistence bootstrap | Canonical objects persist | `models.py`, Alembic | `test_models.py`, migration smoke test | schema creates cleanly |
