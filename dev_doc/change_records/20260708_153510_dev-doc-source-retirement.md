# 2026-07-08 15:35 - Retire Obsolete Dev Doc Sources

## Context
- `dev_doc/spec 20260502.md` and `dev_doc/reference_map.md` were still treated as active context sources, but their contents had already been split across current architecture, blueprint, and terminology docs.
- The old reference map pointed to many historical project paths that are no longer present in this workspace, making it misleading as a live path index.

## Change
- Moved the active product-contract role to `dev_doc/architecture/` and `dev_doc/blueprints/00_project.md`.
- Moved useful historical lineage from the reference map into the project and module blueprints as natural-language context.
- Added stable old-spec terms such as rawData, cost, expensive evaluation, normalized variables, workflow, calc_cost, local mode, distributed mode, and GPSAF to `terminology.md`.
- Updated active documentation references in `dev_doc/README.md`, architecture docs, blueprint notes, the dev-doc blueprint, and `project/README.md`.
- Retired the obsolete spec/reference-map files and archived the completed toDo handoff.

## Rationale
- Current-view contracts should be easier to find and less likely to conflict with obsolete source files.
- Historical reference information is still useful, but it belongs beside the modules it informs rather than in a stale standalone path map.

## Impact
- Future `dev_doc` context gathering reads architecture, terminology, toDo files, and targeted blueprints instead of the retired root-level spec/reference map.
- Maintainers should update module blueprints when historical lineage changes.
- `obsolete/` remains available for archival investigation but is not part of default context gathering.

## Follow-Up
- None.
