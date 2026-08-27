from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import struct
import threading
import time
import zipfile

import numpy as np
import pytest

from yadof.config import load_config
from yadof.evaluate_manager.finalizer import finalize_result
from yadof.evaluate_manager.types import JobResult
from yadof.job_template import RAWDATA_SCHEMA_VERSION, NamedRawDataItem
from yadof.recorded_data import api as recorded_api
from yadof.recorded_data.campaign_lock import CampaignActiveError
from yadof.recorded_data.paths import recorded_data_paths
from yadof.recorded_data.records import build_owned_envelope
from yadof.recorded_data.segment_store import (
    CatalogSnapshot,
    SegmentReference,
    discover_catalog,
    open_historical_rawdata_snapshot,
    publish_segment,
)
from yadof.recorded_data.session import CampaignSession, RecordingError
from yadof.tools.history import clear_history
from yadof.workspace.init import init_workspace


def _workspace(path: Path) -> Path:
    init_workspace(path)
    return path


def _payload(
    value: float, *, size: int = 1, dtype: object = np.float64
) -> dict[str, object]:
    values = (
        np.asarray(value, dtype=dtype)
        if size == 1
        else np.full((size,), value, dtype=dtype)
    )
    return {
        "values": values,
        "metadata": {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": list(values.shape),
            "rawdata_name": "response",
        },
    }


def _result(
    index: int,
    value: float,
    *,
    generation: int = 0,
    size: int = 1,
    dtype: object = np.float64,
) -> JobResult:
    return JobResult(
        job_name=f"candidate_{generation}_{index}",
        job_dir=None,
        status="done",
        unnormalized_variables=(0.0,),
        normalized_variables=(0.5,),
        raw_data_items=(
            NamedRawDataItem(
                "response.npz", _payload(value, size=size, dtype=dtype)
            ),
        ),
        metadata={
            "engine": "fast",
            "run_id": "test-run",
            "optimization_index": 0,
            "generation_index": generation,
            "population_index": index,
        },
    )


def _session(
    root: Path, **overrides: object
) -> tuple[CampaignSession, object]:
    config = load_config(root, overrides=overrides)
    session = CampaignSession(config)
    return session, session.begin_generation(config)


