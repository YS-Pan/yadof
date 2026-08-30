# 2026-08-30 14:57 - Partition Obsolete Archive By Source

## Context

`dev_doc/obsolete/` mixed completed toDo handoffs with old diagnostics, plans,
drafts, and other retired developer material in one flat directory. That layout did
not preserve the source distinction already used by the active `toDo/` and
`context/` lifecycles.

## Change

- Defined `obsolete/todo/`, `obsolete/context/`, and `obsolete/other/` as the only
  archive classes. Source and lifecycle determine placement; filenames and subjects
  do not.
- Updated the toDo and context contracts, current development architecture,
  documentation blueprint, and terminology. Archival now preserves filenames and
  substantive content, rejects destination collisions, and leaves no file directly
  below the archive root.
- Used Git history and document content to classify the 58 existing root files.
  Forty-seven files originating as toDo handoffs moved to `obsolete/todo/`; eleven
  diagnostics, old plans, drafts, specifications, and reference material moved to
  `obsolete/other/`. No existing file originated from `context/`.
- Added an empty-directory marker so `obsolete/context/` remains present in Git,
  and updated active-document links to archived toDo handoffs.

## Rationale

Source-partitioned archival makes it clear whether a historical file represents
retired future work, expired cross-session context, or some other obsolete input.
It also lets future archival operations choose a deterministic destination without
reconstructing the whole mixed archive.

## Impact

Developer-document maintenance and targeted historical reads now use the three
archive subdirectories. This is a documentation-only layout and contract change;
it does not alter package code, build mapping, installed documentation routing, or
runtime behavior.

## Follow-Up

Future completed/retired toDos go to `obsolete/todo/`, explicitly reviewed expired
context material goes to `obsolete/context/`, and all other obsolete developer
material goes to `obsolete/other/`.
