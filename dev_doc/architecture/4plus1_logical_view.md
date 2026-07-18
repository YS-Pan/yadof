# 4+1 Logical View

## Core Concepts
- Package/local foundation: the installable `yadof` distribution metadata, version,
  console interface, and read-only documentation/versioned-template resources under
  `src/yadof/`, plus workspace job composition and local execution. It is distinct
  from the transitional `project/` runtime and writes only into an explicitly
  selected writable task workspace.
- Workspace context: one immutable set of absolute paths rooted at the explicitly
  selected writable task directory. The current directory is only the default root;
  package `__file__` never selects a user-data path.
- Effective config: immutable package defaults merged with uppercase values from
  workspace `config.py` and optional in-memory overrides, together with the source
  of every final value.
- Task module snapshot: one freshly compiled `parameters_constraints.py`,
  `calc_cost.py`, or other requested submit-side module plus its local imports,
  isolated from all other workspaces and removed from global import caches after use.
- Workspace marker: portable `.yadof/workspace.json` provenance containing the
  workspace schema, creating yadof version, template name/version, and rawData schema.
  Its existence means init completed; it contains no absolute installation path.
- Workspace template: a versioned bundled manifest and generic pure-Python starter
  copied into user ownership. It is an initialization input, not a live source that
  later rewrites user files.
- Workspace check: a read-only diagnostic report over structure, provenance,
  config/task contracts, static rawData, and selected backend prerequisites. It is
  not an evaluator, installer, upgrader, or repair tool.
- Optimization variable: normalized in `optimize`, raw/unnormalized in `recorded_data`.
- rawData: one or more `.npz` files produced by a workflow.
- Cost: dynamic objective value calculated from rawData by current `job_template/calc_cost.py`. Objective names, count, physical meaning, and numeric scale are task-specific.
- Job: one real evaluation sandbox under the selected workspace, composed from
  package-reserved worker support plus non-conflicting workspace task payload.
- Standalone smoke test: an explicit no-timeout local run of exactly one midpoint
  individual. The unchanged generic starter is safe by default; edited or external
  tasks require `--real-task` because execution may launch expensive software.
- Individual metadata: job-local lifecycle JSON written by `workflow.py`, including the evaluation start/end times when the workflow reaches those points.
- Per-job execution limit: the HTCondor-side `allowed_execute_duration` applied to one normal distributed individual. It is separate from the submit-side whole-generation wait budget; smoke jobs have no such limit.
- Yadof resource retry: a fresh Condor submission of the same prepared individual after a standard memory- or disk-exhaustion hold. Only the exhausted request is doubled, and memory/disk retry budgets are independent.
- Checkpoint: recoverable surrogate state. Surrogate checkpoints include a JSON summary plus conditional-INR member artifacts; optimizer generation metadata is recorded under `recorded_data/optMeta/` and is not treated as a checkpoint.

## Logical Modules
- `yadof` package foundation: repository-independent help/version/document lookup,
  safe init/check, explicit workspace/config/task-loading APIs, and installed
  parameter/rawData/cost-helper contracts.
- `yadof.evaluate_manager`: package-era job preparation, local subprocess execution,
  rawData validation, dynamic cost return, and local failure/timeout isolation.
  Recording remains a later workspace migration.
- `optimize`: uses GA for single-objective runs and NSGA-III reference-direction survival for multi-objective candidate generation, real evaluations, and optional surrogate-predicted candidate screening.
- `evaluate_manager`: turns candidate rows into job execution and records results.
- `job_template`: defines the current task and interprets rawData.
- `recorded_data`: stores real raw evidence and serves derived historical views.
- `surrogate`: trains a conditional INR deep ensemble over rawData slots, predicts rawData, and converts it to cost through the same cost path.

## Boundary Rules
- New installed-package code uses `yadof.*` or package-relative imports and does not
  provide a `project.*` alias. Until migrated, runtime code continues to use the
  current source contract under `project/`.
- Every packaged API that reads task or runtime state receives a workspace/context
  explicitly. Config and task loading cannot fall back to a package-relative or
  current `project/` path.
