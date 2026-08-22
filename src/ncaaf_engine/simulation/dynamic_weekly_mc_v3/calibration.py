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

Lane C hardening adds four more, each closing a path by which an ungoverned
number could have reached a promotion record looking like evidence:

* The governed ranking is :func:`rank_experiments_governed`, which requires the
  criterion named in ruling R2-CAL-OBJECTIVE. :func:`rank_experiments` still
  honours any named objective, because supporting diagnostics are reported that
  way, but a *named* objective is not automatically a *governed* one.
* An :class:`ExperimentRecord` declares the split its metrics came from, so
  "holdout" is a property of the run rather than an assertion made later by
  whoever writes the promotion request.
* :func:`bind_promotion_evidence` records whether a promotion cites a measured
  experiment against registered bytes, or a hand-written dictionary. The R2 gate
  accepts both; only one of them is a measurement, and the record now says which.
  Under ruling R6-CAL-TEMPORAL-ORDER the measured path additionally requires the
  admission receipt :func:`load_admitted_observations` issues for those exact
  bytes, so the executable chain terminates as: registered source -> digest
  verified -> rows temporally admitted -> partition proven forward-only ->
  calibration result -> promotion evidence binding. The hand-written path
  survives unchanged and stays explicitly not promotion-eligible.
* :func:`require_temporal_split_integrity` proves the partition is ordered in
  time. :func:`require_split_separation` proves only disjointness, and a randomly
  assigned holdout of sequential weekly ratings is not out-of-sample at all.

Ruling R6-CAL-TEMPORAL-ORDER adds one more, and it is a widening rather than a
tightening, so it is worth being precise about what it does not widen. The
governed historical corpus holds no authentic kickoff time for a large part of
its span. ``event_time`` therefore stays null for those observations instead of
being filled with a synthetic noon, and the causal-order guarantee it carried is
replaced by provenance-bound ordering evidence at a declared, weaker
granularity. ``event_time`` is not made globally optional, nothing may be
admitted on a basis stronger than its source supports, and a governed source
sequence is never serialized as a kickoff instant. See
:func:`admit_temporal_order` and
:func:`require_governed_temporal_split_integrity`.

The ingestion contract those splits and datasets must satisfy lives in
:mod:`.calibration_contract`. No observation set currently satisfies it.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Iterable

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
    #: The format registration actually parsed. Carried so the admission gate
    #: reads the bytes exactly as registration did: `fmt` may override the file
    #: suffix, and re-deriving the format from the suffix later would read a
    #: tab-separated file as one giant column.
    fmt: str = "csv"


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
    #: Which partition produced ``metrics``. A record that does not say cannot be
    #: cited as holdout evidence, because "holdout" would then be the claim of
    #: whoever writes the promotion request rather than a property of the run.
    split: str | None = None
    status: str = "EXPERIMENTAL_RESULT_NOT_PROMOTED"

    def __post_init__(self) -> None:
        if self.split is not None and self.split.strip().lower() not in DATA_SPLITS:
            raise InputValidationError(
                f"Experiment {self.experiment_id} declares split {self.split!r}; "
                f"expected one of {list(DATA_SPLITS)}"
            )

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


SUPPORTED_DATASET_FORMATS = ("csv", "tsv", "json")

#: Governed allowlist. A calibration observation set may carry these columns and
#: nothing else; anything unrecognised is refused rather than ignored.
#:
#: The four ``temporal_order_*`` columns were admitted by ruling
#: R6-CAL-TEMPORAL-ORDER, which requires them of any observation admitted without
#: an authentic kickoff timestamp. They are here because a ruling put them here,
#: not because a fit needed them: the four fields under
#: ``calibration_contract.FIELDS_REQUIRING_ADMISSION_RULING`` are still awaiting
#: their own ruling and are still not admitted.
CALIBRATION_OBSERVATION_COLUMNS = (
    "game_id",
    "season",
    "week",
    "event_time",
    "temporal_order_basis",
    "temporal_order_key",
    "temporal_order_source",
    "temporal_order_source_sha256",
    "team",
    "opponent",
    "venue",
    "pregame_team_rating",
    "pregame_opponent_rating",
    "expected_margin",
    "actual_margin",
    "game_result",
    "prior_rating_state",
    "subsequent_outcomes",
    "source_provenance",
    "observed_at",
    "recorded_at",
    "model_version",
    "configuration_version",
    "split",
)

#: Minimum columns without which no experiment can be scored.
REQUIRED_OBSERVATION_COLUMNS = (
    "game_id",
    "season",
    "week",
    "team",
    "opponent",
    "expected_margin",
    "actual_margin",
    "observed_at",
    "recorded_at",
)

#: Substrings that identify a betting-flow or injury signal under any spelling.
#: Matched as substrings precisely because an exact-name denylist is trivially
#: sidestepped by renaming ``public_money_pct`` to ``public_money_percentage``.
FORBIDDEN_SIGNAL_PATTERNS = (
    "public_money",
    "publicmoney",
    "public_bet",
    "publicbet",
    "bet_pct",
    "betpct",
    "bet_percent",
    "betting_percent",
    "handle_pct",
    "handle_percent",
    "ticket_pct",
    "ticket_percent",
    "money_pct",
    "money_percent",
    "wager",
    "sharp_money",
    "steam",
    "injury",
    "injuries",
)

BLOCKED_ON_CALIBRATION_DATA = "BLOCKED_ON_CALIBRATION_DATA"


def _forbidden_columns(columns: tuple[str, ...]) -> list[str]:
    out = []
    for column in columns:
        flat = column.strip().lower().replace("-", "_").replace(" ", "_")
        if flat in FORBIDDEN_DATASET_SIGNALS or any(
            pattern in flat for pattern in FORBIDDEN_SIGNAL_PATTERNS
        ):
            out.append(column)
    return sorted(set(out))


def _decode(path: Path, dataset_id: str) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} at {path} is not valid UTF-8 ({exc.reason}). "
            "A dataset whose encoding cannot be established cannot be audited."
        ) from None


def _columns_from_csv(text: str, delimiter: str) -> tuple[str, ...]:
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        header = next(reader)
    except StopIteration:
        return ()
    return tuple(c.strip() for c in header if c.strip())


def _delimited_records(
    text: str, delimiter: str, dataset_id: str, columns: tuple[str, ...]
) -> int:
    """Count and shape-check delimited records, rather than counting text lines.

    Line counting is wrong in a way that matters: a quoted field containing a
    newline is one record spread over two lines, so a line count silently
    overstates the size of a governed dataset. ``rows`` is recorded as provenance
    and cited in experiment records, so it has to be the record count.

    Ragged rows are refused here for the same reason an unknown column is refused
    at registration. A short row is not a row with blanks at the end; it is a row
    whose fields no longer line up with the header, and reading ``actual_margin``
    out of it returns whatever happens to sit at that index.
    """
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter)
    try:
        next(reader)
    except StopIteration:
        return 0
    width = len(columns)
    count = 0
    ragged: list[str] = []
    for lineno, record in enumerate(reader, start=2):
        if not record or all(not cell.strip() for cell in record):
            continue
        count += 1
        if len(record) != width:
            ragged.append(f"line {lineno}: {len(record)} fields, header declares {width}")
    if ragged:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} has rows that do not match its header "
            f"width: {ragged[:5]}. A ragged observation row cannot be read field-wise "
            "and is refused rather than padded."
        )
    return count


def _columns_from_json(text: str, dataset_id: str) -> tuple[tuple[str, ...], int]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} declares format json but does not parse: {exc.msg}"
        ) from None
    rows = payload.get("observations") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} must be a JSON list of observation objects, or an "
            "object with an 'observations' list."
        )
    columns: list[str] = []
    for row in rows:
        for key in row:
            if key not in columns:
                columns.append(key)
    return tuple(columns), len(rows)


