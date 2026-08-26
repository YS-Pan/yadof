# Module Blueprint: CLI

## Intent

Expose benchmark planning, validation, execution, resume, collection, reporting,
and inspection as predictable commands for humans and coding agents.

## Responsibilities

- Parse global output-root and subcommand options.
- Select bounded versus explicitly expanded JSON.
- Route to core functions without duplicating business logic.
- Print JSON on stdout, live/progress/table content on stderr, and map benchmark
  errors to stable nonzero exit behavior.
- Pause after final run/resume output only when stdin is interactive.

## I/O and constraints

All paths become `Path` values. Suggested follow-up commands preserve the resolved
runs root. `inspect` is read-only and returns active status/ETA without waiting.
The CLI must not load large metrics just to render a status summary.

## Mutability

Command names/options may expand, but bounded defaults, stream separation, explicit
full-detail flags, and thin routing remain stable.
