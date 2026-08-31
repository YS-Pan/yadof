# Split cost-history and surrogate-training data

## Background and when to use it

`split_cost_surrogate_data.py` demonstrates that optimizer history and model
training evidence are separate explicit values. The optimizer keeps all successful
real cost rows, while PCA/SVD receives every other successful row under a named
transform. Replace that toy rule with a preregistered scientific filter when a
surrogate should train on a stricter evidence subset.

## Workspace dependencies

Use a complete initialized workspace with compatible rawData and the surrogate
extra. The task must define stable parameter and objective dimensions. The example
does not provide a simulator, cost function, configuration, or data assets.

## Data flow

`step.context.history` remains the full optimizer cost history. The program
materializes all eligible evidence, derives an ordered row-ID subset, and
rematerializes it as `SurrogateTrainingData` with a stable `transform_id`. That
same explicit value controls GPSAF freshness, prediction, and model training; real
evaluation remains authoritative for the committed costs.

## Concurrency and resources

Training overlaps evaluation as in the overlap example. A smaller evidence view
can reduce fit time and memory, but filtering may reduce coverage or introduce
bias. Row order and `transform_id` participate in provenance and checkpoint
freshness, so change them deliberately.

## Adoption

Copy the Python file to `submit/optimization.py`, replace
`surrogate_training_view()` with a documented task-owned rule, and update the
program identity whenever the rule changes. Run `yadof check` and audit the
recorded training row IDs before a long campaign.