def register_dataset(
    path: Path, dataset_id: str, *, fmt: str | None = None
) -> CalibrationDataset:
    """Register a historical calibration dataset, format-aware and fail-closed.

    Format is taken from ``fmt`` when given, otherwise from the file suffix. An
    unknown format is refused rather than guessed at, because guessing is how a
    tab-separated file gets read as one giant column and a forbidden signal
    hides inside it.

    This is **registration only**. It establishes identity, digest, record count,
    shape and column admissibility, and it deliberately reads no observation
    values: a registered dataset is not an admitted one, and nothing here proves
    that a single row carries real chronology. Executable use goes through
    :func:`load_admitted_observations`, which is the only door, and
    :func:`require_admitted_observations` refuses a `CalibrationDataset` handed
    to a consumer in place of an admitted set.
    """
    if not path.exists():
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} not found at {path}. "
            f"{BLOCKED_ON_CALIBRATION_DATA}: no historical observation set is mounted."
        )

    declared = (fmt or path.suffix.lstrip(".")).strip().lower()
    if declared not in SUPPORTED_DATASET_FORMATS:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} has unsupported format {declared!r}. "
            f"Supported formats are {list(SUPPORTED_DATASET_FORMATS)}; an unrecognised "
            "format is refused rather than parsed by guess."
        )

    data = path.read_bytes()
    text = _decode(path, dataset_id)

    if declared in ("csv", "tsv"):
        delimiter = "," if declared == "csv" else "\t"
        columns = _columns_from_csv(text, delimiter)
        rows = _delimited_records(text, delimiter, dataset_id, columns) if columns else 0
    else:
        columns, rows = _columns_from_json(text, dataset_id)

    if not columns:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} declares format {declared} but exposes no columns."
        )

    duplicated = sorted(
        {c for c in (x.strip().lower() for x in columns)
         if [y.strip().lower() for y in columns].count(c) > 1}
    )
    if duplicated:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} declares duplicate columns: {duplicated}. "
            "Which copy a reader takes is positional, so a duplicated observation column "
            "is refused rather than resolved by convention."
        )

    offending = _forbidden_columns(columns)
    if offending:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} contains non-admissible predictive signals: "
            f"{offending}. Public money creates flow, not belief; injuries remain deferred."
        )

    unknown = sorted(
        c for c in columns
        if c.strip().lower() not in {a.lower() for a in CALIBRATION_OBSERVATION_COLUMNS}
    )
    if unknown:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} carries columns outside the governed "
            f"observation allowlist: {unknown}. Extend the allowlist by ruling; do not "
            "admit an unrecognised signal by silence."
        )

    lowered = {x.strip().lower() for x in columns}

    carried = [c for c in TEMPORAL_ORDER_PROVENANCE_COLUMNS if c in lowered]
    if carried and len(carried) != len(TEMPORAL_ORDER_PROVENANCE_COLUMNS):
        absent = [c for c in TEMPORAL_ORDER_PROVENANCE_COLUMNS if c not in lowered]
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} carries partial governed temporal "
            f"provenance {carried} and is missing {absent}. Under ruling "
            f"{TEMPORAL_ORDER_RULING} an observation admitted without an authentic "
            f"event_time must carry all of {list(TEMPORAL_ORDER_PROVENANCE_COLUMNS)}; a "
            "basis with no re-checkable source is an assertion, not evidence."
        )

    missing = sorted(
        c for c in REQUIRED_OBSERVATION_COLUMNS
        if c not in lowered
    )
    if missing:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} is missing required observation columns: "
            f"{missing}. {BLOCKED_ON_CALIBRATION_DATA}."
        )

    if rows < 1:
        raise GovernanceBlock(
            f"Calibration dataset {dataset_id} carries a conforming header and zero "
            f"observations. {BLOCKED_ON_CALIBRATION_DATA}: a header is a schema, not "
            "evidence, and an empty set must not register as a mounted dataset."
        )

    return CalibrationDataset(
        dataset_id=dataset_id,
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        rows=rows,
        columns=columns,
        fmt=declared,
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


# --- R2 calibration governance ------------------------------------------------
#
# Ruling R2-CAL-OBJECTIVE names one primary criterion and two witnesses, and it
# is deliberate that they are not combined. A weighted blend of Baxter, Colley
# and SRS is the Body-of-Work Index recorded PROPOSAL ONLY / NOT ADOPTED in
# 18_ACC_POLICY_REFERENCE ACC-EXT-12.

from .rulings import R2_CALIBRATION  # noqa: E402

#: FACT — ruling R2-CAL-OBJECTIVE.
PRIMARY_CALIBRATION_METRIC = "out_of_sample_baxter_rating_rmse"
PRIMARY_CALIBRATION_DIRECTION = "minimize"

#: Reported independently, never blended into the primary criterion.
INDEPENDENT_WITNESSES = ("colley_matrix", "srs")

#: Reported where useful, alongside the primary criterion.
SUPPORTING_DIAGNOSTICS = (
    "brier_score",
    "log_loss",
    "probability_calibration",
    "rating_stability",
    "blowout_sensitivity",
    "week_to_week_movement_distribution",
)

DATA_SPLITS = ("training", "validation", "holdout")

#: The two authorities under which a promotion may be recorded.
PROMOTION_AUTHORITY_MATHEMATICAL = "GOVERNED_CALIBRATION_EVIDENCE"
PROMOTION_AUTHORITY_CHAIRMAN = "EXPLICIT_CHAIRMAN_JUSTIFICATION"
PROMOTION_AUTHORITIES = (PROMOTION_AUTHORITY_MATHEMATICAL, PROMOTION_AUTHORITY_CHAIRMAN)


PRIMARY_OBJECTIVE = EvaluationObjective(
    objective_id="R2-CAL-PRIMARY",
    metric=PRIMARY_CALIBRATION_METRIC,
    direction=PRIMARY_CALIBRATION_DIRECTION,
    description=(
        "Minimise out-of-sample Baxter Rating RMSE. Colley Matrix and SRS are reported "
        "independently as witnesses and are never blended into this criterion."
    ),
)


def require_primary_objective(objective: EvaluationObjective | None) -> EvaluationObjective:
    """Fail closed unless the objective is the governed primary criterion."""
    if objective is None:
        raise GovernanceBlock(
            "No evaluation objective supplied. Ruling "
            f"{R2_CALIBRATION.convergence_id} names {PRIMARY_CALIBRATION_METRIC} "
            f"({PRIMARY_CALIBRATION_DIRECTION}) as the primary criterion."
        )
    if objective.metric != PRIMARY_CALIBRATION_METRIC:
        raise GovernanceBlock(
            f"Objective metric {objective.metric!r} is not the governed primary calibration "
            f"criterion {PRIMARY_CALIBRATION_METRIC!r}."
        )
    if objective.direction != PRIMARY_CALIBRATION_DIRECTION:
        raise GovernanceBlock(
            f"Primary calibration criterion must be {PRIMARY_CALIBRATION_DIRECTION}d."
        )
    return objective


def reject_witness_composite(components: Iterable[str]) -> None:
    """Refuse any weighted composite of the primary criterion and its witnesses."""
    named = {c.strip().lower() for c in components}
    family = {"baxter", "baxter_rating", PRIMARY_CALIBRATION_METRIC, *INDEPENDENT_WITNESSES}
    overlap = sorted(n for n in named if n in family or n.startswith("baxter"))
    if len(overlap) > 1:
        raise GovernanceBlock(
            f"A weighted composite of {overlap} is not authorised. Ruling "
            f"{R2_CALIBRATION.convergence_id} keeps Baxter Rating RMSE primary and reports "
            "Colley and SRS independently; ACC-EXT-12 records the blend as NOT ADOPTED."
        )


def require_split_separation(assignments: dict[str, str]) -> dict[str, list[str]]:
    """Confirm every observation lands in exactly one of the three splits."""
    buckets: dict[str, list[str]] = {s: [] for s in DATA_SPLITS}
    for game_id, split in sorted(assignments.items()):
        key = split.strip().lower()
        if key not in buckets:
            raise InputValidationError(
                f"Observation {game_id} has split {split!r}; expected one of {list(DATA_SPLITS)}"
            )
        buckets[key].append(game_id)
    overlaps = sorted(
        {g for a in DATA_SPLITS for b in DATA_SPLITS if a < b
         for g in set(buckets[a]) & set(buckets[b])}
    )
    if overlaps:
        raise GovernanceBlock(f"Observations appear in more than one split: {overlaps}")
    return buckets


def promote_regime_r2(
    regime: CandidateRegime,
    *,
    authority: str | None = None,
    approval_token: str | None = None,
    justification: str = "",
    evidence: dict[str, Any] | None = None,
    ranked_first: bool = False,
    experiment: ExperimentRecord | None = None,
    dataset: CalibrationDataset | None = None,
    observations: Any = None,
) -> dict[str, Any]:
    """Promotion gate under ruling R2-CAL-OBJECTIVE.

    Two authorities are recognised and the record must name which was used. Both
    still require the human approval token: naming an authority is not the same
    as being one, and a top ranking is neither.

    ``observations`` is passed through to :func:`bind_promotion_evidence`. A
    promotion that cites an experiment and a dataset must carry the admission
    receipt for those bytes; without it the binding refuses, because a
    calibration result whose observations never passed the successor temporal
    contract is not promotion-eligible evidence.
    """
    if authority is None:
        raise GovernanceBlock(
            f"Regime {regime.regime_id} cannot be promoted: no promotion authority named. "
            f"Ruling {R2_CALIBRATION.convergence_id} recognises {list(PROMOTION_AUTHORITIES)}."
            + (" A top ranking is not an authority." if ranked_first else "")
        )
    if authority not in PROMOTION_AUTHORITIES:
        raise GovernanceBlock(
            f"Unknown promotion authority {authority!r}; expected one of "
            f"{list(PROMOTION_AUTHORITIES)}."
        )
    if authority == PROMOTION_AUTHORITY_MATHEMATICAL:
        supplied = evidence or {}
        if PRIMARY_CALIBRATION_METRIC not in supplied:
            raise GovernanceBlock(
                f"Promotion of {regime.regime_id} under {PROMOTION_AUTHORITY_MATHEMATICAL} "
                f"requires governed {PRIMARY_CALIBRATION_METRIC} evidence."
            )
        if supplied.get("split") != "holdout":
            raise GovernanceBlock(
                "Mathematical promotion evidence must come from the holdout split; "
                f"got {supplied.get('split')!r}."
            )
    if authority == PROMOTION_AUTHORITY_CHAIRMAN and not justification.strip():
        raise GovernanceBlock(
            f"Promotion of {regime.regime_id} under {PROMOTION_AUTHORITY_CHAIRMAN} requires an "
            "explicit written justification."
        )

    binding = bind_promotion_evidence(
        regime,
        evidence=evidence,
        experiment=experiment,
        dataset=dataset,
        observations=observations,
    )

    base = promote_regime(regime, approval_token=approval_token, ranked_first=ranked_first)
    base.update(
        {
            "ruling": R2_CALIBRATION.convergence_id,
            "promotion_authority": authority,
            "justification": justification,
            "evidence": dict(evidence or {}),
            "primary_metric": PRIMARY_CALIBRATION_METRIC,
            "witnesses_reported_independently": list(INDEPENDENT_WITNESSES),
            **binding,
        }
    )
    return base


#: Stamped on a promotion record whose evidence is a hand-written dict rather than
#: a metric read back off a real experiment against a registered dataset.
EVIDENCE_UNBOUND = "EVIDENCE_UNBOUND_NOT_SUFFICIENT_FOR_CANONICAL_WRITE"
EVIDENCE_BOUND = "EVIDENCE_BOUND_TO_REGISTERED_DATASET_AND_EXPERIMENT"

#: Keys a caller may not put in an evidence payload. Admission is established by
#: the receipt :func:`load_admitted_observations` issues and by nothing else; a
#: dict key spelling the same word is an assertion, and letting one through would
#: rebuild the bypass the receipt exists to close.
ADMISSION_ASSERTION_KEYS = (
    "observations_admitted",
    "admitted_observation_count",
    "admission_gate",
    "temporally_admitted",
    "rows_admitted",
)


def _require_digest_continuity(
    dataset: CalibrationDataset, admitted: AdmittedObservationSet
) -> str:
    """Confirm the admitted bytes are still the bytes on disk.

    An admission receipt is a statement about a specific sequence of bytes. If
    those bytes have since changed, the receipt describes a file that no longer
    exists, and reusing it would attach a proof of admission to rows nobody
    admitted.
    """
    try:
        current = hashlib.sha256(dataset.path.read_bytes()).hexdigest()
    except OSError as exc:
        raise GovernanceBlock(
            f"Calibration dataset {dataset.dataset_id} cannot be re-read at "
            f"{dataset.path} to confirm its admitted bytes ({exc.strerror}). An "
            "admission receipt that cannot be re-checked is refused."
        ) from None
    if current != admitted.dataset_sha256:
        raise GovernanceBlock(
            f"Calibration dataset {dataset.dataset_id} now hashes to {current} but its "
            f"admission receipt was issued for {admitted.dataset_sha256}. The bytes "
            "changed after admission, so the receipt is stale and proves nothing about "
            "the rows that are there now."
        )
    return current


def bind_promotion_evidence(
    regime: CandidateRegime,
    *,
    evidence: dict[str, Any] | None,
    experiment: ExperimentRecord | None,
    dataset: CalibrationDataset | None,
    observations: Any = None,
) -> dict[str, Any]:
    """Tie promotion evidence to a real experiment and a registered dataset.

    Ruling R2-CAL-OBJECTIVE requires holdout evidence but does not itself say how
    a reviewer distinguishes a measured holdout number from a typed one. A bare
    ``{"out_of_sample_baxter_rating_rmse": 0.0001, "split": "holdout"}`` satisfies
    the wording of the gate while containing no measurement at all.

    Rather than tighten the ruling own gate beyond what was ruled, this records
    which of the two it was. An unbound promotion still carries its authority and
    its token, and it also carries :data:`EVIDENCE_UNBOUND` in its own provenance,
    so the weaker path cannot be mistaken for the stronger one later.

    When a record and dataset *are* supplied, disagreement is fatal: a promotion
    citing an experiment whose numbers differ from the cited evidence is worse
    than one citing nothing, because it looks checked.

    ``observations`` is where the chain terminates, and it is a gate rather than a
    stamp. A registered dataset proves identity, digest and shape; it does not
    prove that a single row carried real chronology, because registration reads no
    values. So a *bound* result — the promotion-eligible one — requires the
    :class:`AdmittedObservationSet` that :func:`load_admitted_observations` issued
    for these exact bytes. Without it this refuses rather than returning a bound
    record with a caveat attached, because a caveat inside a promotion-eligible
    record is read by nobody at the moment it matters.

    The unbound path is preserved and stays exactly what it was: a record that
    carries its authority and its token, is stamped
    :data:`EVIDENCE_UNBOUND`, and is explicitly not promotion-eligible. That is
    the only path that survives without an admission receipt, and it cannot be
    mistaken for the other one.
    """
    supplied = dict(evidence or {})
    asserted = sorted(
        k for k in supplied if str(k).strip().lower() in ADMISSION_ASSERTION_KEYS
    )
    if asserted:
        raise GovernanceBlock(
            f"Promotion evidence for {regime.regime_id} asserts {asserted} in its own "
            f"payload. Temporal admission is established by the receipt {ADMISSION_GATE} "
            "issues and by nothing else; a caller-supplied claim that the rows were "
            "admitted is the bypass the receipt exists to close."
        )
    admitted = observations if observations is None else require_admitted_observations(
        observations
    )
    if experiment is None or dataset is None:
        if admitted is not None:
            raise GovernanceBlock(
                f"Promotion of {regime.regime_id} supplies an admission receipt for "
                f"{admitted.dataset_id} but cites no experiment and dataset to bind it "
                "to. A receipt on its own attaches to nothing."
            )
        return {
            "evidence_binding": EVIDENCE_UNBOUND,
            "evidence_bound": False,
            "promotion_eligible": False,
            "bound_experiment_id": None,
            "bound_dataset_sha256": None,
            "observations_admitted": False,
            "admitted_observation_count": 0,
            "admission_gate": None,
        }

    if experiment.regime_id != regime.regime_id:
        raise GovernanceBlock(
            f"Promotion of {regime.regime_id} cites experiment {experiment.experiment_id}, "
            f"which scored regime {experiment.regime_id}."
        )
    if experiment.dataset_id != dataset.dataset_id or experiment.dataset_sha256 != dataset.sha256:
        raise GovernanceBlock(
            f"Experiment {experiment.experiment_id} does not match registered dataset "
            f"{dataset.dataset_id}: the cited bytes are not the scored bytes."
        )
    if (experiment.split or "").strip().lower() != "holdout":
        raise GovernanceBlock(
            f"Experiment {experiment.experiment_id} declares split "
            f"{experiment.split!r}; mathematical promotion evidence must be measured on "
            "the holdout split."
        )
    if PRIMARY_CALIBRATION_METRIC not in experiment.metrics:
        raise GovernanceBlock(
            f"Experiment {experiment.experiment_id} carries no "
            f"{PRIMARY_CALIBRATION_METRIC}; it cannot support a mathematical promotion."
        )
    measured = experiment.metrics[PRIMARY_CALIBRATION_METRIC]
    cited = supplied.get(PRIMARY_CALIBRATION_METRIC)
    if cited is not None and cited != measured:
        raise GovernanceBlock(
            f"Promotion cites {PRIMARY_CALIBRATION_METRIC}={cited} but experiment "
            f"{experiment.experiment_id} measured {measured}."
        )
    if admitted is None:
        raise GovernanceBlock(
            f"Promotion of {regime.regime_id} cites dataset {dataset.dataset_id}, which "
            "is registered but not admitted. Registration establishes identity, digest, "
            "record count and shape and reads no observation values, so it proves "
            "nothing about whether a single row carried real chronology. Bound promotion "
            f"evidence requires the AdmittedObservationSet {ADMISSION_GATE} issues for "
            "these bytes: there is no supported route from a registered source to "
            "promotion evidence that skips temporal admission."
        )
    if (
        admitted.dataset_id != dataset.dataset_id
        or admitted.dataset_sha256 != dataset.sha256
    ):
        raise GovernanceBlock(
            f"Promotion of {regime.regime_id} cites dataset {dataset.dataset_id} "
            f"({dataset.sha256}) but its admitted observations came from "
            f"{admitted.dataset_id} ({admitted.dataset_sha256}). An admission receipt "
            "for other bytes proves nothing about these."
        )
    _require_digest_continuity(dataset, admitted)
    return {
        "evidence_binding": EVIDENCE_BOUND,
        "evidence_bound": True,
        "promotion_eligible": True,
        "bound_experiment_id": experiment.experiment_id,
        "bound_dataset_sha256": dataset.sha256,
        "measured_primary_metric": measured,
        "observations_admitted": True,
        "admitted_observation_count": len(admitted.observations),
        "admission_gate": ADMISSION_GATE,
        "admitted_split_report": dict(admitted.split_report),
    }


def rank_experiments_governed(
    records: list[ExperimentRecord], objective: EvaluationObjective | None
) -> list[ExperimentRecord]:
    """Rank against the governed primary criterion, and nothing else.

    :func:`rank_experiments` will honour any named objective, which is correct for
    reporting a supporting diagnostic. It is not correct for deciding which regime
    is best: an objective can be named, explicit, and still be one somebody chose
    because their own candidate wins under it. This path wires
    :func:`require_primary_objective` into the ranking, so the governed decision
    can only be made against the criterion in ruling R2-CAL-OBJECTIVE.

    Every record must also declare which split produced its metric, and mixed
    splits are refused: a regime scored on training does not compete with one
    scored on holdout.
    """
    require_primary_objective(objective)
    undeclared = [r.experiment_id for r in records if not r.split]
    if undeclared:
        raise GovernanceBlock(
            f"Experiments do not declare which split produced their metric: {undeclared}. "
            "An out-of-sample ranking cannot be assembled from records that do not say "
            "whether they are out of sample."
        )
    splits = {(r.split or "").strip().lower() for r in records}
    if len(splits) > 1:
        raise GovernanceBlock(
            f"Refusing to rank across mixed splits {sorted(splits)}; scores from "
            "different partitions are not comparable."
        )
    return rank_experiments(records, objective)


# =============================================================================
# Governed temporal order — ruling R6-CAL-TEMPORAL-ORDER
# =============================================================================
#
# The governed historical corpus does not carry an authentic kickoff time for
# every observation. The staged calibration evidence census found zero authentic
# time-of-day values: the 2006-2011 packages carry a per-season chronology
# sequence, a week where one was resolved and a game date where one was
# resolved, with a quality flag on each; the modern 2024/2025 walk-forward
# evidence carries a game date, an event order and a global sequence, and its
# undated postseason rows carry only a stage label and a sequence. The
# historical source packages state in terms that chronology was not invented.
#
# There are exactly two responses to that and only one is admissible. Generating
# a noon or midnight kickoff so a row satisfies a schema manufactures the very
# evidence the source declined to invent, and once serialized the fabricated
# instant is indistinguishable from a measured one for every reader downstream.
# So event_time stays null where no timestamp exists, and the causal-order
# guarantee it carried is replaced — not dropped — by provenance-bound ordering
# evidence of a declared, weaker granularity.
#
# Two things this section is careful not to do.
#
# It does not invent a key grammar. The ordering value is a *named-field*
# structure, :class:`TemporalOrderValue`, assembled from separately validated
# source-derived fields and serialized as a self-describing canonical JSON
# object. A positional packed string would have made an implementation
# convenience into a governance rule, and it would have forced a supplier to
# supply fields the source never recorded: the real corpus holds week-ordered
# rows with no date at all, and stage labels ("P1", "PS", "CCG", "Bowl", "R1")
# that no fixed vocabulary of ours anticipates. Labels are carried verbatim as
# provenance and are never parsed for ordering; only a source-supplied ordinal
# orders anything.
#
# It does not compare across granularities it does not have. An ordering proven
# at day or week granularity cannot separate two games inside one day, and a
# governed source sequence orders rows only relative to each other inside one
# named, hashed source. :func:`require_governed_temporal_split_integrity`
# refuses a partition boundary it cannot prove at the granularity actually
# available.

#: Chairman authority for the successor semantics in this section.
TEMPORAL_ORDER_RULING = "R6-CAL-TEMPORAL-ORDER"
TEMPORAL_ORDER_RULING_ID = "V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1"
TEMPORAL_ORDER_APPROVAL_TOKEN = "APPROVE_V3_CALIBRATION_TEMPORAL_ORDER_SUCCESSOR_R1"

BASIS_EXACT_EVENT_TIME = "EXACT_EVENT_TIME"
BASIS_EXACT_GAME_DATE = "EXACT_GAME_DATE"
BASIS_WEEK_STAGE_DATE = "WEEK_STAGE_DATE"
BASIS_GOVERNED_SOURCE_SEQUENCE = "GOVERNED_SOURCE_SEQUENCE"

#: Temporal evidence precedence, strongest first. An observation is admitted on
#: the strongest basis its source actually supports and never on a stronger one.
TEMPORAL_EVIDENCE_PRECEDENCE = (
    BASIS_EXACT_EVENT_TIME,
    BASIS_EXACT_GAME_DATE,
    BASIS_WEEK_STAGE_DATE,
    BASIS_GOVERNED_SOURCE_SEQUENCE,
)

#: Granularity each basis can actually prove. Reported on every resolved order so
#: a downstream reader never has to infer precision from the shape of a value.
TEMPORAL_ORDER_GRANULARITY = {
    BASIS_EXACT_EVENT_TIME: "INSTANT",
    BASIS_EXACT_GAME_DATE: "DAY",
    BASIS_WEEK_STAGE_DATE: "WEEK",
    BASIS_GOVERNED_SOURCE_SEQUENCE: "RELATIVE_SEQUENCE",
}

#: Provenance an observation admitted without event_time must carry. All four or
#: none: three of the four prove nothing a reviewer can re-check.
TEMPORAL_ORDER_PROVENANCE_COLUMNS = (
    "temporal_order_basis",
    "temporal_order_key",
    "temporal_order_source",
    "temporal_order_source_sha256",
)

#: The named fields a temporal ordering value may carry. This is a vocabulary of
#: *field names*, not of values: no stage or week label is enumerated anywhere,
#: because the corpus uses several incompatible label sets and inventing one
#: would be a governance rule we were never given.
TEMPORAL_ORDER_VALUE_FIELDS = (
    "season",
    "game_date",
    "week_ordinal",
    "week_label",
    "stage_label",
    "sequence",
)

#: Ordering domains. Values are comparable to each other only inside one domain;
#: across domains, only a season difference proves an order.
CALENDAR_DOMAIN = "CALENDAR"
SEASON_WEEK_DOMAIN = "SEASON_WEEK"

#: Time-of-day values a fabricated timestamp characteristically lands on. Used by
#: the supplementary detector below, never as the correctness boundary.
DEFAULT_TIME_OF_DAY_FILLS = ("00:00:00", "12:00:00")

#: Split-assignment methods refused by name. The list is not the rule — anything
#: other than TEMPORAL_ONLY is refused — but naming the random family makes the
#: refusal legible in the error a supplier actually reads.
REFUSED_SPLIT_ASSIGNMENTS = (
    "RANDOM",
    "RANDOM_SPLIT",
    "SHUFFLE",
    "SHUFFLED",
    "STRATIFIED_RANDOM",
    "KFOLD",
    "K_FOLD",
    "CROSS_VALIDATION",
    "BOOTSTRAP",
)

TEMPORAL_SPLIT_ASSIGNMENT = "TEMPORAL_ONLY"

#: The only split regime selection and hyperparameter search may read.
SELECTION_SPLIT = "validation"
HOLDOUT_USE = "SCORED_ONCE_AT_THE_END_NEVER_FOR_SELECTION"

#: The single gate through which observations become executable.
ADMISSION_GATE = "calibration.load_admitted_observations"

_INSTANT_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEQUENCE_RE = re.compile(r"^\d{1,12}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

#: A time of day, in either shape a fabricated instant arrives in: an ISO
#: date-time separator sitting between digits, or a bare clock reading. Matching
#: a bare "T" would reject a legitimately malformed value such as "Sept 2 2006"
#: with the wrong refusal.
_TIME_OF_DAY_RE = re.compile(r"\d[Tt]\d|\d{1,2}:\d{2}")


@dataclass(frozen=True)
class TemporalOrderValue:
    """The source-derived ordering value, carried by name rather than by position.

    Every field is optional here and required by basis at admission, because the
    real corpus supplies different subsets for different spans: a 2006 row may
    carry a sequence and nothing else, a 2008 row a week with no resolved date, a
    2024 regular-season row a date and a sequence, and a 2024 championship row a
    stage label and a sequence with no date at all.

    ``week_label`` and ``stage_label`` are verbatim source provenance and are
    never parsed for ordering. The corpus uses at least three incompatible label
    sets — ``P1``/``1``..``14``, ``PS``/``W1``..``W15``, and phase names such as
    ``CCG``, ``Bowl``, ``QF``, ``R1`` — and ranking them would mean inventing a
    precedence no source states. Only ``week_ordinal``, supplied by the source,
    orders anything.
    """

    season: int | None = None
    game_date: str | None = None
    week_ordinal: int | None = None
    week_label: str | None = None
    stage_label: str | None = None
    sequence: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """Named fields, absent ones omitted rather than nulled."""
        payload = {f: getattr(self, f) for f in TEMPORAL_ORDER_VALUE_FIELDS}
        return {k: v for k, v in payload.items() if v is not None}

    def canonical(self) -> str:
        """Self-describing canonical serialization.

        A JSON object with sorted keys and no whitespace. Self-describing because
        a reviewer reading a CSV cell should be able to tell a week ordinal from
        a sequence without consulting a grammar, and because a positional format
        silently changes meaning the day a field is added.
        """
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))


