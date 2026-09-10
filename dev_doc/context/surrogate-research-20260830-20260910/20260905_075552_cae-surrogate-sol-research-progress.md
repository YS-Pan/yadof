# CAE surrogate research lessons retained after the baseline revision

The earlier development log and its single-seed perfect-surrogate gates have been
archived. This document retains research lessons, not acceptance thresholds or a
request to restart the closed experiments. The H21–H26 closure keeps its original
development results and provenance; no candidate passed the required fresh
confirmation or was promoted into the packaged surrogate.

- Accurate reconstruction of measured responses does not establish an accurate
  parameter-to-response predictor. Check both stages independently, using prior
  real training records and held-out complete responses.
- Average response error or cost MAE can improve while the candidates that matter
  to greedy-HV selection and the best-ten cost metric get worse. Evaluate ranking,
  uncertainty and physical feasibility in the selected tail as well as aggregate
  prediction accuracy.
- A lossless or near-lossless response codec is useful infrastructure. It does not
  justify treating a reconstruction oracle as a learned surrogate or counting its
  access to measured responses as a prediction result.
- Joint complete-response models improved some SAW development cases without
  resolving Chrono failures. An improvement on one simulator is not evidence for
  a general model, and a baseline-name branch is not a substitute for a shared
  algorithm tested across tasks.
- Preserve cross-field correlations when propagating uncertainty through the
  actual task cost function. The expected cost of complete response members need
  not equal the cost of their mean response.
- Surrogates must return the response structures required by the public task
  boundary. Cost-only placeholders are not a packaged replacement for complete
  rawData prediction.
- Fitting capacity, memory use and prediction cost matter to the full workflow.
  Additional training can be sensible when simulations are expensive; timing of
  the complete run is needed to assess the tradeoff.
- Exact compute reuse can preserve numerical outputs while improving a specific
  operation. The H26 inverse-transform cache has parity evidence in the separate
  closure document, but remains task-local and has no measured full online H26
  speedup or scientific acceptance.

Use the new five-seed P/B perfect-surrogate study for current descriptive
comparisons. Match P, B, initial population, the formal budget and the paired
ordinary reference; do not copy a historical single-seed crossing into a new
acceptance gate. A perfect queried-pool prediction is an empirical comparator,
not a proof that its search policy globally optimizes every downstream metric.

Current evidence: [five-seed P/B baseline](20260909_152719_five-seed-perfect-surrogate-pb-baseline.md).
