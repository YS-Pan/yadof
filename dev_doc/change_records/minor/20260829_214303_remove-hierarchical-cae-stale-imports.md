# 2026-08-29 21:43 - Remove Hierarchical CAE Stale Imports

## Context

- Earlier decomposition of the Hierarchical CAE implementation left several
  modules with copied import headers that still referenced responsibilities now
  owned by sibling services.
- Those bindings were not read anywhere in the affected modules, but they made
  the implementation appear more coupled and larger than its runtime behavior.

## Change

- Removed statically unused imports from the Hierarchical CAE data adapter,
  inference, network, objective, posterior adapter, projection, state repository,
  and training modules.
- Preserved the deliberate re-export surfaces in `__init__.py` and `runtime.py`.
- Rechecked every other module in the package with an AST-based unused-import
  audit after the cleanup.

## Rationale

- These imports were mechanically provable dead code and could be removed without
  changing control flow, public interfaces, exception behavior, artifacts, or
  numerical results.
- Broader consolidation of selectors, schedulers, or training loops is excluded
  because those changes require separate contract and responsibility analysis.

## Impact

- Import-time coupling and incidental source volume are reduced.
- No public API, configuration, checkpoint schema, artifact layout, model
  behavior, or architectural ownership changed.

## Follow-Up

- Evaluate any remaining duplicated policy only as independent refactors with
  focused behavior-equivalence tests; do not treat textual similarity alone as a
  sufficient reason to introduce a shared abstraction.
