# Notes

## Source Priority
- `dev_doc/spec 20260502.md` is the highest-level design source and was read in full before writing this blueprint set.
- Existing code under `project/` is the implementation source for current module boundaries.
- Reference prompts under `reference/20260403 fanyufei/prompt` and `reference/20260418 shorten/prompt` define the documentation style and preserve non-obvious inherited techniques.
- `dev_doc/README.md` defines the current documentation reading policy.
- `dev_doc/toDo/` is read in full on the first `dev_doc` pass so pending future work
  can influence current implementation choices.

## Current Implementation Notes
- Local mode is implemented and remains the default; distributed/HTCondor is implemented as an optional backend that captures submit/runtime failures without repairing the host HTCondor installation.
- `hfss_com.py` exists under `job_template`, but current runnable jobs use `test_com.py` and exclude `hfss_com.py` from copied job folders.
- The current surrogate is a conditional INR rawData deep ensemble adapted from the `20260418 shorten` direction while preserving the v3 rawData-first public API.
- The v3 surrogate keeps the small `api.py` surface from the earlier implementation, but `runtime.py` now delegates neural model construction/training/prediction to `surrogate/modeling.py`.
- The current optimizer uses pymoo GA for single-objective runs and pymoo NSGA-III reference-direction mechanics for multi-objective runs inside a GPSAF-shaped flow.

## Documentation Maintenance
- Keep blueprint files module-level until the project stabilizes; avoid adding file-level
  `.md` blueprints during rapid iteration.
- Update `dev_doc/reference_map.md` when copying or replacing reference-derived implementation ideas.
- Update `dev_doc/architecture/` when module responsibilities, public APIs, data persistence, or execution topology change.
- Update `dev_doc/blueprints/` when module intent, I/O shape, non-obvious techniques, or mutability boundaries change.
- Add a time-named file under `dev_doc/change_records/` after each code change to describe what changed and why.
- Move a completed `dev_doc/toDo/` handoff into `dev_doc/obsolete/` after finishing
  that task.
- Update `dev_doc/terminology.md` when a mistaken concept is corrected or a new non-obvious name appears.
