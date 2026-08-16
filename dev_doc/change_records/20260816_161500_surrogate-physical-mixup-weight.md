# 2026-08-16 16:15 - Make Surrogate Mixup a Low-Weight Physical Prior

## Context

- The rawData INR gave mixup loss the same coefficient as direct evaluated-data
  loss.  That is an unnecessarily strong linear-interpolation assumption for
  physical responses with moving resonances, extrema, and threshold crossings.
- A fixed SAW holdout experiment exposed low average-cost ranking accuracy even
  though the rawData-first execution and cost path were valid.

## Change

- Added validated `SURROGATE_INR_MIXUP_WEIGHT`, with a default of `0.10` and
  support for `0.0` to disable mixup.
- Applied the coefficient only to the mixup loss and exposed it in training
  history.
- Documented task-level selection guidance and refreshed surrogate blueprints.

## Rationale

- Direct simulator rawData is the evidence the surrogate must fit.  A small mixup
  coefficient can regularize sparse interpolation without letting synthetic linear
  targets erase sharply nonlinear response structure.

## Impact

- Existing workspaces receive the safer default without task-file changes and can
  tune or disable the prior in `config.py`.
- Checkpoints preserve the selected train configuration through the existing model
  artifact metadata.

## Follow-Up

- Compare physical and synthetic holdout accuracy after wheel installation; retain
  task-specific rawData importance masks only when they improve the same evidence.
