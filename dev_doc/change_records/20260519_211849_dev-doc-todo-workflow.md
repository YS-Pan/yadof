# 2026-05-19 21:18 - Dev Doc ToDo Workflow

## Context
- The project needed a documented place for future tasks that are known but not yet
  implemented.
- Pending future work should influence current technical choices, even when the
  current request is not directly about that future work.

## Change
- Renamed the documentation entry point from `dev_doc/readme.md` to
  `dev_doc/README.md`.
- Added `dev_doc/toDo/` as the default-read future-work folder.
- Moved the NSGA-III surrogate handoff into `dev_doc/toDo/` with a time-prefixed
  filename.
- Updated the new-project reference guide to include `README.md`, `toDo/`, and the
  rule for archiving completed toDo files in `obsolete/`.

## Rationale
- `toDo/` separates future intent from completed change history.
- Default-reading pending work helps AI agents choose implementations that remain
  compatible with planned work.
- Moving completed toDo files to `obsolete/` keeps active future work easy to scan
  without deleting useful handoff context.

## Impact
- AI agents must read every Markdown file under `dev_doc/toDo/` during the first
  `dev_doc` pass.
- `change_records/` remains historical and is still not part of default context
  gathering.
- `obsolete/` now explicitly includes completed toDo handoffs.

## Follow-Up
- Future tasks should be added under `dev_doc/toDo/` with
  `YYYYMMDD_HHMMSS_short-description.md` filenames.
