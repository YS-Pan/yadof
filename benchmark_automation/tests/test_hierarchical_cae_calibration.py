from __future__ import annotations

import json
from pathlib import Path

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
