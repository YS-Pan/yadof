from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
import zipfile

import numpy as np
import pytest

from yadof.job_template import RAWDATA_SCHEMA_VERSION
from yadof.recorded_data import api as recorded_api
from yadof.workspace_init import init_workspace


def _workspace(path: Path) -> Path:
    init_workspace(path)
    return path


def _write_rawdata(
    raw_dir: Path,
    value: float,
    *,
    metadata: dict[str, object] | None = None,
) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    payload = (
        {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": [],
            "rawdata_name": "response",
            "variables": {"input_value": 123.0},
            "job_metadata": {"duplicate": True},
        }
        if metadata is None
        else metadata
    )
    np.savez(
        raw_dir / "response.npz",
        values=np.asarray(float(value), dtype=float),
        metadata=json.dumps(payload, sort_keys=True),
    )
    return raw_dir


def _replace_parameter_range(root: Path, old: str, new: str) -> None:
    path = root / "job_template/parameters_constraints.py"
    source = path.read_text(encoding="utf-8")
    assert old in source
    path.write_text(source.replace(old, new), encoding="utf-8", newline="\n")


def _multiply_cost(root: Path, factor: float) -> None:
    path = root / "job_template/calc_cost.py"
    source = path.read_text(encoding="utf-8")
    old = "return (float(value.item()),)"
    assert old in source
    path.write_text(
        source.replace(old, f"return (float(value.item()) * {float(factor)!r},)"),
        encoding="utf-8",
        newline="\n",
    )


def _record_worker(root_text: str, index: int) -> None:
    root = Path(root_text)
    recorded_api.record_job_result(
        root,
        f"job_{index}",
        (0.0,),
        root / f"jobs/source_{index}/rawData",
        {"worker": index},
    )


def test_same_named_jobs_are_isolated_between_workspace_histories(tmp_path: Path) -> None:
    first = _workspace(tmp_path / "first")
    second = _workspace(tmp_path / "second")
    _replace_parameter_range(second, "(-1.0, 1.0)", "(0.0, 2.0)")
    _multiply_cost(second, 10.0)

    first_record = recorded_api.record_job_result(
        first,
        "same_job",
        (0.5,),
        _write_rawdata(first / "jobs/first/rawData", 1.0),
        {
            "cost": 999.0,
            "created_at": "discarded",
            "started_at": "2026-07-18T10:00:00+08:00",
            "ended_at": "2026-07-18T10:00:01+08:00",
            "run_id": "first-run",
            "nested": {"costs": [123.0], "kept": True},
        },
    )
    recorded_api.record_job_result(
        second,
        "same_job",
        (0.5,),
        _write_rawdata(second / "jobs/second/rawData", 2.0),
        {"run_id": "second-run"},
    )

    assert first_record["started_at"] == "2026-07-18T10:00:00+08:00"
    assert first_record["ended_at"] == "2026-07-18T10:00:01+08:00"
    assert first_record["run_id"] == "first-run"
    assert "started_at" not in first_record["job_metadata"]
    assert "cost" not in first_record["job_metadata"]
    assert "created_at" not in first_record["job_metadata"]
    assert first_record["job_metadata"]["nested"] == {"kept": True}
    raw_metadata = first_record["rawdata_metadata"]["same_job/response.npz"]
    assert "variables" not in raw_metadata
    assert "job_metadata" not in raw_metadata

    assert recorded_api.get_historical_results(first) == (
        ("same_job", pytest.approx((0.75,)), pytest.approx((1.0,))),
    )
    assert recorded_api.get_historical_results(second) == (
        ("same_job", pytest.approx((0.25,)), pytest.approx((20.0,))),
    )
    assert recorded_api.get_historical_results(first)[0][2] == pytest.approx((1.0,))

    for root in (first, second):
        recorded = root / "recorded_data"
        assert (recorded / "indMeta.jsonl").is_file()
        assert (recorded / "rawData.npz").is_file()
        assert (recorded / "indMeta.jsonl.lock").is_file()
        with zipfile.ZipFile(recorded / "rawData.npz", "r") as archive:
            assert archive.namelist() == ["same_job/response.npz"]


