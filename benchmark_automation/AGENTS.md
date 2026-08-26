# benchmark_automation agent instructions

These instructions apply to work below `benchmark_automation/`. Run benchmark
commands from the yadof source-checkout root. Keep the first read small: route to
the narrowest artifact that can answer the task.

The configured default puts every generated run directly below the checkout's
ignored `temp/` directory as `temp/<run-id>/`; do not add a task-specific container
layer. If `--runs-dir` overrides that root, reuse the exact option for every later
command addressing the run. Do not infer agent mode in the runner and do not delete
temporary evidence before handoff.

## Progressive disclosure

For an existing run, start with:

```powershell
python ".\benchmark_automation\benchmark.py" `
  --runs-dir ".\temp" `
  inspect --run-id <run-id>
```

Then expand only if the summary leaves a specific question unanswered:

1. For a running benchmark, use the summary's `run.timing` fields for active
   progress, inactivity age, remaining seconds, completion UTC, confidence, and
   basis. Do not read logs merely to recompute ETA.

2. Read `<runs-dir>/<run-id>/report.md` for concise narrative and paired values.
3. Query only the needed top-level field or pair from `report.json`.
4. For a failed/incomplete cell, query that cell in `run_state.json`, then its
   latest `command.finished.json`, then the tail of the relevant stdout/stderr log.
5. Read one cell and one field from `metrics.json` or an append-only
   `collection.json` only when the report cannot answer the question.
6. When visual inspection is relevant, open only the attempt's declared result
   directory below `visualizations/` and its one matching prefixed cost plot below
   `visualizations/viewcost/`. Do not load every visualization artifact.

Never read `metrics.json` or `collection.json` wholesale. Never recursively list
or search all of the selected runs directory, attempt workspaces, baselines, or the
repository to learn one run's status. Do not read successful-cell logs during
ordinary result interpretation.

## CLI output policy

- Use the default bounded output from `plan`, `preflight`, `report`, and `inspect`.
- Use `plan --full-json`, `preflight --full-json`, or `report --full-json` only when
  a named field omitted from the summary is required.
- `run` and `resume` always preserve child stdout/stderr in per-command logs. Do
  not pass `--stream-output` unless the user requests live raw output or a specific
  failure requires it.
- In an interactive terminal, `run` and `resume` use Rich to keep the active
  cell's individual-evaluation bar immediately above the global cell bar. Both
  task states update before one atomic refresh; cell progress is cumulative across
  generations and leads with count, percentage, and generation. A positive count
  always lights one bar cell, low percentages retain one decimal, and compact rows
  preserve their complete counts/status in normal terminals. Both bars remain below
  unchanged lifecycle/streamed messages and disappear cleanly after execution. The
  CLI waits for Enter after the final JSON summary.
  Non-interactive agent execution emits throttled complete snapshots and exits
  normally.
- After `collect`, run `report`; do not open the generated collection directly.
- Default `report` and completed `inspect` keep JSON on stdout and print the
  bounded final cumulative-HV Markdown table on stderr.
- Treat performance output as descriptive evidence. Do not invent rankings,
  significance claims, thresholds, or scientific acceptance decisions.

## Execution safety

`plan` is the no-write starting point. `preflight` performs validation but does not
launch a simulator. `collect` can perform surrogate model inference. Smoke tests,
optimization runs, resume, and collection remain subject to the cost/risk rules in
`README.md`; obtain user authorization when those rules require it.

Do not use a few generations or a population of only dozens to evaluate or tune
surrogate/optimizer performance. That purpose requires the complete unfiltered
`performance` suite, currently 100 individuals by 20 generations in every measured
cell (2,000 attempts per cell; 36,000 across 18 cells). Structural and pilot suites
may diagnose wiring, prerequisites, failures, and runtime cost only; their results
must not drive algorithm-performance claims or tuning.

Baseline templates may be edited in place for future runs. Run `preflight` after
editing them. Never edit an existing run's `inputs/`, attempt workspace, or evidence
to repair results; resume must use the run-local baseline snapshot and linked
replacement attempts created by the runner.

## Development changes

Before changing runner code or output schemas, follow the complete reading order in
`dev_doc/README.md`: operator-doc contract and root docs, every split architecture
view, terminology, active toDos, and targeted blueprints. Use the selected Python
containing the installed yadof distribution, add focused tests, and run the unit
suite with a fresh absolute pytest `--basetemp` and `-p no:cacheprovider`.
Preserve existing user/runtime evidence.
