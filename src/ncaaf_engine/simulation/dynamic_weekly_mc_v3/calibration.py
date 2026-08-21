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
* :func:`require_temporal_split_integrity` proves the partition is ordered in
  time. :func:`require_split_separation` proves only disjointness, and a randomly
  assigned holdout of sequential weekly ratings is not out-of-sample at all.

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
CALIBRATION_OBSERVATION_COLUMNS = (
    "game_id",
    "season",
    "week",
    "event_time",
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

    missing = sorted(
        c for c in REQUIRED_OBSERVATION_COLUMNS
        if c not in {x.strip().lower() for x in columns}
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
) -> dict[str, Any]:
    """Promotion gate under ruling R2-CAL-OBJECTIVE.

    Two authorities are recognised and the record must name which was used. Both
    still require the human approval token: naming an authority is not the same
    as being one, and a top ranking is neither.
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
        regime, evidence=evidence, experiment=experiment, dataset=dataset
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


def bind_promotion_evidence(
    regime: CandidateRegime,
    *,
    evidence: dict[str, Any] | None,
    experiment: ExperimentRecord | None,
    dataset: CalibrationDataset | None,
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
    """
    supplied = dict(evidence or {})
    if experiment is None or dataset is None:
        return {
            "evidence_binding": EVIDENCE_UNBOUND,
            "evidence_bound": False,
            "bound_experiment_id": None,
            "bound_dataset_sha256": None,
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
    return {
        "evidence_binding": EVIDENCE_BOUND,
        "evidence_bound": True,
        "bound_experiment_id": experiment.experiment_id,
        "bound_dataset_sha256": dataset.sha256,
        "measured_primary_metric": measured,
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


def require_temporal_split_integrity(
    ordered_events: dict[str, tuple[str, str]]
) -> dict[str, Any]:
    """Confirm the partition is temporal and leak-free.

    ``ordered_events`` maps each ``game_id`` to ``(split, event_time)``.

    Weekly reratings are a sequential process, so a randomly assigned holdout is
    not out-of-sample: training weeks that follow it in time have already absorbed
    its result. :func:`require_split_separation` proves each observation sits in
    exactly one bucket, which is disjointness, not ordering. This proves ordering.
    """
    buckets = require_split_separation({g: v[0] for g, v in ordered_events.items()})
    times = {
        split: sorted(ordered_events[g][1] for g in ids)
        for split, ids in buckets.items()
    }
    empty = [s for s in DATA_SPLITS if not times[s]]
    if empty:
        raise GovernanceBlock(
            f"Temporal split integrity requires all of {list(DATA_SPLITS)} to be "
            f"populated; empty: {empty}."
        )
    violations = []
    for earlier, later in zip(DATA_SPLITS, DATA_SPLITS[1:]):
        if times[earlier][-1] >= times[later][0]:
            violations.append(
                f"{earlier} ends at {times[earlier][-1]} but {later} starts at "
                f"{times[later][0]}"
            )
    if violations:
        raise GovernanceBlock(
            f"Split assignment is not temporally ordered: {violations}. A holdout that "
            "overlaps training in time does not measure out-of-sample error."
        )
    return {
        "splits": {s: len(times[s]) for s in DATA_SPLITS},
        "boundaries": {s: (times[s][0], times[s][-1]) for s in DATA_SPLITS},
        "assignment": "TEMPORAL_ONLY",
        "leak_free": True,
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
    }
