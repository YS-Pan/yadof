"""Behavioral acceptance of the installed amplitude/shape GP component."""

from dataclasses import replace
import hashlib
import json
import subprocess
import sys
import threading
from types import SimpleNamespace

import numpy as np
import pytest

from yadof.config import load_config
from yadof.job_template import NamedRawDataItem
from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.recorded_data import calculate_cost_table, get_evidence_dataset, list_records, record_job_result
from yadof.surrogate import (
    AmplitudeGPComponent, AmplitudeGPState, DeterministicSurrogateComponent, SurrogateTrainingData,
    TrainingCancelledError, TrainingHandleState, amplitude_gp, assess_surrogate_selection_freshness,
)
from yadof.surrogate.amplitude_gp import checkpoints, runtime, scheduler
from yadof.task_snapshot import create_generation_snapshot
from yadof.workspace.init import init_workspace


def _payload(values):
    values = np.asarray(values, dtype=np.float64)
    payload = {"values": values}
    axes = []
    for index, size in enumerate(values.shape):
        name = f"axis{index}"
        payload[name] = np.linspace(0.0, 1.0, size)
        axes.append({"index": index, "size": size, "name": name, "values_key": name})
    payload["metadata"] = {"schema_version": 1, "shape": list(values.shape), "axes": axes}
    return payload


def _sample(x):
    phase = np.linspace(0, 1, 17)
    curve = (2 + x) + (1 + x**2) * np.sin(phase * (3 + x))
    volume = x + np.cos(np.arange(24).reshape(2, 3, 4) * (0.1 + x))
    return StructuredRawDataSample.from_items((
        NamedRawDataItem("response.npz", _payload(curve)),
        NamedRawDataItem("volume.npz", _payload(volume)),
        NamedRawDataItem("scalar.npz", _payload(4 + x)),
        NamedRawDataItem("constant.npz", _payload(np.full(7, 2.0))),
    ))


