# Reference Map

This map answers the question: given a module in `project/`, which files in `reference/` are the closest source references or conceptual ancestors?

The map is not a one-to-one copy plan. The current project follows `spec 20260502.md`, so conflicts are resolved in favor of the v3 modular structure, API boundaries, rawData-first cost calculation, and no durable cost files.

## `project/` as a whole

For the whole project, the primary references are:

- `reference/20260403 fanyufei/prompt/00_project.md`
- `reference/20260403 fanyufei/prompt/10_modules/optimization_core.md`
- `reference/20260403 fanyufei/prompt/10_modules/job_pipeline.md`
- `reference/20260403 fanyufei/prompt/10_modules/surrogate_and_recording.md`
- `reference/20260403 fanyufei/prompt/10_modules/solver_worker.md`
- `reference/20260418 shorten/prompt/_project.md`
- `reference/20260418 shorten/prompt/_module.md`
- `reference/20260319 huangzetao/job_template/workflow.py`
- `reference/20260319 huangzetao/job_template/hfss_com.py`
- `reference/20260319 huangzetao/job_template/Metal_recon_ant.aedt`
- `reference/htcondor_windows_debug_reference.md`
- `reference/GPSAF A Generalized Probabilistic Surrogate-Assisted Framework for Constrained Single- and Multi-objective Optimization.tex`

Natural-language mapping: `project/` combines the mature job pipeline and raw-data recording habits from `20260403 fanyufei`, the surrogate-refresh and cumulative-archive ideas from `20260418 shorten`, the HFSS task/workflow from `20260319 huangzetao`, the HTCondor experience from `20260124 combined` and the HTCondor debug note, and the algorithmic direction from the GPSAF paper.

## `project/optimize`

Input module name: `optimize`.

Closest reference files:

- `reference/20260403 fanyufei/code/optimize.py`
- `reference/20260403 fanyufei/code/optimize_misc.py`
- `reference/20260403 fanyufei/code/optConfig.py`
- `reference/20260418 shorten/code/optimize_surrogate.py`
- `reference/20260418 shorten/code/generation_plan.py`
- `reference/20260418 shorten/code/archive_store.py`
- `reference/20260418 shorten/code/surrogate_runtime.py`
- `reference/GPSAF A Generalized Probabilistic Surrogate-Assisted Framework for Constrained Single- and Multi-objective Optimization.tex`

Natural-language mapping: when working on `project/optimize`, look first at the fanyufei optimizer for campaign orchestration, resume behavior, and optimizer/recording separation. Look at shorten's `optimize_surrogate.py`, `generation_plan.py`, and `archive_store.py` for surrogate-assisted generation flow and archive reuse. Use the GPSAF paper for the alpha/beta/gamma surrogate-assistance concept. The v3 implementation should still call only public module APIs and should not directly manage jobs or rawData storage.

## `project/surrogate`

Input module name: `surrogate`.

Closest reference files:

- `reference/20260418 shorten/code/surrogate_runtime.py`
- `reference/20260418 shorten/code/modeling.py`
- `reference/20260418 shorten/code/pipeline.py`
- `reference/20260418 shorten/code/problem.py`
- `reference/20260418 shorten/code/objectives.py`
- `reference/20260418 shorten/code/archive_store.py`
- `reference/20260403 fanyufei/code/surrogate.py`

Natural-language mapping: `project/surrogate` inherits the idea of a refreshed optimizer-facing surrogate runtime from shorten and now uses a rawData-first conditional INR deep ensemble behind the stable v3 API. Shorten's `modeling.py` and `pipeline.py` are direct references for the richer training/export behavior, while fanyufei's `surrogate.py` remains a reference for keeping the surrogate route behind a small integration surface.

Current implementation note: `project/surrogate/runtime.py` keeps the v3 public service boundary and generic rawData flatten/reconstruct logic. `project/surrogate/modeling.py` is the direct local adaptation of shorten's conditional INR/deep-ensemble machinery, trimmed to the v3 rawData-first contract instead of the shorten archive/workspace layout.

## `project/evaluate_manager`

Input module name: `evaluate_manager`.

Closest reference files:

- `reference/20260403 fanyufei/code/prepare_job.py`
- `reference/20260403 fanyufei/code/batch_eval.py`
- `reference/20260403 fanyufei/code/run_optimize.bat`
- `reference/20260403 fanyufei/code/optConfig.py`
- `reference/20260124 combined/batch_eval.py`
- `reference/20260124 combined/main.py`
- `reference/20260124 combined/misc.py`
- `reference/htcondor_windows_debug_reference.md`

Natural-language mapping: `evaluate_manager` is the v3 replacement for prepare/evaluate orchestration from fanyufei. `prepare_job.py` maps to job-folder creation and static hashing. `batch_eval.py` maps to generation evaluation, status collection, recording, and failure handling. The older combined project and HTCondor debug note are the active references for optional distributed mode, while local mode remains the default baseline.

Current implementation note: `project/evaluate_manager/condor_runner.py` now adapts the `reference/20260124 combined/batch_eval.py` HTCondor submit/poll pattern to the v3 rawData-first contract. It keeps the Windows sandbox environment, uses the configured worker Python executable with `arguments = workflow.py`, and relies on HTCondor's default output transfer instead of relying on `cost.json`.

