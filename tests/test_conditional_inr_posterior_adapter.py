from __future__ import annotations

import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from yadof.config import DEFAULT_CONFIG
from yadof.job_template import Parameter
from yadof.job_template.rawdata_contract import NamedRawDataItem
from yadof.job_template.api import CostInterpreter
from yadof.job_template.rawdata_projector import RawDataCostProjector
from yadof.optimize.qnehvi_backend import score_discrete_qlognehvi
from yadof.surrogate import (
    RawDataPosteriorSurrogate,
    conditional_inr,
    conditional_inr_posterior,
    project_rawdata_sampler,
)
from yadof.surrogate.conditional_inr import modeling, runtime
from yadof.surrogate.conditional_inr.types import (
    RawArraySlot,
    RawDataSchema,
    SurrogateState,
    TargetScaler,
)


def _metadata(shape, axes):
    return np.asarray(
        json.dumps(
            {
                "schema_version": 1,
                "shape": list(shape),
                "axes": list(axes),
            },
            sort_keys=True,
        ),
        dtype=np.str_,
    )


def _curve_payload():
    return {
        "values": np.asarray([10.0, 20.0], dtype=np.float64),
        "frequency": np.asarray([1.0, 2.0], dtype=np.float64),
        "unit_frequency": np.asarray("GHz", dtype=np.str_),
        "metadata": _metadata(
            (2,),
            (
                {
                    "index": 0,
                    "size": 2,
                    "name": "frequency",
                    "values_key": "frequency",
                },
            ),
        ),
    }


def _scalar_payload():
    return {
        "values": np.asarray(3.0, dtype=np.float64),
        "metadata": _metadata((), ()),
    }


class _NamedSession:
    def named_rawdata_samples(self, *, status=None):
        assert status == "completed"
        return (
            (
                "real-0001",
                (
                    NamedRawDataItem("z_curve.npz", _curve_payload()),
                    NamedRawDataItem("a_scalar.npz", _scalar_payload()),
                ),
            ),
        )


