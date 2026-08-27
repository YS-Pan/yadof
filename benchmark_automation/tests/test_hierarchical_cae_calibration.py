from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

import hierarchical_cae_calibration as calibration
import hierarchical_cae_dataset as dataset


def _write_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_calibration_locator_requires_explicit_authorization(tmp_path: Path) -> None:
    locator_path = tmp_path / "calibration_locator.json"
    _write_json(
        locator_path,
        {
            "protocol": dataset.LOCATOR_PROTOCOL,
            "rows": [{"design_id": "held-out-design"}],
        },
    )
    manifest_path = tmp_path / "sealed_dataset_manifest.json"
    _write_json(
        manifest_path,
        {
            "protocol": dataset.DATASET_PROTOCOL,
            "protocol_version": dataset.DATASET_PROTOCOL_VERSION,
            "partition_locators": {
                "calibration": {
                    "path": locator_path.name,
                    "sha256": _sha256(locator_path),
                    "row_count": 1,
                }
            },
        },
    )
    denied_path = tmp_path / "denied.json"
    _write_json(
        denied_path,
        {
            "status": "sealed",
            "dataset_manifest_sha256": _sha256(manifest_path),
            "calibration_access_authorized": False,
            "offline_test_access_authorized": False,
        },
    )
    with pytest.raises(PermissionError, match="do not authorize calibration"):
        dataset.load_locator_rows(
            manifest_path,
            scope="calibration",
            sealed_threshold_path=denied_path,
        )

    allowed_path = tmp_path / "allowed.json"
    _write_json(
        allowed_path,
        {
            "status": "sealed",
            "dataset_manifest_sha256": _sha256(manifest_path),
            "calibration_access_authorized": True,
            "offline_test_access_authorized": False,
        },
    )
    assert dataset.load_locator_rows(
        manifest_path,
        scope="calibration",
        sealed_threshold_path=allowed_path,
    ) == ({"design_id": "held-out-design"},)


def test_design_level_folds_are_stable_and_row_order_independent() -> None:
    design_ids = tuple(f"design-{index:04d}" for index in range(200))
    forward = calibration._folds(design_ids, seed=82609691, fold_count=2)
    reversed_ids = tuple(reversed(design_ids))
    reverse = calibration._folds(reversed_ids, seed=82609691, fold_count=2)
    reverse_by_id = dict(zip(reversed_ids, reverse, strict=True))
    assert np.array_equal(
        forward,
        np.asarray([reverse_by_id[value] for value in design_ids], dtype=np.int64),
    )
    assert np.all(np.bincount(forward, minlength=2) >= 2)


def test_cross_fitted_field_spread_preserves_member_pairing_and_mean() -> None:
    truth = np.arange(24, dtype=np.float64).reshape(12, 2) / 10.0
    center = truth + np.linspace(-0.3, 0.3, 12)[:, None]
    members = np.stack((center - 0.1, center, center + 0.1), axis=0)
    folds = calibration._folds(
        tuple(f"design-{index}" for index in range(12)),
        seed=82609691,
        fold_count=2,
    )
    adjusted, final_scale, fold_results, _ = calibration._cross_fit_spread(
        members=members,
        truth=truth,
        folds=folds,
        candidate_scales=(1.0, 2.0, 4.0, 8.0),
        target_coverages=(0.5, 0.8, 0.9),
    )
    np.testing.assert_allclose(
        adjusted.mean(axis=0), members.mean(axis=0), atol=1.0e-14
    )
    assert np.array_equal(np.argsort(adjusted, axis=0), np.argsort(members, axis=0))
    assert final_scale in (1.0, 2.0, 4.0, 8.0)
    assert {row["fold"] for row in fold_results} == {0, 1}


