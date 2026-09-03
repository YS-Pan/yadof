# File blueprint: src/yadof/optimize/gpsaf/settings.py

## Intent

- Hold the private frozen alpha/beta/gamma/exploration/infill-policy snapshot constructed by
  `gpsaf_settings()`.

## Invariants

- Alpha and beta are non-negative integers; gamma is finite and nonnegative;
  exploration is a finite fraction. Validation is eager and standard-library only.
- Infill selection defaults to `hypervolume`; explicit `cluster` retains the
  original PKT/gamma policy. Omitted and explicit hypervolume settings are equal.
- Training freshness is deliberately absent because it remains core campaign policy.
