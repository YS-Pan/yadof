from __future__ import annotations

import gc
import hashlib
import json
from pathlib import Path
import threading
from types import SimpleNamespace
import weakref

import numpy as np
import pytest

from yadof.config import load_config
from yadof.job_template import RAWDATA_SCHEMA_VERSION, NamedRawDataItem
from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.optimize import (
    bind_surrogate_prediction,
    prepare_search,
    pymoo_ga,
    search_candidates,
)
from yadof.optimize.problem_info import ProblemInfo
from yadof.recorded_data import (
    EvidenceDataset,
    calculate_cost_table,
    derive_evidence_row,
    get_evidence_dataset,
    list_records,
    record_job_result,
)
from yadof.recorded_data.session import CampaignSession
from yadof.surrogate import (
    SurrogatePrediction,
    SurrogateTrainingData,
    TrainingCancelledError,
    TrainingHandle,
    TrainingHandleState,
    materialize_training_data,
    pca_svd,
    conditional_inr,
    hierarchical_cae,
)
from yadof.surrogate.linear_subspace import runtime, scheduler
from yadof.task_snapshot import create_generation_snapshot
from yadof.tools.surrogate_viewer.backend import (
    CheckpointPredictor,
    PlotRequest,
    discover_checkpoints,
)
from yadof.tools.surrogate_viewer.backend.rawdata import flatten_samples_for_schema
from yadof.workspace.init import init_workspace


def _payload(values) -> dict[str, object]:
    array = values if np.ma.isMaskedArray(values) else np.asarray(values)
    return {
        "values": array,
        "metadata": {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": list(array.shape),
            "rawdata_name": "response",
        },
    }


def _sample(values) -> StructuredRawDataSample:
    return StructuredRawDataSample.from_items(
        (NamedRawDataItem("response.npz", _payload(values)),)
    )


def _data(
    values=(0.0, 0.25, 0.5, 0.75, 1.0),
    *,
    row_prefix: str = "row",
    transform_id: str | None = None,
) -> SurrogateTrainingData:
    rows = tuple(float(value) for value in values)
    return SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=tuple((value,) for value in rows),
        raw_data=tuple(_sample(np.asarray(value, dtype=np.float64)) for value in rows),
        row_ids=tuple(f"{row_prefix}-{index}" for index in range(len(rows))),
        evidence_ids=tuple(f"evidence-{row_prefix}-{index}" for index in range(len(rows))),
        statuses=tuple("committed:succeeded" for _ in rows),
        transform_id=transform_id,
    )


def _workspace(path: Path) -> Path:
    init_workspace(path)
    (path / "config.py").write_text('EVALUATION_MODE = "local"\n', encoding="utf-8")
    return path


def _record(root: Path, index: int, design: float, response: float) -> None:
    record_job_result(
        root,
        f"candidate_{index}",
        (design,),
        _sample(np.asarray(response, dtype=np.float64)).items,
        {
            "run_id": "explicit-fit-test",
            "optimization_index": 0,
            "generation_index": 0,
            "population_index": index,
        },
    )


def test_retained_neural_components_schedule_only_explicit_training_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from yadof.surrogate.conditional_inr import scheduler as conditional_scheduler
    from yadof.surrogate.hierarchical_cae import scheduler as cae_scheduler
    from yadof.surrogate.conditional_inr.types import TrainingData
    from yadof.surrogate.hierarchical_cae.types import NamedTrainingData

    class ForbiddenSession:
        def __getattr__(self, name):
            raise AssertionError(f"hidden session read attempted: {name}")

    context = SimpleNamespace(
        config=SimpleNamespace(
            workspace=tmp_path,
            OPTIMIZE_RANDOM_SEED=101,
            OPTIMIZE_SURROGATE_MAX_TRAINING_LAG=1,
        ),
        generation_index=4,
        session=ForbiddenSession(),
    )
    explicit = _data(values=(0.1, 0.9))
    captured = {}

    def conditional_start(_workspace, generation_index, **kwargs):
        captured["conditional"] = kwargs["_training_data"]
        assert generation_index == 4
        return SimpleNamespace(action="started")

    def cae_start(_workspace, generation_index, **kwargs):
        captured["cae"] = kwargs["_training_data"]
        assert generation_index == 4
        return SimpleNamespace(action="started")

    monkeypatch.setattr(conditional_scheduler, "start_training", conditional_start)
    monkeypatch.setattr(cae_scheduler, "start_training", cae_start)

    assert conditional_inr().start_training(context, explicit).action == "started"
    assert hierarchical_cae().start_training(context, explicit).action == "started"
    assert isinstance(captured["conditional"], TrainingData)
    assert isinstance(captured["cae"], NamedTrainingData)
    assert captured["conditional"].parameter_names == explicit.parameter_names
    assert captured["conditional"].normalized_variables == explicit.normalized_variables
    assert captured["cae"].raw_data == explicit.raw_data
    assert captured["cae"].record_metadata == explicit.record_metadata


