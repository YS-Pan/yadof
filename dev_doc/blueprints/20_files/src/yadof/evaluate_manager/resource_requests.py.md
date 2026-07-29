# File blueprint: src/yadof/evaluate_manager/resource_requests.py

## Intent

- Format one backend-neutral calibrated estimate as the concrete CPU, memory, and
  disk request for a generated HTCondor submit file.

## Functionalities

- Preserve `HTCONDOR_REQUEST_CPUS` as the user's scheduler request.
- Parse configured memory/disk quantities through the shared resource quantity
  helpers.
- Delegate history selection, backend-neutral measurement aliases, trimming, and
  bootstrap estimation to `resource_calibration.py`.
- Apply the extra disk multiplier after the selected disk amount.
- Fall back to configured request quantities when no usable metadata is present;
  do not write back to `key.py` or `all.py`.

## I/O Format

- Input: one `JobSpec`, one loaded config, and the shared resource estimator.
- Output: immutable `HTCondorResourceRequest` with CPU integer, one concrete
  MiB/KiB request, calibration source, and sample count. The text properties use
  HTCondor-compatible `MB` and `KB` units.

## Non-Obvious Techniques

- A resource request is a scheduling capacity, not time-weighted average use. CPU
  remains manual because changing an HFSS solver's configured parallelism changes
  a user-selected throughput policy rather than just a memory-like capacity limit.
- The HTCondor-only disk safety multiplier stays in this formatter even though the
  underlying disk estimate is backend-neutral.
- This module does not read recorded history directly; local and distributed modes
  must use the same selection and unit rules from `resource_calibration.py`.

## Mutability Profile

- History selection, unit parsing, measurement aliases, and calibration rules
  belong in `resource_calibration.py`. Held-job retry policy belongs only in
  `resource_retries.py`.
- Defaults belong in `package defaults and workspace config.py`; users may override the disk safety
  factor through the short key config.
