# 2026-07-18 10:36 - Split Package Conversion Into Ordered Stages

## Context

- The package/workspace conversion plan and its follow-up `yadof run` plan were too
  large to execute safely as single manual toDos.
- The plans overlapped: the master package document required a CLI, while the run
  document was gated on completion of the package conversion.
- Reading the automatic config-layout follow-up also showed that its explicit
  two-day lifetime had expired after 2026-07-17 20:42:10 local time.

## Change

- Archived the two original manual plans under `dev_doc/obsolete/` with their full
  requirement text retained.
- Replaced them with ten ordered manual toDos covering build/resources, workspace
  loaders, init/check, local jobs, recorded data, optimize/surrogate, user tools,
  distributed execution, run/optional smoke, and final installed-artifact/docs audit.
- Positioned `yadof run` after the runtime/package migrations but before the final
  packaging audit, removing the circular completion dependency.
- Archived the expired automatic config-layout follow-up according to its obsolete
  rule.

## Rationale

- Each successor now has a bounded implementation surface, explicit prerequisite,
  focused verification, and completion handoff while preserving the two archived
  documents as an audit checklist.
- The order makes the package/workspace boundary testable early and delays deletion
  of legacy launch paths until their installed replacements are verified.

## Impact

- Only future-work organization and archival documentation changed; no current
  runtime, architecture, module contract, user workflow, or terminology changed.
- Future agents should execute the successor files in timestamp order and archive
  each completed step before triggering the next.

## Follow-Up

- Begin with `dev_doc/toDo/20260718_103600_package-01-build-and-resource-foundation.md`
  when the user explicitly requests the package conversion sequence.
