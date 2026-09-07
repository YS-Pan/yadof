# Amplitude and shape Gaussian-process surrogate

`from yadof.surrogate import amplitude_gp` selects an independent, opt-in
deterministic rawData surrogate. It fits each named response field without
task names, field-specific rules, direct objective heads, or external labels.
The existing CAE and conditional INR components remain available.

Install the `gp` extra in the environment used to run yadof:

```powershell
python -m pip install ".\dist\yadof-0.6.0-py3-none-any.whl[gp]"
```

This extra supplies SciPy, scikit-learn and threadpoolctl. The component does not
require Torch. Importing the parent surrogate module or constructing this
component does not load the numerical GP backend; selecting it validates the
optional distributions. Runtime versions participate in state compatibility.

## Model and evidence

For every real, finite main array in a named rawData field, flatten the array,
subtract its minimum, and divide by its span. A zero-span array has zero
normalized shape. Fit separate parameter-to-response Gaussian processes for
the minimum and log span, and one GP sharing a kernel across the normalized
shape's PCA coefficients. The minimum uses a robust centered asinh transform.
Shape coefficients share a single RMS scale so their relative energy remains
meaningful. Constant targets use their training mean.

At prediction, invert these transforms, map the decoded shape back to its own
unit range, and restore the predicted minimum and span. Reconstruct every
complete named rawData field with its original shape, main dtype, axis values,
metadata and static payload. Scalar, curve, surface and higher-dimensional
arrays use the same procedure. No field is replaced with another design's
rawData. A collapsed shape with positive predicted span is counted in
diagnostics; it cannot represent that span.

All valid caller-owned training rows contribute to the shape codec. GP fitting
uses at most 512 rows by default: half have the lowest arithmetic mean current
true cost; the rest greedily cover normalized parameter space by farthest
distance from already selected rows. Stable cost ordering resolves ties, and
selected indices are sorted before fitting. This is a training subset policy,
not a replacement for the search optimizer.

`component.training_data(dataset, cost_table)` materializes successful evidence
and orders it by generation index, population index, then row ID. Explicit
`row_ids=` preserve caller order. Low-level fits accept only an already-owned
`SurrogateTrainingData`; they never query a campaign recorder or fetch historical
labels. Selected row IDs must be unique. The supplied snapshot's unchanged cost
interpreter projects these rows to obtain training priorities. Invalid current
costs cause a fit error rather than silent relabeling.

Training retains shared read-only rawData and one canonical set of static axes
and metadata per schema. Fitting builds one writable float64 matrix for the
current field, reuses it for unit-range normalization and PCA centering, and
releases it before the next field. The input samples remain read-only; sample
counts, GP row selection, precision, and decomposition settings are unchanged.
This reduces duplicate arrays, but full-field PCA and GP workspaces still require
memory proportional to the selected data and model dimensions. Cross-generation
decode reuse follows the training-input lifetime described in
[the optimization workflow](optimization_workflow.md).

## Explicit parameters

All factory parameters are keyword-only, immutable and included in semantic
identity. These are the defaults:

| Parameters | Default |
| --- | --- |
| `shape_rank`, `gp_max_rows`, `elite_fraction` | 16, 512, 0.5 |
| `minimum_training_samples`, `random_seed` | 64, 20260905 |
| `optimizer_iterations`, `optimizer_factr` | 60, 1e8 |
| `kernel_amplitude`, `kernel_amplitude_bounds` | 1.0, (1e-3, 1e3) |
| `length_scale`, `length_scale_bounds`, `matern_nu` | 0.5, (0.02, 30.0), 2.5 |
| `noise_level`, `noise_level_bounds`, `alpha` | 1e-3, (1e-8, 0.3), 1e-9 |
| `constant_tolerance`, `numerical_floor` | 1e-12, 1e-12 |
| `span_floor_relative` | 1e-6 |
| `minimum_scale_quantile`, `minimum_scale_std_fraction` | 0.75, 0.05 |

The kernel is constant amplitude times an ARD Matérn kernel, plus independent
white noise. Each fit uses one L-BFGS-B start and the declared bounds/iteration
limit. The effective PCA rank is the minimum of requested rank, sample count
minus one, and field width; randomized PCA uses the component seed. Fits and
predictions limit numerical thread pools to one thread. Cost intervals are
zero-width point intervals. The component exposes no calibrated uncertainty,
posterior sampler, applicability probability, or qNEHVI readiness.

## Fit, state, prediction and scheduling