## `project/job_template`

Input module name: `job_template`.

Closest reference files:

- `reference/20260403 fanyufei/code/job_template/workflow.py`
- `reference/20260403 fanyufei/code/job_template/worker_misc.py`
- `reference/20260403 fanyufei/code/job_template/hfss_com.py`
- `reference/20260403 fanyufei/code/parameters_constraints.py`
- `reference/20260403 fanyufei/code/parameters_constraints_class.py`
- `reference/20260124 combined/job_template/workflow.py`
- `reference/20260124 combined/job_template/worker_misc.py`
- `reference/20260124 combined/job_template/hfss_com.py`
- `reference/20260319 huangzetao/job_template/workflow.py`
- `reference/20260319 huangzetao/job_template/hfss_com.py`
- `reference/20260319 huangzetao/job_template/Metal_recon_ant.aedt`
- `reference/20260319 huangzetao/parameters_constraints.py`
- `reference/20260418 shorten/code/problem.py`
- `reference/20260418 shorten/code/objectives.py`

Natural-language mapping: `job_template` now uses the huangzetao `Metal_recon_ant` HFSS task as its closest runnable reference, while retaining the fanyufei worker/workflow and HFSS-adapter lineage. V3 still splits workflow and cost more strictly than the reference: workflow produces flat schema-valid rawData, and `calc_cost.py` computes the four old objective costs later. The shorten `problem.py` and `objectives.py` files remain historical references for synthetic problem outputs.

## `project/recorded_data`

Input module name: `recorded_data`.

Closest reference files:

- `reference/20260403 fanyufei/code/batch_eval.py`
- `reference/20260403 fanyufei/code/prepare_job.py`
- `reference/20260403 fanyufei/code/tools/viewCost.py`
- `reference/20260418 shorten/code/archive_store.py`
- `reference/20260418 shorten/code/common.py`
- `reference/20260418 shorten/code/interactive_results.py`

Natural-language mapping: `recorded_data` takes the durable-history role that fanyufei's batch layer previously handled with JSONL and rawData archives, then makes it a dedicated v3 module. Shorten's `archive_store.py` is the closest reference for a cumulative reusable archive, while fanyufei's `viewCost.py` shows how downstream tools depend on stable history contracts. V3 differs by refusing to persist cost and normalized variables as source data.

## `project/tools`

Input module name: `tools`.

Closest reference files:

- `reference/20260403 fanyufei/code/tools/viewCost.py`
- `reference/20260403 fanyufei/code/tools/viewTime.py`
- `reference/20260403 fanyufei/code/tools/backup_recorded_data.py`
- `reference/20260403 fanyufei/code/tools/hfss_get_para_and_range.py`
- `reference/20260319 huangzetao/tools/hfss_get_para_and_range.py`
- `reference/20260418 shorten/code/interactive_results.py`

Natural-language mapping: `tools` follows fanyufei's optional observability and maintenance tools. Current `project/tools/viewCost.py` maps most directly to fanyufei's cost plotter, but it reads current `recorded_data.api` instead of legacy `para_cost.jsonl`. `project/tools/hfss_get_para_and_range.py` now maps to the huangzetao parameter-extraction tool, adapted to write `job_template/parameters_constraints.py` in the v3 `Parameter` format. Shorten's viewer is a reference for inspecting the latest shared optimization workspace.

## `project/config.py`

Input module name: `config`.

Closest reference files:

- `reference/20260403 fanyufei/code/optConfig.py`
- `reference/20260418 shorten/code/experiment_config.py`
- `reference/20260418 shorten/code/generation_plan.py`

Natural-language mapping: `project/config.py` is the v3 shared settings surface. Fanyufei's `optConfig.py` is the ancestor for optimizer/evaluation launch settings, while shorten's `experiment_config.py` is the ancestor for surrogate and optimizer defaults. The current surrogate settings expose conditional-INR training, target scaling, torch device selection, and GPSAF pressure controls; unlike both older projects, v3 keeps problem shape and objective names in `job_template.api` rather than global config.

## `project/jobs`

Input module name: `jobs`.

Closest reference files:

- `reference/20260403 fanyufei/code/prepare_job.py`
- `reference/20260403 fanyufei/code/batch_eval.py`
- `reference/20260403 fanyufei/code/job_template/workflow.py`
- `reference/20260124 combined/batch_eval.py`

Natural-language mapping: `jobs` is a runtime directory, not a source module. Its reference lineage is the fanyufei prepared-job folder layout and the older combined execution flow. In v3, job folders are still the execution sandbox, but they are not the source of truth for cost; after recording, `recorded_data` owns durable rawData.

## `project/test`

Input module name: `test`.

Closest reference files:

- `reference/20260403 fanyufei/prompt/99_notes.md`
- `reference/20260403 fanyufei/prompt/10_modules/job_pipeline.md`
- `reference/20260403 fanyufei/prompt/10_modules/surrogate_and_recording.md`
- `reference/20260418 shorten/prompt/_project.md`
- `spec 20260502.md`

Natural-language mapping: `project/test` is driven more by v3 contracts than by old test files. Its reference value comes from old prompt invariants and the current spec: local mode must work without HTCondor, rawData stays flat, cost is dynamic, failures do not crash the generation, and surrogate remains rawData-first.
