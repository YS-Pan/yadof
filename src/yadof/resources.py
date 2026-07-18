"""Read-only access to documentation and template package resources."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Literal

try:  # Python 3.11 moved these resource ABCs into importlib.resources.
    from importlib.resources.abc import Traversable
except ImportError:  # pragma: no cover - exercised on supported Python 3.10.
    from importlib.abc import Traversable

DocumentationKind = Literal["dev", "user"]

_DOCUMENTATION_DIRECTORIES: dict[DocumentationKind, str] = {
    "dev": "dev_doc",
    "user": "user_doc",
}


class ResourceNotFoundError(LookupError):
    """Raised when an expected packaged resource is unavailable."""


def _embedded_root() -> Traversable:
    return files("yadof").joinpath("_resources")


def _source_checkout_root() -> Path:
    return Path(__file__).resolve().parents[2]


def documentation_entry(kind: DocumentationKind) -> Traversable:
    """Return the selected documentation entry point without extracting it."""

    if kind not in _DOCUMENTATION_DIRECTORIES:
        choices = ", ".join(sorted(_DOCUMENTATION_DIRECTORIES))
        raise ValueError(f"unknown documentation kind {kind!r}; expected one of: {choices}")

    directory_name = _DOCUMENTATION_DIRECTORIES[kind]
    embedded = (
        _embedded_root()
        .joinpath("docs")
        .joinpath(directory_name)
        .joinpath("README.md")
    )
    if embedded.is_file():
        return embedded

    # Builds force-include the authoritative root documentation trees. This source
    # fallback keeps checkout development usable without duplicating those trees.
    source = _source_checkout_root().joinpath(directory_name, "README.md")
    if source.is_file():
        return source

    raise ResourceNotFoundError(
        f"the {kind!r} documentation entry is missing from package resources"
    )


def read_documentation_entry(kind: DocumentationKind) -> str:
    """Read a documentation entry point as UTF-8 text."""

    return documentation_entry(kind).read_text(encoding="utf-8")


def template_names() -> tuple[str, ...]:
    """List bundled software-neutral template resource names."""

    root = _embedded_root().joinpath("templates")
    if not root.is_dir():
        return ()
    return tuple(sorted(child.name for child in root.iterdir() if child.is_dir()))
