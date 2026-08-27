"""Assess the fixed v6 offline mechanism evidence without setting thresholds."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Mapping, Sequence


PROTOCOL = "yadof.gate0-v6.experimental-coordinate-offline-mechanism"
EXPECTED_STATUS = "completed-experimental-performance-not-accepted"


class ExperimentalAssessmentError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ExperimentalAssessmentError(message)


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(
                value,
                stream,
                indent=2,
                sort_keys=True,
                ensure_ascii=False,
                allow_nan=False,
            )
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _maximum(rows: Sequence[Mapping[str, object]], key: str) -> float:
    return max(float(row[key]) for row in rows)


def assess(evidence_root: Path) -> dict[str, object]:
    evidence_root = evidence_root.resolve()
    summary_path = evidence_root / "offline_summary.json"
    run_spec_path = evidence_root / "run_spec.json"
    summary = _json(summary_path)
    run_spec = _json(run_spec_path)
    _require(summary["protocol"] == PROTOCOL, "offline summary protocol drifted")
    _require(summary["status"] == EXPECTED_STATUS, "offline summary status drifted")
    _require(int(summary["completed_cell_count"]) == 12, "offline cell count drifted")
    _require(int(summary["expected_cell_count"]) == 12, "expected cell count drifted")
    _require(int(summary["offline_test_design_count"]) == 1200, "test design count drifted")
    _require(summary["offline_test_locator_accessed"] is True, "offline test was not accessed")
    _require(summary["calibration_locator_accessed"] is False, "calibration was accessed")
    _require(summary["simulator_launched"] is False, "offline runner launched a simulator")
    _require(summary["scientific_acceptance_claimed"] is False, "summary claims acceptance")
    _require(summary["todo_082608_may_archive"] is False, "summary archives TODO 082608")
    _require(summary["v5_failure_unchanged"] is True, "summary altered v5 failure")
    _require(
        summary["coordinate_numeric_acceptance_thresholds"] is None,
        "post-access coordinate threshold was inserted",
    )
    _require(run_spec["calibration_locator_accessed"] is False, "run spec accessed calibration")
    _require(run_spec["simulator_launched"] is False, "run spec launched simulator")
    _require(run_spec["scientific_acceptance_claimed"] is False, "run spec claims acceptance")

    cells = []
    coordinate_rows = []
    for entry in summary["cells"]:
        cell_id = str(entry["cell_id"])
        path = evidence_root / "cells" / f"{cell_id}.json"
        _require(path.is_file(), f"missing offline cell {cell_id}")
        _require(_sha256(path) == entry["sha256"], f"offline cell drifted: {cell_id}")
        cell = _json(path)
        _require(cell["status"] == "completed", f"offline cell incomplete: {cell_id}")
        _require(cell["offline_test_locator_accessed"] is True, f"cell lacks test access: {cell_id}")
        _require(cell["calibration_locator_accessed"] is False, f"cell accessed calibration: {cell_id}")
        _require(cell["simulator_launched"] is False, f"cell launched simulator: {cell_id}")
        _require(cell["scientific_acceptance_claimed"] is False, f"cell claims acceptance: {cell_id}")
        _require(
            cell["acceptance_status"] == "experimental-performance-not-accepted",
            f"cell acceptance status drifted: {cell_id}",
        )
        cells.append(
            {
                "cell_id": cell_id,
                "sha256": str(entry["sha256"]),
                "model": str(cell["model"]),
                "wall_sec": float(cell["cell_wall_sec"]),
            }
        )
        if cell["model"] != "hierarchical-cae-coordinate":
            continue
        coordinate = cell["result"]["coordinate_readout"]
        _require(coordinate["all_queries_finite"] is True, f"non-finite coordinate output: {cell_id}")
        _require(coordinate["query_state_unchanged"] is True, f"coordinate query mutated state: {cell_id}")
        _require(coordinate["numeric_acceptance_thresholds"] is None, f"cell invented threshold: {cell_id}")
        _require(coordinate["scientific_acceptance_claimed"] is False, f"coordinate claims acceptance: {cell_id}")
        _require(
            cell["result"]["training_partition"][
                "offline_test_used_for_training_or_early_stopping"
            ]
            is False,
            f"offline leakage reported: {cell_id}",
        )
        fields = coordinate["fields"]
        coordinate_rows.append(
            {
                "cell_id": cell_id,
                "case": str(cell["case"]),
                "train_size": int(cell["train_size"]),
                "field_count": len(fields),
                "all_queries_finite": True,
                "query_state_unchanged": True,
                "max_member_coordinate_vs_grid_standardized_mae": _maximum(
                    fields, "member_coordinate_vs_grid_standardized_mae"
                ),
                "max_member_coordinate_vs_grid_standardized_rmse": _maximum(
                    fields, "member_coordinate_vs_grid_standardized_rmse"
                ),
                "off_grid_probe_value_count": int(
                    coordinate["off_grid_probe_value_count"]
                ),
                "peak_process_rss_bytes": int(
                    cell["result"]["resources"]["peak_process_rss_bytes"]
                ),
                "peak_torch_vram_bytes": int(
                    cell["result"]["resources"]["peak_torch_vram_bytes"]
                ),
                "parameter_count": int(
                    cell["result"]["resources"]["parameter_count"]
                ),
            }
        )
    _require(len(cells) == 12, "offline cell inventory is incomplete")
    _require(len(coordinate_rows) == 6, "coordinate cell inventory is incomplete")
    paired = summary["paired_descriptive_results"]
    _require(len(paired) == 6, "paired descriptive result count drifted")
    for row in paired:
        _require(row["descriptive_only"] is True, "paired result is not descriptive")
        _require(row["acceptance_decision"] is None, "paired result contains acceptance")
    return {
        "schema_version": 1,
        "assessment_id": "20260827-gate0-v7-082608-experimental-framework-result",
        "status": "completed-experimental-framework-mechanism-performance-not-accepted",
        "external_evidence": {
            "root": evidence_root.as_posix(),
            "run_spec_sha256": _sha256(run_spec_path),
            "offline_summary_sha256": _sha256(summary_path),
            "process_exit_code": 0,
            "wall_sec": float(summary["wall_sec"]),
            "completed_cell_count": 12,
            "offline_test_design_count": 1200,
            "calibration_locator_accessed": False,
            "simulator_launched": False,
        },
        "mechanism_result": {
            "coordinate_framework_executed": True,
            "offline_test_path_executed": True,
            "all_coordinate_queries_finite": True,
            "all_coordinate_queries_preserved_state": True,
            "full_grid_remained_authoritative": True,
            "offline_test_used_for_training_or_early_stopping": False,
        },
        "paired_descriptive_results": paired,
        "coordinate_descriptive_results": coordinate_rows,
        "resource_envelope_descriptive": {
            "max_peak_process_rss_bytes": max(
                row["peak_process_rss_bytes"] for row in coordinate_rows
            ),
            "max_peak_torch_vram_bytes": max(
                row["peak_torch_vram_bytes"] for row in coordinate_rows
            ),
            "max_parameter_count": max(
                row["parameter_count"] for row in coordinate_rows
            ),
        },
        "cells": sorted(cells, key=lambda row: row["cell_id"]),
        "scientific_decision": {
            "v5_failure_unchanged": True,
            "performance_accepted": False,
            "coordinate_performance_accepted": False,
            "numeric_thresholds_after_access": None,
            "todo_082608_may_archive": False,
            "performance_work_deferred": True,
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = assess(args.evidence_root)
        if args.output is not None:
            _write_json_atomic(args.output.resolve(), result)
    except (
        ExperimentalAssessmentError,
        KeyError,
        TypeError,
        ValueError,
        OSError,
        json.JSONDecodeError,
    ) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
