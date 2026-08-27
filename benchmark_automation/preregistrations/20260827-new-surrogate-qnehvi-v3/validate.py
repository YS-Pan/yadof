"""Validate Gate 0 v1/v2 and the v3 diagnostic-path amendment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parent
V2_ROOT = ROOT.parent / "20260827-new-surrogate-qnehvi-v2"
AMENDMENT_PATH = ROOT / "benchmark_preregistration.amendment.json"
PROTOCOL_PATH = ROOT / "quality_regime_protocol.json"
RECEIPT_PATH = ROOT / "dataset_seal_receipt.json"


class Gate0V3ValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate0V3ValidationError(message)


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


def _validate_parent() -> dict[str, object]:
    path = V2_ROOT / "validate.py"
    spec = importlib.util.spec_from_file_location("gate0_v2_validator", path)
    _require(spec is not None and spec.loader is not None, "cannot load v2 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.validate()
    _require(result["ok"] is True, "Gate 0 v2 validator did not pass")
    _require(result["formal_test_ready"] is False, "v2 formal test must remain blocked")
    _require(result["simulator_launched"] is False, "v2 validator launched a simulator")
    return result


def _validate_integrity(amendment: Mapping[str, object]) -> None:
    parent = amendment["parent_integrity"]
    paths = {
        "v2_amendment_sha256": V2_ROOT / "benchmark_preregistration.amendment.json",
        "v2_quality_protocol_sha256": V2_ROOT / "quality_regime_protocol.json",
        "v2_threshold_template_sha256": V2_ROOT / "acceptance_thresholds.template.json",
    }
    for key, path in paths.items():
        _require(path.is_file(), f"missing frozen parent artifact {path.name}")
        _require(_sha256(path) == parent[key], f"frozen parent artifact drifted: {path.name}")
    artifacts = amendment["artifact_integrity"]
    for name, expected in artifacts.items():
        path = ROOT / str(name)
        _require(path.is_file(), f"missing v3 artifact {name}")
        _require(_sha256(path) == expected, f"v3 artifact drifted: {name}")


def _validate_protocol(protocol: Mapping[str, object]) -> None:
    _require(
        protocol["protocol_id"] == "new-surrogate-quality-regime-v2",
        "v3 quality protocol ID drifted",
    )
    policy = protocol["chrono_task_policy"]
    _require(policy["policy_version"] == 2, "Chrono policy version drifted")
    _require(
        policy["diagnostic_path"] == ["task_diagnostics", "child"],
        "Chrono diagnostic path correction drifted",
    )
    _require(
        policy["assessment_path"]
        == ["task_diagnostics", "child", "yadof_rawdata_quality_assessment"],
        "Chrono explicit-assessment path correction drifted",
    )
    rules = policy["ordered_rules"]
    _require(
        [rule["regime"] for rule in rules] == ["failure", "chatter"],
        "Chrono rule priority drifted",
    )
    _require(
        set(protocol["required_ablations"])
        == {
            "no-gating",
            "robust-weighting-only",
            "shared-latent-isolation",
            "gated-private-residual",
        },
        "v3 ablation matrix drifted",
    )
    _require(
        protocol["model_semantics"]["observation_noise"]
        == "zero; regime uncertainty is epistemic/structural",
        "zero-observation-noise interpretation drifted",
    )


def _validate_dataset(
    manifest_path: Path, receipt: Mapping[str, object]
) -> dict[str, object]:
    manifest_path = manifest_path.resolve()
    expected = receipt["sealed_dataset_manifest"]
    _require(manifest_path.is_file(), "sealed dataset manifest is missing")
    _require(
        manifest_path.stat().st_size == int(expected["bytes"]),
        "sealed dataset manifest byte count drifted",
    )
    _require(
        _sha256(manifest_path) == expected["sha256"],
        "sealed dataset manifest hash drifted",
    )
    manifest = _load_json(manifest_path)
    _require(
        manifest["protocol"] == "yadof.gate0-v2.sealed-representation-dataset",
        "sealed dataset protocol drifted",
    )
    _require(
        manifest["access_log"]["offline_test_metrics_accessed"] is False,
        "sealed dataset reports offline-test metric access",
    )
    for name, expected_locator in receipt["partition_locators"].items():
        actual = manifest["partition_locators"][name]
        _require(
            int(actual["row_count"]) == int(expected_locator["rows"]),
            f"{name} locator row count drifted",
        )
        _require(
            actual["sha256"] == expected_locator["sha256"],
            f"{name} locator hash drifted",
        )
    for case_id, expected_case in receipt["case_counts"].items():
        actual = manifest["cases"][case_id]
        _require(
            int(actual["compatible_unique_designs"])
            == int(expected_case["compatible_unique_designs"]),
            f"{case_id} compatible design count drifted",
        )
        _require(
            int(actual["selected_unique_designs"])
            == int(expected_case["selected_unique_designs"]),
            f"{case_id} selected design count drifted",
        )
    return manifest


def validate(dataset_manifest: Path) -> dict[str, object]:
    parent = _validate_parent()
    amendment = _load_json(AMENDMENT_PATH)
    protocol = _load_json(PROTOCOL_PATH)
    receipt = _load_json(RECEIPT_PATH)
    _validate_integrity(amendment)
    _validate_protocol(protocol)
    manifest = _validate_dataset(dataset_manifest, receipt)
    _require(
        amendment["development_evidence"]["offline_test_locator_accessed"] is False,
        "v3 amendment reports offline-test access",
    )
    _require(
        amendment["readiness"]["validation_metric_access_allowed"] is True,
        "v3 must permit the next development validation step",
    )
    _require(
        amendment["readiness"]["offline_test_access_allowed"] is False,
        "v3 must keep offline-test blocked",
    )
    return {
        "schema_version": 1,
        "view": "gate0-v3-diagnostic-path-validation",
        "ok": True,
        "preregistration_id": amendment["preregistration_id"],
        "parent_preregistration_id": parent["preregistration_id"],
        "parent_validator_ok": True,
        "quality_protocol_id": protocol["protocol_id"],
        "chrono_policy_version": protocol["chrono_task_policy"]["policy_version"],
        "dataset_manifest_sha256": _sha256(dataset_manifest.resolve()),
        "selected_designs_per_case": {
            case_id: int(value["selected_unique_designs"])
            for case_id, value in manifest["cases"].items()
        },
        "development_rows": receipt["partition_locators"]["development"]["rows"],
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
        Gate0V3ValidationError,
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
