# CAE surrogate goal progress log

This is the persistent working ledger for `temp/cae-surrogate-goal.md`.  The
goal's wording and success criteria remain authoritative; this file records
provenance, protocol decisions, evidence, failures, and next actions without
relaxing that contract.

## 2026-09-04 - startup, provenance, and protocol freeze

### Current product state

- Outer workspace: `D:\project\20260414 yadof\20260822 modular`.
- Source checkout: `20260822 yadof`.
- Starting source HEAD: `51e30f8fbd2e624d9c93e292934a09c20eff2eb5` on
  `main`, two commits ahead of the then-current local `origin/main` tracking
  ref.  Starting staged and unstaged diffs were empty.
- Installed packages used for the first audit: yadof 0.6.0 and
  yadof-benchmark 0.6.0, both imported from this workspace's
  `.venv/Lib/site-packages`.
- The mandatory installed `yadof docs show user README.md` startup route and
  the applicable yadof and yadof-benchmark development/user contracts were
  read before task actions.

### Trebuchet determinism provenance

- The pre-fix mismatch evidence is retained at
  `temp/20260902_gpsaf-analysis/initial_repeat_differences.json`.  Equal
  parameter vectors sometimes produced materially different Trebuchet costs;
  the largest recorded absolute component difference was about 0.8571.  This
  evidence is historical and is not admissible as post-fix CAE data.
- Commit `7972f8c50636672932dce5a3cbd05419368bb360` added
  `SetMinBounceSpeed(0.15)` to every newly created Chrono NSC system and
  documented that Chrono 10.0.0 otherwise leaves the member uninitialized.
  Commit `0a788b762852a8b035bf521c7571174ee113ee72` retained the fix while adding
  resident fast sessions.
- The corresponding accepted change record is
  `dev_doc/change_records/20260903_000500_restore-gpsaf-perfect-oracle-validity.md`.
  Its retained post-fix evidence covers Trebuchet population cases
  0, 44, 84, 105, and 158, eight runs per case across independent sequential,
  concurrent, and persistent-process execution.  It reports bitwise identity
  for all 16 NPZ files / 23 numeric arrays and all four costs, with maximum
  raw/cost difference exactly zero under PyChrono 10.0.0
  (`py313h418371c_0`).
- A small independent repeat probe against the current installed wheel is still
  required before this checkpoint is closed.  It will use no evaluation cache
  and will compare raw arrays, metadata sufficient to identify the runtime, and
  interpreted costs.

#### Current-wheel repeat probe result

The independent probe is complete and passed.  Evidence is retained at
`temp/cae-surrogate-determinism-current-20260904/evidence.json`; the executable
probe is `temp/probe_current_trebuchet_determinism.py`.

- It used installed yadof 0.6.0 and yadof-benchmark 0.6.0, plus the configured
  external `pychrono-10` interpreter, with evaluation caching disabled.
- It replayed the historically sensitive generation-zero positions 105 and 158
  from the retained paired parameter design.  Each case ran three times in one
  persistent resident process and twice more in separate fresh processes (ten
  actual simulator calls total).
- For each case all five full raw-payload SHA-256 digests were identical, all
  four interpreted costs were bitwise identical, and the maximum absolute cost
  difference was exactly zero.  Position 105's vector was
  `[1.0, 0.22287917746600133, 0.17282794500036686,
  0.14279860805374583]`; position 158's was
  `[0.7622877070286345, 0.45563046425216525,
  0.8994547019242758, 0.0786833215365072]`.
- Installed worker SHA-256:
  `a2d03b02e0e74aee509e631f25cd373e6f89c845bfd5d49a86bd0c31aaaf2300`.
  Installed adapter SHA-256:
  `e86b329ec7817b82da6f2dbb61c4711e5de42e0b52971f701815bd9c67904c85`.

Together with the broader retained post-fix acceptance evidence, this closes
the Trebuchet determinism checkpoint.  Any later simulator or adapter change
requires rerunning it before performance evidence is accepted.

### Recovered clean seed-101 reference/oracle evidence

The accepted post-fix, installed-wheel, population-200 evidence in
`dev_doc/context/20260903_214613_greedy-hv-perfect-surrogate-crossings.md`
establishes the following development thresholds.  Formal counts include full
completed batches; strict inequality is required.

| baseline | ordinary reference R | first perfect Q < R | N_perfect | candidate 1.5x ceiling |
| --- | ---: | ---: | ---: | ---: |
| chrono/trebuchet | 0.1985232880294068 | 0.19748450111281463 | 1600 | 2400 |
| ngspice/saw-ladder | 0.21998848884193284 | 0.21452308310249957 | 3800 | 5700 |
| test-com/synthetic-antenna | 0.29019996992584607 | 0.28948195653903852 | 3600 | 5400 |

Because population batches contain 200 formal evaluations, a candidate can only
claim complete-generation crossings at 2400, 5600, and 5400 respectively.  The
5700 arithmetic ceiling for SAW is not rounded upward.

### Frozen comparison protocol

This protocol is frozen before substantial candidate comparisons.  A change to
it invalidates later comparisons and must be justified here before rerunning
all affected arms.

1. **Metric.**  For every eligible truly evaluated individual, compute the
   arithmetic mean of its finite objective costs.  At formal budget `n`, `Q(n)`
   is the arithmetic mean of the ten smallest such values in cumulative formal
   history.  Failed/non-finite evaluations do not displace finite individuals;
   fewer than ten eligible finite individuals cannot cross.  No interpolation
   within a batch is allowed.
2. **Reference and perfect arms.**  Ordinary NSGA-III uses population 200 and 50
   generations (10,000 formal evaluations).  The perfect arm uses the same
   paired initial population and the already documented GPSAF defaults
   (alpha=3, beta=3, gamma=0.5, exploration=0.10, greedy hypervolume infill and
   the documented NSGA-III operators).  `N_perfect` is the first complete formal
   batch with strict `Q_perfect < R`.
3. **Candidate arm.**  The candidate uses population 200, the same search and
   GPSAF settings, and the same paired initial population.  Its first strict
   complete-batch crossing is `N_candidate`.  It passes a seed only when both
   `Q_candidate(N_candidate) < R` and
   `N_candidate <= 1.5 * N_perfect`.  Evaluations already present in a candidate
   training archive count against its formal budget; the default protocol uses
   no external starting archive.
