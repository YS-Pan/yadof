# Define an optimization task

All paths below are relative to a selected workspace.

## 1. Parameters

`job_template/parameters_constraints.py` returns yadof `Parameter` objects. Keep the
canonical definitions unassigned; job preparation writes a fresh assigned snapshot
for each normalized candidate. Parameter names, ranges, units, constraints, and
count come from this task file, not framework config.

For AEDT projects, extraction is an explicit, backed-up workspace operation:

```powershell
yadof task hfss extract-parameters --workspace D:\work\study-a `
  --project job_template\model.aedt --design MyDesign --yes
```

The command first parses the AEDT file directly, including optimization attributes
stored inline in `VariableProp(...)`. Continuous variables use their Optimetrics
`Min`/`Max` bounds; discrete variables use the values in `Level`. Direct parsing does
not launch AEDT. If direct parsing cannot obtain any parameters, the command falls
back to PyAEDT; `--design` selects the fallback design, `--graphical` permits a
graphical session, and `--verbose` exposes fallback diagnostics. Relative project
paths resolve from the workspace root. When `--project` is omitted, exactly one
`.aedt` file must exist in `job_template/`.

Before replacement, the current parameter file is copied to
`.yadof/tool_output/parameter_history/`. The operation preserves the rest of a
current-format file, including `CONSTRAINTS`, and replaces only `PARAMETERS`. Use
`--yes` for non-interactive confirmation.

## 2. Workflow and adapters

`job_template/workflow.py` consumes assigned raw parameter values and writes flat
`rawData/*.npz`. It must not write authoritative costs. Put only task-varying
simulation logic in this file and call `worker_misc.run_workflow()` for the fixed
execute lifecycle. That package-owned helper collects `execute_machine`, owns the
standard job paths, prepares rawData, atomically writes running/done/error metadata,
records exceptions, and creates `rawData.zip`.

Put task-specific helpers, models, lookup tables, and active adapters below
`job_template/`; prepared jobs copy that payload recursively while package worker
support adds only `worker_misc.py`. Do not put generic lifecycle, transport,
metadata, machine-detection, filesystem, or error-handling implementations in the
workspace. Top-level files or directories whose names end
with `.aedtresults` or `.aedt.lock` (case-insensitive) are treated as AEDT runtime
artifacts and are not copied. This suffix rule applies only to direct children of
`job_template/`; nested task assets are not inspected by it. The assigned parameter
snapshot is self-contained. Distributed jobs execute `workflow.py` directly and do
not receive or import the yadof package.

`run_workflow()` creates top-level `rawData.zip` on both success and error paths.
Its members are direct `.npz` basenames, not an enclosing `rawData/` directory.
Condor returns the zip and the submit host restores it into job-local `rawData/`.

List and copy a packaged reference adapter without overwriting user edits:

```powershell
yadof task adapters
yadof task copy-adapter hfss_com.py --workspace D:\work\study-a
```

## 3. rawData and cost

Each flat `.npz` item carries schema-versioned metadata and numerical arrays. The
framework records raw evidence and derives cost through the current
`job_template/calc_cost.py`. Changing a cost policy therefore reinterprets history
without rerunning simulation. Clear history when task semantics or rawData meaning
become incompatible.

Keep only task-varying rawData interpretation, objective definitions, thresholds,
and importance-region selection in `calc_cost.py`. Reusable axis reduction,
definition dispatch, worst-curve aggregation, constraint handling, error fallback,
importance-weight allocation, and objective counting belong to
`yadof.job_template` and must be called rather than copied into the task module.

Real evaluation and the surrogate follow the same path:

```text
normalized candidate
  -> assigned task parameters
  -> workflow rawData
  -> current calc_cost
  -> objective tuple
```

## 4. Validate and smoke

```powershell
yadof check --workspace D:\work\study-a
yadof smoke-test --workspace D:\work\study-a
```

An edited/external task requires `--real-task` for the standalone smoke command.
This acknowledges that it may launch expensive software. Use `--mode distributed`
to submit exactly one unlimited smoke job. Pool deployment and Windows slot-user
configuration remain administrator responsibilities.

## 5. Optimize and inspect

```powershell
yadof run --workspace D:\work\study-a --generations 10
yadof run --workspace D:\work\study-a --start-generation 10 --generations 5
yadof view cost --workspace D:\work\study-a -o costs.png
yadof view time --workspace D:\work\study-a
yadof view all --workspace D:\work\study-a
```

The two individual view commands create timestamped PNGs below
`.yadof/tool_output/` by default. `view time` includes failure rate, execute-machine
colors, and labeled error-type bands. `view all` prints both summaries and creates
both images. Use `--summary-only` when only terminal output is wanted.

Individual prepare/run/timeout/record failures become diagnostic records and
correct-width `inf` costs. `--fail-on-all-infinite` stops after the first generation
with no finite objective.
