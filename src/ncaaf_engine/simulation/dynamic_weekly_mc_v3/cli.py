from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import V3Config
from .engine import DynamicWeeklyMCV3
from .errors import GovernanceBlock, InputValidationError
from .manifest import write_manifest


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sythalax-dynamic-weekly-mc-v3")
    parser.add_argument("command", choices=["validate", "run", "show-blockers"])
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-root", default="output/dynamic_weekly_mc_v3")
    args = parser.parse_args(argv)

    config = V3Config.from_json(args.config)
    engine = DynamicWeeklyMCV3(config)

    if args.command == "show-blockers":
        try:
            report = engine.preflight()
            blockers = report["execution_blockers"]
        except (GovernanceBlock, InputValidationError, ValueError) as exc:
            blockers = config.execution_blockers() + [f"preflight.{exc}"]
        payload = {"status": "BLOCKED" if blockers else "READY", "blockers": blockers}
        print(json.dumps(payload, indent=2))
        return 0

    output_root = Path(args.output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    run_id = _run_id()

    report: dict[str, object] | None = None
    try:
        if args.command == "validate":
            out = output_root / f"PREFLIGHT_{run_id}"
            report = engine.validate_to_directory(out)
            print(json.dumps(report, indent=2, sort_keys=True))
            return 0

        # Never create final-looking V3 summaries until all gates pass.
        report = engine.require_execution_ready()
        out = output_root / f"RUN_{run_id}.incomplete"
        out.mkdir(parents=True, exist_ok=False)
        write_manifest(config, out)
        (out / "preflight_report.json").write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        # Full 10,000-path + postseason execution is intentionally unreachable until the
        # governed rerating and remaining data policies are unblocked and implemented.
        raise GovernanceBlock("Full V3 run gate reached; rerating/postseason production activation remains blocked by governance.")
    except (GovernanceBlock, InputValidationError, ValueError) as exc:
        blocked = output_root / f"BLOCKED_{run_id}"
        blocked.mkdir(parents=True, exist_ok=True)
        if report is None:
            try:
                report = engine.preflight()
            except (GovernanceBlock, InputValidationError, ValueError):
                report = None
        payload = {
            "status": "BLOCKED",
            "model": config.model_name,
            "model_version": config.model_version,
            "configuration_version": config.configuration_version,
            "reason": str(exc),
            "execution_blockers": (
                report["execution_blockers"] if report is not None else config.execution_blockers()
            ),
            "preflight_status": None if report is None else report.get("status"),
        }
        (blocked / "BLOCKED.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(payload, indent=2, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
