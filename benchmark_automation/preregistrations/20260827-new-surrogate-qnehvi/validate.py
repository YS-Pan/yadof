"""Validate the frozen Gate 0 schema and preregistration without simulation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct
import sys
import tomllib
from typing import Iterable, Mapping, Sequence

import numpy as np


PREREGISTRATION_ROOT = Path(__file__).resolve().parent
AUTOMATION_ROOT = PREREGISTRATION_ROOT.parents[1]
INVENTORY_PATH = PREREGISTRATION_ROOT / "schema_inventory.json"
PREREGISTRATION_PATH = PREREGISTRATION_ROOT / "benchmark_preregistration.json"
DATA_AUDIT_PATH = PREREGISTRATION_ROOT / "data_availability_audit.json"
THRESHOLD_TEMPLATE_PATH = PREREGISTRATION_ROOT / "acceptance_thresholds.template.json"

if str(AUTOMATION_ROOT) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_ROOT))

from benchmark_core import task_fingerprint  # noqa: E402


class Gate0ValidationError(RuntimeError):
    """Raised when a frozen Gate 0 artifact no longer matches its source."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate0ValidationError(message)


def _load_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name} must contain a JSON object")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _axis_values(axis: Mapping[str, object]) -> np.ndarray:
    generator = axis["generator"]
    _require(isinstance(generator, dict), "axis generator must be an object")
    kind = generator.get("kind")
    if kind == "linspace":
        values = np.linspace(
            float(generator["start"]),
            float(generator["stop"]),
            int(generator["count"]),
            dtype=np.float64,
        )
    elif kind == "explicit":
        values = np.asarray(generator["values"], dtype=np.float64)
    else:
        raise Gate0ValidationError(f"unsupported axis generator: {kind!r}")
    return np.asarray(values, dtype=np.float64)


def _array_digest(values: np.ndarray) -> str:
    canonical = np.asarray(values, dtype="<f8", order="C")
    return hashlib.sha256(canonical.tobytes(order="C")).hexdigest()


def _shape_size(shape: Sequence[object]) -> int:
    result = 1
    for raw_size in shape:
        size = int(raw_size)
        _require(size > 0, f"shape dimensions must be positive: {shape!r}")
        result *= size
    return result


