# 4+1 Process View

## New run

1. Parse selectors and build a no-write plan.
2. Preflight current baselines, package, strategies, resources, and storage.
3. Freeze run spec and matrix, snapshot each selected baseline, and shallow-scan a
   bounded set of prior run directories into the new run's timing-history snapshot.
4. Publish initial state and execute cells sequentially.
5. For each attempt: init, materialize inputs, check, optimize/smoke, postprocess,
   view cost, verify fingerprints, seal, and atomically advance state.
6. Remove the live region, print bounded final JSON, and wait for Enter only in an
   interactive foreground window.

## Child stream and Rich progress

Two drain threads preserve stdout/stderr independently. Every complete line is
logged immediately, then a progress or optional streamed-output event is queued.
The foreground loop that waits for the child process drains this queue at short
intervals; it is the only thread that writes through Rich or refreshes the live
region. It also appends every timestamped parsed snapshot to the command's
`progress.jsonl`, bracketed by command-start/end events. The common yadof parser
consumes matching snapshots from either stream. A
parsed generation snapshot becomes `generation * population + finished`. The
progress lock updates cell and global tasks together, then performs one refresh. A
positive ratio uses ceiling bar fill, and small percentages retain a decimal.

## Read-only inspection and ETA

`inspect` loads immutable spec plus atomic state. For terminal cells it reads no
successful logs. It reads the run-local frozen timing sample and derives additional
current-run duration observations from completed attempt create/seal timestamps.
For the one running cell it locates only the latest command directory, reads
started/finished metadata, and scans at most the bounded tail of `progress.jsonl`;
older commands fall back to stderr. It reports last-activity age even before an
evaluation snapshot exists.

Because cells run sequentially, ETA is the estimated remainder of the active cell
plus the sum of pending-cell estimates. Cohort order is exact prior matched cell,
current same-case/arm, compatible prior matched cell, then current same arm;
cross-arm same-case and all-arm pooling are excluded. Medians and relative MAD
describe cohort center/spread. Three or more completed generation intervals feed a
robust non-decreasing duration trend that can raise the active remainder; simple
cumulative-throughput projection is only the pre-trend fallback. Missing
observations fall back to declared evaluation-only lower bounds and reduce
confidence. Repeated external inspection is safe; it does not scan other runs,
write state, or wait on the benchmark process.

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
