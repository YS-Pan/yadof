from __future__ import annotations

from dataclasses import replace
import json
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from yadof.config import load_config
from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_contract import NamedRawDataItem
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.surrogate import (
    CAETrainConfig,
    DiagnosticCondition,
    DiagnosticRegimeRule,
    RawDataQualityPolicy,
    ShapeQualityRule,
    hierarchical_cae,
)
from yadof.surrogate.hierarchical_cae import (
    data_adapter,
    inference,
    networks,
    objectives,
    training,
)
from yadof.surrogate.hierarchical_cae import runtime
from yadof.surrogate.hierarchical_cae.coordinates import (
    coordinate_grid,
    encode_coordinate_points,
    interpolate_stored_values,
)
from yadof.surrogate.hierarchical_cae.schema import (
    build_schema,
    field_matrices,
    fit_scalers,
    reconstruct_samples,
    standardized_field_matrices,
)
from yadof.surrogate.quality import (
    RAWDATA_QUALITY_ASSESSMENT_PROTOCOL,
    assess_quality,
    quality_policy_from_mapping,
)
from yadof.surrogate.hierarchical_cae.types import NamedTrainingData
from yadof.workspace.init import init_workspace


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


def _payload(values, axis_names=()):
    array = np.asarray(values, dtype=np.float64)
    axes = []
    payload = {"values": array}
    for index, name in enumerate(axis_names):
        coordinates = np.linspace(0.0, 1.0, array.shape[index], dtype=np.float64)
        payload[name] = coordinates
        axes.append(
            {
                "index": index,
                "size": array.shape[index],
                "name": name,
                "values_key": name,
            }
        )
    payload["metadata"] = _metadata(array.shape, axes)
    return payload


def _mixed_sample(value: float = 0.0) -> StructuredRawDataSample:
    phase = np.linspace(0.0, 1.0, 8, dtype=np.float64)
    row = np.linspace(-1.0, 1.0, 4, dtype=np.float64)[:, None]
    column = np.linspace(0.0, 2.0, 5, dtype=np.float64)[None, :]
    return StructuredRawDataSample.from_items(
        (
            NamedRawDataItem("a_scalar.npz", _payload(value)),
            NamedRawDataItem(
                "b_curve.npz",
                _payload(np.sin(phase * np.pi) + value, ("phase",)),
            ),
            NamedRawDataItem(
                "c_surface.npz",
                _payload(row + column + value, ("x", "y")),
            ),
        )
    )


def _rank3_sample() -> StructuredRawDataSample:
    values = np.arange(2 * 3 * 4, dtype=np.float64).reshape(2, 3, 4)
    return StructuredRawDataSample.from_items(
        (NamedRawDataItem("field.npz", _payload(values, ("Freq", "Phi", "Theta"))),)
    )


def test_schema_round_trip_mixed_rank_and_field_macro_scaling() -> None:
    samples = tuple(_mixed_sample(value) for value in (0.0, 0.5, 1.0))
    schema = build_schema(samples[0])
    assert [layout.codec_kind for layout in schema.layouts] == [
        "scalar-mlp",
        "conv1d",
        "conv2d",
    ]
    matrices = field_matrices(schema, samples)
    schema = replace(schema, scalers=fit_scalers(matrices, scale_floor=1.0e-6))
    standardized = standardized_field_matrices(schema, matrices)
    rebuilt = reconstruct_samples(schema, standardized)
    for expected, actual in zip(samples, rebuilt):
        assert actual.field_selectors == expected.field_selectors
        for expected_item, actual_item in zip(expected.items, actual.items):
            np.testing.assert_allclose(
                actual_item.payload["values"],
                expected_item.payload["values"],
                atol=1.0e-6,
            )
            assert actual_item.payload["values"].dtype == np.float64
            assert str(actual_item.payload["metadata"]) == str(
                expected_item.payload["metadata"]
            )

    targets = (torch.zeros(2), torch.zeros(2, 1000))
    predictions = (torch.ones(2), torch.ones(2, 1000))
    design_fields = objectives.design_field_losses(predictions, targets)
    assert design_fields.shape == (2, 2)
    torch.testing.assert_close(design_fields[:, 0], design_fields[:, 1])
    torch.testing.assert_close(
        objectives.field_macro_loss(predictions, targets),
        torch.tensor(0.5),
    )


