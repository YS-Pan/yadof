"""Bad individuals cannot prevent training on the remaining complete real evidence."""
from dataclasses import replace
from types import SimpleNamespace
import zipfile

import numpy as np
import pytest

from yadof.config import load_config
from yadof.recorded_data.dataset import (
    CostRow, CostTable, EvidenceDataset, EvidenceRow, EvidenceState,
    InterpretationStatus, RawDataHandle,
)
from yadof.surrogate import (
    SurrogateTrainingData, amplitude_gp, conditional_inr, hierarchical_cae,
    materialize_training_data, pca_svd, retrieval_response,
)
from yadof.workspace.init import init_workspace


def sample(value=1.0, *, count=3, fields=1):
    return {f"response-{field}.npz": {
        "values": np.full(count, value + field, dtype=np.float64),
        "axis": np.arange(count, dtype=np.float64),
        "metadata": {"schema_version": 1, "shape": [count], "axes": [
            {"index": 0, "name": "axis", "size": count, "values_key": "axis"},
        ]},
    } for field in range(fields)}


def views(raw_samples):
    evidence, costs = [], []
    for i, raw in enumerate(raw_samples):
        def load(raw=raw):
            if isinstance(raw, Exception):
                raise raw
            from yadof.job_template.rawdata_contract import NamedRawDataItem
            return tuple(NamedRawDataItem(name, payload) for name, payload in raw.items())
        evidence.append(EvidenceRow(
            row_id=f"row-{i}", evidence_id=f"row-{i}", job_name=f"job-{i}",
            execution_status="completed", evidence_state=EvidenceState.COMMITTED,
            design_key=f"design-{i}", raw_variables=(float(i),),
            record={"generation_index": 0, "population_index": i},
            _rawdata_handle=RawDataHandle(
                tuple(raw) if isinstance(raw, dict) else ("missing.npz",), 0, "fixture", load),
        ))
        costs.append(CostRow(
            interpretation_id=f"interpretation-{i}", row_id=f"row-{i}", evidence_id=f"row-{i}",
            job_name=f"job-{i}", status=InterpretationStatus.SUCCEEDED,
            interpretation_fingerprint="task", objective_schema_id="objectives", objective_width=1,
            normalized_variables=(i / max(1, len(raw_samples) - 1),), costs=(0.5,),
        ))
    return (EvidenceDataset(("input_value",), tuple(evidence)),
            CostTable(("cost",), "objectives", "task", tuple(costs)))


@pytest.mark.parametrize("factory", [conditional_inr, hierarchical_cae, pca_svd, amplitude_gp, retrieval_response])
def test_every_component_skips_nonfinite_and_incomplete_rows(factory, caplog):
    malformed = sample()
    malformed["response-0.npz"]["values"] = np.asarray([1.0])
    dataset, table = views([sample(count=1), sample(1), sample(np.nan), malformed, sample(2), sample(np.inf)])
    data = factory().training_data(dataset, table)
    assert data.row_ids == ("row-1", "row-4")
    assert data.evidence_ids == data.row_ids
    assert data.normalized_variables == ((0.2,), (0.8,))
    assert [row["population_index"] for row in data.record_metadata] == [1, 4]
    assert data.sample_count == 2
    assert "skipped" in caplog.text and "row-2" in caplog.text
    assert all(np.isfinite(item.payload["values"]).all() for row in data.raw_data for item in row.items)


@pytest.mark.parametrize("bad", [FileNotFoundError("missing segment"), zipfile.BadZipFile("corrupt segment"), EOFError("truncated NPZ"), KeyError("missing NPZ member")])
def test_unreadable_individual_is_skipped_without_touching_other_rows(bad):
    dataset, table = views([sample(1), bad, sample(2)])
    original_records = tuple(row.record for row in dataset.rows)
    data = materialize_training_data(dataset, table, row_ids=("row-2", "row-1", "row-0", "row-2"))
    assert data.row_ids == ("row-2", "row-0", "row-2")
    assert data.evidence_ids == data.row_ids
    assert tuple(row.record for row in dataset.rows) == original_records


