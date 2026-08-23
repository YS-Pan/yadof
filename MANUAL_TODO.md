# Manual TODO: repeatable yadof optimize/surrogate benchmarks

Status: `MANUAL / NOT STARTED`

Activation rule: execute this TODO only after the user explicitly asks to build or
run the benchmark automation. Do not treat merely reading this file, changing
yadof, or noticing a new workspace as authorization to start an optimization.

Location boundary: every automation source file and generated benchmark artifact
must stay under the outer workspace
`D:\project\20260414 yadof\20260822 modular\benchmark_automation`. Do not place the
runner in `20260822 yadof`, and do not modify the installed package under `.venv`.

## Goal

Build one repeatable, resumable command-line runner that can prepare isolated
copies of frozen benchmark inputs, run every selected optimization arm, and
collect machine-readable evidence for algorithm debugging and comparison.

The runner must support two distinct purposes:

1. **Structural regression**: after yadof code or workspace structure changes,
   prove that real-only optimization, GPSAF, conditional-INR training, checkpoint
   publication, and result inspection still run end to end. Checkpoint recovery is
   yadof code/integration-test scope and is deliberately outside this benchmark.
2. **Algorithm performance**: run optimize/surrogate algorithms under a frozen,
   paired input protocol with equal real-evaluation budgets and repeated seeds,
   then publish the raw and descriptive results needed by a human or AI analyst.

These purposes share preparation and evidence infrastructure but not acceptance
semantics. A successful short canary does not establish that an algorithm is
better. The runner never declares which algorithm is better and never turns
performance metrics into an algorithm pass/fail verdict; that interpretation is
performed later by a human or AI reading the evidence.

## Established background

- The current package is yadof `0.4.0`. Complete strategy composition now belongs
  to each workspace's `submit/optimization.py`; yadof exposes small components such
  as `real_search(...)`, `gpsaf(...)`, `pymoo_ga()`, `pymoo_nsga3()`, and
  `conditional_inr()`.
- The three user-confirmed benchmark cases are:
  - `20260807 saw`: physical ngspice/SAW case and the main dense-curve prediction
    and ranking case.
  - `20260811 chrono trebuchet flexible`: physical Project Chrono case with
    normalized release kinematics, total time, stress history, event/failure
    behavior, and exact moving-mass calculation outside the surrogate.
  - `20260816 surrogate test_com`: fast synthetic, high-query-count regression and
    stress case; useful for automation and resource checks but not sufficient by
    itself for production-physics acceptance.
- Before the latest release-marker cleanup, all three migrated workspaces passed
  `yadof check` and real-task smoke, their recorded evidence was interpretable,
  and none had a compatible trained 0.4.0 checkpoint. Old checkpoint artifacts
  were intentionally not migrated.
- Existing `BENCHMARK_READINESS.md` is a historical pre-benchmark snapshot. Its
  `template-version-2` wording predates the later removal of incidental workspace
  version markers and must not be copied into the new runner or documentation.
- The real-only/field-balanced surrogate policy is the current baseline: only real
  recorded evidence or bootstrap draws are trained, modeled fields receive equal
  macro weight, and old mixup/relative-loss/importance behavior must not be
  reintroduced by the benchmark harness.
- `soft_cost()` now uses the slow-tail algebraic sigmoid. Benchmark reports must
  compare current recalculated dimensionless costs, not stale persisted costs or
  physical values with mixed units.

## Known prerequisite issue discovered during planning

On 2026-08-22, read-only `yadof check` attempts from the active Codex execution
identity failed before semantic validation with `WinError 5` while opening
`.yadof/workspace.json` and `config.py` in all three benchmark workspaces. Direct
access also showed that the directories/files were created under mixed Windows
identities. This is an ACL/execution-identity problem, not evidence of an optimize
or surrogate failure.

Before implementing or running the matrix:

- choose the one Windows identity that will own and execute benchmark runs;
- make fresh, readable baseline copies under that identity rather than weakening
  global ACLs or taking ownership of unrelated directories;
- regenerate current workspace markers through `yadof init` when needed; do not
  hand-invent or silently patch `.yadof/workspace.json`;
- copy and validate task sources and any deliberately retained recorded-data
  snapshot;
- rerun `yadof check` with the exact interpreter and identity the automation will
  use;
- update or supersede `BENCHMARK_READINESS.md` only after the current package can
  actually read all three refreshed baselines.

