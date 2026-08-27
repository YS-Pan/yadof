from __future__ import annotations

import json

import numpy as np
import pytest

from yadof.job_template import RawDataSchemaTemplate
from yadof.surrogate import (
    CALIBRATED,
    NOT_APPLICABLE,
    SUPPORT_FINITE,
    ApplicabilityCalibration,
    ApplicabilityPrediction,
    CalibratedRawDataPosteriorSampler,
    FieldSpreadCalibration,
    MaterializedRawDataPosterior,
    PosteriorCalibrationArtifact,
    RawDataFunctionDraw,
    RawDataPosteriorDiagnostics,
    calibrated_applicability_prediction,
    calibration_identity_signature,
    fit_monotone_applicability_calibration,
    select_conservative_spread_scale,
    transform_applicability_members,
)


STATE = "1" * 64
STRATEGY = "2" * 64


def _metadata(shape, axes):
    return np.asarray(
        json.dumps(
            {"schema_version": 1, "shape": list(shape), "axes": list(axes)},
            sort_keys=True,
        ),
        dtype=np.str_,
    )


def _schema() -> RawDataSchemaTemplate:
    return RawDataSchemaTemplate.from_items(
        {
            "strong.npz": {
                "values": np.zeros((2,), dtype=np.float64),
                "frequency": np.asarray([1.0, 2.0], dtype=np.float64),
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
            },
            "weak.npz": {
                "data": np.zeros((2,), dtype=np.float64),
                "time": np.asarray([0.0, 1.0], dtype=np.float64),
                "metadata": _metadata(
                    (2,),
                    (
                        {
                            "index": 0,
                            "size": 2,
                            "name": "time",
                            "values_key": "time",
                        },
                    ),
                ),
            },
        }
    )


class _Sampler:
    def __init__(self, schema, *, draw_count=3, state_signature=STATE):
        self.schema = schema
        sources = tuple(index % 3 for index in range(draw_count))
        self.sources = sources
        self._diagnostics = RawDataPosteriorDiagnostics(
            posterior_kind="empirical_predictor_ensemble",
            requested_draw_count=draw_count,
            support_kind=SUPPORT_FINITE,
            unique_support=3,
            seed=19,
            draw_ids=tuple(f"draw-{index}" for index in range(draw_count)),
            draw_sources=tuple(f"member-{index}" for index in sources),
            schema_signature=schema.signature,
            state_signature=state_signature,
            strategy_signature=STRATEGY,
            approximate=True,
            limitations=("finite uncalibrated support",),
            field_selectors=schema.field_selectors,
            observation_noise_included=False,
        )

    @property
    def diagnostics(self):
        return self._diagnostics

    def predict(self, population):
        rows = tuple(tuple(float(value) for value in row) for row in population)
        offsets = (-1.0, 0.25, 1.5)
        draws = []
        for draw_id, source in zip(
            self._diagnostics.draw_ids, self.sources, strict=True
        ):
            samples = []
            for (x,) in rows:
                strong = x + offsets[source]
                weak = 2.0 * x + (0.1, -0.3, 0.7)[source]
                samples.append(
                    self.schema.reconstruct(
                        {
                            ("strong.npz", "values"): np.asarray(
                                [strong, strong + x], dtype=np.float64
                            ),
                            ("weak.npz", "data"): np.asarray(
                                [weak, weak - x], dtype=np.float64
                            ),
                        }
                    )
                )
            draws.append(RawDataFunctionDraw(draw_id, tuple(samples)))
        return MaterializedRawDataPosterior(
            rows,
            tuple(draws),
            self._diagnostics.for_prediction(len(rows)),
        )


