# Architecture Index

This folder describes the v3 `yadot` architecture from multiple viewpoints. It is
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

## Documentation Center
The documentation home is:

```text
dev_doc/
  README.md
  spec 20260502.md
  terminology.md
  reference_map.md
  architecture/
  prompt/
  toDo/
  change_records/
  obsolete/
```

`spec 20260502.md`, `architecture/`, `reference_map.md`, and `terminology.md` are
full-read context sources. `toDo/` is also full-read so pending future goals can shape
current implementation choices. `prompt/` is listed first and read selectively.
`change_records/` is historical and `obsolete/` is archival; neither is read by default.
