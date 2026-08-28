# Module blueprint: documentation

## Sources and distribution

Root `dev_doc/` and `user_doc/` are authoritative editable sources. Build mapping
copies both trees into read-only wheel resources so installed documentation matches
installed code. `yadof docs list/show/bundle` addresses audience-relative paths,
rejects traversal, and never requires callers to locate site-packages.
The `user` audience is named for the role whose workflow it serves; its documents
are written primarily for an AI coding agent acting under a human user's direction.
Those documents own the portable execution-risk policy: agents may run understood,
bounded low-cost workflows autonomously, while long or consequential runs require
explicit user authorization and detached-run handling.

The integrated cost and surrogate viewers retain relatively independent developer
trees at `src/yadof/tools/cost_viewer/dev_doc/` and
`src/yadof/tools/surrogate_viewer/dev_doc/`. Those trees ship with their tool
packages and own viewer-specific architecture, blueprints, and terminology; the
root developer README links to them instead of duplicating those contracts.
The source-checkout benchmark likewise owns nested current-view architecture,
blueprints, terminology, and operator routing. Repository-wide pending-work and
history lifecycle remains centralized here: nested developer trees do not add
their own toDo, obsolete, or change-record contracts/directories.

Administrator documentation is a separate source-checkout tree at
`admin_tool/admin_doc/`, organized by administered system. Executable administrator
tools remain in sibling directories under `admin_tool/` and link to the canonical
procedures instead of duplicating them. Neither administrator documentation nor
tools are installed yadof documentation audiences.

## Developer document roles

- `README.md`: entry point for mandatory reading order, environment, validation,
  cross-module maintenance, and links to detailed contracts.
- `development_environment.md`: dated machine/tool/package reproducibility snapshot
  that is explicitly separate from declared compatibility requirements.
- `skill/`: module-specific contracts for user documentation, architecture,
  blueprints, toDo/obsolete handling, terminology, and change records.
- `architecture/`: current system relationships and invariants.
- `blueprints/10_modules/`: current module responsibility, dependencies, I/O, and
  non-obvious constraints.
- `blueprints/20_files/`: file lineage for high-risk/specialized implementation.
- `terminology.md`: project-specific terms whose meaning is not obvious.
- `change_records/`: append-only time-named decision/implementation explanations.
- `toDo/`: unresolved work recorded as standalone handoffs. Each active document
  embeds the task-specific problem, intent, evidence, material operating envelope,
  decision status, scope, and completion meaning needed by a maintainer who lacks
  the originating conversation; references provide supplemental provenance rather
  than hidden requirements. Root entries require explicit request, while active
  `auto/` entries receive a bounded match check against already in-scope evidence
  before normal work is reported complete.
- `obsolete/`: historical completed/cancelled toDos, not current guidance.

`user_doc/example_prompts/` is an expandable collection with one Markdown file per
copyable prompt. Its index may link placeholders whose prompt bodies remain empty
until examples are supplied.

`user_doc/agent_environment_permissions.md` is an optional, standalone host-agent
troubleshooting reference. It keeps sandbox identity, filesystem ACL, Git
ownership, `safe.directory`, and index-lock guidance structurally separate from
yadof's package/workspace/runtime contracts.

## Maintenance rules

Architecture and blueprints describe the present, so update them in place when code
changes. Change records remain append-only. Old external references may restore lost
rationale, but obsolete layouts, names, and fallbacks are filtered against current
code before inclusion. A new or substantially revised toDo distinguishes verified
current facts, explicit requirements or decisions, proposals, assumptions, and open
questions where their status affects implementation. It qualifies important values
as defaults, targets, limits, gates, best-effort goals, or guarantees, and folds
later settled decisions into one coherent active handoff rather than relying on
conversation history. A completed toDo moves to `obsolete/` only after applicable
code/tests, user docs, architecture, blueprints, terminology, and one change record
agree; documentation-only work does not invent inapplicable software tests.
Completing one occurrence of a recurring automatic toDo does not complete its
document-level goal, so the handoff remains active until its own completion rule or
an explicit user decision retires it.

The development guide defines the sibling installed-package venv and mandatory
build/force-reinstall/import-path/full-test workflow after package code, build, or
resource changes. Content-only documentation edits use proportional
UTF-8/diff/link/reference checks and enter that software test workflow only when
documentation packaging, discovery, routing, generation, or executable examples
are affected.

## Invariants

- Documentation-only changes receive a change record and commit except for one
  localized correction in exactly one existing documentation file that changes no
  contract, workflow, architecture, blueprint, toDo state, user instruction,
  public behavior, or historical decision; that narrow exception is reported as an
  uncommitted diff unless the user requests a commit.
- `README.md` links every module contract instead of duplicating its detailed rules.
- Installed docs are generated from root source, never edited under site-packages.
- Viewer-specific docs are edited only in the owning viewer subtree and ship beside its
  code; they are not duplicated into the root documentation lifecycle.
- Current architecture/blueprints override historical change records.
- User docs contain task-authoring/runtime instructions written primarily for the
  user's AI agent; administrator deployment guidance remains in
  `admin_tool/admin_doc/` and executable administrator tools remain beside it under
  `admin_tool/`.
- Generic agent-host and Git permission troubleshooting remains in its standalone
  user reference and is explicitly identified as external to yadof behavior.
- Automatic toDos are always evaluated within established task scope; they neither
  require accidental discovery nor authorize an unrelated repository-wide search.
- Root `dev_doc/` is the exclusive repository owner of toDo, obsolete, and change-
  record lifecycle; nested tool/benchmark developer trees link to these contracts
  instead of duplicating them.