def _refuse_time_of_day(game_id: str, basis: str, field_name: str, raw: str) -> None:
    """Refuse a coarse-evidence field that smuggles a time of day in anyway.

    This is one of the structural guards the ruling exists to install: the source
    recorded no kickoff time, and a noon or midnight value is attached so the row
    clears admission. Once serialized it is indistinguishable from a measured
    instant.
    """
    if _TIME_OF_DAY_RE.search(raw):
        raise GovernanceBlock(
            f"Observation {game_id} declares temporal basis {basis} and carries a time "
            f"of day in {field_name}={raw!r}. {basis} proves ordering at "
            f"{TEMPORAL_ORDER_GRANULARITY[basis]} granularity only. The governed corpus "
            "records no authentic kickoff time for such an observation, and a default "
            "noon or midnight value must not be generated to stand in for absent source "
            "evidence."
        )


def _coerce_int(game_id: str, basis: str, field_name: str, raw: Any) -> int:
    text = str(raw).strip()
    _refuse_time_of_day(game_id, basis, field_name, text)
    if not _SEQUENCE_RE.match(text):
        raise GovernanceBlock(
            f"Observation {game_id} declares {basis} with {field_name}={raw!r}; expected "
            "a non-negative integer supplied by the source."
        )
    return int(text)


