"""Command line for the C2 Baxter RMSE harness.

Separate from the V3 engine CLI on purpose: this is an experiment runner, and it
must not be reachable from the path that produces V3 outputs.

    python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.baxter_harness.cli \
        status --contract config/dynamic_weekly_mc_v3/experimental/baxter_data_contract.json

Run identity is supplied on the command line rather than read from the clock, so
the same inputs produce the same bytes. ``evaluate`` therefore requires
``--run-id`` and ``--as-of``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ..calibration import CALIBRATION_FIELDS, load_candidate_regimes
from ..config import V3Config
from ..errors import GovernanceBlock, InputValidationError
from .contract import READY_FOR_DATA, load_contract, resolve_contract
from .evaluate import RunContext, evaluate_regimes
from .interface import interface_contract


def _resolution(args: argparse.Namespace):
    contract = load_contract(args.contract)
    hfa = None
    if args.v3_config:
        hfa = V3Config.from_json(args.v3_config).hfa_baseline_points
    return contract, resolve_contract(contract, v3_hfa_baseline_points=hfa)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="c2-baxter-rmse-harness",
        description="Experimental Baxter Rating RMSE evaluation. Never promotes.",
    )
    parser.add_argument("command", choices=["status", "interface", "evaluate"])
    parser.add_argument("--contract", help="Path to the versioned data contract document.")
    parser.add_argument("--v3-config", help="Governed V3 config supplying home-field points.")
    parser.add_argument("--regimes", help="Experimental candidate regime file.")
    parser.add_argument("--run-id", help="Caller-supplied run identifier.")
    parser.add_argument("--as-of", help="Caller-supplied ISO-8601 run timestamp.")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--include-holdout",
        action="store_true",
        help="Confirmation run for a single already-selected regime.",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "interface":
            print(json.dumps(interface_contract(), indent=2, sort_keys=True))
            return 0

        if not args.contract:
            parser.error("--contract is required")

        contract, resolution = _resolution(args)

        if args.command == "status":
            payload = resolution.as_dict()
            payload["calibration_axes"] = list(CALIBRATION_FIELDS)
            payload["harness"] = "C2_BAXTER_RMSE_HARNESS"
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0 if resolution.status != "BLOCKED" else 2

        if not (args.run_id and args.as_of):
            parser.error("evaluate requires --run-id and --as-of")

        regimes = load_candidate_regimes(Path(args.regimes)) if args.regimes else []
        config_version = "UNSPECIFIED"
        model_version = "UNSPECIFIED"
        if args.v3_config:
            config = V3Config.from_json(args.v3_config)
            config_version = config.configuration_version
            model_version = config.model_version

        if resolution.status == READY_FOR_DATA:
            payload = evaluate_regimes(
                resolution,
                regimes,
                context=RunContext(
                    run_id=args.run_id,
                    as_of=args.as_of,
                    model_version=model_version,
                    configuration_version=config_version,
                    seed=args.seed,
                ),
            )
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        payload = evaluate_regimes(
            resolution,
            regimes,
            context=RunContext(
                run_id=args.run_id,
                as_of=args.as_of,
                model_version=model_version,
                configuration_version=config_version,
                seed=args.seed,
            ),
            include_holdout=args.include_holdout,
        )
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    except (GovernanceBlock, InputValidationError) as exc:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "harness": "C2_BAXTER_RMSE_HARNESS",
                    "reason": str(exc),
                    "error": type(exc).__name__,
                },
                indent=2,
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
