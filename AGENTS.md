# benchmark_automation agent instructions

These instructions apply when this Git repository is opened as the project. Keep
the first read small: route to the narrowest artifact that can answer the task.

## Progressive disclosure

For an existing run, start with:

```powershell
& "..\.venv\Scripts\python.exe" ".\benchmark.py" inspect --run-id <run-id>
```

Then expand only if the summary leaves a specific question unanswered:

1. Read `runs/<run-id>/report.md` for concise narrative and paired values.
2. Query only the needed top-level field or pair from `report.json`.
3. For a failed/incomplete cell, query that cell in `run_state.json`, then its
   latest `command.finished.json`, then the tail of the relevant stdout/stderr log.
4. Read one cell and one field from `metrics.json` or an append-only
   `collection.json` only when the report cannot answer the question.

Never read `metrics.json` or `collection.json` wholesale. Never recursively list
or search all of `runs/`, attempt workspaces, baselines, or the outer workspace to
learn one run's status. Do not read successful-cell logs during ordinary result
interpretation.

## CLI output policy

- Use the default bounded output from `plan`, `preflight`, `report`, and `inspect`.
- Use `plan --full-json`, `preflight --full-json`, or `report --full-json` only when
  a named field omitted from the summary is required.
- `run` and `resume` always preserve child stdout/stderr in per-command logs. Do
  not pass `--stream-output` unless the user requests live raw output or a specific
  failure requires it.
- After `collect`, run `report`; do not open the generated collection directly.
- Treat performance output as descriptive evidence. Do not invent rankings,
  significance claims, thresholds, or scientific acceptance decisions.

## Execution safety

`plan` is the no-write starting point. `preflight` performs validation but does not
launch a simulator. `collect` can perform surrogate model inference. Smoke tests,
optimization runs, resume, and collection remain subject to the cost/risk rules in
`README.md`; obtain user authorization when those rules require it.

Never edit a frozen baseline or an existing run/attempt to repair evidence. Create
a new baseline identity or linked replacement attempt through the runner.

## Development changes

Before changing runner code or output schemas, read `dev_doc/README.md` and
`dev_doc/architecture.md`. Use the outer workspace interpreter explicitly, add
focused tests, and run the unit suite with a fresh absolute pytest `--basetemp` and
`-p no:cacheprovider`. Preserve existing user/runtime evidence.
