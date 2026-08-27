# 4+1 logical view

## Domain concepts

- Parameter definitions contain names, allowed ranges/levels, and optional units.
  Optimizers use normalized coordinates; jobs receive denormalized assigned values.
- rawData is one or more schema-versioned `.npz` evidence files. The directory is
  flat: every file is directly under `rawData/` and no subdirectory is valid.
- Cost is the current objective tuple calculated by workspace `calc_cost.py` from
  rawData. Newly authored task objectives are independent, dimensionless
  minimization costs in `[0, 1]`, with fixed task-owned physical `goal`/`worst`
  thresholds and `1.0` as the task-level error fallback. Objective names, count,
  physical meaning, thresholds, and windows are task concerns; physical units stay
  in rawData and extraction logic. Framework execution failures may still use an
  all-`inf` sentinel outside the normal task-cost scale.
- A joint rawData posterior is derived submit-side state. One persistent sampler
  fixes stable draw IDs (and finite-support source IDs when applicable), then
  evaluates the same possible functions over arbitrary candidate chunks. Each
  candidate/draw is a complete named rawData sample whose field identity is the
  exact `(direct .npz basename, resolved values/data main key)` pair. Candidate
  ordering and chunking may only reorder or partition those function values.
- A rawData cost projector owns no task logic. It validates each predicted sample
  against one frozen selector/shape/dtype/axis/metadata template, denormalizes the
  matching candidate with one frozen `CostInterpreter`, invokes the current task
  callback, checks objective width and finiteness, and emits joint costs plus a
  validity mask. Finite task fallback values such as `1.0` remain valid because
  their origin is not observable at this boundary; schema, callback, width, and
  non-finite-result failures are invalid.
- A prepared job is one local/distributed candidate evaluation and owns parameters,
  task inputs, rawData, lifecycle metadata, transport artifacts, and diagnostics.
  A fast logical evaluation keeps the identity/metadata contract but has no durable
  job directory; its evidence is memory-backed until recorded.
- Recorded data is durable evidence and compact provenance. It is not an optimizer
  cache of permanently authoritative cost values.
- A record envelope is candidate-owned validated rawData plus bounded provenance
  handed to the recorder only after current cost is known. A campaign session owns
  the hot derived row while the envelope is pending, applies backpressure when the
  unpublished budget is full, and does not cross the population boundary until the
  envelope is durably published.
- A segment is an immutable standard ZIP containing a bounded micro-batch. Candidate
  member loss and whole-segment loss are distinct recovery units.
- An external simulator Python runtime is a separately provisioned interpreter and
  process, not an alternative host environment for yadof. The PyChrono v1 contract
  exchanges only bounded versioned JSON and schema-compatible NPZ evidence through
  candidate-isolated scratch. No object identity or import namespace crosses it.

The logical pipeline is `normalized variables -> assigned task parameters ->
job_template workflow rawData -> current submit calc_cost -> objective tuple`.

`job_template/workflow.py` and `submit/calc_cost.py` own only the task-variable parts of that pipeline.
The package owns invariant execution lifecycle, paths, metadata, transport,
rawData manipulation, cost dispatch, constraint/failure policy, and objective
counting. Task files select and parameterize those package mechanisms.

Resource evidence follows a parallel backend-neutral interpretation path. Local
process-tree measurements and HTCondor ClassAd measurements publish common CPU,
memory, and disk keys. One shared calibration component selects smoke or
preceding-generation evidence and trims its upper tail. HTCondor turns the result
into scheduler requests; local mode turns it into a safe worker count constrained
by current submit-host capacity.

## Source-of-truth policy

Durable source truth includes raw variables once per individual, flat rawData,
schema metadata, workflow start/end information, job/run/generation identities,
execution diagnostics, and lightweight optimization metadata. Normalized variables,
costs, surrogate predictions, and repeated variable payloads inside each rawData item
are derived or scrubbed. A workflow-written `cost.json` is forbidden.

Changing `submit/calc_cost.py` intentionally changes interpretation of existing compatible
rawData. Changing parameter definitions changes normalization and job static hashes.
If task semantics make old evidence invalid, users must remove or exclude it
explicitly; the package does not guess a scientific migration.

