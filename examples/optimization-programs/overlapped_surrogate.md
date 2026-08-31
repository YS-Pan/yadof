# Overlapped evaluation and surrogate training

## Background and when to use it

`overlapped_surrogate.py` makes the yadof 0.5 handle ordering explicit. It starts
real evaluation, then fits PCA/SVD from immutable prior-generation evidence while
evaluation is running. Use it when both workloads can safely share the host and
lag-one training is scientifically acceptable.

## Workspace dependencies

The target must be a complete initialized workspace. Its rawData must be compatible
with PCA/SVD, and the surrogate extra must be installed. The program is backend
neutral, but distributed simulation credentials and local accelerator allocation
remain workspace/operator responsibilities.

## Data flow

One prior-evidence `SurrogateTrainingData` value is passed to GPSAF selection and
the training request. Real evaluation starts before training. The program waits and
closes the evaluation handle, joins training in the nested cleanup path, then
commits only real costs. Current-generation evidence first becomes training input
in the next generation.

## Concurrency and resources

Simulation/evaluation and CPU model fitting may contend for cores, memory, or I/O.
Choose a CPU rank/device and backend worker counts that fit the same resource
envelope. The explicit `finally` blocks guarantee both owners are joined at the
generation boundary, including failure paths.

## Adoption

Copy the Python file to `submit/optimization.py`, assess shared-resource capacity,
tune component settings, and run `yadof check`. Compare a bounded run against the
sequential example before adopting the overlap policy for longer campaigns.
