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

Fast does not execute `workflow.py`. It requires sibling `evaluation.py` and calls
`evaluate_rawdata(parameters, context)` inside a reusable isolated worker process.
Keep one task algorithm by importing that kernel from ordinary `workflow.py` and
only adapting its returned memory payloads to job-local files there.

## Shared Fast/Prepared Kernel

`evaluation.py` must not import yadof or calculate costs:

```python
from __future__ import annotations

import json
import numpy as np


def evaluate_rawdata(parameters, context):
    value = float(parameters["input_value"])
    response = np.asarray(value * value, dtype=float)
    return {
        "response.npz": {
            "values": response,
            "metadata": json.dumps(
                {
                    "schema_version": 1,
                    "rawdata_name": "response",
                    "shape": list(response.shape),
                }
            ),
        }
    }, {"simulator_returncode": 0}
```

`parameters` and `context` are read-only mappings. Context keys include
`evaluation_name`, `scratch_dir`, `environment`, `timeout_sec`, `run_id`,
`optimization_index`, `generation_index`, and `population_index`; none is a job
path. Return diagnostics as JSON-compatible values. A task exception, worker exit,
or timeout affects only this individual and causes worker replacement.

The prepared `workflow.py` wrapper can call the same kernel:

```python
from types import MappingProxyType
import numpy as np
from evaluation import evaluate_rawdata
from parameters_constraints import get_parameters


def _evaluate(context):
    parameters = MappingProxyType(
        {parameter.name: float(parameter.value) for parameter in get_parameters()}
    )
    items, _diagnostics = evaluate_rawdata(
        parameters,
        MappingProxyType(
            {
                "evaluation_name": context.base_dir.name,
                "scratch_dir": context.temp_dir,
                "environment": MappingProxyType({}),
            }
        ),
    )
    for filename, payload in items.items():
        np.savez_compressed(context.raw_data_dir / filename, **payload)
```

For an external subprocess, use `context["scratch_dir"]` as its explicit working
directory, merge `context["environment"]` into a copied environment, capture the
actual return code/stderr/elapsed time in task diagnostics, and parse required
outputs into memory before returning. The scratch directory can involve real disk
I/O, but it is never a durable job, evidence, or recovery path.

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

Choose the surrogate evidence at the workflow boundary. Save the complete numeric
shape needed by the task's intended prediction and cost contract, but do not save
objective-irrelevant numeric fields or regions in the hope that `calc_cost.py` can
de-emphasize them later. Surrogate training has no task-owned attention mask: every
modeled numeric rawData field receives equal field-level importance.

## Adapter Workflow Pattern

If `workflow.py` calls an external simulator or custom evaluator, copy the needed
`*_com.py` file with `yadof task copy-adapter` into the workspace `job_template/`, then import it
by same-directory name.

Read `user_doc/adapters/README.md` first, then read the document for the specific
adapter:

- `user_doc/adapters/hfss_com.md` for HFSS/PyAEDT workflows.
- `user_doc/adapters/ngspice_com.md` for ngspice batch-process workflows.
- `user_doc/adapters/test_com.md` for pure-Python synthetic workflows.
- `user_doc/adapters/chrono_com.md` for a separately provisioned PyChrono process.

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
