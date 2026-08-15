# 2026-08-15 17:05 - Link Recording Guard To Migration Source

## Context

- The loss-tolerant recording consistency guard may expose defects caused by the
  recent development-environment migration.
- The user requested a direct link to the pre-migration project so future diagnosis
  can compare the two trees efficiently.

## Change

- Added the relative local link to `20260719 test package` in the persistent
  recording-consistency automatic toDo.
- Marked the old project as historical comparison material rather than an
  authoritative source that can override current code, documentation, or recording
  contracts.

## Impact

- Future bounded consistency checks can locate the supplied old implementation
  without rediscovering its machine path.
- No runtime code, public behavior, or toDo trigger/obsolete rule changed; software
  tests are not applicable.
