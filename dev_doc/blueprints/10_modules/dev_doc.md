# Module blueprint: dev_doc

## Intent
- Own the project's development documentation system under `dev_doc/`.
- Give AI agents and human maintainers a clear reading order before code changes.
- Preserve the distinction between stable specification, current architecture,
  generative blueprints, terminology, reference ancestry, and historical change records.
- Coordinate with `user_doc/`, the separate user-facing documentation home for task
  setup and run instructions.

## Functionalities
- `README.md` is the entry point for documentation reading and writing rules.
- `../user_doc/README.md` is read at the start of a `dev_doc` pass and then controls
  which user-facing task docs are read. A `user_doc` pass does not read back into
  `dev_doc`.
- `spec 20260502.md` is the highest-level product and architecture contract.
- `architecture/` describes the current system using C4 and 4+1 viewpoints.
- `blueprints/` contains generative module blueprints that can guide recreation of equivalent
  module behavior.
- `reference_map.md` maps current modules to old-project references.
- `terminology.md` defines project-specific names and conceptual boundaries.
- `toDo/` stores time-named future-work handoffs that are always read during the
  first `dev_doc` pass.
- `change_records/` stores time-named records explaining what changed and why.
- `obsolete/` stores archival planning and diagnostic material that is not read by
  default, including completed toDo handoffs.

## I/O Format
- Default context gathering reads `spec 20260502.md`, all files in `architecture/`,
  `reference_map.md`, and `terminology.md` in full.
- Default `dev_doc` context gathering also reads `../user_doc/README.md` and follows
  its instructions for user-facing task setup files.
- Default context gathering reads every Markdown file in `toDo/` in full, even when
  the current user request appears unrelated to the pending work.
- Default context gathering lists all files in `blueprints/`, then reads only relevant
  blueprint files in full.
- `toDo/` filenames start with `YYYYMMDD_HHMMSS_` followed by a short description.
- `change_records/` filenames start with `YYYYMMDD_HHMMSS_` followed by a short
  description.
- Change records use sections: `Context`, `Change`, `Rationale`, `Impact`, and
  optional `Follow-Up`.

## Non-Obvious Techniques
- Blueprint files are not ordinary summaries. Their center thought is that an AI should
  be able to recreate a module with equivalent behavior from the blueprint.
- Architecture files are current-view maps; they should emphasize stable module
  relationships, runtime flows, and invariants rather than line-by-line implementation.
- Change records are intentionally excluded from default reading so historical detail
  does not drown out current contracts.
- ToDo files are intentionally included in default reading so future goals can shape
  today's technical route before implementation begins.
- `user_doc/` prevents user task instructions from being duplicated throughout
  development docs. `dev_doc` may mention user-facing behavior from an architecture
  or maintainer perspective, but detailed "what the user should do" instructions
  belong under `user_doc`.
- Terminology is updated only for project-specific concepts, corrected misunderstandings,
  or names that are not intuitive from ordinary software usage.

## Mutability Profile
- `README.md` should change when documentation workflow changes.
- `architecture/` and `blueprints/` should change alongside code when module contracts,
  responsibilities, I/O, or important implementation techniques change.
- `user_doc/` should change when user-facing task setup, adapter usage, workflow,
  cost, config, smoke-test, or launch instructions change.
- `toDo/` receives pending future-work handoffs and should be moved to `obsolete/`
  when the corresponding work is completed.
- `change_records/` is append-only in normal work.
- `obsolete/` is archival and should rarely be edited.
