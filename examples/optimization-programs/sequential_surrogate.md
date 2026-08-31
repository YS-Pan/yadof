# Sequential surrogate program

## Background and when to use it

`sequential_surrogate.py` shows PCA/SVD rawData modeling with retained GPSAF
`alpha`, `beta`, and `gamma` settings. Evaluation finishes first; the newly recorded
generation is then materialized and trained before commit. Use this ordering when
simple lifecycle reasoning matters more than overlapping work.

## Workspace dependencies

The destination must be an initialized workspace with task-owned configuration,
evaluation, rawData, and cost code. PCA/SVD requires the yadof surrogate extra and
a rawData schema that the component can encode. Search uses GA for one objective
and NSGA-III otherwise.

## Data flow

Prior evidence is materialized for selection. GPSAF either uses a compatible fresh
checkpoint or falls back to real search. The selected population is evaluated and
recorded; a second explicit view then includes current evidence for training. The
program joins training and commits the authoritative real costs.

## Concurrency and resources

Evaluation and model training do not overlap. This can increase wall-clock time,
but it avoids simultaneous simulator/worker and model-fitting pressure. The
evaluation handle and training lifecycle are both complete before commit.

## Adoption

Copy the Python file to `submit/optimization.py`, tune the PCA/SVD rank and device
for the task, preserve the literal identity when semantics are unchanged, and run
`yadof check`. Start with a bounded real-only comparison before relying on GPSAF.
