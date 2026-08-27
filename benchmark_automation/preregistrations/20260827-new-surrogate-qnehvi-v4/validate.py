"""Validate Gate 0 through the v4 validation metric-adapter repair."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parent
V3_ROOT = ROOT.parent / "20260827-new-surrogate-qnehvi-v3"
REPOSITORY_ROOT = ROOT.parents[2]
AMENDMENT_PATH = ROOT / "benchmark_preregistration.amendment.json"
FAILURE_PATH = ROOT / "failed_validation_v1_receipt.json"
PLAN_PATH = ROOT / "validation_plan_v2.json"


class Gate0V4ValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate0V4ValidationError(message)


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name} must be a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_parent(dataset_manifest: Path) -> dict[str, object]:
    path = V3_ROOT / "validate.py"
    spec = importlib.util.spec_from_file_location("gate0_v3_validator", path)
    _require(spec is not None and spec.loader is not None, "cannot load v3 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.validate(dataset_manifest)
    _require(result["ok"] is True, "Gate 0 v3 validator did not pass")
    _require(result["formal_test_ready"] is False, "v3 formal test must remain blocked")
    _require(result["simulator_launched"] is False, "v3 validator launched a simulator")
    return result


def _validate_integrity(amendment: Mapping[str, object]) -> None:
    parent = amendment["parent_integrity"]
    _require(
        _sha256(V3_ROOT / "benchmark_preregistration.amendment.json")
        == parent["v3_amendment_sha256"],
        "frozen v3 amendment drifted",
    )
    _require(
        _sha256(V3_ROOT / "validation_plan.json")
        == parent["v3_validation_plan_sha256"],
        "frozen v3 validation plan drifted",
    )
    for relative, expected in amendment["artifact_integrity"].items():
        path = (ROOT / str(relative)).resolve()
        _require(path.is_file(), f"missing v4 artifact {relative}")
        _require(_sha256(path) == expected, f"v4 artifact drifted: {relative}")


def _validate_failure(failure: Mapping[str, object]) -> None:
    _require(
        failure["status"] == "failed-before-first-metric-publication",
        "v1 failure status drifted",
    )
    _require(int(failure["process_exit_code"]) == 1, "v1 exit code drifted")
    _require(int(failure["completed_cell_count"]) == 0, "v1 completed-cell count drifted")
    _require(
        failure["partition_access"]["offline_test"] is False,
        "v1 failure receipt reports offline-test access",
    )
    evidence = failure["evidence"]
    for path_key, hash_key in (
        ("run_spec_path", "run_spec_sha256"),
        ("saw_preflight_path", "saw_preflight_sha256"),
    ):
        path = REPOSITORY_ROOT / str(evidence[path_key])
        _require(path.is_file(), f"missing failed-run evidence {path}")
        _require(_sha256(path) == evidence[hash_key], f"failed-run evidence drifted: {path.name}")
    cells = (
        REPOSITORY_ROOT
        / "temp"
        / "hierarchical_cae_gate4_runs"
        / "hierarchical-cae-gate4-v2-20260827"
        / "validation_v1"
        / "cells"
    )
    _require(
        not cells.exists() or not any(cells.glob("*.json")),
        "v1 unexpectedly contains a published validation cell",
    )


def _validate_plan(plan: Mapping[str, object]) -> None:
    _require(
        plan["plan_id"]
        == "20260827-hierarchical-cae-gate4-development-validation-v2",
        "validation v2 plan ID drifted",
    )
    _require(
        plan["parent_plan"]["sha256"]
        == _sha256(V3_ROOT / "validation_plan.json"),
        "validation v2 parent-plan binding drifted",
    )
    repair = plan["metric_adapter_repair"]
    _require(int(repair["completed_v1_cell_count"]) == 0, "v1 metric reuse drifted")
    _require(
        repair["model_config_split_seed_metric_or_threshold_changed"] is False,
        "adapter repair expanded scientific scope",
    )
    runner = REPOSITORY_ROOT / str(plan["metric_implementation"])
    _require(_sha256(runner) == plan["metric_implementation_sha256"], "v2 runner hash drifted")
    _require(int(plan["expected_cell_count"]) == 116, "validation matrix size drifted")


def validate(dataset_manifest: Path) -> dict[str, object]:
    parent = _validate_parent(dataset_manifest.resolve())
    amendment = _load_json(AMENDMENT_PATH)
    failure = _load_json(FAILURE_PATH)
    plan = _load_json(PLAN_PATH)
    _validate_integrity(amendment)
    _validate_failure(failure)
    _validate_plan(plan)
    _require(
        amendment["access_state"]["offline_test_locator_accessed"] is False,
        "v4 amendment reports offline-test access",
    )
    _require(
        amendment["readiness"]["validation_v2_may_run"] is True,
        "v4 does not allow the repaired validation run",
    )
    _require(
        amendment["readiness"]["offline_test_access_allowed"] is False,
        "v4 must keep offline-test blocked",
    )
    return {
        "schema_version": 1,
        "view": "gate0-v4-metric-adapter-repair-validation",
        "ok": True,
        "preregistration_id": amendment["preregistration_id"],
        "parent_preregistration_id": parent["preregistration_id"],
        "parent_validator_ok": True,
        "failed_v1_completed_cells": 0,
        "validation_plan_id": plan["plan_id"],
        "expected_validation_cells": int(plan["expected_cell_count"]),
        "dataset_manifest_sha256": _sha256(dataset_manifest.resolve()),
        "offline_test_locator_accessed": False,
        "formal_test_ready": False,
        "simulator_launched": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = validate(args.dataset_manifest)
    except (
        Gate0V4ValidationError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
