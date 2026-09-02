# 2026-09-02 19:39 - Rebuild README For First-Time Users

## Context

The author requested a substantial README rewrite after in-depth project research
and authorized independent agent research when useful. The editorial perspective
is a technical writer for developer products, with developer-relations attention
to the first successful user experience.

## Research And Decisions

- Review the current architecture, version-matched user contracts, packaged
  starter, optimization program examples, adapter boundaries, and experimental
  component status. Two independent read-only reviews check project positioning
  and onboarding, then review the rewritten draft.
- The earlier opening emphasized record internals and the development machine
  before explaining why an engineer would use yadof. Lead with expensive
  simulations, reusable raw outputs, and an editable Python optimization program.
- Show the real/surrogate output paths through the current cost function. Keep
  history reuse conditional on meaningful task compatibility and preserve the
  documented parameter/objective shape restrictions.
- Replace the assumed local `dist/` installation with the published 0.5.1 wheel
  download. Provide one bounded starter route, including observable results, and
  distinguish it from authoring and executing a real simulator task.
- Preserve English and the human-directed AI-agent workflow. Replace the blank
  task prompt with a scaffold for simulator inputs, parameters, objectives,
  runtime, concurrency, budget, and workspace location.
- Explain workspace ownership, current default components, and all three execution
  modes. Identify PCA/SVD as diagnostic and posterior/qNEHVI selection as blocked
  behind readiness checks. Link detailed material instead of presenting research
  components as established performance improvements.
- Keep examples and the independent benchmark distribution distinct. Link the
  existing migration, environment, history, and contribution documents.

The root README remains a project overview and entry point. Normative user and
developer documentation ownership, routing, and runtime contracts are unchanged.

## Validation

- Confirm installed yadof 0.5.1 imports from the workspace environment's
  `site-packages`. The released wheel's `[surrogate,plot]` requirement passes a
  no-index pip dry run in that environment; no dependency replacement is needed.
- Run the unmodified starter in a new task-owned temporary workspace:
  `init`, `check`, local `smoke-test`, local `run --generations 1
  --population-size 8 --no-smoke-test`, and `view all` all exit successfully.
  The static check reports zero warnings; smoke returns cost approximately 0.1;
  generation zero completes eight successful candidates with zero errors.
- The views report nine completed records, zero ignored issues, zero failures,
  and create both cost and time PNGs. Generation zero uses random initialization
  without a surrogate, so the README makes no performance claim from this demo.
- Validate UTF-8, balanced fences, CommonMark/table rendering, and all 18 local
  link occurrences covering 16 distinct paths/fragments. Verify the GitHub
  release asset and issue entry, and use the current canonical Codex URL.
- Generate wheel metadata with Hatchling's metadata-preparation hook in the
  task's temporary directory. Verify package/version, Markdown content type, and
  exact README body after newline normalization. This checks the project long
  description without replacing the published artifact or installed package.

This is a prose and executable-instruction change. Runtime code, tests, build
configuration, resource mappings, and documentation mechanisms are unchanged;
validation targets the README, metadata, and documented commands rather than
rerunning the software suite. The installed 0.5.1 package is retained.

## Existing Work

No pre-existing tracked changes were present. The untracked local GPSAF paper is
preserved with its original SHA-256 and excluded from this documentation commit.
