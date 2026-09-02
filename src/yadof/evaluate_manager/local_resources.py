"""User-directed local concurrency and process-tree resource measurement."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
from threading import Event, Thread
import time
from typing import Mapping, Sequence

import psutil

from ..config import LoadedConfig

from .config import (
    htcondor_request_cpus,
    htcondor_request_disk,
    htcondor_request_memory,
)
from .resource_calibration import (
    disk_quantity_kib,
    estimate_resources,
    memory_quantity_mib,
)


@dataclass(frozen=True)
class SystemResourceSnapshot:
    """Submit-host capacity available when one local batch is planned."""

    physical_cpus: int
    logical_cpus: int
    available_memory_mib: int | None
    free_disk_kib: int | None


@dataclass(frozen=True)
class LocalWorkerPlan:
    """Effective local concurrency and the limits that produced it."""

    worker_count: int
    configured_max: int
    source: str
    estimate_source: str
    calibration_sample_count: int
    cpus_per_worker: int
    memory_mib_per_worker: int
    disk_kib_per_worker: int
    cpu_limit: int | None
    memory_limit: int | None
    disk_limit: int | None
    system: SystemResourceSnapshot

    def metadata(self) -> dict[str, object]:
        return {
            "local_worker_count": self.worker_count,
            "local_worker_configured_max": self.configured_max,
            "local_worker_plan_source": self.source,
            "local_resource_estimate_source": self.estimate_source,
            "local_resource_calibration_sample_count": self.calibration_sample_count,
            "local_resource_cpus_per_worker": self.cpus_per_worker,
            "local_resource_memory_mib_per_worker": self.memory_mib_per_worker,
            "local_resource_disk_kib_per_worker": self.disk_kib_per_worker,
            "local_resource_cpu_worker_limit": self.cpu_limit,
            "local_resource_memory_worker_limit": self.memory_limit,
            "local_resource_disk_worker_limit": self.disk_limit,
            "local_resource_limits_enforced": False,
            "local_system_physical_cpus": self.system.physical_cpus,
            "local_system_logical_cpus": self.system.logical_cpus,
            "local_system_available_memory_mib": self.system.available_memory_mib,
            "local_system_free_disk_kib": self.system.free_disk_kib,
        }

    def summary(self) -> str:
        limits = ", ".join(
            f"{name}={value if value is not None else 'unknown'}"
            for name, value in (
                ("configured", self.configured_max),
                ("advisory_cpu", self.cpu_limit),
                ("advisory_memory", self.memory_limit),
                ("advisory_disk", self.disk_limit),
            )
        )
        return (
            f"local: workers={self.worker_count}; {limits}; "
            f"estimate={self.estimate_source}; samples={self.calibration_sample_count}"
        )


def plan_local_workers(
    config: LoadedConfig,
    *,
    population_size: int,
    configured_max: int,
    generation_index: int | None,
    run_id: str | None,
    system: SystemResourceSnapshot | None = None,
    history_records: Sequence[Mapping[str, object]] | None = None,
) -> LocalWorkerPlan:
    """Use configured concurrency and observe resources without clamping it."""

    population_limit = max(1, int(population_size))
    configured_limit = min(max(1, int(configured_max)), population_limit)
    snapshot = system or system_resource_snapshot(config.workspace.jobs_dir)
    autodetect_enabled = bool(config.LOCAL_RESOURCE_AUTODETECT_ENABLED)
    estimate = estimate_resources(
        config,
        generation_index=generation_index,
        run_id=run_id,
        base_cpus=max(1, int(htcondor_request_cpus(config))),
        base_memory_mib=memory_quantity_mib(
            htcondor_request_memory(config),
            "HTCONDOR_REQUEST_MEMORY",
        ),
        base_disk_kib=disk_quantity_kib(
            htcondor_request_disk(config),
            "HTCONDOR_REQUEST_DISK",
        ),
        autodetect_enabled=autodetect_enabled,
        calibrate_cpus=True,
        disk_multiplier=1.0,
        history_records=history_records,
    )

    cpu_limit: int | None = None
    memory_limit: int | None = None
    disk_limit: int | None = None
    worker_count = configured_limit
    source = "configured_limit"
    if autodetect_enabled:
        reserve_fraction = float(config.LOCAL_RESOURCE_SYSTEM_RESERVE_FRACTION)
        usable_fraction = max(0.0, 1.0 - reserve_fraction)
        cpu_limit = max(
            1,
            snapshot.physical_cpus // max(1, estimate.cpus),
        )
        if snapshot.available_memory_mib is not None:
            memory_limit = max(
                1,
                math.floor(
                    snapshot.available_memory_mib
                    * usable_fraction
                    / max(1, estimate.memory_mib)
                ),
            )
        if snapshot.free_disk_kib is not None:
            disk_limit = max(
                1,
                math.floor(
                    snapshot.free_disk_kib
                    * usable_fraction
                    / max(1, estimate.disk_kib)
                ),
            )
        source = f"configured_limit_with_{estimate.source}_observation"

    return LocalWorkerPlan(
        worker_count=max(1, worker_count),
        configured_max=configured_limit,
        source=source,
        estimate_source=estimate.source,
        calibration_sample_count=estimate.sample_count,
        cpus_per_worker=estimate.cpus,
        memory_mib_per_worker=estimate.memory_mib,
        disk_kib_per_worker=estimate.disk_kib,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        disk_limit=disk_limit,
        system=snapshot,
    )


def system_resource_snapshot(path: str | Path) -> SystemResourceSnapshot:
    """Read physical/logical CPU, available memory, and free local disk."""

    logical_cpus = max(1, int(psutil.cpu_count(logical=True) or os.cpu_count() or 1))
    physical_cpus = max(
        1,
        int(psutil.cpu_count(logical=False) or logical_cpus),
    )
    try:
        available_memory_mib = max(
            1,
            int(psutil.virtual_memory().available // (1024**2)),
        )
    except (AttributeError, OSError):
        available_memory_mib = None
    try:
        anchor = _existing_anchor(Path(path))
        free_disk_kib = max(1, int(psutil.disk_usage(str(anchor)).free // 1024))
    except (AttributeError, OSError):
        free_disk_kib = None
    return SystemResourceSnapshot(
        physical_cpus=physical_cpus,
        logical_cpus=logical_cpus,
        available_memory_mib=available_memory_mib,
        free_disk_kib=free_disk_kib,
    )


class ProcessTreeResourceMonitor:
    """Sample one local workflow process tree without affecting its outcome."""

    def __init__(self, pid: int, *, interval_sec: float = 0.2) -> None:
        self._pid = int(pid)
        self._interval_sec = max(0.05, float(interval_sec))
        self._stop_event = Event()
        self._thread = Thread(
            target=self._run,
            name=f"yadof-resource-monitor-{self._pid}",
            daemon=True,
        )
        self._started_monotonic = time.monotonic()
        self._peak_rss_bytes = 0
        self._peak_process_count = 0
        self._cpu_seconds_by_pid: dict[int, float] = {}

    def start(self) -> None:
        self._sample()
        self._thread.start()

    def stop(self) -> dict[str, object]:
        self._sample()
        self._stop_event.set()
        self._thread.join(timeout=max(1.0, self._interval_sec * 4.0))
        elapsed_sec = max(0.0, time.monotonic() - self._started_monotonic)
        cpu_time_sec = sum(self._cpu_seconds_by_pid.values())
        metadata: dict[str, object] = {
            "local_resource_measurement_source": "psutil_process_tree",
            "local_peak_memory_usage_mib": self._peak_rss_bytes / (1024**2),
            "resource_memory_usage_mib": self._peak_rss_bytes / (1024**2),
            "local_peak_process_count": self._peak_process_count,
            "local_process_tree_cpu_time_sec": cpu_time_sec,
            "local_resource_measurement_elapsed_sec": elapsed_sec,
        }
        if elapsed_sec > 0.0 and cpu_time_sec > 0.0:
            average_cores = cpu_time_sec / elapsed_sec
            metadata["local_average_cpu_cores"] = average_cores
            metadata["resource_cpu_usage_cores"] = average_cores
        return metadata

    def _run(self) -> None:
        while not self._stop_event.wait(self._interval_sec):
            self._sample()

    def _sample(self) -> None:
        try:
            root = psutil.Process(self._pid)
            processes = (root, *root.children(recursive=True))
        except (psutil.Error, OSError):
            return
        rss_bytes = 0
        sampled_pids: set[int] = set()
        for process in processes:
            if process.pid in sampled_pids:
                continue
            sampled_pids.add(process.pid)
            try:
                with process.oneshot():
                    rss_bytes += max(0, int(process.memory_info().rss))
                    cpu_times = process.cpu_times()
                cpu_seconds = max(
                    0.0,
                    float(cpu_times.user) + float(cpu_times.system),
                )
                self._cpu_seconds_by_pid[process.pid] = max(
                    self._cpu_seconds_by_pid.get(process.pid, 0.0),
                    cpu_seconds,
                )
            except (psutil.Error, OSError):
                continue
        self._peak_rss_bytes = max(self._peak_rss_bytes, rss_bytes)
        self._peak_process_count = max(self._peak_process_count, len(sampled_pids))


def job_directory_disk_usage_kib(path: str | Path) -> int:
    """Return current recursive job-directory size, ignoring vanished files."""

    total_bytes = 0
    for root, _directories, files in os.walk(Path(path)):
        root_path = Path(root)
        for name in files:
            try:
                total_bytes += (root_path / name).stat().st_size
            except OSError:
                continue
    return max(1, math.ceil(total_bytes / 1024.0))


def with_disk_usage(metadata: Mapping[str, object], job_dir: Path) -> dict[str, object]:
    result = dict(metadata)
    disk_kib = job_directory_disk_usage_kib(job_dir)
    result["local_disk_usage_kib"] = disk_kib
    result["resource_disk_usage_kib"] = disk_kib
    return result


def _existing_anchor(path: Path) -> Path:
    candidate = path.resolve()
    while not candidate.exists() and candidate.parent != candidate:
        candidate = candidate.parent
    return candidate


__all__ = [
    "job_directory_disk_usage_kib",
    "LocalWorkerPlan",
    "plan_local_workers",
    "ProcessTreeResourceMonitor",
    "SystemResourceSnapshot",
    "system_resource_snapshot",
    "with_disk_usage",
]
