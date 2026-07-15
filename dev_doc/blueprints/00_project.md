# Prompt: yadof modular optimization framework

## Intent
- Build the current `yadof` framework as a modular, recoverable optimization system under `project/`.
- Merge the mature job orchestration and recording ideas from older fanyufei-style workflows with the surrogate-assisted optimization ideas from the shorten-style experiments.
- Keep the central modeling chain as `normalized variables -> rawData -> cost`, where cost is always derived from rawData through the current `job_template/calc_cost.py`.
- Make the framework tolerant of long-running campaigns: failed evaluations, interrupted runs, changed parameter ranges, changed workflows, and local/distributed execution backends should not force a rewrite of the core optimizer.

## Historical Lineage
- Mature campaign orchestration, prepared-job folders, JSONL-style recording, and optional plotting/maintenance tools come from the older fanyufei project lineage. Current contracts live in `evaluate_manager`, `recorded_data`, and `tools` blueprints rather than in old copied paths.
- HTCondor execution experience comes from the older combined-project lineage plus the current `admin_tool/htcondor_doc/` notes. Distributed mode must reuse the local job/recording contract and capture pool failures as metadata instead of repairing the host installation.
- Surrogate-assisted generation, refreshed runtime state, cumulative archive thinking, and richer neural modeling come from the shorten experiment lineage, now reshaped around the current rawData-first API.
- The active HFSS task and adapter style descend from earlier huangzetao/fanyufei task files, but simulator files, `_com.py` adapters, workflows, rawData names, and objectives are replaceable task inputs.
- GPSAF supplies the optimizer's surrogate-assistance framing. The implementation keeps the GPSAF-shaped alpha/beta/gamma pressure controls while using pymoo GA/NSGA-III mechanics for candidate generation and diversity.

## Functionalities
- `project.optimize` owns the optimization loop, NSGA-III multi-objective candidate generation, GPSAF-style history warm start, optional surrogate-assisted candidate selection, and lightweight optimization-level metadata handoff.
- `project.evaluate_manager` converts normalized individuals into job folders, asks
  `job_template.api` to fresh-load and materialize assigned parameter snapshots,
  passes run/generation context, runs local jobs or submits HTCondor jobs, reads
  workflow-owned individual metadata, records failures, and returns in-memory costs
  to the optimizer.
- `project.job_template` owns task-specific files: parameter definitions, workflow, rawData contract, simulator stand-ins or adapters, rawData-to-cost calculation, and optional rawData importance weights for surrogate training.
- The framework does not fix a default optimization task, simulator model filename, rawData names, or objective names. Those are task-specific and come from the active files in `project/job_template/`, especially `workflow.py`, `calc_cost.py`, and `parameters_constraints.py`.
- Active workflow adapters live in `project/job_template` so prepared jobs are self-contained. `project/com_lib` is only a staging/reference area for adapter source/reference copies such as `hfss_com.py` and retained synthetic `test_com.py`; reusable fixes from an active adapter are synchronized back after task-only assumptions are excluded.
- `project.recorded_data` stores real evaluation records, raw variables once per individual, rawData files, compact rawData metadata, workflow-owned timing, run/generation identifiers, job metadata, and job names; it does not store cost, normalized variables, repeated variable echoes, or submit-side `created_at` as durable source data.
- `project.surrogate` trains a conditional INR deep ensemble from `recorded_data`, predicts rawData arrays, converts predictions to costs through `job_template.api`, audits historical prediction error, returns ensemble member min/max cost intervals, and writes per-generation checkpoints plus member artifacts.
- `project.tools` remains optional and user-launched; generic tools stay at its root and simulator-specific tools live under `project.tools.specific.<software>`. Core runtime and generic tests must not depend on tools. System-environment and HTCondor-pool configuration belong in `admin_tool/`.
- `project.config` is a package: `key.py` holds routine generic settings, `all.py` holds the complete generic surface, and `specific/` contains simulator-specific extensions.
- `project.test` verifies generic framework contracts only: local closed-loop orchestration through task doubles, rawData contracts, failure isolation, dynamic cost/normalization behavior, surrogate behavior, and generic tool compatibility. Current-task tests belong in ignored `temp/` now and in the workspace after package separation.
- `dev_doc` owns project documentation guidance, including current architecture
  contracts, selective blueprint reading, terminology, historical lineage,
  manual and automatic toDo handoffs, obsolete archives, and append-only change
  records. Root-level toDos require an explicit prompt trigger; `toDo/auto/` items
  are only opportunistic during already in-scope work and have stale-document rules.

