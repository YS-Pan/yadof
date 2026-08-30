from __future__ import annotations

import gc
import hashlib
import json
import math
from pathlib import Path
import weakref
import zipfile

import numpy as np
import pytest

from yadof.config import load_config
from yadof.job_template import RAWDATA_SCHEMA_VERSION, NamedRawDataItem
from yadof.optimize.strategy import history_records
from yadof.recorded_data import (
    EvidenceDataset,
    EvidenceRow,
    EvidenceState,
    InterpretationStatus,
    calculate_cost_table,
    calculate_costs,
    derive_evidence_row,
    get_evidence_dataset,
    get_historical_results,
    get_surrogate_training_data,
    record_job_result,
    record_job_results,
)
from yadof.recorded_data import dataset as dataset_module
from yadof.recorded_data.records import build_owned_envelope
from yadof.recorded_data.session import CampaignSession
from yadof.task_snapshot import create_generation_snapshot
from yadof.workspace.init import init_workspace


def _workspace(path: Path) -> Path:
    init_workspace(path)
    _write_cost(path, ("return (value,)",))
    return path


def _payload(value: float) -> dict[str, object]:
    values = np.asarray(value, dtype=np.float64)
    return {
        "values": values,
        "metadata": {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": list(values.shape),
            "rawdata_name": "response",
        },
    }


def _rawdata(value: float) -> tuple[NamedRawDataItem, ...]:
    return (NamedRawDataItem("response.npz", _payload(value)),)


def _write_cost(
    root: Path,
    body: tuple[str, ...],
    *,
    objective_names: tuple[str, ...] = ("response",),
) -> None:
    indented = "\n".join(f"    {line}" for line in body)
    (root / "submit/calc_cost.py").write_text(
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    value = float(sample_rawdata[0]['values'].item())\n"
        f"{indented}\n"
        "def get_objective_names():\n"
        f"    return {objective_names!r}\n"
        "def get_objective_count():\n"
        f"    return {len(objective_names)}\n",
        encoding="utf-8",
        newline="\n",
    )


def _record(root: Path, index: int, design: float, response: float) -> None:
    record_job_result(
        root,
        f"candidate_{index}",
        (design,),
        _rawdata(response),
        {
            "run_id": "stage2-test",
            "optimization_index": 0,
            "generation_index": 0,
            "population_index": index,
        },
    )


def _snapshot(root: Path):
    return create_generation_snapshot(load_config(root))


def test_identity_view_operations_lazy_decode_and_cost_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _workspace(tmp_path / "workspace")
    _record(root, 0, 0.25, 0.2)
    _record(root, 1, 0.25, 0.8)

    calls = 0
    active: list[weakref.ReferenceType[np.ndarray]] = []
    peak_active = 0
    real_load = dataset_module.load_reference_rawdata

    def observed_load(reference):
        nonlocal calls, peak_active
        gc.collect()
        active[:] = [item for item in active if item() is not None]
        items = real_load(reference)
        active.append(weakref.ref(items[0].payload["values"]))
        peak_active = max(peak_active, len(active))
        calls += 1
        return items

    monkeypatch.setattr(dataset_module, "load_reference_rawdata", observed_load)
    dataset = get_evidence_dataset(root)
    assert len(dataset) == 2
    assert dataset.rows[0].evidence_id != dataset.rows[1].evidence_id
    assert dataset.rows[0].row_id == dataset.rows[0].candidate_id
    assert dataset.rows[0].design_key == dataset.rows[1].design_key
    assert dataset.rows[0].is_durable

    copied = dataset.copy()
    filtered = copied.where(lambda row: row.job_name == "candidate_1")
    reversed_dataset = dataset.select(tuple(row.row_id for row in reversed(dataset.rows)))
    assert calls == 0
    assert filtered.rows == (dataset.rows[1],)
    assert reversed_dataset.rows == tuple(reversed(dataset.rows))
    with pytest.raises(TypeError):
        dataset.rows[0].record["new"] = "forbidden"  # type: ignore[index]

    snapshot = _snapshot(root)
    try:
        table = calculate_cost_table(reversed_dataset, snapshot)
    finally:
        snapshot.close()
    assert calls == 2
    assert peak_active <= 1
    assert table.valid_mask == (True, True)
    scrambled = table.select(tuple(row.row_id for row in reversed(table.rows)))
    joined = dataset.join_costs(scrambled)
    assert [item.evidence.job_name for item in joined] == [
        "candidate_0",
        "candidate_1",
    ]
    assert [item.cost.costs for item in joined] == [(0.2,), (0.8,)]

    history = history_records(root)
    assert [row.job_name for row in history] == ["candidate_0", "candidate_1"]
    assert all(row.candidate_id and row.row_id for row in history)
    assert [row.costs for row in history] == [(0.2,), (0.8,)]


