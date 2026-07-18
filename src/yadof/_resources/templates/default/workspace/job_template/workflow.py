"""Pure-Python starter workflow: assigned variables -> generic rawData."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import traceback

import numpy as np

from parameters_constraints import get_parameters
from yadof.job_template import RAWDATA_SCHEMA_VERSION


ROOT = Path(__file__).resolve().parent
INDIVIDUAL_METADATA_PATH = ROOT / "individual_metadata.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_metadata(payload: dict[str, object]) -> None:
    temporary = INDIVIDUAL_METADATA_PATH.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, INDIVIDUAL_METADATA_PATH)


def main() -> int:
    metadata: dict[str, object] = {"status": "running", "started_at": _now()}
    _write_metadata(metadata)
    try:
        values = np.asarray([parameter.value for parameter in get_parameters()], dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("starter workflow requires assigned finite parameter values")

        response = np.asarray(float(np.mean(values**2)), dtype=float)
        rawdata_dir = ROOT / "rawData"
        rawdata_dir.mkdir(exist_ok=True)
        rawdata_metadata = {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": list(response.shape),
            "rawdata_name": "response",
        }
        output = rawdata_dir / "response.npz"
        np.savez(
            output,
            values=response,
            metadata=json.dumps(rawdata_metadata, sort_keys=True),
        )
        metadata.update(
            {
                "status": "done",
                "ended_at": _now(),
                "rawdata_files": [output.name],
            }
        )
        _write_metadata(metadata)
        return 0
    except Exception as exc:
        metadata.update(
            {
                "status": "error",
                "ended_at": _now(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc().splitlines()[-20:],
            }
        )
        _write_metadata(metadata)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
