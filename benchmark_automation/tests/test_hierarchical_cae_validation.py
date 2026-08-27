from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np

from yadof.job_template.rawdata_contract import NamedRawDataItem
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.surrogate.hierarchical_cae.schema import build_schema, field_matrices

from benchmark_automation import hierarchical_cae_validation as validation
from benchmark_automation import hierarchical_cae_gate4_assessment as assessment


def test_conditional_metric_adapter_restores_frozen_metadata_without_changing_values() -> None:
    metadata = np.asarray(
        json.dumps(
            {
                "schema_version": 1,
                "shape": [3],
                "axes": [
                    {
                        "index": 0,
                        "size": 3,
                        "name": "phase",
                        "values_key": "phase",
                    }
                ],
            },
            sort_keys=True,
        ),
        dtype=np.str_,
    )
    sample = StructuredRawDataSample.from_items(
        (
            NamedRawDataItem(
                "curve.npz",
                {
                    "values": np.asarray([1.0, 2.0, 3.0]),
                    "phase": np.asarray([0.0, 0.5, 1.0]),
                    "metadata": metadata,
                },
            ),
        )
    )
    schema = build_schema(sample)
    enriched_metadata = np.asarray(
        json.dumps(
            {
                "schema_version": 1,
                "shape": [3],
                "axes": [
                    {
                        "index": 0,
                        "size": 3,
                        "name": "phase",
                        "values_key": "phase",
                    }
                ],
                "surrogate_prediction": True,
            },
            sort_keys=True,
        ),
        dtype=np.str_,
    )
    predicted_values = np.asarray([4.0, 5.0, 6.0])
    rebuilt = validation._conditional_named_samples(
        schema,
        (
            (
                {
                    "values": predicted_values,
                    "phase": np.asarray([0.0, 0.5, 1.0]),
                    "metadata": enriched_metadata,
                },
            ),
        ),
    )
    matrices = field_matrices(schema, rebuilt)
    np.testing.assert_array_equal(matrices[0][0], predicted_values)
    assert str(rebuilt[0].items[0].payload["metadata"]) == str(metadata)


def _stats(*, mean: float, median: float | None = None, maximum: float | None = None):
    return {
        "mean": mean,
        "median": mean if median is None else median,
        "max": mean if maximum is None else maximum,
    }


def _quality_row(train_size: int, arm: str, leakage: float) -> dict[str, object]:
    return {
        "train_size": train_size,
        "arm": arm,
        "clean_target_high_frequency_leakage_rate": _stats(mean=leakage),
        "smooth_high_frequency_roughness_inflation": _stats(
            mean=1.0, median=1.0
        ),
        "regime_classifier": {
            "auprc": _stats(mean=0.5),
            "expected_calibration_error": _stats(mean=0.05),
            "brier_score": _stats(mean=0.05),
        },
        "strata_field_macro_standardized_mae": {
            key: _stats(mean=0.2)
            for key in ("smooth", "chatter", "failure", "boundary")
        },
    }


def test_gate4_threshold_application_is_fail_closed_per_size_and_ablation() -> None:
    representation = []
    for train_size, mae in ((1000, 1.05), (2000, 1.051)):
        representation.append(
            {
                "case": "synthetic",
                "train_size": train_size,
                "field_macro_standardized_mae_ratio": _stats(mean=mae),
                "field_macro_standardized_rmse_ratio": _stats(mean=1.05),
                "current_cost_macro_mae_ratio": _stats(mean=1.10),
                "worst_field_standardized_rmse_ratio": _stats(
                    mean=1.0, maximum=1.25
                ),
            }
        )
    quality = [
        _quality_row(1000, "shared-latent-isolation", 0.25),
        _quality_row(1000, "gated-private-residual", 0.20),
        _quality_row(2000, "shared-latent-isolation", 0.25),
        _quality_row(2000, "gated-private-residual", 0.30),
    ]
    thresholds = {
        "representation_thresholds": {
            f"train_{train_size}": {
                "field_macro_standardized_mae_ratio_max_vs_conditional_inr": 1.05,
                "field_macro_standardized_rmse_ratio_max_vs_conditional_inr": 1.05,
                "current_cost_macro_mae_ratio_max_vs_conditional_inr": 1.10,
                "maximum_single_field_standardized_rmse_degradation_ratio": 1.25,
            }
            for train_size in (1000, 2000)
        },
        "quality_regime_thresholds": {
            "clean_target_high_frequency_leakage_rate_max": 0.35,
            "predicted_to_real_roughness_inflation_max": 2.0,
            "regime_classifier_auprc_min": 0.3,
            "regime_probability_expected_calibration_error_max": 0.1,
            "regime_probability_brier_score_max": 0.09,
            "smooth_stratum_field_macro_error_max": 0.4,
            "chatter_stratum_field_macro_error_max": 0.4,
            "failure_stratum_field_macro_error_max": 0.4,
            "boundary_stratum_field_macro_error_max": 0.4,
            "gated_residual_vs_shared_isolation_required_improvement": 0.0,
        },
    }
    result = assessment._apply_thresholds(representation, quality, thresholds)
    assert result["representation"][0]["passed"] is True
    assert result["representation"][1]["passed"] is False
    assert result["quality_regime"][0]["passed"] is True
    assert result["quality_regime"][1]["passed"] is False
    assert result["quality_regime"][1]["checks"][
        "gated_residual_vs_shared_isolation_improvement"
    ] is False
    assert result["full_grid_gate_passed"] is False
    assert result["coordinate_gate_open"] is False
    assert result["offline_test_access_allowed"] is False