def test_derived_lineage_is_deterministic_and_never_enters_recorder(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    _record(root, 0, 0.1, 0.25)
    dataset = get_evidence_dataset(root)
    parent = dataset.rows[0]
    segment_before = tuple(root.glob("recorded_data/segments/**/*.zip"))

    first = derive_evidence_row(
        parent,
        operation="scale-response",
        ordinal=0,
        rawdata_source=_rawdata(0.5),
        parameters={"factor": 2.0},
    )
    repeated = derive_evidence_row(
        parent,
        operation="scale-response",
        ordinal=0,
        rawdata_source=_rawdata(0.5),
        parameters={"factor": 2.0},
    )
    next_ordinal = derive_evidence_row(
        parent,
        operation="scale-response",
        ordinal=1,
        rawdata_source=_rawdata(0.5),
        parameters={"factor": 2.0},
    )
    changed_content = derive_evidence_row(
        parent,
        operation="scale-response",
        ordinal=0,
        rawdata_source=_rawdata(0.75),
        parameters={"factor": 2.0},
    )

    assert first.row_id == repeated.row_id
    assert first.row_id != next_ordinal.row_id
    assert first.row_id != changed_content.row_id
    assert first.evidence_id == parent.evidence_id
    assert first.parent_row_id == parent.row_id
    assert first.evidence_state == EvidenceState.DERIVED
    assert first.lineage[-1].ordinal == 0
    assert first.lineage[-1].parameters["factor"] == 2.0

    transformed = EvidenceDataset(dataset.parameter_names, (first,), source="derived")
    snapshot = _snapshot(root)
    try:
        table = calculate_cost_table(transformed, snapshot)
    finally:
        snapshot.close()
    assert table.rows[0].status == InterpretationStatus.SUCCEEDED
    assert table.rows[0].costs == (0.5,)
    assert table.rows[0].interpretation_id != first.row_id
    assert tuple(root.glob("recorded_data/segments/**/*.zip")) == segment_before
    assert get_evidence_dataset(root).rows == dataset.rows


@pytest.mark.parametrize(
    ("body", "error_type"),
    [
        (("raise RuntimeError('broken cost')",), "RuntimeError"),
        (("return (value, value)",), "CostObjectiveWidthError"),
        (("return (float('nan'),)",), "CostNonFiniteError"),
        (("return (float('inf'),)",), "CostNonFiniteError"),
        (("return (float('-inf'),)",), "CostNonFiniteError"),
    ],
)
def test_cost_failures_remain_typed_until_optimizer_boundary(
    tmp_path: Path,
    body: tuple[str, ...],
    error_type: str,
) -> None:
    root = _workspace(tmp_path / "workspace")
    _write_cost(root, body)
    _record(root, 0, 0.0, 0.25)
    dataset = get_evidence_dataset(root)
    snapshot = _snapshot(root)
    try:
        table = calculate_cost_table(dataset, snapshot)
    finally:
        snapshot.close()

    (row,) = table.rows
    assert row.status == InterpretationStatus.FAILED
    assert row.costs is None
    assert table.valid_mask == (False,)
    assert row.diagnostics["stage"] == "cost_interpretation"
    assert row.diagnostics["error_type"] == error_type
    ((adapter_value,),) = table.to_optimizer_costs()
    assert math.isinf(adapter_value) and adapter_value > 0.0
    assert get_evidence_dataset(root).rows == dataset.rows


def test_execution_and_missing_rawdata_have_distinct_statuses(tmp_path: Path) -> None:
    root = _workspace(tmp_path / "workspace")
    record_job_result(
        root,
        "execution_failed",
        (0.0,),
        (),
        {"population_index": 0},
        status="error",
    )
    durable = get_evidence_dataset(root)
    parameter_name = durable.parameter_names[0]
    missing_id = "a" * 64
    missing = EvidenceRow(
        row_id=missing_id,
        evidence_id=missing_id,
        job_name="missing_rawdata",
        execution_status="completed",
        evidence_state=EvidenceState.COMMITTED,
        design_key=None,
        raw_variables=(0.0,),
        record={
            "candidate_id": missing_id,
            "job_name": "missing_rawdata",
            "status": "completed",
            "raw_variables": {parameter_name: 0.0},
            "rawdata_files": [],
        },
    )
    dataset = EvidenceDataset(
        durable.parameter_names,
        (durable.rows[0], missing),
        source="test-missing",
    )
    snapshot = _snapshot(root)
    try:
        table = calculate_cost_table(dataset, snapshot)
    finally:
        snapshot.close()
    assert table.statuses == (
        InterpretationStatus.NOT_APPLICABLE,
        InterpretationStatus.MISSING,
    )
    assert all(row.costs is None for row in table.rows)
    assert all(math.isinf(row[0]) for row in table.to_optimizer_costs())


def test_live_pending_visibility_commit_equivalence_and_new_session_recovery(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    config = load_config(root)
    session = CampaignSession(config)
    snapshot = session.begin_generation(config)
    envelope = build_owned_envelope(
        snapshot.config.workspace,
        "live_candidate",
        (0.2,),
        _rawdata(0.4),
        {
            "run_id": "stage2-live",
            "optimization_index": 0,
            "generation_index": 0,
            "population_index": 0,
        },
    )
    try:
        receipt = session.submit_evidence(envelope, group_id="stage2-live:0")
        pending = session.evidence_dataset()
        assert pending.rows[0].evidence_state == EvidenceState.PENDING
        assert not pending.rows[0].has_rawdata
        assert get_evidence_dataset(root).rows == ()
        pending_table = calculate_cost_table(pending, snapshot)
        assert pending_table.statuses == (InterpretationStatus.MISSING,)

        session.flush_boundary()
        receipt.wait_committed(timeout=5.0)
        committed_live = session.evidence_dataset()
        durable = get_evidence_dataset(root)
        assert committed_live.rows == durable.rows
        assert committed_live.rows[0].evidence_state == EvidenceState.COMMITTED
        assert committed_live.rows[0].has_rawdata
        assert session.cost_table(snapshot).statuses == (
            InterpretationStatus.SUCCEEDED,
        )
    finally:
        session.close()

    recovered = CampaignSession(load_config(root))
    try:
        assert recovered.evidence_dataset().rows == durable.rows
    finally:
        recovered.close()


def test_task_hot_reload_creates_new_interpretation_without_touching_evidence(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    _record(root, 0, 0.0, 0.25)
    dataset = get_evidence_dataset(root)
    segment = next(root.glob("recorded_data/segments/**/*.zip"))
    segment_digest = hashlib.sha256(segment.read_bytes()).hexdigest()

    first_snapshot = _snapshot(root)
    try:
        first = calculate_cost_table(dataset, first_snapshot)
    finally:
        first_snapshot.close()
    _write_cost(root, ("return (value + 10.0,)",))
    second_snapshot = _snapshot(root)
    try:
        second = calculate_cost_table(dataset, second_snapshot)
    finally:
        second_snapshot.close()

    assert first.rows[0].costs == (0.25,)
    assert second.rows[0].costs == (10.25,)
    assert first.interpretation_fingerprint != second.interpretation_fingerprint
    assert first.rows[0].interpretation_id != second.rows[0].interpretation_id
    assert get_evidence_dataset(root).rows == dataset.rows
    assert hashlib.sha256(segment.read_bytes()).hexdigest() == segment_digest


def test_corrupt_candidate_and_segment_are_isolated_with_diagnostics(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    requests = tuple(
        (
            f"candidate_{index}",
            (float(index),),
            _rawdata(0.1 + index),
            {
                "run_id": "stage2-corrupt",
                "generation_index": 0,
                "population_index": index,
            },
            "completed",
        )
        for index in range(2)
    )
    record_job_results(root, requests)
    segment = next(root.glob("recorded_data/segments/**/*.zip"))
    with zipfile.ZipFile(segment, "r") as source:
        entries = {name: source.read(name) for name in source.namelist()}
    manifest = json.loads(entries["manifest.json"])
    broken_member = manifest["candidates"][0]["metadata_member"]
    broken_record = json.loads(entries[broken_member])
    broken_record["candidate_id"] = "wrong-candidate-id"
    entries[broken_member] = json.dumps(broken_record).encode("utf-8")
    replacement = segment.with_suffix(".replacement")
    with zipfile.ZipFile(replacement, "w") as destination:
        for name, payload in entries.items():
            destination.writestr(name, payload)
    segment.unlink()
    replacement.replace(segment)
    (segment.parent / "segment_999999.zip").write_bytes(b"not-a-zip")

    dataset = get_evidence_dataset(root)
    assert len(dataset.rows) == 1
    error_types = {str(item["error_type"]) for item in dataset.diagnostics}
    assert "candidate_unreadable" in error_types
    assert "segment_unreadable" in error_types
    snapshot = _snapshot(root)
    try:
        table = calculate_cost_table(dataset, snapshot)
    finally:
        snapshot.close()
    assert table.valid_mask == (True,)


def test_multiobjective_compatibility_queries_and_surrogate_adapter_use_identity(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "workspace")
    _write_cost(
        root,
        ("return (value, 1.0 - value)",),
        objective_names=("response", "complement"),
    )
    _record(root, 0, -0.25, 0.2)
    _record(root, 1, 0.25, 0.8)

    dataset = get_evidence_dataset(root)
    snapshot = _snapshot(root)
    try:
        table = calculate_cost_table(dataset, snapshot)
    finally:
        snapshot.close()
    assert table.objective_names == ("response", "complement")
    assert table.objective_width == 2
    assert np.allclose(
        np.asarray([row.costs for row in table.rows]),
        np.asarray(((0.2, 0.8), (0.8, 0.2))),
    )
    assert np.allclose(
        np.asarray(table.to_optimizer_costs()),
        np.asarray(((0.2, 0.8), (0.8, 0.2))),
    )

    historical = get_historical_results(root)
    costs = calculate_costs(root)
    training = get_surrogate_training_data(root)
    assert [row[0] for row in historical] == ["candidate_0", "candidate_1"]
    assert np.allclose(
        np.asarray([row[2] for row in historical]),
        np.asarray(((0.2, 0.8), (0.8, 0.2))),
    )
    assert [row[0] for row in costs] == ["candidate_0", "candidate_1"]
    assert np.allclose(
        np.asarray([row[1] for row in costs]),
        np.asarray(((0.2, 0.8), (0.8, 0.2))),
    )
    assert training["job_names"] == ("candidate_0", "candidate_1")
    assert training["normalized_variables"] == tuple(row[1] for row in historical)
    assert tuple(item[0]["values"].item() for item in training["raw_data"]) == (
        0.2,
        0.8,
    )
    history = history_records(root)
    assert [row.candidate_id for row in history] == [
        row.evidence_id for row in dataset.rows
    ]
    assert [row.interpretation_id for row in history] == [
        row.interpretation_id for row in table.rows
    ]
