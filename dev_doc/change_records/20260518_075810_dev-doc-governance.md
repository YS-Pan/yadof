# 2026-05-18 07:58 - dev_doc Governance

## Context

- Project documentation had lived partly at the repository root, which made the root
  directory noisy and made document reading order unclear.
- The user moved architecture, prompt, reference map, spec, obsolete notes, and
  terminology into `dev_doc/`.
- Future AI work needs explicit rules for which documents to read in full, which to
  inspect on demand, and how to keep documents synchronized with code changes.

## Change

- Added `dev_doc/readme.md` as the documentation entry point and writing guide.
- Added `dev_doc/change_records/` for time-named records of what changed and why.
- Documented that `spec 20260502.md`, `architecture/`, `reference_map.md`, and
  `terminology.md` should be read in full during context gathering.
- Documented that `prompt/` should be listed first and read selectively.
- Documented that `change_records/` and `obsolete/` are not read by default.
- Updated architecture and prompt docs to recognize `dev_doc/` as the documentation
  home and to require architecture, prompt, terminology, and change-record updates
  after relevant changes.

## Rationale

- `change_records` is broader than a strict ADR folder: it can record architecture
  decisions, implementation changes, and documentation-only governance changes.
- Keeping records out of the default reading set prevents historical detail from
  overwhelming normal code work, while still preserving the reasoning behind changes.
- Separating prompt documents from architecture documents keeps their writing goals
  distinct: prompts are generative module specs; architecture docs are current-view
  system maps.

## Impact

- Future AI agents should start documentation context from `dev_doc/readme.md`.
- Code changes should now include corresponding updates to architecture, prompt, and
  `change_records/` when the change affects documented contracts or behavior.
- If a concept is corrected or a non-obvious name appears, `terminology.md` should be
  updated in the same change.

## Follow-Up

- Existing documents still contain some older path phrasing. Update those references
  opportunistically when touching the relevant files.
