# C4 package components

## Foundation

- `workspace.context`, `workspace.manifest`, `workspace.init`, `workspace.check`:
  resolve, create, and diagnose user-owned workspaces without implicit package
  writes.
- `config`: immutable effective values with package < workspace < temporary override
  precedence and validation.
- `task_loader`: fresh compile/execute from either selected source root in temporary module namespaces, including
  workspace-local helper packages without lasting `sys.path` or `sys.modules`
  pollution.
- `_resources`: generic workspace template, reusable adapter references, invariant
  execute-side worker lifecycle support, and installed documentation resources.

## Task interpretation

- `job_template.api`: canonical parameter queries, submit-side objective/cost
  loading, assignment materialization, normalization, dynamic cost, and task
  validation.
- `parameters_constraints_class`: canonical submit-side `Parameter` semantics.
- `rawdata_contract`: schema-versioned `.npz` validation, rawData views, and reusable
  axis-curve reduction.
- `rawdata_template`: exact direct-basename/main-key field selectors, immutable
  schema templates/signatures, structured sample reconstruction, and rejection of
  selector, shape, dtype, axis, unit, or metadata drift.
- `rawdata_projector`: per-draw/per-candidate validation and frozen
  `CostInterpreter` projection into joint objective samples, validity masks, and
  bounded typed diagnostics. It preserves finite task fallback values and never
  records predicted rawData.
- `cost_misc`: neutral multi-sample/defined/custom-callback cost calculation,
  slow-tail algebraic physical-to-`[0, 1]` objective mapping, result-width
  validation,
  worst-curve aggregation, objective-name derivation, constraint handling, and
  failure fallback.

## Evaluation

- `evaluate_manager.api`: backend selection, population ordering, local worker pool,
  per-individual failure isolation, recording, and cost return.
- `fast_runner`, `fast_resources`, `process_control`: reusable spawn workers,
  memory-backed task-kernel execution, bounded host-capacity concurrency, ephemeral
  scratch, hard timeout/crash replacement, and shared process-tree termination.
- `job_files`: task copying, self-contained assigned parameter snapshots, job static
  hashes, package worker-lifecycle copying, top-level AEDT runtime-artifact
  exclusion, and preparation provenance.
- `local_runner`: direct workflow subprocess, timeout/process cleanup, rawData
  validation, psutil process-tree resource measurement, and shared metadata
  finalization.
- `resource_calibration`: backend-neutral smoke/preceding-generation observation
  selection, upper-tail trimming, bootstrap scaling, and concrete per-job estimates
  shared by local and HTCondor policy.
- `local_resources`: submit-host CPU/memory/disk discovery, adaptive worker-count
  planning, process-tree monitoring, and job-directory disk measurement.
- `condor_runner`: direct `workflow.py` submit, input selection, explicit
  `rawData.zip` transport, flat archive restoration, queue polling, collection,
  `condor.log` execution-clock and execute-site parsing, source-labeled timeout
  machine fallback, bounded removal, ClassAd diagnostics, and pool matchmaking
  analysis.
- `resource_requests`, `resource_retries`, `time_limits`: workspace-local adaptive
  policy separated from backend orchestration. Resource requests format
  HTCondor-specific values over the shared calibration result; retry and time-limit
  policies remain backend-specific.
- `job_result`, `types`: common result shape and metadata utilities, including
  explicit file-backed or memory-backed rawData and an optional real job path.
- `finalizer`: the single backend-neutral rawData ownership, current-cost,
  `JobResult` finalization, and reliable recorder-handoff boundary.
- `task_snapshot`: generation-scoped complete `submit/` plus `job_template/`
  capture, separate interpretation/evaluation/optimization fingerprints, full snapshot identity, and stable
  parameter/objective-shape validation.

## Durable evidence and optimization
- `recorded_data.session`: one explicit campaign-owned hot catalog, bounded
  backpressured writer, current derived history, recorder counters, and OS
  campaign-lock lifetime.
- `recorded_data.rawdata`, `records`, `segment_store`: owned no-pickle NPZ
  conversion, immutable standard-ZIP micro-batch segments, candidate-scoped
  metadata/evidence, atomic same-directory publication, and tolerant discovery.
- `recorded_data.query`: partial history over finalized segments only; temporary
  and unrelated files are outside its surface. Its cost-view snapshot freezes names
  once and streams every segment through one open ZIP for structural checks, NPZ
  decode/schema validation, and candidate diagnostics.
- `optimize.strategy`, `components`, `state`: common campaign result/context and
  real-evaluation boundary, snapshotted workspace-strategy loading, public
  composition factories, and one active semantic strategy pointer with retained
  namespaces. Private `optimize.gpsaf` owns GPSAF assistance/phases/records and
  private `optimize.pymoo` owns the thin lazy GA/NSGA-III backend adapter. The
  package has no complete-method selector or registry. Each selected component
  carries a private frozen settings snapshot built from explicit keyword-only
  factory arguments; runtime adapters receive that snapshot rather than consulting
  ambient algorithm configuration.
- `config`: one declarative core-setting schema owns defaults, validation kind,
  reload policy, and path policy for genuine campaign/framework settings. It does
  not register search, GPSAF, or surrogate implementation parameters.
- `optimize.posterior_assisted`, `optimize.qnehvi.acquisition`: the independent
  opt-in
  generation orchestrator and acquisition-family component. The strategy owns the
  private-pymoo candidate pool, fixed real Pareto baseline, typed readiness,
  streamed projection, explicit real exploration quota, fallback, and common real
  evaluator handoff. The acquisition owns support policy and discrete greedy
  multi-start batch selection.
