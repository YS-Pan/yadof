"""Run-local execution of user-declared postprocessors."""
from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import BenchmarkError, PostprocessContext
from .storage import json_safe, save_state, utc_now, write_new_json

EventSink = Callable[[Mapping[str, Any]], None]


def _emit(sink: EventSink | None, **event: Any) -> None:
    if sink is not None:
        sink({"utc": utc_now(), **event})


def _load_workflow(run_root: Path) -> Any:
    workflow_root = run_root / "inputs" / "workflow"
    source = workflow_root / "benchmark.py"
    name = f"_yadof_benchmark_postprocess_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise BenchmarkError(f"cannot load run workflow snapshot: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(workflow_root))
    try:
        spec.loader.exec_module(module)
    except Exception as exc:
        raise BenchmarkError(f"run workflow snapshot import failed: {exc}") from exc
    finally:
        sys.path.remove(str(workflow_root))
        sys.modules.pop(name, None)
    return module


def _run_one(
    run_root: Path,
    item: Mapping[str, Any],
    state: dict[str, Any],
    event_sink: EventSink | None,
) -> bool:
    item_id = str(item["id"])
    item_state = state["postprocessors"][item_id]
    number = len(item_state["attempts"]) + 1
    attempt_root = run_root / "postprocessing" / item_id / "attempts" / f"{number:04d}"
    attempt_root.mkdir(parents=True, exist_ok=False)
    attempt = {
        "number": number,
        "path": attempt_root.relative_to(run_root).as_posix(),
        "status": "running",
        "created_utc": utc_now(),
        "finished_utc": None,
        "result": None,
        "error": None,
    }
    item_state["attempts"].append(attempt)
    item_state["status"] = "running"
    item_state["error"] = None
    save_state(run_root, state)
    _emit(event_sink, event="postprocessor-started", postprocessor=item_id)
    try:
        module = _load_workflow(run_root)
        callback = getattr(module, str(item["callback"]), None)
        if not callable(callback):
            raise BenchmarkError(
                f"postprocessor callback is not available: {item['callback']}"
            )
        context = PostprocessContext(
            run=run_root,
            inputs=run_root / "inputs" / "workflow",
            results=run_root / "results.json",
            visualizations=run_root / "visualizations",
            reports=run_root / "reports",
            temp=run_root / "temp",
            attempt=attempt_root,
        )
        returned = callback(context)
        result_path = attempt_root / "result.json"
        write_new_json(result_path, {"return": json_safe(returned)})
        attempt["result"] = result_path.relative_to(run_root).as_posix()
        attempt["status"] = "succeeded"
        attempt["finished_utc"] = utc_now()
        item_state["status"] = "succeeded"
        save_state(run_root, state)
        _emit(event_sink, event="postprocessor-finished", postprocessor=item_id)
        return True
    except Exception as exc:
        attempt["status"] = "failed"
        attempt["finished_utc"] = utc_now()
        attempt["error"] = str(exc)
        item_state["status"] = "failed"
        item_state["error"] = str(exc)
        save_state(run_root, state)
        _emit(
            event_sink,
            event="postprocessor-failed",
            postprocessor=item_id,
            error=str(exc),
        )
        return False


def execute_postprocessors(
    run_root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    *,
    event_sink: EventSink | None = None,
) -> bool:
    items = list(spec["workflow"].get("postprocessors", []))
    if not items:
        return True
    fail_fast = bool(spec["workflow"].get("fail_fast", False))
    succeeded = True
    for item in items:
        item_state = state["postprocessors"][str(item["id"])]
        if item_state["status"] == "succeeded":
            continue
        if not _run_one(run_root, item, state, event_sink):
            succeeded = False
            if fail_fast:
                break
    return succeeded and all(
        item["status"] == "succeeded"
        for item in state["postprocessors"].values()
    )


__all__ = ["execute_postprocessors"]
