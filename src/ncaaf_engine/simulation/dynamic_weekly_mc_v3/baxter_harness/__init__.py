"""C2 — experimental evaluation harness for the Baxter Rating RMSE objective.

Ruling R2-CAL-OBJECTIVE names out-of-sample Baxter Rating RMSE as the primary
mathematical calibration criterion. This package is the instrument that measures
it for a candidate regime over the six unresolved V3 calibration axes:

* ``weekly_performance_residual_coefficient``
* ``weekly_movement_cap_points``
* ``recent_form_weights``
* ``blowout_treatment``
* ``game_sd_points``
* ``sample_size_regularization``

What it is not: it is not the production rerater, it does not author candidate
values, it does not write canonical configuration, and it does not promote. The
production guardrail in :mod:`..rerating` stays closed, and the promotion gate
stays in :func:`..calibration.promote_regime_r2` behind a human approval token.

Every location it reads comes from a versioned data contract (:mod:`.contract`).
With no observation set mounted the harness reports ``READY_FOR_DATA`` and no
metrics, because a calibration harness that answers without data is how an
invented number acquires a provenance record.
"""

from .contract import (
    BLOCKED,
    CONTRACT_SCHEMA_VERSION,
    READY,
    READY_FOR_DATA,
    BaxterDataContract,
    ContractResolution,
    load_contract,
    resolve_contract,
)
from .evaluate import EVALUATED, RunContext, evaluate_regimes, payload_digest
from .regime import ResolvedRegime, regime_grid, resolve_regime, resolve_regimes

__all__ = [
    "BLOCKED",
    "CONTRACT_SCHEMA_VERSION",
    "EVALUATED",
    "READY",
    "READY_FOR_DATA",
    "BaxterDataContract",
    "ContractResolution",
    "ResolvedRegime",
    "RunContext",
    "evaluate_regimes",
    "load_contract",
    "payload_digest",
    "regime_grid",
    "resolve_contract",
    "resolve_regime",
    "resolve_regimes",
]