4. **No leakage.**  The ordinary and perfect histories, oracle calls, held-out
   labels, known optima, and baseline identity are unavailable to candidate
   training and selection.  The reference scalar may be used only by an
   independent stop/report observer after a completed formal batch.  Perfect
   oracle calls remain in a separate campaign pool and never enter formal or
   candidate histories.  Candidate fitting uses only its own completed formal
   evaluations.
5. **General-purpose behavior.**  One architecture and one set of defaults is
   used for every baseline.  Adaptation may depend only on observed candidate
   data and generic schema facts such as parameter count, field shapes, and
   sample count.  No code/config branch may mention a baseline/provider/task
   identity, known optimum, or reference score.  Conditional INR is a protected
   control and must remain behaviorally and byte-for-byte source unchanged.
6. **Development checkpoint.**  Seed 101 is the only performance seed used for
   architecture iteration.  Its post-fix reference/perfect thresholds are the
   table above.  Offline diagnostics may use separately retained evidence only
   when clearly labeled non-candidate and never fed into a measured candidate.
7. **Confirmatory validation.**  Once the implementation and defaults are
   frozen, run new paired ordinary, perfect, and candidate arms at seeds 401,
   402, and 403.  These seeds are held out from architecture/model selection.
   Every declared seed outcome is reported.  A baseline passes only if all
   three candidate cells strictly cross their own seed's reference within that
   seed's 1.5x perfect ceiling; median and range are descriptive, not substitutes
   for a failed seed.  If validation informs another design change, these seeds
   become development evidence and a new three-seed held-out set must be frozen
   here before the next confirmatory run.
8. **Reproducibility and accounting.**  Record source commit/diff, installed
   wheel hashes and import origins, benchmark manifest, simulator/runtime
   identity, seed, complete generation/budget, failures, cache counters, oracle
   counters, and the exact first-crossing score.  Cache hits or reused workspace
   state invalidate a formal cell unless the protocol explicitly proves the
   cached evaluation was already charged in the same formal history.

### Evidence interpretation and immediate checkpoints

- The 2026-08-30 hierarchical-CAE measurements are useful architectural
  diagnostics but are pre-fix and therefore cannot establish current
  performance.  In that evidence, CAE latent reconstruction was not the dominant
  Chrono limitation; parameter-to-latent prediction and narrow stress features
  were.  Test-com aggregate ranking was stronger, while SAW was mixed.
- A historical Butterworth-filter experiment reduced visual spikes but improved
  CAE error only marginally and did not fix raw-target error.  Filtering is not a
  selected production route.
- Next checkpoints: (1) close present-state Trebuchet repeatability; (2) inspect
  current CAE/linear-subspace code and build a clean post-fix, seed-101 candidate
  comparison; (3) use its measured failure modes to choose a general-purpose
  model change; (4) verify development crossings for all three baselines;
  (5) freeze wheels and run the held-out three-seed validation; (6) finish docs,
  installed-package tests, Git commit/fetch/push decision, and the required final
  result table.

## 2026-09-04 - clean current-CAE Chrono reassessment

The current installed yadof 0.6.0 hierarchical-CAE defaults were measured in a
fresh candidate-only seed-101 campaign at population 200 with the frozen GPSAF
and NSGA-III settings.  The candidate had no external archive, cache, oracle, or
reference threshold in its selection loop.  The benchmark authoring workspace is
`temp/20260904_080454-cae-current-seed101`; the exact durable metric analysis is
`c0001-analysis.json` below that workspace.

- The first generation was the paired random design.  Generation 2 attempted
  GPSAF before a fresh trained state existed and correctly fell back with
  `no_fresh_trained_surrogate`.  Generations 3--12 all used the hierarchical CAE
  in GPSAF alpha/beta selection.
- The run was deliberately stopped after generation 12 committed, before any
  generation-13 evaluation, because 2,400 is the Chrono 1.5x formal ceiling.
  All 12 generations contain exactly 200 formal records: 2,400 total, 2,237
  finite and 163 declared failures/non-finite.
- The cumulative top-10 metric improved monotonically from
  `Q(200)=0.31666821491515973` to `Q(2400)=0.24163108311277265` but did not cross
  `R=0.1985232880294068`.  The absolute remaining gap is
  `0.04310779508336585`, or about 21.7% of R.  Therefore current CAE fails the
  Chrono acceptance gate and has no admissible `N_candidate`.
- Prequential batch-maximum objective errors were large.  By generation 11 the
  rolling error vector was approximately
  `[0.4218, 0.7048, 0.8436, 0.9816]`; this confirms that the candidate was using
  a trained but inaccurate parameter-to-rawData model.
- End-to-end refitting also became a material operational defect: late fits took
  multiple minutes and the generation-12 fit accumulated substantial CPU time
  with about 2.4 GB resident memory.  Simulator batches were much faster than
  retraining.  This supports testing a fast nonlinear tabular mapping over a
  compact rawData representation rather than merely increasing CAE epochs or
  capacity.

This failed development arm remains valid evidence and will not be reused as a
candidate training archive.  Its formal history may be used only for labeled
offline diagnostics on seed 101, with any resulting design tested from a fresh
paired initial population.

## 2026-09-04 - nonlinear and direct-cost diagnostics

The clean current-CAE Chrono history was used only as offline seed-101
development evidence to test whether a faster nonlinear parameter mapper could
remove the measured bottleneck.  The executable diagnostics are
`temp/diagnose_nonlinear_subspace.py` and
`temp/diagnose_direct_cost_models.py`; their durable results are
`temp/20260904_080454-cae-current-seed101/chrono-offline-nonlinear-subspace.json`
and `chrono-offline-direct-cost.json` in the same directory.

- On a chronological split (generations 1--8 train, 9--12 validate), a
  16-component PCA representation retained 121 response coefficients.
  Extra Trees fitted those coefficients in 0.25 seconds and improved held-out
  aggregate-cost MAE/Spearman from the current linear mapper's
  `0.1589/0.3188` to `0.0928/0.4707`, but its predicted-best ten had true mean
  `0.3294` versus the validation oracle-best `0.2430`.
  Random Forest, random Fourier features, and a quadratic map were no better.
