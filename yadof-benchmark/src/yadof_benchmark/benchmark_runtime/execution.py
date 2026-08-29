"""Exact-cell materialization, subprocess logging, and resume."""
from __future__ import annotations

import os
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contracts import BenchmarkError, CommandResult
from .postprocessing import execute_postprocessors
from .results import collect_cell, publish_results
from .naming import slug
from .storage import (
    latest_attempt,
    load_run,
    mark_interrupted,
    prepare_attempt,
    save_state,
    utc_now,
    write_new_json,
)

EventSink = Callable[[Mapping[str, Any]], None]
CommandRunner = Callable[..., CommandResult]
Collector = Callable[[Path, Mapping[str, Any]], dict[str, Any]]

_YADOF_PROGRESS = re.compile(
    r"^\[yadof\] (?P<phase>smoke|generation (?P<generation>\d+)) "
    r"\([^)]*\) \[[#.]+\] (?P<finished>\d+)/(?P<total>\d+) "
    r"successful=(?P<successful>\d+) errors=(?P<errors>\d+) "
    r"remaining=(?P<remaining>\d+)\s*$"
)


def _emit(sink: EventSink | None, **event: Any) -> None:
    if sink is not None:
        sink({"utc": utc_now(), **event})


def _parse_yadof_progress(line: str) -> dict[str, Any] | None:
    """Return one complete progress snapshot from a piped yadof child."""

    match = _YADOF_PROGRESS.fullmatch(line.strip())
    if match is None:
        return None
    generation_text = match.group("generation")
    return {
        "phase": match.group("phase"),
        "generation": (
            None if generation_text is None else int(generation_text)
        ),
        "finished": int(match.group("finished")),
        "total": max(1, int(match.group("total"))),
        "successful": int(match.group("successful")),
        "errors": int(match.group("errors")),
        "remaining": int(match.group("remaining")),
    }


def _command_integer(command: Sequence[str], option: str) -> int | None:
    try:
        index = list(command).index(option)
        return int(command[index + 1])
    except (IndexError, TypeError, ValueError):
        return None


def _emit_child_progress(
    snapshots: queue.Queue[dict[str, Any]],
    *,
    command: Sequence[str],
    label: str,
    event_sink: EventSink | None,
) -> None:
    """Render queued child snapshots from the foreground command owner."""

    generations = max(1, _command_integer(command, "--generations") or 1)
    population = max(1, _command_integer(command, "--population-size") or 1)
    planned = generations * population
    for _ in range(4096):
        try:
            snapshot = snapshots.get_nowait()
        except queue.Empty:
            break
        if int(snapshot["finished"]) <= 0:
            # Cell start already owns the zero state. Waiting for the first
            # completed evaluation avoids a redundant 0% refresh/log entry and
            # makes the first child-derived update observably real.
            continue
        generation = snapshot["generation"]
        absolute = int(snapshot["finished"])
        if generation is not None:
            absolute += int(generation) * int(snapshot["total"])
        _emit(
            event_sink,
            event="cell-progress",
            label=label,
            phase=snapshot["phase"],
            generation=generation,
            generation_number=(
                None if generation is None else int(generation) + 1
            ),
            generations=max(
                generations,
                1 if generation is None else int(generation) + 1,
            ),
            evaluations=absolute,
            planned_evaluations=max(planned, absolute),
            successful=int(snapshot["successful"]),
            errors=int(snapshot["errors"]),
            remaining=int(snapshot["remaining"]),
        )


def _state_progress(state: Mapping[str, Any]) -> dict[str, int]:
    cells = list(state.get("cells", {}).values())
    completed = sum(item.get("status") == "collected" for item in cells)
    failed = sum(
        item.get("status") == "failed"
        or (
            item.get("status") != "collected"
            and bool(item.get("error"))
        )
        for item in cells
    )
    finished = completed + failed
    return {
        "total_cells": len(cells),
        "finished_cells": finished,
        "completed_cells": completed,
        "failed_cells": failed,
        "remaining_cells": max(0, len(cells) - finished),
    }


