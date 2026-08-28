from __future__ import annotations

import json
from pathlib import Path

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
