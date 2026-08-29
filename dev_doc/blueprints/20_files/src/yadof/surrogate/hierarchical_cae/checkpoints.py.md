# File blueprint: src/yadof/surrogate/hierarchical_cae/checkpoints.py

## Intent

- Publish and recover hierarchical CAE state atomically in a component-specific
  strategy namespace.

## Functionalities

- Hash parameter definitions, schema/layout/axes/groups/scalers, full train config,
  selected data-filter mode and frequency-filter declaration, head/loss semantics, backend
  version, and strategy identity.
- Stage the minimal model/scaler/schema bundle, atomically publish its artifact tree,
  and commit a namespace manifest and convenience pointer.
- Delegate component-neutral namespace/path allocation and atomic JSON replacement
  to `surrogate._shared.artifacts` while retaining CAE payload/identity policy.
- Recover only complete compatible publications; retain incompatible/interrupted
  artifacts without activating them.

## Invariants

- Checkpoints never copy training rawData.
- Conditional-INR paths and signatures are not reused or overwritten.
- Filter/version or any anti-noise switch change forces a different state signature.
