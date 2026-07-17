from __future__ import annotations

from pathlib import Path


def _request():
    from project.evaluate_manager.resource_requests import HTCondorResourceRequest

    return HTCondorResourceRequest(
        cpus=2,
        memory_mib=100,
        disk_kib=200,
        source="test_default",
        sample_count=0,
    )


def _job(tmp_path: Path):
    from project.evaluate_manager.types import JobSpec

    job_dir = tmp_path / "job_001"
    job_dir.mkdir(parents=True)
    (job_dir / "workflow.py").write_text("# test\n", encoding="utf-8", newline="\n")
    return JobSpec(
        name="job_001",
        directory=job_dir,
        normalized_variables=(0.5,),
        unnormalized_variables=(5.0,),
        run_id="run_001",
        generation_index=1,
    )


def _resource_hold(resource: str) -> dict[str, object]:
    subcode = 102 if resource == "memory" else 104
    return {
        "condor_hold_reason": f"{resource} usage exceeded",
        "condor_hold_reason_code": "34",
        "condor_hold_reason_subcode": str(subcode),
    }


def test_yadof_doubles_memory_until_its_retry_limit(monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager.resource_retries import (
        decide_resource_retry,
        new_resource_retry_state,
        resource_retry_metadata,
    )

    monkeypatch.setattr(project_config, "YADOF_RESOURCE_RETRY_DOUBLINGS", 2)
    state = new_resource_retry_state(_request())

    first = decide_resource_retry(
        state,
        hold_info=_resource_hold("memory"),
        resource_usage={"condor_memory_usage_mib": 101},
        cluster_id=10,
    )
    assert first is not None and first.should_retry is True
    assert first.state.request.memory_mib == 200
    assert first.state.request.disk_kib == 200

    second = decide_resource_retry(
        first.state,
        hold_info=_resource_hold("memory"),
        resource_usage={"condor_memory_usage_mib": 201},
        cluster_id=11,
    )
    assert second is not None and second.should_retry is True
    assert second.state.request.memory_mib == 400

    exhausted = decide_resource_retry(
        second.state,
        hold_info=_resource_hold("memory"),
        resource_usage={"condor_memory_usage_mib": 401},
        cluster_id=12,
    )
    assert exhausted is not None and exhausted.should_retry is False
    assert exhausted.state.request.memory_mib == 400
    metadata = resource_retry_metadata(exhausted.state)
    assert metadata["yadof_resource_retry_memory_count"] == 2
    assert metadata["yadof_resource_retry_disk_count"] == 0
    assert metadata["yadof_resource_retry_total_count"] == 2
    assert metadata["yadof_resource_retry_exhausted"] is True
    assert metadata["yadof_resource_retry_exhausted_resource"] == "memory"
    assert [event["action"] for event in metadata["yadof_resource_retry_history"]] == [
        "retry",
        "retry",
        "exhausted",
    ]


def test_memory_and_disk_retry_counts_are_independent(monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager.resource_retries import decide_resource_retry, new_resource_retry_state

    monkeypatch.setattr(project_config, "YADOF_RESOURCE_RETRY_DOUBLINGS", 2)
    state = new_resource_retry_state(_request())
    memory = decide_resource_retry(
        state,
        hold_info=_resource_hold("memory"),
        resource_usage={},
        cluster_id=20,
    )
    assert memory is not None
    disk = decide_resource_retry(
        memory.state,
        hold_info=_resource_hold("disk"),
        resource_usage={},
        cluster_id=21,
    )
    assert disk is not None and disk.should_retry is True
    assert disk.state.request.memory_mib == 200
    assert disk.state.request.disk_kib == 400
    assert disk.state.memory_retry_count == 1
    assert disk.state.disk_retry_count == 1


def test_non_resource_and_timeout_holds_are_never_resource_retried(monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager.resource_retries import decide_resource_retry, new_resource_retry_state

    monkeypatch.setattr(project_config, "YADOF_RESOURCE_RETRY_DOUBLINGS", 4)
    state = new_resource_retry_state(_request())
    timeout_hold = {
        "condor_hold_reason_code": "47",
        "condor_hold_reason_subcode": "0",
    }
    unknown_resource_hold = {
        "condor_hold_reason_code": "34",
        "condor_hold_reason_subcode": "999",
    }

    assert decide_resource_retry(state, hold_info=timeout_hold, resource_usage={}, cluster_id=30) is None
    assert decide_resource_retry(state, hold_info=unknown_resource_hold, resource_usage={}, cluster_id=31) is None


def test_retry_reset_removes_attempt_outputs_but_preserves_static_inputs(tmp_path):
    from project.evaluate_manager.resource_retries import reset_job_for_resource_retry

    job = _job(tmp_path)
    (job.directory / "metadata.json").write_text('{"status":"submitted"}\n', encoding="utf-8", newline="\n")
    for name in (
        "cluster.id",
        "condor.log",
        "stdout.txt",
        "stderr.txt",
        "condor_submit.stdout.txt",
        "condor_submit.stderr.txt",
        "individual_metadata.json",
        "rawData_outputs.zip",
        "batch.log",
    ):
        (job.directory / name).write_text("old attempt\n", encoding="utf-8", newline="\n")
    for name in ("rawData", "._home", "._appdata", "._localappdata", "._tmp"):
        folder = job.directory / name
        folder.mkdir()
        (folder / "old.txt").write_text("old\n", encoding="utf-8", newline="\n")

    reset_job_for_resource_retry(job.directory)

    assert (job.directory / "workflow.py").is_file()
    assert (job.directory / "metadata.json").is_file()
    assert not (job.directory / "condor.log").exists()
    assert not (job.directory / "rawData").exists()
    assert not (job.directory / "._tmp").exists()


def test_condor_runner_resubmits_resource_hold_with_yadof_request(tmp_path, monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager import condor_runner
    from project.evaluate_manager.condor_runner import CondorSubmission
    from project.evaluate_manager.types import JobResult

    monkeypatch.setattr(project_config, "YADOF_RESOURCE_RETRY_DOUBLINGS", 2)
    job = _job(tmp_path)
    initial_request = _request()
    submissions: list[tuple[object, dict[str, object] | None]] = []
    removed: list[int | None] = []

    def fake_submit(job_spec, *, env=None, resource_request=None, resource_retry_metadata=None):
        request = resource_request or initial_request
        cluster_id = 100 + len(submissions)
        submit_file = job_spec.directory / "job.sub"
        submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
        submissions.append((request, resource_retry_metadata))
        return CondorSubmission(
            job=job_spec,
            submit_file=submit_file,
            cluster_id=cluster_id,
            submitted_at="2026-07-17T00:00:00+08:00",
            stdout="submitted",
            stderr="",
            resource_request=request,
        )

    def fake_collect(job_spec, *, submission, timed_out, terminal_reason, **_kwargs):
        return JobResult(
            job_name=job_spec.name,
            job_dir=job_spec.directory,
            status="done",
            unnormalized_variables=job_spec.unnormalized_variables,
            metadata={"job_name": job_spec.name, "status": "done", "engine": "htcondor"},
        )

    monkeypatch.setattr(condor_runner, "submit_condor_job", fake_submit)
    monkeypatch.setattr(
        condor_runner,
        "terminal_log_reason",
        lambda _job_dir: "held" if len(submissions) == 1 else "terminated",
    )
    monkeypatch.setattr(condor_runner, "condor_hold_info", lambda _submission: _resource_hold("memory"))
    monkeypatch.setattr(
        condor_runner,
        "condor_resource_usage",
        lambda _submission: {"condor_memory_usage_mib": 101},
    )
    monkeypatch.setattr(
        condor_runner,
        "remove_condor_job",
        lambda submission: removed.append(submission.cluster_id),
    )
    monkeypatch.setattr(condor_runner, "collect_condor_result", fake_collect)
    monkeypatch.setattr(condor_runner.time, "sleep", lambda _seconds: None)

    (result,) = condor_runner.run_condor_jobs((job,), timeout_sec=1)

    assert result.status == "done"
    assert len(submissions) == 2
    retry_request, retry_metadata = submissions[1]
    assert retry_request.memory_mib == 200
    assert retry_request.disk_kib == 200
    assert retry_metadata is not None
    assert retry_metadata["yadof_resource_retry_total_count"] == 1
    assert removed == [100]


def test_condor_runner_stops_after_resource_retry_limit(tmp_path, monkeypatch):
    from project.config import all as project_config
    from project.evaluate_manager import condor_runner
    from project.evaluate_manager.condor_runner import CondorSubmission
    from project.evaluate_manager.types import JobResult

    monkeypatch.setattr(project_config, "YADOF_RESOURCE_RETRY_DOUBLINGS", 1)
    job = _job(tmp_path)
    initial_request = _request()
    submissions: list[tuple[object, dict[str, object] | None]] = []
    collected: list[dict[str, object]] = []
    removed: list[int | None] = []

    def fake_submit(job_spec, *, env=None, resource_request=None, resource_retry_metadata=None):
        request = resource_request or initial_request
        cluster_id = 200 + len(submissions)
        submit_file = job_spec.directory / "job.sub"
        submit_file.write_text("queue 1\n", encoding="utf-8", newline="\n")
        submissions.append((request, resource_retry_metadata))
        return CondorSubmission(
            job=job_spec,
            submit_file=submit_file,
            cluster_id=cluster_id,
            submitted_at="2026-07-17T00:00:00+08:00",
            stdout="submitted",
            stderr="",
            resource_request=request,
        )

    def fake_collect(job_spec, *, submission, timed_out, terminal_reason, **kwargs):
        collected.append(dict(kwargs))
        return JobResult(
            job_name=job_spec.name,
            job_dir=job_spec.directory,
            status="error",
            unnormalized_variables=job_spec.unnormalized_variables,
            metadata={"job_name": job_spec.name, "status": "error", "engine": "htcondor"},
        )

    monkeypatch.setattr(condor_runner, "submit_condor_job", fake_submit)
    monkeypatch.setattr(condor_runner, "terminal_log_reason", lambda _job_dir: "held")
    monkeypatch.setattr(condor_runner, "condor_hold_info", lambda _submission: _resource_hold("disk"))
    monkeypatch.setattr(
        condor_runner,
        "condor_resource_usage",
        lambda _submission: {"condor_disk_usage_kib": 201},
    )
    monkeypatch.setattr(
        condor_runner,
        "remove_condor_job",
        lambda submission: removed.append(submission.cluster_id),
    )
    monkeypatch.setattr(condor_runner, "collect_condor_result", fake_collect)
    monkeypatch.setattr(condor_runner.time, "sleep", lambda _seconds: None)

    (result,) = condor_runner.run_condor_jobs((job,), timeout_sec=1)

    assert result.status == "error"
    assert len(submissions) == 2
    assert submissions[1][0].disk_kib == 400
    assert removed == [200, 201]
    assert len(collected) == 1
    retry_metadata = collected[0]["extra_metadata"]
    assert retry_metadata["yadof_resource_retry_disk_count"] == 1
    assert retry_metadata["yadof_resource_retry_exhausted"] is True
    assert retry_metadata["yadof_resource_retry_exhausted_resource"] == "disk"
