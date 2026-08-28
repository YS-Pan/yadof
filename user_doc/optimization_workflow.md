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

Store quantities with different physical or semantic meanings as independent
rawData fields. A scalar should be its own scalar field, and independent sampled
curves should each be their own 1-D field with their shared physical coordinate
axis. Do not concatenate several unrelated 1-D curves into a 2-D `sample × channel`
array merely to reduce the number of files; that invents a channel axis, obscures
field identity, and makes the field-balanced surrogate learn one artificial joined
target. Use a multidimensional field only when its dimensions form one coherent
physical grid or tensor whose joint meaning is part of the intended prediction
contract.

Fast, local, and distributed backends all return `JobResult` to one finalizer,
which owns and validates rawData once, calculates the current objective tuple, and
hands the owned evidence to the campaign recorder. The recorder keeps bounded
asynchronous micro-batching, but its limits now apply backpressure: a full
unpublished budget waits for publication instead of dropping the new result. The
population boundary waits until every result has been atomically published before
the next generation can start. An oversized record or a writer that cannot publish
after its configured attempts raises a recording error and stops the campaign; it
does not continue with incomplete history or convert the scientific result to an
`inf` candidate.

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
3. Conditional-INR training treats every modeled rawData field equally at the
   field-loss level; task code cannot override that production policy. The
   experimental hierarchical CAE has the same equal-weight behavior when no
   quality policy is selected. Its optional versioned quality policy may
   declaratively downweight a diagnosed chatter/failure field and mask its shared
   latent contribution without dropping other fields in the design. The policy is
   part of strategy/checkpoint identity and cannot be an arbitrary task callback.

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

### Joint posterior component boundary

The installed package exposes a lightweight protocol for surrogate and acquisition
components that need joint rawData function draws. The current template still
composes conditional INR with GPSAF, but a workspace may now explicitly select the
independent `posterior_assisted(..., acquisition=qnehvi(...))` strategy. Conditional
INR has a separate opt-in posterior adapter and an experimental full-grid
hierarchical CAE component is available. Both currently expose typed fail-closed
readiness, so neither may control exploitation until its architecture is accepted
and its calibration is usable and transferable.

A posterior-capable component creates one persistent, schema-bearing sampler with a
draw count and seed. The sampler fixes every draw's underlying function identity before candidates
are split into chunks. Calling `predict()` for different chunks or in another chunk
order must evaluate those same functions; repeated candidates receive the same
value within one draw. Every candidate/draw reconstructs complete rawData fields.
The stable field selector is exactly `(direct .npz basename including .npz,
resolved values/data main key)`, never optional `metadata.rawdata_name` or mapping
order. Axis arrays, units, metadata, shape, and dtype stay frozen in the schema
template.

`task_rawdata_cost_projector()` holds one `CostInterpreter` open against the selected
generation snapshot. `project_rawdata_sampler()` streams one complete rawData draw
for one candidate chunk through that interpreter and retains only
`[draw,candidate,objective]` costs, a validity mask, and bounded diagnostics. A
finite callback result—including a task helper's indistinguishable
`error_cost=1.0` fallback—is valid. Schema mismatch, callback exception, wrong
objective width, or a non-finite objective is invalid and cannot be treated as a
favorable uncertain sample. Predicted rawData is discarded after projection and
never enters jobs, rawData transport, recorded segments, or history.

Component authors must place the posterior protocol/backend version and every
controlled parameter in the component and consuming strategy's semantic identity.
Finite ensembles report their real distinct support even when draws repeat;
continuous or unknown support reports `unique_support=None`. Importing
`yadof.surrogate`, `yadof.optimize`, or these protocol types does not load Torch,
BoTorch, or another optional numerical backend.

### Conditional-INR compatibility adapter

`conditional_inr_posterior()` explicitly wraps the existing conditional-INR
component for a future posterior consumer. It does not replace
`conditional_inr()` in the package template and does not change GPSAF, mean rawData,
mean costs, min/max intervals, training, viewer behavior, or checkpoint
compatibility. Its persistent sampler selects one ensemble member per seeded draw
and keeps that member fixed across candidate chunks, all rawData fields, and all
derived objectives. Prediction reconstructs only the complete stored grid.

This is a finite empirical ensemble, not a calibrated posterior. Nominal
`unique_support` is the loaded distinct member count (normally three under the
default training configuration); requesting more draws repeats member sources and
adds no information. Diagnostics also report effective distinct sources after
member inference and current-cost projection. A member failure invalidates its
complete candidate draw rather than filling fields from another member. Any future
strategy must explicitly warn, reject, or fall back when that effective support is
below its declared policy.

### Experimental hierarchical CAE and quality/regime boundary

`hierarchical_cae()` is an explicit development component, not the starter default.
It freezes direct field selectors, shapes, axes, dtype templates, optional groups,
and rank-3 channel/spatial roles; scalar, 1-D, and 2-D fields use separate codecs.
One parameter-predictor member emits global/optional-group/field-private latents for
all fields, so a persistent posterior draw keeps a coherent member identity across
candidates and fields. Complete fixed-grid rawData remains the authoritative
prediction path and current `calc_cost.py` still produces costs.

