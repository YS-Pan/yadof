# Workspace format

A workspace marker is:

```text
.benchmark/workspace.json
```

with `format = "yadof.benchmark.workspace"`, `workflow = "benchmark.py"`, and
`resources = "resources"`.

The initialized layout is:

```text
WORKSPACE/
├── .benchmark/workspace.json
├── benchmark.py
├── resources/
├── cells/
├── postprocessing/
├── reports/
├── visualizations/
└── temp/
```

The workspace path is timestamp-prefixed by `init` and returned to the caller.
It is both the authoring root and the single execution root.

`load_workspace` validates only the current marker, workflow file, and resource
directory. The package makes no promise to interpret older multi-run workspace
contents.

`benchmark.py` must define `build_benchmark(benchmark)` and return `None`.
Top-level named workflow postprocessors may be registered. A strategy entry must
define legacy `build_optimization()` or contain a literal
`YADOF_OPTIMIZATION_PROGRAM` declaration. Planning parses explicit declarations
without importing the strategy and resolves every declared helper below the
entry module's directory.

Planning is read-only: it imports the live file with bytecode writes disabled,
validates selected baseline/strategy sources, fingerprints the entry and all
declared helpers, resolves defaults, and expands cells as `c0001`, `c0002`, and
so on. Semantic collision concerns are handled in the spec rather than
filesystem names.

Execution does not copy the authoring program or resources. Workflow
postprocessors import the same live `benchmark.py` once after cell collection.
Concurrency with human edits during execution is intentionally outside the simple
single-workspace contract.
