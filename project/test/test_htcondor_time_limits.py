from __future__ import annotations


def _job(tmp_path, *, generation_index=0, run_id="run_001"):
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


def _configure_auto(monkeypatch, *, smoke_enabled=True):
    from project.config import all as project_config

    monkeypatch.setattr(project_config, "HTCONDOR_JOB_TIMEOUT_MODE", "auto")
    monkeypatch.setattr(project_config, "HTCONDOR_JOB_TIMEOUT_SEC", 3600)
    monkeypatch.setattr(project_config, "HTCONDOR_JOB_TIMEOUT_MULTIPLIER", 2.0)
    monkeypatch.setattr(project_config, "HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION", 0.10)
    monkeypatch.setattr(project_config, "OPTIMIZE_SMOKE_TEST_ENABLED", smoke_enabled)


def _record(duration, *, generation_index, status="completed", run_id="run_001", recorded_at=""):
    return {
        "status": status,
        "generation_index": generation_index,
        "run_id": run_id,
        "recorded_at": recorded_at,
        "job_metadata": {
            "engine": "htcondor",
            "condor_remote_wall_clock_sec": duration,
            "condor_cumulative_suspension_sec": 0,
        },
    }


def test_smoke_job_has_no_condor_time_limit(tmp_path, monkeypatch):
    from project.evaluate_manager import time_limits

    _configure_auto(monkeypatch)
    monkeypatch.setattr(
        time_limits.recorded_data_api,
        "list_records",
        lambda: (_ for _ in ()).throw(AssertionError("smoke must not read calibration history")),
    )

    limit = time_limits.time_limit_for_job(_job(tmp_path, generation_index=None))

    assert limit.seconds is None
    assert limit.source == "smoke_no_timeout"


def test_generation_zero_uses_latest_smoke_execution_time(tmp_path, monkeypatch):
    from project.evaluate_manager import time_limits

    _configure_auto(monkeypatch)
    records = (
        _record(30, generation_index=None, recorded_at="2026-07-16T00:00:00+00:00"),
        _record(50, generation_index=None, recorded_at="2026-07-16T01:00:00+00:00"),
    )
    monkeypatch.setattr(time_limits.recorded_data_api, "list_records", lambda: records)

    limit = time_limits.time_limit_for_job(_job(tmp_path, generation_index=0))

    assert limit.seconds == 100
    assert limit.source == "smoke_calibration"
    assert limit.sample_count == 1


def test_later_generation_trims_top_ten_percent(tmp_path, monkeypatch):
    from project.evaluate_manager import time_limits

    _configure_auto(monkeypatch)
    records = tuple(_record(value, generation_index=0) for value in range(1, 11))
    monkeypatch.setattr(time_limits.recorded_data_api, "list_records", lambda: records)

    limit = time_limits.time_limit_for_job(_job(tmp_path, generation_index=1))

    assert limit.seconds == 18
    assert limit.source == "generation_0_calibration"
    assert limit.sample_count == 10


def test_timeout_count_above_trim_fraction_uses_largest_finite_duration(tmp_path, monkeypatch):
    from project.evaluate_manager import time_limits

    _configure_auto(monkeypatch)
    finite = tuple(_record(value, generation_index=0) for value in range(1, 8))
    timed_out = tuple(_record(100, generation_index=0, status="timeout") for _ in range(3))
    monkeypatch.setattr(time_limits.recorded_data_api, "list_records", lambda: finite + timed_out)

    limit = time_limits.time_limit_for_job(_job(tmp_path, generation_index=1))

    assert limit.seconds == 14
    assert limit.sample_count == 10


def test_all_timeouts_fall_back_to_user_limit(tmp_path, monkeypatch):
    from project.evaluate_manager import time_limits

    _configure_auto(monkeypatch)
    records = tuple(_record(100, generation_index=0, status="timeout") for _ in range(5))
    monkeypatch.setattr(time_limits.recorded_data_api, "list_records", lambda: records)

    limit = time_limits.time_limit_for_job(_job(tmp_path, generation_index=1))

    assert limit.seconds == 3600
    assert limit.source == "configured_fallback"


def test_disabled_smoke_treats_user_limit_as_smoke_measurement(tmp_path, monkeypatch):
    from project.evaluate_manager import time_limits

    _configure_auto(monkeypatch, smoke_enabled=False)
    monkeypatch.setattr(
        time_limits.recorded_data_api,
        "list_records",
        lambda: (_ for _ in ()).throw(AssertionError("disabled smoke must ignore old smoke history")),
    )

    limit = time_limits.time_limit_for_job(_job(tmp_path, generation_index=0))

    assert limit.seconds == 7200
    assert limit.source == "configured_smoke_fallback"
    assert limit.sample_count == 1


def test_fixed_mode_uses_user_limit_without_history(tmp_path, monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager import time_limits

    _configure_auto(monkeypatch)
    monkeypatch.setattr(project_config, "HTCONDOR_JOB_TIMEOUT_MODE", "fixed")
    monkeypatch.setattr(
        time_limits.recorded_data_api,
        "list_records",
        lambda: (_ for _ in ()).throw(AssertionError("fixed mode must not read history")),
    )

    limit = time_limits.time_limit_for_job(_job(tmp_path, generation_index=3))

    assert limit.seconds == 3600
    assert limit.source == "configured_fixed"
