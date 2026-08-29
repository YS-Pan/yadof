"""Command-line interface for yadof benchmark workspaces."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import api
from .benchmark_runtime.launch import launch_detached
from .benchmark_runtime.terminal import BenchmarkTerminal


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


def _workspace_command(commands: Any, name: str, help_text: str) -> Any:
    command = commands.add_parser(name, help=help_text)
    command.add_argument("--workspace", type=Path, default=Path("."))
    command.add_argument("--baselines-root", type=Path)
    return command


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and run code-first yadof benchmark workspaces."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a benchmark workspace")
    init.add_argument("workspace", type=Path)

    baselines = commands.add_parser(
        "baselines", help="list discovered self-describing baselines"
    )
    baselines.add_argument("--root", type=Path)

    _workspace_command(
        commands, "check", "execute benchmark.py and validate its complete plan"
    )
    _workspace_command(
        commands, "plan", "print a deterministic plan without creating a run"
    )
    run = _workspace_command(commands, "run", "snapshot and execute a workspace")
    run.add_argument("--run-id")
    run.add_argument(
        "--detach",
        action="store_true",
        help="start in a separate console and immediately return a launch receipt",
    )
    run.add_argument(
        "--hidden",
        action="store_true",
        help="explicitly hide a detached console (requires --detach)",
    )

    resume = commands.add_parser(
        "resume", help="continue a run from its own driver and input snapshots"
    )
    resume.add_argument("--run", type=Path, required=True)
    resume.add_argument(
        "--detach",
        action="store_true",
        help="continue in a separate console and immediately return a launch receipt",
    )
    resume.add_argument(
        "--hidden",
        action="store_true",
        help="explicitly hide a detached console (requires --detach)",
    )

    inspect = commands.add_parser(
        "inspect", help="read current run state and result locations without writing"
    )
    inspect.add_argument("--run", type=Path, required=True)

    docs = commands.add_parser("docs", help="read version-matched user documentation")
    doc_commands = docs.add_subparsers(dest="docs_command", required=True)
    doc_commands.add_parser("list", help="list user documents")
    show = doc_commands.add_parser("show", help="print one user document")
    show.add_argument("path", nargs="?", default="README.md")
    return parser


def _docs(args: argparse.Namespace) -> None:
    root = api.user_doc_root().resolve()
    if args.docs_command == "list":
        _json(
            {
                "format": "yadof.benchmark.docs",
                "documents": [
                    path.relative_to(root).as_posix()
                    for path in sorted(root.rglob("*.md"))
                ],
            }
        )
        return
    relative = Path(args.path)
    if relative.is_absolute() or ".." in relative.parts:
        raise api.BenchmarkError("document path must stay below user_doc")
    selected = (root / relative).resolve()
    try:
        selected.relative_to(root)
    except ValueError as exc:
        raise api.BenchmarkError("document path must stay below user_doc") from exc
    if not selected.is_file():
        raise api.BenchmarkError(f"user document does not exist: {args.path}")
    print(selected.read_text(encoding="utf-8"), end="", flush=True)


def _foreground(
    action: Callable[[Callable[[Mapping[str, Any]], None]], dict[str, Any]],
    *,
    run: str | Path | None = None,
) -> dict[str, Any]:
    terminal = BenchmarkTerminal(run)
    terminal.start()
    try:
        result = action(terminal.handle)
    except BaseException as exc:
        terminal.finish(error=exc)
        raise
    terminal.finish(result=result)
    return result


def _require_detach_for_hidden(args: argparse.Namespace) -> None:
    if bool(args.hidden) and not bool(args.detach):
        raise api.BenchmarkError("--hidden is valid only with explicit --detach")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            _json(api.init_workspace(args.workspace))
            return 0
        if args.command == "baselines":
            manifests = api.discover_baselines(args.root)
            _json(
                {
                    "format": "yadof.benchmark.baselines",
                    "baselines": [
                        manifests[key].public_dict() for key in sorted(manifests)
                    ],
                }
            )
            return 0
        if args.command in {"check", "plan"}:
            spec = api.plan_workspace(
                args.workspace, baselines_root=args.baselines_root
            )
            output = spec.to_dict()
            output["writes"] = False
            _json(output)
            return 0
        if args.command == "run":
            _require_detach_for_hidden(args)
            if args.detach:
                run_root = api._prepare_workspace_run(
                    args.workspace,
                    run_id=args.run_id,
                    baselines_root=args.baselines_root,
                )
                _json(launch_detached(run_root, hidden=bool(args.hidden)))
                return 0
            result = _foreground(
                lambda event_sink: api.run_workspace(
                    args.workspace,
                    run_id=args.run_id,
                    baselines_root=args.baselines_root,
                    event_sink=event_sink,
                )
            )
            _json(result)
            return 0 if result["status"] == "completed" else 1
        if args.command == "resume":
            _require_detach_for_hidden(args)
            if args.detach:
                _json(launch_detached(args.run, hidden=bool(args.hidden)))
                return 0
            result = _foreground(
                lambda event_sink: api.resume_run(
                    args.run, event_sink=event_sink
                ),
                run=args.run,
            )
            _json(result)
            return 0 if result["status"] == "completed" else 1
        if args.command == "inspect":
            _json(api.inspect_run(args.run))
            return 0
        if args.command == "docs":
            _docs(args)
            return 0
        raise AssertionError(f"unhandled command: {args.command}")
    except api.BenchmarkError as exc:
        print(f"benchmark error: {exc}", file=sys.stderr, flush=True)
        return 2
    except KeyboardInterrupt:
        print("benchmark interrupted", file=sys.stderr, flush=True)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
