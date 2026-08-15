"""Workspace-local paths and schema constants for v2 recorded data."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from ..workspace import WorkspaceContext, resolve_workspace


WorkspaceLike = WorkspaceContext | str | os.PathLike[str]
RECORD_FORMAT_VERSION = 2
IND_META_SCHEMA_VERSION = 2
OPT_META_SCHEMA_VERSION = 2
VALID_RECORD_STATUSES = ("completed", "error", "timeout")


@dataclass(frozen=True, slots=True)
class RecordedDataPaths:
    """All durable and temporary paths used by one workspace's history."""

    directory: Path
    v2_directory: Path
    segments_directory: Path
    metadata_directory: Path
    campaign_lock_path: Path

    @classmethod
    def from_workspace(cls, workspace: WorkspaceLike) -> "RecordedDataPaths":
        context = resolve_workspace(workspace)
        directory = context.recorded_data_dir.resolve()
        v2_directory = directory / "v2"
        return cls(
            directory=directory,
            v2_directory=v2_directory,
            segments_directory=v2_directory / "segments",
            metadata_directory=v2_directory / "metadata",
            campaign_lock_path=context.root.resolve() / ".yadof" / "campaign.lock",
        )


def recorded_data_paths(workspace: WorkspaceLike) -> RecordedDataPaths:
    """Resolve a fresh path set without retaining workspace-global state."""

    return RecordedDataPaths.from_workspace(workspace)


__all__ = [
    "IND_META_SCHEMA_VERSION",
    "OPT_META_SCHEMA_VERSION",
    "RECORD_FORMAT_VERSION",
    "RecordedDataPaths",
    "VALID_RECORD_STATUSES",
    "WorkspaceLike",
    "recorded_data_paths",
]
