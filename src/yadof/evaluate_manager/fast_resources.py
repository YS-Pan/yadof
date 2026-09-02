"""User-directed concurrency with advisory fast-backend resource observations."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path

from ..config import LoadedConfig
from .local_resources import SystemResourceSnapshot, system_resource_snapshot


@dataclass(frozen=True)
class FastWorkerPlan:
    worker_count: int
    configured_max: int
    cpus_per_worker: int
    memory_mib_per_worker: int
    scratch_disk_kib_per_worker: int
    cpu_limit: int | None
    memory_limit: int | None
    disk_limit: int | None
    system: SystemResourceSnapshot
    source: str

    def metadata(self) -> dict[str, object]:
        return {
            "fast_worker_count": self.worker_count,
            "fast_worker_configured_max": self.configured_max,
            "fast_worker_plan_source": self.source,
            "fast_resource_cpus_per_worker": self.cpus_per_worker,
            "fast_resource_memory_mib_per_worker": self.memory_mib_per_worker,
            "fast_resource_scratch_disk_kib_per_worker": (
                self.scratch_disk_kib_per_worker
            ),
            "fast_resource_cpu_worker_limit": self.cpu_limit,
            "fast_resource_memory_worker_limit": self.memory_limit,
            "fast_resource_disk_worker_limit": self.disk_limit,
            "fast_resource_limits_enforced": False,
            "fast_system_physical_cpus": self.system.physical_cpus,
            "fast_system_logical_cpus": self.system.logical_cpus,
            "fast_system_available_memory_mib": self.system.available_memory_mib,
            "fast_system_free_disk_kib": self.system.free_disk_kib,
        }

    def summary(self) -> str:
        limits = ", ".join(
            f"{name}={value if value is not None else 'unknown'}"
            for name, value in (
                ("configured", self.configured_max),
                ("advisory_cpu", self.cpu_limit),
                ("advisory_memory", self.memory_limit),
                ("advisory_scratch_disk", self.disk_limit),
            )
        )
        return f"fast: workers={self.worker_count}; {limits}; source={self.source}"


def validate_fast_configuration(config: LoadedConfig) -> Path:
    """Return a safe scratch root that cannot overlap durable/task roots."""

    scratch = config.workspace.fast_evaluation_scratch_dir.resolve()
    workspace_root = config.workspace.root.resolve()
    if scratch == workspace_root:
        raise ValueError(
            "FAST_EVALUATION_SCRATCH_DIR must not be the workspace root: "
            f"{scratch}"
        )
    protected = (
        ("job template", config.workspace.job_template_dir.resolve()),
        ("jobs", config.workspace.jobs_dir.resolve()),
        ("recorded_data", config.workspace.recorded_data_dir.resolve()),
    )
    for label, path in protected:
        if _paths_overlap(scratch, path):
            raise ValueError(
                "FAST_EVALUATION_SCRATCH_DIR must not overlap "
                f"the {label} path: {scratch} and {path}"
            )
    return scratch


def plan_fast_workers(
    config: LoadedConfig,
    *,
    population_size: int,
    configured_max: int,
    system: SystemResourceSnapshot | None = None,
) -> FastWorkerPlan:
    """Use the configured cap and observe host capacity without clamping it."""

    scratch = validate_fast_configuration(config)
    population_limit = max(1, int(population_size))
    configured_limit = min(max(1, int(configured_max)), population_limit)
    snapshot = system or system_resource_snapshot(scratch)
    cpus_per_worker = int(config.FAST_EVALUATION_CPUS_PER_WORKER)
    memory_per_worker = int(config.FAST_EVALUATION_MEMORY_MIB_PER_WORKER)
    disk_per_worker = int(config.FAST_EVALUATION_SCRATCH_DISK_KIB_PER_WORKER)

    worker_count = configured_limit
    cpu_limit: int | None = None
    memory_limit: int | None = None
    disk_limit: int | None = None
    source = "configured_limit"
    if bool(config.FAST_RESOURCE_AUTODETECT_ENABLED):
        usable_fraction = max(
            0.0, 1.0 - float(config.FAST_RESOURCE_SYSTEM_RESERVE_FRACTION)
        )
        cpu_limit = max(1, snapshot.physical_cpus // cpus_per_worker)
        if snapshot.available_memory_mib is not None:
            memory_limit = max(
                1,
                math.floor(
                    snapshot.available_memory_mib
                    * usable_fraction
                    / memory_per_worker
                ),
            )
        if snapshot.free_disk_kib is not None:
            disk_limit = max(
                1,
                math.floor(snapshot.free_disk_kib * usable_fraction / disk_per_worker),
            )
        source = "configured_limit_with_resource_observation"

    return FastWorkerPlan(
        worker_count=max(1, worker_count),
        configured_max=configured_limit,
        cpus_per_worker=cpus_per_worker,
        memory_mib_per_worker=memory_per_worker,
        scratch_disk_kib_per_worker=disk_per_worker,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        disk_limit=disk_limit,
        system=snapshot,
        source=source,
    )


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


__all__ = [
    "FastWorkerPlan",
    "plan_fast_workers",
    "validate_fast_configuration",
]
