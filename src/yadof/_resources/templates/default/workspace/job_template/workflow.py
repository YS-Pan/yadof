"""Pure-Python starter workflow: assigned variables -> generic rawData."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import traceback
import zipfile

import numpy as np

from parameters_constraints import get_parameters


RAWDATA_SCHEMA_VERSION = 1
ROOT = Path(__file__).resolve().parent
INDIVIDUAL_METADATA_PATH = ROOT / "individual_metadata.json"
RAW_DATA_DIR = ROOT / "rawData"
RAW_DATA_ZIP = ROOT / "rawData.zip"


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


def _write_rawdata_zip() -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    entries = sorted(RAW_DATA_DIR.iterdir(), key=lambda path: path.name.casefold())
    invalid = [
        path.name
        for path in entries
        if path.is_dir() or not path.is_file() or path.suffix.casefold() != ".npz"
    ]
    files = [
        path
        for path in entries
        if path.is_file() and path.suffix.casefold() == ".npz"
    ]
    temporary = RAW_DATA_ZIP.with_name(RAW_DATA_ZIP.name + ".tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    os.replace(temporary, RAW_DATA_ZIP)
    if invalid:
        raise ValueError(
            "rawData must contain only direct .npz files; invalid entries: "
            + ", ".join(invalid)
        )


def main() -> int:
    metadata: dict[str, object] = {"status": "running", "started_at": _now()}
    _write_metadata(metadata)
    try:
        values = np.asarray([parameter.value for parameter in get_parameters()], dtype=float)
        if not np.all(np.isfinite(values)):
            raise ValueError("starter workflow requires assigned finite parameter values")

        response = np.asarray(float(np.mean(values**2)), dtype=float)
        RAW_DATA_DIR.mkdir(exist_ok=True)
        rawdata_metadata = {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "shape": list(response.shape),
            "rawdata_name": "response",
        }
        output = RAW_DATA_DIR / "response.npz"
        np.savez(
            output,
            values=response,
            metadata=json.dumps(rawdata_metadata, sort_keys=True),
        )
        _write_rawdata_zip()
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
        _write_rawdata_zip()
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
