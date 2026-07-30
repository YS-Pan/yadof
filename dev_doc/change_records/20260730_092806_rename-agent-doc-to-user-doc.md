# 2026-07-30 09:28 - Rename Agent Documentation To User Documentation

## Context

- `agent_doc` named the documentation after its usual literal reader, which made it
  easy to confuse the user's task-authoring agent with a framework-development
  agent.
- The documents belong to the user role and describe only user-owned workspace
  preparation, validation, execution, and inspection. Users normally direct an AI
  coding agent to read and execute the detailed instructions rather than following
  every command personally.
- A previous package-layout change intentionally renamed `user_doc` to `agent_doc`;
  the role boundary is now more important than naming the execution mechanism.

## Change

- Renamed the authoritative source tree from `agent_doc/` to `user_doc/` and the
  matching developer contract from `skill/agent_doc.md` to `skill/user_doc.md`.
- Renamed the installed documentation audience from `agent` to `user` across
  resource APIs, `yadof docs list|show|bundle`, prompt starters, package mapping,
  wheel/sdist paths, and tests. No old-name compatibility alias remains.
- Rewrote the user-document entry and current developer contracts to state that the
  primary reader/executor is an AI coding agent acting under a human user's
  direction, while the human supplies goals, reviews results, and authorizes real
  execution.
- The recurring redundancy auto-toDo check found that the CLI separately hard-coded
  the same audience tuple as `DocumentationKind`; the CLI now derives its choices
  from that type instead of maintaining a second value list.
- Added a seven-day automatic follow-up for rename inconsistencies. Its first
  bounded check replaced artifact tests that named the removed directory only in
  negative assertions with stronger exact-current-document-root assertions.
- Updated current architecture, blueprints, terminology, adapter references, and
  package documentation to use the role-based name.

## Rationale

- `user_doc` answers whose workflow, files, and authority the guidance belongs to;
  the text can separately and unambiguously answer who usually reads it.
- Keeping user task guidance separate from `dev_doc` prevents a user-directed agent
  from treating framework source maintenance as part of normal task authoring.
- A clean audience rename avoids preserving the same ambiguity through an `agent`
  alias.

## Impact

- The supported installed commands are now `yadof docs list user`,
  `yadof docs show user ...`, and `yadof docs bundle user`.
- Wheels contain `yadof/_resources/docs/user_doc/` and sdists contain
  `user_doc/`; neither artifact contains `agent_doc/`.
- Existing prompts that name the old `agent` audience must use `user`.
- Runtime optimization, workspace, adapter, and administrator behavior is
  unchanged.

## Follow-Up

- A seven-day automatic toDo remains active to correct rename inconsistencies
  encountered during normal in-scope work. Historical change records remain
  append-only and are not current-name inconsistencies.
