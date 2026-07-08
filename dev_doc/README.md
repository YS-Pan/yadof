# dev_doc README

`dev_doc/` stores the project documents that help an AI or human maintainer understand
what the project is, how it is shaped, and why it changed over time.

The documents in this folder are not all read with the same priority. Use the rules
below before changing code or documentation. The canonical entry point is
`dev_doc/README.md`.

## Reading Guide

When collecting project context, read these files in full:

- `../user_doc/README.md`, then follow its reading instructions for user-facing
  task setup context.
- every file in `architecture/`
- `terminology.md`
- every Markdown file in `toDo/`

Read `toDo/` in full during the first `dev_doc` pass even when the user's current
instruction appears unrelated to every pending item. These files describe work that
has not been done yet, and their purpose is to help the AI choose a technical route
that will not fight likely future goals.

Reading `dev_doc/` must include the `user_doc/README.md` pass above because framework
changes can affect how users and AI assistants prepare tasks. Reading `user_doc/`
alone must not trigger a `dev_doc/` pass; user-facing task setup docs are allowed to
stand on their own.

Read `blueprints/` in a targeted pass:

1. List all filenames under `blueprints/`, `blueprints/10_modules/`, and recursively under `blueprints/20_files/` when that folder exists.
2. Read `blueprints/00_project.md` when the work affects project-wide contracts, documentation rules, or multiple modules.
3. Read the module or file blueprint files that match the modules or concepts being changed.

Do not read `change_records/` by default. Use it only when you need the reason behind
a past change, when a current change conflicts with old intent, or when the user asks
for project history.

`obsolete/` is archival material. Do not read it by default; use it only when a newer
document explicitly points there, when investigating old plans, or when checking a
completed toDo handoff.

## Encoding And Mojibake

Markdown files in `dev_doc/` and `reference/` should be treated as UTF-8 text. Some
documents contain Chinese, and reading them with a local ANSI/default code page can
produce mojibake instead of readable text.

When using PowerShell, prefer explicit UTF-8 reads:

```powershell
Get-Content -Raw -Encoding UTF8 dev_doc/README.md
Get-Content -Raw -Encoding UTF8 reference/how_to_create_new_project.md
```

If text appears garbled, do not edit based on the garbled display. Re-read the file
with UTF-8 first, or use an editor that shows the file encoding. When writing these
documents from tools or scripts, preserve UTF-8 and avoid default-encoding commands
that depend on the current Windows code page.

## Document Roles

### `../user_doc/README.md`

`user_doc/` is the companion user-facing documentation home. It explains how users
and AI assistants should prepare task files, use `_com.py` adapters, write
`workflow.py` and `calc_cost.py`, edit run config, smoke-test, and launch
optimization.

Read it and follow its instructions whenever collecting `dev_doc` context. Do not
duplicate detailed user instructions here when they already belong under `user_doc/`.

### `architecture/`

Architecture documents describe the current system from several viewpoints. They
should explain how the project is organized now, what boundaries matter, and how
runtime/development flows work.

The architecture folder is now the highest-priority current-view contract for
system boundaries, persistence rules, runtime flows, recovery behavior, and
core invariants.

Use them to answer:

- Which modules exist and how do they communicate?
- Where does data flow at runtime?
- Which files own which responsibilities?
- What must be updated when a contract changes?

Write architecture docs as current-view maps. They can describe the current
implementation, but should emphasize stable relationships and invariants rather than
line-by-line code details.

Recommended file roles:

```text
00_architecture_index.md      overview and reading order
c4_context.md                 system boundary and external actors
c4_container.md               major modules and data flow
c4_component.md               important internal components
4plus1_logical_view.md        concepts, responsibilities, invariants
4plus1_process_view.md        runtime sequences and failure flows
4plus1_development_view.md    source layout, dependency rules, doc rules
4plus1_physical_view.md       filesystem and deployment layout
4plus1_scenarios.md           concrete use cases
```

Recommended section shape:

```text
# View Name
## Scope
## Diagram Or Structure
## Responsibilities
## Rules / Invariants
## Notes
```

### `blueprints/`

Blueprint documents are generative module descriptions. Their center thought is:

> A capable AI should be able to recreate a file or module with the same function
> from this blueprint, even if the current source file is not visible.

Therefore blueprint files should not merely summarize the current source code. They
should explain intent, expected behavior, I/O shapes, non-obvious techniques, and
mutability boundaries.

Use blueprint files to answer:

- What should this module do?
- What shape should its inputs and outputs have?
- Which implementation tricks are easy to lose?
- Which parts are intended to change often?
- Which historical implementation ideas or reference ancestors still matter for
  this module?

Recommended structure:

```text
# Module blueprint: module_name

## Intent
- Why this module exists.

## Functionalities
- What this module must provide.

## I/O Format
- Public data shapes, files, APIs, and return values.

## Non-Obvious Techniques
- Important implementation ideas that should survive rewrites.

## Mutability Profile
- Which parts may change often and which contracts should stay stable.
```

Keep blueprint files module-level until the project stabilizes. Avoid file-level blueprint
documents unless a single file has a complex contract that cannot be captured by the
module blueprint. File-level blueprints under `blueprints/20_files/` mirror the
source path as folders, such as `blueprints/20_files/project/surrogate/runtime.py.md`;
do not encode a path into one filename such as `project_surrogate_runtime.py.md`.

Historical reference ancestry belongs in the relevant project or module blueprint
as natural-language context. Avoid maintaining a separate path map to old reference
trees unless those paths are present and actively useful in the current workspace.

### `toDo/`

`toDo/` contains time-named Markdown files for future work that has not been done
yet. A file may describe one task or a cluster of related tasks. It is part of the
default context-reading set because pending work can affect today's implementation
choice even when today's request is not directly about that future task.

Filename format:

```text
YYYYMMDD_HHMMSS_short-description.md
```

Examples:

```text
20260519_193400_nsga3-surrogate-handoff.md
20260602_143000_surrogate-cache-policy.md
```

Recommended toDo structure:

```text
# Short Future Task Title

## Context
- Why this future work matters.

## Goal
- What should be true when the task is complete.

## Guidance
- Technical direction, constraints, and relevant files.

## Completion Rule
- How to recognize completion and whether any follow-up should remain.
```

When the user asks the AI to execute a task described in `toDo/`, complete the code
and documentation work first, then move the corresponding Markdown file to
`obsolete/`. If only part of the future work is completed, update the remaining
toDo file or split out a new time-named toDo file before archiving the completed one.

### `terminology.md`

Terminology defines project-specific words whose meanings are not obvious from common
software usage.

Use it to answer:

- What exactly does this project mean by a name?
- Is a term durable data, derived data, runtime state, or a workflow concept?

Recommended structure:

```text
# Project-Specific Terminology

Only terms that need project context are listed here.

| Term | Meaning In This Project |
|---|---|
| `term` | Definition and boundary notes. |
```

Update terminology when a change reveals a mistaken concept, introduces a new
non-obvious name, or clarifies a term that could otherwise be misused.

### `change_records/`

`change_records/` contains time-named change records. It is similar to Architecture
Decision Records, but broader: each record explains a concrete change, why it was
made, what was affected, and what remains open.

The folder is not part of the default context-reading set. Read it only for historical
reasoning.

Filename format:

```text
YYYYMMDD_HHMMSS_short-description.md
```

Examples:

```text
20260518_075810_dev-doc-governance.md
20260602_143000-surrogate-cache-policy.md
```

Recommended record structure:

```text
# YYYY-MM-DD HH:MM - Short Title

## Context
- What situation or problem triggered the change.

## Change
- What was changed.

## Rationale
- Why this approach was chosen.

## Impact
- Which modules, docs, tests, or workflows are affected.

## Follow-Up
- Optional remaining work, risks, or things to revisit.
```

### `obsolete/`

`obsolete/` stores old plans, old diagnostics, completed toDo handoffs, and drafts
that are no longer active design input.

Use it to answer:

- Why did a past plan exist?
- What was completed and archived?
- Is a current question explicitly pointing to an old handoff?

Do not use `obsolete/` as a current fact source unless a current document explicitly
brings a piece of information forward.

## Maintenance Rules

After each code change:

1. Update relevant files in `architecture/` when module responsibilities, public APIs,
   data persistence, execution topology, or development workflow changes.
2. Update relevant files in `blueprints/` when module intent, I/O, non-obvious techniques,
   or mutability boundaries change.
3. Add one file under `change_records/` describing what changed and why.
4. Update `terminology.md` if the change corrects a mistaken concept or introduces a
   name that is not intuitive.
5. If the change completes a task described in `toDo/`, move that toDo file to
   `obsolete/` after updating the current docs and adding the change record.

For documentation-only changes, still update architecture/blueprints when the documentation
system itself changes, and add a change record.

When adding new future work, put it under `toDo/` rather than `change_records/`.
`change_records/` explains completed changes; `toDo/` describes pending work that
should influence future technical choices.
