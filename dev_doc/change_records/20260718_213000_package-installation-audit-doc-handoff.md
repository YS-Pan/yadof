# 2026-07-18 21:30 - Package Installation Audit And Documentation Handoff

## Context

- The package/workspace conversion needed a final layout, artifact, installed-
  behavior, test, and documentation audit before the old source namespace could be
  removed.

## Change

- Copied the mature tests into the standard `tests/` directory, adapted them to
  installed package APIs, removed pytest path injection, and deleted the old source
  namespace and root entry points after their package copies were verified.
- Created the explicit `workspaces/hfss-newchoke` example by copying the existing
  task/model/config/history inputs before adapting package imports and workspace
  metadata.
- Updated root/user/developer documentation, architecture views, module/file
  blueprints, terminology, test guidance, and packaged documentation resources to
  the sole installed-package/workspace workflow.
- Extended wheel/sdist and clean-install tests for package data exclusions,
  repository-external operation, read-only installed files, generic tasks, two
  workspaces, CLI tools, run/resume, failures, surrogate state, and mocked
  distributed execution.

## Rationale

- Removing the duplicate namespace makes imports and writable ownership
  deterministic. Artifact-first verification proves the product rather than the
  source checkout.

## Impact

- Framework code and immutable resources live under `src/yadof`; task inputs and
  runtime state live in explicit workspaces.
- Installation, initialization, checking, smoke testing, running/resuming, and
  inspection are documented and exercised through the `yadof` CLI.

## Verification

- `python -m build --no-isolation` produced `yadof-0.1.0.tar.gz` and
  `yadof-0.1.0-py3-none-any.whl`; archive assertions verified required code,
  templates, adapters, worker bootstrap, and documentation while excluding active
  workspaces, tests, simulator models, caches, and the removed source namespace.
- An interpreter importing `yadof` from the installed wheel ran default pytest with
  no repository `PYTHONPATH`: **130 passed**.
- The artifact test created clean repository-external environments, made installed
  package files read-only, and exercised help/version/docs, init/check, generic
  smoke, local failure/timeout, run/resume, cost/time views, history clear, package
  immutability, and source immutability.
