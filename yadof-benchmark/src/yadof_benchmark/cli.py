"""Command-line interface for yadof benchmark workspaces."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from . import api
from .benchmark_runtime.contracts import evidence_notice, replication_notice
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
    command.add_argument(
        "--budget-profile",
        choices=("declared", "smoke"),
        default="declared",
        help="use declared budgets or mechanically set every cell to one generation",
    )
    return command


def _bounded_values(values: Sequence[Any], *, limit: int = 8) -> dict[str, Any]:
    selected = sorted({str(value) for value in values})
    return {
        "values": selected[:limit],
        "count": len(selected),
        "truncated": max(0, len(selected) - limit),
    }


def _plan_summary(
    spec: api.RunSpec,
    *,
    command: str,
    workspace: Path,
    baselines_root: Path | None,
) -> dict[str, Any]:
    cells = list(spec.cells)
    populations = [cell.population for cell in cells]
    generations = [cell.generations for cell in cells]
    replication_scopes = sorted({cell.replication_scope for cell in cells})
    simulation_concurrency = [
        (
            f"{cell.baseline_id}:physical_core_multiplier="
            f"{cell.execution.get('simulation_concurrency', {}).get('physical_core_multiplier')}"
        )
        for cell in cells
        if isinstance(cell.execution.get("simulation_concurrency"), Mapping)
    ]
    full_json = [
        "yadof-benchmark",
        command,
        "--workspace",
        str(workspace.resolve()),
    ]
    if baselines_root is not None:
        full_json.extend(["--baselines-root", str(baselines_root.resolve())])
    if spec.workflow.budget_profile != "declared":
        full_json.extend(["--budget-profile", spec.workflow.budget_profile])
    full_json.append("--json")
    return {
        "format": f"yadof.benchmark.{command}-summary",
        "valid": True,
        "writes": False,
        "workflow": spec.workflow.name,
        "budget_profile": spec.workflow.budget_profile,
        "evidence": {
            "class": spec.workflow.evidence,
            "notice": evidence_notice(spec.workflow.evidence),
        },
        "replication": {
            "scopes": replication_scopes,
            "notices": {
                scope: replication_notice(scope) for scope in replication_scopes
            },
        },
        "workspace": str(spec.workflow.workspace),
        "counts": {
            "comparisons": len(spec.workflow.comparisons),
            "cells": len(cells),
            "planned_evaluations": sum(
                cell.planned_evaluations for cell in cells
            ),
        },
        "cells": {
            "values": [
                {"id": cell.id, "display_label": cell.display_label}
                for cell in cells[:8]
            ],
            "count": len(cells),
            "truncated": max(0, len(cells) - 8),
        },
        "baselines": _bounded_values([cell.baseline_id for cell in cells]),
        "strategies": _bounded_values([cell.strategy_id for cell in cells]),
        "seeds": _bounded_values([cell.seed for cell in cells]),
        "budget": {
            "population_min": min(populations, default=0),
            "population_max": max(populations, default=0),
            "generations_min": min(generations, default=0),
            "generations_max": max(generations, default=0),
            "contains_slow_surrogate": any(
                cell.contains_slow_surrogate for cell in cells
            ),
        },
        "concurrency": {
            "cells": spec.workflow.cell_concurrency,
            "simulations": _bounded_values(simulation_concurrency),
        },
        "next_commands": {"full_json": full_json},
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create and run code-first yadof benchmark workspaces."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init", help="create a benchmark workspace")
    init.add_argument("workspace", type=Path)
    init_preset = init.add_mutually_exclusive_group()
    init_preset.add_argument(
        "--preset",
        choices=("portable", "complete"),
        help=(
            "select portable or the explicit long-running complete preset "
            "(default: portable)"
        ),
    )
    init_preset.add_argument(
        "--blank",
        action="store_true",
        help="create an explicit blank authoring workspace",
    )

    commands.add_parser(
        "presets",
        help="list packaged presets, budgets, dependencies, and long-run warnings",
    )

    baselines = commands.add_parser(
        "baselines", help="list discovered self-describing baselines"
    )
    baselines.add_argument("--root", type=Path)

    check = _workspace_command(
        commands, "check", "execute benchmark.py and validate its complete plan"
    )
    check.add_argument(
        "--json",
        action="store_true",
        help="print the complete expanded plan instead of the bounded summary",
    )
    plan = _workspace_command(
        commands, "plan", "print a deterministic plan without writing outputs"
    )
    plan.add_argument(
        "--json",
        action="store_true",
        help="print the complete expanded plan instead of the bounded summary",
    )
    run = _workspace_command(
        commands, "run", "execute the workspace's single benchmark"
    )
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
    run.add_argument(
        "--stream-child-output",
        action="store_true",
        help="echo raw child stdout/stderr in addition to separate command logs",
    )

    inspect = commands.add_parser(
        "inspect", help="read workspace state and result locations without writing"
    )
    inspect.add_argument("--workspace", type=Path, default=Path("."))

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
    workspace: str | Path,
) -> dict[str, Any]:
    terminal = BenchmarkTerminal(workspace)
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
            selected = "blank" if args.blank else (args.preset or "portable")
            _json(api.init_workspace(args.workspace, preset=selected))
            return 0
        if args.command == "presets":
            _json(
                {
                    "format": "yadof.benchmark.presets",
                    "presets": list(api.discover_presets().values()),
                }
            )
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
                args.workspace,
                baselines_root=args.baselines_root,
                budget_profile=args.budget_profile,
            )
            if args.json:
                output = spec.to_dict()
                output["writes"] = False
            else:
                output = _plan_summary(
                    spec,
                    command=args.command,
                    workspace=args.workspace,
                    baselines_root=args.baselines_root,
                )
            _json(output)
            return 0
        if args.command == "run":
            _require_detach_for_hidden(args)
            if args.detach:
                spec = api.plan_workspace(
                    args.workspace,
                    baselines_root=args.baselines_root,
                    budget_profile=args.budget_profile,
                )
                _json(
                    launch_detached(
                        args.workspace,
                        baselines_root=args.baselines_root,
                        evidence=spec.workflow.evidence,
                        budget_profile=args.budget_profile,
                        hidden=bool(args.hidden),
                        stream_child_output=bool(args.stream_child_output),
                    )
                )
                return 0
            result = _foreground(
                lambda event_sink: api.run_workspace(
                    args.workspace,
                    baselines_root=args.baselines_root,
                    budget_profile=args.budget_profile,
                    event_sink=event_sink,
                    stream_child_output=bool(args.stream_child_output),
                ),
                workspace=args.workspace,
            )
            _json(result)
            return 0 if result["status"] == "completed" else 1
        if args.command == "inspect":
            _json(api.inspect_workspace(args.workspace))
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
