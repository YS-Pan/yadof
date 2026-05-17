"""Workflow entry point.

This module converts unnormalized optimization variables into rawData ``.npz``
files under ``rawData/``. It must not calculate or save cost.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

try:
    from . import test_com
    from .parameters_constraints import get_parameters
    from .rawdata_contract import validate_rawdata_directory, with_schema_version
except ImportError:  # Allows copied job folders to run workflow.py directly.
    import test_com
    from parameters_constraints import get_parameters
    from rawdata_contract import validate_rawdata_directory, with_schema_version


BASE_DIR = Path(__file__).resolve().parent
RAWDATA_DIR = BASE_DIR / "rawData"
INDIVIDUAL_METADATA_PATH = BASE_DIR / "individual_metadata.json"
INDIVIDUAL_METADATA_SCHEMA_VERSION = 1


def _variables_mapping(variables: Mapping[str, float] | Sequence[float]) -> dict[str, float]:
    if isinstance(variables, Mapping):
        return {str(name): float(value) for name, value in variables.items()}
    names = [parameter.name for parameter in get_parameters()]
    values = tuple(float(value) for value in variables)
    if len(names) != len(values):
        raise ValueError(f"expected {len(names)} variables, got {len(values)}")
    return dict(zip(names, values))


def _metadata_json(metadata: Mapping[str, object]) -> np.ndarray:
    return np.asarray(json.dumps(dict(metadata), ensure_ascii=False), dtype=np.str_)


def run_workflow(
    variables: Mapping[str, float] | Sequence[float],
    output_dir: str | Path | None = None,
    job_metadata: Mapping[str, object] | None = None,
) -> tuple[Path, ...]:
    rawdata_dir = Path(output_dir) if output_dir is not None else RAWDATA_DIR
    rawdata_dir.mkdir(parents=True, exist_ok=True)
    if any(path.is_dir() for path in rawdata_dir.iterdir()):
        raise ValueError("rawData directory must not contain subdirectories")

    variable_map = _variables_mapping(variables)
    generated_at = datetime.now(timezone.utc).isoformat()
    saved_paths: list[Path] = []

    for name, block in test_com.evaluate_raw_data(variable_map).items():
        metadata = with_schema_version(dict(block["metadata"]))  # type: ignore[arg-type]
        metadata.update(
            {
                "rawdata_name": name,
                "generated_at": generated_at,
            }
        )
        arrays = dict(block["arrays"])  # type: ignore[arg-type]
        path = rawdata_dir / f"{name}.npz"
        np.savez_compressed(path, **arrays, metadata=_metadata_json(metadata))
        saved_paths.append(path)

    return validate_rawdata_directory(rawdata_dir)


def main() -> None:
    variables_path = BASE_DIR / "variables.json"
    job_input_path = BASE_DIR / "job_input.json"
    job_name = BASE_DIR.name
    context: dict[str, object] = {}
    if variables_path.exists():
        variables = json.loads(variables_path.read_text(encoding="utf-8"))
    elif job_input_path.exists():
        payload = json.loads(job_input_path.read_text(encoding="utf-8"))
        job_name = str(payload.get("job_name") or job_name)
        raw_context = payload.get("evaluation_context", {})
        if isinstance(raw_context, Mapping):
            context = {str(key): value for key, value in raw_context.items()}
        variables = payload.get("unnormalized_variables", payload.get("raw_variables"))
        if variables is None:
            raise ValueError(f"{job_input_path} must contain unnormalized_variables")
    else:
        raise FileNotFoundError(f"missing variables file: {variables_path} or {job_input_path}")
    _update_individual_metadata(
        {
            "schema_version": INDIVIDUAL_METADATA_SCHEMA_VERSION,
            "job_name": job_name,
            "status": "running",
            "started_at": _now_text(),
            "workflow_pid": os.getpid(),
            **context,
        }
    )
    try:
        saved_paths = run_workflow(variables)
    except Exception as exc:
        _update_individual_metadata(
            {
                "status": "error",
                "ended_at": _now_text(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            }
        )
        raise
    _update_individual_metadata(
        {
            "status": "done",
            "ended_at": _now_text(),
            "raw_data_files": [path.name for path in saved_paths],
        }
    )


def _update_individual_metadata(update: Mapping[str, object]) -> None:
    metadata = _read_individual_metadata()
    metadata.update(dict(update))
    temp_path = INDIVIDUAL_METADATA_PATH.with_suffix(INDIVIDUAL_METADATA_PATH.suffix + ".tmp")
    temp_path.write_text(
        json.dumps(metadata, ensure_ascii=True, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    temp_path.replace(INDIVIDUAL_METADATA_PATH)


def _read_individual_metadata() -> dict[str, object]:
    if not INDIVIDUAL_METADATA_PATH.is_file():
        return {}
    try:
        loaded = json.loads(INDIVIDUAL_METADATA_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(loaded) if isinstance(loaded, dict) else {}


def _now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


if __name__ == "__main__":
    main()
