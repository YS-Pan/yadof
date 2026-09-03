"""Execution of user-declared postprocessors in one workspace."""
from __future__ import annotations

import importlib.util
import sys
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import BenchmarkError, BenchmarkStorageError, PostprocessContext
from .storage import json_safe, save_state, utc_now, write_new_json

EventSink = Callable[[Mapping[str, Any]], None]


def _emit(sink: EventSink | None, **event: Any) -> None:
    if sink is not None:
        sink({"utc": utc_now(), **event})


def _load_workflow(workspace: Path) -> Any:
    source = workspace / "benchmark.py"
    name = f"_yadof_benchmark_postprocess_{uuid.uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, source)
    if spec is None or spec.loader is None:
        raise BenchmarkError(f"cannot load workspace workflow: {source}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(workspace))
    try:
        spec.loader.exec_module(module)
    except BenchmarkStorageError:
        raise
    except Exception as exc:
        raise BenchmarkError(f"workspace workflow import failed: {exc}") from exc
    finally:
        sys.path.remove(str(workspace))
        sys.modules.pop(name, None)
    return module


def _run_one(
    workspace: Path,
    item: Mapping[str, Any],
    state: dict[str, Any],
    event_sink: EventSink | None,
) -> bool:
    item_id = str(item["id"])
    item_state = state["postprocessors"][item_id]
    output = workspace / "postprocessing" / item_id
    output.mkdir(parents=True, exist_ok=False)
    item_state["created_utc"] = utc_now()
    item_state["status"] = "running"
    item_state["error"] = None
    save_state(workspace, state)
    _emit(event_sink, event="postprocessor-started", postprocessor=item_id)
    try:
        module = _load_workflow(workspace)
        callback = getattr(module, str(item["callback"]), None)
        if not callable(callback):
            raise BenchmarkError(
                f"postprocessor callback is not available: {item['callback']}"
            )
        context = PostprocessContext(
            workspace=workspace,
            resources=workspace / "resources",
            results=workspace / "results.json",
            visualizations=workspace / "visualizations",
            reports=workspace / "reports",
            temp=workspace / "temp",
            output=output,
        )
        result_path = output / "result.json"
        write_new_json(result_path, {"return": json_safe(callback(context))})
        item_state["result"] = result_path.relative_to(workspace).as_posix()
        item_state["status"] = "succeeded"
        item_state["finished_utc"] = utc_now()
        save_state(workspace, state)
        _emit(event_sink, event="postprocessor-finished", postprocessor=item_id)
        return True
    except BenchmarkStorageError:
        raise
    except Exception as exc:
        item_state["status"] = "failed"
        item_state["finished_utc"] = utc_now()
        item_state["error"] = str(exc)
        save_state(workspace, state)
        _emit(
            event_sink,
            event="postprocessor-failed",
            postprocessor=item_id,
            error=str(exc),
        )
        return False


def execute_postprocessors(
    workspace: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    *,
    event_sink: EventSink | None = None,
) -> bool:
    items = list(spec["workflow"].get("postprocessors", []))
    if not items:
        return True
    fail_fast = bool(spec["workflow"].get("fail_fast", False))
    cells_complete = bool(state["cells"]) and all(
        cell["status"] == "collected" for cell in state["cells"].values()
    )
    succeeded = True
    for item in items:
        if not cells_complete and not item.get("run_on_failure", False):
            item_state = state["postprocessors"][str(item["id"])]
            item_state.update(status="skipped", finished_utc=utc_now(),
                              skip_reason="requires every cell to be collected")
            save_state(workspace, state)
            continue
        if not _run_one(workspace, item, state, event_sink):
            succeeded = False
            if fail_fast:
                break
    return succeeded and all(
        item["status"] in {"succeeded", "skipped"}
        for item in state["postprocessors"].values()
    )


__all__ = ["execute_postprocessors"]
