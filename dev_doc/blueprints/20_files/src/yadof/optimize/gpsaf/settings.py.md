# File blueprint: src/yadof/optimize/gpsaf/settings.py

## Intent

- Hold the private frozen alpha/beta/gamma/exploration snapshot constructed by
  `gpsaf()`.

## Invariants

- Alpha and beta are non-negative integers; gamma and exploration are finite
  fractions. Validation is eager and standard-library only.
- Training freshness is deliberately absent because it remains core campaign policy.
