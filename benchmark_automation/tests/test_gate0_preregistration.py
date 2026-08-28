from __future__ import annotations

import json
from pathlib import Path


AUTOMATION_ROOT = Path(__file__).resolve().parents[1]
PREREGISTRATION_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi"
    / "benchmark_preregistration.json"
)


def test_gate0_artifacts_match_current_baselines_and_remain_formal_blocked() -> None:
    registration = json.loads(PREREGISTRATION_PATH.read_text(encoding="utf-8"))

    assert registration["status"] == "gate-0-frozen-formal-benchmark-blocked"
    assert registration["readiness"]["formal_benchmark_runnable"] is False
    assert registration["readiness"]["eligible_frozen_dataset_available"] is False
    assert registration["thresholds"]["status"] == "unsealed"
    assert registration["thresholds"]["formal_test_ready"] is False
    suite = registration["current_automation_contract"][
        "performance_suite_at_registration"
    ]
    assert suite["cases"] == ["saw", "chrono", "test-com"]
    assert suite["arms"] == ["nsga3", "gpsaf-conditional-inr"]
    assert suite["total_attempted_evaluations"] == 12000
