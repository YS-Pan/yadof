# yadof benchmark automation

This directory owns a reproducible, resumable comparison of the SAW, PyChrono
trebuchet, and synthetic `test_com` tasks. It has two deliberately
separate purposes:

- **Structural suites** verify task wiring, real-evaluation-only NSGA-III, GPSAF,
  conditional-INR training/use, checkpoint publication, and public inspection.
- **Performance suites** publish raw per-seed values and paired descriptive
  differences. They do not rank arms, apply significance tests, or decide which
  algorithm is better.

Baseline templates are editable in place under
`baselines/<provider>/<baseline-id>`; the directory name is semantic and contains
no fingerprint suffix. Creating a run copies the current declared inputs into an
immutable run-local snapshot. Every cell starts with `yadof init`, receives inputs
only from that snapshot, and has its own workspace, history, optimizer state,
checkpoint namespace, logs, and lock. Later baseline edits affect only later runs.

This is a source-checkout tool. It is tracked beside yadof so a user who clones or
downloads the yadof repository can run the benchmark, but it is deliberately
outside `src/yadof` and is not installed by `pip install yadof`. The runner consumes
a regular installed yadof distribution from the selected Python environment.

## Current execution status

The initial SAW and Chrono baselines and the runner were created on 2026-08-23
with installed `yadof 0.4.0`. The selected Chrono baseline was refreshed on
2026-08-24 with ground contact, semantic rawData curves, Trebuchet visualization,
and prefix-capable visualization output, then refreshed on 2026-08-25 with the
generic Windows short-launch-junction Chrono adapter fix. The selected synthetic
`test_com` task retains its 20-variable non-separable multimodal landscape. All
three current baselines accept the runner's output directory and filename-prefix
interface. The runner now groups task-specific artifacts by baseline workspace and
groups all cost views in one sibling directory. Their creation fingerprints remain
provenance only; the templates and semantic directory names may change in place.

| Evidence | Result |
|---|---|
| Phase-0 smoke for all three baselines | Passed; costs and rawData shapes match the declared contracts |
| selected Chrono baseline `trebuchet` | Preflight 5/5 passed; real fast smoke `20260825_001100-chrono-adapter-long-path-regression-abcdefghijklmnopqrstuvwxyz0123456789` completed with the unchanged four midpoint costs while its representative physical PyChrono scratch/request paths were about 298/311 characters |
| `adapter-smoke` run `20260823T052657Z-adapters-1b7c0d27af47` | Structural contract satisfied |
| yadof-tools repair `0665541155009787c938cbf15df177e8c9488fb8` | Built, force-reinstalled, 274 tests passed, and pushed to `origin/main` |
| post-fix `structural-canary` run `20260823T060003Z-post-viewer-fix-9e43d5c3327b` | Structural contract satisfied, including finite public summary and both audits |
| post-fix `structural-full` run `20260823T060119Z-post-viewer-fix-ba5ad9cc3103` | All three cases and both arms satisfied every structural check |
| `performance-pilot` run `20260823T060351Z-post-viewer-fix-5a583e492089` | 192/192 evaluations completed; three paired rows included and none excluded |
| historical three-generation `performance` run `pfull-0823` | 18/18 cells completed; 1080 attempted, 1062 publicly recorded completions, 18 recorder-budget losses, zero timeouts/all-infinite generations, and 9/9 paired rows included |
| historical 100-by-20 `performance` run `p20x100-0823` | 18/18 cells completed; its `test-com` rows use the superseded `synthetic-antenna-aa89d46f3d9a` objectives and must not be compared with new-baseline runs |
| historical first replacement `synthetic-antenna-c7b0133b3a4e` | Corrected objective scaling, but three real-only NSGA-III runs reached HV 0.8597-0.8833 after only 2,000 evaluations; its superseded baseline directory was later removed |
| selected hard `test-com` baseline `synthetic-antenna` | Preserves the accepted scientific task and common diagnostic plot while adding collision-safe flat-output filenames; the underlying three real-only NSGA-III validations each recorded 10,000/10,000 rows, reached HV 0.4347-0.4409, and still gained 5.13%-5.94% over their final ten generations |

