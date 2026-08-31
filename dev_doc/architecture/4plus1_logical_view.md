# 4+1 logical view

## Domain concepts

- **Parameter definitions** describe named continuous or discrete task variables.
  Optimizers use normalized coordinates; evaluations receive assigned task values.
- **rawData** is schema-versioned task evidence. It retains physical measurements
  and metadata needed for later interpretation.
- **Current cost** is the objective tuple produced by the current workspace cost
  policy from validated rawData. It is derived, not stored source truth.
- **Prepared job** is one local or distributed candidate execution boundary. A fast
  evaluation has the same logical identity and evidence contract without a durable
  job directory.
- **Backend-neutral result** preserves candidate identity, outcome, diagnostics,
  and either file-backed or memory-backed rawData.
- **Evaluation batch** freezes candidate order and effective backend configuration
  without opening a session, snapshot, worker, process, or scheduler resource.
- **Evaluation handle** is the generation-scoped owner of one started batch. It
  exposes state and idempotent wait/cancel/close operations while hiding concrete
  worker, process, and cluster types.
- **Evaluation result** is the immutable ordered set of payload-free finalized
  `JobResult` rows. Its optimizer-cost view is the only handle boundary that maps a
  missing row cost to correct-width infinity.
- **Campaign session** owns current accepted rows, the workspace campaign lock, and
  reliable publication for one optimization lifetime.
- **Publication receipt** is the candidate/group acknowledgement that changes from
  pending to committed only after immutable segment publication, or to failed when
  publication cannot complete.
- **Recording segment** is immutable durable evidence containing a bounded group of
  candidate records.
- **Evidence dataset** is an immutable ordered view whose original row identity is
  the durable candidate identity. A separate design key may identify repeated
  physical designs without merging their evidence.
- **Cost table** is a current-task interpretation view joined to evidence by row
  identity. It retains objective schema, interpretation fingerprint, typed status,
  and bounded diagnostics without changing the evidence row.
- **Derived evidence row** is a transient owned rawData transform with deterministic
  parent/operation/parameter/ordinal/content lineage. It is never a recorder row.
- **Generation task snapshot** is the coherent task/configuration definition used
  throughout one generation.
- **Surrogate prediction and posterior samples** are transient derived views of
  possible rawData. They are not recorded evidence.
- **External simulator runtime** is a separately provisioned process boundary, not
  another environment in which yadof is installed.

The principal logical pipeline is:

```text
normalized variables -> assigned values -> task rawData -> committed evidence -> current cost
```

Task files own definitions that vary with the scientific problem. The package owns
invariant lifecycle, validation, transport, persistence, failure, and composition
mechanisms.

## Source-of-truth policy

Durable truth includes raw task variables, rawData, schema metadata, lifecycle
metadata, and bounded provenance. Normalized variables, costs, predictions,
posterior draws, and acquisition values are recalculable or transient.

Original `candidate_id`, `evidence_id`, and `row_id` are the same durable identity.
The design key is only an equivalence aid. A derived row keeps its root evidence
identity but receives a deterministic row identity and explicit lineage, so neither
duplicate designs nor reordered views can silently change joins.

Changing task cost code intentionally changes the interpretation of compatible
evidence. Changing parameter ranges or levels changes normalization and later
assignments. The framework can detect mechanical incompatibility, but only the user
decides whether evidence from different task definitions remains scientifically
comparable.

## Generation-boundary mutability

The task definition may change during a campaign. The next generation captures one
new coherent snapshot and rebuilds affected derived views. Parameter identity/count
and objective count remain stable under the current supported contract; structural
dimension changes require separate state semantics.

Fingerprints provide provenance and invalidate derived caches where appropriate.
They do not by themselves prove or disprove scientific compatibility.

## Derived model state

Surrogates learn from recorded real evidence and reconstruct complete rawData before
current-cost interpretation. Any posterior sampler must preserve one function draw
across candidates, fields, and objectives. Candidate-selection components may use
those derived results only behind their declared readiness and failure boundaries;
selected candidates still receive normal real evaluation.

## Invariants

- Fast, local, and distributed execution converge before evidence-first
  finalization and recording.
- Population order and objective width are stable on every return path.
- A started evaluation cannot outlive its generation/session scope. An open handle
  prevents the next snapshot; session shutdown cancels and closes registered
  handles before stopping the recorder or deleting snapshots.
- Handle results are invisible until every returned row has committed evidence and
  a succeeded/failed/not-applicable interpretation classification.
- Individual execution, rawData, or cost failures remain explicit diagnostic rows.
- Valid rawData is durably committed before current cost starts, and all receipts
  resolve before a population boundary completes.
- Stored rawData remains rich enough for later compatible reinterpretation.
- Evidence/cost joins use row identity; view position, job name, and design key are
  never substitutes for sample identity.
- Non-successful interpretations remain typed until the explicit optimizer-shape
  boundary maps them to correct-width `inf`.
- One active campaign owns one workspace lock and one bounded writer.
- Task code never duplicates cross-task framework mechanisms, and package code does
  not hard-code task-specific simulator or objective policy.
- External simulator failures or partial artifacts never publish normal evidence.
- Predicted rawData never enters real history.
- Optional numerical backends remain absent from ordinary parent imports.
