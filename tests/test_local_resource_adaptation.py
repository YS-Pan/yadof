from __future__ import annotations

from pathlib import Path

from yadof.config import load_config
from yadof.evaluate_manager import (
    fast_resources,
    local_resources,
    resource_calibration,
)
from yadof.workspace.init import init_workspace


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    init_workspace(root)
    return root


def _system() -> local_resources.SystemResourceSnapshot:
    return local_resources.SystemResourceSnapshot(
        physical_cpus=8,
        logical_cpus=16,
        available_memory_mib=32 * 1024,
        free_disk_kib=100 * 1024**2,
    )


def test_local_plan_observes_calibration_without_clamping_configured_workers(
    tmp_path,
    monkeypatch,
):
    workspace = _workspace(tmp_path)
    config = load_config(workspace)
    records = (
        {
            "status": "completed",
            "generation_index": None,
            "job_metadata": {
                "engine": "local",
                "resource_cpu_usage_cores": 2.0,
                "resource_memory_usage_mib": 6 * 1024,
                "resource_disk_usage_kib": 1024**2,
            },
        },
        {
            "status": "completed",
            "generation_index": None,
            "job_metadata": {
                "engine": "htcondor",
                "condor_cpus_usage": 3.0,
                "condor_memory_usage_mib": 8 * 1024,
                "condor_disk_usage_kib": 2 * 1024**2,
            },
        },
    )
    monkeypatch.setattr(
        resource_calibration.recorded_data_api,
        "list_records",
        lambda _workspace: records,
    )

    plan = local_resources.plan_local_workers(
        config,
        population_size=20,
        configured_max=8,
        generation_index=0,
        run_id="run-a",
        system=_system(),
    )

    assert plan.worker_count == 8
    assert plan.configured_max == 8
    assert plan.cpu_limit == 4
    assert plan.memory_limit == 2
    assert plan.source == "configured_limit_with_smoke_calibration_observation"
    assert plan.estimate_source == "smoke_calibration"
    assert plan.calibration_sample_count == 2
    assert plan.cpus_per_worker == 2
    assert plan.memory_mib_per_worker == 12 * 1024
    assert plan.disk_kib_per_worker == 2 * 1024**2


def test_local_autodetect_can_be_disabled_to_use_larger_default_cap(
    tmp_path,
):
    workspace = _workspace(tmp_path)
    config_path = workspace / "config.py"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\nLOCAL_RESOURCE_AUTODETECT_ENABLED = False\n",
        encoding="utf-8",
    )
    config = load_config(workspace)

    plan = local_resources.plan_local_workers(
        config,
        population_size=20,
        configured_max=int(config.LOCAL_EVALUATION_MAX_WORKERS),
        generation_index=0,
        run_id="run-a",
        system=_system(),
    )

    assert plan.worker_count == 8
    assert plan.source == "configured_limit"
    assert plan.cpu_limit is None
    assert plan.memory_limit is None
    assert plan.disk_limit is None


def test_local_autodetect_is_independent_of_condor_switch(tmp_path):
    workspace = _workspace(tmp_path)
    config_path = workspace / "config.py"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\nHTCONDOR_RESOURCE_AUTODETECT_ENABLED = False\n",
        encoding="utf-8",
    )
    config = load_config(workspace)

    plan = local_resources.plan_local_workers(
        config,
        population_size=20,
        configured_max=8,
        generation_index=0,
        run_id="run-a",
        system=_system(),
    )

    assert plan.worker_count == 8
    assert plan.source == "configured_limit_with_configured_default_observation"
    assert plan.cpu_limit == 8
    assert plan.memory_limit == 6


def test_local_plan_never_exceeds_population_size(tmp_path):
    workspace = _workspace(tmp_path)
    config = load_config(workspace)

    plan = local_resources.plan_local_workers(
        config,
        population_size=3,
        configured_max=8,
        generation_index=None,
        run_id=None,
        system=_system(),
    )

    assert plan.worker_count == 3
    assert plan.configured_max == 3


def test_fast_plan_observes_resources_without_clamping_configured_workers(tmp_path):
    workspace = _workspace(tmp_path)
    config = load_config(workspace)
    constrained = local_resources.SystemResourceSnapshot(
        physical_cpus=2,
        logical_cpus=4,
        available_memory_mib=1,
        free_disk_kib=1,
    )

    plan = fast_resources.plan_fast_workers(
        config,
        population_size=20,
        configured_max=8,
        system=constrained,
    )

    assert plan.worker_count == 8
    assert plan.configured_max == 8
    assert plan.cpu_limit == 2
    assert plan.memory_limit == 1
    assert plan.disk_limit == 1
    assert plan.source == "configured_limit_with_resource_observation"
    assert plan.metadata()["fast_resource_limits_enforced"] is False
