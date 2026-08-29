# File blueprint: src/yadof/surrogate/hierarchical_cae/types.py

## Intent

- Hold immutable data/schema/config/runtime-state types for the hierarchical CAE.

## Functionalities

- Represent named design-level training rows and aligned record metadata.
- Represent explicit axis encodings, selector-keyed codec layouts, field scalers,
  groups, and the complete hierarchical schema.
- Validate training, robust-loss, regime-head, ablation, batching, and sharing
  configuration; retain the recoverable in-memory state descriptor.

## Invariants

- Rank/layout and axis roles are explicit and stable-selector keyed.
- Every behavior-changing head/loss/filter switch is serializable identity state.
- `coordinate_readout` remains false for the Gate 0 v5 failed MVP.
