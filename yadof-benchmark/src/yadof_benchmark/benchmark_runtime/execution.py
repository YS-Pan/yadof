"""Cell materialization, subprocess logging, and workspace execution."""
from __future__ import annotations

import json
import os
import queue
import re
import signal
import subprocess
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from .contracts import BenchmarkError, BenchmarkStorageError, CommandResult
from .capacity import CapacityPolicy, cell_with_capacity, validate_capacity_decision
from .concurrency import detect_physical_cores
from .memory_guard import (
    BenchmarkResourceError, NATIVE_THREAD_LIMITS, ResourceCancellation,
    cancel_on_error, child_environment,
)
from .postprocessing import execute_postprocessors
from .results import collect_cell, publish_results
from .storage import (
    load_execution,
    prepare_cell,
    save_state,
    utc_now,
    write_new_json,
)

EventSink = Callable[[Mapping[str, Any]], None]
CommandRunner = Callable[..., CommandResult]
Collector = Callable[[Path, Mapping[str, Any]], dict[str, Any]]

_YADOF_PROGRESS = re.compile(
    r"^\[yadof\] (?P<phase>smoke|population|evaluation|generation (?P<generation>\d+)) "
    r"\([^)]*\) \[[#.]+\] (?P<finished>\d+)/(?P<total>\d+) "
    r"successful=(?P<successful>\d+) errors=(?P<errors>\d+) "
    r"remaining=(?P<remaining>\d+)\s*$"
)


