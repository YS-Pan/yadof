# amplitude_gp with GPSAF

## Workspace dependencies

Copy this file to `submit/optimization.py` in an initialized task and run
`yadof check --workspace PATH`. Install `yadof[gp]` first.
The program supports one objective through GA and multiple objectives through NSGA-III.

## Data flow

It fits all valid own-prior rawData before each assisted batch, preserves failure
records, projects complete predicted responses through current cost, and commits
only real results. Fit failure propagates; it is not hidden as successful training.
The model is opt-in; development evidence does not establish a universal speedup.

## Concurrency and resources

Training is synchronous before selection. Real evaluation uses the workspace
worker policy. H9 uses two field workers; N02 keeps neural training on one CPU
thread and restores process thread settings when it exits.

## Adoption

P/B/I come from task configuration, independently of model settings. To reproduce
the small-batch research shape, set `OPTIMIZE_POPULATION_SIZE=50`,
`OPTIMIZE_BATCH_SIZE=50`, `OPTIMIZE_INITIAL_POPULATION_SIZE=200` in `config.py`.
An initial 200 plus 96 subsequent batches of 50 gives 5000 formal attempts.
These are examples, not new framework defaults. The supplied full benchmark uses
the standard P200/B200/I200/G25 for a uniform 5000-attempt comparison.

See the packaged [component guide](../../user_doc/amplitude_gp.md) for numerical
settings, runtime limits and scientific evidence.
