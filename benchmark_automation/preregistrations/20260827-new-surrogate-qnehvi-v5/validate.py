"""Validate Gate 0 through the v5 082608 development decision."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parent
V4_ROOT = ROOT.parent / "20260827-new-surrogate-qnehvi-v4"
REPOSITORY_ROOT = ROOT.parents[2]
AMENDMENT_PATH = ROOT / "benchmark_preregistration.amendment.json"
THRESHOLDS_PATH = ROOT / "acceptance_thresholds.082608.partial-seal.json"
DECISION_PATH = ROOT / "validation_decision.json"
ASSESSMENT_PATH = REPOSITORY_ROOT / "benchmark_automation" / "hierarchical_cae_gate4_assessment.py"
PLAN_PATH = V4_ROOT / "validation_plan_v2.json"


class Gate0V5ValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate0V5ValidationError(message)


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


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_parent(dataset_manifest: Path) -> dict[str, object]:
    module = _load_module("gate0_v4_validator", V4_ROOT / "validate.py")
    result = module.validate(dataset_manifest)
    _require(result["ok"] is True, "Gate 0 v4 validator did not pass")
    _require(result["formal_test_ready"] is False, "v4 formal test unexpectedly ready")
    _require(result["simulator_launched"] is False, "v4 validator launched a simulator")
    return result


def _validate_integrity(amendment: Mapping[str, object]) -> None:
    _require(
        _sha256(V4_ROOT / "benchmark_preregistration.amendment.json")
        == amendment["parent_integrity"]["v4_amendment_sha256"],
        "frozen v4 amendment drifted",
    )
    for relative, expected in amendment["artifact_integrity"].items():
        path = (ROOT / str(relative)).resolve()
        _require(path.is_file(), f"missing v5 artifact {relative}")
        _require(_sha256(path) == expected, f"v5 artifact drifted: {relative}")


def _validate_external(amendment: Mapping[str, object]) -> Path:
    evidence = amendment["external_evidence"]
    validation_root = REPOSITORY_ROOT / str(evidence["validation_root"])
    summary = validation_root / "validation_summary.json"
    run_spec = validation_root / "run_spec.json"
    _require(summary.is_file() and run_spec.is_file(), "v5 external validation evidence is missing")
    _require(_sha256(summary) == evidence["validation_summary_sha256"], "validation summary drifted")
    _require(_sha256(run_spec) == evidence["run_spec_sha256"], "validation run spec drifted")
    _require(int(evidence["cell_count"]) == 116, "v5 cell count drifted")
    _require(int(evidence["process_exit_code"]) == 0, "v5 validation exit code drifted")
    _require(evidence["offline_test_locator_accessed"] is False, "v5 reports offline-test access")
    _require(evidence["simulator_launched_by_validation"] is False, "v5 validation reports simulator launch")
    return validation_root


def _validate_threshold_scope(thresholds: Mapping[str, object]) -> None:
    _require(
        thresholds["status"] == "sealed-082608-development-representation-and-quality-only",
        "v5 partial threshold status drifted",
    )
    _require(thresholds["formal_test_ready"] is False, "partial thresholds cannot enable formal test")
    _require(thresholds["evidence"]["offline_test_locator_accessed"] is False, "threshold evidence reports test access")
    coordinate = thresholds["coordinate_readout_activation"]
    for key in (
        "stored_grid_consistency_max",
        "off_grid_error_max",
        "wall_clock_max",
        "peak_memory_max_bytes",
    ):
        _require(coordinate[key] is None, f"coordinate threshold {key} was invented")
    _require(str(coordinate["status"]).startswith("blocked-"), "coordinate gate must remain blocked")


def validate(dataset_manifest: Path) -> dict[str, object]:
    parent = _validate_parent(dataset_manifest.resolve())
    amendment = _load_json(AMENDMENT_PATH)
    thresholds = _load_json(THRESHOLDS_PATH)
    frozen_decision = _load_json(DECISION_PATH)
    _validate_integrity(amendment)
    validation_root = _validate_external(amendment)
    _validate_threshold_scope(thresholds)
    assessment = _load_module("gate4_assessment", ASSESSMENT_PATH)
    current_decision = assessment.assess(
        validation_root=validation_root,
        plan_path=PLAN_PATH,
        thresholds_path=THRESHOLDS_PATH,
    )
    _require(current_decision == frozen_decision, "recomputed v5 decision drifted")
    decision = frozen_decision["decision"]
    _require(decision["full_grid_gate_passed"] is False, "v5 full-grid decision drifted")
    _require(decision["coordinate_gate_open"] is False, "v5 coordinate decision drifted")
    _require(decision["offline_test_access_allowed"] is False, "v5 offline-test decision drifted")
    _require(amendment["decision"]["todo_082608_may_archive"] is False, "v5 TODO status drifted")
    return {
        "schema_version": 1,
        "view": "gate0-v5-082608-development-decision",
        "ok": True,
        "preregistration_id": amendment["preregistration_id"],
        "parent_preregistration_id": parent["preregistration_id"],
        "parent_validator_ok": True,
        "completed_validation_cells": 116,
        "validation_process_exit_code": 0,
        "representation_passed": False,
        "quality_regime_passed": False,
        "full_grid_gate_passed": False,
        "coordinate_gate_open": False,
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
        Gate0V5ValidationError,
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
