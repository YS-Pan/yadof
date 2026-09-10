"""Installed retrieval-response ownership, recovery and numerical boundaries."""
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
from yadof.recorded_data import list_records
from yadof.surrogate import retrieval_response, DeterministicSurrogateComponent, TrainingCancelledError
from yadof.surrogate.retrieval_response import runtime, checkpoints, scheduler
from yadof.task_snapshot import create_generation_snapshot
from yadof.workspace.init import init_workspace
from test_amplitude_gp import _data, _cost_file, _sample

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
    return retrieval_response(shape_rank=3, hidden_width=12, members=1, steps=3, validation_steps=2)

def test_public_defaults_lazy_import_and_identity():
    component = retrieval_response()
    assert isinstance(component, DeterministicSurrogateComponent)
    assert component.settings.steps * component.settings.members + component.settings.validation_steps == 200
    assert component.semantic_identity(None, None) != retrieval_response(neighbors=4).semantic_identity(None, None)
    script = "import sys; from yadof.surrogate import retrieval_response; retrieval_response(); "
    script += "assert 'torch' not in sys.modules and 'sklearn' not in sys.modules; "
    script += "import yadof.surrogate.retrieval_response.runtime; from yadof.surrogate import retrieval_response; assert callable(retrieval_response)"
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr

@pytest.mark.parametrize("kwargs", [{"steps":0}, {"shape_rank":True}, {"neighbors":9}, {"members":4},
    {"learning_rate":float("nan")}, {"minimum_training_samples":2}, {"validation_fraction":1},
    {"random_seed":2**32}, {"prediction_chunk":1.5}])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        retrieval_response(**kwargs)

def test_complete_rawdata_checkpoint_and_cost_reinterpretation(workspace, component):
    data = _data()
    state = component.fit(workspace, data, generation_index=2)
    assert state.train_history["total_gradient_steps"] == 5
    assert state.train_history["context_row_ids"] == list(data.row_ids)
    assert not set(state.train_history["validation_context_row_ids"]) & set(state.train_history["validation_query_row_ids"])
    assert state.train_history["validation_used_for_selection"] is False
    before_records = list_records(workspace)
    snapshot = create_generation_snapshot(load_config(workspace))
    queries = tuple((float(x),) for x in np.linspace(0, 1, 129))
    try:
        prediction = component.predict(state, queries, snapshot=snapshot)
        assert all(prediction.valid_mask)
        assert prediction.raw_data[0].as_mapping()["volume.npz"]["values"].shape == (2, 3, 4)
        runtime.reset_workspace_state(workspace)
        restored = component.recover(workspace, data, snapshot=snapshot)
        assert restored is not None
        actual = component.predict(restored, queries, snapshot=snapshot)
        assert actual.costs == prediction.costs
        assert np.array_equal(restored.model.z, state.model.z)
        for a,b in zip(prediction.raw_data, actual.raw_data, strict=True):
            for x,y in zip(a.items,b.items,strict=True):
                assert np.array_equal(x.payload["values"],y.payload["values"])
        for invalid in (((-1e-12,),), ((1+1e-12,),), ((float("nan"),),)):
            with pytest.raises(ValueError):
                component.predict(restored, invalid, snapshot=snapshot)
        assert component.predict(restored, (), snapshot=snapshot).costs == ()
    finally:
        snapshot.close()
    _cost_file(workspace, shift=20)
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        # No objective-dependent priorities: unchanged training can be recovered.
        restored = component.recover(workspace, data, snapshot=snapshot)
        assert restored is not None
        actual = component.predict(restored, queries, snapshot=snapshot)
        assert actual.costs[0][0] == pytest.approx(prediction.costs[0][0]+20)
    finally:
        snapshot.close()
    assert list_records(workspace) == before_records

def test_own_rows_failed_evidence_and_lagged_recovery(workspace, component):
    data = _data()
    prefix = runtime.training_subset(data, data.row_ids[:8])
    component.fit(workspace, prefix, generation_index=2)
    snapshot = create_generation_snapshot(load_config(workspace))
    try:
        assert component.recover(workspace, data, snapshot=snapshot) is None
        context = SimpleNamespace(config=snapshot.config, snapshot=snapshot, generation_index=3, session=None)
        assert component.latest_trained_generation(context, data) == 2
        changed = replace(data, raw_data=(_sample(.02),)+data.raw_data[1:])
        assert component.latest_trained_generation(context, changed) is None
        wrong = retrieval_response(shape_rank=2, hidden_width=12, members=1, steps=3, validation_steps=2)
        assert wrong.recover(workspace,prefix,snapshot=snapshot) is None
    finally:
        snapshot.close()
    failed = replace(data, valid_mask=(False,)+(True,)*11,
                     statuses=("failed",)+data.statuses[1:])
    state = component.fit(workspace, failed)
    assert state.sample_count == 11 and data.row_ids[0] not in state.train_history["context_row_ids"]

@pytest.mark.parametrize("damage", ["bytes", "path", "tensor", "extra", "schema"])
def test_checkpoint_corruption_rejected(workspace, component, damage):
    data = _data()
    state = component.fit(workspace, data)
    manifest = json.loads(state.namespace_manifest_path.read_text())
    path = state.artifact_dir / "model.npz"
    if damage == "bytes":
        path.write_bytes(b"broken")
    elif damage == "path":
        manifest["artifact_dir"] = "../outside"
    else:
        with np.load(path,allow_pickle=False) as archive:
            arrays = {key:archive[key] for key in archive.files}
        if damage == "tensor":
            arrays["member0_delta.weight"] = arrays["member0_delta.weight"][:-1]
        elif damage == "extra":
            arrays["unexpected"] = np.ones(1)
        else:
            schema_payload = manifest["fields"][0]["payload"]["mapping"]
            key = schema_payload["axis0"]["array"]
            arrays[key] = arrays[key]+.5
        np.savez_compressed(path, **arrays)
        manifest["artifact_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    state.namespace_manifest_path.write_text(json.dumps(manifest))
    runtime.reset_workspace_state(workspace)
    assert component.recover(workspace,data) is None

def test_cancellation_and_cpu_rng_restoration(workspace, component):
    import torch
    from yadof.surrogate.retrieval_response import model
    data = _data()
    before = torch.random.get_rng_state().clone()
    threads = torch.get_num_threads()
    component.fit(workspace,data)
    assert torch.equal(before,torch.random.get_rng_state())
    assert torch.get_num_threads() == threads
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(TrainingCancelledError):
        model.fit_model(data,data.selected_indices,settings=component.settings,cancel_event=cancel)
    # Cancellation while waiting for the numerical scope cannot leak a lock/RNG change.
    ready = threading.Event()
    release = threading.Event()
    def owner():
        with model._NUMERICAL_LOCK:
            ready.set()
            release.wait(5)
    thread = threading.Thread(target=owner)
    thread.start()
    assert ready.wait(2)
    try:
        with pytest.raises(TrainingCancelledError):
            with model._runtime(component.settings.semantic_parameters(), cancel):
                pass
    finally:
        release.set()
        thread.join(5)
    assert torch.equal(before,torch.random.get_rng_state())

def test_training_neighbors_exclude_identity_not_duplicate_design():
    from yadof.surrogate.retrieval_response.model import NeighborIndex
    x = np.array([[0.],[0.],[.5],[1.]])
    indices = NeighborIndex(x,3).query(x,self_positions=np.arange(4))
    assert not np.any(indices == np.arange(4)[:,None])
    assert 1 in indices[0] and 0 in indices[1]
