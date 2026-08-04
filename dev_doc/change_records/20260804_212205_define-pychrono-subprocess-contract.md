# 2026-08-04 21:22 - Define the PyChrono Subprocess Contract

## Context

- PyChrono uses a dedicated administrator-maintained Python/Conda interpreter and
  must remain an external simulator runtime rather than becoming yadof's host
  environment.
- The future Project Chrono adapter needed a stable process, artifact, environment,
  scratch, diagnostic, timeout, and failure boundary before adapter implementation
  or real mechanics validation.

## Change

- Added the canonical `yadof.pychrono-subprocess` v1 architecture contract covering
  explicit absolute interpreter resolution, argument-vector launch, controlled
  child environment, candidate-isolated scratch, versioned JSON request/result
  schemas, no-pickle NPZ evidence, size/hash/path validation, diagnostic limits,
  exit codes, failure taxonomy, cancellation/timeouts, process-tree cleanup, and
  local/fast/distributed publication equivalence.
- Updated the current architecture, adapter/project/test blueprints, architecture
  reading contract, and terminology to expose the new pre-adapter boundary while
  keeping Project Chrono unavailable as a packaged adapter.
- Added an executable fake-child conformance suite covering paths with spaces,
  environment contamination, success, bounded large stderr, malformed and invalid
  outputs, handled failure versus crash, descendant timeout cleanup, and concurrent
  scratch/evidence isolation without Miniforge or PyChrono.

## Rationale

- A file protocol keeps yadof and PyChrono in separate runtimes and prevents live
  objects, pickle, costs, environment activation, or partial evidence from crossing
  the trust boundary.
- Defining and executing the acceptance cases first gives the separate adapter task
  a precise target without prematurely adding or advertising `chrono_com.py`.

## Impact

- Developer architecture and generic tests now define the future adapter's stable
  contract. User adapter discovery and runtime behavior are unchanged.
- The focused installed-environment conformance run passed all 11 tests using a
  fake task-owned child and the `.venv` interpreter as the external executable.
- No yadof dependency or optional extra was added, and neither test process imports
  PyChrono.

## Follow-Up

- Implement the separately requested packaged Project Chrono adapter against this
  contract, then run the separately authorized real mechanics integration task.
