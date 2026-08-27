"""Revalidate the v9 receipt against final wheel and public canary evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yadof
from yadof.recorded_data import list_optimization_metadata, list_records


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parent.parent.parent
OUTER_ROOT = REPOSITORY_ROOT.parent
RECEIPT_PATH = ROOT / "framework_result_receipt.json"


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


def validate_result() -> dict[str, object]:
    receipt = _json(RECEIPT_PATH)
    _require(
        receipt["status"] == "complete-framework-mechanism-performance-not-accepted",
        "v9 result status drifted",
    )
    package = dict(receipt["installed_package"])
    wheel_path = REPOSITORY_ROOT / str(package["wheel_path"])
    _require(_sha256(wheel_path) == package["wheel_sha256"], "wheel hash drifted")
    _require(
        "site-packages" in str(Path(yadof.__file__).resolve()).casefold(),
        "result validator must use installed yadof",
    )
    source = dict(receipt["source"])
    source_paths = {
        "posterior_assisted_sha256": "src/yadof/optimize/posterior_assisted.py",
        "qnehvi_acquisition_sha256": "src/yadof/optimize/qnehvi_acquisition.py",
        "exploitation_sha256": "src/yadof/surrogate/exploitation.py",
        "focused_test_sha256": "tests/test_posterior_assisted_strategy.py",
        "change_record_sha256": "dev_doc/change_records/20260828_020622_qnehvi-posterior-assisted-framework.md",
    }
    for name, relative in source_paths.items():
        _require(
            _sha256(REPOSITORY_ROOT / relative) == source[name],
            f"source hash drifted: {relative}",
        )

    canary = dict(receipt["real_canary"])
    workspace = OUTER_ROOT / "temp" / "082611-qnehvi-framework-canary-v9"
    records = list_records(workspace)
    metadata = list_optimization_metadata(workspace)
    _require(len(records) == int(canary["public_record_count"]), "record count drifted")
    _require(len(metadata) == 1, "canary optimization metadata count drifted")
    latest = metadata[0]
    diagnostics = dict(latest["diagnostics"])
    _require(latest["strategy_signature"] == canary["strategy_signature"], "strategy signature drifted")
    _require(latest["task_snapshot_id"] == canary["task_snapshot_id"], "task snapshot drifted")
    _require(latest["source"] == canary["source"], "canary source drifted")
    _require(latest["surrogate_used"] is False, "canary used a surrogate")
    _require(diagnostics["fallback_reason"] == canary["fallback_reason"], "fallback reason drifted")
    _require(diagnostics["evaluation_handoff"] == canary["evaluation_handoff"], "evaluation handoff drifted")
    _require(
        all(record["status"] == "completed" for record in records),
        "canary contains a non-completed record",
    )
    boundary = dict(receipt["scientific_boundary"])
    _require(boundary["architecture_performance_accepted"] is False, "performance boundary changed")
    _require(boundary["transferable_calibration_available"] is False, "calibration boundary changed")
    _require(boundary["todo_082611_may_archive"] is False, "082611 archive boundary changed")
    return {
        "protocol": "yadof.082611.framework-result-validation",
        "protocol_version": 1,
        "status": "valid-complete-framework-mechanism-performance-not-accepted",
        "receipt_sha256": _sha256(RECEIPT_PATH),
        "wheel_sha256": package["wheel_sha256"],
        "public_record_count": len(records),
        "source": latest["source"],
        "fallback_reason": diagnostics["fallback_reason"],
        "surrogate_used": latest["surrogate_used"],
        "performance_accepted": False,
        "082612_started": False,
    }


if __name__ == "__main__":
    print(json.dumps(validate_result(), sort_keys=True, allow_nan=False))
