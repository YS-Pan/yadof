# Typical `workflow.py` Patterns

`workflow.py` is copied into each job folder and executed there. It receives one
individual's variables and writes rawData. It should be written as task code, not as
framework code.

## Required Contract

A good workflow does these things:

- reads assigned values from the job-local `parameters_constraints.py`,
- writes `individual_metadata.json` with `status`, `started_at`, and `ended_at`,
- writes rawData `.npz` files directly under `rawData/`,
- writes `rawData_outputs.zip` after rawData is produced so distributed jobs can transfer outputs,
- records exception details when possible,
- exits with an error when the workflow failed,
- never writes `cost.json` and never calculates final objective costs.

Use helpers from `worker_misc.py`; that file is copied into each job.

## Minimal Skeleton

```python
from __future__ import annotations

import json
import traceback
from pathlib import Path

import numpy as np

from parameters_constraints import get_parameters
from worker_misc import (
    now_text,
    prepare_rawdata_dir,
    raw_data_file_names,
    write_json,
    write_rawdata_transfer_zip,
)

BASE_DIR = Path(__file__).resolve().parent
RAW_DATA_DIR = BASE_DIR / "rawData"
RAW_DATA_TRANSFER_ZIP = BASE_DIR / "rawData_outputs.zip"
INDIVIDUAL_METADATA = BASE_DIR / "individual_metadata.json"


def _save_rawdata(name: str, values: np.ndarray, axis: np.ndarray) -> None:
    values = np.asarray(values, dtype=float)
    metadata = {
        "schema_version": 1,
        "rawdata_name": name,
        "shape": list(values.shape),
        "axis_names": ["x"],
        "axes": [
            {"index": 0, "size": int(values.shape[0]), "name": "x", "values_key": "axis_x"},
        ],
    }
    np.savez_compressed(
        RAW_DATA_DIR / f"{name}.npz",
        values=values,
        axis_x=np.asarray(axis, dtype=float),
        metadata=json.dumps(metadata, ensure_ascii=True),
    )


def main() -> None:
    started_at = now_text()
    prepare_rawdata_dir(RAW_DATA_DIR, RAW_DATA_TRANSFER_ZIP)
    write_json(INDIVIDUAL_METADATA, {"status": "running", "started_at": started_at})

    try:
        parameters = get_parameters()
        variables = {parameter.name: parameter.value for parameter in parameters}
        # Convert variables -> rawData here.
        x = np.linspace(0.0, 1.0, 101)
        y = np.sin(float(next(iter(variables.values()))) * x)
        _save_rawdata("response_curve", y, x)

        write_rawdata_transfer_zip(RAW_DATA_DIR, RAW_DATA_TRANSFER_ZIP)
        write_json(
            INDIVIDUAL_METADATA,
            {
                "status": "done",
                "started_at": started_at,
                "ended_at": now_text(),
                "raw_data_files": raw_data_file_names(RAW_DATA_DIR),
            },
        )
    except Exception as exc:
        write_rawdata_transfer_zip(RAW_DATA_DIR, RAW_DATA_TRANSFER_ZIP)
        write_json(
            INDIVIDUAL_METADATA,
            {
                "status": "error",
                "started_at": started_at,
                "ended_at": now_text(),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback_tail": traceback.format_exc()[-4000:],
                "raw_data_files": raw_data_file_names(RAW_DATA_DIR),
            },
        )
        raise


if __name__ == "__main__":
    main()
```

## RawData `.npz` Shape

Each rawData file needs:

- `values` or `data`: the main numeric array,
- `metadata`: scalar JSON text,
- `metadata["schema_version"] == 1`,
- `metadata["rawdata_name"]`,
- `metadata["shape"]` matching the main array shape,
- optional ordered `axes` descriptors with `index`, `size`, `name`, and `values_key`.

Keep `rawData/` flat. Do not put subfolders inside it.

Avoid storing the full variable vector in every rawData metadata item. The framework
records variables separately.

## Adapter Workflow Pattern

If `workflow.py` calls an external simulator or custom evaluator, copy the needed
`*_com.py` file from `project/com_lib/` into `project/job_template/`, then import it
by same-directory name.

Read `user_doc/com_lib/README.md` first, then read the document for the specific
adapter:

- `user_doc/com_lib/hfss_com.md` for HFSS/PyAEDT workflows.
- `user_doc/com_lib/test_com.md` for pure-Python synthetic workflows.

A workflow should use adapter functions only to produce rawData. Final objective
costs still belong in `calc_cost.py`.

When an adapter accepts a parameter file, pass the job-local
`parameters_constraints.py` directly. That file is already the assigned snapshot
for the current individual; do not reconstruct a second parameter file from legacy
job-input helpers.

## Error Handling

Prefer one top-level `try` block around the simulation section. On failure:

- preserve any rawData that was already written,
- write `individual_metadata.json` with `status = "error"`,
- include `error_type`, `error_message`, and a short `traceback_tail`,
- re-raise the exception so the local or distributed runner can mark the job failed.

For simulators that need cleanup, keep cleanup in `finally`. If cleanup itself fails
after a successful simulation, write a clear error metadata record.
