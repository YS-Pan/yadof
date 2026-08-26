# Repository agent instructions

These instructions apply to the yadof source checkout. Keep the first read small
and follow the documentation entry point for the part of the repository being
changed.

## Package and workspace tasks

- Start with `python -m yadof docs show user README.md` and follow its request-type
  routing.
- Before changing yadof package code, tests, build configuration, or packaged
  documentation, read `dev_doc/README.md` and `user_doc/README.md` and follow their
  targeted-reading and installed-package acceptance rules.
- Edit framework source only under `src/yadof/`; never edit an installed copy in
  site-packages. Keep generated scratch data below the ignored root `temp/`.

## Source-checkout benchmark tasks

- For any task below `benchmark_automation/`, read
  `benchmark_automation/AGENTS.md` first, then only the benchmark documentation or
  evidence it routes to.
- Run benchmark commands from this repository root with a Python environment that
  contains the matching installed yadof distribution.
- The configured default writes each run directly to `temp/<run-id>/`; do not add
  another task-specific container layer. If `--runs-dir` overrides that root, reuse
  the same path for every command addressing the run. Do not recursively scan run
  trees: start with bounded `plan`, `preflight`, or `inspect` output and expand one
  artifact or failed cell at a time.
- Benchmark execution, resume, and collection remain subject to the cost/risk
  policy in `benchmark_automation/README.md`. Preserve frozen inputs and existing
  runtime evidence.
