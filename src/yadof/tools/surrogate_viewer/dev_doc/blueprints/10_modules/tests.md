# Module blueprint: tests

## Intent

Verify the viewer's deterministic contracts without requiring a live simulator,
optimization, or full model audit in the default suite.

## Functionalities

- Check conditional-INR and hierarchical-CAE checkpoint discovery/dispatch, sorting,
  method isolation, and malformed-file skipping.
- Check scalar rawData plus user-selected 0D/1D/2D slices from higher-rank data,
  including stored fixed dimensions and the two-axis limit.
- Check that stored-grid direct queries equal each method's checkpoint-grid result,
  conditional-INR retains its decoder/scaler semantics, and hierarchical CAE covers
  all declared axes, rejects out-of-domain values, and preserves model state.
- Check fixed-coordinate dropdown values and preservation of arbitrary finite text
  input.
- Check ensemble finite minimum/maximum derivation for curves and surfaces.
- Check that axis and `Auto refresh` controls stay synchronized with their state.
- Check that workspace loading preselects a real generation and individual.
- Check Tcl-only popup ancestry safety.
- Check instant aggregate switching across relative/absolute, cost/rawData, all,
  and item-specific quantities.
- Check bounded workspace-summary fields and equivalent human-readable/JSON
  rendering.
- Check exact named quantity resolution, relative/absolute/both audit selection,
  generation-axis order, null-safe JSON, and terminal matrix formatting.
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
- CLI parser tests construct GUI, summary, and audit actions without importing the
  optional viewer modules.
- GUI module imports may be tested without opening a visible window. A hidden Tk
  smoke is appropriate for component behavior but should not make the default
  suite depend on a display where avoidable.
- Real-workspace audit and CUDA utilization measurements are integration checks,
  not default unit tests.
- Widget colors/copy, Matplotlib artist classes, contour overlays, mesh edge style,
  and exact geometry are presentation choices rather than stable test contracts.

## Mutability Profile

Add focused tests when contracts expand. Keep packaging and lazy CLI coverage in
yadof's generic package tests. Avoid snapshots tied to incidental widget geometry
or exact Matplotlib internals unless a later explicit user requirement makes the
detail part of the contract.