- A direct objective Extra Trees model improved the same held-out aggregate
  metrics to MAE `0.08450` and Spearman `0.5888`; its predicted-best ten had
  true mean `0.26459`.  This established a
  useful upper-bound diagnostic but not an acceptance-quality model.

To distinguish raw-response reconstruction from online acquisition behavior, a
fresh no-archive campaign used a diagnostic direct-objective Extra Trees model
inside the unchanged GPSAF/search loop.  The first authoring attempt at
`temp/20260904_084422-direct-cost-trees-chrono-seed101` failed before any
generation because the temporary model did not special-case the empty initial
training set; it consumed zero formal evaluations.  After correcting only that
diagnostic bookkeeping, the clean measured workspace was
`temp/20260904_084422-direct-cost-trees-chrono-seed101-v2`, with exact analysis
in `c0001-analysis.json`.

- The valid cell completed exactly 2,400 formal attempts, with 2,198 finite and
  202 failed/non-finite results.  It used the paired generation-zero population,
  no external archive, and no oracle/reference input.
- Extra Trees training was operationally cheap and GPSAF used the model from
  generation 3 onward.  Nevertheless `Q(2400)=0.2605478121255362`, which is
  `0.0620245240961294` above the ordinary reference and worse than the current
  CAE's `0.24163108311277265` at the same budget.
- This rules out rawData reconstruction as the dominant explanation for the
  online failure.  Direct objective prediction is moderately rank-informative
  on historical points but its piecewise-constant, non-extrapolating acquisition
  misdirects offspring selection.  The next checkpoint therefore targets a
  general-purpose uncertainty-aware/local acquisition and search policy, using
  only candidate-owned observations.

### Protocol amendment for a replacement architecture

The frozen success metric, ordinary/perfect reference arms, formal accounting,
strict ceilings, no-leakage rules, and held-out validation remain unchanged.
The earlier candidate clause required the CAE replacement to remain inside the
same NSGA-III/GPSAF acquisition loop.  The two clean diagnostics above show that
this restriction confounds response modeling with a selection policy that has
no candidate-local uncertainty and does not reliably exploit moderately useful
rank predictions.  Because the task explicitly permits replacing the CAE
architecture with a general-purpose alternative, candidate architectures may
from this point own their acquisition/search policy under these additional
controls:

1. generation zero must remain bitwise paired with the ordinary and perfect
   arms, and every later formal attempt counts normally;
2. only the candidate's own prior formal observations may influence fitting or
   selection; reference/oracle histories remain report-only;
3. one baseline-independent architecture/default set must preserve all objective
   values and use only generic operations (including equal-weight or diversified
   scalarizations), never a baseline identity or known threshold; and
4. any selected replacement must be integrated and documented as a supported
   yadof component, not left as an ad-hoc benchmark strategy.

This amendment broadens what is being replaced without changing the acceptance
gate.  Existing CAE/direct-tree cells remain comparable failure evidence because
their metric, pairing requirement, and charged formal budgets are unchanged;
the already frozen ordinary/perfect arms are unaffected and need not be rerun for
this development screen.

### Scalar and trust-region architecture controls

The first replacement control used a deterministic pymoo GA on the equal-weight
arithmetic mean of all current objective costs, retaining the existing genetic
operator defaults.  Its clean workspace is
`temp/20260904_090219-20260904_scalar-ga-chrono-seed101`; exact analysis is
`c0001-analysis.json`.

- Its generation-zero population SHA-256 is
  `411f483f75b5fd2c10fbc1542e53148fbacd5039c6896b26558a94857926c59c`,
  bitwise equal to both frozen Chrono arms.
- It completed 2,400 attempts with 2,252 finite and 148 failed/non-finite.
  `Q(2400)=0.22995390740188199`, an improvement over current CAE but still
  `0.03143061937247519` above the reference, so it fails.
- Its best individual was `0.21004976158114996`; this showed that it had found a
  useful basin but did not refine enough distinct top-ten members within budget.

The next control retained the same scalar GA as 30% of each post-initial batch
and used a baseline-independent portfolio for the other 70%: 80 Gaussian local
mutations around up to 32 observed elites, 30 smaller coordinate mutations, 20
differential mutations, and 10 global random candidates.  The trust radius is
`max(0.02, 0.18 * 0.82**generation_index)` and the expected mutated dimension
count is capped at seven.  These defaults were frozen before applying the
strategy to another baseline.  The clean Chrono workspace is
`temp/20260904_090819-scalar-trust-chrono-seed101`; exact analysis is
`c0001-analysis.json`.

- The valid cell completed exactly 2,400 attempts, with 2,272 finite and 128
  failed/non-finite.  Its generation-zero metric matches the paired arms and
  will receive the same independent byte-hash check before final acceptance.
- It first crossed at generation 10 / 2,000 formal evaluations:
  `Q(2000)=0.19274093588033997 < R=0.1985232880294068`.  This satisfies the
  Chrono development gate with 400 evaluations of ceiling margin.  The final
  `Q(2400)=0.18635589048803425`.
- No learned model, oracle, reference score, external archive, or baseline
  identity entered selection.  This establishes that multi-basin discovery plus
  aggressive local refinement is a viable replacement direction.  The exact
  architecture/defaults are now frozen for seed-101 SAW and test_com checks;
  failures there will drive a generic change and a full rerun, not a
  baseline-specific branch.

The unchanged cross-baseline run is retained at
`temp/20260904_091354-scalar-trust-saw-testcom-seed101`, with exact analyses in
`c0001-analysis.json` and `c0002-analysis.json`.

- SAW's generation-zero SHA-256 is
  `f6d9ec49c11823b1341ef7d35ff60009fc711e13d4306a1277466be78bc2c404`;
  test_com's is
  `861e1e7d2cb7702a2958c981a583203e1982a1b63439792b098a856aed8a6445`.
  Each is bitwise equal to its frozen ordinary/perfect pair.  Both cells
  completed without a failed evaluation.