def parse_temporal_order_value(
    raw: Any, *, basis: str, game_id: str
) -> TemporalOrderValue:
    """Read an ordering value from any admitted representation.

    Three representations are accepted and nothing else:

    * a :class:`TemporalOrderValue`, or a mapping of its named fields (the form a
      JSON observation set and in-process code use);
    * the canonical self-describing JSON object as text (the form a CSV cell
      uses);
    * a bare ``YYYY-MM-DD`` under :data:`BASIS_EXACT_GAME_DATE`, or a bare
      non-negative integer under :data:`BASIS_GOVERNED_SOURCE_SEQUENCE`, because
      each of those directly *is* the evidence and needs no envelope.

    A positional packed string is not among them. It is refused rather than
    parsed, because a grammar no source states would become a governance rule by
    the back door.
    """
    if isinstance(raw, TemporalOrderValue):
        fields = raw.as_dict()
    elif isinstance(raw, Mapping):
        fields = {k: v for k, v in raw.items() if v is not None and str(v).strip() != ""}
    else:
        text = str(raw if raw is not None else "").strip()
        if not text:
            raise GovernanceBlock(
                f"Observation {game_id} is admitted on {basis} but supplies no "
                "temporal_order_key. The basis names the kind of evidence; the key is "
                "the evidence."
            )
        if text.startswith("{"):
            try:
                decoded = json.loads(text)
            except json.JSONDecodeError as exc:
                raise GovernanceBlock(
                    f"Observation {game_id} supplies a temporal_order_key that opens as a "
                    f"canonical JSON object but does not parse: {exc.msg}."
                ) from None
            if not isinstance(decoded, dict):
                raise GovernanceBlock(
                    f"Observation {game_id} supplies a temporal_order_key that is JSON but "
                    "not an object of named fields."
                )
            fields = {
                k: v for k, v in decoded.items() if v is not None and str(v).strip() != ""
            }
        elif basis == BASIS_EXACT_GAME_DATE:
            _refuse_time_of_day(game_id, basis, "temporal_order_key", text)
            fields = {"game_date": text}
        elif basis == BASIS_GOVERNED_SOURCE_SEQUENCE:
            _refuse_time_of_day(game_id, basis, "temporal_order_key", text)
            fields = {"sequence": text}
        else:
            _refuse_time_of_day(game_id, basis, "temporal_order_key", text)
            raise GovernanceBlock(
                f"Observation {game_id} supplies temporal_order_key {text!r} under {basis}. "
                f"{basis} evidence must be carried as named fields — a "
                f"{TemporalOrderValue.__name__}, a mapping, or its canonical JSON object "
                f"naming any of {list(TEMPORAL_ORDER_VALUE_FIELDS)}. A positional packed "
                "string is refused: it is a grammar no governed source states, and "
                "reading one would make an implementation convenience into a rule."
            )

    unknown = sorted(k for k in fields if k not in TEMPORAL_ORDER_VALUE_FIELDS)
    if unknown:
        raise GovernanceBlock(
            f"Observation {game_id} supplies temporal ordering fields outside the "
            f"governed set: {unknown}. Admitted fields are "
            f"{list(TEMPORAL_ORDER_VALUE_FIELDS)}; an unrecognised ordering field is "
            "refused rather than ignored."
        )

    value: dict[str, Any] = {}
    for name in ("season", "week_ordinal", "sequence"):
        if name in fields:
            value[name] = _coerce_int(game_id, basis, name, fields[name])
    for name in ("game_date", "week_label", "stage_label"):
        if name in fields:
            text = str(fields[name]).strip()
            _refuse_time_of_day(game_id, basis, name, text)
            value[name] = text

    if "game_date" in value and not _DATE_RE.match(value["game_date"]):
        raise GovernanceBlock(
            f"Observation {game_id} declares {basis} with game_date "
            f"{value['game_date']!r}; expected a bare calendar date YYYY-MM-DD. A date "
            "the source did not resolve must be left absent, never approximated."
        )
    return TemporalOrderValue(**value)


