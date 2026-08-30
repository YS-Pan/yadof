# Installation and workspaces

## AI agent prerequisite

yadof is intended to be used through an AI coding agent. Install an agent before
authoring a task, then open the selected writable workspace in that agent. OpenAI
Codex is recommended because the author used it for development and verification.
The agent should begin with `yadof docs show user README.md` and follow the
version-matched reading order before it edits anything.

## Install

Install a built wheel into the Python environment used by submit and local worker
processes. Add extras only for features you use:

```powershell
python -m pip install .\dist\yadof-0.4.2-py3-none-any.whl
python -m pip install ".\dist\yadof-0.4.2-py3-none-any.whl[surrogate,plot]"
python -m pip install ".\dist\yadof-0.4.2-py3-none-any.whl[qnehvi]"
python -m pip install ".\dist\yadof-0.4.2-py3-none-any.whl[viewer]"
```

The default template's `submit/optimization.py` composes conditional INR. Install
the `surrogate` extra (or `viewer`, which includes Torch) before using the default
`init`, `check`, or `run` workflow. The core-only wheel can operate an existing
workspace whose complete strategy intentionally selects no surrogate component;
strategy validation reports a missing selected backend without importing it
eagerly from package parent modules.

The opt-in `pca_svd()` baseline uses the same `surrogate` extra. Importing its
factory remains lightweight; selecting, validating, or fitting it requires Torch.
It does not require scikit-learn and does not add a posterior capability.

The separate `qnehvi` extra supplies the optional BoTorch numerical backend for the
opt-in `qnehvi()` acquisition and `posterior_assisted()` strategy. It is not a
package default. It declares Torch directly and BoTorch 0.18.x; that BoTorch series
requires Python 3.11 or newer even though core yadof continues to support Python
3.10. Ordinary real search, GPSAF, conditional INR, and `import yadof.optimize` do
not import BoTorch. The currently shipped posterior components are deliberately
blocked from qNEHVI exploitation because their architecture/calibration evidence
is not accepted or transferable; an explicit posterior-assisted composition still
runs through its audited real-search fallback.

The integrated v10 release decision keeps this feature experimental. Offline
checkpoint/viewer validation is allowed, and the explicit composition remains a
useful fail-closed structural surface, but it is neither a recommended opt-in nor
a scientific optimizer result. The package template still selects GPSAF plus
conditional INR. Installing the `qnehvi` extra does not open the typed gate and
does not authorize a performance campaign.

`yadof --version` and `yadof version` report the same package version. Distributed
jobs do **not** carry the yadof package, wheel, source tree, or runtime archive.
HTCondor executes job-local `workflow.py` directly. The assigned parameter snapshot
is self-contained and the package copies only `worker_misc.py` beside the workflow.
That helper owns behavior invariant across tasks: standard paths, execute identity,
lifecycle/error metadata, rawData preparation, and flat output transport. Python,
NumPy, adapters' third-party dependencies, PyAEDT, and simulator software still
belong to the worker environment.

The packaged Project Chrono adapter is also copied task code, but it launches the
absolute interpreter configured by `YADOF_PYCHRONO_PYTHON`. The yadof environment
does not import PyChrono, and the separately provisioned PyChrono environment does
not install or import yadof. See `user_doc/adapters/chrono_com.md` before authoring
that task boundary.

The `viewer` extra installs the Torch and Matplotlib dependencies needed by
`yadof view surrogate`. Tkinter must also be available when using its default
desktop GUI; the `summary` and `audit` text modes do not open Tkinter. The viewer is
submit-side, read-only inspection software and is never copied into distributed
jobs.

The current package version is `0.4.2`. Recorded history uses immutable
standard-ZIP segments and immutable metadata event files.

The reference development machine used Windows 11 Pro 25H2, ANSYS Electronics
Desktop 2024 R1, CPython 3.13.11, PyAEDT 0.24.1, NumPy 2.2.6, pymoo 0.6.2, and
psutil 7.2.2, and HTCondor 25.4.0. psutil is a core dependency because local
resource planning measures the workflow and simulator process tree. This is a
reproducibility snapshot rather than a minimum-version contract; the wheel metadata
remains authoritative for Python and dependency requirements.

## Independent benchmark package

`yadof-benchmark` is a separate distribution developed beside yadof. It depends
on public yadof behavior; yadof does not import benchmark orchestration or include
concrete baselines. Its wheel owns the API, console command, baseline resources,
and version-matched documents.

```powershell
$workspace = (yadof-benchmark init D:\benchmarks\comparison |
  ConvertFrom-Json).workspace
yadof-benchmark baselines
yadof-benchmark plan --workspace $workspace
```

One benchmark workspace owns one `benchmark.py` and one execution. Another
execution uses another initialized workspace. There is no `runs/`, run ID,
resume path, numbered attempt hierarchy, or copied code-driver snapshot. The
installed package records its and yadof's versions once in `runtime.json` before
cell work.

