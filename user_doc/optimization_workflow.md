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

For Project Chrono, copy `chrono_com.py`, add the task-owned `chrono_worker.py`,
and follow `user_doc/adapters/chrono_com.md`. The adapter uses
`YADOF_PYCHRONO_PYTHON` as an external runtime; it does not make PyChrono a yadof
dependency.

### Fast-compatible shared task kernel

Use fast only for computations or local simulators whose result can be returned as
memory rawData. Add `job_template/evaluation.py` with:

```python
def evaluate_rawdata(parameters, context):
    # parameters is a read-only {name: assigned_float} mapping.
    # context includes evaluation_name, scratch_dir, environment, and identities.
    return {
        "response.npz": {
            "values": response_array,
            "metadata": metadata_json,
        }
    }, {"simulator_returncode": 0}
```

Names must be unique direct `.npz` basenames. Every payload follows the same schema
as file rawData, diagnostics must be JSON-serializable, and neither return value may
contain objective costs. Put the simulation algorithm in this kernel and make
ordinary `workflow.py` call it and save each payload under its job-local
`rawData/`; do not maintain two algorithms.

The fast context has no job path. `scratch_dir` is the only candidate-specific
filesystem exception. Pass it explicitly as a simulator working directory and pass
`{**os.environ, **dict(context["environment"])}` explicitly to subprocesses. Parse
all needed output into memory before returning. The parent reaps simulator
descendants that remain after a task response and removes scratch after success,
task error, timeout, or worker crash. Do not treat scratch as history,
checkpoint, or recoverable job state. Prefer local/distributed when a task needs a
durable job directory, detailed job-local files, remote execution, or recovery from
large intermediate files.

## 3. rawData and cost

Each flat `.npz` item carries schema-versioned metadata and numerical arrays. The
framework records raw evidence and derives cost through the current
`submit/calc_cost.py`. Changing a cost policy therefore reinterprets history
without rerunning simulation. Clear history when task semantics or rawData meaning
become incompatible.

Current cost is an execution result, not a persistence result. Fast, local, and
distributed backends all return `JobResult` to one finalizer, which owns and
validates rawData once, calculates the current objective tuple, releases the worker,
and makes a non-blocking best-effort recording offer. A full history queue,
oversized record, permission error, disk-full error, or dead recorder may lose that
record but cannot turn its valid cost into `inf`.

A campaign is not required to keep its original task definition forever. If the
user discovers a mistake, they may correct `calc_cost.py`, parameter definitions,
`config.py`, `workflow.py`, `evaluation.py`, or task helpers and continue at a
generation boundary. This intentionally creates a new optimization problem. Yadof
does not attempt to judge whether pre-edit and post-edit problems are scientifically
equivalent and does not override the user's decision. Old records remain candidates
for reinterpretation; records that the current parameter/rawData/cost code cannot
actually process are skipped. The user decides whether keeping that mixture is
reasonable, whether to clear history, or whether the corrected task belongs in a
new workspace.

For this in-campaign correction path, keep parameter names/order/count and objective
count unchanged. Parameter ranges/levels, objective meaning/thresholds, cost code,
and task execution code may change at the boundary. Structural parameter or
objective-width changes need separate optimizer-state support; use a new workspace
and campaign for them for now.

At each generation boundary yadof copies the complete `submit/` and `job_template/`
source trees below one immutable snapshot root. Every candidate in that
generation—including fast worker task
imports—uses that same snapshot. Changes made while a generation is running are
therefore visible at the next boundary and cannot split the current generation.
Interpretation, evaluation, and optimization fingerprints are recorded separately:
only a changed
interpretation fingerprint invalidates cached normalization/current-cost values;
an evaluation-only edit records new provenance without forcing old cost work.

History is stored as immutable standard-ZIP micro-batch segments below
`recorded_data/segments/`. Published segments are never appended or rewritten.
Readers ignore temporary and unrelated files, skip a bad candidate member where
possible, and skip one whole segment when its ZIP directory or manifest is
unreadable.

Keep these three decisions separate:

1. `workflow.py` decides what evidence is saved. Save a complete compatible
   far-field grid only when the full grid belongs to the intended prediction
   contract; exclude objective-irrelevant numeric fields or regions at this
   boundary rather than expecting a later attention mask.
2. The surrogate builds its training bundle from recorded rawData. Compatible
   varying numeric slots enter its query table; constant slots are preserved in the
   rawData template instead of being learned. Large fields may be sampled by query
   minibatches during individual training steps, but remain part of the full
   modeled field and full-grid prediction contract.
3. Surrogate training treats every modeled rawData field equally at the field-loss
   level. Within each field, every selected scalar position has equal pointwise
   importance. Task code cannot override this policy.

Therefore, “include all saved far-field rawData in surrogate training” is a
workflow/rawData requirement. The surrogate models every varying numeric slot in
the evidence that the workflow deliberately saved under its field-balanced policy.

Keep only task-varying rawData interpretation, objective definitions, and thresholds
in `submit/calc_cost.py`. Reusable axis reduction, definition dispatch, worst-curve
aggregation, constraint handling, error fallback, and objective counting belong to
`yadof.job_template` and must be called rather than copied into the task module.

Real evaluation and the surrogate follow the same path:

```text
normalized candidate
  -> assigned task parameters
  -> workflow rawData
  -> current calc_cost
  -> objective tuple
```

