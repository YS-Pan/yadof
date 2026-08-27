# 2026-08-27 08:35 - Plan Joint rawData Posterior Architecture

## Context

- The existing conditional-INR/GPSAF boundary exposes mean predicted costs and
  member min/max diagnostics, while the requested qNEHVI path needs coherent joint
  posterior samples derived from complete rawData.
- The target workload values fitting quality around 1000--2000 designs, does not
  require few-shot performance, and has real evaluations generally below one CPU
  hour. Heterogeneous rawData fields such as 1-D S11 and 2-D gain may remain
  physically correlated.
- The user approved a new convolutional autoencoder, parameter latent predictor,
  coordinate readout, and qNEHVI path as additive modules. Existing
  conditional-INR and GPSAF behavior must remain available.

## Change

- Added six manual future-work handoffs covering:
  - a batch-joint rawData posterior and current-cost projection contract;
  - a hierarchical CAE with global, optional explicit-group, and field-private
    latent paths;
  - coherent posterior function sampling and held-out calibration;
  - a non-invasive conditional-INR empirical-ensemble adapter;
  - an independent discrete/sample-backed qNEHVI acquisition strategy;
  - benchmark gates, migration, viewer/documentation work, and opt-in rollout.
- Recorded that default `groups=()` means no explicit group latent while all fields
  still share a global latent; it does not mean independent field models.
- Recorded that qNEHVI sampling is joint over the complete candidate set and all
  fields/objectives, and that worker, rawData, and recorded-data persistence formats
  do not need to change.

## Rationale

- A posterior-sample capability separates acquisition logic from CAE ensembles,
  weight posteriors, bootstrap, dropout, or future implementations without losing
  yadof's rawData-first source-of-truth boundary.
- Additive protocols and strategy composition protect current GPSAF/checkpoint
  behavior while allowing the new model and acquisition to be benchmarked
  independently.
- Splitting the work makes API compatibility, model quality, uncertainty semantics,
  acquisition correctness, and real-budget validation separate completion gates.

## Impact

- This change adds planning documentation only. Runtime APIs, models, persistence,
  task formats, dependencies, and user-visible optimization behavior are unchanged.
- Future implementation will require coordinated surrogate, optimize, job-template,
  viewer, configuration, documentation, and installed-wheel verification described
  by the new handoffs.

## Follow-Up

- Execute the manual TODOs only when explicitly requested, beginning with the joint
  posterior contract and using the dependency order recorded in the documents.
- Pre-register benchmark thresholds before examining final test or real-campaign
  results; passing mechanics alone must not make the new path a default strategy.
