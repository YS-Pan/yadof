# Benchmark developer guide

`benchmark_automation/` is a source-checkout comparison tool for complete yadof
optimization strategies. It is not installed in the yadof wheel. The tool knows
how to snapshot a task, invoke public yadof commands, collect public observations,
and align equal-budget results. It does not know how an optimization strategy is
assembled.

## Current documents

- [Architecture](architecture.md) defines responsibilities and invariants.
- [Study format](study_format.md) defines the external comparison request.
- [Run format](run_format.md) defines durable output and recovery.

The repository root `dev_doc/` owns project-wide architecture, terminology,
pending work, completed-change records, and maintenance procedure.

## Source layout

```text
benchmark_automation/
├── benchmark.py
├── benchmark_core.py
├── baselines/
├── benchmark_runtime/
├── dev_doc/
└── tests/
```

The two root Python files are the CLI and public API. Runtime modules own contracts,
baseline discovery, planning, storage, execution, progress, and results. Baselines
are self-describing. Tests exercise only these generic contracts.

## Development workflow

Run commands from the yadof checkout root with its regularly installed yadof
distribution:

```powershell
python ".\benchmark_automation\benchmark.py" baselines
python ".\benchmark_automation\benchmark.py" plan --study D:\studies\comparison.toml
```

For a code change:

1. Inspect the repository worktree and preserve unrelated work.
2. Update focused tests before or with the implementation.
3. Run the benchmark tests with a fresh absolute pytest base directory and disable
   the cache provider.
4. Run a no-write `plan` using multiple strategy sources that are not named in
   benchmark code.
5. Do not launch a simulator or measured study merely to validate runner code.
6. Update these current documents and the root project documents they affect.
7. Follow the root build, wheel replacement, installed-package tests, change-record,
   TODO, and Git workflow.

## Engineering constraints

- A strategy input is a complete `submit/optimization.py` defining
  `build_optimization()`.
- No strategy registry, component assembly, algorithm category, fixed comparison
  role, or algorithm-specific report field belongs here.
- Every cell receives the same study budget and its own workspace.
- The exact materialized cell is checked before execution.
- New runs snapshot the complete driver, baseline, and strategy inputs.
- Resume executes the run-owned driver and does not read current study or strategy
  sources.
- Digests explain provenance; they do not lock recovery to the current checkout.
- Result interpretation is descriptive and never creates a ranking, significance
  claim, acceptance decision, or package default.
- Active runner code stays below the size and dependency limits asserted by tests.

## Execution authority

`baselines`, `plan`, and `inspect` do not execute task software.
`run` and `resume` may launch every simulator selected by the study. Apply
`user_doc/config_and_run.md` to the concrete budget, runtime, licenses, external
systems, and resource use before executing them. Development tests use fakes and
must not launch a real task.
