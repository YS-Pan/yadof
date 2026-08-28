# 2026-08-28 20:28 - Separate Administrator Docs And Condense Architecture

## Context

- Administrator procedures and executable tools shared `admin_tool/` without a
  clear documentation boundary: HTCondor documents used a one-off `htcondor_doc`
  directory while PyChrono's complete procedure lived beside its scripts.
- Every full developer context pass reads every root architecture file. That set
  had grown to 10 files and about 1,996 lines, including detailed protocol schemas,
  experiment gates, algorithm steps, CLI/UI behavior, administrator settings, test
  matrices, and historical implementation status.

## Change

- Added `admin_tool/admin_doc/` as the canonical source-checkout administrator
  documentation home, with topic directories for HTCondor and PyChrono.
- Moved `htcondor_doc/` intact to `admin_doc/htcondor/` and updated only paths,
  links, and navigation needed by the move. Moved the PyChrono runtime procedure to
  `admin_doc/pychrono/`; executable scripts remain under `pychrono_runtime/` with a
  short link to the canonical procedure.
- Rewrote the nine C4/4+1 root architecture views around stable system boundaries,
  ownership, data flow, persistence, recovery, deployment topology, and core
  invariants. The mandatory architecture set is now about 709 lines.
- Removed the standalone detailed PyChrono subprocess protocol page. High-level
  external-runtime rules remain in architecture; task use remains in user docs;
  implementation details remain in the adapter blueprint, source, and executable
  conformance tests.
- Updated the architecture contract, developer entry point, documentation and
  project blueprints, adapter/Condor references, and terminology to reflect the new
  boundaries.

## Rationale

- Administrator documentation is rarely part of normal agent context and can retain
  operational and historical detail without burdening package development tasks.
- Root architecture is mandatory reading and should provide a compact current-view
  system map. Detailed implementation, operation, validation, experiment, and
  history material already has selectively read owners.
- Removing duplication reduces context cost and stale cross-document claims while
  preserving the contracts that affect multiple modules or durable evidence.

## Impact

- No package code, public API, runtime behavior, administrator command, or
  HTCondor/PyChrono policy changed.
- No HTCondor administrator document was deleted or substantively shortened.
- Administrator links now resolve through `admin_tool/admin_doc/`; these resources
  remain outside the installed documentation audiences and wheel/sdist behavior.
- Full developer context passes read roughly 1,287 fewer architecture lines while
  retaining links to selectively read user, administrator, blueprint, test, and
  historical material.

## Follow-Up

- Future architecture edits should keep exact schemas, defaults, algorithms,
  procedures, test matrices, experiment results, and dated status in their
  audience- or component-specific documentation rather than expanding the mandatory
  root architecture set.
