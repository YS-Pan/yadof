"""CLI commands for discovering and reading installed documentation resources."""

from __future__ import annotations

import argparse

from ..resources import (
    DocumentationKind,
    documentation_names,
    read_documentation,
    read_documentation_bundle,
)
from ._output import write_text


_AUDIENCES: tuple[DocumentationKind, ...] = ("agent", "dev")


def _list_docs(args: argparse.Namespace) -> int:
    names = documentation_names(args.audience)
    write_text("\n".join(names) if names else "No packaged documentation is available.")
    return 0


def _show_doc(args: argparse.Namespace) -> int:
    write_text(read_documentation(args.audience, args.path))
    return 0


def _bundle_docs(args: argparse.Namespace) -> int:
    write_text(read_documentation_bundle(args.audience))
    return 0


def add_docs_parser(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the packaged-documentation command tree."""

    docs_parser = subparsers.add_parser(
        "docs",
        help="list, show, or bundle packaged documentation",
        description=(
            "Discover and read UTF-8 documentation from the installed yadof version "
            "without locating or writing site-packages."
        ),
    )
    docs_subparsers = docs_parser.add_subparsers(
        dest="docs_action", metavar="ACTION", required=True
    )

    list_parser = docs_subparsers.add_parser(
        "list", help="list packaged documentation paths"
    )
    list_parser.add_argument("audience", choices=_AUDIENCES)
    list_parser.set_defaults(handler=_list_docs)

    show_parser = docs_subparsers.add_parser(
        "show", help="print one packaged documentation file"
    )
    show_parser.add_argument("audience", choices=_AUDIENCES)
    show_parser.add_argument(
        "path",
        nargs="?",
        default="README.md",
        help="audience-relative path (default: README.md)",
    )
    show_parser.set_defaults(handler=_show_doc)

    bundle_parser = docs_subparsers.add_parser(
        "bundle", help="print every document for one audience"
    )
    bundle_parser.add_argument("audience", choices=_AUDIENCES)
    bundle_parser.set_defaults(handler=_bundle_docs)


__all__ = ["add_docs_parser"]