The resolved viewer gap and its historical failure evidence are documented in
[`tool_gaps/20260823-surrogate-viewer-raw-variables.md`](tool_gaps/20260823-surrogate-viewer-raw-variables.md).
The synthetic-task difficulty diagnosis and 30,000-row acceptance evidence are in
[`verification/20260824-test-com-difficulty-recalibration.md`](verification/20260824-test-com-difficulty-recalibration.md).
No benchmark-only checkpoint scraping or monkey patch was used. Generated runs are
local and Git-ignored; the tracked, portable descriptive result is
[`verification/20260823-pfull-0823-summary.md`](verification/20260823-pfull-0823-summary.md).

An earlier authorized full run,
`20260823T062344Z-approved-full-campaign-55651e90c9ef`, is retained as incomplete
evidence. Its three Chrono GPSAF cells reached a roughly 272-character PyChrono
child working directory and failed at Windows process launch with `WinError 267`.
The final run used the same scientific inputs with the explicit short run
ID `pfull-0823`; all Chrono GPSAF cells then completed. The selected
`trebuchet` baseline now carries the package-level adapter fix: every
Windows PyChrono child launches through a short candidate junction targeting its
original physical scratch, so future run IDs and output roots do not need manual
shortening. Historical run specifications remain immutable.

## Prerequisites

Run commands from the yadof source-checkout root with the Python environment in
which the matching yadof distribution and benchmark extra are installed. The
benchmark extra supplies Rich for reliable multi-progress terminal rendering:

```powershell
python -m pip install "yadof[benchmark]"
python ".\benchmark_automation\benchmark.py" --help
```

The runner preflights all selected resources without starting a simulator:

- SAW requires `YADOF_NGSPICE_EXE` to name a readable ngspice console executable.
- Chrono requires `YADOF_PYCHRONO_PYTHON` to name the external PyChrono Python.
- `test_com` requires Torch CUDA availability for the declared conditional-INR
  profile.
- At least the configured free-space floor (currently 2048 MiB) must remain.

The selected Python executable, Python version, installed yadof origin/version,
module hash, distribution `RECORD` hash, Torch/CUDA/device facts, baseline hashes,
history identity, strategy hashes, and fully expanded commands are frozen in each
`run_spec.json`.

A baseline manifest's `yadof_version` and `task_fingerprint` are creation
provenance, not locks on current template content or the exact execution patch.
Preflight requires the version provenance, checks runtime cleanliness, and runs the
current installed `yadof check`. Run creation then records the current task
fingerprint, snapshots declared inputs, and freezes the actual execution package
identity. A template created by 0.4.0 can therefore be edited and executed under
compatible 0.4.1 without fingerprint-derived directories.

## Commands

`plan` is the only no-write planning interface. Its default JSON is a bounded
agent summary: selection, cell/evaluation counts by case, prerequisites, and rough
lower-bound evaluation/storage estimates. Add `--full-json` only when expanded
cells and exact planned command lines are required:

```powershell
python ".\benchmark_automation\benchmark.py" plan `
  --suite structural-canary
```

Preflight performs static validation and `yadof check`, but never launches the
task workflow. Its default JSON lists every check outcome but omits captured
command stdout/stderr and expanded identities; `--full-json` restores the complete
evidence:

```powershell
python ".\benchmark_automation\benchmark.py" preflight `
  --suite structural-canary
```

Create and execute a new run:

```powershell
python ".\benchmark_automation\benchmark.py" run `
  --suite structural-canary `
  --label local-check
```

