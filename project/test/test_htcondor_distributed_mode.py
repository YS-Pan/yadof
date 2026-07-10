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


def test_condor_submit_file_uses_direct_workflow_executable_and_rawdata_contract(tmp_path):
    from project import config_all as project_config
    from project.evaluate_manager.condor_runner import write_condor_submit_file

    job = _job(tmp_path)
    for name in (
        "workflow.py",
        "job_input.json",
        "parameters_constraints.py",
        "parameters_constraints_class.py",
        "rawdata_contract.py",
        "hfss_com.py",
        "calc_cost.py",
    ):
        (job.directory / name).write_text("# test\n", encoding="utf-8", newline="\n")
    (job.directory / "rawData").mkdir()
    (job.directory / "individual_metadata.json").write_text('{"status":"error"}\n', encoding="utf-8", newline="\n")
    (job.directory / "rawData_outputs.zip").write_bytes(b"old zip")

    submit_path = write_condor_submit_file(job, env={"EXTRA_FLAG": "1"})
    text = submit_path.read_text(encoding="utf-8")

    assert "executable = workflow.py" in text
    assert not any(line.startswith("arguments =") for line in text.splitlines())
    assert "transfer_executable = True" in text
    assert "transfer_output_files" not in text
    assert "run_as_owner = False" in text
    assert "load_profile = True" in text
    environment_line = next(line for line in text.splitlines() if line.startswith("environment = "))
    assert environment_line == f'environment = "{project_config.HTCONDOR_ENVIRONMENT}"'
    assert "EXTRA_FLAG=1" not in text
    assert "USERPROFILE=._home" in text
    assert "APPDATA=._appdata" in text
    assert "LOCALAPPDATA=._localappdata" in text
    assert "TEMP=._tmp" in text
    assert "YADOF_HFSS_NON_GRAPHICAL=1" in text
    assert "ANSYSLMD_LICENSE_FILE=1055@localhost" in text
    assert f"request_cpus = {project_config.HTCONDOR_REQUEST_CPUS}" in text
    assert f"request_memory = {project_config.HTCONDOR_REQUEST_MEMORY}" in text
    assert 'Machine != "DESKTOP-A2091"' not in text
    if project_config.HTCONDOR_ALLOWED_MACHINES:
        for machine in project_config.HTCONDOR_ALLOWED_MACHINES:
            assert f'Machine =?= "{machine}"' in text
    else:
        assert 'Machine =?= "DESKTOP-A2091"' not in text
    assert 'TARGET.YADOF_RAMDISK =?= True' in text
    transfer_line = next(line for line in text.splitlines() if line.startswith("transfer_input_files = "))
    assert "workflow.py" not in transfer_line
    assert "rawData" not in transfer_line
    assert "individual_metadata.json" not in transfer_line
    assert "rawData_outputs.zip" not in transfer_line
    assert "._home" in transfer_line
    assert "._appdata" in transfer_line
    assert "._localappdata" in transfer_line
    assert "._tmp" in transfer_line
    for name in ("._home", "._appdata", "._localappdata", "._tmp"):
        assert (job.directory / name).is_dir()
    assert "job_input.json" in text
    assert "hfss_com.py" in text
    assert "calc_cost.py" not in text
    assert "cost.json" not in text
    assert not (job.directory / "run_workflow.cmd").exists()
    assert not (job.directory / "batch.log").exists()