def _load_parameter_module(path: Path, case_id: str):
    spec = importlib.util.spec_from_file_location(
        f"gate0_parameters_{case_id.replace('-', '_')}", path
    )
    _require(spec is not None and spec.loader is not None, f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _validate_parameter_contract(
    baseline_root: Path,
    case_id: str,
    contract: Mapping[str, object],
) -> None:
    module = _load_parameter_module(
        baseline_root / "workspace" / "job_template" / "parameters_constraints.py",
        case_id,
    )
    parameters = tuple(module.PARAMETERS)
    names = [str(parameter.name) for parameter in parameters]
    _require(names == contract["names"], f"{case_id}: parameter names/order drifted")
    _require(len(parameters) == int(contract["count"]), f"{case_id}: parameter count drifted")
    piecewise = sum(len(tuple(parameter.ranges)) > 1 for parameter in parameters)
    single = sum(len(tuple(parameter.ranges)) == 1 for parameter in parameters)
    _require(
        piecewise == int(contract["continuous_piecewise"]),
        f"{case_id}: piecewise parameter count drifted",
    )
    _require(
        single == int(contract["continuous_single_interval"]),
        f"{case_id}: single-interval parameter count drifted",
    )
    _require(int(contract["discrete"]) == 0, f"{case_id}: validator supports no discrete fields in v1")


def _validate_inventory(
    inventory: Mapping[str, object], config: Mapping[str, object]
) -> dict[str, object]:
    _require(inventory.get("schema_version") == 1, "inventory schema_version must be 1")
    _require(inventory.get("status") == "frozen-source-schema", "inventory status drifted")
    axes = inventory["axes"]
    _require(isinstance(axes, dict) and axes, "inventory axes must be non-empty")
    for axis_id, raw_axis in axes.items():
        _require(isinstance(raw_axis, dict), f"axis {axis_id} must be an object")
        values = _axis_values(raw_axis)
        _require(list(values.shape) == raw_axis["shape"], f"axis {axis_id} shape drifted")
        _require(values.nbytes == int(raw_axis["array_bytes"]), f"axis {axis_id} byte count drifted")
        _require(
            _array_digest(values) == raw_axis["canonical_little_endian_float64_sha256"],
            f"axis {axis_id} digest drifted",
        )

    cases = inventory["cases"]
    _require(isinstance(cases, dict) and set(cases) == {"saw", "chrono", "test-com"}, "case set drifted")
    configured_cases = config["cases"]
    result: dict[str, object] = {}
    for case_id, raw_case in cases.items():
        _require(isinstance(raw_case, dict), f"case {case_id} must be an object")
        case = raw_case
        configured = configured_cases[case_id]
        _require(configured["baseline"] == case["baseline"], f"{case_id}: baseline path drifted")
        _require(
            int(configured["expected_objectives"]) == int(case["objective_count"]),
            f"{case_id}: objective count drifted",
        )
        baseline_root = AUTOMATION_ROOT / str(case["baseline"])
        manifest_path = baseline_root / "baseline.json"
        _require(_sha256(manifest_path) == case["baseline_manifest_sha256"], f"{case_id}: baseline manifest drifted")
        manifest = _load_json(manifest_path)
        validation = manifest["validation"]
        _require(validation["baseline_record_rows"] == 0, f"{case_id}: baseline unexpectedly contains records")
        _require(validation["baseline_checkpoint_files"] == 0, f"{case_id}: baseline unexpectedly contains checkpoints")
        _require(manifest["baseline_id"] == case["baseline_id"], f"{case_id}: baseline ID drifted")
        include_paths = configured["include_paths"]
        observed_fingerprint = task_fingerprint(baseline_root / "workspace", include_paths)
        _require(observed_fingerprint == case["task_fingerprint"], f"{case_id}: task fingerprint drifted")
        _validate_parameter_contract(baseline_root, case_id, case["parameter_contract"])

        for relative, expected_hash in case["source_sha256"].items():
            source_path = baseline_root / relative
            _require(_sha256(source_path) == expected_hash, f"{case_id}: source drifted: {relative}")

        selectors: set[tuple[str, str]] = set()
        raw_shapes: dict[str, list[int]] = {}
        main_bytes = 0
        axis_bytes = 0
        fields = case["fields"]
        for raw_field in fields:
            _require(isinstance(raw_field, dict), f"{case_id}: field must be an object")
            selector = tuple(raw_field["selector"])
            _require(len(selector) == 2, f"{case_id}: invalid selector {selector!r}")
            basename, main_key = selector
            _require(str(basename).endswith(".npz"), f"{case_id}: selector must include .npz")
            _require(main_key in {"data", "values"}, f"{case_id}: invalid main key {main_key!r}")
            _require(selector not in selectors, f"{case_id}: duplicate selector {selector!r}")
            selectors.add(selector)
            shape = list(raw_field["shape"])
            _require(raw_field["dtype"] == "float64", f"{case_id}: v1 dtype must be float64")
            expected_main_bytes = _shape_size(shape) * 8
            _require(expected_main_bytes == int(raw_field["main_array_bytes"]), f"{case_id}: main bytes drifted")
            field_axes = raw_field["axes"]
            _require(len(field_axes) == len(shape), f"{case_id}: axis rank mismatch for {basename}")
            for index, axis_ref in enumerate(field_axes):
                axis_id = axis_ref["inventory_axis"]
                _require(axis_id in axes, f"{case_id}: unknown axis {axis_id}")
                axis_shape = axes[axis_id]["shape"]
                _require(axis_shape == [shape[index]], f"{case_id}: axis size mismatch for {basename}")
                axis_bytes += int(axes[axis_id]["array_bytes"])
            main_bytes += expected_main_bytes
            raw_shapes[str(basename)[:-4]] = shape
        totals = case["per_design_array_bytes_excluding_metadata_and_units"]
        _require(main_bytes == int(totals["main_arrays"]), f"{case_id}: case main-byte total drifted")
        _require(axis_bytes == int(totals["repeated_axis_arrays"]), f"{case_id}: case axis-byte total drifted")
        _require(main_bytes + axis_bytes == int(totals["total"]), f"{case_id}: case byte total drifted")
        _require(dict(configured["rawdata_shapes"]) == raw_shapes, f"{case_id}: benchmark.toml rawData shapes drifted")
        result[case_id] = {
            "task_fingerprint": observed_fingerprint,
            "parameter_count": int(case["parameter_contract"]["count"]),
            "objective_count": int(case["objective_count"]),
            "field_count": len(fields),
            "main_array_bytes_per_design": main_bytes,
        }
    return result


def _derived_seed(index: int) -> int:
    prefix = b"yadof:new-surrogate-qnehvi:gate0:v1:seed:"
    return int.from_bytes(hashlib.sha256(prefix + str(index).encode("ascii")).digest()[:4], "big") & 0x7FFFFFFF


def canonical_design_id(
    case_id: str,
    task_fingerprint_value: str,
    normalized_variables: Sequence[float],
) -> str:
    """Return the preregistered identity for one normalized design."""

    values = tuple(float(value) for value in normalized_variables)
    _require(values, "a design must contain at least one normalized variable")
    _require(all(math.isfinite(value) for value in values), "normalized variables must be finite")
    payload = bytearray(b"yadof:new-surrogate-qnehvi:gate0:v1:design-id\0")
    payload.extend(str(case_id).encode("utf-8"))
    payload.extend(b"\0")
    payload.extend(str(task_fingerprint_value).encode("ascii"))
    payload.extend(b"\0")
    payload.extend(struct.pack("<I", len(values)))
    for value in values:
        payload.extend(struct.pack("<d", value))
    return hashlib.sha256(payload).hexdigest()


def _partition_order_digest(salt: str, case_id: str, task_fingerprint_value: str, design_id: str) -> str:
    payload = "\0".join((salt, case_id, task_fingerprint_value, design_id)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def assign_design_splits(
    design_ids: Iterable[str],
    *,
    case_id: str,
    task_fingerprint_value: str,
    preregistration: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Apply the exact row-order-independent Gate 0 partition algorithm."""

    plan = preregistration or _load_json(PREREGISTRATION_PATH)
    split = plan["dataset_and_split"]
    assignment = split["assignment_algorithm"]
    quotas = split["partition_quotas_per_case"]
    unique_ids = set(str(item) for item in design_ids)
    required = sum(int(quotas[name]) for name in ("test", "calibration", "validation", "train_pool"))
    _require(len(unique_ids) >= required, f"need at least {required} unique designs")
    ordered = sorted(
        unique_ids,
        key=lambda design_id: (
            _partition_order_digest(
                str(assignment["assignment_salt"]),
                case_id,
                task_fingerprint_value,
                design_id,
            ),
            design_id,
        ),
    )[:required]
    cursor = 0
    partitions: dict[str, list[str]] = {}
    for name in ("test", "calibration", "validation", "train_pool"):
        count = int(quotas[name])
        partitions[name] = ordered[cursor : cursor + count]
        cursor += count
    train_order = sorted(
        partitions["train_pool"],
        key=lambda design_id: (
            _partition_order_digest(
                str(assignment["training_order_salt"]),
                case_id,
                task_fingerprint_value,
                design_id,
            ),
            design_id,
        ),
    )
    views = split["nested_training_views"]
    return {
        "partitions": partitions,
        "training_views": {
            "warmup_diagnostic": train_order[: int(views["warmup_diagnostic"])],
            "train_1000": train_order[: int(views["train_1000"])],
            "train_2000": train_order[: int(views["train_2000"])],
        },
    }


def _validate_preregistration(
    inventory: Mapping[str, object],
    preregistration: Mapping[str, object],
    data_audit: Mapping[str, object],
    threshold_template: Mapping[str, object],
) -> None:
    preregistration_id = preregistration.get("preregistration_id")
    _require(preregistration_id == inventory.get("preregistration_id"), "artifact preregistration IDs differ")
    _require(preregistration_id == data_audit.get("preregistration_id"), "data-audit preregistration ID differs")
    _require(preregistration_id == threshold_template.get("preregistration_id"), "threshold preregistration ID differs")
    integrity = preregistration["artifact_integrity"]
    for key, path in (
        ("schema_inventory", INVENTORY_PATH),
        ("data_availability_audit", DATA_AUDIT_PATH),
        ("acceptance_threshold_template", THRESHOLD_TEMPLATE_PATH),
    ):
        _require(_sha256(path) == integrity[key]["sha256"], f"artifact hash drifted: {path.name}")
    config_ref = integrity["benchmark_configuration_at_registration"]
    _require(_sha256(AUTOMATION_ROOT / "benchmark.toml") == config_ref["sha256"], "benchmark.toml drifted")

    _require(data_audit.get("status") == "no-eligible-frozen-dataset", "data audit status must remain explicit")
    audited = data_audit["audited_sources"]["baseline_templates"]
    _require(all(item["eligible_design_rows"] == 0 for item in audited.values()), "baseline templates are not datasets")
    _require(data_audit["new_real_campaign_authorized_by_this_preregistration"] is False, "Gate 0 cannot authorize a campaign")
    _require(threshold_template.get("status") == "unsealed-template", "threshold template must remain unsealed")
    _require(threshold_template.get("formal_test_ready") is False, "unsealed thresholds cannot be test-ready")
    nullable_thresholds = (
        threshold_template["rawdata_representation"]["field_macro_standardized_rmse_ratio_max_vs_conditional_inr"],
        threshold_template["posterior"]["maximum_calibration_error"],
        threshold_template["optimization"]["qnehvi_vs_gpsaf_paired_hv_margin"],
        threshold_template["engineering_cost"]["maximum_cae_training_wall_sec"],
    )
    _require(all(value is None for value in nullable_thresholds), "Gate 0 must not invent numeric thresholds")

    split = preregistration["dataset_and_split"]
    quotas = split["partition_quotas_per_case"]
    _require(sum(int(value) for value in quotas.values()) == int(split["minimum_unique_compatible_designs_per_case"]), "split quotas drifted")
    views = split["nested_training_views"]
    _require(int(views["warmup_diagnostic"]) <= int(views["train_1000"]) <= int(views["train_2000"]) == int(quotas["train_pool"]), "nested train views drifted")

    seed_registry = preregistration["seed_registry"]
    expected_groups = {
        "model_fit_and_bootstrap": range(0, 5),
        "threshold_pilot_optimization": range(5, 8),
        "posterior_metric_and_backend_spike": range(8, 10),
        "formal_optimization_test": range(10, 15),
    }
    observed_sets: list[set[int]] = []
    for name, indices in expected_groups.items():
        expected = [_derived_seed(index) for index in indices]
        observed = [int(value) for value in seed_registry[name]]
        _require(observed == expected, f"seed registry drifted: {name}")
        observed_sets.append(set(observed))
    for index, current in enumerate(observed_sets):
        _require(not any(current & other for other in observed_sets[index + 1 :]), "seed groups overlap")

    environment = preregistration["registration_environment"]
    host = environment["host"]
    gpu = environment["gpu"]
    packages = environment["python_and_packages"]
    _require(int(host["physical_cores"]) > 0, "registration host physical cores missing")
    _require(int(host["logical_cores"]) >= int(host["physical_cores"]), "registration host core counts invalid")
    _require(int(host["total_memory_bytes_psutil"]) > 0, "registration host memory missing")
    _require(int(gpu["total_memory_bytes"]) > 0, "registration GPU memory missing")
    _require(len(gpu["compute_capability"]) == 2, "registration GPU compute capability invalid")
    _require(packages["botorch"] is None and packages["gpytorch"] is None, "Gate 0 must not imply an installed qNEHVI backend")
    runtimes = environment["external_runtimes"]
    _require(runtimes["ngspice"]["preflight_exists"] is True, "registered ngspice preflight result missing")
    pychrono = runtimes["pychrono_python"]
    _require(pychrono["preflight_exists"] is True, "registered PyChrono interpreter preflight result missing")
    _require(pychrono["pychrono_version"] == "10.0.0", "registered PyChrono version drifted")
    conda_record = pychrono["conda_record"]
    _require(conda_record["build"] == "py313h418371c_0", "registered PyChrono build drifted")
    _require(int(conda_record["build_number"]) == 0, "registered PyChrono build number drifted")
    for label, digest in (
        ("PyChrono interpreter", pychrono["sha256"]),
        ("PyChrono Conda record", conda_record["sha256"]),
        ("PyChrono package", conda_record["package_sha256"]),
    ):
        _require(len(str(digest)) == 64, f"{label} SHA-256 is not frozen")

    formal_arms = {item["id"] for item in preregistration["comparison_matrix"]["formal_online_arms"]}
    _require(
        formal_arms
        == {
            "nsga3",
            "gpsaf-conditional-inr",
            "gpsaf-hierarchical-cae",
            "qnehvi-hierarchical-cae",
            "qnehvi-conditional-inr-adapter",
        },
        "formal comparison matrix drifted",
    )
    readiness = preregistration["readiness"]
    _require(readiness["eligible_frozen_dataset_available"] is False, "current checkout has no sealed dataset")
    _require(readiness["numeric_thresholds_sealed"] is False, "thresholds are not sealed")
    _require(readiness["formal_benchmark_runnable"] is False, "formal benchmark must remain blocked")


def validate() -> dict[str, object]:
    inventory = _load_json(INVENTORY_PATH)
    preregistration = _load_json(PREREGISTRATION_PATH)
    data_audit = _load_json(DATA_AUDIT_PATH)
    threshold_template = _load_json(THRESHOLD_TEMPLATE_PATH)
    with (AUTOMATION_ROOT / "benchmark.toml").open("rb") as stream:
        config = tomllib.load(stream)
    cases = _validate_inventory(inventory, config)
    _validate_preregistration(inventory, preregistration, data_audit, threshold_template)
    return {
        "schema_version": 1,
        "view": "gate0-preregistration-validation",
        "ok": True,
        "preregistration_id": inventory["preregistration_id"],
        "cases": cases,
        "data_status": data_audit["status"],
        "threshold_status": threshold_template["status"],
        "registration_environment_frozen": True,
        "pychrono_version_evidence": "conda-record:10.0.0",
        "formal_test_ready": False,
        "simulator_launched": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true", help="indent the JSON output")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = validate()
    except (Gate0ValidationError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}, ensure_ascii=True))
        return 1
    print(json.dumps(result, ensure_ascii=True, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
