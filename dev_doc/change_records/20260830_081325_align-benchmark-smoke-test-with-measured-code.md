# 2026-08-30 08:13 - Align Benchmark Smoke Tests With Measured Code

## Context

- A recent PCA/SVD benchmark used a separate one-point-per-case canary workspace
  before launching the full measured execution.
- That workflow proved that a reduced variant could run, but it could not by
  itself prove that the measured benchmark's complete cell/arm matrix, strategy
  modules, task code, or postprocessors would run unchanged.

## Change

- Added normative benchmark user guidance defining `benchmark smoke test` as a
  fresh, separate execution with only a smaller explicit evaluation budget.
- Required the smoke workspace to retain the measured workflow's code, baselines,
  strategies, task inputs, policies, dependencies, complete cell/arm matrix, and
  postprocessors.
- Documented plan comparison, validity gates, non-evidence status, and the absence
  of a separate benchmark smoke-test CLI command.
- Added the term to the project glossary and retired `canary` as the current name
  in benchmark workflow guidance.

## Rationale

The smoke test should expose integration failures in the same execution path that
will produce measured evidence. Reducing evaluation count controls cost without
creating a second implementation whose success can diverge from the real run.

## Impact

- `yadof-benchmark/user_doc/README.md`, `workspace.md`, `execution.md`, and
  `api.md` now describe the smoke-test contract.
- `dev_doc/terminology.md` distinguishes the benchmark smoke test from the core
  `yadof smoke-test` command.
- No package code, CLI behavior, or existing benchmark evidence was changed.

## Follow-Up

- Existing workspaces or historical notes that use `canary` are not rewritten;
  future benchmark authoring should use the smoke-test contract.
