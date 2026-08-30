# Add identity-preserving evidence and cost views

## Context

Recorded evidence already had a durable candidate identity, but public historical
results exposed parallel tuples keyed only by job name and position. Optimizer
history and surrogate-training compatibility assembly therefore discarded evidence
identity, interpretation identity, typed failure status, and transform lineage.
RawData, execution outcome, and current-task cost also have different lifetimes and
must not be collapsed into one persisted row or premature `inf` value.

## Decision

Introduce an immutable `EvidenceDataset` over the existing durable segment catalog
and live campaign state, plus a separate task/objective-schema-bound `CostTable`.
Original `candidate_id`, `evidence_id`, and `row_id` are identical; a canonical
`design_key` may match repeated physical designs but never becomes sample identity.
Cost and history consumers join by row ID. Interpretation status remains
`succeeded`, `failed`, `not_applicable`, or `missing` until the explicit optimizer
conversion maps non-successful rows to correct-width `inf`.

Committed rawData remains behind lazy segment references. Cost calculation uses one
frozen interpreter and materializes/releases at most one row at a time. Explicit
rawData transforms create owned transient rows with deterministic
parent/operation/parameter/ordinal/content lineage; they do not publish segments or
enter committed optimizer history.

## Implementation

- Added `recorded_data/dataset.py` with frozen evidence, lineage, rawData-handle,
  cost, and joined-row value types plus durable/live construction,
  reinterpretation, and derived-row APIs.
- Exported the new public surface through `yadof.recorded_data`; added live
  `CampaignSession.evidence_dataset()` and `cost_table()` views with
  same-fingerprint interpretation hints and no segment mutation.
- Rebuilt historical cost/result and surrogate-training compatibility queries from
  identity joins while preserving their public tuple/dict shapes.
- Extended `HistoryRecord` with default candidate/row/design/interpretation fields
  and restricted current history to successful committed original evidence.
- Added 12 direct acceptance tests and the wheel member assertion, and synchronized
  C4/4+1 architecture, module/file blueprints, terminology, and user guidance.

No recorded-data ZIP member/layout, parameter/objective width policy, generation
loop, surrogate fit implementation, search composition, or GPSAF setting changed.
GPSAF `gamma=0.5` remained present in factory input, strategy identity, and runtime
diagnostics.

## Verification and evidence

- Built `yadof-0.4.2-py3-none-any.whl`, force-reinstalled it without dependencies,
  and confirmed `yadof.__file__` under the outer `.venv/Lib/site-packages`.
- New direct tests passed `12/12`; the recording/session review set passed `37/37`;
  the focused recording/optimization/package suite passed `76/76` after restoring
  the existing `session.job_template_api` monkeypatch seam.
- The final installed-package suite passed `400 passed in 81.00s` with a fresh
  absolute pytest base directory and the cache provider disabled.
- The fresh 20 x 2 smoke workspace was collected/valid with
  `40/40/40` attempted/completed/finite evaluations, complete generation zero, and
  matching objective/rawData contracts.
- The single authorized fresh 100 x 20 measured workspace was collected/valid with
  `2000/2000/2000` attempted/completed/finite evaluations, 20 generation records,
  generation zero `100/100`, matching objective/rawData contracts, zero issues, and
  runtime `539.1970091 s`. Descriptive final hypervolume was
  `0.19862125778923248`; it was not an improvement gate.
- Smoke and measured strategy source SHA-256 was
  `08E4BE42C4E4A8D377866BF8BC21765A0B776A27C32823290F97210FE086CBA7`.
  Evidence workspaces are
  `temp/20260831_002328-stage2-benchmark-smoke` and
  `temp/20260831_002514-stage2-benchmark-measured`.

## Automatic TODO check

The reliable-recording consistency check was naturally in scope. Direct tests
confirmed that pending rows have no readable handle, committed live rows reuse
durable references, view construction creates no second persistence path, corrupt
entries remain isolated, and only successful committed originals enter optimizer
history; no additional inconsistency remained.

The bounded redundancy check triggered and completed in the touched history path:
the session-local raw-variable tuple helper and duplicated cost-replay loop were
removed in favor of the shared dataset/cost-table implementation, while the
existing public compatibility shapes and monkeypatch seam were retained and
verified. The release-marker check found no incidental transition marker; the
semantic rawData digest domain tag is a real content-contract identifier. The
component-configuration check found no new uppercase key, alias, settings entry, or
runtime fallback; the benchmark continued to use explicit strategy factory kwargs.
All four recurring automatic TODOs remain active.
