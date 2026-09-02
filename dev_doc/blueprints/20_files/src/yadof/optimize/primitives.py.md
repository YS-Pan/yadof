# File blueprint: src/yadof/optimize/primitives.py

## Intent

- Expose one backend-neutral, explicitly composable search/prediction/selection
  boundary without publishing concrete pymoo objects or durable mid-stack state.
- Make real-only, GPSAF, and posterior full-real fallback share identical history,
  archive, seed, refill, and source-naming mechanics.

## Values and ownership

- `SearchCandidate` freezes one transient candidate ID, normalized row, rounded
  duplicate key, origin, state root/ordinal, and optional separate source evidence
  ID. It never carries a pymoo `Individual`.
- `SearchState` exposes deterministic strategy/generation/problem/seed/archive
  identity, revision, counters, and bounded diagnostics. Its private token-protected
  runtime owns cloned pymoo state, context, history archive, and Python RNG state.
- `CandidatePool` and `CandidateSelection` align ordered unique candidates to exact
  backend records privately and expose only normalized `population` publicly.
- `PredictedCostRows` aligns finite current-cost means to exact candidate IDs and
  rows, interpretation fingerprint, fitted-state signature, and source. It is not
  real `CostTable`, rawData-owning `SurrogatePrediction`, or posterior
  `JointObjectiveSamples`.

## Operations

- `prepare_search()` binds one root to the exact strategy signature, generation,
  task interpretation snapshot, problem shape, search semantic identity, history,
  seeds, and duplicate precision, then asks the private adapter to reconstruct the
  history-informed algorithm.
- `search_candidates()` clones input state, delegates ask to pymoo, applies one
  bounded unique refill policy, and returns an exact pool plus next state. Exhaustion
  raises `InsufficientCandidatePoolError`; partial success is never returned.
- `bind_surrogate_prediction()` consumes the Stage 4 DTO. The explicit legacy
  binder accepts only plain deterministic current-cost rows and rejects real,
  posterior, and unbound surrogate owners.
- `combine_predicted_cost_rows()` selects ordered candidate subsets from one or
  more prediction supersets and concatenates them only when interpretation, fitted
  state, source, objective width, and candidate bindings agree exactly.
- `select_candidates()` delegates current-cost survival to pymoo;
- `select_candidate_indices()` returns an ordered validated subset for positional
  tournaments, without adding environmental survival. Predicted rows preserve an
  explicit validity mask; only failed rows may carry all positive infinity.
  `advance_search()` delegates beta simulation to pymoo tell. Neither mutates input
  state.
- `fork_search_state()` and `continue_search_from()` support deterministic
  same-generation branches while keeping algorithm state separate from archive/RNG
  bookkeeping.
- `compose_real_population()` preserves ordered unique groups and bounded refill.
  `full_real_search()` is the sole complete no-history random, generation-zero warm
  start, and later-offspring path.

## Invariants

- Search selection is only a continuation commit point. Real evidence can be
  committed only by the common evaluator/finalizer/recorder path.
- State cannot cross a strategy, generation, problem/snapshot root, cannot be
  constructed without the framework token, and deliberately refuses pickle.
  Durable resume reconstructs from real history at a generation boundary.
  Real generation and population labels participate in state identity/replay.
- Concrete pymoo imports occur only inside operations. Pymoo owns algorithms,
  operators, `Individual`, ask/tell, reference directions, and survival.
- Candidate identity, rounded design equivalence, and durable evidence identity are
  never interchangeable. Predicted values never enter history, checkpoint, recorder,
  `EvidenceDataset`, or `CostTable`.