Child stdout/stderr is always written to the append-only command logs. The default
terminal output contains the same short lifecycle events. Rich keeps the active
cell's individual-evaluation bar directly above the global cell bar at the bottom
of an interactive terminal, without leaving old frames when other output appears;
both bars disappear before the final JSON summary. Non-interactive output receives
throttled complete snapshots. Add `--stream-output` only for deliberate live raw
output; it can be large. While the live region is active, Rich renders both child
channels through its stderr console so messages cannot split the cursor owner;
the append-only logs still preserve stdout and stderr separately. Each child
snapshot updates the cell and global Rich tasks before one atomic refresh, so a
stale zero-valued cell frame cannot replace the new value. The cell detail starts
with cumulative percentage and `gen=<current>/<total>` across the whole cell,
rather than showing only the current generation's local fraction.
Every measured optimization calls the selected baseline's root `postprocess.py`
after its final generation. SAW writes S-parameter plots/data, Chrono writes a
trebuchet MP4/poster/manifest, and test_com writes a compact antenna response plot.
The runner writes those task-specific artifacts into one
`visualizations/<baseline-id>/` directory per baseline workspace. All measured
cells for that baseline share the directory and use the collision-safe
`<cell-id>__attempt-<NNNN>__` filename prefix. It then invokes `yadof view cost`
and groups every cost plot in
`visualizations/viewcost/` under the collision-safe
`<cell-id>__attempt-<NNNN>__benchmark-cost.png` name. Either postprocessing or
cost-view failure fails the attempt so missing human-review artifacts are explicit.

Select a precise subset without editing TOML. Repeat a selector to include more
than one value:

```powershell
python ".\benchmark_automation\benchmark.py" run `
  --suite performance `
  --case saw `
  --arm nsga3 `
  --arm gpsaf-conditional-inr `
  --seed 104729
```

Collection is intentionally separate because surrogate audit performs model
inference. Collection prints only artifact paths and an instruction to report; do
not read `metrics.json` or `collection.json` wholesale. Reporting is a pure
transformation of the latest collected snapshot. Its stdout is still one bounded
JSON agent summary, while the terminal also receives a compact Markdown table of
final cumulative hypervolume by case, seed, and concrete algorithm name:

```powershell
python ".\benchmark_automation\benchmark.py" collect `
  --run-id <existing-id>

python ".\benchmark_automation\benchmark.py" report `
  --run-id <existing-id>
```

Inspect an existing run without changing it. This is the normal first command for
an agent asked to interpret or diagnose a run:

```powershell
python ".\benchmark_automation\benchmark.py" inspect `
  --run-id <existing-id>
```

`inspect` combines execution status, validity totals, structural failures or
paired performance evidence, artifact sizes/read policies, and the next applicable
commands. `report --full-json` remains available for consumers that explicitly
need the complete stable report.

Resume the exact immutable spec after a completed-boundary interruption:

```powershell
python ".\benchmark_automation\benchmark.py" run `
  --resume <existing-id>
