# 2026-08-30 13:29 - Add cross-session context documents

## Context

Ongoing algorithm updates and validation produce experimental information that
must remain available across agent sessions. The developer documentation had no
appropriate home for this material: `toDo/` means pending work,
`change_records/` means completed-change history, architecture and blueprints are
current system contracts, and `obsolete/` is not read by default.

## Change

- Added `dev_doc/context/` as the home for time-named Markdown documents containing
  cross-session experimental evidence and working context.
- Added `dev_doc/skill/context.md` with filename-first discovery, targeted full-read,
  naming, scope, and explicit user-triggered expiry rules.
- Routed the new contract through the developer README and updated the developer
  architecture, documentation blueprints, terminology, and obsolete archive
  description.

## Rationale

Filename-only discovery gives every agent awareness of available context at low
context cost. A descriptive timestamped filename lets an agent open only documents
likely to answer the current task's information need. Separating expiry review from
routine work prevents useful experimental evidence from being discarded merely
because time passed or because an unrelated task listed it.

## Impact

This is a documentation-system content change only. It changes no package code,
documentation resource mapping, CLI routing, generated documentation, task-authoring
behavior, runtime state, or experiment artifact. Future context documents remain
read-only inputs unless a user's task separately authorizes work.

## Validation

- Verified the new and changed Markdown paths, links, naming rules, and UTF-8 text.
- Confirmed the existing documentation source mapping already includes the root
  `dev_doc/` tree, so no packaging or discovery mechanism changed.
- Reviewed the final diff and whitespace checks under the documentation-only
  validation exception; no wheel build, reinstall, import-origin check, pytest run,
  simulator launch, or benchmark was required.
