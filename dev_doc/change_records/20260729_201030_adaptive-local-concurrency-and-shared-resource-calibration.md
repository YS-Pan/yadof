# Adaptive local concurrency and shared resource calibration

## Context

Local execution defaulted to one worker and used only a fixed configured maximum.
HTCondor already calibrated memory and disk requests from smoke/prior-generation
records, but those history and trimming rules were embedded in a scheduler-specific
module. Local workflow subprocesses can also create resource-heavy child process
trees, so measuring only the immediate Python process would be misleading.

## Change

- Raised `LOCAL_EVALUATION_MAX_WORKERS` from 1 to 8.
- Added local resource autodetection and a configurable 15% host reserve.
- Added a shared backend-neutral resource calibration module used by local and
  HTCondor planning.
- Added local capacity planning from population size, configured cap, physical
  CPUs, available memory, and free jobs-disk space.
- Added recursive process-tree CPU/memory monitoring and finished job-directory
  disk measurement through the core `psutil` dependency.
- Added common resource metadata keys so evidence can calibrate either backend,
  while retaining backend-specific compatibility keys.
- Added progress and job metadata that explain the selected worker count and each
  limiting capacity.
- Added deterministic adaptation, cross-backend calibration, packaged smoke,
  config-default, and package-content coverage.

## Rationale

A configured cap is still necessary for licenses and operator policy, but it should
not force every machine to the same unsafe or underutilized concurrency. One
calibration contract also prevents local and distributed modes from drifting in
their record-selection, unit, and bootstrap behavior.

## Impact

Normal local runs can now use up to eight concurrent simulations by default, but
the effective number is recalculated for every dispatch and can be lower. Existing
workspaces can disable local autodetection or set a smaller cap. Smoke execution
remains serial. HTCondor CPU requests remain explicitly configured; only local
capacity planning consumes measured CPU evidence.

## Follow-up

Sites with restrictive simulator-license counts should set
`LOCAL_EVALUATION_MAX_WORKERS` to the number of locally available licenses. Future
resource dimensions should be added to the shared calibration contract before
backend-specific formatting.
