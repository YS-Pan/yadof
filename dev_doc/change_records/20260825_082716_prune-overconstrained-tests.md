# 2026-08-25 08:27 - Prune Overconstrained Tests

## Context

The maintained suite collected 278 tests. Several tests did not exercise a user,
data, failure, or public API contract: they scanned source text for removed names,
asserted repository layout or compatibility-facade identity, required selected
messages to remain absent, or froze exact Matplotlib/Tk presentation details.
Those tests added maintenance cost and made harmless refactoring or visual changes
look like regressions.

## Change

- Removed 25 collected tests in those low-value categories, including the
  test-layout meta-module.
- Kept behavior-oriented coverage for wheel contents and clean installation, CLI
  routing, workspace isolation, cost/time data adaptation, hypervolume values,
  real PNG rendering, viewer state, evaluation failures, and durable recording.
- Relaxed remaining rendering and widget tests so they verify usable output and
  state semantics without fixing pixel dimensions, colors, label coordinates, or
  opacity values.
- Updated root and viewer blueprints to distinguish stable scientific/runtime
  behavior from mutable presentation and source layout.
- Replaced incidental `legacy` wording for the current checkpoint-grid path with
  responsibility-based terminology.

## Rationale

Tests should protect observable contracts and high-risk boundaries. Negative token
scans, duplicate namespace checks, and exact presentation snapshots usually fail
because code was reorganized or restyled, not because yadof became incorrect.
Keeping rendering smoke tests and semantic calculations preserves useful defect
detection while allowing future implementations to change shape.

## Impact

The suite now collects 253 tests from 23 modules and 230 test functions before
parameter expansion. Package/runtime behavior and public data formats are
unchanged. Test and tool blueprints now explicitly permit presentation details and
internal layout to evolve independently of compatibility contracts.

## Follow-Up

Future tests should continue to prefer public outcomes, durable evidence, failure
semantics, and security or concurrency boundaries over source-text or exact-style
assertions.
