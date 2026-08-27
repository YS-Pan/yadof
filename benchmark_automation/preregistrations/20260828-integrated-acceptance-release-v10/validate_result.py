"""Revalidate the v10 receipt against final wheel and bounded public evidence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import yadof
from yadof.recorded_data import list_optimization_metadata, list_records


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent.parent.parent
OUTER_ROOT = REPOSITORY_ROOT.parent
RECEIPT_PATH = ROOT / "acceptance_release_result_receipt.json"
INPUT_VALIDATOR_PATH = ROOT / "validate.py"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain one JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _mapping(value: object, label: str) -> dict[str, object]:
    _require(isinstance(value, dict), f"{label} must be an object")
    return dict(value)


def _input_validation() -> dict[str, object]:
    spec = importlib.util.spec_from_file_location(
        "integrated_acceptance_release_input_validator", INPUT_VALIDATOR_PATH
    )
    _require(spec is not None and spec.loader is not None, "cannot load input validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return dict(module.validate())


def validate_result() -> dict[str, object]:
    receipt = _json(RECEIPT_PATH)
    _require(
        receipt.get("status")
        == "complete-integrated-framework-structural-release-performance-not-accepted",
        "v10 result status drifted",
    )
    inputs = _input_validation()
    preregistration = _mapping(receipt.get("preregistration"), "preregistration")
    _require(inputs["status"] == preregistration["input_validation_status"], "input status drifted")
    _require(inputs["plan_sha256"] == preregistration["plan_sha256"], "plan hash drifted")
    _require(
        _sha256(INPUT_VALIDATOR_PATH) == preregistration["input_validator_sha256"],
        "input validator hash drifted",
    )
    _require(
        _sha256(Path(__file__).resolve()) == preregistration["result_validator_sha256"],
        "result validator hash drifted",
    )

    package = _mapping(receipt.get("final_installed_package"), "final_installed_package")
    wheel_path = REPOSITORY_ROOT / str(package["wheel_path"])
    _require(_sha256(wheel_path) == package["wheel_sha256"], "final wheel hash drifted")
    installed_origin = str(Path(yadof.__file__).resolve())
    _require("site-packages" in installed_origin.casefold(), "validator must use installed yadof")
    _require(installed_origin == package["origin"], "installed yadof origin drifted")
    _require(yadof.__version__ == package["version"], "installed yadof version drifted")
    installed_docs = Path(yadof.__file__).resolve().parent / "_resources" / "docs"
    workflow = (
        installed_docs / "user_doc" / "optimization_workflow.md"
    ).read_text(encoding="utf-8")
    architecture = (
        installed_docs / "dev_doc" / "architecture" / "00_architecture_index.md"
    ).read_text(encoding="utf-8")
    _require("Current integrated release status" in workflow, "installed user docs are stale")
    _require("Integrated release is a separate fail-closed decision layer" in architecture, "installed architecture docs are stale")

    source_hashes = _mapping(receipt.get("source_hashes"), "source_hashes")
    for relative, expected in source_hashes.items():
        path = REPOSITORY_ROOT / relative
        _require(path.is_file(), f"source evidence is missing: {relative}")
        _require(_sha256(path) == expected, f"source hash drifted: {relative}")

    structural = _mapping(receipt.get("structural_regression"), "structural_regression")
    run_root = REPOSITORY_ROOT / str(structural["run_root"])
    artifacts = _mapping(structural.get("artifact_sha256"), "artifact_sha256")
    for relative, expected in artifacts.items():
        path = run_root / relative
        _require(path.is_file(), f"structural artifact is missing: {relative}")
        _require(_sha256(path) == expected, f"structural artifact hash drifted: {relative}")

    spec = _json(run_root / "run_spec.json")
    state = _json(run_root / "run_state.json")
    collection = _json(run_root / "evidence" / "collect-0001" / "collection.json")
    report = _json(run_root / "report.json")
    _require(spec["spec_sha256"] == structural["spec_sha256"], "structural spec drifted")
    _require(spec["suite"] == "structural-full", "structural suite drifted")
    _require(spec["purpose"] == "structural", "structural purpose drifted")
    _require(state["status"] == "completed", "structural run is not complete")
    state_cells = _mapping(state.get("cells"), "run cells")
    _require(len(state_cells) == int(structural["cell_count"]), "structural cell count drifted")
    _require(all(cell["status"] == "completed" for cell in state_cells.values()), "a structural cell is not complete")
    report_structural = _mapping(report.get("structural"), "structural report")
    _require(report_structural["contract_satisfied"] is True, "structural contract failed")
    checks = list(report_structural["checks"])
    _require(len(checks) == int(structural["check_count"]), "structural check count drifted")
    _require(all(check["ok"] is True for check in checks), "a structural check failed")

    attempted = 0
    completed = 0
    failed = 0
    for cell in _mapping(collection.get("cells"), "collection cells").values():
        metrics = _mapping(cell.get("metrics"), "cell metrics")
        attempted += int(metrics["attempted_real_evaluations"])
        completed += int(metrics["record_status_counts"].get("completed", 0))
        failed += int(metrics["record_status_counts"].get("error", 0))
    _require(attempted == int(structural["attempted_evaluations"]), "attempt total drifted")
    _require(completed == int(structural["completed_evaluations"]), "completed total drifted")
    _require(failed == int(structural["failed_evaluations"]), "failed total drifted")

    canary = _mapping(receipt.get("v9_fallback_revalidation"), "v9_fallback_revalidation")
    canary_workspace = OUTER_ROOT / str(canary["workspace"])
    records = list_records(canary_workspace)
    metadata = list_optimization_metadata(canary_workspace)
    _require(len(records) == int(canary["public_record_count"]), "v9 record count drifted")
    _require(len(metadata) == 1, "v9 metadata count drifted")
    latest = metadata[0]
    diagnostics = dict(latest["diagnostics"])
    _require(latest["surrogate_used"] is False, "v9 canary used a surrogate")
    _require(diagnostics["fallback_reason"] == canary["fallback_reason"], "v9 fallback drifted")
    _require(diagnostics["evaluation_handoff"] == canary["evaluation_handoff"], "v9 handoff drifted")

    validation = _mapping(receipt.get("validation"), "validation")
    for name, result in validation.items():
        result_map = _mapping(result, name)
        _require(int(result_map["failed"]) == 0, f"validation failed: {name}")

    boundary = _mapping(receipt.get("scientific_boundary"), "scientific_boundary")
    _require(boundary["architecture_performance_accepted"] is False, "performance boundary opened")
    _require(boundary["transferable_calibration_available"] is False, "calibration boundary opened")
    _require(boundary["formal_benchmark_started"] is False, "formal benchmark unexpectedly started")
    _require(boundary["recommended_opt_in"] is False, "recommendation boundary opened")
    _require(boundary["package_default_changed"] is False, "package default changed")
    _require(all(value is False for value in boundary["todos_may_archive"].values()), "a TODO was archived")
    return {
        "protocol": "yadof.082612.integrated-acceptance-result-validation",
        "protocol_version": 1,
        "status": "valid-complete-integrated-framework-structural-release-performance-not-accepted",
        "receipt_sha256": _sha256(RECEIPT_PATH),
        "wheel_sha256": package["wheel_sha256"],
        "structural_run_id": structural["run_id"],
        "structural_contract_satisfied": True,
        "structural_cells_completed": len(state_cells),
        "attempted_evaluations": attempted,
        "completed_evaluations": completed,
        "failed_evaluations": failed,
        "fallback_reason": diagnostics["fallback_reason"],
        "formal_benchmark_started": False,
        "scientific_acceptance": False,
        "recommended_opt_in": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate_result(), sort_keys=True, allow_nan=False))
