from __future__ import annotations

import json
import math
import os
from pathlib import Path

from project import config
from project.optimize.api import run_generations


def _int_env(name: str, default: int) -> int:
    text = os.environ.get(name)
    return int(text) if text not in (None, "") else int(default)


def _bool_env(name: str) -> bool:
    return str(os.environ.get(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def main() -> int:
    generations = _int_env("YADOF_GENERATIONS", int(getattr(config, "OPTIMIZE_GENERATIONS", 1)))
    start_generation = _int_env("YADOF_START_GENERATION", int(getattr(config, "OPTIMIZE_START_GENERATION", 0)))

    print("project config:", config.__file__, flush=True)
    print("evaluation mode:", config.EVALUATION_MODE, flush=True)
    print("jobs dir:", config.JOBS_DIR, flush=True)
    print("population size:", config.OPTIMIZE_POPULATION_SIZE, flush=True)
    print("random seed:", config.OPTIMIZE_RANDOM_SEED, flush=True)
    print("generation count:", generations, flush=True)
    print("start generation:", start_generation, flush=True)
    print("starting optimization", flush=True)

    results = run_generations(
        generations,
        start_generation=start_generation,
        population_size=None,
        random_seed=None,
    )

    for result in results:
        print(
            f"gen={result.generation_index} "
            f"source={result.source} "
            f"surrogate={result.surrogate_used} "
            f"history={result.history_count} "
            f"costs={result.costs[:2]}",
            flush=True,
        )
        if _bool_env("YADOF_FAIL_ON_ALL_INF") and _all_inf(result.costs):
            _print_recent_job_failures(Path(config.JOBS_DIR))
            raise RuntimeError(
                f"generation {result.generation_index} produced no finite cost rows; "
                "treating this as a failed distributed optimization run"
            )
    print("finished optimization", flush=True)
    return 0


def _all_inf(costs) -> bool:
    rows = tuple(tuple(float(value) for value in row) for row in costs)
    return bool(rows) and not any(math.isfinite(value) for row in rows for value in row)


def _print_recent_job_failures(jobs_dir: Path, limit: int = 8) -> None:
    print("recent job failure summaries:", flush=True)
    metadata_files = sorted(
        jobs_dir.glob("*/metadata.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not metadata_files:
        print("  no metadata.json files found under jobs dir", flush=True)
        return

    shown = 0
    for path in metadata_files:
        if shown >= int(limit):
            break
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"  {path.parent.name}: could not read metadata.json: {exc}", flush=True)
            shown += 1
            continue

        status = str(metadata.get("status", ""))
        if status not in {"error", "timeout"}:
            continue
        shown += 1
        print(f"  {path.parent.name}: status={status}", flush=True)
        for key in (
            "failure_stage",
            "error_type",
            "error_message",
            "error",
            "condor_return_value",
            "condor_abnormal_termination",
            "condor_terminal_reason",
            "condor_submit_stdout_tail",
            "condor_submit_stderr_tail",
            "stdout_tail",
            "stderr_tail",
            "batch_log_tail",
            "condor_log_tail",
            "traceback_tail",
        ):
            value = metadata.get(key)
            if value not in (None, ""):
                print(f"    {key}: {_one_line(value)}", flush=True)

    if shown == 0:
        print("  no recent error or timeout metadata found", flush=True)


def _one_line(value) -> str:
    return " ".join(str(value).split())[:1600]


if __name__ == "__main__":
    raise SystemExit(main())
