from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import numpy as np
import pytest

from project.job_template.rawdata_contract import RAWDATA_SCHEMA_VERSION


def _normalized_variables() -> tuple[float, ...]:
    from project.job_template import api as job_template_api

    return (0.25, 0.5, 0.75) + (0.5,) * (job_template_api.get_variable_count() - 3)


def _raw_variables() -> tuple[float, ...]:
    from project.job_template import api as job_template_api

    return job_template_api.denormalize_variables(_normalized_variables())


def _configure_recorded_api(recorded_api, root: Path) -> None:
    recorded_api.MODULE_DIR = root
    recorded_api.MANIFEST_PATH = root / "manifest.json"
    recorded_api.RAWDATA_ROOT = root / "rawData"


def _write_rawdata_set(raw_dir: Path, *, offset: float = 0.0) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    metadata_base = {"schema_version": RAWDATA_SCHEMA_VERSION}
    np.savez(
        raw_dir / "summary.npz",
        values=np.array([0.90 - offset, 0.10 + offset]),
        metadata=json.dumps({**metadata_base, "rawdata_name": "summary", "source": "test", "shape": [2]}),
    )
    np.savez(
        raw_dir / "curve.npz",
        axis_0=np.array([0.0, 1.0]),
        axis_1=np.array([0.0, 0.5, 1.0]),
        values=np.array([[100.0, 0.90 - offset, 100.0], [100.0, 0.10 + offset, 100.0]]),
        metadata=json.dumps(
            {
                **metadata_base,
                "rawdata_name": "curve",
                "source": "test",
                "shape": [2, 3],
                "axes": [
                    {"index": 0, "size": 2, "values_key": "axis_0"},
                    {"index": 1, "size": 3, "values_key": "axis_1"},
                ],
            }
        ),
    )
    np.savez(
        raw_dir / "surface.npz",
        axis_0=np.array([0.0, 0.5, 1.0]),
        axis_1=np.array([0.0, 0.5, 1.0]),
        values=np.array([[0.0, 0.0, 0.0], [0.0, 0.90 - offset, 0.0], [0.0, 0.0, 0.0]]),
        metadata=json.dumps(
            {
                **metadata_base,
                "rawdata_name": "surface",
                "source": "test",
                "shape": [3, 3],
                "axes": [
                    {"index": 0, "size": 3, "values_key": "axis_0"},
                    {"index": 1, "size": 3, "values_key": "axis_1"},
                ],
            }
        ),
    )
    return raw_dir


def _write_invalid_rawdata_set(raw_dir: Path, *, metadata: dict[str, object], values) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    np.savez(
        raw_dir / "summary.npz",
        values=np.asarray(values),
        metadata=json.dumps(metadata),
    )
    np.savez(
        raw_dir / "curve.npz",
        axis_0=np.array([0.0, 1.0]),
        axis_1=np.array([0.0, 0.5, 1.0]),
        values=np.array([[100.0, 0.90, 100.0], [100.0, 0.10, 100.0]]),
        metadata=json.dumps(
            {
                "schema_version": RAWDATA_SCHEMA_VERSION,
                "rawdata_name": "curve",
                "source": "test",
                "shape": [2, 3],
                "axes": [
                    {"index": 0, "size": 2, "values_key": "axis_0"},
                    {"index": 1, "size": 3, "values_key": "axis_1"},
                ],
            }
        ),
    )
    np.savez(
        raw_dir / "surface.npz",
        axis_0=np.array([0.0, 0.5, 1.0]),
        axis_1=np.array([0.0, 0.5, 1.0]),
        values=np.array([[0.0, 0.0, 0.0], [0.0, 0.90, 0.0], [0.0, 0.0, 0.0]]),
        metadata=json.dumps(
            {
                "schema_version": RAWDATA_SCHEMA_VERSION,
                "rawdata_name": "surface",
                "source": "test",
                "shape": [3, 3],
                "axes": [
                    {"index": 0, "size": 3, "values_key": "axis_0"},
                    {"index": 1, "size": 3, "values_key": "axis_1"},
                ],
            }
        ),
    )
    return raw_dir


def _record_error_worker(root_text: str, index: int) -> None:
    from project.recorded_data import api as recorded_api

    root = Path(root_text)
    _configure_recorded_api(recorded_api, root)
    recorded_api.record_job_result(
        f"job_{index}",
        (float(index), float(index + 1), 0.5),
        (),
        {"worker": index},
        status="error",
    )