```

The equivalent `resume --run-id <existing-id>` command is also available. Resume
refuses config, installed-package, run-local baseline snapshot, history, strategy,
or execution-runner fingerprint drift; edits to the source baseline do not affect
it. Completed cells are skipped. A workspace that stopped inside a
generation is sealed and retained; retry creates a new attempt workspace with an
explicit `replacement_for` link. It never reruns that generation in the failed
workspace.

## Suites and cost/risk

Suite order is deterministic and execution is sequential to avoid shared-resource
contention.

| Suite | Scope | Default behavior |
|---|---|---|
| `structural-canary` | `test_com` smoke, real generation 0, GPSAF generations 0–1, and declared generation 2 when no surrogate use has occurred | Fail fast; full declared training profile |
| `adapter-smoke` | one disposable SAW smoke and one disposable Chrono smoke | Fail fast; no measured arm |
| `structural-full` | full structural path for all three cases | Fail fast; manual/release tier |
| `performance-pilot` | one paired seed, three generations per arm and case | Continue independent cells; bounded cost discovery |
| `performance` | three paired seeds, 100 individuals × 20 generations per arm and case | Continue independent cells; long-running |

`plan` estimates task-evaluation time from prior observations and declared worker
caps. It excludes optimizer and surrogate training overhead. The pilot must be run
and reviewed before the full matrix. If the resulting full real-evaluation or
training cost is material, obtain explicit user approval before starting it.

Every measured cell deliberately sets `FAST_EVALUATION_MAX_WORKERS = 32` and
`FAST_RESOURCE_AUTODETECT_ENABLED = False`. This permits CPU oversubscription—for
example, 32 simulator processes on an 8-core host—when workflows spend substantial
time waiting on external software or I/O. The value is an experiment setting, not a
hardware safety guarantee: memory, simulator licensing, and external-runtime limits
must still be checked during preflight and pilot review. Smoke cells retain the
baseline's normal one-individual safety behavior.

The current performance matrix uses cold starts, equal planned attempted
real-evaluation budgets across arms for each case, and the seeds `104729`, `130363`,
and `155921`. Failed candidates consume attempted budget but do not contribute a
Pareto or hypervolume point.

The formal `performance` suite plans 36,000 attempted real evaluations: 2,000 per
cell across 18 cells. `performance-pilot` deliberately remains a three-generation
cost-discovery tier and must not be reported as the full benchmark. Measured cells
also raise recorder batching/headroom to 100 candidates per segment and 128
unpublished candidates so one full 100-individual generation can be admitted
without the default 32-candidate queue becoming the experiment's evidence limit.

### Mandatory scale for algorithm work

When the purpose is to evaluate surrogate/optimizer algorithm performance or to
tune either algorithm from benchmark results, small runs are prohibited. A few
generations with only dozens of individuals are structural or cost-discovery
evidence, not algorithm-performance evidence, and must not drive algorithm changes.
Run the complete, unfiltered `performance` suite instead: the current contract is
100 individuals × 20 generations, or 2,000 attempted real evaluations in every
measured cell and 36,000 across the full 18-cell matrix. Do not reduce its cases,
arms, seeds, population, or generation count for performance diagnosis or tuning.
The smaller suites remain valid only for wiring, prerequisite, failure-path, and
runtime-cost checks.

### Visible detached Windows launch

`run` is a foreground, resumable command whose cell lifecycle is flushed to the
terminal and whose child command output is always retained in per-command logs.
For a user-authorized long run on Windows, launch that same foreground command in a
separate normal PowerShell window with `Start-Process -PassThru`, then let the
calling agent disconnect without `-Wait`. Use an explicit `--run-id` when a stable
operator-chosen identity is useful, and keep the same explicit `--runs-dir` for
later `inspect`, `collect`, and `report` commands.
The returned process object supplies its PID. After run/resume reaches a final
state, an interactive CLI waits for Enter instead of exiting automatically, so the
separate window and its final summary remain visible. Piped/non-interactive
invocations do not pause. Do not add `-WindowStyle Hidden` for this deliberately
user-visible launch.

## Output and immutability

The configured default output root is the source checkout's ignored `temp/`
directory, expressed as `../temp` relative to `benchmark.toml`. Override it with
the global `--runs-dir PATH` option before the subcommand. An absolute path is used
as given; a relative override resolves from the invocation directory.

When `run` does not receive an explicit `--run-id`, its output directory name
starts with the UTC timestamp `YYYYMMDD_HHMMSS`: both the date and time components
contain digits only. A sanitized optional label and the 12-hex run-spec suffix
follow that prefix, for example `20260824_123456-full-benchmark-a1b2c3d4e5f6`.

Run from the yadof checkout root. Each run ID supplies the unique directory directly
below `temp/`; do not add a benchmark or task-specific container layer. An explicit
equivalent root can still be supplied, for example:

```powershell
python ".\benchmark_automation\benchmark.py" `
  --runs-dir ".\temp" `
  inspect --run-id <existing-id>