This user-authoritative mutability also applies during an active campaign.
Generation boundaries are the coherent reload point for current configuration,
parameter ranges/levels, fixed-width objective/cost policy, evaluator/workflow task
code, complete strategy composition, and helpers. Both complete source roots are copied once at the boundary;
the next generation reconstructs its affected derived
history view from current definitions. The current hot-change contract assumes
stable parameter identity/count and objective count; structural parameter or
objective-width changes require separate optimizer-state semantics and are future
work. A content fingerprint may invalidate derived caches and record provenance,
but fingerprint inequality is not a scientific-compatibility decision and cannot
by itself reject old evidence. Yadof attempts to reinterpret old records under
current code and isolates only concrete normalization, rawData, or cost failures.
Whether combining pre-edit and post-edit evidence is scientifically appropriate
remains the user's decision.

Optimizer and surrogate are consumers of the same evidence. The surrogate predicts
rawData before cost, constructs its modeled query table from compatible recorded
numeric rawData, reconstructs full public rawData, and calls current cost logic.
Every modeled rawData field receives equal macro loss weight and task code cannot
change training weights. Per-query rawData targets use recorded mean/standard-
deviation scaling and a linear decoder; normalized design inputs are centered at
zero, and predictions may extrapolate beyond the recorded rawData envelope before
inverse scaling. The surrogate never establishes a parallel
`variables -> cost` truth path. Its schedule and checkpoints are keyed by effective
workspace paths plus active strategy/component identities; source hashes remain
separate provenance.

Posterior samples are another derived surrogate view, not evidence. A sampler
reports its posterior/support kind honestly (`finite` with an integer unique
support, or `continuous_or_unknown` with no invented finite count), seed, stable
draw identities, schema/state/strategy signatures, limitations, fields, and bounded
failure statistics. Projection streams one draw for one candidate chunk through
the frozen cost interpreter and discards the rawData immediately, retaining only
the smaller `[draw, candidate, objective]` tensor and validity mask. Neither the
sampler nor projector imports or calls the recorder.

The conditional-INR posterior adapter is an explicit derived view over the loaded
ensemble: seeded draws retain one member across candidates, fields, and objectives,
and full-grid reconstruction freezes selector metadata/axes. Its nominal finite
support is distinct loaded members; its effective support counts distinct drawn
members that remain complete after inference and cost projection. The experimental
qLogNEHVI spike consumes only the reduced objective tensor, rejects incomplete
draws as a whole, and retains no rawData. It proves backend compatibility without
creating an optimization strategy or new source of truth.

## Invariants

- Fast/local/distributed evaluators differ in execution transport and intermediate
  evidence backing, but converge on one finalizer. Current cost precedes recorder
  admission, and later evaluation depends on reliable durable publication.
- Fast uses bounded reusable local processes. A crash or timeout discards and
  replaces only that worker, cleans its configured scratch, and preserves ordering.
- Local concurrency is bounded by population size, an explicit cap, physical CPU,
  currently available memory, and free disk; smoke remains exactly one worker.
- Parameter identity/order/count and objective width are checked against the first
  generation and remain stable for supported in-campaign edits; the task snapshot
  itself is refreshed every generation.
- One generation uses one coherent task/config snapshot; supported task edits become
  visible at the following generation boundary rather than dividing a population
  between definitions.
- All population-return paths preserve input order and objective width.
- Individual execution/rawData/current-cost failures yield diagnostic rows and
  infinite costs without deleting successful evidence; the diagnostic rows are
  themselves published before the population completes.
- One campaign lock and one bounded writer exist per active workspace. Count and
  conservative peak-resident byte credits cover queued and in-flight envelopes;
  full budgets block producers, publication failure stops the campaign, and
  published segments and legacy files are never rewritten.
- Stored rawData stays rich enough for later cost changes and surrogate learning;
  task cost code may select smaller windows when calculating objectives.
- New task cost policies use fixed physical thresholds and a bounded mapping rather
  than history/population-dependent normalization, so identical evidence retains
  the same interpretation independently of other samples.
- No task module duplicates behavior that is invariant across optimization tasks,
  and no package module hard-codes behavior that changes with a task.
- External simulator subprocess failures never publish partial evidence. Validated
  local/distributed files and fast in-memory payloads retain identical rawData
  basenames, arrays, metadata, units, and meaning before common recording/cost.
- A persistent posterior draw denotes one possible function across every candidate,
  rawData field, and derived objective. Repeated candidates have identical values
  within a draw; candidate permutation, chunk size, and chunk call order do not
  resample it. Optional numerical backends remain lazy at parent
  `yadof.surrogate` and `yadof.optimize` import.
