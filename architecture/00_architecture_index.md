# Architecture Index

This folder describes the v3 `yadot` architecture from multiple viewpoints.

## Files
- `c4_context.md`: system context, actors, external systems, and project boundary.
- `c4_container.md`: major runtime containers/modules and their data flow.
- `c4_component.md`: internal components of the five core modules.
- `4plus1_logical_view.md`: domain concepts, module responsibilities, and API boundaries.
- `4plus1_process_view.md`: runtime flows for local evaluation, surrogate assistance, and failure handling.
- `4plus1_development_view.md`: source organization, dependency rules, and change boundaries.
- `4plus1_physical_view.md`: local workstation deployment now and distributed/HTCondor deployment later.
- `4plus1_scenarios.md`: use cases that connect the other views.

## Architectural Center
The most important invariant is:

```text
normalized variables
  -> workflow/rawData
  -> job_template/calc_cost.py
  -> cost
```

Cost and normalized historical variables are derived views, not durable source records.