def test_gate0_v5_threshold_scope_stays_partial_without_external_evidence() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    root = (
        repository_root
        / "benchmark_automation"
        / "preregistrations"
        / "20260827-new-surrogate-qnehvi-v5"
    )
    thresholds = json.loads(
        (root / "acceptance_thresholds.082608.partial-seal.json").read_text(
            encoding="utf-8"
        )
    )
    spec = importlib.util.spec_from_file_location("gate0_v5_static", root / "validate.py")
    assert spec is not None and spec.loader is not None
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    validator._validate_threshold_scope(thresholds)
    assert thresholds["formal_test_ready"] is False
    assert thresholds["evidence"]["offline_test_locator_accessed"] is False
    assert set(thresholds["remaining_unsealed_scopes"]) == {
        "coordinate readout stored-grid/off-grid/resource thresholds",
        "082609 posterior and applicability calibration thresholds",
        "082611 qNEHVI decision and exploration thresholds",
        "082612 formal optimization and total engineering-cost thresholds",
    }


def test_gate0_v6_v7_framework_result_cannot_reverse_v5_or_backfill_thresholds() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    preregistrations = repository_root / "benchmark_automation" / "preregistrations"
    v6 = preregistrations / "20260827-new-surrogate-qnehvi-v6"
    v7 = preregistrations / "20260827-new-surrogate-qnehvi-v7"
    amendment_v6 = json.loads(
        (v6 / "benchmark_preregistration.amendment.json").read_text(encoding="utf-8")
    )
    plan = json.loads(
        (v6 / "experimental_framework_plan.json").read_text(encoding="utf-8")
    )
    amendment_v7 = json.loads(
        (v7 / "benchmark_preregistration.amendment.json").read_text(encoding="utf-8")
    )
    receipt = json.loads(
        (v7 / "offline_result_receipt.json").read_text(encoding="utf-8")
    )
    launch_failure = json.loads(
        (v7 / "pre_access_launch_failure_receipt.json").read_text(encoding="utf-8")
    )

    assert amendment_v6["decision"] == {
        "v5_full_grid_failure_unchanged": True,
        "v5_thresholds_unchanged": True,
        "coordinate_framework_implementation_allowed": True,
        "coordinate_framework_status": "experimental-performance-not-accepted",
        "offline_test_access_allowed_by_v6_for_fixed_mechanism_run": True,
        "offline_test_may_create_scientific_acceptance": False,
        "calibration_locator_access_allowed": False,
        "performance_tuning_allowed_in_this_execution_unit": False,
        "successor_architecture_allowed_in_this_execution_unit": False,
        "todo_082608_may_archive": False,
    }
    assert plan["expected_cell_count"] == 12
    assert plan["cases"] == ["saw", "chrono", "test-com"]
    assert plan["train_sizes"] == [1000, 2000]
    assert plan["model_fit_seeds"] == [69168527]
    assert plan["acceptance"]["performance_thresholds"] is None
    assert plan["acceptance"]["coordinate_numeric_thresholds"] is None

    decision = amendment_v7["decision"]
    assert decision["v5_full_grid_failure_unchanged"] is True
    assert decision["performance_accepted"] is False
    assert decision["coordinate_performance_accepted"] is False
    assert decision["numeric_thresholds_after_access"] is None
    assert decision["todo_082608_may_archive"] is False
    assert amendment_v7["external_evidence"]["completed_cell_count"] == 12
    assert amendment_v7["external_evidence"]["offline_test_design_count"] == 1200
    assert amendment_v7["external_evidence"]["calibration_locator_accessed"] is False
    assert amendment_v7["external_evidence"]["simulator_launched"] is False

    assert len(receipt["cells"]) == 12
    assert len(receipt["coordinate_descriptive_results"]) == 6
    assert len(receipt["paired_descriptive_results"]) == 6
    assert all(
        row["acceptance_decision"] is None
        and row["descriptive_only"] is True
        for row in receipt["paired_descriptive_results"]
    )
    assert receipt["mechanism_result"] == {
        "all_coordinate_queries_finite": True,
        "all_coordinate_queries_preserved_state": True,
        "coordinate_framework_executed": True,
        "full_grid_remained_authoritative": True,
        "offline_test_path_executed": True,
        "offline_test_used_for_training_or_early_stopping": False,
    }
    assert launch_failure["offline_test_locator_accessed"] is False
    assert launch_failure["training_started"] is False
    assert launch_failure["cell_count"] == 0
