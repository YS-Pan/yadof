# 2026-09-29 21:07 - Show generation progress in the Condor GUI

## Context

The GUI streamed optimization output but did not show a per-generation progress
bar. The evaluator already emitted completed/total outcome counts, although its
normal optimization phase label omitted the generation index.

## Change

- Label optimization population progress with its zero-based generation index,
  while keeping smoke output separate.
- Parse those lines in the GUI's existing log event flow and update a determinate
  progress bar and completed/total label on the Tk thread.
- Reset the bar at the start of a launch and at each new generation. Display the
  human-readable generation number together with its zero-based CLI index.

## Impact

The count includes successful and failed terminal evaluations. It does not imply
that a particular sequential job is running, because evaluations may overlap.
No optimizer, HTCondor scheduling, or task behavior changes.
