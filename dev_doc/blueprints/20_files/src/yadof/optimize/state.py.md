# File blueprint: src/yadof/optimize/state.py

## Intent

- Publish/read the one active semantic strategy pointer while retaining every
  inactive strategy/component artifact.
- Publish/read the strict explicit-program complete-generation boundary.

## Functionalities

- Derive `strategy-<signature-prefix>` from a validated SHA-256 signature.
- Atomically write `.yadof/optimization/active.json` with semantic identity and a
  separate optimization source hash.
- Atomically write `.yadof/optimization/program-completion.json` with schema,
  program semantic signature, last complete generation, frozen source fingerprint,
  task snapshot ID, and timestamp.

## Invariants

- The pointer selects one active strategy but never deletes, migrates, or reads
  legacy component artifacts.
- Source hash inequality alone does not change semantic state compatibility or
  invalidate recorded real evidence.
- The completion pointer advances only after normal generation commit and contains
  no user, candidate, prediction, rawData, or backend continuation payload.
- A strategy that consumes joint rawData posterior samples must include the
  protocol version, posterior/backend version, and all effective posterior
  parameters in this semantic identity. Merely installing the protocol leaves the
  current conditional-INR/GPSAF identity unchanged.
