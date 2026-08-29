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
  collection, mandatory per-cell cost/domain visualization, and orchestration;
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
terminal: a caller may use its current visible terminal, while an agent detaching a
long Windows run creates a separate normal console. Hidden launch flags are used
only when the user explicitly requests that exception. Python API calls remain
synchronous and do not create an operating-system console.
