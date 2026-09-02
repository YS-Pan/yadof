# Change Record Contract

## Purpose

`../change_records/` contains append-only, time-named records in two significance
tiers. Like Architecture Decision Records but broader, each file explains a
concrete completed change, why it was made, what was affected, and what remains
open.

- Records for substantive changes live directly under `../change_records/`.
- Records for minor changes live under `../change_records/minor/`.

The tier changes discoverability, not authority or retention. Both locations are
historical records governed by this contract.

## Reading Contract

Change records in either tier are not part of the default context-reading set.
List or search both locations when a targeted read is required, and read only the
records needed when:

- the reason behind a past change is necessary;
- a current change conflicts with older intent; or
- the user asks for project history.

Architecture and blueprints describe the current system and override historical
records when they differ.

## Significance Classification

Place a record under `minor/` only when the completed change is localized,
low-risk, and preserves every existing project contract. Typical examples are a
small presentation adjustment, a narrow warning or diagnostic correction, a
localized bug fix that does not alter the documented contract, or focused test or
documentation maintenance that still requires a record.

A record must remain directly under `change_records/` when the change does any of
the following:

- changes a public API, CLI workflow, configuration meaning/default, user
  instruction, durable schema, persistence/recovery behavior, concurrency or
  reliability rule, security/safety boundary, dependency, release, or migration;
- changes architecture, module ownership, cross-module contracts, compatibility,
  or a task/framework boundary;
- establishes or revises benchmark/scientific evidence, an acceptance decision,
  or a material historical decision; or
- requires broad coordinated validation because of the change itself.

File count and diff size are supporting evidence, not the classification rule. A
one-file contract change is substantive, while a few tightly coupled files may
still implement one minor correction. When classification is uncertain, keep the
record directly under `change_records/`.

## Naming And Content Contract

Use this filename format:

```text
YYYYMMDD_HHMMSS_short-description.md
```

Recommended record structure:

```text
# YYYY-MM-DD HH:MM - Short Title

## Context
- What situation or problem triggered the change.

## Change
- What was changed.

## Rationale
- Why this approach was chosen.

## Impact
- Which modules, docs, tests, or workflows are affected.

## Follow-Up
- Optional remaining work, risks, or things to revisit.
```

## Maintenance Contract

Add one change record after every code change and classify it before commit: use
`minor/` only when every minor criterion above is satisfied, otherwise use the
`change_records/` root. Documentation-only changes also require a classified
record except for a trivial correction that changes exactly one existing
documentation file, is limited to localized typo/grammar/formatting/link repair,
adds/deletes/renames/moves no file, and changes no architecture, blueprint,
contract, workflow, toDo state, user instruction, public behavior, or historical
decision. An exempt correction may remain uncommitted unless the user requests a
commit; report that working-tree diff and do not create a change record in either
tier.

Every non-exempt documentation change receives a classified record and a commit.
Describe the completed work; unresolved future work belongs in `toDo/`, not in
either change-record tier. After commit, tier placement and record content are
historical: never move or rewrite an older record merely to make it describe the
current system.

The user-authorized introduction of `minor/` is a one-time historical
reclassification. During that migration, preserve every moved record's filename
and substantive content, and update only the path references needed to keep links
resolvable. Future records follow the two-tier rule from creation.