Do not bury this prerequisite in the runner as an automatic ACL mutation. The
runner should diagnose access and stop with an actionable message.

## Fixed design decisions

1. The runner reads only refreshed, frozen task baselines maintained below
   `benchmark_automation/baselines/<case>/<baseline-id>/workspace/`. The original
   sibling workspaces are Phase 0 import sources, not live benchmark inputs. A
   baseline ID combines a creation date and content-fingerprint prefix, is selected
   explicitly by `benchmark.toml`, and is never overwritten; refreshing a case
   creates a new baseline ID. Each baseline contains a validated current-format
   task definition and explicitly declared task-owned assets, but no mutable jobs,
   logs, optimization state, checkpoints, or measured history.
2. Optional warm-start evidence lives separately below
   `benchmark_automation/history_snapshots/`. Every snapshot has its own immutable
   identity, provenance, row count, and content fingerprint. Cold-start arms use no
   snapshot. Every experimental arm and seed runs in its own newly initialized
   workspace populated from one task baseline and, when selected, the same frozen
   history snapshot.
3. Never switch real-only and surrogate-assisted strategies inside one campaign.
   They must not share mutable history, active optimization state, checkpoints,
   jobs, logs, or a campaign lock.
4. A smoke test runs only in a disposable smoke workspace. Smoke evidence must not
   silently enter a measured arm. The `preflight` command itself remains static and
   never starts a simulator.
5. Runs are sequential by default to avoid shared-resource contention and respect
   one active campaign per workspace. Arm order is recorded but is not used for an
   optimization wall-time comparison.
6. Every `yadof run` command supplies an explicit generation count, population,
   seed, mode, and `--no-smoke-test`; the runner must never inherit the CLI's
   50-generation default.
7. Baseline and history fingerprints cover only declared immutable inputs. Runtime
   paths such as jobs, logs, locks, checkpoints, and scratch are excluded. The
   selected input fingerprints are checked before and after preparation/execution;
   a benchmark cell is invalid if its frozen inputs changed.
8. Destructive `history clear`, recursive deletion of a baseline/source workspace,
   force push, package installation, and yadof source edits are outside this runner.
9. A failed command or evaluation is retained as validity evidence. Failure counts,
   missing generations, and all-infinite results are not algorithm-performance
   metrics and the runner does not infer whether they came from the workspace or
   the algorithm. It must nevertheless expose them so incomplete evidence is never
   mistaken for a valid comparison. Resume is allowed only across completed
   command/cell boundaries. A generation is complete only after the yadof command
   returns successfully and its expected complete generation metadata is present.
   If optimization stops during a generation, seal that workspace and cell as
   `incomplete`; never rerun the same generation in that measured workspace. A
   retry creates a new cell workspace and records its relationship to the failed
   cell. Non-optimization inspection commands such as check, summary, audit,
   collect, and report may append a new attempt without mutating measured evidence.
10. When a cell fails, stop its dependent steps. Structural suites stop the whole
    selected matrix by default. Performance suites continue other independent
    case/arm/seed cells by default, preserve all partial evidence, and finish with
    a nonzero overall status. `--fail-fast` may stop a performance matrix
    immediately. Incomplete performance cells are listed separately and excluded
    from primary paired descriptive aggregates while their raw evidence remains
    available.
11. Performance reports contain raw per-seed results and descriptive aggregates,
    not acceptance thresholds, significance claims, rankings, or a declaration of
    which arm is better.
12. Reusable single-workspace observation belongs in yadof tools. The runner should
    consume public tool APIs and machine-readable tool output such as `view cost`
    functionality and `view surrogate summary/audit --format json`. Cross-case,
    cross-arm, and cross-seed experiment assembly remains benchmark responsibility.
    When a generally useful measurement is missing, record a tool gap and open a
    separate future yadof-tools task after the benchmark exposes the concrete need;
    do not implement private-layout scraping or expand this TODO to predict every
    future tool change.

## Target directory layout

The implementation should remain small and use the standard library plus the
already installed yadof environment where practical.

