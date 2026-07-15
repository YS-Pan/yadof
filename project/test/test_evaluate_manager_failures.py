from __future__ import annotations

import math
from pathlib import Path
import threading
import time


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

    costs = api.evaluate_population(((0.0,), (1.0,)), mode="local", jobs_dir=tmp_path, timeout_sec=1)

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
            raise OSError("metadata locked")
        return (4.0,)

    monkeypatch.setattr(api, "prepare_job", prepare_job)
    monkeypatch.setattr(api, "run_local_job", run_local_job)
    monkeypatch.setattr(api, "record_result", record_result)

    costs = api.evaluate_population(((0.0,), (1.0,)), mode="local", jobs_dir=tmp_path, timeout_sec=1)

    assert costs == ((math.inf,), (4.0,))
    assert len(recorded_failures) == 1
    failure = recorded_failures[0]
    assert failure.job_name == "job_0"
    assert failure.status == "error"
    assert failure.metadata["failure_stage"] == "record"
    assert failure.metadata["error_type"] == "OSError"
    assert failure.metadata["error_message"] == "metadata locked"
    assert failure.metadata["population_row"] == [0.0]


def test_default_jobs_dir_reads_project_config_at_call_time(tmp_path, monkeypatch):
    from project.config import all as config
    from project.evaluate_manager import api
    from project.evaluate_manager.types import JobResult, JobSpec
    from project.job_template import api as job_template_api

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

    population = ((0.25, 0.5, 0.75) + (0.5,) * (job_template_api.get_variable_count() - 3),)
    costs = api.evaluate_population(population, mode="local", timeout_sec=1)

    assert costs == ((1.0,),)
    assert seen["job"].directory.parent == configured_jobs_dir
    assert configured_jobs_dir.is_dir()


def test_local_evaluation_can_run_jobs_in_parallel(tmp_path, monkeypatch):
    from project.config import all as config
    from project.evaluate_manager import api
    from project.evaluate_manager.types import JobResult, JobSpec

    active = 0
    max_active = 0
    lock = threading.Lock()

    def prepare_job(variables, *, jobs_dir, job_template_dir):
        values = tuple(float(value) for value in variables)
        name = f"job_{int(values[0])}"
        return JobSpec(name=name, directory=Path(jobs_dir) / name, unnormalized_variables=values)

    def run_local_job(job, *, timeout_sec, python_executable, env):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return JobResult(
            job_name=job.name,
            job_dir=job.directory,
            status="done",
            unnormalized_variables=job.unnormalized_variables,
            metadata={"job_name": job.name, "status": "done"},
        )

    monkeypatch.setattr(api, "prepare_job", prepare_job)
    monkeypatch.setattr(api, "run_local_job", run_local_job)
    monkeypatch.setattr(api, "record_result", lambda result: (result.unnormalized_variables[0],))

    costs = api.evaluate_population(
        ((0.0,), (1.0,), (2.0,), (3.0,)),
        mode="local",
        jobs_dir=tmp_path,
        timeout_sec=1,
        local_max_workers=2,
    )

    assert costs == ((0.0,), (1.0,), (2.0,), (3.0,))
    assert max_active >= 2


def test_local_worker_config_is_read_fresh(monkeypatch):
    import types

    from project.evaluate_manager import config as eval_config

    values = iter((3, 5))

    def fresh_project_config():
        return types.SimpleNamespace(LOCAL_EVALUATION_MAX_WORKERS=next(values))

    monkeypatch.delenv("LOCAL_EVALUATION_MAX_WORKERS", raising=False)
    monkeypatch.setattr(eval_config, "_fresh_project_config", fresh_project_config)

    assert eval_config.local_evaluation_max_workers() == 3
    assert eval_config.local_evaluation_max_workers() == 5