- SAW ended at `Q(5600)=0.24512218282949833`, a
  `0.02513369398756549` gap above `R=0.21998848884193284`.  Test_com ended at
  `Q(5400)=0.293008839102435`, a `0.00280886917658893` gap above
  `R=0.29019996992584607`.  Neither has an admissible crossing, so the v1
  architecture fails the all-baseline development checkpoint.
- Offline geometry files `saw-offline-perfect-geometry.json` and
  `testcom-offline-perfect-geometry.json` use the separately retained perfect
  history for diagnosis only.  The v1 top ten collapsed into a late single
  basin on both tasks.  Its nearest distances to the perfect top-ten basins were
  roughly 0.30--0.54 in 10-dimensional SAW and 0.77--1.06 in 20-dimensional
  test_com.  The perfect histories include consequential basin-discovery jumps,
  while v1's local radius decays to 0.02 and 70% of each batch is locally
  generated.

The next generic revision will therefore preserve local refinement but add
objective-diverse discovery: equal-weight scalar GA, NSGA-III offspring,
deterministic random scalarizations, diversity-selected elite mutations, a
non-decaying broad mutation arm, and global random candidates.  Counts and
defaults are selected once without inspecting baseline variables or identities;
the revision must be rerun on all three development baselines if selected.

The frozen v2 SAW screen is
`temp/20260904_092628-scalar-discovery-v2-saw-seed101`; exact analysis is
`c0001-analysis.json`.  It completed 5,600 formal evaluations with 5,600 finite
results and no failures.  Generation 12 remained above the reference at
`Q(2400)=0.2234369789499712`, then the first strict crossing occurred at
generation 13 / 2,600 evaluations:
`Q(2600)=0.21881063253719463 < R=0.21998848884193284`.  This is well within the
5,600 complete-batch ceiling.  Final `Q(5600)=0.16760393984603986`.

V2 is therefore frozen without further parameter change.  Its exact source must
now pass Chrono and test_com seed 101 before it can be considered for product
integration; a failure will require a generic v3 and rerunning every affected
development baseline.

### Scope correction: optimizer controls are not surrogate candidates

The user clarified on 2026-09-04 that the scalar trust-region/discovery
portfolio is an optimization algorithm.  If retained as a product concept, it
belongs under `optimize` beside NSGA-III; it is not a CAE replacement and must
not be placed under `surrogate`.  The preceding "Protocol amendment for a
replacement architecture" is therefore revoked for acceptance and integration.

All scalar-GA, scalar-trust, and scalar-discovery-v2 results above remain useful
only as explicitly non-accepting optimizer upper-bound diagnostics.  They do
not establish progress toward the surrogate acceptance gate, regardless of
their score.  The unfinished test_com cell in
`temp/20260904_093226-scalar-discovery-v2-chrono-testcom-seed101` was interrupted
after this correction; its persisted benchmark state may remain stale at
`running`, and it will not be resumed or counted.

The candidate protocol is restored to the original frozen boundary: the
ordinary NSGA-III optimizer and GPSAF acquisition/settings stay fixed, while
only a surrogate implementation under `surrogate` may replace or improve CAE.
The surrogate may learn from the candidate run's own prior formal evaluations
only; ordinary/perfect histories, thresholds, and held-out results remain
report-only.  One architecture and one baseline-independent default set must be
used across test_com, SAW, and Chrono.  INR remains unchanged.

### Objective-surrogate development screen

With the corrected boundary in force, the next experiment changed only the
surrogate model and retained the frozen NSGA-III/GPSAF search and settings.  An
offline seed-101 development screen compared genuine multiobjective regressors
on the separately retained perfect-arm histories; those rows were never used by
the measured candidate.  The executable is
`temp/diagnose_objective_surrogates.py` and the durable result is
`temp/cae-surrogate-objective-model-screen.json`.

The best generic aggregate model in that screen was a three-member MLP ensemble
trained on every objective plus a scalar-coherence head, with a smooth
rank-derived emphasis on the low-cost tail.  It reduced aggregate mean scalar
MAE from Extra Trees' 0.08078 to 0.04538 and improved mean Spearman correlation
from 0.7473 to 0.8085, although its low-tail regret remained material on Chrono
and SAW.

That frozen MLP was then run from an empty archive in the clean workspace
`temp/20260904_094525-objective_mlp_seed101`.  Its source explicitly identifies
it as a development objective surrogate; the nearest-observed rawData payload
is only a temporary compatibility placeholder and is not eligible for product
integration.  The measured model consumed only its own prior finite formal
costs, while NSGA-III, GPSAF alpha/beta/gamma/exploration/HV settings, population,
seed, and initial population remained unchanged.

- The cell completed exactly 2,400 formal attempts: 2,164 finite and 236
  failed/non-finite.  Generation one reproduced the paired metric
  `Q(200)=0.31666821491515973`.
- It used the surrogate from generations 3--12 without selection fallbacks.
  End-to-end runtime was about 3.3 minutes for evaluation and repeated fitting,
  eliminating CAE's multi-minute-per-fit operational problem.
- Exact frozen-metric analysis is `c0001-analysis.json`.  Final
  `Q(2400)=0.2494015116683464`, which is
  `0.05087822363893961` above Chrono's reference.  It is worse than the current
  CAE's 0.24163108311277265 and therefore fails with no admissible crossing.
- Late prequential maximum-error scales remained very large, approximately
  `[0.4273, 0.1254, 0.2860, 0.9649]` at generation 12.  Direct target learning
  and faster training alone are therefore insufficient; this architecture will
  not proceed to product integration or cross-baseline candidate runs.

The next surrogate-only checkpoint tests local objective response models that
can extrapolate within the optimizer's nearby offspring, rather than another
global regressor or a surrogate-owned search policy.

### Product-module boundary clarification

The user further clarified that a substantially different surrogate
architecture must not replace or be hidden inside the existing
`surrogate.hierarchical_cae` module.  If a non-CAE architecture eventually
passes the evidence gates, it must be integrated as its own public module under
`yadof.surrogate`, with CAE retained as a distinct implementation.  Only changes
that remain genuinely part of the hierarchical CAE architecture may modify that
module.  All objective-tree/MLP/local-model work so far remains temporary
development code under `temp`; no product source has been changed.

