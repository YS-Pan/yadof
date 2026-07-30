# 2026-07-30 08:56 - Make Automatic ToDo Trigger Checks Explicit

## Context

- The recurring code-redundancy automatic toDo had never been observed to trigger,
  even across later source changes.
- The trigger contract said to act when normal work "naturally exposes" a match but
  did not require a concrete pre-completion check of already in-scope evidence.
- The generic completion text also said to archive a fully handled automatic toDo,
  while the redundancy document says one completed occurrence must leave the
  recurring handoff active.
- `manual` under an automatic toDo's obsolete rule was easy to confuse with the
  separate manual-trigger classification.

## Change

- Added a mandatory, bounded automatic-trigger checkpoint after normal scope and
  findings are known: compare active automatic toDos with already encountered
  files, direct evidence, and the current diff before reporting completion.
- Defined that an objective in-scope match triggers the toDo, a risky/out-of-scope
  match is reported but left pending, and no match creates neither extra work nor a
  reporting requirement.
- Clarified that focused proof for an encountered candidate is allowed but an
  unrelated repository-wide candidate hunt is not.
- Distinguished one-shot completion from recurring occurrence completion so a
  recurring automatic toDo remains active after each handled match.
- Replaced the overloaded `manual` obsolete-rule value on current automatic toDos
  with `persistent`, which affects expiry without changing their automatic trigger.
- Updated the developer entry point, development view, project/documentation
  blueprints, terminology, and the recurring redundancy handoff.

## Rationale

- "Automatic" must make consideration deterministic even though execution remains
  conditional; relying on accidental observation made a valid toDo easy to skip
  indefinitely.
- Restricting the checkpoint to existing scope preserves the original protection
  against unrequested cleanup campaigns.
- Separate trigger, expiry, and document-level completion concepts remove the
  ambiguity that could make a recurring handoff appear manual or already complete.

## Impact

- Future framework maintenance explicitly evaluates active automatic toDos before
  completion and can therefore show observable triggered occurrences.
- No runtime API, package behavior, task-authoring workflow, or administrator
  contract changes.

## Follow-Up

- The code-redundancy and packagify automatic toDos remain active for future
  matching occurrences.
