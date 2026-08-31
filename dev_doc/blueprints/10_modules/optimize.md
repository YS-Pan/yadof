# Module blueprint: optimize

## Responsibility

`yadof.optimize` owns workspace-explicit campaign/generation APIs, common
result/context/history/real-evaluation contracts, strategy invocation, and compact
metadata. The snapshotted workspace owns the complete method through
`submit/optimization.py:build_optimization()`. Package components expose thin lazy
pymoo GA/NSGA-III search, objective-count dispatch, real search, irreducible GPSAF
assistance, and the separate posterior-assisted/qNEHVI composition; there is no
complete-method registry or config selector.

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
- `qnehvi/` owns the public qNEHVI-family component implementation:
  `acquisition.py` provides controls and discrete greedy multi-start selection,
  `backend.py` provides the lightweight scoring boundary, and
  `_botorch_backend.py` owns the optional Torch/BoTorch numerics.
- `posterior_assisted.py` owns only the independent generation orchestration around
  injected search, posterior surrogate, and acquisition components. It reuses the
  private pymoo mechanics but does not modify GPSAF.
- The public `gpsaf()` and `qnehvi()` factories remain at `yadof.optimize`;
  loading their same-named private implementation packages must not replace those
  callables with subpackage modules.

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

For the migrated PCA/SVD component, GPSAF freezes an explicit
`SurrogateTrainingData` from the generation's evidence/cost views before freshness,
state, and prediction calls. Its after-submit hook materializes again at the hook's
actual backend timing and starts an explicit fit handle. A narrow compatibility
adapter unwraps typed deterministic predictions into GPSAF rows; conditional-INR
and hierarchical-CAE keep their existing method signatures in this stage.

The public joint rawData posterior protocol, typed exploitation readiness, and cost
projector feed the explicitly composed posterior-assisted strategy. It requires
both runtime-checkable capabilities rather than probing with `hasattr`, binds the
search/surrogate/posterior/readiness/acquisition identities plus all pool/draw/
chunk/exploration controls and objective names, consumes only projected joint cost
samples/valid masks, and sends every selection through the common real evaluator.
Merely adding a posterior adapter or blocker must not change the existing GPSAF
identity or conditional-INR checkpoint namespace.

## Discrete qNEHVI acquisition and qLogNEHVI backend

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
timing/memory diagnostics. `qnehvi()` groups singleton and incremental batches for
deterministic greedy multi-start selection while the backend owns every score. It
deliberately has no pending points, outcome constraints, gradient `optimize_acqf`,
candidate-pool mechanics, real evaluator, or recorder path. BoTorch remains an
independent `qnehvi` optional extra and ordinary `import yadof.optimize` does not
load it.

## Posterior-assisted generation

The strategy first checks the static typed performance/calibration/transferability
identity. A blocker immediately selects a complete real-search population. An
eligible path freezes the finite unique nondominated real baseline, applies the
surrogate freshness gate, proposes one unique history-informed pymoo pool, obtains
candidate-aligned runtime readiness, and reserves
`ceil(population * exploration_fraction)` real exploration rows. Calibrated
applicability excludes below-threshold exploitation and prioritizes low/boundary
real exploration only according to the sealed gate identity.

One persistent schema-bearing sampler evaluates only eligible exploitation rows in
candidate chunks. Projection discards rawData and the acquisition selects the
configured remainder. Exploitation and exploration are combined once, verified
unique, and passed to common `evaluate_population()`. Selection/projection/backend
exceptions and configured support fallback discard all derived choices and run a
full real-search generation. Configured support rejection propagates. Evaluation,
finalization, and recording begin outside the fallback catch, so recorder failure
still aborts the campaign.

Distributed evaluation may invoke the scheduler-specific after-submit hook while
real jobs are running. Fast creates no scheduler submission and does not fabricate
that event; the existing orchestration fallback invokes deferred work only after
the fast evaluation call returns.

## Warm start and orchestration

History warm start joins the session's immutable evidence dataset and task-bound
cost table by row identity. It consumes only successful committed original rows and
carries candidate, row, design, and interpretation identity alongside the existing
name/normalized-variable/cost fields. `run_generations` supports start/resume,
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

The real-evaluation adapter creates those `inf` rows only after evidence-first
finalization returns no authoritative current cost. If valid rawData was already
committed, the immutable record remains `completed` and replayable; optimization
does not write the sentinel back into evidence or interpretation state. Recorder
failure remains campaign-fatal and never becomes an individual `inf`.

## Invariants

- No workspace-global optimizer singleton or implicit history path.
- One workspace has one active optimization campaign; concurrent campaigns use
  different workspaces.
- Current rows become visible to result consumers only after their receipts commit
  and ordered interpretation finishes; the next generation starts only after every
  row is durable.
- Surrogate predictions never bypass real-evaluation validation.
- Resume reuses compatible evidence/checkpoints but does not copy another workspace.
- A semantic strategy switch waits for pending component work, releases old memory,
  and activates `strategy-<signature>` while retaining inactive artifacts.
- Source fingerprints remain separate from deterministic semantic signatures.
- Stored optimization metadata stays lightweight; rawData remains in recorded_data.
- History identity comes from durable candidate/row IDs, never job names, design
  equality, or view position; non-successful cost rows remain typed until an
  explicit optimizer-shape adapter requires `inf`.
- Predicted posterior rawData and projected acquisition samples remain transient and
  never become optimizer history, recorder input, or real-evaluation results.
- Current conditional-INR and hierarchical-CAE posterior components always block
  exploitation; implementation completeness is not scientific activation.
