"""Minimal repository-independent yadof console interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
import math
import sys

from ._version import __version__
from .resources import ResourceNotFoundError, read_documentation_entry


def _write_text(text: str) -> None:
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def _show_version(_args: argparse.Namespace) -> int:
    _write_text(__version__)
    return 0


def _show_docs(args: argparse.Namespace) -> int:
    _write_text(read_documentation_entry(args.kind))
    return 0


def _init_workspace_command(args: argparse.Namespace) -> int:
    from .workspace_init import WorkspaceInitError, init_workspace

    try:
        result = init_workspace(args.path)
    except WorkspaceInitError as exc:
        print(f"yadof: error: {exc}", file=sys.stderr)
        return 1
    if result.created:
        _write_text(
            f"Initialized yadof workspace at {result.workspace.root} "
            f"(template {result.template_name} version {result.template_version})."
        )
    else:
        _write_text(
            f"Workspace already initialized at {result.workspace.root}; "
            "no files changed."
        )
    return 0


def _check_workspace_command(args: argparse.Namespace) -> int:
    from .workspace_check import check_workspace

    report = check_workspace(args.workspace)
    _write_text(report.format())
    return 0 if report.ok else 1


def _smoke_test_command(args: argparse.Namespace) -> int:
    from .config import ConfigError, load_config
    from .evaluate_manager import JobPreparationError, run_smoke_test
    from .smoke_test import assess_smoke_task

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
    _write_text(
        f"Smoke test succeeded for exactly one individual in {config.workspace.root}: "
        f"costs={costs[0]!r}"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the stable top-level parser used by the console entry point."""

    parser = argparse.ArgumentParser(
        prog="yadof",
        description=(
            "Task-agnostic optimization framework with safe workspace setup, "
            "diagnosis, and explicit local workflow smoke evaluation."
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
        help="run exactly one representative local workflow individual",
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
        choices=("local",),
        default="local",
        help="evaluation backend (current installed stage supports local only)",
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

    docs_parser = subparsers.add_parser(
        "docs",
        help="print a packaged documentation entry point",
        description=(
            "Print the selected UTF-8 documentation entry without opening a GUI "
            "or writing package resources."
        ),
    )
    docs_parser.add_argument(
        "kind",
        choices=("dev", "user"),
        help="documentation set whose README entry should be printed",
    )
    docs_parser.set_defaults(handler=_show_docs)
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
