from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import board_of_record, committee_policy, fcs, hfa
from .errors import GovernanceBlock


DEFAULT_PRIOR_DECAY = {
    0: 1.00,  # preseason
    1: 0.80,  # W1 audit-only; not promoted
    2: 0.60,
    3: 0.40,
    4: 0.20,
    5: 0.00,
}


@dataclass(frozen=True)
class ReratingCalibration:
    weekly_performance_residual_coefficient: float | None = None
    weekly_movement_cap_points: float | None = None
    recent_form_weights: tuple[float, ...] | None = None
    blowout_treatment: dict[str, Any] | None = None
    game_sd_points: float | None = None
    sample_size_regularization: dict[str, Any] | None = None

    def blockers(self) -> list[str]:
        missing: list[str] = []
        fields = {
            "weekly_performance_residual_coefficient": self.weekly_performance_residual_coefficient,
            "weekly_movement_cap_points": self.weekly_movement_cap_points,
            "recent_form_weights": self.recent_form_weights,
            "blowout_treatment": self.blowout_treatment,
            "game_sd_points": self.game_sd_points,
            "sample_size_regularization": self.sample_size_regularization,
        }
        for name, value in fields.items():
            if value is None:
                missing.append(name)
        return missing


@dataclass(frozen=True)
class InputPaths:
    canonical_master_md: Path
    unified_preseason_ratings_xlsx: Path
    schedule_xlsx: Path
    model_parameters_xlsx: Path
    bracket_regime_xlsx: Path
    playoff_calendar_xlsx: Path
    fcs_reconciled_master_xlsx: Path
    v2_1_control_xlsx: Path
    aac_divisions_csv: Path | None = None
    #: Board of Record named by ruling R2-BOARD-OF-RECORD. Not mounted here.
    board_of_record_xlsx: Path | None = None