### Local and probabilistic objective-surrogate rejection

The local-linear development screen is retained at
`temp/cae-surrogate-local-objective-screen.json`, generated by
`temp/diagnose_local_objective_surrogate.py`.  Across the three held-out
seed-101 perfect histories, its variants had mean predicted-best-ten regrets of
approximately 0.0776--0.1143.  They were materially worse than the global
objective MLP and were rejected before an online candidate run.

An independently implemented ARD Matérn Gaussian-process screen is retained at
`temp/cae-surrogate-ard-gp-screen-v2.json`.  It used at most 800 past rows, a
scalar-coherence target, and data-derived length scales.  Its mean
predicted-best-ten regret was 0.07723.  Even a diagnostic conservative
mean-plus-two-standard-deviations selection yielded true best-ten means of
0.23844 on Chrono, 0.285924 on SAW, and 0.292427 on test_com, all above their
respective ordinary references.

The frozen conservative GP was nevertheless tested online from an empty archive
with the ordinary NSGA-III/GPSAF boundary unchanged.  The clean workspace is
`temp/20260904_100140-objective_gp_seed101`; exact analysis is
`c0001-analysis.json`.  It completed 2,400 formal attempts, with 2,222 finite
and 178 failed/non-finite evaluations.  Final Chrono
`Q(2400)=0.2514192634105782`, which is `0.0528959753811714` above the ordinary
reference and worse than both current CAE and the objective MLP.  It had no
admissible crossing and is rejected.

### Existing-member uncertainty and CAE-like auxiliary supervision

The current CAE's five predictor members were re-evaluated offline without new
oracle calls.  The diagnostic
`temp/20260904_080454-cae-current-seed101/chrono-offline-cae-member-acquisition.json`
uses only candidates that the clean current-CAE run had already selected and
then truly evaluated.  Selecting ten rows per retained generation by decoded
raw mean gave aggregate true mean 0.37459; member mean, mean-plus-one-standard-
deviation, mean-plus-two-standard-deviation, and member maximum gave 0.33197,
0.30550, 0.30550, and 0.33131 respectively, versus an oracle ten-row mean of
0.241631.  Member dispersion contains some useful ordering signal, but the
selected candidate tail is too poor for uncertainty alone to close the gap.

A second offline diagnostic tested cost-relevant auxiliary supervision while
preserving CAE semantics: the model predicted PCA coefficients, decoded those
coefficients to `rawData`, and obtained every reported prediction by running the
unchanged task interpreter on that decoded payload.  Direct cost heads were
training-only auxiliaries and never replaced decoded `rawData` at inference.
The executable is `temp/diagnose_nonlinear_subspace.py`; the durable result is
`temp/20260904_080454-cae-current-seed101/chrono-offline-objective-aware-latent.json`.

On generations 9--12 after training through generation 8, the no-auxiliary MLP
had scalar Spearman 0.32222 and the ten candidates it predicted best had true
mean 0.31709174672396523.  Repeating objective auxiliaries 4 and 16 times raised
Spearman to 0.47126 and 0.49614, but worsened predicted-best-ten true mean to
0.360494731124435 and 0.4246944819877525.  The validation set's true best-ten
mean was 0.24299893591948996.  This
naive auxiliary-loss construction improves global rank correlation while
damaging the low-cost tail and is rejected before online use.

### Metric correction: do not use individual overlap

The user clarified on 2026-09-04 that exact individual overlap is not a relevant
validation target in a continuous floating-point search space with stochastic
optimization.  Some development diagnostics recorded a `best10_overlap` field;
within those files it meant index-set recovery inside one fixed held-out
candidate table, not equality of individuals across independent runs.  Even so,
it is not an acceptance metric and must not drive model choice or appear as
evidence of optimization quality.  From this point onward, decisions and reports
use the true cost attained by selected/formally evaluated individuals, especially
the documented cumulative mean of the ten lowest true costs and its first strict
crossing budget.  Existing overlap fields remain only as immutable diagnostic
payload and are ignored.

### Rejected local, ensemble, ranking, and regime objective variants

The decoded-rawData local interpolation screen is retained at
`temp/20260904_080454-cae-current-seed101/chrono-offline-local-rawdata.json`.
On the same generations-1--8 / generations-9--12 Chrono split, the best local
variant was a 64-neighbour affine latent predictor.  The ten candidates it
ranked best had true mean cost 0.27944838200723093, versus 0.24299893591948996
for the ten lowest true costs available in that held-out candidate table.
Nearest-neighbour and kernel-weighted decoded-response interpolation were worse.

Tree-member uncertainty and cross-validated objective ensembles were screened
across all three development histories in
`temp/cae-surrogate-tree-uncertainty-screen.json` and
`temp/cae-surrogate-adaptive-objective-ensemble.json`.  Conservative tree
quantiles did not materially improve the attained low-cost tail.  The best
OOF-adaptive rule had mean held-out best-ten regret about 0.04162, essentially
the same scale as the earlier fixed MLP, despite lower aggregate prediction
error for some blends.

A state-digest-seeded eight-tree posterior function draw was then tested online
under unchanged NSGA-III/GPSAF in
`temp/20260904_102800-tree-posterior-chrono-seed101`.  Exact analysis is
`c0001-analysis.json`.  It completed 2,400 formal attempts with 2,238 finite and
162 failed/non-finite rows.  Final Chrono
`Q(2400)=0.24578044003122565`, a `0.04725715200181885` gap above the ordinary
reference and worse than current CAE.  It had no admissible crossing and was not
continued to the other baselines.

The strongest subsequent direct-objective diagnostic was a two-member residual
MLP without Fourier features.  Evidence is in
`temp/cae-surrogate-pairwise-rank-screen.json` and
`temp/cae-surrogate-pairwise-rank-screen-v2.json`.  Its mean cross-baseline
held-out best-ten regret was 0.03524325349843096.  Fourier features were much
worse, and pairwise rank weights 0.05, 0.2, and 1.0 did not improve the plain
robust-regression result.  Its attained held-out tail remained about 0.23 on
Chrono, 0.28 on SAW, and 0.29 on test_com, so it still did not justify an online
candidate against the stricter crossing targets.

