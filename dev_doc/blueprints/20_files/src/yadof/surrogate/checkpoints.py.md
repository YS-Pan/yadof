# File blueprint: src/yadof/surrogate/checkpoints.py

## Intent
- Own surrogate checkpoint and auxiliary artifact serialization.

## Functionalities
- Compute a semantic state signature over active strategy, format/method/policy, parameters,
  rawData schema/query tables, train config, and relevant runtime version.
- Stage and atomically rename one complete artifact tree, write the root generation
  convenience pointer, then atomically write a unique namespaced manifest as the
  publication commit record.
- Write `model_aux.npz` with query tables, field ids, sample count, and target scaling.
- Convert `RawDataSchema` and train config into JSON-safe summaries.

## I/O Format
- Root `generation_*.json` is a convenience pointer, not the recovery commit source.
- Immutable publication artifacts and committed unique manifests live below
  `runs/strategy-<signature>/components/conditional-inr/`.
- Manifests explicitly declare `format_version`, `surrogate_method`,
  `training_policy`, strategy and state signatures, and run/component namespaces.

## Non-Obvious Techniques
- Member model weights are saved by `modeling.py`; this file writes the runtime-level summary and auxiliary arrays.
- Checkpoint summaries should describe rawData-first prediction and never store surrogate-predicted evaluation history as durable truth.
- A failed publication may leave an inactive artifact or an uncommitted root pointer,
  but cannot create a discoverable namespace commit for a partial checkpoint.

## Mutability Profile
- This format has no legacy fallback reader. A format/method/policy/signature mismatch
  is cold-train behavior, not an invitation to guess compatibility.
