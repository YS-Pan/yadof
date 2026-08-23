#!/usr/bin/env python
"""CLI entry point for the yadof benchmark campaign."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import benchmark_core as core


DEFAULT_CONFIG = Path(__file__).resolve().with_name("benchmark.toml")


def _print_json(value: Any) -> None:
    print(json.dumps(core._json_safe(value), ensure_ascii=False, indent=2, allow_nan=False))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan, preflight, execute, resume, collect, and report the frozen "
            "real-search versus GPSAF+conditional-INR benchmark."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"benchmark TOML (default: {DEFAULT_CONFIG})",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_selection(command: argparse.ArgumentParser, *, suite_required: bool = True) -> None:
        command.add_argument("--suite", required=suite_required)
        command.add_argument("--case", dest="case_ids", action="append")
        command.add_argument("--arm", dest="arm_ids", action="append")
        command.add_argument("--seed", dest="seeds", action="append", type=int)

    plan = commands.add_parser("plan", help="print a deterministic plan; writes nothing")
    add_selection(plan)

    preflight = commands.add_parser(
        "preflight", help="validate baselines, strategies, resources, disk, and yadof checks"
    )
    add_selection(preflight)

    run = commands.add_parser("run", help="create and execute a new immutable run")
    add_selection(run, suite_required=False)
    run.add_argument("--label")
    run.add_argument("--run-id")
    run.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="resume one immutable existing run instead of creating a new run",
    )
    run.add_argument(
        "--fail-fast",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="override the suite failure policy",
    )
    resume = commands.add_parser(
        "resume", help="seal any interrupted attempt and create linked replacement attempts"
    )
    resume.add_argument("--run-id", required=True)
    resume.add_argument(
        "--fail-fast",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="override the immutable suite failure policy for this resume invocation",
    )
    collect = commands.add_parser("collect", help="capture a new append-only public-API snapshot")
    collect.add_argument("--run-id", required=True)

    report = commands.add_parser("report", help="render a new append-only report from latest collection")
    report.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config, paths = core.load_config(args.config)
        if args.command == "plan":
            _print_json(
                core.build_plan(
                    config,
                    paths,
                    args.suite,
                    case_ids=args.case_ids,
                    arm_ids=args.arm_ids,
                    seeds=args.seeds,
                )
            )
            return 0
        if args.command == "preflight":
            result = core.preflight(
                config,
                paths,
                args.suite,
                case_ids=args.case_ids,
                arm_ids=args.arm_ids,
                seeds=args.seeds,
            )
            _print_json(result)
            return 0 if result["ok"] else 2
        if args.command == "run":
            if args.resume:
                if any((args.suite, args.case_ids, args.arm_ids, args.seeds, args.label, args.run_id)):
                    raise core.BenchmarkError(
                        "--resume cannot be combined with --suite/--case/--arm/--seed/--label/--run-id"
                    )
                _run_root, spec, _state = core.load_run(paths, args.resume)
                selection = spec["plan"]["selection"]
                resume_preflight = core.preflight(
                    config,
                    paths,
                    spec["suite"],
                    case_ids=selection["cases"],
                    arm_ids=selection["arms"] or None,
                    seeds=selection["seeds"],
                )
                if not resume_preflight["ok"]:
                    _print_json(resume_preflight)
                    return 2
                core.verify_run_inputs(paths, spec)
                state = core.execute_run(
                    config,
                    paths,
                    args.resume,
                    fail_fast_override=args.fail_fast,
                )
                _print_json({"run_id": args.resume, "execution_state": state["status"]})
                return 0 if state["status"] == "completed" else 1
            if not args.suite:
                raise core.BenchmarkError("run requires --suite or --resume")
            preflight_result = core.preflight(
                config,
                paths,
                args.suite,
                case_ids=args.case_ids,
                arm_ids=args.arm_ids,
                seeds=args.seeds,
            )
            if not preflight_result["ok"]:
                _print_json(preflight_result)
                return 2
            spec = core.build_run_spec(
                config,
                paths,
                args.suite,
                preflight_result,
                label=args.label,
            )
            run_id, _run_root = core.create_run(paths, spec, run_id=args.run_id)
            state = core.execute_run(
                config,
                paths,
                run_id,
                fail_fast_override=args.fail_fast,
            )
            _print_json({"run_id": run_id, "execution_state": state["status"]})
            return 0 if state["status"] == "completed" else 1
        if args.command == "resume":
            _run_root, spec, _state = core.load_run(paths, args.run_id)
            selection = spec["plan"]["selection"]
            resume_preflight = core.preflight(
                config,
                paths,
                spec["suite"],
                case_ids=selection["cases"],
                arm_ids=selection["arms"] or None,
                seeds=selection["seeds"],
            )
            if not resume_preflight["ok"]:
                _print_json(resume_preflight)
                return 2
            core.verify_run_inputs(paths, spec)
            state = core.execute_run(
                config,
                paths,
                args.run_id,
                fail_fast_override=args.fail_fast,
            )
            _print_json({"run_id": args.run_id, "execution_state": state["status"]})
            return 0 if state["status"] == "completed" else 1
        if args.command == "collect":
            path, collection = core.collect_run(paths, args.run_id)
            _print_json(
                {
                    "run_id": args.run_id,
                    "collection": str(path),
                    "execution_state": collection["execution_state"],
                }
            )
            return 0
        if args.command == "report":
            json_path, markdown_path, report = core.report_run(paths, args.run_id)
            _print_json(
                {
                    "run_id": args.run_id,
                    "report_json": str(json_path),
                    "report_markdown": str(markdown_path),
                    "purpose": report["purpose"],
                }
            )
            return 0
        raise AssertionError(f"unhandled command {args.command}")
    except core.BenchmarkError as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
