# Module prompt: dev_doc

## Intent
- Own the project's development documentation system under `dev_doc/`.
- Give AI agents and human maintainers a clear reading order before code changes.
- Preserve the distinction between stable specification, current architecture,
  generative prompts, terminology, reference ancestry, and historical change records.

## Functionalities
- `readme.md` is the entry point for documentation reading and writing rules.
- `spec 20260502.md` is the highest-level product and architecture contract.
- `architecture/` describes the current system using C4 and 4+1 viewpoints.
- `prompt/` contains generative module prompts that can guide recreation of equivalent
  module behavior.
- `reference_map.md` maps current modules to old-project references.
- `terminology.md` defines project-specific names and conceptual boundaries.
- `change_records/` stores time-named records explaining what changed and why.
- `obsolete/` stores archival planning and diagnostic material that is not read by
  default.

## I/O Format
- Default context gathering reads `spec 20260502.md`, all files in `architecture/`,
  `reference_map.md`, and `terminology.md` in full.
- Default context gathering lists all files in `prompt/`, then reads only relevant
  prompt files in full.
- `change_records/` filenames start with `YYYYMMDD_HHMMSS_` followed by a short
  description.
- Change records use sections: `Context`, `Change`, `Rationale`, `Impact`, and
  optional `Follow-Up`.

## Non-Obvious Techniques
- Prompt files are not ordinary summaries. Their center thought is that an AI should
  be able to recreate a module with equivalent behavior from the prompt.
- Architecture files are current-view maps; they should emphasize stable module
  relationships, runtime flows, and invariants rather than line-by-line implementation.
- Change records are intentionally excluded from default reading so historical detail
  does not drown out current contracts.
- Terminology is updated only for project-specific concepts, corrected misunderstandings,
  or names that are not intuitive from ordinary software usage.

## Mutability Profile
- `readme.md` should change when documentation workflow changes.
- `architecture/` and `prompt/` should change alongside code when module contracts,
  responsibilities, I/O, or important implementation techniques change.
- `change_records/` is append-only in normal work.
- `obsolete/` is archival and should rarely be edited.
