# 2026-07-20 11:56 - Batch Population Recording

## Context

A 200-individual stress test with roughly 215 KB of compressed rawData per sample
showed generation recording time growing with total archive size. Each individual
atomically copied `rawData.npz` and rewrote `indMeta.jsonl`, producing quadratic
campaign I/O.

## Change

- Added `record_job_results()` as an atomic multi-job recorded-data API.
- Added grouped rawData publication that validates every source, copies the existing
  archive once, appends all job members, and publishes once.
- Changed local and distributed population evaluation to defer completed results and
  derive all batch costs in one query.
- Retained the single-result path as a fallback when batch preparation or publication
  fails, preserving per-individual failure isolation.
- Added coverage proving a batch copies an existing archive only once and adjusted
  the recording-failure test to exercise the fallback path.

## Rationale

Atomic publication remains necessary, but its cost should be paid once per natural
evaluation batch rather than once per individual. This changes total archive copying
from population-size copies per generation to one.

## Impact

Single-job callers and stored schemas are unchanged. Population evaluation now holds
completed job results until the batch publication step. A global batch failure is
diagnosed and retried with the previous single-job behavior.

## Follow-Up

None.