def _stop_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
        )
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def _start_process(command: Sequence[str], cwd: Path) -> subprocess.Popen[str]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    try:
        return subprocess.Popen(
            list(command),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
        )
    except OSError as exc:
        raise BenchmarkError(f"cannot start command: {exc}") from exc


def _drain(
    source: Any,
    destination: Path,
    last_activity: list[float],
    lock: threading.Lock,
    progress_snapshots: queue.Queue[dict[str, Any]],
) -> None:
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        for line in iter(source.readline, ""):
            stream.write(line)
            stream.flush()
            snapshot = _parse_yadof_progress(line)
            if snapshot is not None:
                progress_snapshots.put(snapshot)
            with lock:
                last_activity[0] = time.monotonic()
    source.close()


def _watch(
    process: subprocess.Popen[str],
    *,
    started: float,
    timeout_seconds: int,
    last_activity: list[float],
    lock: threading.Lock,
    label: str,
    command: Sequence[str],
    progress_snapshots: queue.Queue[dict[str, Any]],
    event_sink: EventSink | None,
) -> bool:
    next_update = started
    while process.poll() is None:
        now = time.monotonic()
        if now - started >= timeout_seconds:
            _stop_process_tree(process)
            return True
        _emit_child_progress(
            progress_snapshots,
            command=command,
            label=label,
            event_sink=event_sink,
        )
        if now >= next_update:
            with lock:
                inactive = now - last_activity[0]
            _emit(
                event_sink,
                event="command-progress",
                label=label,
                elapsed_seconds=round(now - started, 3),
                inactivity_seconds=round(inactive, 3),
            )
            next_update = now + 5.0
        time.sleep(0.05)
    _emit_child_progress(
        progress_snapshots,
        command=command,
        label=label,
        event_sink=event_sink,
    )
    return False


def _finish_command(
    command: Sequence[str],
    command_root: Path,
    label: str,
    process: subprocess.Popen[str],
    started: float,
    started_utc: str,
    timed_out: bool,
    event_sink: EventSink | None,
) -> CommandResult:
    duration = time.monotonic() - started
    result = CommandResult(
        tuple(str(item) for item in command),
        int(process.returncode),
        duration,
        timed_out,
        command_root / "stdout.log",
        command_root / "stderr.log",
    )
    write_new_json(
        command_root / "finished.json",
        {
            "label": label,
            "command": list(command),
            "returncode": result.returncode,
            "timed_out": timed_out,
            "duration_seconds": duration,
            "started_utc": started_utc,
            "finished_utc": utc_now(),
            "stdout": result.stdout.name,
            "stderr": result.stderr.name,
        },
    )
    _emit(
        event_sink,
        event="command-finished",
        label=label,
        returncode=result.returncode,
        timed_out=timed_out,
        duration_seconds=round(duration, 3),
    )
    return result