def test_history_reinterprets_current_ranges_and_calc_cost(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    recorded_api.record_job_result(
        root,
        "historical",
        (0.5,),
        _write_rawdata(root / "jobs/historical/rawData", 2.0),
    )

    assert recorded_api.get_normalized_variables(root) == (
        ("historical", pytest.approx((0.75,))),
    )
    assert recorded_api.calculate_costs(root) == (
        ("historical", pytest.approx((2.0,))),
    )

    _replace_parameter_range(root, "(-1.0, 1.0)", "(0.0, 2.0)")
    _multiply_cost(root, 3.0)

    assert recorded_api.get_normalized_variables(root) == (
        ("historical", pytest.approx((0.25,))),
    )
    assert recorded_api.calculate_costs(root) == (
        ("historical", pytest.approx((6.0,))),
    )
    row = recorded_api.list_records(root)[0]
    assert "cost" not in row
    assert "normalized_variables" not in row


def test_invalid_rawdata_is_durable_but_skipped_and_diagnosed(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    invalid = _write_rawdata(
        root / "jobs/invalid/rawData",
        4.0,
        metadata={"shape": [], "rawdata_name": "response"},
    )
    valid = _write_rawdata(root / "jobs/valid/rawData", 2.0)
    recorded_api.record_job_result(root, "invalid", (0.0,), invalid)
    recorded_api.record_job_result(root, "valid", (0.0,), valid)

    assert tuple(name for name, _costs in recorded_api.calculate_costs(root)) == (
        "valid",
    )
    assert tuple(row[0] for row in recorded_api.get_historical_results(root)) == (
        "valid",
    )
    diagnostics = recorded_api.get_rawdata_diagnostics(root)
    assert len(diagnostics) == 1
    assert diagnostics[0]["job_name"] == "invalid"
    assert diagnostics[0]["error_type"] == "legacy_schema"
    assert diagnostics[0]["status"] == "skipped"


def test_failed_records_remain_visible_and_status_is_normalized(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    recorded_api.record_job_result(
        root,
        "failed",
        (),
        (),
        {"error": "boom"},
        status="error",
    )
    completed = recorded_api.record_job_result(
        root,
        "completed",
        (0.0,),
        _write_rawdata(root / "jobs/completed/rawData", 1.0),
        status="done",
    )

    assert completed["status"] == "completed"
    assert recorded_api.get_job_names(root) == ("failed", "completed")
    assert recorded_api.get_job_names(root, status="error") == ("failed",)
    assert tuple(row[0] for row in recorded_api.get_historical_results(root)) == (
        "completed",
    )
    assert recorded_api.list_records(root)[0]["job_metadata"]["error"] == "boom"


def test_existing_jsonl_is_recovered_and_duplicate_requires_overwrite(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    recorded = root / "recorded_data"
    recorded.mkdir()
    old = {
        "schema_version": 1,
        "job_name": "old_job",
        "status": "error",
        "raw_variables": [],
        "rawdata_files": [],
    }
    (recorded / "indMeta.jsonl").write_text(
        json.dumps(old) + "\n", encoding="utf-8", newline="\n"
    )

    recorded_api.record_job_result(root, "new_job", (), (), status="error")
    assert recorded_api.get_job_names(root) == ("old_job", "new_job")
    with pytest.raises(ValueError, match="already exists"):
        recorded_api.record_job_result(root, "new_job", (), (), status="error")
    replacement = recorded_api.record_job_result(
        root,
        "new_job",
        (),
        (),
        {"attempt": 2},
        status="timeout",
        overwrite=True,
    )
    assert replacement["status"] == "timeout"
    assert recorded_api.get_job_names(root) == ("old_job", "new_job")
    assert not tuple(recorded.glob("*.tmp"))


def test_corrupt_archive_is_skipped_and_diagnosed(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    recorded_api.record_job_result(
        root,
        "corrupt",
        (0.0,),
        _write_rawdata(root / "jobs/corrupt/rawData", 1.0),
    )
    (root / "recorded_data/rawData.npz").write_bytes(b"not a zip archive")

    assert recorded_api.get_historical_results(root) == ()
    diagnostics = recorded_api.get_rawdata_diagnostics(root)
    assert diagnostics[0]["job_name"] == "corrupt"
    assert diagnostics[0]["error_type"] == "unreadable_rawdata"


def test_concurrent_archive_and_manifest_writes_keep_every_record(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    for index in range(4):
        _write_rawdata(root / f"jobs/source_{index}/rawData", float(index + 1))

    context = multiprocessing.get_context("spawn")
    processes = [
        context.Process(target=_record_worker, args=(str(root), index))
        for index in range(4)
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(30)
        if process.is_alive():
            process.terminate()
            process.join()
            pytest.fail("recording worker did not finish")
        assert process.exitcode == 0

    assert sorted(recorded_api.get_job_names(root)) == [
        f"job_{index}" for index in range(4)
    ]
    assert sorted(cost[0] for _name, cost in recorded_api.calculate_costs(root)) == [
        1.0,
        2.0,
        3.0,
        4.0,
    ]
    with zipfile.ZipFile(root / "recorded_data/rawData.npz", "r") as archive:
        assert sorted(archive.namelist()) == [
            f"job_{index}/response.npz" for index in range(4)
        ]
    assert not tuple((root / "recorded_data").rglob("*.tmp"))


def test_optimization_and_surrogate_metadata_stay_workspace_local(
    tmp_path: Path,
) -> None:
    first = _workspace(tmp_path / "first")
    second = _workspace(tmp_path / "second")
    recorded_api.record_optimization_metadata(first, {"generation_index": 2})
    recorded_api.record_surrogate_metadata(
        first,
        {"generation_index": 2, "status": "completed", "sample_count": 5},
    )

    assert len(recorded_api.list_optimization_metadata(first)) == 2
    surrogate = recorded_api.list_surrogate_metadata(first)
    assert len(surrogate) == 1
    assert surrogate[0]["record_type"] == "surrogate_training"
    assert recorded_api.list_optimization_metadata(second) == ()
    assert (first / "recorded_data/optMeta/optMeta.jsonl").is_file()
    assert not (second / "recorded_data").exists()