@dataclass(frozen=True)
class V3Config:
    model_name: str
    model_version: str
    configuration_version: str
    paths: int
    base_seed: int
    weeks: tuple[int, ...]
    first_promoted_rerating_after_week: int
    prior_decay: dict[int, float]
    hfa_baseline_points: float | None
    freeze_strength_after_selection: bool
    write_path_level_parquet: bool
    inputs: InputPaths
    calibration: ReratingCalibration
    fcs_translation_policy: str | None = None
    #: Retired by ruling R2-COMMITTEE-TB. Accepted only as ``None``.
    committee_tiebreak_strength_source: str | None = None
    #: The structured deterministic chain that replaces it.
    committee_tiebreak_policy: str | None = None

    @classmethod
    def from_json(cls, path: str | Path) -> "V3Config":
        path = Path(path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        base = path.parent
        ip = raw["inputs"]

        def p(name: str) -> Path:
            value = Path(ip[name])
            return value if value.is_absolute() else (base / value).resolve()

        def optional(name: str) -> Path | None:
            value = ip.get(name)
            if not value:
                return None
            candidate = Path(value)
            return candidate if candidate.is_absolute() else (base / candidate).resolve()

        aac_path = optional("aac_divisions_csv")
        board_path = optional("board_of_record_xlsx")

        cal = raw.get("calibration", {})
        weights = cal.get("recent_form_weights")
        return cls(
            model_name=raw["model_name"],
            model_version=raw["model_version"],
            configuration_version=raw["configuration_version"],
            paths=int(raw["paths"]),
            base_seed=int(raw["base_seed"]),
            weeks=tuple(int(x) for x in raw.get("weeks", range(1, 17))),
            first_promoted_rerating_after_week=int(raw["first_promoted_rerating_after_week"]),
            prior_decay={int(k): float(v) for k, v in raw["prior_decay"].items()},
            hfa_baseline_points=(None if raw.get("hfa_baseline_points") is None else float(raw["hfa_baseline_points"])),
            freeze_strength_after_selection=bool(raw["freeze_strength_after_selection"]),
            write_path_level_parquet=bool(raw.get("write_path_level_parquet", True)),
            inputs=InputPaths(
                canonical_master_md=p("canonical_master_md"),
                unified_preseason_ratings_xlsx=p("unified_preseason_ratings_xlsx"),
                schedule_xlsx=p("schedule_xlsx"),
                model_parameters_xlsx=p("model_parameters_xlsx"),
                bracket_regime_xlsx=p("bracket_regime_xlsx"),
                playoff_calendar_xlsx=p("playoff_calendar_xlsx"),
                fcs_reconciled_master_xlsx=p("fcs_reconciled_master_xlsx"),
                v2_1_control_xlsx=p("v2_1_control_xlsx"),
                aac_divisions_csv=aac_path,
                board_of_record_xlsx=board_path,
            ),
            calibration=ReratingCalibration(
                weekly_performance_residual_coefficient=cal.get("weekly_performance_residual_coefficient"),
                weekly_movement_cap_points=cal.get("weekly_movement_cap_points"),
                recent_form_weights=tuple(float(x) for x in weights) if weights is not None else None,
                blowout_treatment=cal.get("blowout_treatment"),
                game_sd_points=cal.get("game_sd_points"),
                sample_size_regularization=cal.get("sample_size_regularization"),
            ),
            fcs_translation_policy=raw.get("fcs_translation_policy"),
            committee_tiebreak_strength_source=raw.get("committee_tiebreak_strength_source"),
            committee_tiebreak_policy=raw.get("committee_tiebreak_policy"),
        )

    def prior_weight_after_week(self, week: int) -> float:
        if week <= 5:
            return self.prior_decay[week]
        return 0.0

    def audit_only_after_week(self, week: int) -> bool:
        return week < self.first_promoted_rerating_after_week

    def execution_blockers(self) -> list[str]:
        """Execution blockers produced by the configuration itself.

        Each governed field clears only when it carries the value its ruling
        sets, not merely when it is non-null. A configuration holding the legacy
        HFA, or an invented FCS policy, is still blocked.
        """
        blockers = [f"calibration.{x}" for x in self.calibration.blockers()]
        if not hfa.hfa_conflict_resolved(self.hfa_baseline_points):
            blockers.append("hfa_baseline_points")
        if self.fcs_translation_policy != fcs.FCS_FIXED_ELO_POLICY:
            blockers.append("fcs_translation_policy")
        # The retired strength-source concept must stay null; the structured
        # chain replaces it. A populated retired field is a hard refusal, not a
        # blocker, so it cannot be mistaken for progress.
        committee_policy.reject_retired_strength_source(self.committee_tiebreak_strength_source)
        if self.committee_tiebreak_policy != committee_policy.COMMITTEE_TIEBREAK_POLICY:
            blockers.append("committee_tiebreak_policy")
        if self.inputs.aac_divisions_csv is None or not self.inputs.aac_divisions_csv.exists():
            blockers.append("inputs.aac_divisions_csv")
        board_status = board_of_record.board_of_record_status(
            self.inputs.board_of_record_xlsx
        )
        if board_status["blocker"] is not None:
            blockers.append(board_of_record.BOARD_OF_RECORD_BLOCKER)
        return blockers

    def require_executable(self) -> None:
        blockers = self.execution_blockers()
        if blockers:
            raise GovernanceBlock("V3 execution blocked: " + ", ".join(blockers))

    def validate_architecture(self) -> None:
        if self.paths != 10_000:
            raise ValueError("V3 requires exactly 10,000 independent paths")
        if self.first_promoted_rerating_after_week != 2:
            raise ValueError("First promoted rerating must occur after Week 2")
        if self.weeks != tuple(range(1, 17)):
            raise ValueError("V3 weekly loop must cover Weeks 1 through 16")
        if self.prior_decay != DEFAULT_PRIOR_DECAY:
            raise ValueError("Preseason-prior decay does not match the governed V3 schedule")
