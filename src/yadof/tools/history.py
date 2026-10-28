from __future__ import annotations

from pathlib import Path
import shutil
import stat

from ..config import load_config
from ..recorded_data.campaign_lock import CampaignLock
from ..recorded_data.paths import recorded_data_paths
from ..workspace import WorkspaceContext


WorkspaceLike = WorkspaceContext | str | Path


class HistoryClearConfirmationRequired(RuntimeError):
    """Raised when destructive history cleanup lacks explicit confirmation."""


def _is_junction(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    return getattr(info, "st_reparse_tag", None) == stat.IO_REPARSE_TAG_MOUNT_POINT


def _validate_runtime_directory(path: Path, workspace_root: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    anchor = Path(resolved.anchor).resolve(strict=False)
    if resolved in {workspace_root.resolve(), anchor}:
        raise RuntimeError(f"refusing to clear broad {label} path: {resolved}")
    return resolved


def _remove_path(path: Path) -> bool:
    junction = _is_junction(path)
    if not path.exists() and not path.is_symlink() and not junction:
        return False
    if junction:
        path.rmdir()
    elif path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True


def _clear_directory(path: Path) -> int:
    if not path.exists():
        return 0
    if not path.is_dir() or path.is_symlink() or _is_junction(path):
        raise RuntimeError(f"expected a real runtime directory: {path}")
    count = 0
    for child in tuple(path.iterdir()):
        _remove_path(child)
        count += 1
    return count


def clear_history(
    workspace: WorkspaceLike, *, confirm: bool = False, all_recorded_data: bool = False
) -> dict[str, object]:
    """Clear campaign state; opt in to clearing the entire recorded-data root.

    ``all_recorded_data`` also deletes unrelated entries in that root and requires
    every deletion target to remain inside the selected workspace.
    """

    if not confirm:
        raise HistoryClearConfirmationRequired(
            "history clearing is destructive; pass confirm=True or use CLI --yes"
        )

    config = load_config(workspace)
    context = config.workspace
    storage = recorded_data_paths(context)
    jobs_dir = _validate_runtime_directory(
        context.jobs_dir, context.root, "jobs"
    )
    checkpoints_dir = _validate_runtime_directory(
        context.surrogate_checkpoint_dir, context.root, "surrogate checkpoint"
    )
    optimization_state_dir = _validate_runtime_directory(
        context.root / ".yadof" / "optimization",
        context.root,
        "optimization state",
    )
    record_targets = tuple(
        _validate_runtime_directory(path, context.root, "recorded data")
        for path in (
            (storage.directory,) if all_recorded_data
            else (storage.segments_directory, storage.metadata_directory)
        )
    )
    targets = (jobs_dir, checkpoints_dir, optimization_state_dir, *record_targets)
    protected = (
        context.config_file.resolve(), context.submit_dir.resolve(),
        context.job_template_dir.resolve(),
        (context.root / ".yadof/workspace.json").resolve(),
        storage.campaign_lock_path.resolve(),
    )
    for target in targets:
        if all_recorded_data and not target.is_relative_to(context.root):
            raise RuntimeError(f"refusing to clear path outside workspace: {target}")
        if any(
            target == path or target in path.parents or path in target.parents
            for path in protected
        ):
            raise RuntimeError(f"refusing to clear protected workspace path: {target}")

    lock = CampaignLock(storage.campaign_lock_path)
    lock.acquire()
    try:
        # Finish any workspace-local background writer before removing its outputs.
        try:
            from ..surrogate import deactivate_workspace

            deactivate_workspace(context)
        except ImportError:
            pass

        jobs_deleted = _clear_directory(jobs_dir)
        checkpoints_deleted = _remove_path(checkpoints_dir)
        optimization_state_deleted = _remove_path(optimization_state_dir)
        removed_record_targets: list[str] = []
        for record_target in record_targets:
            if _remove_path(record_target):
                removed_record_targets.append(str(record_target))

        jobs_dir.mkdir(parents=True, exist_ok=True)
        if all_recorded_data:
            storage.directory.mkdir(parents=True, exist_ok=True)
    finally:
        lock.release()
    return {
        "workspace": str(context.root),
        "jobs_entries_deleted": jobs_deleted,
        "surrogate_checkpoints_deleted": checkpoints_deleted,
        "optimization_state_deleted": optimization_state_deleted,
        "record_targets_deleted": tuple(removed_record_targets),
    }


__all__ = [
    "HistoryClearConfirmationRequired",
    "clear_history",
]
