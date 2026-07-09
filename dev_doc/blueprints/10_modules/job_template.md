# Module blueprint: job_template

## Intent
- Own the task-specific definition of optimization variables, workflow execution, rawData shape, and rawData-to-cost calculation.
- Allow each optimization campaign to replace task files without changing the framework core.
- Keep expensive evaluation outputs as rawData only; cost is a dynamic interpretation of rawData under the current task definition.

## Historical Lineage
- HFSS workflow and adapter conventions descend from earlier huangzetao/fanyufei task templates, but active task files are intentionally replaceable.
- The old workflow habit of writing final costs was split: current workflows write rawData only, while `calc_cost.py` owns rawData-to-cost interpretation.
- Shorten-style synthetic problem/objective ideas remain useful as references for non-HFSS tasks and surrogate-friendly rawData shapes.

## Functionalities
- `api.py` exposes parameter metadata, variable count, objective metadata, normalization helpers, job-file copying, rawData cost calculation, and optional rawData importance weights for surrogate training.
- `parameters_constraints.py` defines the current task's `PARAMETERS`.
- `parameters_constraints_class.py` defines `Parameter`, normalization, denormalization, continuous intervals, and discrete values.
- `workflow.py` converts raw variables into flat schema-valid `rawData/*.npz` files, reads job-local `config.py` for HFSS defaults when present, writes job-local lifecycle metadata, can import task-local adapter files from the same directory, and never saves cost.
- `project/com_lib/hfss_com.py` is a source/reference copy for the HFSS adapter; a task can copy it into `project/job_template/` when its workflow needs HFSS.
- `project/com_lib/test_com.py` is the retained pure-Python simulator stand-in for `variables -> rawData`, including an HFSS-like profile that emits S11 traces plus `Freq x Phi x Theta` far-field grids for surrogate-speed tests; it must be copied into `job_template` before a workflow can use it.
- `calc_cost.py` converts one sample's task rawData items into the current objective cost tuple. It also may mark objective-relevant rawData slots for surrogate training through task-owned importance weights.
- `rawdata_contract.py` validates `.npz` metadata, shape, axis descriptors, schema version, and flat rawData directories.
- Adapter files present in `job_template` are copied into prepared jobs with the workflow and are task-owned implementation details.

## I/O Format
- Parameter API returns names, ranges, units, and variable count.
- Workflow input is either `variables.json` or `job_input.json` containing unnormalized variables.
- Workflow output is one or more task-defined `.npz` files directly under `rawData/`.
- Workflow lifecycle output is `individual_metadata.json` in the job folder, with `started_at`, `ended_at`, status, rawData file names, runtime HFSS defaults such as core count, and catchable exception details when the workflow fails before producing rawData.
- Each rawData `.npz` must contain a numeric `values` or `data` array and scalar JSON metadata under the canonical `metadata` key with `schema_version`, `shape`, and optional ordered `axes`. Do not also write a duplicate `meta` array.
- Cost API accepts samples shaped as `samples[sample][rawData_item]` and returns `samples[sample][objective_cost]`.
- RawData importance API accepts one sample shaped as `sample[rawData_item]` and returns per-item weight arrays keyed by rawData array name. Weights emphasize objective-relevant windows while retaining a positive floor for the rest of each field.
- The task defines the objective count, names, and numeric scale through `calc_cost.py`; framework code must discover them through `job_template.api` rather than hard-coding them.

## Non-Obvious Techniques
- `workflow.py` owns `variables -> rawData`; `calc_cost.py` owns `rawData -> cost`. Do not let workflow write `cost.json`.
- `workflow.py` owns the individual's evaluation timing. It writes `started_at` before rawData generation and `ended_at` after success or catchable failure; catchable failures include `error_type`, `error_message`, and a traceback tail for distributed diagnostics.
- rawData metadata should describe the data item only; do not echo the full variable vector or job metadata into every `.npz`. The only accepted metadata payload key is `metadata`; `meta` is not a compatibility alias.
- Default cost shaping mirrors the old fanyufei workflow style: a tanh-based soft cost maps values near a goal to 0 and values near a worst threshold to 1.
- HFSS far-field exports should preserve full-field information for surrogate training when the active task needs it. Task-specific `calc_cost.py` code can select objective windows later; explicit `primary_sweep_variable` requests remain available only for trace-style diagnostics or task variants that intentionally need reduced data.
- `calc_cost.py` must treat full-matrix Far Fields as the default rawData shape. It selects `Phi=90deg`, target `Theta`, and target `Freq` only while deriving objective curves; it should reduce any remaining non-objective axes at calculation time instead of requiring workflow exports to be trace-only.
- RawData importance weights should mirror the current task's objective-relevant windows while retaining a positive weight floor for the rest of each field.
- `recorded_data` asks this module to normalize historical raw variables using current parameter ranges, which supports mid-run range edits.
- The rawData contract is generic. Core framework code validates shape and metadata but should not infer physical meaning from axis names.
- Job-copy behavior excludes module APIs and cost code, but `evaluate_manager` adds the submit-side `config.py` and `config_all.py` beside the copied workflow so each job keeps the run configuration that produced it.
- Task files are intentionally replaceable by user or AI-generated code before a new campaign.

## Mutability Profile
- `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, active adapter files in `job_template`, and simulator model files are the most mutable source files in the project.
- `parameters_constraints_class.py`, `api.py`, and `rawdata_contract.py` define shared contracts and should be more stable.
- Real simulator adapters can be added later, but the no-cost-in-workflow rule should remain stable.
