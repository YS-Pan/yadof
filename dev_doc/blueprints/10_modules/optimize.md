# Module blueprint: optimize

## Responsibility

`yadof.optimize` owns workspace-explicit campaign/generation APIs, common
result/context/history/real-evaluation contracts, strategy invocation, and compact
metadata. The snapshotted workspace owns the complete method through
`submit/optimization.py:build_optimization()`. Package components expose thin lazy
pymoo GA/NSGA-III search, objective-count dispatch, real search, and irreducible
GPSAF assistance; there is no complete-method registry or config selector.

One `CampaignSession` spans a complete `run_generations` campaign. It owns the
workspace lock, bounded recorder, startup catalog, and in-memory current-campaign
rows. Standalone `run_one_generation` owns a shorter session with the same
contracts.

## Source structure

- Parent files own campaign/session execution, strategy loading/state, problem
  shape, metadata helpers, and the lightweight public component/factory surface.
- `gpsaf/` owns only GPSAF assistance, alpha/beta/exploration phases, and its
  private candidate records.
- `pymoo/` owns the concrete GA/NSGA-III adapter shared by GPSAF and real-search
  strategies. Pymoo objects do not cross into the public strategy contract.
- `qnehvi_backend.py` owns a lightweight experimental scoring boundary;
  `_qlognehvi_backend.py` owns its optional Torch/BoTorch implementation. Neither
  file is a public complete-strategy factory or generation orchestrator.
- The public `gpsaf()` factory remains at `yadof.optimize`; loading private
  `optimize.gpsaf.*` modules must not replace that callable with the subpackage.

## Candidate and objective handling

Variable count comes from current workspace parameters; objective count/names come
from current `submit/calc_cost.py`. Pymoo owns algorithms, operators, ask/tell, and
survival. Its thin adapter acts in normalized space and uses
configured crossover/mutation probabilities and distribution indices. NSGA-III
reference directions are generated from objective count and configured partitions.
Duplicate/archive keys use configured decimal precision and bounded refill attempts.

GPSAF alpha/beta pools are ranked using surrogate-predicted mean current costs
through pymoo survival. Conditional-INR member min/max spread remains a diagnostic
output at the surrogate/viewer boundary; GPSAF candidate records do not carry it,
and it is not converted into optimizer noise, knockout probability, or a trust
decision. A configured exploration quota keeps some candidates outside surrogate
preference. Every selected row is validated by the real evaluator before becoming
durable truth.

The public joint rawData posterior protocol and cost projector are available to a
future explicitly composed strategy, but optimize currently has no posterior-
assisted strategy or acquisition component. The Gate 2 discrete qLogNEHVI scorer
is only a backend compatibility spike. A complete consumer must require the
runtime-checkable capability rather than probe with `hasattr`, include the
posterior-capability identity (backend version and every controlled parameter) in
its strategy identity, consume only projected joint cost samples/valid masks, and
send every selection through the common real evaluator. Merely adding a posterior
adapter to a surrogate package must not change the existing GPSAF identity or
conditional-INR checkpoint namespace.

## Experimental discrete qLogNEHVI backend

`score_discrete_qlognehvi()` accepts fixed completed baseline rows/costs, a
`JointObjectiveSamples` tensor, and explicit candidate-index batches. It requires
at least two objectives, a non-empty unique normalized candidate pool, valid
`[0,1]` minimization costs, a fixed in-contract baseline, and no overlap with
completed rows. It defaults the cost reference point to all ones and negates costs
and reference exactly once for BoTorch maximization semantics.

The private lookup `EnsembleModel` repeats each observed baseline cost across the
same empirical draw axis and exposes aligned candidate draws through
`EnsemblePosterior`; an enumerating sampler consumes every retained draw exactly
once. BoTorch `qLogNoisyExpectedHypervolumeImprovement` owns hypervolume,
partitioning, smoothing, and log-improvement numerics. Yadof groups only supplied
discrete q batches for evaluation. Any candidate failure rejects its entire MC draw
conservatively, while a finite task result of `1.0` stays valid. Optional finite
minimum-support policy either warns or rejects visibly using post-mask distinct
draw sources.

The result contains only batch indices, log acquisition values, backend/support/
timing/memory diagnostics. The spike deliberately has no pending points, outcome
constraints, gradient `optimize_acqf`, candidate-pool mechanics, generation
fallback, real evaluator, or recorder path. BoTorch remains an independent
`qnehvi` optional extra and ordinary `import yadof.optimize` does not load it.

Distributed evaluation may invoke the scheduler-specific after-submit hook while
real jobs are running. Fast creates no scheduler submission and does not fabricate
that event; the existing orchestration fallback invokes deferred work only after
the fast evaluation call returns.

## Warm start and orchestration

History warm start derives current normalized variables and costs from the session's
startup catalog plus accepted current rows. `run_generations` supports start/resume,
stable run and optimization
identities, deterministic seed, temporary config overrides, optional pre-run smoke,
and generation metadata including timings, populations, task fingerprints, and
recorder counters. Config is loaded once per generation so one coherent policy
applies to its work; recorder capacities and storage path remain frozen at campaign
start.

Task flexibility is generation-scoped. At each generation boundary, optimization
creates an immutable complete two-root task snapshot, loads exactly one strategy,
and uses its shape-preserving parameter and
fixed-width objective definitions. An interpretation-fingerprint change
reinterprets mechanically usable history before selection; an evaluation-only
change reuses the existing derived view. Changes to optimization composition or
workflow/evaluation code affect
the next generation's real evaluations.
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
- Current accepted rows are available within the generation while publication is
  pending; the next generation starts only after every row is durable.
- Surrogate predictions never bypass real-evaluation validation.
- Resume reuses compatible evidence/checkpoints but does not copy another workspace.
- A semantic strategy switch waits for pending component work, releases old memory,
  and activates `strategy-<signature>` while retaining inactive artifacts.
- Source fingerprints remain separate from deterministic semantic signatures.
- Stored optimization metadata stays lightweight; rawData remains in recorded_data.
- Predicted posterior rawData and projected acquisition samples remain transient and
  never become optimizer history, recorder input, or real-evaluation results.
