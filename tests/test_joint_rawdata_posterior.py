from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pytest

from yadof.config import DEFAULT_CONFIG, load_config
from yadof.job_template import (
    RawDataSchemaTemplate,
    RawDataTemplateError,
    task_rawdata_cost_projector,
)
from yadof.optimize.strategy import semantic_strategy_signature
from yadof.surrogate import (
    MaterializedRawDataPosterior,
    RawDataFunctionDraw,
    RawDataPosteriorDiagnostics,
    RawDataPosteriorSurrogate,
    SUPPORT_CONTINUOUS_OR_UNKNOWN,
    SUPPORT_FINITE,
    posterior_capability_identity,
    project_rawdata_sampler,
    require_rawdata_posterior_surrogate,
)
from yadof.task_snapshot import create_generation_snapshot
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


def _template_items():
    return {
        "surface.npz": {
            "values": np.zeros((2, 2), dtype=np.float64),
            "row": np.asarray([0.0, 1.0], dtype=np.float64),
            "column": np.asarray([10.0, 20.0], dtype=np.float64),
            "unit_row": np.asarray("m", dtype=np.str_),
            "unit_column": np.asarray("s", dtype=np.str_),
            "metadata": _metadata(
                (2, 2),
                (
                    {"index": 0, "size": 2, "name": "row", "values_key": "row"},
                    {
                        "index": 1,
                        "size": 2,
                        "name": "column",
                        "values_key": "column",
                    },
                ),
            ),
        },
        "curve.npz": {
            "data": np.zeros((3,), dtype=np.float64),
            "frequency": np.asarray([1.0, 2.0, 3.0], dtype=np.float64),
            "unit_frequency": np.asarray("GHz", dtype=np.str_),
            "metadata": _metadata(
                (3,),
                (
                    {
                        "index": 0,
                        "size": 3,
                        "name": "frequency",
                        "values_key": "frequency",
                    },
                ),
            ),
        },
    }


def _schema() -> RawDataSchemaTemplate:
    return RawDataSchemaTemplate.from_items(_template_items())


class _SampleBackedSampler:
    def __init__(
        self,
        schema: RawDataSchemaTemplate,
        *,
        draw_count: int,
        seed: int,
    ) -> None:
        self.schema = schema
        self.source_indices = tuple((int(seed) + 2 * index) % 3 for index in range(draw_count))
        draw_ids = tuple(
            f"seed-{int(seed)}-draw-{index:04d}" for index in range(draw_count)
        )
        self._diagnostics = RawDataPosteriorDiagnostics(
            posterior_kind="empirical_ensemble",
            requested_draw_count=draw_count,
            support_kind=SUPPORT_FINITE,
            unique_support=3,
            seed=int(seed),
            draw_ids=draw_ids,
            draw_sources=tuple(
                f"sample-function-{index}" for index in self.source_indices
            ),
            schema_signature=schema.signature,
            state_signature="fake-state-v1",
            strategy_signature="fake-strategy-v1",
            approximate=True,
            limitations=("finite sample-backed support", "uncalibrated"),
            field_selectors=schema.field_selectors,
        )
        self.predict_call_count = 0

    @property
    def diagnostics(self) -> RawDataPosteriorDiagnostics:
        return self._diagnostics

    def predict(self, population):
        self.predict_call_count += 1
        rows = tuple(tuple(float(value) for value in row) for row in population)
        offsets = (0.1, 0.2, 0.3)
        draws = []
        for draw_id, source_index in zip(
            self._diagnostics.draw_ids,
            self.source_indices,
        ):
            samples = []
            offset = offsets[source_index]
            for x, y in rows:
                joint = offset + 0.20 * x + 0.10 * y
                samples.append(
                    self.schema.reconstruct(
                        {
                            ("curve.npz", "data"): np.asarray(
                                [joint, joint + x, joint - y],
                                dtype=np.float64,
                            ),
                            ("surface.npz", "values"): np.asarray(
                                [
                                    [joint, offset + x],
                                    [offset + y, joint + x - y],
                                ],
                                dtype=np.float64,
                            ),
                        }
                    )
                )
            draws.append(RawDataFunctionDraw(draw_id, tuple(samples)))
        return MaterializedRawDataPosterior(
            population=rows,
            draws=tuple(draws),
            diagnostics=self._diagnostics.for_prediction(len(rows)),
        )