## I/O Format
- User-edited inputs are primarily `project/config/key.py`, the active software settings under `project/config/specific/`, and task-specific files in `project/job_template/` such as `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, simulator model files, and copied active adapters.
- Optimizer input and output use normalized float tuples shaped as `population[individual][variable]`.
- Evaluator input is a generation of normalized float tuples; evaluator output is cost tuples shaped as `population[individual][objective_cost]`.
- Job folders contain copied runtime files, a `parameters_constraints.py` snapshot
  with assigned normalized/raw values, submit-side `metadata.json`/`metaData.json`,
  workflow-owned `individual_metadata.json`, and flat `rawData/*.npz` files. Jobs do
  not contain or save `cost.json`.
- Recorded history is represented by append-only individual metadata in `project/recorded_data/indMeta.jsonl`, optimization-level metadata in `project/recorded_data/optMeta/optMeta.jsonl`, and a single zip-based `project/recorded_data/rawData.npz` archive whose members are shaped like `job_name/file.npz`.
- Public cross-core-module calls go through `api.py` files only: `optimize/api.py`, `evaluate_manager/api.py`, `job_template/api.py`, `recorded_data/api.py`, and `surrogate/api.py`.

## Core Invariants
- Expensive evaluations produce rawData and metadata, not authoritative costs.
- Cost and normalized historical variables are derived from stored raw evidence and the current task definition.
- The core framework remains simulator-agnostic; adding Maxwell, TwinBuilder, custom Python, or multi-software workflows should happen through task files and adapters rather than core rewrites.
- Complex per-individual workflows are allowed as long as their output contract is flat rawData plus metadata.
- Past completed rawData may be reused after controlled task edits; users must remove or ignore old history when new task semantics make it misleading.
- Individual failures, timeouts, submit failures, invalid rawData, and record failures should degrade to inspectable metadata and `inf` costs instead of crashing a whole generation.
- Local mode must stay usable without HTCondor or real simulator software for default tests.

## Non-Obvious Techniques
- Cost is deliberately not a persisted evaluation artifact. Any module that needs cost asks `recorded_data` or `job_template` to compute it from rawData using the current `calc_cost.py`.
- Normalized historical variables are also derived data. `recorded_data` stores raw variables and uses current `job_template` parameter ranges to calculate normalized variables on demand.
- `job_static_hash` captures copied static job inputs. For the assigned parameter
  snapshot it hashes only name, ranges, unit, and constraints, so mid-run definition
  changes are visible without making every individual unique by hash.
- rawData directories must stay flat. Each `.npz` is one rawData unit and must include schema-versioned metadata.
- Workflow lifecycle time is owned by the individual job: `workflow.py` writes `started_at` and `ended_at` into `individual_metadata.json`, and `evaluate_manager` only reads and forwards it.
- Variable values are stored once as individual `raw_variables`; repeated variable payloads are scrubbed from rawData metadata and job metadata before appending `indMeta.jsonl`.
- `evaluate_manager` isolates per-individual failures. Prepare, run, timeout, and record failures should become metadata and `inf` costs rather than crashing the whole generation.
- `surrogate` predicts rawData first, then derives costs through the same rawData-to-cost path used for real samples. Its INR training uses target scaling, task-owned rawData importance weights, ensemble/member spread, and relative-loss weighting so small objective values and objective-relevant windows still matter.
- GPSAF surrogate pressure is controlled by `OPTIMIZE_SURROGATE_ALPHA`, `OPTIMIZE_SURROGATE_BETA`, and `OPTIMIZE_SURROGATE_GAMMA`; `OPTIMIZE_SURROGATE_EXPLORATION_FRACTION` reserves real-evaluation slots that bypass surrogate selection to reduce branch starvation.
- Multi-objective optimizer diagnostics include `pymoo.NSGA3`, requested population size, reference-direction method, partition count, and reference-direction count.
- HTCondor distributed evaluation uses the same job folder and recording contract as local mode. Submit failures, stale daemons, credential errors, or broken pool topology are captured as job metadata; the project does not try to repair the installed HTCondor environment.
- Windows HTCondor execution must target slot-user jobs with `run_as_owner = False`
  and `load_profile = True`. The deployment pool consists of many office/personal
  workstations with different interactive owners, and any workstation may submit or
  execute jobs, so owner execution is not a deployable fix path.
- Portability is a core contract. Source code, config defaults, launchers, and tools must not assume fixed absolute install paths, and must not require users to create new system environment variables before first use. They may rely on repository-derived paths, explicit parameters, standard install discovery, and environment variables already provided by installed tools such as Conda, Ansys, or HTCondor.

## Mutability Profile
- `project/job_template/parameters_constraints.py`, `workflow.py`, `calc_cost.py`, simulator model files, and active adapter files in `job_template/` are intentionally highly mutable between optimization tasks.
- `project/config/key.py` and the active files under `project/config/specific/` are mutable at campaign setup time and during tuning; `project/config/all.py` carries the full grouped generic defaults.
- `project/optimize`, `project/evaluate_manager`, `project/recorded_data`, and `project/surrogate` should change more carefully because they define shared contracts.
- Runtime files such as `project/jobs/`, `project/recorded_data/indMeta.jsonl`, `project/recorded_data/rawData.npz`, `project/recorded_data/optMeta/`, and surrogate checkpoint directories are generated artifacts.
- Root `temp/` is a retained scratch directory: keep `temp/.gitkeep` tracked and ignore other contents.
- `dev_doc/architecture/`, `dev_doc/blueprints/`, `dev_doc/terminology.md`,
  `dev_doc/toDo/`, and `dev_doc/change_records/` are current documentation
  artifacts; `dev_doc/obsolete/` is archival. Manual toDos live directly under
  `toDo/`; automatic toDos live under `toDo/auto/` and use either automatic
  time/configured-condition obsoletion or an explicitly manual obsolete policy.
  User-defined conditions are optional and absent by default.
- Update architecture and blueprint files when module responsibilities, contracts, I/O, persistence behavior, execution topology, historical lineage, or non-obvious techniques change.
- Add one `dev_doc/change_records/` file after each code change to explain what changed and why.
- Update `dev_doc/terminology.md` when a change corrects a concept or introduces a non-obvious name.