def _artifact(
    schema,
    *,
    state_signature=STATE,
    rawdata_status=CALIBRATED,
    applicability_status=NOT_APPLICABLE,
    slope=None,
    intercept=None,
):
    policy = {"policy_id": "test-policy", "policy_version": 1}
    fields = tuple(
        FieldSpreadCalibration(
            selector=selector,
            scale=(2.0 if selector[0] == "strong.npz" else 1.5),
            fit_design_count=40,
            candidate_scales=(1.0, 1.5, 2.0),
            target_coverages=(0.5, 0.8, 0.9),
        )
        for selector in schema.field_selectors
    )
    failure_reasons = ()
    if rawdata_status != CALIBRATED:
        fields = tuple(
            FieldSpreadCalibration(
                selector=selector,
                scale=1.0,
                fit_design_count=40,
                candidate_scales=(1.0, 1.5, 2.0),
                target_coverages=(0.5, 0.8, 0.9),
            )
            for selector in schema.field_selectors
        )
        failure_reasons = ("frozen gate failed",)
    return PosteriorCalibrationArtifact(
        artifact_id="test-calibration",
        rawdata_status=rawdata_status,
        state_signature=state_signature,
        strategy_signature=STRATEGY,
        schema_signature=schema.signature,
        posterior_kind="empirical_predictor_ensemble",
        support_kind=SUPPORT_FINITE,
        unique_support=3,
        checkpoint_hashes={
            "manifest": "3" * 64,
            "model": "4" * 64,
            "scalers": "5" * 64,
        },
        training_provenance_sha256="6" * 64,
        dataset_manifest_sha256="7" * 64,
        calibration_locator_sha256="8" * 64,
        calibration_design_ids_sha256="9" * 64,
        calibration_design_count=40,
        fold_count=2,
        seed=23,
        field_calibrations=fields,
        applicability=ApplicabilityCalibration(
            status=applicability_status,
            policy_signature=calibration_identity_signature(policy),
            fit_design_count=(40 if applicability_status != NOT_APPLICABLE else 0),
            positive_count=(20 if applicability_status != NOT_APPLICABLE else 0),
            negative_count=(20 if applicability_status != NOT_APPLICABLE else 0),
            minimum_class_count=10,
            slope=slope,
            intercept=intercept,
            failure_reason=(
                None
                if applicability_status == CALIBRATED
                else "quality policy is not configured"
            ),
        ),
        policy_identity=policy,
        label_head_loss_identity={
            "label": "smooth-vs-chatter-failure-v1",
            "head": "member-applicability-v1",
            "loss": "binary-cross-entropy-v1",
        },
        evidence={"result_sha256": "a" * 64},
        failure_reasons=failure_reasons,
    )


def _arrays(posterior, selector):
    output = []
    for draw in posterior.iter_draws():
        values = []
        for sample in draw.samples:
            mapping = sample.as_mapping()
            values.append(np.asarray(mapping[selector[0]][selector[1]]))
        output.append(values)
    return np.asarray(output, dtype=np.float64)


def test_field_calibration_preserves_mean_pairing_chunks_and_permutations():
    schema = _schema()
    base_sampler = _Sampler(schema)
    sampler = CalibratedRawDataPosteriorSampler(base_sampler, _artifact(schema))
    population = ((0.1,), (0.8,), (0.35,))
    base = base_sampler.predict(population)
    calibrated = sampler.predict(population)

    assert calibrated.diagnostics.calibrated is True
    assert calibrated.diagnostics.observation_noise_included is False
    assert calibrated.diagnostics.unique_support == 3
    assert calibrated.diagnostics.draw_sources == base.diagnostics.draw_sources
    for selector, factor in (
        (("strong.npz", "values"), 2.0),
        (("weak.npz", "data"), 1.5),
    ):
        before = _arrays(base, selector)
        after = _arrays(calibrated, selector)
        np.testing.assert_allclose(after.mean(axis=0), before.mean(axis=0), atol=1e-14)
        np.testing.assert_allclose(
            after - after.mean(axis=0),
            factor * (before - before.mean(axis=0)),
            atol=1e-14,
        )

    first = sampler.predict(population[:1])
    remainder = sampler.predict(population[1:])
    for selector in schema.field_selectors:
        chunked = np.concatenate(
            (_arrays(first, selector), _arrays(remainder, selector)), axis=1
        )
        np.testing.assert_allclose(chunked, _arrays(calibrated, selector))
    permutation = (2, 0, 1)
    permuted = sampler.predict(tuple(population[index] for index in permutation))
    for selector in schema.field_selectors:
        inverse = np.argsort(permutation)
        np.testing.assert_allclose(
            _arrays(permuted, selector)[:, inverse],
            _arrays(calibrated, selector),
        )
    duplicate = sampler.predict((population[0], population[0]))
    for selector in schema.field_selectors:
        values = _arrays(duplicate, selector)
        np.testing.assert_allclose(values[:, 0], values[:, 1])


def test_calibration_rejects_stale_state_repeated_support_and_failed_gate():
    schema = _schema()
    with pytest.raises(ValueError, match="state_signature"):
        CalibratedRawDataPosteriorSampler(
            _Sampler(schema), _artifact(schema, state_signature="f" * 64)
        )
    with pytest.raises(ValueError, match="enumerate every unique member once"):
        CalibratedRawDataPosteriorSampler(
            _Sampler(schema, draw_count=4), _artifact(schema)
        )
    with pytest.raises(RuntimeError, match="not available"):
        CalibratedRawDataPosteriorSampler(
            _Sampler(schema), _artifact(schema, rawdata_status="uncalibrated")
        )


