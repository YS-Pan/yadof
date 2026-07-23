# Module blueprint: documentation

## Sources and distribution

Root `dev_doc/` and `agent_doc/` are authoritative editable sources. Build mapping
copies both trees into read-only wheel resources so installed documentation matches
installed code. `yadof docs list/show/bundle` addresses audience-relative paths,
rejects traversal, and never requires callers to locate site-packages.

## Developer document roles

- `README.md`: entry point for mandatory reading order, environment, validation,
  cross-module maintenance, and links to detailed contracts.
- `skill/`: module-specific contracts for agent documentation, architecture,
  blueprints, toDo/obsolete handling, terminology, and change records.
- `architecture/`: current system relationships and invariants.
- `blueprints/10_modules/`: current module responsibility, dependencies, I/O, and
  non-obvious constraints.
- `blueprints/20_files/`: file lineage for high-risk/specialized implementation.
- `terminology.md`: project-specific terms whose meaning is not obvious.
- `change_records/`: append-only time-named decision/implementation explanations.
- `toDo/`: unresolved work; root entries require explicit request, `auto/` entries
  are only low-priority natural follow-ups.
- `obsolete/`: historical completed/cancelled toDos, not current guidance.

## Maintenance rules

Architecture and blueprints describe the present, so update them in place when code
changes. Change records remain append-only. Old external references may restore lost
rationale, but obsolete layouts, names, and fallbacks are filtered against current
code before inclusion. A completed toDo moves to `obsolete/` only after code, tests,
agent docs, architecture, blueprints, terminology, and one change record agree.

The development guide defines the sibling installed-package venv and mandatory
build/force-reinstall/import-path/full-test workflow after package changes.

## Invariants

- Documentation-only changes still receive a change record.
- `README.md` links every module contract instead of duplicating its detailed rules.
- Installed docs are generated from root source, never edited under site-packages.
- Current architecture/blueprints override historical change records.
- Agent docs contain task-authoring/runtime instructions; administrator deployment
  remains in `admin_tool/`.
