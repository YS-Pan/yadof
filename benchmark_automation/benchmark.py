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


def _print_json(value: Any, *, pretty: bool = False) -> None:
    options: dict[str, Any] = {"ensure_ascii": False, "allow_nan": False}
    if pretty:
        options["indent"] = 2
    else:
        options["separators"] = (",", ":")
    print(json.dumps(core._json_safe(value), **options), flush=True)


def _pause_after_run() -> None:
    """Keep an interactively launched benchmark window open after execution."""

    if not bool(getattr(sys.stdin, "isatty", lambda: False)()):
        return
    print("Benchmark finished. Press Enter to return to the shell...", file=sys.stderr, flush=True)
    try:
        sys.stdin.readline()
    except (EOFError, KeyboardInterrupt):
        pass


def _finish_run_command(run_root: Path, run_id: str, state: dict[str, Any]) -> int:
    _print_json(core.summarize_run_state(run_root, run_id, state))
    _pause_after_run()
    return 0 if state["status"] == "completed" else 1


def _print_hypervolume_table(report: dict[str, Any]) -> None:
    table = core.format_hypervolume_table(report)
    if table:
        print(table, file=sys.stderr, flush=True)


def _with_runs_dir(value: dict[str, Any], paths: core.Paths) -> dict[str, Any]:
    output = dict(value)
    output["runs_dir"] = str(paths.runs)
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Plan, preflight, execute, resume, collect, and report the frozen "
            "NSGA-III versus GPSAF+conditional-INR benchmark."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"benchmark TOML (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        help=(
            "run output root; a relative override resolves from the invocation "
            "directory and overrides [runner].runs_dir"
        ),
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_selection(command: argparse.ArgumentParser, *, suite_required: bool = True) -> None:
        command.add_argument("--suite", required=suite_required)
        command.add_argument("--case", dest="case_ids", action="append")
        command.add_argument("--arm", dest="arm_ids", action="append")
        command.add_argument("--seed", dest="seeds", action="append", type=int)

    def add_full_json(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--full-json",
            action="store_true",
            help="print the complete expanded JSON instead of the bounded agent summary",
        )

    def add_stream_output(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--stream-output",
            action="store_true",
            help="also stream child stdout/stderr; logs are always preserved without this flag",
        )

    plan = commands.add_parser("plan", help="print a bounded deterministic plan; writes nothing")
    add_selection(plan)
    add_full_json(plan)

    preflight = commands.add_parser(
        "preflight", help="validate baselines, strategies, resources, disk, and yadof checks"
    )
    add_selection(preflight)
    add_full_json(preflight)

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
    add_stream_output(run)
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
    add_stream_output(resume)
    collect = commands.add_parser("collect", help="capture a new append-only public-API snapshot")
    collect.add_argument("--run-id", required=True)

    report = commands.add_parser("report", help="render a new report and print its bounded agent summary")
    report.add_argument("--run-id", required=True)
    add_full_json(report)

    inspect = commands.add_parser(
        "inspect",
        help="print the bounded first-read summary for an existing run without changing it",
    )
    inspect.add_argument("--run-id", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config, paths = core.load_config(
            args.config,
            runs_dir_override=args.runs_dir,
            invocation_cwd=Path.cwd(),
        )
        if args.command == "plan":
            result = core.build_plan(
                config,
                paths,
                args.suite,
                case_ids=args.case_ids,
                arm_ids=args.arm_ids,
                seeds=args.seeds,
            )
            output = _with_runs_dir(
                result if args.full_json else core.summarize_plan(result), paths
            )
            _print_json(output, pretty=args.full_json)
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
            output = _with_runs_dir(
                result if args.full_json else core.summarize_preflight(result), paths
            )
            _print_json(output, pretty=args.full_json)
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
                    _print_json(
                        _with_runs_dir(core.summarize_preflight(resume_preflight), paths)
                    )
                    return 2
                core.verify_run_inputs(paths, _run_root, spec)
                state = core.execute_run(
                    config,
                    paths,
                    args.resume,
                    fail_fast_override=args.fail_fast,
                    stream_subprocess_output=args.stream_output,
                )
                return _finish_run_command(_run_root, args.resume, state)
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
                _print_json(
                    _with_runs_dir(core.summarize_preflight(preflight_result), paths)
                )
                return 2
            spec = core.build_run_spec(
                config,
                paths,
                args.suite,
                preflight_result,
                label=args.label,
            )
            run_id, run_root = core.create_run(paths, spec, run_id=args.run_id)
            state = core.execute_run(
                config,
                paths,
                run_id,
                fail_fast_override=args.fail_fast,
                stream_subprocess_output=args.stream_output,
            )
            return _finish_run_command(run_root, run_id, state)
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
                _print_json(
                    _with_runs_dir(core.summarize_preflight(resume_preflight), paths)
                )
                return 2
            core.verify_run_inputs(paths, _run_root, spec)
            state = core.execute_run(
                config,
                paths,
                args.run_id,
                fail_fast_override=args.fail_fast,
                stream_subprocess_output=args.stream_output,
            )
            return _finish_run_command(_run_root, args.run_id, state)
        if args.command == "collect":
            path, collection = core.collect_run(paths, args.run_id)
            _print_json(
                {
                    "schema_version": core.SCHEMA_VERSION,
                    "view": "collection-summary",
                    "run_id": args.run_id,
                    "runs_dir": str(paths.runs),
                    "run_root": str(paths.runs / args.run_id),
                    "collection": str(path),
                    "execution_state": collection["execution_state"],
                    "metrics": str(paths.runs / args.run_id / "metrics.json"),
                    "read_policy": "Do not read collection or metrics whole; run report next.",
                    "next_command": [
                        "--runs-dir",
                        str(paths.runs),
                        "report",
                        "--run-id",
                        args.run_id,
                    ],
                }
            )
            return 0
        if args.command == "report":
            json_path, markdown_path, report = core.report_run(paths, args.run_id)
            _print_json(
                report if args.full_json else core.inspect_run(paths, args.run_id),
                pretty=args.full_json,
            )
            if not args.full_json:
                _print_hypervolume_table(report)
            return 0
        if args.command == "inspect":
            result = core.inspect_run(paths, args.run_id)
            _print_json(result)
            report_path = paths.runs / args.run_id / "report.json"
            if report_path.is_file():
                _print_hypervolume_table(core.read_json(report_path))
            return 0
        raise AssertionError(f"unhandled command {args.command}")
    except core.BenchmarkError as exc:
        print(f"benchmark error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
