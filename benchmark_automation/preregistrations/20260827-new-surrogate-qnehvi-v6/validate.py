"""Validate Gate 0 through the v6 experimental continuation decision."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parent
V5_ROOT = ROOT.parent / "20260827-new-surrogate-qnehvi-v5"
REPOSITORY_ROOT = ROOT.parents[2]
AMENDMENT_PATH = ROOT / "benchmark_preregistration.amendment.json"
PLAN_PATH = ROOT / "experimental_framework_plan.json"
ACCESS_SEAL_PATH = ROOT / "experimental_offline_access_seal.json"


class Gate0V6ValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate0V6ValidationError(message)


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
    module = _load_module("gate0_v5_validator", V5_ROOT / "validate.py")
    result = module.validate(dataset_manifest)
    _require(result["ok"] is True, "Gate 0 v5 validator did not pass")
    _require(result["full_grid_gate_passed"] is False, "v5 failure drifted")
    _require(result["coordinate_gate_open"] is False, "v5 coordinate gate drifted")
    _require(
        result["offline_test_locator_accessed"] is False,
        "v5 reports offline-test access",
    )
    return result


def _validate_integrity(amendment: Mapping[str, object]) -> None:
    parent = amendment["parent_integrity"]
    _require(
        _sha256(V5_ROOT / "benchmark_preregistration.amendment.json")
        == parent["v5_amendment_sha256"],
        "frozen v5 amendment drifted",
    )
    _require(
        _sha256(V5_ROOT / "acceptance_thresholds.082608.partial-seal.json")
        == parent["v5_thresholds_sha256"],
        "frozen v5 thresholds drifted",
    )
    _require(
        _sha256(V5_ROOT / "validation_decision.json")
        == parent["v5_decision_sha256"],
        "frozen v5 decision drifted",
    )
    for relative, expected in amendment["artifact_integrity"].items():
        path = (ROOT / str(relative)).resolve()
        _require(path.is_file(), f"missing v6 artifact {relative}")
        _require(_sha256(path) == expected, f"v6 artifact drifted: {relative}")


def validate(dataset_manifest: Path) -> dict[str, object]:
    dataset_manifest = dataset_manifest.resolve()
    parent = _validate_parent(dataset_manifest)
    amendment = _load_json(AMENDMENT_PATH)
    plan = _load_json(PLAN_PATH)
    access = _load_json(ACCESS_SEAL_PATH)
    _validate_integrity(amendment)
    _require(
        _sha256(dataset_manifest) == plan["dataset_manifest_sha256"],
        "v6 plan does not bind the dataset manifest",
    )
    _require(
        access["dataset_manifest_sha256"] == plan["dataset_manifest_sha256"],
        "v6 access seal dataset binding drifted",
    )
    _require(access["status"] == "sealed", "v6 access seal is not sealed")
    _require(
        access["offline_test_access_authorized"] is True,
        "v6 access seal must authorize the fixed offline mechanism run",
    )
    _require(
        access["calibration_access_authorized"] is False,
        "v6 must not authorize calibration access",
    )
    _require(
        access["scientific_acceptance_authorized"] is False,
        "v6 must not authorize scientific acceptance",
    )
    _require(
        plan["acceptance"]["performance_thresholds"] is None
        and plan["acceptance"]["coordinate_numeric_thresholds"] is None,
        "v6 invented numeric acceptance thresholds",
    )
    _require(
        plan["acceptance"]["todo_082608_may_archive"] is False,
        "v6 cannot archive TODO 082608",
    )
    _require(
        amendment["decision"]["v5_full_grid_failure_unchanged"] is True,
        "v6 altered the v5 failure",
    )
    for relative, expected in plan["artifact_integrity"][
        "source_artifacts"
    ].items():
        path = REPOSITORY_ROOT / str(relative)
        _require(path.is_file(), f"missing v6 source artifact {relative}")
        _require(
            _sha256(path) == expected,
            f"v6 source artifact drifted: {relative}",
        )
    _require(int(plan["expected_cell_count"]) == 12, "v6 cell count drifted")
    return {
        "schema_version": 1,
        "view": "gate0-v6-experimental-framework-continuation",
        "ok": True,
        "preregistration_id": amendment["preregistration_id"],
        "parent_preregistration_id": amendment["parent_preregistration_id"],
        "parent_validator_ok": parent["ok"],
        "v5_full_grid_gate_passed": False,
        "v5_failure_unchanged": True,
        "coordinate_framework_status": "experimental-performance-not-accepted",
        "experimental_offline_access_ready": True,
        "offline_test_locator_accessed": False,
        "calibration_locator_accessed": False,
        "scientific_acceptance_authorized": False,
        "todo_082608_may_archive": False,
        "formal_test_ready": False,
        "simulator_launched": False
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
        Gate0V6ValidationError,
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
