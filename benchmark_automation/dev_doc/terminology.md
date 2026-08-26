# Benchmark-Specific Terminology

| Term | Meaning |
|---|---|
| `source-checkout benchmark` | The tracked runner, configuration, editable baselines, strategies, tests, and documentation below `benchmark_automation/`; it executes an installed yadof distribution but is excluded from wheel/sdist. |
| `baseline template` | A mutable semantic task directory used only to create later run snapshots. |
| `run-local baseline snapshot` | Immutable copy of declared baseline inputs owned by one run and used by all of its cells/resume attempts. |
| `run specification` | Immutable resolved identity over package, runner, configuration, host facts, cases, arms, resources, plan, and snapshots. |
| `cell` | One isolated case/arm/seed experiment or disposable smoke unit in the matrix. |
| `attempt` | One immutable execution workspace and command history for a cell; an interrupted attempt may have a linked replacement. |
| `run state` | Atomically replaced latest index of cell and attempt statuses. It is operational state, not scientific evidence. |
| `yadof progress snapshot` | One complete plain piped line reporting a smoke/generation local total, successes, errors, and remaining count. The runner logs it and converts it to cumulative cell progress. |
| `cell progress` | Display-only cumulative attempted evaluations across generations for the active cell. Any positive count lights a bar cell and sub-10% values retain one decimal. |
| `benchmark ETA` | Read-only best-effort wall-clock estimate from the immutable plan, completed-cell duration cohorts, and active command progress. It includes confidence/basis and is neither a deadline nor benchmark evidence. |
| `inactivity age` | Seconds since the active command start or latest stdout/stderr write, whichever is newer; it helps a later turn distinguish slow progress from a quiet or potentially stuck phase. |
| `bounded summary` | Default JSON containing the next decision's facts while omitting expanded commands, fingerprints, raw metric rows, and large diagnostics. |
| `structural evidence` | Wiring, prerequisite, failure-path, checkpoint, and public-inspection validation; it cannot justify algorithm-performance tuning. |
| `performance evidence` | Full-scale equal-budget paired observations and descriptive differences; it does not rank algorithms or imply significance. |
