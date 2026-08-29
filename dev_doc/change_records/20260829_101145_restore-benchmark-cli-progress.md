# 2026-08-29 10:11 - Restore benchmark CLI process and progress UX

## Context

- Historical benchmark tasks required a mature Rich presentation with fixed
  active-cell/global rows, real intermediate child progress, and foreground-only
  terminal ownership. The code-first rewrite emitted JSON lifecycle events but
  did not restore that terminal contract.
- A later explicit user decision superseded the earlier hidden agent launch:
  human- and AI-started measured work must be visible by default, with hidden
  execution available only by request.

## Change

- Added a foreground-owned Rich terminal with active-cell then global rows,
  lifecycle output above the live region, compact narrow layouts, `TERM=dumb`
  recovery for a real TTY, `NO_COLOR` support, bounded non-TTY snapshots, and an
  append-only run-level `benchmark.log`.
- Parsed yadof generation snapshots in pipe-drain threads, queued them, and
  delivered timestamped cell events from the foreground command owner. The
  redundant zero snapshot is suppressed, so the first child-derived update
  records a completed evaluation.
- Added Windows `run|resume --detach`. It creates a separate normal console,
  breaks away from caller job cleanup, preserves console-owned standard handles,
  and immediately returns PID, run/log paths, visibility, and an inspect command.
  Explicit `--detach --hidden` redirects to durable files; `--hidden` alone fails.
- Kept the Python API synchronous, window-neutral, and input-free. Added Rich as
  an independent package dependency and synchronized package/root contracts.

## Rationale

- Rendering from a background pipe thread caused the historical ghost/stalled
  progress failures. A queue preserves pipe throughput while keeping every Rich
  operation on one terminal-owning foreground thread.
- `CREATE_NEW_CONSOLE` is insufficient under Codex if the child retains the
  command host's standard pipes or kill-on-close job. Console-owned handles plus
  job breakaway let the returned receipt be genuinely non-blocking without
  terminating or hiding the child.

## Verification

- The wheel was built, force-reinstalled, and imported from the outer virtual
  environment's site-packages. The complete installed benchmark suite passed.
- A structural-only `test-com` Windows/Codex run launched in a real visible
  detached console, returned a PID/run/log/inspect receipt, logged `1/12` before
  `12/12`, completed, and remained inspectable without starting an external
  simulator or producing performance evidence.

## Follow-Up

- Inspect/ETA, performance classification and scale, pairing/count metrics,
  expanded recovery semantics, and concurrency remain active in sections 4--9 of
  the restoration TODO.
