# 2026-07-18 19:30 - Package Optimizer And Surrogate Workspaces

## Context

- Evaluation and recorded data were package-owned and workspace-explicit, while
  optimization and surrogate training still lived in the repository source layout.
- The migration had to preserve mature GPSAF and INR behavior without creating a
  second compatibility implementation.

## Change

- Copied the optimizer and surrogate modules into `src/yadof`, then adapted their
  imports, public entry points, configuration reads, history access, scheduler
  state, and checkpoint paths to an explicit `WorkspaceContext`.
- Added packaged generation runners with run/generation provenance, durable
  optimizer metadata, restart from workspace history, and an explicit all-infinite
  generation error used by the CLI.
- Keyed in-process surrogate state by resolved workspace, recovered current-schema
  checkpoints from each workspace, and fixed checkpoint artifact unpacking and
  validation.
- Added generic and two-workspace tests for generation isolation, recovery,
  checkpoint selection, cost recomputation, and package-only imports.

## Rationale

- Copy-first adaptation preserved the numerical and lifecycle behavior of the old
  implementation while making mutable state ownership unambiguous.
- Workspace-keyed state prevents two optimizations in one interpreter from sharing
  models, histories, paths, or configuration.

## Impact

- `yadof.optimize` and `yadof.surrogate` are the sole runtime implementations.
- Optimizer history and surrogate checkpoints are written only below the selected
  workspace and can be resumed without a repository checkout.
