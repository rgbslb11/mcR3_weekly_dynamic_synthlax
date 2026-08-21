"""Experimental calibration harness for Dynamic Weekly MC V3.

The six V3 rerating calibration values are unresolved and stay that way. This
module exists so candidate values can be *tested* without ever becoming
canonical, and it is built around one invariant:

    An experiment can never write the canonical config.

Canonical values live in ``config/dynamic_weekly_mc_v3/v3_experimental.json``
and remain ``null``. Candidate regimes live under a separate experimental path,
``config/dynamic_weekly_mc_v3/experimental/``, and are loaded by this module
only. Promotion from a candidate regime to a canonical value requires an
explicit human approval token; :func:`promote_regime` refuses every other path,
including a regime that "won" whatever objective was scored.

Three further limits are deliberate rather than incidental:

* No regime may be declared best without a named
  :class:`EvaluationObjective`. Ranking candidates against an unstated goal is
  how an arbitrary choice acquires the appearance of evidence.
* Margin SD 20.2 is *not* treated as approved. It is the recorded achieved value
  from a prior engine run that sits above its own 16–18 harness band, and
  open item ENG-CAL-MARGIN keeps it open.
* Public-money signals are never admissible as predictive probability, and
  injury effects remain deferred. Both are rejected at dataset registration.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import GovernanceBlock, InputValidationError

#: The six unresolved calibration fields, in canonical config order.
CALIBRATION_FIELDS = (
    "weekly_performance_residual_coefficient",
    "weekly_movement_cap_points",
    "recent_form_weights",
    "blowout_treatment",
    "game_sd_points",
    "sample_size_regularization",
)

#: Signals that may never enter a calibration dataset as predictive input.
FORBIDDEN_DATASET_SIGNALS = (
    "public_money",
    "public_money_pct",
    "public_crowding_score",
    "handle_pct",
    "ticket_pct",
    "injury",
    "injuries",
    "injury_adjustment",
)

#: Recorded achieved value from the prior engine run. Above its 16-18 band and
#: still governed by open item ENG-CAL-MARGIN. Present for comparison only.
RECORDED_LEGACY_MARGIN_SD = 20.2
LEGACY_MARGIN_SD_BAND = (16.0, 18.0)

_APPROVAL_TOKEN = re.compile(r"^APPROVE_V3_CALIBRATION_PROMOTION::[A-Z0-9_.-]{4,}$")


@dataclass(frozen=True)
class EvaluationObjective:
    """An explicit, named objective a set of experiments is scored against."""

    objective_id: str
    metric: str
    direction: str  # "minimize" or "maximize"
    description: str

    def __post_init__(self) -> None:
        if self.direction not in ("minimize", "maximize"):
            raise InputValidationError(
                f"Evaluation objective direction must be minimize or maximize, got {self.direction!r}"
            )


@dataclass(frozen=True)
class CandidateRegime:
    """A named set of candidate calibration values. Never canonical."""

    regime_id: str
    values: dict[str, Any]
    rationale: str
    status: str = "EXPERIMENTAL"

    def __post_init__(self) -> None:
        if self.status != "EXPERIMENTAL":
            raise GovernanceBlock(
                f"Candidate regime {self.regime_id} must be EXPERIMENTAL, got {self.status!r}"
            )
        unknown = sorted(set(self.values) - set(CALIBRATION_FIELDS))
        if unknown:
            raise InputValidationError(f"Regime {self.regime_id} sets unknown fields: {unknown}")


@dataclass(frozen=True)
class CalibrationDataset:
    """A registered historical observation set used to score candidates."""

    dataset_id: str
    path: Path
    sha256: str
    rows: int
    columns: tuple[str, ...]


@dataclass(frozen=True)
class ExperimentRecord:
    """Full provenance for one calibration experiment."""

    experiment_id: str
    model_version: str
    configuration_version: str
    seed: int
    regime_id: str
    candidate_values: dict[str, Any]
    dataset_id: str
    dataset_sha256: str
    objective_id: str
    run_timestamp: str
    metrics: dict[str, float]
    v2_1_control_comparison: dict[str, Any]
    status: str = "EXPERIMENTAL_RESULT_NOT_PROMOTED"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["candidate_values"] = dict(self.candidate_values)
        return payload


def load_candidate_regimes(path: Path) -> list[CandidateRegime]:
    """Load candidate regimes from the experimental config path.

    Refuses to load from the canonical config file, so a candidate value cannot
    reach the engine by being written into the wrong document.
    """
    resolved = path.resolve()
    if resolved.name == "v3_experimental.json":
        raise GovernanceBlock(
            "Candidate regimes must not live in the canonical V3 config. "
            "Use config/dynamic_weekly_mc_v3/experimental/."
        )
    if "experimental" not in resolved.parts:
        raise GovernanceBlock(
            f"Candidate regimes must load from an experimental config path, got {resolved}"
        )
    raw = json.loads(resolved.read_text(encoding="utf-8"))
    return [
        CandidateRegime(
            regime_id=entry["regime_id"],
            values=entry.get("values", {}),
            rationale=entry.get("rationale", ""),
            status=entry.get("status", "EXPERIMENTAL"),
        )
        for entry in raw.get("regimes", [])
    ]


def register_dataset(path: Path, dataset_id: str) -> CalibrationDataset:
    """Register a historical calibration dataset, rejecting forbidden signals."""
    if not path.exists():
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} not found at {path}. "
            "BLOCKED_ON_CALIBRATION_DATA: no historical observation set is mounted."
        )
    data = path.read_bytes()
    text = data.decode("utf-8")
    header = text.splitlines()[0] if text.splitlines() else ""
    columns = tuple(c.strip() for c in header.split(",") if c.strip())
    offending = sorted({c for c in columns if c.lower() in FORBIDDEN_DATASET_SIGNALS})
    if offending:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} contains non-admissible predictive signals: "
            f"{offending}. Public money creates flow, not belief; injuries remain deferred."
        )
    return CalibrationDataset(
        dataset_id=dataset_id,
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        rows=max(len(text.splitlines()) - 1, 0),
        columns=columns,
    )


def rank_experiments(
    records: list[ExperimentRecord], objective: EvaluationObjective | None
) -> list[ExperimentRecord]:
    """Rank experiments against an explicit objective.

    Without a named objective there is no ranking to give, so this raises rather
    than falling back to an implicit default.
    """
    if objective is None:
        raise GovernanceBlock(
            "No evaluation objective supplied. A calibration regime cannot be called "
            "best without an explicit, named objective."
        )
    missing = [r.experiment_id for r in records if objective.metric not in r.metrics]
    if missing:
        raise InputValidationError(
            f"Experiments missing objective metric {objective.metric!r}: {missing}"
        )
    return sorted(
        records,
        key=lambda r: r.metrics[objective.metric],
        reverse=(objective.direction == "maximize"),
    )


def promote_regime(
    regime: CandidateRegime,
    *,
    approval_token: str | None = None,
    ranked_first: bool = False,
) -> dict[str, Any]:
    """Promotion gate. Refuses everything except an explicit human approval token.

    ``ranked_first`` is accepted only so it can be explicitly ignored: winning an
    evaluation is not authority to become canonical.
    """
    if approval_token is None:
        raise GovernanceBlock(
            f"Regime {regime.regime_id} cannot be promoted: no human approval token. "
            "Experimental results never update canonical V3 configuration automatically"
            + (" (including the top-ranked regime)." if ranked_first else ".")
        )
    if not _APPROVAL_TOKEN.match(approval_token):
        raise GovernanceBlock(
            f"Malformed calibration promotion approval token for {regime.regime_id}. "
            "Expected APPROVE_V3_CALIBRATION_PROMOTION::<RULING_ID>."
        )
    return {
        "regime_id": regime.regime_id,
        "approval_token": approval_token,
        "promoted_values": dict(regime.values),
        "note": (
            "Promotion authorized. Canonical config is still written by a human-reviewed "
            "change, not by this harness."
        ),
        "writes_canonical_config": False,
    }


def calibration_status(config_calibration_values: dict[str, Any]) -> dict[str, Any]:
    """Report calibration readiness without asserting any value is approved."""
    unresolved = [f for f in CALIBRATION_FIELDS if config_calibration_values.get(f) is None]
    return {
        "unresolved_fields": unresolved,
        "all_canonical_values_null": len(unresolved) == len(CALIBRATION_FIELDS),
        "recorded_legacy_margin_sd": RECORDED_LEGACY_MARGIN_SD,
        "legacy_margin_sd_band": list(LEGACY_MARGIN_SD_BAND),
        "legacy_margin_sd_within_band": (
            LEGACY_MARGIN_SD_BAND[0] <= RECORDED_LEGACY_MARGIN_SD <= LEGACY_MARGIN_SD_BAND[1]
        ),
        "legacy_margin_sd_approved": False,
        "open_item": "ENG-CAL-MARGIN",
        "disposition": "CALIBRATION_EXPERIMENT_REQUIRED",
    }
