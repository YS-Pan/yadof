"""Read-only access to documentation and template package resources."""

from __future__ import annotations

import json
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


def template_root(name: str) -> Traversable:
    """Return one bundled workspace template directory without extracting it."""

    if not name or name not in template_names():
        choices = ", ".join(template_names()) or "none"
        raise ResourceNotFoundError(
            f"unknown workspace template {name!r}; available templates: {choices}"
        )
    root = _embedded_root().joinpath("templates").joinpath(name)
    if not root.is_dir():
        raise ResourceNotFoundError(f"workspace template resource is missing: {name}")
    return root


def read_template_manifest(name: str) -> dict[str, object]:
    """Read and decode one bundled template's JSON manifest."""

    manifest = template_root(name).joinpath("template.json")
    if not manifest.is_file():
        raise ResourceNotFoundError(
            f"workspace template {name!r} has no template.json manifest"
        )
    try:
        decoded = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ResourceNotFoundError(
            f"workspace template {name!r} has an invalid manifest: {exc}"
        ) from exc
    if not isinstance(decoded, dict):
        raise ResourceNotFoundError(
            f"workspace template {name!r} manifest must be a JSON object"
        )
    return decoded


def adapter_names() -> tuple[str, ...]:
    """List optional example adapters bundled as read-only resources."""

    root = _embedded_root().joinpath("adapters")
    if not root.is_dir():
        return ()
    return tuple(
        sorted(
            child.name
            for child in root.iterdir()
            if child.is_file()
            and child.name.endswith("_com.py")
            and not child.name.startswith(".")
        )
    )


def adapter_resource(name: str) -> Traversable:
    """Return one exact bundled adapter without extracting or writing it."""

    selected = str(name).strip()
    if selected and not selected.endswith(".py"):
        selected += ".py"
    if selected not in adapter_names():
        choices = ", ".join(adapter_names()) or "none"
        raise ResourceNotFoundError(
            f"unknown adapter {name!r}; available adapters: {choices}"
        )
    resource = _embedded_root().joinpath("adapters").joinpath(selected)
    if not resource.is_file():
        raise ResourceNotFoundError(f"adapter resource is missing: {selected}")
    return resource


__all__ = [
    "DocumentationKind",
    "ResourceNotFoundError",
    "adapter_names",
    "adapter_resource",
    "documentation_entry",
    "read_documentation_entry",
    "read_template_manifest",
    "template_names",
    "template_root",
]
