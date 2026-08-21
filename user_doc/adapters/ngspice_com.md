# `ngspice_com.py`

Use this adapter for local or distributed ngspice circuit simulation. It launches
one batch subprocess per workflow evaluation, so candidates do not share simulator
state. The executable is selected by the `YADOF_NGSPICE_EXE` environment variable
on the machine that executes the workflow.

Ngspice batch evaluations are often fast and workspace-local. After checking the
netlist, executable, output paths, and an estimated evaluation count, an agent may
run a smoke test or an explicitly bounded optimization without separate
confirmation when the expected total cost is modest. Use explicit generation and
resource bounds; complex circuits, very long transients, shared remote execution,
or uncertain runtime follow the central
[execution policy](../config_and_run.md#execution-authority-and-cost-based-agent-judgment)
and may still require authorization.

Copy the packaged resource into the workspace before importing it:

```powershell
yadof task copy-adapter ngspice_com.py --workspace PATH
```

## Netlist contract

Keep the task's source netlist declarative. It must contain exactly one top-level
`.end`, the circuit and model statements, and either one batch analysis statement
such as `.tran`, `.ac`, or `.dc`, or an analysis supplied to `analyze()`. Do not put
`.control`/`.endc` in the source netlist: the adapter owns that block so it can apply
parameters, request deterministic ASCII output, run once, write the rawfile, and
quit without changing the source file.

Top-level values varied by yadof must be declared as ngspice parameters:

```text
RC low-pass
.param resistance=1k
V1 in 0 pulse(0 1 0 1u 1u 10m 20m)
R1 in out {resistance}
C1 out 0 1u
.tran 100u 10m
.end
```

Relative `.include`/`.lib` paths are resolved from the adapter work directory,
which defaults to the source netlist directory. Keep the netlist and its relative
dependencies together below `job_template/` so every prepared job is
self-contained.

## Initialize and set parameters

```python
from pathlib import Path

from ngspice_com import solver_init, set_para, set_variables

BASE_DIR = Path(__file__).resolve().parent
session = solver_init(BASE_DIR / "circuit.cir")
set_para(session, BASE_DIR / "parameters_constraints.py")
```

`set_para()` reads the assigned job-local `PARAMETERS`; each value is formatted as
`value + unit`. Use ngspice scale suffixes such as `k`, `Meg`, `u`, or `n` as the
yadof parameter unit when appropriate. The parameter names must match top-level
`.param` names in the netlist.

Use `set_variables()` for task-local parameter values that do not come from the
optimizer:

```python
set_variables(session, {"temperature_offset": 5, "load_capacitance": "2u"})
```

The original netlist is never edited. `analyze()` writes a candidate-specific
driver netlist containing `alterparam`, then `reset`, then the analysis command.
The rawfile must remain below `work_dir` and its work-relative path must not contain
whitespace; the default names satisfy this rule even when the workspace path itself
contains spaces. This avoids ngspice control-language ambiguity around quoted
Windows output paths.

## Run a simulation

```python
from ngspice_com import analyze

result = analyze(
    session,
    analysis_command="run",
    vectors=("all",),
    timeout=120,
    rawfile=BASE_DIR / "ngspice.raw",
    logfile=BASE_DIR / "ngspice.log",
    driver_netlist=BASE_DIR / "ngspice_yadof.cir",
)
```

`run` executes the analysis statement in the declarative netlist. To select the
analysis from workflow task code, omit that statement from the netlist and pass an
ngspice control command such as `analysis_command="ac dec 20 1k 1Meg"`.

The adapter invokes ngspice with `-n -b`: user `.spiceinit` files are ignored and no
GUI is opened. A nonzero process exit, timeout, missing output, or invalid rawfile
raises `NgspiceError`, which `worker_misc.run_workflow()` records as an individual
failure.

## Export rawData

```python
from ngspice_com import save_result

save_result(
    result,
    "v(out)",
    component="real",
    out_dir=context.raw_data_dir,
    output_name="output_voltage",
    metadata={"task_quantity": "output_voltage"},
)
```

`save_result()` reads the single-plot ASCII rawfile, selects one vector, and writes
a schema-versioned float `.npz` file. Multi-point data uses ngspice's scale vector
(normally time, frequency, or a DC sweep) as its yadof rawData axis. A one-point
result is exported as a scalar.

AC vectors are complex. Choose the scientific representation explicitly with
`component="real"`, `"imag"`, `"magnitude"`, `"phase_rad"`, `"phase_deg"`, or
`"db20"`; complex arrays are not passed implicitly into the float surrogate path.
Call `save_result()` once per vector/component that the task needs. Objective
selection and thresholds remain in workspace `calc_cost.py`.

## Workflow pattern

```python
from pathlib import Path

from ngspice_com import analyze, save_result, set_para, solver_init

BASE_DIR = Path(__file__).resolve().parent


def _evaluate(context) -> None:
    session = solver_init(BASE_DIR / "circuit.cir")
    set_para(session, BASE_DIR / "parameters_constraints.py")
    result = analyze(session)
    save_result(
        result,
        "v(out)",
        out_dir=context.raw_data_dir,
        output_name="output_voltage",
    )
```

Wrap this task callback with the standard job-local
`worker_misc.run_workflow()` lifecycle as described in
[Typical workflow patterns](../workflow_typical_patterns.md).
