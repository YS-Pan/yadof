from __future__ import annotations

from types import SimpleNamespace


def _job(tmp_path, *, generation_index=None, run_id="run_001"):
    from project.evaluate_manager.types import JobSpec

    job_dir = tmp_path / "job_001"
    job_dir.mkdir(parents=True, exist_ok=True)
    return JobSpec(
        name="job_001",
        directory=job_dir,
        normalized_variables=(0.5,),
        unnormalized_variables=(5.0,),
        run_id=run_id,
        generation_index=generation_index,
    )


def _configure_defaults(monkeypatch):
    from project.config import all as project_config

    monkeypatch.setattr(project_config, "HTCONDOR_REQUEST_CPUS", 3)
    monkeypatch.setattr(project_config, "HTCONDOR_REQUEST_MEMORY", "10MB")
    monkeypatch.setattr(project_config, "HTCONDOR_REQUEST_DISK", "100KB")
    monkeypatch.setattr(project_config, "HTCONDOR_RESOURCE_AUTODETECT_ENABLED", True)
    monkeypatch.setattr(project_config, "HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER", 2.0)
    monkeypatch.setattr(project_config, "HTCONDOR_RESOURCE_TRIM_TOP_FRACTION", 0.05)
    monkeypatch.setattr(project_config, "HTCONDOR_REQUEST_DISK_MULTIPLIER", 1.0)
    monkeypatch.setattr(project_config, "OPTIMIZE_SMOKE_TEST_ENABLED", True)


def test_hfss_solver_core_count_uses_the_specific_multiplier():
    from project.config import key as key_config
    from project.config.specific import hfss

    assert hfss.HFSS_CPUCORE_MULTIPLIER == 2
    assert hfss.HFSS_JOB_CPUCORE == max(1, int(key_config.HTCONDOR_REQUEST_CPUS) * hfss.HFSS_CPUCORE_MULTIPLIER)


def test_generation_zero_uses_smoke_measurements_with_bootstrap_and_disk_multiplier(tmp_path, monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager import resource_requests

    _configure_defaults(monkeypatch)
    monkeypatch.setattr(project_config, "HTCONDOR_REQUEST_DISK_MULTIPLIER", 1.5)
    monkeypatch.setattr(
        resource_requests.recorded_data_api,
        "list_records",
        lambda: (
            {
                "status": "completed",
                "job_metadata": {
                    "engine": "htcondor",
                    "condor_memory_usage_mib": 512,
                    "condor_disk_usage_kib": 2048,
                },
            },
        ),
    )

    request = resource_requests.request_for_job(_job(tmp_path, generation_index=0))

    assert request.cpus == 3
    assert request.memory_mib == 1024
    assert request.disk_kib == 6144
    assert request.source == "smoke_calibration"
    assert request.sample_count == 1


def test_later_generation_discards_highest_configured_fraction_from_its_own_run(tmp_path, monkeypatch):
    from project.evaluate_manager import resource_requests

    _configure_defaults(monkeypatch)
    records = tuple(
        {
            "status": "completed",
            "generation_index": 1,
            "run_id": "run_001",
            "job_metadata": {
                "engine": "htcondor",
                "condor_memory_usage_mib": value,
                "condor_disk_usage_kib": value * 10,
            },
        }
        for value in range(1, 21)
    ) + (
        {
            "generation_index": 1,
            "run_id": "another_run",
            "job_metadata": {
                "engine": "htcondor",
                "condor_memory_usage_mib": 999,
                "condor_disk_usage_kib": 9990,
            },
        },
    )
    monkeypatch.setattr(resource_requests.recorded_data_api, "list_records", lambda: records)

    request = resource_requests.request_for_job(_job(tmp_path, generation_index=2))

    assert request.memory_mib == 19
    assert request.disk_kib == 190
    assert request.source == "generation_1_calibration"
    assert request.sample_count == 20


def test_missing_calibration_uses_configured_values_and_disk_multiplier(tmp_path, monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager import resource_requests

    _configure_defaults(monkeypatch)
    monkeypatch.setattr(project_config, "HTCONDOR_REQUEST_DISK_MULTIPLIER", 2.0)
    monkeypatch.setattr(resource_requests.recorded_data_api, "list_records", lambda: ())

    request = resource_requests.request_for_job(_job(tmp_path, generation_index=3))

    assert request.memory_mib == 10
    assert request.disk_kib == 200
    assert request.source == "configured_default"


def test_disabled_smoke_treats_configured_resources_as_smoke_measurements(tmp_path, monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager import resource_requests

    _configure_defaults(monkeypatch)
    monkeypatch.setattr(project_config, "OPTIMIZE_SMOKE_TEST_ENABLED", False)
    monkeypatch.setattr(project_config, "HTCONDOR_REQUEST_DISK_MULTIPLIER", 1.5)
    monkeypatch.setattr(
        resource_requests.recorded_data_api,
        "list_records",
        lambda: (
            {
                "status": "completed",
                "job_metadata": {
                    "engine": "htcondor",
                    "condor_memory_usage_mib": 999,
                    "condor_disk_usage_kib": 9999,
                },
            },
        ),
    )

    request = resource_requests.request_for_job(_job(tmp_path, generation_index=0))

    assert request.memory_mib == 20
    assert request.disk_kib == 300
    assert request.source == "configured_smoke_fallback"
    assert request.sample_count == 1


def test_condor_history_usage_is_promoted_to_runner_metadata(tmp_path, monkeypatch):
    from project.evaluate_manager import condor_runner
    from project.evaluate_manager.condor_runner import CondorSubmission

    job = _job(tmp_path)
    submit_file = job.directory / "job.sub"
    submit_file.write_text("queue 1\n", encoding="utf-8")
    submission = CondorSubmission(
        job=job,
        submit_file=submit_file,
        cluster_id=765,
        submitted_at="2026-07-15T20:42:10+08:00",
        stdout="",
        stderr="",
    )

    def fake_run(command, **_kwargs):
        assert command[0] == "condor_history"
        assert command[1] == "765.0"
        return SimpleNamespace(
            returncode=0,
            stdout=(
                '[{"MemoryUsage": 1536, "DiskUsage": 4096, "ResidentSetSize": 1572864, '
                '"CpusUsage": 1.25, "RequestMemory": 2048, "RequestDisk": 8192, "RequestCpus": 3, '
                '"RemoteWallClockTime": 125.5, "CumulativeSuspensionTime": 5}]'
            ),
            stderr="",
        )

    monkeypatch.setattr(condor_runner.subprocess, "run", fake_run)

    usage = condor_runner.condor_resource_usage(submission)

    assert usage == {
        "condor_memory_usage_mib": 1536,
        "condor_disk_usage_kib": 4096,
        "condor_resident_set_size_kib": 1572864,
        "condor_cpus_usage": 1.25,
        "condor_reported_request_memory_mib": 2048,
        "condor_reported_request_disk_kib": 8192,
        "condor_reported_request_cpus": 3,
        "condor_remote_wall_clock_sec": 125.5,
        "condor_cumulative_suspension_sec": 5,
        "condor_resource_usage_source": "condor_history",
    }
