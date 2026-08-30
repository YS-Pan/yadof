# 2026-08-30 19:49 - Clarify long benchmark waiting

## Context

The overall plan prescribed roughly 60-second polling for a long benchmark. The
user asked whether Codex can wait longer, suggested a 20-minute cadence, and
clarified that the one-launch rule applies independently within every
implementation stage.

## Change

- Reworded the shared benchmark policy so each implementation stage launches its
  long benchmark only once and follows the same foreground terminal/session to a
  final exit code.
- Replaced the fixed 60-second poll with the longest bounded or event-driven wait
  supported by the current Codex/runtime.
- Defined about 20 minutes as a quiet-run observation/reporting target rather than
  a promise that one terminal poll can block for that duration.
- Applied the same wording to the exact stage 1 TODO so it does not override the
  overall plan with the old cadence.

## Rationale

Long-running Goal work and terminal polling are separate layers. Codex can keep a
multi-hour task and its terminal session active, while an individual terminal wait
has a runtime-specific upper bound and can return early when output or completion
arrives. Reusing bounded waits on the same session preserves process identity and
avoids duplicate benchmark runs without hard-coding a transient tool limit into
the plan.

## Impact

Only developer planning documentation changed. No Goal or TODO was executed, and
no source, tests, package resources, installed wheel, or benchmark process changed.

## Follow-Up

At execution time, use the longest wait primitive then available, continue the
same session when it returns, and reserve analysis/reporting for completion,
failure, required input, or meaningful new state.
