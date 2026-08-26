# 2026-08-26 09:35 - Make Benchmark Cell Progress Current

## Context

The interactive benchmark displayed the cell task above the global task, but one
progress event refreshed the global task before updating the cell task. It
therefore deliberately rendered an intermediate frame containing the previous cell
value before requesting the coherent frame. That stale frame matched the observed
empty bar even though the captured yadof log had advanced through many generations.

The compact detail also began with the long cell ID. Narrow terminals therefore
showed the repeated identity while hiding the useful generation and outcome fields.

## Change

- Rich automatic timer refresh is disabled for the benchmark's event-driven live
  region.
- Each event updates both the cell and global tasks without rendering, then issues
  one atomic refresh.
- The cell detail now leads with cumulative whole-cell percentage and a compact
  `gen=<current>/<total> ok=<count> err=<count>` summary.
- A regression test captures every requested frame and proves that a generation-14
  snapshot produces one refresh at `1350/2000`, rather than an earlier zero-valued
  frame followed by a second refresh.

## Rationale

Rich remains the sole terminal cursor owner, while one refresh per coherent state
change removes the ordering race and makes the most useful progress facts visible
within the fixed-width detail column.

## Impact

Future benchmark run/resume processes show cumulative cell progress reliably.
Existing immutable run evidence and already-started processes are unchanged.

## Follow-Up

None.
