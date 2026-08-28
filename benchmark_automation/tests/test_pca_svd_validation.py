from __future__ import annotations

import json

import pytest

from benchmark_automation.experiment_runtime.linear_subspace import (
    ARM_IDS,
    load_partition,
    preflight,
    run_partition,
)


def _manifest(tmp_path, **updates):
    workspace = tmp_path / "case"
    workspace.mkdir()
    payload = {
        "protocol": "yadof.pca-svd-design-partition",
        "protocol_version": 1,
        "cases": [
            {
                "id": "saw",
                "workspace": str(workspace.resolve()),
                "training_job_names": ["train-1", "train-2"],
                "validation_job_names": ["validation-1"],
            }
        ],
    }
    payload.update(updates)
    path = tmp_path / "partition.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_preflight_is_schema_only_and_exposes_all_frozen_arms(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _manifest(tmp_path)
    monkeypatch.setattr(
        "benchmark_automation.experiment_runtime.linear_subspace._run_case",
        lambda _case: (_ for _ in ()).throw(AssertionError("fit must not run")),
    )
    result = preflight(path)
    assert result["status"] == "preflight-valid-no-fit"
    assert tuple(result["arm_ids"]) == ARM_IDS
    assert result["measured_run_started"] is False


def test_measured_run_is_double_gated_before_recorded_evidence_access(tmp_path) -> None:
    path = _manifest(tmp_path)
    assert load_partition(path)["cases"][0]["id"] == "saw"
    with pytest.raises(PermissionError, match="execution authority"):
        run_partition(path)


def test_partition_rejects_design_leakage_and_test_locators(tmp_path) -> None:
    path = _manifest(tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["cases"][0]["validation_job_names"] = ["train-1"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="overlap"):
        load_partition(path)
    payload["cases"][0]["validation_job_names"] = ["validation-1"]
    payload["cases"][0]["test_job_names"] = ["forbidden"]
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="test locators"):
        load_partition(path)
