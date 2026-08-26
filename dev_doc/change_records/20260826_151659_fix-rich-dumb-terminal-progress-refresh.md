# 2026-08-26 15:16 - Fix Rich Dumb-Terminal Progress Refresh

## Context

- A newly launched visible Windows benchmark still held each cell at zero and
  showed 100 percent only briefly before the next cell, even after all Rich calls
  had moved to the foreground terminal-owner thread.
- Read-only inspection of the active run showed its command log advancing through
  intermediate values such as 800/2,000 while the displayed row remained at zero.
- The launcher environment contained `TERM=dumb` and `NO_COLOR=1`. The runner
  forced Rich's console to terminal mode because stderr returned true from
  `isatty()`, but Rich independently retained its dumb-terminal classification.
  During a started transient live display, that branch makes every explicit
  `Live.refresh()` a no-op. Later lifecycle `Console.print()` calls incidentally
  rendered the then-current zero or complete frame, exactly matching the observed
  timing.
- Existing regressions verified task values and refresh calls, or inspected frames
  after lifecycle output. None asserted that an intermediate refresh itself wrote
  bytes under the inherited launcher environment.

## Change

- When the destination stream is genuinely interactive and `TERM` is `dumb` or
  `unknown`, build only the Rich `Console` with a copied environment from which
  `TERM` is removed.
- Preserve the process-wide environment and every child command's environment.
  Non-interactive streams continue to use their existing bounded snapshots.
- Added a regression that sets `TERM=dumb` and `NO_COLOR=1`, proves Rich no longer
  classifies the fake interactive stream as dumb, and requires the `1/2000` frame
  to be written before any later lifecycle message or cell completion.
- Updated benchmark operator, architecture, blueprint, compatibility, and root
  integration documentation with the console-capability invariant.

## Rationale

The stream's successful `isatty()` check is stronger evidence about this concrete
output destination than an inherited Unix terminal hint copied into a newly
created native Windows console. Restricting the override to Rich's console-local
environment fixes rendering without changing simulator behavior or concealing the
launcher environment from subprocesses.

## Impact

- Interactive Windows runs launched from Codex now emit each event-driven cell
  progress frame instead of waiting for an unrelated lifecycle print.
- ASCII/no-color behavior, command logs, progress parsing, run identity, ETA,
  evidence, and installed yadof package code are unchanged.
- The focused output suite passes 19 tests and the complete benchmark automation
  suite passes 55 tests with fresh external pytest state.
- A new visible no-surrogate performance run passed all 12 preflight checks and
  started all 9 planned NSGA-III cells / 18,000 evaluations under run id
  `20260826_152116-full-nsga3-rich-refresh`; the first independent inspection read
  an intermediate 4/2,000 (0.2 percent) active-cell snapshot.

## Follow-Up

- None.