```text
benchmark_automation/
  MANUAL_TODO.md                 this handoff
  README.md                      exact user commands and interpretation guide
  benchmark.toml                 cases, suites, arms, seeds, budgets, metrics
  benchmark.py                   one CLI entry point
  baselines/
    <case>/<baseline-id>/
      workspace/                 frozen current-format task baseline
  history_snapshots/
    <case>/<snapshot-id>/        optional frozen warm-start evidence
  strategy_templates/
    real_search.py               real-only pymoo GA/NSGA-III composition
    gpsaf_conditional_inr.py     GPSAF + the same search + conditional INR
  tests/
    ...                          runner unit/integration tests
  runs/                          generated; one identity-stable directory per run
```

A generated invocation should resemble:

```text
runs/<run-id>/
  run_spec.json                  immutable resolved inputs and matrix identity
  run_state.json                 atomically updated execution/collection state
  matrix.json
  report.md
  report.json
  <case>/<arm>/seed-<seed>/
    workspace/
    commands/
      001-check/
        attempt-001/
          metadata.json
          stdout.log
          stderr.log
      002-run/
        attempt-001/
          metadata.json
          stdout.log
          stderr.log
      003-surrogate-summary/
        attempt-001/
          metadata.json
          stdout.log
          stderr.log
      004-surrogate-audit/
        attempt-001/
          metadata.json
          stdout.log
          stderr.log
    metrics.json
```

The run directory is not globally immutable: workspaces evolve while running,
`run_state.json` advances atomically, and derived metrics/reports may be regenerated.
`run_spec.json` becomes immutable before execution. Command-attempt directories are
append-only, and a failed attempt is never overwritten by resume. `metadata.json`
stores the command, timestamps, exit state, log paths, and log hashes; potentially
large stdout/stderr streams remain in their own UTF-8-safe log files. A completed
run may be sealed against further execution while still allowing deterministic
collection/report regeneration.

`run_spec.json` must record at least the resolved config, suite, selected matrix,
creation time, host identity, Python executable/version, installed yadof
version/import origin and distribution fingerprint when obtainable, Torch/CUDA/device
facts, baseline/history/strategy-template fingerprints, and planned command lines.
The yadof checkout HEAD and dirty state are optional secondary provenance; they do
not substitute for the installed distribution identity. Runtime timestamps, exit
states, and actual attempts belong in `run_state.json` and the append-only command
records. Do not store secrets or dump the full environment.

## Configuration and arm contract

Use TOML so Python 3.13 can read the configuration through `tomllib` without a new
parser dependency. Every relative path is resolved from the directory containing
`benchmark.toml`, never from the caller's current directory. The absolute Windows
path at the top of this TODO is a current-machine boundary, not a path to hard-code
inside the runner.

Each case must declare:

- stable case ID and frozen baseline path;
- explicit task-input include paths covering `config.py`, complete `submit/` and
  `job_template/` roots, and every required task-owned simulator/project asset;
- execution mode;
- structural and performance population/budget settings;
- history policy (`empty` or an explicitly fingerprinted frozen snapshot ID);
- expected objective count and important rawData shapes;
- resource prerequisites and an optional representative expensive-generation
  duration used only to contextualize surrogate training time.

Each arm must declare an exact strategy template and configuration overrides.
The initial paired arms are:

- `real-search`: `real_search(search=by_objective_count(...))`;
- `gpsaf-conditional-inr`:
  `gpsaf(search=by_objective_count(...), surrogate=conditional_inr())`.

Both arms must use the same pymoo backend, population, parameter definitions,
objective definitions, real evaluator, seed list, and real-evaluation budget for a
given case. GPSAF-only settings such as alpha/beta and conditional-INR training
settings are recorded as treatment parameters, not allowed to change unnoticed
between repetitions. A paired cell means the same case, seed, task fingerprint,
starting-evidence fingerprint, and initial population. It does not claim that two
different algorithms consume identical random-number streams after they diverge.

Write the selected strategy file into the generated run workspace. Do not modify
yadof, dynamically monkey-patch installed modules, or perform fragile text
replacement inside the package. Workspace config overrides may be appended to a
freshly generated copy exactly once in a clearly delimited deterministic block,
with the final effective values captured in `run_spec.json`. Resume verifies the
generated config fingerprint and never appends the block again.

## Runner command contract

The future README must document commands equivalent to:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" plan `
  --suite structural-canary

& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" preflight `
  --suite structural-canary

& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" run `
  --suite structural-canary [--case ID] [--arm ID] [--seed N] [--label TEXT]

& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" collect `
  --run-id <existing-id>

& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" report `
  --run-id <existing-id>