def _state(tmp_path: Path, member_count: int = 3) -> SurrogateState:
    schema = RawDataSchema(
        templates=(_curve_payload(), _scalar_payload()),
        modeled_slots=(
            RawArraySlot(0, "values", (2,), "float64", 0, 2, 0),
            RawArraySlot(1, "values", (), "float64", 2, 3, 1),
        ),
        flat_dim=3,
        coord_table=np.asarray(
            [[-1.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            dtype=np.float32,
        ),
        field_ids=np.asarray([0, 0, 1], dtype=np.int64),
    )
    train_cfg = modeling.INRTrainConfig(
        ensemble_size=member_count,
        hidden_dim=8,
        hidden_layers=1,
        x_latent_dim=4,
        field_emb_dim=2,
        coord_fourier_features=2,
        sample_batch_eval=2,
        query_batch_eval=3,
    )
    members = []
    for member_index in range(member_count):
        torch.manual_seed(100 + member_index)
        members.append(modeling.build_inr_model(2, 2, train_cfg))
    model = modeling.DeepEnsembleINR(members)
    model.eval()
    return SurrogateState(
        generation_index=4,
        sample_count=12,
        checkpoint_path=tmp_path / "checkpoint.json",
        namespace_manifest_path=tmp_path / "namespace.json",
        model_path=tmp_path / "model.npz",
        artifact_dir=tmp_path / "artifact",
        model_name=modeling.MODEL_NAME,
        strategy_signature="adapter-strategy-v1",
        state_signature="adapter-state-v1",
        run_namespace="strategy-adapter",
        component_namespace="conditional-inr",
        parameter_names=("x", "y"),
        parameter_definition_signature={"parameters": (), "constraints": ()},
        schema=schema,
        scaler=TargetScaler(
            mean=np.asarray([10.0, 20.0, 3.0], dtype=np.float64),
            scale=np.asarray([2.0, 4.0, 0.5], dtype=np.float64),
        ),
        model=model,
        train_cfg=train_cfg,
        device=torch.device("cpu"),
        train_history={"member_count": member_count, "skipped": False},
    )


def _context(monkeypatch, tmp_path: Path, member_count: int = 3):
    state = _state(tmp_path, member_count)
    monkeypatch.setattr(runtime, "_require_state", lambda config, settings: state)
    context = SimpleNamespace(
        config=object(),
        session=_NamedSession(),
        strategy_signature=state.strategy_signature,
    )
    return state, context


def _main_arrays(sample):
    mapping = sample.as_mapping()
    return (
        mapping["z_curve.npz"]["values"],
        mapping["a_scalar.npz"]["values"],
    )


def _cost(payloads):
    curve = np.asarray(payloads[0]["values"], dtype=np.float64)
    scalar = float(np.asarray(payloads[1]["values"]))
    return (float(np.mean(curve) + scalar), float(np.max(curve) - scalar))


@pytest.mark.parametrize("draw_count", (2, 3, 8))
def test_seeded_draws_report_honest_finite_support(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    draw_count: int,
) -> None:
    _state_value, context = _context(monkeypatch, tmp_path)
    adapter = conditional_inr_posterior()
    first = adapter.make_rawdata_sampler(context, draw_count=draw_count, seed=7)
    repeated = adapter.make_rawdata_sampler(context, draw_count=draw_count, seed=7)
    changed = adapter.make_rawdata_sampler(context, draw_count=draw_count, seed=8)

    assert first.diagnostics.posterior_kind == "empirical_ensemble"
    assert first.diagnostics.support_kind == "finite"
    assert first.diagnostics.unique_support == 3
    assert first.diagnostics.actual_draw_count == draw_count
    assert first.diagnostics.draw_sources == repeated.diagnostics.draw_sources
    assert first.diagnostics.draw_sources != changed.diagnostics.draw_sources
    assert len(set(first.diagnostics.draw_sources[: min(3, draw_count)])) == min(
        3, draw_count
    )
    assert len(set(first.diagnostics.draw_sources)) <= 3


def test_member_draws_match_runtime_full_grid_and_keep_joint_cost_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state, context = _context(monkeypatch, tmp_path)
    population = ((0.1, 0.2), (0.8, 0.4))
    sampler = conditional_inr_posterior().make_rawdata_sampler(
        context,
        draw_count=3,
        seed=11,
    )
    posterior = sampler.predict(population)

    for draw, source in zip(posterior.draws, posterior.diagnostics.draw_sources):
        member_index = int(source.rsplit("-", 1)[1])
        flat = runtime._predict_selected_member_flat(
            state,
            runtime._x_matrix(population, 2),
            member_index,
        )
        runtime_samples = runtime._raw_samples_from_flat(state.schema, flat)
        for adapter_sample, runtime_sample in zip(draw.samples, runtime_samples):
            curve, scalar = _main_arrays(adapter_sample)
            np.testing.assert_allclose(curve, runtime_sample[0]["values"])
            np.testing.assert_allclose(scalar, runtime_sample[1]["values"])
            assert _cost(runtime_sample) == pytest.approx(_cost((
                {"values": curve},
                {"values": scalar},
            )))
    assert posterior.diagnostics.effective_unique_support == 3


def test_sampler_is_chunk_permutation_and_duplicate_invariant(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _state_value, context = _context(monkeypatch, tmp_path)
    sampler = conditional_inr_posterior().make_rawdata_sampler(
        context,
        draw_count=7,
        seed=17,
    )
    a, b, c = (0.1, 0.2), (0.4, 0.3), (0.7, 0.9)

    full = sampler.predict((a, b, c, a))
    left = sampler.predict((a, b))
    right = sampler.predict((c, a))
    permuted = sampler.predict((c, a, b))

    def values(posterior, draw_index, candidate_index):
        return tuple(
            np.asarray(value).copy()
            for value in _main_arrays(
                posterior.draws[draw_index].samples[candidate_index]
            )
        )

    for draw_index in range(7):
        for lhs, rhs in zip(values(full, draw_index, 0), values(full, draw_index, 3)):
            np.testing.assert_array_equal(lhs, rhs)
        for lhs, rhs in zip(values(full, draw_index, 0), values(left, draw_index, 0)):
            np.testing.assert_array_equal(lhs, rhs)
        for lhs, rhs in zip(values(full, draw_index, 1), values(left, draw_index, 1)):
            np.testing.assert_array_equal(lhs, rhs)
        for lhs, rhs in zip(values(full, draw_index, 2), values(right, draw_index, 0)):
            np.testing.assert_array_equal(lhs, rhs)
        for lhs, rhs in zip(values(full, draw_index, 0), values(right, draw_index, 1)):
            np.testing.assert_array_equal(lhs, rhs)
        for expected_index, actual_index in ((2, 0), (0, 1), (1, 2)):
            for lhs, rhs in zip(
                values(full, draw_index, expected_index),
                values(permuted, draw_index, actual_index),
            ):
                np.testing.assert_array_equal(lhs, rhs)


def test_member_failure_reduces_effective_support_without_field_splicing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _state_value, context = _context(monkeypatch, tmp_path)
    original = runtime._predict_selected_member_flat

    def fail_one(state, x, member_index):
        if int(member_index) == 1:
            raise RuntimeError("member one inference failed")
        return original(state, x, member_index)

    monkeypatch.setattr(runtime, "_predict_selected_member_flat", fail_one)
    sampler = conditional_inr_posterior().make_rawdata_sampler(
        context,
        draw_count=40,
        seed=7,
    )
    posterior = sampler.predict(((0.2, 0.3),))

    failed_draws = 0
    for draw, source in zip(posterior.draws, posterior.diagnostics.draw_sources):
        if source.endswith("-0001"):
            failed_draws += 1
            assert draw.samples == ((),)
        else:
            assert set(draw.samples[0].as_mapping()) == {
                "a_scalar.npz",
                "z_curve.npz",
            }
    assert posterior.diagnostics.unique_support == 3
    assert posterior.diagnostics.effective_unique_support == 2
    assert posterior.diagnostics.prediction_failure_count == failed_draws
    assert len(posterior.diagnostics.retained_prediction_failures) == min(
        failed_draws, 32
    )

    projector = RawDataCostProjector(
        CostInterpreter(
                parameters=(Parameter("x", (0.0, 1.0)), Parameter("y", (0.0, 1.0))),
            objective_names=("one", "two"),
            _source_path=tmp_path / "calc_cost.py",
            _calculate_sample=lambda items, raw_variables: (
                float(np.mean(np.asarray(items[1]["values"])) / 30.0),
                float(np.asarray(items[0]["values"]) / 6.0),
            ),
        ),
        sampler._schema_template,
    )
    projected = project_rawdata_sampler(
        sampler,
        projector,
        ((0.2, 0.3),),
    )
    assert projected.source_diagnostics["effective_unique_support"] == 2
    assert projected.source_diagnostics["effective_draw_count"] == 40 - failed_draws


def test_adapter_is_explicit_and_legacy_component_identity_stays_unchanged() -> None:
    legacy = conditional_inr()
    adapter = conditional_inr_posterior()

    assert not isinstance(legacy, RawDataPosteriorSurrogate)
    assert isinstance(adapter, RawDataPosteriorSurrogate)
    assert legacy.semantic_identity(DEFAULT_CONFIG, object())["component_version"] == 2
    identity = adapter.semantic_identity(DEFAULT_CONFIG, object())
    assert identity["component"] == "conditional-inr-posterior-adapter"
    assert identity["base_surrogate"] == legacy.semantic_identity(
        DEFAULT_CONFIG,
        object(),
    )
    assert identity["posterior"]["controlled_parameters"][
        "observation_noise_included"
    ] is False


@pytest.mark.filterwarnings("ignore:Failed to compile fused qLogEHVI")
def test_conditional_inr_adapter_projects_into_qlognehvi_backend_spike(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("botorch")
    _state_value, context = _context(monkeypatch, tmp_path)
    sampler = conditional_inr_posterior().make_rawdata_sampler(
        context,
        draw_count=5,
        seed=29,
    )

    def calculate_cost(items, raw_variables):
        del raw_variables
        scalar = float(np.asarray(items[0]["values"]))
        curve = np.asarray(items[1]["values"], dtype=np.float64)
        return (
            float(np.clip(np.mean(curve) / 30.0, 0.0, 1.0)),
            float(np.clip(scalar / 6.0, 0.0, 1.0)),
        )

    projector = RawDataCostProjector(
        CostInterpreter(
            parameters=(Parameter("x", (0.0, 1.0)), Parameter("y", (0.0, 1.0))),
            objective_names=("curve", "scalar"),
            _source_path=tmp_path / "calc_cost.py",
            _calculate_sample=calculate_cost,
        ),
        sampler._schema_template,
    )
    population = ((0.2, 0.3), (0.6, 0.4), (0.3, 0.8))
    objective_samples = project_rawdata_sampler(
        sampler,
        projector,
        population,
        candidate_chunk_size=2,
    )
    result = score_discrete_qlognehvi(
        baseline_population=((0.0, 0.0), (1.0, 1.0)),
        baseline_costs=((0.4, 0.7), (0.7, 0.4)),
        candidate_samples=objective_samples,
        candidate_batches=((0,), (1, 2)),
        minimum_unique_support=3,
        seed=29,
    )

    assert objective_samples.source_diagnostics["effective_unique_support"] == 3
    assert result.diagnostics["effective_unique_support"] == 3
    assert all(math.isfinite(value) for value in result.log_acquisition_values)
    assert not hasattr(result, "rawdata")