Tasks that need chatter/failure handling may supply a `RawDataQualityPolicy` made
from JSON-safe explicit assessments, declarative record-diagnostic rules, and—only
when diagnostics are absent—declared morphology thresholds. Yadof core contains no
Chrono names or release/contact thresholds. Assessment changes only training
weights, shared-token contribution, private residual labels, and the uncalibrated
applicability head; it never filters by cost, smooths stored curves, or rewrites
recorded rawData. With no policy, training is ordinary equal design-by-field macro
Smooth L1.

The applicability API reports each predictor member's uncalibrated `P(smooth)` and
ensemble spread. This is structural/epistemic regime uncertainty with zero
observation noise, not an independent Gaussian error attached to each candidate.
Calibration on independent designs is a separate exact-signature adjunct; the
current v8 evidence failed closed, and any exploitation rule remains future work.

Gate 0 v5 retained this component as an experimental baseline but rejected the
first 1000/2000-design candidate: multiple representation guards failed and the
gated residual did not sufficiently prevent clean-target high-frequency leakage.
Do not treat it as a production recommendation.

A later, separately preregistered v6/v7 framework continuation added an optional
architecture-version-2 coordinate readout and a read-only viewer adapter. Enable it
only with `hierarchical_cae(architecture_version=2, coordinate_readout=True, ...)`.
`predict_field_at_coordinates()` accepts explicit in-domain coordinates for every
declared field axis, using declared linear, log, or periodic encodings. It reuses the
same predictor-member global/group/private state and keeps the gated residual
field-private. Full-grid decoding remains authoritative for rawData, cost, posterior,
audit, and optimization; coordinate queries never modify a checkpoint.

The fixed v6 offline mechanism run covered all 1200 frozen offline-test designs and
proved finite all-axis queries, checkpoint-state preservation, and viewer/evaluation
plumbing. It deliberately had no numeric coordinate or performance threshold, and
its single-seed errors did not reverse v5. The component and viewer support therefore
remain `experimental / performance-not-accepted`. Independent calibration requires
a new pre-access registration bound to an exact experimental state; qNEHVI
exploitation remains unavailable until an architecture passes its performance gate
and that applicability capability is independently calibrated.

### Signature-bound posterior calibration adjunct

The lightweight public surface now includes `PosteriorCalibrationArtifact`,
`FieldSpreadCalibration`, `ApplicabilityCalibration`, and
`CalibratedRawDataPosteriorSampler`. A successful artifact is bound to exact
state/strategy/schema signatures, checkpoint-file hashes, training provenance,
held-out calibration data, quality policy, and label/head/loss identity. A finite
calibrated sampler must enumerate each unique member exactly once. Per-field scales
act around the unchanged empirical member mean and preserve one member/draw axis
across candidates, chunks, fields, and objectives. Applicability uses one positive-
slope logit-affine mapping for every member before averaging. Neither path adds
observation noise or fits current cost directly.

This API is fail-closed. A stale/tampered artifact, repeated finite support, failed
gate, or signature mismatch cannot silently reuse coefficients. Failed rawData
calibration exposes only identity scales; failed applicability calibration exposes
no slope or intercept. Every current hierarchical-CAE calibration artifact also
fixes `experimental-performance-not-accepted` and `transferable=False`.

The frozen 082609 v8 run evaluated six 1000/2000-design checkpoint cells on 600
independent calibration designs. All six rawData candidates failed at least one
preregistered rawData/current-cost/acquisition-proxy check. Chrono had only 19 smooth
versus 181 chatter/failure calibration labels, so its design-level two-fold fits
failed the minimum-class-support rule. The resulting artifacts are therefore all
explicitly uncalibrated (or applicability `not-applicable`), and no current artifact
may gate 082611 exploitation. Gate 0 v5 and the component's experimental status are
unchanged.

The private numerical path behind `qnehvi()` uses BoTorch qLogNEHVI. It treats a
finite task cost of `1.0` as valid, rejects an incomplete Monte Carlo draw as a
whole, and retains only compact acquisition diagnostics. The public acquisition
selects a discrete batch with explicit greedy restarts; it still does not own
candidate generation, pending state, outcome constraints, evaluation, or recording.
Those generation responsibilities belong only to `posterior_assisted()`. Do not
return a qNEHVI backend scorer directly from `build_optimization()`.

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

The factory calls above are also the only workspace entry for component settings.
For example, a tuned source may use
`pymoo_ga(crossover_probability=0.9, mutation_eta=15.0)`,
`gpsaf(..., alpha=3, beta=3, exploration_fraction=0.15)`, and
`conditional_inr(device="cuda", epochs=64, bootstrap_members=True)`. These
keyword-only values are validated when the generation snapshot loads. Editing the
file affects the next generation; the current generation continues with its frozen
component values. Removed uppercase algorithm/model names in `config.py` fail as
unknown settings instead of being translated or ignored.

