# File blueprint: project/evaluate_manager/resource_requests.py

## Intent

- Turn recorded HTCondor resource measurements into the concrete memory and disk
  lines for one generated submit file without automating CPU policy.

## Functionalities

- Preserve `HTCONDOR_REQUEST_CPUS` as the user's scheduler request.
- Parse configured memory/disk quantities into Condor's MiB/KiB units.
- Use unindexed distributed smoke records for generation zero; use the previous
  generation from the same optimizer run for later generations.
- Remove the highest configured fraction of each measurement series, select the
  remaining maximum, and apply the bootstrap multiplier only between smoke and
  generation zero.
- Apply the extra disk multiplier after the selected disk amount.
- Fall back to configured bootstrap quantities when no usable HTCondor metadata is
  present; do not write back to `key.py` or `all.py`.
- When the launch smoke test is disabled, treat the configured memory/disk quantities as synthetic smoke measurements and apply the normal generation-zero bootstrap multiplier.

## I/O Format

- Input: one `JobSpec` and the public `recorded_data.api.list_records()` rows.
- Relevant recorded metadata fields: `engine = "htcondor"`,
  `condor_memory_usage_mib`, and `condor_disk_usage_kib`.
- Output: immutable `HTCondorResourceRequest` with CPU integer, one concrete
  MiB/KiB request, calibration source, and sample count. The text properties use
  HTCondor-compatible `MB` and `KB` units.

## Non-Obvious Techniques

- The trim operation removes `ceil(n * fraction)` largest values while always
  retaining at least one measurement. With the default 5%, 20 samples discard the
  largest one and use the nineteenth value.
- Disk calibration is separate from memory calibration, so an absent disk reading
  does not discard a valid memory calibration (and vice versa).
- A resource request is a scheduling capacity, not time-weighted average use. CPU
  remains manual because changing an HFSS solver's configured parallelism changes
  a user-selected throughput policy rather than just a memory-like capacity limit.

## Mutability Profile

- Quantity parsing and history-selection rules are shared backend contracts and
  require focused unit tests for changes. Held-job retry policy belongs only in
  `resource_retries.py`.
- Defaults belong in `project/config/all.py`; users may override the disk safety
  factor through the short key config.