Every objective in that tuple must normally be a dimensionless minimization cost
in `[0, 1]`, independently normalized from its physical metric: `0` is best and `1`
is worst. A `calc_cost.py` must not return values directly in seconds, microseconds,
Hz, MHz, dB, metres, or other task units. Keep those values and units in rawData and
local extraction variables, choose fixed task-owned physical `goal` and `worst`
thresholds, and map them with `yadof.job_template.cost_misc.soft_cost()` or a
defined-cost helper that uses it. Do not derive normalization bounds from the
currently observed history; that would make an unchanged sample's cost depend on
which other evaluations happen to exist.

Treat `goal` and `worst` as algebraic-sigmoid calibration anchors, not hard bounds.
The default `edge_cost=0.1` maps them to costs `0.1` and `0.9`, deliberately
reserving the outer
intervals `(0, 0.1)` and `(0.9, 1)` for values outside the expected physical range.
This matters when conservative thresholds underestimate what the simulator will
produce: two results worse than `worst` still receive different costs and can guide
the optimizer back toward the useful region. Likewise, unexpectedly strong results
better than `goal` remain distinguishable. Do not clip a physical metric to
`[goal, worst]`, and do not rescale the algebraic result merely to force the two
anchors to exact `0` and `1`; either operation would create flat plateaus precisely
where the initial thresholds may be wrong. The normalized extrema are limits approached
by the tails, while `0.1`/`0.9` are the default scientific anchor costs.

Use `error_cost=1.0` for a task-level missing/invalid-data fallback so it remains at
the normalized worst value. A framework execution failure may still return an
all-`inf` row to preserve failure isolation; that sentinel is outside the normal
`calc_cost.py` objective scale. Depart from the `[0, 1]` task-cost contract only
when the user explicitly requests it and the workspace documents the reason.

## 4. Compose the optimization strategy

`submit/optimization.py` is the only complete-strategy selection source. It must
define a side-effect-free `build_optimization()` function. The starter composes
GPSAF, objective-count dispatch, pymoo GA or NSGA-III, and conditional INR:

```python
from yadof.optimize import by_objective_count, gpsaf, pymoo_ga, pymoo_nsga3
from yadof.surrogate import conditional_inr


def build_optimization():
    return gpsaf(
        search=by_objective_count(
            single=pymoo_ga(),
            multi=pymoo_nsga3(),
        ),
        surrogate=conditional_inr(),
    )
```

For a real multi-objective NSGA-III-only campaign with no GPSAF or surrogate:

```python
from yadof.optimize import pymoo_nsga3, real_search


def build_optimization():
    return real_search(search=pymoo_nsga3())
```

That composition requires at least two objectives and never silently falls back to
GA. There are no `OPTIMIZE_METHOD`, `SURROGATE_METHOD`, or search-backend selector
settings and no complete-method registry. Source hashes are provenance; a
deterministic semantic strategy signature governs derived-state compatibility.

Only one strategy is active per workspace. A semantic change waits for pending
component work, releases active in-memory state, and activates a retained
strategy/component namespace. Recorded real evidence and inactive checkpoints stay
on disk. Returning to a compatible old strategy may recover its state; switching
strategies never requires `history clear`.

## 5. Validate and smoke

```powershell
yadof check --workspace D:\work\study-a
yadof smoke-test --workspace D:\work\study-a
yadof smoke-test --workspace D:\work\study-a --mode fast --real-task
```

An edited/external task requires `--real-task` for the standalone smoke command.
This acknowledges that it may launch expensive software. Use `--mode distributed`
to submit exactly one unlimited smoke job. Pool deployment and Windows slot-user
configuration remain administrator responsibilities.
Use `--mode fast` only after `check` confirms the explicit kernel. Fast smoke still
runs exactly one worker and has no timeout or durable job directory.

## 6. Optimize and inspect

`yadof check` constructs and validates the submit-side strategy, but does not train,
predict, evaluate candidates, import the workflow, or write an active pointer.

```powershell
yadof run --workspace D:\work\study-a
yadof run --workspace D:\work\study-a --generations 10
yadof run --workspace D:\work\study-a --start-generation 10 --generations 5
yadof view cost --workspace D:\work\study-a -o costs.png
yadof view time --workspace D:\work\study-a
yadof view all --workspace D:\work\study-a
```

The first command uses the CLI default of 50 generations. Use `--generations` for a
different count.

The two individual view commands create timestamped PNGs below
`.yadof/tool_output/` by default. `view time` includes failure rate, execute-machine
colors, machine-specific average-time labels, left-labeled error-type bands, and an
elapsed-time axis that automatically changes between minutes, seconds, and
milliseconds to keep fast evaluations readable.
`view all` prints both summaries and creates both images. Use `--summary-only` when
only terminal output is wanted. Worker-reported machine identity is preferred; a
timed-out distributed job may use its source-labeled Condor user-log machine when
worker metadata could not return, while a job that never executed remains
`unknown`. Existing timeout records use their stored Condor log tail for the same
read-only display fallback; history is not rewritten.

Individual prepare/run/timeout/rawData/current-cost failures become diagnostic rows
and correct-width `inf` costs. History-recording loss is independent and preserves
the valid current cost. `--fail-on-all-infinite` stops after the first generation
with no finite objective.