For a real multi-objective NSGA-III-only campaign with no GPSAF or surrogate:

```python
from yadof.optimize import pymoo_nsga3, real_search


def build_optimization():
    return real_search(search=pymoo_nsga3())
```

For an explicit structural posterior-assisted composition, set
`OPTIMIZE_POPULATION_SIZE = 10` and make every control visible in the strategy
source:

```python
from yadof.optimize import posterior_assisted, pymoo_nsga3, qnehvi
from yadof.surrogate import conditional_inr_posterior


def build_optimization():
    return posterior_assisted(
        search=pymoo_nsga3(),
        surrogate=conditional_inr_posterior(),
        acquisition=qnehvi(
            batch_size=8,
            greedy_restarts=4,
            minimum_unique_support=3,
            low_support_policy="fallback",
        ),
        candidate_pool_size=256,
        posterior_draws=3,
        candidate_chunk_size=16,
        exploration_fraction=0.2,
    )
```

This exact example is intentionally real-search-only today: the conditional-INR
posterior reports `experimental-performance-not-accepted`, `uncalibrated`, and
`transferable=False`, so the typed gate prevents acquisition use. The fallback
still proposes a complete pymoo population, sends every point through common real
evaluation/finalization/recording, and schedules component training only after jobs
are submitted. Backend/projection failures have the same full-real fallback;
`low_support_policy="reject"` is instead an explicit campaign-stopping gate.

The qNEHVI batch must equal population size minus
`ceil(population_size * exploration_fraction)`, with at least one real exploration
point and at least one exploitation point. The candidate pool, posterior draws,
chunk size, batch/restarts, reference point, support rule, exploration fraction,
objective names, and component identities all enter the semantic strategy
signature. Pending points and stochastic outcome constraints are not v1
capabilities and are rejected rather than ignored.

An applicability-aware future composition must receive an explicit typed calibrated
probability capability and a `calibrated_applicability_gate()` whose threshold,
boundary width, policy version, calibration-policy SHA-256, and boundary/low
exploration ordering were sealed before test access. Values below the sealed
threshold cannot enter exploitation. Some low-probability or boundary points may
still enter the explicit real exploration quota and always use the public real
evaluator. Training loss, cost, member min/max, or enlarged ensemble variance can
never satisfy this gate.

### Current integrated release status

The v10 integrated decision separates mechanism availability from scientific
release:

- Phase A permits frozen-evidence offline work and checkpoint/viewer checks.
  Diagnostic shadow ranking needs its own frozen plan, cannot change selection or
  submit extra evaluations, and is not currently activated.
- Phase B exposes the explicit composition above, but today's typed capability
  must report `typed-exploitation-capability-blocked` and evaluate a complete real
  search population. Fixed-baseline/state/backend soft failures also use visible
  full-real fallback. Explicit support rejection, invalid qNEHVI configuration,
  and recording/finalization failures stop the campaign.
- Phase C is blocked: the combination is not a recommended opt-in and cannot
  replace the GPSAF plus conditional-INR template default.

Formal re-entry requires a new versioned architecture candidate; passed
1000/2000-design representation, worst-field, quality/regime, coordinate, and
resource gates; exact-state transferable rawData calibration; calibrated
applicability policy where applicable; all seven frozen comparison arms (including
hierarchical-CAE + GPSAF); pre-access posterior/optimization/engineering thresholds;
final installed-wheel and fallback/viewer/checkpoint/recorder checks; and explicit
campaign authority. Only a complete same-budget run that jointly passes every
scientific and engineering decision can become a recommended opt-in. Changing the
default still needs a later explicit user decision.

That composition requires at least two objectives and never silently falls back to
GA. There are no `OPTIMIZE_METHOD`, `SURROGATE_METHOD`, or search-backend selector
settings and no complete-method registry. Source hashes are provenance; a
deterministic semantic strategy signature governs derived-state compatibility.

Only one strategy is active per workspace. A semantic change waits for pending
component work, releases active in-memory state, and activates a retained
strategy/component namespace. Recorded real evidence and inactive checkpoints stay
on disk. Returning to a compatible old strategy may recover its state; switching
strategies never requires `history clear`.

Conditional INR starts training from completed real evidence after evaluation is
submitted. The package default permits the model used for selection to lag by at
most one generation; when necessary, selection waits for pending training rather
than using an older model. Set `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG` to a
non-negative integer only when the task's evaluation/training timing justifies a
different throughput-versus-freshness tradeoff. Query minibatches rotate through
one seeded ordering per rawData field so scarce coordinates are covered before
they repeat. Every ensemble member sees all retained real rows by default, with
independent initialization supplying diversity without discarding design support.
If `conditional_inr(bootstrap_members=True)` is selected, bootstrap is still
deferred until at least two real samples per input variable are available.

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
and correct-width `inf` costs, and those failure rows are recorded like successful
rows. A history publication failure stops the campaign before another generation;
it is not reported as an ordinary candidate `inf`. `--fail-on-all-infinite` stops
after the first generation with no finite objective.
