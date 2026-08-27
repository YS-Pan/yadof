# File blueprint: src/yadof/surrogate/hierarchical_cae/__init__.py

## Intent

- Mark the private implementation package without eagerly importing Torch-backed
  modeling/runtime code.

## Invariants

- Public construction remains in `yadof.surrogate.api`.
- Importing `yadof.surrogate` stays lazy with respect to Torch execution modules.