def test_training_data_digest_separates_content_from_provenance() -> None:
    values = np.arange(6, dtype=np.float64).reshape(2, 3)
    c_order = SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=np.asarray(((0.5,),), dtype=np.float64),
        raw_data=(_sample(np.ascontiguousarray(values)),),
        row_ids=("source-a",),
        evidence_ids=("evidence-a",),
        statuses=("committed:succeeded",),
        transform_id="filter-a",
    )
    f_order = SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=np.asfortranarray(((0.5,),)),
        raw_data=(_sample(np.asfortranarray(values)),),
        row_ids=("source-b",),
        evidence_ids=("evidence-b",),
        statuses=("committed:succeeded",),
        transform_id="filter-b",
    )
    assert c_order.content_digest == f_order.content_digest
    assert c_order.provenance_digest != f_order.provenance_digest

    changed = SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=((0.5,),),
        raw_data=(_sample(values + 1.0),),
        row_ids=("source-a",),
        evidence_ids=("evidence-a",),
        statuses=("committed:succeeded",),
        transform_id="filter-a",
    )
    changed_dtype = SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=((0.5,),),
        raw_data=(_sample(values.astype(np.float32)),),
        statuses=("committed:succeeded",),
    )
    changed_shape = SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=((0.5,),),
        raw_data=(_sample(values.reshape(3, 2)),),
        statuses=("committed:succeeded",),
    )
    changed_status = SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=((0.5,),),
        raw_data=(_sample(values),),
        statuses=("derived:succeeded",),
    )
    masked_out = SurrogateTrainingData(
        parameter_names=("input_value",),
        normalized_variables=((0.5,),),
        raw_data=(_sample(values),),
        statuses=("committed:succeeded",),
        valid_mask=(False,),
    )
    assert changed.content_digest != c_order.content_digest
    assert changed_dtype.content_digest != c_order.content_digest
    assert changed_shape.content_digest != c_order.content_digest
    assert changed_status.content_digest != c_order.content_digest
    assert masked_out.content_digest != c_order.content_digest

    reordered = _data((1.0, 0.0))
    original = _data((0.0, 1.0))
    duplicated = _data((0.0, 1.0, 1.0))
    assert reordered.content_digest != original.content_digest
    assert duplicated.content_digest != original.content_digest


def test_training_data_rejects_lazy_and_non_real_targets() -> None:
    with pytest.raises(TypeError, match="materialized"):
        SurrogateTrainingData(
            parameter_names=("input_value",),
            normalized_variables=((value,) for value in (0.0, 1.0)),
            raw_data=(_sample(0.0), _sample(1.0)),
        )
    with pytest.raises(TypeError, match="materialized"):
        SurrogateTrainingData(
            parameter_names=("input_value",),
            normalized_variables=((0.0,),),
            raw_data=(sample for sample in (_sample(0.0),)),
        )
    with pytest.raises(Exception, match="mask|masked"):
        SurrogateTrainingData(
            parameter_names=("input_value",),
            normalized_variables=((0.0,),),
            raw_data=(_sample(np.ma.array([1.0], mask=[True])),),
        )
    with pytest.raises(Exception, match="non-finite"):
        SurrogateTrainingData(
            parameter_names=("input_value",),
            normalized_variables=((0.0,),),
            raw_data=(_sample(np.asarray([np.nan])),),
        )
    for values in (
        np.asarray([1 + 2j], dtype=np.complex128),
        np.asarray([object()], dtype=object),
    ):
        with pytest.raises(Exception):
            SurrogateTrainingData(
                parameter_names=("input_value",),
                normalized_variables=((0.0,),),
                raw_data=(_sample(values),),
            )