```

Required UX:

- `plan` is the one no-write planning interface. It prints the fully expanded matrix,
  commands, real-evaluation counts, and rough campaign-cost/prerequisite estimate.
- `preflight` checks paths, access, free space, interpreter/package identity,
  baseline/history fingerprints, workspace contracts, strategy construction, and
  required simulator or CUDA availability without starting optimization.
- `run` performs the same preflight automatically, prepares isolated workspaces,
  and runs the selected matrix. `--case`, `--arm`, and `--seed` select a precise
  subset without editing TOML.
- A run ID is generated automatically from UTC time and the resolved-spec short
  hash. `--label` adds a human label; an explicit internal run ID is not required
  for normal use.
- `--resume` continues only the same immutable `run_spec.json`, refuses
  config/baseline/history/strategy fingerprint drift, skips completed cells, and
  never resumes an optimization that stopped during a generation in the same
  measured workspace. Retrying such a cell creates a linked replacement workspace.
- Structural suites fail fast by default. Performance suites continue independent
  cells by default and return a nonzero overall status if any cell is incomplete;
  `--fail-fast` changes the performance default for that invocation.
- `collect` and `report` do not modify measured workspaces, history, or checkpoints.
  They may atomically regenerate derived `metrics.json`, `report.json`, and
  `report.md`. Keep `collect` separate because surrogate audit can perform material
  model inference; `report` is a pure transformation of already collected evidence.
- Nonzero subprocess exits propagate to the invocation status while preserving
  stdout, stderr, duration, and partial metrics.

Use `subprocess` with argument lists and the fixed outer `.venv` interpreter. Do
not invoke commands through an interpolated shell string.

## Benchmark suites

### A. Structural regression suite

Purpose: detect broken wiring after source or workspace structure changes without
forcing the full physical matrix on every iteration. Structural status is separate
from algorithm-performance results.

Provide three explicitly named tiers:

1. **`structural-canary`** uses `20260816 surrogate test_com` to exercise the
   complete reusable path:
   - disposable `yadof check` and one real-task smoke;
   - one empty-history bounded `real-search` generation;
   - an isolated empty-history `gpsaf-conditional-inr` campaign with enough bounded
     generations to exercise training and later surrogate use;
   - compatible checkpoint publication plus machine-readable surrogate `summary`
     and `audit`.
   Begin with two generations and permit one declared extension to three. Use the
   case's real declared ensemble, epoch, query-sample, and device configuration;
   do not substitute a reduced canary-only training profile. The third generation
   aligns with the real maximum-training-lag gate and may wait for or run required
   training synchronously. Never extend past the declared bound merely to obtain a
   checkpoint. This tier does not test checkpoint recovery across process restart
   or strategy switching.
2. **`adapter-smoke`** runs `yadof check` plus one disposable real-task smoke for
   `20260807 saw` and `20260811 chrono trebuchet flexible`, subject to their concrete
   resource/risk policy. Smoke rows never enter measured performance arms.
3. **`structural-full`** is an explicit manual/release tier that applies the full
   real-only/GPSAF/checkpoint/summary/audit path to all three cases. `test_com` alone
   is not production-physics acceptance, but the full tier need not run during each
   benchmark-runner iteration.

Structural acceptance for the selected tier requires:

- all selected checks pass with zero errors; warnings are listed and explicitly
  judged;
- every expected generation completes with at least one finite cost;
- objective counts and required rawData shapes match the frozen case contract;
- generated task snapshots contain complete `submit/` and `job_template/` roots;
- optimization metadata identifies the intended arm and generation sequence;
- tiers that exercise GPSAF produce a compatible checkpoint and finite JSON audit;
- paired arms' generation-zero normalized population vectors are reconstructed in
  population-index order, fingerprinted, and verified equal rather than assumed
  equal merely because their seeds match;
- no baseline/history input changes and no cross-arm state leakage occur;
- command attempts, state, and fingerprints reproduce the exact sequence.

Any failed command, missing generation, or all-infinite generation makes the cell's
evidence incomplete and is reported as validity status. It is not converted into an
algorithm-performance score.

### B. Algorithm performance suite

Purpose: produce aligned evidence for debugging and studying algorithms. The runner
does not judge which arm performs better.

1. Run a bounded pilot to verify the matrix, evidence volume, tool coverage, and
   practical campaign cost. The pilot does not establish thresholds because this
   benchmark has no algorithm pass/fail policy.
2. Freeze population, real-evaluation budget, history policy, arm settings,
   predeclared seed list, and requested observations in `benchmark.toml` before the
   measured campaign.
3. Start with at least three repeated paired input seeds so variation is visible;
   allow the config to request more. This count is not presented as universal
   statistical proof.
4. Run each case/seed for both arms from independently created workspaces with the
   same task fingerprint, starting-evidence fingerprint, initial population, and
   real-evaluation budget. Reconstruct the ordered generation-zero normalized
   population for both arms, save its fingerprint, and mark the paired comparison
   invalid if they differ.
5. Define the real-evaluation budget as attempted candidate evaluations: candidates
   handed to the real evaluator, excluding backend-internal retries. Track planned,
   attempted, completed, finite, and error/timeout/all-infinite counts separately.
   Align HV and other evaluation-indexed results at equal cumulative attempted
   counts, not at equal completed/finite counts, surrogate query counts, or training
   steps. Failed attempts consume budget but contribute no Pareto/HV point.
6. Report every seed plus descriptive paired aggregates. Never publish only the best
   seed and never emit a winner, ranking, significance claim, or acceptance verdict.
7. Run sequentially by default and record order. Optimizer wall time and arm-order
   timing differences are outside the comparison because expensive real simulation
   dominates the intended use case.

Prefer existing public yadof tool surfaces for every reusable single-workspace
observation:

- use the public `yadof.tools.cost_viewer` package/the `view cost` tool surface for
  recalculated cost rows, Pareto information, and cumulative/current-generation
  hypervolume series; do not build new integrations against the compatibility
  facade `yadof.tools.view_cost`;
- use `view surrogate summary --format json` for checkpoint/training metadata;
- use `view surrogate audit --format json` for absolute and relative cost/rawData
  error matrices;
- use an existing public time/training metadata surface for surrogate training
  duration and training lag when available.

The benchmark layer may serialize those tool results, align arms at common real
evaluation counts, and calculate cross-arm/cross-seed descriptive differences. It
must not duplicate a generally useful single-workspace analyzer merely to avoid a
tool gap. For example, if evaluation-normalized HV-AUC, training-duration JSON, or
task-specific ranking diagnostics are not exposed by a suitable public tool, mark
the requested observation unavailable with a concrete explanation and create a
separate future yadof-tools task after the need is demonstrated. Tools changes are
not implementation prerequisites that must all be anticipated or completed by this
TODO.

Surrogate audit is a cross-generation matrix, not automatically a generalization
score. Preserve the full tool output. When checkpoint training-cutoff provenance is
available, label training-overlap and temporal-forward cells separately; when it is
not available, report the ambiguity and do not summarize the whole matrix as
out-of-sample performance. A fixed holdout may be added later through a generally
useful yadof tool contract, not a private benchmark-only model path.

Surrogate time reporting focuses on absolute training duration and training lag.
If a case declares a representative expensive-generation duration (for example two
hours), report the training-duration headroom against that external reference for
context. Do not compare training time to the current cheap benchmark generation and
do not treat the contextual ratio as an algorithm verdict. Optimizer wall time,
peak resource use, and checkpoint size are not requested metrics.

Command/evaluation failures, missing rows, and all-infinite generations remain a
separate evidence-validity section. They are never folded into performance metrics
or interpreted as proof about an algorithm.

The default performance history policy should be a cold start for end-to-end
optimization comparison. An optional warm-start suite may use one immutable,
fingerprinted evidence snapshot copied identically into both arms. Never use the
current mutable original-workspace history directly as one arm's training set.

## Implementation checklist

Completed on 2026-08-23. The final measured run is `pfull-0823`; its append-only
JSON and Markdown reports are under `runs/pfull-0823/reports/report-0001/`. A
separate yadof-tools repair was required to restore the documented public viewer
contract; the benchmark itself did not patch the installed package or inspect
private checkpoint layouts.

### Phase 0 - Refresh and freeze readable baselines

- [x] Resolve the mixed-identity access problem without global ACL weakening.
- [x] Create current-format baseline workspaces below
  `benchmark_automation/baselines/<case>/<baseline-id>/workspace/` with `yadof init`
  plus deliberate task-source and task-asset transfer. Derive the immutable
  baseline ID from its creation date and content-fingerprint prefix, select it
  explicitly in TOML, and never overwrite it. Do not carry mutable runtime evidence
  into a baseline.
- [x] Export any deliberately retained warm-start evidence separately below
  `benchmark_automation/history_snapshots/` with provenance and fingerprints.
- [x] Remove stale release-marker wording from maintained benchmark documentation
  where it still describes a current contract.
- [x] Run `yadof check` and bounded real-task smoke for all three refreshed
  baselines using the final runner identity.
- [x] Confirm current rawData shapes and objective counts, confirm that task
  baselines contain no measured rows or compatible checkpoints, and record row
  counts for each separately exported history snapshot.
- [x] Fingerprint and freeze the baselines and history snapshots used by the runner.

### Phase 1 - Implement the runner core

- [x] Add TOML schema validation and resolved-path handling.
- [x] Implement fresh `yadof init` run-workspace preparation from declared baseline
  inputs, with explicit inclusion of task assets and exclusion of runtime paths.
- [x] Add strategy templates and generated config overrides.
- [x] Add deterministic matrix expansion, automatic unique run IDs, case/arm/seed
  filtering, input hash checks, immutable `run_spec.json`, atomic `run_state.json`,
  and append-only command attempts.
- [x] Implement completed-boundary-only resume, sealed mid-generation failures,
  linked replacement cell workspaces, structural fail-fast, performance
  continue-independent-cells, and the performance `--fail-fast` override.
- [x] Execute subprocesses with structured logs, elapsed time, exit code, and
  bounded timeout/interrupt handling. Store metadata and stdout/stderr in separate
  files below each append-only attempt directory.
- [x] Add `plan`, `preflight`, `run`, `collect`, `report`, and `--resume`; `run`
  reuses preflight and `plan` is the only dry planning interface.

### Phase 2 - Collect and report evidence

- [x] Consume existing public `yadof.tools.cost_viewer` functionality for
  recalculated costs, Pareto data, and hypervolume series; do not reimplement its
  analyzer or bind new code to the `yadof.tools.view_cost` compatibility facade.
- [x] Collect surrogate summary/audit JSON and any public surrogate training
  duration/lag output available in the installed version.
- [x] Record planned, attempted, completed, finite, and failed candidate-evaluation
  counts; align per-seed arm evidence at equal cumulative attempted counts and emit
  raw tool results plus descriptive paired aggregates without a winner or
  acceptance verdict.
- [x] Reconstruct and fingerprint ordered generation-zero normalized populations;
  keep mismatched or incomplete pairs out of primary paired aggregates while
  retaining their raw evidence and validity status.
- [x] Preserve the complete cross-generation audit and label training overlap versus
  temporal-forward evidence only when tool provenance supports that distinction.
- [x] Emit a versioned stable JSON schema plus a concise Markdown report.
- [x] Mark unavailable observations as `null` with an explanation and a concrete
  future yadof-tools gap; never scrape private layouts or silently drop a failed or
  incomplete case, arm, or seed.
- [x] Keep validity status separate from performance metrics, and omit optimizer
  wall time, peak resource, and checkpoint-size metrics.

### Phase 3 - Verify the automation

- [x] Unit-test config validation, path containment, clone exclusions, strategy
  selection, input immutability, resume rules, atomic state, and failed-attempt
  retention.
- [x] Unit-test mid-generation sealing/replacement, suite-specific cell-failure
  behavior, candidate-budget accounting, and initial-population comparison.
- [x] Test path handling with spaces and non-ASCII-safe UTF-8 I/O on Windows.
- [x] Run `structural-canary` on disposable `test_com` workspaces.
- [x] Run `adapter-smoke` on the SAW and Chrono baselines under their risk policy.
- [x] Run `structural-full` manually and inspect every generated report before a
  release claim that requires all three physics cases.
- [x] Repeat one structural run with the same declared seed and verify that inputs,
  commands, and expected deterministic fields match.
- [x] Do not add checkpoint process-recovery or strategy-switch recovery scenarios;
  those belong in yadof's own code/integration tests.

### Phase 4 - Document use

- [x] Write `README.md` with prerequisites, exact commands, suite cost/risk notes,
  output layout, resume behavior, failure diagnosis, and result interpretation.
- [x] Explain clearly that `structural` is short regression evidence and
  `performance` can become expensive.
- [x] Include instructions for adding a case, strategy arm, seed, or metric without
  editing yadof.
- [x] Include a worked no-write `plan` and one example report.
- [x] Explain the boundary between reusable yadof single-workspace tools and
  benchmark-owned cross-arm/cross-seed aggregation.

### Phase 5 - Run the first performance campaign

- [x] Run only the bounded pilot after the structural suite passes.
- [x] Review tool coverage, evidence volume, surrogate training duration/lag,
  incomplete cells, and practical campaign cost.
- [x] Ask the user to approve the full real-evaluation budget if the selected matrix
  is materially expensive.
- [x] Freeze the measured-campaign inputs and run the paired multi-seed matrix.
- [x] Publish raw per-seed results and descriptive aggregates without thresholds,
  pass/fail performance criteria, or an automated claim that one arm is better.

The current three cases are expected to be relatively inexpensive compared with
future production simulators, and surrogate training is expected to dominate much
of this campaign's overhead. Treat that as a planning expectation, not a guaranteed
runtime: `plan` and the bounded pilot must still expose the resolved population,
generations, seeds, real-evaluation count, and observed training cost before the
full matrix proceeds. Those gates were completed before the user-approved
`pfull-0823` campaign; this manual TODO is now complete, while its reported tool
gaps and validity limitations remain part of the evidence contract.

## Completion criteria

This TODO is complete only when:

- the automation lives entirely under `benchmark_automation` and does not modify
  the yadof checkout or installed package;
- one command can enumerate and run every declared case/arm/seed optimization in a
  suite or a filtered subset using isolated workspaces;
- `structural-canary`, `adapter-smoke`, and one explicitly authorized
  `structural-full` run pass; the full tier demonstrates both real-only and
  surrogate-assisted paths, compatible checkpoint publication, and audit across
  all three selected benchmark cases;
- repeated runs are identifiable, resumable, input-immutable, preserve append-only
  attempts, and produce stable machine-readable specs/state/metrics plus a human
  report;
- tests cover preparation, command generation, failure/resume, and reporting;
- `README.md` lets a user run a no-write plan, a bounded structural tier, and a
  filtered or complete performance campaign without reading the implementation;
- the first performance campaign consumes public yadof tool evidence where
  available, reports concrete tool gaps without private scraping, and emits raw
  per-seed/descriptive results without an automated algorithm verdict;
- checkpoint recovery remains outside this benchmark and no optimizer wall-time,
  peak-resource, checkpoint-size, or failure-as-performance metric is introduced.

## Evidence consulted when drafting this TODO

Relevant Codex tasks updated on 2026-08-21 and 2026-08-22:

- `codex://threads/01a022ed-c1ee-7ce1-96a7-b2dd85c7ec5a` - real-only,
  field-balanced surrogate implementation and review.
