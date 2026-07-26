# 2026-07-25 15:38 - Exclude Top-Level AEDT Runtime Artifacts

## Context

- Opening an AEDT project directly below a workspace `job_template/` creates
  `.aedtresults` and `.aedt.lock` items.
- Job preparation previously attempted to copy those live artifacts. Locked
  semaphore files could make every candidate fail before backend submission.

## Change

- Job preparation now excludes direct `job_template/` children whose names end
  case-insensitively with `.aedtresults` or `.aedt.lock`.
- The suffix rule is deliberately limited to direct children; recursively copied
  task directories retain same-suffixed nested files and directories.
- Generic tests and current architecture, blueprints, and agent task-authoring
  documentation describe and verify the boundary.

## Rationale

- AEDT results and lock items beside the source project are runtime artifacts, not
  portable task inputs.
- Limiting the rule to the task-template root implements the requested behavior
  without guessing whether similarly named nested assets are intentional.

## Impact

- Local and distributed prepared jobs no longer include top-level AEDT results or
  lock artifacts.
- Opening a task project on the submit host cannot make job preparation copy its
  live result semaphores.

## Follow-Up

- Other simulator-specific transient artifacts remain ordinary task payload unless
  an explicit contract is added for them.
