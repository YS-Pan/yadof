"""Explicit paths for one writable yadof workspace."""

from __future__ import annotations

from dataclasses import dataclass, replace
import os
from pathlib import Path
from typing import Mapping


_PATH_SETTING_TO_FIELD = {
    "JOB_TEMPLATE_DIR": "job_template_dir",
    "JOBS_DIR": "jobs_dir",
    "RECORDED_DATA_DIR": "recorded_data_dir",
    "SURROGATE_CHECKPOINT_DIR": "surrogate_checkpoint_dir",
    "LOGS_DIR": "logs_dir",
    "TOOL_OUTPUT_DIR": "tool_output_dir",
}


def _absolute_root(value: str | os.PathLike[str] | None) -> Path:
    selected = Path.cwd() if value is None else Path(value).expanduser()
    return selected.resolve()


def _workspace_path(root: Path, value: str | os.PathLike[str]) -> Path:
    selected = Path(value).expanduser()
    if not selected.is_absolute():
        selected = root / selected
    return selected.resolve()


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    """Absolute paths for task inputs and all writable runtime state.

    Constructing a context is read-only: it resolves paths but never creates a
    directory. Relative overrides are resolved from ``root``; an absolute override
    is the only supported way to place one path outside the workspace.
    """

    root: Path
    config_file: Path
    job_template_dir: Path
    jobs_dir: Path
    recorded_data_dir: Path
    surrogate_checkpoint_dir: Path
    logs_dir: Path
    tool_output_dir: Path

    @classmethod
    def from_path(
        cls,
        root: str | os.PathLike[str] | None = None,
        *,
        job_template_dir: str | os.PathLike[str] = "job_template",
        jobs_dir: str | os.PathLike[str] = "jobs",
        recorded_data_dir: str | os.PathLike[str] = "recorded_data",
        surrogate_checkpoint_dir: str | os.PathLike[str] = ".yadof/surrogate/checkpoints",
        logs_dir: str | os.PathLike[str] = ".yadof/logs",
        tool_output_dir: str | os.PathLike[str] = ".yadof/tool_output",
    ) -> "WorkspaceContext":
        workspace_root = _absolute_root(root)
        return cls(
            root=workspace_root,
            config_file=workspace_root / "config.py",
            job_template_dir=_workspace_path(workspace_root, job_template_dir),
            jobs_dir=_workspace_path(workspace_root, jobs_dir),
            recorded_data_dir=_workspace_path(workspace_root, recorded_data_dir),
            surrogate_checkpoint_dir=_workspace_path(
                workspace_root, surrogate_checkpoint_dir
            ),
            logs_dir=_workspace_path(workspace_root, logs_dir),
            tool_output_dir=_workspace_path(workspace_root, tool_output_dir),
        )

    def with_path_settings(
        self, settings: Mapping[str, str | os.PathLike[str]]
    ) -> "WorkspaceContext":
        """Return a context with validated config path settings applied."""

        changes: dict[str, Path] = {}
        for name, value in settings.items():
            try:
                field_name = _PATH_SETTING_TO_FIELD[name]
            except KeyError as exc:
                raise KeyError(f"unknown workspace path setting: {name}") from exc
            changes[field_name] = _workspace_path(self.root, value)
        return replace(self, **changes)

    def path_settings(self) -> dict[str, Path]:
        """Return effective config path names mapped to their absolute values."""

        return {
            name: getattr(self, field_name)
            for name, field_name in _PATH_SETTING_TO_FIELD.items()
        }

    def writable_paths(self) -> tuple[Path, ...]:
        """Return paths that runtime phases may create or modify."""

        return (
            self.jobs_dir,
            self.recorded_data_dir,
            self.surrogate_checkpoint_dir,
            self.logs_dir,
            self.tool_output_dir,
        )


def resolve_workspace(
    workspace: WorkspaceContext | str | os.PathLike[str] | None = None,
) -> WorkspaceContext:
    """Coerce a context or workspace root, defaulting to the current directory."""

    if isinstance(workspace, WorkspaceContext):
        return workspace
    return WorkspaceContext.from_path(workspace)


__all__ = ["WorkspaceContext", "resolve_workspace"]
