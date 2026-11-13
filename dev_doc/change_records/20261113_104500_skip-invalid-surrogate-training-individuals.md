# 2026-11-13 - Skip invalid surrogate training individuals; release 0.8.3

## Context

The user requested that incomplete and non-finite individual data no longer abort
surrogate training, and requested a 0.8.3 package and GitHub code/release push.
Previously the shared training value validated all rows at once; one bad target or
a schema mismatch could stop the complete materialization before fitting.

## Change

- Shared training materialization skips unreadable/truncated individual payloads.
- Both evidence-based and direct materialized inputs discard complete individuals
  with malformed, empty, non-real or non-finite data. They retain the largest exact
  compatible schema cohort; ties use selected-row count, total-row count, field
  count, point count and then original occurrence. A bad first sample therefore
  cannot automatically impose a truncated schema on the remaining population.
- Preserve surviving row order, requested duplicates, masks, identities, lineage
  and record metadata. Content/provenance digests are those of the retained rows.
- Log a bounded skip summary. All-invalid input becomes empty for normal no-data
  scheduling and real-evaluation fallback; programmer, identity and persistence
  errors retain their existing failure boundaries.
- Version 0.8.3 includes the preceding 0.8.2 cluster-settings save fixes.

## Validation and operating boundary

Regression coverage uses synthetic evidence, all five public surrogate training
adapters, corrupt loaders, direct materialized input, empty-data scheduling, and an
actual fit/checkpoint containing only intact rows. Installed-wheel acceptance and
MSI validation use isolated environments and an independent MSI product identity.
No live campaign, installed runtime, workspace, Condor configuration or service is
updated as part of development or release validation.