```

Use the same `--runs-dir` for `run`, `resume`, `collect`, `report`, and `inspect`.
Bounded output includes the resolved run root and carries the option into suggested
next commands. A temporary output root is not deleted automatically; retain it
until the result has been handed off. Human-operated durable runs may omit the
override or select another persistent output root explicitly.

Each run is identity-stable:

```text
temp/<run-id>/
  run_spec.json              immutable resolved inputs and runner identity
  matrix.json                immutable selected cell/command expansion
  run_state.json             atomically advanced execution state
  inputs/baselines/<case>/workspace/
                             immutable declared-input snapshot for all cells/resume
  metrics.json               latest derived public-API collection
  report.json                latest derived report
  report.md                  latest concise report
  cells/<cell-id>/attempts/<NNNN>/
    input_manifest.json
    workspace/
    commands/<NNNN-label>/
      command.started.json
      command.finished.json
      stdout.log
      stderr.log
  visualizations/
    viewcost/
      <cell-id>__attempt-<NNNN>__benchmark-cost.png
    <baseline-id>/
      <cell-id>__attempt-<NNNN>__postprocess_manifest.json
      <cell-id>__attempt-<NNNN>__<task-specific-artifact>
  evidence/collect-<NNNN>/   append-only collection and public tool outputs
  reports/report-<NNNN>/     append-only report snapshots
```

`run_spec.json`, `matrix.json`, command attempts, logs, and prior evidence/report
snapshots are never overwritten. `run_state.json` and the root-level latest
`metrics.json`/reports are written atomically. Collection and reporting do not
modify measured workspaces, histories, or checkpoints.

Smoke workspaces are separate disposable cells. Their records never enter a
measured NSGA-III or GPSAF arm.

## Agent reading order

The repository [`AGENTS.md`](AGENTS.md) defines the complete progressive-
disclosure policy. In short:

1. Start with `inspect --run-id ...` or the default `plan`/`preflight` summary.
2. Read `report.md` only when narrative context is useful.
3. Query targeted `report.json` fields when the summary omits a required detail.
4. Diagnose one failed cell through `run_state.json`, command metadata, and one log
   tail.
5. Query one cell/field from `metrics.json` only as the final evidence layer.

Do not recursively scan the selected output root and do not load multi-megabyte
collection files into an agent context. Full evidence remains on disk even when
the CLI suppresses it from stdout.

## Measurements and interpretation

Collection uses these public surfaces:

- `yadof.recorded_data` for records, generation metadata, normalized variables,
  rawData samples, and surrogate training metadata;
- `yadof.tools.cost_viewer` for recalculated cost rows, Pareto summary, and
  cumulative/current-generation hypervolume;
- `yadof view surrogate summary/audit --format json` for supported surrogate
  observations.

Generation-0 normalized populations are reconstructed in the public
`created_job_names` order and content-fingerprinted. A paired performance row is
excluded from primary descriptive aggregates if either cell is incomplete, its
observed attempted budget differs, or its generation-0 fingerprint differs. The
raw evidence remains listed.

Hypervolume is aligned at cumulative attempted real-evaluation generation ends.
Evaluation-normalized HV-AUC is `null` because yadof exposes no public metric
contract for it. Checkpoint training-cutoff provenance is also unavailable, so
surrogate audit matrices are never relabeled or summarized as out-of-sample.

Command failures, timeouts, missing generations, all-infinite generations, and
warnings live in the validity section. They are not algorithm-performance metrics.
Optimizer wall time, peak resource use, and checkpoint size are not comparison
metrics. Command durations remain in command metadata only for operational
diagnosis.

## Worked examples

A no-write canary plan resolves to three isolated cells:

```text
smoke__test-com__seed-20260816
  smoke: 1 disposable midpoint evaluation
test-com__nsga3__seed-20260816
  population 12 × 1 generation = 12 planned attempted evaluations
test-com__gpsaf-conditional-inr__seed-20260816
  population 12 × 2 base generations = 24 planned attempted evaluations
  one declared generation-2 extension when the base run has not used the surrogate
