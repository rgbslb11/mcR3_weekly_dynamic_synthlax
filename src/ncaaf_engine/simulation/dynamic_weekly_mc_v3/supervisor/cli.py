"""Operator interface for the autonomous V3 model-run supervisor.

Five verbs, matching what an operator actually needs to do::

    python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor plan   --config <path>
    python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor run    --config <path>
    python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor status --config <path> --run-id <id>
    python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor approve --config <path> \
        --run-id <id> --recommendation-sha <sha> --approver <name>
    python -m ncaaf_engine.simulation.dynamic_weekly_mc_v3.supervisor resume --config <path> --run-id <id>

Exit codes follow the V3 CLI's convention: ``0`` for a run that did what it was
asked, ``2`` for a governance refusal or a halted run. A run that stops at the
human approval gate exits ``0`` -- it did exactly what it was supposed to do, and
an operator scripting the pipeline should not have to treat the designed stop as
an error. A run that halted for review or failure exits ``2``, because those are
stops that need somebody.

``plan`` has no side effects. It creates no run directory, acquires no lock and
calls no model interface, so it is safe to run against production configuration
at any time.

Which model interfaces a run is driven through is named in the configuration's
``executor`` key, not chosen here, so it is recorded in the run manifest with
everything else the run was bound to. With no ``executor`` the unmounted default
refuses every call, and a run against it halts on the first stage that needs one.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from ..errors import GovernanceBlock, InputValidationError
from . import states as S
from .runstore import run_directory
from .supervisor import Supervisor, SupervisorConfig

__all__ = ["main"]


def _emit(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def _supervisor(args: argparse.Namespace) -> Supervisor:
    config = SupervisorConfig.from_json(args.config)
    if getattr(args, "run_root", None):
        # ``replace`` rather than a field-by-field rebuild: an override that has
        # to restate every field silently drops the next one that is added.
        config = replace(config, run_root=Path(args.run_root))
    return Supervisor(
        config, config.build_executor(), run_id=getattr(args, "run_id", None) or None
    )


def _exit_code_for(state: str) -> int:
    if state in (S.HALTED_FAILED, S.HALTED_FOR_HUMAN_REVIEW):
        return 2
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sythalax-v3-supervisor")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("plan", "Resolve the run and report it. No side effects."),
        ("run", "Start a new run and drive every eligible deterministic stage."),
        ("status", "Report one run's state."),
        ("resume", "Continue an existing run after verifying code and input identity."),
        ("approve", "Grant the single human parameter approval."),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("--config", required=True, help="Supervisor configuration JSON.")
        p.add_argument("--run-root", default=None, help="Override the run root directory.")
        if name in ("status", "resume", "approve"):
            p.add_argument("--run-id", required=True)
        else:
            p.add_argument("--run-id", default=None)
        if name == "approve":
            p.add_argument("--recommendation-sha", required=True)
            p.add_argument("--approver", required=True)
            p.add_argument("--action", default=None)
            p.add_argument("--note", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        supervisor = _supervisor(args)

        if args.command == "plan":
            _emit(supervisor.plan())
            return 0

        if args.command == "run":
            report = supervisor.run()
            _emit(report)
            return _exit_code_for(report["state"])

        if args.command == "resume":
            report = supervisor.resume()
            _emit(report)
            return _exit_code_for(report["state"])

        if args.command == "status":
            supervisor.run_dir = run_directory(args.run_id, supervisor.config.run_root)
            _emit(supervisor.status())
            return 0

        if args.command == "approve":
            from .approval import APPROVAL_ACTION

            report = supervisor.approve(
                recommendation_sha256=args.recommendation_sha,
                approver=args.approver,
                action=args.action or APPROVAL_ACTION,
                note=args.note,
            )
            _emit(report)
            return 0

    except (GovernanceBlock, InputValidationError, ValueError) as exc:
        _emit({"status": "REFUSED", "error": type(exc).__name__, "message": str(exc)})
        return 2

    return 0  # pragma: no cover - argparse requires a subcommand


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
