# 2026-07-15 20:42 - Config Layout Audit And HFSS Test Cleanup

## Context
- The earlier config-boundary refactor moved the project to a layered
  `config/` package, so its cross-module imports and current documentation need to
  stay independent of a concrete simulator extension.
- `project/com_lib/test_hfss_com.py` was added with that refactor, but default
  pytest collection is deliberately limited to `project/test/` and no code or test
  path referenced the file.

## Change
- Added a two-day automatic follow-up toDo for incidental config-layout checks and
  fixes.
- Corrected the terminology entries to describe `config/key.py`, `config/all.py`,
  and the copied config package.
- Made `evaluate_manager.config` refresh active extensions through the public
  `config.specific` boundary instead of importing `specific.hfss` directly.
- Added a generic unit test for extension refresh selection and ordering.
- Removed the uncollected, HFSS-specific adapter test file.

## Rationale
- Generic configuration code must not embed a dependency on the active simulator.
  The extension package already declares which specific modules are active.
- The removed test did not participate in the default framework suite and its
  metadata contract is covered by the generic rawData contract tests.

## Impact
- Configuration refresh remains compatible with the active HFSS extension while
  allowing additional extensions without an evaluator-code change.
- Future incidental config work has an explicit, short-lived follow-up checklist.
- The default test surface remains software-agnostic.
