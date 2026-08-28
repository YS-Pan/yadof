#!/usr/bin/env python
"""Command-line interface for modular yadof benchmark studies."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import benchmark_core as core

def _json(value: Any) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        ),
        flush=True,
    )


def _progress(event: Any) -> None:
    print(
        json.dumps(event, ensure_ascii=False, allow_nan=False, sort_keys=True),
        file=sys.stderr,
        flush=True,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare complete yadof optimization strategies on self-describing "
            "baseline workspaces."
        )
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser(
        "baselines",
        help="list discovered self-describing baselines",
    )
    plan = commands.add_parser(
        "plan",
        help="validate and print a deterministic study plan without writing",
    )
    plan.add_argument("--study", type=Path, required=True)

    run = commands.add_parser(
        "run",
        help="snapshot and execute a study",
    )
    run.add_argument("--study", type=Path, required=True)
    run.add_argument("--run-id")

    resume = commands.add_parser(
        "resume",
        help="continue a run through its own driver and input snapshots",
    )
    resume.add_argument("--run", type=Path, required=True)

    inspect = commands.add_parser(
        "inspect",
        help="read current run state and result locations without writing",
    )
    inspect.add_argument("--run", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "baselines":
            manifests = core.discover_baselines()
            _json(
                {
                    "format": "yadof.benchmark.baselines",
                    "baselines": [
                        manifests[key].public_dict() for key in sorted(manifests)
                    ],
                }
            )
            return 0
        if args.command == "plan":
            spec = core.plan_study(args.study)
            output = spec.to_dict()
            output["writes"] = False
            _json(output)
            return 0
        if args.command == "run":
            result = core.run_study(
                args.study,
                run_id=args.run_id,
                event_sink=_progress,
            )
            _json(result)
            return 0 if result["status"] == "completed" else 1
        if args.command == "resume":
            result = core.resume_run(args.run, event_sink=_progress)
            _json(result)
            return 0 if result["status"] == "completed" else 1
        if args.command == "inspect":
            _json(core.inspect_run(args.run))
            return 0
        raise AssertionError(f"unhandled command: {args.command}")
    except core.BenchmarkError as exc:
        print(f"benchmark error: {exc}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("benchmark interrupted", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
