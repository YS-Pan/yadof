# Module blueprint: optimize

## Responsibility

`yadof.optimize` owns workspace-explicit campaign/generation APIs. It creates
candidates through pymoo GA/NSGA-III mechanics, combines real history and
surrogate-assisted GPSAF selection, invokes real evaluation, and records lightweight
generation/campaign metadata. It does not execute simulators or persist rawData
itself.

## Candidate and objective handling

Variable count comes from current workspace parameters; objective count/names come
from current `calc_cost.py`. Genetic operators act in normalized space and use
configured crossover/mutation probabilities and distribution indices. NSGA-III
reference directions are generated from objective count and configured partitions.
Duplicate/archive keys use configured decimal precision and bounded refill attempts.

GPSAF alpha/beta pools are ranked using surrogate-predicted current costs and member
intervals; gamma controls replacement pressure. A configured exploration quota keeps
some candidates outside surrogate preference. Every selected row is validated by the
real evaluator before becoming durable truth.

Distributed evaluation may invoke the scheduler-specific after-submit hook while
real jobs are running. Fast creates no scheduler submission and does not fabricate
that event; the existing orchestration fallback invokes deferred work only after
the fast evaluation call returns.

## Warm start and orchestration

History warm start derives current normalized variables and costs from workspace
evidence. `run_generations` supports start/resume, stable run and optimization
identities, deterministic seed, temporary config overrides, optional pre-run smoke,
and generation metadata including timings and populations. Config is loaded once per
generation so one coherent policy applies to its work.

Task flexibility is generation-scoped. At each generation boundary, optimization
must use current shape-preserving parameter and fixed-width objective definitions.
A changed `calc_cost.py` reinterprets mechanically usable history before selection.
Changes to workflow/evaluation code affect the next generation's real evaluations.
Parameter identity/count and objective count remain stable during a campaign;
rebuilding pymoo problem/reference-direction state for structural dimension changes
is separate future work. Source fingerprints are cache-invalidation/provenance
inputs only; optimize does not decide whether the user's old and new problems are
scientifically equivalent or silently discard history because a signature changed.

## Failure behavior

Individual infinite rows remain in shape and may be handled by optimizer mechanics.
Optional strict mode stops immediately after an all-infinite generation and reports
recent per-job diagnostics. A smoke failure prevents generation submission.

## Invariants

- No workspace-global optimizer singleton or implicit history path.
- One workspace has one active optimization campaign; concurrent campaigns use
  different workspaces.
- Surrogate predictions never bypass real-evaluation validation.
- Resume reuses compatible evidence/checkpoints but does not copy another workspace.
- Stored optimization metadata stays lightweight; rawData remains in recorded_data.
