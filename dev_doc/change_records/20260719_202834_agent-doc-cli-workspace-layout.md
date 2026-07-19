# 2026-07-19 20:28 - Agent Documentation And Package Layout

## Context

Pip-installed yadof documentation existed as package resources, but the CLI exposed
only each tree's README. An AI agent could not list or open linked documents through
the supported interface, and the `user_doc` name did not reflect the documentation's
actual AI-agent audience. CLI and workspace foundation modules also remained as
top-level files while their responsibilities had grown into distinct groups.

## Change

- Renamed root `user_doc/` to `agent_doc/` and rewrote its README as the installed
  agent entry and operating contract.
- Added `yadof docs list`, `show`, and `bundle` over safe audience-relative package
  resources; removed the old `docs user|dev` entry-only command shape.
- Moved command routing under `yadof.cli` and workspace context, marker,
  initialization, and checking under `yadof.workspace` without old-path aliases.
- Added a short English prompt starter near the top of the project README.
- Updated package metadata, architecture, blueprints, terminology, imports, and
  artifact tests for the new current layout.

## Rationale

Markdown files remain the single editable source of truth, while the CLI gives an
agent a version-matched, repository-independent way to discover and read them. The
new audience name and module directories make the intended boundaries explicit and
avoid asking an agent to locate or edit site-packages directly.

## Impact

The current documentation audience is `agent` rather than `user`. Current workspace
module imports use `yadof.workspace.init`, `yadof.workspace.check`, and
`yadof.workspace.manifest`; current CLI imports use the `yadof.cli` package. Wheels
and sdists contain `agent_doc` and no longer contain the former documentation or
top-level module paths.

## Follow-Up

Task-specific reference workspaces remain source-only. Additional software-neutral
installed templates can be added later without changing the documentation access
contract.
