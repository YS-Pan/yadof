# File blueprint: src/yadof/surrogate/hierarchical_cae/runtime.py

## Intent

- Adapt recorded/session evidence into hierarchical training, recovery, full rawData
  prediction, current-cost projection, and applicability diagnostics.

## Functionalities

- Align normalized parameters, named rawData, and copied record metadata by job;
  deduplicate complete designs and build/freeze the field schema.
- Train or recover a compatible model under the component namespace.
- Predict complete member/mean rawData, calculate current costs through the active
  task interpreter, expose member min/max costs, and return uncalibrated smooth
  probabilities and ensemble spread.

## Invariants

- Source rawData is read-only and predicted rawData is never recorded.
- Current `calc_cost.py` is reapplied after recovery.
- Coordinate queries fail explicitly while the Gate 0 coordinate gate is closed.