def test_submit_condor_job_clears_stale_runtime_artifacts_before_submit(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from project.evaluate_manager import condor_runner

    job = _job(tmp_path)
    for name in ("workflow.py", "job_input.json"):
        (job.directory / name).write_text("# test\n", encoding="utf-8", newline="\n")
    (job.directory / "individual_metadata.json").write_text('{"status":"error"}\n', encoding="utf-8", newline="\n")
    (job.directory / "rawData_outputs.zip").write_bytes(b"old zip")
    (job.directory / "cost.json").write_text('{"cost": 1}\n', encoding="utf-8", newline="\n")

    def fake_submit(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout="Submitting job(s).\n1 job(s) submitted to cluster 456.\n",
            stderr="",
        )

    monkeypatch.setattr(condor_runner.subprocess, "run", fake_submit)

    submission = condor_runner.submit_condor_job(job)

    assert submission.cluster_id == 456
    assert not (job.directory / "individual_metadata.json").exists()
    assert not (job.directory / "rawData_outputs.zip").exists()
    assert not (job.directory / "cost.json").exists()


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


def test_condor_requirements_can_be_relaxed_or_exclude_workers(monkeypatch):
    from project import config_all as project_config
    from project.evaluate_manager import config

    monkeypatch.setattr(project_config, "HTCONDOR_ALLOWED_MACHINES", ())
    monkeypatch.setattr(project_config, "HTCONDOR_EXCLUDED_MACHINES", ("DESKTOP-A2096", "DESKTOP-A2093"))

    requirements = config.htcondor_requirements()

    assert 'Machine =?= "DESKTOP-A2091"' not in requirements
    assert 'Machine =!= "DESKTOP-A2096"' in requirements
    assert 'Machine =!= "DESKTOP-A2093"' in requirements
    assert 'TARGET.YADOF_RAMDISK =?= True' in requirements


def test_condor_result_records_windows_access_denied_return_value(tmp_path):
    from project.evaluate_manager.condor_runner import CondorSubmission, collect_condor_result

    job = _job(tmp_path)
    submit_file = job.directory / "job.sub"
    submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
    (job.directory / "condor.log").write_text(
        "... Job terminated. (1) Normal termination (return value -1073741790) ...\n",
        encoding="utf-8",
        newline="\n",
    )
    (job.directory / "batch.log").write_text("worker batch detail\n", encoding="utf-8", newline="\n")
    submission = CondorSubmission(
        job=job,
        submit_file=submit_file,
        cluster_id=123,
        submitted_at="2026-05-29T00:00:00+08:00",
        stdout="Submitting job(s).\n1 job(s) submitted to cluster 123.\n",
        stderr="",
    )

    result = collect_condor_result(job, submission=submission, timed_out=False, terminal_reason="terminated")

    assert result.status == "error"
    assert result.metadata["condor_return_value"] == -1073741790
    assert result.metadata["condor_return_value_hex"] == "0xC0000022"
    assert result.metadata["condor_return_value_name"] == "STATUS_ACCESS_DENIED"
    assert "Windows denied starting" in result.metadata["condor_return_value_explanation"]
    assert "STATUS_ACCESS_DENIED" in result.metadata["error"]
    assert "worker batch detail" in result.metadata["batch_log_tail"]


def test_condor_result_restores_rawdata_transfer_zip(tmp_path):
    import zipfile

    from project.evaluate_manager.condor_runner import CondorSubmission, collect_condor_result

    job = _job(tmp_path)
    submit_file = job.directory / "job.sub"
    submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
    (job.directory / "condor.log").write_text(
        "... Job terminated. (1) Normal termination (return value 0) ...\n",
        encoding="utf-8",
        newline="\n",
    )
    (job.directory / "individual_metadata.json").write_text(
        '{"status":"done","raw_data_files":["curve.npz"]}\n',
        encoding="utf-8",
        newline="\n",
    )
    with zipfile.ZipFile(job.directory / "rawData_outputs.zip", "w") as archive:
        archive.writestr("curve.npz", b"npz bytes")
    submission = CondorSubmission(
        job=job,
        submit_file=submit_file,
        cluster_id=123,
        submitted_at="2026-05-29T00:00:00+08:00",
        stdout="Submitting job(s).\n1 job(s) submitted to cluster 123.\n",
        stderr="",
    )

    result = collect_condor_result(job, submission=submission, timed_out=False, terminal_reason="terminated")

    assert result.status == "done"
    assert (job.directory / "rawData" / "curve.npz").read_bytes() == b"npz bytes"


def test_condor_result_ignores_bad_transfer_zip_when_nested_rawdata_exists(tmp_path):
    from project.evaluate_manager.condor_runner import CondorSubmission, collect_condor_result

    job = _job(tmp_path)
    submit_file = job.directory / "job.sub"
    submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
    (job.directory / "condor.log").write_text(
        "... Job terminated. (1) Normal termination (return value 0) ...\n",
        encoding="utf-8",
        newline="\n",
    )
    (job.directory / "individual_metadata.json").write_text(
        '{"status":"done","raw_data_files":["curve.npz"]}\n',
        encoding="utf-8",
        newline="\n",
    )
    raw_dir = job.directory / "rawData"
    raw_dir.mkdir()
    (raw_dir / "curve.npz").write_bytes(b"already returned")
    (job.directory / "rawData_outputs.zip").write_bytes(b"not a zip")
    submission = CondorSubmission(
        job=job,
        submit_file=submit_file,
        cluster_id=123,
        submitted_at="2026-05-29T00:00:00+08:00",
        stdout="Submitting job(s).\n1 job(s) submitted to cluster 123.\n",
        stderr="",
    )

    result = collect_condor_result(job, submission=submission, timed_out=False, terminal_reason="terminated")

    assert result.status == "done"
    assert result.raw_data_paths == (raw_dir / "curve.npz",)
    assert "rawdata_transfer_zip_error" not in result.metadata


def test_condor_result_reports_bad_transfer_zip_without_raising(tmp_path):
    from project.evaluate_manager.condor_runner import CondorSubmission, collect_condor_result

    job = _job(tmp_path)
    submit_file = job.directory / "job.sub"
    submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
    (job.directory / "condor.log").write_text(
        "... Job terminated. (1) Normal termination (return value 0) ...\n",
        encoding="utf-8",
        newline="\n",
    )
    (job.directory / "individual_metadata.json").write_text(
        '{"status":"done","raw_data_files":["curve.npz"]}\n',
        encoding="utf-8",
        newline="\n",
    )
    (job.directory / "rawData_outputs.zip").write_bytes(b"not a zip")
    submission = CondorSubmission(
        job=job,
        submit_file=submit_file,
        cluster_id=123,
        submitted_at="2026-05-29T00:00:00+08:00",
        stdout="Submitting job(s).\n1 job(s) submitted to cluster 123.\n",
        stderr="",
    )

    result = collect_condor_result(job, submission=submission, timed_out=False, terminal_reason="terminated")

    assert result.status == "error"
    assert "rawData_outputs.zip" in result.metadata["rawdata_transfer_zip_error"]
    assert "Workflow reported done and listed rawData files" in result.metadata["error"]


def test_condor_result_explains_legacy_missing_nested_rawdata(tmp_path):
    from project.evaluate_manager.condor_runner import CondorSubmission, collect_condor_result

    job = _job(tmp_path)
    submit_file = job.directory / "job.sub"
    submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
    (job.directory / "condor.log").write_text(
        "... Job terminated. (1) Normal termination (return value 0) ...\n",
        encoding="utf-8",
        newline="\n",
    )
    (job.directory / "individual_metadata.json").write_text(
        '{"status":"done","raw_data_files":["curve.npz"]}\n',
        encoding="utf-8",
        newline="\n",
    )
    submission = CondorSubmission(
        job=job,
        submit_file=submit_file,
        cluster_id=123,
        submitted_at="2026-05-29T00:00:00+08:00",
        stdout="Submitting job(s).\n1 job(s) submitted to cluster 123.\n",
        stderr="",
    )

    result = collect_condor_result(job, submission=submission, timed_out=False, terminal_reason="terminated")

    assert result.status == "error"
    assert "Workflow reported done and listed rawData files" in result.metadata["error"]
    assert "rawData_outputs.zip" in result.metadata["error"]


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

def test_run_condor_jobs_calls_after_submit_callback_before_wait(tmp_path, monkeypatch):
    from project.evaluate_manager import condor_runner
    from project.evaluate_manager.condor_runner import CondorSubmission

    job = _job(tmp_path)
    (job.directory / "workflow.py").write_text("# test\n", encoding="utf-8", newline="\n")
    (job.directory / "job_input.json").write_text("{}", encoding="utf-8", newline="\n")
    events: list[str] = []

    def fake_submit(job_spec, *, env=None):
        events.append("submit")
        submit_file = job_spec.directory / "job.sub"
        submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
        return CondorSubmission(
            job=job_spec,
            submit_file=submit_file,
            cluster_id=321,
            submitted_at="2026-07-05T00:00:00+08:00",
            stdout="submitted",
            stderr="",
        )

    def fake_collect(job_spec, *, submission, timed_out, terminal_reason, remove_error=None):
        events.append("collect")
        from project.evaluate_manager.types import JobResult

        return JobResult(
            job_name=job_spec.name,
            job_dir=job_spec.directory,
            status="done",
            unnormalized_variables=job_spec.unnormalized_variables,
            metadata={"job_name": job_spec.name, "status": "done", "engine": "htcondor"},
        )

    monkeypatch.setattr(condor_runner, "submit_condor_job", fake_submit)
    monkeypatch.setattr(condor_runner, "terminal_log_reason", lambda _job_dir: "terminated")
    monkeypatch.setattr(condor_runner, "collect_condor_result", fake_collect)

    results = condor_runner.run_condor_jobs(
        (job,),
        timeout_sec=1,
        after_jobs_submitted=lambda: events.append("callback"),
    )

    assert results[0].status == "done"
    assert events == ["submit", "callback", "collect"]


def test_run_condor_jobs_isolates_collect_failure(tmp_path, monkeypatch):
    from project.evaluate_manager import condor_runner
    from project.evaluate_manager.condor_runner import CondorSubmission
    from project.evaluate_manager.types import JobResult

    first = _job(tmp_path, "job_001")
    second = _job(tmp_path, "job_002")
    events: list[str] = []

    def fake_submit(job_spec, *, env=None):
        submit_file = job_spec.directory / "job.sub"
        submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
        return CondorSubmission(
            job=job_spec,
            submit_file=submit_file,
            cluster_id=100 if job_spec.name == "job_001" else 101,
            submitted_at="2026-07-05T00:00:00+08:00",
            stdout="submitted",
            stderr="",
        )

    def fake_collect(job_spec, *, submission, timed_out, terminal_reason, remove_error=None):
        events.append(job_spec.name)
        if job_spec.name == "job_001":
            raise RuntimeError("bad returned payload")
        return JobResult(
            job_name=job_spec.name,
            job_dir=job_spec.directory,
            status="done",
            unnormalized_variables=job_spec.unnormalized_variables,
            metadata={"job_name": job_spec.name, "status": "done", "engine": "htcondor"},
        )

    monkeypatch.setattr(condor_runner, "submit_condor_job", fake_submit)
    monkeypatch.setattr(condor_runner, "terminal_log_reason", lambda _job_dir: "terminated")
    monkeypatch.setattr(condor_runner, "collect_condor_result", fake_collect)

    results = condor_runner.run_condor_jobs((first, second), timeout_sec=1)

    assert [result.status for result in results] == ["error", "done"]
    assert results[0].metadata["failure_stage"] == "collect"
    assert results[0].metadata["error_message"] == "bad returned payload"
    assert events == ["job_001", "job_002"]
