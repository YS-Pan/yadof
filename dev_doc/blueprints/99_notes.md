# Blueprint notes

- `src/yadof/` is the only framework implementation source; `tests/` is the only
  maintained pytest source.
- `blueprints/00_project.md` defines the system contract. Module and file blueprints
  preserve intent, I/O, non-obvious techniques, mutability, and useful lineage.
- File blueprints mirror current source paths below `blueprints/20_files/`.
- User task files and active adapters live in explicit workspaces. Packaged adapter
  resources are copied by CLI, never imported from a repository staging namespace.
- Historical paths may remain in `change_records/` and `obsolete/`; current
  architecture, blueprints, user docs, and pending toDos must use package/workspace
  terminology.
