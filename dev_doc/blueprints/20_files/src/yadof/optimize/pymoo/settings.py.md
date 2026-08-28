# File blueprint: src/yadof/optimize/pymoo/settings.py

## Intent

- Hold the private immutable pymoo operator/refill/reference-direction snapshot
  constructed by `pymoo_ga()` or `pymoo_nsga3()`.

## Invariants

- Standard-library only and safe to import without pymoo.
- GA drops NSGA-III-only values; NSGA-III validates its method and optional positive
  partition count at construction.
- This type is implementation detail, not a workspace-author compatibility surface.
