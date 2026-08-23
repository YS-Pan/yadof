# 2026-08-23 16:47 - Integrate Source Benchmark Automation

## Context

- The benchmark runner was useful to users as well as maintainers, but lived in a
  separate private Git root and assumed a fixed local output location.
- Its large evidence files and verbose command output also encouraged agents to
  consume more context than needed for planning, status, or failure diagnosis.

## Change

- Imported the benchmark repository and its history at top-level
  `benchmark_automation/`, deliberately outside `src/yadof/`.
- Added an explicit output-root override, disjoint-path validation, bounded command
  summaries, output-root-aware next commands, and focused tests.
- Added nested and root agent instructions that route through bounded
  `plan`/`preflight`/`inspect` summaries before targeted evidence reads. Agent runs
  use ignored `temp/benchmark/<task-id>` directories.
- Added a portable tracked summary for the completed performance run and removed
  machine-specific public provenance from frozen baseline metadata.
- Documented the source-checkout boundary across user guidance, architecture,
  blueprints, terminology, and repository entry points.

## Rationale

- Keeping the tool at repository top level makes it available in a clone or
  repository download without coupling concrete frozen tasks to the reusable
  installed framework.
- A selectable output root preserves a durable human default while isolating
  agent-generated evidence from source and keeping it Git-ignored.
- Progressive disclosure keeps complete evidence recoverable on disk while making
  normal agent output and reads small enough for targeted reasoning.

## Impact

- Source-checkout users can plan, preflight, run, resume, inspect, collect, and
  report the benchmark with a matching installed yadof distribution.
- Benchmark automation remains absent from wheel/sdist; installed package APIs,
  console entry points, runtime workspaces, and existing benchmark scientific
  inputs are unchanged. Packaged documentation gains the new boundary guidance and
  this change record.
- Benchmark development has its own 29-test unit suite and bounded no-simulator
  acceptance path; package acceptance remains governed by `dev_doc/README.md`.

## Follow-Up

- None required for the completed source and Git integration.
