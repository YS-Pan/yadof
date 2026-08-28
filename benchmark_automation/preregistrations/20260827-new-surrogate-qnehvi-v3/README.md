# Gate 0 v3: diagnostic-path correction before validation metrics

Gate 0 v3 is an append-only amendment to v1 and v2. It does not change the
dataset campaign, design identity, split algorithm, model seeds, metric set,
four anti-noise ablations, or null numeric threshold template.

The first authorized row loaded through the sealed **development** locator
showed that the Chrono fast runner stores simulator diagnostics below
`job_metadata.task_diagnostics.child`. The v2 task policy expected those keys
directly below `task_diagnostics`. The v3 policy increments its version and
corrects only this declarative path before any validation metric, calibration
locator, or offline-test locator access.

Run `validate.py --dataset-manifest <sealed_dataset_manifest.json>` to verify
the complete parent chain, policy semantics, committed receipt, and external
sealed dataset. A passing validator does not authorize offline-test access;
numeric acceptance thresholds remain unsealed until legal validation evidence
exists.
# Historical preregistration

This directory is retained as historical plan/evidence only. Its executable
validator was retired on 2026-08-28 because current source, wheel, and artifact
digests are provenance—not gates on historical conclusions. Commands below
describe the former workflow and are no longer available at current HEAD.