def test_stage2_identity_materializer_handles_selection_order_duplicates_and_lineage(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "materialized")
    _record(root, 0, -0.5, 0.2)
    _record(root, 1, 0.5, 0.8)
    dataset = get_evidence_dataset(root)
    snapshot = create_generation_snapshot(load_config(root))
    try:
        table = calculate_cost_table(dataset, snapshot)
    finally:
        snapshot.close()

    materialized = materialize_training_data(dataset, table)
    assert materialized.row_ids == tuple(row.row_id for row in dataset.rows)
    reversed_ids = tuple(row.row_id for row in reversed(dataset.rows))
    reversed_data = materialize_training_data(dataset, table, row_ids=reversed_ids)
    assert reversed_data.row_ids == reversed_ids
    duplicate = materialize_training_data(
        dataset,
        table,
        row_ids=(dataset.rows[0].row_id, dataset.rows[0].row_id),
    )
    assert duplicate.sample_count == 2
    assert duplicate.normalized_variables[0] == duplicate.normalized_variables[1]
    with pytest.raises(KeyError, match="missing"):
        materialize_training_data(dataset, table, row_ids=("missing",))

    derived = derive_evidence_row(
        dataset.rows[0],
        operation="scale-response",
        ordinal=0,
        rawdata_source=_sample(0.4).items,
        parameters={"factor": 2.0},
    )
    transformed = EvidenceDataset(dataset.parameter_names, (derived,), source="derived")
    snapshot = create_generation_snapshot(load_config(root))
    try:
        transformed_table = calculate_cost_table(transformed, snapshot)
    finally:
        snapshot.close()
    derived_data = materialize_training_data(
        transformed,
        transformed_table,
        transform_id="scale-v1",
    )
    assert derived_data.row_ids == (derived.row_id,)
    assert derived_data.evidence_ids == (dataset.rows[0].evidence_id,)
    assert derived_data.lineage[0][-1]["operation"] == "scale-response"
    assert derived_data.transform_id == "scale-v1"


def test_training_handle_has_cached_terminal_and_memory_release_semantics() -> None:
    created = TrainingHandle(lambda _cancel: "unused")
    assert created.state == TrainingHandleState.CREATED
    assert created.cancel() is True
    assert created.cancel() is False
    for _ in range(2):
        with pytest.raises(TrainingCancelledError, match="before start"):
            created.wait()
    created.close()
    created.close()
    assert created.state == TrainingHandleState.CLOSED
    assert created.terminal_state == TrainingHandleState.CANCELLED

    release = threading.Event()

    def finish_after_release(_cancel):
        release.wait(2.0)
        return "done"

    completed = TrainingHandle(finish_after_release).start()
    with pytest.raises(TimeoutError):
        completed.wait(0.001)
    assert completed.state == TrainingHandleState.RUNNING
    release.set()
    assert completed.wait() == "done"
    assert completed.wait() == "done"
    completed.close()
    assert completed.terminal_state == TrainingHandleState.COMPLETED

    failure = RuntimeError("fit failed")
    failed = TrainingHandle(lambda _cancel: (_ for _ in ()).throw(failure)).start()
    for _ in range(2):
        with pytest.raises(RuntimeError, match="fit failed"):
            failed.wait()
    with pytest.raises(RuntimeError, match="fit failed"):
        failed.close()
    assert failed.terminal_state == TrainingHandleState.FAILED

    entered = threading.Event()

    def cancellable(cancel_event: threading.Event):
        entered.set()
        cancel_event.wait(2.0)
        raise TrainingCancelledError("cancelled during fit")

    running = TrainingHandle(cancellable).start()
    assert entered.wait(2.0)
    assert running.cancel() is True
    with pytest.raises(TrainingCancelledError, match="during fit"):
        running.wait()
    running.close()
    assert running.terminal_state == TrainingHandleState.CANCELLED

    class Payload:
        value = 7

    payload = Payload()
    reference = weakref.ref(payload)

    def retain_until_run(_cancel, held=payload):
        return held.value

    released = TrainingHandle(retain_until_run).start()
    assert released.wait() == 7
    released.close()
    del retain_until_run, payload
    gc.collect()
    assert reference() is None


