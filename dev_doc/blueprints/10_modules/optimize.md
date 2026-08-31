# Module blueprint: optimize

## Responsibility

`yadof.optimize` owns workspace-explicit campaign/generation APIs, common
result/context/history/real-evaluation contracts, explicit optimization-program
lifecycle scopes and generation-local selection operations, transitional strategy
adapters, and compact metadata. An
explicit workspace owns the complete control flow through the frozen
`submit/optimization.py:optimization_program(context)` entry and its exact declared
helpers. Package components expose thin lazy
pymoo GA/NSGA-III search, objective-count dispatch, real search, irreducible GPSAF
assistance, and the separate posterior-assisted/qNEHVI composition; there is no
complete-method registry or config selector.

One `CampaignSession` spans a complete `run_generations` campaign. It owns the
workspace lock, bounded recorder, startup catalog, and in-memory current-campaign
rows. Standalone `run_one_generation` owns a shorter session with the same
contracts. `OptimizationRunScope` and `ProgramGenerationScope` expose that owner;
they do not duplicate its recorder, evaluator, handle registry, or lock.

## Source structure

- `program.py` statically validates the literal v1 declaration, freezes the entry
  and exact helper sources, isolated-loads the entry once, and owns the public
  program/run/generation contexts plus strict complete-generation commit/resume.
- Parent files own campaign/session execution, transitional strategy loading/state, problem
  shape, metadata helpers, and the lightweight public component/factory surface.
- `primitives.py` owns frozen backend-neutral `SearchCandidate`, `CandidatePool`,
  `PredictedCostRows`, `CandidateSelection`, and opaque generation-local
  `SearchState` values plus prepare/search/bind/select/advance/compose/full-real
  operations. It imports the concrete pymoo adapter only inside operations.
- `gpsaf/` owns the generation-local typed GPSAF selector,
  alpha/beta/exploration phases, explicit training start/finish helpers, and its
  retained private pymoo record adapter; it does not own real evaluation or
  generation commit.
- `pymoo/` owns the concrete GA/NSGA-III adapter shared by GPSAF and real-search
  strategies. Pymoo objects do not cross into the public strategy contract.
- `qnehvi/` owns the public qNEHVI-family component implementation:
  `acquisition.py` provides controls and discrete greedy multi-start selection,
  `backend.py` provides the lightweight scoring boundary, and
  `_botorch_backend.py` owns the optional Torch/BoTorch numerics.
- `posterior_assisted.py` owns the independent generation-local selector around
  injected search, posterior surrogate, readiness, projector, and acquisition
  components. Its pool and complete-real fallback reuse the common primitives;
  the workspace program always owns evaluation and commit.
- The public `gpsaf()`, `gpsaf_settings()`, and `qnehvi()` factories remain at
  `yadof.optimize`;
  loading their same-named private implementation packages must not replace those
  callables with subpackage modules.

## Candidate and objective handling

Variable count comes from current workspace parameters; objective count/names come
from current `submit/calc_cost.py`. Pymoo owns algorithms, operators, ask/tell, and
survival. Its thin adapter acts in normalized space and uses
configured crossover/mutation probabilities and distribution indices. NSGA-III
reference directions are generated from objective count and configured partitions.
Duplicate/archive keys use configured decimal precision and bounded refill attempts.
Every search operation clones its opaque input state and returns an exact next state;
the same input can be forked deterministically. Candidate IDs, rounded design keys,
and optional source evidence IDs remain separate. State is bound to strategy,
generation, problem, seeds, archive precision, and interpretation snapshot; it is
not pickleable or durable. Generation-boundary resume rebuilds from real history.

`PredictedCostRows` aligns finite current-cost means to exact pool candidate IDs and
is the only deterministic survival input. `CostTable`, `SurrogatePrediction`, and
`JointObjectiveSamples` remain distinct owners/types. Selection commits only the
search continuation; real evidence commits only after the common evaluator.
`combine_predicted_cost_rows()` projects and concatenates exact candidate-bound
rows from one semantic prediction owner, including prediction supersets needed by
beta anchors; it rejects missing, duplicate, or mixed-semantics rows.

