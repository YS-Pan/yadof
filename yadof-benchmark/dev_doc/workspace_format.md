# Workspace and workflow contract

`.benchmark/workspace.json` is a fixed JSON identity marker with format
`yadof.benchmark.workspace`, `workflow` equal to `benchmark.py`, and `resources`
equal to `resources`. It does not encode strategies, matrices, or behavior.

The loader imports `benchmark.py` under a unique temporary module name, obtains
`build_benchmark`, passes a new `Benchmark` builder, requires a `None` return, and
freezes the builder. Import errors and builder errors become contextual
`BenchmarkError` instances. Every postprocessor must resolve to the same named
top-level function in the loaded module.

Builder paths are absolute after resolution from the workspace. Strategies may
provide one default complete source plus baseline-specific complete sources.
Planning parses each selected module and requires a top-level
`build_optimization()`. It does not import strategy modules or classify algorithms.

Each `compare()` call owns its baseline IDs, strategy IDs, seeds, budget, and
optional reference. Multiple calls express heterogeneous future workflows without
expanding a fixed schema. Deterministic expansion order is comparison declaration,
baseline declaration, strategy declaration, then seed declaration. Cell IDs include
all four identities and collision-check before any write.

The workflow input digest covers `benchmark.py` and every non-cache file below
`resources/`. Planning also digests each selected strategy, baseline clean input,
and driver. The resulting `RunSpec` is the only execution plan.
