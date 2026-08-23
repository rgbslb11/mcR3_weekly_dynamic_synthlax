"""Autonomous V3 model-run supervisor.

Drives the remaining SYTHALAX V3 model run -- frozen synthetic evidence,
calibration, validation, holdout, the single human approval gate, then 500 DEV,
2,000 ANALYSIS, 10,000 PUBLISH and final freeze -- as one deterministic state
machine.

It orchestrates. It does not choose parameter values, does not implement model
mathematics, and does not approve anything. Which sources may estimate the
primary vector is decided by the frozen Agent-12 R2 evidence manifest, read from
a pinned commit and keyed on source byte digests; what is computed is delegated
to :class:`~.execution.ModelRunExecutor`, whose default refuses every call
because the frozen evidence bundle does not exist yet.

Every governed parameter reaches the single human gate carrying one of nine
epistemic dispositions alongside its value, and the approval binds both. After
that gate the tiers run to completion or fail: the convergence diagnostics are
derived from the run samples, and the post-approval states have no edge to a
second human stop.
"""

from .authority import AuthorityBinding, CURRENT_AUTHORITY_GENERATION
from .convergence import ConvergencePolicy
from .dispositions import DISPOSITIONS
from .domain_manifest import EvidenceDomainManifest, SourceRecord
from .execution import DatasetBinding, ModelRunExecutor, UnmountedEvidenceExecutor
from .states import StageResult
from .supervisor import Supervisor, SupervisorConfig
from .wave1 import Wave1Binding, Wave1Expectation, Wave1Package

__all__ = [
    "AuthorityBinding",
    "CURRENT_AUTHORITY_GENERATION",
    "ConvergencePolicy",
    "DISPOSITIONS",
    "DatasetBinding",
    "EvidenceDomainManifest",
    "ModelRunExecutor",
    "SourceRecord",
    "StageResult",
    "Supervisor",
    "SupervisorConfig",
    "UnmountedEvidenceExecutor",
    "Wave1Binding",
    "Wave1Expectation",
    "Wave1Package",
]