def test_rank3_requires_explicit_axis_roles_and_restores_original_order() -> None:
    sample = _rank3_sample()
    with pytest.raises(ValueError, match="rank-3"):
        build_schema(sample)
    selector = ("field.npz", "values")
    schema = build_schema(
        sample,
        field_layouts={
            selector: {
                "channel_axes": ("Freq",),
                "spatial_axes": ("Phi", "Theta"),
            }
        },
    )
    layout = schema.layouts[0]
    assert layout.model_channels == 2
    assert layout.model_spatial_shape == (3, 4)
    matrices = field_matrices(schema, (sample,))
    schema = replace(schema, scalers=fit_scalers(matrices, scale_floor=1.0e-6))
    rebuilt = reconstruct_samples(
        schema, standardized_field_matrices(schema, matrices)
    )[0]
    np.testing.assert_array_equal(
        rebuilt.items[0].payload["values"], sample.items[0].payload["values"]
    )


def test_groups_use_stable_selectors_and_reject_overlap() -> None:
    sample = _mixed_sample()
    group = (("b_curve.npz", "values"), ("a_scalar.npz", "values"))
    schema = build_schema(sample, groups=(group,))
    assert schema.groups == (
        (("a_scalar.npz", "values"), ("b_curve.npz", "values")),
    )
    with pytest.raises(ValueError, match="overlap"):
        build_schema(
            sample,
            groups=(
                group,
                (("b_curve.npz", "values"), ("c_surface.npz", "values")),
            ),
        )


def test_coordinate_encoding_and_interpolation_cover_all_declared_axes() -> None:
    selector = ("field.npz", "values")
    schema = build_schema(
        _rank3_sample(),
        field_layouts={
            selector: {
                "channel_axes": ("Freq",),
                "spatial_axes": ("Phi", "Theta"),
            }
        },
        axis_encodings={
            selector: {
                "Freq": "linear",
                "Phi": {"kind": "periodic", "period": 1.0},
                "Theta": "linear",
            }
        },
    )
    layout = schema.layouts[0]
    points, shape, axes = coordinate_grid(
        layout,
        (
            np.asarray([0.25, 0.75]),
            np.asarray([0.125, 0.625]),
            np.asarray([0.2, 0.8]),
        ),
    )
    encoded = encode_coordinate_points(layout, points)
    assert shape == (2, 2, 2)
    assert encoded.shape == (8, 4)
    assert len(axes) == 3
    stored = np.arange(layout.point_count, dtype=np.float64)
    selected = interpolate_stored_values(
        layout,
        stored,
        np.asarray([[0.0, 0.0, 0.0], [1.0, 2.0 / 3.0, 1.0]]),
    )
    np.testing.assert_allclose(selected, [0.0, 61.0 / 3.0])
    with pytest.raises(ValueError, match="outside the stored domain"):
        encode_coordinate_points(
            layout, np.asarray([[1.5, 0.5, 0.5]], dtype=np.float64)
        )


def test_coordinate_readout_requires_architecture_v2() -> None:
    with pytest.raises(ValueError, match="architecture_version"):
        CAETrainConfig(coordinate_readout=True)


def _chrono_like_policy() -> RawDataQualityPolicy:
    return RawDataQualityPolicy(
        policy_id="chrono-contact-regime",
        policy_version=1,
        diagnostic_rules=(
            DiagnosticRegimeRule(
                "failure",
                (DiagnosticCondition(("released",), "falsy"),),
            ),
            DiagnosticRegimeRule(
                "chatter",
                (
                    DiagnosticCondition(
                        ("reattach_count",), "greater-than", 0
                    ),
                    DiagnosticCondition(
                        ("contacts_at_end",), "greater-than", 0
                    ),
                ),
                match="any",
            ),
        ),
        diagnostic_field_selectors=(("b_curve.npz", "values"),),
        chatter_field_weight=0.25,
        failure_field_weight=0.2,
        chatter_shared_weight=0.0,
        failure_shared_weight=0.0,
    )


