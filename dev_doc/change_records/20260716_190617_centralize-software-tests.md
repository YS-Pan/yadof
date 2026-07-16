# 2026-07-16 19:06 - Centralize Software-Specific Tests

## Context
- Two maintained pytest modules had been placed beside the HFSS tools under
  `project/tools/specific/hfss/`.
- The current test contract explicitly allowed software-specific tests beside
  implementation code, which conflicted with the intended single test location and
  made task-specific checks easier to mix into reusable tests.

## Change
- Made `project/test/` the only source location for maintained automated tests,
  including reusable simulator-, vendor-, adapter-, and tool-specific tests.
- Defined task-specific tests by their task-owned filenames/designs, objectives,
  variable shape, expected physical results, or dependency on active
  `project/job_template/` files.
- Required task-specific tests and all supporting resources to live under disposable
  root `temp/` in the current layout.
- Moved reusable HFSS tool/adapter coverage into `project/test/`, isolated active-task
  checks under `temp/`, and added a test-layout guard against future colocated pytest
  modules.

## Rationale
- Software-specific behavior is reusable across tasks and therefore belongs in the
  maintained suite, while task-owned assumptions must remain disposable and outside
  project source.
- A single test location makes pytest discovery and contributor expectations
  predictable and prevents tests from accumulating next to production modules.

## Impact
- Test placement and scope contracts changed in architecture, project/module
  blueprints, terminology, contributor test documentation, and user-facing pytest
  descriptions.
- `pytest -q` now includes the reusable HFSS parser and adapter contract tests without
  requiring HFSS or a task model.
