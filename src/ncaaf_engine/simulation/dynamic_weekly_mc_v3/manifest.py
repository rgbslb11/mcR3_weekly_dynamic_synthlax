from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from .config import V3Config
from .inputs import sha256_file


def build_input_manifest(config: V3Config, execution_blockers: list[str] | None = None) -> dict[str, object]:
    paths = config.inputs
    names = [
        "canonical_master_md",
        "unified_preseason_ratings_xlsx",
        "schedule_xlsx",
        "model_parameters_xlsx",
        "bracket_regime_xlsx",
        "playoff_calendar_xlsx",
        "fcs_reconciled_master_xlsx",
        "v2_1_control_xlsx",
    ]
    files = {}
    for name in names:
        p = getattr(paths, name)
        files[name] = {"path": str(p), "sha256": sha256_file(p), "bytes": p.stat().st_size}
    if paths.aac_divisions_csv and paths.aac_divisions_csv.exists():
        files["aac_divisions_csv"] = {
            "path": str(paths.aac_divisions_csv),
            "sha256": sha256_file(paths.aac_divisions_csv),
            "bytes": paths.aac_divisions_csv.stat().st_size,
        }
    return {
        "model_name": config.model_name,
        "model_version": config.model_version,
        "configuration_version": config.configuration_version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "input_files": files,
        "execution_blockers": config.execution_blockers() if execution_blockers is None else execution_blockers,
    }


def write_manifest(
    config: V3Config, output_dir: Path, execution_blockers: list[str] | None = None
) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    p = output_dir / "input_manifest.json"
    p.write_text(
        json.dumps(build_input_manifest(config, execution_blockers), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return p
