from __future__ import annotations

import json
import importlib
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from project import config

from .gpsaf import OptimizationResult


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def new_run_id() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return f"opt_{stamp}_{uuid4().hex[:8]}"


def job_names() -> tuple[str, ...]:
    try:
        recorded_api = importlib.import_module("project.recorded_data.api")
        func = getattr(recorded_api, "get_job_names", None)
        if callable(func):
            return tuple(str(name) for name in func())
    except Exception:
        return ()
    return ()


def created_job_names(before: tuple[str, ...], after: tuple[str, ...]) -> tuple[str, ...]:
    before_counts: dict[str, int] = {}
    for name in before:
        before_counts[name] = before_counts.get(name, 0) + 1

    created = []
    for name in after:
        count = before_counts.get(name, 0)
        if count > 0:
            before_counts[name] = count - 1
        else:
            created.append(name)
    return tuple(created)


def _checkpoint_dir(checkpoint_dir: str | Path | None) -> Path:
    return Path(config.OPTIMIZE_CHECKPOINT_DIR if checkpoint_dir is None else checkpoint_dir)


def write_generation_metadata(
    *,
    run_id: str,
    result: OptimizationResult,
    started_at: str,
    ended_at: str,
    jobs_before: tuple[str, ...],
    jobs_after: tuple[str, ...],
    checkpoint_dir: str | Path | None = None,
) -> Path:
    run_dir = _checkpoint_dir(checkpoint_dir) / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "run_id": str(run_id),
        "generation_index": int(result.generation_index),
        "source": str(result.source),
        "surrogate_used": bool(result.surrogate_used),
        "history_count": int(result.history_count),
        "population_size": int(len(result.population)),
        "population": [list(row) for row in result.population],
        "created_job_names": list(created_job_names(jobs_before, jobs_after)),
        "started_at": str(started_at),
        "ended_at": str(ended_at),
        "diagnostics": {
            key: value
            for key, value in result.diagnostics.items()
            if key not in {"costs", "pred_costs", "cost_intervals"}
        },
    }
    path = run_dir / f"generation_{int(result.generation_index):06d}.json"
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    index_path = run_dir / "run.jsonl"
    with index_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, sort_keys=True) + "\n")
    return path
