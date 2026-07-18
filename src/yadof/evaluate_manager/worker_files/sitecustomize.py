"""Fail a transferred job early when its installed yadof runtime is incompatible."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "yadof_worker_config.json"
METADATA_PATH = ROOT / "individual_metadata.json"


def _fail(message: str, *, expected: str = "", actual: str = "") -> None:
    payload = {
        "status": "error",
        "failure_stage": "worker_bootstrap",
        "error_type": "YadofWorkerCompatibilityError",
        "error_message": message,
        "expected_yadof_version": expected,
        "actual_yadof_version": actual,
        "worker_python_executable": sys.executable,
        "worker_bootstrap_failed_at": datetime.now(timezone.utc).isoformat(),
    }
    temporary = METADATA_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, METADATA_PATH)
    print(f"yadof worker bootstrap failed: {message}", file=sys.stderr, flush=True)
    os._exit(86)


if CONFIG_PATH.is_file():
    try:
        worker_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        expected_version = str(worker_config["yadof_version"])
    except Exception as exc:
        _fail(f"invalid yadof worker config: {type(exc).__name__}: {exc}")
    try:
        import yadof
    except Exception as exc:
        _fail(
            "compatible yadof is not importable on this worker: "
            f"{type(exc).__name__}: {exc}",
            expected=expected_version,
        )
    actual_version = str(getattr(yadof, "__version__", ""))
    if actual_version != expected_version:
        _fail(
            f"yadof version mismatch: expected {expected_version}, got {actual_version or '<missing>'}",
            expected=expected_version,
            actual=actual_version,
        )