class _SampleBackedComponent:
    def __init__(self, schema: RawDataSchemaTemplate) -> None:
        self.schema = schema

    def posterior_semantic_identity(self, _config, _problem):
        return posterior_capability_identity(
            posterior_kind="empirical_ensemble",
            support_kind=SUPPORT_FINITE,
            backend_distribution="test-sample-backend",
            backend_version="1.0",
            controlled_parameters={"support_size": 3},
        )

    def semantic_identity(self, config, problem):
        return {
            "component": "test-sample-backed",
            "posterior": self.posterior_semantic_identity(config, problem),
        }

    def make_rawdata_sampler(self, _context, *, draw_count, seed):
        return _SampleBackedSampler(
            self.schema,
            draw_count=draw_count,
            seed=seed,
        )


def _workspace(root: Path) -> Path:
    init_workspace(root)
    (root / "job_template/parameters_constraints.py").write_text(
        "from yadof.job_template import Parameter\n"
        "PARAMETERS = (\n"
        "    Parameter('x', ((10.0, 20.0),)),\n"
        "    Parameter('y', ((0.0, 2.0),)),\n"
        ")\n"
        "CONSTRAINTS = ()\n",
        encoding="utf-8",
    )
    (root / "submit/calc_cost.py").write_text(
        "from yadof.job_template.cost_misc import calculate_rawdata_cost\n"
        "OBJECTIVES = ('cost_curve', 'cost_surface')\n"
        "def _loaded(views, raw_variables):\n"
        "    curve = next(view for view in views if view.data_key == 'data')\n"
        "    surface = next(view for view in views if view.data_key == 'values')\n"
        "    marker = float(curve.data.reshape(-1)[0])\n"
        "    if marker == -1.0:\n"
        "        raise ValueError('task helper fallback')\n"
        "    return (\n"
        "        float(curve.data.mean()) / 2.0 + float(raw_variables[0]) / 1000.0,\n"
        "        float(surface.data.mean()) / 2.0 + float(raw_variables[1]) / 1000.0,\n"
        "    )\n"
        "def calculate_cost(sample_rawdata, raw_variables=None):\n"
        "    marker = float(sample_rawdata[0]['data'].reshape(-1)[0])\n"
        "    if marker == -2.0:\n"
        "        return (0.2,)\n"
        "    if marker == -3.0:\n"
        "        return (float('nan'), 0.2)\n"
        "    if marker == -4.0:\n"
        "        raise RuntimeError('unhandled callback failure')\n"
        "    return calculate_rawdata_cost(\n"
        "        sample_rawdata, raw_variables,\n"
        "        objective_names=OBJECTIVES,\n"
        "        calculate_loaded_cost=_loaded,\n"
        "        error_cost=1.0,\n"
        "    )\n"
        "def get_objective_names():\n"
        "    return OBJECTIVES\n",
        encoding="utf-8",
    )
    return root


def _draw_arrays(posterior):
    output = []
    for draw in posterior.iter_draws():
        rows = []
        for sample in draw.samples:
            mapping = sample.as_mapping()
            rows.append(
                (
                    mapping["curve.npz"]["data"],
                    mapping["surface.npz"]["values"],
                )
            )
        output.append((draw.draw_id, rows))
    return output


def _assert_same_posterior(left, right) -> None:
    left_arrays = _draw_arrays(left)
    right_arrays = _draw_arrays(right)
    assert [item[0] for item in left_arrays] == [item[0] for item in right_arrays]
    for (_draw_id, left_rows), (_same, right_rows) in zip(left_arrays, right_arrays):
        assert len(left_rows) == len(right_rows)
        for left_row, right_row in zip(left_rows, right_rows):
            np.testing.assert_array_equal(left_row[0], right_row[0])
            np.testing.assert_array_equal(left_row[1], right_row[1])


def _sample_with_marker(schema: RawDataSchemaTemplate, marker: float):
    return schema.reconstruct(
        {
            ("curve.npz", "data"): np.asarray(
                [marker, 0.2, 0.3], dtype=np.float64
            ),
            ("surface.npz", "values"): np.asarray(
                [[0.2, 0.3], [0.4, 0.5]], dtype=np.float64
            ),
        }
    )


