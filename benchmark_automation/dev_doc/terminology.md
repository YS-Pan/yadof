# Benchmark-Specific Terminology

| Term | Meaning |
|---|---|
| `source-checkout benchmark` | The tracked runner, configuration, editable baselines, strategies, tests, and documentation below `benchmark_automation/`; it executes an installed yadof distribution but is excluded from wheel/sdist. |
| `baseline template` | A mutable semantic task directory used only to create later run snapshots. |
| `run-local baseline snapshot` | Immutable copy of declared baseline inputs owned by one run and used by all of its cells/resume attempts. |
| `benchmark preregistration` | A versioned tracked schema/experiment contract below `preregistrations/` that freezes provenance, design-level splits, metrics, comparisons, seeds, resource capture, threshold-sealing rules, and stop conditions before test access. It is neither a runnable suite nor evidence; an unsealed dataset or threshold explicitly keeps formal execution blocked. |
| `run specification` | Immutable resolved identity over package, runner, configuration, host facts, cases, arms, resources, plan, and snapshots. |
| `cell` | One isolated case/arm/seed experiment or disposable smoke unit in the matrix. |
| `attempt` | One immutable execution workspace and command history for a cell; an interrupted attempt may have a linked replacement. |
| `run state` | Atomically replaced latest index of cell and attempt statuses. It is operational state, not scientific evidence. |
| `yadof progress snapshot` | One complete plain piped line reporting a smoke/generation local total, successes, errors, and remaining count. The runner logs it and converts it to cumulative cell progress. |
| `command progress event stream` | One command-local append-only `progress.jsonl` containing timestamped command-start, parsed yadof progress, and command-end events. The foreground owner writes it; finished metadata records its fingerprint. |
| `cell progress` | Display-only cumulative attempted evaluations across generations for the active cell. Any positive count lights a bar cell and sub-10% values retain one decimal. |
| `timing-history snapshot` | Immutable bounded operational `timing_history.json` created by shallow-reading earlier immediate run directories. It holds completed-cell durations plus exact/compatible signatures for ETA only; it is not run identity or scientific evidence. |
| `benchmark ETA` | Read-only best-effort wall-clock estimate from the immutable plan, exact/compatible matched-cell timing medians, current arm-safe observations, and active timestamped generation phases. It excludes cross-arm same-case point estimates, reports confidence/basis/sample dispersion, and is neither a deadline nor benchmark evidence. |
| `inactivity age` | Seconds since the active command start/end, latest timestamped progress event, or latest command stream write, whichever is newer; it helps a later turn distinguish slow progress from a quiet or potentially stuck phase. |
| `bounded summary` | Default JSON containing the next decision's facts while omitting expanded commands, fingerprints, raw metric rows, and large diagnostics. |
| `structural evidence` | Wiring, prerequisite, failure-path, checkpoint, and public-inspection validation; it cannot justify algorithm-performance tuning. |
| `performance evidence` | Full-scale equal-budget paired observations and descriptive differences; it does not rank algorithms or imply significance. |
