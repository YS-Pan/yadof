# File blueprint: ui/heatmap.py

## Intent

Own the cross-generation audit tab's controls and state without performing backend
inference.

## Functionalities

- Construct error, quantity, and sample controls.
- Build deterministic `QuantityOption(label, kind, index)` mappings from workspace
  objective/rawData names.
- Validate sample percentage before requesting work.
- Show progress and emit Stop intent.
- Retain the last complete `CrossGenerationErrorAudit`.
- Derive the selected `ErrorMatrix` and delegate drawing.
- Restore prior complete output after cancellation.

## I/O Format

`on_calculate` receives a validated percentage from 1 through 100. `on_stop` takes
no arguments. State transitions accept progress triples or one complete audit.

Quantity kinds are `cost` or `rawdata`; an index of `None` means all items of that
kind.

## Non-Obvious Techniques

- Combo text is presentation only; index-based options carry semantics.
- `begin_calculation()` does not clear `_audit`.
- `finish()` is the only calculation transition that replaces `_audit`.
- `cancelled()` redraws old state when available and otherwise restores the empty
  plot.
- Metric changes during calculation affect what will be shown on completion, not
  the backend work already running.

## Mutability Profile

Labels, widths, and progress copy may change. Independent error/quantity selection,
all/item mappings, percentage validation, cooperative Stop intent, and
last-complete preservation should remain stable.