def _data(count=12):
    values = np.linspace(0, 1, count)
    return SurrogateTrainingData(
        parameter_names=("input_value",), normalized_variables=tuple((float(v),) for v in values),
        raw_data=tuple(_sample(v) for v in values), row_ids=tuple(f"row-{i}" for i in range(count)),
        record_metadata=tuple({"generation_index": i // 4, "population_index": i % 4} for i in range(count)),
    )


def _cost_file(root, shift=0):
    (root / "submit/calc_cost.py").write_text(
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        f"    return ({shift!r} + float(sample_rawdata[1]['values'].min()),)\n"
        "def get_objective_names():\n    return ('minimum',)\n"
        "def get_objective_count():\n    return 1\n", encoding="utf-8")


@pytest.fixture
def workspace(tmp_path):
    root = tmp_path / "workspace"
    init_workspace(root)
    (root / "config.py").write_text('EVALUATION_MODE = "local"\n', encoding="utf-8")
    _cost_file(root)
    yield root
    scheduler.deactivate_workspace(root)


@pytest.fixture
def component():
    return amplitude_gp(minimum_training_samples=2, gp_max_rows=8, shape_rank=3, optimizer_iterations=8)


def _context(root, snapshot, generation=3):
    return SimpleNamespace(config=load_config(root), snapshot=snapshot, generation_index=generation, session=None)


def test_public_component_defaults_identity_and_lazy_backends():
    selected = amplitude_gp()
    assert isinstance(selected, AmplitudeGPComponent)
    assert isinstance(selected, DeterministicSurrogateComponent)
    assert selected.settings.shape_rank == 16 and selected.settings.gp_max_rows == 512
    assert selected.settings.optimizer_iterations == 60 and selected.settings.random_seed == 20260905
    assert not hasattr(selected, "estimate_initial_error")
    assert not hasattr(selected, "make_rawdata_sampler")
    assert selected.semantic_identity(None, None) != amplitude_gp(shape_rank=2).semantic_identity(None, None)
    result = subprocess.run([sys.executable, "-c",
        "import sys; from yadof.surrogate import amplitude_gp; amplitude_gp(); "
        "assert 'sklearn' not in sys.modules and 'torch' not in sys.modules; "
        "import yadof.surrogate.amplitude_gp.runtime; "
        "from yadof.surrogate import amplitude_gp; assert callable(amplitude_gp)"],
        capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("kwargs", [
    {"gp_max_rows": 1}, {"shape_rank": True}, {"minimum_training_samples": 1},
    {"random_seed": -1}, {"random_seed": 2**32}, {"optimizer_iterations": 1.2},
    {"elite_fraction": 0}, {"elite_fraction": 1}, {"matern_nu": True},
    {"length_scale_bounds": (0, 1)}, {"noise_level": float("nan")},
    {"kernel_amplitude_bounds": (2, 3)}, {"constant_tolerance": -1},
])
def test_invalid_settings_fail_before_training(kwargs):
    with pytest.raises(ValueError):
        amplitude_gp(**kwargs)


def test_fit_full_rawdata_checkpoint_and_current_cost_roundtrip(workspace, component):
    data = _data()
    state = component.fit(workspace, data, generation_index=3)
    assert isinstance(state, AmplitudeGPState)
    assert state.train_history["gp_fit_rows"] == 8
    assert len(state.train_history["gp_row_ids"]) == 8
    before_records = list_records(workspace)
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        expected = component.predict(state, ((0.13,), (0.81,)), snapshot=snapshot)
        assert expected.valid_mask == (True, True)
        for sample in expected.raw_data:
            assert sample.field_selectors == data.raw_data[0].field_selectors
            assert sample.as_mapping()["volume.npz"]["values"].shape == (2, 3, 4)
            for before, after in zip(data.raw_data[0].items, sample.items, strict=True):
                assert set(before.payload) == set(after.payload)
                assert after.payload["values"].dtype == before.payload["values"].dtype
            assert np.array_equal(sample.as_mapping()["constant.npz"]["values"], np.full(7, 2.0))
        assert expected.costs[0][0] == expected.raw_data[0].as_mapping()["response.npz"]["values"].min()
        runtime.reset_workspace_state(workspace)
        recovered = component.recover(workspace, data, snapshot=snapshot)
        assert recovered is not None and recovered.state_signature == state.state_signature
        actual = component.predict(recovered, expected.normalized_variables, snapshot=snapshot)
        assert actual.costs == expected.costs
        for a, b in zip(actual.raw_data, expected.raw_data, strict=True):
            for fa, fb in zip(a.items, b.items, strict=True):
                assert np.array_equal(fa.payload["values"], fb.payload["values"])
        assert component.predict(state, (), snapshot=snapshot).costs == ()
        with pytest.raises(ValueError, match="normalized"):
            component.predict(state, ((1.1,),), snapshot=snapshot)
    finally:
        snapshot.close()
    assert list_records(workspace) == before_records
    with np.load(state.artifact_dir / "model.npz", allow_pickle=False) as arrays:
        assert arrays.files and all(arrays[name].dtype.kind == "f" for name in arrays.files)


def test_cost_update_reprojects_explicit_state_but_requires_refit_for_selection(workspace, component):
    data = _data()
    old_snapshot = create_generation_snapshot(load_config(workspace))
    try:
        state = component.fit(workspace, data, snapshot=old_snapshot)
        old = component.predict(state, ((0.31,),), snapshot=old_snapshot)
        _cost_file(workspace, shift=40)
        new_snapshot = create_generation_snapshot(load_config(workspace))
        try:
            new = component.predict(state, ((0.31,),), snapshot=new_snapshot)
            assert new.costs[0][0] == pytest.approx(old.costs[0][0] + 40)
            assert old.interpretation_fingerprint != new.interpretation_fingerprint
            assert component.recover(workspace, data, snapshot=new_snapshot) is None
            assert not component.has_trained_state(_context(workspace, new_snapshot), data)
            # The retained snapshot keeps its original interpretation.
            assert component.predict(state, ((0.31,),), snapshot=old_snapshot).costs == old.costs
        finally:
            new_snapshot.close()
    finally:
        old_snapshot.close()


def test_exact_and_lagged_recovery_check_owned_rows_settings_and_parameters(workspace, component):
    data = _data()
    prefix = runtime.training_subset(data, data.row_ids[:8])
    component.fit(workspace, prefix, generation_index=2)
    runtime.reset_workspace_state(workspace)
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        context = _context(workspace, snapshot)
        assert component.recover(workspace, data, snapshot=snapshot) is None
        assert component.latest_trained_generation(context, data) == 2
        assert assess_surrogate_selection_freshness(component, context, data).ready
        changed = replace(data, raw_data=(_sample(0.02),) + data.raw_data[1:])
        assert component.latest_trained_generation(context, changed) is None
        other = amplitude_gp(minimum_training_samples=2, gp_max_rows=8, shape_rank=2, optimizer_iterations=8)
        assert other.recover(workspace, prefix, snapshot=snapshot) is None
    finally:
        snapshot.close()


@pytest.mark.parametrize("damage", ["bytes", "path", "settings", "shape"])
def test_corrupt_or_incompatible_artifacts_are_not_recovered(workspace, component, damage):
    data = _data()
    state = component.fit(workspace, data)
    manifest = json.loads(state.namespace_manifest_path.read_text(encoding="utf-8"))
    artifact = state.artifact_dir / "model.npz"
    if damage == "bytes":
        artifact.write_bytes(b"incomplete")
    elif damage == "path":
        manifest["artifact_dir"] = "../outside"
    elif damage == "settings":
        manifest["identity"]["settings"]["shape_rank"] += 1
        manifest["state_signature"] = checkpoints.hash_json(manifest["identity"])
    elif damage == "shape":
        with np.load(artifact, allow_pickle=False) as arrays:
            values = {name: arrays[name] for name in arrays.files}
        key = next(name for name in values if name.endswith("_x"))
        values[key] = values[key][:-1]
        np.savez_compressed(artifact, **values)
        manifest["artifact_sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    state.namespace_manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    runtime.reset_workspace_state(workspace)
    assert component.recover(workspace, data) is None


def test_scheduler_waits_once_cancels_without_publication_and_releases_snapshot(workspace, component, monkeypatch):
    from yadof.surrogate.amplitude_gp import model

    entered, release = threading.Event(), threading.Event()
    original = model.fit_amplitude_model

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(model, "fit_amplitude_model", blocked)
    owned_snapshots = []
    original_snapshot = runtime.create_generation_snapshot

    def capture(config):
        snapshot = original_snapshot(config)
        owned_snapshots.append(snapshot)
        return snapshot

    monkeypatch.setattr(runtime, "create_generation_snapshot", capture)
    handle = component.start_fit(workspace, _data())
    try:
        assert entered.wait(10)
        with pytest.raises(TimeoutError):
            handle.wait(timeout=0.01)
        assert handle.cancel()
        release.set()
        with pytest.raises(TrainingCancelledError):
            handle.wait()
    finally:
        release.set()
        handle.close()
    assert handle.terminal_state == TrainingHandleState.CANCELLED and not handle.owner_alive
    assert not owned_snapshots[0].snapshot_root.exists()
    assert component.recover(workspace, _data()) is None
    root = load_config(workspace).workspace.surrogate_checkpoint_dir
    assert not tuple(root.glob("runs/*/components/amplitude-gp/generation_*.json"))


def test_scheduler_success_and_failure_release_workers(workspace, component, monkeypatch):
    from yadof.surrogate.amplitude_gp import model

    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        context = _context(workspace, snapshot)
        data = _data()
        assert component.start_training(context, data).action == "started"
        assert component.start_training(context, data).action == "already_running"
        assert component.finish_training(context).action == "completed"
        assert component.finish_training(context).action == "idle"
        assert component.ensure_fresh_enough(context, data).action == "fresh"
        def fail(*args, **kwargs):
            raise RuntimeError("training failure")
        monkeypatch.setattr(model, "fit_amplitude_model", fail)
        assert component.start_training(context, data).action == "started"
        result = component.finish_training(context)
        assert result.action == "failed" and "training failure" in result.error
        assert component.finish_training(context).action == "idle"
        assert scheduler.deactivate_workspace(workspace).action == "deactivated"
    finally:
        snapshot.close()


def test_deactivation_drains_owned_fit_after_live_config_becomes_invalid(workspace, component):
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        context = _context(workspace, snapshot)
        assert component.start_training(context, _data()).action == "started"
        (workspace / "config.py").write_text("this is invalid Python\n", encoding="utf-8")
        assert component.finish_training(context).action == "completed"
        assert scheduler.deactivate_workspace(workspace).action == "deactivated"
        assert not [key for key in runtime._STATES if key[0] == str(workspace.resolve())]
    finally:
        snapshot.close()


def test_numeric_failure_has_no_rawdata_and_positive_infinity_cost(workspace, component):
    data = _data()
    state = component.fit(workspace, data)
    state.model.fields[0].low_scale = np.finfo(float).max
    state.model.fields[0].minimum.constant = np.array([1000.0])
    state.model.fields[0].minimum.model = None
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        predicted = component.predict(state, ((0.3,),), snapshot=snapshot)
        assert predicted.valid_mask == (False,) and predicted.raw_data == (None,)
        assert predicted.costs == ((float("inf"),),)
    finally:
        snapshot.close()


def test_parameter_definition_change_rejects_state_and_prediction(workspace, component):
    data = _data()
    state = component.fit(workspace, data)
    path = workspace / "job_template/parameters_constraints.py"
    source = path.read_text(encoding="utf-8")
    assert "((-1.0, 1.0),)" in source
    path.write_text(source.replace("((-1.0, 1.0),)", "((-2.0, 2.0),)"), encoding="utf-8")
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        assert component.recover(workspace, data, snapshot=snapshot) is None
        with pytest.raises(ValueError, match="parameter definition"):
            component.predict(state, ((0.3,),), snapshot=snapshot)
    finally:
        snapshot.close()


def test_campaign_checkpoint_recovers_exact_physical_rows_after_normalization_roundtrip(workspace, component):
    config = load_config(workspace)
    hashes = {"submit/optimization.py": hashlib.sha256((workspace / "submit/optimization.py").read_bytes()).hexdigest()}
    fingerprint = checkpoints.hash_json({"api": "yadof.optimize.program/v1", "sources": hashes})
    campaign = create_generation_snapshot(config, program_source_hashes=hashes, program_fingerprint=fingerprint)
    plain = create_generation_snapshot(config)
    try:
        data = _data()
        records = tuple({**record, "raw_variables": {"input_value":
            job_template_api.denormalize_variables(campaign.config.workspace, row)[0]}}
            for row, record in zip(data.normalized_variables, data.record_metadata, strict=True))
        data = replace(data, record_metadata=records, statuses=("committed:succeeded",) * data.sample_count)
        current = replace(data, normalized_variables=tuple(job_template_api.normalize_variables(
            plain.config.workspace, (record["raw_variables"]["input_value"],)) for record in records))
        assert current.content_digest != data.content_digest  # Exercise actual floating round trips.
        assert campaign.interpretation_fingerprint != plain.interpretation_fingerprint
        assert dict(campaign.source_hashes) == dict(plain.source_hashes)
        state = component.fit(workspace, data, generation_index=2, snapshot=campaign)
        expected = component.predict(state, ((0.38,),), snapshot=plain)
        runtime.reset_workspace_state(workspace)
        recovered = component.recover(workspace, current, snapshot=plain)
        assert recovered is not None
        assert recovered.training_data_digest == data.content_digest
        assert recovered.training_normalized_variables == data.normalized_variables
        assert component.predict(recovered, ((0.38,),), snapshot=plain).costs == expected.costs

        # Even a one-ulp edit that is not the proved normalization must be rejected.
        altered_x = list(current.normalized_variables)
        altered_x[2] = (float(np.nextafter(altered_x[2][0], 1.0)),)
        assert component.recover(workspace, replace(current, normalized_variables=tuple(altered_x)), snapshot=plain) is None
        altered_records = list(records)
        altered_records[2] = {**records[2], "raw_variables": {"input_value": 0.123}}
        assert component.recover(workspace, replace(current, record_metadata=tuple(altered_records)), snapshot=plain) is None
        assert component.recover(workspace, replace(current, raw_data=(_sample(0.02),) + current.raw_data[1:]), snapshot=plain) is None
        assert component.recover(workspace, replace(current, evidence_ids=("other",) + current.evidence_ids[1:]), snapshot=plain) is None
        assert component.recover(workspace, replace(current, statuses=("derived:succeeded",) * current.sample_count), snapshot=plain) is None
    finally:
        campaign.close()
        plain.close()


def test_materialization_default_chronology_and_explicit_caller_order(workspace, component):
    for index in (2, 0, 1):
        record_job_result(workspace, f"candidate-{index}", (index / 3,), _sample(index / 3).items,
                          {"run_id": "order-test", "optimization_index": 0,
                           "generation_index": 0, "population_index": index})
    dataset = get_evidence_dataset(workspace)
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        costs = calculate_cost_table(dataset, snapshot)
    finally:
        snapshot.close()
    data = component.training_data(dataset, costs)
    assert [row["population_index"] for row in data.record_metadata] == [0, 1, 2]
    reversed_ids = tuple(reversed(data.row_ids))
    explicit = component.training_data(dataset, costs, row_ids=reversed_ids)
    assert explicit.row_ids == reversed_ids


def test_fit_uses_owned_float64_buffer_without_changing_training_samples(monkeypatch):
    from yadof.surrogate.amplitude_gp import model

    data = _data()
    before = tuple(sample.as_mapping() for sample in data.raw_data)
    original_pca = model.PCA
    buffers = []

    class InspectPCA(original_pca):
        def fit_transform(self, values, y=None):
            assert values.dtype == np.float64 and values.flags.writeable and values.flags.owndata
            assert not self.copy
            buffers.append(weakref.ref(values))
            return super().fit_transform(values, y)

    import weakref
    monkeypatch.setattr(model, "PCA", InspectPCA)
    fitted = model.fit_amplitude_model(data, tuple(range(data.sample_count)),
        np.asarray(data.normalized_variables), settings=amplitude_gp(
            minimum_training_samples=2, gp_max_rows=8, shape_rank=3, optimizer_iterations=3).settings)
    assert buffers and all(ref() is None for ref in buffers)
    for sample, expected in zip(data.raw_data, before, strict=True):
        for item in sample.items:
            np.testing.assert_array_equal(item.payload["values"], expected[item.filename]["values"])
    assert all(sample is not None for sample in fitted.predict(np.array([[0.2], [0.8]]))[0])


def test_amplitude_split_reuses_buffer_and_preserves_zero_span_rows():
    from yadof.surrogate.amplitude_gp.model import split_amplitude

    target = np.array([[1., 3., 2.], [4., 4., 4.], [-2., -1., 0.]])
    low, span, expected = split_amplitude(target)
    owned = target.copy()
    actual_low, actual_span, actual = split_amplitude(owned, out=owned)
    assert actual is owned
    np.testing.assert_array_equal(actual_low, low)
    np.testing.assert_array_equal(actual_span, span)
    np.testing.assert_array_equal(actual, expected)
    np.testing.assert_array_equal(actual[1], np.zeros(3))
    np.testing.assert_array_equal(target[0], [1., 3., 2.])
