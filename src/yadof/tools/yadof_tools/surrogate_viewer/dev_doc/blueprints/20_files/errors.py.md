# File blueprint: errors.py

## Responsibility

Define viewer-local typed runtime failures and normalize terminal
summary/audit/inspect exceptions into stable human-readable or schema-versioned
standard JSON errors.

## Contracts

- JSON errors have `schema_version`, `analysis="surrogate_tool_error"`, and one
  `error` object containing `code`, `message`, `details`, and `hints`.
- Normalize non-finite detail values to `null` and encode with `allow_nan=False`.
- Preserve typed selection/output/inference/render codes; map configuration,
  missing optional dependency, and no-compatible-checkpoint failures without
  parsing message text. Unknown exceptions expose only a safe generic type/code,
  not a traceback or arbitrary internal message.
- Distinguish `OUTPUT_CONFLICT` (an existing target would be overwritten) from
  `OUTPUT_WRITE_FAILED` (destination inspection, creation, publication, hashing,
  or manifest I/O failed) and `RENDER_FAILED` (Agg drawing itself failed).
- CLI routing owns stdout/stderr and exit status. This file owns no parsing,
  workspace loading, inference, rendering, or writes.
