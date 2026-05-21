from __future__ import annotations

import json
import multiprocessing
from pathlib import Path
import zipfile

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
    recorded_api.IND_META_PATH = root / "indMeta.jsonl"
    recorded_api.RAWDATA_ARCHIVE_PATH = root / "rawData.npz"
    recorded_api.OPT_META_DIR = root / "optMeta"
    recorded_api.OPT_META_PATH = root / "optMeta" / "optMeta.jsonl"


def _write_rawdata_set(raw_dir: Path, *, offset: float = 0.0) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    metadata_base = {
        "schema_version": RAWDATA_SCHEMA_VERSION,
        "variables": {"x0": 0.25, "x1": 0.5},
        "job_metadata": {"job_name": "repeated"},
    }
    freq_axis = np.array([2.30, 2.39, 2.44, 2.49, 2.60])
    theta_axis = np.array([-30.0, 0.0, 30.0])
    for state in (1, 2, 3, 4):
        np.savez(
            raw_dir / f"s11_pinState{state}.npz",
            axis_Freq=freq_axis,
            unit_Freq=np.asarray("GHz"),
            data=np.array([-3.0, -3.0, -12.0 + offset, -3.0, -3.0]),
            metadata=json.dumps(
                {
                    **metadata_base,
                    "rawdata_name": f"s11_pinState{state}",
                    "source": "test",
                    "pin_state": state,
                    "shape": [5],
                    "axis_names": ["Freq"],
                    "axes": [{"index": 0, "size": 5, "name": "Freq", "values_key": "axis_Freq", "unit": "GHz"}],
                }
            ),
        )
    gain_values = {
        1: [7.0 - offset, 0.0, 0.0 + offset],
        2: [0.0 + offset, 0.0, 7.0 - offset],
        3: [7.0 - offset, -15.0 + offset, 7.0 - offset],
        4: [0.0, 8.0 - offset, 0.0],
    }
    for state, values in gain_values.items():
        np.savez(
            raw_dir / f"gain_pinState{state}.npz",
            axis_Theta=theta_axis,
            unit_Theta=np.asarray("deg"),
            data=np.asarray(values, dtype=float),
            metadata=json.dumps(
                {
                    **metadata_base,
                    "rawdata_name": f"gain_pinState{state}",
                    "source": "test",
                    "pin_state": state,
                    "shape": [3],
                    "axis_names": ["Theta"],
                    "axes": [{"index": 0, "size": 3, "name": "Theta", "values_key": "axis_Theta", "unit": "deg"}],
                }
            ),
        )
    return raw_dir


