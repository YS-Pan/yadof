# Module blueprint: dev_doc

## Intent
- Own the project's development documentation system under `dev_doc/`.
- Give AI agents and human maintainers a clear reading order before code changes.
- Define the boundary between users, who run campaigns, and administrators, who
  maintain the execution environment.
- Preserve the distinction between current architecture contracts, generative blueprints, terminology, future-work handoffs, historical change records, and archival notes.
- Keep historical reference ancestry inside the relevant project/module blueprints when it remains useful, instead of maintaining a separate active path map.
- Coordinate with `user_doc/`, the separate user-facing documentation home for task setup and run instructions.

## Functionalities
- `README.md` is the entry point for documentation reading and writing rules.
- `../user_doc/README.md` is read at the start of a `dev_doc` pass and then controls which user-facing task docs are read. A `user_doc` pass does not read back into `dev_doc`.
- `architecture/` describes the current system using C4 and 4+1 viewpoints and carries the highest-priority current-view contracts for boundaries, data flow, runtime behavior, persistence, and invariants.
- `blueprints/00_project.md` is the generative project-level contract: it preserves project goals, module responsibilities, non-obvious techniques, mutability boundaries, and useful historical lineage.
- `blueprints/10_modules/` contains module blueprints. `blueprints/20_files/`
  contains file blueprints in a folder hierarchy that mirrors the source path, such
  as `blueprints/20_files/project/surrogate/runtime.py.md`, and should hold
  file-specific historical reference ancestry when needed.
- `terminology.md` defines project-specific names and conceptual boundaries.
- `toDo/` stores time-named future-work handoffs that are always read during the first `dev_doc` pass.
- `change_records/` stores time-named records explaining what changed and why.
- `obsolete/` stores archival planning and diagnostic material that is not read by default, including completed toDo handoffs and retired active documents.
- `../admin_tool/README.md` indexes administrator-only environment and HTCondor-pool
  resources. Those resources are not part of `project/tools/` or user task setup.

## I/O Format
- Default context gathering reads all files in `architecture/`, `terminology.md`, and every Markdown file in `toDo/` in full.
- Default `dev_doc` context gathering also reads `../user_doc/README.md` and follows its instructions for user-facing task setup files.
- Default context gathering lists all files in `blueprints/`, including recursive
  files under `blueprints/20_files/`, then reads `blueprints/00_project.md` for
  project-wide work and the relevant module/file blueprint files in full.
- `toDo/` filenames should start with `YYYYMMDD_HHMMSS_` followed by a short description when possible.
- `change_records/` filenames start with `YYYYMMDD_HHMMSS_` followed by a short description.
- Change records use sections: `Context`, `Change`, `Rationale`, `Impact`, and optional `Follow-Up`.

## Non-Obvious Techniques
- Architecture files are current-view maps; they should emphasize stable module relationships, runtime flows, and invariants rather than line-by-line implementation.
- Blueprint files are not ordinary summaries. Their center thought is that an AI should be able to recreate a module or file with equivalent behavior from the blueprint.
- Historical reference details are useful only when they preserve a durable implementation idea, not when they are a stale path list. Put the useful natural-language lineage in the relevant blueprint.
- File-level blueprint paths mirror source paths after `blueprints/20_files/`; the
  Markdown suffix is appended to the source filename instead of replacing directory
  separators with underscores.
- Change records are intentionally excluded from default reading so historical detail does not drown out current contracts.
- ToDo files are intentionally included in default reading so future goals can shape today's technical route before implementation begins.
- `user_doc/` prevents user task instructions from being duplicated throughout development docs. `dev_doc` may mention user-facing behavior from an architecture or maintainer perspective, but detailed "what the user should do" instructions belong under `user_doc`.
- Terminology is updated only for project-specific concepts, corrected misunderstandings, or names that are not intuitive from ordinary software usage.

## Mutability Profile
- `README.md` should change when documentation workflow changes.
- `architecture/` and `blueprints/` should change alongside code when module contracts, responsibilities, I/O, persistence behavior, execution topology, historical lineage, or important implementation techniques change.
- `user_doc/` should change when user-facing task setup, adapter usage, workflow, cost, config, smoke-test, or launch instructions change.
- `toDo/` receives pending future-work handoffs and should be moved to `obsolete/` when the corresponding work is completed.
- `change_records/` is append-only in normal work.
- `obsolete/` is archival and should rarely be edited except when retiring active documents or completed handoffs.
