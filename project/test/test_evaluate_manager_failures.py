from __future__ import annotations

import math
from pathlib import Path


def test_prepare_failure_returns_inf_and_generation_continues(tmp_path, monkeypatch):
    from project.evaluate_manager import api
    from project.evaluate_manager.types import JobResult, JobSpec

    recorded: list[JobResult] = []

    def prepare_job(variables, *, jobs_dir, job_template_dir):
        values = tuple(float(value) for value in variables)
        if values[0] == 0.0:
            raise RuntimeError("template copy exploded")
        return JobSpec(name="job_success", directory=Path(jobs_dir) / "job_success", unnormalized_variables=values)

    def run_local_job(job, *, timeout_sec, python_executable, env):
        return JobResult(
            job_name=job.name,
            job_dir=job.directory,
            status="done",
            unnormalized_variables=job.unnormalized_variables,
            metadata={"job_name": job.name, "status": "done"},
        )

    def record_result(result):
        recorded.append(result)
        if result.status == "done":
            return (2.0, 3.0)
        return None

    monkeypatch.setattr(api, "prepare_job", prepare_job)
    monkeypatch.setattr(api, "run_local_job", run_local_job)
    monkeypatch.setattr(api, "record_result", record_result)

    costs = api.evaluate_population(((0.0,), (1.0,)), jobs_dir=tmp_path, timeout_sec=1)

    assert costs[0] == (math.inf, math.inf)
    assert costs[1] == (2.0, 3.0)
    failure = recorded[0]
    assert failure.status == "error"
    assert failure.metadata["failure_stage"] == "prepare"
    assert failure.metadata["error_type"] == "RuntimeError"
    assert failure.metadata["error_message"] == "template copy exploded"
    assert failure.metadata["population_row"] == [0.0]


def test_record_failure_returns_inf_and_generation_continues(tmp_path, monkeypatch):
    from project.evaluate_manager import api
    from project.evaluate_manager.types import JobResult, JobSpec

    recorded_failures: list[JobResult] = []

    def prepare_job(variables, *, jobs_dir, job_template_dir):
        values = tuple(float(value) for value in variables)
        name = f"job_{int(values[0])}"
        return JobSpec(name=name, directory=Path(jobs_dir) / name, unnormalized_variables=values)

    def run_local_job(job, *, timeout_sec, python_executable, env):
        return JobResult(
            job_name=job.name,
            job_dir=job.directory,
            status="done",
            unnormalized_variables=job.unnormalized_variables,
            metadata={"job_name": job.name, "status": "done"},
        )

    def record_result(result):
        if result.metadata.get("failure_stage") == "record":
            recorded_failures.append(result)
            return None
        if result.job_name == "job_0":
            raise OSError("manifest locked")
        return (4.0,)

    monkeypatch.setattr(api, "prepare_job", prepare_job)
    monkeypatch.setattr(api, "run_local_job", run_local_job)
    monkeypatch.setattr(api, "record_result", record_result)

    costs = api.evaluate_population(((0.0,), (1.0,)), jobs_dir=tmp_path, timeout_sec=1)

    assert costs == ((math.inf,), (4.0,))
    assert len(recorded_failures) == 1
    failure = recorded_failures[0]
    assert failure.job_name == "job_0"
    assert failure.status == "error"
    assert failure.metadata["failure_stage"] == "record"
    assert failure.metadata["error_type"] == "OSError"
    assert failure.metadata["error_message"] == "manifest locked"
    assert failure.metadata["population_row"] == [0.0]


def test_default_jobs_dir_reads_project_config_at_call_time(tmp_path, monkeypatch):
    from project import config
    from project.evaluate_manager import api
    from project.evaluate_manager.types import JobResult, JobSpec

    configured_jobs_dir = tmp_path / "configured_jobs"
    seen: dict[str, JobSpec] = {}

    def run_local_job(job, *, timeout_sec, python_executable, env):
        seen["job"] = job
        return JobResult(
            job_name=job.name,
            job_dir=job.directory,
            status="done",
            unnormalized_variables=job.unnormalized_variables,
            metadata={"job_name": job.name, "status": "done"},
        )

    monkeypatch.setattr(config, "JOBS_DIR", configured_jobs_dir)
    monkeypatch.setattr(api, "run_local_job", run_local_job)
    monkeypatch.setattr(api, "record_result", lambda result: (1.0,))

    costs = api.evaluate_population(((0.25, 0.5, 0.75, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5),), timeout_sec=1)

    assert costs == ((1.0,),)
    assert seen["job"].directory.parent == configured_jobs_dir
    assert configured_jobs_dir.is_dir()
