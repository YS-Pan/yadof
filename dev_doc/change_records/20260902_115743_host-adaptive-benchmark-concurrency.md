# Make benchmark simulator concurrency host-adaptive

## Context

The packaged benchmark baselines stored fixed simulator worker counts, while
yadof's default resource planner could clamp those counts again. On the target
host this left CPU, memory, and storage lightly used. The requested contract is a
portable per-baseline physical-core multiplier, selected by short 200-individual,
one-generation measurements, with no fixed worker count in baseline authoring.
The user additionally requires yadof to trust an explicit fast/local worker cap
rather than applying a second CPU/memory/disk clamp.

## Changes

- `yadof-benchmark 0.5.0` baseline manifests accept only the finite positive
  `simulation_concurrency.physical_core_multiplier`; the old `max_workers` and
  `resource_autodetect` fields are rejected.
- Cell materialization detects physical cores with
  `psutil.cpu_count(logical=False)`, resolves
  `max(1, floor(physical_cores * multiplier))`, applies the integer to the
  isolated yadof config, and records detection, multiplier, rounding, and result
  in state, reports, events, terminal output, and active inspection.
- Packaged defaults are 2.0 for Chrono, 2.0 for ngspice, and 1.0 for synthetic,
  based on the bounded tuning evidence in
  `dev_doc/context/20260902_114845_yadof-benchmark-simulator-concurrency-tuning.md`.
- yadof fast/local resource planners continue to record host snapshots,
  calibrated estimates, and advisory CPU/memory/disk limits, but those limits no
  longer reduce an explicit configured worker cap. Metadata states that resource
  limits are not enforced. Population size remains the natural upper bound on
  useful simultaneous work, and smoke remains one worker.
- User and development documentation, architecture, terminology, blueprints, and
  structural tests now express the multiplier and authoritative-cap contracts.

## Verification

- Built and force-reinstalled `yadof 0.5.0` and `yadof-benchmark 0.5.0`; both
  imported from the outer `.venv/Lib/site-packages` with source injection removed.
- Installed yadof focused resource-planning tests passed 5/5, including lower
  advisory host limits with unchanged explicit fast/local worker counts.
- The full installed yadof suite passed 452/452 in 97.79 seconds.
- The full installed benchmark suite passed 50/50 in 5.35 seconds, including
  multiplier validation, legacy-field rejection, deterministic floor resolution,
  materialized config/state evidence, reporting, and terminal presentation.
- Installed read-only benchmark check/plan on the fresh acceptance workspace
  reported three cells, population 200, one generation, 600 planned evaluations,
  and multipliers 2.0/2.0/1.0 without writing execution evidence.
- The installed real acceptance completed all three baselines: 3/3 cells were
  collected and valid, with physical cores 8 and resolved workers 16/16/8. yadof
  metadata retained advisory CPU limit 8 while using all 16 configured workers in
  both 2.0x cells, directly proving removal of the second clamp.
