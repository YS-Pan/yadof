from __future__ import annotations

import math
from pathlib import Path


def _job(tmp_path: Path, name: str = "job_001"):
    from project.evaluate_manager.types import JobSpec

    job_dir = tmp_path / name
    job_dir.mkdir(parents=True)
    return JobSpec(
        name=name,
        directory=job_dir,
        normalized_variables=(0.25,),
        unnormalized_variables=(2.5,),
        run_id="pytest_run",
        optimization_index=4,
        generation_index=5,
        population_index=0,
    )


def test_condor_submit_file_uses_direct_workflow_and_rawdata_contract(tmp_path):
    from project.evaluate_manager.condor_runner import write_condor_submit_file

    job = _job(tmp_path)
    for name in (
        "workflow.py",
        "job_input.json",
        "parameters_constraints.py",
        "parameters_constraints_class.py",
        "rawdata_contract.py",
        "test_com.py",
        "calc_cost.py",
        "hfss_com.py",
    ):
        (job.directory / name).write_text("# test\n", encoding="utf-8", newline="\n")
    (job.directory / "rawData").mkdir()

    submit_path = write_condor_submit_file(job, env={"EXTRA_FLAG": "1"})
    text = submit_path.read_text(encoding="utf-8")

    assert "executable = workflow.py" in text
    assert "transfer_executable = True" in text
    assert "transfer_output_files = rawData,individual_metadata.json" in text
    assert "run_as_owner = False" in text
    assert "load_profile = True" in text
    assert "EXTRA_FLAG=1" in text
    assert "job_input.json" in text
    assert "calc_cost.py" not in text
    assert "hfss_com.py" not in text
    assert "cost.json" not in text


def test_run_condor_jobs_records_submit_failure_without_fixing_condor(tmp_path, monkeypatch):
    from project.evaluate_manager import condor_runner

    job = _job(tmp_path)
    (job.directory / "workflow.py").write_text("# test\n", encoding="utf-8", newline="\n")
    (job.directory / "job_input.json").write_text("{}", encoding="utf-8", newline="\n")

    def missing_condor(*_args, **_kwargs):
        raise OSError("condor_submit is not healthy")

    monkeypatch.setattr(condor_runner.subprocess, "run", missing_condor)

    (result,) = condor_runner.run_condor_jobs((job,), timeout_sec=1)

    assert result.status == "error"
    assert result.raw_data_paths == ()
    assert result.metadata["engine"] == "htcondor"
    assert result.metadata["failure_stage"] == "submit"
    assert result.metadata["error_message"] == "condor_submit is not healthy"


def test_distributed_mode_uses_condor_runner_and_shared_finalization(tmp_path, monkeypatch):
    from project.evaluate_manager import api
    from project.evaluate_manager.types import JobResult, JobSpec

    submitted: list[JobSpec] = []
    recorded: list[JobResult] = []

    def prepare_job(variables, *, jobs_dir, job_template_dir, run_id=None, optimization_index=None, generation_index=None, population_index=None):
        values = tuple(float(value) for value in variables)
        name = f"job_{population_index}"
        return JobSpec(
            name=name,
            directory=Path(jobs_dir) / name,
            normalized_variables=values,
            unnormalized_variables=values,
            run_id=run_id,
            optimization_index=optimization_index,
            generation_index=generation_index,
            population_index=population_index,
        )

    def run_condor_jobs(jobs, *, timeout_sec, env):
        submitted.extend(jobs)
        return (
            JobResult(
                job_name=jobs[0].name,
                job_dir=jobs[0].directory,
                status="done",
                unnormalized_variables=jobs[0].unnormalized_variables,
                metadata={"job_name": jobs[0].name, "status": "done", "engine": "htcondor"},
            ),
            JobResult(
                job_name=jobs[1].name,
                job_dir=jobs[1].directory,
                status="error",
                unnormalized_variables=jobs[1].unnormalized_variables,
                metadata={"job_name": jobs[1].name, "status": "error", "engine": "htcondor"},
            ),
        )

    def record_result(result):
        recorded.append(result)
        if result.status == "done":
            return (2.0, 3.0)
        return None

    monkeypatch.setattr(api, "prepare_job", prepare_job)
    monkeypatch.setattr(api, "run_condor_jobs", run_condor_jobs)
    monkeypatch.setattr(api, "record_result", record_result)

    costs = api.evaluate_population(((0.1,), (0.2,)), mode="distributed", jobs_dir=tmp_path, timeout_sec=1)

    assert [job.name for job in submitted] == ["job_0", "job_1"]
    assert costs == ((2.0, 3.0), (math.inf, math.inf))
    assert [result.status for result in recorded] == ["done", "error"]
    assert recorded[0].metadata["engine"] == "htcondor"
