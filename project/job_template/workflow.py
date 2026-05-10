"""Workflow entry point.

This module converts unnormalized optimization variables into rawData ``.npz``
files under ``rawData/``. It must not calculate or save cost.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

try:
    from . import test_com
    from .parameters_constraints import get_parameters
except ImportError:  # Allows copied job folders to run workflow.py directly.
    import test_com
    from parameters_constraints import get_parameters


BASE_DIR = Path(__file__).resolve().parent
RAWDATA_DIR = BASE_DIR / "rawData"


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
        metadata = dict(block["metadata"])  # type: ignore[arg-type]
        metadata.update(
            {
                "rawdata_name": name,
                "generated_at": generated_at,
                "variables": variable_map,
                "job_metadata": dict(job_metadata or {}),
            }
        )
        arrays = dict(block["arrays"])  # type: ignore[arg-type]
        path = rawdata_dir / f"{name}.npz"
        np.savez_compressed(path, **arrays, metadata=_metadata_json(metadata))
        saved_paths.append(path)

    return tuple(saved_paths)


def main() -> None:
    variables_path = BASE_DIR / "variables.json"
    job_input_path = BASE_DIR / "job_input.json"
    if variables_path.exists():
        variables = json.loads(variables_path.read_text(encoding="utf-8"))
    elif job_input_path.exists():
        payload = json.loads(job_input_path.read_text(encoding="utf-8"))
        variables = payload.get("unnormalized_variables", payload.get("raw_variables"))
        if variables is None:
            raise ValueError(f"{job_input_path} must contain unnormalized_variables")
    else:
        raise FileNotFoundError(f"missing variables file: {variables_path} or {job_input_path}")
    run_workflow(variables)


if __name__ == "__main__":
    main()