@pytest.mark.parametrize("bad", [
    sample(np.nan), sample(np.inf), sample(-np.inf), sample(count=0), {},
    {"broken.npz": {"values": np.asarray([1.0])}},
])
def test_direct_training_data_skips_whole_invalid_individual(bad):
    data = SurrogateTrainingData(
        ("input_value",), ((0.0,), (0.5,), (1.0,)),
        (sample(1), bad, sample(2)), row_ids=("good-a", "bad", "good-b"),
        evidence_ids=("evidence-a", "evidence-bad", "evidence-b"),
        record_metadata=({"ordinal": 0}, {"ordinal": 1}, {"ordinal": 2}),
    )
    expected = SurrogateTrainingData(
        ("input_value",), ((0.0,), (1.0,)), (sample(1), sample(2)),
        row_ids=("good-a", "good-b"), evidence_ids=("evidence-a", "evidence-b"),
        record_metadata=({"ordinal": 0}, {"ordinal": 2}),
    )
    assert data.row_ids == expected.row_ids
    assert data.normalized_variables == expected.normalized_variables
    assert data.content_digest == expected.content_digest
    assert data.provenance_digest == expected.provenance_digest


def test_schema_selection_prefers_complete_fields_on_ties_and_preserves_row_order():
    dataset, table = views([sample(fields=1), sample(1, fields=2)])
    data = materialize_training_data(dataset, table)
    assert data.row_ids == ("row-1",)
    dataset, table = views([sample(1), sample(count=1), sample(2)])
    data = materialize_training_data(dataset, table, row_ids=("row-2", "row-1", "row-0"))
    assert data.row_ids == ("row-2", "row-0")


def test_nonfinite_axis_drops_entire_individual():
    bad = sample(1)
    bad["response-0.npz"]["axis"][1] = np.nan
    dataset, table = views([bad, sample(2), sample(3)])
    assert materialize_training_data(dataset, table).row_ids == ("row-1", "row-2")


@pytest.mark.parametrize("factory", [conditional_inr, hierarchical_cae, pca_svd, amplitude_gp, retrieval_response])
def test_no_valid_individuals_produces_empty_data_and_scheduler_skips(tmp_path, factory):
    dataset, table = views([sample(np.nan), FileNotFoundError("missing")])
    data = materialize_training_data(dataset, table)
    assert data.sample_count == 0 and data.raw_data == data.row_ids == ()
    root = tmp_path / "empty"
    init_workspace(root)
    context = SimpleNamespace(config=load_config(root), generation_index=1, session=None, snapshot=None)
    assert factory().start_training(context, data).action == "skipped_no_data"


@pytest.mark.parametrize("factory,module", [
    (conditional_inr, "conditional_inr"), (hierarchical_cae, "hierarchical_cae"),
])
def test_empty_neural_training_cannot_select_old_state_or_publish_empty_checkpoint(factory, module, tmp_path, monkeypatch):
    from importlib import import_module
    from yadof.surrogate import assess_surrogate_selection_freshness
    runtime = import_module(f"yadof.surrogate.{module}.runtime")
    scheduler = import_module(f"yadof.surrogate.{module}.scheduler")
    def unexpected(*args, **kwargs):
        pytest.fail("empty training must not reuse or replace an old learned state")
    monkeypatch.setattr(runtime, "latest_state_generation", unexpected)
    monkeypatch.setattr(runtime, "has_trained_state", unexpected)
    monkeypatch.setattr(scheduler, "start_training", unexpected)
    root = tmp_path / "empty-neural"
    init_workspace(root)
    context = SimpleNamespace(config=load_config(root), generation_index=4)
    empty = SurrogateTrainingData(("input_value",), (), ())
    component = factory()
    assert component.has_trained_state(context, empty) is False
    assert assess_surrogate_selection_freshness(component, context, empty).action == "skipped_no_data"
    assert component.start_training(context, empty).action == "skipped_no_data"


def test_real_fit_and_checkpoint_use_only_valid_individuals(tmp_path):
    dataset, table = views([sample(count=1), sample(1), sample(np.nan), sample(2), sample(3)])
    data = pca_svd().training_data(dataset, table)
    root = tmp_path / "fit"
    init_workspace(root)
    state = pca_svd(rank=1, device="cpu").fit(root, data)
    assert state.sample_count == 3
    assert state.training_row_ids == ("row-1", "row-3", "row-4")
    assert state.training_data_digest == data.content_digest
    assert state.namespace_manifest_path.is_file()


def test_identity_errors_and_unexpected_loader_failures_still_propagate():
    dataset, table = views([sample(1)])
    with pytest.raises(KeyError, match="missing"):
        materialize_training_data(dataset, table, row_ids=("missing",))
    mismatched = replace(table, rows=(replace(table.rows[0], evidence_id="another-evidence"),))
    with pytest.raises(ValueError, match="root identity"):
        materialize_training_data(dataset, mismatched)
    dataset, table = views([RuntimeError("implementation bug")])
    with pytest.raises(RuntimeError, match="implementation bug"):
        materialize_training_data(dataset, table)