def test_explicit_and_declarative_quality_assessment_are_versioned_and_field_local() -> None:
    policy = _chrono_like_policy()
    samples = (_mixed_sample(0.0), _mixed_sample(1.0), _mixed_sample(2.0))
    explicit = {
        "protocol": RAWDATA_QUALITY_ASSESSMENT_PROTOCOL,
        "protocol_version": 1,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "design_regime": "smooth",
        "fields": {},
    }
    metadata = (
        {
            "task_diagnostics": {
                "yadof_rawdata_quality_assessment": explicit,
                "released": False,
            }
        },
        {"task_diagnostics": {"released": False, "reattach_count": 0}},
        {
            "task_diagnostics": {
                "released": True,
                "reattach_count": 4,
                "contacts_at_end": 0,
            }
        },
    )
    assessed = assess_quality(
        policy=policy, samples=samples, record_metadata=metadata
    )
    assert assessed.design_regimes == ("smooth", "failure", "chatter")
    assert assessed.explicit_assessment_count == 1
    assert assessed.diagnostic_assessment_count == 2
    assert assessed.applicability_targets.tolist() == [1.0, 0.0, 0.0]
    curve_index = samples[0].field_selectors.index(("b_curve.npz", "values"))
    scalar_index = samples[0].field_selectors.index(("a_scalar.npz", "values"))
    assert assessed.field_weights[2, curve_index] == pytest.approx(0.25)
    assert assessed.shared_weights[2, curve_index] == 0.0
    assert assessed.field_weights[2, scalar_index] == 1.0
    assert assessed.residual_targets[2, curve_index] == 1.0
    assert assessed.residual_targets[2, scalar_index] == 0.0
    assert quality_policy_from_mapping(policy.as_dict()) == policy


def test_quality_assessment_priority_shape_fallback_and_no_policy_behavior() -> None:
    samples = (_mixed_sample(0.0), _mixed_sample(1.0))
    ordinary = assess_quality(policy=None, samples=samples)
    np.testing.assert_array_equal(ordinary.field_weights, 1.0)
    np.testing.assert_array_equal(ordinary.shared_weights, 1.0)
    np.testing.assert_array_equal(ordinary.residual_targets, 0.0)
    np.testing.assert_array_equal(ordinary.applicability_targets, 1.0)
    assert ordinary.design_regimes == ("smooth", "smooth")

    policy = replace(
        _chrono_like_policy(),
        shape_fallback_rules=(
            ShapeQualityRule(
                ("b_curve.npz", "values"),
                second_difference_rms_max=0.0,
            ),
        ),
        missing_assessment="shape-fallback",
    )
    explicit = {
        "protocol": RAWDATA_QUALITY_ASSESSMENT_PROTOCOL,
        "protocol_version": 1,
        "policy_id": policy.policy_id,
        "policy_version": policy.policy_version,
        "design_regime": "smooth",
        "fields": {},
    }
    assessed = assess_quality(
        policy=policy,
        samples=samples,
        record_metadata=(
            {
                "task_diagnostics": {
                    "yadof_rawdata_quality_assessment": explicit,
                    "released": False,
                }
            },
            {},
        ),
    )
    assert assessed.design_regimes == ("smooth", "chatter")
    assert assessed.explicit_assessment_count == 1
    assert assessed.diagnostic_assessment_count == 0
    assert assessed.shape_fallback_count == 1
    curve_index = samples[0].field_selectors.index(("b_curve.npz", "values"))
    scalar_index = samples[0].field_selectors.index(("a_scalar.npz", "values"))
    assert assessed.field_regimes[1][curve_index] == "chatter"
    assert assessed.field_regimes[1][scalar_index] == "smooth"


