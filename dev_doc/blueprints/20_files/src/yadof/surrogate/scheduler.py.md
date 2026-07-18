# File blueprint: src/yadof/surrogate/scheduler.py

## Intent
- Coordinate staggered surrogate training so real simulation jobs can run while submit-side training happens.

## Functionalities
- Start at most one background training task at a time.
- Wait for pending training when the optimizer would otherwise use a too-stale model.
- Enforce `OPTIMIZE_SURROGATE_MAX_TRAINING_LAG`.
- Track pending and latest completed training generations.
- Record failure metadata when blocking or background training fails.

## I/O Format
- Public status is `TrainingScheduleStatus(action, generation_index, pending_generation_index, latest_completed_generation_index, error)`.
- `start_training(generation_index, block=False)` usually returns immediately after scheduling.
- `ensure_fresh_enough(generation_index)` may block and train if the lag limit requires it.

## Non-Obvious Techniques
- Missing first trained state is not fixed by prediction. The optimizer falls back to baseline candidates and schedules training after evaluation submission.
- Background training uses a single-worker executor to avoid concurrent writes to checkpoint artifacts and global runtime state.

## Mutability Profile
- Scheduling policy may change, but the one-at-a-time training and lag-limit behavior are the current public contract.
