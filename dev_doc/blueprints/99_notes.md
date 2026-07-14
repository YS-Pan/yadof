# Notes

## Source Priority
- Existing code under `project/` is the implementation source for current module boundaries.
- `dev_doc/architecture/` is the current-view contract source for system boundaries, runtime flows, persistence rules, and core invariants.
- `dev_doc/blueprints/00_project.md` is the generative project-level contract; module and file blueprints preserve module intent, I/O, non-obvious techniques, mutability boundaries, and useful historical lineage.
- Current files under `admin_tool/` are read only when the active docs or task point to them. They contain administrator-only operational resources; historical project ancestry should be treated as natural-language lineage in blueprints, not as a live path map.
- `dev_doc/README.md` defines the current documentation reading policy.
- `dev_doc/toDo/` is read in full on the first `dev_doc` pass so pending future work can influence current implementation choices.

## Current Implementation Notes
- Local mode is implemented and remains the default; distributed/HTCondor is implemented as an optional backend that captures submit/runtime failures without repairing the host HTCondor installation.
- Runnable jobs use whichever task files and active adapter files are placed in `project/job_template/`; `project/com_lib/hfss_com.py` is the HFSS reference/source copy, and `project/com_lib/test_com.py` remains available only as a synthetic adapter reference.
- The current surrogate is a conditional INR rawData deep ensemble adapted from the shorten-style direction while preserving the v3 rawData-first public API.
- The v3 surrogate keeps the small `api.py` surface from the earlier implementation, but `runtime.py` now delegates neural model construction/training/prediction to `surrogate/modeling.py`.
- The current optimizer uses pymoo GA for single-objective runs and pymoo NSGA-III reference-direction mechanics for multi-objective runs inside a GPSAF-shaped flow.

## Documentation Maintenance
- Keep module-level blueprint files as the overview layer. For stable modules, add
  file-level `.md` blueprints under `dev_doc/blueprints/20_files/` when a
  change introduces important per-file responsibilities. File-level blueprint paths
  mirror source paths, for example
  `dev_doc/blueprints/20_files/project/surrogate/runtime.py.md`.
- Update `dev_doc/architecture/` when module responsibilities, public APIs, data persistence, execution topology, or current-view invariants change.
- Update `dev_doc/blueprints/` when module intent, I/O shape, non-obvious techniques, mutability boundaries, or useful historical lineage changes.
- Add a time-named file under `dev_doc/change_records/` after each code change to describe what changed and why.
- Move a completed `dev_doc/toDo/` handoff into `dev_doc/obsolete/` after finishing that task.
- Retire obsolete active documents into `dev_doc/obsolete/` only after their still-useful facts have been moved into current architecture, blueprint, or terminology docs.
- Update `dev_doc/terminology.md` when a mistaken concept is corrected or a new non-obvious name appears.
