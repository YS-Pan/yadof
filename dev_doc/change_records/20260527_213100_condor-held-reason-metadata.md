# 2026-05-27 21:31 - Condor Held Reason Metadata

## Context
- Distributed jobs could be recorded with only `HTCondor reported terminal state: held`, which hides the actionable hold reason from the job metadata.
- The submit machine can query `condor_q` while the job is still in the queue to retrieve `HoldReason`, `HoldReasonCode`, and `HoldReasonSubCode`.

## Change
- Added hold-detail querying in `project/evaluate_manager/condor_runner.py` when a submitted job reaches terminal reason `held`.
- Stored `condor_hold_reason`, `condor_hold_reason_code`, and `condor_hold_reason_subcode` in job metadata when available.
- Updated the evaluate-manager blueprint.

## Rationale
- Held jobs are external scheduler failures or runtime policy failures; the reason text is needed to distinguish memory, executable, path, credential, and process-exit causes.

## Impact
- New held jobs will have more actionable metadata.
- Existing held job metadata is not rewritten; use `condor_q -hold` or `condor_q <cluster>.0 -af HoldReason HoldReasonCode HoldReasonSubCode` for already-submitted jobs.
