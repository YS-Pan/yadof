# Module blueprint: job_template

## Intent
- Own the task-specific definition of optimization variables, workflow execution, rawData shape, and rawData-to-cost calculation.
- Allow each optimization campaign to replace task files without changing the framework core.
- Keep expensive evaluation outputs as rawData only; cost is a dynamic interpretation of rawData under the current task definition.

## Functionalities
- `api.py` exposes parameter metadata, variable count, objective metadata, normalization helpers, job-file copying, rawData cost calculation, and optional rawData importance weights for surrogate training.
- `parameters_constraints.py` defines the current task's `PARAMETERS`.
- `parameters_constraints_class.py` defines `Parameter`, normalization, denormalization, continuous intervals, and discrete values.
- `workflow.py` converts raw variables into flat schema-valid `rawData/*.npz` files, writes job-local lifecycle metadata, uses same-directory `hfss_com.py` for the current HFSS task, and never saves cost.
- `project/com_lib/hfss_com.py` is the source/reference copy for the current HFSS adapter; `project/job_template/hfss_com.py` is the active copy used by jobs.
- `project/com_lib/test_com.py` is the retained pure-Python simulator stand-in for `variables -> rawData`, but it must be copied into `job_template` before a workflow can use it.
- `calc_cost.py` converts one sample's HFSS rawData items into three objective cost tuples: `cost_s11_band`, `cost_gain_lhcp_targets`, and `cost_axial_ratio_targets`. It also marks S11 frequency bands and target far-field angles as objective-relevant rawData slots for surrogate training.
- `rawdata_contract.py` validates `.npz` metadata, shape, axis descriptors, schema version, and flat rawData directories.
- `hfss_com.py` in `job_template` is the current real HFSS/PyAEDT adapter and is copied into prepared jobs with the workflow.

## I/O Format
- Parameter API returns names, ranges, units, and variable count.
- Workflow input is either `variables.json` or `job_input.json` containing unnormalized variables.
- Workflow output is one or more `.npz` files directly under `rawData/`; the current HFSS workflow writes S11, LHCP realized-gain, and axial-ratio files for pin states 1 through 3.
- Workflow lifecycle output is `individual_metadata.json` in the job folder, with `started_at`, `ended_at`, status, rawData file names, and catchable exception details when the workflow fails before producing rawData.
- Each rawData `.npz` must contain a numeric `values` or `data` array and scalar JSON metadata under the canonical `metadata` key with `schema_version`, `shape`, and optional ordered `axes`. Do not also write a duplicate `meta` array.
- Cost API accepts samples shaped as `samples[sample][rawData_item]` and returns `samples[sample][objective_cost]`.
- RawData importance API accepts one sample shaped as `sample[rawData_item]` and returns per-item weight arrays keyed by rawData array name. Weights emphasize objective-relevant windows while retaining a positive floor for the rest of each field.
- The current HFSS task returns three minimization costs, each bounded to `[0, 1]`.

## Non-Obvious Techniques
- `workflow.py` owns `variables -> rawData`; `calc_cost.py` owns `rawData -> cost`. Do not let workflow write `cost.json`.
- `workflow.py` owns the individual's evaluation timing. It writes `started_at` before rawData generation and `ended_at` after success or catchable failure; catchable failures include `error_type`, `error_message`, and a traceback tail for distributed diagnostics.
- rawData metadata should describe the data item only; do not echo the full variable vector or job metadata into every `.npz`. The only accepted metadata payload key is `metadata`; `meta` is not a compatibility alias.
- Default cost shaping mirrors the old fanyufei workflow style: a tanh-based soft cost maps values near a goal to 0 and values near a worst threshold to 1.
- Current HFSS far-field exports should preserve full-field information for surrogate training while still using the AEDT far-field setup name from the active project (`Infinite Sphere1` for `Newchoke20260620.aedt`) and the solution family that owns each quantity. LHCP gain uses `Setup1 : LastAdaptive` at the target frequency with full `Theta/Phi` coverage, and axial ratio uses `Setup1 : Sweep` with full `Theta/Phi/Freq` coverage. `hfss_com.py` should default Far Fields to full-matrix rawData; explicit `primary_sweep_variable` requests remain available only for trace-style diagnostics or task variants that intentionally need reduced data.
- `calc_cost.py` must treat full-matrix Far Fields as the default rawData shape. It selects `Phi=90deg`, target `Theta`, and target `Freq` only while deriving objective curves; it should reduce any remaining non-objective axes at calculation time instead of requiring workflow exports to be trace-only.
- Current rawData importance weights mirror the cost observation windows: S11 values inside 2.40-2.48 GHz and far-field values at target theta cuts receive extra surrogate-training weight while all other full-field slots retain a positive weight floor.
- `recorded_data` asks this module to normalize historical raw variables using current parameter ranges, which supports mid-run range edits.
- The rawData contract is generic. Core framework code validates shape and metadata but should not infer physical meaning from axis names.
- Job-copy behavior excludes module APIs and cost code, keeping copied jobs small and focused on rawData generation.
- Task files are intentionally replaceable by user or AI-generated code before a new campaign.

## Mutability Profile
- `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, active adapter files in `job_template`, and simulator model files are the most mutable source files in the project.
- `parameters_constraints_class.py`, `api.py`, and `rawdata_contract.py` define shared contracts and should be more stable.
- Real simulator adapters can be added later, but the no-cost-in-workflow rule should remain stable.
