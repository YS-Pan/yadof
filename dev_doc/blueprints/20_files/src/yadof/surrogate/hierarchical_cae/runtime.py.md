# File blueprint: src/yadof/surrogate/hierarchical_cae/runtime.py

## Intent

- Provide a narrow lifecycle compatibility facade over data adaptation, state
  repository, and projection services.

## Functionalities

- Re-export the established private/public lifecycle surface without implementing
  training, recovery, or prediction.
- Preserve imports used by `api`, scheduler, viewer, and tests during the split.

## Invariants

- Source rawData is read-only and predicted rawData is never recorded.
- Current `calc_cost.py` is reapplied after recovery.
- Coordinate queries fail explicitly while the Gate 0 coordinate gate is closed.
- Dependency direction is runtime -> data/state/projection ->
  schema/objectives/training/inference/checkpoints; lower layers never import runtime.
