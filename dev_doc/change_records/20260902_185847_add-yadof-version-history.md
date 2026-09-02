# 2026-09-02 18:58 - Add Concise Yadof Version History

## Context

The project had detailed completed-change records but no concise overview of its
major versions. The author supplied the milestones from 0.1.0 through 0.5.0 and
approved keeping that overview in `dev_doc/history.md`.

## Change

- Added a Chinese history covering the initial shared-folder implementation,
  package/workspace separation, local and fast modes, optimize/surrogate modules,
  and programmable optimization flow.
- Linked the history from the developer README and registered its role in the
  documentation ownership view and documentation module blueprint.
- Kept the overview at milestone level and linked detailed change records for
  further reading.

## Rationale

A short version history makes the project's evolution easy to find and maintain.
The author-provided milestones supply its historical scope; current architecture
and user documentation continue to define runtime behavior.

## Validation

UTF-8, milestone content, relative links, and Git whitespace checks passed. This
content-only documentation change uses the development guide's documentation-only
validation exception; no wheel rebuild, reinstall, or software test run is needed.

## Impact

Only developer documentation changed. No runtime behavior, package-resource
mapping, documentation command, or task-authoring contract changed.
