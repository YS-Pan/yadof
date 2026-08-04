# Project Chrono subprocess adapter

`chrono_com.py` runs task-owned Project Chrono mechanics in a separate Python
process. The yadof process never imports `pychrono`, and the PyChrono environment
does not need yadof installed. Parameters cross the boundary as bounded JSON;
validated evidence returns as schema-versioned NPZ files.

## Runtime setup

An administrator provisions Project Chrono separately and exposes its absolute
interpreter path to every evaluation host:

```powershell
[Environment]::SetEnvironmentVariable(
  "YADOF_PYCHRONO_PYTHON",
  "C:\ProgramData\Miniforge3\envs\pychrono-10\python.exe",
  "Machine"
)
```

The adapter does not run `conda activate`, search `PATH`, alter `PATH`, install
packages, or fall back to yadof's interpreter. Restart the calling process after a
machine-level environment change. For distributed execution, the same absolute
path must exist and be executable on the selected execute host.

Copy the adapter into the selected workspace without overwriting task code:

```powershell
yadof task copy-adapter chrono_com.py --workspace D:\work\chrono-study
```

Keep `chrono_com.py`, `chrono_worker.py`, and the importing workflow/evaluation
module together in `job_template/`. Prepared jobs then carry the task-owned copies.

## Task-owned `chrono_worker.py`

The worker owns every mechanical decision. The template below deliberately leaves
model construction and measurements as task functions:

```python
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

from chrono_com import worker_main


def run_task_model(chrono, assigned):
    # Build bodies, loads, contacts, solver settings, stepping, and measurements.
    # Return only portable finite numeric evidence required by calc_cost.py.
    raise NotImplementedError("replace with this workspace's mechanics")


def simulate(request, rawdata_dir: Path):
    # Import only after worker_main has validated the request.
    import pychrono as chrono

    assigned = request["parameters"]["assigned"]
    response = np.asarray(run_task_model(chrono, assigned), dtype=np.float64)
    metadata = {
        "schema_version": 1,
        "rawdata_name": "response",
        "shape": list(response.shape),
        "axes": [],
        "unit": "task-defined",
    }
    target = rawdata_dir / "response.npz"
    partial = target.with_name(target.name + ".part")
    with partial.open("wb") as stream:
        np.savez_compressed(
            stream,
            values=response,
            metadata=np.asarray(json.dumps(metadata, separators=(",", ":"))),
        )
    os.replace(partial, target)
    return {"pychrono_version": getattr(chrono, "__version__", "unknown")}


if __name__ == "__main__":
    raise SystemExit(worker_main(simulate))
```

The child must not import yadof. It writes only direct `.npz` files in the
`rawdata_dir` supplied by `worker_main`; the helper validates them, hashes them,
and writes the result manifest last. Do not write objectives or `cost.json` here.

## Prepared local or distributed workflow

Use assigned values from the job-local parameter snapshot. The adapter publishes
only fully validated files to the workflow's final flat `rawData/`:

```python
from pathlib import Path

from chrono_com import run_pychrono
from parameters_constraints import get_parameters


def _evaluate(context):
    assigned = {parameter.name: parameter.value for parameter in get_parameters()}
    result = run_pychrono(
        Path(__file__).with_name("chrono_worker.py"),
        assigned,
        scratch_root=context.temp_dir / "pychrono",
        backend="local",  # use "distributed" on an execute workflow
        rawdata_dir=context.raw_data_dir,
        timeout=900.0,
        evaluation_id=context.base_dir.name,
    )
    # result.as_diagnostics() is bounded diagnostic data, not objective evidence.
```

Wrap `_evaluate` with the normal `worker_misc.run_workflow()` lifecycle. The child
scratch is unique and is removed on success or failure; it is never durable
evidence.

## Fast evaluation

Fast mode loads validated NPZ arrays into memory and publishes no job folder:

```python
from pathlib import Path

from chrono_com import run_pychrono


def evaluate_rawdata(parameters, context):
    result = run_pychrono(
        Path(__file__).with_name("chrono_worker.py"),
        parameters,
        scratch_root=Path(context["scratch_dir"]) / "pychrono",
        backend="fast",
        load_rawdata=True,
        timeout=context.get("timeout_sec"),
        environment=context.get("environment"),
        evaluation_id=context["evaluation_name"],
    )
    return result.rawdata, result.as_diagnostics()
```

The adapter removes inherited `PYTHONPATH`, disables user-site and bytecode writes,
and points `TEMP`/`TMP` at the unique candidate scratch without mutating the parent
environment. It launches an argument vector with the configured absolute
interpreter; paths containing spaces need no manual quoting.

## Failures and diagnostics

`PyChronoError.category` distinguishes configuration, launch, child, protocol,
path, and evidence failures. `as_diagnostics()` (or the exception's
`as_diagnostics()`) contains the return code, bounded stdout/stderr tails,
truncation flags, and a validated child error manifest when available. Important
categories include `runtime_not_configured`, `runtime_invalid`, `worker_missing`,
`timeout`, `cancelled`, `child_reported_error`, `child_process_error`,
`protocol_mismatch`, `output_path_invalid`, and `rawdata_invalid`.

Treat every failure as an evaluation failure. Do not recover partial child files or
convert them into a normal cost. Actual Project Chrono mechanics validation remains
an explicitly authorized integration activity; the package's normal tests use fake
external interpreters and require no global PyChrono installation.
