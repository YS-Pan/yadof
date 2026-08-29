# Architecture

`src/yadof_benchmark/cli.py` owns argument parsing, bounded default summaries,
explicit complete-JSON presentation, and opt-in child-output streaming.
`src/yadof_benchmark/api.py` is the explicit public facade. Workspace
`benchmark.py` is the only editable workflow program.

One workflow has one explicit frozen evidence class. `structural` covers package,
CLI, adapter-smoke, and bounded canary validation without permitting algorithm
performance conclusions. `performance` covers descriptive measured campaigns
without winner/acceptance logic. Recovery and fault-injection tests are separately
marked engineering evidence: they prove resume semantics, not optimizer quality.
The runtime propagates the class through plans, cells, run reports, indexes, and
inspect instead of inferring it from budget size.

Explicit classification does not permit an internally inconsistent performance
plan. Workflow freeze rejects any performance comparison below population 100 or
20 generations, a 2000-real-evaluation hard floor. Structural workflows retain
small budgets. Performance comparisons derive a separate replication scope from
their explicit seed list: one seed is exploratory, while two or more are
multi-seed without an automatic robustness or significance claim.

The bounded `benchmark_runtime/` package separates responsibilities:

- `workspace.py` and `naming.py`: workspace identity, timestamped human-visible
  names, and non-overwriting initialization;
- `workflow.py`: small user-facing builder and immutable request construction;
- `planning.py`: dynamic Python loading, strategy validation, and cell expansion;
- `baselines.py`: recursive manifests and clean workspace snapshots;
- `storage.py`: digests, immutable inputs, readable attempt evidence, compact
  run-local execution workspaces, frozen matched-timing history, host identity,
  and atomic state;
- `execution.py`: checked subprocess execution, all-infinite-generation rejection,
  foreground-thread progress event delivery, collection, mandatory per-cell
  cost/domain visualization, and orchestration;
- `terminal.py`: caller-thread Rich ownership, fixed cell/global rows, bounded
  plain-terminal snapshots, and durable run-level lifecycle logging;
- `launch.py`: Windows visible-by-default detached launch and immediate
  PID/run/log/inspect receipt; hidden launch is an explicit exception;
- `postprocessing.py`: retryable run-local user callbacks;
- `results.py`: public-yadof collection, four-way evaluation accounting,
  generation-0 population fingerprinting, paired-fairness validation,
  attempted-evaluation-aligned HV trajectory/AUC and cross-seed descriptive
  reports, bounded inspect summaries, and workspace-level run indexes;
- `progress.py` and `timing.py`: read-only activity/ETA calculation, exact versus
  compatible same-arm matching, timestamped-generation trend replay, and bounded
  timing-history construction;
- `contracts.py`: dependency-free frozen and serialized contracts.

The dependency direction is:

```text
workspace benchmark.py -> public yadof_benchmark API -> bounded runtime
bounded runtime -> public installed yadof APIs and CLI
yadof core -X-> yadof_benchmark
```

Planning deliberately executes arbitrary user Python. Its safety boundary is
documentary and operational: `benchmark.py` is trusted workspace code, `check` and
`plan` are advertised as run-read-only rather than code-sandboxed, and expensive or
external side effects are forbidden by the authoring contract.

A long performance run follows a documented ladder: bounded plan/check, real
adapter smoke, then a bounded structural canary using the same baseline/strategy/
configuration paths. These measured steps retain normal simulator authority. A
benchmark incompatibility is repaired and structurally revalidated before full
execution; a yadof framework defect becomes a separate root toDo and blocks the
affected full campaign rather than acquiring a benchmark-local workaround.

Difficulty remains task-owned rather than a generic validator property. The user
contract requires a complete non-surrogate reference calibration toward roughly
10000 evaluations to convergence when the 2000-evaluation floor solves a baseline
too easily; the runtime cannot infer scientific task difficulty from budget alone.

Pairing is validity, not optimizer scoring. Arms in the same baseline/seed group
must share the frozen baseline digest, planned and attempted real-evaluation
budgets, and the fingerprint of the complete ordered normalized generation-0
population. Any mismatch invalidates the pair, suppresses its reference delta, and
excludes that seed from cross-seed aggregates while preserving its cell evidence.
Final HV and trapezoidal HV-AUC use cumulative attempted real evaluations as their
axis. Failures, non-finite objectives, and incomplete counts remain validity facts;
the runtime does not turn them into a performance score.

Optimizer wall time remains operational evidence rather than a primary algorithm
metric. Public surrogate-training metadata is summarized separately. An optional
positive `representative_generation_seconds` workflow value supplies an external
expensive real-evaluation-generation reference for descriptive ratios; the cheap
benchmark generation runtime is never substituted for it.

Process-window ownership stays at the caller boundary rather than inside the
runtime driver. Measured CLI `run` and `resume` operations default to a visible
terminal: a caller may use its current visible terminal, while `--detach` creates
a separate normal Windows console and immediately returns inspection details.
`--hidden` is valid only with explicit detach and user authority. Drain threads
write child logs and enqueue parsed snapshots; only the foreground command owner
emits events and creates, refreshes, prints above, or stops the Rich presentation.
The Windows child explicitly breaks away from a caller job so Codex command-host
cleanup cannot terminate the long run after the receipt returns. Visible launch
also leaves all three standard handles console-owned; redirecting even stdin would
cause Windows to preserve the short-lived automation host's pipe handles instead.
Python API calls remain synchronous, window-neutral, and input-free.
