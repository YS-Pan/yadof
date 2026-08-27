from __future__ import annotations

from datetime import datetime
import time
from typing import Mapping

from ...recorded_data import api as recorded_api
from ...workspace import WorkspaceContext
from .modeling import MODEL_NAME
from .types import HierarchicalState


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def monotonic_time() -> float:
    return time.monotonic()


def training_success_metadata(
    state: HierarchicalState,
    *,
    started_at: str,
    ended_at: str,
    duration_sec: float,
) -> dict[str, object]:
    history = dict(state.train_history or {})
    return {
        "record_type": "surrogate_training",
        "status": "completed",
        "generation_index": int(state.generation_index),
        "started_at": str(started_at),
        "ended_at": str(ended_at),
        "duration_sec": float(duration_sec),
        "model": MODEL_NAME,
        "sample_count": int(state.sample_count),
        "train_sample_count": int(history.get("train_design_count", 0)),
        "validation_sample_count": int(
            history.get("validation_design_count", 0)
        ),
        "member_count": int(history.get("member_count", 0)),
        "device": str(history.get("device", "")),
        "skipped": bool(history.get("skipped", False)),
        "skip_reason": str(history.get("skip_reason", "")),
        "training_policy": str(history.get("training_policy", "")),
        "strategy_signature": state.strategy_signature,
        "state_signature": state.state_signature,
        "run_namespace": state.run_namespace,
        "component_namespace": state.component_namespace,
        "checkpoint_path": str(state.checkpoint_path),
        "namespace_manifest_path": str(state.namespace_manifest_path),
        "artifact_dir": str(state.artifact_dir),
    }


def training_failure_metadata(
    *,
    generation_index: int,
    exc: BaseException,
    started_at: str | None = None,
    strategy_signature: str = "",
) -> dict[str, object]:
    return {
        "record_type": "surrogate_training",
        "status": "error",
        "generation_index": int(generation_index),
        "started_at": "" if started_at is None else str(started_at),
        "ended_at": now_text(),
        "model": MODEL_NAME,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "strategy_signature": str(strategy_signature),
    }


def record_surrogate_metadata(
    workspace: WorkspaceContext, metadata: Mapping[str, object]
) -> dict[str, object] | None:
    try:
        return recorded_api.record_surrogate_metadata(workspace, dict(metadata))
    except Exception:
        return None


def record_training_success(
    workspace: WorkspaceContext,
    state: HierarchicalState,
    *,
    started_at: str,
    ended_at: str,
    duration_sec: float,
) -> dict[str, object] | None:
    return record_surrogate_metadata(
        workspace,
        training_success_metadata(
            state,
            started_at=started_at,
            ended_at=ended_at,
            duration_sec=duration_sec,
        ),
    )


def record_training_failure(
    workspace: WorkspaceContext,
    *,
    generation_index: int,
    exc: BaseException,
    started_at: str | None = None,
    strategy_signature: str = "",
) -> dict[str, object] | None:
    return record_surrogate_metadata(
        workspace,
        training_failure_metadata(
            generation_index=generation_index,
            exc=exc,
            started_at=started_at,
            strategy_signature=strategy_signature,
        ),
    )


__all__ = [
    "monotonic_time",
    "now_text",
    "record_training_failure",
    "record_training_success",
]
