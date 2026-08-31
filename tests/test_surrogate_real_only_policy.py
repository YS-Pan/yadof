from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from yadof.surrogate.conditional_inr import checkpoints, modeling, runtime
from yadof.optimize import prepare_search, pymoo_ga, search_candidates
from yadof.optimize.gpsaf.phases import predict_pool
from yadof.optimize.problem_info import ProblemInfo
from yadof.surrogate.conditional_inr.types import (
    RawArraySlot,
    RawDataSchema,
    SurrogateState,
    TargetScaler,
)
from yadof.tools.surrogate_viewer.backend import discover_checkpoints


def test_field_macro_loss_is_invariant_to_slot_duplication() -> None:
    base = modeling._field_macro_smooth_l1(
        torch.tensor([[2.0, 4.0]]),
        torch.zeros((1, 2)),
        beta=1.0,
        field_ids=torch.tensor([0, 1]),
    )
    duplicated = modeling._field_macro_smooth_l1(
        torch.tensor([[2.0, 2.0, 2.0, 2.0, 4.0]]),
        torch.zeros((1, 5)),
        beta=1.0,
        field_ids=torch.tensor([0, 0, 0, 0, 1]),
    )

    assert float(duplicated) == pytest.approx(float(base))


def test_target_scaler_uses_standard_scores_and_allows_extrapolation() -> None:
    values = np.asarray(
        [
            [0.0, 10.0],
            [2.0, 10.0 + 1.0e-8],
            [4.0, 10.0 + 2.0e-8],
        ],
        dtype=np.float64,
    )

    scaler = runtime._fit_scaler(values, scale_floor=0.25)
    transformed = scaler.transform(values)

    np.testing.assert_allclose(scaler.mean, [2.0, 10.0 + 1.0e-8])
    np.testing.assert_allclose(scaler.scale, [np.sqrt(8.0 / 3.0), 0.25])
    np.testing.assert_allclose(np.mean(transformed, axis=0), [0.0, 0.0], atol=1.0e-6)
    np.testing.assert_allclose(scaler.inverse(transformed), values, atol=1.0e-7)
    assert scaler.inverse(np.asarray([[2.0, 0.0]], dtype=np.float32))[0, 0] > 4.0


def test_conditional_inr_centers_inputs_and_has_unbounded_linear_output() -> None:
    config = modeling.INRTrainConfig(
        hidden_dim=8,
        hidden_layers=1,
        x_latent_dim=4,
        field_emb_dim=2,
        coord_fourier_features=2,
    )
    model = modeling.build_inr_model(3, 1, config)
    encoder_inputs: list[torch.Tensor] = []
    hook = model.x_encoder.register_forward_pre_hook(
        lambda _module, args: encoder_inputs.append(args[0].detach().clone())
    )
    try:
        model.encode_x(torch.tensor([[0.0, 0.5, 1.0]], dtype=torch.float32))
    finally:
        hook.remove()
    torch.testing.assert_close(
        encoder_inputs[0],
        torch.tensor([[-1.0, 0.0, 1.0]], dtype=torch.float32),
    )

    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        output_layer = model.decoder.net[-1]
        assert isinstance(output_layer, torch.nn.Linear)
        output_layer.bias.fill_(2.0)
    prediction = model(
        torch.full((1, 3), 0.5, dtype=torch.float32),
        torch.zeros((1, 2, 3), dtype=torch.float32),
        torch.zeros((1, 2), dtype=torch.long),
    )
    torch.testing.assert_close(prediction, torch.full((1, 2), 2.0))


