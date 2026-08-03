"""Shared local process-tree observation and termination helpers."""

from __future__ import annotations

import os
import signal
import subprocess
from collections.abc import Iterable

import psutil


def process_tree_pids(root_pid: int) -> tuple[int, ...]:
    """Return the live root/descendant PIDs visible at this instant."""

    try:
        root = psutil.Process(int(root_pid))
        processes = (root, *root.children(recursive=True))
    except (psutil.Error, OSError):
        return ()
    return tuple(dict.fromkeys(process.pid for process in processes))


def terminate_process_tree(
    root_pid: int,
    *,
    known_descendant_pids: Iterable[int] = (),
    process_group: bool = False,
) -> None:
    """Best-effort hard termination for one exact local worker tree."""

    root_pid = int(root_pid)
    known = {
        int(pid)
        for pid in known_descendant_pids
        if int(pid) > 0 and int(pid) != root_pid
    }
    known.update(pid for pid in process_tree_pids(root_pid) if pid != root_pid)

    if os.name == "nt":
        if psutil.pid_exists(root_pid):
            subprocess.run(
                ["taskkill", "/PID", str(root_pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        _kill_known_processes(known)
        return

    if process_group and psutil.pid_exists(root_pid):
        try:
            os.killpg(root_pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            pass
    _kill_known_processes(known)
    _kill_known_processes((root_pid,))


def terminate_descendants(
    root_pid: int,
    *,
    known_descendant_pids: Iterable[int] = (),
) -> None:
    """Best-effort termination of descendants while preserving the root."""

    root_pid = int(root_pid)
    descendants = {
        int(pid)
        for pid in known_descendant_pids
        if int(pid) > 0 and int(pid) != root_pid
    }
    descendants.update(
        pid for pid in process_tree_pids(root_pid) if pid != root_pid
    )
    _kill_known_processes(descendants)


def _kill_known_processes(pids: Iterable[int]) -> None:
    processes: list[psutil.Process] = []
    for pid in dict.fromkeys(int(value) for value in pids if int(value) > 0):
        try:
            processes.append(psutil.Process(pid))
        except (psutil.Error, OSError):
            continue
    for process in reversed(processes):
        try:
            process.kill()
        except (psutil.Error, OSError):
            continue
    if processes:
        psutil.wait_procs(processes, timeout=2.0)


__all__ = [
    "process_tree_pids",
    "terminate_descendants",
    "terminate_process_tree",
]