def test_schema_template_uses_exact_basename_and_main_key() -> None:
    schema = _schema()
    reversed_schema = RawDataSchemaTemplate.from_items(
        dict(reversed(tuple(_template_items().items())))
    )

    assert schema.field_selectors == (
        ("curve.npz", "data"),
        ("surface.npz", "values"),
    )
    assert schema.signature == reversed_schema.signature
    assert all(
        "rawdata_name" not in json.loads(
            str(np.asarray(field.payload["metadata"]).item())
        )
        for field in schema.fields
    )

    sample = _sample_with_marker(schema, 0.25)
    assert sample.field_selectors == schema.field_selectors
    assert tuple(item["data"].shape for item in sample.cost_items() if "data" in item) == ((3,),)

    with pytest.raises(RawDataTemplateError, match="selector set"):
        schema.reconstruct(
            {
                ("curve.npz", "data"): np.zeros((3,), dtype=np.float64),
            }
        )
    with pytest.raises(RawDataTemplateError, match="shape mismatch"):
        schema.reconstruct(
            {
                ("curve.npz", "data"): np.zeros((4,), dtype=np.float64),
                ("surface.npz", "values"): np.zeros((2, 2), dtype=np.float64),
            }
        )
    with pytest.raises(RawDataTemplateError, match="dtype mismatch"):
        schema.reconstruct(
            {
                ("curve.npz", "data"): np.zeros((3,), dtype=np.float32),
                ("surface.npz", "values"): np.zeros((2, 2), dtype=np.float64),
            }
        )

    axis_drift = sample.as_mapping()
    axis_drift["curve.npz"]["frequency"] = np.asarray(
        [1.0, 2.0, 4.0], dtype=np.float64
    )
    with pytest.raises(RawDataTemplateError, match="frozen"):
        schema.validate_sample(axis_drift)


def test_persistent_sampler_is_seeded_joint_and_chunk_permutation_invariant() -> None:
    schema = _schema()
    component = _SampleBackedComponent(schema)
    assert isinstance(component, RawDataPosteriorSurrogate)
    assert require_rawdata_posterior_surrogate(component) is component
    sampler = component.make_rawdata_sampler(None, draw_count=5, seed=7)
    population = ((0.1, 0.2), (0.7, 0.4), (0.1, 0.2))

    full = sampler.predict(population)
    same_seed = _SampleBackedSampler(schema, draw_count=5, seed=7).predict(population)
    _assert_same_posterior(full, same_seed)

    different_seed = _SampleBackedSampler(schema, draw_count=5, seed=8).predict(population)
    with pytest.raises(AssertionError):
        _assert_same_posterior(full, different_seed)

    # Predict chunks in reverse order. Persistent draw identity must not depend on
    # call order or chunk size.
    tail = sampler.predict(population[1:])
    head = sampler.predict(population[:1])
    full_arrays = _draw_arrays(full)
    head_arrays = _draw_arrays(head)
    tail_arrays = _draw_arrays(tail)
    for draw_index in range(5):
        assert full_arrays[draw_index][0] == head_arrays[draw_index][0]
        assert full_arrays[draw_index][0] == tail_arrays[draw_index][0]
        np.testing.assert_array_equal(
            full_arrays[draw_index][1][0][0],
            head_arrays[draw_index][1][0][0],
        )
        for full_row, tail_row in zip(
            full_arrays[draw_index][1][1:],
            tail_arrays[draw_index][1],
        ):
            np.testing.assert_array_equal(full_row[0], tail_row[0])
            np.testing.assert_array_equal(full_row[1], tail_row[1])

        # Repeated candidates share the exact same function value, and the first
        # scalar is jointly shared by both differently shaped fields.
        np.testing.assert_array_equal(
            full_arrays[draw_index][1][0][0],
            full_arrays[draw_index][1][2][0],
        )
        assert full_arrays[draw_index][1][0][0][0] == pytest.approx(
            full_arrays[draw_index][1][0][1][0, 0]
        )

    permutation = (2, 0, 1)
    permuted = sampler.predict(tuple(population[index] for index in permutation))
    permuted_arrays = _draw_arrays(permuted)
    for draw_index in range(5):
        for permuted_index, original_index in enumerate(permutation):
            np.testing.assert_array_equal(
                permuted_arrays[draw_index][1][permuted_index][0],
                full_arrays[draw_index][1][original_index][0],
            )
            np.testing.assert_array_equal(
                permuted_arrays[draw_index][1][permuted_index][1],
                full_arrays[draw_index][1][original_index][1],
            )

    diagnostics = sampler.diagnostics
    assert diagnostics.requested_draw_count == diagnostics.actual_draw_count == 5
    assert diagnostics.support_kind == SUPPORT_FINITE
    assert diagnostics.unique_support == 3
    assert len(set(diagnostics.draw_sources)) == 3
    json.dumps(diagnostics.as_dict(), allow_nan=False, sort_keys=True)

    with pytest.raises(ValueError, match="unique_support=None"):
        RawDataPosteriorDiagnostics(
            posterior_kind="weight_posterior",
            requested_draw_count=1,
            support_kind=SUPPORT_CONTINUOUS_OR_UNKNOWN,
            unique_support=1,
            seed=0,
            draw_ids=("draw-0",),
            draw_sources=("weights-0",),
            schema_signature=schema.signature,
            state_signature="state",
            strategy_signature="strategy",
            approximate=True,
            limitations=(),
            field_selectors=schema.field_selectors,
        )