def test_conditional_inr_rejects_incompatible_bounded_output_artifacts(
    tmp_path: Path,
) -> None:
    (tmp_path / "inr_meta.json").write_text(
        json.dumps(
            {
                "model": "conditional_inr_rawdata_deep_ensemble",
                "input_dim": 1,
                "n_fields": 1,
                "member_count": 1,
                "train_cfg": {},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="architecture version 0"):
        modeling.load_inr_artifacts(tmp_path, torch.device("cpu"))


def test_field_balanced_query_sampling_is_seeded_balanced_and_rotating() -> None:
    fields = np.repeat(np.arange(3, dtype=np.int64), 10)
    first = modeling._field_balanced_query_indices(
        field_ids=fields,
        sample_count=7,
        seed=123,
        step_index=4,
    )
    repeated = modeling._field_balanced_query_indices(
        field_ids=fields,
        sample_count=7,
        seed=123,
        step_index=4,
    )

    assert first is not None
    assert np.array_equal(first, repeated)
    assert len(first) == len(np.unique(first)) == 7
    counts = np.bincount(fields[first], minlength=3)
    assert sorted(counts.tolist()) == [2, 2, 3]

    rotating_fields = np.repeat(np.arange(5, dtype=np.int64), 2)
    selected_fields = set()
    for step in range(5):
        indices = modeling._field_balanced_query_indices(
            field_ids=rotating_fields,
            sample_count=2,
            seed=7,
            step_index=step,
        )
        assert indices is not None
        assert len(np.unique(rotating_fields[indices])) == 2
        selected_fields.update(int(value) for value in rotating_fields[indices])
    assert selected_fields == set(range(5))

    unequal_fields = np.asarray([0] * 8 + [1] * 3 + [2], dtype=np.int64)
    unequal = modeling._field_balanced_query_indices(
        field_ids=unequal_fields,
        sample_count=6,
        seed=99,
        step_index=0,
    )
    assert unequal is not None
    assert np.bincount(unequal_fields[unequal], minlength=3).tolist() == [3, 2, 1]

    one_per_field = modeling._field_balanced_query_indices(
        field_ids=np.repeat(np.arange(4, dtype=np.int64), 3),
        sample_count=4,
        seed=99,
        step_index=0,
    )
    assert one_per_field is not None
    assert np.bincount(
        np.repeat(np.arange(4, dtype=np.int64), 3)[one_per_field],
        minlength=4,
    ).tolist() == [1, 1, 1, 1]

    coverage_fields = np.repeat(np.arange(2, dtype=np.int64), 8)
    coverage_steps = [
        modeling._field_balanced_query_indices(
            field_ids=coverage_fields,
            sample_count=4,
            seed=123,
            step_index=step,
        )
        for step in range(4)
    ]
    for field_id in range(2):
        seen = [
            int(index)
            for indices in coverage_steps
            for index in indices
            if int(coverage_fields[index]) == field_id
        ]
        assert len(seen) == len(set(seen)) == 8


def test_trainer_extends_short_runs_until_every_field_is_seen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_fields: list[set[int]] = []
    real_loss = modeling._field_macro_smooth_l1

    def capture_loss(pred, target, *, beta, field_ids):
        observed_fields.append(
            {int(value) for value in field_ids.detach().cpu().tolist()}
        )
        return real_loss(
            pred,
            target,
            beta=beta,
            field_ids=field_ids,
        )

    monkeypatch.setattr(modeling, "_field_macro_smooth_l1", capture_loss)
    config = modeling.INRTrainConfig(
        epochs=1,
        ensemble_size=1,
        batch_size=2,
        train_query_sample_count=2,
        bootstrap_members=False,
        hidden_dim=8,
        hidden_layers=1,
        x_latent_dim=4,
        field_emb_dim=2,
        coord_fourier_features=2,
    )
    _model, history = modeling.fit_deep_ensemble_conditional_inr(
        input_dim=1,
        n_fields=5,
        X_train=np.linspace(0.0, 1.0, 12, dtype=np.float32).reshape(12, 1),
        Y_train=np.arange(120, dtype=np.float32).reshape(12, 10),
        coord_table=np.zeros((10, 3), dtype=np.float32),
        field_ids=np.repeat(np.arange(5, dtype=np.int64), 2),
        device=torch.device("cpu"),
        train_cfg=config,
        seed=11,
    )

    assert history["effective_epochs"] == 2
    assert history["effective_training_steps"] == 10
    assert len(observed_fields) == 10
    assert set().union(*observed_fields) == set(range(5))
    appearances = {
        field_id: sum(field_id in step_fields for step_fields in observed_fields)
        for field_id in range(5)
    }
    assert set(appearances.values()) == {4}


def test_bootstrap_members_only_receive_rows_from_real_training_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[tuple[np.ndarray, np.ndarray]] = []

    def capture_member(_model, **kwargs):
        captured.append((kwargs["X_train"].copy(), kwargs["Y_train"].copy()))
        return {
            "loss": 0.0,
            "configured_epochs": 1.0,
            "effective_epochs": 1.0,
            "effective_training_steps": 1.0,
            "field_coverage_steps": 1.0,
        }

    monkeypatch.setattr(modeling, "_train_one_member", capture_member)
    x_train = np.arange(8, dtype=np.float32).reshape(4, 2)
    y_train = np.arange(12, dtype=np.float32).reshape(4, 3)
    config = modeling.INRTrainConfig(
        ensemble_size=2,
        bootstrap_members=True,
        bootstrap_fraction=1.0,
        hidden_dim=8,
        hidden_layers=1,
        x_latent_dim=4,
        field_emb_dim=2,
        coord_fourier_features=2,
    )

    modeling.fit_deep_ensemble_conditional_inr(
        input_dim=2,
        n_fields=2,
        X_train=x_train,
        Y_train=y_train,
        coord_table=np.zeros((3, 3), dtype=np.float32),
        field_ids=np.asarray([0, 0, 1], dtype=np.int64),
        device=torch.device("cpu"),
        train_cfg=config,
        seed=41,
    )

    real_rows = {
        tuple(x_row.tolist() + y_row.tolist())
        for x_row, y_row in zip(x_train, y_train)
    }
    assert len(captured) == 2
    for visible_x, visible_y in captured:
        assert all(
            tuple(x_row.tolist() + y_row.tolist()) in real_rows
            for x_row, y_row in zip(visible_x, visible_y)
        )


def test_default_ensemble_members_receive_every_real_training_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[np.ndarray] = []

    def capture_member(_model, **kwargs):
        captured.append(kwargs["X_train"].copy())
        return {
            "loss": 0.0,
            "configured_epochs": 1.0,
            "effective_epochs": 1.0,
            "effective_training_steps": 1.0,
            "field_coverage_steps": 1.0,
        }

    monkeypatch.setattr(modeling, "_train_one_member", capture_member)
    x_train = np.arange(200, dtype=np.float32).reshape(100, 2)
    config = modeling.INRTrainConfig(
        ensemble_size=3,
        hidden_dim=8,
        hidden_layers=1,
        x_latent_dim=4,
        field_emb_dim=2,
        coord_fourier_features=2,
    )

    _model, history = modeling.fit_deep_ensemble_conditional_inr(
        input_dim=2,
        n_fields=1,
        X_train=x_train,
        Y_train=np.arange(200, dtype=np.float32).reshape(100, 2),
        coord_table=np.zeros((2, 3), dtype=np.float32),
        field_ids=np.zeros((2,), dtype=np.int64),
        device=torch.device("cpu"),
        train_cfg=config,
        seed=41,
    )

    from yadof.surrogate.conditional_inr.settings import (
        DEFAULT_CONDITIONAL_INR_SETTINGS,
    )

    assert DEFAULT_CONDITIONAL_INR_SETTINGS.bootstrap_members is False
    assert config.bootstrap_members is False
    assert history["bootstrap_requested"] is False
    assert history["bootstrap_applied"] is False
    assert len(captured) == 3
    assert all(np.array_equal(visible_x, x_train) for visible_x in captured)


def test_sparse_high_dimensional_training_preserves_all_real_rows_per_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[np.ndarray] = []

    def capture_member(_model, **kwargs):
        captured.append(kwargs["X_train"].copy())
        return {
            "loss": 0.0,
            "configured_epochs": 1.0,
            "effective_epochs": 1.0,
            "effective_training_steps": 1.0,
            "field_coverage_steps": 1.0,
        }

    monkeypatch.setattr(modeling, "_train_one_member", capture_member)
    x_train = np.arange(24, dtype=np.float32).reshape(4, 6)
    config = modeling.INRTrainConfig(
        ensemble_size=2,
        bootstrap_members=True,
        hidden_dim=8,
        hidden_layers=1,
        x_latent_dim=4,
        field_emb_dim=2,
        coord_fourier_features=2,
    )

    _model, history = modeling.fit_deep_ensemble_conditional_inr(
        input_dim=6,
        n_fields=1,
        X_train=x_train,
        Y_train=np.arange(8, dtype=np.float32).reshape(4, 2),
        coord_table=np.zeros((2, 3), dtype=np.float32),
        field_ids=np.zeros((2,), dtype=np.int64),
        device=torch.device("cpu"),
        train_cfg=config,
        seed=41,
    )

    assert history["bootstrap_requested"] is True
    assert history["bootstrap_applied"] is False
    assert history["bootstrap_min_sample_count"] == 12
    assert len(captured) == 2
    assert all(np.array_equal(visible_x, x_train) for visible_x in captured)


def test_optimizer_records_discard_member_spread() -> None:
    import yadof.surrogate.api as surrogate_api

    class StubSurrogate:
        def __init__(self, interval) -> None:
            self.interval = interval

        def predict_population(self, _context, _rows):
            return (((0.2,), (self.interval,)),)

    config = SimpleNamespace(
        OPTIMIZE_ARCHIVE_KEY_DECIMALS=10,
        OPTIMIZE_POPULATION_SIZE=1,
    )
    context = SimpleNamespace(
        config=config,
        problem=ProblemInfo(1, 1, ("objective",)),
        population_size=1,
        random_seed=41,
        generation_index=0,
        history=(),
        strategy_signature="1" * 64,
        snapshot=SimpleNamespace(interpretation_fingerprint="2" * 64),
    )
    pool = search_candidates(
        prepare_search(context, pymoo_ga()),
        1,
        origin="test",
    )
    wide = predict_pool(
        StubSurrogate((-1000.0, 1000.0)),
        context,
        pool,
    )
    narrow = predict_pool(
        StubSurrogate((0.19, 0.21)),
        context,
        pool,
    )

    assert wide.costs == narrow.costs
    assert not hasattr(wide, "intervals")
    assert not hasattr(surrogate_api, "evaluate_historical_errors")


def _dummy_publication(
    root: Path,
    *,
    generation: int,
) -> tuple[SurrogateState, Path]:
    strategy_signature = "1" * 64
    schema = RawDataSchema(
        templates=({"data": np.zeros((1,), dtype=np.float32)},),
        modeled_slots=(
            RawArraySlot(0, "data", (1,), "float32", 0, 1, 0),
        ),
        flat_dim=1,
        coord_table=np.zeros((1, 3), dtype=np.float32),
        field_ids=np.zeros((1,), dtype=np.int64),
    )
    train_cfg = modeling.INRTrainConfig(
        ensemble_size=1,
        hidden_dim=8,
        hidden_layers=1,
        x_latent_dim=4,
        field_emb_dim=2,
        coord_fourier_features=2,
    )
    signature = checkpoints.semantic_state_signature(
        strategy_signature=strategy_signature,
        parameter_names=("x",),
        parameter_definition_signature={"parameters": (), "constraints": ()},
        schema=schema,
        train_cfg=train_cfg,
    )
    (
        checkpoint_path,
        namespace_manifest_path,
        artifact_dir,
        staged_artifact_dir,
        run_namespace,
        component_namespace,
    ) = checkpoints.new_publication_paths(
        root,
        generation_index=generation,
        strategy_signature=strategy_signature,
    )
    staged_artifact_dir.mkdir(parents=True)
    model = modeling.build_inr_model(1, 1, train_cfg)
    modeling.save_inr_artifacts(
        model,
        staged_artifact_dir,
        input_dim=1,
        n_fields=1,
        train_cfg=train_cfg,
    )
    state = SurrogateState(
        generation_index=generation,
        sample_count=4,
        checkpoint_path=checkpoint_path,
        namespace_manifest_path=namespace_manifest_path,
        model_path=artifact_dir / "model_aux.npz",
        artifact_dir=artifact_dir,
        model_name="conditional_inr_rawdata_deep_ensemble",
        strategy_signature=strategy_signature,
        state_signature=signature,
        run_namespace=run_namespace,
        component_namespace=component_namespace,
        parameter_names=("x",),
        parameter_definition_signature={"parameters": (), "constraints": ()},
        schema=schema,
        scaler=TargetScaler(
            mean=np.zeros((1,), dtype=np.float32),
            scale=np.ones((1,), dtype=np.float32),
        ),
        model=model,
        train_cfg=train_cfg,
        device=torch.device("cpu"),
        train_history={
            "member_count": 1,
            "skipped": False,
            "training_policy": "real_field_balanced",
        },
    )
    return state, staged_artifact_dir


@pytest.mark.parametrize("failure_boundary", ("active", "namespace"))
def test_failed_atomic_publication_keeps_the_previous_checkpoint_valid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_boundary: str,
) -> None:
    first, first_staging = _dummy_publication(tmp_path, generation=2)
    checkpoints.write_checkpoint(first, staged_artifact_dir=first_staging)
    original_payload = json.loads(first.namespace_manifest_path.read_text(encoding="utf-8"))
    assert len(discover_checkpoints(tmp_path)) == 1
    loaded, input_dim, n_fields, loaded_cfg = modeling.load_inr_artifacts(
        first.artifact_dir,
        torch.device("cpu"),
    )
    assert loaded is not None
    assert (input_dim, n_fields, loaded_cfg) == (1, 1, first.train_cfg)

    second, second_staging = _dummy_publication(tmp_path, generation=2)
    real_atomic_write = checkpoints._atomic_write_json

    failed_path = (
        second.checkpoint_path
        if failure_boundary == "active"
        else second.namespace_manifest_path
    )

    def fail_manifest(path: Path, payload: dict[str, object]) -> None:
        if Path(path) == failed_path:
            raise OSError(f"injected {failure_boundary}-manifest failure")
        real_atomic_write(path, payload)

    monkeypatch.setattr(checkpoints, "_atomic_write_json", fail_manifest)
    with pytest.raises(OSError, match="injected"):
        checkpoints.write_checkpoint(second, staged_artifact_dir=second_staging)

    assert json.loads(
        first.namespace_manifest_path.read_text(encoding="utf-8")
    ) == original_payload
    visible = discover_checkpoints(tmp_path)
    assert len(visible) == 1
    assert visible[0].payload["artifact_dir"] == original_payload["artifact_dir"]
    recovered_dir = checkpoints.resolve_artifact_dir(tmp_path, visible[0].payload)
    recovered, input_dim, n_fields, recovered_cfg = modeling.load_inr_artifacts(
        recovered_dir,
        torch.device("cpu"),
    )
    assert recovered is not None
    assert (input_dim, n_fields, recovered_cfg) == (1, 1, first.train_cfg)
    assert second.artifact_dir.is_dir()
