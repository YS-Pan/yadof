"""HTCondor request formatting over shared resource calibration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import LoadedConfig, load_config
from ..workspace import WorkspaceContext
from .config import (
    htcondor_request_cpus,
    htcondor_request_disk,
    htcondor_request_memory,
)
from .resource_calibration import (
    disk_quantity_kib,
    estimate_resources,
    memory_quantity_mib,
    positive_float,
)
from .types import JobSpec


@dataclass(frozen=True)
class HTCondorResourceRequest:
    """One concrete resource request emitted into a generated submit file."""

    cpus: int
    memory_mib: int
    disk_kib: int
    source: str
    sample_count: int

    @property
    def memory_text(self) -> str:
        return f"{self.memory_mib}MB"

    @property
    def disk_text(self) -> str:
        return f"{self.disk_kib}KB"


def request_for_job(
    workspace: WorkspaceContext | str | Path,
    job: JobSpec,
    *,
    config: LoadedConfig | None = None,
) -> HTCondorResourceRequest:
    """Return the initial CPU, memory, and disk values for one Condor job.

    A normal distributed smoke test has no ``generation_index``.  Generation zero
    consumes those smoke-test measurements; later generations consume only the
    preceding generation from the same optimizer run.  Missing measurements leave
    the user-configured bootstrap values in effect.
    """

    effective = load_config(workspace) if config is None else config
    estimate = estimate_resources(
        effective,
        generation_index=_generation_index(job.generation_index),
        run_id=job.run_id,
        base_cpus=max(1, int(htcondor_request_cpus(effective))),
        base_memory_mib=memory_quantity_mib(
            htcondor_request_memory(effective),
            "HTCONDOR_REQUEST_MEMORY",
        ),
        base_disk_kib=disk_quantity_kib(
            htcondor_request_disk(effective),
            "HTCONDOR_REQUEST_DISK",
        ),
        autodetect_enabled=bool(effective.HTCONDOR_RESOURCE_AUTODETECT_ENABLED),
        calibrate_cpus=False,
        disk_multiplier=positive_float(
            effective.HTCONDOR_REQUEST_DISK_MULTIPLIER,
            "HTCONDOR_REQUEST_DISK_MULTIPLIER",
        ),
    )

    return HTCondorResourceRequest(
        cpus=estimate.cpus,
        memory_mib=estimate.memory_mib,
        disk_kib=estimate.disk_kib,
        source=estimate.source,
        sample_count=estimate.sample_count,
    )


def _generation_index(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
