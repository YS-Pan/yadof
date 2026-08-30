# Context Document Contract

## Purpose And Boundary

`../context/` stores time-named Markdown documents whose experimental evidence,
observations, artifact locations, or other working context must remain available
across agent sessions. A context document is neither an instruction to perform
future work nor an authoritative current-view system contract. Current code,
architecture, blueprints, user documentation, and explicit user instructions take
precedence when they disagree with it.

Use `context/` for information that a later task may need but that does not belong
in `toDo/` as pending work or in `change_records/` as the history of a completed
change. Large or generated artifacts may remain outside Git; a context document can
record their stable location, identity, conditions, and relevant findings.

## Filename-First Reading Contract

Every agent performing a `dev_doc/` context pass, including an agent handling a
delegated subtask, must recursively enumerate every filename and relative path
under `../context/`. This mandatory pass reads names only: do not open, preview,
search, grep, summarize, or otherwise inspect file contents.

After the task's information needs are known, read a context document in full only
when its filename makes it reasonably likely that the document contains relevant
information. Read only the matching documents. If no filename indicates likely
relevance, continue without opening any context document.

Listing a filename does not make its contents current fact, authorize work, or
trigger an expiry review.

## Naming And Content Contract

Use the same time-named form as `toDo/`:

```text
YYYYMMDD_HHMMSS_short-description.md
```

Choose a short description that makes targeted discovery possible without opening
the file. Within the document, preserve enough experiment conditions, evidence
identity or location, observations, limitations, and provenance for a later agent
to use the information without the originating session. Distinguish verified facts
from interpretations, assumptions, and unresolved questions when that distinction
affects later use.

## Expiry And Archival Contract

Do not assess context documents for expiry during normal listing, reading,
maintenance, or task completion. Age alone never triggers a review. Assess expiry
only when the user explicitly instructs an agent to determine whether one or more
context documents have expired.

During an explicitly requested expiry review, read each document being assessed in
full and compare it with the current repository and any relevant current evidence.
A document is expired only when specific evidence shows that it can no longer serve
as active cross-session context, for example because its evidence was superseded,
invalidated, or made irrelevant. If the conclusion is uncertain, leave the
document in `context/` and report the uncertainty.

Move each document confirmed expired, unchanged and with the same filename, to
`../obsolete/`. Do not overwrite an existing destination. The move follows the
normal documentation maintenance, validation, change-record, and commit rules.

## Maintenance Contract

Keep filenames specific enough for the filename-first routing contract. Update a
context document when the same continuing evidence set gains material information;
create a new time-named document when a distinct experiment or evidence set needs
its own identity. Do not move or rewrite a document merely because it has not been
selected for several tasks.
