"""Workspace-local paths and schema constants for recorded data."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from ..workspace import WorkspaceContext, resolve_workspace


WorkspaceLike = WorkspaceContext | str | os.PathLike[str]
VALID_RECORD_STATUSES = ("completed", "error", "timeout")


@dataclass(frozen=True, slots=True)
class RecordedDataPaths:
    """All durable and temporary paths used by one workspace's history."""

    directory: Path
    segments_directory: Path
    metadata_directory: Path
    campaign_lock_path: Path

    @classmethod
    def from_workspace(cls, workspace: WorkspaceLike) -> "RecordedDataPaths":
        context = resolve_workspace(workspace)
        directory = context.recorded_data_dir.resolve()
        return cls(
            directory=directory,
            segments_directory=directory / "segments",
            metadata_directory=directory / "metadata",
            campaign_lock_path=context.root.resolve() / ".yadof" / "campaign.lock",
        )


def recorded_data_paths(workspace: WorkspaceLike) -> RecordedDataPaths:
    """Resolve a fresh path set without retaining workspace-global state."""

    return RecordedDataPaths.from_workspace(workspace)


__all__ = [
    "RecordedDataPaths",
    "VALID_RECORD_STATUSES",
    "WorkspaceLike",
    "recorded_data_paths",
]
