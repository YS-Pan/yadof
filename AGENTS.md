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
  `benchmark_automation/dev_doc/README.md` and follow its targeted links.
- Run benchmark commands from this repository root with a Python environment that
  contains the matching installed yadof distribution.
- The external study request chooses the run directory. Preserve run directories
  by default and diagnose or resume one explicit run at a time.
- `plan` and `inspect` are read-only. `run` and `resume` may invoke the task
  declared by a baseline, so apply the installed user guide's execution and cost
  policy before using them.
- Baseline templates may be edited for future runs; preserve existing run-local
  driver and input snapshots together with runtime evidence.
