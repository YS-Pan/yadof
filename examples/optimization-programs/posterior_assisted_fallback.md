# Posterior-assisted selector with honest fallback

## Background and when to use it

`posterior_assisted_fallback.py` documents the current qNEHVI boundary without
claiming readiness that yadof does not have. The conditional-INR posterior exposes
typed finite draws, but its performance, calibration, and transferability gates
remain blocked. The selector therefore chooses a full-real NSGA-III population.
Use this example to integrate and test fail-closed behavior, not to claim
posterior-assisted exploitation.

## Workspace dependencies

The destination must be a multi-objective initialized workspace with at least two
population members, compatible conditional-INR rawData, and the surrogate extra.
The qNEHVI backend is configured but is not entered while typed readiness is
blocked. The example supplies no task assets, costs, or simulator.

## Data flow

The program materializes explicit training data and passes it to
`PosteriorAssistedSelector`. Static typed readiness fails closed before posterior
sampling, producing a full-real population and diagnostic reason. Evaluation starts,
the underlying conditional-INR component may train from prior evidence, both
handles are joined, and only real costs are committed.

## Concurrency and resources

Training and real evaluation overlap, so allocate workers and model resources as a
single budget. If readiness becomes accepted in a future release, qNEHVI candidate
pool size, draws, chunks, and device will add memory and compute costs; adoption
must then be re-reviewed rather than silently changing this example's meaning.

## Adoption

Copy the Python file to `submit/optimization.py` only for a multi-objective task,
run `yadof check`, and verify each generation records
`typed-exploitation-capability-blocked` with `surrogate_used=False`. Do not edit
diagnostics or gates to force qNEHVI execution.