Consensus blends with Extra Trees and histogram gradient boosting are retained
at `temp/cae-surrogate-residual-consensus-screen.json`; every mean, median, and
pessimistic-maximum rule was worse than the residual network alone.  Generic
failure-regime models were also tested because the Chrono prefix contains 434
rows with at least one objective at the error-cost atom, while SAW contains 232
and test_com contains none.  Tree gates in
`temp/cae-surrogate-regime-objective-screen.json` and a masked residual mixture
in `temp/cae-surrogate-regime-residual-screen.json` both worsened the attained
tail.  The best masked-mixture policy had mean regret 0.04340.

These results reject the current direct-cost family (global mean models,
conservative tree/GP uncertainty, posterior tree draws, CV AutoML, pairwise
ranking, model consensus, and failure-regime gates) as an acceptance candidate.
They remain development diagnostics only, use nearest-observed rawData solely as
a temporary compatibility payload where run online, and are not eligible for
product integration.  A substantially different future surrogate still follows
the separate-module requirement under `yadof.surrogate`.

Kernel regressors were also screened under the same historical-prefix / future-
generation split.  The durable result is
`temp/cae-surrogate-kernel-objective-screen.json`.  The best support-vector
regression variant had cross-baseline mean held-out best-ten regret about
0.05594, worse than the residual network and far from an acceptance candidate.

### CAE latent calibration and longer response fine-tuning

Two diagnostics tested whether the current CAE merely needed a better-scaled
latent loss or more response-level fine-tuning.  Both recover the immutable
generation-8 Chrono checkpoint, train only on its recorded 1,471-row prefix, and
use the following 766 already evaluated rows solely as a development holdout.
They make no new simulator calls and never expose the holdout during fitting.

`temp/20260904_080454-cae-current-seed101/chrono-offline-cae-scaled-latent-checkpoint.json`
retrained the existing parameter-to-latent predictors after normalizing each
latent dimension by its training variance, then applied the standard 12-epoch
response fine-tune.  Its selected held-out ten had true mean cost
0.3480970098884594, versus the held-out oracle ten mean
0.24299893591948996 (regret 0.10509807396896942).  This simple calibration is
rejected.

`temp/20260904_080454-cae-current-seed101/chrono-offline-cae-finetune-96.json`
instead left the checkpoint predictors unchanged and attempted 96 additional
response-level fine-tune epochs.  Field-macro validation loss increased from
0.15282755025795527 to 0.15301241087062017, so the existing acceptance gate
correctly rejected the candidate.  Its selected held-out ten had true mean cost
0.4718807361582268, versus 0.24299893591948996 for the held-out oracle ten.
Thus the observed mapping bottleneck is not explained by the default 12-epoch
fine-tune budget alone.  The next CAE work must make the learned representation
predictable from parameters during representation training, rather than merely
post-calibrating an arbitrary reconstruction latent space.

### Training-compute authority clarification

The user clarified on 2026-09-04 that the current benchmark simulators are
deliberately cheap validation vehicles and must not impose their short wall time
as an architecture constraint.  For intended expensive workloads such as 3-D
FEM, one generation is expected to take at least about two hours; model training
up to roughly one hour per generation is acceptable when it improves formal-
evaluation efficiency.  Candidate decisions therefore prioritize the frozen
true-cost/crossing target.  Training and inference wall time remain reportable
tradeoffs, and the intended operational guard is that one generation's training
stay below one generation's expensive simulation time, not that training finish
within a few minutes on these benchmark tasks.

### Predictable-latent and higher-compute CAE diagnostics

`temp/20260904_080454-cae-current-seed101/chrono-offline-cae-predictable-joint.json`
tested three symmetric predictable-latent joint objectives starting from the
immutable generation-8 CAE checkpoint.  All fitting used only its 1,471-row
prefix; 766 later rows were metrics-only.  The weakest regularizer changed the
held-out selected-ten true mean only from 0.4718807361582268 to
0.4712343673237651.  Stronger variants retained the original state because
internal predicted-field validation did not improve.  Checkpoint-local joint
fine-tuning is rejected.

The higher-compute from-scratch test is retained at
`temp/20260904_080454-cae-current-seed101/chrono-offline-cae-predictable-from-scratch.json`.
It used a 64-wide codec, global/group/private latent sizes 64/32/32, five
512-wide five-layer predictors, up to 300 codec and 600 predictor epochs, then
up to 500 joint epochs with reconstruction and symmetric predictability losses.
The staged model took about 230 seconds and attained held-out selected-ten true
mean 0.42149486293485783.  Joint training stopped after 166 epochs and improved
that value to 0.3894578941391281; total wall time was about 736 seconds.  This is
better than the original checkpoint but remains 0.14645895821963817 above the
held-out oracle ten and is rejected before online use.  The result also confirms
that training-time limits were not driving rejection.

### Conditional response and local response alternatives

A substantially different conditional rawData architecture was kept separate
in `temp/diagnose_conditional_response_subspace.py`, with the corresponding
Chrono evidence at
`temp/20260904_080454-cae-current-seed101/chrono-offline-conditional-response-subspace-v2.json`.
It fits a leakage-safe adaptive PCA response basis and trains three 512-wide,
six-block residual networks.  The 1,414 retained coefficients preserve the
held-out response well: projecting the true held-out response into and out of
the basis yields selected-ten true mean 0.2432356403048684 versus the unprojected
oracle 0.24299893591948996.  Therefore representation loss is negligible for
cost at this rank.  The learned mapping remains the bottleneck: plain and
harmonic networks attained 0.3797173528181592 and 0.34137990753532177,
respectively.  Both are rejected.

The local high-rank version is retained at
`temp/20260904_080454-cae-current-seed101/chrono-offline-local-conditional-response.json`.
Its rule was selected only by an internal chronological suffix; the later arm
remained metrics-only.  The selected 32-neighbour Gaussian affine rule attained
held-out selected-ten true mean 0.2765275300065972 versus oracle
0.24299893591948996.  Although materially better than global CAE mappings, it
was not stable across the three development histories.  Applying the same
configuration space and internal rule selection to the frozen perfect-history
prefixes produced:

- Chrono: 0.2738305085745196 versus oracle 0.19748450111281463
  (`temp/local-conditional-response-perfect-chrono-seed101.json`);
- SAW: 0.30406429580666466 versus oracle 0.21630982566898896
  (`temp/local-conditional-response-perfect-saw-seed101.json`);
- test_com: 0.30284340285414557 versus oracle 0.2894819565390385
  (`temp/local-conditional-response-perfect-testcom-seed101.json`).

This alternative is rejected before online use.  The rank-3 test_com screen also
showed that a naive flattened rank-256 basis can consume about 7.6 GB; any future
high-dimensional response module must use field-wise blocked or tensorized
bases rather than relying on an unbounded flat representation.

### Elite-ordinal objective screen

`temp/cae-surrogate-elite-ordinal-screen.json` tests a cost-only development
architecture that combines four empirical elite-quantile classifiers with a
direct scalar regressor rank.  Its one cross-baseline-selected rule was an RBF
SVC ordinal score plus scalar weight 2.  Selected-ten true means were
0.25413337156998095 on Chrono, 0.29491775745779836 on SAW, and
0.3004696050129819 on test_com; mean regret was 0.04874815023997304.  This is
worse than the earlier residual MLP and is rejected.  It never used placeholder
rawData and was not integrated; any future cost-only replacement would require
an explicit, documented rawData-capability migration rather than pretending a
nearest observed response is a genuine prediction.

### Field-wise and summary-corrected response diagnostics

`temp/20260904_080454-cae-current-seed101/chrono-offline-fieldwise-conditional-response.json`
replaces a shared flattened response map with independently selected models for
each schema field.  The selection rule and split are task-neutral and the 766
later Chrono rows remain metrics-only.  The selected-ten true mean was
0.3188132074283806 versus the held-out oracle 0.24299893591948996, so the
architecture is rejected.  Its per-field losses nevertheless localize the main
mapping error in event-dependent fields: standardized losses for fields 1, 2,
4, 12, 13, and 14 were about 0.2785, 0.2473, 0.2698, 0.2080, 0.3817, and
0.3418, while several smooth or directly determined fields were much easier.
This supports regime-aware work, but no Chrono field name or index may become a
product branch.

`temp/20260904_080454-cae-current-seed101/chrono-offline-summary-corrected-response.json`
tests a generic schema-driven correction of the selected 32-neighbour local
response.  For every nonscalar field it predicts first, last, minimum, maximum,
mean, and standard deviation; scalar fields with at most eight observed values
are treated as categorical after leakage-safe class encoding.  Internal
validation selects among Extra Trees, histogram gradient boosting, and an MLP
per field.  The run took 92.82 seconds.  The base selected-ten true mean was
0.2765275300065972.  Endpoint, extrema, and all-summary correction produced
0.30026786477940376, 0.3967893150050673, and 0.4032478798734408 respectively,
all versus oracle 0.24299893591948996.  Although all-summary correction reduced
whole-holdout average-cost MAE from 0.1382242 to 0.0884766, it substantially
worsened the low-cost tail.  It is therefore rejected and provides a concrete
warning not to select a surrogate by global response or cost error when the
acceptance metric is the true-cost best-ten tail.

### Tail-distribution and joint response-cost surrogate screens

`temp/cae-surrogate-tail-distribution-screen.json` evaluates a separate,
baseline-independent multi-task surrogate with objective, scalar cost,
empirical-rank, and low-quantile classification heads.  Every member selects
its epoch count on an internal prefix split and is then retrained on the full
prefix; three tail-weight/pairwise-loss settings and deterministic uncertainty
policies were screened identically on all three development cases.  The best
single cross-baseline rule was tail weight 10 with a pessimistic three-head
score plus 0.5 ensemble standard deviation.  Its mean best-ten regret was
0.03503845873831946.  Per-case diagnostic minima were 0.21672490873489747 on
Chrono, 0.28525116007517487 on SAW, and 0.29823782097506085 on test_com.
The architecture improves Chrono but does not solve SAW and is not an online
candidate by itself.

The generic rawData subspace result for SAW is retained at
`temp/conditional-response-perfect-saw-seed101.json`.  Two field-wise PCA bases
retain 269 coefficients and are effectively lossless for the target: projecting
the true future responses gives best-ten true mean 0.21682817890081346 versus
oracle 0.21630982566898896.  Three 512-wide six-block conditional networks give
0.28606665919692736 with plain inputs and 0.3038608660145786 with harmonic
features.  As on Chrono, parameter-to-response mapping, not representation, is
the bottleneck.

`temp/multitask-response-cost-perfect-{chrono,saw,testcom}-seed101.json` tests a
shared-trunk surrogate with genuine rawData-subspace, objective-cost, scalar,
and tail-rank heads under one fixed configuration.  The same direct/response
mean policy attained held-out best-ten true means 0.24554635827394602 on
Chrono, 0.23794404668786767 on SAW, and 0.29255477674768365 on test_com.  On
SAW this is a large, complementary-error improvement over the direct head
(0.2854170891232565) and response head (0.27021253485729113) individually.
The test_com direct head reached 0.2918701702612955.  Chrono still needs the
tail-distribution expert, so the fixed policy is not accepted; the evidence
supports a task-neutral internal-validation gate between surrogate experts.

An 80-epoch low-rate full-prefix fine-tune is retained separately at
`temp/multitask-response-cost-perfect-saw-seed101-v2.json`.  Although whole-
holdout Spearman correlation for the direct/response blend improved from about
0.9105 to 0.9177, selected-ten true mean worsened from 0.23794404668786767 to
0.27506597271645805.  Full-prefix fine-tuning is rejected.  The naive flattened
test_com PCA also reached about 7.5 GB working set (about 10.3 GB private
memory); any integrated implementation must use blocked or tensorized bases.

### Expert-gate and blend rejection

The internal policy gates in
`temp/multitask-response-cost-perfect-saw-seed101-v3-gated.json`,
`temp/multitask-response-cost-perfect-chrono-seed101-v3-gated.json`, and
`temp/multitask-response-cost-chronological-chrono-seed101.json` were rejected.
Random/design validation selected the three-head mean on SAW (future true
best-ten mean 0.2496193631) and the response head on Chrono (0.29468119), while
chronological validation selected a direct/response policy whose later Chrono
result was 0.274104.  The expert ordering reverses under the optimization
distribution shift, so these gates cannot justify a baseline-independent
product rule.

