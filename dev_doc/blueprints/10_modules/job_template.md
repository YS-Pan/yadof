# Module blueprint: job_template

## Intent
- Own the task-specific definition of optimization variables, workflow execution, rawData shape, and rawData-to-cost calculation.
- Allow each optimization campaign to replace task files without changing the framework core.
- Keep expensive evaluation outputs as rawData only; cost is a dynamic interpretation of rawData under the current task definition.
- Separate stable installed framework support from a workspace's mutable task files.

## Historical Lineage
- HFSS workflow and adapter conventions descend from earlier huangzetao/fanyufei task templates, but active task files are intentionally replaceable.
- The old workflow habit of writing final costs was split: current workflows write rawData only, while `calc_cost.py` owns rawData-to-cost interpretation.
- Shorten-style synthetic problem/objective ideas remain useful as references for non-HFSS tasks and surrogate-friendly rawData shapes.

## Functionalities
- `yadof.job_template` owns the installed `Parameter` class, normalization and
  assigned-snapshot materialization, rawData contract/views, generic cost helpers,
  and workspace-explicit parameter/objective/cost APIs.
- A package-era workspace `job_template/` owns only
  `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, active `*_com.py`
  adapters, simulator/custom inputs, lookup tables, and other task assets. It does
  not contain framework `api.py`, the parameter class, rawData contract, or generic
  cost helpers.
- The default bundled workspace template supplies only those three task files. Its
  generic parameter/objective names and pure-Python/NumPy workflow are placeholders,
  not a selected simulator, adapter, model, physical result, or active campaign.
- `yadof.task_loader` fresh-loads submit-side task modules. It supports sibling
  absolute imports and package-relative imports, even when two workspaces use the
  same helper names, without a permanent `sys.path` entry or module-cache residue.
- `api.py` exposes fresh parameter queries, isolated parameter-file loading,
  definition-only hash signatures, job-local parameter materialization, objective
  metadata, normalization helpers, job-file copying, rawData cost calculation, and
  optional rawData importance weights for surrogate training.
- Canonical `parameters_constraints.py` defines the current task's unassigned
  `PARAMETERS`; each job-local file is a definition snapshot with that individual's
  `normalized_value` and raw `value` assigned.
- `parameters_constraints_class.py` defines the mutable `Parameter` assignment
  state, normalization, denormalization, continuous intervals, and discrete values.
- `workflow.py` converts raw variables into flat schema-valid `rawData/*.npz` files, reads its matching job-local module under `config/specific/` for simulator defaults when present, writes job-local lifecycle metadata, can import task-local adapter files from the same directory, and never saves cost.
- `project/com_lib/hfss_com.py` is the synchronized reusable reference copy for the HFSS adapter; a task can copy it into `project/job_template/` when its workflow needs HFSS. Reusable fixes validated in the active copy should be copied back without task-only assumptions.
- `project/com_lib/test_com.py` is the retained pure-Python simulator stand-in for `variables -> rawData`, including an HFSS-like profile that emits S11 traces plus `Freq x Phi x Theta` far-field grids for surrogate-speed tests; it must be copied into `job_template` before a workflow can use it.
- `calc_cost.py` converts one sample's task rawData items into the current objective cost tuple. It also may mark objective-relevant rawData slots for surrogate training through task-owned importance weights.
- `rawdata_contract.py` validates `.npz` metadata, shape, axis descriptors, schema version, and flat rawData directories.
- Adapter files present in `job_template` are copied into prepared jobs with the workflow and are task-owned implementation details.
- Stable workflow helpers such as `worker_misc.py` are installed package worker
  support, not workspace task files. The package copies them into each job under a
  reserved filename after proving the task payload does not collide.

## I/O Format
- Every installed job-template query takes an explicit workspace/context first.
  Parameter and objective metadata are immutable snapshots of current workspace
  source; cost accepts rawData samples and derives rows through freshly loaded
  `calc_cost.py`.
- Workspace `parameters_constraints.py` imports `Parameter` from
  `yadof.job_template`. A materialized job snapshot does the same and contains the
  current definitions plus finite assigned raw/normalized values.
- Parameter API returns fresh names, ranges, units, constraints, and variable count.
- Job materialization accepts one normalized row and returns the raw values written
  into the same job-local `parameters_constraints.py` snapshot.
- Workflow input is the assigned `parameter.value` fields in that snapshot.
- Workflow output is one or more task-defined `.npz` files directly under `rawData/`.
- Workflow lifecycle output is `individual_metadata.json` in the job folder, with `started_at`, `ended_at`, status, rawData file names, runtime HFSS defaults such as core count, and catchable exception details when the workflow fails before producing rawData.
- `yadof_worker_config.json` is package-generated local worker context. It contains
  yadof/workspace provenance and only effective local evaluation mode, timeout, and
  worker count with sources; task code must not expect a copied package config tree.
- Each rawData `.npz` must contain a numeric `values` or `data` array and scalar JSON metadata under the canonical `metadata` key with `schema_version`, `shape`, and optional ordered `axes`. Do not also write a duplicate `meta` array.
- Cost API accepts samples shaped as `samples[sample][rawData_item]` and returns `samples[sample][objective_cost]`.
- RawData importance API accepts one sample shaped as `sample[rawData_item]` and returns per-item weight arrays keyed by rawData array name. Weights emphasize objective-relevant windows while retaining a positive floor for the rest of each field.
- The task defines the objective count, names, and numeric scale through `calc_cost.py`; framework code must discover them through `job_template.api` rather than hard-coding them.

## Non-Obvious Techniques
- The isolated task loader uses a unique ephemeral package for relative imports and
  a temporary meta-path finder for local absolute imports. It compiles source bytes
  directly, removes all workspace-owned entries from `sys.modules`, restores
  collisions, and never edits `sys.path`.
- Task validation imports parameters and cost policy but only checks that
  `workflow.py` exists; it must not launch an expensive workflow as a side effect.
- Workspace init additionally syntax-parses staged `workflow.py`; workspace check
  syntax-parses the current workflow and explicitly reports that it was not imported
  or executed. An already-present task-local `rawData/` directory is checked with the
  same flat schema validator, but neither command creates or evaluates rawData.
- `workflow.py` owns `variables -> rawData`; `calc_cost.py` owns `rawData -> cost`. Do not let workflow write `cost.json`.
- A simulator workflow must consume the assigned job-local
  `parameters_constraints.py` snapshot directly. It must not reconstruct individual
  values from a removed or parallel job-input channel.
- `workflow.py` owns the individual's evaluation timing. It writes `started_at` before rawData generation and `ended_at` after success or catchable failure; catchable failures include `error_type`, `error_message`, and a traceback tail for distributed diagnostics.
- rawData metadata should describe the data item only; do not echo the full variable vector or job metadata into every `.npz`. The only accepted metadata payload key is `metadata`; `meta` is not a compatibility alias.
- Default cost shaping mirrors the old fanyufei workflow style: a tanh-based soft cost maps values near a goal to 0 and values near a worst threshold to 1.
- HFSS far-field exports should preserve full-field information for surrogate training when the active task needs it. Task-specific `calc_cost.py` code can select objective windows later; explicit `primary_sweep_variable` requests remain available only for trace-style diagnostics or task variants that intentionally need reduced data.
- `calc_cost.py` must treat full-matrix Far Fields as the default rawData shape. It selects `Phi=90deg`, target `Theta`, and target `Freq` only while deriving objective curves; it should reduce any remaining non-objective axes at calculation time instead of requiring workflow exports to be trace-only.
- RawData importance weights should mirror the current task's objective-relevant windows while retaining a positive weight floor for the rest of each field.
- `recorded_data` asks this module to normalize historical raw variables using current parameter ranges, which supports mid-run range edits.
- Parameter queries and job materialization execute the requested parameter file in
  a fresh isolated module namespace. They do not reuse a long-lived imported
  `PARAMETERS` object, mutate `sys.path`, or reload shared modules during concurrent
  preparation.
- A canonical file may leave assignment fields as NaN. A materialized job must have
  finite normalized/raw assignments and a parameter count matching its candidate.
- The rawData contract is generic. Core framework code validates shape and metadata but should not infer physical meaning from axis names.
- Package job-copy behavior excludes framework APIs, canonical parameters, runtime
  artifacts, and cost code. It recursively preserves arbitrary nested task assets
  and multiple adapters, adds an assigned parameter snapshot plus package
  `worker_misc.py`, and adds compact JSON rather than a full config package.
- Task files are intentionally replaceable by user or AI-generated code before a new campaign.

## Mutability Profile
- `src/yadof/job_template/` and `src/yadof/task_loader.py` are stable installed
  framework code. Workspace task files are the package-era highly mutable boundary.
- `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, active adapter files in `job_template`, and simulator model files are the most mutable source files in the project.
- `parameters_constraints_class.py`, `api.py`, and `rawdata_contract.py` define shared contracts and should be more stable.
- Real simulator adapters can be added later, but the no-cost-in-workflow rule should remain stable.
