# 2026-08-30 12:18 - Split CAE/EHVI work and reassess completed evidence

## Context

The active `20260828_121904_surrogate-qnehvi-remaining-work.md` handoff combined
Hierarchical CAE architecture research, binary performance acceptance, posterior
calibration/readiness, qNEHVI mechanics, a mandatory seven-arm optimization matrix,
and release/default decisions. The user judged its CAE performance policy too
strict and explicitly rejected an all-or-nothing performance gate.

The fresh base Hierarchical CAE benchmark started in a separate Codex task had also
finished. Its final workspace completed all 6 simulation cells and all 24 logical
analysis cells, so the earlier 22/24 progress report was no longer sufficient. The
user additionally asked that the original PCA/SVD purpose and measured evidence be
used to assess Hierarchical CAE's nonlinear representation benefit.

## Evidence review

The completed CAE workspace is the outer workspace's
`temp/20260830_094718-hierarchical-cae-base-performance-measured-visible-20260830`.
Its postprocessor succeeded and the sealed rule produced
`gate_passed=false`/`performance_accepted=false`, because every logical cell failed
at least one required performance check. This was not an execution failure:
partition completion, finite cost projection, checkpoint reload, all-axis finite
coordinate queries, query-state immutability, training wall, RSS, CUDA memory,
parameter count, and the sealed coordinate-vs-grid bound passed in all 24 cells.

A four-replicate mean review by case/train showed:

- synthetic antenna: CAE rawData RMSE ratios of about `0.952/0.767`, cost-MAE ratios
  of `0.788/0.683`, Spearman improvements of about `+0.392/+0.396`, but worst-field
  ratios around `2.20`;
- SAW: rawData RMSE ratios of `0.985/0.949`, rawData MAE about 14% worse, cost-MAE
  ratios of `0.848/1.167`, and small/mixed ranking changes;
- Chrono: rawData MAE/RMSE about `3.3--4.4x` the conditional-INR baseline,
  worst-field ratios about `8.6--10.7x`, and substantially worse ranking at the
  larger training size, despite similar cost MAE;
- all resource checks passed, with mean CAE/conditional-INR training-wall ratios of
  about `0.50`, `0.41`, and `0.75` for antenna, SAW, and Chrono respectively.

The PCA/SVD history and measured analysis were reread rather than inferred from the
old summary. PCA/SVD was introduced first as a linear low-rank oracle to test whether
Hierarchical CAE supplied meaningful nonlinear representation, then promoted to a
deployable ridge `parameters -> coefficients -> rawData` component to separate
representation difficulty from parameter-to-latent difficulty. Its completed
three-case study found rank-32 oracle relative Frobenius error near `0.000056` for
synthetic antenna, about `0.069` for SAW, and about `0.239` for Chrono; every case
had a deployable-minus-oracle cost-RMSE gap of about `0.16--0.21`.

The combined evidence does not identify a pure nonlinear representation treatment
effect. The CAE arm combines a nonlinear parameter predictor with a nonlinear
representation, while the deployable PCA/SVD arm combines a linear representation
with ridge. A CAE reconstruction oracle, a nonlinear predictor over PCA/SVD
coefficients, and paired exact splits are still missing. The supportable conclusion
is domain-specific: synthetic antenna has virtually no nonlinear representation
headroom; SAW shows useful nonlinear end-to-end modeling but probably modest pure
representation benefit; Chrono has linear-representation headroom that the current
CAE did not realize.

## Change

- Added `20260830_120818_hierarchical-cae-evidence-led-research.md` as the standalone
  CAE handoff. It records the final benchmark, PCA/SVD purpose/results, a
  domain-specific nonlinear-benefit assessment, and a paired diagnostic plan that
  separates representation from parameter mapping without a performance gate.
- Rewrote `20260828_121904_surrogate-qnehvi-remaining-work.md` as the standalone
  posterior-assisted EHVI/qNEHVI handoff. Exact posterior capability can still be
  unavailable for semantic/integrity reasons, but CAE performance is no longer a
  global binary prerequisite. The seven-arm suite is now a modular target matrix;
  valid arm pairs remain evidence when another arm is unavailable.
- Updated the parked anti-noise and acquisition-protocol TODO links and ownership
  descriptions so they point to the separate CAE and EHVI responsibilities.
- Updated the project/surrogate blueprints and terminology to describe continuous,
  case/use-specific CAE evidence, capability-specific posterior blocking, and
  modular same-budget comparisons instead of an integrated all-cell release gate.

## Rationale

Representation quality, downstream current-cost quality, ranking, worst-field
behavior, coordinate quality, and resource cost are not interchangeable metrics.
A universal conjunction discarded useful antenna/SAW evidence while adding no
clarity about Chrono's failure. Separating CAE research from EHVI use also prevents
posterior readiness from becoming a hidden global performance verdict.

Pre-access data roles, budgets, seeds, metrics, exclusions, and stopping rules
remain important protections against leakage and result-directed tuning. The
change removes universal pass/fail performance thresholds, not schema integrity,
exact-state binding, posterior coherence, real-evaluation, recorder reliability,
or user execution authority.

## Impact

This is a documentation/toDo-state change only. It changes no package code, current
runtime behavior, checkpoint, benchmark artifact, template default, or previously
sealed conclusion. Current real posterior components remain blocked and
posterior-assisted execution continues to fall back to full real search.

Architecture and user task-authoring behavior did not change. The current project
and surrogate blueprints plus project terminology were updated because the future
evidence/release intent changed; no user-document update is required.

## Validation

- Re-read the final CAE gate result, plan, state, and all 24 logical cells, and
  aggregated the final metrics directly from the JSON evidence.
- Re-read the PCA/SVD recovery analysis, tracked completion record, and the Codex
  task's source review of the original PCA/SVD diagnostic purpose.
- Verified current TODO cross-links, standalone handoff coverage, UTF-8 text, and
  final Git diff/check output under the documentation-only validation exception.
- No wheel build, reinstall, import-origin check, pytest run, simulator launch, or
  new benchmark was required because no code, resource mapping, documentation
  mechanism, or executable example changed.
