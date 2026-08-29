"""Visible-by-default detached launcher for long Windows benchmark runs."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .contracts import BenchmarkError
from .storage import utc_now
from .terminal import CONSOLE_LOG_NAME

ProcessFactory = Callable[..., subprocess.Popen[Any]]


def _inspect_command(run_root: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "yadof_benchmark",
        "inspect",
        "--run",
        str(run_root),
    ]


def _resume_command(run_root: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "yadof_benchmark",
        "resume",
        "--run",
        str(run_root),
    ]


def _command_text(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    import shlex

    return shlex.join(command)


def launch_detached(
    run: str | Path,
    *,
    hidden: bool = False,
    process_factory: ProcessFactory = subprocess.Popen,
) -> dict[str, Any]:
    """Start a run in a new console and return an immediate inspection receipt."""

    run_root = Path(run).resolve()
    if not run_root.is_dir():
        raise BenchmarkError(f"run does not exist: {run_root}")
    if os.name != "nt":
        raise BenchmarkError(
            "detached launch requires a caller-owned visible terminal or terminal "
            "multiplexer on this platform; run in the foreground instead"
        )
    log_path = run_root / CONSOLE_LOG_NAME
    stdout_path = run_root / "detached.stdout.log"
    stderr_path = run_root / "detached.stderr.log"
    command = _resume_command(run_root)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # Codex and other automation hosts commonly place the caller in a
    # kill-on-close job. A new console alone does not leave that job, so the
    # benchmark would be terminated as soon as the launch command returned.
    flags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    flags |= (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if hidden
        else getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    )
    handles: list[Any] = []
    kwargs: dict[str, Any] = {
        "cwd": run_root,
        "creationflags": flags,
        "close_fds": True,
    }
    if hidden:
        stdout_path.touch(exist_ok=True)
        stderr_path.touch(exist_ok=True)
        stdout_handle = stdout_path.open("a", encoding="utf-8", newline="\n")
        stderr_handle = stderr_path.open("a", encoding="utf-8", newline="\n")
        handles.extend((stdout_handle, stderr_handle))
        kwargs.update(
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(
            f"{utc_now()} detached launch requested; hidden={hidden}; "
            f"command={_command_text(command)}\n"
        )
    try:
        process = process_factory(command, **kwargs)
    except OSError as exc:
        with log_path.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"{utc_now()} detached launch failed: {exc}\n")
        raise BenchmarkError(f"cannot launch detached benchmark: {exc}") from exc
    finally:
        for handle in handles:
            handle.close()
    inspect_command = _inspect_command(run_root)
    receipt = {
        "format": "yadof.benchmark.detached-launch",
        "pid": int(process.pid),
        "visible": not hidden,
        "run": str(run_root),
        "log": str(log_path),
        "inspect": _command_text(inspect_command),
    }
    if hidden:
        receipt["stdout"] = str(stdout_path)
        receipt["stderr"] = str(stderr_path)
    return receipt


__all__ = ["launch_detached"]
