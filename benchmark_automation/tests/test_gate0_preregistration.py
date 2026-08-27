from __future__ import annotations

import importlib.util
from pathlib import Path


AUTOMATION_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi"
    / "validate.py"
)


def _validator_module():
    spec = importlib.util.spec_from_file_location("gate0_preregistration_validator", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate0_artifacts_match_current_baselines_and_remain_formal_blocked() -> None:
    module = _validator_module()

    result = module.validate()

    assert result["ok"] is True
    assert result["formal_test_ready"] is False
    assert result["data_status"] == "no-eligible-frozen-dataset"
    assert result["threshold_status"] == "unsealed-template"
    assert result["registration_environment_frozen"] is True
    assert result["pychrono_version_evidence"] == "conda-record:10.0.0"
    assert {case: details["field_count"] for case, details in result["cases"].items()} == {
        "saw": 2,
        "chrono": 16,
        "test-com": 9,
    }


def test_design_split_is_row_order_independent_disjoint_and_nested() -> None:
    module = _validator_module()
    task_fingerprint = "f" * 64
    design_ids = [
        module.canonical_design_id("case", task_fingerprint, (index / 3000.0, 0.25))
        for index in range(2800)
    ]

    forward = module.assign_design_splits(
        design_ids,
        case_id="case",
        task_fingerprint_value=task_fingerprint,
    )
    reversed_result = module.assign_design_splits(
        reversed(design_ids),
        case_id="case",
        task_fingerprint_value=task_fingerprint,
    )

    assert forward == reversed_result
    partitions = forward["partitions"]
    assert {name: len(values) for name, values in partitions.items()} == {
        "test": 400,
        "calibration": 200,
        "validation": 200,
        "train_pool": 2000,
    }
    partition_sets = [set(values) for values in partitions.values()]
    assert sum(map(len, partition_sets)) == len(set().union(*partition_sets)) == 2800
    views = forward["training_views"]
    assert len(views["warmup_diagnostic"]) == 400
    assert len(views["train_1000"]) == 1000
    assert len(views["train_2000"]) == 2000
    assert set(views["warmup_diagnostic"]) <= set(views["train_1000"]) <= set(views["train_2000"])
