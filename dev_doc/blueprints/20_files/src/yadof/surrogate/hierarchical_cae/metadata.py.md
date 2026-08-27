# File blueprint: src/yadof/surrogate/hierarchical_cae/metadata.py

## Intent

- Publish bounded immutable training events for hierarchical CAE runs.

## Functionalities

- Record generation, namespace/signature, sample/member counts, timings, training
  history summaries, quality diagnostics, and checkpoint paths as JSON-safe events.

## Invariants

- Metadata is diagnostic derived state, not recorded evidence or an active pointer.
- Publication failures remain visible and cannot expose a partial checkpoint.
