# 2026-05-20 10:06 - Blueprints Directory Rename

## Context
- The `dev_doc/prompt/` folder name could be misunderstood as ordinary prompt text
  or human-facing notes.
- The documents in that folder are meant to be generative module blueprints: an AI
  should be able to recreate equivalent code behavior from them.

## Change
- Renamed `dev_doc/prompt/` to `dev_doc/blueprints/`.
- Updated current documentation paths and wording from prompt documents to blueprint
  documents.
- Updated blueprint file headings from `Module prompt` to `Module blueprint`.
- Kept historical `reference/.../prompt/` paths unchanged because those are old
  source-reference directory names.

## Rationale
- `blueprints` is short, readable, and conveys reconstruction intent without implying
  that the files are merely conversational prompts.
- The new name better matches the directory's role as a set of implementation
  blueprints for code regeneration.

## Impact
- AI agents should list `dev_doc/blueprints/` and `dev_doc/blueprints/10_modules/`
  before selectively reading relevant blueprint files.
- Documentation maintenance should update `blueprints/` when module intent, I/O,
  non-obvious techniques, or mutability boundaries change.

## Follow-Up
- Leave old change records and old reference directories unchanged unless a current
  document needs to bring their content forward.
