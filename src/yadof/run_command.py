"""Implementation of the installed ``yadof run`` command."""

from __future__ import annotations

from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import sys
from typing import Iterator

from .config import ConfigError, load_config
from .evaluate_manager import run_smoke_test
from .optimize import AllInfiniteGenerationError, run_generations


def run_from_args(args) -> int:
    overrides = {}
    if args.mode is not None:
        overrides["EVALUATION_MODE"] = args.mode
    try:
        config = load_config(args.workspace, overrides=overrides)
    except (ConfigError, OSError, TypeError, ValueError) as exc:
        print(f"yadof: error: run configuration is invalid: {exc}", file=sys.stderr)
        return 1

    mode = str(config.EVALUATION_MODE)
    smoke_enabled = (
        bool(config.OPTIMIZE_SMOKE_TEST_ENABLED)
        if args.smoke_test is None
        else bool(args.smoke_test)
    )
    _print_run_summary(
        config,
        mode=mode,
        generations=args.generations,
        start_generation=args.start_generation,
        population_size=args.population_size,
        random_seed=args.random_seed,
        smoke_enabled=smoke_enabled,
        smoke_source=(
            config.source_for("OPTIMIZE_SMOKE_TEST_ENABLED")
            if args.smoke_test is None
            else "CLI override"
        ),
    )

    try:
        with _progress_environment(bool(args.progress)):
            if smoke_enabled:
                print(
                    "Starting real-task smoke test "
                    "(one midpoint individual, no generation/per-job timeout).",
                    flush=True,
                )
                smoke_costs = run_smoke_test(config.workspace, mode=mode)
                print(f"Smoke test costs: {smoke_costs[0]!r}", flush=True)
                if _all_infinite(smoke_costs):
                    _print_recent_job_failures(config.workspace.jobs_dir)
                    print(
                        "yadof: error: smoke test returned no finite objective; "
                        "optimization was not started",
                        file=sys.stderr,
                    )
                    return 1

            results = run_generations(
                config.workspace,
                args.generations,
                start_generation=args.start_generation,
                population_size=args.population_size,
                random_seed=args.random_seed,
                config_overrides=overrides,
                fail_on_all_infinite=bool(args.fail_on_all_infinite),
            )
    except AllInfiniteGenerationError as exc:
        _print_result(exc.result)
        _print_recent_job_failures(config.workspace.jobs_dir)
        print(f"yadof: error: {exc}", file=sys.stderr)
        return 1
    except (ConfigError, ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        _print_recent_job_failures(config.workspace.jobs_dir)
        print(f"yadof: error: optimization could not run: {exc}", file=sys.stderr)
        return 1

    for result in results:
        _print_result(result)
    print(
        f"Optimization finished: {len(results)} generation(s) in "
        f"{config.workspace.root}",
        flush=True,
    )
    return 0


def _print_run_summary(
    config,
    *,
    mode: str,
    generations: int,
    start_generation: int,
    population_size: int | None,
    random_seed: int | None,
    smoke_enabled: bool,
    smoke_source: str,
) -> None:
    print(f"Workspace: {config.workspace.root}", flush=True)
    print(f"Evaluation mode: {mode}", flush=True)
    print(f"Jobs directory: {config.workspace.jobs_dir}", flush=True)
    print(
        "Population size: "
        f"{config.OPTIMIZE_POPULATION_SIZE if population_size is None else population_size}",
        flush=True,
    )
    print(
        "Random seed: "
        f"{config.OPTIMIZE_RANDOM_SEED if random_seed is None else random_seed}",
        flush=True,
    )
    print(f"Generation count: {generations}", flush=True)
    print(f"Start generation: {start_generation}", flush=True)
    print(f"Smoke test: {smoke_enabled} ({smoke_source})", flush=True)


def _print_result(result) -> None:
    print(
        f"gen={result.generation_index} source={result.source} "
        f"surrogate={result.surrogate_used} history={result.history_count} "
        f"costs={result.costs[:2]}",
        flush=True,
    )


def _all_infinite(costs) -> bool:
    rows = tuple(tuple(float(value) for value in row) for row in costs)
    return bool(rows) and not any(
        math.isfinite(value) for row in rows for value in row
    )


def _print_recent_job_failures(jobs_dir: Path, limit: int = 8) -> None:
    metadata_files = sorted(
        Path(jobs_dir).glob("*/metadata.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    failures: list[tuple[Path, dict[str, object]]] = []
    for path in metadata_files:
        try:
            metadata = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if str(metadata.get("status", "")) in {"error", "timeout"}:
            failures.append((path, metadata))
        if len(failures) >= int(limit):
            break
    if not failures:
        return
    print("Recent job failures:", file=sys.stderr)
    for path, metadata in failures:
        details = []
        for key in (
            "failure_stage",
            "error_type",
            "error_message",
            "error",
            "condor_terminal_reason",
            "stderr_tail",
        ):
            value = metadata.get(key)
            if value not in (None, ""):
                details.append(f"{key}={_one_line(value)}")
        suffix = "; ".join(details) if details else "no detail recorded"
        print(
            f"  {path.parent.name}: status={metadata.get('status')}; {suffix}",
            file=sys.stderr,
        )


def _one_line(value: object) -> str:
    return " ".join(str(value).split())[:1600]


@contextmanager
def _progress_environment(enabled: bool) -> Iterator[None]:
    name = "YADOF_PROGRESS"
    previous = os.environ.get(name)
    try:
        if enabled:
            os.environ[name] = "1"
        else:
            os.environ.pop(name, None)
        yield
    finally:
        if previous is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = previous


__all__ = ["run_from_args"]
