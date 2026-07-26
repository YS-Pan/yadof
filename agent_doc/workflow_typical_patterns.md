# Typical `workflow.py` Patterns

`workflow.py` is copied into each job folder and executed there. It receives one
individual's variables and writes rawData. It should be written as task code, not as
framework code.

The dividing rule is strict: code that can change with the optimization task stays
in `workflow.py`; code that is identical across tasks belongs in yadof. The copied
package-owned `worker_misc.py` is the execute-side yadof support surface. Call it
instead of duplicating lifecycle, path, metadata, machine-detection, packaging, or
generic error-handling code.

## Required Contract

A good workflow does these things:

- reads assigned values from the job-local `parameters_constraints.py`,
- writes rawData `.npz` files directly under `rawData/`,
- calls `worker_misc.run_workflow()` around the task-specific operation,
- never writes `cost.json` and never calculates final objective costs.

`run_workflow()` owns `individual_metadata.json`, `execute_machine`, timestamps,
running/done/error status, exception diagnostics, standard job paths, rawData
preparation, flat `rawData.zip`, and re-raising task failures. The installed package
copies this stable helper into each prepared job. Do not place your own
`worker_misc.py` or
case-variant equivalent in workspace `job_template/`: that filename is reserved and
job preparation rejects a collision instead of overwriting it.

Local jobs consume `rawData/` directly. Distributed jobs run `workflow.py` directly
and HTCondor returns the helper-created `rawData.zip` instead of the directory. Do
not import yadof from workflow or assigned parameter code: yadof is intentionally
not sent to execute nodes. `worker_misc` becomes importable after yadof prepares the
job; importing an unprepared workspace workflow should remain non-executing.

## Minimal Skeleton

```python
from __future__ import annotations

import json

import numpy as np

from parameters_constraints import get_parameters


def _save_rawdata(context, name: str, values: np.ndarray, axis: np.ndarray) -> None:
    from worker_misc import rawdata_metadata

    values = np.asarray(values, dtype=float)
    metadata = rawdata_metadata(
        name,
        values.shape,
        extra={
            "axis_names": ["x"],
            "axes": [
                {
                    "index": 0,
                    "size": int(values.shape[0]),
                    "name": "x",
                    "values_key": "axis_x",
                },
            ],
        },
    )
    np.savez_compressed(
        context.raw_data_dir / f"{name}.npz",
        values=values,
        axis_x=np.asarray(axis, dtype=float),
        metadata=json.dumps(metadata, ensure_ascii=True),
    )


def _evaluate(context) -> None:
    parameters = get_parameters()
    variables = {parameter.name: parameter.value for parameter in parameters}
    # Convert task variables -> task rawData here.
    x = np.linspace(0.0, 1.0, 101)
    y = np.sin(float(next(iter(variables.values()))) * x)
    _save_rawdata(context, "response_curve", y, x)


def main() -> None:
    from worker_misc import run_workflow

    run_workflow(_evaluate)


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

The zip must also be flat. Valid members look like `response_curve.npz`; invalid
members include `rawData/response_curve.npz`, any directory, or a non-`.npz` file.
The helper enforces this rule and publishes the zip atomically.

Avoid storing the full variable vector in every rawData metadata item. The framework
records variables separately.

## Adapter Workflow Pattern

If `workflow.py` calls an external simulator or custom evaluator, copy the needed
`*_com.py` file with `yadof task copy-adapter` into the workspace `job_template/`, then import it
by same-directory name.

Read `agent_doc/adapters/README.md` first, then read the document for the specific
adapter:

- `agent_doc/adapters/hfss_com.md` for HFSS/PyAEDT workflows.
- `agent_doc/adapters/test_com.md` for pure-Python synthetic workflows.

A workflow should use adapter functions only to produce rawData. Final objective
costs still belong in `calc_cost.py`.

When an adapter accepts a parameter file, pass the job-local
`parameters_constraints.py` directly. That file is already the assigned snapshot
for the current individual; do not reconstruct a second parameter file from legacy
job-input helpers.

## Error Handling

Do not duplicate a top-level lifecycle `try/except` in task code.
`run_workflow()` preserves already-written rawData, attempts the transfer archive,
writes standard error fields, runs optional cleanup, and re-raises the task failure.

For a simulator that needs task-specific cleanup, pass a callback:

```python
run_workflow(_evaluate, cleanup=_close_task_simulator)
```

The callback contains only simulator-specific cleanup. The helper owns cleanup
failure reporting and preserves the original task exception when both stages fail.
