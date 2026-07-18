from __future__ import annotations

from pathlib import Path
import shutil

from ..config import load_config
from ..workspace import WorkspaceContext


WorkspaceLike = WorkspaceContext | str | Path


class HistoryClearConfirmationRequired(RuntimeError):
    """Raised when destructive history cleanup lacks explicit confirmation."""


def _is_junction(path: Path) -> bool:
    checker = getattr(path, "is_junction", None)
    return bool(checker()) if callable(checker) else False


def _validate_runtime_directory(path: Path, workspace_root: Path, label: str) -> Path:
    resolved = path.resolve(strict=False)
    anchor = Path(resolved.anchor).resolve(strict=False)
    if resolved in {workspace_root.resolve(), anchor}:
        raise RuntimeError(f"refusing to clear broad {label} path: {resolved}")
    return resolved


def _remove_path(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_dir() and not path.is_symlink() and not _is_junction(path):
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
    workspace: WorkspaceLike, *, confirm: bool = False
) -> dict[str, object]:
    """Clear jobs, records, and surrogate artifacts for one explicit workspace."""

    if not confirm:
        raise HistoryClearConfirmationRequired(
            "history clearing is destructive; pass confirm=True or use CLI --yes"
        )

    config = load_config(workspace)
    context = config.workspace
    jobs_dir = _validate_runtime_directory(
        context.jobs_dir, context.root, "jobs"
    )
    checkpoints_dir = _validate_runtime_directory(
        context.surrogate_checkpoint_dir, context.root, "surrogate checkpoint"
    )
    records_dir = _validate_runtime_directory(
        context.recorded_data_dir, context.root, "recorded-data"
    )

    # Finish any workspace-local background writer before removing its outputs.
    try:
        from ..surrogate import runtime as surrogate_runtime
        from ..surrogate import scheduler as surrogate_scheduler

        surrogate_scheduler.wait_for_pending_training(context)
        surrogate_scheduler.reset_workspace_schedule(context)
        surrogate_runtime.reset_workspace_state(context)
    except ImportError:
        pass

    jobs_deleted = _clear_directory(jobs_dir)
    checkpoints_deleted = _remove_path(checkpoints_dir)
    removed_record_targets: list[str] = []
    for target in (
        records_dir / "indMeta.jsonl",
        records_dir / "indMeta.jsonl.lock",
        records_dir / "rawData.npz",
        records_dir / "optMeta",
    ):
        if _remove_path(target):
            removed_record_targets.append(str(target))
    for target in tuple(records_dir.glob("*.tmp*")):
        if _remove_path(target):
            removed_record_targets.append(str(target))

    jobs_dir.mkdir(parents=True, exist_ok=True)
    return {
        "workspace": str(context.root),
        "jobs_entries_deleted": jobs_deleted,
        "surrogate_checkpoints_deleted": checkpoints_deleted,
        "record_targets_deleted": tuple(removed_record_targets),
    }


__all__ = [
    "HistoryClearConfirmationRequired",
    "clear_history",
]
