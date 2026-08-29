# C4 package components

## Foundation

- `workspace` resolves, initializes, and validates explicit writable workspaces.
- `config` builds immutable effective campaign configuration.
- `task_loader` and `task_snapshot` isolate workspace modules and provide one
  coherent task definition per generation.
- `_resources` supplies read-only templates, adapters, worker support, and installed
  documentation.

## Task interpretation

- `job_template` owns parameter assignment, normalization, rawData validation and
  views, current-cost dispatch, and task checking.
- RawData templates describe exact named evidence fields for consumers that need a
  stable schema.
- Cost projection converts complete schema-compatible predicted rawData through a
  frozen current task interpreter. It does not own task objective policy or record
  predictions.

## Evaluation

- `evaluate_manager` selects the backend and preserves population order and
  per-individual failure isolation.
- Job preparation copies task inputs, assigned parameters, and invariant worker
  support into self-contained prepared jobs.
- Fast, local, and HTCondor runners own their transport, timeout, cleanup, and
  diagnostic mechanisms.
- Resource components interpret backend observations for future scheduling without
  changing task evidence.
- The common finalizer owns rawData validation/ownership, current-cost evaluation,
  result construction, and recorder handoff.

## Durable evidence

- `recorded_data` owns the campaign session, workspace lock, immutable segment
  publication, tolerant discovery, and current-history queries.
- The writer bounds unpublished ownership and makes publication failure
  campaign-fatal.
- Readers isolate corrupt or incompatible records without rewriting surviving
  evidence.

## Optimization and surrogate components

- `optimize` owns the campaign engine, workspace-selected strategy seam, and common
  real-evaluation boundary.
- Search, surrogate-assistance, posterior-assisted selection, and acquisition
  components remain explicitly composed rather than selected by a second global
  method registry.
- `surrogate` owns rawData-first component lifecycles, checkpoints, prediction, and
  optional posterior capabilities. Concrete models remain behind lightweight
  public contracts and lazy optional dependencies. Hierarchical CAE owns its
  training-data filtering implementations below its private package and selects
  them through one component-local mode whose default is no filtering; the current
  opt-in implementation is `frequency`.
- Posterior and readiness contracts describe derived candidate-selection
  capabilities; they do not bypass real evaluation or persistence.

## Tools and CLI

- `cli` routes explicit commands and workspace arguments.
- `tools` contains optional inspection, history, adapter-copy, and task-support
  utilities. Integrated viewer subtrees own their detailed developer documentation
  and remain outside core execution.

## Dependency direction

Core components communicate through public package exports or narrow APIs.
Evaluation may consume task and persistence contracts; optimization may coordinate
evaluation, history, and surrogate components. Core runtime does not depend on
optional tools, administrators, benchmark automation, or concrete simulator
projects.

Optional numerical backends load only after their component is selected. Workspace
task modules may import job-local files and deliberately installed dependencies,
but distributed workflows must not import yadof. Stateful public APIs accept an
explicit workspace instead of deriving mutable paths from package location.

Detailed module and exceptional-file behavior belongs in `../blueprints/`, which
is read selectively for the component being changed.