def test_completed_record_enters_history_and_manifest_has_metadata(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    raw_dir = _write_rawdata_set(tmp_path / "job_rawdata")

    record = recorded_api.record_job_result(
        "job_completed",
        _raw_variables(),
        raw_dir,
        {
            "runner": "local",
            "cost": 999.0,
            "normalized_variables": (0.1, 0.2, 0.3),
            "nested": {"costs": (1.0,), "kept": True},
        },
    )

    assert record["status"] == "completed"
    assert "cost" not in record
    assert "normalized_variables" not in record
    assert "cost" not in record["job_metadata"]
    assert "normalized_variables" not in record["job_metadata"]
    assert record["job_metadata"]["nested"] == {"kept": True}
    assert record["rawdata_metadata"]["summary.npz"]["rawdata_name"] == "summary"
    assert record["rawdata_metadata"]["summary.npz"]["schema_version"] == RAWDATA_SCHEMA_VERSION

    manifest = json.loads(recorded_api.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == recorded_api.MANIFEST_SCHEMA_VERSION
    assert isinstance(manifest["updated_at"], str)
    assert manifest["record_statuses"] == list(recorded_api.VALID_RECORD_STATUSES)

    history = recorded_api.get_optimization_history()
    assert len(history) == 1
    job_name, normalized_variables, costs = history[0]
    assert job_name == "job_completed"
    assert normalized_variables == pytest.approx(_normalized_variables())
    assert len(costs) == 3
    assert all(0.0 <= value <= 1.0 for value in costs)
    assert all(value < 0.1 for value in costs)
    assert recorded_api.get_rawdata_diagnostics() == ()


def test_error_and_timeout_are_recorded_but_excluded_from_default_history(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    raw_dir = _write_rawdata_set(tmp_path / "job_rawdata")

    recorded_api.record_job_result("job_completed", _raw_variables(), raw_dir)
    recorded_api.record_job_result("job_error", _raw_variables(), (), {"error": "boom"}, status="error")
    recorded_api.record_job_result("job_timeout", _raw_variables(), (), {"timed_out": True}, status="timeout")

    assert recorded_api.get_job_names() == ("job_completed", "job_error", "job_timeout")
    assert recorded_api.get_job_names(status="error") == ("job_error",)
    assert recorded_api.get_job_names(status="timeout") == ("job_timeout",)
    assert len(recorded_api.list_records()) == 3
    assert tuple(row[0] for row in recorded_api.get_optimization_history()) == ("job_completed",)
    assert len(recorded_api.get_surrogate_training_data()["raw_data"]) == 1


@pytest.mark.parametrize(
    ("metadata", "values"),
    (
        (
            {
                "schema_version": RAWDATA_SCHEMA_VERSION,
                "rawdata_name": "summary",
                "source": "legacy",
                "shape": [3],
                "axes": {"time": "seconds"},
            },
            [0.35, -0.45, 0.65],
        ),
        (
            {"schema_version": RAWDATA_SCHEMA_VERSION, "rawdata_name": "summary", "source": "legacy", "shape": [2]},
            [0.35, -0.45, 0.65],
        ),
    ),
)
def test_incompatible_completed_rawdata_is_skipped_in_optimization_history(tmp_path, metadata, values):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    bad_raw_dir = _write_invalid_rawdata_set(tmp_path / "bad_rawdata", metadata=metadata, values=values)
    good_raw_dir = _write_rawdata_set(tmp_path / "good_rawdata")

    recorded_api.record_job_result("job_bad", _raw_variables(), bad_raw_dir)
    recorded_api.record_job_result("job_good", _raw_variables(), good_raw_dir)

    costs = recorded_api.calculate_costs()
    history = recorded_api.get_optimization_history()
    diagnostics = recorded_api.get_rawdata_diagnostics()

    assert tuple(row[0] for row in costs) == ("job_good",)
    assert tuple(row[0] for row in history) == ("job_good",)
    assert len(history[0][2]) == 3
    assert all(value < 0.1 for value in history[0][2])
    assert tuple(row["job_name"] for row in diagnostics) == ("job_bad",)
    assert diagnostics[0]["filename"] == "summary.npz"
    assert diagnostics[0]["status"] == "skipped"
    assert diagnostics[0]["error_message"]


def test_incompatible_completed_rawdata_is_skipped_for_surrogate_training(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    bad_raw_dir = _write_invalid_rawdata_set(
        tmp_path / "bad_rawdata",
        metadata={"schema_version": RAWDATA_SCHEMA_VERSION, "rawdata_name": "summary", "source": "legacy", "shape": [2]},
        values=[0.35, -0.45, 0.65],
    )
    good_raw_dir = _write_rawdata_set(tmp_path / "good_rawdata")

    recorded_api.record_job_result("job_bad", _raw_variables(), bad_raw_dir)
    recorded_api.record_job_result("job_good", _raw_variables(), good_raw_dir)

    training_data = recorded_api.get_surrogate_training_data()

    assert len(training_data["normalized_variables"]) == 1
    assert training_data["normalized_variables"][0] == pytest.approx(_normalized_variables())
    assert len(training_data["raw_data"]) == 1


def test_incompatible_variable_count_is_skipped_in_history_and_training(tmp_path):
    from project.recorded_data import api as recorded_api
    from project.job_template import api as job_template_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    raw_dir = _write_rawdata_set(tmp_path / "job_rawdata")
    short_variables = (0.5,) * (job_template_api.get_variable_count() - 1)

    recorded_api.record_job_result("job_short_variables", short_variables, raw_dir)

    assert recorded_api.get_optimization_history() == ()
    assert recorded_api.get_surrogate_training_data()["raw_data"] == ()


def test_legacy_rawdata_missing_schema_version_is_skipped_and_diagnosed(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    legacy_raw_dir = _write_invalid_rawdata_set(
        tmp_path / "legacy_rawdata",
        metadata={"rawdata_name": "summary", "source": "legacy", "shape": [3]},
        values=[0.35, -0.45, 0.65],
    )
    good_raw_dir = _write_rawdata_set(tmp_path / "good_rawdata")

    recorded_api.record_job_result("job_legacy", _raw_variables(), legacy_raw_dir)
    recorded_api.record_job_result("job_good", _raw_variables(), good_raw_dir)

    diagnostics = recorded_api.get_rawdata_diagnostics()

    assert tuple(row[0] for row in recorded_api.get_optimization_history()) == ("job_good",)
    assert tuple(row["job_name"] for row in diagnostics) == ("job_legacy",)
    assert diagnostics[0]["error_type"] == "legacy_schema"


def test_duplicate_job_requires_explicit_overwrite(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    raw_dir = _write_rawdata_set(tmp_path / "job_rawdata")

    recorded_api.record_job_result("job_repeat", _raw_variables(), raw_dir, {"attempt": 1})
    with pytest.raises(ValueError, match="already exists"):
        recorded_api.record_job_result("job_repeat", _raw_variables(), raw_dir, {"attempt": 2})

    replacement = recorded_api.record_job_result(
        "job_repeat",
        _raw_variables(),
        (),
        {"attempt": 3},
        status="error",
        overwrite=True,
    )

    assert replacement["status"] == "error"
    records = recorded_api.list_records()
    assert len(records) == 1
    assert records[0]["job_metadata"] == {"attempt": 3}
    assert recorded_api.get_optimization_history() == ()


def test_record_job_result_rejects_nested_rawdata_directory(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    raw_dir = _write_rawdata_set(tmp_path / "job_rawdata")
    (raw_dir / "nested").mkdir()

    with pytest.raises(ValueError, match="flat"):
        recorded_api.record_job_result("job_nested", _raw_variables(), raw_dir)


def test_old_manifest_is_readable_and_upgraded_on_next_write(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    record_root.mkdir(parents=True)
    recorded_api.MANIFEST_PATH.write_text(
        json.dumps({"records": [{"job_name": "old_job", "status": "error", "raw_variables": []}]}),
        encoding="utf-8",
    )

    assert tuple(record["job_name"] for record in recorded_api.list_records()) == ("old_job",)

    recorded_api.record_job_result("new_job", _raw_variables(), (), status="error")
    manifest = json.loads(recorded_api.MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == recorded_api.MANIFEST_SCHEMA_VERSION
    assert isinstance(manifest["updated_at"], str)
    assert tuple(record["job_name"] for record in manifest["records"]) == ("old_job", "new_job")


def test_concurrent_recording_keeps_all_manifest_records(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    ctx = multiprocessing.get_context("spawn")
    processes = [
        ctx.Process(target=_record_error_worker, args=(str(record_root), index))
        for index in range(4)
    ]

    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join()
            pytest.fail("recording worker did not finish")
        assert process.exitcode == 0

    records = recorded_api.list_records()
    assert sorted(record["job_name"] for record in records) == [f"job_{index}" for index in range(4)]
    assert all(record["status"] == "error" for record in records)
