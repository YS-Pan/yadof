# Module blueprint: documentation

Root `dev_doc/` and `agent_doc/` are authoritative editable sources and are mapped
to read-only wheel resources. Installed documentation commands list, show, and
bundle audience-relative files without exposing package paths. Architecture describes current truth; blueprints define
contracts/lineage; terminology defines non-obvious terms; change records are
append-only; obsolete files are historical. A completed toDo moves to `obsolete/`
only after code, tests, user docs, architecture, blueprint, terminology, and its own
change record agree.