The explicit lifecycle follows the shared
[fit and prediction contract](optimization_workflow.md):

```python
from yadof.surrogate import amplitude_gp

surrogate = amplitude_gp()
training = surrogate.training_data(dataset, cost_table)
state = surrogate.fit(workspace, training, generation_index=3, snapshot=snapshot)
prediction = surrogate.predict(state, normalized_candidates, snapshot=snapshot)
```

`fit()` waits and closes its handle. `start_fit()` returns a
`TrainingHandle`; the caller must finish or close it. When no snapshot is
provided, fitting creates and owns one until handle cleanup. A provided snapshot
must belong to the selected workspace. When a campaign session is provided, the
handle registers the normal generation boundary lease. Waiting with a timeout
does not cancel fitting. Cancellation is cooperative between fields, optimizer
evaluations and before publication; a committed atomic publication that already
won the race remains valid.

The component's `start_training(context, training)` starts at most one pending
worker per workspace, strategy and settings. `finish_training(context)` waits
for it and reports completion, cancellation or failure. `ensure_fresh_enough()`
can wait or fit as needed under the configured training lag. Pure selection
freshness checks do not fit. Fewer than `minimum_training_samples` rows skip
scheduled fitting; low-level `fit()` raises instead.

An optimization program owns the schedule. To use the development candidate's
schedule, start and finish training on all current prior formal evidence
**before** each generation's assisted selection. Do not claim the same
candidate when switching to lagged background training. This component supplies
no initial GPSAF error estimator; it leaves the existing search/GPSAF contract
and settings to the explicit program.

`prediction.costs` is exactly the supplied current snapshot's cost projection
of `prediction.raw_data`. The DTO retains the fitted state signature and
training content digest while reporting the current interpretation fingerprint.
A transform overflow or invalid cost projection yields no rawData for that
candidate, all-positive-infinity costs/point intervals, and a false validity
mask. Prediction writes neither observations nor formal optimization history.

## Checkpoints and compatibility

Fitted GP means and PCA inverse transforms are numeric NPZ arrays with a JSON
manifest; loading never enables pickle. Artifacts are atomically published
under `runs/strategy-*/components/amplitude-gp/` below the configured checkpoint
directory. The conventional generation
manifest is a convenience alias; recovery scans only this component's namespace.
Corrupt files, unexpected arrays, invalid shapes, escaping paths and mismatched
digests are rejected.

`recover(workspace, training, snapshot=...)` requires the full fitted content.
Selection can also recover a lagged state by recreating its ordered row IDs
from the explicit current training value and checking the exact old content.
Missing or changed rows, schema, parameter definitions, component settings,
backend versions, strategy, or training-priority interpretation invalidate reuse.
Recovery never retrains and never scans durable observation history.

The checkpoint also retains every original fitted normalized input. A live
campaign can retain the optimizer's coordinates while a reloaded formal record
computes normalization from physical coordinates, differing in the last floating
point bit. Recovery handles this only for unchanged committed formal rows: row
and evidence IDs, statuses, masks and physical record metadata must match;
fitted coordinates must denormalize exactly to those physical records and the
supplied coordinates must equal their exact normalization. It then recreates the
original fitted view and requires the original full content digest. There is no
epsilon-based acceptance, and arbitrary coordinate or rawData edits are rejected.
Derived rows cannot use this reconciliation. Prediction continues to report the
original fitted content digest.

The training-priority source signature covers parameter definitions and the
complete submit source hashes, including the frozen program hashes retained by
campaign snapshots. Thus campaign and standalone snapshots of identical sources
can recover the same state. Prediction still reports the caller's actual
interpretation fingerprint. Checkpoint format v2 includes fitted inputs; the
unreleased structural v1 artifacts remain incompatible and are never rewritten.

An explicitly retained raw model can still be projected with a new cost snapshot
when parameter definitions remain compatible. Selection recovery requires
refitting after the priority interpretation changes, since costs affect the GP
training subset. Separate training provenance is retained without changing the
meaning of the fitted content digest.

## Evidence status

One frozen research implementation with these defaults and synchronous
pre-selection fitting passed all three seed-101 development targets: Chrono at
2200 formal attempts, SAW at 2600 and test_com at 5200. The corresponding ratios
to perfect-surrogate first crossing were 1.375, 0.6842105263 and 1.4444444444.
These are development results, not independent multi-seed confirmation or
installed-component acceptance. Integration reproduction and preregistered
paired confirmation remain required before a broader performance claim.
