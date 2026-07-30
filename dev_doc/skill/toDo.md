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
- **Automatic trigger** is declared by placement. Automatic toDos live under
  `toDo/auto/`. They describe worthwhile, low-priority cleanup whose exact source
  location may not be known. Every active automatic toDo receives the bounded
  trigger check below; execution remains conditional on an objective match in the
  normal task scope. Do not search the repository solely to find occurrences and do
  not broaden the user's task for one.

Manual toDos may shape implementation choices, but they must not add unrequested
work to the current task.

## Automatic Trigger Check

Reading an automatic toDo is not, by itself, a trigger. After the normal task has
established its concrete files and a current diff or findings exist, perform this
check before reporting the task complete:

1. Compare every active automatic toDo with facts already encountered in the
   in-scope files, their directly relevant callers/tests/documentation, and the
   current diff.
2. Treat a toDo as triggered when that bounded review finds the objective condition
   described by the document. "Naturally exposed" includes this deliberate review
   of already in-scope evidence; it does not require an accidental observation.
3. If the matching work is safe and stays inside both the normal task scope and the
   automatic toDo's limits, complete it and report it. If a match exists but the
   work is risky or outside those limits, report the match and leave the document
   pending.
4. If no objective match exists, do not perform extra work and do not report the
   automatic toDo merely to prove it was read.

This checkpoint may use focused searches needed to establish callers, imports,
exports, tests, or documented contracts for an already encountered candidate. It
must not become an unrelated repository-wide hunt for candidates.

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
  or state `persistent` to disable automatic obsoletion.
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
2. **Persistent.** When `## Obsolete Rule` says `persistent`, do not archive because
   of age or a configured condition. This word governs obsoletion only; placement
   under `toDo/auto/` still declares an automatic trigger. The document remains
   until its own completion rule permits retirement or a user explicitly retires
   it.

These stale-document rules do not replace completion handling. After a manual toDo
is explicitly triggered, or an automatic toDo's bounded check finds a match,
complete the code and documentation work first and then apply that document's
completion rule. Move a one-shot toDo to `../obsolete/` only when its document-level
goal is fully complete. A recurring automatic toDo whose completion rule says to
remain active is not completed by one trigger instance and must stay under
`toDo/auto/`. If only part of a one-shot goal is complete, update the remaining toDo
or split out a new time-named toDo before archiving the completed portion.

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
the current code, tests, user documentation, architecture, blueprints, terminology,
and change record first; only then move a completed one-shot toDo to `obsolete/`.
Keep a recurring automatic toDo active after each completed occurrence unless its
own completion rule or an explicit user decision retires the document.
