"""Bounded surrogate training-event publication primitives."""

from __future__ import annotations

from datetime import datetime
import time
from typing import Mapping

from ...recorded_data import api as recorded_api
from ...workspace import WorkspaceContext


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def monotonic_time() -> float:
    return time.monotonic()


def failure_metadata(
    *,
    generation_index: int,
    exc: BaseException,
    model: str = "",
    started_at: str | None = None,
    ended_at: str | None = None,
    strategy_signature: str = "",
) -> dict[str, object]:
    payload: dict[str, object] = {
        "record_type": "surrogate_training",
        "status": "error",
        "generation_index": int(generation_index),
        "started_at": "" if started_at is None else str(started_at),
        "ended_at": now_text() if ended_at is None else str(ended_at),
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "strategy_signature": str(strategy_signature),
    }
    if model:
        payload["model"] = str(model)
    return payload


def record_training_event(
    workspace: WorkspaceContext, metadata: Mapping[str, object]
) -> dict[str, object] | None:
    try:
        return recorded_api.record_surrogate_metadata(workspace, dict(metadata))
    except Exception:
        return None