def _write_invalid_rawdata_set(raw_dir: Path, *, metadata: dict[str, object], values) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    _write_rawdata_set(raw_dir)
    np.savez(
        raw_dir / "s11_pinState1.npz",
        data=np.asarray(values),
        metadata=json.dumps(metadata),
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


def test_completed_record_enters_history_and_jsonl_archive_has_metadata(tmp_path):
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
            "created_at": "2026-05-14T08:00:00+08:00",
            "started_at": "2026-05-14T08:00:10+08:00",
            "ended_at": "2026-05-14T08:00:20+08:00",
            "run_id": "pytest_run",
            "optimization_index": 3,
            "generation_index": 2,
            "variables": {"x0": 0.25},
            "unnormalized_variables": (1.0, 2.0),
            "normalized_variables": (0.1, 0.2, 0.3),
            "nested": {"costs": (1.0,), "kept": True},
        },
    )

    assert record["status"] == "completed"
    assert "cost" not in record
    assert record["started_at"] == "2026-05-14T08:00:10+08:00"
    assert record["ended_at"] == "2026-05-14T08:00:20+08:00"
    assert record["run_id"] == "pytest_run"
    assert record["optimization_index"] == 3
    assert record["generation_index"] == 2
    assert "normalized_variables" not in record
    assert "cost" not in record["job_metadata"]
    assert "created_at" not in record["job_metadata"]
    assert "variables" not in record["job_metadata"]
    assert "unnormalized_variables" not in record["job_metadata"]
    assert "normalized_variables" not in record["job_metadata"]
    assert "started_at" not in record["job_metadata"]
    assert "ended_at" not in record["job_metadata"]
    assert record["job_metadata"]["nested"] == {"kept": True}
    assert record["rawdata_metadata"]["job_completed/s11_pinState1.npz"]["rawdata_name"] == "s11_pinState1"
    assert record["rawdata_metadata"]["job_completed/s11_pinState1.npz"]["schema_version"] == RAWDATA_SCHEMA_VERSION
    assert "variables" not in record["rawdata_metadata"]["job_completed/s11_pinState1.npz"]
    assert "job_metadata" not in record["rawdata_metadata"]["job_completed/s11_pinState1.npz"]

    rows = [
        json.loads(line)
        for line in recorded_api.IND_META_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["schema_version"] == recorded_api.IND_META_SCHEMA_VERSION
    assert rows[0]["job_name"] == "job_completed"
    assert isinstance(rows[0]["recorded_at"], str)
    with zipfile.ZipFile(recorded_api.RAWDATA_ARCHIVE_PATH, "r") as archive:
        assert sorted(archive.namelist()) == [
            "job_completed/gain_pinState1.npz",
            "job_completed/gain_pinState2.npz",
            "job_completed/gain_pinState3.npz",
            "job_completed/gain_pinState4.npz",
            "job_completed/s11_pinState1.npz",
            "job_completed/s11_pinState2.npz",
            "job_completed/s11_pinState3.npz",
            "job_completed/s11_pinState4.npz",
        ]

    history = recorded_api.get_optimization_history()
    assert len(history) == 1
    job_name, normalized_variables, costs = history[0]
    assert job_name == "job_completed"
    assert normalized_variables == pytest.approx(_normalized_variables())
    assert len(costs) == 4
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
                "rawdata_name": "s11_pinState1",
                "source": "legacy",
                "shape": [3],
                "axes": {"time": "seconds"},
            },
            [0.35, -0.45, 0.65],
        ),
        (
            {"schema_version": RAWDATA_SCHEMA_VERSION, "rawdata_name": "s11_pinState1", "source": "legacy", "shape": [2]},
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
    assert len(history[0][2]) == 4
    assert all(value < 0.1 for value in history[0][2])
    assert tuple(row["job_name"] for row in diagnostics) == ("job_bad",)
    assert diagnostics[0]["filename"] == "s11_pinState1.npz"
    assert diagnostics[0]["status"] == "skipped"
    assert diagnostics[0]["error_message"]


def test_incompatible_completed_rawdata_is_skipped_for_surrogate_training(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    bad_raw_dir = _write_invalid_rawdata_set(
        tmp_path / "bad_rawdata",
        metadata={"schema_version": RAWDATA_SCHEMA_VERSION, "rawdata_name": "s11_pinState1", "source": "legacy", "shape": [2]},
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
        metadata={"rawdata_name": "s11_pinState1", "source": "legacy", "shape": [3]},
        values=[0.35, -0.45, 0.65],
    )
    good_raw_dir = _write_rawdata_set(tmp_path / "good_rawdata")

    recorded_api.record_job_result("job_legacy", _raw_variables(), legacy_raw_dir)
    recorded_api.record_job_result("job_good", _raw_variables(), good_raw_dir)

    diagnostics = recorded_api.get_rawdata_diagnostics()

    assert tuple(row[0] for row in recorded_api.get_optimization_history()) == ("job_good",)
    assert tuple(row["job_name"] for row in diagnostics) == ("job_legacy",)
    assert diagnostics[0]["error_type"] == "legacy_schema"


def test_corrupt_rawdata_archive_is_skipped_and_diagnosed(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    raw_dir = _write_rawdata_set(tmp_path / "job_rawdata")
    recorded_api.record_job_result("job_bad_archive", _raw_variables(), raw_dir)
    recorded_api.RAWDATA_ARCHIVE_PATH.write_bytes(b"not a zip archive")

    assert recorded_api.get_optimization_history() == ()
    diagnostics = recorded_api.get_rawdata_diagnostics()

    assert tuple(row["job_name"] for row in diagnostics) == (
        "job_bad_archive",
        "job_bad_archive",
        "job_bad_archive",
        "job_bad_archive",
        "job_bad_archive",
        "job_bad_archive",
        "job_bad_archive",
        "job_bad_archive",
    )
    assert {row["error_type"] for row in diagnostics} == {"unreadable_rawdata"}


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


def test_existing_ind_meta_jsonl_is_preserved_on_next_write(tmp_path):
    from project.recorded_data import api as recorded_api

    record_root = tmp_path / "recorded_data"
    _configure_recorded_api(recorded_api, record_root)
    record_root.mkdir(parents=True)
    recorded_api.IND_META_PATH.write_text(
        json.dumps({"schema_version": 1, "job_name": "old_job", "status": "error", "raw_variables": []}) + "\n",
        encoding="utf-8",
    )

    assert tuple(record["job_name"] for record in recorded_api.list_records()) == ("old_job",)

    recorded_api.record_job_result("new_job", _raw_variables(), (), status="error")
    rows = [
        json.loads(line)
        for line in recorded_api.IND_META_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert tuple(record["job_name"] for record in rows) == ("old_job", "new_job")
    assert rows[1]["schema_version"] == recorded_api.IND_META_SCHEMA_VERSION
    assert isinstance(rows[1]["recorded_at"], str)


def test_concurrent_recording_keeps_all_ind_meta_records(tmp_path):
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
