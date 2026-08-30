# File blueprint: src/yadof/recorded_data/query.py

## Intent

- Expose tolerant workspace-explicit reads over finalized evidence without
  relying on mutable aggregate files.

## Functionalities

- List/filter catalog records and derive normalized variables/current costs using
  current task code.
- Build compatibility cost/history/training results from `EvidenceDataset` and
  `CostTable` identity joins while retaining existing public tuple/dict shapes.
- Load rawData samples, assemble surrogate training bundles, and report bounded
  segment/candidate diagnostics.
- Preserve direct NPZ basenames through `get_named_rawdata_samples()` and expose
  copied JSON-safe job metadata through `get_record_metadata()`. Hierarchical
  and PCA/SVD training bundles align direct job names, filenames, and metadata to
  the same accepted historical rows so training provenance is stable; neither
  view mutates a segment.
- Expose a cost-view history snapshot whose batches carry already decoded and
  schema-validated evidence from one open segment.
- Skip malformed, missing, incompatible, or non-finite candidates while preserving
  readable siblings and stable record order.

## Invariants

- Temporary and unrelated files are ignored.
- Public reads perform no repair, overwrite, or publication.
- Derived values are recalculated under the caller's current task interpretation;
  durable evidence remains unchanged.
- Duplicate job names/designs and reordered views cannot misalign rawData,
  metadata, normalized variables, or costs because internal alignment uses row ID.
