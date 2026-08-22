"""Autonomous V3 model-run supervisor.

Drives the remaining SYTHALAX V3 model run -- frozen synthetic evidence,
calibration, validation, holdout, the single human approval gate, then 500 DEV,
2,000 ANALYSIS, 10,000 PUBLISH and final freeze -- as one deterministic state
machine.

It orchestrates. It does not choose parameter values, does not implement model
mathematics, and does not approve anything. What may be fitted is read out of a
frozen evidence manifest; what is computed is delegated to
:class:`~.execution.ModelRunExecutor`, whose default refuses every call because
the frozen evidence bundle does not exist yet.
"""

from .execution import DatasetBinding, ModelRunExecutor, UnmountedEvidenceExecutor
from .states import StageResult
from .supervisor import Supervisor, SupervisorConfig

__all__ = [
    "DatasetBinding",
    "ModelRunExecutor",
    "StageResult",
    "Supervisor",
    "SupervisorConfig",
    "UnmountedEvidenceExecutor",
]
