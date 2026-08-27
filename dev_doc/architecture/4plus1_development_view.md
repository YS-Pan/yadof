# 4+1 development view

## Repository layout

Framework source lives only under `src/yadof/`; maintained generic tests live under
`tests/`. Root `dev_doc/` and `user_doc/` are authoritative editable sources and
are mapped into the wheel as read-only resources. `admin_tool/` owns system/pool
operations outside package runtime. Complete reference workspaces may be tracked
under `examples/`. `benchmark_automation/` owns the repository-downloadable
comparison runner, editable baseline templates, and its focused tests. Each run
owns an immutable snapshot of the selected baseline content. Build inclusion
excludes both examples and benchmark automation from wheel/sdist. Runtime
workspaces are user-owned and normally live outside package source.

```text
src/yadof/                 installed framework
  cli/                     command routing
  workspace/               context/init/check/marker
  job_template/            parameter, rawData, and submit-cost gateways
    rawdata_template.py    exact named field templates and schema signatures
    rawdata_projector.py   frozen current-cost projection and validity diagnostics
  evaluate_manager/        fast/job/local/HTCondor execution
    finalizer.py           common current-cost and recorder-offer boundary
    fast_runner.py         reusable isolated no-job-folder fast workers
    fast_resources.py      fast-specific host-capacity planning
    process_control.py     shared exact process-tree termination
  task_snapshot.py         immutable two-root generation capture/fingerprints
  recorded_data/           campaign session and immutable segments
    session.py             hot history, bounded writer, counters, lock lifetime
    segment_store.py       standard-ZIP publication/tolerant discovery
    records.py             owned envelopes and immutable event files
    query.py               partial/corruption-tolerant history
  optimize/                campaign engine + public strategy components/state
    gpsaf/                 GPSAF assistance, phases, and private records
    pymoo/                 lazy GA/NSGA-III backend adapter
  surrogate/               lightweight public rawData-surrogate API
    posterior.py           backend-neutral persistent function-sampler protocol
    conditional_inr/       model, runtime, scheduling, checkpoint implementation
  tools/                   optional user-launched utilities
    cost_viewer/           reusable cost analysis/rendering and dev_doc
    surrogate_viewer/      optional read-only GUI/text inspection and dev_doc
  _resources/              templates/adapters/docs/worker helper
tests/                     maintained generic verification
dev_doc/                   developer source documentation
  README.md                entry, reading order, environment, maintenance workflow
  development_environment.md detected reproducibility snapshot
  skill/                   module-specific documentation contracts
user_doc/                  user-workflow documentation, primarily for the user's AI agent
  agent_environment_permissions.md
                            optional host sandbox/filesystem/Git troubleshooting;
                            explicitly outside yadof runtime behavior
  example_prompts/         expandable prompt-example collection
admin_tool/                administrator-only operations
benchmark_automation/      source-checkout runner, editable inputs, reports, and tests
  baselines/<provider>/<baseline-id>/
                            mutable simulator/adapter and optimization-task templates
  preregistrations/<registration-id>/
                            versioned schema/experiment freezes and read-only validators;
                            neither executable suites nor recorded evidence
temp/<run-id>/             default ignored benchmark runtime evidence; run ID is the
                           only directory layer below the configured output root
  inputs/baselines/<case>/  immutable task snapshot captured when the run is created
```

## Dependency discipline

Core modules communicate through public package exports or `api.py` boundaries.
`job_template` must remain task-neutral. `evaluate_manager` may depend on task and
persistence APIs; `optimize` may coordinate evaluation/history/surrogate; core code
must not depend on optional tools. Stateful APIs accept explicit workspace context.
No module calculates mutable user paths relative to package `__file__`.

The lightweight `surrogate.posterior` protocol depends only on core Python/NumPy
and the task-neutral named rawData/projector types. It must not import Torch,
BoTorch, pymoo algorithms, or a concrete surrogate. `job_template` never imports
`surrogate`; the projector accepts structured named samples and reuses an injected
`CostInterpreter`. A future acquisition strategy may depend on both public
surfaces, while a concrete surrogate depends only on the posterior protocol.

Code placement follows variability: behavior invariant across optimization tasks
belongs in yadof; behavior that changes with simulator, model, rawData meaning, or
objective policy belongs in workspace `job_template/workflow.py` and
`submit/calc_cost.py`; complete composition belongs in `submit/optimization.py`. Execute-side
fixed behavior is shipped through the package-owned `worker_misc.py`, while
submit-side reusable cost/rawData behavior is exposed through
`yadof.job_template`. Task modules call these surfaces and do not copy them.

Tests import an installed distribution. Generic default tests do not depend on a
simulator or live HTCondor pool; scheduler commands and adapters are mocked. Artifact
tests build the distributions, inspect members, install a wheel outside the
repository, make package files read-only, and exercise the CLI and two-workspace
contracts.

