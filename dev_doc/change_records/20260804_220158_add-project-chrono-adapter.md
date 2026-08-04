# 2026-08-04 22:01 - Add the Project Chrono Adapter

## Context

- The version-1 PyChrono subprocess contract was already canonical, but Project
  Chrono was not yet exposed as a packaged adapter resource.
- PyChrono must remain in a separately provisioned interpreter: yadof must not
  import it, and the child runtime must not require yadof or Conda activation.

## Changes

- Added self-contained `src/yadof/_resources/adapters/chrono_com.py` with explicit
  interpreter resolution, bounded JSON request/result exchange, unique scratch,
  controlled child environment, process-tree timeout/cancellation, bounded
  diagnostics, path/hash/NPZ validation, and fast or file-backed publication.
- Added `worker_main(simulate)` for task-owned `chrono_worker.py`; it validates the
  request before the task callback can import PyChrono and publishes the manifest
  only after direct rawData passes the trust boundary.
- Made `chrono_com.py` discoverable and copyable through the existing resource/CLI
  workflow, with wheel membership covered by package tests.
- Replaced the test-only parent protocol implementation with tests that copy and
  execute the packaged adapter itself. The fake external runtime covers paths with
  spaces, missing configuration, clean environment, malformed/version-mismatched
  or escaping evidence, nonzero exits, bounded stderr, timeout, cancellation,
  Windows descendant cleanup, and concurrent isolated candidates.
- Added user setup and worker templates, a copyable task-authoring prompt, updated
  architecture/terminology/module and file blueprints, and archived the completed
  manual toDo.

## Decisions

- Mechanical bodies, loads, contact, solver selection, measurements, and costs stay
  task-owned. The package adapter contains only invariant launch and evidence
  mechanics.
- The child imports the copied adapter only for its dependency-light protocol
  helper. `pychrono` is imported inside the task callback after validation; neither
  dependency metadata nor adapter source imports it.
- Windows termination records descendants before `taskkill` and uses the existing
  core `psutil` dependency as a parent-side fallback. The import is lazy so the
  external PyChrono environment does not require psutil merely to run a worker.
- Real Project Chrono mechanics remain outside the default suite and require the
  separate explicitly authorized integration task.

## Verification

- Built `dist/yadof-0.2.0-py3-none-any.whl` and force-reinstalled it into the
  sibling `.venv` without editable or `PYTHONPATH` shortcuts.
- Isolated import resolved under `.venv/Lib/site-packages`; the installed resource
  list and installed user docs contained `chrono_com.py` and `chrono_com.md`.
- Focused adapter, CLI, package-artifact, clean-install, and documentation tests:
  `27 passed`.
- Complete installed-package suite: `217 passed`.
- `git diff --check` reported no whitespace errors.

## Automatic toDo check

- No packagify-path or `agent_doc`/`user_doc` naming inconsistency was encountered
  in the bounded in-scope review.
- The persistent redundancy check matched the now-duplicated reference parent
  launcher in `tests/test_pychrono_subprocess_contract.py`. It was removed in favor
  of the packaged adapter public surface, deleting 538 lines while adding 246 lines
  of adapter-focused worker/acceptance coverage (net 292 fewer test lines).