def test_shared_teacher_masks_noisy_token_and_clean_gate_blocks_private_residual() -> None:
    schema = build_schema(_mixed_sample())
    cfg = CAETrainConfig(
        token_dim=4,
        global_latent_dim=3,
        group_latent_dim=2,
        private_latent_dim=3,
        codec_width=8,
        predictor_width=8,
        predictor_layers=1,
        predictor_members=2,
        codec_epochs=1,
        predictor_epochs=1,
        fine_tune_epochs=0,
        batch_size=2,
        inference_batch_size=2,
        early_stopping_patience=1,
        minimum_samples=2,
        regime_head=True,
        mixed_precision=False,
    )
    model = networks.HierarchicalCAEModel(2, schema, cfg)
    torch.manual_seed(17)
    tokens = tuple(torch.randn(2, cfg.token_dim) for _ in schema.layouts)
    changed = list(tokens)
    changed[1] = changed[1] + 1000.0
    weights = torch.ones(2, len(schema.layouts))
    weights[:, 1] = 0.0
    first = model.teacher_latent_from_tokens(tokens, weights)
    second = model.teacher_latent_from_tokens(tuple(changed), weights)
    torch.testing.assert_close(
        first[:, model.global_slice], second[:, model.global_slice]
    )
    assert not torch.allclose(
        first[:, model.private_slices[1]], second[:, model.private_slices[1]]
    )

    latent = torch.randn(2, model.latent_dim)
    zeros = torch.zeros(2, len(schema.layouts))
    clean = model.decode_joint(latent, zeros)
    for codec in model.codecs:
        for name, parameter in codec.named_parameters():
            if name.startswith("residual_"):
                parameter.data.add_(100.0)
    clean_after_residual_change = model.decode_joint(latent, zeros)
    for before, after in zip(clean, clean_after_residual_change):
        torch.testing.assert_close(before, after)


def test_antinoise_ablation_switches_control_independent_paths() -> None:
    samples = (_mixed_sample(0.0), _mixed_sample(1.0))
    quality = assess_quality(
        policy=_chrono_like_policy(),
        samples=samples,
        record_metadata=(
            {"task_diagnostics": {"released": True}},
            {
                "task_diagnostics": {
                    "released": True,
                    "reattach_count": 2,
                    "contacts_at_end": 0,
                }
            },
        ),
    )
    rows = np.asarray([0, 1], dtype=np.int64)
    device = torch.device("cpu")

    def batch(**switches):
        cfg = CAETrainConfig(
            codec_epochs=1,
            predictor_epochs=1,
            minimum_samples=2,
            regime_head=True,
            mixed_precision=False,
            **switches,
        )
        return objectives._quality_batch(quality, rows, device, cfg)

    no_gating = batch(
        quality_weighted_loss=False,
        shared_quality_isolation=False,
        gated_private_residual=False,
    )
    torch.testing.assert_close(no_gating[0], torch.ones_like(no_gating[0]))
    torch.testing.assert_close(no_gating[1], torch.ones_like(no_gating[1]))
    torch.testing.assert_close(no_gating[2], torch.zeros_like(no_gating[2]))

    robust_only = batch(
        quality_weighted_loss=True,
        shared_quality_isolation=False,
        gated_private_residual=False,
    )
    torch.testing.assert_close(
        robust_only[0], torch.as_tensor(quality.field_weights)
    )
    torch.testing.assert_close(robust_only[1], torch.ones_like(robust_only[1]))
    torch.testing.assert_close(robust_only[2], torch.zeros_like(robust_only[2]))

    isolated = batch(
        quality_weighted_loss=True,
        shared_quality_isolation=True,
        gated_private_residual=False,
    )
    torch.testing.assert_close(isolated[0], torch.as_tensor(quality.field_weights))
    torch.testing.assert_close(isolated[1], torch.as_tensor(quality.shared_weights))
    torch.testing.assert_close(isolated[2], torch.zeros_like(isolated[2]))

    gated = batch(
        quality_weighted_loss=True,
        shared_quality_isolation=True,
        gated_private_residual=True,
    )
    torch.testing.assert_close(gated[0], torch.as_tensor(quality.field_weights))
    torch.testing.assert_close(gated[1], torch.as_tensor(quality.shared_weights))
    torch.testing.assert_close(gated[2], torch.as_tensor(quality.residual_targets))

    schema = build_schema(samples[0])
    ungated_cfg = CAETrainConfig(
        token_dim=4,
        global_latent_dim=3,
        group_latent_dim=2,
        private_latent_dim=3,
        codec_width=8,
        predictor_width=8,
        predictor_layers=1,
        predictor_members=1,
        codec_epochs=1,
        predictor_epochs=1,
        minimum_samples=2,
        regime_head=True,
        gated_private_residual=False,
        mixed_precision=False,
    )
    model = networks.HierarchicalCAEModel(2, schema, ungated_cfg)
    parameters = torch.randn(2, 2)
    latent, _applicability, residual_logits = model.predictor_output(
        0, parameters
    )
    expected = model.decode_joint(
        latent, torch.zeros_like(residual_logits)
    )
    actual = model.predict_member(0, parameters)[0]
    for expected_field, actual_field in zip(expected, actual):
        torch.testing.assert_close(actual_field, expected_field)


