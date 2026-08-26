# 4+1 Process View

## New run

1. Parse selectors and build a no-write plan.
2. Preflight current baselines, package, strategies, resources, and storage.
3. Freeze run spec and matrix, then snapshot each selected baseline.
4. Publish initial state and execute cells sequentially.
5. For each attempt: init, materialize inputs, check, optimize/smoke, postprocess,
   view cost, verify fingerprints, seal, and atomically advance state.
6. Remove the live region, print bounded final JSON, and wait for Enter only in an
   interactive foreground window.

## Child stream and Rich progress

Two drain threads preserve stdout/stderr independently. Every complete line is
logged immediately. The common yadof parser consumes matching snapshots from either
stream; non-progress output is optionally displayed above Rich. A parsed generation
snapshot becomes `generation * population + finished`. The progress lock updates
cell and global tasks together, then performs one refresh. A positive ratio uses
ceiling bar fill, and small percentages retain a decimal.

## Read-only inspection and ETA

`inspect` loads immutable spec plus atomic state. For terminal cells it reads no
successful logs. It derives duration observations from completed attempt
create/seal timestamps. For the one running cell it locates only the latest command
directory, reads started/finished metadata, and scans at most the bounded tail of
stderr for the newest yadof snapshot. It reports last-activity age even before an
evaluation snapshot exists.

Because cells run sequentially, ETA is the estimated remainder of the active cell
plus the sum of pending-cell estimates. Cohort medians are scaled by planned
evaluations. Live optimize projection can raise the active estimate when current
throughput is slower. Missing observations fall back to declared evaluation-only
lower bounds and reduce confidence. Repeated external inspection is safe; it does
not write state or wait on the benchmark process.

## Interruption and resume

Completed boundaries remain immutable. An interrupted in-generation attempt is
sealed and replaced. Resume refuses identity drift, skips completed cells, and
continues the selected immutable matrix. It never edits an old attempt to make it
appear complete.

## Failure flow

Command timeout/nonzero exit, missing generation, postprocess failure, cost-view
failure, or input drift fails the attempt with targeted metadata. Performance runs
continue independent cells unless fail-fast is selected. Structural runs normally
stop. Collection may still preserve partial public evidence.
