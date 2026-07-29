# File blueprint: src/yadof/evaluate_manager/local_resources.py

## Intent

- Choose a safe, useful local simulation concurrency from live host capacity and
  shared per-job resource estimates, then measure each local process tree for the
  next calibration step.

## Functionalities

- Snapshot physical/logical CPU counts, available memory, and free space on the
  jobs filesystem.
- Reserve the configured host fraction and calculate independent CPU, memory, and
  disk concurrency limits.
- Bound the effective worker count by population size and
  `LOCAL_EVALUATION_MAX_WORKERS`, while always allowing one job.
- Reuse `resource_calibration.py` for per-job CPU, memory, and disk estimates.
- Monitor a workflow process and its recursive children with `psutil`, recording
  peak RSS, accumulated CPU time, average CPU cores, and peak process count.
- Measure the finished job directory and emit both local-specific and common
  resource metadata.
- Produce a concise planning summary and metadata explaining every limit.

## I/O Format

- Input: selected workspace, loaded config, population size, generation/run
  identity, and optional maximum-worker override.
- Output: immutable `LocalWorkerPlan` containing worker count, resource estimates,
  host snapshot, capacity limits, provenance, and serializable metadata.
- Job metadata includes `local_*` measurements and the shared
  `resource_cpu_usage_cores`, `resource_memory_usage_mib`, and
  `resource_disk_usage_kib` fields.

## Non-Obvious Techniques

- Physical cores are preferred over logical threads because simulator workloads
  are normally CPU-saturating; logical cores are retained as diagnostics.
- Each PID contributes CPU time at most once while RSS is sampled across the
  current recursive tree, avoiding CPU double counting when children exit.
- Capacity limits are independent and the smallest limit wins. This keeps a high
  CPU count from oversubscribing memory or workspace storage.
- Monitoring is best-effort: a disappearing short-lived process does not turn a
  successful simulation into a framework failure.
- Standalone/run smoke dispatch remains explicitly capped at one worker by its
  caller even though the normal local default cap is higher.

## Mutability Profile

- Concurrency math or metadata changes require deterministic capacity tests and a
  real packaged local smoke-contract test.
- Backend-neutral history rules must be changed in `resource_calibration.py`, not
  duplicated here.
- New platform probes must retain a conservative fallback when the probe is
  unavailable.

