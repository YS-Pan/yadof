# Module blueprint: tests

## Intent

Verify the viewer's deterministic contracts without requiring a live simulator,
optimization, or full model audit in the default suite.

## Functionalities

- Check valid checkpoint discovery, sorting, and malformed-file skipping.
- Check rawData curve axis selection and nearest-zero slicing.
- Check ensemble mean/std derivation.
- Check Tcl-only popup ancestry safety.
- Check instant aggregate switching across relative/absolute, cost/rawData, all,
  and item-specific quantities.
- Check per-generation random sampling counts and uniqueness.
- Check cooperative cancellation before work begins.

## I/O Format

Tests use temporary checkpoint JSON, synthetic NumPy rawData items, immutable
backend dataclasses, and `threading.Event`. They import through
`yadof.tools.surrogate_viewer.backend` where the public viewer-local surface is
under test.

## Non-Obvious Techniques

- Maintained tests live in yadof's top-level `tests/test_surrogate_viewer.py` and
  use the repository's standard pytest temporary-root configuration.
- Viewer-specific tests skip as a group when optional Torch or Matplotlib
  dependencies are unavailable; parser/help/artifact tests still run core-only.
- GUI module imports may be tested without opening a visible window. A hidden Tk
  smoke is appropriate for component behavior but should not make the default
  suite depend on a display where avoidable.
- Real-workspace audit and CUDA utilization measurements are integration checks,
  not default unit tests.

## Mutability Profile

Add focused tests when contracts expand. Keep packaging and lazy CLI coverage in
yadof's generic package tests. Avoid snapshots tied to incidental widget geometry
or exact Matplotlib internals unless those details implement an explicit user
requirement.
