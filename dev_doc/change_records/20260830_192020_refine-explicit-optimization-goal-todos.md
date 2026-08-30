# 2026-08-30 19:20 - Refine explicit-optimization goal and TODOs

## Context

The user clarified that the refactor's purpose is to make yadof a composable
framework whose workspace `optimization.py` owns the optimization loop and ordinary
Python data flow. The user also settled how the generic starter, source-checkout
program examples, companion documentation, and `init` behavior should be divided.

## Change

- Strengthened stage 1 from exception-only evidence preservation to the explicit
  `validate/own -> durable publish -> calculate_cost` reliability boundary,
  including committed acknowledgement and termination/recovery evidence.
- Recorded the explicit removal of the behavior-neutral GPSAF `gamma` surface in
  stage 4 while requiring selection parity.
- Recorded in stage 5 that the packaged default `optimization.py` is the one
  backend-safe starter, while a dedicated top-level `examples/` directory will
  contain multiple non-standalone optimization programs with paired Markdown
  context documents.
- Required a lightweight user-document index, preserved source-checkout-only
  example ownership, and explicitly rejected an `init` template selector or
  algorithm registry.
- Clarified in stages 5 and 6 that overlap is chosen by visible program order, not
  automatically by the fast/local/distributed backend.

## Rationale

The stable goal should state the framework outcome and refer to evolving TODOs for
stage-specific delivery. Keeping one conservative starter avoids hidden backend
policy in `init`; colocated `.py`/`.md` example pairs can explain materially
different orchestration without pretending to be complete workspaces.

## Impact

Only active planning documents changed. No package behavior, current architecture,
template, example, user documentation, installed wheel, or benchmark artifact was
modified or executed.

## Follow-Up

Stage 1 remains the only exact executable TODO. Later stages stay predictive until
the preceding stage's tests and benchmark evidence justify refinement.
