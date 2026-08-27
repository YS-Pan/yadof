"""Seal and selectively load the Gate 0 v2 representation dataset.

The sealer is the only command in this module that reads every compatible
rawData row.  It writes opaque partition assignments separately from the
partition locators so validation/model code cannot accidentally load the
offline-test partition.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Iterable, Mapping, Sequence

from yadof.job_template import api as job_template_api
from yadof.job_template.rawdata_template import StructuredRawDataSample
from yadof.recorded_data import (
    get_named_rawdata_samples,
    get_record_metadata,
    open_historical_rawdata_snapshot,
)
from yadof.surrogate.hierarchical_cae.schema import (
    build_schema,
    validate_samples,
)


AUTOMATION_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = AUTOMATION_ROOT.parent
PREREGISTRATION_ROOT = (
    AUTOMATION_ROOT / "preregistrations" / "20260827-new-surrogate-qnehvi"
)
V2_ROOT = (
    AUTOMATION_ROOT / "preregistrations" / "20260827-new-surrogate-qnehvi-v2"
)
INVENTORY_PATH = PREREGISTRATION_ROOT / "schema_inventory.json"
PREREGISTRATION_PATH = PREREGISTRATION_ROOT / "benchmark_preregistration.json"
AMENDMENT_PATH = V2_ROOT / "benchmark_preregistration.amendment.json"
VALIDATOR_PATH = PREREGISTRATION_ROOT / "validate.py"
DATASET_PROTOCOL = "yadof.gate0-v2.sealed-representation-dataset"
DATASET_PROTOCOL_VERSION = 1
LOCATOR_PROTOCOL = "yadof.gate0-v2.partition-locator"


def _json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def _json_bytes(value: object) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _write_json_atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f"{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(_json_bytes(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while True:
            block = stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def _validator_module():
    spec = importlib.util.spec_from_file_location(
        "yadof_gate0_v1_validator", VALIDATOR_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _rank3_layouts(case: Mapping[str, object]) -> dict[tuple[str, str], dict[str, object]]:
    layouts: dict[tuple[str, str], dict[str, object]] = {}
    for raw_field in case["fields"]:
        field = dict(raw_field)
        shape = tuple(int(value) for value in field["shape"])
        if len(shape) != 3:
            continue
        layout = dict(field["layout"])
        layouts[tuple(str(value) for value in field["selector"])] = {
            "channel_axes": tuple(str(value) for value in layout["channel_axes"]),
            "spatial_axes": tuple(str(value) for value in layout["spatial_axes"]),
        }
    return layouts


def _attempt_workspace(cell: Mapping[str, object]) -> tuple[Path, Mapping[str, object]]:
    completed = [
        attempt
        for attempt in cell.get("attempts", [])
        if isinstance(attempt, Mapping) and attempt.get("status") == "completed"
    ]
    if len(completed) != 1:
        raise ValueError(
            f"cell {cell.get('case')}/{cell.get('seed')} needs exactly one completed attempt"
        )
    attempt = completed[0]
    return Path(str(attempt["workspace"])).resolve(), attempt


def _source_entry(
    *,
    case_id: str,
    cell_id: str,
    seed: int,
    workspace: Path,
    reference,
    normalized: Sequence[float],
) -> dict[str, object]:
    return {
        "case": case_id,
        "cell_id": cell_id,
        "seed": int(seed),
        "workspace": str(workspace),
        "candidate_id": str(reference.candidate_id),
        "job_name": str(reference.record.get("job_name", "")),
        "normalized_variables": [float(value) for value in normalized],
    }


def seal_dataset(run_root: Path, output_dir: Path) -> dict[str, object]:
    run_root = run_root.resolve()
    output_dir = output_dir.resolve()
    state_path = run_root / "run_state.json"
    spec_path = run_root / "run_spec.json"
    state = _json(state_path)
    run_spec = _json(spec_path)
    if state.get("status") != "completed":
        raise RuntimeError("dataset campaign is not completed")
    if run_spec.get("suite") != "representation-dataset":
        raise ValueError("run is not the preregistered representation-dataset suite")

    inventory = _json(INVENTORY_PATH)
    preregistration = _json(PREREGISTRATION_PATH)
    amendment = _json(AMENDMENT_PATH)
    expected_config_hash = str(
        amendment["artifact_integrity"]["v2"][
            "../../representation_dataset_v2.toml"
        ]
    )
    if str(run_spec["config"]["sha256"]) != expected_config_hash:
        raise ValueError("representation campaign config hash drifted")

    validator = _validator_module()
    cases = inventory["cases"]
    cells = state.get("cells")
    if not isinstance(cells, Mapping):
        raise TypeError("run_state cells must be an object")

    all_rows: dict[str, dict[str, list[dict[str, object]]]] = {
        case_id: defaultdict(list) for case_id in cases
    }
    schemas: dict[str, object] = {}
    cell_receipts: list[dict[str, object]] = []
    segment_receipts: list[dict[str, object]] = []

    for cell_id, raw_cell in sorted(cells.items()):
        if not isinstance(raw_cell, Mapping):
            raise TypeError(f"cell {cell_id!r} must be an object")
        cell = dict(raw_cell)
        if cell.get("status") != "completed":
            raise RuntimeError(f"cell {cell_id} is not completed")
        if cell.get("arm") != "nsga3":
            raise ValueError(f"cell {cell_id} is not the frozen dataset arm")
        case_id = str(cell["case"])
        if case_id not in cases:
            raise ValueError(f"unknown dataset case {case_id!r}")
        case = cases[case_id]
        task_fingerprint = str(case["task_fingerprint"])
        workspace, attempt = _attempt_workspace(cell)
        input_manifest_path = Path(str(attempt["input_manifest"]))
        input_manifest = _json(input_manifest_path)
        if str(input_manifest.get("baseline_task_fingerprint")) != task_fingerprint:
            raise ValueError(f"{cell_id}: task fingerprint drifted")

        snapshot = open_historical_rawdata_snapshot(workspace, status="completed")
        if snapshot.diagnostics:
            raise RuntimeError(f"{cell_id}: recorded-data snapshot diagnostics present")
        for segment_path in snapshot.segment_paths:
            segment_receipts.append(
                {
                    "cell_id": str(cell_id),
                    "path": str(segment_path.resolve()),
                    "bytes": int(segment_path.stat().st_size),
                    "sha256": _sha256(segment_path),
                }
            )

        parameter_names = tuple(job_template_api.get_parameter_names(workspace))
        if parameter_names != tuple(case["parameter_contract"]["names"]):
            raise ValueError(f"{cell_id}: parameter identity/order drifted")
        expected_selectors = {
            tuple(str(value) for value in field["selector"])
            for field in case["fields"]
        }
        compatible = 0
        decoded = 0
        batch_diagnostics = 0
        for batch in snapshot.iter_batches():
            batch_diagnostics += len(batch.diagnostics)
            for reference, items in batch.records:
                decoded += 1
                raw_variables = reference.record.get("raw_variables")
                if not isinstance(raw_variables, Mapping):
                    continue
                try:
                    raw_row = tuple(float(raw_variables[name]) for name in parameter_names)
                    normalized = tuple(
                        float(value)
                        for value in job_template_api.normalize_variables(
                            workspace, raw_row
                        )
                    )
                    if not normalized or not all(math.isfinite(value) for value in normalized):
                        raise ValueError("normalized variables are not finite")
                    sample = StructuredRawDataSample.from_items(items)
                    if set(sample.field_selectors) != expected_selectors:
                        raise ValueError("rawData selector inventory drifted")
                    schema = schemas.get(case_id)
                    if schema is None:
                        schema = build_schema(
                            sample, field_layouts=_rank3_layouts(case)
                        )
                        schemas[case_id] = schema
                    validate_samples(schema, (sample,))
                    design_id = validator.canonical_design_id(
                        case_id, task_fingerprint, normalized
                    )
                except (KeyError, TypeError, ValueError):
                    continue
                all_rows[case_id][design_id].append(
                    _source_entry(
                        case_id=case_id,
                        cell_id=str(cell_id),
                        seed=int(cell["seed"]),
                        workspace=workspace,
                        reference=reference,
                        normalized=normalized,
                    )
                )
                compatible += 1
        if batch_diagnostics:
            raise RuntimeError(f"{cell_id}: {batch_diagnostics} streamed row diagnostics")
        cell_receipts.append(
            {
                "cell_id": str(cell_id),
                "case": case_id,
                "seed": int(cell["seed"]),
                "workspace": str(workspace),
                "input_manifest": str(input_manifest_path.resolve()),
                "input_manifest_sha256": _sha256(input_manifest_path),
                "decoded_completed_rows": int(decoded),
                "schema_compatible_rows": int(compatible),
            }
        )

    locator_rows: dict[str, list[dict[str, object]]] = {
        "development": [],
        "calibration": [],
        "offline-test": [],
    }
    opaque_designs: list[dict[str, object]] = []
    case_receipts: dict[str, object] = {}
    for case_id, case in cases.items():
        rows_by_id = all_rows[case_id]
        design_ids = tuple(rows_by_id)
        split = validator.assign_design_splits(
            design_ids,
            case_id=case_id,
            task_fingerprint_value=str(case["task_fingerprint"]),
            preregistration=preregistration,
        )
        partition_by_id = {
            design_id: partition
            for partition, ids in split["partitions"].items()
            for design_id in ids
        }
        training_rank = {
            design_id: index
            for index, design_id in enumerate(
                split["training_views"]["train_2000"]
            )
        }
        selected_ids = set(partition_by_id)
        duplicate_count = sum(max(0, len(rows_by_id[item]) - 1) for item in selected_ids)
        for design_id in sorted(selected_ids):
            sources = sorted(
                rows_by_id[design_id],
                key=lambda item: (
                    str(item["cell_id"]),
                    str(item["candidate_id"]),
                    str(item["job_name"]),
                ),
            )
            source = dict(sources[0])
            partition = partition_by_id[design_id]
            opaque_designs.append(
                {
                    "case": case_id,
                    "design_id": design_id,
                    "partition": partition,
                    "training_rank": training_rank.get(design_id),
                    "duplicate_source_count": len(sources),
                }
            )
            locator_name = (
                "development"
                if partition in {"train_pool", "validation"}
                else "calibration"
                if partition == "calibration"
                else "offline-test"
            )
            locator_rows[locator_name].append(
                {
                    **source,
                    "design_id": design_id,
                    "partition": partition,
                    "training_rank": training_rank.get(design_id),
                }
            )
        schema = schemas.get(case_id)
        if schema is None:
            raise RuntimeError(f"{case_id}: no compatible schema was observed")
        case_receipts[case_id] = {
            "task_fingerprint": str(case["task_fingerprint"]),
            "compatible_unique_designs": len(rows_by_id),
            "selected_unique_designs": len(selected_ids),
            "selected_duplicate_sources": duplicate_count,
            "partition_counts": {
                name: len(values) for name, values in split["partitions"].items()
            },
            "training_view_counts": {
                name: len(values)
                for name, values in split["training_views"].items()
            },
            "schema": schema.as_dict(include_axis_values=False),
            "schema_sha256": hashlib.sha256(
                _json_bytes(schema.as_dict(include_axis_values=True))
            ).hexdigest(),
        }

    locator_receipts: dict[str, object] = {}
    for name, rows in locator_rows.items():
        path = output_dir / f"{name}_locator.json"
        payload = {
            "protocol": LOCATOR_PROTOCOL,
            "protocol_version": 1,
            "run_id": str(state["run_id"]),
            "partition_scope": name,
            "rows": sorted(rows, key=lambda item: (item["case"], item["design_id"])),
        }
        _write_json_atomic(path, payload)
        locator_receipts[name] = {
            "path": path.name,
            "sha256": _sha256(path),
            "row_count": len(rows),
        }

    manifest_path = output_dir / "sealed_dataset_manifest.json"
    manifest = {
        "protocol": DATASET_PROTOCOL,
        "protocol_version": DATASET_PROTOCOL_VERSION,
        "status": "sealed-development-partitions-test-unaccessed",
        "run_id": str(state["run_id"]),
        "run_state": {"path": str(state_path), "sha256": _sha256(state_path)},
        "run_spec": {"path": str(spec_path), "sha256": _sha256(spec_path)},
        "preregistration": {
            "v1_sha256": _sha256(PREREGISTRATION_PATH),
            "v2_amendment_sha256": _sha256(AMENDMENT_PATH),
            "inventory_sha256": _sha256(INVENTORY_PATH),
        },
        "cases": case_receipts,
        "cells": cell_receipts,
        "source_segments": sorted(
            segment_receipts, key=lambda item: (item["cell_id"], item["path"])
        ),
        "partition_locators": locator_receipts,
        "designs": sorted(
            opaque_designs, key=lambda item: (item["case"], item["design_id"])
        ),
        "access_log": {
            "sealer_validated_all_rows": True,
            "development_locator_created": True,
            "calibration_locator_created_but_not_read_by_metric_code": True,
            "offline_test_locator_created_but_not_read_by_metric_code": True,
            "offline_test_metrics_accessed": False,
        },
    }
    _write_json_atomic(manifest_path, manifest)
    receipt = {
        "status": "sealed",
        "manifest": {
            "path": manifest_path.name,
            "sha256": _sha256(manifest_path),
            "bytes": manifest_path.stat().st_size,
        },
        "locators": locator_receipts,
        "case_counts": {
            case_id: {
                "compatible_unique_designs": value["compatible_unique_designs"],
                "selected_unique_designs": value["selected_unique_designs"],
            }
            for case_id, value in case_receipts.items()
        },
        "offline_test_accessed": False,
    }
    _write_json_atomic(output_dir / "dataset_seal_receipt.json", receipt)
    return receipt


def verify_seal(manifest_path: Path) -> dict[str, object]:
    manifest_path = manifest_path.resolve()
    manifest = _json(manifest_path)
    if manifest.get("protocol") != DATASET_PROTOCOL:
        raise ValueError("unsupported sealed dataset protocol")
    if int(manifest.get("protocol_version", -1)) != DATASET_PROTOCOL_VERSION:
        raise ValueError("unsupported sealed dataset protocol version")
    root = manifest_path.parent
    for name, raw_receipt in manifest["partition_locators"].items():
        receipt = dict(raw_receipt)
        path = root / str(receipt["path"])
        if _sha256(path) != str(receipt["sha256"]):
            raise ValueError(f"{name} locator hash mismatch")
        locator = _json(path)
        if locator.get("protocol") != LOCATOR_PROTOCOL:
            raise ValueError(f"{name} locator protocol mismatch")
        if len(locator.get("rows", [])) != int(receipt["row_count"]):
            raise ValueError(f"{name} locator row count mismatch")
    for segment in manifest["source_segments"]:
        path = Path(str(segment["path"]))
        if path.stat().st_size != int(segment["bytes"]):
            raise ValueError(f"source segment size mismatch: {path}")
        if _sha256(path) != str(segment["sha256"]):
            raise ValueError(f"source segment hash mismatch: {path}")
    return {
        "status": "valid",
        "manifest_sha256": _sha256(manifest_path),
        "cases": manifest["cases"],
        "offline_test_accessed": False,
    }


def load_locator_rows(
    manifest_path: Path,
    *,
    scope: str = "development",
    sealed_threshold_path: Path | None = None,
) -> tuple[dict[str, object], ...]:
    """Load one locator, guarding calibration and offline-test access."""

    manifest_path = manifest_path.resolve()
    manifest = _json(manifest_path)
    if manifest.get("protocol") != DATASET_PROTOCOL:
        raise ValueError("unsupported sealed dataset protocol")
    scope = str(scope)
    if scope not in {"development", "calibration", "offline-test"}:
        raise ValueError("unknown partition locator scope")
    if scope != "development":
        if sealed_threshold_path is None:
            raise PermissionError(
                f"{scope} access requires an immutable sealed threshold file"
            )
        threshold = _json(sealed_threshold_path.resolve())
        if threshold.get("status") != "sealed":
            raise PermissionError("threshold file is not sealed")
        expected_manifest_hash = str(threshold.get("dataset_manifest_sha256", ""))
        if expected_manifest_hash != _sha256(manifest_path):
            raise PermissionError("threshold file does not bind this dataset manifest")
        if scope == "offline-test" and not bool(
            threshold.get("offline_test_access_authorized", False)
        ):
            raise PermissionError("sealed thresholds do not authorize offline-test access")
    receipt = manifest["partition_locators"][scope]
    path = manifest_path.parent / str(receipt["path"])
    if _sha256(path) != str(receipt["sha256"]):
        raise ValueError(f"{scope} locator hash mismatch")
    locator = _json(path)
    rows = locator.get("rows")
    if not isinstance(rows, list):
        raise TypeError(f"{scope} locator rows must be a list")
    return tuple(dict(row) for row in rows)


def load_selected_records(
    rows: Iterable[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    """Decode only explicitly selected locator rows, grouped by source workspace."""

    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["workspace"])].append(row)
    output = []
    for workspace_text, selected in sorted(grouped.items()):
        workspace = Path(workspace_text)
        names = tuple(str(row["job_name"]) for row in selected)
        samples = dict(
            get_named_rawdata_samples(
                workspace, job_names=names, status="completed"
            )
        )
        metadata = dict(
            get_record_metadata(workspace, job_names=names, status="completed")
        )
        for row in selected:
            name = str(row["job_name"])
            if name not in samples:
                raise KeyError(f"selected rawData row disappeared: {workspace}::{name}")
            output.append(
                {
                    "locator": dict(row),
                    "normalized_variables": tuple(
                        float(value) for value in row["normalized_variables"]
                    ),
                    "sample": StructuredRawDataSample.from_items(samples[name]),
                    "record_metadata": metadata.get(name, {}),
                }
            )
    return tuple(output)


def load_selected_rawdata(
    rows: Iterable[Mapping[str, object]],
) -> tuple[
    tuple[tuple[float, ...], StructuredRawDataSample, Mapping[str, object]], ...
]:
    """Backward-compatible tuple view over :func:`load_selected_records`."""

    records = load_selected_records(rows)
    return tuple(
        (
            record["normalized_variables"],
            record["sample"],
            record["record_metadata"],
        )
        for record in records
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    seal = subparsers.add_parser("seal")
    seal.add_argument("--run-root", type=Path, required=True)
    seal.add_argument("--output-dir", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    if arguments.command == "seal":
        result = seal_dataset(arguments.run_root, arguments.output_dir)
    else:
        result = verify_seal(arguments.manifest)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
