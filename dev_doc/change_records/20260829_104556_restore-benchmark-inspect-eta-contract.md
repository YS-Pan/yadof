# 2026-08-29 10:45 - Restore Benchmark Inspect And ETA Contract

## Context

The code-first `yadof-benchmark` rewrite retained a small read-only inspect command
but lost the earlier agent-facing bounded-output and timing-estimation behavior.
Plan/check still printed every expanded cell, inspect did not summarize validity or
comparison readiness, and ETA had no matched cross-run evidence or nonlinear phase
model. The active benchmark UX restoration TODO explicitly requires progressive
disclosure, separate child logs, read-only inspection, same-case/same-arm timing
matching, and timestamped phase evidence.

## Change

- Made CLI `check` and `plan` bounded by default and added explicit `--json` for the
  complete expanded plan.
- Kept child stdout/stderr in separate attempt logs by default and added explicit
  `--stream-child-output` delivery through the foreground terminal owner.
- Added timestamped per-command `progress.jsonl` events and run start/finish,
  host/Python, and hashed external-resource identity.
- Added bounded immutable `timing_history.json` snapshots at run creation. Read-only
  ETA prefers recent exact then compatible evidence with the same baseline,
  strategy, budget, task, resource, host, and configuration; it never substitutes
  another strategy and uses a non-negative generation-duration trend after three
  completed generations.
- Expanded inspect with bounded validity/comparison/anomaly summaries, progressive
  evidence paths, next commands, elapsed/active/recent activity, and
  confidence-qualified remaining/completion estimates. Older completed runs without
  the newer descriptive report or timing fields remain inspectable.

## Rationale

AI agents and humans need a small first response that says what happened and where
to look next; large plans, raw child streams, and detailed result rows should be
opened deliberately. Runtime evidence from another algorithm is not a defensible
point estimate, while matched previous cells and observed generation-duration
growth directly address the large underestimates seen with late surrogate training.
Freezing history at run creation preserves recovery determinism and keeps inspect
read-only.

## Impact

The independent benchmark runtime, CLI/API, focused fake-command tests, installed
user/developer documents, root architecture/blueprints/terminology, and active
restoration TODO now share this contract. Deterministic tests cover bounded output,
explicit streaming, exact/compatible selection, cross-arm exclusion, nonlinear
generation replay, old-run adaptation, and terminal behavior without launching a
simulator.

## Follow-Up

Restoration TODO sections 5--9 remain active. This change does not classify
structural versus performance studies, impose performance budgets, add paired
scientific metrics, change recovery/failure semantics, or configure parallelism.
