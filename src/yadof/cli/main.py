"""Minimal repository-independent yadof console interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import math
import sys
from pathlib import Path

from .._version import __version__
from ..resources import ResourceNotFoundError
from ._output import write_text
from .docs import add_docs_parser


def _show_version(_args: argparse.Namespace) -> int:
    write_text(__version__)
    return 0


def _init_workspace_command(args: argparse.Namespace) -> int:
    from ..workspace.init import WorkspaceInitError, init_workspace

    try:
        result = init_workspace(args.path)
    except WorkspaceInitError as exc:
        print(f"yadof: error: {exc}", file=sys.stderr)
        return 1
    if result.created:
        write_text(
            f"Initialized yadof workspace at {result.workspace.root} "
            f"(template {result.template_name} version {result.template_version})."
        )
    else:
        write_text(
            f"Workspace already initialized at {result.workspace.root}; "
            "no files changed."
        )
    return 0


def _check_workspace_command(args: argparse.Namespace) -> int:
    from ..workspace.check import check_workspace

    report = check_workspace(args.workspace)
    write_text(report.format())
    return 0 if report.ok else 1


def _smoke_test_command(args: argparse.Namespace) -> int:
    from ..config import ConfigError, load_config
    from ..evaluate_manager import JobPreparationError, run_smoke_test
    from ..smoke_test import assess_smoke_task

    try:
        config = load_config(
            args.workspace,
            overrides={"EVALUATION_MODE": args.mode},
        )
        assessment = assess_smoke_task(config.workspace)
        if not assessment.is_unchanged_generic_starter and not args.real_task:
            print(
                "yadof: error: refusing to execute an edited or external task "
                f"without --real-task ({assessment.reason}). This command runs "
                "workflow.py and may launch expensive external software.",
                file=sys.stderr,
            )
            return 1
        costs = run_smoke_test(config.workspace, mode=args.mode)
    except (
        ConfigError,
        JobPreparationError,
        ImportError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as exc:
        print(f"yadof: error: smoke test could not run: {exc}", file=sys.stderr)
        return 1

    finite = any(math.isfinite(value) for row in costs for value in row)
    if not finite:
        print(
            "yadof: error: smoke test failed: no finite objective cost was returned; "
            f"inspect recent jobs under {config.workspace.jobs_dir}",
            file=sys.stderr,
        )
        return 1
    write_text(
        f"Smoke test succeeded for exactly one individual in {config.workspace.root}: "
        f"costs={costs[0]!r}"
    )
    return 0


def _run_optimization_command(args: argparse.Namespace) -> int:
    from ..run_command import run_from_args

    return run_from_args(args)


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer")
    return parsed


def _view_command(args: argparse.Namespace) -> int:
    try:
        if args.view_kind == "cost":
            from ..tools.view_cost import view_cost

            status = None if args.status == "all" else args.status
            summary, output = view_cost(
                args.workspace, status=status, output_path=args.output
            )
        else:
            from ..tools.view_time import view_time

            status = None if args.status == "all" else args.status
            summary, output = view_time(
                args.workspace, status=status, output_path=args.output
            )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"yadof: error: could not view {args.view_kind}: {exc}", file=sys.stderr)
        return 1
    write_text(summary)
    if output is not None:
        write_text(f"saved: {output}")
    return 0


def _confirm_destructive(*, confirmed: bool, prompt: str) -> bool:
    if confirmed:
        return True
    if not sys.stdin.isatty():
        print(
            "yadof: error: destructive command requires --yes in non-interactive use",
            file=sys.stderr,
        )
        return False
    try:
        answer = input(f"{prompt} Type 'yes' to continue: ")
    except EOFError:
        return False
    return answer.strip().lower() == "yes"


def _history_clear_command(args: argparse.Namespace) -> int:
    if not _confirm_destructive(
        confirmed=args.yes,
        prompt=(
            f"Clear jobs, recorded history, and surrogate checkpoints for "
            f"workspace {Path(args.workspace).resolve()}?"
        ),
    ):
        return 1
    try:
        from ..tools.history import clear_history

        summary = clear_history(args.workspace, confirm=True)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"yadof: error: history was not cleared: {exc}", file=sys.stderr)
        return 1
    write_text("Workspace optimization history cleared.")
    for name, value in summary.items():
        write_text(f"{name}: {value}")
    return 0


def _task_adapters_command(_args: argparse.Namespace) -> int:
    from ..tools.adapters import list_adapters

    names = list_adapters()
    write_text("\n".join(names) if names else "No bundled adapters are available.")
    return 0


def _task_copy_adapter_command(args: argparse.Namespace) -> int:
    try:
        from ..tools.adapters import copy_adapter

        result = copy_adapter(args.workspace, args.adapter)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"yadof: error: adapter was not copied: {exc}", file=sys.stderr)
        return 1
    action = "copied" if result.created else "already matches"
    write_text(f"Adapter {result.name} {action}: {result.destination}")
    return 0


def _task_extract_parameters_command(args: argparse.Namespace) -> int:
    if not _confirm_destructive(
        confirmed=args.yes,
        prompt=(
            "Replace the workspace parameters_constraints.py after creating a "
            "backup?"
        ),
    ):
        return 1
    try:
        from ..tools.hfss import extract_parameters

        result = extract_parameters(
            args.workspace,
            project=args.project,
            design=args.design,
            graphical=args.graphical,
            verbose=args.verbose,
            confirm=True,
        )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        print(f"yadof: error: parameters were not extracted: {exc}", file=sys.stderr)
        return 1
    method = "direct AEDT parsing" if result.used_direct_parser else "PyAEDT"
    write_text(
        f"Extracted {result.parameter_count} parameter(s) using {method}: "
        f"{result.parameter_file}"
    )
    if result.backup_file is not None:
        write_text(f"backup: {result.backup_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the stable top-level parser used by the console entry point."""

    parser = argparse.ArgumentParser(
        prog="yadof",
        description=(
            "Task-agnostic optimization framework with safe workspace setup, "
            "diagnosis, local workflow evaluation, history inspection, and task "
            "utilities."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="show the installed yadof version and exit",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    version_parser = subparsers.add_parser(
        "version",
        help="print the installed yadof version",
        description="Print the single runtime/package version value.",
    )
    version_parser.set_defaults(handler=_show_version)

    init_parser = subparsers.add_parser(
        "init",
        help="initialize a safe generic workspace",
        description=(
            "Create the minimum generic pure-Python workspace without overwriting "
            "existing files or running a workflow. Repeating init is non-mutating."
        ),
    )
    init_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="workspace directory to initialize (default: current directory)",
    )
    init_parser.set_defaults(handler=_init_workspace_command)

    check_parser = subparsers.add_parser(
        "check",
        help="diagnose a workspace without running its workflow",
        description=(
            "Validate workspace marker, config, task imports, static rawData, and "
            "selected backend prerequisites. This command never runs the workflow "
            "or installs/repairs external software."
        ),
    )
    check_parser.add_argument(
        "--workspace",
        default=".",
        help="workspace directory to inspect (default: current directory)",
    )
    check_parser.set_defaults(handler=_check_workspace_command)

    smoke_parser = subparsers.add_parser(
        "smoke-test",
        help="run exactly one representative workflow individual",
        description=(
            "Execute workflow.py for exactly one individual at the deterministic "
            "parameter midpoint with no timeout. An unchanged generic starter may "
            "run directly. Edited, "
            "external, or potentially expensive tasks require --real-task because "
            "this command can launch simulator or custom software. This is distinct "
            "from package self-tests such as pytest."
        ),
    )
    smoke_parser.add_argument(
        "--workspace",
        default=".",
        help="workspace whose task will execute (default: current directory)",
    )
    smoke_parser.add_argument(
        "--mode",
        choices=("local", "distributed"),
        default="local",
        help="evaluation backend; distributed submits exactly one HTCondor job",
    )
    smoke_parser.add_argument(
        "--real-task",
        action="store_true",
        help=(
            "confirm execution of an edited/external task that may launch expensive "
            "software; unnecessary for the unchanged generic starter"
        ),
    )
    smoke_parser.set_defaults(handler=_smoke_test_command)

    run_parser = subparsers.add_parser(
        "run",
        help="start or resume workspace optimization",
        description=(
            "Start or resume optimization through installed package APIs. A real-task "
            "smoke may launch external or expensive software; its default comes from "
            "workspace config and explicit CLI smoke flags take precedence."
        ),
    )
    run_parser.add_argument(
        "--workspace",
        default=".",
        help="workspace to optimize (default: current directory)",
    )
    run_parser.add_argument(
        "--generations",
        type=_positive_int,
        default=1,
        help="number of generations to run (default: 1)",
    )
    run_parser.add_argument(
        "--start-generation",
        type=_nonnegative_int,
        default=0,
        help="generation index used for start/resume (default: 0)",
    )
    run_parser.add_argument(
        "--mode",
        choices=("local", "distributed"),
        default=None,
        help="temporary backend override; otherwise use workspace config",
    )
    run_parser.add_argument(
        "--population-size",
        type=_positive_int,
        default=None,
        help="temporary population-size override",
    )
    run_parser.add_argument(
        "--random-seed",
        type=_nonnegative_int,
        default=None,
        help="temporary optimizer random seed",
    )
    smoke_group = run_parser.add_mutually_exclusive_group()
    smoke_group.add_argument(
        "--smoke-test",
        dest="smoke_test",
        action="store_true",
        help="run one midpoint real-task smoke before any generation",
    )
    smoke_group.add_argument(
        "--no-smoke-test",
        dest="smoke_test",
        action="store_false",
        help="skip the pre-run smoke and use configured calibration baselines",
    )
    run_parser.set_defaults(smoke_test=None)
    run_parser.add_argument(
        "--progress",
        action="store_true",
        help="show detailed generation/backend progress during this invocation",
    )
    run_parser.add_argument(
        "--fail-on-all-infinite",
        action="store_true",
        help="stop after the first generation with no finite objective",
    )
    run_parser.set_defaults(handler=_run_optimization_command)

    add_docs_parser(subparsers)

    view_parser = subparsers.add_parser(
        "view",
        help="inspect workspace cost or timing history",
        description=(
            "Print a workspace history summary. Supplying --output writes a PNG "
            "and requires the optional plot dependencies; no GUI opens implicitly."
        ),
    )
    view_subparsers = view_parser.add_subparsers(
        dest="view_kind", metavar="KIND", required=True
    )
    for kind, default_status in (("cost", "completed"), ("time", "all")):
        item = view_subparsers.add_parser(kind, help=f"inspect {kind} history")
        item.add_argument(
            "--workspace",
            default=".",
            help="workspace to inspect (default: current directory)",
        )
        item.add_argument(
            "--status",
            default=default_status,
            help="record status to include; use 'all' for every status",
        )
        item.add_argument(
            "-o",
            "--output",
            type=Path,
            help="optional PNG output path; omit for printable summary only",
        )
        item.set_defaults(handler=_view_command)

    history_parser = subparsers.add_parser(
        "history", help="manage workspace optimization history"
    )
    history_subparsers = history_parser.add_subparsers(
        dest="history_command", metavar="ACTION", required=True
    )
    history_clear = history_subparsers.add_parser(
        "clear",
        help="clear jobs, records, and surrogate checkpoints",
        description=(
            "Permanently clear runtime optimization history for one explicit "
            "workspace. This never runs from init or upgrade."
        ),
    )
    history_clear.add_argument("--workspace", default=".")
    history_clear.add_argument(
        "--yes",
        action="store_true",
        help="confirm destructive cleanup non-interactively",
    )
    history_clear.set_defaults(handler=_history_clear_command)

    task_parser = subparsers.add_parser(
        "task", help="manage workspace task inputs and optional adapters"
    )
    task_subparsers = task_parser.add_subparsers(
        dest="task_command", metavar="ACTION", required=True
    )
    task_adapters = task_subparsers.add_parser(
        "adapters", help="list optional bundled example adapters"
    )
    task_adapters.set_defaults(handler=_task_adapters_command)

    task_copy = task_subparsers.add_parser(
        "copy-adapter", help="copy one selected adapter into a workspace"
    )
    task_copy.add_argument("adapter", help="adapter name, such as test_com.py")
    task_copy.add_argument("--workspace", default=".")
    task_copy.set_defaults(handler=_task_copy_adapter_command)

    task_extract = task_subparsers.add_parser(
        "extract-parameters",
        help="extract HFSS optimization variables into the workspace task",
        description=(
            "Parse an AEDT file directly when possible, with an optional PyAEDT "
            "fallback. Replacing parameters_constraints.py requires confirmation."
        ),
    )
    task_extract.add_argument("--workspace", default=".")
    task_extract.add_argument(
        "--project",
        help="AEDT project path; relative paths resolve from the workspace root",
    )
    task_extract.add_argument("--design", help="HFSS design for PyAEDT fallback")
    task_extract.add_argument(
        "--graphical",
        action="store_true",
        help="explicitly allow a graphical AEDT session during PyAEDT fallback",
    )
    task_extract.add_argument("--verbose", action="store_true")
    task_extract.add_argument(
        "--yes",
        action="store_true",
        help="confirm replacement non-interactively",
    )
    task_extract.set_defaults(handler=_task_extract_parameters_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the yadof CLI and return a process exit status."""

    parser = build_parser()
    args = parser.parse_args(argv)
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 0

    try:
        return int(handler(args))
    except (ResourceNotFoundError, OSError) as exc:
        print(f"yadof: error: {exc}", file=sys.stderr)
        return 1
