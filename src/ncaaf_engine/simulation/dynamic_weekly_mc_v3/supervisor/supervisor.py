"""The autonomous supervisor: one command, every eligible deterministic stage.

What this module does is small to describe and load-bearing to get right. It
walks the state machine in :mod:`.states`, and at each live state it either does
the bookkeeping that state implies or calls the one stage handler that state
owns. A handler returns a :class:`~.states.StageResult`; the driver writes it
immutably, and then advances -- to the next spine state on ``PASS`` or
``PASS_WITH_ADVISORY``, to :data:`~.states.HALTED_FOR_HUMAN_REVIEW` on
``HUMAN_REVIEW_REQUIRED``, and to :data:`~.states.HALTED_FAILED` on ``FAIL``.

It stops for three things and nothing else: a genuine evidence or model failure,
the parameter-approval gate, and an unrecoverable execution error. It does not
stop for advisories. An advisory is recorded on the stage result and the run
continues, unless run policy has explicitly named that advisory required -- which
is the one place an advisory can halt, and it is a decision made in the
configuration before the run rather than by the supervisor when the advisory
arrives.

Stage results are the memory
-----------------------------

Nothing meaningful is held only in Python. Each stage writes its full detail to
``stage_results/``, and every later stage reads what it needs from there through
:meth:`Supervisor._detail`. That is what makes resume real rather than
aspirational: a supervisor restarted after a crash rehydrates from the same files
an auditor would read, so a resumed run and a fresh one that reached the same
state are the same run in every respect that matters.

Two authorities, and only one of them is a filename
----------------------------------------------------

What may be fitted is read out of two artifacts, not one. The run-local frozen
manifest in :mod:`.evidence` classifies parameters; the Agent-12 R2 evidence
manifest in :mod:`.domain_manifest`, resolved from a pinned commit through the
git object store, classifies *sources* by the digest of their bytes and is the
authority on domain and on parameter eligibility. Where the two disagree the R2
manifest wins, by :mod:`.authority`'s supersession rank, and the disagreement is
recorded rather than smoothed over. Nothing decides a domain question from a
file name; the naming patterns still run, second, as defence in depth.

Mixed dispositions, one gate, no second stop
---------------------------------------------

A parameter no longer has to be fitted for the run to continue. Every governed
parameter reaches the recommendation carrying one of the nine dispositions in
:mod:`.dispositions`, and where production reads a value this run could not
produce, the recommendation asks the approver for one. That question is asked at
the single human gate and nowhere else: after the approval the machine has no
edge to :data:`~.states.HALTED_FOR_HUMAN_REVIEW` at all, and the tier gates
diagnose convergence from the run samples rather than from a tolerance somebody
would otherwise have to supply mid-run.

What it will not do
--------------------

It does not choose parameter values -- a search runs only where both authorities
say :data:`~.evidence.FIT_ALLOWED`, and refuses otherwise. It does not implement
model mathematics -- every numerical act goes through
:class:`~.execution.ModelRunExecutor`, whose default refuses everything because
the frozen evidence bundle does not exist yet. It does not approve anything. It
does not invent a value for a parameter nobody measured. And it never lets the
real-football witness change the vector it just selected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .. import run_tier as tier_policy
from ..errors import GovernanceBlock, InputValidationError
from . import convergence as CV
from . import dispositions as D
from . import evidence as EV
from . import gates
from . import states as S
from . import wave1 as W1
from .authority import (
    AuthorityBinding,
    CURRENT_AUTHORITY_GENERATION,
    EligibilityClaim,
    resolve_authority,
    supersession_report,
)
from .domain_manifest import (
    EvidenceDomainManifest,
    FILENAME_CHECKS_ROLE,
    load_domain_manifest_from_authority,
)
from .approval import (
    APPROVAL_ACTION,
    ApprovalRecord,
    approve as approve_recommendation,
    require_approval_for_execution,
)
from .digests import code_tree_digest
from .execution import (
    DatasetBinding,
    ModelRunExecutor,
    UnmountedEvidenceExecutor,
    volume_shortfalls,
)
from .holdout import HoldoutGuard, HoldoutSeal, guarded_oracle
from .recommendation import (
    ParameterRecommendation,
    RecommendationPackage,
    RunBindings,
)
from .retry import RETRY_POLICY, run_with_temp_root_retry
from .runstore import (
    DEFAULT_RUN_ROOT,
    RunLock,
    RunState,
    atomic_write_json,
    new_run_id,
    run_directory,
    utc_now,
    write_run_manifest,
)
from .search import (
    IDENTIFIED,
    PARAMETER_UNIDENTIFIED,
    SearchAxis,
    SearchOutcome,
    ScoringOracle,
    UNIDENTIFIED_NONBINDING,
    candidate_universe_digest,
    classify_movement_cap,
    coarse_search,
    refine,
)
from .witness import (
    WitnessObservation,
    WitnessThreshold,
    classify_witness,
    default_thresholds,
    require_vector_unchanged,
)

__all__ = [
    "SCALAR_SEARCH_PARAMETERS",
    "STAGE_FOR_STATE",
    "Supervisor",
    "SupervisorConfig",
]

# --- stage names -------------------------------------------------------------

STAGE_SYNTHETIC_EVIDENCE = "synthetic_evidence"
STAGE_CALIBRATION_DATASET = "calibration_dataset"
STAGE_PREFLIGHT = "preflight"
STAGE_POINT_SCALE = "point_scale"
STAGE_COARSE_SEARCH = "coarse_search"
STAGE_REFINEMENT = "refinement"
STAGE_VALIDATION = "validation"
STAGE_HOLDOUT_SEAL = "holdout_seal"
STAGE_HOLDOUT_RELEASE = "holdout_release"
STAGE_HOLDOUT_SCORE = "holdout_score"
STAGE_GAME_SD = "game_sd"
STAGE_FCS_ADAPTER = "fcs_adapter"
STAGE_WITNESS = "real_world_witness"
STAGE_RECOMMENDATION = "recommendation"
STAGE_APPROVAL_CHECK = "approval_binding_check"

#: Which state owns which stage. A state absent from this map does no work; it is
#: a completion marker the driver walks straight through.
STAGE_FOR_STATE: dict[str, str] = {
    S.SYNTHETIC_EVIDENCE_REQUIRED: STAGE_SYNTHETIC_EVIDENCE,
    S.CALIBRATION_DATASET_REQUIRED: STAGE_CALIBRATION_DATASET,
    S.PREFLIGHT_REQUIRED: STAGE_PREFLIGHT,
    S.POINT_SCALE_DECISION_REQUIRED: STAGE_POINT_SCALE,
    S.COARSE_SEARCH_REQUIRED: STAGE_COARSE_SEARCH,
    S.REFINEMENT_REQUIRED: STAGE_REFINEMENT,
    S.VALIDATION_REQUIRED: STAGE_VALIDATION,
    S.VALIDATION_COMPLETE: STAGE_HOLDOUT_SEAL,
    S.HOLDOUT_LOCKED: STAGE_HOLDOUT_RELEASE,
    S.HOLDOUT_RELEASED: STAGE_HOLDOUT_SCORE,
    S.GAME_SD_REQUIRED: STAGE_GAME_SD,
    S.FCS_ADAPTER_REQUIRED: STAGE_FCS_ADAPTER,
    S.REAL_WORLD_WITNESS_REQUIRED: STAGE_WITNESS,
    S.REAL_WORLD_WITNESS_COMPLETE: STAGE_RECOMMENDATION,
    S.PARAMETERS_APPROVED: STAGE_APPROVAL_CHECK,
    S.DEV_500_REQUIRED: gates.DEV_500_STAGE,
    S.ANALYSIS_2000_REQUIRED: gates.ANALYSIS_2000_STAGE,
    S.PUBLISH_10000_REQUIRED: gates.PUBLISH_10000_STAGE,
    S.FINAL_FREEZE_REQUIRED: gates.FINAL_FREEZE_STAGE,
}

#: Parameters the coordinate search fits directly as scalar axes.
#:
#: ``recent_form_weights``, ``blowout_treatment`` and ``sample_size_regularization``
#: are structured rather than scalar. They are fitted through a declared scalar
#: parameterization -- a decay rate that generates the weight vector, a threshold
#: that generates the blowout rule -- which the manifest supplies as that
#: parameter's search space. The supervisor searches the scalar; the executor owns
#: turning it back into the structure, because that mapping is model mathematics.
SCALAR_SEARCH_PARAMETERS: tuple[str, ...] = (
    "weekly_performance_residual_coefficient",
    "weekly_movement_cap_points",
    "recent_form_weights",
    "blowout_treatment",
    "sample_size_regularization",
)

#: The parameter whose non-binding classification is checked after refinement.
CONSTRAINT_PARAMETER = "weekly_movement_cap_points"

_TRAINING_SPLIT = "training"
_VALIDATION_SPLIT = "validation"


@dataclass(frozen=True)
class SupervisorConfig:
    """Everything the supervisor needs that is not a model interface.

    Tolerances are here, not in the gates, and they are read from a file written
    before the run. That is the whole point of predeclaring them: a tolerance
    chosen once the divergence is visible is a choice of outcome.
    """

    evidence_manifest_path: Path
    run_root: Path = DEFAULT_RUN_ROOT
    v3_config_path: Path | None = None
    base_seed: int | None = None
    #: Where the Agent-12 R2 evidence manifest lives, as a ref, a path within
    #: that ref's tree and an optional pinned commit. The authoritative
    #: primary-domain gate reads it out of the object store; without it the run
    #: fails closed at the first stage, which is correct while the manifest does
    #: not exist.
    evidence_authority: AuthorityBinding | None = None
    #: Repository used purely as a ``git -C`` target for object reads. No path
    #: inside another worktree is ever constructed from it.
    repo: Path | None = None
    #: Where the Wave-1 calibration result will be, when there is one.
    wave1: W1.Wave1Binding = field(default_factory=W1.Wave1Binding)
    #: The predeclared headline quantities for the convergence diagnostic. The
    #: only judgement configuration supplies -- which outputs matter -- rather
    #: than how much divergence is acceptable, which is derived from the samples.
    headline_quantities: tuple[str, ...] = ()
    equivalence_tolerance: float = 1e-6
    witness_thresholds: tuple[WitnessThreshold, ...] = ()
    required_advisories: tuple[str, ...] = ()
    label: str = "V3_AUTONOMOUS_MODEL_RUN"
    #: ``package.module:factory`` naming the model-run executor, or empty.
    #:
    #: Named in configuration rather than chosen by the CLI so that which
    #: interfaces a run was driven through is recorded in the run manifest
    #: alongside everything else it was bound to. Empty means the unmounted
    #: default, which refuses every call.
    executor_factory: str = ""

    @classmethod
    def from_json(cls, path: str | Path) -> "SupervisorConfig":
        resolved = Path(path).resolve()
        raw = json.loads(resolved.read_text(encoding="utf-8"))
        base = resolved.parent

        def _path(value: str | None) -> Path | None:
            if not value:
                return None
            candidate = Path(value)
            return candidate if candidate.is_absolute() else (base / candidate).resolve()

        manifest_path = _path(raw.get("evidence_manifest"))
        if manifest_path is None:
            raise InputValidationError(
                f"Supervisor config {resolved} names no evidence_manifest. The frozen "
                "manifest is what decides which parameters may be fitted; without it "
                "there is nothing to authorise a search."
            )
        thresholds = tuple(
            WitnessThreshold(
                comparison=entry["comparison"],
                advisory_at=float(entry["advisory_at"]),
                failure_at=float(entry["failure_at"]),
                on_failure=entry.get("on_failure", S.HUMAN_REVIEW_REQUIRED),
                required=bool(entry.get("required", False)),
                units=entry.get("units", "absolute_divergence"),
            )
            for entry in raw.get("witness_thresholds", [])
        )
        run_root = _path(raw.get("run_root")) or DEFAULT_RUN_ROOT
        repo = _path(raw.get("repo"))
        authority_raw = raw.get("evidence_authority") or {}
        authority = (
            AuthorityBinding(
                ref=str(authority_raw["ref"]),
                path=str(authority_raw["path"]),
                generation=str(
                    authority_raw.get("generation", CURRENT_AUTHORITY_GENERATION)
                ),
                commit=str(authority_raw.get("commit", "")),
                repo=repo,
            )
            if authority_raw.get("ref")
            else None
        )
        wave1_raw = raw.get("wave1") or {}
        wave1 = W1.Wave1Binding(
            ref=str(wave1_raw.get("ref", W1.WAVE1_REF)),
            path=str(wave1_raw.get("path", "")),
            commit=str(wave1_raw.get("commit", "")),
            repo=repo,
        )
        return cls(
            evidence_manifest_path=manifest_path,
            evidence_authority=authority,
            repo=repo,
            wave1=wave1,
            run_root=run_root,
            v3_config_path=_path(raw.get("v3_config")),
            base_seed=(None if raw.get("base_seed") is None else int(raw["base_seed"])),
            headline_quantities=tuple(
                str(x) for x in raw.get("headline_quantities", [])
            ),
            equivalence_tolerance=float(raw.get("equivalence_tolerance", 1e-6)),
            witness_thresholds=thresholds,
            required_advisories=tuple(str(x) for x in raw.get("required_advisories", [])),
            label=str(raw.get("label", "V3_AUTONOMOUS_MODEL_RUN")),
            executor_factory=str(raw.get("executor", "")),
        )

    @property
    def convergence_policy(self) -> CV.ConvergencePolicy:
        """The declared diagnostic policy for both tier comparisons."""
        return CV.ConvergencePolicy(headline=tuple(self.headline_quantities))

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "evidence_manifest": str(self.evidence_manifest_path),
            "evidence_authority": (
                None if self.evidence_authority is None else self.evidence_authority.as_dict()
            ),
            "repo": None if self.repo is None else str(self.repo),
            "wave1": self.wave1.as_dict(),
            "run_root": str(self.run_root),
            "v3_config": None if self.v3_config_path is None else str(self.v3_config_path),
            "base_seed": self.base_seed,
            "convergence_policy": self.convergence_policy.as_dict(),
            "equivalence_tolerance": self.equivalence_tolerance,
            "witness_thresholds": [t.as_dict() for t in self.witness_thresholds],
            "required_advisories": list(self.required_advisories),
            "executor": self.executor_factory,
        }

    def build_executor(self) -> ModelRunExecutor:
        """Resolve the configured executor, or the refusing default.

        The import is done here rather than in the CLI so that every entry
        point -- CLI, wrapper, a future scheduler -- resolves it the same way,
        and so the refusal for a bad factory reads as a configuration error
        rather than an import traceback. The result is type-checked: an object
        that is not a :class:`~.execution.ModelRunExecutor` would fail later,
        one stage at a time, instead of here.
        """
        if not self.executor_factory.strip():
            return UnmountedEvidenceExecutor()
        target = self.executor_factory.strip()
        module_name, _, attribute = target.partition(":")
        if not module_name or not attribute:
            raise InputValidationError(
                f"Executor {target!r} is not of the form package.module:factory."
            )
        import importlib

        try:
            module = importlib.import_module(module_name)
            factory = getattr(module, attribute)
        except (ImportError, AttributeError) as exc:
            raise InputValidationError(
                f"Executor factory {target!r} could not be resolved: {exc}"
            ) from None
        executor = factory(self)
        if not isinstance(executor, ModelRunExecutor):
            raise InputValidationError(
                f"Executor factory {target!r} returned {type(executor).__name__}, which "
                "is not a ModelRunExecutor."
            )
        return executor


class Supervisor:
    """Drives one V3 model run through the state machine."""

    def __init__(
        self,
        config: SupervisorConfig,
        executor: ModelRunExecutor | None = None,
        *,
        run_id: str | None = None,
        clock: Callable[[], str] = utc_now,
    ) -> None:
        self.config = config
        self.executor = executor or UnmountedEvidenceExecutor()
        self.clock = clock
        self.run_id = run_id or new_run_id()
        self.run_dir = run_directory(self.run_id, config.run_root)
        self.state: RunState | None = None
        self._manifest: EV.SyntheticEvidenceManifest | None = None
        self._domain_manifest: EvidenceDomainManifest | None = None
        self._detail_cache: dict[str, dict[str, Any]] = {}
        self._guard: HoldoutGuard | None = None
        self._oracle: ScoringOracle | None = None
        self._approval: ApprovalRecord | None = None

    # -- evidence -------------------------------------------------------------

    @property
    def manifest(self) -> EV.SyntheticEvidenceManifest:
        if self._manifest is None:
            self._manifest = EV.load_evidence_manifest(self.config.evidence_manifest_path)
        return self._manifest

    @property
    def repo(self) -> Path:
        """The git object store the frozen evidence is read out of.

        Defaults to this package's own repository. It is a ``git -C`` target and
        nothing else: no filesystem path into any other worktree is built from
        it, here or in :mod:`.authority`.
        """
        if self.config.repo is not None:
            return Path(self.config.repo)
        return Path(__file__).resolve().parents[5]

    def resolve_authority(self) -> dict[str, Any]:
        """Resolve the R2 evidence authority without requiring it to exist.

        Reports what the configured ref resolves to and whether the manifest is
        present in that commit. A plan may see ``present: false``; a run may not
        proceed on it, and :meth:`domain_manifest` is where that refusal happens.
        """
        binding = self.config.evidence_authority
        if binding is None:
            return {
                "declared": False,
                "present": False,
                "reason": (
                    "Configuration names no evidence_authority. The authoritative "
                    "primary-domain gate reads the Agent-12 R2 manifest out of a pinned "
                    "commit, so with no authority declared there is no gate and the run "
                    "fails closed."
                ),
            }
        try:
            resolved = resolve_authority(binding, self.repo)
        except GovernanceBlock as exc:
            # An unresolvable ref is reported rather than raised, so ``plan``
            # stays a read-only report of the world as it is -- including the
            # world in which the evidence branch has not been published yet. The
            # run still fails closed: :meth:`domain_manifest` raises, and no
            # source is classified until it resolves.
            return {
                "declared": True,
                **binding.as_dict(),
                "present": False,
                "resolved_commit": "",
                "sha256": "",
                "absence_reason": str(exc),
            }
        return {"declared": True, **resolved.as_dict()}

    @property
    def domain_manifest(self) -> EvidenceDomainManifest:
        """The authoritative Agent-12 R2 manifest, or a fail-closed refusal."""
        if self._domain_manifest is None:
            binding = self.config.evidence_authority
            if binding is None:
                raise GovernanceBlock(
                    "No evidence authority is configured. The primary estimation domain "
                    "is decided by the frozen Agent-12 R2 evidence manifest, read from a "
                    "pinned commit; with none configured no source is classified, and an "
                    "unclassified source is refused for every purpose."
                )
            resolved = resolve_authority(binding, self.repo)
            self._domain_manifest = load_domain_manifest_from_authority(resolved)
        return self._domain_manifest

    def _wave1_expectation(self) -> W1.Wave1Expectation:
        """What this run independently holds, for a Wave-1 package to match.

        The candidate universe is computed over every axis the manifest
        authorises rather than over the axes this run will actually search, so
        the expectation does not change depending on whether Wave 1 has already
        settled one of them.
        """
        binding = self._detail(STAGE_CALIBRATION_DATASET)
        return W1.Wave1Expectation(
            execution_commit=self.config.wave1.commit,
            execution_tree=code_tree_digest(),
            evidence_manifest_sha256=self.domain_manifest.source_bytes_sha256,
            dataset_sha256=binding["sha256"],
            split_sha256=binding["split_sha256"],
            candidate_universe_digest=candidate_universe_digest(
                self._manifest_axes(), self._carry_forward_vector()
            ),
            scoring_oracle_digest=self._oracle_for_run().digest,
            experiment_config_sha256=binding["experiment_config_sha256"],
            field_admission_sha256=self.domain_manifest.manifest_digest,
        )

    def ingest_wave1(self, expectation: W1.Wave1Expectation | None = None) -> dict[str, Any]:
        """Read the Wave-1 result package if there is one. Absence is a state."""
        return W1.ingest(self.config.wave1, expectation, repo=self.repo)

    # -- plan -----------------------------------------------------------------

    def plan(self) -> dict[str, Any]:
        """Resolve the run without touching anything.

        Reads the frozen manifest and reports what would happen. It creates no
        run directory, acquires no lock, calls no executor method and writes no
        file -- a plan that had side effects would be a run.
        """
        manifest = self.manifest
        stages: list[dict[str, Any]] = []
        for state in S.SPINE:
            stage = STAGE_FOR_STATE.get(state)
            if stage is None:
                continue
            resolution = self._plan_stage_resolution(stage, manifest)
            stages.append({"state": state, "stage": stage, **resolution})

        authority = self.resolve_authority()
        parameters = {
            name: {
                "eligibility": record.eligibility,
                "circularity": record.circularity,
                "disposition": _planned_disposition(record),
                "production_semantics": D.PRODUCTION_VALUE_SEMANTICS[name],
                "current_value": record.current_value,
                "search_space": record.search_space,
                "rationale": record.rationale,
            }
            for name, record in sorted(manifest.parameters.items())
        }
        return {
            "mode": "PLAN_ONLY",
            "side_effects": "NONE",
            "evidence_authority": authority,
            "wave1": self.ingest_wave1(),
            "convergence_policy": self.config.convergence_policy.as_dict(),
            "filename_checks_role": FILENAME_CHECKS_ROLE,
            "supported_parameter_statuses": list(D.DISPOSITIONS),
            "label": self.config.label,
            "run_id": self.run_id,
            "run_directory": str(self.run_dir),
            "evidence_manifest": {
                "path": str(manifest.source_path),
                "manifest_id": manifest.manifest_id,
                "source_sha256": manifest.source_sha256,
                "digest": manifest.manifest_digest,
            },
            "primary_estimation_domain": list(manifest.primary_estimation_domain),
            "projection_season": manifest.projection_season,
            "real_world_role": manifest.real_witness_role,
            "required_inputs": self._required_inputs(),
            "parameters": parameters,
            "point_scale": manifest.point_scale.as_dict(),
            "parameters_fitted": list(manifest.fittable_parameters()),
            "parameters_fixed": list(manifest.parameters_in_class(EV.FIXED)),
            "parameters_blocked": list(
                manifest.parameters_in_class(EV.BLOCKED)
                + manifest.parameters_in_class(EV.MISSING)
            ),
            "parameters_circular": list(
                manifest.parameters_in_class(EV.CIRCULAR_NOT_IDENTIFIABLE)
            ),
            "stages": stages,
            "stages_skipped": [s["stage"] for s in stages if s["skipped"]],
            "human_gates": [
                {
                    "state": S.AWAITING_HUMAN_APPROVAL,
                    "action": APPROVAL_ACTION,
                    "binds_to": [
                        "recommendation_sha256",
                        "approved_vector",
                        "approved_dispositions",
                    ],
                }
            ],
            "human_gate_count": 1,
            "post_approval_states": list(S.POST_APPROVAL_STATES),
            "run_tiers": tier_policy.as_dict(),
            "retry_policy": RETRY_POLICY,
            "output_locations": self._output_locations(),
            "state_machine": {
                "state_count": len(S.STATES),
                "spine": list(S.SPINE),
                "halt_states": list(S.HALT_STATES),
            },
            "executor": self.executor.name,
        }

    def _plan_stage_resolution(
        self, stage: str, manifest: EV.SyntheticEvidenceManifest
    ) -> dict[str, Any]:
        if stage == STAGE_POINT_SCALE:
            resolution = manifest.point_scale.resolution
            return {
                "skipped": resolution != EV.POINT_SCALE_FIT_ALLOWED,
                "disposition": resolution,
                "note": manifest.point_scale.rationale,
            }
        if stage in (STAGE_COARSE_SEARCH, STAGE_REFINEMENT):
            axes = [p for p in SCALAR_SEARCH_PARAMETERS if manifest.parameters[p].fittable]
            return {
                "skipped": not axes,
                "disposition": "SEARCH" if axes else "NO_FITTABLE_AXES",
                "note": f"axes={axes}",
            }
        if stage == STAGE_FCS_ADAPTER:
            record = manifest.parameters["fcs_point_adapter"]
            return {
                "skipped": not record.fittable,
                "disposition": record.eligibility,
                "note": record.rationale,
            }
        if stage == STAGE_GAME_SD:
            record = manifest.parameters["game_sd_points"]
            return {
                "skipped": not record.fittable,
                "disposition": record.eligibility,
                "note": record.rationale,
            }
        return {"skipped": False, "disposition": "REQUIRED", "note": ""}

    def _required_inputs(self) -> list[dict[str, Any]]:
        authority = self.config.evidence_authority
        inputs = [
            {
                "name": "agent12_r2_evidence_manifest",
                "ref": None if authority is None else authority.ref,
                "path": None if authority is None else authority.path,
                "present": None,
                "role": (
                    "Authoritative primary-domain gate. Classifies every source by the "
                    "SHA-256 of its bytes; read from a pinned commit, never from a "
                    "working tree."
                ),
            },
            {
                "name": "synthetic_evidence_manifest",
                "path": str(self.config.evidence_manifest_path),
                "present": self.config.evidence_manifest_path.exists(),
                "role": "Decides which parameters may be fitted.",
            },
            {
                "name": "governed_calibration_dataset",
                "path": "<supplied by executor>",
                "present": None,
                "role": "Synthetic 2024/2025 estimation table, byte-registered.",
            },
            {
                "name": "real_world_witness_corpus",
                "sha256": EV.REAL_WITNESS_CORPUS_SHA256,
                "present": None,
                "role": EV.EXTERNAL_WITNESS_ONLY,
            },
        ]
        if self.config.v3_config_path is not None:
            inputs.append(
                {
                    "name": "v3_config",
                    "path": str(self.config.v3_config_path),
                    "present": self.config.v3_config_path.exists(),
                    "role": "Governed V3 configuration and mounted input paths.",
                }
            )
        return inputs

    def _output_locations(self) -> dict[str, str]:
        return {
            "run_directory": str(self.run_dir),
            "state": str(self.run_dir / "state.json"),
            "run_manifest": str(self.run_dir / "run_manifest.json"),
            "stage_results": str(self.run_dir / "stage_results"),
            "recommendation": str(self.run_dir / "recommendation"),
            "approval": str(self.run_dir / "approval"),
            "dev_500": str(self.run_dir / "dev_500"),
            "analysis_2000": str(self.run_dir / "analysis_2000"),
            "publish_10000": str(self.run_dir / "publish_10000"),
            "freeze": str(self.run_dir / "freeze"),
            "logs": str(self.run_dir / "logs"),
        }

    # -- lifecycle ------------------------------------------------------------

    def start(self) -> RunState:
        """Create the run directory and its manifest. Idempotent per run id."""
        if (self.run_dir / "state.json").exists():
            raise GovernanceBlock(
                f"Run {self.run_id} already exists at {self.run_dir}. Resume it rather "
                "than starting over: a second start would overwrite the state file that "
                "records what the first one already did."
            )
        state = RunState.create(self.run_id, self.run_dir)
        state.evidence_manifest_digest = self.manifest.manifest_digest
        state.input_digest = self.manifest.source_sha256
        state.save()
        write_run_manifest(
            self.run_dir,
            {
                "run_id": self.run_id,
                "label": self.config.label,
                "created_at": self.clock(),
                "config": self.config.as_dict(),
                "evidence_manifest": self.manifest.as_dict(),
                "state_machine": S.transition_summary(),
                "run_tiers": tier_policy.as_dict(),
                "retry_policy": RETRY_POLICY,
                "code_tree_digest": state.code_tree_digest,
                "human_gate": {
                    "state": S.AWAITING_HUMAN_APPROVAL,
                    "action": APPROVAL_ACTION,
                },
            },
        )
        self.state = state
        return state

    def _load(self) -> RunState:
        state = RunState.load(self.run_dir)
        self.state = state
        self._rehydrate()
        return state

    def _rehydrate(self) -> None:
        """Rebuild in-memory scratch from what is on disk.

        Every value a later stage needs was written by an earlier one, so a
        resumed supervisor reads the same files an auditor would. The holdout
        guard is restored from the state file rather than the stage results
        because ``released`` and ``scored`` are properties of the run, not of any
        single stage's output.
        """
        state = self.state
        assert state is not None
        self._detail_cache = {}
        directory = self.run_dir / "stage_results"
        if directory.exists():
            for path in sorted(directory.glob("*.json")):
                payload = json.loads(path.read_text(encoding="utf-8"))
                self._detail_cache[payload["stage"]] = payload.get("detail", {})
        if state.holdout:
            self._guard = HoldoutGuard(
                seal=HoldoutSeal(**state.holdout["seal"]),
                released=bool(state.holdout.get("released", False)),
                scored=bool(state.holdout.get("scored", False)),
                outcome=state.holdout.get("outcome"),
                release_record=dict(state.holdout.get("release_record", {})),
            )
        approval_path = self.run_dir / "approval" / "approval.json"
        if approval_path.exists():
            raw = json.loads(approval_path.read_text(encoding="utf-8"))
            self._approval = ApprovalRecord(
                run_id=raw["run_id"],
                action=raw["action"],
                recommendation_sha256=raw["recommendation_sha256"],
                approver=raw["approver"],
                approved_at=raw["approved_at"],
                bindings=RunBindings(**raw["bindings"]),
                approved_vector=dict(raw.get("approved_vector", {})),
                approved_dispositions=dict(raw.get("approved_dispositions", {})),
                human_answers=dict(raw.get("human_answers", {})),
                note=raw.get("note", ""),
            )

    def _detail(self, stage: str) -> dict[str, Any]:
        try:
            return self._detail_cache[stage]
        except KeyError:
            raise GovernanceBlock(
                f"Stage {stage} has no recorded result in run {self.run_id}. A later "
                "stage cannot proceed on evidence that was never written."
            ) from None

    # -- driving --------------------------------------------------------------

    def run(self) -> dict[str, Any]:
        """Start a new run and drive it as far as it is eligible to go."""
        self.start()
        return self._drive()

    def resume(self) -> dict[str, Any]:
        """Continue an existing run after verifying it is still the same run."""
        state = RunState.load(self.run_dir)
        state.require_resumable(observed_input_digest=self.manifest.source_sha256)
        self.state = state
        self._rehydrate()
        return self._drive(fresh=False)

    def _drive(self, *, fresh: bool = True) -> dict[str, Any]:
        if self.state is None:  # pragma: no cover - start/resume always set it
            self._load()
        state = self.state
        assert state is not None
        with RunLock(self.run_dir):
            if not fresh:
                state.require_resumable(observed_input_digest=self.manifest.source_sha256)
            while True:
                current = state.state
                if current in S.TERMINAL_STATES:
                    break
                if current == S.AWAITING_HUMAN_APPROVAL:
                    # The one normal stop. The run is healthy and complete up to
                    # here; what it needs is a person, and no amount of further
                    # deterministic work can substitute.
                    break
                stage = STAGE_FOR_STATE.get(current)
                if stage is None:
                    state.advance(
                        _next_state(current), reason="Completion marker; no work required."
                    )
                    continue
                if not self._step(stage):
                    break
        return self.status()

    def _step(self, stage: str) -> bool:
        """Run one stage and act on its result. Returns whether to continue."""
        state = self.state
        assert state is not None
        try:
            result = self._handlers()[stage]()
        except (GovernanceBlock, InputValidationError) as exc:
            result = S.StageResult(
                stage=stage,
                status=S.FAIL,
                summary=f"{type(exc).__name__}: {exc}",
                detail={"exception": type(exc).__name__, "message": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001 - unrecoverable execution error
            # An unrecoverable execution error is one of the three declared
            # stops. It is recorded as a stage result rather than propagated so
            # the run directory explains why the run ended.
            result = S.StageResult(
                stage=stage,
                status=S.FAIL,
                summary=f"Unrecoverable execution error: {type(exc).__name__}: {exc}",
                detail={"exception": type(exc).__name__, "message": str(exc)},
            )

        state.record_stage(result)
        self._detail_cache[result.stage] = dict(result.detail)

        if result.status == S.FAIL:
            state.advance(S.HALTED_FAILED, result=result, reason=result.summary)
            return False
        post_approval = state.state in S.POST_APPROVAL_STATES
        if result.status in (S.HUMAN_REVIEW_REQUIRED, S.RETRY_AUTOMATICALLY):
            # RETRY_AUTOMATICALLY reaching the driver means a stage asked for a
            # retry it did not perform. Retries are narrow and are executed
            # inside the stage that owns them, so this is a question for a human
            # rather than a loop for the driver to invent.
            if post_approval:
                # There is no human left to ask. The machine has no edge from
                # here to HALTED_FOR_HUMAN_REVIEW, so a post-approval stage that
                # asks a question is a defect in that stage, and it fails closed
                # rather than inventing the second gate the doctrine forbids.
                state.advance(
                    S.HALTED_FAILED,
                    result=result,
                    reason=(
                        f"{result.stage} reported {result.status} after the parameter "
                        "approval. The run has exactly one human gate and it is "
                        f"upstream of {S.DEV_500_REQUIRED}; a question raised here is a "
                        f"failure. {result.summary}"
                    ),
                )
                return False
            state.advance(
                S.HALTED_FOR_HUMAN_REVIEW, result=result, reason=result.summary
            )
            return False
        required = [a for a in result.advisories if a in self.config.required_advisories]
        if required and not post_approval:
            # Run policy may promote a pre-approval advisory to a stop. It may
            # not do so after the approval: PASS_WITH_ADVISORY continues through
            # every execution tier, which is what makes 500 -> 2,000 -> 10,000
            # automatic rather than merely usually automatic.
            state.advance(
                S.HALTED_FOR_HUMAN_REVIEW,
                result=result,
                reason=f"Advisory marked required by run policy: {required}",
            )
            return False
        state.advance(_next_state(state.state), result=result, reason=result.summary)
        return True

    def _handlers(self) -> dict[str, Callable[[], S.StageResult]]:
        return {
            STAGE_SYNTHETIC_EVIDENCE: self._stage_synthetic_evidence,
            STAGE_CALIBRATION_DATASET: self._stage_calibration_dataset,
            STAGE_PREFLIGHT: self._stage_preflight,
            STAGE_POINT_SCALE: self._stage_point_scale,
            STAGE_COARSE_SEARCH: self._stage_coarse_search,
            STAGE_REFINEMENT: self._stage_refinement,
            STAGE_VALIDATION: self._stage_validation,
            STAGE_HOLDOUT_SEAL: self._stage_holdout_seal,
            STAGE_HOLDOUT_RELEASE: self._stage_holdout_release,
            STAGE_HOLDOUT_SCORE: self._stage_holdout_score,
            STAGE_GAME_SD: self._stage_game_sd,
            STAGE_FCS_ADAPTER: self._stage_fcs_adapter,
            STAGE_WITNESS: self._stage_witness,
            STAGE_RECOMMENDATION: self._stage_recommendation,
            STAGE_APPROVAL_CHECK: self._stage_approval_check,
            gates.DEV_500_STAGE: self._stage_dev_500,
            gates.ANALYSIS_2000_STAGE: self._stage_analysis_2000,
            gates.PUBLISH_10000_STAGE: self._stage_publish_10000,
            gates.FINAL_FREEZE_STAGE: self._stage_final_freeze,
        }

    # -- stages ---------------------------------------------------------------

    def _authority_claims(self) -> list[EligibilityClaim]:
        """Every generation's claim about every governed parameter's eligibility.

        The run-local frozen manifest speaks for the generation it was produced
        under; the R2 manifest speaks for the current one. Both are recorded, and
        :func:`~.authority.resolve_claim` picks the winner by rank rather than by
        which one happened to be read last.
        """
        domain = self.domain_manifest
        claims = [
            EligibilityClaim(
                generation=domain.generation,
                subject=name,
                claim=domain.eligibility(name),
                source=f"{domain.manifest_id}@{domain.authority_commit}",
                rationale="Current evidence authority.",
            )
            for name in EV.GOVERNED_PARAMETERS
            if name in domain.parameter_eligibility
        ]
        prior_generation = next(
            (g for g in reversed(domain.supersedes) if g), ""
        )
        if prior_generation:
            claims.extend(
                EligibilityClaim(
                    generation=prior_generation,
                    subject=name,
                    claim=self.manifest.parameters[name].eligibility,
                    source=str(self.manifest.source_path),
                    rationale=self.manifest.parameters[name].rationale,
                )
                for name in EV.GOVERNED_PARAMETERS
            )
        return claims

    def _stage_synthetic_evidence(self) -> S.StageResult:
        manifest = self.manifest
        domain = self.domain_manifest
        claims = self._authority_claims()
        supersession = supersession_report(claims) if claims else {}
        # Where the two manifests disagree, the current authority decides and the
        # disagreement is written down. Nothing is edited to make it go away.
        overridden = sorted(
            name
            for name in EV.GOVERNED_PARAMETERS
            if name in domain.parameter_eligibility
            and domain.parameter_eligibility[name] != manifest.parameters[name].eligibility
        )
        wave1 = self.ingest_wave1()
        detail = {
            "authority": {
                **self.resolve_authority(),
                "manifest_id": domain.manifest_id,
                "generation": domain.generation,
                "manifest_sha256": domain.source_bytes_sha256,
                "manifest_digest": domain.manifest_digest,
                "primary_sources": [
                    s.source_id for s in domain.primary_sources()
                ],
                "witness_sources": [s.source_id for s in domain.witness_sources()],
                "forbidden_fields": sorted(domain.forbidden_fields),
            },
            "manifest_domain_enforcement": "AUTHORITATIVE_BY_SOURCE_SHA256",
            "filename_checks_role": FILENAME_CHECKS_ROLE,
            "supersession": supersession,
            "authority_overrides": overridden,
            "authoritative_eligibility": {
                name: self.eligibility_of(name) for name in EV.GOVERNED_PARAMETERS
            },
            "wave1": wave1,
            "manifest_id": manifest.manifest_id,
            "manifest_digest": manifest.manifest_digest,
            "source_sha256": manifest.source_sha256,
            "primary_estimation_domain": list(manifest.primary_estimation_domain),
            "projection_season": manifest.projection_season,
            "real_world_role": manifest.real_witness_role,
            "real_world_corpus_sha256": manifest.real_witness_sha256,
            "eligibility": {
                name: record.eligibility for name, record in sorted(manifest.parameters.items())
            },
            "circularity": {
                name: record.circularity for name, record in sorted(manifest.parameters.items())
            },
            "point_scale": manifest.point_scale.as_dict(),
            "synthetic_only_primary_calibration_enforced": True,
            "real_data_witness_only_enforced": True,
        }
        # A required parameter with no admissible evidence no longer fails the
        # run here. R1 refused, which was right when the only representable
        # outcome was a fitted value; under R2 the outcome is an epistemic
        # disposition, and MISSING_FAIL_CLOSED is one the recommendation can
        # carry to the human. What it cannot do is authorise execution, and that
        # refusal now lives at the approval gate where the human has answered.
        advisories = []
        for name in EV.GOVERNED_PARAMETERS:
            eligibility = self.eligibility_of(name)
            if eligibility == EV.FIT_ALLOWED:
                continue
            disposition = _planned_disposition(manifest.parameters[name], eligibility)
            advisories.append(
                f"{name} is {eligibility} -> {disposition}: "
                f"{manifest.parameters[name].rationale}"
            )
        if overridden:
            advisories.append(
                f"{domain.generation} supersedes the run-local manifest on {overridden}. "
                "The earlier record is retained unedited and no longer decides "
                "eligibility."
            )
        return _pass(
            STAGE_SYNTHETIC_EVIDENCE,
            f"Frozen synthetic evidence accepted under {domain.generation}.",
            detail,
            tuple(advisories),
        )

    def eligibility_of(self, parameter: str) -> str:
        """The eligibility the current authority assigns, superseding older ones.

        The R2 manifest wins wherever it speaks. Where it is silent about a
        governed parameter the run-local manifest stands, which is a gap the
        manifest should close rather than a licence -- a silent authority does
        not make a parameter fittable, it leaves the older classification in
        force, and the older classifications are conservative.
        """
        domain = self.domain_manifest
        if parameter in domain.parameter_eligibility:
            return domain.eligibility(parameter)
        return self.manifest.parameters[parameter].eligibility

    def _stage_calibration_dataset(self) -> S.StageResult:
        binding: DatasetBinding = self.executor.calibration_dataset()
        if binding.estimation_domain:
            EV.require_synthetic_only_primary_estimation_domain(binding.estimation_domain)
        self.domain_manifest.require_dataset_binding(
            binding.sha256, binding.split_sha256
        )
        shortfalls = volume_shortfalls(binding)
        detail = {
            **binding.as_dict(),
            "volume_shortfalls": shortfalls,
            "bound_to_evidence_manifest": self.domain_manifest.manifest_id,
        }
        if shortfalls:
            return S.StageResult(
                stage=STAGE_CALIBRATION_DATASET,
                status=S.FAIL,
                summary=f"Calibration dataset fails {len(shortfalls)} governed volume minimum(s).",
                detail=detail,
            )
        return _pass(
            STAGE_CALIBRATION_DATASET,
            f"Dataset {binding.dataset_id} registered at {binding.sha256}.",
            detail,
        )

    def _stage_preflight(self) -> S.StageResult:
        report = dict(self.executor.preflight())
        blockers = [str(b) for b in report.get("execution_blockers", [])]
        # The calibration blockers are what this run exists to close. Everything
        # else is a governance or custody gate that must already be clear before
        # a calibration run means anything.
        expected = [
            b
            for b in blockers
            if b.startswith("calibration.") or b == "governance.GAME_SD_CALIBRATION_OPEN"
        ]
        blocking = sorted(set(blockers) - set(expected))
        detail = {
            "report": report,
            "execution_blockers": blockers,
            "expected_calibration_blockers": sorted(expected),
            "blocking": blocking,
        }
        if blocking:
            return S.StageResult(
                stage=STAGE_PREFLIGHT,
                status=S.FAIL,
                summary=f"Preflight is blocked by non-calibration gates: {blocking}.",
                detail=detail,
            )
        advisories = (
            (
                "Calibration blockers remain open, which is the condition this run "
                f"exists to resolve: {sorted(expected)}.",
            )
            if expected
            else ()
        )
        return _pass(STAGE_PREFLIGHT, "Structural preflight passed.", detail, advisories)

    def _stage_point_scale(self) -> S.StageResult:
        scale = self.manifest.point_scale
        detail: dict[str, Any] = {"resolution": scale.resolution, "rationale": scale.rationale}
        if scale.resolution == EV.POINT_SCALE_BLOCKED:
            return S.StageResult(
                stage=STAGE_POINT_SCALE,
                status=S.FAIL,
                summary="Point scale is BLOCKED by the frozen manifest.",
                detail=detail,
            )
        if scale.resolution == EV.POINT_SCALE_CIRCULAR_NOT_IDENTIFIABLE:
            detail["value"] = None
            detail["identification_status"] = PARAMETER_UNIDENTIFIED
            return _pass(
                STAGE_POINT_SCALE,
                "Point scale is circular and not identifiable; no fit attempted.",
                detail,
                (
                    "point_scale: the evidence was generated by the mechanism whose "
                    "scale is being estimated, so it is not identified from its own "
                    f"outputs. {scale.rationale}",
                ),
            )
        if scale.resolution == EV.POINT_SCALE_FIXED_EXISTING_VALUE:
            detail["value"] = scale.value
            detail["identification_status"] = EV.FIXED
            return _pass(
                STAGE_POINT_SCALE,
                f"Point scale fixed at the governed value {scale.value}.",
                detail,
            )
        outcome = dict(self.executor.point_scale_identification(self._carry_forward_vector()))
        detail.update(outcome)
        if outcome.get("identification_status") != IDENTIFIED:
            return S.StageResult(
                stage=STAGE_POINT_SCALE,
                status=S.HUMAN_REVIEW_REQUIRED,
                summary=(
                    "Point-scale identification did not identify a value: "
                    f"{outcome.get('identification_status')!r}."
                ),
                detail=detail,
            )
        return _pass(
            STAGE_POINT_SCALE, f"Point scale identified at {outcome.get('value')}.", detail
        )

    def _manifest_axes(self) -> list[SearchAxis]:
        """Every scalar axis the authorities agree may be searched.

        Both must agree. The run-local manifest supplies the search space and the
        current authority supplies the permission, and a parameter the authority
        has reclassified away from FIT_ALLOWED is dropped here regardless of what
        search space it still carries.
        """
        axes = []
        for name in SCALAR_SEARCH_PARAMETERS:
            record = self.manifest.parameters[name]
            if self.eligibility_of(name) != EV.FIT_ALLOWED or not record.fittable:
                continue
            EV.require_fit_permitted(self.manifest, name)
            D.require_estimator_admissible(name, D.FIT_RESULT)
            axes.append(SearchAxis.from_search_space(name, record.search_space or {}))
        return axes

    def _axes(self) -> list[SearchAxis]:
        """The axes this run will actually search.

        The manifest-authorised set, minus anything a verified Wave-1 package has
        already settled. Re-fitting a parameter Wave 1 measured would produce a
        second answer bound to the same evidence, and there would be no principled
        way to choose between them.
        """
        settled = set(self._wave1_settled())
        return [axis for axis in self._manifest_axes() if axis.parameter not in settled]

    def _wave1_results(self) -> dict[str, Any]:
        detail = self._detail_cache.get(STAGE_COARSE_SEARCH) or self._detail_cache.get(
            STAGE_SYNTHETIC_EVIDENCE
        ) or {}
        return dict((detail.get("wave1") or {}).get("results") or {})

    def _wave1_settled(self) -> tuple[str, ...]:
        """Wave-1 parameters that arrived with a verified fit result."""
        return tuple(
            sorted(
                name
                for name, entry in self._wave1_results().items()
                if entry.get("status") == D.FIT_RESULT
            )
        )

    def _carry_forward_vector(self) -> dict[str, Any]:
        """The vector before any fitting: fixed values, and ``None`` elsewhere."""
        vector: dict[str, Any] = {}
        for name in EV.GOVERNED_PARAMETERS:
            record = self.manifest.parameters[name]
            vector[name] = (
                record.current_value
                if record.eligibility in EV.CARRY_FORWARD_ELIGIBILITY
                else None
            )
        scale = self.manifest.point_scale
        if scale.resolution == EV.POINT_SCALE_FIXED_EXISTING_VALUE:
            vector["point_scale"] = scale.value
        return vector

    def _oracle_for_run(self) -> ScoringOracle:
        """The scoring oracle, wrapped in this run's holdout guard.

        The executor is handed the *guarded* oracle, not the raw one. Anything
        it scores for itself -- finalists, sensitivity -- therefore goes through
        the same refusal a search does, so "no worker may inspect the holdout
        during candidate generation" holds for workers the supervisor does not
        itself drive.
        """
        if self._oracle is None:
            base = self.executor.scoring_oracle()
            guard = self._holdout_guard(optional=True)
            self._oracle = guarded_oracle(base, guard) if guard is not None else base
            self.executor.bind_oracle(self._oracle)
        return self._oracle

    def _holdout_guard(self, *, optional: bool = False) -> HoldoutGuard | None:
        if self._guard is None and not optional:
            raise GovernanceBlock(
                "The holdout has not been sealed in this run, so it cannot be released "
                "or scored."
            )
        return self._guard

    def _stage_coarse_search(self) -> S.StageResult:
        # A pre-sealing search must never be able to read the holdout. The guard
        # does not exist yet at this point in the run, so the oracle is wrapped
        # against a locked one that is created here and carried forward. It is
        # installed before anything else because the Wave-1 expectation reads the
        # oracle digest, and an unguarded oracle must never exist at all.
        if self._guard is None:
            self._pre_seal_guard()
        wave1 = self.ingest_wave1(
            self._wave1_expectation() if self.config.wave1.declared else None
        )
        # Published into the cache before the axes are built, because which axes
        # this run searches depends on what Wave 1 already settled.
        self._detail_cache[STAGE_COARSE_SEARCH] = {"wave1": wave1}
        settled = list(self._wave1_settled())
        axes = self._axes()
        detail: dict[str, Any] = {
            "wave1": wave1,
            "wave1_settled": settled,
            "axes": [a.as_dict() for a in axes],
            # Over the manifest-authorised axis set, not the searched one, so the
            # universe a Wave-1 package is checked against does not depend on
            # whether that package exists.
            "candidate_universe_digest": candidate_universe_digest(
                self._manifest_axes(), self._carry_forward_vector()
            ),
        }
        if not axes:
            return _pass(
                STAGE_COARSE_SEARCH,
                "No parameter is FIT_ALLOWED for this run; no search was run.",
                {**detail, "outcomes": {}, "vector": self._carry_forward_vector()},
                (
                    "No fittable axes: the current evidence authority authorises no "
                    f"search here. Wave-1 settled: {settled or 'none'}.",
                ),
            )
        oracle = self._oracle_for_run()
        context = self._carry_forward_vector()
        outcomes: dict[str, Any] = {}
        unidentified: list[str] = []
        for axis in axes:
            outcome = coarse_search(axis, oracle, split=_TRAINING_SPLIT, context=context)
            outcomes[axis.parameter] = outcome.as_dict()
            if outcome.identified:
                context[axis.parameter] = outcome.best_value
            else:
                unidentified.append(axis.parameter)
        detail["outcomes"] = outcomes
        detail["vector"] = dict(context)
        detail["unidentified"] = unidentified
        if unidentified:
            return S.StageResult(
                stage=STAGE_COARSE_SEARCH,
                status=S.HUMAN_REVIEW_REQUIRED,
                summary=(
                    "Coarse search remained boundary-bound after the declared expansion "
                    f"budget for: {unidentified}. Reported PARAMETER_UNIDENTIFIED rather "
                    "than accepting an edge value as a measurement."
                ),
                detail=detail,
            )
        expanded = sorted(
            name for name, o in outcomes.items() if o["expansions_used"] > 0
        )
        advisories = tuple(
            [f"Declared search range was expanded for: {expanded}."] if expanded else []
        ) + tuple(
            [f"Wave-1 supplied a verified fit result for: {settled}."] if settled else []
        )
        return _pass(
            STAGE_COARSE_SEARCH,
            f"Coarse search identified {len(axes)} axis/axes.",
            detail,
            advisories,
        )

    def _pre_seal_guard(self) -> None:
        """Install a locked guard before any candidate scoring happens.

        The real seal is taken at :data:`~.states.VALIDATION_COMPLETE`, once the
        experiment is frozen. Until then a placeholder guard -- locked, never
        released -- stands in, purely so that any holdout read during candidate
        generation raises rather than succeeding. Its bindings are deliberately
        not the real ones; it is a lock, not evidence, and it is replaced whole
        when the real seal is taken.
        """
        self._guard = HoldoutGuard(
            seal=HoldoutSeal(
                dataset_sha256="PRE_SEAL_PLACEHOLDER",
                split_sha256="PRE_SEAL_PLACEHOLDER",
                experiment_config_sha256="PRE_SEAL_PLACEHOLDER",
                candidate_universe_digest="PRE_SEAL_PLACEHOLDER",
                scoring_oracle_digest="PRE_SEAL_PLACEHOLDER",
            )
        )

    def _stage_refinement(self) -> S.StageResult:
        coarse_detail = self._detail(STAGE_COARSE_SEARCH)
        axes = {a.parameter: a for a in self._axes()}
        if not axes:
            return _pass(
                STAGE_REFINEMENT,
                "No axis was searched, so there is nothing to refine.",
                {
                    "outcomes": {},
                    "vector": dict(
                        coarse_detail.get("vector") or self._carry_forward_vector()
                    ),
                    "candidate_universe_digest": coarse_detail.get(
                        "candidate_universe_digest", ""
                    ),
                },
                ("Refinement ran no axis; the vector is unchanged from carry-forward.",),
            )
        oracle = self._oracle_for_run()
        context = dict(coarse_detail.get("vector") or self._carry_forward_vector())
        outcomes: dict[str, Any] = {}
        for name, axis in sorted(axes.items()):
            coarse = _outcome_from_dict(coarse_detail["outcomes"][name])
            outcome = refine(axis, coarse, oracle, split=_TRAINING_SPLIT, context=context)
            outcomes[name] = outcome.as_dict()
            context[name] = outcome.best_value

        detail: dict[str, Any] = {"outcomes": outcomes, "vector": dict(context)}
        advisories: list[str] = []

        if CONSTRAINT_PARAMETER in axes:
            finalists = list(self.executor.finalists(context))
            classification = classify_movement_cap(
                finalists,
                equivalence_tolerance=self.config.equivalence_tolerance,
                parameter=CONSTRAINT_PARAMETER,
            )
            detail["constraint_classification"] = classification
            if classification["identification_status"] == UNIDENTIFIED_NONBINDING:
                context[CONSTRAINT_PARAMETER] = None
                detail["vector"] = dict(context)
                advisories.append(
                    f"{CONSTRAINT_PARAMETER} is {UNIDENTIFIED_NONBINDING}: "
                    + classification["rationale"]
                )

        detail["candidate_universe_digest"] = coarse_detail.get("candidate_universe_digest", "")
        return _pass(
            STAGE_REFINEMENT,
            "Refinement complete.",
            detail,
            tuple(advisories),
        )

    def _selected_vector(self) -> dict[str, Any]:
        return dict(self._detail(STAGE_REFINEMENT)["vector"])

    def _stage_validation(self) -> S.StageResult:
        vector = self._selected_vector()
        report = dict(self.executor.validate(vector))
        split = str(report.get("split", "")).strip().lower()
        detail = {"vector": vector, "report": report}
        if split != _VALIDATION_SPLIT:
            return S.StageResult(
                stage=STAGE_VALIDATION,
                status=S.FAIL,
                summary=(
                    f"Validation evidence declares split {split!r}. Regime selection "
                    "reads the validation partition; a record that does not say which "
                    "partition produced it cannot be cited as validation evidence."
                ),
                detail=detail,
            )
        return _pass(STAGE_VALIDATION, "Validation complete.", detail)

    def _observed_seal(self) -> HoldoutSeal:
        binding = self._detail(STAGE_CALIBRATION_DATASET)
        universe = self._detail(STAGE_REFINEMENT).get("candidate_universe_digest") or self._detail(
            STAGE_COARSE_SEARCH
        ).get("candidate_universe_digest", "")
        return HoldoutSeal(
            dataset_sha256=binding["sha256"],
            split_sha256=binding["split_sha256"],
            experiment_config_sha256=binding["experiment_config_sha256"],
            candidate_universe_digest=universe or "NO_SEARCH_PERFORMED",
            scoring_oracle_digest=self._oracle_for_run().digest,
        )

    def _stage_holdout_seal(self) -> S.StageResult:
        seal = self._observed_seal()
        # Replace the placeholder lock wholesale. The real seal is the one the
        # release verifies against, and carrying a released flag across the swap
        # would be the one way a placeholder could authorise anything.
        self._guard = HoldoutGuard(seal=seal)
        state = self.state
        assert state is not None
        state.holdout = self._guard.as_dict()
        state.save()
        return _pass(
            STAGE_HOLDOUT_SEAL,
            f"Holdout sealed at {seal.seal_digest}.",
            {"seal": seal.as_dict(), "seal_digest": seal.seal_digest},
        )

    def _stage_holdout_release(self) -> S.StageResult:
        guard = self._holdout_guard()
        assert guard is not None
        state = self.state
        assert state is not None
        record = guard.release(
            current_state=state.state,
            observed=self._observed_seal(),
            released_at=self.clock(),
        )
        state.holdout = guard.as_dict()
        state.save()
        return _pass(STAGE_HOLDOUT_RELEASE, "Holdout released once.", {"release": record})

    def _stage_holdout_score(self) -> S.StageResult:
        guard = self._holdout_guard()
        assert guard is not None
        vector = self._selected_vector()
        outcome = dict(self.executor.score_holdout(vector))
        recorded = guard.record_score(outcome)
        state = self.state
        assert state is not None
        state.holdout = guard.as_dict()
        state.save()
        return _pass(
            STAGE_HOLDOUT_SCORE,
            "Holdout scored once.",
            {"vector": vector, "outcome": recorded},
        )

    def _stage_game_sd(self) -> S.StageResult:
        record = self.manifest.parameters["game_sd_points"]
        eligibility = self.eligibility_of("game_sd_points")
        vector = self._selected_vector()
        holdout_evidence = self._detail(STAGE_HOLDOUT_SCORE)["outcome"]
        if eligibility in EV.CARRY_FORWARD_ELIGIBILITY:
            return _pass(
                STAGE_GAME_SD,
                f"game_sd_points carried forward as {eligibility}.",
                {"value": record.current_value, "eligibility": eligibility},
            )
        if eligibility != EV.FIT_ALLOWED:
            return _classification_result(STAGE_GAME_SD, "game_sd_points", record, eligibility)
        outcome = dict(self.executor.game_sd(vector, holdout_evidence))
        detail = {"vector": vector, "outcome": outcome}
        if outcome.get("identification_status") != IDENTIFIED:
            return S.StageResult(
                stage=STAGE_GAME_SD,
                status=S.HUMAN_REVIEW_REQUIRED,
                summary=(
                    "Out-of-sample residual dispersion did not identify game_sd_points: "
                    f"{outcome.get('identification_status')!r}."
                ),
                detail=detail,
            )
        return _pass(
            STAGE_GAME_SD, f"game_sd_points identified at {outcome.get('value')}.", detail
        )

    def _stage_fcs_adapter(self) -> S.StageResult:
        record = self.manifest.parameters["fcs_point_adapter"]
        eligibility = self.eligibility_of("fcs_point_adapter")
        if eligibility in EV.CARRY_FORWARD_ELIGIBILITY:
            return _pass(
                STAGE_FCS_ADAPTER,
                f"FCS point adapter carried forward as {eligibility}.",
                {"value": record.current_value, "eligibility": eligibility},
            )
        if eligibility != EV.FIT_ALLOWED:
            # The state this stage completes into is explicitly named
            # "COMPLETE_OR_EXPLICITLY_UNIDENTIFIED". Under R2 an adapter with no
            # admissible evidence is a recorded epistemic outcome that travels to
            # the human gate; the fail-closed happens where production reads it,
            # not by refusing to produce a recommendation at all.
            return _classification_result(
                STAGE_FCS_ADAPTER, "fcs_point_adapter", record, eligibility
            )
        outcome = dict(self.executor.fcs_adapter(self._selected_vector()))
        detail = {"outcome": outcome, "eligibility": record.eligibility}
        if outcome.get("identification_status") != IDENTIFIED:
            return _pass(
                STAGE_FCS_ADAPTER,
                "FCS point adapter explicitly unidentified.",
                detail,
                (
                    "fcs_point_adapter is explicitly unidentified: "
                    f"{outcome.get('rationale', outcome.get('identification_status'))}",
                ),
            )
        return _pass(
            STAGE_FCS_ADAPTER,
            f"FCS point adapter identified at {outcome.get('value')}.",
            detail,
        )

    def _stage_witness(self) -> S.StageResult:
        selected = self._selected_vector()
        # The executor is handed a mutable copy of the selected vector, and the
        # copy is compared afterwards. A witness that writes back through the
        # mapping it was given is caught here rather than at review.
        probe = dict(selected)
        observations: Sequence[WitnessObservation] = self.executor.witness(probe)
        require_vector_unchanged(selected, probe)
        classification = classify_witness(
            observations, self.config.witness_thresholds or default_thresholds()
        )
        detail = {
            "vector": selected,
            "classification": classification,
            "corpus_sha256": self.manifest.real_witness_sha256,
            "role": EV.EXTERNAL_WITNESS_ONLY,
            "may_change_parameter_vector": False,
        }
        status = classification["status"]
        if status == S.FAIL:
            return S.StageResult(
                stage=STAGE_WITNESS,
                status=S.FAIL,
                summary="Real-world witness failed a required declared threshold.",
                detail=detail,
            )
        if status == S.HUMAN_REVIEW_REQUIRED:
            return S.StageResult(
                stage=STAGE_WITNESS,
                status=S.HUMAN_REVIEW_REQUIRED,
                summary=(
                    "Real-world witness breached a declared threshold whose declared "
                    "handling is human review. The synthetic parameter vector is "
                    "unchanged."
                ),
                detail=detail,
            )
        advisories = tuple(classification["advisories"])
        return _pass(
            STAGE_WITNESS,
            "Real-world witness complete; vector unchanged.",
            detail,
            advisories,
        )

    def _bindings(self) -> RunBindings:
        binding = self._detail(STAGE_CALIBRATION_DATASET)
        guard = self._holdout_guard()
        assert guard is not None
        return RunBindings(
            evidence_manifest_digest=self.manifest.manifest_digest,
            dataset_sha256=binding["sha256"],
            split_sha256=binding["split_sha256"],
            experiment_config_sha256=binding["experiment_config_sha256"],
            candidate_universe_digest=guard.seal.candidate_universe_digest,
            scoring_oracle_digest=guard.seal.scoring_oracle_digest,
            input_manifest_digest=binding["input_manifest_digest"],
            code_tree_digest=code_tree_digest(),
            holdout_seal_digest=guard.seal.seal_digest,
        )

    def _stage_recommendation(self) -> S.StageResult:
        manifest = self.manifest
        vector = self._selected_vector()
        refinement = self._detail(STAGE_REFINEMENT)
        coarse = self._detail(STAGE_COARSE_SEARCH)
        validation = self._detail(STAGE_VALIDATION)["report"]
        holdout = self._detail(STAGE_HOLDOUT_SCORE)["outcome"]
        witness_detail = self._detail(STAGE_WITNESS)["classification"]
        game_sd = self._detail(STAGE_GAME_SD)
        fcs = self._detail(STAGE_FCS_ADAPTER)
        scale = self._detail(STAGE_POINT_SCALE)
        sensitivity = dict(self.executor.sensitivity(vector))
        constraint = refinement.get("constraint_classification", {})
        wave1_results = self._wave1_results()

        entries: list[ParameterRecommendation] = []
        for name in EV.GOVERNED_PARAMETERS:
            record = manifest.parameters[name]
            eligibility = self.eligibility_of(name)
            outcome = refinement["outcomes"].get(name) or coarse["outcomes"].get(name) or {}
            value, identification, boundary = self._resolve_parameter(
                name,
                record,
                outcome,
                constraint,
                game_sd,
                fcs,
                scale,
                vector,
                eligibility,
                wave1_results.get(name) or {},
            )
            disposition, reason = _resolve_disposition(
                name, record, eligibility, identification, value
            )
            entries.append(
                ParameterRecommendation(
                    parameter=name,
                    eligibility=eligibility,
                    identification_status=identification,
                    disposition=disposition,
                    disposition_reason=reason,
                    boundary_status=boundary,
                    prior_value=record.prior_value,
                    current_value=record.current_value,
                    recommended_value=value,
                    objective_evidence={
                        "metric": self._oracle_for_run().metric,
                        "search_outcome": outcome,
                    },
                    validation_evidence=dict(validation),
                    holdout_evidence=dict(holdout),
                    sensitivity=dict(sensitivity.get(name, {})),
                    synthetic_domain_evidence={
                        "primary_estimation_domain": list(manifest.primary_estimation_domain),
                        "projection_season": manifest.projection_season,
                        "circularity": record.circularity,
                        "evidence_fields": list(record.evidence_fields),
                        "authority": self.domain_manifest.generation,
                        "authority_commit": self.domain_manifest.authority_commit,
                        "wave1": wave1_results.get(name) or {},
                    },
                    real_world_witness={
                        "status": witness_detail["status"],
                        "role": EV.EXTERNAL_WITNESS_ONLY,
                        "may_change_parameter_vector": False,
                    },
                    rationale=record.rationale,
                )
            )

        package = RecommendationPackage(
            run_id=self.run_id,
            generated_at=self.clock(),
            bindings=self._bindings(),
            parameters=tuple(entries),
            real_world_witness=witness_detail,
            point_scale_resolution=scale,
            notes=(
                "Primary calibration is synthetic-only; real football is "
                f"{EV.EXTERNAL_WITNESS_ONLY}.",
                "Domain admission is decided by the "
                f"{self.domain_manifest.generation} evidence manifest keyed on source "
                f"byte digests. Filename checks are {FILENAME_CHECKS_ROLE}.",
                "Parameters carry an epistemic disposition as well as a value. "
                "Approving this package approves both.",
                "This artifact recommends. It does not write canonical configuration.",
            ),
        )
        atomic_write_json(
            self.run_dir / "recommendation" / "recommendation.json", package.as_artifact()
        )
        state = self.state
        assert state is not None
        state.recommendation_sha256 = package.recommendation_sha256
        state.bindings = package.bindings.as_dict()
        state.save()
        requests = package.human_disposition_requests()
        detail = {
            "recommendation_sha256": package.recommendation_sha256,
            "bindings": package.bindings.as_dict(),
            "recommended_vector": package.recommended_vector(),
            "disposition_vector": package.disposition_vector(),
            "human_disposition_requests": [r.as_dict() for r in requests],
            "artifact": str(self.run_dir / "recommendation" / "recommendation.json"),
        }
        advisories = tuple(
            f"{r.parameter} is {r.disposition} and production reads it "
            f"({r.production_semantics}); the approval gate must supply a disposition. "
            f"{r.reason}"
            for r in requests
        )
        return _pass(
            STAGE_RECOMMENDATION,
            f"Recommendation {package.recommendation_sha256} ready for human approval "
            f"with {len(requests)} disposition question(s).",
            detail,
            advisories,
        )

    def _resolve_parameter(
        self,
        name: str,
        record: EV.ParameterEvidence,
        outcome: Mapping[str, Any],
        constraint: Mapping[str, Any],
        game_sd: Mapping[str, Any],
        fcs: Mapping[str, Any],
        scale: Mapping[str, Any],
        vector: Mapping[str, Any],
        eligibility: str,
        wave1: Mapping[str, Any],
    ) -> tuple[Any, str, str]:
        """Resolve one parameter's recommended value, and how it was arrived at."""
        if wave1.get("status") == D.FIT_RESULT:
            return wave1.get("value"), IDENTIFIED, "WAVE1_VERIFIED"
        if eligibility in EV.CARRY_FORWARD_ELIGIBILITY:
            return record.current_value, EV.FIXED, "NOT_SEARCHED"
        if eligibility in (EV.CIRCULAR_NOT_IDENTIFIABLE, EV.WITNESS_ONLY):
            return None, PARAMETER_UNIDENTIFIED, "NOT_SEARCHED"
        if eligibility in EV.REFUSING_ELIGIBILITY:
            return None, PARAMETER_UNIDENTIFIED, "NOT_SEARCHED"
        if name == "point_scale":
            return (
                scale.get("value"),
                scale.get("identification_status", PARAMETER_UNIDENTIFIED),
                "NOT_SEARCHED",
            )
        if name == "game_sd_points":
            value = (game_sd.get("outcome") or {}).get("value", game_sd.get("value"))
            status = IDENTIFIED if value is not None else PARAMETER_UNIDENTIFIED
            return value, status, "NOT_SEARCHED"
        if name == "fcs_point_adapter":
            outcome_fcs = fcs.get("outcome") or {}
            status = outcome_fcs.get("identification_status", PARAMETER_UNIDENTIFIED)
            value = outcome_fcs.get("value") if status == IDENTIFIED else None
            return value, status, "NOT_SEARCHED"
        if name == CONSTRAINT_PARAMETER and constraint:
            status = constraint["identification_status"]
            if status == UNIDENTIFIED_NONBINDING:
                return None, UNIDENTIFIED_NONBINDING, outcome.get("boundary_status", "")
        return (
            vector.get(name),
            outcome.get("identification_status", PARAMETER_UNIDENTIFIED),
            outcome.get("boundary_status", ""),
        )

    # -- approval and execution ----------------------------------------------

    def approve(
        self,
        *,
        recommendation_sha256: str,
        approver: str,
        action: str = APPROVAL_ACTION,
        dispositions: Mapping[str, Mapping[str, Any]] | None = None,
        note: str = "",
    ) -> dict[str, Any]:
        """Grant the one human approval.

        Binds the recommendation digest, the approved value vector and the
        approved disposition vector in one act. ``dispositions`` answers every
        question the recommendation raised: ``{parameter: {"value": ...,
        "status": ...}}``, where a status carrying no value -- an FCS adapter left
        :data:`~.dispositions.MISSING_FAIL_CLOSED`, say -- passes ``None``.
        """
        state = RunState.load(self.run_dir)
        self.state = state
        self._rehydrate()
        artifact_path = self.run_dir / "recommendation" / "recommendation.json"
        if not artifact_path.exists():
            raise GovernanceBlock(
                f"Run {self.run_id} has no recommendation artifact to approve."
            )
        artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        package = _package_from_artifact(artifact)
        with RunLock(self.run_dir):
            record = approve_recommendation(
                package,
                action=action,
                recommendation_sha256=recommendation_sha256,
                approver=approver,
                approved_at=self.clock(),
                current_state=state.state,
                active_recommendation_sha256=state.recommendation_sha256,
                observed_bindings=self._bindings(),
                dispositions=dispositions,
                note=note,
            )
            atomic_write_json(self.run_dir / "approval" / "approval.json", record.as_artifact())
            self._approval = record
            state.approval_digest = record.approval_digest
            state.advance(
                S.PARAMETERS_APPROVED,
                reason=f"{action} bound to recommendation {record.recommendation_sha256}.",
            )
        return {
            "run_id": self.run_id,
            "state": state.state,
            "approval_digest": record.approval_digest,
            "recommendation_sha256": record.recommendation_sha256,
            "approver": record.approver,
            "approved_vector": dict(record.approved_vector),
            "approved_dispositions": dict(record.approved_dispositions),
            "execution_obstacles": D.execution_obstacles(
                record.approved_vector, record.approved_dispositions
            ),
            "use_site_fail_closed": D.use_site_fail_closed(
                record.approved_vector, record.approved_dispositions
            ),
        }

    def _stage_approval_check(self) -> S.StageResult:
        state = self.state
        assert state is not None
        approval = require_approval_for_execution(
            self._approval,
            recommendation_sha256=state.recommendation_sha256,
            observed_bindings=self._bindings(),
        )
        fail_closed = D.use_site_fail_closed(
            approval.approved_vector, approval.approved_dispositions
        )
        detail = {
            "approval_digest": approval.approval_digest,
            "recommendation_sha256": approval.recommendation_sha256,
            "approver": approval.approver,
            "approved_vector": dict(approval.approved_vector),
            "approved_dispositions": dict(approval.approved_dispositions),
            "execution_obstacles": [],
            "use_site_fail_closed": fail_closed,
        }
        return _pass(
            STAGE_APPROVAL_CHECK,
            "Approval verified against re-derived bindings, values and dispositions.",
            detail,
            tuple(fail_closed),
        )

    def _approved_vector(self) -> dict[str, Any]:
        """What production runs with, after the human answered.

        Not :meth:`_selected_vector`. The selected vector is what the search
        produced; the approved vector is that plus every disposition a human
        supplied at the gate, and running the first would silently discard the
        second.
        """
        if self._approval is None:
            raise GovernanceBlock(
                "No approval is recorded, so there is no approved vector to execute."
            )
        return dict(self._approval.approved_vector)

    def _execute_tier(self, tier: tier_policy.RunTier) -> tuple[dict[str, Any], dict[str, Any]]:
        vector = self._approved_vector()
        bindings = self._expected_execution_bindings()
        outcome = run_with_temp_root_retry(
            lambda basetemp: dict(
                self.executor.execute_tier(
                    tier.name, vector, bindings=bindings, basetemp=basetemp
                )
            )
        )
        return outcome.value, outcome.as_dict()

    def _stage_dev_500(self) -> S.StageResult:
        report, retry = self._execute_tier(tier_policy.DEV)
        atomic_write_json(self.run_dir / "dev_500" / "report.json", report)
        result = gates.gate_dev_500(report)
        return _with_detail(result, {"report": report, "retry": retry})

    def _stage_analysis_2000(self) -> S.StageResult:
        report, retry = self._execute_tier(tier_policy.ANALYSIS)
        atomic_write_json(self.run_dir / "analysis_2000" / "report.json", report)
        dev_report = self._detail(gates.DEV_500_STAGE)["report"]
        result = gates.gate_analysis_2000(
            report,
            dev_report=dev_report,
            policy=self.config.convergence_policy,
        )
        return _with_detail(result, {"report": report, "retry": retry})

    def _expected_execution_bindings(self) -> dict[str, str]:
        state = self.state
        assert state is not None
        bindings = dict(self._bindings().as_dict())
        bindings["recommendation_sha256"] = state.recommendation_sha256
        bindings["approval_digest"] = state.approval_digest
        if self.config.base_seed is not None:
            bindings["run_seed"] = str(self.config.base_seed)
        return bindings

    def _stage_publish_10000(self) -> S.StageResult:
        report, retry = self._execute_tier(tier_policy.PUBLISH)
        atomic_write_json(self.run_dir / "publish_10000" / "report.json", report)
        result = gates.gate_publish_10000(
            report,
            expected_bindings=self._expected_execution_bindings(),
            analysis_report=self._detail(gates.ANALYSIS_2000_STAGE)["report"],
            policy=self.config.convergence_policy,
        )
        return _with_detail(result, {"report": report, "retry": retry})

    def _stage_final_freeze(self) -> S.StageResult:
        expected = self._expected_execution_bindings()
        report = dict(self.executor.freeze(self._approved_vector(), expected))
        result = gates.gate_final_freeze(
            report,
            tier_paths=tier_policy.PUBLISH.paths,
            upstream_passed={
                "dev_500": gates.DEV_500_STAGE in self._detail_cache,
                "analysis_2000": gates.ANALYSIS_2000_STAGE in self._detail_cache,
                "publish_10000": gates.PUBLISH_10000_STAGE in self._detail_cache,
            },
            expected_bindings=expected,
        )
        # No final-looking output until the gate has passed.
        if result.continues:
            atomic_write_json(self.run_dir / "freeze" / "freeze.json", report)
        return _with_detail(result, {"report": report})

    # -- reporting ------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        state = self.state
        if state is None:
            state = RunState.load(self.run_dir)
            self.state = state
        return {
            "run_id": state.run_id,
            "run_directory": str(self.run_dir),
            "state": state.state,
            "terminal": state.state in S.TERMINAL_STATES,
            "awaiting_human_approval": state.state == S.AWAITING_HUMAN_APPROVAL,
            "halt_reason": state.halt_reason,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "code_tree_digest": state.code_tree_digest,
            "evidence_manifest_digest": state.evidence_manifest_digest,
            "recommendation_sha256": state.recommendation_sha256,
            "approval_digest": state.approval_digest,
            "stages_completed": sorted(state.stage_digests),
            "stage_digests": dict(state.stage_digests),
            "holdout": dict(state.holdout),
            "history": [dict(h) for h in state.history],
            "next_action": _next_action(state.state),
        }


