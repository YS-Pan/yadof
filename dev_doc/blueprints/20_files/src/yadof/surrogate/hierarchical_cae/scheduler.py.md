# File blueprint: src/yadof/surrogate/hierarchical_cae/scheduler.py

## Intent

- Serialize background hierarchical-CAE training and enforce generation freshness.

## Functionalities

- Key pending/completed/error state by workspace, strategy, and component semantics.
- Start after real submission, wait when configured lag is exceeded, retain errors
  without replacing real evaluation, and release state on strategy deactivation.

## Invariants

- At most one hierarchical training future executes at a time.
- A pending process is always joined rather than duplicated.
- Owned generation snapshots and training bundles isolate background work from task
  edits during a generation.
