# 2026-08-29 18:47 - Simplify benchmark to one execution per workspace

## Context

A full benchmark exposed four practical failures: a sandbox-owned detached process
did not show a human-visible window, one simulation error invalidated an entire
cell, the expanded multi-seed/large-generation matrix ran too long for slow
surrogates, and semantic cell/attempt names exceeded comfortable Windows path
lengths. The multi-run, resume, driver-snapshot, and attempt architecture also made
workspace navigation harder than its value justified.

The user manually stopped the motivating benchmark and explicitly removed any
requirement to resume it or support older workspace formats.

## Decision

- One benchmark workspace owns one execution. Another execution uses another
  initialized workspace.
- Use the installed yadof-benchmark and yadof packages directly. Record versions,
  Python, host, and process account once in `runtime.json` before cell work.
- Remove `runs/`, run IDs, resume API/CLI, driver/workflow/strategy snapshots,
  numbered cell/postprocessor attempts, workspace output indexes, and cross-run
  timing history.
- Use short ordinal cell IDs such as `c0001`; keep semantic identity in
  `spec.json` and reports.
- Default to seed 101, population 200, and 50 generations. When any selected
  strategy declares `slow_surrogate=True`, default to 15 generations. Explicit
  seeds and budgets always win.
- Treat individual failed or non-finite simulations as reported evidence. A cell
  remains valid when attempted count equals plan, finite output and final metric
  exist, task contracts match, and generation-0 population evidence is complete.
- Document that Windows AI agents must use host execution under the interactive
  human account. `--detach` cannot switch a sandbox process into that session.

## Implementation

The independent package was released as `0.2.0`. Storage now writes
`runtime.json`, `spec.json`, `state.json`, cell evidence, reports, and
visualizations directly below the workspace. Each cell materializes its baseline
under `cells/cNNNN/workspace`, owns direct command logs and one result, and uses
short visualization prefixes.

The workflow builder resolves standard/slow defaults at freeze time. Result
publication now distinguishes attempted-count completeness from completed and
finite subsets and exposes failed/non-finite counts plus
`simulation_errors_tolerated`.

User/developer documentation, root architecture, project/test blueprints,
terminology, baseline manifests, packaged examples, and the affected future
surrogate TODO were updated. The superseded restoration TODO was archived.
The obsolete timing module and recovery document were removed rather than retained
as compatibility layers.

## Verification

- Built `yadof_benchmark-0.2.0-py3-none-any.whl`.
- Force-reinstalled it into the workspace `.venv`.
- Verified yadof 0.4.2 and yadof-benchmark 0.2.0 import from
  `.venv/Lib/site-packages`.
- Verified wheel membership includes `user_doc/execution.md` and excludes the
  removed recovery document and timing module.
- Verified installed `docs list`, `docs show execution.md`, CLI help, and all
  three packaged baseline manifests.
- Ran the focused installed-package suite with a fresh pytest base temp:
  `16 passed`.
- The suite covers standard/slow defaults, one seed, short direct paths, no
  attempt layer, one-time runtime provenance, simulation-error tolerance,
  incomplete-attempt failure, postprocessing, inspection, CLI surface, terminal
  lifecycle, and detached-launch receipt.
- No simulator or measured benchmark execution was started.
