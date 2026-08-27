from __future__ import annotations

import importlib.util
from pathlib import Path


VALIDATOR = (
    Path(__file__).resolve().parents[1]
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v2"
    / "validate.py"
)


def test_gate0_v2_preserves_v1_and_freezes_quality_regime_without_test_access() -> None:
    spec = importlib.util.spec_from_file_location(
        "gate0_v2_quality_regime_validator", VALIDATOR
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    result = module.validate()

    assert result["ok"] is True
    assert result["parent_validator_ok"] is True
    assert result["quality_protocol_id"] == "new-surrogate-quality-regime-v1"
    assert result["required_ablation_count"] == 4
    assert result["null_threshold_count"] == 25
    assert result["formal_test_ready"] is False
    assert result["simulator_launched"] is False
