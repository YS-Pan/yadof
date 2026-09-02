# 2026-09-02 12:32 - Split Minor Change Records From Substantive History

## Context

- `dev_doc/change_records/` mixed small presentation, diagnostic, and maintenance
  fixes into the same flat listing as releases, migrations, architecture changes,
  reliability work, and scientific decisions.
- The root listing had grown to 265 records, making substantive history harder to
  scan even though existing records were already excluded from default developer
  context.
- The user requested a `minor/` child for very small changes while retaining less
  minor records directly under `change_records/`.

## Change

- Added a two-tier significance contract: localized low-risk work that preserves
  existing contracts may use `change_records/minor/`; substantive or uncertain
  work remains at the root.
- Defined explicit root-tier boundaries for public workflows and APIs,
  configuration, durable schemas, persistence/recovery, concurrency/reliability,
  security, dependencies, releases/migrations, architecture/module ownership,
  cross-module contracts, scientific/benchmark evidence, material decisions, and
  changes that require broad coordinated validation.
- Kept the existing narrow no-record exception for a localized typo, grammar,
  formatting, or link correction in exactly one existing documentation file.
- Updated the developer entry point, development architecture, project and
  documentation blueprints, blueprint notes, and terminology to describe the same
  two-tier lifecycle.
- Reviewed all 265 pre-existing root records. Eighteen localized low-risk records
  moved unchanged into `change_records/minor/`; 247 remained at the root. A
  concurrent task's later substantive record was outside that frozen migration
  cohort.

## Rationale

- Classification follows semantic impact rather than line count or the number of
  touched files. This keeps significant one-file decisions visible while allowing
  a few tightly coupled presentation or contract-preserving bug-fix files to remain
  minor.
- Uncertain records stay at the root. This makes `minor/` a deliberately narrow
  convenience tier rather than a place where consequential history can disappear.
- The one-time migration preserves filenames and substantive content. Tier
  placement becomes historical after commit, like record content itself.

## Impact

- Future maintainers choose the record tier before commit and apply the same
  targeted-reading policy to both locations.
- The migration changed no package code, user workflow, runtime behavior, or
  documentation discovery mechanism.
- All 18 moved records retained identical SHA-256 content, no root/minor name
  collision or invalid filename was found, and no moved record had an inbound old
  path or internal relative link requiring an edit.

## Follow-Up

- None. Apply the root-by-default rule whenever a future classification is
  uncertain.
