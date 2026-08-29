# 2026-08-29 20:31 - Park Anti-Noise Hierarchical CAE Work

## Context

- The anti-noise Hierarchical CAE successor remained scientifically unaccepted
  after the frozen v5/v8 failures, while a separate completed refactor made
  Hierarchical CAE training-data filtering component-local, explicitly selectable
  as `frequency`, and disabled by default.
- The user decided to shelve the anti-noise successor temporarily and asked that
  the four related active toDos reflect the new dependency structure without
  treating the pause as success or erasing the frozen evidence.
- The existing summary title used the generic word `surrogate`, which obscured that
  its primary experimental component and release subject is Hierarchical CAE.

## Change

- Marked the anti-noise Hierarchical CAE successor toDo `PARKED`, recorded the
  current no-filter/frequency interface boundary, prohibited execution while
  parked, and defined explicit reactivation and archival conditions.
- Renamed the summary in prose to **Hierarchical CAE/qNEHVI control** and stated
  that its concrete surrogate is `HierarchicalCAEComponent` / `hierarchical_cae()`;
  conditional-INR and PCA/SVD retain their distinct baseline roles.
- Removed the parked anti-noise successor from the current execution path. The
  summary now permits independent PCA/SVD evidence work while keeping Hierarchical
  CAE performance acceptance, exact calibration, eligible qNEHVI, the complete
  seven-arm benchmark, and release intentionally blocked.
- Clarified in the PCA/SVD and Acquisition Capability Protocol toDos that the pause
  neither blocks PCA/SVD work nor triggers acquisition-protocol extraction.

## Rationale

- Separating an already implemented opt-in frequency filter from a future
  regime-specialized scientific successor prevents code organization from being
  misreported as performance evidence.
- Keeping all scientific gates fail-closed preserves the frozen failures and makes
  the consequence of the user's prioritization decision explicit rather than
  silently dropping required evidence.

## Impact

- No package code, public API, benchmark evidence, checkpoint, calibration artifact,
  or release decision changed.
- PCA/SVD measured evidence and formal-arm integration remain active independent
  work. The anti-noise successor is dormant until explicit user reactivation.
- Hierarchical CAE remains experimental/performance-not-accepted, and real qNEHVI
  exploitation remains unavailable behind the existing full-real fallback.

## Follow-Up

- To resume the anti-noise route, the user must explicitly reactivate it and a new
  preregistration must re-audit the current frequency-filter API and available
  evidence before any new test or calibration access.
- A different Hierarchical CAE successor requires its own approved, standalone
  toDo and preregistration before it can replace the parked route in the summary.
