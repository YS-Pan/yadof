from __future__ import annotations

from datetime import datetime
import time
from typing import Mapping

from ..recorded_data import api as recorded_api
from ..workspace import WorkspaceContext
from .types import SurrogateState


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def monotonic_time() -> float:
    return time.monotonic()


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
        "member_count": _safe_int(history.get("member_count"), 0),
        "device": str(history.get("device", "")),
        "skipped": bool(history.get("skipped", False)),
        "skip_reason": str(history.get("skip_reason", "")),
        "mean_relative_error": float(state.mean_relative_error),
        "historical_relative_error_p50": list(state.historical_relative_error_p50),
        "historical_relative_error_p90": list(state.historical_relative_error_p90),
        "historical_relative_error_p95": list(state.historical_relative_error_p95),
        "historical_absolute_error_p90": list(state.historical_absolute_error_p90),
        "checkpoint_path": str(state.checkpoint_path),
        "checkpoint_file": state.checkpoint_path.name,
        "artifact_dir": state.artifact_dir.name,
    }


def training_failure_metadata(
    *,
    generation_index: int,
    exc: BaseException,
    started_at: str | None = None,
    ended_at: str | None = None,
) -> dict[str, object]:
    ended = now_text() if ended_at is None else str(ended_at)
    return {
        "record_type": "surrogate_training",
        "status": "error",
        "generation_index": int(generation_index),
        "started_at": "" if started_at is None else str(started_at),
        "ended_at": ended,
        "error_type": type(exc).__name__,
        "error_message": str(exc),
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
) -> dict[str, object] | None:
    return record_surrogate_metadata(
        workspace,
        training_failure_metadata(
            generation_index=int(generation_index),
            exc=exc,
            started_at=started_at,
            ended_at=ended_at,
        )
    )


def _safe_int(value: object, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)
