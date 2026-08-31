from __future__ import annotations

import math
from pathlib import Path
import threading
import time

import psutil
import pytest
import numpy as np

from yadof.config import load_config
from yadof.evaluate_manager import (
    EvaluationHandle,
    EvaluationHandleState,
    evaluate_population,
    prepare_evaluation,
    start_evaluation,
)
from yadof.job_template import api as job_template_api
from yadof.job_template import NamedRawDataItem, RAWDATA_SCHEMA_VERSION
from yadof.recorded_data import api as recorded_api
from yadof.recorded_data.paths import recorded_data_paths
from yadof.recorded_data.segment_store import discover_catalog
from yadof.recorded_data.session import CampaignSession, RecordingError
from yadof.evaluate_manager.types import JobResult
from yadof.workspace.init import init_workspace


def _workspace(tmp_path: Path, name: str = "workspace") -> Path:
    root = tmp_path / name
    init_workspace(root)
    return root


def _wait_for(predicate, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition did not become true before timeout")


def _write_sleeping_local_workflow(root: Path, seconds: float = 30.0) -> None:
    (root / "job_template/workflow.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import time\n"
        "Path('workflow.pid').write_text(str(os.getpid()), encoding='utf-8')\n"
        f"time.sleep({float(seconds)!r})\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_sleeping_fast_task(root: Path, seconds: float = 30.0) -> None:
    (root / "job_template/evaluation.py").write_text(
        "from __future__ import annotations\n"
        "import json\n"
        "import time\n"
        "import numpy as np\n"
        "def evaluate_rawdata(parameters, context):\n"
        f"    time.sleep({float(seconds)!r})\n"
        "    response = np.asarray(float(parameters['input_value']), dtype=float)\n"
        "    return {'response.npz': {'values': response, 'metadata': json.dumps({\n"
        "        'schema_version': 1, 'rawdata_name': 'response', 'shape': []\n"
        "    })}}\n",
        encoding="utf-8",
        newline="\n",
    )


def _memory_result(job, value: float) -> JobResult:
    values = np.asarray(value, dtype=np.float64)
    return JobResult(
        job_name=job.name,
        job_dir=job.directory,
        status="done",
        unnormalized_variables=tuple(job.unnormalized_variables),
        normalized_variables=tuple(job.normalized_variables),
        raw_data_items=(
            NamedRawDataItem(
                "response.npz",
                {
                    "values": values,
                    "metadata": {
                        "schema_version": RAWDATA_SCHEMA_VERSION,
                        "shape": list(values.shape),
                        "rawdata_name": "response",
                    },
                },
            ),
        ),
        metadata={
            "engine": "fake-htcondor",
            "population_index": job.population_index,
        },
    )


def test_cancel_before_start_is_ordered_idempotent_and_creates_no_evidence(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    batch = prepare_evaluation(root, ((0.25,), (0.75,)), mode="local")
    handle = EvaluationHandle(batch)

    assert handle.state == EvaluationHandleState.CREATED
    assert handle.cancel() is True
    assert handle.cancel() is False
    result = handle.wait()
    assert handle.wait() is result
    assert result.cancel_requested is True
    assert [row.status for row in result.rows] == ["cancelled", "cancelled"]
    assert all(row.metadata["evidence_state"] == "not_started" for row in result.rows)
    assert all(math.isinf(row[0]) for row in result.costs)
    with pytest.raises(RuntimeError, match="cancelled before start"):
        handle.start()

    handle.close()
    handle.close()
    assert handle.state == EvaluationHandleState.CLOSED
    assert not (root / "jobs").exists()
    assert recorded_api.list_records(root) == ()


def test_wait_exposes_only_committed_identity_and_open_handle_blocks_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path)
    config = load_config(root)
    session = CampaignSession(config)
    snapshot = session.begin_generation(config)
    observed: list[str] = []
    real_calculate = job_template_api.CostInterpreter.calculate_costs
    batch = prepare_evaluation(
        root,
        ((0.25,),),
        mode="local",
        timeout_sec=5.0,
        local_max_workers=1,
        _campaign_session=session,
        _task_snapshot=snapshot,
    )
    handle = EvaluationHandle(batch)

    def observed_calculate(self, samples, raw_variables=None):
        (record,) = session.records()
        assert record["evidence_state"] == "committed"
        assert record["publication_receipt"]["state"] == "committed"
        assert handle.state in {
            EvaluationHandleState.RUNNING,
            EvaluationHandleState.CANCELLING,
        }
        observed.append(str(record["publication_receipt"]["candidate_id"]))
        return real_calculate(self, samples, raw_variables)

    monkeypatch.setattr(
        job_template_api.CostInterpreter,
        "calculate_costs",
        observed_calculate,
    )
    handle.start()
    result = handle.wait()
    assert handle.wait() is result
    assert observed == [result.rows[0].metadata["candidate_id"]]
    assert result.rows[0].metadata["candidate_id"] == result.rows[0].metadata["evidence_id"]
    assert result.rows[0].metadata["publication_receipt_state"] == "committed"
    assert result.rows[0].metadata["interpretation_state"] == "succeeded"
    assert len(result.costs[0]) == 1
    assert math.isfinite(result.costs[0][0])
    with pytest.raises(TypeError):
        result.diagnostics["mutated"] = True
    with pytest.raises(TypeError):
        result.rows[0].metadata["mutated"] = True
    with pytest.raises(RuntimeError, match="handles remain open"):
        session.begin_generation(load_config(root))

    handle.close()
    handle.close()
    assert handle.cancel() is False
    second = session.begin_generation(load_config(root))
    assert second is session.current_snapshot
    session.close()
    (reference,) = discover_catalog(recorded_data_paths(root)).references
    assert reference.candidate_id == observed[0]


def test_wait_timeout_and_context_exception_cancel_local_process_tree(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    _write_sleeping_local_workflow(root)
    batch = prepare_evaluation(
        root,
        ((0.25,),),
        mode="local",
        timeout_sec=60.0,
        local_max_workers=1,
    )
    pid_path: Path | None = None
    with pytest.raises(LookupError, match="caller failure"):
        with EvaluationHandle(batch) as handle:
            with pytest.raises(TimeoutError, match="still running"):
                handle.wait(0.001)

            def process_started() -> bool:
                nonlocal pid_path
                jobs = tuple((root / "jobs").glob("*/workflow.pid"))
                if jobs:
                    pid_path = jobs[0]
                    return True
                return False

            _wait_for(process_started)
            raise LookupError("caller failure")

    assert handle.state == EvaluationHandleState.CLOSED
    assert pid_path is not None
    process_pid = int(pid_path.read_text(encoding="utf-8"))
    _wait_for(lambda: not psutil.pid_exists(process_pid))
    result = handle.wait()
    assert result.cancelled is True
    assert result.rows[0].status == "cancelled"
    assert recorded_api.list_records(root)[0]["status"] == "cancelled"


def test_session_close_cancels_registered_handle_before_writer_and_snapshot(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    _write_sleeping_local_workflow(root)
    config = load_config(root)
    session = CampaignSession(config)
    snapshot = session.begin_generation(config)
    handle = start_evaluation(
        prepare_evaluation(
            root,
            ((0.25,),),
            mode="local",
            timeout_sec=60.0,
            local_max_workers=1,
            _campaign_session=session,
            _task_snapshot=snapshot,
        )
    )
    pid_paths: list[Path] = []

    def process_started() -> bool:
        pid_paths[:] = list((root / "jobs").glob("*/workflow.pid"))
        return bool(pid_paths)

    _wait_for(process_started)
    process_pid = int(pid_paths[0].read_text(encoding="utf-8"))
    session.close()

    assert handle.state == EvaluationHandleState.CLOSED
    assert handle.wait().rows[0].status == "cancelled"
    _wait_for(lambda: not psutil.pid_exists(process_pid))
    assert not snapshot.snapshot_root.exists()
    followup = CampaignSession(load_config(root))
    followup.close()


def test_fast_cancel_stops_active_worker_and_drains_queued_candidate(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path)
    _write_sleeping_fast_task(root)
    config_path = root / "config.py"
    config_path.write_text(
        config_path.read_text(encoding="utf-8")
        + "\nFAST_RESOURCE_AUTODETECT_ENABLED = False\n",
        encoding="utf-8",
        newline="\n",
    )
    handle = start_evaluation(
        prepare_evaluation(
            root,
            ((0.25,), (0.75,)),
            mode="fast",
            timeout_sec=60.0,
            fast_max_workers=1,
        )
    )
    scratch = root / ".yadof/fast_scratch"
    _wait_for(lambda: scratch.is_dir() and bool(tuple(scratch.iterdir())))
    assert handle.cancel() is True
    result = handle.wait(15.0)
    assert [row.status for row in result.rows] == ["cancelled", "cancelled"]
    active = next(
        row for row in result.rows if row.metadata["failure_stage"] == "worker_cancel"
    )
    worker_pid = int(active.metadata["fast_worker_pid"])
    _wait_for(lambda: not psutil.pid_exists(worker_pid))
    handle.close()
    assert not scratch.exists() or not tuple(scratch.iterdir())
    assert [row["status"] for row in recorded_api.list_records(root)] == [
        "cancelled",
        "cancelled",
    ]


def test_fast_handle_success_returns_ordered_finalized_rows(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    _write_sleeping_fast_task(root, seconds=0.0)
    handle = start_evaluation(
        prepare_evaluation(
            root,
            ((0.25,), (0.75,)),
            mode="fast",
            timeout_sec=10.0,
            fast_max_workers=2,
        )
    )
    result = handle.wait(15.0)
    handle.close()
    assert [row.status for row in result.rows] == ["done", "done"]
    assert [row.normalized_variables for row in result.rows] == [
        (0.25,),
        (0.75,),
    ]
    assert all(row.metadata["candidate_id"] for row in result.rows)
    assert all(math.isfinite(row[0]) for row in result.costs)


def test_distributed_handle_cancel_removes_fake_clusters_and_keeps_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.evaluate_manager import condor_runner

    root = _workspace(tmp_path)
    submitted = threading.Event()
    removed: list[int] = []
    cluster_ids = iter((401, 402))

    def fake_submit(_workspace, job, **_kwargs):
        cluster_id = next(cluster_ids)
        return condor_runner.CondorSubmission(
            job=job,
            submit_file=job.directory / "job.sub",
            cluster_id=cluster_id,
            submitted_at="2026-08-31T00:00:00+00:00",
            stdout=f"submitted to cluster {cluster_id}",
            stderr="",
        )

    def fake_remove(_workspace, submission, **_kwargs):
        removed.append(int(submission.cluster_id))
        return None

    monkeypatch.setattr(condor_runner, "submit_condor_job", fake_submit)
    monkeypatch.setattr(condor_runner, "remove_condor_job", fake_remove)
    handle = start_evaluation(
        prepare_evaluation(
            root,
            ((0.25,), (0.75,)),
            mode="distributed",
            timeout_sec=60.0,
            after_jobs_submitted=submitted.set,
        )
    )
    assert submitted.wait(10.0)
    assert handle.cancel() is True
    result = handle.wait(15.0)
    assert [row.status for row in result.rows] == ["cancelled", "cancelled"]
    assert sorted(removed) == [401, 402]
    assert [row.metadata["condor_cluster_id"] for row in result.rows] == [401, 402]
    handle.close()


def test_distributed_handle_success_uses_same_finalized_result_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.evaluate_manager import condor_runner

    root = _workspace(tmp_path)

    def fake_run(_workspace, jobs, **_kwargs):
        return tuple(
            _memory_result(job, abs(float(job.unnormalized_variables[0])) ** 2)
            for job in jobs
        )

    monkeypatch.setattr(condor_runner, "run_condor_jobs", fake_run)
    handle = start_evaluation(
        prepare_evaluation(
            root,
            ((0.25,), (0.75,)),
            mode="distributed",
            timeout_sec=10.0,
        )
    )
    result = handle.wait(15.0)
    handle.close()
    assert [row.status for row in result.rows] == ["done", "done"]
    assert [row.normalized_variables for row in result.rows] == [
        (0.25,),
        (0.75,),
    ]
    assert all(row.metadata["publication_receipt_state"] == "committed" for row in result.rows)
    assert all(row.metadata["interpretation_state"] == "succeeded" for row in result.rows)


def test_recording_failure_wakes_repeated_waiters_and_remains_fatal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path)

    def fail_publish(*_args, **_kwargs):
        raise OSError("injected handle publication failure")

    monkeypatch.setattr(session_module, "publish_segment", fail_publish)
    handle = start_evaluation(
        prepare_evaluation(root, ((0.25,),), mode="local", timeout_sec=5.0)
    )
    for _ in range(2):
        with pytest.raises(
            RecordingError,
            match="before all evidence could be published",
        ):
            handle.wait(10.0)
    assert handle.state == EvaluationHandleState.FAILED
    with pytest.raises(RecordingError, match="before all evidence could be published"):
        handle.close()
    assert handle.state == EvaluationHandleState.CLOSED
    with pytest.raises(RecordingError, match="before all evidence could be published"):
        handle.close()
    assert recorded_api.list_records(root) == ()


def test_sync_facade_and_handle_share_one_result_adapter(tmp_path: Path) -> None:
    handle_root = _workspace(tmp_path, "handle")
    sync_root = _workspace(tmp_path, "sync")
    handle = start_evaluation(
        prepare_evaluation(handle_root, ((0.25,), (0.75,)), mode="local")
    )
    waited: list[object] = []

    def wait_once() -> None:
        waited.append(handle.wait())

    waiters = [threading.Thread(target=wait_once) for _ in range(2)]
    for waiter in waiters:
        waiter.start()
    for waiter in waiters:
        waiter.join(timeout=10.0)
        assert not waiter.is_alive()
    assert len(waited) == 2
    assert waited[0] is waited[1]
    result = waited[0]
    assert handle.cancel() is False
    handle.close()
    sync_costs = evaluate_population(sync_root, ((0.25,), (0.75,)), mode="local")
    for handle_row, sync_row in zip(result.costs, sync_costs):
        assert handle_row == pytest.approx(sync_row)
    assert [row.status for row in result.rows] == ["done", "done"]
