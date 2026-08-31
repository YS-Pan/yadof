from __future__ import annotations

import json
import subprocess
import sys

import numpy as np
import pytest

from yadof.config import load_config
from yadof.job_template.rawdata_contract import NamedRawDataItem
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.surrogate import PCASVDComponent, SurrogateTrainingData, pca_svd
from yadof.surrogate.linear_subspace import runtime
from yadof.task_snapshot import create_generation_snapshot
from yadof.workspace.init import init_workspace


def _payload(values, axis_names=()):
    array = np.asarray(values, dtype=np.float64)
    axes = []
    payload = {"values": array}
    for index, name in enumerate(axis_names):
        payload[name] = np.linspace(0.0, 1.0, array.shape[index])
        axes.append(
            {
                "index": index,
                "size": array.shape[index],
                "name": name,
                "values_key": name,
            }
        )
    payload["metadata"] = np.asarray(
        json.dumps(
            {"schema_version": 1, "shape": list(array.shape), "axes": axes},
            sort_keys=True,
        ),
        dtype=np.str_,
    )
    return payload


def _sample(x: float, *, filename: str = "field.npz"):
    curve = 3.0 + x * np.asarray([-2.0, -1.0, 1.0, 2.0])
    surface = x + np.arange(6, dtype=np.float64).reshape(2, 3)
    return StructuredRawDataSample.from_items(
        (
            NamedRawDataItem(filename, _payload(curve, ("phase",))),
            NamedRawDataItem("surface.npz", _payload(surface, ("x", "y"))),
            NamedRawDataItem("scalar.npz", _payload(4.0)),
        )
    )


def _data(values=(0.0, 0.25, 0.5, 0.75, 1.0)):
    rows = tuple(float(value) for value in values)
    return SurrogateTrainingData(
        parameter_names=("x",),
        normalized_variables=tuple((value,) for value in rows),
        raw_data=tuple(_sample(value) for value in rows),
        row_ids=tuple(f"job-{index}" for index in range(len(rows))),
    )


def test_factory_is_opt_in_component_with_no_posterior_capability() -> None:
    component = pca_svd(decomposition="svd", rank=3, ridge_alpha=1e-5)
    assert isinstance(component, PCASVDComponent)
    assert component.settings.decomposition == "svd"
    assert component.settings.rank == 3
    assert not hasattr(component, "make_rawdata_sampler")
    assert not hasattr(component, "posterior_semantic_identity")
    with pytest.raises(ValueError, match="at least one"):
        pca_svd(rank=0)


def test_parent_import_does_not_eagerly_import_torch() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import yadof.surrogate; "
            "assert 'torch' not in sys.modules; print('lazy')",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.stdout.strip() == "lazy"


