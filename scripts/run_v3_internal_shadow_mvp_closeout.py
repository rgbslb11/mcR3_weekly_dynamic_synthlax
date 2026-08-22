"""Execute the V3 INTERNAL / SHADOW / TEST_ONLY MVP closeout, end to end.

One entry point, in the order the governance requires: install the R5 items
through their gates, emit the calibration evidence, confirm the blocker state is
zero for the MVP scope, then run the three governed tiers in ascending order.

The simulation gate is real. ``run_tier`` re-runs preflight and refuses a tier
whose execution blockers are non-empty, so a tier cannot be reached by calling
this script with the governance uninstalled.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ncaaf_engine.simulation.dynamic_weekly_mc_v3 import (  # noqa: E402
    blocker_report,
    fcs,
    mvp_control,
    run_tier as tier_policy,
    season_run,
)
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.config import V3Config  # noqa: E402
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.engine import DynamicWeeklyMCV3  # noqa: E402
from ncaaf_engine.simulation.dynamic_weekly_mc_v3.textio import write_json_lf  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reference" / "dynamic_weekly_mc_v3" / "mvp_control"
MVP_CONFIG = ROOT / "config" / "dynamic_weekly_mc_v3" / "v3_internal_shadow_mvp.json"
BASELINE_CONFIG = ROOT / "config" / "dynamic_weekly_mc_v3" / "v3_experimental.json"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    baseline = DynamicWeeklyMCV3(V3Config.from_json(BASELINE_CONFIG)).preflight()
    before = sorted(str(b) for b in baseline["execution_blockers"])
    print(f"pre-ruling blockers: {len(before)}")

    activation = season_run.activate_internal_shadow_mvp(ROOT)
    calibration = activation["calibration_report"]
    write_json_lf(OUT / mvp_control.CONTROL_CALIBRATION_REPORT, calibration)
    write_json_lf(
        OUT / mvp_control.CONTROL_PROMOTION_RECORD, activation["calibration_promotion"]
    )
    print("calibration emitted")

    config = V3Config.from_json(MVP_CONFIG)
    report = DynamicWeeklyMCV3(config).preflight()
    after = sorted(str(b) for b in report["execution_blockers"])
    print(f"INTERNAL_SHADOW_MVP blockers: {len(after)} {after}")
    if after:
        print("SIMULATION GATE CLOSED — refusing to run any tier", file=sys.stderr)
        return 2

    delta = blocker_report.internal_shadow_mvp_delta()
    write_json_lf(
        OUT / "V3_MVP_BLOCKER_STATE_R1.json",
        {
            "scope": mvp_control.MVP_SCOPE,
            "rulings": activation["rulings"],
            "measured_before": before,
            "measured_after": after,
            "measured_retired": sorted(set(before) - set(after)),
            "measured_remaining": after,
            "register_delta": delta,
            "measured_matches_register": (
                set(before) == set(delta["before"]) and set(after) == set(delta["after"])
            ),
            "formal_global_scope_blockers": delta["formal_global_scope"],
            "real_world_validation": mvp_control.REAL_WORLD_VALIDATION_STATUS,
        },
    )

    results = []
    for tier in tier_policy.GOVERNED_TIERS:
        start = time.time()
        result = season_run.run_tier(
            config, ROOT, paths=tier.paths, output_dir=OUT / "runs"
        )
        elapsed = time.time() - start
        print(
            f"{result.tier:9s} paths={result.paths:6d} "
            f"passed={result.validation['passed']} "
            f"output={result.output_hash[:16]} {elapsed:6.1f}s"
        )
        if not result.validation["passed"]:
            print(f"VALIDATION FAILED: {result.validation['findings']}", file=sys.stderr)
            return 3
        results.append(result)

    parameter_hashes = {r.parameter_set_hash for r in results}
    write_json_lf(
        OUT / "V3_MVP_SIMULATION_RUNS_R1.json",
        {
            "scope": mvp_control.MVP_SCOPE,
            "calibration_evidence": mvp_control.MVP_CALIBRATION_STATUS,
            "real_world_validation": mvp_control.REAL_WORLD_VALIDATION_STATUS,
            "value_bearing": False,
            "market_action_taken": False,
            "deployment_performed": False,
            "fcs_scale": fcs.governed_fcs_scale_as_dict(),
            "fcs_venue_clause": fcs.fcs_venue_clause_as_dict(),
            "tiers": [r.as_dict() for r in results],
            "same_model_semantics_across_tiers": len(parameter_hashes) == 1,
            "shared_parameter_set_hash": sorted(parameter_hashes),
            "only_path_quantity_changed": True,
            "publish_freeze_eligible_tiers": [
                r.tier for r in results if tier_policy.tier_for_paths(r.paths).publish_freeze
            ],
        },
    )
    print("runs emitted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
