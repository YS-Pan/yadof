# New surrogate and qNEHVI Gate 0 preregistration

This directory is the tracked Gate 0 input for the new rawData surrogate,
joint-posterior, and qNEHVI work. It freezes the decisions that must precede model
implementation and test-result access. It is deliberately not an executable suite
and contains no recorded design rows.

## Frozen artifacts

- `schema_inventory.json` records the exact field selectors, main keys, shapes,
  source-derived axis arrays and digests, dtype representation, per-design array
  bytes, parameter semantics, objective widths, rank-3 antenna layouts, explicit
  S11/gain groups, task fingerprints, and directly relevant source hashes.
- `data_availability_audit.json` defines legal recorded-evidence provenance and
  records the current gap. All three editable baseline manifests have zero records,
  no tracked history snapshot is selected, and the historical run summaries named
  by the operator README are not inspectable rawData in this checkout.
- `benchmark_preregistration.json` freezes design-level split identity and quotas,
  disjoint seeds, required offline/online comparisons, metrics, the registration
  resource block, stop rules, and the inputs allowed at each later gate.
- `acceptance_thresholds.template.json` freezes the numeric fields, derivation
  evidence, pass logic, and sealing order. Its values are intentionally null: no
  eligible 1000/2000-training-design data or model/resource pilot exists yet.
- `validate.py` checks all cross-file hashes, source fingerprints, parameter/field
  contracts, axis digests, benchmark configuration, seed derivation, split quotas,
  and the explicit blocked state without launching a simulator.

Run the validator from the yadof checkout root with the matching installed yadof:

```powershell
& "..\.venv\Scripts\python.exe" `
  ".\benchmark_automation\preregistrations\20260827-new-surrogate-qnehvi\validate.py" `
  --pretty
```

The correct Gate 0 result is `ok: true` together with
`formal_test_ready: false`. Formal readiness would be false-positive evidence
until both a versioned sealed dataset manifest and a versioned sealed numeric
threshold file exist.

## Data and authorization boundary

The schema inventory is source/schema evidence, not model-performance evidence.
`baseline.json` smoke shapes and costs cannot supply even one training design. A
future dataset must contain at least 2,800 unique compatible designs per case so
the frozen partitions can provide 2,000 nested training designs plus independent
validation, calibration, and test partitions.

Gate 0 does not authorize a real simulator campaign. A separately authorized run
may later supply immutable recorded evidence, but it needs its own run ID, run
specification, baseline snapshot, segment hashes, row/exclusion counts, and sealed
dataset manifest. Formal optimization comparison is a separate five-arm,
five-seed, three-case matrix with 2,000 attempted evaluations per cell; its 150,000
attempted evaluations require explicit authorization at Gate 6.

The Chrono resource block follows the existing adapter boundary: the outer yadof
environment names a separate interpreter through `YADOF_PYCHRONO_PYTHON`, and the
adapter crosses that boundary through its subprocess protocol. Gate 0 records
PyChrono 10.0.0 from that environment's Conda package record, including the build,
channel, record hash, and package hash, without importing the native module or
running a model. Preflight still governs whether the interpreter is usable for an
actual run.

## Threshold and test discipline

Numeric thresholds are sealed after train/validation/calibration and disjoint
threshold-pilot evidence, but before offline test access or formal optimization
launch. The sealed file must identify data, metrics, models, strategies, seeds,
and hardware. Changing a threshold after seeing test/formal results creates a new
experiment version and cannot make this preregistration pass retroactively.

The full-grid representation gate, posterior decision/calibration gate, qNEHVI
equal-budget gate, and engineering-cost gate must all pass for an opt-in
recommendation. Failure leaves the affected module experimental. It cannot be
bypassed with ensemble min/max summaries or a direct parameters-to-cost model.

## Next execution unit

The joint rawData posterior contract may begin after this validator passes in the
committed source tree. That next unit is limited to a lightweight persistent
function-sampler protocol, chunk/permutation invariance, structured fake rawData,
and a thin current-`CostInterpreter` projector. It does not require the missing
2,800-design datasets and must make no fitting, calibration, or optimization
performance claim.