def test_selected_component_reports_missing_surrogate_extra(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from importlib import metadata

    from yadof.surrogate import api as surrogate_api

    original = surrogate_api.metadata.version

    def missing_torch(name: str):
        if name == "torch":
            raise metadata.PackageNotFoundError(name)
        return original(name)

    monkeypatch.setattr(surrogate_api.metadata, "version", missing_torch)
    with pytest.raises(RuntimeError, match=r"yadof\[surrogate\]"):
        pca_svd().validate(None, None)


def test_public_import_does_not_eagerly_import_torch() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import yadof.surrogate; assert 'torch' not in sys.modules",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("decomposition", ["pca", "svd"])
def test_oracle_and_deployable_preserve_exact_named_schema(decomposition: str) -> None:
    component = pca_svd(decomposition=decomposition, rank=2, device="cpu")
    data = _data()
    model = component.fit_deployable(
        data.normalized_variables,
        data.raw_data,
        parameter_names=data.parameter_names,
    )
    predicted = component.predict_rawdata(model, ((0.125,), (0.875,)))
    assert len(predicted) == 2
    assert predicted[0].field_selectors == data.raw_data[0].field_selectors
    for expected, actual in zip(data.raw_data[0].items, predicted[0].items):
        assert set(expected.payload) == set(actual.payload)
        assert actual.payload["values"].dtype == expected.payload["values"].dtype
    codec = component.fit_codec(data.raw_data)
    repeated = component.fit_codec(data.raw_data)
    for field, repeated_field in zip(codec.fields, repeated.fields):
        assert np.allclose(field.basis, repeated_field.basis)
        for column in range(field.basis.shape[1]):
            pivot = int(np.argmax(np.abs(field.basis[:, column])))
            assert field.basis[pivot, column] >= 0.0
    oracle = component.evaluate_oracle(codec, (_sample(0.125),))
    assert oracle.diagnostic_only is True
    assert oracle.validation_rawdata_encoded is True
    assert oracle.samples[0].field_selectors == data.raw_data[0].field_selectors
    assert np.allclose(
        oracle.samples[0].as_mapping()["field.npz"]["values"],
        _sample(0.125).as_mapping()["field.npz"]["values"],
        atol=2e-5,
    )
    if decomposition == "pca":
        assert any(np.any(field.mean != 0.0) for field in codec.fields)
    else:
        assert all(np.all(field.mean == 0.0) for field in codec.fields)


def test_ridge_prediction_uses_parameters_and_rejects_invalid_inputs() -> None:
    component = pca_svd(rank=2, ridge_alpha=0.0)
    data = _data()
    model = component.fit_deployable(
        data.normalized_variables,
        data.raw_data,
        parameter_names=data.parameter_names,
    )
    predicted = component.predict_rawdata(model, ((0.33,),))[0]
    assert np.allclose(
        predicted.as_mapping()["field.npz"]["values"],
        _sample(0.33).as_mapping()["field.npz"]["values"],
        atol=2e-5,
    )
    with pytest.raises(ValueError, match=r"\[0, 1\]"):
        component.predict_rawdata(model, ((1.1,),))
    bad = list(data.raw_data)
    bad[2] = _sample(float("nan"))
    with pytest.raises(ValueError, match="non-finite"):
        component.fit_deployable(
            data.normalized_variables,
            bad,
            parameter_names=data.parameter_names,
        )
    drift = list(data.raw_data)
    drift[-1] = _sample(1.0, filename="renamed.npz")
    with pytest.raises(Exception, match="selector set"):
        component.fit_codec(drift)


def test_constant_and_single_row_pca_are_explicit_mean_only_models() -> None:
    component = pca_svd(decomposition="pca", rank=8)
    one = _data((0.5,))
    codec = component.fit_codec(one.raw_data)
    assert all(field.effective_rank == 0 for field in codec.fields)
    assert all("mean-only" in field.rank_reason for field in codec.fields)
    model = component.fit_deployable(
        one.normalized_variables,
        one.raw_data,
        parameter_names=one.parameter_names,
    )
    predicted = component.predict_rawdata(model, ((0.0,), (1.0,)))
    assert np.array_equal(
        predicted[0].as_mapping()["field.npz"]["values"],
        predicted[1].as_mapping()["field.npz"]["values"],
    )


def test_checkpoint_recovery_and_zero_width_cost_intervals(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "pca-svd-runtime"
    init_workspace(workspace)
    (workspace / "config.py").write_text('EVALUATION_MODE = "local"\n', encoding="utf-8")
    config = load_config(workspace)
    data = _data()
    component = pca_svd(rank=2, device="cpu")
    monkeypatch.setattr(
        runtime.job_template_api,
        "get_parameter_definition_signature",
        lambda _workspace: {"signature": "test-parameters"},
    )
    state = runtime.train_with_config(
        config,
        generation_index=3,
        training_data=data,
        settings=component.settings,
    )
    assert state.checkpoint_path.is_file()
    assert state.namespace_manifest_path.is_file()
    assert state.artifact_path.is_file()
    assert "components/pca-svd" in state.artifact_dir.as_posix()
    runtime.reset_workspace_state(workspace)
    assert runtime.has_trained_state(
        workspace,
        data,
        _settings=component.settings,
    )
    recovered = runtime._require_state(
        config,
        data,
        settings=component.settings,
    )
    assert recovered.state_signature == state.state_signature
    monkeypatch.setattr(
        runtime,
        "_costs_from_samples",
        lambda _workspace, _samples, rows: tuple((float(row[0]),) for row in rows),
    )
    snapshot = create_generation_snapshot(config)
    try:
        output = runtime.predict_population(
            workspace,
            ((0.2,), (0.8,)),
            _training_data=data,
            _snapshot=snapshot,
            _settings=component.settings,
        )
    finally:
        snapshot.close()
    assert output == (((0.2,), ((0.2, 0.2),)), ((0.8,), ((0.8, 0.8),)))


def test_checkpoint_recovery_rejects_changed_training_design(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "pca-svd-stale"
    init_workspace(workspace)
    (workspace / "config.py").write_text('EVALUATION_MODE = "local"\n', encoding="utf-8")
    config = load_config(workspace)
    component = pca_svd(rank=2)
    original_data = _data()
    monkeypatch.setattr(
        runtime.job_template_api,
        "get_parameter_definition_signature",
        lambda _workspace: {"signature": "test-parameters"},
    )
    runtime.train_with_config(config, training_data=original_data, settings=component.settings)
    changed_data = _data((0.0, 0.25, 0.5, 0.75, 0.9))
    runtime.reset_workspace_state(workspace)
    assert not runtime.has_trained_state(
        workspace,
        changed_data,
        _settings=component.settings,
    )


def test_in_memory_state_rejects_changed_parameter_normalization(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "pca-svd-parameter-drift"
    init_workspace(workspace)
    (workspace / "config.py").write_text('EVALUATION_MODE = "local"\n', encoding="utf-8")
    config = load_config(workspace)
    component = pca_svd(rank=2)
    signature = {"signature": "original"}
    monkeypatch.setattr(
        runtime.job_template_api,
        "get_parameter_definition_signature",
        lambda _workspace: dict(signature),
    )
    runtime.train_with_config(config, training_data=_data(), settings=component.settings)
    signature["signature"] = "changed"
    assert not runtime.has_trained_state(
        workspace,
        _data(),
        _settings=component.settings,
    )
