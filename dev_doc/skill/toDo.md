# toDo And Obsolete Contract

## Purpose And Default Reading

`../toDo/` contains time-named Markdown files for future work that has not been
completed. One file may describe one task or a related cluster. Read every Markdown
file below `../toDo/` recursively during the first `dev_doc/` context pass, even
when the user's current instruction appears unrelated to every pending item.

Pending work is context for choosing a technical route that will not fight likely
future goals. Reading a manual toDo is context gathering, not authorization to
execute it. Apply each automatic toDo's obsolete rules before treating that document
as active.

## Trigger Contract

Placement is the authoritative trigger declaration:

- **Manual trigger** is the default. Manual toDos live directly under `toDo/`.
  Reading or mentioning one does not trigger its instructions. Execute it only when
  the user's prompt explicitly says to execute the instructions in that particular
  file. All toDos that predate `toDo/auto/` are manual.
- **Automatic trigger** is opt-in. Automatic toDos live under `toDo/auto/`. They
  describe worthwhile, low-priority cleanup whose exact source location may not be
  known. Do not search the repository solely to find occurrences and do not broaden
  the user's task for one. When normal work naturally exposes a match in files
  already in scope, apply it opportunistically only if the change is safe within
  that scope; otherwise leave it pending.

Manual toDos may shape implementation choices, but they must not add unrequested
work to the current task.

## Naming And Content Contract

Use this filename format:

```text
YYYYMMDD_HHMMSS_short-description.md
```

The timestamp is mandatory for automatic toDos because it is their portable
creation time for the default expiry rule. Parse the leading `YYYYMMDD_HHMMSS` as a
local wall-clock timestamp. A time expiry is strict: archive only after the exact
timestamp plus its duration, not at that instant. For example,
`20260715_204210_example.md` with a two-day limit remains active at
`2026-07-17 20:42:10` and is stale immediately afterward. Manual toDos should use
the same format, but older manual filenames remain valid.

Examples:

```text
20260519_193400_nsga3-surrogate-handoff.md
20260602_143000_surrogate-cache-policy.md
auto/20260714_120000_normalize-incidental-formatting.md
```

Recommended structure:

```text
# Short Future Task Title

## Context
- Why this future work matters.

## Goal
- What should be true when the task is complete.

## Guidance
- Technical direction, constraints, and relevant files.

## Completion Rule
- How to recognize completion and whether any follow-up should remain.

## Obsolete Rule
- Automatic toDos only: omit for the default seven-day time limit with no extra
  condition; state a custom time limit and/or an explicit user-defined condition,
  or state `manual` to disable automatic obsoletion.
```

## Automatic Obsolete Contract

Whenever an automatic toDo is read, apply the applicable stale-document rule before
treating it as active:

1. **Automatic: time OR configured condition (default).** Check every configured
   condition and move the document to `../obsolete/` as soon as one is true:
   - **Time:** use the leading `YYYYMMDD_HHMMSS` filename timestamp as the local
     creation time. With no obsolete-related annotation, the limit is seven days.
     A document may state a different duration or date in `## Obsolete Rule`.
     Archive only when the read time is strictly later than the deadline; equality
     with the deadline is not obsolete.
   - **User-defined condition:** a document may state an objective, user-chosen
     condition such as "after task X is completed". This condition is optional and
     absent by default. Do not invent one from project changes or from a subjective
     judgment that the document is no longer valid.
2. **Manual.** When `## Obsolete Rule` says `manual`, do not archive because of age
   or a configured condition. The document remains until explicitly retired or its
   work is completed.

These stale-document rules do not replace completion handling. After a manual toDo
is explicitly triggered, or an automatic toDo is opportunistically triggered,
complete the code and documentation work first and then move the fully completed
file to `../obsolete/`. If only part is complete, update the remaining toDo or split
out a new time-named toDo before archiving the completed portion.

## Obsolete Archive Contract

`../obsolete/` stores old plans, old diagnostics, completed toDo handoffs,
automatic toDos retired by age or a configured condition, and drafts that are no
longer active design input.

Do not read `obsolete/` by default. Read it only when a current document explicitly
points there, when investigating old plans, or when checking a completed toDo
handoff. Never use an obsolete document as current fact unless a current document
explicitly brings that fact forward.

## Maintenance Contract

When adding future work, put manual-trigger work directly under `toDo/` and
automatic-trigger work under `toDo/auto/`. When a task is fully completed, update
the current code, tests, agent documentation, architecture, blueprints, terminology,
and change record first; only then move its toDo to `obsolete/`.
