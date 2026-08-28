# 2026-08-28 14:15 - Group qNEHVI implementation into a subpackage

## Context

The qNEHVI acquisition, lightweight scoring boundary, and optional BoTorch
numerical implementation had grown into three flat files in `yadof.optimize`,
while the other multi-file optimization components already used private
algorithm-owned subpackages.

## Change

- Moved the qNEHVI implementation under `yadof.optimize.qnehvi` as
  `acquisition.py`, `backend.py`, and `_botorch_backend.py`.
- Kept `yadof.optimize.qnehvi()` as the public callable factory by preloading the
  private package before rebinding the parent attribute, matching the existing
  GPSAF package pattern.
- Updated package-internal imports, maintained tests, wheel-membership assertions,
  architecture, blueprints, and user wording. Frozen benchmark runners,
  preregistration plans, and receipts were left unchanged.

## Rationale

The directory now exposes one explicit ownership boundary for the acquisition
family without adding a registry, compatibility forwarding modules, or another
public configuration path. The exact `qnehvi` name remains more accurate than a
generic `ehvi` package, and the heavy backend remains lazy.

## Impact

Workspace composition through `from yadof.optimize import qnehvi` is unchanged.
The former flat implementation-module paths were private and are intentionally
replaced by the new subpackage paths. Historical frozen evidence continues to
refer to the source layout against which it was sealed.