def test_design_field_loss_cap_and_weights_do_not_drop_other_fields() -> None:
    targets = (torch.zeros(2, 1), torch.zeros(2, 1))
    predictions = (
        torch.tensor([[0.0], [10.0]]),
        torch.tensor([[2.0], [1.0]]),
    )
    losses = objectives.design_field_losses(predictions, targets)
    torch.testing.assert_close(
        losses,
        torch.tensor([[0.0, 1.5], [9.5, 0.5]]),
    )
    torch.testing.assert_close(
        objectives.field_macro_loss(predictions, targets),
        torch.tensor(2.875),
    )
    weights = torch.tensor([[1.0, 0.5], [0.25, 0.0]])
    torch.testing.assert_close(
        objectives.field_macro_loss(
            predictions,
            targets,
            field_weights=weights,
            loss_cap=1.0,
        ),
        torch.tensor(0.75 / 1.75),
    )


def test_component_identity_carries_quality_head_and_zero_observation_noise() -> None:
    selector = ("b_curve.npz", "values")
    component = hierarchical_cae(
        quality_policy=_chrono_like_policy(),
        field_layouts={selector: {"spatial_axes": ("phase",)}},
        axis_encodings={selector: {"phase": "linear"}},
    )
    assert component.train_cfg.regime_head is True
    assert component.train_cfg.robust_loss_cap == 4.0
    payload = component.configuration_payload()
    assert payload["quality_policy"]["policy_id"] == "chrono-contact-regime"
    identity = component.posterior_semantic_identity(None, None)
    assert identity["controlled_parameters"]["observation_noise_included"] is False
    assert identity["controlled_parameters"]["regime_head"] is True
    assert component.train_cfg.quality_weighted_loss is True
    assert component.train_cfg.shared_quality_isolation is True
    assert component.train_cfg.gated_private_residual is True
    with pytest.raises(TypeError):
        component.field_layouts[selector] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        component.axis_encodings[selector]["phase"] = None  # type: ignore[index]