class _YadofProgressTracker:
    """Infer batch boundaries only from observed child evaluation snapshots."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = -1
        self._last_finished: int | None = None
        self._last_remaining: int | None = None
        self._completed: dict[int, tuple[int, int, int]] = {}

    def parse(self, line: str) -> dict[str, Any] | None:
        match = _YADOF_PROGRESS.fullmatch(line.strip())
        if match is None:
            return None
        finished = int(match.group("finished"))
        total = max(1, int(match.group("total")))
        successful = int(match.group("successful"))
        errors = int(match.group("errors"))
        remaining = int(match.group("remaining"))
        generation_text = match.group("generation")
        with self._lock:
            if generation_text is not None:
                generation = int(generation_text)
                self._generation = max(self._generation, generation)
            else:
                if self._generation < 0:
                    self._generation = 0
                elif (
                    self._last_finished is not None
                    and (
                        finished < self._last_finished
                        or (
                            self._last_remaining == 0
                            and finished != self._last_finished
                        )
                    )
                ):
                    self._generation += 1
                generation = self._generation
            evaluations_before = sum(
                item[0] for index, item in self._completed.items() if index < generation
            )
            successful_before = sum(
                item[1] for index, item in self._completed.items() if index < generation
            )
            errors_before = sum(
                item[2] for index, item in self._completed.items() if index < generation
            )
            if remaining <= 0:
                self._completed[generation] = (total, successful, errors)
            self._last_finished = finished
            self._last_remaining = remaining
        return {
            "phase": match.group("phase"),
            "generation": generation,
            "finished": finished,
            "total": total,
            "successful": successful_before + successful,
            "errors": errors_before + errors,
            "remaining": remaining,
            "evaluations_before": evaluations_before,
        }


def _state_guard(lock: threading.RLock | None):
    return nullcontext() if lock is None else lock


def _emit(sink: EventSink | None, **event: Any) -> None:
    if sink is not None:
        sink({"utc": utc_now(), **event})


def _cell_sink(
    sink: EventSink | None,
    cell: Mapping[str, Any],
) -> EventSink | None:
    if sink is None:
        return None

    def bound(event: Mapping[str, Any]) -> None:
        sink(
            {
                **event,
                "cell": str(cell["id"]),
                "display_label": str(
                    cell.get("display_label", cell["id"])
                ),
            }
        )

    return bound


def _emit_progress(
    sink: EventSink | None,
    progress_path: Path,
    **event: Any,
) -> None:
    value = {"utc": utc_now(), **event}
    with progress_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(
            json.dumps(
                value,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
    if sink is not None:
        sink(value)


def _parse_yadof_progress(
    line: str,
    tracker: _YadofProgressTracker | None = None,
) -> dict[str, Any] | None:
    """Return one complete progress snapshot from a piped yadof child."""

    return (tracker or _YadofProgressTracker()).parse(line)


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
    progress_path: Path,
    event_sink: EventSink | None,
) -> None:
    """Render queued child snapshots from the foreground command owner."""

    generations = max(1, _command_integer(command, "--generations") or 1)
    population = max(1, _command_integer(command, "--population-size") or 1)
    batch_size = _command_integer(command, "--batch-size") or population
    initial_population = _command_integer(command, "--initial-population-size") or population
    planned = initial_population + (generations - 1) * batch_size
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
        absolute = int(snapshot.get("evaluations_before", 0)) + int(
            snapshot["finished"]
        )
        _emit_progress(
            event_sink,
            progress_path,
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
            finished=int(snapshot["finished"]),
            total=int(snapshot["total"]),
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
        psutil_cleanup_complete = False
        try:
            import psutil
        except ImportError:
            psutil = None
        if psutil is not None:
            try:
                parent = psutil.Process(process.pid)
                descendants = parent.children(recursive=True)
                for target in reversed(descendants):
                    try:
                        target.kill()
                    except psutil.NoSuchProcess:
                        pass
                _, alive = psutil.wait_procs(descendants, timeout=10)
                for target in alive:
                    try:
                        target.kill()
                    except psutil.NoSuchProcess:
                        pass
                if alive:
                    _, alive = psutil.wait_procs(alive, timeout=5)
                # Keep the parent alive until every enumerated descendant is
                # gone, so taskkill /T can still traverse the tree on fallback.
                if not alive:
                    try:
                        parent.kill()
                    except psutil.NoSuchProcess:
                        pass
                    _, parent_alive = psutil.wait_procs([parent], timeout=10)
                    psutil_cleanup_complete = not parent_alive
            except (OSError, psutil.Error):
                # Fall through to Windows' recursive tree termination when
                # process enumeration races or the host denies access.
                pass
        if not psutil_cleanup_complete and process.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _start_process(command: Sequence[str], cwd: Path, *, resource_guard=None) -> subprocess.Popen[str]:
    flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
    if resource_guard is not None:
        resource_guard.check()
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=child_environment(),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
            start_new_session=os.name != "nt",
        )
    except OSError as exc:
        if getattr(exc, "winerror", None) in {8, 14, 1455}:
            raise BenchmarkResourceError(f"cannot start command due to memory exhaustion: {exc}") from exc
        raise BenchmarkError(f"cannot start command: {exc}") from exc
    if resource_guard is not None:
        try:
            resource_guard.assign(process)
        except BaseException:
            _stop_process_tree(process)
            raise
    return process


def _drain(
    source: Any,
    destination: Path,
    last_activity: list[float],
    lock: threading.Lock,
    progress_snapshots: queue.Queue[dict[str, Any]],
    progress_tracker: _YadofProgressTracker,
    output_lines: queue.Queue[tuple[str, str]] | None,
    stream_name: str,
) -> None:
    with destination.open("x", encoding="utf-8", newline="\n") as stream:
        for line in iter(source.readline, ""):
            stream.write(line)
            stream.flush()
            snapshot = _parse_yadof_progress(line, progress_tracker)
            if snapshot is not None:
                progress_snapshots.put(snapshot)
            if output_lines is not None:
                output_lines.put((stream_name, line.rstrip("\r\n")))
            with lock:
                last_activity[0] = time.monotonic()
    source.close()


def _emit_child_output(
    output_lines: queue.Queue[tuple[str, str]] | None,
    event_sink: EventSink | None,
) -> None:
    if output_lines is None:
        return
    for _ in range(4096):
        try:
            stream_name, line = output_lines.get_nowait()
        except queue.Empty:
            break
        _emit(
            event_sink,
            event="child-output",
            stream=stream_name,
            text=line,
        )


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
    progress_path: Path,
    output_lines: queue.Queue[tuple[str, str]] | None,
    event_sink: EventSink | None,
    cancel_event: threading.Event | None,
) -> bool:
    next_update = started
    while process.poll() is None:
        now = time.monotonic()
        if cancel_event is not None and cancel_event.is_set():
            _stop_process_tree(process)
            return False
        if now - started >= timeout_seconds:
            _stop_process_tree(process)
            return True
        _emit_child_progress(
            progress_snapshots,
            command=command,
            label=label,
            progress_path=progress_path,
            event_sink=event_sink,
        )
        _emit_child_output(output_lines, event_sink)
        if now >= next_update:
            with lock:
                inactive = now - last_activity[0]
            _emit_progress(
                event_sink,
                progress_path,
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
        progress_path=progress_path,
        event_sink=event_sink,
    )
    _emit_child_output(output_lines, event_sink)
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
            "process_tree_cleanup": (
                "requested-and-parent-exited" if timed_out else "not-required"
            ),
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
        process_tree_cleanup=(
            "requested-and-parent-exited" if timed_out else "not-required"
        ),
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
    stream_child_output: bool = False,
    cancel_event: threading.Event | None = None,
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
            "native_thread_limits": dict(NATIVE_THREAD_LIMITS),
        },
    )
    started = time.monotonic()
    last_activity = [started]
    activity_lock = threading.Lock()
    progress_snapshots: queue.Queue[dict[str, Any]] = queue.Queue()
    progress_tracker = _YadofProgressTracker()
    output_lines: queue.Queue[tuple[str, str]] | None = (
        queue.Queue(maxsize=4096) if stream_child_output else None
    )
    process = _start_process(command, cwd, resource_guard=(
        cancel_event if isinstance(cancel_event, ResourceCancellation) else None
    ))
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
                progress_tracker,
                output_lines,
                "stdout",
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
                progress_tracker,
                output_lines,
                "stderr",
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
            progress_path=command_root / "progress.jsonl",
            output_lines=output_lines,
            event_sink=event_sink,
            cancel_event=cancel_event,
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
        progress_path=command_root / "progress.jsonl",
        event_sink=event_sink,
    )
    _emit_child_output(output_lines, event_sink)
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
    root: Path,
    cell_state: dict[str, Any],
    command_root: Path,
    result: CommandResult,
) -> None:
    cell_state["commands"].append(command_root.relative_to(root).as_posix())
    cell_state["runtime_seconds"] += result.duration_seconds
    cell_state["active_command"] = None


def _run_command(
    command_runner: CommandRunner,
    command: Sequence[str],
    *,
    cwd: Path,
    command_root: Path,
    label: str,
    timeout_seconds: int,
    event_sink: EventSink | None,
    stream_child_output: bool,
    cancel_event: threading.Event | None = None,
) -> CommandResult:
    kwargs: dict[str, Any] = {
        "cwd": cwd,
        "command_root": command_root,
        "label": label,
        "timeout_seconds": timeout_seconds,
        "event_sink": event_sink,
    }
    if stream_child_output:
        kwargs["stream_child_output"] = True
    if cancel_event is not None and command_runner is run_logged:
        kwargs["cancel_event"] = cancel_event
    return command_runner(command, **kwargs)


def _command_failure(label: str, result: CommandResult) -> BenchmarkError:
    suffix = " after timeout" if result.timed_out else ""
    stderr = Path(result.stderr)
    if stderr.is_file():
        with stderr.open("rb") as stream:
            stream.seek(max(0, stderr.stat().st_size - 65536))
            tail = stream.read().decode("utf-8", errors="replace")
        if re.search(r"MemoryError|WinError\s+(?:8|14|1455)\b|paging file is too small|not enough memory", tail, re.IGNORECASE):
            return BenchmarkResourceError(
                f"{label} failed due to memory exhaustion; stopped all cells; see {result.stderr}"
            )
    return BenchmarkError(
        f"{label} failed with exit code {result.returncode}{suffix}; "
        f"see {result.stderr}"
    )


def _require_nonempty_file(path: Path, *, label: str) -> None:
    if not path.is_file() or path.stat().st_size <= 0:
        raise BenchmarkError(f"{label} did not create a non-empty artifact: {path}")


def _render_cell_outputs(
    root: Path,
    cell_root: Path,
    workspace: Path,
    cell_state: dict[str, Any],
    cell: Mapping[str, Any],
    state: dict[str, Any],
    *,
    python: str,
    command_runner: CommandRunner,
    event_sink: EventSink | None,
    stream_child_output: bool,
    state_lock: threading.RLock | None = None,
    cancel_event: threading.Event | None = None,
) -> dict[str, Any]:
    cell_id = str(cell["id"])
    cost_dir = root / "visualizations" / "cost"
    cost_dir.mkdir(parents=True, exist_ok=True)
    cost_path = cost_dir / f"{cell_id}.png"
    cost_root = cell_root / "commands" / "03-view-cost"
    with _state_guard(state_lock):
        cell_state["active_command"] = cost_root.relative_to(root).as_posix()
        save_state(root, state)
    cost = _run_command(
        command_runner,
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
        stream_child_output=stream_child_output,
        cancel_event=cancel_event,
    )
    with _state_guard(state_lock):
        _record_command(root, cell_state, cost_root, cost)
    if cost.returncode:
        raise _command_failure("yadof view cost", cost)
    _require_nonempty_file(cost_path, label="yadof view cost")

    postprocessor = workspace / "postprocess.py"
    if not postprocessor.is_file():
        raise BenchmarkError(f"baseline postprocessor does not exist: {postprocessor}")
    domain_dir = root / "visualizations" / "domain"
    domain_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{cell_id}--"
    postprocess_root = cell_root / "commands" / "04-postprocess"
    with _state_guard(state_lock):
        cell_state["active_command"] = postprocess_root.relative_to(root).as_posix()
        save_state(root, state)
    domain = _run_command(
        command_runner,
        [
            python,
            str(postprocessor),
            "--workspace",
            str(workspace),
            "--output-dir",
            str(domain_dir),
            "--output-prefix",
            prefix,
        ],
        cwd=workspace,
        command_root=postprocess_root,
        label="baseline-postprocess",
        timeout_seconds=600,
        event_sink=event_sink,
        stream_child_output=stream_child_output,
        cancel_event=cancel_event,
    )
    with _state_guard(state_lock):
        _record_command(root, cell_state, postprocess_root, domain)
    if domain.returncode:
        raise _command_failure("baseline postprocess", domain)
    domain_outputs = sorted(
        path
        for path in domain_dir.iterdir()
        if path.is_file()
        and path.name.startswith(prefix)
        and path.stat().st_size > 0
    )
    if not domain_outputs:
        raise BenchmarkError(
            f"baseline postprocess created no non-empty artifact with prefix {prefix!r}"
        )
    return {
        "cost": cost_path.relative_to(root).as_posix(),
        "domain": [path.relative_to(root).as_posix() for path in domain_outputs],
    }


def _execute_cell(
    root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    cell: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
    event_sink: EventSink | None,
    stream_child_output: bool,
    state_lock: threading.RLock | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    cell_event_sink = _cell_sink(event_sink, cell)
    with _state_guard(state_lock):
        cell_root, workspace, cell_state = prepare_cell(root, spec, cell, state)
        resolved_concurrency = cell_state.get("simulation_concurrency")
    if isinstance(resolved_concurrency, Mapping):
        _emit(
            cell_event_sink,
            event="simulation-concurrency-resolved",
            simulator_workers=resolved_concurrency.get("resolved_max_workers"),
            simulator_physical_cores=resolved_concurrency.get("physical_cores"),
            simulator_physical_core_multiplier=resolved_concurrency.get(
                "physical_core_multiplier"
            ),
        )
    timeout = int(cell.get("execution", {}).get("timeout_seconds", 7200))
    python = str(spec["workflow"]["python"])
    try:
        _resource_check(cell.get("execution", {}))
        from ..runtime_freeze import verify_runtime
        verify_runtime(root)
        if cell.get("top10_reference") is not None:
            from ..perfect_protocol import prepare_control
            prepare_control(root, spec, state, cell, workspace)
        check_root = cell_root / "commands" / "01-check"
        with _state_guard(state_lock):
            cell_state["active_command"] = check_root.relative_to(root).as_posix()
            save_state(root, state)
        check = _run_command(
            command_runner,
            [python, "-m", "yadof", "check", "--workspace", str(workspace)],
            cwd=workspace,
            command_root=check_root,
            label="check",
            timeout_seconds=min(timeout, 600),
            event_sink=cell_event_sink,
            stream_child_output=stream_child_output,
            cancel_event=cancel_event,
        )
        with _state_guard(state_lock):
            _record_command(root, cell_state, check_root, check)
        if check.returncode:
            raise _command_failure("yadof check", check)
        with _state_guard(state_lock):
            cell_state["status"] = "checked"
            save_state(root, state)

        command = [
            python,
            "-m",
            "yadof",
            "run",
            "--workspace",
            str(workspace),
            "--generations",
            str(cell["generations"]),
            "--population-size",
            str(cell["population"]),
            "--batch-size",
            str(cell.get("batch_size") or cell["population"]),
            "--initial-population-size",
            str(cell.get("initial_population") or cell["population"]),
            "--random-seed",
            str(cell["seed"]),
            "--no-smoke-test",
            "--fail-on-all-infinite",
        ]
        mode = cell.get("execution", {}).get("mode")
        if mode:
            command.extend(["--mode", str(mode)])
        run_command_root = cell_root / "commands" / "02-run"
        with _state_guard(state_lock):
            cell_state["active_command"] = run_command_root.relative_to(root).as_posix()
            cell_state["status"] = "running"
            save_state(root, state)
        measured = _run_command(
            command_runner,
            command,
            cwd=workspace,
            command_root=run_command_root,
            label="run",
            timeout_seconds=timeout,
            event_sink=cell_event_sink,
            stream_child_output=stream_child_output,
            cancel_event=cancel_event,
        )
        with _state_guard(state_lock):
            _record_command(root, cell_state, run_command_root, measured)
        if measured.returncode:
            raise _command_failure("yadof run", measured)
        with _state_guard(state_lock):
            cell_state["status"] = "succeeded"
            cell_state["finished_utc"] = utc_now()
            save_state(root, state)
        return True
    except (BenchmarkStorageError, BenchmarkResourceError):
        raise
    except Exception as exc:
        with _state_guard(state_lock):
            cell_state["active_command"] = None
            cell_state["status"] = "failed"
            cell_state["finished_utc"] = utc_now()
            cell_state["error"] = str(exc)
            save_state(root, state)
            progress = _state_progress(state)
        _emit(
            event_sink,
            event="cell-failed",
            cell=cell["id"],
            display_label=cell.get("display_label", cell["id"]),
            error=str(exc),
            **progress,
        )
        return False


def _collect_succeeded(
    root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    cell: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
    collector: Collector,
    event_sink: EventSink | None,
    stream_child_output: bool,
    state_lock: threading.RLock | None = None,
    cancel_event: threading.Event | None = None,
) -> bool:
    cell_event_sink = _cell_sink(event_sink, cell)
    with _state_guard(state_lock):
        cell_state = state["cells"][str(cell["id"])]
        cell_root = root / str(cell_state["path"])
        workspace = root / str(cell_state["workspace"])
    result: dict[str, Any] | None = None
    try:
        result = collector(workspace, cell)
        result.setdefault("cell", cell["id"])
        result.setdefault(
            "display_label",
            cell.get("display_label", cell["id"]),
        )
        result["runtime_seconds"] = cell_state.get("runtime_seconds", 0.0)
        if "capacity_revision" in cell_state:
            result["capacity_revision"] = cell_state["capacity_revision"]
            result["simulation_concurrency"] = deepcopy(cell_state["simulation_concurrency"])
        result["visualizations"] = _render_cell_outputs(
            root,
            cell_root,
            workspace,
            cell_state,
            cell,
            state,
            python=str(spec["workflow"]["python"]),
            command_runner=command_runner,
            event_sink=cell_event_sink,
            stream_child_output=stream_child_output,
            state_lock=state_lock,
            cancel_event=cancel_event,
        )
        result_path = cell_root / "result.json"
        write_new_json(result_path, result)
        with _state_guard(state_lock):
            cell_state["result"] = result_path.relative_to(root).as_posix()
            cell_state["status"] = "collected"
            cell_state["finished_utc"] = utc_now()
            cell_state["error"] = None
            save_state(root, state)
            progress = _state_progress(state)
        _emit(
            event_sink,
            event="cell-collected",
            cell=cell["id"],
            display_label=cell.get("display_label", cell["id"]),
            **progress,
        )
        return True
    except (BenchmarkStorageError, BenchmarkResourceError):
        raise
    except Exception as exc:
        with _state_guard(state_lock):
            if result is not None:
                issues = result.setdefault("issues", [])
                if isinstance(issues, list):
                    issues.append(f"required visualization failed: {exc}")
                result_path = cell_root / "result.json"
                if not result_path.exists():
                    write_new_json(result_path, result)
                    cell_state["result"] = result_path.relative_to(root).as_posix()
                cell_state["status"] = "failed"
                cell_state["error"] = f"required visualization failed: {exc}"
                event = "visualization-failed"
            else:
                cell_state["status"] = "failed"
                cell_state["error"] = f"collection failed: {exc}"
                event = "collection-failed"
            cell_state["active_command"] = None
            cell_state["finished_utc"] = utc_now()
            save_state(root, state)
            progress = _state_progress(state)
        _emit(
            event_sink,
            event=event,
            cell=cell["id"],
            display_label=cell.get("display_label", cell["id"]),
            error=str(exc),
            **progress,
        )
        return False


def _publish_or_fail(
    root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    *,
    boundary: str,
    event_sink: EventSink | None,
) -> dict[str, Any]:
    try:
        return publish_results(root, spec, state)
    except Exception as exc:
        failure = {
            "utc": utc_now(),
            "boundary": boundary,
            "error": f"{type(exc).__name__}: {exc}",
        }
        failures = state.setdefault("publication_failures", [])
        if isinstance(failures, list):
            failures.append(failure)
        state["status"] = "failed"
        state["finished_utc"] = failure["utc"]
        state_error: Exception | None = None
        try:
            save_state(root, state)
        except Exception as persistence_exc:
            state_error = persistence_exc
        _emit(
            event_sink,
            event="publication-failed",
            boundary=boundary,
            error=failure["error"],
        )
        detail = (
            "benchmark result publication failed; execution stopped before another "
            f"cell at {boundary}: {failure['error']}"
        )
        if state_error is not None:
            detail += (
                "; publication-failure state could not be persisted: "
                f"{type(state_error).__name__}: {state_error}"
            )
        raise BenchmarkError(detail) from exc


def _publication_cells_valid(
    publication: Mapping[str, Any], state: Mapping[str, Any]
) -> bool:
    summaries = publication.get("cell_summaries", [])
    return (
        isinstance(summaries, list)
        and len(summaries) == len(state.get("cells", {}))
        and all(
            isinstance(item, Mapping)
            and bool(item.get("completed"))
            and bool(item.get("valid"))
            for item in summaries
        )
    )


def _publication_cell_valid(
    publication: Mapping[str, Any], cell_id: str
) -> bool:
    summaries = publication.get("cell_summaries", [])
    if not isinstance(summaries, list):
        return False
    return any(
        isinstance(item, Mapping)
        and str(item.get("cell")) == cell_id
        and bool(item.get("completed"))
        and bool(item.get("valid"))
        for item in summaries
    )


def _process_cell(
    root: Path,
    spec: Mapping[str, Any],
    state: dict[str, Any],
    cell: Mapping[str, Any],
    *,
    command_runner: CommandRunner,
    collector: Collector,
    event_sink: EventSink | None,
    stream_child_output: bool,
    state_lock: threading.RLock,
    cancel_event: threading.Event,
) -> bool:
    if not _execute_cell(
        root,
        spec,
        state,
        cell,
        command_runner=command_runner,
        event_sink=event_sink,
        stream_child_output=stream_child_output,
        state_lock=state_lock,
        cancel_event=cancel_event,
    ):
        return False
    return _collect_succeeded(
        root,
        spec,
        state,
        cell,
        command_runner=command_runner,
        collector=collector,
        event_sink=event_sink,
        stream_child_output=stream_child_output,
        state_lock=state_lock,
        cancel_event=cancel_event,
    )


def execute_workspace(
    workspace: str | Path,
    *,
    command_runner: CommandRunner = run_logged,
    collector: Collector = collect_cell,
    event_sink: EventSink | None = None,
    stream_child_output: bool = False,
    capacity_policy: CapacityPolicy | None = None,
) -> dict[str, Any]:
    root = Path(workspace).resolve()
    spec, state = load_execution(root)
    state["status"] = "running"
    state["started_utc"] = utc_now()
    state["finished_utc"] = None
    save_state(root, state)
    _emit(
        event_sink,
        event="workspace-started",
        workspace=str(root),
        **_state_progress(state),
    )
    cell_by_id = {str(cell["id"]): cell for cell in spec["cells"]}
    fail_fast = bool(spec["workflow"].get("fail_fast", False))
    cell_order = [str(cell["id"]) for cell in spec["cells"]]
    pending = list(cell_order)
    cell_concurrency = min(
        max(1, int(spec["workflow"].get("cell_concurrency", 1))),
        max(1, len(pending)),
    )
    physical_cores = None
    capacity = {"cell_concurrency": cell_concurrency,
                "baseline_physical_core_multipliers": {}, "reason": ""}
    policy_completed_count = -1
    state_lock = threading.RLock()
    cancel_event = ResourceCancellation() if command_runner is run_logged else threading.Event()
    event_queue: queue.Queue[Mapping[str, Any]] = queue.Queue()
    worker_sink: EventSink | None = event_queue.put if event_sink is not None else None

    def drain_events() -> None:
        if event_sink is None:
            return
        while True:
            try:
                event_sink(event_queue.get_nowait())
            except queue.Empty:
                return

    active: dict[Future[bool], str] = {}
    # A threshold may be consumed only after its reference's publication barrier.
    dependencies = {}
    for cell_id, cell in cell_by_id.items():
        reference = cell.get("top10_reference")
        if reference and cell["strategy"] != reference:
            dependencies[cell_id] = next(
                other_id for other_id, other in cell_by_id.items()
                if (other["comparison"], other["baseline"], other["seed"], other["strategy"])
                == (cell["comparison"], cell["baseline"], cell["seed"], reference)
            )
    published: set[str] = set()
    stop_admission = False

    def update_capacity() -> None:
        nonlocal capacity, policy_completed_count, physical_cores
        if capacity_policy is None:
            return
        if physical_cores is None:
            physical_cores = detect_physical_cores()
        with state_lock:
            completed_count = sum(item["status"] in {"collected", "failed"}
                                  for item in state["cells"].values())
            if completed_count == policy_completed_count:
                return
            context = {"workspace": str(root), "physical_cores": physical_cores,
                       "maximum_cell_concurrency": cell_concurrency,
                       "completed_cells": completed_count,
                       "current_capacity": deepcopy(capacity),
                       "cells": deepcopy(state["cells"])}
        decision = validate_capacity_decision(
            capacity_policy(context), maximum_cells=cell_concurrency,
            baselines=spec["baselines"],
        )
        policy_completed_count = completed_count
        with state_lock:
            history = state.setdefault("capacity_history", [])
            if history and decision == capacity:
                return
            capacity = decision
            revision = {**deepcopy(capacity), "revision": len(history) + 1,
                        "utc": utc_now(), "completed_cells": completed_count,
                        "physical_cores": physical_cores}
            history.append(revision)
            state["effective_cell_concurrency"] = capacity["cell_concurrency"]
            save_state(root, state)
        _emit(event_sink, event="capacity-changed", **revision)

    try:
        if isinstance(cancel_event, ResourceCancellation):
            cancel_event.start()
            state["resource_protection"] = cancel_event.metadata()
            save_state(root, state)
        with ThreadPoolExecutor(
            max_workers=cell_concurrency,
            thread_name_prefix="yadof-benchmark-cell",
        ) as executor, cancel_on_error(cancel_event):
            while pending or active:
                if isinstance(cancel_event, ResourceCancellation):
                    cancel_event.raise_if_failed()
                try:
                    update_capacity()
                except Exception:
                    cancel_event.set()
                    raise
                while pending and len(active) < capacity["cell_concurrency"] and not stop_admission:
                    if isinstance(cancel_event, ResourceCancellation):
                        cancel_event.check()
                    ready_indices = [index for index, item in enumerate(pending)
                                     if item not in dependencies or dependencies[item] in published]
                    if capacity_policy is None:
                        ready = next(iter(ready_indices), None)
                    else:
                        # Balance ready baselines while a resource policy learns their capacities.
                        active_baselines = [cell_by_id[item]["baseline"] for item in active.values()]
                        ready = min(ready_indices, key=lambda index: (
                            active_baselines.count(cell_by_id[pending[index]]["baseline"]), index
                        ), default=None)
                    if ready is None:
                        break
                    cell_id = pending.pop(ready)
                    cell = cell_by_id[cell_id]
                    if capacity_policy is not None:
                        cell = cell_with_capacity(cell, capacity)
                        with state_lock:
                            state["cells"][cell_id]["capacity_revision"] = state["capacity_history"][-1]["revision"]
                    execution = cell.get("execution", {})
                    simulation = execution.get("simulation_concurrency", {})
                    resource = execution.get("resource", {})
                    with state_lock:
                        progress = _state_progress(state)
                    _emit(
                        event_sink,
                        event="cell-started",
                        cell=cell_id,
                        display_label=cell.get("display_label", cell_id),
                        baseline=cell.get("baseline"),
                        strategy=cell.get("strategy"),
                        seed=cell.get("seed"),
                        population=int(cell["population"]),
                        batch_size=int(cell.get("batch_size") or cell["population"]),
                        initial_population=int(cell.get("initial_population") or cell["population"]),
                        generations=int(cell["generations"]),
                        planned_evaluations=int(cell["planned_evaluations"]),
                        timeout_seconds=int(execution.get("timeout_seconds", 7200)),
                        simulator_mode=execution.get("mode"),
                        simulator_physical_core_multiplier=simulation.get(
                            "physical_core_multiplier"
                        ),
                        simulator_resource=(
                            resource.get("variable") or resource.get("kind")
                        ),
                        **progress,
                    )
                    future = executor.submit(
                        _process_cell,
                        root,
                        spec,
                        state,
                        cell,
                        command_runner=command_runner,
                        collector=collector,
                        event_sink=worker_sink,
                        stream_child_output=stream_child_output,
                        state_lock=state_lock,
                        cancel_event=cancel_event,
                    )
                    active[future] = cell_id
                if not active:
                    break
                finished, _ = wait(
                    active,
                    timeout=0.05,
                    return_when=FIRST_COMPLETED,
                )
                drain_events()
                for future in sorted(
                    finished,
                    key=lambda item: cell_order.index(active[item]),
                ):
                    cell_id = active.pop(future)
                    try:
                        succeeded = future.result()
                    except Exception:
                        cancel_event.set()
                        raise
                    drain_events()
                    try:
                        with state_lock:
                            publication = _publish_or_fail(
                                root,
                                spec,
                                state,
                                boundary=f"cell:{cell_id}",
                                event_sink=event_sink,
                            )
                    except Exception:
                        cancel_event.set()
                        raise
                    published.add(cell_id)
                    if fail_fast and (
                        not succeeded
                        or not _publication_cell_valid(publication, cell_id)
                    ):
                        stop_admission = True
                        cancel_event.set()
            drain_events()
            if isinstance(cancel_event, ResourceCancellation):
                cancel_event.raise_if_failed()
    except BaseException as exc:
        cancel_event.set()
        drain_events()
        # A command/state persistence error can bypass normal cell completion.
        # The executor has joined cancelled workers before this terminal write.
        with state_lock:
            state["status"] = "failed"
            state["finished_utc"] = state.get("finished_utc") or utc_now()
            state["execution_error"] = {
                "utc": utc_now(),
                "error": f"{type(exc).__name__}: {exc}",
            }
            if isinstance(cancel_event, ResourceCancellation):
                state["resource_protection"] = cancel_event.metadata()
            for cell_state in state["cells"].values():
                started = cell_state.get("created_utc") is not None
                if started and cell_state["status"] not in {"collected", "failed"}:
                    cell_state["status"] = "failed"
                    cell_state["finished_utc"] = state["finished_utc"]
                    cell_state["error"] = (
                        cell_state.get("error")
                        or f"execution stopped: {type(exc).__name__}: {exc}"
                    )
                cell_state["active_command"] = None
            try:
                save_state(root, state)
            except Exception as persistence_exc:
                raise BenchmarkStorageError(
                    f"{type(exc).__name__}: {exc}; could not persist failed state: "
                    f"{type(persistence_exc).__name__}: {persistence_exc}"
                ) from exc
        raise
    finally:
        if isinstance(cancel_event, ResourceCancellation):
            state["resource_protection"] = cancel_event.metadata()
            cancel_event.close()

    cells_complete = bool(state["cells"]) and all(
        item["status"] == "collected" for item in state["cells"].values()
    )
    if cells_complete or spec["workflow"].get("postprocessors"):
        state["status"] = "postprocessing"
        save_state(root, state)
        publication = _publish_or_fail(
            root,
            spec,
            state,
            boundary="pre-postprocessing",
            event_sink=event_sink,
        )
        processed = execute_postprocessors(
            root, spec, state, event_sink=event_sink
        )
        cells_valid = _publication_cells_valid(publication, state)
        state["status"] = "completed" if cells_complete and processed and cells_valid else "failed"
        if not cells_valid:
            state["validity_error"] = (
                "one or more collected cells are invalid; see cell validity reports"
            )
        else:
            state.pop("validity_error", None)
    else:
        state["status"] = "failed"
    state["finished_utc"] = utc_now()
    save_state(root, state)
    _publish_or_fail(
        root,
        spec,
        state,
        boundary="final",
        event_sink=event_sink,
    )
    _emit(
        event_sink,
        event="workspace-finished",
        status=state["status"],
        workspace=str(root),
        **_state_progress(state),
    )
    return state


__all__ = ["execute_workspace", "run_logged"]
