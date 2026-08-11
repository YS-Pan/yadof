# 2026-08-11 16:33 - Refine View Legends And Generation Labels

## Context

- The shade-only hypervolume legend described both bounds with a long phrase that
  consumed too much horizontal space.
- Generation indices overlapped when many narrow generations were visible.
- The persistent packagify-inconsistency automatic toDo was explicitly retired by
  the user.

## Change

- Shortened the cost-view shade legend to `HV (all & current gen.)` while retaining
  the same cumulative-all versus current-generation meaning.
- Added a shared 0.05 axes-relative stagger: even generation labels remain at
  `0.98`, while odd labels render at `0.93`.
- Applied the generation-label placement to both cost and time views under their
  visual-alignment contract.
- Removed
  `dev_doc/toDo/auto/20260719_142114_report-packagify-inconsistencies.md` rather
  than archiving it, following the explicit retirement request.
- Updated focused tests, user guidance, root blueprints, and cost-viewer local
  blueprints.

## Rationale

- `current gen.` is short but unambiguous; `one gen.` could be read as an arbitrary
  generation rather than the generation active at each plotted endpoint.
- Alternating two stable vertical positions preserves every generation label and
  avoids data-dependent omission or rotation.
- Cost and time generation labels share one presentation contract, so changing
  only one view would create avoidable visual drift.

## Impact

- Cost plots have a narrower HV legend and denser generation sequences remain
  readable.
- Time plots receive only the matching label stagger; their data and axes are
  unchanged.
- One persistent automatic maintenance handoff is no longer active or packaged.

## Follow-Up

- None.
