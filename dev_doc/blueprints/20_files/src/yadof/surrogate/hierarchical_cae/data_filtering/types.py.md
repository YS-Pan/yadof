# File blueprint: src/yadof/surrogate/hierarchical_cae/data_filtering/types.py

## Intent

- Keep mode-neutral assessment and applicability containers independent of every
  concrete filtering implementation.

## Functionalities

- Represent aligned design-by-field weights, shared masks, residual/applicability
  targets, regime labels, and bounded diagnostics.
- Produce the uniform immutable assessment used by default mode `none` without
  routing through a concrete filter.
- Carry uncalibrated member-level applicability predictions into the calibration
  boundary without importing Torch.

## Invariants

- Future modes depend on these common types, not on `frequency.py`.
- The uniform assessment preserves every design and field with unit weights.
