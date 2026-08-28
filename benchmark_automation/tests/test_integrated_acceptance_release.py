from __future__ import annotations

import json
from pathlib import Path


AUTOMATION_ROOT = Path(__file__).resolve().parents[1]
PREREGISTRATION_ROOT = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260828-integrated-acceptance-release-v10"
)


def _load(name: str) -> dict[str, object]:
    return json.loads((PREREGISTRATION_ROOT / name).read_text(encoding="utf-8"))


def test_integrated_release_remains_formal_benchmark_blocked() -> None:
    plan = _load("acceptance_release_plan.json")
    receipt = _load("acceptance_release_result_receipt.json")

    assert receipt["status"] == (
        "complete-integrated-framework-structural-release-performance-not-accepted"
    )
    matrix = plan["formal_comparison_matrix"]
    assert len(matrix) == 7
    assert [row["current_runner_arm"] for row in matrix if row["current_runner_arm"]] == [
        "gpsaf-conditional-inr",
        "nsga3",
    ]
    assert {row["id"] for row in matrix if row["current_runner_arm"] is None} == {
        "hierarchical-cae-mean",
        "hierarchical-cae-qnehvi",
        "conditional-inr-qnehvi",
        "pca-svd-reconstruction",
        "hierarchical-cae-gpsaf",
    }
    boundary = receipt["scientific_boundary"]
    assert boundary["formal_benchmark_started"] is False
    assert boundary["scientific_acceptance_completed"] is False
    assert set(boundary["todos_may_archive"].values()) == {False}


def test_release_phases_fallbacks_and_reentry_are_explicit() -> None:
    plan = _load("acceptance_release_plan.json")

    phases = plan["release_phases"]
    assert phases["phase_a"]["may_change_campaign_selection"] is False
    assert phases["phase_b"]["current_required_behavior"] == (
        "full-real-search-fallback"
    )
    assert phases["phase_b"]["surrogate_may_control_exploitation"] is False
    assert phases["phase_c"]["recommended_opt_in"] is False
    assert phases["phase_c"]["later_explicit_user_decision_required_for_default_change"] is True

    fallback = {
        item["condition"]: item
        for item in plan["fallback_and_hard_stop_contract"]
    }
    assert fallback["typed-scientific-capability-blocked"]["classification"] == (
        "soft-fallback"
    )
    assert fallback["configured-support-reject-or-invalid-qnehvi-configuration"][
        "classification"
    ] == "hard-stop"
    assert fallback["recording-or-finalization-failure"]["required_outcome"] == (
        "abort-campaign"
    )
    assert [item["id"] for item in plan["formal_reentry_conditions"]] == [
        f"R{i}" for i in range(1, 10)
    ]