Benchmark tests remain below `benchmark_automation/tests/` and exercise the
source-checkout runner against an installed yadof distribution. They may describe
the configured benchmark cases, but their default unit/preflight path does not start a
simulator or a measured campaign. Generated benchmark output belongs only in the
selected ignored runs root, never in package source or editable baseline templates.
The current comparison names its concrete non-surrogate NSGA-III arm, uses a
runner-owned 32-worker oversubscribed fast setting for measured cells, runs one
cost-view render after each measured optimization, uses Rich for an active-cell
evaluation bar above the global cell bar with one atomic event-driven refresh and
cumulative count/percentage/generation detail, guarantees visible positive progress
in large cells, keeps every Rich refresh on the foreground runner thread while
pipe threads only log and enqueue events, overrides an inherited Rich-only
`TERM=dumb`/`unknown` classification after the stream proves interactive, and keeps
complete compact status fields within normal terminal widths. Read-only benchmark
inspection derives an
explicitly qualified ETA from a bounded run-local prior timing snapshot, arm-safe
completed wall times, immutable plan data, and the active command's timestamped
bounded progress-event tail for later unattended agent turns. Matched-cell medians
and generation-duration trends replace cross-arm same-case and purely linear
point estimates. The
nested benchmark `dev_doc/` mirrors the root current-view discipline with
operator/architecture/blueprint/terminology
contracts, split C4 and 4+1 architecture, generative blueprints, and terminology;
root `dev_doc/` remains the exclusive owner of repository-wide toDos, obsolete
handoffs, and change records. Attempt postprocessor
artifacts remain collision-prefixed inside one directory per baseline workspace;
cost plots stay under `visualizations/viewcost/`; bounded JSON stdout remains
separate from terminal progress and the final algorithm-labeled HV table.

Mocked distributed tests cover event-log execute segments and preserve provenance
priority: worker-reported `execute_machine` wins, timed-out active/held segments may
fall back to `condor_execute_machine`, historical terminal/removal tails are
recognized, and never-executed queued jobs remain unassigned.

The PyChrono subprocess protocol and packaged adapter share a fake-child conformance
suite. It launches an absolute ordinary Python interpreter through `chrono_com.py`
and verifies JSON/NPZ exchange, environment isolation, diagnostic bounds, failure
taxonomy, timeout descendant cleanup, path quoting, and concurrent scratch
isolation without importing or installing PyChrono.

Task-specific tests that hard-code a concrete model, design, objective, frequency,
or exact active variable set belong with a disposable/reference workspace, not in
the reusable package suite. Small neutral shapes and fake adapters remain valid
generic fixtures.

Joint-posterior contract tests use neutral fake/sample-backed functions with mixed
rawData shapes and task callbacks. They prove draw/selector identity, seed,
duplicate, empty, permutation and chunk invariance, streaming/materialized cost
equivalence, bounded invalid diagnostics, recorder non-entry, semantic identity,
and optional-backend lazy imports without claiming fitting or acquisition quality.

psutil is a core dependency because local and fast evaluation must observe process
trees and submit-host capacity on supported platforms. It remains submit-host
package logic and is never copied into distributed job payloads.

The viewers remain leaves below `tools`: CLI parser construction and
`yadof.tools` imports must not load Torch, Matplotlib, or Tkinter. The surrogate
subpackage loads backend/model dependencies only for a selected viewer mode, and
loads Matplotlib/Tkinter only for the GUI. Text reports use the same viewer backend
and write only stdout/stderr.
Cost-view numerical/plot dependencies are loaded only by the selected operation;
its stable functions are reusable by CLI, Python, and a future unified GUI without
owning widgets. Viewer-specific architecture and blueprints remain below
`tools/cost_viewer/dev_doc/` and `tools/surrogate_viewer/dev_doc/`, while
maintained pytest coverage lives in the repository's top-level `tests/`.

The canonical local environment is the repository sibling `../.venv`, created from
the system Python. Development acceptance never uses an editable install or
repository `src/` on `PYTHONPATH`: after package code/build/resource changes, build
a wheel, force-reinstall that wheel without dependency churn, verify the import path
is below the venv's site-packages, and only then run pytest with the venv
interpreter. Content-only documentation edits do not require that software test
cycle unless they change documentation packaging/discovery, command routing,
generation, or executable examples; they receive proportional static/reference
checks instead.

## Change discipline

- Read the development guide and its linked module contracts, then architecture,
  terminology, relevant blueprints, and active toDos before editing.
- Author and substantially revise toDos as standalone handoffs for a maintainer who
  has the current repository and documentation but not the originating
  conversation. Embed the task-specific problem, intent, evidence, material
  operating envelope, settled versus open decisions, and the semantics of defaults,
  limits, best-effort goals, and guarantees; links remain supplemental provenance.
  Keep the active document internally coherent after later decisions supersede
  earlier wording.
- Before reporting normal work complete, compare active automatic toDos with the
  already in-scope files, their direct evidence, and the current diff. Execute only
  objective matches that stay within the documented scope; this bounded checkpoint
  must not become an unrelated repository scan.
- Update architecture when system relationships change; update blueprints when
  module/file contracts change; update user docs when task-authoring behavior
  changes; add one append-only change record. A localized correction to exactly one
  existing documentation file may skip both the record and Git commit only under
  the narrow no-contract/no-workflow exception defined by the development guide
  and change-record contract.
- Prefer current contracts over compatibility aliases and silent fallbacks. Obsolete
  design notes are preserved only as historical evidence.
- Protect workspace isolation, rawData schema, persistence atomicity, direct
  workflow submission, payload exclusions, and artifact membership with tests.

Installed command routing lives under `src/yadof/cli/`; workspace context,
initialization, marker, and checking live under `src/yadof/workspace/`. Packaged
documentation commands list, show, or bundle audience-relative resources without
requiring an agent to locate site-packages.
