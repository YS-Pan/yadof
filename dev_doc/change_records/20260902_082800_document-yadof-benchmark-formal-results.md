# 2026-09-02 08:28 - Document yadof Benchmark Formal Results

## Context

- The benchmark closure ledger recorded the acceptance gates and artifact
  identities, while the formal strategy metrics and their interpretation remained
  distributed across untracked runtime reports.
- The user requested a dedicated `dev_doc/context/` file that summarizes this
  benchmark result for future filename-targeted discovery.

## Change

- Added a focused context document for the 2026-09-01 formal complete campaign.
- Recorded the campaign configuration, terminal validity gates, three-seed final
  hypervolume and normalized HV-AUC observations, tolerated simulator failures,
  surrogate-training timings, supporting smoke/test evidence, concurrency
  decision, artifact locations, hashes, and provenance limitation.
- Clearly separated verified terminal facts from descriptive interpretation and
  stated that the evidence does not rank strategies or establish statistical or
  general scientific superiority.

## Rationale

- A specific time-named file lets future agents discover the formal result from
  its filename without opening a broad implementation ledger.
- Keeping the compact interpretation beside immutable artifact identities makes
  the external runtime evidence usable across sessions while preserving its
  limitations.

## Impact

- Documentation only: no code, test, package-resource mapping, public behavior,
  runtime artifact, or existing historical document changed.
- The new context file is historical evidence, not an instruction or pending-work
  queue.

## Follow-Up

- Any future strategy ranking or default change requires separately authorized
  evidence with an explicit statistical design; it must not be inferred from this
  three-seed descriptive campaign.
