# 2026-08-30 10:12 - Prohibit Benchmark Launch Substitutes

## Context

The Windows benchmark guide already prescribed host execution with `--detach`, but
an agent could still confuse a Codex PTY or Terminal panel with a user-visible
Windows console, recreate the launcher with `Start-Process`, or treat an early
empty window handle as launch failure.

## Change

- The benchmark execution guide now explicitly prohibits those three substitute
  mechanisms.
- It directs agents to use the detached-launch receipt and `inspect` instead of
  polling Windows window metadata.

## Rationale

The installed `--detach` launcher already owns console creation, argument quoting,
and window persistence. Reusing that supported path avoids UI-delivery ambiguity,
duplicate launcher logic, and false failure reports while leaving launch behavior
unchanged.

## Impact

Only benchmark user guidance changed. There is no code, CLI, workspace-format,
result-format, or execution-behavior change.

## Follow-Up

None.
