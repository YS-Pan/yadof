# qNEHVI acquisition and posterior-assisted framework

## Scope and inherited scientific boundary

This change executes the independently legal framework portion of TODO 082611. It
does not change GPSAF, tune the hierarchical CAE, alter any v5/v8 threshold, open a
protected dataset, or execute the 082612 acceptance/release campaign. Gate 0 v5
still rejects the hierarchical architecture, Gate 0 v6/v7 remains
`experimental / performance-not-accepted`, and all six v8 calibration artifacts
remain uncalibrated and non-transferable. Consequently, every currently shipped
posterior component is typed as ineligible for exploitation.

## Implementation-day library audit

The selected environment used CPython 3.13.11, BoTorch 0.18.1, Torch
2.10.0+cu128, and pymoo 0.6.2. BoTorch 0.18.1 is MIT-licensed and distributed as a
Python 3 wheel. Its public `Model.posterior()`/`Posterior.rsample()` boundary still
supports a custom sample-backed model, and
`qLogNoisyExpectedHypervolumeImprovement` still owns `X_baseline`, pending, and
constraint-capable numerical machinery. Yadof v1 deliberately exposes neither
pending nor stochastic outcome constraints because `GenerationContext` and task
rawData have no matching joint contract.

Primary references checked on 2026-08-28:

- [BoTorch models and custom posterior contract](https://botorch.org/docs/models)
- [BoTorch acquisition API](https://botorch.readthedocs.io/en/latest/acquisition.html)
- [BoTorch 0.18.1 distribution metadata](https://pypi.org/project/botorch/)

| Responsibility | Owner |
|---|---|
| hypervolume partitioning, log improvement, qLogNEHVI score | BoTorch 0.18.1 |
| sample lookup, minimization negation, whole-draw mask, compact diagnostics | existing yadof qLog backend adapter |
| history-informed unique discrete pool and variation | private pymoo adapter |
| greedy multi-start grouping and deterministic batch choice | new `qnehvi()` component |
| freshness, typed readiness, baseline, projection, exploration, fallback | new `posterior_assisted()` strategy |
| real finalization and durable recording | existing common `evaluate_population()` path |

No custom hypervolume or empirical improvement estimator was introduced.

## Public and typed surfaces

- `qnehvi()` validates multi-objective shape, explicit batch/restarts/reference/
  device/support controls, rejects pending/outcome inputs, and delegates every
  singleton/incremental batch score to the mature backend.
- `posterior_assisted()` binds search, surrogate posterior/readiness, acquisition,
  objective names, candidate pool, persistent draw count, chunk size,
  applicability gate, and real exploration fraction into semantic identity.
- `PosteriorExploitationReadiness` requires performance acceptance, calibrated
  transferable exact-state posterior evidence, zero observation noise, and
  calibrated or not-applicable applicability. It has no variance, cost, loss, or
  member-range field.
- `calibrated_applicability_gate()` binds a sealed probability threshold, boundary
  width, policy version, calibration-policy SHA-256, and low/boundary real-
  exploration order. Below-threshold candidates cannot exploit.
- Persistent samplers now expose their exact `RawDataSchemaTemplate`, allowing the
  strategy to create one frozen snapshot projector without concrete-surrogate
  imports.

Conditional-INR and hierarchical-CAE posterior adapters expose static and runtime
blocked readiness. The hierarchical path does not call or leak its uncalibrated
applicability probabilities. Existing component/GPSAF semantic identities and
private GPSAF files were not changed.

## Generation and failure semantics

The eligible path builds a unique private-pymoo pool, filters completed history to
a fixed unique nondominated real baseline, reserves
`ceil(population * exploration_fraction)` real exploration rows, creates one
persistent calibrated sampler, streams candidate chunks through current
`calc_cost.py`, and selects the remaining exploitation batch. Only the combined
unique real population crosses common evaluation.

Static/runtime scientific blockers, missing baseline/state, sampler mismatch,
projection/backend failure, or configured support fallback discard derived choices
and evaluate a complete real-search population. Configured support rejection and
source-support misconfiguration remain explicit hard stops. Evaluation is outside
the selection fallback catch, so recorder failure still aborts the campaign.
Predicted rawData and objective samples are released and never recorded.

## Preregistration, benchmark boundary, and real mechanism evidence

Gate 0 v9 under
`benchmark_automation/preregistrations/20260828-qnehvi-strategy-framework-v9/`
sealed the structural assertions and exact canary inputs before installed-wheel
validation and execution. Its read-only validator reported
`valid-fail-closed-framework-inputs`, confirmed installed site-packages origin, and
rechecked the v8 zero-calibrated/non-transferable boundary without simulator or
protected-locator access.

The no-write benchmark `performance` plan remains the existing 3-case × 2-arm ×
1-seed matrix: 6 measured cells, 100 individuals × 20 generations, and 12,000
planned attempted evaluations. It contains no posterior-assisted arm and was not
started. Existing Gate 2 pool/draw/objective timing evidence remains the only
qLogNEHVI microbenchmark; the v9 canary cannot support a performance claim.

One foreground generated `test_com` workspace then ran exactly one generation,
population two, seed 82611, with a deliberately blocked typed posterior. Both real
local evaluations completed and were durably published in one segment. Public
optimization metadata records:

- strategy signature
  `f0d83665392b2fc5d114e167154d29f992c974f31fdb49f00e606b57f56a82e8`;
- task snapshot
  `e7392c76350eeff4cf00330631c89598327a45467d72b3807b092e7a1b686cf5`;
- source `posterior_assisted_real_random`, `surrogate_used=false`, fallback reason
  `typed-exploitation-capability-blocked`, and handoff
  `common-real-evaluate-population`;
- recorder offered/admitted/published 2/2/2, zero write/fatal failures, and two
  public completed rows; cost view found 2 rows, zero ignored issues, and a 2-row
  Pareto front.

This is runnable mechanism/failure-path evidence only.

## Verification

- focused posterior/acquisition/GPSAF/real-search/posterior/calibration regression:
  `49 passed in 5.79s`;
- complete installed-wheel package suite with a fresh external pytest base and no
  cache provider: `314 passed in 72.70s`;
- installed import origin:
  `D:\project\20260414 yadof\20260822 modular\.venv\Lib\site-packages\yadof\__init__.py`;
- workspace check: 1 parameter, 2 objectives, 0 warnings;
- real canary: 2/2 successful, no simulation duplication, under one second, so no
  scheduled heartbeat was required.

TODO 082611 remains active. Its scientific completion rule still requires an
independently performance-accepted architecture, a calibrated transferable
posterior/applicability capability with sealed exploitation/exploration policy,
and the full same-budget 082612 benchmark meeting its preregistered thresholds.
