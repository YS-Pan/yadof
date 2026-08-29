"""Persistent visible-by-default launcher for one benchmark workspace."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence

from .contracts import BenchmarkError, evidence_notice
from .storage import utc_now
from .terminal import CONSOLE_LOG_NAME

ProcessFactory = Callable[..., subprocess.Popen[Any]]


def _inspect_command(workspace: Path) -> list[str]:
    return [
        sys.executable,
        "-m",
        "yadof_benchmark",
        "inspect",
        "--workspace",
        str(workspace),
    ]


def _run_command(
    workspace: Path,
    *,
    baselines_root: Path | None,
    stream_child_output: bool,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "yadof_benchmark",
        "run",
        "--workspace",
        str(workspace),
    ]
    if baselines_root is not None:
        command.extend(["--baselines-root", str(baselines_root)])
    if stream_child_output:
        command.append("--stream-child-output")
    return command


def _command_text(command: Sequence[str]) -> str:
    if os.name == "nt":
        return subprocess.list2cmdline(list(command))
    import shlex

    return shlex.join(command)


def _powershell_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _persistent_console_command(command: Sequence[str]) -> list[str]:
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
    powershell = (
        str(
            Path(system_root)
            / "System32"
            / "WindowsPowerShell"
            / "v1.0"
            / "powershell.exe"
        )
        if system_root
        else "powershell.exe"
    )
    invocation = "& " + " ".join(
        _powershell_literal(str(part)) for part in command
    )
    completion_message = (
        "Benchmark command finished with exit code {0}. "
        "This window will remain open; type exit to close it."
    )
    script = (
        f"{invocation}; "
        "$yadofBenchmarkExitCode = $LASTEXITCODE; "
        "Write-Host ''; "
        f"Write-Host ({_powershell_literal(completion_message)} "
        "-f $yadofBenchmarkExitCode)"
    )
    return [
        powershell,
        "-NoLogo",
        "-NoProfile",
        "-NoExit",
        "-Command",
        script,
    ]


def launch_detached(
    workspace: str | Path,
    *,
    baselines_root: str | Path | None = None,
    evidence: str = "unclassified",
    hidden: bool = False,
    stream_child_output: bool = False,
    process_factory: ProcessFactory = subprocess.Popen,
) -> dict[str, Any]:
    """Start the workspace in a new console and return an inspection receipt."""

    root = Path(workspace).resolve()
    if not root.is_dir():
        raise BenchmarkError(f"workspace does not exist: {root}")
    if os.name != "nt":
        raise BenchmarkError(
            "detached launch requires a caller-owned visible terminal or terminal "
            "multiplexer on this platform; run in the foreground instead"
        )
    selected_baselines = (
        None if baselines_root is None else Path(baselines_root).resolve()
    )
    log_path = root / CONSOLE_LOG_NAME
    stdout_path = root / "detached.stdout.log"
    stderr_path = root / "detached.stderr.log"
    benchmark_command = _run_command(
        root,
        baselines_root=selected_baselines,
        stream_child_output=stream_child_output,
    )
    command = (
        benchmark_command
        if hidden
        else _persistent_console_command(benchmark_command)
    )
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    flags |= getattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB", 0)
    flags |= (
        getattr(subprocess, "CREATE_NO_WINDOW", 0)
        if hidden
        else getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    )
    handles: list[Any] = []
    kwargs: dict[str, Any] = {
        "cwd": root,
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
            f"evidence={evidence}; command={_command_text(command)}\n"
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
    receipt = {
        "format": "yadof.benchmark.detached-launch",
        "pid": int(process.pid),
        "visible": not hidden,
        "window_remains_open_after_run": not hidden,
        "stream_child_output": stream_child_output,
        "evidence": {
            "class": evidence,
            "notice": evidence_notice(evidence),
        },
        "workspace": str(root),
        "log": str(log_path),
        "inspect": _command_text(_inspect_command(root)),
    }
    if hidden:
        receipt["stdout"] = str(stdout_path)
        receipt["stderr"] = str(stderr_path)
    return receipt


__all__ = ["launch_detached"]
