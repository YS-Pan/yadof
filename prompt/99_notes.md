# Notes

## Source Priority
- `spec 20260502.md` is the highest-level design source and was read in full before writing this prompt set.
- Existing code under `project/` is the implementation source for current module boundaries.
- Reference prompts under `reference/20260403 fanyufei/prompt` and `reference/20260418 shorten/prompt` define the documentation style and preserve non-obvious inherited techniques.

## Current Implementation Notes
- Local mode is implemented; distributed/HTCondor remains a planned backend.
- `hfss_com.py` exists under `job_template`, but current runnable jobs use `test_com.py` and exclude `hfss_com.py` from copied job folders.
- The current surrogate is a conditional INR rawData deep ensemble adapted from the `20260418 shorten` direction while preserving the v3 rawData-first public API.
- The v3 surrogate keeps the small `api.py` surface from the earlier implementation, but `runtime.py` now delegates neural model construction/training/prediction to `surrogate/modeling.py`.
- The current optimizer uses pymoo GA/NSGA2 mechanics inside a GPSAF-shaped flow, not the old DEAP NSGA-III entry point.

## Documentation Maintenance
- Keep prompt files module-level until the project stabilizes; avoid adding file-level `.md` prompts during rapid iteration.
- Update `reference_map.md` when copying or replacing reference-derived implementation ideas.
- Update `architecture/` when module responsibilities, public APIs, data persistence, or execution topology change.