@dataclass(frozen=True)
class TemporalOrderEvidence:
    """Governed ordering evidence for an observation that has no kickoff time.

    A carrier, not a validator: every field is checked by
    :func:`admit_temporal_order`, so a basis cannot be validated one way here and
    another way at the admission gate.
    """

    basis: str
    value: Any
    source: str
    source_sha256: str

    def as_dict(self) -> dict[str, Any]:
        value = self.value
        if isinstance(value, TemporalOrderValue):
            value = value.canonical()
        elif isinstance(value, Mapping):
            value = json.dumps(dict(value), sort_keys=True, separators=(",", ":"))
        return {
            "temporal_order_basis": self.basis,
            "temporal_order_key": value,
            "temporal_order_source": self.source,
            "temporal_order_source_sha256": self.source_sha256,
        }


@dataclass(frozen=True)
class ResolvedTemporalOrder:
    """An admitted observation's proven position in the causal order.

    ``event_time`` is populated only where the source recorded one. For every
    other basis it is ``None`` and stays ``None`` through serialization: a
    governed source sequence establishes relative causal order and must never be
    represented as an inferred kickoff timestamp.
    """

    game_id: str
    basis: str
    granularity: str
    domain: str
    value: TemporalOrderValue
    event_time: str | None = None
    source: str | None = None
    source_sha256: str | None = None

    @property
    def has_authentic_event_time(self) -> bool:
        return self.basis == BASIS_EXACT_EVENT_TIME and self.event_time is not None

    @property
    def precedence_rank(self) -> int:
        return TEMPORAL_EVIDENCE_PRECEDENCE.index(self.basis)

    @property
    def key(self) -> str:
        """The canonical, self-describing form of this observation's ordering value."""
        return self.value.canonical()

    @property
    def calendar_date(self) -> str | None:
        return self.value.game_date

    @property
    def sequence_ordinal(self) -> int | None:
        return self.value.sequence

    def sort_key(self) -> tuple[str, str, int, str, str]:
        """A total order that is deterministic and confined to one domain.

        The domain leads, so rows whose orders are not comparable are grouped
        rather than interleaved. Inside a governed source sequence the supplied
        ordinal is the whole ordering; inside a season-week domain it is the
        season and the source-supplied week ordinal; inside the calendar domain
        the date leads and an exact instant refines it only where one was
        actually recorded.
        """
        if self.domain.startswith(BASIS_GOVERNED_SOURCE_SEQUENCE):
            return (self.domain, "", self.value.sequence or 0, "", self.game_id)
        if self.domain.startswith(SEASON_WEEK_DOMAIN):
            return (
                self.domain,
                f"{self.value.season:04d}",
                self.value.week_ordinal or 0,
                "",
                self.game_id,
            )
        return (
            self.domain,
            self.value.game_date or "",
            self.value.week_ordinal or 0,
            self.event_time or "",
            self.game_id,
        )

    def as_dict(self) -> dict[str, Any]:
        """Serialize without ever manufacturing a timestamp.

        ``event_time`` is echoed only when authentic. ``inferred_kickoff_time``
        is present and always ``None`` so a reader who goes looking for one finds
        an explicit refusal rather than an absent key they might fill in.
        """
        return {
            "game_id": self.game_id,
            "temporal_order_basis": self.basis,
            "temporal_order_granularity": self.granularity,
            "temporal_order_domain": self.domain,
            "temporal_order_key": self.key,
            "temporal_order_value": self.value.as_dict(),
            "temporal_order_source": self.source,
            "temporal_order_source_sha256": self.source_sha256,
            "event_time": self.event_time if self.has_authentic_event_time else None,
            "event_time_is_authentic": self.has_authentic_event_time,
            "inferred_kickoff_time": None,
            "serialized_as_timestamp": self.has_authentic_event_time,
        }


def _resolve_basis_value(
    game_id: str, basis: str, value: TemporalOrderValue, source: str, digest: str
) -> tuple[str, TemporalOrderValue]:
    """Check the value against its declared basis and place it in a domain.

    The basis and the value representation must agree. That agreement is the
    structural anti-fabrication rule: a row cannot claim date-level evidence
    while carrying only a sequence, and a row cannot claim sequence-level
    evidence while carrying a date it would then be read at.
    """
    if basis == BASIS_EXACT_GAME_DATE:
        if value.game_date is None:
            raise GovernanceBlock(
                f"Observation {game_id} declares {BASIS_EXACT_GAME_DATE} but supplies no "
                "game_date. The basis names the kind of evidence; the value is the "
                "evidence, and a date the source did not resolve is not invented here."
            )
        return CALENDAR_DOMAIN, value

    if basis == BASIS_WEEK_STAGE_DATE:
        if value.season is None:
            raise GovernanceBlock(
                f"Observation {game_id} declares {BASIS_WEEK_STAGE_DATE} but supplies no "
                "season. Week and stage evidence orders nothing without the season it "
                "belongs to."
            )
        if value.game_date is not None:
            return CALENDAR_DOMAIN, value
        if value.week_ordinal is None:
            raise GovernanceBlock(
                f"Observation {game_id} declares {BASIS_WEEK_STAGE_DATE} with no "
                f"game_date and no week_ordinal; week_label={value.week_label!r} and "
                f"stage_label={value.stage_label!r} are carried as provenance and are "
                "never parsed for ordering, because the governed corpus uses several "
                "incompatible label sets and no source states a precedence over them. "
                f"Supply the source's own week ordinal, or admit this observation on "
                f"{BASIS_GOVERNED_SOURCE_SEQUENCE}."
            )
        return f"{SEASON_WEEK_DOMAIN}::{source}::{digest}", value

    if value.sequence is None:
        raise GovernanceBlock(
            f"Observation {game_id} declares {BASIS_GOVERNED_SOURCE_SEQUENCE} but "
            "supplies no sequence. The preserved source ordering is the evidence."
        )
    if value.game_date is not None:
        raise GovernanceBlock(
            f"Observation {game_id} declares {BASIS_GOVERNED_SOURCE_SEQUENCE} and also "
            f"carries game_date {value.game_date!r}. A governed source sequence "
            "establishes relative causal order only; carrying a date under it would "
            "silently upgrade sequence evidence to date-level evidence. Declare "
            f"{BASIS_EXACT_GAME_DATE} or {BASIS_WEEK_STAGE_DATE} if the date is real."
        )
    return f"{BASIS_GOVERNED_SOURCE_SEQUENCE}::{source}::{digest}", value