```

The executed adapter example produced this root-level report result:

```json
{
  "run_id": "20260823T052657Z-adapters-1b7c0d27af47",
  "suite": "adapter-smoke",
  "purpose": "structural",
  "structural": {
    "contract_satisfied": true
  }
}
```

The original corrected canary report had `contract_satisfied=false` for exactly
one public viewer error. After the reusable yadof-tools repair, the post-fix canary
and `structural-full` reports both have `contract_satisfied=true`. The final
performance report contains all nine predeclared case/seed pairs and zero excluded
pairs. It remains descriptive only: raw hypervolume values and paired differences
are not an algorithm ranking or acceptance verdict.

The three historical `test-com` cells whose arm ID was then `real-search` each
emitted six best-effort recorder budget losses. Optimization still completed all
planned attempted evaluations, but
the public evidence contains 66 rather than 72 completed rows in each affected
cell. The stable JSON report exposes the resulting totals (1080 attempted, 1062
completed, 18 failed/missing); consumers must retain that validity context when
interpreting the nine descriptive rows.

## Failure diagnosis

1. Read `run_state.json` and find cells not marked `completed`.
2. Open the latest attempt's `command.finished.json`, then its separate stdout and
   stderr logs. A `command.started.json` without a finished companion indicates an
   interrupted command.
3. Run `collect --run-id ...` even for an incomplete performance matrix; partial
   evidence is retained and incomplete pairs are excluded rather than hidden.
4. Fix only the external prerequisite or reusable yadof issue. Do not edit a
   measured workspace.
5. Use `run --resume ...`; the old attempt stays sealed and a replacement is linked.

Structural suites stop after the first failed cell by default. Performance suites
continue independent cells and exit nonzero when any cell is incomplete.
`--fail-fast` overrides the performance default for that invocation.

## Extending the benchmark without editing yadof

To add or edit a case:

1. Create or edit the semantic
   `baselines/<provider>/<baseline-id>/workspace` template with current `yadof
   init`, deliberate task-input transfer, zero runtime evidence,
   a root `postprocess.py` implementing the common `--workspace`, `--output-dir`,
   and `--output-prefix` interface, `yadof check`, and one disposable smoke. The
   postprocessor receives the baseline-specific shared result directory below
   `visualizations/` and a collision-safe cell/attempt filename prefix. It must
   write every persistent artifact directly in that directory, create no further
   result subdirectories, and refuse to overwrite existing names. Temporary
   scratch belongs outside the result directory. The runner owns the separate
   shared `visualizations/viewcost/` directory and its prefixed cost-plot names.
2. Keep matching `provider_id`, `case_id`, and semantic `baseline_id` provenance in
   `baseline.json`, then declare the exact baseline path, `include_paths`, objective
   count, rawData shapes, resource prerequisite, history policy, and budgets in
   `benchmark.toml`. The recorded task fingerprint is creation provenance and need
   not be renamed or updated after each edit; the next run records its current
   fingerprint automatically.
3. Run `plan`, `preflight`, and the smallest structural tier before performance.

To add an arm, add a complete strategy module under `strategy_templates/` with a
callable `build_optimization()`, declare its exact overrides in TOML, and give it
equal performance budgets. To add seeds, edit the suite's predeclared list before
creating a run. To add a cross-arm descriptive metric, consume a public
single-workspace yadof API/tool result and version the emitted schema. If the
single-workspace observation does not exist publicly, document a yadof-tools gap;
do not scrape `.yadof` internals in the benchmark.

Reusable single-workspace analyzers belong in yadof. This directory owns only
run-snapshotted experiment assembly, cross-case/arm/seed alignment, validity
handling, and descriptive aggregation.

## Development

Maintainers should start with [`dev_doc/README.md`](dev_doc/README.md). The
developer guide defines the repository boundary, fixed environment, verification
workflow, and links to the current architecture and invariants.
