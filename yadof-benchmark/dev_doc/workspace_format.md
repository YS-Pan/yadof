# Workspace and workflow contract

`.benchmark/workspace.json` is a fixed JSON identity marker with format
`yadof.benchmark.workspace`, `workflow` equal to `benchmark.py`, and `resources`
equal to `resources`. It does not encode strategies, matrices, or behavior.

Initialization treats the requested leaf as a semantic name and materializes a
human-visible `YYYYMMDD_HHMMSS-<semantic>` workspace unless the leaf is already
timestamp-prefixed. Workspace-level `reports/<run-id>/` and
`visualizations/<run-id>/` directories are run indexes, not second copies of
authoritative evidence; their run IDs carry the same local timestamp prefix.

The loader imports `benchmark.py` under a unique temporary module name, obtains
`build_benchmark`, passes a new `Benchmark` builder, requires a `None` return, and
freezes the builder. Import errors and builder errors become contextual
`BenchmarkError` instances. Every postprocessor must resolve to the same named
top-level function in the loaded module.

Builder paths are absolute after resolution from the workspace. Strategies may
provide one default complete source plus baseline-specific complete sources.
Planning parses each selected module and requires a top-level
`build_optimization()`. It does not import strategy modules or classify algorithms.

Every selected baseline must include `workspace/postprocess.py`. Its command-line
surface is fixed to `--workspace`, `--output-dir`, and `--output-prefix`; a run
snapshot owns the script used by each cell.

Each `compare()` call owns its baseline IDs, strategy IDs, seeds, budget, and
optional reference. Multiple calls express heterogeneous future workflows without
expanding a fixed schema. Deterministic expansion order is comparison declaration,
baseline declaration, strategy declaration, then seed declaration. Cell IDs include
all four identities and collision-check before any write.

`Benchmark.configure(evidence=...)` is mandatory and accepts exactly `structural`
or `performance`. The value belongs to the whole workflow/run, is copied into each
cell, and participates in the immutable specification digest. It is never inferred
from budget. Structural means integration-only smoke/canary evidence and forbids
algorithm performance conclusions. Performance remains descriptive and grants no
execution authority or automatic scientific decision.

An initialized `benchmark.py` visibly scaffolds run policy, one semantically named
algorithm strategy, baseline selection, seeds, budget, and a top-level
postprocessor. The scaffold remains inert until the author supplies complete
strategy resources and deliberately enables the declarations. Strategy IDs and
display names describe algorithms, not comparison roles.

Within a selected baseline collection, each manifest directory relative to the
collection root must exactly equal its semantic ID, such as
`ngspice/saw-ladder`. Editable source directories never append provenance digests;
run creation records digests and freezes the complete selected source instead.

The workflow input digest covers `benchmark.py` and every non-cache file below
`resources/`. Planning also digests each selected strategy, baseline clean input,
and driver. The resulting `RunSpec` is the only execution plan.

CLI `check` and `plan` present a bounded count/ID/budget summary by default. Their
`--json` option exposes this complete `RunSpec`; both modes remain run-read-only.