def admit_temporal_order(
    game_id: str,
    *,
    event_time: str | None = None,
    evidence: TemporalOrderEvidence | None = None,
) -> ResolvedTemporalOrder:
    """Admit one observation's position in the causal order, or fail closed.

    An authentic kickoff instant is authoritative wherever one exists. Where one
    does not, the observation may still be admitted on governed ordering
    evidence, but only if that evidence names its basis, its ordering value, the
    source it came from and the SHA-256 of that source, so the claim is
    re-checkable rather than asserted. Missing chronology is never invented to
    make an observation pass.

    Nothing here tries to prove that a timestamp claimed as authentic is
    historically true; software cannot infer that. What it enforces is
    *consistency* between the claimed source evidence, the declared basis, the
    provenance and the supplied temporal fields — which is what actually catches
    a fabricated value, because a fabricated value has to be declared as
    something.
    """
    label = (game_id or "").strip() or "<unidentified observation>"
    stamp = event_time.strip() if isinstance(event_time, str) else event_time

    if stamp:
        if not _INSTANT_RE.match(stamp):
            raise GovernanceBlock(
                f"Observation {label} carries event_time {stamp!r}, which is not a "
                "well-formed ISO-8601 instant with an explicit offset. An unparseable "
                "timestamp is refused rather than coerced."
            )
        if evidence is not None and evidence.basis.strip() != BASIS_EXACT_EVENT_TIME:
            raise GovernanceBlock(
                f"Observation {label} carries event_time {stamp!r} and also declares "
                f"temporal basis {evidence.basis!r}. event_time remains authoritative "
                "wherever it exists, so a coarser basis standing alongside a recorded "
                "instant means one of the two was manufactured: either the source did "
                "record a kickoff time, in which case the coarse basis is wrong, or it "
                "did not, in which case the timestamp is invented. Refused rather than "
                "resolved by precedence."
            )
        digest = evidence.source_sha256.strip().lower() if evidence is not None else ""
        if digest and not _SHA256_RE.match(digest):
            raise GovernanceBlock(
                f"Observation {label} carries temporal_order_source_sha256 "
                f"{evidence.source_sha256!r}, which is not a 64-character lowercase "
                "SHA-256."
            )
        if evidence is not None:
            declared = parse_temporal_order_value(
                evidence.value, basis=BASIS_EXACT_EVENT_TIME, game_id=label
            )
            if declared.game_date is not None and declared.game_date != stamp[:10]:
                raise GovernanceBlock(
                    f"Observation {label} declares {BASIS_EXACT_EVENT_TIME} with "
                    f"game_date {declared.game_date!r} against event_time {stamp!r}. The "
                    "date of an exact-event-time observation is the date of its event."
                )
        return ResolvedTemporalOrder(
            game_id=label,
            basis=BASIS_EXACT_EVENT_TIME,
            granularity=TEMPORAL_ORDER_GRANULARITY[BASIS_EXACT_EVENT_TIME],
            domain=CALENDAR_DOMAIN,
            value=TemporalOrderValue(game_date=stamp[:10]),
            event_time=stamp,
            source=(evidence.source.strip() or None) if evidence is not None else None,
            source_sha256=digest or None,
        )

    if evidence is None:
        raise GovernanceBlock(
            f"Observation {label} carries no authentic event_time and no governed "
            f"temporal evidence. Admission requires one of "
            f"{list(TEMPORAL_EVIDENCE_PRECEDENCE)} carrying "
            f"{list(TEMPORAL_ORDER_PROVENANCE_COLUMNS)}. Missing chronology is never "
            "fabricated to make an observation pass contract admission."
        )

    basis = evidence.basis.strip()
    source = evidence.source.strip()
    digest = evidence.source_sha256.strip().lower()

    if basis not in TEMPORAL_EVIDENCE_PRECEDENCE:
        raise GovernanceBlock(
            f"Observation {label} declares temporal_order_basis {evidence.basis!r}, which "
            f"is not one of {list(TEMPORAL_EVIDENCE_PRECEDENCE)}. An unrecognised basis is "
            "refused rather than mapped onto the nearest known one."
        )
    if basis == BASIS_EXACT_EVENT_TIME:
        raise GovernanceBlock(
            f"Observation {label} declares {BASIS_EXACT_EVENT_TIME} but carries no "
            "event_time. A declared basis is not a timestamp, and the missing instant must "
            "not be synthesised to match the claim."
        )
    if not source:
        raise GovernanceBlock(
            f"Observation {label} is admitted on {basis} but names no "
            "temporal_order_source. Alternate ordering is admissible only where a reviewer "
            "can re-open the source the order came from."
        )
    if not _SHA256_RE.match(digest):
        raise GovernanceBlock(
            f"Observation {label} is admitted on {basis} from source {source!r} with "
            f"temporal_order_source_sha256 {evidence.source_sha256!r}, which is not a "
            "64-character lowercase SHA-256. An ordering claim against unpinned bytes "
            "cannot be re-checked and is refused."
        )

    value = parse_temporal_order_value(evidence.value, basis=basis, game_id=label)
    domain, value = _resolve_basis_value(label, basis, value, source, digest)
    return ResolvedTemporalOrder(
        game_id=label,
        basis=basis,
        granularity=TEMPORAL_ORDER_GRANULARITY[basis],
        domain=domain,
        value=value,
        event_time=None,
        source=source,
        source_sha256=digest,
    )


def admit_observation_temporal_order(row: Mapping[str, Any]) -> ResolvedTemporalOrder:
    """Admit one observation row, taking its temporal fields by governed name."""
    game_id = str(row.get("game_id") or "").strip()
    supplied = {
        column: row[column]
        for column in TEMPORAL_ORDER_PROVENANCE_COLUMNS
        if column in row and str(row[column] or "").strip()
    }
    evidence: TemporalOrderEvidence | None = None
    if supplied:
        absent = [c for c in TEMPORAL_ORDER_PROVENANCE_COLUMNS if c not in supplied]
        if absent:
            raise GovernanceBlock(
                f"Observation {game_id or '<unidentified observation>'} supplies partial "
                f"governed temporal provenance; missing {absent}. All of "
                f"{list(TEMPORAL_ORDER_PROVENANCE_COLUMNS)} are required together, because "
                "a basis without a re-checkable source is an assertion rather than "
                "evidence."
            )
        evidence = TemporalOrderEvidence(
            basis=str(supplied["temporal_order_basis"]).strip(),
            value=supplied["temporal_order_key"],
            source=str(supplied["temporal_order_source"]).strip(),
            source_sha256=str(supplied["temporal_order_source_sha256"]).strip(),
        )
    return admit_temporal_order(game_id, event_time=row.get("event_time"), evidence=evidence)


#: The time-of-day fill detector is a supplementary diagnostic and is never the
#: correctness boundary. The structural rules — a coarse basis may not carry a
#: time of day, an event_time may not stand beside a coarse basis, a declared
#: basis and its value representation must agree, alternate ordering must carry
#: complete re-checkable provenance — refuse a fabricated timestamp one row at a
#: time and do not depend on this running at all.
TIME_OF_DAY_FILL_DETECTOR_IS_DIAGNOSTIC_ONLY = True


def refuse_default_time_of_day_fill(orders: Iterable[ResolvedTemporalOrder]) -> None:
    """Report a dataset whose event_times all collapse onto one default fill.

    Real kickoffs across multiple dates do not share a single second-precise time
    of day. A whole column that does, and that lands on midnight or noon, is a
    date column that was widened into a timestamp column.

    This is a *diagnostic*. It catches a shape the structural rules cannot,
    because a row that claims EXACT_EVENT_TIME and supplies a well-formed instant
    is internally consistent and no amount of checking can tell whether the
    instant was measured. It is deliberately not load-bearing: disabling it opens
    no admission path, since every coarse-evidence route is already closed one
    row at a time by :func:`admit_temporal_order`.
    """
    stamps = [o.event_time for o in orders if o.has_authentic_event_time and o.event_time]
    if len(stamps) < 2:
        return
    times = {s[11:19] for s in stamps}
    dates = {s[:10] for s in stamps}
    if len(times) == 1 and len(dates) > 1:
        only = next(iter(times))
        if only in DEFAULT_TIME_OF_DAY_FILLS:
            raise GovernanceBlock(
                f"Every event_time across {len(dates)} distinct dates carries the identical "
                f"time of day {only}, a default fill value. A date column widened into a "
                "timestamp column is a fabricated kickoff time. Leave event_time null and "
                "admit these observations on governed temporal order instead "
                f"({list(TEMPORAL_EVIDENCE_PRECEDENCE[1:])})."
            )


def admit_observations(
    rows: Iterable[Mapping[str, Any]]
) -> list[ResolvedTemporalOrder]:
    """Admit a set of observation rows, structurally and then diagnostically."""
    orders = [admit_observation_temporal_order(row) for row in rows]
    refuse_default_time_of_day_fill(orders)
    return orders


def governed_temporal_order(
    orders: Iterable[ResolvedTemporalOrder],
) -> list[ResolvedTemporalOrder]:
    """Sort admitted observations deterministically inside their own domains."""
    return sorted(orders, key=lambda o: o.sort_key())


def _unproven_before(
    earlier: ResolvedTemporalOrder, later: ResolvedTemporalOrder
) -> str | None:
    """Return why ``earlier`` is not provably before ``later``, or None if it is.

    Comparison happens at the coarser of the two granularities. Two exact
    instants are compared as instants; anything else on the calendar falls back
    to the date, because a day- or week-granularity row carries no claim about
    where inside that day it sat and pretending otherwise is the fabrication this
    ruling forbids.
    """
    if earlier.domain != later.domain:
        return (
            f"{earlier.game_id} is ordered in domain {earlier.domain} and "
            f"{later.game_id} in {later.domain}; the two orders are not comparable"
        )
    if earlier.domain.startswith(BASIS_GOVERNED_SOURCE_SEQUENCE):
        if (earlier.value.sequence or 0) < (later.value.sequence or 0):
            return None
        return (
            f"{earlier.game_id} holds source sequence {earlier.value.sequence} and "
            f"{later.game_id} holds {later.value.sequence}"
        )
    if earlier.domain.startswith(SEASON_WEEK_DOMAIN):
        left = (earlier.value.season, earlier.value.week_ordinal or 0)
        right = (later.value.season, later.value.week_ordinal or 0)
        if left < right:
            return None
        return (
            f"{earlier.game_id} sits at season {left[0]} week {left[1]} and "
            f"{later.game_id} at season {right[0]} week {right[1]}"
        )
    if earlier.has_authentic_event_time and later.has_authentic_event_time:
        if str(earlier.event_time) < str(later.event_time):
            return None
        return (
            f"{earlier.game_id} at {earlier.event_time} does not precede {later.game_id} "
            f"at {later.event_time}"
        )
    if str(earlier.calendar_date) < str(later.calendar_date):
        return None
    return (
        f"{earlier.game_id} on {earlier.calendar_date} ({earlier.granularity}) does not "
        f"provably precede {later.game_id} on {later.calendar_date} ({later.granularity}); "
        "at this granularity same-day ordering is not proven"
    )


@dataclass(frozen=True)
class PartitionedObservation:
    """An admitted observation together with the partition it was assigned to."""

    game_id: str
    season: int
    split: str
    order: ResolvedTemporalOrder


