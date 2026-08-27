"""Validate the v7 experimental framework result and immutable v5 failure."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parent
V6_ROOT = ROOT.parent / "20260827-new-surrogate-qnehvi-v6"
REPOSITORY_ROOT = ROOT.parents[2]
AMENDMENT_PATH = ROOT / "benchmark_preregistration.amendment.json"
RECEIPT_PATH = ROOT / "offline_result_receipt.json"


class Gate0V7ValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate0V7ValidationError(message)


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
    module = _load_module("gate0_v6_validator", V6_ROOT / "validate.py")
    result = module.validate(dataset_manifest)
    _require(result["ok"] is True, "Gate 0 v6 validator did not pass")
    _require(result["v5_full_grid_gate_passed"] is False, "v5 failure drifted")
    _require(result["scientific_acceptance_authorized"] is False, "v6 acceptance drifted")
    return result


def _validate_integrity(amendment: Mapping[str, object]) -> None:
    parent = amendment["parent_integrity"]
    _require(
        _sha256(V6_ROOT / "benchmark_preregistration.amendment.json")
        == parent["v6_amendment_sha256"],
        "frozen v6 amendment drifted",
    )
    _require(
        _sha256(V6_ROOT / "experimental_framework_plan.json")
        == parent["v6_plan_sha256"],
        "frozen v6 plan drifted",
    )
    _require(
        _sha256(V6_ROOT / "experimental_offline_access_seal.json")
        == parent["v6_access_seal_sha256"],
        "frozen v6 access seal drifted",
    )
    for relative, expected in amendment["artifact_integrity"].items():
        path = (ROOT / str(relative)).resolve()
        _require(path.is_file(), f"missing v7 artifact {relative}")
        _require(_sha256(path) == expected, f"v7 artifact drifted: {relative}")


def validate(dataset_manifest: Path) -> dict[str, object]:
    parent = _validate_parent(dataset_manifest.resolve())
    amendment = _load_json(AMENDMENT_PATH)
    frozen_receipt = _load_json(RECEIPT_PATH)
    _validate_integrity(amendment)
    evidence_root = REPOSITORY_ROOT / str(amendment["external_evidence"]["root"])
    assessment = _load_module(
        "hierarchical_cae_experimental_assessment",
        REPOSITORY_ROOT
        / "benchmark_automation"
        / "hierarchical_cae_experimental_assessment.py",
    )
    current = assessment.assess(evidence_root)
    _require(current == frozen_receipt, "recomputed v7 receipt drifted")
    evidence = amendment["external_evidence"]
    _require(
        current["external_evidence"]["run_spec_sha256"]
        == evidence["run_spec_sha256"],
        "v7 run spec hash drifted",
    )
    _require(
        current["external_evidence"]["offline_summary_sha256"]
        == evidence["offline_summary_sha256"],
        "v7 offline summary hash drifted",
    )
    decision = current["scientific_decision"]
    _require(decision["v5_failure_unchanged"] is True, "v7 altered v5")
    _require(decision["performance_accepted"] is False, "v7 claims performance acceptance")
    _require(decision["coordinate_performance_accepted"] is False, "v7 claims coordinate acceptance")
    _require(decision["numeric_thresholds_after_access"] is None, "v7 inserted post-access threshold")
    _require(decision["todo_082608_may_archive"] is False, "v7 archives TODO 082608")
    mechanism = current["mechanism_result"]
    _require(all(bool(value) for key, value in mechanism.items() if key != "offline_test_used_for_training_or_early_stopping"), "v7 mechanism invariant failed")
    _require(
        mechanism["offline_test_used_for_training_or_early_stopping"] is False,
        "v7 reports offline leakage",
    )
    return {
        "schema_version": 1,
        "view": "gate0-v7-experimental-framework-result",
        "ok": True,
        "preregistration_id": amendment["preregistration_id"],
        "parent_preregistration_id": amendment["parent_preregistration_id"],
        "parent_validator_ok": parent["ok"],
        "pre_access_commit": amendment["pre_access_commit"],
        "completed_offline_cells": 12,
        "offline_test_design_count": 1200,
        "offline_test_locator_accessed": True,
        "calibration_locator_accessed": False,
        "simulator_launched": False,
        "coordinate_framework_mechanism_completed": True,
        "offline_test_path_mechanism_completed": True,
        "performance_accepted": False,
        "coordinate_performance_accepted": False,
        "scientific_acceptance_claimed": False,
        "todo_082608_may_archive": False,
        "formal_test_ready": False
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
        Gate0V7ValidationError,
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