def test_artifact_round_trip_and_tamper_detection(tmp_path):
    artifact = _artifact(_schema())
    path = artifact.write(tmp_path / "calibration.json")
    assert PosteriorCalibrationArtifact.read(path) == artifact
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["field_calibrations"][0]["scale"] = 1.5
    with pytest.raises(ValueError, match="hash mismatch"):
        PosteriorCalibrationArtifact.from_mapping(payload)


def test_spread_scale_selection_is_conservative_and_improves_coverage():
    truth = np.asarray([[0.0], [1.0], [2.0], [3.0], [4.0], [5.0]])
    center = truth + np.asarray([[0.4], [-0.4], [0.5], [-0.5], [0.4], [-0.4]])
    members = np.stack((center - 0.1, center, center + 0.1), axis=0)
    selected, table = select_conservative_spread_scale(
        members,
        truth,
        candidate_scales=(1.0, 2.0, 4.0, 8.0),
        target_coverages=(0.5, 0.8),
    )
    assert selected >= 1.0
    selected_row = next(row for row in table if row["scale"] == selected)
    assert selected_row["mean_undercoverage"] <= table[0]["mean_undercoverage"]


def test_applicability_calibration_is_monotone_member_paired_and_bound():
    labels = np.asarray([0.0] * 20 + [1.0] * 20)
    base = np.linspace(0.25, 0.75, 40)
    probabilities = np.stack(
        (
            np.clip(base - 0.08, 0.01, 0.99),
            base,
            np.clip(base + 0.08, 0.01, 0.99),
        )
    )
    slope, intercept, diagnostics = fit_monotone_applicability_calibration(
        probabilities, labels, minimum_class_count=10
    )
    transformed = transform_applicability_members(
        probabilities, slope=slope, intercept=intercept
    )
    assert diagnostics["positive_count"] == 20
    assert np.all(np.diff(transformed, axis=1) > 0.0)
    for member in range(probabilities.shape[0]):
        assert np.array_equal(
            np.argsort(probabilities[member]), np.argsort(transformed[member])
        )

    schema = _schema()
    artifact = _artifact(
        schema,
        applicability_status=CALIBRATED,
        slope=slope,
        intercept=intercept,
    )
    prediction = ApplicabilityPrediction(
        population=tuple((float(index),) for index in range(40)),
        mean_smooth_probability=tuple(float(value) for value in probabilities.mean(axis=0)),
        member_smooth_probabilities=tuple(
            tuple(float(value) for value in row) for row in probabilities
        ),
        policy_identity=artifact.policy_identity,
        state_signature=STATE,
        strategy_signature=STRATEGY,
    )
    calibrated = calibrated_applicability_prediction(prediction, artifact)
    assert calibrated.calibrated is True
    np.testing.assert_allclose(calibrated.member_smooth_probabilities, transformed)
    with pytest.raises(ValueError, match="policy_identity"):
        calibrated_applicability_prediction(
            ApplicabilityPrediction(
                population=prediction.population,
                mean_smooth_probability=prediction.mean_smooth_probability,
                member_smooth_probabilities=prediction.member_smooth_probabilities,
                policy_identity={"different": True},
                state_signature=STATE,
                strategy_signature=STRATEGY,
            ),
            artifact,
        )


def test_applicability_fit_rejects_insufficient_class_support():
    with pytest.raises(ValueError, match="insufficient class support"):
        fit_monotone_applicability_calibration(
            np.full((3, 10), 0.5),
            np.asarray([0.0] * 9 + [1.0]),
            minimum_class_count=2,
        )


def test_calibrated_diagnostics_require_method_and_artifact_hash():
    schema = _schema()
    kwargs = dict(_Sampler(schema).diagnostics.__dict__) if hasattr(
        _Sampler(schema).diagnostics, "__dict__"
    ) else None
    assert kwargs is None  # slots keep the protocol container compact.
    with pytest.raises(ValueError, match="require a method"):
        RawDataPosteriorDiagnostics(
            posterior_kind="test",
            requested_draw_count=2,
            support_kind=SUPPORT_FINITE,
            unique_support=2,
            seed=1,
            draw_ids=("a", "b"),
            draw_sources=("a", "b"),
            schema_signature=schema.signature,
            state_signature=STATE,
            strategy_signature=STRATEGY,
            approximate=True,
            limitations=(),
            field_selectors=schema.field_selectors,
            calibrated=True,
        )