def test_runtime_cancellation_before_publication_and_commit_wins_race(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    component = pca_svd(rank=1, device="cpu")
    data = _data((0.0, 0.5, 1.0))

    cancelled_root = _workspace(tmp_path / "cancelled")
    entered_fit = threading.Event()
    release_fit = threading.Event()
    original_fit = runtime.fit_linear_subspace

    def blocked_fit(training_data, settings):
        model = original_fit(training_data, settings)
        entered_fit.set()
        assert release_fit.wait(5.0)
        return model

    monkeypatch.setattr(runtime, "fit_linear_subspace", blocked_fit)
    handle = component.start_fit(cancelled_root, data)
    assert entered_fit.wait(5.0)
    assert handle.cancel() is True
    release_fit.set()
    with pytest.raises(TrainingCancelledError):
        handle.wait()
    handle.close()
    cancelled_checkpoints = load_config(
        cancelled_root
    ).workspace.surrogate_checkpoint_dir
    assert not tuple(
        cancelled_checkpoints.glob("runs/*/components/pca-svd/generation_*.json")
    )

    monkeypatch.setattr(runtime, "fit_linear_subspace", original_fit)
    committed_root = _workspace(tmp_path / "committed")
    entered_commit = threading.Event()
    release_commit = threading.Event()
    original_write = runtime.checkpoints.write_checkpoint

    def blocked_commit(state, *, staging_dir):
        entered_commit.set()
        assert release_commit.wait(5.0)
        return original_write(state, staging_dir=staging_dir)

    monkeypatch.setattr(runtime.checkpoints, "write_checkpoint", blocked_commit)
    committed = component.start_fit(committed_root, data)
    assert entered_commit.wait(5.0)
    assert committed.cancel() is True
    release_commit.set()
    state = committed.wait()
    committed.close()
    assert committed.terminal_state == TrainingHandleState.COMPLETED
    assert state.namespace_manifest_path.is_file()

    monkeypatch.setattr(runtime.checkpoints, "write_checkpoint", original_write)
    failed_root = _workspace(tmp_path / "failed-publication")

    def fail_publication(_state, *, staging_dir):
        del staging_dir
        raise RuntimeError("publication interrupted")

    monkeypatch.setattr(runtime.checkpoints, "write_checkpoint", fail_publication)
    failed = component.start_fit(failed_root, data)
    with pytest.raises(RuntimeError, match="publication interrupted"):
        failed.wait()
    with pytest.raises(RuntimeError, match="publication interrupted"):
        failed.close()
    runtime.reset_workspace_state(failed_root)
    assert component.recover(failed_root, data) is None
    failed_checkpoints = load_config(failed_root).workspace.surrogate_checkpoint_dir
    assert not tuple(
        failed_checkpoints.glob("runs/*/components/pca-svd/generation_*.json")
    )


def test_pca_scheduler_deactivation_waits_and_releases_pending_fit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _workspace(tmp_path / "deactivate")
    started = threading.Event()
    release = threading.Event()

    def fake_train(_config, *, generation_index, **_kwargs):
        started.set()
        assert release.wait(5.0)
        return SimpleNamespace(generation_index=int(generation_index))

    monkeypatch.setattr(runtime, "train_with_config", fake_train)
    status = scheduler.start_training(
        root,
        7,
        _training_data=_data((0.0, 1.0)),
    )
    assert status.action == "started"
    assert started.wait(5.0)
    outcome: list[object] = []
    done = threading.Event()

    def deactivate() -> None:
        outcome.append(scheduler.deactivate_workspace(root))
        done.set()

    worker = threading.Thread(target=deactivate)
    worker.start()
    assert not done.wait(0.05)
    release.set()
    worker.join(5.0)
    assert not worker.is_alive()
    assert outcome[0].action == "deactivated"
    assert outcome[0].latest_completed_generation_index == 7
    assert scheduler.wait_for_pending_training(root).action == "idle"


def test_generation_boundaries_wait_normally_and_cancel_on_session_close(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "session-normal")
    config = load_config(root)
    session = CampaignSession(config)
    snapshot = session.begin_generation(config)
    component = pca_svd(rank=1, device="cpu")
    handle = component.start_fit(
        root,
        _data((0.0, 0.5, 1.0)),
        session=session,
        snapshot=snapshot,
    )
    session.finish_generation()
    assert handle.state == TrainingHandleState.CLOSED
    assert handle.terminal_state == TrainingHandleState.COMPLETED
    session.begin_generation(config)
    session.close()

    abnormal_root = _workspace(tmp_path / "session-abnormal")
    abnormal_config = load_config(abnormal_root)
    abnormal = CampaignSession(abnormal_config)
    abnormal_snapshot = abnormal.begin_generation(abnormal_config)
    entered = threading.Event()

    def runner(cancel_event: threading.Event):
        entered.set()
        cancel_event.wait(5.0)
        raise TrainingCancelledError("campaign closed")

    cancelled = TrainingHandle(
        runner,
        session=abnormal,
        snapshot=abnormal_snapshot,
    ).start()
    assert entered.wait(5.0)
    abnormal.close()
    assert cancelled.state == TrainingHandleState.CLOSED
    assert cancelled.terminal_state == TrainingHandleState.CANCELLED


def test_typed_prediction_uses_hot_snapshot_and_never_records(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "prediction")
    component = pca_svd(rank=1, ridge_alpha=0.0, device="cpu")
    data = _data((0.0, 0.5, 1.0))
    state = component.fit(root, data)
    config = load_config(root)
    old_snapshot = create_generation_snapshot(config)
    before = list_records(root)
    (root / "submit" / "calc_cost.py").write_text(
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    return (40.0 + float(sample_rawdata[0]['values'].item()),)\n"
        "def get_objective_names():\n"
        "    return ('hot_response',)\n"
        "def get_objective_count():\n"
        "    return 1\n",
        encoding="utf-8",
        newline="\n",
    )
    hot_snapshot = create_generation_snapshot(load_config(root))
    try:
        old = component.predict(state, ((0.25,),), snapshot=old_snapshot)
        hot = component.predict(state, ((0.25,),), snapshot=hot_snapshot)
        generation_context = SimpleNamespace(
            config=config,
            generation_index=0,
            population_size=1,
            random_seed=43,
            history=(),
            problem=ProblemInfo(1, 1, ("hot_response",)),
            strategy_signature="3" * 64,
            strategy_identity={},
            snapshot=hot_snapshot,
            session=None,
        )
        pool = search_candidates(
            prepare_search(
                generation_context,
                pymoo_ga(),
                population_size=1,
            ),
            1,
            origin="typed-pca-selection",
        )
        typed = component.predict_for_selection(
            generation_context,
            pool.population,
            data,
        )
        bound = bind_surrogate_prediction(pool, typed)
    finally:
        old_snapshot.close()
        hot_snapshot.close()
    assert isinstance(hot, SurrogatePrediction)
    assert hot.raw_data[0].items[0].payload["values"].flags.writeable is False
    assert hot.intervals == (((hot.costs[0][0], hot.costs[0][0]),),)
    assert hot.costs[0][0] == pytest.approx(40.25, abs=1e-8)
    assert old.costs != hot.costs
    assert isinstance(typed, SurrogatePrediction)
    assert bound.normalized_variables == pool.population
    assert bound.costs == typed.costs
    assert bound.candidate_ids == tuple(
        candidate.candidate_id for candidate in pool.candidates
    )
    assert not hasattr(bound, "raw_data")
    with pytest.raises(TypeError):
        hot.diagnostics["mutate"] = True  # type: ignore[index]
    oracle = component.fit_oracle(data.raw_data)
    with pytest.raises(TypeError, match="LinearSubspaceState"):
        component.predict(oracle, ((0.25,),), snapshot=None)
    assert list_records(root) == before


def test_pca_selection_uses_exact_compatible_lagged_state_without_training(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "lagged-selection")
    component = pca_svd(rank=1, ridge_alpha=0.0, device="cpu")
    prior = _data((0.0, 0.5), row_prefix="evidence")
    component.fit(root, prior, generation_index=2)
    current = _data((0.0, 0.5, 1.0), row_prefix="evidence")
    runtime.reset_workspace_state(root)
    config = load_config(root)
    snapshot = create_generation_snapshot(config)
    context = SimpleNamespace(
        config=config,
        generation_index=3,
        population_size=1,
        random_seed=101,
        history=(),
        problem=ProblemInfo(1, 1, ("response",)),
        strategy_signature="4" * 64,
        strategy_identity={},
        snapshot=snapshot,
        session=None,
    )
    checkpoint_root = root / ".yadof" / "surrogate" / "checkpoints"
    manifests_before = tuple(checkpoint_root.rglob("generation_*.json"))
    events_before = tuple(
        (root / "recorded_data" / "metadata" / "surrogate_training").glob(
            "*.json"
        )
    )
    try:
        assert component.latest_trained_generation(context, current) == 2
        assert component.has_trained_state(context, current)
        prediction = component.predict_for_selection(
            context,
            ((0.25,),),
            current,
        )
    finally:
        snapshot.close()
    assert prediction.training_data_digest == prior.content_digest
    assert tuple(checkpoint_root.rglob("generation_*.json")) == manifests_before
    assert tuple(
        (root / "recorded_data" / "metadata" / "surrogate_training").glob(
            "*.json"
        )
    ) == events_before

    changed = _data((0.0, 0.6, 1.0), row_prefix="evidence")
    runtime.reset_workspace_state(root)
    changed_snapshot = create_generation_snapshot(config)
    context.snapshot = changed_snapshot
    try:
        assert component.latest_trained_generation(context, changed) is None
        assert not component.has_trained_state(context, changed)
    finally:
        changed_snapshot.close()


def test_generic_viewer_discovers_predicts_plots_and_audits_pca_svd(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path / "viewer")
    component = pca_svd(rank=1, ridge_alpha=0.0, device="cpu")
    data = _data((0.0, 0.5, 1.0))
    state = component.fit(root, data, generation_index=4)
    config = load_config(root)
    checkpoints = discover_checkpoints(
        config.workspace.surrogate_checkpoint_dir,
        parameter_definition_signature=(
            job_template_api.get_parameter_definition_signature(root)
        ),
        strategy_signature=state.strategy_signature,
    )
    assert len(checkpoints) == 1
    assert checkpoints[0].member_count == 1
    assert checkpoints[0].payload["surrogate_method"] == "pca_svd"

    artifact_hash = hashlib.sha256(state.artifact_path.read_bytes()).hexdigest()
    predictor = CheckpointPredictor(
        root,
        checkpoints[0],
        data.raw_data[0].cost_items(),
    )
    samples, costs, members = predictor.predict(((0.25,),), include_members=True)
    assert float(samples[0][0]["values"]) == pytest.approx(0.25, abs=1e-8)
    assert len(costs) == 1
    assert len(members) == 1
    plot, member_plots = predictor.predict_plot(
        ((0.25,),),
        PlotRequest(item_index=0, plotted_dimensions=(), fixed_values=()),
    )
    assert float(plot.values) == pytest.approx(0.25, abs=1e-8)
    assert len(member_plots) == 1

    true_flats = flatten_samples_for_schema(predictor.schema, samples)
    audit = predictor.predict_audit_rows(
        ((0.25,),),
        true_flats,
        relative_epsilon=1e-12,
    )
    assert np.all(audit.raw_absolute_sums == 0.0)
    assert np.all(audit.raw_relative_sums == 0.0)
    assert hashlib.sha256(state.artifact_path.read_bytes()).hexdigest() == artifact_hash

    incompatible = state.namespace_manifest_path.parent / "generation_9999_old.json"
    incompatible.write_text(
        json.dumps({"surrogate_method": "pca_svd", "generation_index": 9999}),
        encoding="utf-8",
    )
    assert discover_checkpoints(
        config.workspace.surrogate_checkpoint_dir,
        parameter_definition_signature=(
            job_template_api.get_parameter_definition_signature(root)
        ),
        strategy_signature=state.strategy_signature,
    ) == checkpoints