def test_bounded_acquisition_proxy_uses_existing_joint_backend() -> None:
    rng = np.random.default_rng(82609691)
    design_count = 48
    parameters = rng.random((design_count, 3))
    axis = np.linspace(0.05, 0.95, design_count)
    truth = np.column_stack((axis, 1.0 - axis))
    members = np.stack(
        (
            np.clip(truth + np.asarray([-0.03, 0.02]), 0.0, 1.0),
            truth,
            np.clip(truth + np.asarray([0.02, -0.03]), 0.0, 1.0),
        )
    )
    result = calibration._acquisition_proxy_one(
        members=members,
        valid=np.ones((3, design_count), dtype=bool),
        truth=truth,
        parameters=parameters,
        design_ids=tuple(f"held-out-{index}" for index in range(design_count)),
        objective_names=("objective-a", "objective-b"),
        seed=82609691,
        calibrated=True,
    )
    assert result["proxy_only_not_complete_strategy"] is True
    assert result["same_real_evaluation_budget_within_each_q"] is True
    assert result["q1"]["batch_count"] > 0
    assert result["q2"]["batch_count"] > 0
    assert result["backend_diagnostics"]["effective_unique_support"] == 3


def test_v8_preregistration_preserves_failed_performance_boundary() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "preregistrations"
        / "20260827-new-surrogate-qnehvi-v8"
    )
    plan = json.loads((root / "calibration_plan.json").read_text(encoding="utf-8"))
    seal = json.loads(
        (root / "calibration_access_seal.json").read_text(encoding="utf-8")
    )
    assert plan["status"] == "sealed-before-calibration-access"
    assert plan["parent_state"]["v5_full_grid_gate_passed"] is False
    assert plan["parent_state"]["performance_accepted"] is False
    assert plan["parent_state"]["todo_082608_may_archive"] is False
    assert plan["calibration"]["observation_noise_included"] is False
    assert plan["calibration"]["mean_change_allowed"] is False
    assert all(
        len(value) == 64 and value != "TO_FILL"
        for value in plan["artifact_integrity"]["source_artifacts"].values()
    )
    assert plan["metrics"]["acquisition_boundary"].startswith(
        "This bounded calibration-pool decision proxy"
    )
    assert seal["calibration_access_authorized"] is True
    assert seal["offline_test_access_authorized"] is False
    assert seal["frozen_scientific_boundary"]["performance_accepted"] is False
    assert (
        seal["frozen_scientific_boundary"]["calibration_may_transfer_to_successor"]
        is False
    )


def test_v8_result_receipt_is_fail_closed_and_keeps_082611_blocked() -> None:
    root = (
        Path(__file__).resolve().parents[1]
        / "preregistrations"
        / "20260827-new-surrogate-qnehvi-v8"
    )
    receipt = json.loads(
        (root / "calibration_result_receipt.json").read_text(encoding="utf-8")
    )
    assert receipt["status"] == (
        "complete-experimental-calibration-framework-performance-not-accepted"
    )
    assert receipt["aggregate_result"]["rawdata_calibrated_cell_count"] == 0
    assert receipt["aggregate_result"]["applicability_calibrated_cell_count"] == 0
    assert receipt["aggregate_result"]["all_artifact_field_scales_are_identity"]
    assert receipt["aggregate_result"][
        "all_artifact_applicability_coefficients_absent"
    ]
    assert receipt["aggregate_result"]["usable_probability_capability_for_082611"] is False
    assert len(receipt["cells"]) == 6
    assert all(cell["rawdata_status"] == "uncalibrated" for cell in receipt["cells"])
    assert all(cell["failed_checks"] for cell in receipt["cells"])
    assert receipt["access_state"] == {
        "development_locator_accessed": True,
        "calibration_locator_accessed": True,
        "offline_test_locator_accessed": False,
        "simulator_launched": False,
    }
    assert receipt["scientific_boundary"]["v5_performance_failure_unchanged"] is True
    assert receipt["scientific_boundary"]["performance_accepted"] is False
    assert receipt["scientific_boundary"]["todo_082608_may_archive"] is False
    assert receipt["scientific_boundary"]["todo_082609_may_archive"] is False