def test_streaming_projection_matches_materialized_and_never_records(
    tmp_path: Path,
) -> None:
    schema = _schema()
    root = _workspace(tmp_path / "posterior-workspace")
    snapshot = create_generation_snapshot(load_config(root))
    population = ((0.1, 0.2), (0.7, 0.4), (0.1, 0.2))
    sampler = _SampleBackedSampler(schema, draw_count=5, seed=9)
    before_segments = tuple((root / "recorded_data").rglob("*")) if (root / "recorded_data").exists() else ()
    try:
        with task_rawdata_cost_projector(
            snapshot.config.workspace,
            schema,
        ) as projector:
            posterior = sampler.predict(population)
            materialized = projector.project(
                tuple(draw.samples for draw in posterior.iter_draws()),
                population,
                draw_ids=posterior.diagnostics.draw_ids,
            )
            chunk_one = project_rawdata_sampler(
                _SampleBackedSampler(schema, draw_count=5, seed=9),
                projector,
                population,
                candidate_chunk_size=1,
            )
            chunk_two = project_rawdata_sampler(
                _SampleBackedSampler(schema, draw_count=5, seed=9),
                projector,
                population,
                candidate_chunk_size=2,
            )

            np.testing.assert_array_equal(
                chunk_one.cost_samples,
                materialized.cost_samples,
            )
            np.testing.assert_array_equal(
                chunk_two.cost_samples,
                materialized.cost_samples,
            )
            np.testing.assert_array_equal(chunk_one.valid_mask, materialized.valid_mask)
            assert np.all(materialized.valid_mask)
            np.testing.assert_array_equal(
                materialized.cost_samples[:, 0, :],
                materialized.cost_samples[:, 2, :],
            )

            permutation = (2, 0, 1)
            permuted_population = tuple(population[index] for index in permutation)
            permuted = project_rawdata_sampler(
                _SampleBackedSampler(schema, draw_count=5, seed=9),
                projector,
                permuted_population,
                candidate_chunk_size=2,
            )
            inverse = tuple(permutation.index(index) for index in range(len(permutation)))
            np.testing.assert_array_equal(
                permuted.cost_samples[:, inverse, :],
                materialized.cost_samples,
            )
            assert chunk_one.source_diagnostics["candidate_chunk_count"] == 3
            assert chunk_two.source_diagnostics["candidate_chunk_count"] == 2

            empty_sampler = _SampleBackedSampler(schema, draw_count=5, seed=9)
            empty = project_rawdata_sampler(
                empty_sampler,
                projector,
                (),
                candidate_chunk_size=2,
            )
            assert empty.cost_samples.shape == (5, 0, 2)
            assert empty.valid_mask.shape == (5, 0)
            assert empty_sampler.predict_call_count == 0
    finally:
        snapshot.close()

    after_segments = tuple((root / "recorded_data").rglob("*")) if (root / "recorded_data").exists() else ()
    assert after_segments == before_segments