# --- module helpers ----------------------------------------------------------


def _next_state(current: str) -> str:
    """The single spine successor of ``current``."""
    return S.SPINE[S.state_index(current) + 1]


def _pass(
    stage: str,
    summary: str,
    detail: Mapping[str, Any],
    advisories: tuple[str, ...] = (),
) -> S.StageResult:
    return S.StageResult(
        stage=stage,
        status=S.PASS_WITH_ADVISORY if advisories else S.PASS,
        summary=summary,
        detail=dict(detail),
        advisories=advisories,
    )


def _with_detail(result: S.StageResult, extra: Mapping[str, Any]) -> S.StageResult:
    from dataclasses import replace

    return replace(result, detail={**result.detail, **dict(extra)})


def _classification_result(
    stage: str,
    parameter: str,
    record: EV.ParameterEvidence,
    eligibility: str,
) -> S.StageResult:
    """Report a parameter the current authority says must not be fitted here.

    R1 failed the run when such a parameter was also required, because a
    recommendation could only carry a fitted value and a required parameter
    without one was a hole with nowhere to go. R2 gives it somewhere to go: the
    disposition travels to the single human gate, the approver answers it, and
    the fail-closed happens against the *approved* vector in
    :func:`~.approval.require_approval_for_execution`. Failing here instead would
    mean the human never sees the question that only they can answer.
    """
    disposition = _planned_disposition(record, eligibility)
    detail = {
        "parameter": parameter,
        "eligibility": eligibility,
        "disposition": disposition,
        "circularity": record.circularity,
        "rationale": record.rationale,
        "required": record.required,
        "production_semantics": D.PRODUCTION_VALUE_SEMANTICS[parameter],
        "value": None,
    }
    return _pass(
        stage,
        f"{parameter} explicitly not identified ({eligibility} -> {disposition}).",
        detail,
        (
            f"{parameter} is {eligibility} -> {disposition} and carries no value. "
            f"Production reads it as {D.PRODUCTION_VALUE_SEMANTICS[parameter]}; the "
            f"approval gate must dispose of it. {record.rationale}",
        ),
    )