- `optimize.qnehvi.backend`: a discrete-only adapter that
  converts fixed minimization costs and aligned joint objective draws into a
  BoTorch sample-backed ensemble, delegates qLogNEHVI hypervolume/partitioning
  numerics to BoTorch, and returns compact acquisition diagnostics. Its private
  numerical module loads only on an explicit call and does not orchestrate a
  generation, propose a pool, or evaluate/record candidates.
- `surrogate.posterior`: lightweight backend-neutral protocols and diagnostics for
  persistent joint function samplers, streamed draw/chunk projection, honest
  finite-versus-continuous support, and semantic-capability identity. It imports no
  optional numerical backend.
- `surrogate.exploitation`: a separate runtime-checkable performance, posterior
  calibration, transferability, observation-noise, and applicability readiness
  boundary. It deliberately exposes no variance/loss shortcut.
- `surrogate`: lightweight public component/API over that protocol and separate
  private `surrogate.conditional_inr` and experimental
  `surrogate.hierarchical_cae` models, strategy/component-keyed schedules and
  state, rawData prediction, dynamic cost conversion, and atomic recoverable
  checkpoints scoped to the active strategy. `surrogate.quality` owns only the
  JSON-safe assessment/policy protocol and generic weights/labels; task diagnostic
  names and thresholds remain workspace/benchmark declarations.
  The explicit `conditional_inr_posterior()` adapter fixes one ensemble member per
  draw, reconstructs every selected member on the full stored grid, and reports
  nominal and effective finite support without changing `conditional_inr()`.
  `hierarchical_cae()` shares field codecs across independent parameter-predictor
  members and exposes an uncalibrated applicability score with zero observation
  noise. Its initial full-grid candidate failed Gate 0 v5. A v6/v7 experimental
  continuation adds an all-axis field-local coordinate readout and viewer adapter,
  while leaving full-grid prediction authoritative and production-strategy
  integration absent.
- `tools`, `_resources`: reusable `tools.cost_viewer` package with left-axis
  objective/average costs and a right-axis all-individual versus
  current-generation hypervolume interval, shaded and bounded by thin translucent
  polylines at generation plotting positions; integrated
  time/failure/machine/error view;
  grouped `view all` orchestration; history/task utilities; and read-only
  adapter/template/doc resources. The cost view isolates and reports unusable
  history rows, omits unavailable optional annotations, and continues whenever at
  least one finite, consistent objective row remains. Its history, analysis,
  reporting, plotting, style, and orchestration modules expose a stable non-GUI
  surface; its one command-local task interpreter freezes parameters and cost code
  while the history snapshot is processed. Its streamed progress counts decoded
  candidates, defers the exact total until completion without reopening segments,
  and uses the frozen segment position only for terminal-bar fill; cumulative HV
  retains only the nondominated front; `tools.view_cost` remains a compatibility
  facade.
  `tools.surrogate_viewer` is a lazy, optional
  inspection leaf for GUI prediction, real-result comparison, metadata reports,
  and GUI/terminal cross-generation error audits; its backend owns yadof
  checkpoint/rawData adaptation while its UI and reporting layer never write
  workspace data. The time view colors points by execute-side machine
  metadata and uses directly labeled horizontal bands plus marker rings for error
  types. Software-specific task commands live below an explicit software namespace,
  such as `yadof task hfss`, so future adapters do not collide on generic action
  names.
  The `chrono_com.py` adapter resource owns the isolated Project Chrono
  JSON/NPZ launch/validation boundary; task-owned `chrono_worker.py` owns mechanics.
- `cli`, `run_command`: modular installed command routing, packaged-document access,
  and normal campaign orchestration.

## Dependency direction

The campaign engine consumes public evaluation/history/task contracts and invokes
one workspace-owned strategy. GPSAF consumes only the narrow injected search and
surrogate seams; its private package and the private pymoo/conditional-INR packages
keep concrete implementation imports below the public component layer. Pymoo
algorithms and the Torch runtime load only on selection.
Posterior-capable consumers use `surrogate.posterior`, `surrogate.exploitation`,
and the independent `job_template` projector; concrete surrogate implementations
implement the protocols without being imported by optimization. The qLogNEHVI
backend remains only the numeric sample consumer. `posterior_assisted` is the sole
generation orchestrator for that path. The current GPSAF strategy does not consume
either capability, so its conditional-INR semantic identity and checkpoint
signature remain unchanged.
The experimental hierarchical CAE implements the posterior protocol and a typed
coordinate/applicability capability directly, but its failed v5 development gate
prevents downstream calibration or acquisition from treating it as an accepted
production backend. Calibration plumbing may target one preregistered exact
experimental state; only a separately performance-accepted and calibrated state may
later control exploitation.
`evaluate_manager` consumes task and recorded-data APIs. `recorded_data` and
`surrogate` may ask `job_template` to reinterpret evidence. Core runtime modules
never import `tools`. Workspace workflows may import files copied beside them and
external installed dependencies, but distributed workflows must not import yadof.

Stable cross-module calls use public `api.py` or package `__init__` exports. Stateful
APIs accept a workspace; no module derives user-data paths from package `__file__`.
Task workflow/cost modules contain task-variable callbacks and definitions only:
they invoke copied `worker_misc` or installed `yadof.job_template` helpers for
invariant behavior. The viewer's package-internal checkpoint/rawData dependencies
remain isolated below its backend and never leak into UI modules or core runtime.
