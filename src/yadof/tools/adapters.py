from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import load_config
from ..resources import adapter_names, adapter_resource
from ..workspace import WorkspaceContext


WorkspaceLike = WorkspaceContext | str | Path


@dataclass(frozen=True, slots=True)
class AdapterCopyResult:
    name: str
    destination: Path
    created: bool


def list_adapters() -> tuple[str, ...]:
    return adapter_names()


def copy_adapter(
    workspace: WorkspaceLike, adapter: str
) -> AdapterCopyResult:
    """Copy one selected resource into a workspace without overwriting user code."""

    config = load_config(workspace)
    resource = adapter_resource(adapter)
    content = resource.read_bytes()
    destination = config.workspace.job_template_dir / resource.name
    if destination.exists():
        if destination.is_file() and destination.read_bytes() == content:
            return AdapterCopyResult(resource.name, destination, False)
        raise FileExistsError(
            f"workspace adapter already exists and was not overwritten: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as stream:
        stream.write(content)
    return AdapterCopyResult(resource.name, destination, True)


__all__ = ["AdapterCopyResult", "copy_adapter", "list_adapters"]