Strategies may declare `slow_surrogate=True`. Comparisons default to one seed,
population 200, and 50 generations; a comparison containing a slow surrogate
defaults to 15 generations. Explicit values override defaults. Individual
simulation errors are retained without invalidating a cell when the planned
attempt count is complete and finite, contract-valid metric evidence remains.

Measured `run` may launch task software and remains subject to
`config_and_run.md`. On Windows an AI agent must launch through host execution
under the signed-in human account; a sandbox-owned detached process cannot display
a console in the user's session. Use
`inspect --workspace PATH` as the read-only first view.

## Initialize and inspect

```powershell
yadof init D:\work\study-a
yadof check --workspace D:\work\study-a
```

Initialization publishes a generic pure-Python template and `.yadof/workspace.json`
without overwriting existing destinations. Repeating init on the same complete,
initialized workspace is non-mutating. It does not repair user files or run a
workflow. `check` is read-only: it validates marker/config/task/rawData structure and
discovers backend executables, but never installs or configures software.

## Workspace layout

```text
study-a/
  .yadof/workspace.json
  config.py
  submit/                       fixed submit-side source root
    calc_cost.py
    optimization.py
  job_template/
    parameters_constraints.py
    workflow.py
    evaluation.py                optional; required by fast mode
    optional adapters and assets
  jobs/                         generated
  recorded_data/                generated recorded-data root
    segments/<run>/<generation>/segment_*.zip
    metadata/<event-type>/event_*.json
  .yadof/campaign.lock          OS-backed active-campaign lock file
  .yadof/fast_scratch/          ephemeral fast candidate scratch; normally empty
  .yadof/surrogate/checkpoints/ generated
  .yadof/optimization/active.json generated active strategy pointer
  .yadof/logs/                  generated
  .yadof/tool_output/           generated
  visualization_outputs/       optional task-owned scripts and exported artifacts
```

Relative configured paths resolve from the selected workspace. Two workspaces can
be used consecutively or concurrently in one process without sharing task modules,
records, surrogate state, or output paths. Installed package resources are read-only
inputs and are never used as a runtime-data location.

One workspace is one active optimization campaign/write domain. Yadof takes a
non-stale OS file lock before evaluation and a second campaign fails before it can
start. If two optimizations must run at
the same time, initialize or copy their task definitions into different workspaces;
each workspace then has independent history, locks, recording, checkpoints, and
task changes. Read-only inspection may share a workspace only where the selected
command explicitly supports it, and destructive history clearing must never run
against an active campaign; `history clear` checks the same lock and refuses.

The workspace is user-owned and may contain additional directories beyond this
example layout. Use them for task-specific helper scripts, debugging evidence,
experiment notes, exported animations, images, reports, or other outputs. Choose
names that do not collide with `.yadof/`, `submit/`, `job_template/`, `jobs/`,
`recorded_data/`, or configured framework paths. Yadof ignores such extra
directories unless task/config code explicitly references them. They are not
automatically copied into prepared jobs; place execute-side assets below
`job_template/` (or have task code copy them deliberately) when a worker needs
them.

Prepared distributed jobs contain the task payload, assigned
`parameters_constraints.py`, and `worker_misc.py`. Direct `job_template/` children
ending with `.aedtresults` or `.aedt.lock` are excluded as AEDT runtime artifacts;
the suffix rule does not inspect nested task directories. A distributed workflow
must not import yadof; import only same-directory task files, the Python standard
library, and dependencies deliberately installed on execute nodes.

`submit/` is fixed and is not configurable through `config.py`. Its complete tree
is available only on the submit host and is never copied into a prepared job or an
HTCondor transfer list. `calc_cost.py` owns current rawData interpretation;
`optimization.py` must define `build_optimization()` and compose one complete
strategy from installed yadof components. Canonical unassigned parameters remain
only in `job_template/parameters_constraints.py`.

Workspace `job_template/workflow.py` and `submit/calc_cost.py` contain only
behavior that can change with the optimization task. They call copied `worker_misc`
or installed
`yadof.job_template` helpers for every cross-task invariant.

Fast mode is the third explicit backend beside local and distributed. It requires
task-owned `evaluation.py:evaluate_rawdata()`, runs it in reusable crash-isolated
processes on the submit machine, and creates no durable `jobs/<candidate>/`
directory. A simulator may use the configured fast scratch root, but each candidate
scratch is temporary, isolated, and cleaned; it is not evidence or a recovery point.
The parent validates and owns returned memory rawData in the same backend-neutral
coordinator used by local and distributed execution. It hands bounded evidence
groups to the campaign recorder, waits for committed receipts, and only then runs
current cost in stable population order. When publication cannot keep up, recorder
admission waits for capacity; the population boundary waits for all evidence to
become durable before later evaluation begins. A cost failure preserves already
committed completed evidence for replay and returns transient optimizer `inf`; a
hard record-limit or storage failure stops the campaign visibly instead of
continuing with missing history.

The generic template contains no simulator, vendor, concrete model, or fixed
objective. Use `yadof task adapters` and `yadof task copy-adapter NAME --workspace
PATH` to copy only a selected packaged adapter into user-owned task files.