def partition_observations(
    rows: Iterable[Mapping[str, Any]]
) -> list[PartitionedObservation]:
    """Admit rows and attach the season and split each one declares."""
    partitioned: list[PartitionedObservation] = []
    orders: list[ResolvedTemporalOrder] = []
    for row in rows:
        order = admit_observation_temporal_order(row)
        orders.append(order)
        try:
            season = int(str(row.get("season")).strip())
        except (TypeError, ValueError):
            raise GovernanceBlock(
                f"Observation {order.game_id} declares season {row.get('season')!r}, which "
                "is not an integer season. Season is the one granularity every ordering "
                "domain shares, so an unreadable season makes cross-domain ordering "
                "unprovable."
            ) from None
        partitioned.append(
            PartitionedObservation(
                game_id=order.game_id,
                season=season,
                split=str(row.get("split") or "").strip().lower(),
                order=order,
            )
        )
    refuse_default_time_of_day_fill(orders)
    return partitioned


def require_temporal_split_assignment(method: str | None) -> str:
    """Refuse any split assignment that is not temporal."""
    declared = (method or "").strip().upper()
    if declared in REFUSED_SPLIT_ASSIGNMENTS:
        raise GovernanceBlock(
            f"Split assignment {method!r} is refused. Weekly ratings are a sequential "
            "process, so a randomly assigned holdout game sits earlier in time than "
            "training games that already absorbed its result, and the measured "
            f"out-of-sample error is not out-of-sample. Only {TEMPORAL_SPLIT_ASSIGNMENT} "
            "is admissible."
        )
    if declared != TEMPORAL_SPLIT_ASSIGNMENT:
        raise GovernanceBlock(
            f"Split assignment {method!r} is not {TEMPORAL_SPLIT_ASSIGNMENT}. An "
            "unrecognised assignment method is refused rather than assumed temporal."
        )
    return TEMPORAL_SPLIT_ASSIGNMENT


def require_selection_split(split: str | None, *, purpose: str = "regime selection") -> str:
    """Refuse the holdout as a selection or hyperparameter-search surface.

    The holdout is scored once, at the end. A holdout consulted while a regime is
    being chosen has been fitted to, and its later score stops being the
    out-of-sample number the primary objective is defined as.
    """
    key = (split or "").strip().lower()
    if key not in DATA_SPLITS:
        raise InputValidationError(f"Split {split!r} is not one of {list(DATA_SPLITS)}")
    if key == "holdout":
        raise GovernanceBlock(
            f"The holdout split may not be read for {purpose}. Holdout use is "
            f"{HOLDOUT_USE}: a holdout consulted during selection has been fitted to, and "
            f"its final score stops being out-of-sample. Use {SELECTION_SPLIT!r}."
        )
    if key != SELECTION_SPLIT:
        raise GovernanceBlock(
            f"{purpose.capitalize()} reads the {SELECTION_SPLIT!r} split, not {key!r}. "
            "Training scores are in-sample and rank a regime against the data it was "
            "fitted on."
        )
    return key


def _prove_partition(
    rows: list[PartitionedObservation],
) -> tuple[dict[str, list[PartitionedObservation]], list[str]]:
    """Bucket a partition and return every ordering it cannot prove.

    Shared by both public split gates so the exact-event-time path and the
    successor path cannot drift into proving different things.
    """
    seen: dict[str, str] = {}
    duplicated = []
    for observation in rows:
        if observation.game_id in seen:
            duplicated.append(
                f"{observation.game_id} in {seen[observation.game_id]} and "
                f"{observation.split}"
            )
        seen[observation.game_id] = observation.split
    if duplicated:
        raise GovernanceBlock(
            f"Observations repeat a game_id: {sorted(duplicated)}. Split assignment is "
            "keyed by game_id, so a repeated key collapses into one bucket and silently "
            "discards one of its two assignments."
        )

    buckets = require_split_separation({o.game_id: o.split for o in rows})
    by_id = {o.game_id: o for o in rows}
    by_split = {split: [by_id[i] for i in ids] for split, ids in buckets.items()}

    empty = [s for s in DATA_SPLITS if not by_split[s]]
    if empty:
        raise GovernanceBlock(
            f"Temporal split integrity requires all of {list(DATA_SPLITS)} to be "
            f"populated; empty: {empty}."
        )

    violations: list[str] = []
    for earlier, later in zip(DATA_SPLITS, DATA_SPLITS[1:]):
        left, right = by_split[earlier], by_split[later]
        shared = {o.order.domain for o in left} & {o.order.domain for o in right}
        for domain in sorted(shared):
            last = max(
                (o for o in left if o.order.domain == domain),
                key=lambda o: o.order.sort_key(),
            )
            first = min(
                (o for o in right if o.order.domain == domain),
                key=lambda o: o.order.sort_key(),
            )
            reason = _unproven_before(last.order, first.order)
            if reason:
                violations.append(f"{earlier} -> {later} in domain {domain}: {reason}")

        # Cross-domain, only a season difference can prove an ordering no shared
        # domain covers. Rows on either side of the boundary that are not
        # separated by season must therefore share a domain.
        straddling_left = [o for o in left if o.season >= min(r.season for r in right)]
        straddling_right = [o for o in right if o.season <= max(l.season for l in left)]
        if straddling_left and straddling_right:
            domains = {o.order.domain for o in straddling_left} | {
                o.order.domain for o in straddling_right
            }
            if len(domains) > 1:
                violations.append(
                    f"{earlier} -> {later}: observations of the same season sit in "
                    f"different ordering domains {sorted(domains)}. Their relative order "
                    "is established by no governed evidence and is refused rather than "
                    "assumed."
                )
    return by_split, violations


def _partition_report(
    by_split: dict[str, list[PartitionedObservation]]
) -> dict[str, Any]:
    rows = [o for group in by_split.values() for o in group]
    ordered = governed_temporal_order(o.order for o in rows)
    bases = {b: 0 for b in TEMPORAL_EVIDENCE_PRECEDENCE}
    for order in ordered:
        bases[order.basis] += 1
    domains: dict[str, dict[str, int]] = {}
    for observation in rows:
        counts = domains.setdefault(observation.order.domain, {s: 0 for s in DATA_SPLITS})
        counts[observation.split] += 1
    boundaries = {}
    seasons = {}
    for split in DATA_SPLITS:
        ranked = governed_temporal_order(o.order for o in by_split[split])
        boundaries[split] = (ranked[0].key, ranked[-1].key)
        seasons[split] = (
            min(o.season for o in by_split[split]),
            max(o.season for o in by_split[split]),
        )
    return {
        "splits": {s: len(by_split[s]) for s in DATA_SPLITS},
        "boundaries": boundaries,
        "season_ranges": seasons,
        "assignment": TEMPORAL_SPLIT_ASSIGNMENT,
        "leak_free": True,
        "ruling": TEMPORAL_ORDER_RULING,
        "temporal_bases": bases,
        "ordering_domains": domains,
        "observations_with_authentic_event_time": sum(
            1 for o in ordered if o.has_authentic_event_time
        ),
        "observations_on_governed_temporal_order": sum(
            1 for o in ordered if not o.has_authentic_event_time
        ),
        "fabricated_timestamps": 0,
        "holdout_use": HOLDOUT_USE,
    }


def require_temporal_split_integrity(
    ordered_events: Mapping[str, tuple[str, str]]
) -> dict[str, Any]:
    """Confirm an exact-event-time partition is temporal and leak-free.

    ``ordered_events`` maps each ``game_id`` to ``(split, event_time)``. This is
    the gate for datasets in which every observation carries an authentic kickoff
    instant, and its behaviour for those datasets is unchanged.

    What did change is that each supplied ``event_time`` is now routed through
    :func:`admit_temporal_order` rather than compared as a bare string, so this
    path cannot admit a value the successor gate would refuse. The two gates
    prove the same property through the same code; this one additionally requires
    every observation to be at INSTANT granularity.
    """
    rows = []
    for game_id, (split, event_time) in ordered_events.items():
        order = admit_temporal_order(game_id, event_time=event_time)
        rows.append(
            PartitionedObservation(
                game_id=order.game_id,
                season=int(str(order.calendar_date)[:4]),
                split=str(split or "").strip().lower(),
                order=order,
            )
        )
    by_split, violations = _prove_partition(rows)
    if violations:
        raise GovernanceBlock(
            f"Split assignment is not temporally ordered: {violations}. A holdout that "
            "overlaps training in time does not measure out-of-sample error."
        )
    return _partition_report(by_split)


def require_governed_temporal_split_integrity(
    observations: Iterable[PartitionedObservation],
) -> dict[str, Any]:
    """Prove the partition is forward-only and temporally disjoint.

    :func:`require_temporal_split_integrity` is the same proof restricted to
    observations that all carry an exact kickoff instant. This is the general
    gate for a corpus that mixes granularities, and it proves the property
    without ever comparing across granularities it does not have:

    * inside one ordering domain, the boundary is proven on that domain's native
      value, at the coarser of the two granularities involved;
    * across domains, ordering is provable only by season — the one granularity
      every domain shares. Where two splits hold same-season rows in different
      domains, the boundary is unprovable and is refused rather than assumed.
    """
    by_split, violations = _prove_partition(list(observations))
    if violations:
        raise GovernanceBlock(
            f"Split assignment is not provably forward-only: {violations}. A holdout that "
            "overlaps training in time, or whose order against training cannot be proven, "
            "does not measure out-of-sample error."
        )
    return _partition_report(by_split)


# --- the one executable door -------------------------------------------------
#
# register_dataset is registration only: it establishes identity, digest, shape
# and column admissibility, and it deliberately reads no observation values. The
# gap that leaves is the one this section closes. An observation set becomes
# *executable* — consumable, partitionable, scoreable, fittable, held out — only
# by passing through load_admitted_observations, and the only type that carries
# executable observations cannot be constructed any other way.

#: Private construction token. AdmittedObservationSet exists to be proof that the
#: gate ran, so it must not be constructible by anyone who did not run it.
_ADMISSION_TOKEN = object()


