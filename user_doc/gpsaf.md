# GPSAF mechanisms and workflow adaptations

The selection contract follows Blank and Deb's
[GPSAF paper](https://arxiv.org/abs/2204.04054), Sections III-A/B and Algorithms 2/3.

- Alpha asks `alpha` batches without advancing the real algorithm. Each position
  holds its own tournament. If all competitors are infeasible, choose minimum
  total positive constraint violation; otherwise choose a nondominated feasible
  competitor. Break ties randomly. `alpha=1` disables alpha pressure; the legacy
  value zero also means no alpha pressure.
- Beta clones the alpha algorithm state and performs `beta` consecutive surrogate
  ask/tell advances. Assign every candidate from every advance to the nearest
  alpha anchor using squared Euclidean distance in normalized design coordinates.
  Exact distance ties go to the first anchor, deterministically.
- Each nonempty cluster runs a PKT. Shuffle once, duplicate a random participant
  in odd rounds, and compare pairs until one remains. Add independent fresh noise
  to each objective/constraint of each competitor in each match. This adapter uses
  zero-mean normal noise with the error estimate as its standard deviation; the
  paper leaves the noise distribution unspecified. Zero error adds exactly zero.
- The cluster winner replaces its anchor with probability
  `rho_j = (len(U_j) / max(len(U_k))) ** gamma`. Empty clusters keep their anchor;
  a largest nonempty cluster always replaces it. `gamma` is finite and nonnegative.
  A beta winner need not dominate the alpha anchor: PKT selects within its cluster.

`gpsaf_settings(infill_selection="cluster")` is the default selection policy above.
The optional `infill_selection="hypervolume"` replaces a completed beta batch with
greedy predicted hypervolume coverage relative to the finite real history supplied
by the generation context. Its pool contains the alpha anchors and every beta
candidate. Pymoo computes hypervolume with a fixed all-one reference point, matching
the task's normalized `[0, 1]` minimization costs. Each selected candidate updates
the reference archive before the next marginal gain is computed. Exact gain ties
use pool order; gains at or below `1e-12` end greedy selection.

When positive gains run out, fill the remaining slots with valid original
PKT/gamma choices in their original order, then other valid pool candidates, then
invalid candidates if necessary to keep the requested batch size. Finite `1.0`
penalties remain valid. The configured unassisted exploration quota is composed
after this selection. Alpha and beta ask counts, the genetic operators, and the
restored real optimizer state retain their existing semantics. If beta is disabled
or still waiting for an error estimate, selection uses the alpha result.

This policy uses deterministic predicted means; it does not integrate predictive
uncertainty or replace the posterior-assisted/qNEHVI workflow. PKT error scales and
gamma still determine the fallback order. Use it explicitly when coverage of the
normalized objective space is the intended selection criterion, and validate it
with the chosen surrogate and task. A perfect-oracle experiment does not establish
performance for learned models. Exact hypervolume also adds selection computation;
reduced selected-evaluation counts do not imply lower total oracle cost.

Programs own one `GPSAFErrorState` per run. After materializing prior real training
data, explicitly call
`initialize_gpsaf_error(surrogate, step.context, training, error_state)`, then pass
`error_state=error_state` to `select_gpsaf_generation()`. After true evaluation, call
`error_state.observe(selected, evaluation.costs)` using the captured selection.
The value stores pre-evaluation predictions separately from real history, so
asynchronous fitting cannot change the residuals being measured.

The error statistic is maximum absolute error per objective in a newly evaluated
batch, then an arithmetic moving average over the latest five estimates. The
initial estimate participates in that window. Failed real outcomes do not invent
finite residuals. Deterministic zero-width prediction intervals are unrelated to
model error. State resets when the task interpretation changes.

PCA/SVD supplies a side-effect-free five-fold bootstrap: fit independent models on
training folds, predict only held-out rows, and evaluate both sets through the
current cost chain. With two to four samples it uses leave-one-out; fewer than two
leave beta waiting. No checkpoint, formal evaluation or recorder is created by
this bootstrap. A true simulation oracle supplies exact zero initial error and
audits selected predictions against later formal evaluation.
Freshness asks the component for its current compatible generation even when
training data is empty. A training-free oracle reports the current context
generation, including when the allowed lag is zero; it needs no fabricated
training sample. Learned components without a state still wait for explicit fits.

Conditional INR and hierarchical CAE retain their asynchronous fit APIs and
rawData modeling. Without a bootstrap estimator, alpha gathers the first
prequential error batch and beta waits for it. This explicit cold-start adaptation
avoids fitting hidden neural models during selection or pretending model error is
zero. An independently measured initial estimate can instead be passed to
`GPSAFErrorState(initial_error=...)`. On resume, a new state re-estimates the error;
predictions are never reconstructed from training-set fit residuals.

Other retained adaptations:

- yadof tasks enforce parameter constraints and derive objective penalties in the
  task cost chain. The bundled problems expose no separate surrogate constraint
  vector. The tournament primitive supports general `G <= 0` constraints.
- Components predict rawData and then current costs, rather than the paper's
  independent RBF/Kriging model selection per function. The components remain
  explicit choices; GPSAF does not select or refit them implicitly.
- The default 10% unassisted exploration quota is an explicit extension to the
  paper. Duplicate filtering and bounded refill retain the workflow contract.
- True history is replayed in `(optimization_index, generation_index,
  population_index)` order with one tell per real generation. NSGA-III retains its
  survival/normalization state and generation count. Survival and infill have
  separate deterministic generation streams; alpha/PKT use another local stream.
  Beta advances cloned algorithms and cloned individuals, never the real state.
- Only successful finite real history is replayed. Unscoped smoke and oracle rows
  never enter the archive. Legacy history without generation labels is one warm
  start batch. State remains reconstructible at generation boundaries without
  pickling private pymoo objects.

Ordinary unavailable/stale fitted models can fall back to real selection.
`SurrogateContractError` is a fatal implementation/interface error. A simulation
oracle represents only declared physical failures as invalid `+inf` predictions;
finite all-one cost vectors remain legitimate results.
