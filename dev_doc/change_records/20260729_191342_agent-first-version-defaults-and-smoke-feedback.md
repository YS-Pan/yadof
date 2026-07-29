# 2026-07-29 19:13 - Agent-First Release Defaults And Smoke Feedback

## Context

- The packaged project needed to make its intended AI-agent-first usage explicit.
- Version 0.1.0 is reserved for the older pre-package implementation, while the
  current installable package is the 0.2.0 line.
- A standalone smoke test produced no terminal output until execution finished,
  which made long simulator runs look stalled.
- The run CLI still defaulted to one generation instead of the requested 50.
- The actual development environment and an expandable prompt-example location were
  not documented.

## Change

- Updated the package version source and current reference workspace marker to
  0.2.0, plus current README, agent documentation, and tests.
- Made `yadof run` default to 50 generations while retaining explicit CLI overrides
  and the Python API's explicit generation argument.
- Added flushed standalone-smoke start output with workspace, backend, jobs
  directory, one-midpoint scope, and no-timeout notice.
- Added focused tests for the new run default and for feedback being visible before
  the smoke evaluator is called.
- Reworked the project README around an AI-agent-first workflow, recommended Codex
  as the development reference, linked an expandable agent prompt directory, and
  left the first prompt body blank.
- Added a dated reference environment snapshot covering Windows, AEDT, Python,
  PyAEDT, HTCondor, numerical, surrogate, build, and test versions.
- Synchronized agent docs, architecture, blueprints, terminology, and current
  installation examples.

## Rationale

- Agent-led task authoring is safer when the package can route the agent through
  version-matched ownership, reading, and validation rules.
- Immediate flushed feedback confirms that smoke execution started and tells the
  user where to inspect job artifacts during an unlimited run.
- A CLI-only default preserves explicit Python API behavior while matching normal
  interactive expectations.
- A dated environment snapshot supports reproduction without narrowing the declared
  compatibility contract to one workstation.

## Impact

- The wheel, CLI help, installed agent documents, repository documentation,
  reference workspace provenance, and package/version tests now describe 0.2.0.
- Omitting `--generations` from `yadof run` now requests 50 generations.
- Standalone smoke users receive output before the expensive workflow begins.

## Follow-Up

- The first prompt example remains intentionally blank until concrete task prompts
  are supplied.
