# Architecture

`src/yadof_benchmark/cli.py` owns argument parsing and JSON presentation.
`src/yadof_benchmark/api.py` is the explicit public facade. The files are the
direct successors of the former root entry files; no aliases remain.

The bounded `benchmark_runtime/` package separates responsibilities:

- `workspace.py`: workspace identity and non-overwriting initialization;
- `workflow.py`: small user-facing builder and immutable request construction;
- `planning.py`: dynamic Python loading, strategy validation, and cell expansion;
- `baselines.py`: recursive manifests and clean workspace snapshots;
- `storage.py`: digests, immutable inputs, run layout, and atomic state;
- `execution.py`: checked subprocess execution, collection, and orchestration;
- `postprocessing.py`: retryable run-local user callbacks;
- `results.py`: public-yadof collection and descriptive reports;
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
