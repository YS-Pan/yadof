# Benchmark-Specific Terminology

| Term | Meaning |
|---|---|
| `source-checkout benchmark` | The tracked runner, configuration, editable baselines, strategies, tests, and documentation below `benchmark_automation/`; it executes an installed yadof distribution but is excluded from wheel/sdist. |
| `baseline template` | A mutable semantic task directory used only to create later run snapshots. |
| `run-local baseline snapshot` | Immutable copy of declared baseline inputs owned by one run and used by all of its cells/resume attempts. |
| `run-local execution snapshot` | Complete `inputs/execution/benchmark_runtime` package owned by a new run and imported for execution/resume. Current checkout changes do not alter it. |
| `provenance digest` | Recorded source, package, wheel, input, or artifact hash used for display and historical traceability only; it never compares current files to reject resume or completion. |
| `legacy run migration boundary` | An unfinished run without a complete execution snapshot cannot be safely resumed automatically and requires explicit restart/migration. Completed evidence remains readable. |
| `case strategy template` | One complete arm-and-case `submit/optimization.py` source selected before a run. It carries explicit search/GPSAF/surrogate factory kwargs; managed config overrides remain core-policy-only. |
| `benchmark preregistration` | A versioned tracked schema/experiment contract below `preregistrations/` that freezes provenance, design-level splits, metrics, comparisons, seeds, resource capture, threshold-sealing rules, and stop conditions before test access. It is neither a runnable suite nor evidence; an unsealed dataset or threshold explicitly keeps formal execution blocked. |
| `formal-start gate` | The fail-closed conjunction of accepted upstream scientific evidence, a complete required arm matrix, all pre-access numeric threshold seals, installed-package identity, resource preflight, and campaign authority. A no-write plan or successful structural suite does not open it. |
| `fail-closed release phase` | A preregistered Phase A/B/C status that can expose experimental offline or explicit fallback mechanics while independently prohibiting campaign influence, exploitation, recommendation, default migration, and TODO archival. |
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
