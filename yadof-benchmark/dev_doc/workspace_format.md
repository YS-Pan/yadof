# Workspace format

A workspace marker is:

```text
.benchmark/workspace.json
```

with `format = "yadof.benchmark.workspace"`, `workflow = "benchmark.py"`,
`resources = "resources"`, and the initializing preset ID. A sibling
`.benchmark/preset.json` records a catalog digest plus relative source,
workspace destination, byte count, and SHA-256 for every materialized file.

The initialized layout is:

```text
WORKSPACE/
├── .benchmark/
│   ├── workspace.json
│   └── preset.json
├── benchmark.py
├── resources/
├── cells/
├── postprocessing/
├── reports/
├── visualizations/
└── temp/
```

The workspace path is timestamp-prefixed by `init` and returned to the caller.
`portable` is the no-argument default; `complete` and `blank` require explicit
selection. Preset source paths are package-relative and never expose the build
checkout, account, drive, or historical evidence location.
It is both the authoring root and the single execution root.

`load_workspace` validates only the current marker, workflow file, and resource
directory. The package makes no promise to interpret older multi-run workspace
contents.

`benchmark.py` must define `build_benchmark(benchmark)` and return `None`.
Top-level named workflow postprocessors may be registered. A strategy entry must
contain a literal `YADOF_OPTIMIZATION_PROGRAM` declaration. Planning parses that
declaration without importing the strategy and resolves every declared helper
below the entry module's directory. The removed factory entry is rejected.

Planning is read-only: it imports the live file with bytecode writes disabled,
validates selected baseline/strategy sources, fingerprints the entry and all
declared helpers, resolves defaults, and expands cells as `c0001`, `c0002`, and
so on. Planning also creates a semantic `display_label`; duplicate
baseline/strategy/seed identities or display-label collisions are rejected while
the display label remains outside filesystem names. Readers derive a fallback
label for older spec/state records that lack the field.

Execution does not copy the authoring program or resources. Workflow
postprocessors import the same live `benchmark.py` once after cell collection.
Concurrency with human edits during execution is intentionally outside the simple
single-workspace contract.
