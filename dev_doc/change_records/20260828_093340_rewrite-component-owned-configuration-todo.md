# 2026-08-28 09:33 - Rewrite Component-Owned Configuration TODO

## Context

- The existing configuration handoff assumed Pydantic, a legacy-key compatibility
  window, dual-source conflict handling, and possible machine-readable schema
  consumers.
- The user subsequently decided that out-of-repository workspace compatibility and
  temporary CLI/API overrides for algorithm parameters are not required, that
  algorithm changes must be made in `submit/optimization.py`, and that maximum
  surrogate training lag remains core campaign policy.
- A future CLI-wrapped GUI is not currently a JSON Schema consumer, so Pydantic is
  not justified as a core dependency for this refactor.

## Change

- Renamed and completely rewrote the active configuration TODO as a library-neutral
  direct-cutover plan based on a standard-library declarative core schema and
  component-owned internal frozen settings.
- Removed the planned Pydantic spike, public settings-model choice, legacy adapter,
  deprecation window, `UNSET`/conflict rules, and algorithm temporary-override
  channel.
- Recorded the settled core/component ownership, narrow input normalization,
  generation hot-reload, semantic-identity, repository migration, GUI boundary,
  validation, and completion rules.
- Updated the PCA/SVD baseline TODO to reference and directly follow the revised
  component-owned settings plan.

## Rationale

- The architectural gain comes from ownership and immutable generation binding,
  while direct removal of legacy algorithm keys eliminates most of the migration
  complexity that Pydantic would have helped manage.
- Explicit factory kwargs keep task-owned algorithm composition readable and
  generation-hot without creating a second configuration source.

## Impact

- No package, workspace, CLI, configuration, strategy identity, checkpoint,
  history, or runtime behavior changes in this documentation-only update.
- Future implementation is now authorized only by an explicit trigger of the
  rewritten manual TODO and must treat the algorithm-key removal as one direct
  repository-wide cutover.