def run_logged(
    command: Sequence[str],
    *,
    cwd: Path,
    command_root: Path,
    label: str,
    timeout_seconds: int,
    event_sink: EventSink | None = None,
) -> CommandResult:
    command_root.mkdir(parents=True, exist_ok=False)
    started_utc = utc_now()
    write_new_json(
        command_root / "started.json",
        {
            "label": label,
            "command": list(command),
            "cwd": str(cwd),
            "started_utc": started_utc,
            "timeout_seconds": timeout_seconds,
        },
    )
    started = time.monotonic()
    last_activity = [started]
    activity_lock = threading.Lock()
    progress_snapshots: queue.Queue[dict[str, Any]] = queue.Queue()
    process = _start_process(command, cwd)
    _emit(
        event_sink,
        event="command-started",
        label=label,
        pid=process.pid,
        log_dir=str(command_root),
    )
    threads = [
        threading.Thread(
            target=_drain,
            args=(
                process.stdout,
                command_root / "stdout.log",
                last_activity,
                activity_lock,
                progress_snapshots,
            ),
            daemon=True,
        ),
        threading.Thread(
            target=_drain,
            args=(
                process.stderr,
                command_root / "stderr.log",
                last_activity,
                activity_lock,
                progress_snapshots,
            ),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    try:
        timed_out = _watch(
            process,
            started=started,
            timeout_seconds=timeout_seconds,
            last_activity=last_activity,
            lock=activity_lock,
            label=label,
            command=command,
            progress_snapshots=progress_snapshots,
            event_sink=event_sink,
        )
    except BaseException:
        _stop_process_tree(process)
        raise
    finally:
        process.wait()
        for thread in threads:
            thread.join(timeout=5)
    _emit_child_progress(
        progress_snapshots,
        command=command,
        label=label,
        event_sink=event_sink,
    )
    return _finish_command(
        command, command_root, label, process, started, started_utc, timed_out, event_sink
    )


def _resource_check(execution: Mapping[str, Any]) -> None:
    resource = execution.get("resource")
    if resource in (None, {}):
        return
    if not isinstance(resource, Mapping):
        raise BenchmarkError("baseline execution.resource must be an object")
    kind = resource.get("kind")
    variable = resource.get("variable")
    if kind not in {"environment", "environment_executable"}:
        raise BenchmarkError(f"unknown baseline resource kind: {kind!r}")
    if not isinstance(variable, str) or not variable:
        raise BenchmarkError("baseline resource variable is missing")
    value = os.environ.get(variable)
    if not value:
        raise BenchmarkError(f"required environment variable is not set: {variable}")
    if kind == "environment_executable" and not Path(value).is_file():
        raise BenchmarkError(
            f"{variable} does not name a readable executable file: {value}"
        )


def _record_command(
    run_root: Path,
    attempt: dict[str, Any],
    command_root: Path,
    result: CommandResult,
) -> None:
    attempt["commands"].append(command_root.relative_to(run_root).as_posix())
    attempt["runtime_seconds"] += result.duration_seconds
    attempt["active_command"] = None


def _command_failure(label: str, result: CommandResult) -> BenchmarkError:
    suffix = " after timeout" if result.timed_out else ""
    return BenchmarkError(
        f"{label} failed with exit code {result.returncode}{suffix}; "
        f"see {result.stderr}"
    )


def _require_nonempty_file(path: Path, *, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BenchmarkError(f"{label} did not create a non-empty artifact: {path}")


def _render_cell_outputs(
    run_root: Path,
    attempt_root: Path,
    workspace: Path,
    attempt: dict[str, Any],
    cell: Mapping[str, Any],
    state: dict[str, Any],
    *,
    python: str,
    command_runner: CommandRunner,
    event_sink: EventSink | None,
) -> dict[str, Any]:
    cell_id = str(cell["id"])
    cost_dir = run_root / "visualizations" / "cost"
    cost_dir.mkdir(parents=True, exist_ok=True)
    attempt_number = int(attempt["number"])
    cost_path = cost_dir / f"{cell_id}--attempt-{attempt_number:04d}.png"
    cost_root = attempt_root / "commands" / "03-view-cost"
    attempt["active_command"] = cost_root.relative_to(run_root).as_posix()
    save_state(run_root, state)
    cost = command_runner(
        [
            python,
            "-m",
            "yadof",
            "view",
            "cost",
            "--workspace",
            str(workspace),
            "--output",
            str(cost_path),
        ],
        cwd=workspace,
        command_root=cost_root,
        label="view-cost",
        timeout_seconds=600,
        event_sink=event_sink,
    )
    _record_command(run_root, attempt, cost_root, cost)
    if cost.returncode:
        raise _command_failure("yadof view cost", cost)
    _require_nonempty_file(cost_path, label="yadof view cost")

    postprocessor = workspace / "postprocess.py"
    if not postprocessor.is_file():
        raise BenchmarkError(f"baseline postprocessor does not exist: {postprocessor}")
    baseline_dir = run_root / "visualizations" / slug(str(cell["baseline"]))
    baseline_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{cell_id}--attempt-{attempt_number:04d}--"
    postprocess_root = attempt_root / "commands" / "04-postprocess"
    attempt["active_command"] = postprocess_root.relative_to(run_root).as_posix()
    save_state(run_root, state)
    domain = command_runner(
        [
            python,
            str(postprocessor),
            "--workspace",
            str(workspace),
            "--output-dir",
            str(baseline_dir),
            "--output-prefix",
            prefix,
        ],
        cwd=workspace,
        command_root=postprocess_root,
        label="baseline-postprocess",
        timeout_seconds=600,
        event_sink=event_sink,
    )
    _record_command(run_root, attempt, postprocess_root, domain)
    if domain.returncode:
        raise _command_failure("baseline postprocess", domain)
    domain_outputs = sorted(
        path for path in baseline_dir.iterdir()
        if path.is_file() and path.name.startswith(prefix) and path.stat().st_size > 0
    )
    if not domain_outputs:
        raise BenchmarkError(
            f"baseline postprocess created no non-empty artifact with prefix {prefix!r}"
        )
    return {
        "cost": cost_path.relative_to(run_root).as_posix(),
        "domain": [path.relative_to(run_root).as_posix() for path in domain_outputs],
    }


def _execute_cell(
    run_root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    cell: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
    event_sink: EventSink | None,
) -> bool:
    cell_state = state["cells"][str(cell["id"])]
    attempt_root, workspace, attempt = prepare_attempt(run_root, cell, state)
    timeout = int(cell.get("execution", {}).get("timeout_seconds", 7200))
    python = str(spec["workflow"]["python"])
    try:
        _resource_check(cell.get("execution", {}))
        check_root = attempt_root / "commands" / "01-check"
        attempt["active_command"] = check_root.relative_to(run_root).as_posix()
        save_state(run_root, state)
        check = command_runner(
            [python, "-m", "yadof", "check", "--workspace", str(workspace)],
            cwd=workspace,
            command_root=check_root,
            label="check",
            timeout_seconds=min(timeout, 600),
            event_sink=event_sink,
        )
        _record_command(run_root, attempt, check_root, check)
        if check.returncode:
            raise _command_failure("yadof check", check)
        attempt["status"] = "checked"
        cell_state["status"] = "checked"
        save_state(run_root, state)

        command = [
            python, "-m", "yadof", "run", "--workspace", str(workspace),
            "--generations", str(cell["generations"]),
            "--population-size", str(cell["population"]),
            "--random-seed", str(cell["seed"]), "--no-smoke-test",
            "--fail-on-all-infinite",
        ]
        mode = cell.get("execution", {}).get("mode")
        if mode:
            command.extend(["--mode", str(mode)])
        run_command_root = attempt_root / "commands" / "02-run"
        attempt["active_command"] = run_command_root.relative_to(run_root).as_posix()
        attempt["status"] = "running"
        cell_state["status"] = "running"
        save_state(run_root, state)
        measured = command_runner(
            command,
            cwd=workspace,
            command_root=run_command_root,
            label="run",
            timeout_seconds=timeout,
            event_sink=event_sink,
        )
        _record_command(run_root, attempt, run_command_root, measured)
        if measured.returncode:
            raise _command_failure("yadof run", measured)
        attempt["status"] = "succeeded"
        attempt["finished_utc"] = utc_now()
        cell_state["status"] = "succeeded"
        save_state(run_root, state)
        return True
    except Exception as exc:
        attempt["active_command"] = None
        attempt["status"] = "failed"
        attempt["finished_utc"] = utc_now()
        attempt["error"] = str(exc)
        cell_state["status"] = "failed"
        cell_state["error"] = str(exc)
        save_state(run_root, state)
        _emit(
            event_sink,
            event="cell-failed",
            cell=cell["id"],
            error=str(exc),
            **_state_progress(state),
        )
        return False


def _collect_succeeded(
    run_root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    cell: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
    collector: Collector,
    event_sink: EventSink | None,
) -> bool:
    cell_state = state["cells"][str(cell["id"])]
    attempt_root, attempt = latest_attempt(run_root, cell_state)
    workspace = run_root / str(attempt["workspace"])
    result: dict[str, Any] | None = None
    try:
        result = collector(workspace, cell)
        result["runtime_seconds"] = attempt.get("runtime_seconds", 0.0)
        visualizations = _render_cell_outputs(
            run_root,
            attempt_root,
            workspace,
            attempt,
            cell,
            state,
            python=str(spec["workflow"]["python"]),
            command_runner=command_runner,
            event_sink=event_sink,
        )
        result["visualizations"] = visualizations
        result_path = attempt_root / "result.json"
        write_new_json(result_path, result)
        attempt["result"] = result_path.relative_to(run_root).as_posix()
        attempt["status"] = "collected"
        cell_state["status"] = "collected"
        cell_state["error"] = None
        save_state(run_root, state)
        _emit(
            event_sink,
            event="cell-collected",
            cell=cell["id"],
            **_state_progress(state),
        )
        return True
    except Exception as exc:
        if result is not None:
            issues = result.setdefault("issues", [])
            if isinstance(issues, list):
                issues.append(f"required visualization failed: {exc}")
            result_path = attempt_root / "result.json"
            if not result_path.exists():
                write_new_json(result_path, result)
                attempt["result"] = result_path.relative_to(run_root).as_posix()
            attempt["active_command"] = None
            attempt["status"] = "failed"
            attempt["finished_utc"] = utc_now()
            attempt["error"] = f"required visualization failed: {exc}"
            cell_state["status"] = "failed"
            cell_state["error"] = attempt["error"]
            event = "visualization-failed"
        else:
            cell_state["status"] = "succeeded"
            cell_state["error"] = f"collection failed: {exc}"
            event = "collection-failed"
        save_state(run_root, state)
        _emit(
            event_sink,
            event=event,
            cell=cell["id"],
            error=str(exc),
            **_state_progress(state),
        )
        return False


def execute_existing_run(
    run: str | Path,
    *,
    command_runner: CommandRunner = run_logged,
    collector: Collector = collect_cell,
    event_sink: EventSink | None = None,
) -> dict[str, Any]:
    run_root = Path(run).resolve()
    spec, state = load_run(run_root)
    if not (run_root / "driver" / "benchmark_runtime" / "__init__.py").is_file():
        raise BenchmarkError(f"run driver snapshot is incomplete: {run_root}")
    if state["status"] == "completed":
        return state
    mark_interrupted(run_root, state)
    state["status"] = "running"
    save_state(run_root, state)
    _emit(
        event_sink,
        event="run-started",
        run=str(run_root),
        **_state_progress(state),
    )
    cell_by_id = {str(cell["id"]): cell for cell in spec["cells"]}
    fail_fast = bool(spec["workflow"].get("fail_fast", False))
    for cell_id in [str(cell["id"]) for cell in spec["cells"]]:
        cell = cell_by_id[cell_id]
        cell_state = state["cells"][cell_id]
        if cell_state["status"] == "collected":
            continue
        _emit(
            event_sink,
            event="cell-started",
            cell=cell_id,
            previous_status=cell_state.get("status"),
            previous_error=cell_state.get("error"),
            population=int(cell["population"]),
            generations=int(cell["generations"]),
            planned_evaluations=int(cell["planned_evaluations"]),
            **_state_progress(state),
        )
        if cell_state["status"] != "succeeded":
            if not _execute_cell(
                run_root,
                spec,
                state,
                cell,
                command_runner=command_runner,
                event_sink=event_sink,
            ):
                if fail_fast:
                    break
                continue
        if not _collect_succeeded(
            run_root,
            spec,
            state,
            cell,
            command_runner=command_runner,
            collector=collector,
            event_sink=event_sink,
        ) and fail_fast:
            break
        publish_results(run_root, spec, state)
    cells_complete = bool(state["cells"]) and all(
        item["status"] == "collected" for item in state["cells"].values()
    )
    if cells_complete:
        state["status"] = "postprocessing"
        save_state(run_root, state)
        publish_results(run_root, spec, state)
        processed = execute_postprocessors(
            run_root, spec, state, event_sink=event_sink
        )
        state["status"] = "completed" if processed else "failed"
    else:
        state["status"] = "failed"
    save_state(run_root, state)
    publish_results(run_root, spec, state)
    _emit(
        event_sink,
        event="run-finished",
        status=state["status"],
        run=str(run_root),
        **_state_progress(state),
    )
    return state


__all__ = ["execute_existing_run", "run_logged"]
