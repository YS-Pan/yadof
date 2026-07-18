# 2026-07-18 20:30 - Package Distributed Worker Execution

## Context

- Local execution used package support plus workspace payload, but HTCondor still
  depended on repository modules and could not diagnose an incompatible worker
  installation early.

## Change

- Copied and adapted the HTCondor runner, resource requests/retries, and time-limit
  modules into `yadof.evaluate_manager`, all using the selected workspace config and
  history.
- Added distributed population and smoke dispatch with per-individual failure
  isolation, final ClassAd/resource metadata, bounded memory/disk retries,
  generation calibration, deadlines, and unlimited smoke jobs.
- Prepared jobs now transfer a package-owned bootstrap and effective config
  provenance. The bootstrap records a worker failure before workflow startup when
  `yadof` is missing or its version differs.
- Added mocked tests for submit composition, callback and tuple parity, failures,
  version/missing-package diagnostics, calibration, timeout, and retries.

## Rationale

- Using the same prepared-job contract for local and distributed modes keeps task
  payload and evidence semantics consistent without writing to installed files.

## Impact

- `yadof smoke-test --mode distributed` and distributed optimization are available
  from an installed package; HTCondor pool administration remains outside yadof.
