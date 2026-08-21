"""Versioned data contract consumed by the C2 Baxter Rating RMSE harness.

The harness never reaches for a dataset by a path it invented. It reads a
contract document that a producing lane (C1) fills in, and every location it
touches comes from that document, resolved relative to the document itself.

Three states are kept distinct, because collapsing them is how "we have no data"
turns into "we have a number":

``READY_FOR_DATA``
    The contract is well formed but the observation set it points at is not
    mounted. This is the expected state before C1 delivers, and it is *not* an
    error: no metrics are produced and none are implied.
``BLOCKED``
    Something is mounted but is not admissible — a forbidden signal, an
    unreadable format, a split policy that leaks, a missing metric definition.
``READY``
    An admissible observation set is mounted and evaluation may proceed.

The contract also names which Baxter RMSE definition is in force. That name is
required rather than defaulted: a metric that silently picks its own definition
cannot be audited, and the definitions shipped here are operational (DERIVED),
not ruled.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..calibration import (
    BLOCKED_ON_CALIBRATION_DATA,
    CalibrationDataset,
    register_dataset,
)
from ..errors import GovernanceBlock, InputValidationError

#: Contract schema this harness implements. A producing lane must ship a
#: contract whose major version matches; a minor bump is additive and accepted.
CONTRACT_SCHEMA_VERSION = "1.0.0"
CONTRACT_SUPPORTED_MAJOR = 1

READY = "READY"
READY_FOR_DATA = "READY_FOR_DATA"
BLOCKED = "BLOCKED"

#: Split policies the harness will honour. Every one of them is deterministic
#: and time-respecting.
SUPPORTED_SPLIT_MODES = ("column", "temporal_week", "temporal_season")

#: Split policies refused outright. A random or hashed split of a weekly
#: recursive rating model trains on the future and calls the result
#: out-of-sample, which is exactly the error the holdout exists to prevent.
REFUSED_SPLIT_MODES = ("random", "hash", "shuffle", "stratified", "kfold")


@dataclass(frozen=True)
class BaxterRmseDefinition:
    """One named, written-down way to compute the primary criterion.

    ``governance_status`` is deliberately not "approved". Ruling R2-CAL-OBJECTIVE
    names *Baxter Rating RMSE* as the primary criterion but does not state its
    formula, so the formula below is an operational definition proposed by this
    harness. It is admissible for experimentation and is not admissible as
    promotion evidence until a ruling adopts it.
    """

    definition_id: str
    description: str
    provenance: str = "DERIVED"
    governance_status: str = "OPERATIONAL_DEFINITION_NOT_YET_RULED"

    def as_dict(self) -> dict[str, Any]:
        return {
            "definition_id": self.definition_id,
            "description": self.description,
            "provenance": self.provenance,
            "governance_status": self.governance_status,
        }


BAXTER_MARGIN_PREDICTION_RMSE_V1 = BaxterRmseDefinition(
    definition_id="BAXTER_MARGIN_PREDICTION_RMSE_V1",
    description=(
        "Root mean squared error, over scored out-of-sample observations, of "
        "(rating[team] - rating[opponent] + venue home-field term) against the "
        "observed team-relative final margin, where the ratings are the Baxter "
        "rating state produced by the candidate regime from strictly prior weeks."
    ),
)

BAXTER_RMSE_DEFINITIONS: dict[str, BaxterRmseDefinition] = {
    BAXTER_MARGIN_PREDICTION_RMSE_V1.definition_id: BAXTER_MARGIN_PREDICTION_RMSE_V1
}

#: The contract may name this instead of a literal number, so the harness reads
#: home-field advantage from governed V3 configuration rather than carrying its
#: own copy of a governed value.
HFA_SOURCE_V3_CONFIG = "V3_CONFIG_HFA_BASELINE_POINTS"
HFA_SOURCE_LITERAL = "CONTRACT_LITERAL"


@dataclass(frozen=True)
class BaxterDataContract:
    """A parsed contract document. Locations are resolved, nothing is fetched."""

    contract_id: str
    contract_version: str
    produced_by: str
    consumed_by: str
    document_path: Path
    observations_path: Path | None
    observations_format: str | None
    dataset_id: str | None
    declared_sha256: str | None
    split_policy: dict[str, Any]
    metric_definition_id: str
    hfa_points: float | None
    hfa_source: str
    witness_paths: dict[str, Path | None] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "contract_schema_version": CONTRACT_SCHEMA_VERSION,
            "produced_by": self.produced_by,
            "consumed_by": self.consumed_by,
            "document_path": str(self.document_path),
            "observations_path": (
                None if self.observations_path is None else str(self.observations_path)
            ),
            "observations_format": self.observations_format,
            "dataset_id": self.dataset_id,
            "declared_sha256": self.declared_sha256,
            "split_policy": dict(self.split_policy),
            "metric_definition_id": self.metric_definition_id,
            "hfa_points": self.hfa_points,
            "hfa_source": self.hfa_source,
            "witnesses": {
                name: (None if path is None else str(path))
                for name, path in sorted(self.witness_paths.items())
            },
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ContractResolution:
    """What the harness may actually do, given the contract as it stands."""

    status: str
    contract: BaxterDataContract
    dataset: CalibrationDataset | None
    metric_definition: BaxterRmseDefinition
    hfa_points: float | None
    reasons: tuple[str, ...] = ()
    witnesses: dict[str, str] = field(default_factory=dict)

    @property
    def is_ready(self) -> bool:
        return self.status == READY

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "contract": self.contract.as_dict(),
            "dataset": (
                None
                if self.dataset is None
                else {
                    "dataset_id": self.dataset.dataset_id,
                    "path": str(self.dataset.path),
                    "sha256": self.dataset.sha256,
                    "rows": self.dataset.rows,
                    "columns": list(self.dataset.columns),
                }
            ),
            "metric_definition": self.metric_definition.as_dict(),
            "hfa_points": self.hfa_points,
            "reasons": list(self.reasons),
            "witnesses": dict(sorted(self.witnesses.items())),
        }


def _major(version: str) -> int:
    head = str(version).split(".")[0].strip()
    if not head.isdigit():
        raise InputValidationError(
            f"Contract version {version!r} is not a dotted numeric version."
        )
    return int(head)


def _optional_path(base: Path, value: Any, label: str) -> Path | None:
    """Resolve a declared location relative to the contract document.

    Returns ``None`` when the contract has not been filled in yet. It never
    substitutes a default location: an unfilled slot means no data, not a guess
    at where the data would have been.
    """
    if value in (None, "", False):
        return None
    if not isinstance(value, str):
        raise InputValidationError(f"Contract field {label} must be a string path or null.")
    candidate = Path(value)
    return candidate if candidate.is_absolute() else (base / candidate).resolve()


def _validate_split_policy(policy: Any) -> dict[str, Any]:
    if not isinstance(policy, dict):
        raise InputValidationError("Contract split_policy must be an object.")
    mode = str(policy.get("mode", "")).strip().lower()
    if mode in REFUSED_SPLIT_MODES:
        raise GovernanceBlock(
            f"Split policy mode {mode!r} is refused. A weekly recursive rating model split "
            "at random trains on weeks that follow the ones it is scored on; the resulting "
            "number is not out-of-sample. Use one of "
            f"{list(SUPPORTED_SPLIT_MODES)}."
        )
    if mode not in SUPPORTED_SPLIT_MODES:
        raise InputValidationError(
            f"Contract split_policy mode {mode!r} is not supported; expected one of "
            f"{list(SUPPORTED_SPLIT_MODES)}."
        )
    resolved = dict(policy)
    resolved["mode"] = mode
    if mode == "temporal_week":
        for key in ("training_through", "validation_through"):
            bound = resolved.get(key)
            if not isinstance(bound, dict) or "season" not in bound or "week" not in bound:
                raise InputValidationError(
                    f"Split policy temporal_week requires {key} as "
                    '{"season": <int>, "week": <int>}.'
                )
            resolved[key] = {"season": int(bound["season"]), "week": int(bound["week"])}
        if (resolved["training_through"]["season"], resolved["training_through"]["week"]) >= (
            resolved["validation_through"]["season"],
            resolved["validation_through"]["week"],
        ):
            raise InputValidationError(
                "Split policy temporal_week requires training_through to precede "
                "validation_through."
            )
    if mode == "temporal_season":
        buckets = {}
        for key in ("training_seasons", "validation_seasons", "holdout_seasons"):
            seasons = resolved.get(key) or []
            if not isinstance(seasons, list) or not all(
                isinstance(s, (int, str)) for s in seasons
            ):
                raise InputValidationError(
                    f"Split policy temporal_season field {key} must be a list of seasons."
                )
            buckets[key] = [int(s) for s in seasons]
            resolved[key] = buckets[key]
        overlap = sorted(
            set(buckets["training_seasons"]) & set(buckets["validation_seasons"])
            | set(buckets["training_seasons"]) & set(buckets["holdout_seasons"])
            | set(buckets["validation_seasons"]) & set(buckets["holdout_seasons"])
        )
        if overlap:
            raise GovernanceBlock(
                f"Split policy temporal_season assigns seasons {overlap} to more than one split."
            )
    return resolved


def load_contract(path: str | Path) -> BaxterDataContract:
    """Parse a contract document. Does not touch the data it points at."""
    document = Path(path).resolve()
    if not document.exists():
        raise GovernanceBlock(
            f"Baxter harness data contract not found at {document}. The harness reads every "
            "location from a contract document and has no built-in dataset location."
        )
    raw = json.loads(document.read_text(encoding="utf-8"))

    version = str(raw.get("contract_version", "")).strip()
    if not version:
        raise InputValidationError("Contract document is missing contract_version.")
    if _major(version) != CONTRACT_SUPPORTED_MAJOR:
        raise GovernanceBlock(
            f"Contract version {version} is incompatible with harness contract schema "
            f"{CONTRACT_SCHEMA_VERSION}. A major version change is a renegotiation, not an upgrade."
        )

    observations = raw.get("observations") or {}
    if not isinstance(observations, dict):
        raise InputValidationError("Contract field observations must be an object.")

    base = document.parent
    metric = raw.get("metric") or {}
    definition_id = str(metric.get("baxter_rmse_definition_id", "")).strip()
    if not definition_id:
        raise GovernanceBlock(
            "Contract does not name a baxter_rmse_definition_id. The primary criterion must "
            "state which written definition it is computing."
        )

    hfa = raw.get("hfa") or {}
    hfa_source = str(hfa.get("source", "")).strip() or HFA_SOURCE_V3_CONFIG
    if hfa_source not in (HFA_SOURCE_V3_CONFIG, HFA_SOURCE_LITERAL):
        raise InputValidationError(
            f"Contract hfa.source {hfa_source!r} must be one of "
            f"{[HFA_SOURCE_V3_CONFIG, HFA_SOURCE_LITERAL]}."
        )
    hfa_points = hfa.get("points")
    if hfa_points is not None:
        hfa_points = float(hfa_points)
        if hfa_source != HFA_SOURCE_LITERAL:
            raise InputValidationError(
                "Contract hfa.points is set but hfa.source does not declare it as a literal. "
                "A governed value must be read from governed configuration, not restated."
            )

    witnesses_raw = raw.get("witnesses") or {}
    if not isinstance(witnesses_raw, dict):
        raise InputValidationError("Contract field witnesses must be an object.")
    witness_paths = {
        str(name): _optional_path(base, value, f"witnesses.{name}")
        for name, value in witnesses_raw.items()
    }

    return BaxterDataContract(
        contract_id=str(raw.get("contract_id", "")).strip() or "UNNAMED_CONTRACT",
        contract_version=version,
        produced_by=str(raw.get("produced_by", "")).strip() or "UNDECLARED",
        consumed_by=str(raw.get("consumed_by", "")).strip() or "UNDECLARED",
        document_path=document,
        observations_path=_optional_path(base, observations.get("path"), "observations.path"),
        observations_format=(
            None
            if observations.get("format") in (None, "")
            else str(observations["format"]).strip().lower()
        ),
        dataset_id=(
            None if observations.get("dataset_id") in (None, "") else str(observations["dataset_id"])
        ),
        declared_sha256=(
            None if observations.get("sha256") in (None, "") else str(observations["sha256"]).lower()
        ),
        split_policy=_validate_split_policy(raw.get("split_policy") or {"mode": "column"}),
        metric_definition_id=definition_id,
        hfa_points=hfa_points,
        hfa_source=hfa_source,
        witness_paths=witness_paths,
        notes=tuple(str(n) for n in raw.get("notes", [])),
    )


def resolve_contract(
    contract: BaxterDataContract, *, v3_hfa_baseline_points: float | None = None
) -> ContractResolution:
    """Decide what the contract permits right now.

    ``v3_hfa_baseline_points`` is supplied by the caller from governed V3
    configuration when the contract defers to it, so this module never carries
    its own copy of a governed number.
    """
    definition = BAXTER_RMSE_DEFINITIONS.get(contract.metric_definition_id)
    if definition is None:
        raise GovernanceBlock(
            f"Contract names Baxter RMSE definition {contract.metric_definition_id!r}, which this "
            f"harness does not implement. Known definitions: {sorted(BAXTER_RMSE_DEFINITIONS)}."
        )

    witnesses = {
        name: ("MOUNTED" if path is not None and path.exists() else "NOT_MOUNTED")
        for name, path in contract.witness_paths.items()
    }

    reasons: list[str] = []

    if contract.hfa_source == HFA_SOURCE_LITERAL:
        hfa_points = contract.hfa_points
    else:
        hfa_points = v3_hfa_baseline_points
    if hfa_points is None:
        reasons.append(
            "home_field_points_unresolved: contract defers to "
            f"{contract.hfa_source} and no value was supplied"
        )

    if contract.observations_path is None:
        reasons.insert(
            0,
            f"{BLOCKED_ON_CALIBRATION_DATA}: contract declares no observation set path "
            f"(produced_by={contract.produced_by})",
        )
        return ContractResolution(
            status=READY_FOR_DATA,
            contract=contract,
            dataset=None,
            metric_definition=definition,
            hfa_points=hfa_points,
            reasons=tuple(reasons),
            witnesses=witnesses,
        )

    if not contract.observations_path.exists():
        reasons.insert(
            0,
            f"{BLOCKED_ON_CALIBRATION_DATA}: declared observation set is not mounted at "
            f"{contract.observations_path}",
        )
        return ContractResolution(
            status=READY_FOR_DATA,
            contract=contract,
            dataset=None,
            metric_definition=definition,
            hfa_points=hfa_points,
            reasons=tuple(reasons),
            witnesses=witnesses,
        )

    dataset = register_dataset(
        contract.observations_path,
        contract.dataset_id or f"{contract.contract_id}-OBSERVATIONS",
        fmt=contract.observations_format,
    )

    if contract.declared_sha256 and contract.declared_sha256 != dataset.sha256:
        raise GovernanceBlock(
            f"Observation set at {contract.observations_path} hashes to {dataset.sha256}, but the "
            f"contract declares {contract.declared_sha256}. The mounted file is not the file the "
            "contract was written against."
        )

    status = READY if hfa_points is not None else BLOCKED
    return ContractResolution(
        status=status,
        contract=contract,
        dataset=dataset,
        metric_definition=definition,
        hfa_points=hfa_points,
        reasons=tuple(reasons),
        witnesses=witnesses,
    )
