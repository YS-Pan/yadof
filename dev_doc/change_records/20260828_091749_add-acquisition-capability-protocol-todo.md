# 2026-08-28 09:17 - Add Acquisition Capability Protocol TODO

## Context

- `PosteriorAssistedStrategy` currently depends on the concrete
  `DiscreteQNEHVIAcquisition` type even though its architectural role is to consume
  an acquisition capability.
- qNEHVI is currently the only real acquisition implementation, and no second
  acquisition/search backend is planned in the near term.
- Extracting an interface immediately would risk promoting qNEHVI-specific inputs,
  support rules, and diagnostics into a misleading generic contract.

## Change

- Added a manual future TODO for deriving an acquisition capability protocol only
  after a second approved implementation or another concrete consumer supplies
  evidence for the shared boundary.
- Recorded the expected ownership, compatibility, migration, validation, and
  completion constraints without changing runtime code or approving a new
  acquisition.
- Explicitly kept the future protocol independent of Pydantic, registries, GUI
  implementation types, and optional numerical backends.

## Rationale

- The concrete dependency is worth recording as modularity debt, but the smallest
  honest protocol cannot be known from one implementation alone.
- A trigger-based handoff preserves the intended dependency inversion while
  avoiding speculative abstractions and public compatibility commitments.

## Impact

- No package, configuration, workspace, strategy identity, checkpoint, history,
  or runtime behavior changes.
- Future acquisition work has a standalone handoff and an explicit gate against
  premature implementation.