def test_projector_validity_semantics_and_bounded_failures(tmp_path: Path) -> None:
    schema = _schema()
    root = _workspace(tmp_path / "projection-failures")
    snapshot = create_generation_snapshot(load_config(root))
    valid = _sample_with_marker(schema, 0.2)
    finite_fallback = _sample_with_marker(schema, -1.0)
    wrong_width = _sample_with_marker(schema, -2.0)
    non_finite = _sample_with_marker(schema, -3.0)
    callback_error = _sample_with_marker(schema, -4.0)
    missing_field = valid.as_mapping()
    del missing_field["surface.npz"]
    axis_drift = valid.as_mapping()
    axis_drift["surface.npz"]["column"] = np.asarray(
        [10.0, 21.0], dtype=np.float64
    )
    population = tuple((0.5, 0.5) for _ in range(7))
    try:
        with task_rawdata_cost_projector(
            snapshot.config.workspace,
            schema,
            max_diagnostic_failures=3,
        ) as projector:
            result = projector.project(
                ((
                    valid,
                    finite_fallback,
                    wrong_width,
                    non_finite,
                    callback_error,
                    missing_field,
                    axis_drift,
                ),),
                population,
                draw_ids=("draw-stable",),
            )
            wrong_shape = projector.project(
                ((valid,),),
                population,
                draw_ids=("draw-shape",),
            )
    finally:
        snapshot.close()

    assert result.valid_mask.tolist() == [
        [True, True, False, False, False, False, False]
    ]
    np.testing.assert_array_equal(result.cost_samples[0, 1], [1.0, 1.0])
    assert np.isfinite(result.cost_samples[0, 0]).all()
    assert np.isnan(result.cost_samples[0, 2:]).all()
    assert result.diagnostics.invalid_count == 5
    assert result.diagnostics.failure_count == 5
    assert len(result.diagnostics.retained_failures) == 3
    assert result.diagnostics.truncated_failure_count == 2
    assert result.diagnostics.failure_type_counts == {
        "cost_callback": 1,
        "non_finite_objective": 1,
        "objective_width": 1,
        "rawdata_schema": 2,
    }
    assert not np.any(wrong_shape.valid_mask)
    assert wrong_shape.diagnostics.failure_type_counts == {"posterior_shape": 7}


def test_posterior_identity_is_semantic_and_parent_imports_stay_lazy() -> None:
    first = posterior_capability_identity(
        posterior_kind="empirical_ensemble",
        support_kind=SUPPORT_FINITE,
        backend_distribution="sample-backend",
        backend_version="1.0",
        controlled_parameters={"member_count": 3},
    )
    changed = posterior_capability_identity(
        posterior_kind="empirical_ensemble",
        support_kind=SUPPORT_FINITE,
        backend_distribution="sample-backend",
        backend_version="1.0",
        controlled_parameters={"member_count": 5},
    )
    first_signature = semantic_strategy_signature(
        {"strategy": "posterior-test", "posterior": first},
        parameter_names=("x", "y"),
        objective_names=("a", "b"),
    )
    changed_signature = semantic_strategy_signature(
        {"strategy": "posterior-test", "posterior": changed},
        parameter_names=("x", "y"),
        objective_names=("a", "b"),
    )
    assert first_signature != changed_signature

    command = (
        "import json, sys; "
        "import yadof.job_template, yadof.optimize, yadof.surrogate; "
        "names=('torch','botorch','pymoo.algorithms','matplotlib','tkinter'); "
        "print(json.dumps([name for name in names if name in sys.modules]))"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-c", command],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout) == []

    # The opt-in adapter is posterior-capable without changing the old component
    # identity or GPSAF-facing tuple API.
    from yadof.surrogate import conditional_inr, conditional_inr_posterior

    component = conditional_inr()
    assert not isinstance(component, RawDataPosteriorSurrogate)
    assert callable(component.predict_population)
    assert component.semantic_identity(DEFAULT_CONFIG, object())[
        "component_version"
    ] == 2
    assert isinstance(conditional_inr_posterior(), RawDataPosteriorSurrogate)
