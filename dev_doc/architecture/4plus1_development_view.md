# 4+1 development view

## Repository layout

Framework source lives only under `src/yadof/`; maintained generic tests live under
`tests/`. Root `dev_doc/` and `user_doc/` are authoritative editable sources and
are mapped into the wheel as read-only resources. `admin_tool/` owns system/pool
operations outside package runtime. Complete reference workspaces may be tracked
under `examples/`, but build inclusion excludes them from wheel/sdist. Runtime
workspaces are user-owned and normally live outside package source.

```text
src/yadof/                 installed framework
  cli/                     command routing
  workspace/               context/init/check/marker
  job_template/            parameter, rawData, cost contracts
  evaluate_manager/        fast/job/local/HTCondor execution
    fast_runner.py         reusable isolated no-job-folder fast workers
    fast_resources.py      fast-specific host-capacity planning
    process_control.py     shared exact process-tree termination
  recorded_data/           durable evidence
  optimize/                candidate mechanics and campaign loop
  surrogate/               rawData-first model and scheduling
  tools/                   optional user-launched utilities
    surrogate_viewer/      optional read-only GUI/text inspection and dev_doc
  _resources/              templates/adapters/docs/worker helper
tests/                     maintained generic verification
dev_doc/                   developer source documentation
  README.md                entry, reading order, environment, maintenance workflow
  development_environment.md detected reproducibility snapshot
  skill/                   module-specific documentation contracts
user_doc/                  user-workflow documentation, primarily for the user's AI agent
  example_prompts/         expandable prompt-example collection
admin_tool/                administrator-only operations
```

## Dependency discipline

Core modules communicate through public package exports or `api.py` boundaries.
`job_template` must remain task-neutral. `evaluate_manager` may depend on task and
persistence APIs; `optimize` may coordinate evaluation/history/surrogate; core code
must not depend on optional tools. Stateful APIs accept explicit workspace context.
No module calculates mutable user paths relative to package `__file__`.

Code placement follows variability: behavior invariant across optimization tasks
belongs in yadof; behavior that changes with simulator, model, rawData meaning, or
objective policy belongs in workspace `workflow.py`/`calc_cost.py`. Execute-side
fixed behavior is shipped through the package-owned `worker_misc.py`, while
submit-side reusable cost/rawData behavior is exposed through
`yadof.job_template`. Task modules call these surfaces and do not copy them.

Tests import an installed distribution. Generic default tests do not depend on a
simulator or live HTCondor pool; scheduler commands and adapters are mocked. Artifact
tests build the distributions, inspect members, install a wheel outside the
repository, make package files read-only, and exercise the CLI and two-workspace
contracts.

Mocked distributed tests cover event-log execute segments and preserve provenance
priority: worker-reported `execute_machine` wins, timed-out active/held segments may
fall back to `condor_execute_machine`, historical terminal/removal tails are
recognized, and never-executed queued jobs remain unassigned.

The defined PyChrono subprocess protocol has a fake-child conformance suite before
the packaged adapter exists. It launches an absolute ordinary Python interpreter as
the external runtime and verifies JSON/NPZ exchange, environment isolation,
diagnostic bounds, failure taxonomy, timeout descendant cleanup, path quoting, and
concurrent scratch isolation without importing or installing PyChrono. When the
adapter lands, the same acceptance cases must target its launch surface.

Task-specific tests that hard-code a concrete model, design, objective, frequency,
or exact active variable set belong with a disposable/reference workspace, not in
the reusable package suite. Small neutral shapes and fake adapters remain valid
generic fixtures.

psutil is a core dependency because local and fast evaluation must observe process
trees and submit-host capacity on supported platforms. It remains submit-host
package logic and is never copied into distributed job payloads.

The viewer remains a leaf below `tools`: CLI parser construction and
`yadof.tools` imports must not load Torch, Matplotlib, or Tkinter. Its subpackage
loads backend/model dependencies only for a selected viewer mode, and loads
Matplotlib/Tkinter only for the GUI. Text reports use the same viewer backend and
write only stdout/stderr.
Viewer-specific architecture and blueprints remain below
`tools/surrogate_viewer/dev_doc/`, while maintained pytest coverage lives in the
repository's top-level `tests/`.

The canonical local environment is the repository sibling `../.venv`, created from
the system Python. Development acceptance never uses an editable install or
repository `src/` on `PYTHONPATH`: after each change, build a wheel, force-reinstall
that wheel without dependency churn, verify the import path is below the venv's
site-packages, and only then run pytest with the venv interpreter.

## Change discipline

- Read the development guide and its linked module contracts, then architecture,
  terminology, relevant blueprints, and active toDos before editing.
- Before reporting normal work complete, compare active automatic toDos with the
  already in-scope files, their direct evidence, and the current diff. Execute only
  objective matches that stay within the documented scope; this bounded checkpoint
  must not become an unrelated repository scan.
- Update architecture when system relationships change; update blueprints when
  module/file contracts change; update user docs when task-authoring behavior
  changes; add one append-only change record.
- Prefer current contracts over compatibility aliases and silent fallbacks. Obsolete
  design notes are preserved only as historical evidence.
- Protect workspace isolation, rawData schema, persistence atomicity, direct
  workflow submission, payload exclusions, and artifact membership with tests.

Installed command routing lives under `src/yadof/cli/`; workspace context,
initialization, marker, and checking live under `src/yadof/workspace/`. Packaged
documentation commands list, show, or bundle audience-relative resources without
requiring an agent to locate site-packages.
