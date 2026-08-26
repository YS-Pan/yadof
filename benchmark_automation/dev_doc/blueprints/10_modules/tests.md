# Module Blueprint: Benchmark Tests

## Intent

Prove runner contracts cheaply and deterministically without launching real
simulators, performance campaigns, or collection-time model inference.

## Coverage lanes

- Core configuration, identity, planning, preflight, state, resume, materialization,
  collection, and report transformations.
- CLI bounded output, stream routing, visible-window pause, and exit behavior.
- Rich ordering, complete compact fields, first-evaluation visibility, GBK safety,
  atomic refresh, and child-stream conversion.
- ETA live-progress parsing, cohort fallbacks, confidence, terminal state, and UTC
  projections using fixed times and tiny synthetic logs.
- Baseline postprocessor output/prefix/overwrite contracts.

## Constraints

Use the selected regular installed yadof distribution. Use fresh pytest base roots
outside the repository and disable cache. Fixtures must not read a live run or
modify baseline templates. Assert bounded-output omissions as well as included
decision facts.
