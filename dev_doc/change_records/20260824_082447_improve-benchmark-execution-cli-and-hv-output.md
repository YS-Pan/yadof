# 2026-08-24 08:24 - Improve Benchmark Execution, CLI, And HV Output

## Context

- The source-checkout benchmark called its non-surrogate arm `real-search` even
  though every frozen case is multi-objective and the selected concrete search is
  pymoo NSGA-III.
- Measured fast evaluations were capped at four or eight workers and fast resource
  autodetection capped them again by physical CPU count, leaving the host
  underutilized for simulator workloads that spend time waiting.
- Long visible benchmark windows had only lifecycle messages, closed as soon as
  run/resume returned, did not create a cost-view image for every optimization, and
  required an agent to reshape report JSON before presenting the final cumulative
  hypervolume table.

## Change

- Renamed the non-surrogate arm and strategy template to `nsga3`; the template now
  directly constructs real-evaluation-only NSGA-III, and configured arm display
  names flow into reports.
- Set every measured case to a 32-worker fast cap and disabled fast resource
  autodetection through measured-cell overrides, leaving smoke behavior unchanged.
- Added a thread-safe cell progress renderer that keeps lifecycle and optional
  streamed child text above one bottom bar in an interactive terminal.
- Added a required post-optimization `yadof view cost` command producing
  `benchmark-cost.png` in each measured workspace's tool-output directory.
- Made interactive run/resume wait for Enter after printing the final JSON summary;
  non-interactive execution still returns immediately.
- Added an algorithm-labeled Markdown HV table to report artifacts and to default
  report/inspect terminal output on stderr while preserving JSON-only stdout.

## Rationale

- Experiment identities should name the actual compared algorithms.
- Fixed oversubscription expresses the requested benchmark operating point directly
  instead of allowing the general-purpose host-safety heuristic to restore a
  physical-core ceiling.
- Progress, retained cost plots, a persistent final console, and a ready-to-read HV
  table make long benchmark runs observable without weakening immutable run state,
  bounded stdout, or append-only command evidence.

## Impact

- Existing runs retain their immutable old arm IDs and cannot be resumed against
  the renamed strategy/config identity; new runs use `nsga3` cell IDs.
- Measured runs can place materially more simultaneous load on memory, simulator
  licenses, external runtimes, and GPU/CPU resources, so pilot and preflight review
  remain required.
- The source-checkout benchmark, focused tests, benchmark/operator documentation,
  project architecture, blueprint, and terminology changed. Installed yadof package
  code and frozen baseline contents did not change.

## Follow-Up

- Use the performance pilot to confirm that 32 workers improves utilization on the
  target machine without exhausting simulator-specific resources before launching
  the formal full matrix.
