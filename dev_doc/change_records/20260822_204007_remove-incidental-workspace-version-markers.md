# 2026-08-22 20:40 - Remove Incidental Workspace Version Markers

## Context

- Workspace initialization carried a template release number even though the
  installed package loaded only one current template and had no reader or execution
  path for an earlier template implementation.
- The workspace-composition change also incremented an internal checkpoint format
  number although required method, policy, strategy, state, and artifact identities
  already determine whether a checkpoint is recoverable.
- Current documentation and one config diagnostic presented the native `submit/`
  layout as a migration from an earlier workspace layout.

## Change

- Removed the template release field from the bundled manifest, workspace marker,
  initialization/check/smoke APIs, CLI output, example workspace, and tests.
- Made workspace markers and bundled template manifests reject unrecognized fields
  instead of silently accepting an earlier release marker.
- Removed the checkpoint format counter from serialization, semantic signatures,
  validation, tests, terminology, and blueprints while retaining all structural,
  semantic, runtime, and integrity checks.
- Replaced the old-layout-specific config branch and migration prose with native
  current-layout validation and documentation.
- Replaced the persistent automatic release-marker toDo with an English version
  that preserves its trigger, exclusions, safety boundaries, and completion rules.

## Rationale

- A release counter without two supported implementations communicates historical
  sequencing rather than a current responsibility. Removing the layer makes the
  workspace and checkpoint contracts describe their actual identities directly.
- Strict marker fields prevent accidental compatibility with files from the
  removed contract. Independent workspace/rawData schemas, the surrogate viewer
  JSON schema, the PyChrono protocol, runtime/backend versions, and the public yadof
  package version remain because they are real format, protocol, or provenance
  boundaries.

## Impact

- Newly initialized workspaces contain only workspace/rawData schema identities,
  package provenance, and the template name in `.yadof/workspace.json`.
- Workspace files containing removed or otherwise unknown marker fields are
  rejected rather than upgraded, rewritten, or interpreted through a compatibility
  path.
- Existing checkpoint artifacts from the removed contract cold-start because their
  semantic identity differs or required current identity fields are absent; no
  fallback reader was added.

## Verification

- Built `dist/yadof-0.4.0-py3-none-any.whl`, force-reinstalled it into the sibling
  `.venv`, and confirmed imports resolve below `.venv/Lib/site-packages/yadof`.
- The focused installed-package suite passed 70 tests covering workspace init/check,
  config/task loading, checkpoint recovery, viewer discovery, and package artifacts.
- The complete installed-package suite passed 272 tests with eight expected warnings
  from deliberately injected history-recording loss and writer interruption.
- The maintained HFSS example passed installed `yadof check` with zero warnings.

## Follow-Up

- None. The recurring automatic release-marker toDo remains active for future
  naturally encountered matches.