GPSAF alpha/beta pools are ranked using surrogate-predicted mean current costs
through pymoo survival. Conditional-INR member min/max spread remains a diagnostic
output at the surrogate/viewer boundary; GPSAF candidate records do not carry it,
and it is not converted into optimizer noise, knockout probability, or a trust
decision. A configured exploration quota keeps some candidates outside surrogate
preference. Every selected row is validated by the real evaluator before becoming
durable truth.

For PCA/SVD, conditional-INR, and hierarchical-CAE, the workspace program freezes
one explicit `SurrogateTrainingData` from the generation's evidence/cost views
before state-age inspection, prediction, and training calls. Each runtime-checkable
`DeterministicSurrogateComponent` returns a `SurrogatePrediction` for the exact
candidate pool, and the explicit binder retains only aligned current-cost means for
survival. `select_gpsaf_generation()` returns a generation-local selection DTO; it
does not evaluate, start/wait for training, or commit. Its pure freshness check may
reuse only a compatible state within the configured generation lag. After starting the real-evaluation handle, the
program starts training on that prior immutable evidence and later waits/closes both
operations before commit. Conditional-INR and hierarchical-CAE translate the same
owned value into their retained named-data internals without changing checkpoint
identity. No explicit program path has an `after_jobs_submitted` callback.

The public joint rawData posterior protocol, typed exploitation readiness, and cost
projector feed `PosteriorAssistedStrategy.select_generation()`. The selector
requires
both runtime-checkable capabilities rather than probing with `hasattr`, binds the
search/surrogate/posterior/readiness/acquisition identities plus all pool/draw/
chunk/exploration controls and objective names, consumes only projected joint cost
samples/valid masks, and returns either a typed assisted selection or typed
complete-real fallback for program-owned evaluation.
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

The generation-local selector first checks the static typed
performance/calibration/transferability
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
unique, and returned to the workspace program as a selection DTO.
Selection/projection/backend
exceptions and configured support fallback discard all derived choices and run the
same shared full-real primitive used by real-only/GPSAF fallback. Configured support
rejection propagates. The workspace program performs real evaluation,
finalization, recording, and commit outside the selector and fallback catch, so
recorder failure still aborts the campaign.

Only the closed 0.4.x strategy adapter may still reach the scheduler-specific
after-submit hook. Fast creates no scheduler submission and does not fabricate that
event. Explicit programs instead start an evaluation handle, start training on the
already frozen evidence, and explicitly wait/close both lifecycles; the 0.5.0
cutover removes the callback-bearing adapter and backend field.

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

For an explicit program, source loading is run-scoped: the CLI freezes the program
before optional smoke and passes that exact snapshot into execution; direct APIs
freeze at their own entry. The literal declaration supplies exact API/entry/helper,
semantic identity, and capabilities. Source fingerprint remains separate from the
program semantic signature, and undeclared helper imports fail closed.

Task flexibility is generation-scoped. At each generation boundary, optimization
creates an immutable classified two-root task snapshot that excludes frozen program
sources, then uses its shape-preserving parameter and
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
Opaque mid-generation search state is never written to metadata. A successfully
exited explicit generation first resolves normal-wait training handles, rejects any
open cancel-policy evaluation handle, confirms recording and metadata, and then
atomically advances the compatible program completion pointer. Restart/resume at
this boundary deterministically reconstructs pymoo survivor/archive state from the
identity-joined committed history and current seeds.

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
- Static workspace checking never imports or executes either an explicit program or
  a transitional legacy factory.
- One explicit run uses one frozen program snapshot; generation task snapshots do
  not recopy or reinterpret declared program sources.
- Explicit selectors consume owned evidence values and return selection DTOs; they
  never scan a campaign session for training evidence or evaluate, train, record,
  or commit a generation.
- `ProgramGenerationScope.prepare_evaluation()` exposes no lifecycle callback.
  Callback-bearing evaluation and strategy-owned generation methods are a closed
  0.4.x compatibility surface scheduled for the 0.5.0 cutover.
- A generation without one validated `commit()` never advances the program
  completion pointer; user exceptions and interrupts retain the previous complete
  boundary and cleanup the existing session owners before propagating.
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
- Search candidates, predicted-cost rows, and opaque continuation payloads are also
  transient; no public DTO exposes a pymoo algorithm, `Individual`, operator, ask,
  tell, or survival object.
- Current conditional-INR and hierarchical-CAE posterior components always block
  exploitation; implementation completeness is not scientific activation.
