from __future__ import annotations

from typing import Mapping

from ...workspace import WorkspaceContext
from .._shared.training_events import (
    failure_metadata,
    monotonic_time,
    now_text,
    record_training_event,
)
from .types import SurrogateState


def training_success_metadata(
    state: SurrogateState,
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
        "model": state.model_name,
        "sample_count": int(state.sample_count),
        "train_sample_count": _safe_int(history.get("train_sample_count"), int(state.sample_count)),
        "raw_sample_count_before_filter": _safe_int(history.get("raw_sample_count_before_filter"), int(state.sample_count)),
        "dropped_nonfinite_samples": _safe_int(history.get("dropped_nonfinite_samples"), 0),
        "query_count": _safe_int(history.get("query_count"), 0),
        "train_query_count_per_step": _safe_int(history.get("train_query_count_per_step"), 0),
        "configured_epochs": _safe_int(history.get("epochs"), 0),
        "effective_epochs": _safe_int(history.get("effective_epochs"), 0),
        "effective_training_steps": _safe_int(
            history.get("effective_training_steps"), 0
        ),
        "member_count": _safe_int(history.get("member_count"), 0),
        "device": str(history.get("device", "")),
        "skipped": bool(history.get("skipped", False)),
        "skip_reason": str(history.get("skip_reason", "")),
        "training_policy": str(history.get("training_policy", "real_field_balanced")),
        "strategy_signature": state.strategy_signature,
        "state_signature": state.state_signature,
        "run_namespace": state.run_namespace,
        "component_namespace": state.component_namespace,
        "checkpoint_path": str(state.checkpoint_path),
        "checkpoint_file": state.checkpoint_path.name,
        "namespace_manifest_path": str(state.namespace_manifest_path),
        "artifact_dir": str(state.artifact_dir),
    }


def training_failure_metadata(
    *,
    generation_index: int,
    exc: BaseException,
    started_at: str | None = None,
    ended_at: str | None = None,
    strategy_signature: str = "",
) -> dict[str, object]:
    return failure_metadata(
        generation_index=generation_index,
        exc=exc,
        started_at=started_at,
        ended_at=ended_at,
        strategy_signature=strategy_signature,
    )


def record_surrogate_metadata(
    workspace: WorkspaceContext, metadata: Mapping[str, object]
) -> dict[str, object] | None:
    return record_training_event(workspace, metadata)


def record_training_success(
    workspace: WorkspaceContext,
    state: SurrogateState,
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
        )
    )


def record_training_failure(
    workspace: WorkspaceContext,
    *,
    generation_index: int,
    exc: BaseException,
    started_at: str | None = None,
    ended_at: str | None = None,
    strategy_signature: str = "",
) -> dict[str, object] | None:
    return record_surrogate_metadata(
        workspace,
        training_failure_metadata(
            generation_index=int(generation_index),
            exc=exc,
            started_at=started_at,
            ended_at=ended_at,
            strategy_signature=strategy_signature,
        )
    )


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)
