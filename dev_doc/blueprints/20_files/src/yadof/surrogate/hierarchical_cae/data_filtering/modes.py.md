# File blueprint: src/yadof/surrogate/hierarchical_cae/data_filtering/modes.py

## Intent

- Own the single hierarchical-CAE data-filter mode selector and dispatch without a
  global registry or ambient configuration.

## Functionalities

- Normalize the supported mode strings `none` and `frequency`.
- Reject a frequency filter in `none` mode and require one in `frequency` mode.
- Produce the mode-neutral uniform no-filter assessment or delegate to the
  frequency-filter implementation while leaving source samples immutable.

## Invariants

- `none` is the public factory default.
- There is no implicit policy-based mode inference or compatibility alias.
- A future mode adds one local implementation and explicit dispatch branch with its
  complete semantic configuration; it does not add central campaign config.
