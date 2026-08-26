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
- The public `gpsaf()` factory remains at `yadof.optimize`; loading private
  `optimize.gpsaf.*` modules must not replace that callable with the subpackage.

## Candidate and objective handling

Variable count comes from current workspace parameters; objective count/names come
from current `submit/calc_cost.py`. Pymoo owns algorithms, operators, ask/tell, and
survival. Its thin adapter acts in normalized space and uses
configured crossover/mutation probabilities and distribution indices. NSGA-III
reference directions are generated from objective count and configured partitions.
Duplicate/archive keys use configured decimal precision and bounded refill attempts.

GPSAF alpha/beta pools are ranked through pymoo survival using the surrogate's point
costs. Conditional INR defines those point costs as the per-objective optimistic
member costs: it predicts rawData for every ensemble member, passes each member through
the current task cost function, and returns the lower endpoint of each member-cost
interval. Candidate records do not carry the full interval, and it is not converted
into optimizer noise, knockout probability, or a trust decision. A configured
exploration quota keeps some candidates outside surrogate preference. Every selected
row is validated by the real evaluator before becoming
durable truth.

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
