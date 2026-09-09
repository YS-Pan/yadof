"""Benchmark-local native thread limits and host commit-memory protection."""
from __future__ import annotations

from contextlib import contextmanager
import ctypes
from ctypes import wintypes
from dataclasses import asdict, dataclass
import os
import threading
from typing import Mapping

from .contracts import BenchmarkError

GIB = 1024**3
NATIVE_THREAD_LIMITS = dict.fromkeys((
    "OPENBLAS_NUM_THREADS", "OPENBLAS_DEFAULT_NUM_THREADS", "GOTO_NUM_THREADS",
    "OMP_NUM_THREADS", "MKL_NUM_THREADS", "BLIS_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "NUMEXPR_MAX_THREADS",
), "1")


class BenchmarkResourceError(BenchmarkError):
    """Host resource exhaustion stops all cells, independently of fail_fast."""


def child_environment(environ: Mapping[str, str] | None = None) -> dict[str, str]:
    # A per-Popen copy avoids races between concurrently launched cells and sets
    # limits before NumPy/BLAS import in the child and its spawned descendants.
    return {**(os.environ if environ is None else environ), **NATIVE_THREAD_LIMITS}


@dataclass(frozen=True)
class MemorySnapshot:
    physical_total: int
    physical_available: int
    commit_total: int | None = None
    commit_limit: int | None = None


class _PerformanceInformation(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in (
        "CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable",
        "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize",
    )] + [(name, wintypes.DWORD) for name in ("HandleCount", "ProcessCount", "ThreadCount")]


def memory_snapshot() -> MemorySnapshot:
    if os.name != "nt":
        import psutil
        memory = psutil.virtual_memory()
        return MemorySnapshot(memory.total, memory.available)
    # This small native query does not enumerate the system process table, which
    # can itself fail with WinError 1455 while the commit limit is exhausted.
    library = ctypes.WinDLL("psapi", use_last_error=True)
    function = library.GetPerformanceInfo
    function.argtypes = [ctypes.POINTER(_PerformanceInformation), wintypes.DWORD]
    function.restype = wintypes.BOOL
    info = _PerformanceInformation()
    info.cb = ctypes.sizeof(info)
    if not function(ctypes.byref(info), info.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return MemorySnapshot(info.PhysicalTotal * info.PageSize, info.PhysicalAvailable * info.PageSize,
                          info.CommitTotal * info.PageSize, info.CommitLimit * info.PageSize)


def memory_pressure(snapshot: MemorySnapshot) -> str | None:
    physical_reserve = max(GIB, int(0.10 * snapshot.physical_total))
    if snapshot.physical_available < physical_reserve:
        return f"available physical memory {snapshot.physical_available} bytes is below reserve {physical_reserve}"
    if snapshot.commit_limit is not None and snapshot.commit_total is not None:
        reserve = max(2 * GIB, int(0.20 * snapshot.commit_limit))
        available = snapshot.commit_limit - snapshot.commit_total
        if available < reserve:
            return f"available system commit {available} bytes is below reserve {reserve}"
    return None


def job_commit_budget(snapshot: MemorySnapshot) -> int:
    assert snapshot.commit_limit is not None and snapshot.commit_total is not None
    reserve = max(2 * GIB, int(0.20 * snapshot.commit_limit))
    return min(int(0.60 * snapshot.commit_limit), max(0, snapshot.commit_limit - snapshot.commit_total - reserve))


class _BasicLimits(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class _IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                                                  "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class _ExtendedLimits(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", _BasicLimits), ("IoInfo", _IoCounters)] + [
        (name, ctypes.c_size_t) for name in ("ProcessMemoryLimit", "JobMemoryLimit", "PeakProcessMemoryUsed", "PeakJobMemoryUsed")]


class WindowsMemoryJob:
    """Limit aggregate private commit for attached command roots and descendants."""
    def __init__(self, limit_bytes: int):
        self.limit_bytes = int(limit_bytes)
        if self.limit_bytes <= 0:
            raise BenchmarkResourceError("no commit-memory budget remains for benchmark children")
        self.library = ctypes.WinDLL("kernel32", use_last_error=True)
        self.library.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.library.CreateJobObjectW.restype = wintypes.HANDLE
        self.library.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.library.SetInformationJobObject.restype = wintypes.BOOL
        self.library.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.library.AssignProcessToJobObject.restype = wintypes.BOOL
        self.library.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self.library.OpenProcess.restype = wintypes.HANDLE
        self.library.CloseHandle.argtypes = [wintypes.HANDLE]
        self.library.CloseHandle.restype = wintypes.BOOL
        self.handle = self.library.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = _ExtendedLimits()
        # JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE.
        # The controller is not a job member; closing only stops its command trees.
        info.BasicLimitInformation.LimitFlags = 0x200 | 0x2000
        info.JobMemoryLimit = self.limit_bytes
        if not self.library.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process) -> None:
        handle = self.library.OpenProcess(0x100 | 0x1, False, process.pid)
        if not handle:
            if process.poll() is not None:
                return
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not self.library.AssignProcessToJobObject(self.handle, handle):
                if process.poll() is not None:
                    return
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            self.library.CloseHandle(handle)

    def close(self):
        if self.handle:
            self.library.CloseHandle(self.handle)
            self.handle = None


class ResourceCancellation(threading.Event):
    """Shared cancellation plus independent, low-allocation memory watchdog."""
    def __init__(self, *, reader=None):
        super().__init__()
        self.reader = reader or memory_snapshot
        self.failure = None
        self.latest = None
        self.initial = None
        self.job = None
        self._stop = threading.Event()
        self._thread = None
        self._failure_lock = threading.Lock()

    def fail(self, message):
        with self._failure_lock:
            self.failure = self.failure or str(message)
        self.set()

    def check(self):
        self.raise_if_failed()
        try:
            self.latest = self.reader()
            pressure = memory_pressure(self.latest)
            if pressure:
                self.fail(pressure)
        except Exception as error:
            self.fail(f"cannot verify host memory reserve: {type(error).__name__}: {error}")
        self.raise_if_failed()

    def raise_if_failed(self):
        if self.failure:
            raise BenchmarkResourceError(self.failure)

    def start(self):
        self.check()
        self.initial = self.latest
        if os.name == "nt":
            self.job = WindowsMemoryJob(job_commit_budget(self.initial))
        self._thread = threading.Thread(target=self._watch, daemon=True, name="benchmark-memory-guard")
        self._thread.start()

    def _watch(self):
        while not self._stop.wait(0.25):
            try:
                self.check()
            except BenchmarkResourceError:
                return

    def assign(self, process):
        self.check()
        if self.job is not None:
            try:
                self.job.assign(process)
            except Exception as error:
                self.fail(f"cannot protect command process tree with a commit limit: {error}")
                self.raise_if_failed()

    def metadata(self):
        return {"initial_memory": asdict(self.initial) if self.initial else None,
                "latest_memory": asdict(self.latest) if self.latest else None,
                "native_thread_limits": dict(NATIVE_THREAD_LIMITS),
                "system_commit_reserve_fraction": 0.20, "physical_memory_reserve_fraction": 0.10,
                "windows_job_commit_limit_bytes": self.job.limit_bytes if self.job else None,
                "failure": self.failure}

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self.job:
            self.job.close()


@contextmanager
def cancel_on_error(event):
    try:
        yield
    except BaseException:
        event.set()
        raise
