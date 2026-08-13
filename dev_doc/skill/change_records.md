# Change Record Contract

## Purpose

`../change_records/` contains append-only, time-named records. Like Architecture
Decision Records but broader, each file explains a concrete completed change, why
it was made, what was affected, and what remains open.

## Reading Contract

Change records are not part of the default context-reading set. Read only the
records needed when:

- the reason behind a past change is necessary;
- a current change conflicts with older intent; or
- the user asks for project history.

Architecture and blueprints describe the current system and override historical
records when they differ.

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

Add one change record after every code change. Documentation-only changes also
require a record except for a trivial correction that changes exactly one existing
documentation file, is limited to localized typo/grammar/formatting/link repair,
adds/deletes/renames/moves no file, and changes no architecture, blueprint,
contract, workflow, toDo state, user instruction, public behavior, or historical
decision. An exempt correction may remain uncommitted unless the user requests a
commit; report that working-tree diff and do not create a change record for it.

Every non-exempt documentation change receives a record and a commit. Describe the
completed work; unresolved future work belongs in `toDo/`, not in
`change_records/`. Never rewrite an older record to make it describe the current
system.
