# Module blueprint: documentation

## Sources and distribution

Root `dev_doc/` and `user_doc/` are authoritative editable sources. Build mapping
copies both trees into read-only wheel resources so installed documentation matches
installed code. `yadof docs list/show/bundle` addresses audience-relative paths,
rejects traversal, and never requires callers to locate site-packages.
The `user` audience is named for the role whose workflow it serves; its documents
are written primarily for an AI coding agent acting under a human user's direction.

The integrated surrogate viewer retains a second, relatively independent
developer tree at `src/yadof/tools/surrogate_viewer/dev_doc/`. That tree ships with
the tool package and owns viewer-specific architecture, blueprints, and terminology;
the root developer README links to it instead of duplicating those contracts.

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
- `toDo/`: unresolved work; root entries require explicit request, while active
  `auto/` entries receive a bounded match check against already in-scope evidence
  before normal work is reported complete.
- `obsolete/`: historical completed/cancelled toDos, not current guidance.

`user_doc/example_prompts/` is an expandable collection with one Markdown file per
copyable prompt. Its index may link placeholders whose prompt bodies remain empty
until examples are supplied.

## Maintenance rules

Architecture and blueprints describe the present, so update them in place when code
changes. Change records remain append-only. Old external references may restore lost
rationale, but obsolete layouts, names, and fallbacks are filtered against current
code before inclusion. A completed toDo moves to `obsolete/` only after code, tests,
user docs, architecture, blueprints, terminology, and one change record agree.
Completing one occurrence of a recurring automatic toDo does not complete its
document-level goal, so the handoff remains active until its own completion rule or
an explicit user decision retires it.

The development guide defines the sibling installed-package venv and mandatory
build/force-reinstall/import-path/full-test workflow after package changes.

## Invariants

- Documentation-only changes still receive a change record.
- `README.md` links every module contract instead of duplicating its detailed rules.
- Installed docs are generated from root source, never edited under site-packages.
- Viewer-specific docs are edited only in the viewer subtree and ship beside its
  code; they are not duplicated into the root documentation lifecycle.
- Current architecture/blueprints override historical change records.
- User docs contain task-authoring/runtime instructions written primarily for the
  user's AI agent; administrator deployment remains in `admin_tool/`.
- Automatic toDos are always evaluated within established task scope; they neither
  require accidental discovery nor authorize an unrelated repository-wide search.
