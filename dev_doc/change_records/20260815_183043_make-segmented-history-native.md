# 2026-08-15 18:30 - Make Segmented History Native

## Context

- Immutable segmented recording was already the only supported history path, but
  source module names, the workspace directory layout, error text, tests, and
  documentation still carried a release-transition label.
- The migrated SAW workspace had subsequently produced 2,401 current records in
  176 segments plus 50 metadata events, so its evidence needed an explicit,
  loss-checked layout migration rather than deletion or a cold restart.
- Two user commits made after the earlier migration changed progress output and
  time-view axis units; their patches contained no recording release-marker design.

## Change

- Renamed the query, rawData ownership, record publication, test, and blueprint
  files directly by responsibility and updated every live import and artifact
  assertion.
- Made `recorded_data/segments/` and `recorded_data/metadata/` the native storage
  roots. History clearing now targets those two exact generated directories while
  preserving unrelated recorded-data entries.
- Removed the recorded-data format number from segment manifests and the
  recorded-data schema number from candidate/event JSON. Stable manifest identity,
  structural/member validation, and the independent rawData NPZ schema remain.
- Updated current architecture, blueprints, terminology, user guidance, historical
  labels, and the migrated workspace README to describe the native layout.
- Reworded incidental numbered-value examples in source comments so maintained
  Python code contains no misleading release-like token.
- Added the persistent automatic toDo for removing incidental release-transition
  markers and completed its first bounded execution.
- Migrated the SAW workspace in place while its campaign lock was inactive. The
  migrated result retained 2,401 candidates, 4,802 NPZ members, and 50 events; the
  NPZ evidence digest remained
  `a240cff2c24569017cc32408a320cbf90c0495344636649f68efcde3ce72cc40`.

## Rationale

- Responsibility-based names and direct generated paths describe the actual
  feature without forcing a new workspace to understand a superseded release
  transition.
- Recorded-data version numbering did not provide a supported negotiation or
  migration surface. Removing that layer is clearer than renumbering it, while the
  validations that protect evidence remain intact.

## Impact

- Public `yadof.recorded_data` behavior remains workspace-explicit and
  loss-tolerant, but internal module import paths and generated storage paths are
  now neutral.
- The modified 0.3.0 wheel was force-reinstalled into the sibling `.venv` and its
  import origin was verified below site-packages.
- The installed package read all 2,401 migrated results; workspace check and cost
  view completed with zero ignored history issues. Targeted recording/backend tests
  passed 45 tests, package-foundation tests passed 6 tests, and the full suite
  passed 239 tests.

## Follow-Up

- Keep the new automatic toDo active for future bounded checks.
