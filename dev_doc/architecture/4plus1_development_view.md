# 4+1 development view

## Repository layout

Framework source lives only under `src/yadof/`; maintained generic tests live under
`tests/`. Root `dev_doc/` and `agent_doc/` are authoritative editable sources and
are mapped into the wheel as read-only resources. `admin_tool/` owns system/pool
operations outside package runtime. Complete reference workspaces may be tracked
under `examples/`, but build inclusion excludes them from wheel/sdist. Runtime
workspaces are user-owned and normally live outside package source.

```text
src/yadof/                 installed framework
  cli/                     command routing
  workspace/               context/init/check/marker
  job_template/            parameter, rawData, cost contracts
  evaluate_manager/        job/local/HTCondor execution
  recorded_data/           durable evidence
  optimize/                candidate mechanics and campaign loop
  surrogate/               rawData-first model and scheduling
  tools/                   optional user-launched utilities
  _resources/              templates/adapters/docs/worker helper
tests/                     maintained generic verification
dev_doc/                   developer source documentation
  README.md                entry, reading order, environment, maintenance workflow
  skill/                   module-specific documentation contracts
agent_doc/                 task-authoring source documentation
admin_tool/                administrator-only operations
```

## Dependency discipline

Core modules communicate through public package exports or `api.py` boundaries.
`job_template` must remain task-neutral. `evaluate_manager` may depend on task and
persistence APIs; `optimize` may coordinate evaluation/history/surrogate; core code
must not depend on optional tools. Stateful APIs accept explicit workspace context.
No module calculates mutable user paths relative to package `__file__`.

Tests import an installed distribution. Generic default tests do not depend on a
simulator or live HTCondor pool; scheduler commands and adapters are mocked. Artifact
tests build the distributions, inspect members, install a wheel outside the
repository, make package files read-only, and exercise the CLI and two-workspace
contracts.

Task-specific tests that hard-code a concrete model, design, objective, frequency,
or exact active variable set belong with a disposable/reference workspace, not in
the reusable package suite. Small neutral shapes and fake adapters remain valid
generic fixtures.

The canonical local environment is the repository sibling `../.venv`, created from
the system Python. Development acceptance never uses an editable install or
repository `src/` on `PYTHONPATH`: after each change, build a wheel, force-reinstall
that wheel without dependency churn, verify the import path is below the venv's
site-packages, and only then run pytest with the venv interpreter.

## Change discipline

- Read the development guide and its linked module contracts, then architecture,
  terminology, relevant blueprints, and active toDos before editing.
- Update architecture when system relationships change; update blueprints when
  module/file contracts change; update agent docs when task-authoring behavior
  changes; add one append-only change record.
- Prefer current contracts over compatibility aliases and silent fallbacks. Obsolete
  design notes are preserved only as historical evidence.
- Protect workspace isolation, rawData schema, persistence atomicity, direct
  workflow submission, payload exclusions, and artifact membership with tests.

Installed command routing lives under `src/yadof/cli/`; workspace context,
initialization, marker, and checking live under `src/yadof/workspace/`. Packaged
documentation commands list, show, or bundle audience-relative resources without
requiring an agent to locate site-packages.
