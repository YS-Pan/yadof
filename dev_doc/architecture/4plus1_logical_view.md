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
- **Campaign session** owns current accepted rows, the workspace campaign lock, and
  reliable publication for one optimization lifetime.
- **Recording segment** is immutable durable evidence containing a bounded group of
  candidate records.
- **Generation task snapshot** is the coherent task/configuration definition used
  throughout one generation.
- **Surrogate prediction and posterior samples** are transient derived views of
  possible rawData. They are not recorded evidence.
- **External simulator runtime** is a separately provisioned process boundary, not
  another environment in which yadof is installed.

The principal logical pipeline is:

```text
normalized variables -> assigned values -> task rawData -> current cost
```

Task files own definitions that vary with the scientific problem. The package owns
invariant lifecycle, validation, transport, persistence, failure, and composition
mechanisms.

## Source-of-truth policy

Durable truth includes raw task variables, rawData, schema metadata, lifecycle
metadata, and bounded provenance. Normalized variables, costs, predictions,
posterior draws, and acquisition values are recalculable or transient.

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

- Fast, local, and distributed execution converge before current-cost finalization
  and recording.
- Population order and objective width are stable on every return path.
- Individual execution, rawData, or cost failures remain explicit diagnostic rows.
- Current cost is known before recorder admission, and accepted evidence is durable
  before a population boundary completes.
- Stored rawData remains rich enough for later compatible reinterpretation.
- One active campaign owns one workspace lock and one bounded writer.
- Task code never duplicates cross-task framework mechanisms, and package code does
  not hard-code task-specific simulator or objective policy.
- External simulator failures or partial artifacts never publish normal evidence.
- Predicted rawData never enters real history.
- Optional numerical backends remain absent from ordinary parent imports.
