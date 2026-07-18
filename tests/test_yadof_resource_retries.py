from __future__ import annotations

from pathlib import Path

from yadof.config import load_config
from yadof.evaluate_manager.resource_requests import HTCondorResourceRequest
from yadof.evaluate_manager.resource_retries import (
    decide_resource_retry,
    new_resource_retry_state,
    reset_job_for_resource_retry,
    resource_retry_metadata,
)
from yadof.evaluate_manager.types import JobSpec
from yadof.workspace_init import init_workspace


def _request():
    return HTCondorResourceRequest(2, 100, 200, "test_default", 0)


def _workspace(tmp_path: Path, retries: int = 2) -> Path:
    root = tmp_path / "workspace"
    init_workspace(root)
    (root / "config.py").write_text(
        f"YADOF_RESOURCE_RETRY_DOUBLINGS = {retries}\nHTCONDOR_POLL_SEC = 0.1\n",
        encoding="utf-8",
    )
    return root


def _job(workspace: Path):
    job_dir = workspace / "jobs" / "job_001"
    job_dir.mkdir(parents=True)
    (job_dir / "workflow.py").write_text("# test\n", encoding="utf-8")
    return JobSpec(
        name="job_001",
        directory=job_dir,
        normalized_variables=(0.5,),
        unnormalized_variables=(5.0,),
        run_id="run_001",
        generation_index=1,
    )


def _resource_hold(resource: str) -> dict[str, object]:
    return {
        "condor_hold_reason": f"{resource} usage exceeded",
        "condor_hold_reason_code": "34",
        "condor_hold_reason_subcode": "102" if resource == "memory" else "104",
    }


def test_yadof_doubles_memory_until_workspace_retry_limit(tmp_path):
    workspace = _workspace(tmp_path, retries=2)
    state = new_resource_retry_state(_request(), config=load_config(workspace))
    first = decide_resource_retry(
        state,
        hold_info=_resource_hold("memory"),
        resource_usage={"condor_memory_usage_mib": 101},
        cluster_id=10,
    )
    assert first is not None and first.should_retry
    second = decide_resource_retry(
        first.state,
        hold_info=_resource_hold("memory"),
        resource_usage={"condor_memory_usage_mib": 201},
        cluster_id=11,
    )
    assert second is not None and second.should_retry
    exhausted = decide_resource_retry(
        second.state,
        hold_info=_resource_hold("memory"),
        resource_usage={"condor_memory_usage_mib": 401},
        cluster_id=12,
    )
    assert exhausted is not None and not exhausted.should_retry
    assert exhausted.state.request.memory_mib == 400
    metadata = resource_retry_metadata(exhausted.state)
    assert metadata["yadof_resource_retry_memory_count"] == 2
    assert metadata["yadof_resource_retry_exhausted_resource"] == "memory"
    assert [row["action"] for row in metadata["yadof_resource_retry_history"]] == [
        "retry",
        "retry",
        "exhausted",
    ]


def test_memory_and_disk_counts_are_independent(tmp_path):
    workspace = _workspace(tmp_path)
    state = new_resource_retry_state(_request(), config=load_config(workspace))
    memory = decide_resource_retry(
        state, hold_info=_resource_hold("memory"), resource_usage={}, cluster_id=20
    )
    disk = decide_resource_retry(
        memory.state,
        hold_info=_resource_hold("disk"),
        resource_usage={},
        cluster_id=21,
    )
    assert disk is not None
    assert (disk.state.request.memory_mib, disk.state.request.disk_kib) == (200, 400)
    assert (disk.state.memory_retry_count, disk.state.disk_retry_count) == (1, 1)


def test_non_resource_holds_are_not_retried(tmp_path):
    workspace = _workspace(tmp_path)
    state = new_resource_retry_state(_request(), config=load_config(workspace))
    assert decide_resource_retry(
        state,
        hold_info={"condor_hold_reason_code": "47", "condor_hold_reason_subcode": "0"},
        resource_usage={},
        cluster_id=30,
    ) is None


def test_retry_reset_preserves_static_inputs(tmp_path):
    workspace = _workspace(tmp_path)
    job = _job(workspace)
    (job.directory / "metadata.json").write_text("{}\n", encoding="utf-8")
    for name in ("cluster.id", "condor.log", "individual_metadata.json", "batch.log"):
        (job.directory / name).write_text("old\n", encoding="utf-8")
    for name in ("rawData", "._home", "._tmp"):
        folder = job.directory / name
        folder.mkdir()
        (folder / "old.txt").write_text("old\n", encoding="utf-8")
    reset_job_for_resource_retry(job.directory)
    assert (job.directory / "workflow.py").is_file()
    assert (job.directory / "metadata.json").is_file()
    assert not (job.directory / "condor.log").exists()
    assert not (job.directory / "rawData").exists()


def test_condor_runner_resubmits_a_resource_hold(tmp_path, monkeypatch):
    from yadof.evaluate_manager import condor_runner
    from yadof.evaluate_manager.condor_runner import CondorSubmission
    from yadof.evaluate_manager.types import JobResult

    workspace = _workspace(tmp_path)
    job = _job(workspace)
    submissions = []
    removed = []

    def fake_submit(_workspace, job_spec, **kwargs):
        request = kwargs.get("resource_request") or _request()
        submit_file = job_spec.directory / "job.sub"
        submit_file.write_text("queue 1\n", encoding="utf-8")
        submissions.append((request, kwargs.get("resource_retry_metadata")))
        return CondorSubmission(
            job_spec,
            submit_file,
            100 + len(submissions) - 1,
            "2026-07-17T00:00:00+08:00",
            "submitted",
            "",
            request,
        )

    def fake_collect(_workspace, job_spec, **_kwargs):
        return JobResult(
            job_spec.name,
            job_spec.directory,
            "done",
            job_spec.unnormalized_variables,
            metadata={"status": "done", "engine": "htcondor"},
        )

    monkeypatch.setattr(condor_runner, "submit_condor_job", fake_submit)
    monkeypatch.setattr(
        condor_runner,
        "terminal_log_reason",
        lambda _path: "held" if len(submissions) == 1 else "terminated",
    )
    monkeypatch.setattr(condor_runner, "condor_hold_info", lambda _sub: _resource_hold("memory"))
    monkeypatch.setattr(
        condor_runner,
        "condor_resource_usage",
        lambda *_args, **_kwargs: {"condor_memory_usage_mib": 101},
    )
    monkeypatch.setattr(
        condor_runner,
        "remove_condor_job",
        lambda _workspace, submission, **_kwargs: removed.append(submission.cluster_id),
    )
    monkeypatch.setattr(condor_runner, "collect_condor_result", fake_collect)
    monkeypatch.setattr(condor_runner.time, "sleep", lambda _seconds: None)

    (result,) = condor_runner.run_condor_jobs(workspace, (job,), timeout_sec=1)
    assert result.status == "done"
    assert len(submissions) == 2
    assert submissions[1][0].memory_mib == 200
    assert submissions[1][1]["yadof_resource_retry_total_count"] == 1
    assert removed == [100]
