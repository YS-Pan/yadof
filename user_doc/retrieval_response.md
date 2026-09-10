# Experimental retrieval response surrogate

`from yadof.surrogate import retrieval_response` selects the independent N02-derived
deterministic component. Install `yadof[retrieval]` for its optional Torch, SciPy,
scikit-learn and threadpoolctl dependencies. Ordinary package imports do not load
these numerical backends. The existing default surrogate remains unchanged.

## Evidence and intended use

The model is an experimental option for rawData-first GPSAF. Historical development
at P50/B50/I200 across five seeds gave first-crossing medians of 3900 (synthetic
antenna), 1900 (Chrono) and 1650 (SAW), against matched perfect medians 1300, 1450
and 1450. Two SAW seeds had no crossing within 10000 attempts. The three-baseline
median-two-times-perfect target was not met, and no fresh paired confirmation was
completed. These findings justify preserving a usable experimental component,
not a universal efficiency promise or default migration.

## Numerical model

Each complete named field is split into minimum, span and normalized shape.
Minimum uses an asinh transform, span a logarithm, and shape a rank-clamped
randomized PCA. The concatenated representation retains all fields. Eight nearest
parameter neighbors supply responses to a shared neural attention/correction
network; two members' latent predictions are averaged before decoding the complete
rawData. Current task cost is then calculated from that response. Neither current
cost nor baseline identity enters the model's training targets or neighbor policy.

Training uses only caller-supplied valid prior rows. The validation probe fits its
codec and retrieval context on its own training split, excludes validation rows
from both, and never chooses final settings, epochs or checkpoints. Final models
start afresh and use every selected prior row. Training queries exclude their own
row identity; distinct observations at identical coordinates remain valid neighbors.
The nearest-neighbor backend's tie behavior and exact row order remain relevant.

The factory exposes explicit keyword-only settings:

| Setting | Default |
|---|---:|
| random_seed / neighbors / shape_rank | 20260909 / 8 / 16 |
| hidden_width / members | 96 / 2 |
| steps / validation_steps / validation_fraction | 96 / 8 / 0.2 |
| batch_size / learning_rate / weight_decay | 128 / 0.002 / 0.0001 |
| gradient_clip / minimum_training_samples | 1 / 8 |
| prediction_chunk | 128 |
| constant_tolerance / numerical_floor / span_floor_relative | 1e-12 / 1e-12 / 1e-6 |

The default is **200 optimizer steps per fit**: eight probe steps and 96 steps for
each of two final members. These are not epochs and there is no early stopping.
At most eight neighbors and three members are supported. The initial probe needs
at least two context observations, so a custom minimum sample count must be ≥3.

This component uses one CPU numerical thread. A component-local process-wide lock
serializes its numerical operations; CPU Torch RNG and numerical thread settings
are restored on success, failure and cancellation. The CPU seed repair preserves
the research sequence without resetting accelerator RNGs. Concurrent unrelated
Torch/model operations in the same process are outside this isolation guarantee;
use separate processes for different simultaneous numerical backends.

## Explicit fit and prediction

```python
from yadof.surrogate import retrieval_response

model = retrieval_response()
training = model.training_data(dataset, cost_table)
state = model.fit(workspace, training, generation_index=3, snapshot=snapshot)
prediction = model.predict(state, normalized_candidates, snapshot=snapshot)
```

`training_data()` defaults to chronological generation/population order; explicit
`row_ids=` preserves caller order. `start_fit()` returns the standard owned
`TrainingHandle`; callers wait/close it. `fit()` does that cleanup itself. Supplied
snapshots must belong to the workspace. Cancellation is checked between codec
fields and training steps, while waiting for the numerical lock, and before atomic
publication; a running native PCA call completes before cancellation is observed.
Committed artifacts are retained.

The scheduler starts at most one handle per workspace/strategy/settings, skips
insufficient data, and reports completed/cancelled/failed outcomes. Direct fitting
raises on insufficient data. Pure freshness/selection checks never fit. A program
owns its fit/evaluate/commit order; the supplied
[example](../examples/optimization-programs/retrieval_response.py) fits all own-prior
evidence before every assisted selection. A failed fit propagates. P/B/I remain
independent task configuration; they are not surrogate hyperparameters.

Predictions retain the exact schema, axes, metadata and dtype, require finite
normalized inputs strictly inside [0,1], and publish point intervals with no
posterior capability. Invalid decoded responses or cost projections give a false
validity mask, absent response and positive-infinity costs. Finite task fallback
cost 1 remains a valid value. Individual real failures remain in formal history
and consume evaluation budget; they do not become fabricated training responses.
No fitting or prediction operation writes real evidence.

## Checkpoints and recovery

The separate `retrieval-response` namespace owns JSON manifests and no-pickle NPZ
artifacts. They retain exact context coordinates and the original PCA fit_transform
codes, complete schema/static arrays, codecs and fixed network tensors. Recovery
does not recalculate context codes or fit models. File hashes, known tensor
names/dtypes/shapes, schema, settings, parameter definitions, strategy and training
content are checked. Corrupt/incompatible artifacts remain on disk and are skipped.

Explicit recovery requires the same ordered evidence; selection recovery may use
an exact unchanged subset under the configured lag. Persisted normalized-coordinate
round trips are reconciled only using exact committed physical-record proofs.
Because costs do not choose model targets/priorities, a cost-only edit can retain
the model when training content and parameter definitions remain unchanged;
prediction always uses the supplied current snapshot's cost policy.

The current surrogate GUI/CLI viewer does not yet dispatch this component.
Use the typed `predict()` result's complete `raw_data`, `costs` and diagnostics for
inspection. This limitation does not affect optimization or checkpoint recovery.

The `surrogate-complete` benchmark preset compares real-only, PCA/SVD, amplitude GP
and retrieval response on all three baselines and three seeds at P200/B200/I200/G25.
It is a descriptive 5000-attempt comparison, distinct from the P50 historical goal.


## Installed benchmark closure (2026-09-11)

The complete standard-budget matrix covered three baselines, three seeds and four
programs, with 5000 real attempts per cell. Retrieval response improved final
best-ten mean cost over real-only on all three Chrono and all three SAW seeds;
antenna improved on two seeds and its median paired cost ratio was 0.999759,
effectively no improvement. This is descriptive regression evidence with reused
seeds and P200/B200/I200, not fresh confirmation of the historical P50/perfect goal.
Median optimization times for all surrogate programs exceeded real-only on these inexpensive simulators.
One external interruption required retaining the complete Chrono group and running
the other two complete baseline groups in a fresh workspace with identical inputs.
See the [research delivery summary](../dev_doc/context/20260910_120000_surrogate-research-summary-and-delivery.md)
for exact results, sources, timings and limitations.
