# File blueprint: src/yadof/optimize/pymoo/backend.py

## Intent
- Isolate optional pymoo imports and adapters used by optimization algorithms.

## Functionalities
- Lazily construct pymoo algorithms, problems, populations, operators, and
  survival helpers.
- Translate between normalized yadof rows and pymoo representations.
- Expose the small adapter surface used by common search and GPSAF phases.

## I/O Format
- Accepts normalized bounds, populations, objective rows, core candidate-identity
  policy, and one immutable `PymooSearchSettings` snapshot.
- Returns pymoo-backed search contexts or normalized candidate rows through local
  adapter dataclasses.

## Non-Obvious Techniques
- Keeping this module in a separate private subpackage prevents importing the
  optional pymoo dependency when users import `yadof.optimize`.

## Mutability Profile
- Pymoo-version details stay here; public optimization factories and workspace
  contracts must not expose pymoo objects.
- Operator, refill, and reference-direction values have no fallback lookup in
  `LoadedConfig`; the selected factory snapshot is authoritative.
