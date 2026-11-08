# File blueprint: backend/hierarchical_checkpoints.py

## Intent

Adapt one committed hierarchical-CAE checkpoint into the viewer's existing
read-only predictor contract without making the UI depend on surrogate internals or
changing full-grid authority.

## Functionalities

- Discover only committed `hierarchical-cae` namespace manifests inside the active
  strategy and validate method, training policy, semantic signature, and artifact
  paths.
- Rebuild the exact field schema, declared layouts/axis encodings, scalers, train
  configuration, and model bundle from installed yadof code.
- Predict full-grid mean/member rawData for interactive cost calculation and audit.
- For a coordinate-enabled architecture-v2 checkpoint, query one field at explicit
  in-domain coordinates across every declared axis and return immutable plot-only
  mean/member values.
- Preserve predictor-member identity and reject schema, selector, rank, domain, or
  capability mismatches explicitly.

## I/O Format

The adapter implements the same viewer-local `predict()`, `predict_plot()`, and
`predict_audit_rows()` shapes as the conditional predictor. Coordinate plots retain
the requested output-axis shape and member axis; full-grid predictions retain the
checkpoint field templates used by current cost and audit code.

## Non-Obvious Techniques

- Full-grid decoding is always used for cost, audit, and stored-grid selections.
  Coordinate readout is additive and cannot reconstruct or overwrite authoritative
  rawData.
- All-axis coordinates are encoded by the owning hierarchical-CAE package from
  checkpoint declarations. The viewer does not infer linear/log/periodic semantics.
- Query-state digests must remain unchanged; viewer inference never publishes a
  checkpoint or training state.
- The current model is `experimental / performance-not-accepted`. Adapter
  availability is a mechanism claim, not scientific acceptance.

## Mutability Profile

Checkpoint method/version/schema changes require an explicit coordinated reader
change. Read-only behavior, method isolation, full-grid authority, in-domain
validation, and no fabricated recorded truth remain stable.
