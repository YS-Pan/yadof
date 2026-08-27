"""Validate the v8 082609 chain without opening calibration/offline locators."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence

import yadof


ROOT = Path(__file__).resolve().parent
AUTOMATION_ROOT = ROOT.parent.parent
REPOSITORY_ROOT = AUTOMATION_ROOT.parent
PLAN_PATH = ROOT / "calibration_plan.json"
ACCESS_SEAL_PATH = ROOT / "calibration_access_seal.json"
V5_DECISION_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v5"
    / "validation_decision.json"
)
V7_AMENDMENT_PATH = (
    AUTOMATION_ROOT
    / "preregistrations"
    / "20260827-new-surrogate-qnehvi-v7"
    / "benchmark_preregistration.amendment.json"
)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                value,
                stream,
                sort_keys=True,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _validate_checkpoint_files(
    summary_path: Path, summary: Mapping[str, object]
) -> list[dict[str, object]]:
    cells = []
    for raw_cell in summary["cells"]:
        cell = dict(raw_cell)
        receipt_path = summary_path.parent / str(cell["cell_receipt_path"])
        _require(
            _sha256(receipt_path) == str(cell["cell_receipt_sha256"]),
            f"checkpoint receipt hash drifted: {receipt_path}",
        )
        receipt = _json(receipt_path)
        _require(
            receipt["status"]
            == "durable-development-only-experimental-performance-not-accepted",
            "checkpoint cell status drifted",
        )
        _require(
            receipt["calibration_locator_accessed"] is False,
            "checkpoint cell reports calibration access",
        )
        _require(
            receipt["offline_test_locator_accessed"] is False,
            "checkpoint cell reports offline-test access",
        )
        _require(
            receipt["simulator_launched"] is False,
            "checkpoint cell reports simulator launch",
        )
        checkpoint = dict(receipt["checkpoint"])
        cell_dir = receipt_path.parent
        paths = {
            "active_manifest": (
                cell_dir / str(checkpoint["active_manifest"]),
                str(checkpoint["active_manifest_sha256"]),
            ),
            "namespace_manifest": (
                cell_dir / str(checkpoint["namespace_manifest"]),
                str(checkpoint["namespace_manifest_sha256"]),
            ),
            "model": (
                cell_dir / str(checkpoint["model_path"]),
                str(checkpoint["model_sha256"]),
            ),
            "scalers": (
                cell_dir / str(checkpoint["scaler_path"]),
                str(checkpoint["scaler_sha256"]),
            ),
        }
        for name, (path, expected) in paths.items():
            _require(_sha256(path) == expected, f"{name} hash drifted: {path}")
        active = _json(paths["active_manifest"][0])
        namespace = _json(paths["namespace_manifest"][0])
        _require(active == namespace, "active/namespace checkpoint manifests differ")
        _require(
            str(active["state_signature"]) == str(receipt["state_signature"]),
            "checkpoint state signature drifted",
        )
        _require(
            str(active["strategy_signature"])
            == str(receipt["strategy_signature"]),
            "checkpoint strategy signature drifted",
        )
        _require(
            str(active["train_history"]["training_provenance_sha256"])
            == str(receipt["training_provenance_sha256"]),
            "checkpoint training provenance drifted",
        )
        cells.append(
            {
                "cell_id": str(receipt["cell_id"]),
                "state_signature": str(receipt["state_signature"]),
                "strategy_signature": str(receipt["strategy_signature"]),
                "training_provenance_sha256": str(
                    receipt["training_provenance_sha256"]
                ),
                "model_sha256": str(checkpoint["model_sha256"]),
                "scaler_sha256": str(checkpoint["scaler_sha256"]),
            }
        )
    return cells


def validate(
    *,
    dataset_manifest: Path,
    checkpoint_summary: Path,
    pre_access_commit: str,
) -> dict[str, object]:
    manifest_path = dataset_manifest.resolve()
    summary_path = checkpoint_summary.resolve()
    plan = _json(PLAN_PATH)
    seal = _json(ACCESS_SEAL_PATH)
    manifest = _json(manifest_path)
    summary = _json(summary_path)
    v5 = _json(V5_DECISION_PATH)
    v7 = _json(V7_AMENDMENT_PATH)
    commit = str(pre_access_commit).lower()
    _require(
        len(commit) == 40
        and all(char in "0123456789abcdef" for char in commit),
        "pre_access_commit must be a full lowercase Git commit",
    )
    _require(
        plan.get("protocol") == "yadof.082609.calibration-preregistration",
        "unsupported calibration preregistration protocol",
    )
    _require(int(plan.get("protocol_version", -1)) == 1, "plan version drifted")
    _require(
        plan.get("status") == "sealed-before-calibration-access",
        "calibration plan is not sealed",
    )
    integrity = dict(plan["artifact_integrity"])
    _require(
        _sha256(manifest_path) == str(integrity["dataset_manifest_sha256"]),
        "dataset manifest hash drifted",
    )
    _require(
        _sha256(summary_path)
        == str(integrity["development_checkpoint_summary_sha256"]),
        "development checkpoint summary hash drifted",
    )
    _require(
        _sha256(ACCESS_SEAL_PATH) == str(integrity["access_seal_sha256"]),
        "calibration access seal hash drifted",
    )
    _require(
        _sha256(V5_DECISION_PATH) == str(integrity["v5_decision_sha256"]),
        "v5 decision hash drifted",
    )
    _require(
        _sha256(V7_AMENDMENT_PATH) == str(integrity["v7_amendment_sha256"]),
        "v7 amendment hash drifted",
    )
    for relative, expected in dict(integrity["source_artifacts"]).items():
        path = (REPOSITORY_ROOT / str(relative)).resolve()
        _require(_sha256(path) == str(expected), f"source hash drifted: {relative}")
    _require(seal.get("status") == "sealed", "access seal is not sealed")
    _require(
        seal.get("calibration_access_authorized") is True,
        "calibration access is not authorized",
    )
    _require(
        seal.get("offline_test_access_authorized") is False,
        "offline-test access must remain forbidden",
    )
    _require(
        seal.get("dataset_manifest_sha256") == _sha256(manifest_path),
        "access seal dataset binding drifted",
    )
    calibration = dict(manifest["partition_locators"]["calibration"])
    frozen_calibration = dict(plan["partition"]["calibration_locator"])
    _require(calibration == frozen_calibration, "calibration locator receipt drifted")
    _require(int(calibration["row_count"]) == 600, "calibration count drifted")
    _require(
        summary.get("status")
        == "complete-development-only-experimental-performance-not-accepted",
        "development checkpoint summary is incomplete",
    )
    _require(int(summary.get("cell_count", -1)) == 6, "checkpoint count drifted")
    _require(
        summary.get("access_state")
        == {
            "development_locator_accessed": True,
            "calibration_locator_accessed": False,
            "offline_test_locator_accessed": False,
            "simulator_launched": False,
        },
        "checkpoint bundle access state drifted",
    )
    cells = _validate_checkpoint_files(summary_path, summary)
    _require(v5["decision"]["full_grid_gate_passed"] is False, "v5 changed")
    _require(v5["decision"]["representation_passed"] is False, "v5 changed")
    _require(v5["decision"]["quality_regime_passed"] is False, "v5 changed")
    _require(
        v7["decision"]["v5_full_grid_failure_unchanged"] is True,
        "v7 no longer preserves v5 failure",
    )
    _require(v7["decision"]["performance_accepted"] is False, "v7 changed")
    _require(
        v7["decision"]["todo_082608_may_archive"] is False,
        "082608 archive boundary changed",
    )
    installed_origin = str(Path(yadof.__file__).resolve())
    _require(
        "site-packages" in installed_origin.casefold(),
        "validator must use the installed wheel",
    )
    return {
        "protocol": "yadof.082609.pre-access-validation-receipt",
        "protocol_version": 1,
        "status": "valid-pre-access-chain",
        "pre_access_commit": commit,
        "plan_sha256": _sha256(PLAN_PATH),
        "access_seal_sha256": _sha256(ACCESS_SEAL_PATH),
        "checkpoint_summary_sha256": _sha256(summary_path),
        "dataset_manifest_sha256": _sha256(manifest_path),
        "calibration_locator": frozen_calibration,
        "checkpoint_cells": cells,
        "installed_yadof_origin": installed_origin,
        "calibration_locator_accessed": False,
        "offline_test_locator_accessed": False,
        "simulator_launched": False,
        "v5_failure_unchanged": True,
        "performance_accepted": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint-summary", type=Path, required=True)
    parser.add_argument("--pre-access-commit", required=True)
    parser.add_argument("--output-receipt", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    receipt = validate(
        dataset_manifest=arguments.dataset_manifest,
        checkpoint_summary=arguments.checkpoint_summary,
        pre_access_commit=arguments.pre_access_commit,
    )
    if arguments.output_receipt is not None:
        _write_json_atomic(arguments.output_receipt.resolve(), receipt)
    print(json.dumps(receipt, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
