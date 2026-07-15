# Architecture Index

This folder describes the current `yadof` architecture from multiple viewpoints. It is
part of the documentation home under `dev_doc/`.

## Reading Policy
- Read every file in this folder in full when collecting project context.
- Use `dev_doc/README.md` for the broader documentation reading and writing guide.
- Do not read `dev_doc/change_records/` by default; use it only when historical
  rationale is needed.

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

## Core Goals
- Keep the framework simulator-agnostic: HFSS, other Ansys tools, custom Python, and multi-tool workflows are task choices rather than core assumptions.
- Support complex expensive evaluations that may run several simulations, combine tools, or perform task-local sub-optimization before producing rawData.
- Resume long campaigns from completed recorded rawData, recalculating normalized variables and costs with the current task definition.
- Isolate prepare, workflow, timeout, submit, and recording failures so one bad individual does not stop the generation.
- Allow controlled mid-campaign edits to parameter ranges, workflow files, simulator inputs, and `calc_cost.py`; users remain responsible for discarding old history when semantics drift too far.
- Keep local execution usable without HTCondor while allowing the distributed backend to share the same job and recording contracts.

## Documentation Center
The documentation home is:

```text
dev_doc/
  README.md
  terminology.md
  architecture/
  blueprints/
  toDo/
    auto/
  change_records/
  obsolete/
```

The user-facing documentation home is:

```text
user_doc/
  README.md
  optimization_workflow.md
  workflow_typical_patterns.md
  calc_cost_typical_patterns.md
  com_lib/
    README.md
    hfss_com.md
    test_com.md
  config_and_run.md
```

`architecture/` and `terminology.md` are full-read context sources. `toDo/` is also
read recursively in full so pending future goals can shape current implementation
choices. Files directly under `toDo/` are manual-trigger items and execute only when
the prompt explicitly names a file whose instructions should be executed. Files
under `toDo/auto/` are automatic-trigger, low-priority opportunistic cleanup: they
may run only when current work naturally exposes a matching occurrence, and they
use one of two obsolete policies from `dev_doc/README.md`: automatic, where expiry
by time or satisfaction of an explicitly configured user condition is sufficient,
or manual, which disables automatic obsoletion. No extra user condition exists by
default.
`blueprints/` is listed first and read selectively, with `blueprints/00_project.md`
serving as the generative project-level contract and module blueprints carrying
historical reference ancestry when it is still useful. `change_records/` is
historical and `obsolete/` is archival; neither is read by default.
`dev_doc` context gathering also starts with `user_doc/README.md` and follows its
reading guide for user-facing task setup context. A `user_doc`-only pass does not
read `dev_doc`.
