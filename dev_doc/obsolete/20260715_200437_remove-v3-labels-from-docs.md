# Remove Historical V3 Labels From Documentation

## Context
- Documentation frequently calls the current project, APIs, or contracts "v3".
- That label is a historical residue rather than a meaningful current version
  boundary, and it makes current-view documentation read like an old migration note.

## Goal
- Current documentation should describe Yadof and its contracts without the `v3`
  label.

## Guidance
- When already reading or editing a current document for another in-scope task,
  remove nearby `v3` labels and rewrite the sentence naturally if needed.
- Preserve a version label only when it is part of a literal external identifier or
  when a historical/archival document must distinguish actual released versions.
- Do not search the repository solely for this cleanup and do not edit files under
  `dev_doc/obsolete/` for it.

## Completion Rule
- Remove matching historical labels encountered in current documents already in
  scope.
- Keep this automatic toDo active for other incidental occurrences until its
  obsolete rule archives it.
