# 2026-08-14 16:28 - Refine Recording ToDo And Live Task Contract

## Context

- The loss-tolerant recording toDo had been extended for HDDs with custom candidate
  frames, a `.yadseg` container, byte/count/time flush thresholds, a supervised
  recorder, optional SQLite, and broad recovery machinery.
- An independent review correctly identified several unnecessary mechanisms, but
  did not initially have the earlier discussion establishing rotational-disk
  performance as an explicit requirement.
- The user clarified the intended loss bound, live task-edit behavior, workspace
  concurrency, background-thread requirement, and foreseeable campaign scale.

## Change

- Preserved the complete previous recording toDo under `dev_doc/obsolete/` and
  replaced the active document with a standalone revised specification.
- Kept the HDD-relevant single writer, bounded asynchronous queue, sequential
  immutable micro-batching, no per-candidate flush, and no historical rewrite.
- Selected a 16-candidate segment target and a 32-candidate total unpublished
  budget that includes assembling, queued, encoding, temporary, and in-flight
  states, with parallel byte bounds.
- Replaced the custom segment protocol with standard immutable ZIP segments and
  deferred SQLite, multiple compression workers, automatic writer restart, and
  residence-time flushing.
- Required one active campaign per workspace, with concurrent optimizations using
  different workspaces and destructive history clear refusing an active campaign.
- Made generation-boundary task mutability explicit across the developer
  architecture, blueprints, terminology, and user workflow documents.

## Rationale

- Rotational media justifies amortizing file creation and seeks through one serial
  micro-batch writer, but it does not require a new binary protocol. Standard ZIP
  CRC plus a small bounded segment gives sufficient fault isolation when losing a
  small batch is acceptable.
- The true loss bound must include every unpublished state, not only the segment
  currently being assembled.
- Yadof's flexibility includes correcting cost, parameters, configuration, and
  execution code during a campaign. Such a correction intentionally may define a
  different optimization problem. Source fingerprints are therefore cache
  invalidation/provenance inputs, not scientific-compatibility gates.
- The expected sub-100,000-candidate scale does not justify SQLite before measured
  cold-start or query evidence demonstrates a need.

## Impact

- No package runtime code or current history format changed; the active toDo
  specifies future work.
- Maintainers now have a project-wide contract that generation boundaries are the
  coherent task-change point and that yadof trusts the user's scientific decision
  about retaining old evidence.
- Users are told to run only one campaign per workspace, use separate workspaces for
  concurrent optimization, and use finite generation chunks for a strictly
  controlled edit with the current command surface.
- The future implementation has a smaller, testable storage design with explicit
  failure and scale limits.

## Follow-Up

- Implement the active recording toDo only when explicitly requested.
- During implementation, benchmark the selected ZIP segment byte bounds and the
  cold-start behavior near 100,000 synthetic candidates before adding an index.
