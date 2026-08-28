# Module Blueprint: Benchmark Tests

## Intent

Prove runner contracts cheaply and deterministically without launching real
simulators, performance campaigns, or collection-time model inference.

## Coverage lanes

- Core configuration, identity, planning, preflight, state, resume, materialization,
  collection, and report transformations.
- CLI bounded output, stream routing, visible-window pause, and exit behavior.
- Rich ordering, complete compact fields, first-evaluation visibility, GBK safety,
  atomic refresh, and actual subprocess child-stream conversion whose terminal
  refreshes remain on the foreground owner thread. An interactive fake terminal
  under inherited `TERM=dumb` must receive the intermediate rendered bytes before
  any later lifecycle message or cell completion.
- ETA sidecar timestamps, exact/compatible prior snapshots, cross-arm rejection,
  same-arm/lower-bound fallbacks, generation-duration growth, confidence, terminal
  state, UTC projections, and recorded-session replay using fixed times and tiny
  synthetic artifacts.
- Baseline postprocessor output/prefix/overwrite contracts.
- Run-local execution isolation, source-change tolerance, missing-snapshot
  restart/migration diagnostics, and completed legacy-run readability.
- Historical preregistration conclusions are checked directly from declarative
  plans/receipts; retired validator/source hashes are never re-evaluated.

## Constraints

Use the selected regular installed yadof distribution. Use fresh pytest base roots
outside the repository and disable cache. Fixtures must not read a live run or
modify baseline templates. Assert bounded-output omissions as well as included
decision facts.