def test_tiny_staged_fit_predicts_every_field_with_one_joint_member_identity() -> None:
    samples = tuple(_mixed_sample(index / 15.0) for index in range(16))
    schema = build_schema(samples[0])
    matrices = field_matrices(schema, samples)
    schema = replace(schema, scalers=fit_scalers(matrices, scale_floor=1.0e-6))
    standardized = standardized_field_matrices(schema, matrices)
    parameters = np.asarray(
        [[index / 15.0, (index % 4) / 3.0] for index in range(16)],
        dtype=np.float32,
    )
    policy = _chrono_like_policy()
    metadata = tuple(
        {
            "task_diagnostics": {
                "released": index % 3 != 0,
                "reattach_count": int(index % 5 == 0),
                "contacts_at_end": 0,
            }
        }
        for index in range(16)
    )
    quality = assess_quality(
        policy=policy, samples=samples, record_metadata=metadata
    )
    cfg = CAETrainConfig(
        token_dim=4,
        global_latent_dim=4,
        group_latent_dim=2,
        private_latent_dim=3,
        codec_width=8,
        predictor_width=12,
        predictor_layers=1,
        predictor_members=2,
        codec_epochs=2,
        predictor_epochs=2,
        fine_tune_epochs=0,
        batch_size=4,
        inference_batch_size=5,
        validation_fraction=0.25,
        early_stopping_patience=2,
        minimum_samples=8,
        robust_loss_cap=4.0,
        regime_head=True,
        mixed_precision=False,
    )
    model, history = training.fit_hierarchical_cae(
        input_dim=2,
        schema=schema,
        parameters=parameters,
        standardized_fields=standardized,
        quality=quality,
        device=torch.device("cpu"),
        train_cfg=cfg,
        seed=73,
    )
    fields, applicability, residual = inference.predict_hierarchical_members(
        model=model,
        parameters=parameters[:3],
        device=torch.device("cpu"),
        batch_size=2,
    )
    assert len(fields) == len(schema.layouts)
    assert fields[0].shape == (2, 3)
    assert fields[1].shape == (2, 3, 8)
    assert fields[2].shape == (2, 3, 4, 5)
    assert applicability.shape == (2, 3)
    assert residual.shape == (2, 3, 3)
    assert np.all((applicability >= 0.0) & (applicability <= 1.0))
    assert history["member_count"] == 2
    assert history["training_policy"] == (
        "design-split-field-macro-hierarchical-latent"
    )


