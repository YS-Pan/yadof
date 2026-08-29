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

`Benchmark.configure(representative_generation_seconds=...)` optionally freezes a
positive finite external reference for one representative expensive generation of
real evaluations. Result collection compares recorded surrogate-training duration
with this value descriptively. It must not be populated from the cheap benchmark
cell's own generation runtime and does not create an acceptance threshold.

`Benchmark.configure(cell_concurrency=...)` freezes a positive integer number of
simultaneously active benchmark cells. It defaults to `1`; declaration order is
the FIFO admission order. This control does not set yadof's per-cell simulation
worker pool and never changes population, generation, seed, or pairing budgets.

For `execution.mode` equal to `fast` or `local`, every baseline manifest must also
declare `execution.simulation_concurrency.max_workers` and boolean
`resource_autodetect`. Planning freezes both fields into each cell. Attempt
materialization appends the corresponding `FAST_` or `LOCAL_` yadof settings to
the run-owned `config.py` and records them in `attempt.json`. Other execution modes
cannot use this local-worker field because their concurrency belongs to their
external scheduler.

After the explicit class is known, freeze validates scale consistency. Every
performance comparison requires population at least 100 and generations at least
20, which guarantees at least 2000 planned real evaluations per cell. Structural
comparisons retain arbitrary positive budgets. The exact seed list remains
comparison-owned and configurable. A performance comparison with one seed freezes
`exploratory` replication scope; two or more freeze `multi-seed`, which still does
not assert robustness or significance.

An initialized `benchmark.py` visibly scaffolds run policy, one semantically named
algorithm strategy, baseline selection, seeds, budget, and a top-level
postprocessor. Its 12 × 3 budget is labeled structural-only, while comments state
the performance floor and single-seed interpretation. The scaffold remains inert
until the author supplies complete strategy resources and deliberately enables the declarations. Strategy IDs and
display names describe algorithms, not comparison roles.

Within a selected baseline collection, each manifest directory relative to the
collection root must exactly equal its semantic ID, such as
`ngspice/saw-ladder`. Editable source directories never append provenance digests;
run creation records digests and freezes the complete selected source instead.

The workflow input digest covers `benchmark.py` and every non-cache file below
`resources/`. Planning also digests each selected strategy, baseline clean input,
and driver. The resulting `RunSpec` is the only execution plan.

CLI `check` and `plan` present a bounded count/ID/budget summary by default. Their
summary includes both concurrency layers. Their `--json` option exposes this
complete `RunSpec`; both modes remain run-read-only.
