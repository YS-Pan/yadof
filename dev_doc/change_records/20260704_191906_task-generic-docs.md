# 2026-07-04 19:19 - Task-Generic Documentation Pass

## Context

- Recent task-template changes left several docs describing a specific simulator
  model, rawData names, objective names, and objective counts as if they were
  framework defaults.
- Those details change from one optimization campaign to the next and should live
  in the active `project/job_template/` files, not in generic docs.

## Change

- Reworded dev docs so `workflow.py`, adapter files, rawData items, and objective
  tuples are described as task-owned, replaceable pieces.
- Removed current-task wording from architecture, module blueprints, terminology,
  and `project/README.md`.
- Updated user-facing examples to use neutral placeholders for simulator design
  names, expressions, rawData names, frequency/angle selections, and axis ranges.
- Kept historical `change_records/` and `obsolete/` notes as history rather than
  rewriting them.

## Rationale

- Documentation should teach the contract: normalized variables become rawData,
  and task-owned `calc_cost.py` turns rawData into costs.
- Documentation should not freeze a particular optimization model, target, or
  objective count into the framework description.

## Impact

- Future optimization tasks can replace `job_template` files without making the
  docs look stale or contradictory.
- New adapter docs under `user_doc/com_lib/` can stay focused on adapter APIs
  while leaving model-specific expressions and targets to each task.

## Follow-Up

- Continue fixing any remaining inconsistencies opportunistically when touching
  nearby docs.
