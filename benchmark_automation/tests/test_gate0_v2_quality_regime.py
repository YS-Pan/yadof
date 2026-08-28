from __future__ import annotations

import json
from pathlib import Path


AMENDMENT = (
    Path(__file__).resolve().parents[1]
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v2"
    / "benchmark_preregistration.amendment.json"
)


def test_gate0_v2_preserves_v1_and_freezes_quality_regime_without_test_access() -> None:
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))

    assert amendment["status"] == "gate-0-v2-frozen-formal-benchmark-blocked"
    assert len(amendment["required_ablations"]) == 4
    assert amendment["thresholds"]["numeric_values_all_null"] is True
    assert amendment["thresholds"]["formal_test_ready"] is False
    assert amendment["readiness"]["simulator_launched_by_preregistration"] is False
