# Architecture

`src/yadof_benchmark/cli.py` owns argument parsing and JSON presentation.
`src/yadof_benchmark/api.py` is the explicit public facade. Workspace
`benchmark.py` is the only editable workflow program.

The bounded `benchmark_runtime/` package separates responsibilities:

- `workspace.py` and `naming.py`: workspace identity, timestamped human-visible
  names, and non-overwriting initialization;
- `workflow.py`: small user-facing builder and immutable request construction;
- `planning.py`: dynamic Python loading, strategy validation, and cell expansion;
- `baselines.py`: recursive manifests and clean workspace snapshots;
- `storage.py`: digests, immutable inputs, readable attempt evidence, compact
  run-local execution workspaces, and atomic state;
- `execution.py`: checked subprocess execution, all-infinite-generation rejection,
  foreground-thread progress event delivery, collection, mandatory per-cell
  cost/domain visualization, and orchestration;
- `terminal.py`: caller-thread Rich ownership, fixed cell/global rows, bounded
  plain-terminal snapshots, and durable run-level lifecycle logging;
- `launch.py`: Windows visible-by-default detached launch and immediate
  PID/run/log/inspect receipt; hidden launch is an explicit exception;
- `postprocessing.py`: retryable run-local user callbacks;
- `results.py`: public-yadof collection, cell/HV descriptive reports, and
  workspace-level run indexes;
- `progress.py`: read-only active work summaries;
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
