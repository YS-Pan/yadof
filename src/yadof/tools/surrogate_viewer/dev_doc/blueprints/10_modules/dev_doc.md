# Module blueprint: dev_doc

## Intent

Provide a compact current-design and maintenance context beside the integrated
viewer while linking into yadof's fuller root developer-documentation lifecycle.

## Functionalities

- Give maintainers one canonical README and reading order.
- Record current architecture and invariants.
- Define generative project/module/exceptional-file blueprints.
- Fix ambiguous viewer-specific terminology.
- Define when each document class must be updated.

## I/O Format

The tree contains UTF-8 Markdown under `architecture/`, `blueprints/`, and `skill/`
plus `terminology.md`. Relative links are preferred so the documentation can move
with the viewer subtree inside yadof.

## Non-Obvious Techniques

- Architecture is a required full read; blueprints use targeted reading.
- The tree deliberately omits `toDo/`, `obsolete/`, and `change_records/`.
- Yadof's root change records supply completed package-change history.
- File blueprints mirror source paths and exist only for unusually complex
  contracts.

## Mutability Profile

This infrastructure may grow as the viewer evolves. Do not add local lifecycle
directories merely for structural symmetry; package-wide toDo/obsolete/change
records remain at yadof's root unless a real independent workflow requires
otherwise.
