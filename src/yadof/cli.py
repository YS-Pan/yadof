"""Minimal repository-independent yadof console interface."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
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


def build_parser() -> argparse.ArgumentParser:
    """Create the stable top-level parser used by the console entry point."""

    parser = argparse.ArgumentParser(
        prog="yadof",
        description=(
            "Task-agnostic optimization framework. The current console interface "
            "provides version and packaged-document commands; workspace runtime "
            "commands arrive in later package stages."
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