Fixed cross-case score blends are recorded in
`temp/cae-surrogate-expert-blend-{chrono-saw,response-chrono-saw,direct-chrono-saw,three_head_mean-chrono-saw,three_head_pessimistic-chrono-saw}.json`.
No common weight improved both Chrono and SAW.  For example, the best balanced
tail/joint-direct-response blend used tail weight 0.125 but yielded 0.239613 on
Chrono and 0.248365 on SAW.  These blends are rejected.  All decisions use true
cost levels and regret; exact individual overlap is not an optimization metric.

### Online joint response/cost surrogate: SAW passes

`temp/joint_response_cost_surrogate/optimization.py` is a development-only,
separate surrogate architecture, not a CAE replacement hidden inside
`hierarchical_cae` and not an optimizer.  It uses the frozen NSGA-III and GPSAF
settings, learns a field-wise low-rank rawData response plus direct objective
cost and rank heads, reconstructs genuine predicted rawData, and applies one
fixed task-neutral selection rule: equal-weight direct/response objective cost.
Every generation is retrained only from finite formal history committed before
that generation.  No reference, perfect-surrogate arm, future row, or baseline
identifier enters training or prediction.

The source frozen for the run has SHA-256
`518009E198271DE9BF32BECA2F7A2974988D5DE1CA89786D793222902B396944`; the
materialized optimization source has the identical hash.  The three-generation
SAW smoke run at
`temp/20260904_190825-20260904_joint_response_cost_saw_smoke3` completed
600/600 finite evaluations and exercised real reconstructed rawData prediction.

The clean formal seed-101 SAW cell is
`temp/20260904_191100-20260904_joint_response_cost_saw_seed101`, with the frozen
metric recomputation in `cae-goal-analysis.json`.  Benchmark status is completed
and valid with no anomalies: 5,600 attempted, 5,600 finite, zero failures.  The
ordinary NSGA-III reference is 0.21998848884193284; the perfect-surrogate first
crossing is 3,800 formal evaluations, giving a 5,700 allowance (5,600 under the
whole-generation protocol).  This surrogate first crosses at 4,600 evaluations
with cumulative true-cost best-ten mean 0.21527631173499845, a margin of
0.00471217710693439.  The final value is 0.188208962650707.  The yadof run took
6,164.497 seconds and the complete benchmark cell 6,197.852 seconds.  SAW is
therefore the first baseline to pass the documented performance and budget
gate; Chrono and test_com remain unproven.

The same byte-identical source was then run on Chrono at
`temp/20260904_205720-20260904_joint_response_cost_chrono-seed101` (actual
workspace directory
`temp/20260904_205720-20260904_joint_response_cost_chrono_seed101`).  The cell
completed validly with no benchmark anomalies: 2,400 attempted, 2,210 finite,
and 190 physical failures.  Its final cumulative true-cost best-ten mean was
0.240735292166676, versus reference 0.1985232880294068, leaving a gap of
0.0422120041372692 and no crossing within the 2,400 cap.  This is only a small
improvement over the repaired current CAE's 0.24163108311277265 and rejects the
fixed direct/response rule as a three-baseline solution.  The next architecture
must preserve the SAW complementary-response behavior while adding a generic
tail treatment for failure/discontinuity-heavy histories; it may not branch on
the Chrono name.

Adaptive joint/tail v2 (source SHA-256
`08AAEB892CDAB5B745B6EC4AC76A17CDD6124B908AB8A35448C300978D6CB02C`) is
recorded at `temp/20260904_213857-20260904_adaptive_joint_tail_chrono_seed101`.
It adds the fixed tail10/pair0.2 scalar-rank-ordinal ensemble and chooses that
head only when observed failures are at least
`max(10, ceil(sqrt(formal attempts)))`; this selected the tail head on Chrono
without consulting a baseline identifier.  The valid completed cell had 2,400
attempts, 2,226 finite results, and 174 failures.  Final true-cost best-ten mean
was 0.237588341925906, a 0.0390650538964991 miss.  This modestly improves v1
and reduces failures, but is rejected.  The next isolated question is whether
re-expanding the offline scalar tail score into a predicted multiobjective
shape lets Pareto/hypervolume selection destroy the scalar ranking that made
the offline diagnostic useful.

Adaptive scalar-tail v3 (source SHA-256
`D6D8A2C1491A5DB78774C8DFC153EE3E542871E2DA1DD1061B8AF87B2C0C55FC`) is
recorded at `temp/20260904_221052-20260904_scalar_tail_chrono_seed101`.  When
the generic failure gate is active it replicates the same tail scalar over all
objective columns, preserving the offline average-cost ordering through
GPSAF.  The cell completed validly with 2,400 attempts, 2,204 finite rows, and
196 failures.  Final best-ten true mean was 0.233895283981025, leaving
0.0353719959516183 and no crossing.  This improves v2 only modestly and is
rejected.

`temp/tail-uncertainty-online-chrono-v3-g6.json` refits the same tail family on
the first six v3 generations, selects uncertainty/head policy only on an inner
chronological suffix, and keeps generations 7--12 completely held out.  The
selected optimistic three-head mean still chose a future ten with true mean
0.2778294311160689; even the future-oracle-best policy among all tested heads
and mean plus/minus two standard-deviation rules gave 0.27646815673463576
versus 0.23528776750149674 available in that fixed candidate arm.  Uncertainty
sign alone is therefore rejected.

A read-only geometry comparison shows that v3 found no individual below the
0.1985232880294068 reference (its best was 0.20998634240429698).  The ten best
points of the non-accepting scalar-trust optimizer control are all about
0.38--0.43 normalized L2 from the nearest v3 observation.  This is diagnostic
evidence of missed-basin discovery, not acceptance evidence for that optimizer.
The tail model currently discards all failed attempts, leaving a
missing-not-at-random hole.  The next generic surrogate revision will train its
cost/tail head on every formal parameter row with failures imputed to the
documented unit error cost, while its genuine rawData head remains restricted
to samples that actually have responses.