def test_oversized_recording_aborts_before_later_evaluation(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    session, snapshot = _session(
        root,
        HISTORY_MAX_CANDIDATE_BYTES=4096,
        HISTORY_UNPUBLISHED_MAX_BYTES=8192,
    )
    try:
        with pytest.raises(RecordingError, match="HISTORY_MAX_CANDIDATE_BYTES"):
            finalize_result(session, snapshot, _result(0, 0.25))
        assert session.counters()["admitted"] == 0
    finally:
        session.close()
    assert discover_catalog(recorded_data_paths(root)).references == ()


def test_file_and_memory_evidence_finalize_to_equal_costs(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    raw_path = root / "source.npz"
    payload = _payload(0.35)
    np.savez(
        raw_path,
        values=payload["values"],
        metadata=json.dumps(payload["metadata"], sort_keys=True),
    )
    session, snapshot = _session(root)
    try:
        memory = finalize_result(session, snapshot, _result(0, 0.35))
        file_result = replace(
            _result(1, 999.0),
            raw_data_items=(),
            raw_data_paths=(raw_path,),
        )
        file_backed = finalize_result(session, snapshot, file_result)
        assert file_backed.costs == pytest.approx(memory.costs)
    finally:
        session.close()


def test_named_rawdata_and_record_metadata_align_in_live_and_durable_views(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    session, snapshot = _session(root)
    try:
        finalize_result(session, snapshot, _result(0, 0.35))
        session.flush_boundary()
        live_named = session.named_rawdata_samples(status="completed")
        live_metadata = session.record_metadata(status="completed")
        assert live_named[0][0] == "candidate_0_0"
        assert live_named[0][1][0].filename == "response.npz"
        assert live_metadata[0][0] == "candidate_0_0"
        assert live_metadata[0][1]["engine"] == "fast"
    finally:
        session.close()

    named = recorded_api.get_named_rawdata_samples(root, status="completed")
    metadata = recorded_api.get_record_metadata(root, status="completed")
    assert named[0][0] == metadata[0][0] == "candidate_0_0"
    assert named[0][1][0].filename == "response.npz"
    assert metadata[0][1]["engine"] == "fast"
    bundle = recorded_api.get_surrogate_training_data(root)
    assert bundle["rawdata_filenames"] == (("response.npz",),)
    assert bundle["record_metadata"][0]["engine"] == "fast"


def test_duplicate_campaign_candidate_identity_is_fatal(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    session, snapshot = _session(root)
    try:
        assert finalize_result(session, snapshot, _result(0, 0.35)).costs is not None
        with pytest.raises(RecordingError, match="duplicate campaign candidate identity"):
            finalize_result(session, snapshot, _result(0, 0.45))
        session.flush_boundary()
    finally:
        session.close()
    assert len(discover_catalog(recorded_data_paths(root)).references) == 1


def test_segment_count_limit_and_immutable_zip_layout(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    session, snapshot = _session(
        root,
        HISTORY_SEGMENT_MAX_CANDIDATES=2,
        HISTORY_UNPUBLISHED_MAX_CANDIDATES=8,
        HISTORY_SEGMENT_TARGET_BYTES=8 * 1024 * 1024,
        HISTORY_MAX_CANDIDATE_BYTES=8 * 1024 * 1024,
        HISTORY_UNPUBLISHED_MAX_BYTES=32 * 1024 * 1024,
    )
    try:
        for index in range(5):
            assert finalize_result(session, snapshot, _result(index, index + 1)).costs
        session.flush_boundary()
    finally:
        counters = session.close()
    assert counters["published_candidates"] == 5
    assert counters["peak_unpublished_candidates"] <= 8
    assert counters["peak_unpublished_bytes"] <= 32 * 1024 * 1024
    paths = tuple(root.glob("recorded_data/segments/*/*/segment_*.zip"))
    assert len(paths) == 3
    counts = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            counts.append(manifest["candidate_count"])
            assert "format_version" not in manifest
            metadata_member = manifest["candidates"][0]["metadata_member"]
            assert "schema_version" not in json.loads(
                archive.read(metadata_member)
            )
            assert archive.namelist()[-1] == "manifest.json"
    assert sorted(counts) == [1, 2, 2]


def test_metadata_events_have_no_record_layer_version(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    record = recorded_api.record_optimization_metadata(
        root,
        {"record_type": "generation", "generation_index": 0},
    )
    assert "schema_version" not in record
    (event,) = (root / "recorded_data/metadata/generation").glob("event_*.json")
    assert "schema_version" not in json.loads(event.read_text(encoding="utf-8"))


@pytest.mark.parametrize("dtype", [np.float32, np.float64])
def test_large_candidate_above_target_publishes_singleton(
    tmp_path: Path, dtype: object
) -> None:
    root = _workspace(tmp_path / "workspace")
    session, snapshot = _session(
        root,
        HISTORY_SEGMENT_TARGET_BYTES=128 * 1024,
        HISTORY_MAX_CANDIDATE_BYTES=64 * 1024 * 1024,
        HISTORY_UNPUBLISHED_MAX_BYTES=128 * 1024 * 1024,
    )
    try:
        finalized = finalize_result(
            session,
            snapshot,
            _result(0, 0.5, size=10 * 360 * 360, dtype=dtype),
        )
        assert finalized.costs is not None
        session.flush_boundary()
    finally:
        counters = session.close()
    assert counters["published_candidates"] == 1
    (segment,) = root.glob("recorded_data/segments/*/*/segment_*.zip")
    with zipfile.ZipFile(segment) as archive:
        assert json.loads(archive.read("manifest.json"))["candidate_count"] == 1


def test_hot_reload_reinterprets_cost_and_parameter_range(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    task_asset = root / "job_template/task_asset.txt"
    task_asset.write_text("generation zero", encoding="utf-8")
    config = load_config(root)
    session = CampaignSession(config)
    try:
        first = session.begin_generation(config)
        finalized = finalize_result(
            session,
            first,
            replace(
                _result(0, 0.5),
                unnormalized_variables=(0.5,),
                normalized_variables=(0.75,),
            ),
        )
        old_row = session.historical_results(first)[-1]
        assert old_row[2] == finalized.costs

        calc = root / "submit/calc_cost.py"
        calc.write_text(
            calc.read_text(encoding="utf-8").replace(
                "RESPONSE_WORST = 1.0", "RESPONSE_WORST = 10.0"
            ),
            encoding="utf-8",
            newline="\n",
        )
        parameters = root / "job_template/parameters_constraints.py"
        parameters.write_text(
            parameters.read_text(encoding="utf-8").replace(
                "(-1.0, 1.0)", "(-2.0, 2.0)"
            ),
            encoding="utf-8",
            newline="\n",
        )
        task_asset.write_text("generation one", encoding="utf-8")
        assert (first.source_directory / "task_asset.txt").read_text(
            encoding="utf-8"
        ) == "generation zero"
        second = session.begin_generation(load_config(root))
        assert (second.source_directory / "task_asset.txt").read_text(
            encoding="utf-8"
        ) == "generation one"
        new_row = session.historical_results(second)[-1]
        assert second.interpretation_fingerprint != first.interpretation_fingerprint
        assert new_row[1] != old_row[1]
        assert new_row[2] != old_row[2]
    finally:
        session.close()


def test_evaluation_only_reload_reuses_derived_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path / "workspace")
    config = load_config(root)
    session = CampaignSession(config)
    try:
        first = session.begin_generation(config)
        finalize_result(session, first, _result(0, 0.5))
        expected = session.historical_results(first)
        workflow = root / "job_template/workflow.py"
        workflow.write_text(
            workflow.read_text(encoding="utf-8") + "\n# evaluation-only edit\n",
            encoding="utf-8",
            newline="\n",
        )
        second = session.begin_generation(load_config(root))
        assert second.evaluation_fingerprint != first.evaluation_fingerprint
        assert second.interpretation_fingerprint == first.interpretation_fingerprint
        monkeypatch.setattr(
            "yadof.recorded_data.session.job_template_api.calculate_cost",
            lambda *args, **kwargs: pytest.fail("unchanged history was recalculated"),
        )
        assert session.historical_results(second) == expected
    finally:
        session.close()


def test_recorder_config_is_frozen_for_campaign(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    initial = load_config(root)
    session = CampaignSession(initial)
    try:
        session.begin_generation(initial)
        redirected = root / "redirected"
        live = load_config(
            root,
            overrides={
                "RECORDED_DATA_DIR": redirected,
                "HISTORY_SEGMENT_MAX_CANDIDATES": 1,
            },
        )
        second = session.begin_generation(live)
        assert second.config.workspace.recorded_data_dir == initial.workspace.recorded_data_dir
        assert second.config.HISTORY_SEGMENT_MAX_CANDIDATES == 16
    finally:
        session.close()


def test_second_campaign_and_clear_fail_while_lock_is_held(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    session, _snapshot = _session(root)
    try:
        with pytest.raises(CampaignActiveError):
            CampaignSession(load_config(root))
        with pytest.raises(CampaignActiveError):
            clear_history(root, confirm=True)
    finally:
        session.close()
    assert clear_history(root, confirm=True)["workspace"] == str(root.resolve())


def test_unowned_recorded_data_entries_are_ignored_and_left_untouched(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    unowned = root / "recorded_data/user_notes.jsonl"
    unowned.parent.mkdir(parents=True)
    unowned.write_text('{"note":"keep"}\n', encoding="utf-8")
    recorded_api.record_job_result(root, "new", (), (), status="error")
    assert recorded_api.get_job_names(root) == ("new",)
    clear_history(root, confirm=True)
    assert unowned.read_text(encoding="utf-8") == '{"note":"keep"}\n'


def test_bad_candidate_member_does_not_hide_readable_sibling(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    session, snapshot = _session(
        root,
        HISTORY_SEGMENT_MAX_CANDIDATES=2,
        HISTORY_UNPUBLISHED_MAX_CANDIDATES=4,
    )
    try:
        finalize_result(session, snapshot, _result(0, 0.1))
        finalize_result(session, snapshot, _result(1, 0.2))
        session.flush_boundary()
    finally:
        session.close()
    (segment,) = root.glob("recorded_data/segments/*/*/segment_*.zip")
    with zipfile.ZipFile(segment) as archive:
        member = next(name for name in archive.namelist() if name.endswith("response.npz"))
        info = archive.getinfo(member)
    data = bytearray(segment.read_bytes())
    name_length, extra_length = struct.unpack_from("<HH", data, info.header_offset + 26)
    payload_offset = info.header_offset + 30 + name_length + extra_length
    data[payload_offset + max(1, info.compress_size // 2)] ^= 0x01
    segment.write_bytes(data)
    rows = recorded_api.get_historical_results(root)
    assert len(rows) == 1
    assert rows[0][0] == "candidate_0_1"


def test_writer_failure_retries_same_segment_without_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path / "workspace")
    real_publish = session_module.publish_segment
    calls = 0

    def flaky(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected disk failure")
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(session_module, "publish_segment", flaky)
    session, snapshot = _session(
        root,
        HISTORY_SEGMENT_MAX_CANDIDATES=1,
        HISTORY_UNPUBLISHED_MAX_CANDIDATES=4,
    )
    try:
        first = finalize_result(session, snapshot, _result(0, 0.1))
        deadline = time.monotonic() + 5.0
        while session.counters()["write_failed"] < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        second = finalize_result(session, snapshot, _result(1, 0.2))
        session.flush_boundary()
        assert first.costs is not None and second.costs is not None
    finally:
        counters = session.close()
    assert counters["write_failed"] == 1
    assert counters["published_candidates"] == 2


def test_consecutive_writer_failures_abort_before_next_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path / "workspace")

    def failed_publish(*args, **kwargs):
        raise OSError("persistent injected disk failure")

    monkeypatch.setattr(session_module, "publish_segment", failed_publish)
    session, snapshot = _session(
        root,
        HISTORY_SEGMENT_MAX_CANDIDATES=1,
        HISTORY_UNPUBLISHED_MAX_CANDIDATES=4,
        HISTORY_WRITER_MAX_CONSECUTIVE_FAILURES=2,
    )
    assert finalize_result(session, snapshot, _result(0, 0.1)).costs is not None
    with pytest.raises(RecordingError, match="no later evaluation may proceed"):
        session.flush_boundary()
    counters = session.counters()
    assert counters["write_failed"] == 2
    assert counters["fatal_errors"] == 1
    with pytest.raises(RecordingError, match="before all evidence could be published"):
        session.close()


def test_unexpected_writer_death_keeps_campaign_exclusive_until_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path / "workspace")

    def die(_writer):
        raise KeyboardInterrupt("injected writer death")

    monkeypatch.setattr(session_module._BoundedSegmentWriter, "_run", die)
    session, snapshot = _session(root)
    deadline = time.monotonic() + 5.0
    while session._writer._thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not session._writer._thread.is_alive()
    with pytest.raises(RecordingError, match="writer failed"):
        finalize_result(session, snapshot, _result(0, 0.1))
    assert session.counters()["fatal_errors"] == 1
    with pytest.raises(CampaignActiveError):
        CampaignSession(load_config(root))
    with pytest.raises(RecordingError, match="before all evidence could be published"):
        session.close()
    monkeypatch.undo()
    followup = CampaignSession(load_config(root))
    followup.close()


def test_full_unpublished_budget_backpressures_instead_of_dropping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path / "workspace")
    entered = threading.Event()
    release = threading.Event()
    real_publish = session_module.publish_segment

    def blocked(*args, **kwargs):
        entered.set()
        release.wait()
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(session_module, "publish_segment", blocked)
    session, snapshot = _session(
        root,
        HISTORY_SEGMENT_MAX_CANDIDATES=1,
        HISTORY_UNPUBLISHED_MAX_CANDIDATES=1,
    )
    first = finalize_result(session, snapshot, _result(0, 0.1))
    assert first.costs is not None
    assert entered.wait(2.0)
    outcome: list[JobResult] = []
    errors: list[BaseException] = []

    def finalize_second() -> None:
        try:
            outcome.append(finalize_result(session, snapshot, _result(1, 0.2)))
        except BaseException as exc:
            errors.append(exc)

    producer = threading.Thread(target=finalize_second)
    producer.start()
    deadline = time.monotonic() + 2.0
    while (
        session.counters()["backpressure_waits"] < 1
        and time.monotonic() < deadline
    ):
        time.sleep(0.01)
    assert producer.is_alive()
    assert session.counters()["backpressure_waits"] == 1
    release.set()
    producer.join(5.0)
    assert not producer.is_alive()
    assert errors == []
    assert outcome[0].costs is not None
    session.flush_boundary()
    counters = session.close()
    assert counters["published_candidates"] == 2
    assert counters["backpressure_wait_sec"] > 0.0


def test_campaign_locks_are_independent_between_workspaces(tmp_path: Path) -> None:
    first_root = _workspace(tmp_path / "first")
    second_root = _workspace(tmp_path / "second")
    first = CampaignSession(load_config(first_root))
    try:
        second = CampaignSession(load_config(second_root))
        second.close()
    finally:
        first.close()


def test_temporary_and_corrupt_segments_are_tolerated(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    recorded_api.record_job_result(root, "good", (), (), status="error")
    segment_dir = next((root / "recorded_data/segments").glob("*/*"))
    (segment_dir / "segment_999998.zip.tmp").write_bytes(b"partial")
    (segment_dir / "segment_999999.zip").write_bytes(b"not a zip")
    assert recorded_api.get_job_names(root) == ("good",)
    catalog = discover_catalog(recorded_data_paths(root))
    assert any(item["error_type"] == "segment_unreadable" for item in catalog.diagnostics)


def test_historical_rawdata_snapshot_freezes_paths_and_opens_each_segment_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path / "workspace")
    recorded_api.record_job_result(
        root,
        "first",
        (0.0,),
        (NamedRawDataItem("response.npz", _payload(0.1)),),
    )
    snapshot = open_historical_rawdata_snapshot(recorded_data_paths(root))
    recorded_api.record_job_result(
        root,
        "later",
        (0.0,),
        (NamedRawDataItem("response.npz", _payload(0.2)),),
    )

    real_zip = zipfile.ZipFile
    opened: list[Path] = []

    def counted_zip(file, mode="r", *args, **kwargs):
        if mode == "r" and isinstance(file, (str, Path)):
            opened.append(Path(file))
        return real_zip(file, mode, *args, **kwargs)

    monkeypatch.setattr(
        "yadof.recorded_data.segment_store.zipfile.ZipFile", counted_zip
    )
    batches = tuple(snapshot.iter_batches())

    assert len(snapshot.segment_paths) == 1
    assert len(opened) == 1
    assert [
        reference.record["job_name"]
        for batch in batches
        for reference, _items in batch.records
    ] == ["first"]


def test_publication_never_opens_an_older_segment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path / "workspace")
    workspace = load_config(root).workspace
    items = (NamedRawDataItem("response.npz", _payload(0.1)),)
    first_envelope = build_owned_envelope(
        workspace,
        "first",
        (0.0,),
        items,
        {"run_id": "run", "generation_index": 0, "population_index": 0},
    )
    second_envelope = build_owned_envelope(
        workspace,
        "second",
        (0.0,),
        items,
        {"run_id": "run", "generation_index": 0, "population_index": 1},
    )
    storage = recorded_data_paths(root)
    first_path, _references = publish_segment(storage, (first_envelope,), sequence=0)
    real_zip = zipfile.ZipFile

    def guarded_zip(file, mode="r", *args, **kwargs):
        if isinstance(file, (str, Path)) and Path(file) == first_path:
            pytest.fail("new segment publication opened an older segment")
        return real_zip(file, mode, *args, **kwargs)

    monkeypatch.setattr(
        "yadof.recorded_data.segment_store.zipfile.ZipFile", guarded_zip
    )
    publish_segment(storage, (second_envelope,), sequence=1)


def test_shutdown_waits_for_in_flight_publication_and_retains_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from yadof.recorded_data import session as session_module

    root = _workspace(tmp_path / "workspace")
    entered = threading.Event()
    release = threading.Event()
    real_publish = session_module.publish_segment

    def blocked(*args, **kwargs):
        entered.set()
        release.wait(5.0)
        return real_publish(*args, **kwargs)

    monkeypatch.setattr(session_module, "publish_segment", blocked)
    session, snapshot = _session(
        root,
        HISTORY_SEGMENT_MAX_CANDIDATES=1,
    )
    finalize_result(session, snapshot, _result(0, 0.1))
    assert entered.wait(2.0)
    closed: list[dict[str, object]] = []
    errors: list[BaseException] = []

    def close_session() -> None:
        try:
            closed.append(session.close())
        except BaseException as exc:
            errors.append(exc)

    closer = threading.Thread(target=close_session)
    closer.start()
    time.sleep(0.1)
    assert closer.is_alive()
    with pytest.raises(CampaignActiveError):
        CampaignSession(load_config(root))
    release.set()
    closer.join(5.0)
    assert not closer.is_alive()
    assert errors == []
    assert closed[0]["published_candidates"] == 1
    followup = CampaignSession(load_config(root))
    followup.close()


def test_catalog_scale_near_100000_is_linear_and_tolerant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    storage = recorded_data_paths(_workspace(tmp_path / "workspace"))
    paths = tuple(
        storage.segments_directory
        / "run"
        / "generation_000000"
        / f"segment_{index:06d}.zip"
        for index in range(6250)
    )
    original_rglob = Path.rglob

    def fake_rglob(path: Path, pattern: str):
        if path == storage.segments_directory and pattern == "segment_*.zip":
            return iter(paths)
        return original_rglob(path, pattern)

    def fake_scan(path: Path):
        segment_index = int(path.stem.rsplit("_", 1)[1])
        return (
            tuple(
                SegmentReference(
                    candidate_id=f"{segment_index:06d}-{item:02d}",
                    segment_path=path,
                    record={
                        "job_name": f"job_{segment_index:06d}_{item:02d}",
                        "status": "error",
                    },
                    rawdata_members=(),
                )
                for item in range(16)
            ),
            (),
        )

    monkeypatch.setattr(Path, "rglob", fake_rglob)
    monkeypatch.setattr(
        "yadof.recorded_data.segment_store.scan_segment", fake_scan
    )
    started = time.monotonic()
    catalog = discover_catalog(storage)
    elapsed = time.monotonic() - started
    assert len(catalog.references) == 100_000
    assert catalog.diagnostics == ()
    assert elapsed < 30.0


def test_5000_row_startup_does_not_make_finalizer_scan_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path / "workspace")
    storage = recorded_data_paths(root)
    references = tuple(
        SegmentReference(
            candidate_id=f"seed-{index}",
            segment_path=storage.segments_directory / "synthetic.zip",
            record={"job_name": f"seed_{index}", "status": "error"},
            rawdata_members=(),
        )
        for index in range(5000)
    )
    monkeypatch.setattr(
        "yadof.recorded_data.session.catalog_snapshot",
        lambda _storage: CatalogSnapshot(references, (), ()),
    )
    session, snapshot = _session(
        root,
    )
    try:
        started = time.monotonic()
        costs = [
            finalize_result(session, snapshot, _result(index, 0.1)).costs
            for index in range(100)
        ]
        elapsed = time.monotonic() - started
        assert all(cost is not None for cost in costs)
        assert len(session.records()) == 5100
        assert elapsed < 10.0
    finally:
        session.close()