@dataclass(frozen=True)
class AdmittedObservationSet:
    """Observations that have passed temporal admission and split validation.

    This type *is* the receipt. A consumer that accepts one has a guarantee that
    every row was admitted on real temporal evidence and that the partition was
    proven forward-only; a consumer that accepts a
    :class:`CalibrationDataset` has neither, because registration reads no rows.

    The boundary is deliberately a Python one. ``_ADMISSION_TOKEN`` is
    module-private, which stops a supported or accidental bypass — the shapes
    that actually happen, where a caller reaches for the type because it is what
    the consumer wants. It is not a hostile-code boundary and is not treated as
    one: anything willing to reach into module internals can reach it, and no
    amount of cryptography inside one process would change that.
    """

    dataset_id: str
    dataset_sha256: str
    observations: tuple[PartitionedObservation, ...]
    split_report: dict[str, Any]
    admission_gate: str = ADMISSION_GATE
    token: Any = None

    def __post_init__(self) -> None:
        if self.token is not _ADMISSION_TOKEN:
            raise GovernanceBlock(
                "An AdmittedObservationSet may only be constructed by "
                f"{ADMISSION_GATE}. Building one directly would forge the receipt that "
                "temporal admission ran, which is the whole of what this type asserts."
            )
        # Cleared once checked, so an issued receipt cannot be read for the token
        # that would let a caller mint another one without running the gate.
        object.__setattr__(self, "token", None)

    def ordered(self) -> list[ResolvedTemporalOrder]:
        return governed_temporal_order(o.order for o in self.observations)

    def split(self, name: str) -> tuple[PartitionedObservation, ...]:
        key = (name or "").strip().lower()
        if key not in DATA_SPLITS:
            raise InputValidationError(f"Split {name!r} is not one of {list(DATA_SPLITS)}")
        return tuple(o for o in self.observations if o.split == key)

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_sha256": self.dataset_sha256,
            "admission_gate": self.admission_gate,
            "observations": len(self.observations),
            "split_report": dict(self.split_report),
        }


def _observation_rows(dataset: CalibrationDataset) -> list[dict[str, Any]]:
    """Read the registered bytes back into rows. Deliberately module-private.

    No public function returns raw observation rows from a registered dataset. If
    one did, it would be the bypass this section exists to close: a caller could
    take the rows and score them without ever admitting them.
    """
    data = dataset.path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != dataset.sha256:
        raise GovernanceBlock(
            f"Calibration dataset {dataset.dataset_id} hashes to {digest} but was "
            f"registered as {dataset.sha256}. The bytes changed after registration; a "
            "dataset that is not the one that was registered is refused."
        )
    text = data.decode("utf-8")
    declared = (dataset.fmt or "").strip().lower()
    if declared not in SUPPORTED_DATASET_FORMATS:
        raise GovernanceBlock(
            f"Calibration dataset {dataset.dataset_id} declares format {dataset.fmt!r}, "
            f"which is not one of {list(SUPPORTED_DATASET_FORMATS)}."
        )
    if declared == "json":
        payload = json.loads(text)
        rows = payload.get("observations") if isinstance(payload, dict) else payload
        return [dict(r) for r in rows]
    delimiter = "\t" if declared == "tsv" else ","
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    return [
        {(k or "").strip(): v for k, v in row.items()}
        for row in reader
        if any((v or "").strip() for v in row.values())
    ]


def load_admitted_observations(dataset: CalibrationDataset) -> AdmittedObservationSet:
    """The single executable entrypoint: registration -> admission -> partition.

    Every row is admitted through :func:`admit_observation_temporal_order` before
    anything reads a margin, and the resulting partition is proven forward-only
    before anything is scored. A row that carries neither an authentic
    ``event_time`` nor complete governed temporal evidence fails here, and
    because this is the only door, it cannot reach calibration use by any other
    route.
    """
    lowered = {c.strip().lower() for c in dataset.columns}
    required = [c for c in ("season", "split") if c not in lowered]
    if required:
        raise GovernanceBlock(
            f"Calibration dataset {dataset.dataset_id} cannot be admitted for execution: "
            f"missing {required}. A partition that is assigned at experiment time is not "
            "auditable, and season is the one granularity every ordering domain shares."
        )
    rows = _observation_rows(dataset)
    partitioned = partition_observations(rows)
    report = require_governed_temporal_split_integrity(partitioned)
    return AdmittedObservationSet(
        dataset_id=dataset.dataset_id,
        dataset_sha256=dataset.sha256,
        observations=tuple(partitioned),
        split_report=report,
        token=_ADMISSION_TOKEN,
    )


def require_admitted_observations(candidate: Any) -> AdmittedObservationSet:
    """Refuse anything that is not a gate-issued admitted observation set.

    Any future consumer that scores, fits, selects against or holds out
    observations calls this first. Passing a registered
    :class:`CalibrationDataset` is the mistake it exists to catch: registration
    proves identity and shape, not that a single row carries real chronology.
    """
    if isinstance(candidate, AdmittedObservationSet):
        return candidate
    if isinstance(candidate, CalibrationDataset):
        raise GovernanceBlock(
            f"Calibration dataset {candidate.dataset_id} is registered, not admitted. "
            "Registration establishes identity, digest and column admissibility and "
            f"reads no observation values. Call {ADMISSION_GATE} first: an observation "
            "may not be consumed, partitioned, scored, fitted, validated or held out "
            "before it passes temporal admission."
        )
    raise GovernanceBlock(
        f"Executable calibration use requires an AdmittedObservationSet issued by "
        f"{ADMISSION_GATE}; got {type(candidate).__name__}."
    )


def temporal_order_governance_as_dict() -> dict[str, Any]:
    """The successor temporal-order semantics, as a reviewable record."""
    return {
        "ruling": TEMPORAL_ORDER_RULING,
        "chairman_ruling_id": TEMPORAL_ORDER_RULING_ID,
        "approval_token": TEMPORAL_ORDER_APPROVAL_TOKEN,
        "event_time_authoritative_where_it_exists": True,
        "event_time_globally_optional": False,
        "synthetic_time_of_day_permitted": False,
        "default_time_of_day_fills_refused": list(DEFAULT_TIME_OF_DAY_FILLS),
        "time_of_day_fill_detector_is_diagnostic_only": (
            TIME_OF_DAY_FILL_DETECTOR_IS_DIAGNOSTIC_ONLY
        ),
        "anti_fabrication_is_structural": True,
        "structural_anti_fabrication_rules": [
            "A coarse-basis observation may not carry a time of day in any field.",
            "An event_time may not stand beside a basis weaker than EXACT_EVENT_TIME.",
            "EXACT_EVENT_TIME may not be declared without an event_time.",
            "The declared basis and the supplied value representation must agree.",
            "Alternate ordering requires complete, re-checkable provenance.",
            "GOVERNED_SOURCE_SEQUENCE may not carry a game_date.",
        ],
        "temporal_evidence_precedence": list(TEMPORAL_EVIDENCE_PRECEDENCE),
        "granularity": dict(TEMPORAL_ORDER_GRANULARITY),
        "value_representation": "NAMED_FIELDS_CANONICAL_JSON",
        "value_fields": list(TEMPORAL_ORDER_VALUE_FIELDS),
        "positional_packed_key_grammar_permitted": False,
        "stage_and_week_labels_parsed_for_ordering": False,
        "required_provenance_when_event_time_absent": list(
            TEMPORAL_ORDER_PROVENANCE_COLUMNS
        ),
        "governed_source_sequence_is_relative_only": True,
        "governed_source_sequence_serialized_as_timestamp": False,
        "cross_domain_ordering_proof": "SEASON_ONLY",
        "split_assignment": TEMPORAL_SPLIT_ASSIGNMENT,
        "random_split_permitted": False,
        "refused_split_assignments": list(REFUSED_SPLIT_ASSIGNMENTS),
        "selection_split": SELECTION_SPLIT,
        "holdout_use": HOLDOUT_USE,
        "missing_chronology_may_be_fabricated": False,
        "admission_gate": ADMISSION_GATE,
        "executable_use_requires_admission": True,
        "promotion_binding_requires_admission_receipt": True,
        "promotion_binding_gate": "calibration.bind_promotion_evidence",
        "caller_asserted_admission_permitted": False,
        "admission_assertion_keys_refused": list(ADMISSION_ASSERTION_KEYS),
        "unbound_promotion_path_is_promotion_eligible": False,
        "executable_chain": [
            "registered source",
            "digest verified",
            "rows temporally admitted",
            "partition proven forward-only",
            "calibration/scoring result",
            "promotion evidence binding",
        ],
    }



def calibration_governance_as_dict() -> dict[str, object]:
    return {
        "ruling": R2_CALIBRATION.convergence_id,
        "primary_metric": PRIMARY_CALIBRATION_METRIC,
        "primary_direction": PRIMARY_CALIBRATION_DIRECTION,
        "independent_witnesses": list(INDEPENDENT_WITNESSES),
        "supporting_diagnostics": list(SUPPORTING_DIAGNOSTICS),
        "weighted_composite_authorised": False,
        "splits": list(DATA_SPLITS),
        "promotion_authorities": list(PROMOTION_AUTHORITIES),
        "automatic_promotion": False,
        "observation_allowlist": list(CALIBRATION_OBSERVATION_COLUMNS),
        "supported_dataset_formats": list(SUPPORTED_DATASET_FORMATS),
        "public_money_admissible": False,
        "dataset_mounted": False,
        "disposition": BLOCKED_ON_CALIBRATION_DATA,
        "ranking_requires_primary_objective": True,
        "split_assignment": "TEMPORAL_ONLY",
        "random_split_permitted": False,
        "promotion_evidence_binding_states": [EVIDENCE_BOUND, EVIDENCE_UNBOUND],
        "synthetic_calibration_data_admissible": False,
        "legacy_margin_sd_20_2_promotable": False,
        "temporal_order": temporal_order_governance_as_dict(),
    }
