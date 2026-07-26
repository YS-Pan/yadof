from __future__ import annotations

import json
import zipfile

import numpy as np
import pytest

from yadof.evaluate_manager.worker_files import worker_misc


def test_run_workflow_owns_execute_metadata_and_transport(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_misc, "__file__", str(tmp_path / "worker_misc.py"))
    monkeypatch.setattr(worker_misc.platform, "node", lambda: "execute-node-a")

    def evaluate(context):
        values = np.asarray([1.0, 2.0])
        np.savez(
            context.raw_data_dir / "response.npz",
            values=values,
            metadata=json.dumps(
                worker_misc.rawdata_metadata("response", values.shape),
            ),
        )
        return 17

    result = worker_misc.run_workflow(
        evaluate,
        metadata={"task_name": "synthetic"},
    )

    assert result == 17
    metadata = json.loads(
        (tmp_path / "individual_metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["status"] == "done"
    assert metadata["execute_machine"] == "execute-node-a"
    assert metadata["task_name"] == "synthetic"
    assert metadata["raw_data_files"] == ["response.npz"]
    assert not (tmp_path / "_home").exists()
    assert not (tmp_path / "_appdata").exists()
    assert not (tmp_path / "_localappdata").exists()
    assert not (tmp_path / "_tmp").exists()
    with zipfile.ZipFile(tmp_path / "rawData.zip") as archive:
        assert archive.namelist() == ["response.npz"]


def test_run_workflow_records_task_failure_and_runs_cleanup(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_misc, "__file__", str(tmp_path / "worker_misc.py"))
    cleanup_calls = []

    def evaluate(context):
        del context
        raise RuntimeError("task failed")

    def cleanup(context):
        cleanup_calls.append(context.base_dir)

    with pytest.raises(RuntimeError, match="task failed"):
        worker_misc.run_workflow(evaluate, cleanup=cleanup)

    metadata = json.loads(
        (tmp_path / "individual_metadata.json").read_text(encoding="utf-8")
    )
    assert cleanup_calls == [tmp_path]
    assert metadata["status"] == "error"
    assert metadata["error_type"] == "RuntimeError"
    assert metadata["error_message"] == "task failed"
    assert (tmp_path / "rawData.zip").is_file()


def test_runtime_identity_cannot_override_execute_machine(tmp_path) -> None:
    with pytest.raises(ValueError, match="execute_machine"):
        worker_misc.runtime_identity(
            tmp_path,
            extra={"execute_machine": "submit-side-value"},
        )
