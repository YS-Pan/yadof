# 4+1 process view

## Evaluation sequence

```mermaid
sequenceDiagram
    participant O as strategy or caller
    participant H as evaluation handle
    participant E as evaluation manager
    participant T as task execution
    participant F as common finalizer
    participant R as campaign recorder
    participant C as current task cost
    O->>H: prepare and start normalized population
    H->>E: frozen batch and cancellation signal
    loop each candidate
        E->>T: assigned values and isolated execution context
        T-->>E: rawData or failure diagnostics
        E->>F: backend-neutral result
        F->>F: validate and own evidence
        F->>R: bounded prepared-evidence group
        R-->>F: committed or failed receipt
        F->>C: calculate current cost in population order
    end
    F-->>H: payload-free finalized rows
    H-->>O: immutable result after backend cleanup
```

The evaluation manager prepares candidates as they complete while preserving input
order for interpretation and return. The coordinator flushes on the existing
segment count/byte target or the population tail. Current cost starts only after
the candidate's immutable segment is recovery-visible. Bounded recorder capacity
may pause producers; publication failure wakes the affected receipts and stops the
campaign rather than losing accepted evidence.

`wait()` may be called by multiple threads and returns the same cached terminal
result; its timeout does not cancel work. `cancel()` changes running state to
cancelling once. Fast drains queued work and kills active worker trees, local
terminates active workflow trees and short-circuits queued candidates, and
distributed stops submission/polling and attempts cluster removal. Every unfinished
started row still passes through the common finalizer as `cancelled`; a completion
already observed by the backend remains completed evidence.

## Backend processes

- **Fast:** reusable local workers receive assigned values and an isolated
  candidate context, load task evaluator code, and return named memory rawData.
  Worker crash, timeout, or task failure affects only that candidate and worker.
- **Local:** the submit host prepares a self-contained job and launches its task
  workflow as a subprocess. Process-tree cleanup and job diagnostics remain local
  backend responsibilities.
- **Distributed:** the submit host prepares the same logical job, HTCondor executes
  it under administrator policy, and returned evidence is restored and validated
  before entering the common finalizer.

Backend-specific resource observations may inform later concurrency, requests, or
timeouts, but do not alter evidence meaning.

## Derived candidate selection

A rawData-first surrogate consumes recorded real evidence. Posterior-capable
components may create stable function draws and project complete predicted rawData
through one frozen current-cost interpreter. Candidate selection retains only the
derived objective samples and diagnostics.

Posterior-assisted selection is explicit and fail-closed. It requires its declared
readiness; unavailable or unusable derived state follows the strategy's documented
fallback or stop boundary. Every selected candidate still enters the common real
evaluation, finalization, and recording sequence.

## Generation-boundary task changes

Before each generation the campaign reloads effective configuration and captures
the complete current task source roots. The generation uses that one immutable
snapshot for parameters, evaluation, cost interpretation, and optimization
composition. Edits made during a generation become visible only at a later
generation boundary.

A session registry retains every handle created against its current snapshot.
Beginning another generation fails while any such handle is open, including a
completed-but-not-closed handle. Session close copies the registry, cancels and
closes each handle without holding the recorder state lock, and only then shuts down
the writer and deletes snapshots.

Mechanically compatible history is reinterpreted through the new snapshot. Source
identity can invalidate caches and record provenance, but the user remains
responsible for deciding whether earlier evidence should be retained, cleared, or
separated.

History reinterpretation first freezes an `EvidenceDataset` without decoding
rawData. It then walks rows in stable order through one frozen task interpreter,
materializing and releasing at most one candidate payload at a time. The resulting
`CostTable` binds every interpretation to row identity, objective schema, and task
fingerprint. Identity-based joins feed current history and compatibility adapters;
pending, failed, or derived rows cannot enter committed optimizer history.

## External simulator subprocesses

A packaged adapter may launch task-owned child code in a separately provisioned
simulator runtime. The yadof-side process and simulator child do not import each
other's frameworks. They communicate through bounded, versioned, validated files
inside candidate-isolated scratch, and only complete rawData crosses into the
normal backend result.

Interpreter provisioning, host availability, ACLs, and machine configuration are
administrator responsibilities. Task model construction and measurements remain
workspace responsibilities. The adapter owns invariant launch, isolation,
validation, timeout, cleanup, and publication behavior.

## Failure and recovery

- Candidate preparation, execution, transport, validation, and current-cost
  failures are isolated with the correct objective width. Valid rawData is
  committed as completed evidence before a current-cost failure is reported, so a
  later generation can replay the interpretation.
- Backend-specific retry is permitted only for declared recoverable conditions and
  remains bounded.
- Timeout or cancellation terminates the candidate process/worker tree or attempts
  scheduler removal and ignores partial rawData. Started cancellation is durable
  diagnostic evidence; cancellation before start creates no record.
- Recorder failure is campaign-fatal because later evaluation must not proceed with
  a gap in accepted evidence.
- History readers tolerate unrelated or corrupt entries by isolating them rather
  than mutating surviving evidence.
- Execution failure, missing evidence, and callback/shape/non-finite interpretation
  failure remain distinct cost-table statuses; only the optimizer conversion emits
  fixed-width failure sentinels.

## Concurrency and publication

- Candidate execution contexts and scratch directories are unique.
- Task modules are loaded in isolated temporary namespaces.
- One active campaign holds one workspace lock and one recorder writer.
- Population results are reassembled in input order regardless of completion order.
- Workers never write recorded data directly; the common finalizer and recorder own
  that boundary.
- A process lost after commit but before cost may leave interpretation absent; a
  new session still recovers the evidence. Queue admission alone is never a commit.
