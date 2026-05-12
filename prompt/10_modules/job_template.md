# Module prompt: job_template

## Intent
- Own the task-specific definition of optimization variables, workflow execution, rawData shape, and rawData-to-cost calculation.
- Allow each optimization campaign to replace task files without changing the framework core.
- Keep expensive evaluation outputs as rawData only; cost is a dynamic interpretation of rawData under the current task definition.

## Functionalities
- `api.py` exposes parameter metadata, variable count, objective metadata, normalization helpers, job-file copying, and rawData cost calculation.
- `parameters_constraints.py` defines the current task's `PARAMETERS`.
- `parameters_constraints_class.py` defines `Parameter`, normalization, denormalization, continuous intervals, and discrete values.
- `workflow.py` converts raw variables into flat schema-valid `rawData/*.npz` files and never saves cost.
- `test_com.py` is the current pure-Python simulator stand-in for `variables -> rawData`.
- `calc_cost.py` converts one sample's rawData items into three objective cost tuples: `target_match_cost`, `curve_magnitude_cost`, and `surface_reward_cost`.
- `rawdata_contract.py` validates `.npz` metadata, shape, axis descriptors, schema version, and flat rawData directories.
- `hfss_com.py` is retained as a real HFSS-adapter reference surface, but it is not copied into local test jobs by default.

## I/O Format
- Parameter API returns names, ranges, units, and variable count.
- Workflow input is either `variables.json` or `job_input.json` containing unnormalized variables.
- Workflow output is one or more `.npz` files directly under `rawData/`.
- Each rawData `.npz` must contain a numeric `values` or `data` array and scalar JSON metadata with `schema_version`, `shape`, and optional ordered `axes`.
- Cost API accepts samples shaped as `samples[sample][rawData_item]` and returns `samples[sample][objective_cost]`.
- The default test task returns three minimization costs, each bounded to `[0, 1]`.

## Non-Obvious Techniques
- `workflow.py` owns `variables -> rawData`; `calc_cost.py` owns `rawData -> cost`. Do not let workflow write `cost.json`.
- Default cost shaping mirrors the old fanyufei workflow style: a tanh-based soft cost maps values near a goal to 0 and values near a worst threshold to 1.
- `recorded_data` asks this module to normalize historical raw variables using current parameter ranges, which supports mid-run range edits.
- The rawData contract is generic. Core framework code validates shape and metadata but should not infer physical meaning from axis names.
- Job-copy behavior excludes module APIs and cost code, keeping copied jobs small and focused on rawData generation.
- Task files are intentionally replaceable by user or AI-generated code before a new campaign.

## Mutability Profile
- `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, `test_com.py`, and simulator model files are the most mutable source files in the project.
- `parameters_constraints_class.py`, `api.py`, and `rawdata_contract.py` define shared contracts and should be more stable.
- Real simulator adapters can be added later, but the no-cost-in-workflow rule should remain stable.
