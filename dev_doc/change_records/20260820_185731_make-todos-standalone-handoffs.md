# 2026-08-20 18:57 - Make ToDos Standalone Handoffs

## Context

- Fresh-context reviews of several generated toDos repeatedly supplied plausible
  but incorrect missing premises. Explicit HDD constraints were treated as
  speculative complexity, initial queue/segment values were read as product
  reliability cliffs, a deliberate clean-baseline surrogate change was judged as
  an accidental absence of a performance gate, and workspace-owned optimization
  composition was treated as an arbitrary package-design preference.
- The existing toDo outline asked only why work mattered, what the goal was, and
  what guidance to follow. It did not require the active document to distinguish
  verified facts, explicit user decisions, recommendations, assumptions, unresolved
  questions, or the semantics of important numerical values and promises.

## Change

- Added a standalone-handoff contract for every new or substantially revised toDo.
- Required essential task-specific context to be embedded in the active document
  rather than living only in chats, change records, benchmarks, or adjacent toDos.
- Required clear separation of current facts, user requirements and decisions,
  maintainer proposals, assumptions, and open questions when that status affects
  implementation.
- Required material operating scale and constraints, scope, dependencies,
  compatibility policy, accepted tradeoffs, and numerical/reliability semantics to
  be stated proportionally.
- Added a short context-completeness review and updated the recommended outline,
  development view, and documentation blueprint.

## Rationale

- A future maintainer should be able to understand why a non-obvious design exists
  without inheriting the original session. Making decision status and claim
  semantics explicit prevents the reader from silently converting a default into a
  guarantee or an explicit product requirement into an accidental implementation
  choice.
- The contract remains outcome-based and proportional. It does not require a chat
  transcript, exhaustive design defense, or one rigid heading template, so it does
  not make small future tasks unnecessarily verbose.

## Impact

- Future and substantially revised manual or automatic toDos must satisfy the new
  standalone-context check.
- Existing active toDos are not automatically rewritten by this documentation-only
  governance change.
- No package runtime, installed command, user task-authoring workflow, or
  administrator behavior changes.

## Follow-Up

- None.