def _planned_disposition(record: EV.ParameterEvidence, eligibility: str = "") -> str:
    """The disposition a parameter is expected to carry.

    For a fittable parameter this is a *plan*: :data:`~.dispositions.FIT_RESULT`
    is what it becomes if the search identifies a value, and
    :func:`_resolve_disposition` is what decides afterwards whether it did. For
    every other parameter it is the outcome, because nothing further will be
    measured.

    A manifest may declare a disposition explicitly, which is how
    ``recent_form_weights`` arrives as :data:`~.dispositions.UNIDENTIFIED`
    rather than as the ``MISSING_FAIL_CLOSED`` its eligibility alone would imply
    -- "the evidence exists and does not identify this" and "there is no
    evidence" are different findings, and the manifest is entitled to say which
    one it means.
    """
    resolved = eligibility or record.eligibility
    if resolved != EV.FIT_ALLOWED and record.declared_disposition:
        return record.declared_disposition
    implied = D.disposition_for_eligibility(resolved)
    return implied if implied is not None else D.FIT_RESULT


def _resolve_disposition(
    name: str,
    record: EV.ParameterEvidence,
    eligibility: str,
    identification: str,
    value: Any,
) -> tuple[str, str]:
    """The disposition and reason one recommendation entry carries.

    A fittable parameter is :data:`~.dispositions.FIT_RESULT` only if a search
    actually identified a value. Permission plus a failed search is
    :data:`~.dispositions.UNIDENTIFIED`, and reporting it as a fit result would
    describe an absent measurement as a present one.
    """
    if eligibility != EV.FIT_ALLOWED and record.declared_disposition:
        # Honoured only where nothing was measured. A declared disposition on a
        # parameter that was actually searched would describe the search's
        # result without having watched it.
        return record.declared_disposition, (
            record.disposition_reason or record.rationale
        )
    if eligibility == EV.FIT_ALLOWED:
        if identification == IDENTIFIED and value is not None:
            return D.FIT_RESULT, ""
        return D.UNIDENTIFIED, (
            f"{name} was authorised for fitting and the objective did not identify a "
            f"value ({identification}). {record.rationale}"
        )
    disposition = D.disposition_for_eligibility(eligibility)
    assert disposition is not None
    return disposition, record.rationale


