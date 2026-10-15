# 2026-10-15 15:11 - Prepare the complete GUI contribution branch

## Context

The user requested a branch in the original GitHub repository containing the
complete yadof source with its GUI enhancements. The working installation also
contained machine-specific configuration and mutable task/runtime directories.
Its checkout launcher pinned one absolute development interpreter, which would
not be usable by other contributors.

## Change

- Prepared `codex/gui-workspace-launcher` in a separate source checkout, retaining
  the original repository and its two existing GUI commits as ancestry. Included
  the GUI, separate directory/init/reset controls, history-reset implementation,
  progress labels, failure inspection, drain controls, distributed solver-log
  collection, installed `.pyw` packaging, and their tests and documentation.
- Replaced the checkout launcher's absolute interpreter with relative environment
  selection: checkout `.venv`, parent `.venv`, then the current interpreter. The
  selected environment must already contain the installed distribution. Explicit
  workspace arguments, adjacent-workspace selection, and child exit status are
  preserved. The installed Scripts launcher continues to use its own environment.
- Updated active architecture, blueprints and user guidance for portable checkout
  launching. Historical records retain the earlier machine-specific decisions.
- Excluded local Python environments, generated wheels, caches, optimization
  workspaces, local editor/cluster configuration, task-specific HFSS edits and the
  unrelated default-random-seed change. The original working checkout and runtime
  installation remain unchanged.

## Validation

- Built and installed a regular wheel in a disposable acceptance environment
  below ignored `temp/`, with source injection removed.
- Focused GUI/history/packaging/distributed-execution checks: **74 passed**.
- The initial full-suite collection exposed missing optional GP dependencies in
  the temporary environment. Provisioned GP/qNEHVI packages at the existing
  runtime's versions; no implementation change was needed for that setup issue.
- Full installed-wheel regression: **645 passed** in 160.41 seconds, with two
  existing scikit-learn GP convergence warnings.
- Only a new contribution branch is published; the original default branch is
  not modified.