def test_checkpoint_publish_recover_and_full_rawdata_prediction(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "hierarchical-runtime"
    init_workspace(workspace)
    (workspace / "config.py").write_text(
        'EVALUATION_MODE = "local"\n',
        encoding="utf-8",
    )
    parameter_names = tuple(job_template_api.get_parameter_names(workspace))
    width = len(parameter_names)
    population = tuple(
        tuple(
            float((row + column) % 16) / 15.0
            for column in range(width)
        )
        for row in range(16)
    )
    samples = tuple(
        _mixed_sample(float(np.mean(row))) for row in population
    )
    metadata = tuple(
        {
            "task_diagnostics": {
                "released": index % 3 != 0,
                "reattach_count": int(index % 5 == 0),
                "contacts_at_end": 0,
            }
        }
        for index in range(16)
    )
    data = NamedTrainingData(
        parameter_names=parameter_names,
        normalized_variables=population,
        raw_data=samples,
        record_metadata=metadata,
    )
    component = hierarchical_cae(
        quality_policy=_chrono_like_policy(),
        device="cpu",
        architecture_version=2,
        token_dim=4,
        global_latent_dim=4,
        group_latent_dim=2,
        private_latent_dim=3,
        codec_width=8,
        predictor_width=12,
        predictor_layers=1,
        predictor_members=2,
        codec_epochs=1,
        predictor_epochs=1,
        fine_tune_epochs=0,
        batch_size=4,
        inference_batch_size=5,
        validation_fraction=0.25,
        early_stopping_patience=1,
        minimum_samples=8,
        robust_loss_cap=4.0,
        regime_head=True,
        coordinate_readout=True,
        coordinate_width=8,
        coordinate_layers=1,
        coordinate_epochs=1,
        coordinate_points_per_field=4,
        coordinate_validation_points_per_field=5,
        coordinate_query_batch_size=7,
        mixed_precision=False,
    )
    config = load_config(workspace)
    state = runtime.train_with_config(
        config,
        generation_index=4,
        component=component,
        training_data=data,
    )
    assert state.checkpoint_path.is_file()
    assert state.namespace_manifest_path.is_file()
    assert state.bundle_path.is_file()
    predicted = runtime.predict_raw_data(
        workspace, population[:2], component=component
    )
    assert len(predicted) == 2
    assert predicted[0].field_selectors == samples[0].field_selectors

    monkeypatch.setattr(data_adapter, "_load_training_data", lambda _workspace: data)
    runtime.reset_workspace_state(workspace, component=component)
    assert runtime.has_trained_state(workspace, component=component)
    recovered = runtime._require_state(config, component=component)
    assert recovered.state_signature == state.state_signature
    assert recovered.bundle_path == state.bundle_path
    applicability = runtime.predict_applicability(
        workspace, population[:3], component=component
    )
    assert len(applicability.mean_smooth_probability) == 3
    assert len(applicability.member_smooth_probabilities) == 2
    bundle_before = state.bundle_path.read_bytes()
    coordinate = runtime.predict_field_at_coordinates(
        workspace,
        population[:2],
        component=component,
        field_selector=("c_surface.npz", "values"),
        axis_coordinates=(
            np.asarray([0.0, 0.5, 1.0]),
            np.asarray([0.375]),
        ),
    )
    assert coordinate.member_values.shape == (2, 2, 3, 1)
    assert coordinate.mean_values.shape == (2, 3, 1)
    assert np.all(np.isfinite(coordinate.member_values))
    assert coordinate.authoritative_full_grid is False
    assert state.bundle_path.read_bytes() == bundle_before

    from yadof.tools.surrogate_viewer.backend import PlotRequest
    from yadof.tools.surrogate_viewer.backend.hierarchical_checkpoints import (
        HierarchicalCAECheckpointPredictor,
        discover_hierarchical_cae_checkpoints,
    )

    discovered = discover_hierarchical_cae_checkpoints(
        config.workspace.surrogate_checkpoint_dir,
        strategy_signature=state.strategy_signature,
    )
    assert [item.generation for item in discovered] == [4]
    viewer = HierarchicalCAECheckpointPredictor(
        workspace,
        discovered[0],
        tuple(dict(item.payload) for item in samples[0].items),
    )
    plot, member_plots = viewer.predict_plot(
        (population[0],),
        PlotRequest(
            item_index=2,
            plotted_dimensions=(0,),
            fixed_values=((1, 0.375),),
        ),
    )
    assert plot.values.shape == (4,)
    assert len(member_plots) == 2
    assert all(np.all(np.isfinite(item.values)) for item in member_plots)
    assert state.bundle_path.read_bytes() == bundle_before
    context = SimpleNamespace(
        config=config, strategy_signature=state.strategy_signature
    )
    sampler = component.make_rawdata_sampler(
        context, draw_count=5, seed=91
    )
    posterior = sampler.predict(population[:2])
    assert posterior.diagnostics.unique_support == 2
    assert posterior.diagnostics.observation_noise_included is False
    assert len(posterior.draws) == 5
    assert all(len(draw.samples) == 2 for draw in posterior.draws)
    assert len(set(posterior.diagnostics.draw_sources[:2])) == 2


def test_global_deactivation_preserves_conditional_inr_return_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from yadof.surrogate import api as surrogate_api
    from yadof.surrogate.conditional_inr import scheduler as conditional_scheduler
    from yadof.surrogate.hierarchical_cae import scheduler as hierarchical_scheduler
    from yadof.surrogate.linear_subspace import scheduler as linear_subspace_scheduler

    expected = object()
    calls = []
    monkeypatch.setattr(
        conditional_scheduler,
        "deactivate_workspace",
        lambda *args, **kwargs: calls.append(("conditional", args, kwargs))
        or expected,
    )
    monkeypatch.setattr(
        hierarchical_scheduler,
        "deactivate_workspace",
        lambda *args, **kwargs: calls.append(("hierarchical", args, kwargs)),
    )
    monkeypatch.setattr(
        linear_subspace_scheduler,
        "deactivate_workspace",
        lambda *args, **kwargs: calls.append(("linear-subspace", args, kwargs)),
    )
    assert surrogate_api.deactivate_workspace("workspace") is expected
    assert [call[0] for call in calls] == [
        "conditional",
        "hierarchical",
        "linear-subspace",
    ]
