"""Validate Gate 0 v1 plus the immutable v2 quality/regime amendment."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Mapping, Sequence


ROOT = Path(__file__).resolve().parent
PARENT_ROOT = ROOT.parent / "20260827-new-surrogate-qnehvi"
AMENDMENT_PATH = ROOT / "benchmark_preregistration.amendment.json"
PROTOCOL_PATH = ROOT / "quality_regime_protocol.json"
THRESHOLD_PATH = ROOT / "acceptance_thresholds.template.json"
EVIDENCE_PATH = ROOT / "noise_audit_evidence.json"


class Gate0V2ValidationError(RuntimeError):
    pass


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise Gate0V2ValidationError(message)


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
    path = PARENT_ROOT / "validate.py"
    spec = importlib.util.spec_from_file_location("gate0_v1_validator", path)
    _require(spec is not None and spec.loader is not None, "cannot load v1 validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.validate()
    _require(result["ok"] is True, "Gate 0 v1 validator did not pass")
    _require(result["formal_test_ready"] is False, "v1 formal test must remain blocked")
    _require(result["simulator_launched"] is False, "v1 validator launched a simulator")
    return result


def _null_count(value: object) -> int:
    if value is None:
        return 1
    if isinstance(value, Mapping):
        return sum(_null_count(item) for item in value.values())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return sum(_null_count(item) for item in value)
    return 0


def _validate_integrity(amendment: Mapping[str, object]) -> None:
    integrity = amendment["artifact_integrity"]
    for name, expected in integrity["parent"].items():
        path = PARENT_ROOT / str(name)
        _require(path.is_file(), f"missing frozen v1 artifact {name}")
        _require(_sha256(path) == expected, f"frozen v1 artifact drifted: {name}")
    for name, expected in integrity["v2"].items():
        path = ROOT / str(name)
        _require(path.is_file(), f"missing v2 artifact {name}")
        _require(_sha256(path) == expected, f"v2 artifact drifted: {name}")


def _validate_protocol(protocol: Mapping[str, object]) -> None:
    _require(
        protocol["protocol_id"] == "new-surrogate-quality-regime-v1",
        "quality/regime protocol ID drifted",
    )
    forbidden = set(protocol["core_boundary"]["forbidden_in_core"])
    _require(
        "Chrono field-name or threshold rules" in forbidden,
        "core/task boundary no longer excludes Chrono rules",
    )
    model = protocol["model_semantics"]
    _require(
        model["observation_noise"] == "zero; regime uncertainty is epistemic/structural",
        "zero-observation-noise interpretation drifted",
    )
    expected_ablations = {
        "no-gating",
        "robust-weighting-only",
        "shared-latent-isolation",
        "gated-private-residual",
    }
    _require(
        set(protocol["required_ablations"]) == expected_ablations,
        "quality/regime ablation matrix drifted",
    )
    inventory = _load_json(PARENT_ROOT / "schema_inventory.json")
    chrono_fields = {
        tuple(field["selector"]): tuple(field["shape"])
        for field in inventory["cases"]["chrono"]["fields"]
    }
    selectors = {
        tuple(selector)
        for selector in protocol["chrono_task_policy"]["design_regime_fields"]
    }
    _require(len(selectors) == 7, "Chrono policy must scope exactly seven curves")
    _require(
        all(chrono_fields.get(selector) == (513,) for selector in selectors),
        "Chrono policy curve selectors drifted from the frozen inventory",
    )
    rules = protocol["chrono_task_policy"]["ordered_rules"]
    _require([rule["regime"] for rule in rules] == ["failure", "chatter"], "Chrono diagnostic rule priority drifted")


def _validate_thresholds(thresholds: Mapping[str, object]) -> None:
    _require(thresholds["status"] == "unsealed", "v2 thresholds must remain unsealed")
    _require(thresholds["formal_test_ready"] is False, "v2 formal test must remain blocked")
    expected = int(thresholds["null_count_expected"])
    actual = _null_count(
        {
            key: value
            for key, value in thresholds.items()
            if key not in {"null_count_expected", "note"}
        }
    )
    _require(actual == expected, f"expected {expected} null thresholds, found {actual}")
    _require(
        set(thresholds["evidence_partition_forbidden"])
        == {"offline-test", "formal-optimization-test"},
        "threshold sealing evidence boundary drifted",
    )


def _validate_evidence(evidence: Mapping[str, object]) -> int:
    _require(evidence["formal_dataset_or_test_accessed"] is False, "noise audit was misclassified as formal evidence")
    _require(evidence["source"]["row_count"] == 1929, "noise audit row count drifted")
    verified = 0
    for stem in ("summary", "examples", "scatter"):
        relative = evidence["source"][f"{stem}_path_at_registration"]
        path = (ROOT / str(relative)).resolve()
        expected = evidence["source"][f"{stem}_sha256"]
        if path.is_file():
            _require(_sha256(path) == expected, f"noise audit {stem} evidence drifted")
            verified += 1
    return verified


def validate() -> dict[str, object]:
    parent = _validate_parent()
    amendment = _load_json(AMENDMENT_PATH)
    protocol = _load_json(PROTOCOL_PATH)
    thresholds = _load_json(THRESHOLD_PATH)
    evidence = _load_json(EVIDENCE_PATH)
    _validate_integrity(amendment)
    _validate_protocol(protocol)
    _validate_thresholds(thresholds)
    verified = _validate_evidence(evidence)
    _require(
        amendment["dataset_generation_plan"]["seeds"]
        == [253655847, 1388783452],
        "dataset-generation seeds drifted",
    )
    _require(
        amendment["dataset_generation_plan"]["planned_total_attempted_evaluations"]
        == 12000,
        "dataset-generation budget drifted",
    )
    _require(amendment["thresholds"]["formal_test_ready"] is False, "amendment must block formal test")
    _require(amendment["readiness"]["eligible_frozen_dataset_available"] is False, "no sealed v2 dataset is registered")
    _require(amendment["readiness"]["simulator_launched_by_preregistration"] is False, "preregistration must not launch simulation")
    return {
        "schema_version": 1,
        "view": "gate0-v2-quality-regime-validation",
        "ok": True,
        "preregistration_id": amendment["preregistration_id"],
        "parent_preregistration_id": parent["preregistration_id"],
        "parent_validator_ok": True,
        "quality_protocol_id": protocol["protocol_id"],
        "required_ablation_count": len(protocol["required_ablations"]),
        "null_threshold_count": thresholds["null_count_expected"],
        "external_noise_evidence_files_verified": verified,
        "formal_test_ready": False,
        "simulator_launched": False,
    }


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = validate()
    except (Gate0V2ValidationError, KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"schema_version": 1, "ok": False, "error": str(exc)}, sort_keys=True))
        return 1
    print(json.dumps(result, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
