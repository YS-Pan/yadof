from __future__ import annotations

import importlib.util
from pathlib import Path


AUTOMATION_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260828-integrated-acceptance-release-v10"
    / "validate.py"
)


def _validator_module():
    spec = importlib.util.spec_from_file_location(
        "integrated_acceptance_release_validator", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_integrated_release_remains_formal_benchmark_blocked() -> None:
    result = _validator_module().validate()

    assert result["status"] == "valid-integrated-framework-formal-benchmark-blocked"
    assert result["comparison_arm_count"] == 7
    assert result["current_runner_arms"] == ["nsga3", "gpsaf-conditional-inr"]
    assert set(result["missing_formal_arms"]) == {
        "hierarchical-cae-mean",
        "hierarchical-cae-qnehvi",
        "conditional-inr-qnehvi",
        "pca-svd-reconstruction",
        "hierarchical-cae-gpsaf",
    }
    assert result["formal_benchmark_start_allowed"] is False
    assert result["formal_benchmark_started"] is False
    assert result["simulator_launched"] is False
    assert set(result["todos_may_archive"].values()) == {False}


def test_release_phases_fallbacks_and_reentry_are_explicit() -> None:
    result = _validator_module().validate()

    phases = result["release_phases"]
    assert phases["phase_a"]["may_change_campaign_selection"] is False
    assert phases["phase_b"]["current_required_behavior"] == (
        "full-real-search-fallback"
    )
    assert phases["phase_b"]["surrogate_may_control_exploitation"] is False
    assert phases["phase_c"]["recommended_opt_in"] is False
    assert phases["phase_c"]["later_explicit_user_decision_required_for_default_change"] is True

    fallback = {item["condition"]: item for item in result["fallback_contract"]}
    assert fallback["typed-scientific-capability-blocked"]["classification"] == (
        "soft-fallback"
    )
    assert fallback["configured-support-reject-or-invalid-qnehvi-configuration"][
        "classification"
    ] == "hard-stop"
    assert fallback["recording-or-finalization-failure"]["required_outcome"] == (
        "abort-campaign"
    )
    assert result["formal_reentry_condition_ids"] == [f"R{i}" for i in range(1, 10)]
