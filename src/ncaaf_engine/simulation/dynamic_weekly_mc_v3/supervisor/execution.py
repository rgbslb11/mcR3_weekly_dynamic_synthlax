"""The interface the supervisor drives, and the default that refuses to.

The supervisor orchestrates; it does not do model mathematics. Every numerical
act in the run -- registering the calibration dataset, scoring a candidate,
validating, releasing and scoring the holdout, fitting game SD, identifying the
FCS adapter, running 500/2,000/10,000 paths, freezing -- is delegated through
:class:`ModelRunExecutor` to whatever governed interface actually implements it.

That split is why this lane can build and test the whole mechanism without
running a real calibration or a real season. A test supplies a deterministic
executor and exercises every transition; production supplies one backed by the
real interfaces. Neither changes the supervisor.

:class:`UnmountedEvidenceExecutor` is the default, and it refuses every call.
That is the correct behaviour for this repository today: the frozen synthetic
evidence bundle does not exist yet, so a supervisor run with no executor should
stop with a governance refusal naming what is missing, not proceed on defaults.
A default that returned plausible empty results would let a run reach
``PARAMETER_RECOMMENDATION_READY`` having measured nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from ..calibration_contract import MINIMUM_VOLUME_REQUIREMENTS
from ..errors import GovernanceBlock
from .search import FinalistObservation, ScoringOracle
from .witness import WitnessObservation

__all__ = [
    "DatasetBinding",
    "ModelRunExecutor",
    "UnmountedEvidenceExecutor",
    "volume_shortfalls",
]


@dataclass(frozen=True)
class DatasetBinding:
    """The registered calibration dataset, as digests and volume facts.

    Every field here is something a later gate compares or counts. ``sha256``,
    ``split_sha256`` and ``experiment_config_sha256`` become three of the five
    holdout seal bindings; the volume fields are checked against the governed
    minima in :mod:`..calibration_contract` rather than against numbers restated
    here.
    """

    dataset_id: str
    sha256: str
    split_sha256: str
    experiment_config_sha256: str
    input_manifest_digest: str
    rows: int
    distinct_seasons: int
    holdout_rows: int
    minimum_weeks_per_team_per_season: int
    estimation_domain: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "sha256": self.sha256,
            "split_sha256": self.split_sha256,
            "experiment_config_sha256": self.experiment_config_sha256,
            "input_manifest_digest": self.input_manifest_digest,
            "rows": self.rows,
            "distinct_seasons": self.distinct_seasons,
            "holdout_rows": self.holdout_rows,
            "minimum_weeks_per_team_per_season": self.minimum_weeks_per_team_per_season,
            "estimation_domain": list(self.estimation_domain),
            "notes": list(self.notes),
        }


def volume_shortfalls(binding: DatasetBinding) -> list[str]:
    """Which governed minimum volumes the dataset fails, and by how much.

    The minima are read from :data:`..calibration_contract.MINIMUM_VOLUME_REQUIREMENTS`
    rather than restated, so the contract stays the single place they are set and
    a change there cannot leave this gate quietly checking the old numbers.
    """
    checks = (
        ("minimum_distinct_seasons", binding.distinct_seasons),
        ("minimum_observations_total", binding.rows),
        ("minimum_holdout_observations", binding.holdout_rows),
        (
            "minimum_weeks_per_team_per_season",
            binding.minimum_weeks_per_team_per_season,
        ),
    )
    shortfalls = []
    for key, observed in checks:
        required = MINIMUM_VOLUME_REQUIREMENTS[key]
        if observed < required:
            reason = MINIMUM_VOLUME_REQUIREMENTS[f"{key}_reason"]
            shortfalls.append(
                f"{key}: observed {observed}, governed minimum {required}. {reason}"
            )
    return shortfalls


class ModelRunExecutor:
    """What the supervisor calls to make something actually happen.

    Every method raises by default. Subclassing and overriding only what a
    particular run needs is deliberate: an executor that silently inherits a
    working no-op for a stage it never implemented would let that stage pass.
    """

    name: str = "abstract"

    # -- evidence and inputs --------------------------------------------------

    def calibration_dataset(self) -> DatasetBinding:
        """Register and return the governed calibration dataset binding."""
        raise NotImplementedError

    def preflight(self) -> Mapping[str, Any]:
        """Structural preflight over the mounted inputs."""
        raise NotImplementedError

    def scoring_oracle(self) -> ScoringOracle:
        """The deterministic objective candidates are scored against."""
        raise NotImplementedError

    def bind_oracle(self, oracle: ScoringOracle) -> None:
        """Receive the *guarded* oracle the supervisor will use.

        A no-op by default, unlike every other method here, because this is a
        notification rather than a computation: an executor that does its own
        scoring -- enumerating finalists, measuring sensitivity -- must score
        through this object so that a holdout read during candidate generation
        is refused. One that scores some other way is not made safe by a
        ``NotImplementedError`` here, and one that needs no oracle of its own is
        not broken by the absence of an override.
        """

    # -- identification -------------------------------------------------------

    def point_scale_identification(
        self, context: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Deterministic scale-identification, when the manifest permits a fit."""
        raise NotImplementedError

    def finalists(self, vector: Mapping[str, Any]) -> Sequence[FinalistObservation]:
        """Evidentially equivalent finalists, with constraint-binding counts."""
        raise NotImplementedError

    def sensitivity(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        """Local sensitivity of the objective around the selected vector."""
        raise NotImplementedError

    def validate(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        """Score the selected vector on the validation split."""
        raise NotImplementedError

    def score_holdout(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        """Score once, on the holdout, after release."""
        raise NotImplementedError

    def game_sd(
        self, vector: Mapping[str, Any], holdout_evidence: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        """Out-of-sample residual dispersion, and the game SD it implies."""
        raise NotImplementedError

    def fcs_adapter(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        """Identify the FCS point adapter, or report it unidentified."""
        raise NotImplementedError

    def witness(self, vector: Mapping[str, Any]) -> Sequence[WitnessObservation]:
        """Real-football comparisons. Diagnostic only."""
        raise NotImplementedError

    # -- execution tiers ------------------------------------------------------

    def execute_tier(
        self,
        tier_name: str,
        vector: Mapping[str, Any],
        *,
        bindings: Mapping[str, str],
        basetemp: Path | None = None,
    ) -> Mapping[str, Any]:
        """Run one governed tier and return the report its gate reads.

        ``bindings`` is what the run must stamp onto its output: the config,
        input, approval and seed digests the publish gate compares against. They
        are passed in rather than discovered by the executor so that a report
        which fails the binding check fails because the *run* diverged, not
        because the executor and the supervisor computed the digests differently.

        ``basetemp`` is supplied on a retry after the recognised Windows
        temp-root race and is ``None`` otherwise; an executor that has no
        temporary state may ignore it.
        """
        raise NotImplementedError

    def freeze(
        self, vector: Mapping[str, Any], bindings: Mapping[str, str]
    ) -> Mapping[str, Any]:
        """Produce the final freeze report."""
        raise NotImplementedError


@dataclass
class UnmountedEvidenceExecutor(ModelRunExecutor):
    """The default. Refuses everything, and says why.

    Used when no executor is supplied. A supervisor run against it stops at the
    first stage with a :class:`GovernanceBlock` naming the missing evidence,
    which is the honest state of this repository: the frozen synthetic evidence
    bundle has not been produced, so nothing downstream of it can run.
    """

    name: str = "UNMOUNTED_EVIDENCE"
    reason: str = (
        "No model-run executor is bound to this supervisor. The frozen synthetic "
        "evidence bundle, the governed calibration dataset and the deterministic "
        "scoring interface are not mounted, so no calibration, identification or "
        "path execution can be performed. This lane builds the orchestration "
        "mechanism; it does not run the model."
    )
    refusals: list[str] = field(default_factory=list)

    def _refuse(self, what: str) -> Any:
        self.refusals.append(what)
        raise GovernanceBlock(f"{what} is unavailable. {self.reason}")

    def calibration_dataset(self) -> DatasetBinding:
        return self._refuse("Calibration dataset registration")

    def preflight(self) -> Mapping[str, Any]:
        return self._refuse("Preflight")

    def scoring_oracle(self) -> ScoringOracle:
        return self._refuse("Scoring oracle")

    def point_scale_identification(self, context: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._refuse("Point-scale identification")

    def finalists(self, vector: Mapping[str, Any]) -> Sequence[FinalistObservation]:
        return self._refuse("Finalist enumeration")

    def sensitivity(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._refuse("Sensitivity analysis")

    def validate(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._refuse("Validation scoring")

    def score_holdout(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._refuse("Holdout scoring")

    def game_sd(
        self, vector: Mapping[str, Any], holdout_evidence: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        return self._refuse("Game SD estimation")

    def fcs_adapter(self, vector: Mapping[str, Any]) -> Mapping[str, Any]:
        return self._refuse("FCS adapter identification")

    def witness(self, vector: Mapping[str, Any]) -> Sequence[WitnessObservation]:
        return self._refuse("Real-world witness")

    def execute_tier(
        self,
        tier_name: str,
        vector: Mapping[str, Any],
        *,
        bindings: Mapping[str, str],
        basetemp: Path | None = None,
    ) -> Mapping[str, Any]:
        return self._refuse(f"{tier_name} execution")

    def freeze(
        self, vector: Mapping[str, Any], bindings: Mapping[str, str]
    ) -> Mapping[str, Any]:
        return self._refuse("Final freeze")
