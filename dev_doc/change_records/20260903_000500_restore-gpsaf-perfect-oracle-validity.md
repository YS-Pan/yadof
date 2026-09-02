# 2026-09-03 00:05 - Restore GPSAF and perfect-oracle experiment validity

## Context

The previous perfect-surrogate experiment combined three invalid assumptions:
Chrono 10.0.0 left its NSC minimum-bounce value uninitialized; GPSAF used pooled
survival instead of the paper's positional/cluster mechanisms; and the temporary
oracle passed NamedRawDataItem wrappers into the cost API and fabricated all-one
costs after exceptions. Existing results remain historical evidence, not corrected
performance observations. The user requested unchanged package versions and one
fresh complete paired experiment after validation.

## Change

- Initialize every trebuchet NSC system with SetMinBounceSpeed(0.15). Synchronize
  standalone adapter copies and distinguish declared physical simulation failures
  from prediction/interface contract failures.
- Implement positional alpha tournaments, cloned beta ask/predict/tell advances,
  nearest-alpha clusters, per-cluster noisy PKT and density-to-the-gamma
  replacement. Preserve feasibility/Pareto comparisons, explicit random ties and
  independent seeded streams. Reconstruct optimizer state with one true tell per
  labeled real generation; predicted Individuals never mutate real state.
- Add explicit run-owned prediction-error state: five-fold held-out bootstrap for
  PCA/SVD, maximum absolute residual per batch and a five-estimate moving average.
  Document neural prequential cold start, rawData modeling, task penalties,
  duplicate/refill behavior and the retained exploration quota as adaptations.
- Add an installed perfect oracle using the actual baseline kernel and
  sample.cost_items() through the current cost interpreter. Legitimate all-one
  values remain valid; declared physical failures carry no rawData and +inf
  costs. Errors are visible; predictions never enter formal recording or budget.
  Every selected prediction is audited against its subsequent true evaluation.
- Pure freshness now lets a training-free component declare its current context
  generation with empty data. A multi-generation integration exposed the former
  no-data gate; a regression now requires 66 oracle calls, alpha/beta entry, 11
  selected/true matches and only 24 formal records. The perfect program aborts
  if noninitial selection silently falls back to real-only operation.
- Add the six-cell perfect preset, cumulative formal top-ten metric, frozen real
  reference, first-strict-crossing stop, independent durable-budget validation,
  automatic final summary and installed/task/input fingerprint guard.
- Synchronize user documentation, architecture, terminology, blueprints and
  templates. The full supplied paper and a paper/code/test acceptance map are in
  dev_doc/context. The pre-existing paper is included unchanged, including its
  existing trailing whitespace.

## Acceptance

Both wheel builds and force reinstalls succeeded with yadof 0.5.1 and
yadof-benchmark 0.5.0 unchanged. Imports resolve to the selected environment's
site-packages, and all 725 yadof plus 77 benchmark payload files match their
installed wheel bytes. Wheel SHA-256:

- yadof: f302107101e68041781832d6a594f63415d2f48a326f232aafab1ff45d101ce8
- benchmark: fa72a61cc633ed98ce7179f471cb16be8f798e0e78f427f7e4da281ec16bc00b

Final installed-package tests: yadof 483 passed (101.70 s); benchmark 57 passed
(8.07 s); focused perfect-oracle regression 7 passed (2.99 s). Earlier focused
yadof mechanism/program acceptance passed 38 tests. Initial legacy-golden and
test-fixture failures were corrected; their original logs were retained.

Real-runtime evidence under the task-owned outer temp directory:

- Chrono cases 0,44,84,105,158, eight runs each: two independent sequential
  processes, three concurrent runs, and three runs in one persistent process
  repeatedly creating systems. All 16 NPZ files / 23 numeric arrays and all four
  costs are bitwise identical; maximum raw/cost difference is exactly zero.
  Runtime is PyChrono 10.0.0, build py313h418371c_0.
- Oracle/direct evaluation: three distinct candidates per baseline, all nine
  objective vectors bitwise identical; no formal history was created.
- Final perfect integration: six valid paired cells with population 12 and at
  most four generations. 276 formal evaluations, 528 separate oracle simulations
  and 88 bitwise selected/true matches. All three baselines entered alpha and
  beta; both strict early completion and maximum-budget completion were validated.
- Final ordinary PCA/SVD integration: two valid four-generation cells; alpha and
  beta executed in generations 3 and 4 with measured nonzero prediction errors.
- Required final complete-preset smoke: all 18 cells and nine pairings valid,
  3,600 attempts, 3,252 finite outcomes; 348 physical evaluation failures were
  retained under the ordinary failure contract. All baseline postprocessors
  succeeded. No smoke or integration data is performance evidence.

The final validation artifacts are independent of the fresh formal workspace.
Installed code/user documentation is accepted; this later historical record is
documentation-only and does not require another wheel refresh.

## Experiment protocol

The new formal plan fixes seed 101, population 200, real NSGA-III 50 generations,
then perfect GPSAF at most 50. It uses paired initial designs and alpha=3,
beta=3, gamma=0.5, exploration=0.1 with the original explicit NSGA-III operators.
Workers are 4/8/8 for Chrono/ngspice/synthetic, retaining the original continuation
settings. Per-evaluation timeouts remain 120/60/30 seconds. A task-local manifest
sets 172800 seconds per cell command to accommodate the extra oracle work;
no extra generations or tuning runs are permitted.

Each generation computes the mean of the ten best per-individual mean costs
in cumulative formal history. The real generation-50 metric is frozen and
GPSAF stops at its first strict crossing or generation 50. Final experiment
results are produced autonomously and are outside the launch Goal's boundary.
