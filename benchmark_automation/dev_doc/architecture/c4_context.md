# C4 Context

## System boundary

The benchmark compares several declared optimization tasks and strategy arms under
isolated, reproducible budgets. It owns cross-run orchestration and descriptive
alignment; installed yadof owns every single-workspace optimizer, evaluator,
recorder, surrogate, and viewer mechanism.

## People and responsibilities

- The user selects scientific tasks, arms, suites, authority for real execution,
  and acceptance of algorithm results.
- A coding agent reads bounded summaries, edits tracked benchmark inputs/code, and
  may inspect or report a detached run without polling it continuously.
- Benchmark maintainers own configuration validation, immutable identity, attempt
  isolation, progress, ETA, collection, reports, docs, and tests.
- Yadof maintainers own reusable workspace behavior and public observation APIs.
- Administrators own simulators, CUDA, licenses, external runtimes, storage, and
  machine reliability.

## External systems

- Installed yadof CLI and Python APIs execute and inspect one workspace.
- ngspice, PyChrono, CUDA/Torch, and task postprocessors perform case-specific work.
- Rich owns terminal cursor movement for the two live progress rows.
- The filesystem stores immutable inputs, bounded timing-history snapshots,
  attempts, logs/timestamped progress events, state, visualizations, collection
  snapshots, and reports.
- Each new run owns its complete execution package. The live checkout supplies new
  runs only and is not a resume authority for existing runs.
- A later Codex automation or another agent turn may invoke `inspect` as an
  unattended read-only status/ETA probe.

The runner diagnoses missing or failed external resources but never installs,
repairs, restarts, or silently substitutes them.
