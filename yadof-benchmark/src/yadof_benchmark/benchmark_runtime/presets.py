"""Validated packaged preset discovery and workspace materialization."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .contracts import BenchmarkError

PRESET_FORMAT = "yadof.benchmark.presets/v1"
PRESET_PROVENANCE_FORMAT = "yadof.benchmark.preset-provenance/v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest().upper()


def _relative(value: object, *, label: str) -> PurePosixPath:
    text = str(value)
    path = PurePosixPath(text)
    if (
        not text
        or "\\" in text
        or path.is_absolute()
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != text
    ):
        raise BenchmarkError(f"{label} must be a canonical relative path: {text!r}")
    return path


def _source(root: Path, relative: object, *, label: str) -> tuple[Path, str]:
    path = _relative(relative, label=label)
    selected = root.joinpath(*path.parts)
    try:
        resolved = selected.resolve(strict=True)
    except OSError as exc:
        raise BenchmarkError(f"{label} does not exist: {path.as_posix()}") from exc
    if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
        raise BenchmarkError(f"{label} escapes the packaged preset root or is not a file")
    return resolved, path.as_posix()


def _catalog(root: str | Path) -> tuple[Path, bytes, list[dict[str, Any]]]:
    selected_root = Path(root).resolve()
    manifest = selected_root / "presets.json"
    try:
        raw_bytes = manifest.read_bytes()
        value = json.loads(raw_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BenchmarkError(f"cannot read packaged preset catalog: {manifest}: {exc}") from exc
    if not isinstance(value, dict) or value.get("format") != PRESET_FORMAT:
        raise BenchmarkError(f"unsupported packaged preset catalog: {manifest}")
    entries = value.get("presets")
    if not isinstance(entries, list) or not entries:
        raise BenchmarkError(f"packaged preset catalog has no presets: {manifest}")
    output: list[dict[str, Any]] = []
    ids: set[str] = set()
    defaults: list[str] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise BenchmarkError("packaged preset entries must be objects")
        item = dict(raw)
        preset_id = str(item.get("id", ""))
        if not preset_id or preset_id in ids:
            raise BenchmarkError(f"invalid or duplicate packaged preset id: {preset_id!r}")
        ids.add(preset_id)
        if item.get("default") is True:
            defaults.append(preset_id)
        _source(selected_root, item.get("workflow"), label=f"preset {preset_id!r} workflow")
        files = item.get("files")
        if not isinstance(files, list):
            raise BenchmarkError(f"preset {preset_id!r} files must be a list")
        destinations: set[str] = {"benchmark.py"}
        for entry in files:
            if not isinstance(entry, Mapping):
                raise BenchmarkError(f"preset {preset_id!r} file entry must be an object")
            _source(
                selected_root,
                entry.get("source"),
                label=f"preset {preset_id!r} source",
            )
            destination = _relative(
                entry.get("destination"),
                label=f"preset {preset_id!r} destination",
            ).as_posix()
            folded = destination.casefold()
            if folded in {item.casefold() for item in destinations}:
                raise BenchmarkError(
                    f"preset {preset_id!r} destination is duplicated: {destination!r}"
                )
            destinations.add(destination)
        output.append(item)
    if defaults != ["portable"]:
        raise BenchmarkError("packaged preset catalog must select only portable by default")
    return selected_root, raw_bytes, output


def _public(item: Mapping[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "name",
        "description",
        "default",
        "long_running",
        "cells",
        "population",
        "generations",
        "timeout_seconds",
        "baselines",
        "strategies",
        "seeds",
        "requirements",
    )
    return json.loads(json.dumps({key: item.get(key) for key in keys}))


def discover_presets(root: str | Path) -> dict[str, dict[str, Any]]:
    """Return ordered, user-facing metadata for every packaged preset."""

    _, _, entries = _catalog(root)
    return {str(item["id"]): _public(item) for item in entries}


def materialize_preset(
    root: str | Path,
    preset_id: str,
    workspace: str | Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Copy one validated packaged preset and return public/provenance records."""

    selected_root, catalog_bytes, entries = _catalog(root)
    by_id = {str(item["id"]): item for item in entries}
    try:
        preset = by_id[str(preset_id)]
    except KeyError as exc:
        raise BenchmarkError(
            f"unknown benchmark preset {preset_id!r}; choose from {', '.join(by_id)}"
        ) from exc
    output_root = Path(workspace).resolve()
    planned = [
        {
            "role": "workflow",
            "source": preset["workflow"],
            "destination": "benchmark.py",
        },
        *[
            {
                "role": "strategy-resource",
                "source": entry["source"],
                "destination": entry["destination"],
            }
            for entry in preset["files"]
        ],
    ]
    records: list[dict[str, Any]] = []
    for item in planned:
        source, source_relative = _source(
            selected_root,
            item["source"],
            label=f"preset {preset_id!r} source",
        )
        destination_relative = _relative(
            item["destination"],
            label=f"preset {preset_id!r} destination",
        )
        destination = output_root.joinpath(*destination_relative.parts)
        if not destination.resolve().is_relative_to(output_root):
            raise BenchmarkError(f"preset {preset_id!r} destination escapes workspace")
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = source.read_bytes()
        try:
            with destination.open("xb") as stream:
                stream.write(data)
        except FileExistsError as exc:
            raise BenchmarkError(f"workspace output already exists: {destination}") from exc
        records.append(
            {
                "role": item["role"],
                "source": source_relative,
                "workspace_path": destination_relative.as_posix(),
                "sha256": _sha256(data),
                "bytes": len(data),
            }
        )
    provenance = {
        "format": PRESET_PROVENANCE_FORMAT,
        "id": str(preset["id"]),
        "source": "packaged",
        "catalog": {"path": "presets.json", "sha256": _sha256(catalog_bytes)},
        "files": records,
    }
    return _public(preset), provenance


__all__ = [
    "PRESET_FORMAT",
    "PRESET_PROVENANCE_FORMAT",
    "discover_presets",
    "materialize_preset",
]