def _outcome_from_dict(payload: Mapping[str, Any]) -> SearchOutcome:
    return SearchOutcome(
        parameter=payload["parameter"],
        best_value=payload["best_value"],
        best_score=payload["best_score"],
        boundary_status=payload["boundary_status"],
        identification_status=payload["identification_status"],
        expansions_used=int(payload["expansions_used"]),
        max_expansions=int(payload["max_expansions"]),
        declared_lower=float(payload["declared_lower"]),
        declared_upper=float(payload["declared_upper"]),
        final_lower=float(payload["final_lower"]),
        final_upper=float(payload["final_upper"]),
        evaluations=tuple((float(v), float(s)) for v, s in payload.get("evaluations", [])),
        refinement_rounds_used=int(payload.get("refinement_rounds_used", 0)),
        notes=tuple(payload.get("notes", ())),
    )


def _package_from_artifact(artifact: Mapping[str, Any]) -> RecommendationPackage:
    """Rebuild a recommendation package from its on-disk artifact.

    The digest is recomputed from the rebuilt object rather than read out of the
    file. A recommendation that carried its own digest and was trusted for it
    would be self-attesting, which is the failure
    :mod:`..calibration_evidence` exists to close.
    """
    return RecommendationPackage(
        run_id=artifact["run_id"],
        generated_at=artifact["generated_at"],
        bindings=RunBindings(**artifact["bindings"]),
        parameters=tuple(
            ParameterRecommendation(
                parameter=entry["parameter"],
                eligibility=entry["eligibility"],
                identification_status=entry["identification_status"],
                disposition=entry.get("disposition", D.UNIDENTIFIED),
                disposition_reason=entry.get("disposition_reason", ""),
                boundary_status=entry["boundary_status"],
                prior_value=entry["prior_value"],
                current_value=entry["current_value"],
                recommended_value=entry["recommended_value"],
                objective_evidence=entry.get("objective_evidence", {}),
                validation_evidence=entry.get("validation_evidence", {}),
                holdout_evidence=entry.get("holdout_evidence", {}),
                sensitivity=entry.get("sensitivity", {}),
                synthetic_domain_evidence=entry.get("synthetic_domain_evidence", {}),
                real_world_witness=entry.get("real_world_witness", {}),
                rationale=entry.get("rationale", ""),
            )
            for entry in artifact["parameters"]
        ),
        real_world_witness=artifact.get("real_world_witness", {}),
        point_scale_resolution=artifact.get("point_scale_resolution", {}),
        notes=tuple(artifact.get("notes", ())),
    )


def _next_action(state: str) -> str:
    if state == S.COMPLETE:
        return "None. The run is complete and frozen."
    if state == S.AWAITING_HUMAN_APPROVAL:
        return (
            f"Human parameter approval: {APPROVAL_ACTION} bound to the recommendation "
            "SHA-256."
        )
    if state == S.HALTED_FAILED:
        return "Investigate the recorded failure. A halted run is not resumed."
    if state == S.HALTED_FOR_HUMAN_REVIEW:
        return "A human decision is required. A halted run is not resumed."
    return f"Resume; the supervisor continues from {state}."
