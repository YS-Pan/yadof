# File blueprint: src/yadof/evaluate_manager/resource_calibration.py

## Intent

- Provide one backend-neutral contract for turning recorded job resource evidence
  into conservative per-job CPU, memory, and disk estimates.

## Functionalities

- Parse configured memory and disk quantities into MiB and KiB.
- Prefer common `resource_*` metadata while accepting legacy local and Condor
  aliases.
- Use completed unindexed smoke records for generation zero and completed records
  from the preceding generation of the same run thereafter.
- Trim the configured fraction of highest measurements, retain at least one
  sample, and select the largest remaining value.
- Apply the bootstrap multiplier between smoke and generation zero for memory and
  disk; CPU calibration is enabled only when requested by the caller.
- Return estimate provenance and sample count without mutating workspace config.

## I/O Format

- Input: a loaded config, generation/run identity, configured fallback resources,
  an autodetection flag, a CPU-calibration policy, and an optional disk multiplier.
- Recorded common keys: `resource_cpu_usage_cores`,
  `resource_memory_usage_mib`, and `resource_disk_usage_kib`.
- Legacy fallback keys: corresponding `local_*` and `condor_*` resource fields.
- Output: immutable `ResourceEstimate` and `ResourceCalibration` values.

## Non-Obvious Techniques

- History selection is intentionally backend-neutral so a distributed smoke test
  can calibrate a later local generation, and vice versa.
- The high-tail trim removes `ceil(n * fraction)` values while always retaining
  one. With the default 5%, 20 samples discard only the largest sample.
- Memory, disk, and CPU series are calibrated independently; one missing field
  does not discard other useful measurements.
- HTCondor keeps CPU requests manual by calling the estimator with
  `calibrate_cpus=False`; local capacity planning opts into CPU evidence.
- When launch smoke is disabled, configured memory/disk values act as synthetic
  smoke evidence for generation zero.

## Mutability Profile

- Changes to record selection, aliases, unit parsing, or bootstrap/trim behavior
  affect both execution backends and require focused cross-backend tests.
- Host-capacity discovery and process-tree measurement belong in
  `local_resources.py`; scheduler formatting belongs in `resource_requests.py`.