- Package worker filenames are reserved inputs. Composition fails before creating a
  job when the workspace owns a case-insensitively matching `worker_misc.py` or
  `yadof_worker_config.json`; no precedence or overwrite fallback exists.
- Standalone smoke safety is based on exact bundled task content, not simulator-name
  guesses. Any edited or additional task file requires explicit `--real-task` intent.
- Workspace task loading never permanently changes `sys.path` and never reuses a
  local module cache across calls. Package defaults are immutable, and temporary
  overrides never rewrite workspace `config.py`.
- Init never overwrites a template target, resets a complete workspace, repairs a
  missing user file, or deletes unrelated/history content. A marker is not visible
  until all required files have published successfully.
- Check may import the parameter and cost-policy modules because importability is
  part of their contract, but it only parses workflow syntax and never executes the
  workflow. Backend discovery is read-only and missing administrator prerequisites
  are reported rather than installed or repaired.
- Internal files may call another core module only through that module's `api.py`.
- Internal files should not call their own `api.py` just to reach another module.
- `project.config.all` is the generic runtime shared-settings dependency; `project.config.key` is the short generic override file, and simulator settings live under `project.config.specific`.
- `tools` and `test` have looser access rules but should not become runtime dependencies.

## Derived Data Rules
- Stored: job name, raw variables once per individual, archived rawData, compact rawData metadata, workflow-owned `started_at`/`ended_at`, run/generation identifiers, job metadata, status, and optimization-level metadata.
- Derived on demand: normalized variables, cost, surrogate errors, Pareto summaries.
- Not stored as source truth: `cost.json`, normalized historical variables, repeated variable payloads inside every rawData metadata item, surrogate prediction results, and submit-side `created_at`.

## Logical Invariants
- `workflow.py` never computes final cost.
- Local runners reject and remove a workflow-created `cost.json`; a successful job
  contains rawData and metadata only, and the submit process calculates cost from
  the current workspace policy.
- `recorded_data` never trusts old saved cost when returning history.
- `surrogate` never bypasses rawData by learning only `variables -> cost`.
- `surrogate` may learn normalized/scaled rawData internals, but public predictions are reconstructed rawData passed to `job_template.api` for cost.
- `surrogate` historical error audits must use real model predictions rather than substituting true historical costs.
- Surrogate prediction must use an already-trained state. Training is scheduled after real job submission, and prediction must not call 	rain() implicitly.
- Exact-neighbor snapping or near-training-sample replacement is not part of the current surrogate contract and must not be added unless explicitly requested by the user.
- Task-owned rawData importance weights may emphasize objective-relevant windows, but surrogate training must still retain full-field rawData coverage. For very large rawData fields, stochastic query minibatches may limit per-step backpropagation work while resampling from the full query table and leaving full-field prediction/reconstruction intact.
- Current HFSS far-field rawData is stored as full-matrix data by default; objective cost calculation may select phi/theta/frequency windows from that matrix, but it must not make the workflow export only those windows unless a task intentionally requests trace diagnostics.
- Failed records can exist and be inspected, but default optimization history uses completed records.
- `evaluate_manager` may add runner diagnostics, but workflow-owned timing is read from the job folder before recording.
- A Condor hold with code 46 or 47 is a timeout result. The submit side records it and removes the held job so the timed-out individual is not retried.
- Condor submit files carry one concrete memory/disk request and no native resource-retry ladder. Yadof alone changes resource requests: generation calibration selects the initial request, while `resource_retries.py` handles bounded per-individual memory/disk doublings after resource holds.
- Current HFSS cost shaping follows the old huangzetao/fanyufei tanh-style soft objective mapping: goal-like values approach 0 and worst-threshold values approach 1.
- The installed `Parameter`, rawData contract, and cost helpers are framework code;
  workspace `job_template/` owns only task definitions, workflow, cost policy,
  active adapters, and arbitrary simulator/custom assets.
- A prepared job records `yadof_version`, workspace root/marker identity,
  `job_static_hash`, and a source-annotated summary limited to local evaluation mode,
  timeout, and worker count. Full package config source is never copied into it.
