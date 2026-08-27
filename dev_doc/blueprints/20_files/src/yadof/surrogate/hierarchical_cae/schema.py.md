# File blueprint: src/yadof/surrogate/hierarchical_cae/schema.py

## Intent

- Convert complete named rawData samples to and from fixed field tensors without
  losing selector, dtype, shape, axis, or metadata identity.

## Functionalities

- Normalize selector-keyed groups, rank-3 layouts, and per-axis encodings.
- Select scalar MLP, Conv1d, or Conv2d layouts; reject unsupported complex,
  variable-schema, or undeclared rank-3 inputs.
- Fit per-field scalers, create standardized matrices, and reconstruct exact
  schema-compatible samples in canonical order.

## Invariants

- Point count never changes field identity or macro weight.
- Rank-3 channel/spatial roles are never inferred from dimension length.
- Reconstructed axes and non-main metadata come only from the frozen template.
