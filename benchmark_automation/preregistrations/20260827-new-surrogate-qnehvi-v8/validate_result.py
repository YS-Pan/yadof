"""Validate the immutable 082609 post-access receipt and external artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

import yadof
from yadof.surrogate import PosteriorCalibrationArtifact


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent.parent.parent
RECEIPT_PATH = ROOT / "calibration_result_receipt.json"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(*, run_root: Path) -> dict[str, object]:
    receipt = _json(RECEIPT_PATH)
    root = run_root.resolve()
    expected_root = (
        REPOSITORY_ROOT / str(receipt["external_evidence"]["root"])
    ).resolve()
    _require(
        root == expected_root,
        "calibration run root does not match the frozen receipt",
    )
    summary_path = root / str(receipt["external_evidence"]["summary_path"])
    _require(
        _sha256(summary_path) == str(receipt["external_evidence"]["summary_sha256"]),
        "calibration summary hash drifted",
    )
    summary = _json(summary_path)
    _require(
        summary.get("status")
        == "complete-experimental-calibration-framework-performance-not-accepted",
        "calibration summary status drifted",
    )
    _require(summary.get("cell_count") == 6, "calibration cell count drifted")
    _require(
        summary.get("rawdata_calibrated_cell_count") == 0,
        "a rawData artifact was reclassified after access",
    )
    _require(
        summary.get("applicability_calibrated_cell_count") == 0,
        "an applicability artifact was reclassified after access",
    )
    _require(
        summary.get("access_state")
        == {
            "development_locator_accessed": True,
            "calibration_locator_accessed": True,
            "offline_test_locator_accessed": False,
            "simulator_launched": False,
        },
        "calibration access state drifted",
    )
    _require(
        summary.get("scientific_boundary")
        == {
            "v5_performance_failure_unchanged": True,
            "performance_accepted": False,
            "architecture_promoted": False,
            "artifact_transferable_to_successor": False,
            "formal_test_accessed": False,
            "complete_qnehvi_strategy_implemented": False,
            "formal_same_budget_optimization_benchmark_completed": False,
        },
        "calibration scientific boundary drifted",
    )
    by_id = {str(value["cell_id"]): dict(value) for value in summary["cells"]}
    checked = []
    for frozen in receipt["cells"]:
        cell_id = str(frozen["cell_id"])
        summary_cell = by_id.get(cell_id)
        _require(summary_cell is not None, f"missing calibration cell: {cell_id}")
        result_path = root / str(frozen["result_path"])
        artifact_path = root / str(frozen["artifact_path"])
        _require(
            _sha256(result_path) == str(frozen["result_sha256"]),
            f"result hash drifted: {cell_id}",
        )
        _require(
            _sha256(artifact_path) == str(frozen["artifact_file_sha256"]),
            f"artifact file hash drifted: {cell_id}",
        )
        result = _json(result_path)
        artifact = PosteriorCalibrationArtifact.read(artifact_path)
        _require(
            artifact.sha256 == str(frozen["artifact_self_sha256"]),
            f"artifact self hash drifted: {cell_id}",
        )
        _require(
            artifact.rawdata_status == "uncalibrated",
            f"failed rawData artifact became usable: {cell_id}",
        )
        _require(not artifact.transferable, f"artifact became transferable: {cell_id}")
        _require(
            all(field.scale == 1.0 for field in artifact.field_calibrations),
            f"failed artifact exposes a nonidentity field scale: {cell_id}",
        )
        _require(
            artifact.applicability.slope is None
            and artifact.applicability.intercept is None,
            f"failed artifact exposes applicability coefficients: {cell_id}",
        )
        _require(
            result.get("offline_test_locator_accessed") is False
            and result.get("simulator_launched") is False,
            f"cell escaped the 082609 access boundary: {cell_id}",
        )
        checked.append(
            {
                "cell_id": cell_id,
                "rawdata_status": artifact.rawdata_status,
                "applicability_status": artifact.applicability.status,
                "artifact_self_sha256": artifact.sha256,
            }
        )
    _require(len(checked) == 6, "post-access receipt cell count drifted")
    installed_origin = str(Path(yadof.__file__).resolve())
    _require(
        "site-packages" in installed_origin.casefold(),
        "result validation must use the installed wheel",
    )
    return {
        "status": "valid-experimental-fail-closed-calibration-result",
        "summary_sha256": _sha256(summary_path),
        "receipt_sha256": _sha256(RECEIPT_PATH),
        "checked_cells": checked,
        "rawdata_calibrated_cell_count": 0,
        "applicability_calibrated_cell_count": 0,
        "offline_test_locator_accessed": False,
        "simulator_launched": False,
        "performance_accepted": False,
        "installed_yadof_origin": installed_origin,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    print(json.dumps(validate(run_root=arguments.run_root), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