- `codex://threads/01a02359-f127-7d90-96b1-a141fb5e0d90` - algebraic soft-cost
  change.
- `codex://threads/01a023a5-9bc2-77f2-8aa1-3008e861930a` - Chrono migration and
  benchmark rawData design.
- `codex://threads/01a02764-dcd2-7202-b01a-f6913d126820` - three-workspace
  benchmark suitability assessment.
- `codex://threads/01a027a0-271b-7603-a952-aa8566d02fff` - isolated modular
  environment migration.
- `codex://threads/01a027b5-f262-7b92-8337-db6cac4c9a6f` - yadof 0.4.0 modular
  optimization/workspace composition.
- `codex://threads/01a02904-b24c-73b3-9751-c562f3f95424` - current three-workspace
  migration, smoke, and readiness report.
- `codex://threads/01a0296e-a650-70a1-b071-83167224703b` - removal of incidental
  workspace/checkpoint version markers.

The other recent tasks about AGENTS.md, temporary paths, session context, and Git
permissions were also checked; only their machine/workspace constraints apply
here.

Relevant yadof change records:

- `20260821_121822_delegate-bounded-agent-execution.md`
- `20260821_152002_real-only-field-balanced-surrogate.md`
- `20260821_161213_use-slow-tail-algebraic-soft-cost.md`
- `20260822_112238_confirm-surrogate-benchmark-suite.md`
- `20260822_114152_archive-real-only-surrogate-todo.md`
- `20260822_121655_require-0.4.0-after-modularization.md`
- `20260822_133928_modular-optimization-workspace-composition.md`
- `20260822_204007_remove-incidental-workspace-version-markers.md`
