# 2026-08-26 13:47 - Centralize Benchmark toDos And Change Records

## Context

- The benchmark developer-document expansion introduced local
  `skill/toDo.md` and `skill/change_records.md` contracts even though their content
  routed pending work and completed history back to root yadof `dev_doc/`.
- The user requested one repository-wide toDo/change-record lifecycle implemented
  by yadof's root developer documentation rather than duplicated benchmark-local
  contracts.

## Change

- Removed the benchmark-local toDo and change-record skill contracts.
- Changed the benchmark developer entry route to link directly to root
  `dev_doc/skill/toDo.md` and `dev_doc/skill/change_records.md`.
- Clarified in benchmark agent/architecture guidance and root architecture/project/
  documentation blueprints that nested benchmark docs own current-view operator,
  architecture, blueprint, and terminology material, while root `dev_doc/`
  exclusively owns repository-wide `toDo/`, `obsolete/`, and `change_records/`.

## Rationale

- Pending-work triggers, obsoletion, archival, and completed-change history apply
  to the repository as a whole. Keeping one authoritative contract prevents nested
  rules from drifting or creating two locations for the same benchmark work.
- Benchmark-specific current-view documentation remains useful because its runtime
  and evidence contracts are independent, but it does not require a second
  lifecycle system.

## Impact

- Existing root change records, including prior benchmark records, remain
  append-only and unchanged.
- There was no benchmark-local `toDo/`, `obsolete/`, or `change_records/` data
  directory to migrate.
- This is a content-only documentation-system change outside package resources and
  executable behavior. Static path/link and Git diff checks are sufficient; no
  wheel build, reinstall, or software test is required.

## Follow-Up

Future benchmark pending work and completed changes must use the root yadof
directories and contracts directly.
