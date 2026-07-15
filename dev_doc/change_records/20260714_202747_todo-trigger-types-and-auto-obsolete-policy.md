# 2026-07-14 20:27 - ToDo Trigger Types And Automatic Obsolete Policy

## Context
- The documentation contract required every toDo to be read, but it did not
  distinguish contextual reading from authorization to execute pending work.
- Some desirable, low-priority cleanup is not worth locating through a dedicated
  repository search and is useful only if normal work happens to reveal it.

## Change
- Defined manual and automatic toDo trigger types.
- Kept existing and future manual-trigger documents directly under `dev_doc/toDo/`;
  they execute only when a prompt explicitly requests the instructions from a
  particular file.
- Added `dev_doc/toDo/auto/` for automatic-trigger documents that may be handled
  opportunistically during already in-scope work.
- Added two automatic-toDo obsolete policies. The default automatic policy archives
  a document when either its time limit is exceeded or project changes invalidate
  it; the manual policy disables both automatic conditions. The default time limit
  is seven days from the filename timestamp.

## Rationale
- Separating reading from execution preserves future-work context without silently
  expanding a user's current request.
- Opportunistic triggering makes small cleanup economical while avoiding a
  low-value search for unknown locations.
- Explicit stale-document rules prevent short-lived automatic guidance from
  remaining active after it ages out or no longer matches the project.

## Impact
- Updated `dev_doc/README.md`, the architecture index and development view, the
  project and `dev_doc` blueprints, and project terminology.
- Existing toDo documents remain manual-trigger documents without requiring edits.
- New automatic toDos require a timestamped filename under `dev_doc/toDo/auto/`.

## Follow-Up
- None.
