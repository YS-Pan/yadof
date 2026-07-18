"""Workspace-local paths and schema constants for recorded evaluation data."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from ..workspace import WorkspaceContext, resolve_workspace


WorkspaceLike = WorkspaceContext | str | os.PathLike[str]
IND_META_SCHEMA_VERSION = 1
OPT_META_SCHEMA_VERSION = 1
VALID_RECORD_STATUSES = ("completed", "error", "timeout")


@dataclass(frozen=True, slots=True)
class RecordedDataPaths:
    """All durable and temporary paths used by one workspace's history."""

    directory: Path
    ind_meta_path: Path
    rawdata_archive_path: Path
    opt_meta_dir: Path
    opt_meta_path: Path
    lock_path: Path

    @classmethod
    def from_workspace(cls, workspace: WorkspaceLike) -> "RecordedDataPaths":
        context = resolve_workspace(workspace)
        directory = context.recorded_data_dir.resolve()
        ind_meta_path = directory / "indMeta.jsonl"
        opt_meta_dir = directory / "optMeta"
        return cls(
            directory=directory,
            ind_meta_path=ind_meta_path,
            rawdata_archive_path=directory / "rawData.npz",
            opt_meta_dir=opt_meta_dir,
            opt_meta_path=opt_meta_dir / "optMeta.jsonl",
            lock_path=ind_meta_path.with_suffix(ind_meta_path.suffix + ".lock"),
        )


def recorded_data_paths(workspace: WorkspaceLike) -> RecordedDataPaths:
    """Resolve a fresh path set without retaining workspace-global state."""

    return RecordedDataPaths.from_workspace(workspace)


__all__ = [
    "IND_META_SCHEMA_VERSION",
    "OPT_META_SCHEMA_VERSION",
    "RecordedDataPaths",
    "VALID_RECORD_STATUSES",
    "WorkspaceLike",
    "recorded_data_paths",
]
