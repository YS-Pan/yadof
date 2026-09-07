"""Acceptance of immutable training ownership and bounded sample sharing."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import gc
import weakref

import numpy as np
import pytest

from yadof.config import load_config
from yadof.job_template import NamedRawDataItem
from yadof.job_template.rawdata_template import RawDataSchemaTemplate, StructuredRawDataSample
from yadof.recorded_data import dataset as dataset_module
from yadof.recorded_data.records import build_owned_envelope
from yadof.recorded_data.segment_store import SegmentReference
from yadof.recorded_data.session import CampaignSession
from yadof.surrogate import SurrogateTrainingData, materialize_training_data
from yadof.workspace.init import init_workspace


def _payload(value, shape=(17,)):
    values = np.full(shape, value, dtype=np.float64)
    payload = {"values": values}
    axes = []
    for index, size in enumerate(shape):
        name = f"axis{index}"
        payload[name] = np.linspace(0, 1, size)
        axes.append({"index": index, "size": size, "name": name, "values_key": name})
    payload["metadata"] = {"schema_version": 1, "shape": list(shape), "axes": axes}
    return payload


@pytest.mark.parametrize("shape", [(), (17,), (2, 3)])
def test_shared_samples_keep_independent_values_and_owned_mutable_exports(shape):
    payload = _payload(0.2, shape)
    # Even a read-only view of mutable caller storage must be isolated.
    caller_values = payload["values"]
    payload["values"] = caller_values.view()
    payload["values"].setflags(write=False)
    sample = StructuredRawDataSample((NamedRawDataItem("response.npz", payload),))
    data = SurrogateTrainingData(("x",), ((0.2,), (0.8,)), (
        sample, {"response.npz": _payload(0.8, shape)}))
    caller_values[...] = 99
    payload["metadata"]["shape"].append(99)
    first, second = (sample.items[0].payload for sample in data.raw_data)
    assert np.all(first["values"] == 0.2)
    assert np.all(second["values"] == 0.8)
    assert not np.shares_memory(first["values"], second["values"])
    for key in first.keys() - {"values"}:
        assert first[key] is second[key]
    for value in (first["values"], *(first[f"axis{i}"] for i in range(len(shape)))):
        with pytest.raises(ValueError):
            value.setflags(write=True)
        with pytest.raises(ValueError):
            value[...] = 5
    with pytest.raises(TypeError):
        first["metadata"]["new"] = 1
    cloned = replace(data, row_ids=("a", "b"))
    assert all(a is b for a, b in zip(cloned.raw_data, data.raw_data, strict=True))
    assert cloned.content_digest == data.content_digest
    exported = data.raw_data[0].as_mapping()["response.npz"]
    exported["values"][...] = 7
    exported["metadata"]["new"] = 1
    assert np.all(first["values"] == 0.2) and "new" not in first["metadata"]


@pytest.mark.parametrize("change", ["axis", "metadata", "dtype", "shape"])
def test_sharing_still_rejects_schema_drift(change):
    schema = RawDataSchemaTemplate.from_items({"response.npz": _payload(0.2)})
    payload = _payload(0.8, (18,) if change == "shape" else (17,))
    if change == "axis":
        payload["axis0"][0] = -1
    elif change == "metadata":
        payload["metadata"]["units"] = "changed"
    elif change == "dtype":
        payload["values"] = payload["values"].astype(np.float32)
    with pytest.raises(ValueError, match="template"):
        schema.validate_sample(StructuredRawDataSample.from_items({"response.npz": payload}))


def test_cache_shares_concurrent_reads_invalidates_files_and_releases_unused_history(tmp_path, monkeypatch):
    segment = tmp_path / "segment.zip"
    segment.write_bytes(b"first")
    reference = SegmentReference("row-1", segment, {}, (("response.npz", "row-1/response.npz", 1),))
    calls = []

    def decode(selected):
        calls.append(selected.candidate_id)
        return (NamedRawDataItem("response.npz", _payload(len(calls))),)

    monkeypatch.setattr(dataset_module, "load_reference_rawdata", decode)
    cache = dataset_module._RawDataSampleCache()
    with ThreadPoolExecutor(max_workers=4) as pool:
        samples = list(pool.map(lambda _: cache.load(reference), range(8)))
    assert calls == ["row-1"] and all(s is samples[0] for s in samples)
    sample_ref = weakref.ref(samples[0])
    schema_ref = weakref.ref(RawDataSchemaTemplate.from_items(samples[0]))
    # A different durable identity is separate even with identical variable values.
    other = cache.load(replace(reference, candidate_id="row-2"))
    assert calls == ["row-1", "row-2"] and other is not samples[0]
    assert other.items[0].payload["axis0"] is samples[0].items[0].payload["axis0"]
    segment.write_bytes(b"replaced with different contents")
    changed = cache.load(reference)
    assert changed is not samples[0] and calls == ["row-1", "row-2", "row-1"]
    segment.unlink()
    with pytest.raises(FileNotFoundError):
        cache.load(reference)
    del samples, other, changed
    gc.collect()
    assert sample_ref() is None and schema_ref() is None
    assert not cache._samples and not cache._schemas


@pytest.mark.parametrize("mode", ["fast", "local", "distributed"])
def test_campaign_training_reuses_old_rows_adds_new_rows_and_reinterprets_current_task(tmp_path, monkeypatch, mode):
    root = tmp_path / "workspace"
    init_workspace(root)
    (root / "config.py").write_text(f'EVALUATION_MODE = "{mode}"\n', encoding="utf-8")
    cost_path = root / "submit/calc_cost.py"
    cost_source = (
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    return (float(sample_rawdata[0]['values'].mean()),)\n"
        "def get_objective_names():\n    return ('response',)\n"
        "def get_objective_count():\n    return 1\n"
    )
    cost_path.write_text(cost_source, encoding="utf-8")
    calls = []
    original = dataset_module.load_reference_rawdata

    def decode(reference):
        calls.append(reference.candidate_id)
        return original(reference)

    monkeypatch.setattr(dataset_module, "load_reference_rawdata", decode)
    with CampaignSession(load_config(root)) as session:
        for generation in range(2):
            snapshot = session.begin_generation(load_config(root))
            envelope = build_owned_envelope(snapshot.config.workspace, f"row-{generation}",
                (0.2,), (NamedRawDataItem("response.npz", _payload(0.2 + generation * 0.1)),),
                {"run_id": "sharing", "optimization_index": 0,
                 "generation_index": generation, "population_index": 0})
            receipt = session.submit_evidence(envelope, group_id=f"sharing:{generation}")
            session.flush_boundary()
            receipt.wait_committed(timeout=5)
            table = session.cost_table(snapshot)
            dataset = session.evidence_dataset()
            before = len(calls)
            current = materialize_training_data(dataset, table)
            assert len(calls) == before + 1
            if generation:
                assert current.raw_data[0] is previous.raw_data[0]
            previous = current
        exported = dataset.rows[0].load_rawdata()
        exported[0].payload["values"][...] = 55
        assert np.all(current.raw_data[0].items[0].payload["values"] == 0.2)
        cost_path.write_text(cost_source.replace(".mean())", ".mean()) + 0.1"), encoding="utf-8")
        parameters = root / "job_template/parameters_constraints.py"
        parameters.write_text(parameters.read_text(encoding="utf-8").replace(
            "((-1.0, 1.0),)", "((-2.0, 2.0),)"), encoding="utf-8")
        snapshot = session.begin_generation(load_config(root))
        table = session.cost_table(snapshot)
        before = len(calls)
        updated = materialize_training_data(session.evidence_dataset(), table)
        assert len(calls) == before
        assert updated.raw_data[0] is current.raw_data[0]
        assert updated.normalized_variables[0][0] == pytest.approx(0.55)
        assert table.rows[0].costs == pytest.approx((0.3,))
        assert not updated.normalized_variables == current.normalized_variables
    assert not session._rawdata_sample_cache._samples
    assert np.all(updated.raw_data[0].items[0].payload["values"] == 0.2)
