# yadof

yadof is an installable, task-agnostic optimization framework for expensive local
or HTCondor workflows. The current packaged release is **0.4.2**. Evaluation
history uses immutable standard-ZIP segments plus immutable metadata events.

Its durable modeling contract is:

```text
normalized variables -> rawData -> current task cost
```

## AI-agent-first use

yadof is designed to be operated with an AI coding agent at the center of the
workflow. Install an AI agent on the computer before preparing a yadof task. The
recommended agent is [OpenAI Codex](https://openai.com/codex/get-started/) because
the author developed and verified this package with Codex.

Open the intended writable workspace in the agent, then give it the task together
with this starter:

> Complete the task below. Before you begin, run `python -m yadof docs show user README.md` and follow its instructions, reading any referenced documentation or installed yadof code needed for the task.

The installed, version-matched user documents are written primarily for that
user-directed AI agent: they tell it which files it may edit, what it must read, and
which validation command to run. The human user normally directs, sets execution
limits, and reviews this work rather than executing every documented step
personally; the user documentation lets the agent run understood bounded work while
reserving long or consequential runs for explicit authorization. A reserved blank
prompt is available at
[user_doc/example_prompts/01_task_setup.md](user_doc/example_prompts/01_task_setup.md);
the surrounding [prompt examples directory](user_doc/example_prompts/README.md) is
ready for additional examples.

## Install and run

Install the wheel into the Python environment used on the submit machine:

```powershell
python -m pip install ".\dist\yadof-0.4.2-py3-none-any.whl[surrogate]"
python -m pip install ".\dist\yadof-0.4.2-py3-none-any.whl[viewer]"
```

The default workspace composes conditional INR, so `init`, `check`, and `run`
require the `surrogate` extra (the `viewer` extra includes the same Torch runtime).
A core-only installation remains valid for an existing workspace whose
`submit/optimization.py` selects no surrogate component.

Ask the AI agent to initialize and author the task, or use the underlying commands
directly:

```powershell
yadof init D:\work\my-study
yadof check --workspace D:\work\my-study
yadof smoke-test --workspace D:\work\my-study --real-task
yadof run --workspace D:\work\my-study
yadof view all --workspace D:\work\my-study
yadof view surrogate --workspace D:\work\my-study
```

`yadof run` now runs **50 generations by default**. Use `--generations N` to
override that count. The standalone smoke command prints its workspace, backend,
jobs directory, and no-timeout warning before execution starts, then reports the
final costs or an actionable failure.

### Local concurrency

Local mode previously defaulted to one concurrent simulation. The packaged default
cap is now **8**, with resource autodetection enabled. The effective count for each
batch is the smallest safe value allowed by:

- the population size and `LOCAL_EVALUATION_MAX_WORKERS`;
- physical CPU capacity;
- currently available memory and free disk after a 15% system reserve;
- per-job CPU, peak-memory, and disk estimates calibrated from the preceding smoke
  test or optimization generation.

Local workflows are monitored as process trees, so simulator child processes are
included. Their measurements and HTCondor measurements use the same recorded
resource fields and shared calibration algorithm. `HTCONDOR_REQUEST_CPUS`,
`HTCONDOR_REQUEST_MEMORY`, and `HTCONDOR_REQUEST_DISK` remain the initial per-job
resource hints when no usable history exists. Use `--progress` to print the selected
local worker count and each limiting capacity. Set
`LOCAL_RESOURCE_AUTODETECT_ENABLED = False` only when the configured worker cap
should be used directly.

## Reference development environment

The current packaged line was developed and tested on this machine snapshot,
detected on 2026-07-29:

| Component | Detected version |
|---|---|
| Operating system | Windows 11 Pro 25H2, build 26200.8875, x86-64 |
| ANSYS Electronics Desktop | 2024 R1 (`2024.1.0.1`) |
| Python | CPython 3.13.11 in the repository sibling `.venv` |
| NumPy / pymoo | 2.2.6 / 0.6.2 |
| psutil | 7.2.2 |
| PyAEDT | 0.24.1 |
| HTCondor | 25.4.0 |
| PyTorch / Matplotlib | 2.10.0+cu128 / 3.11.1 |
| pytest | 9.1.1 |

This is a reproducibility snapshot, not a claim that every listed version is a
minimum requirement. See
[dev_doc/development_environment.md](dev_doc/development_environment.md) for paths,
detection details, and the package's declared compatibility boundary.

## Source-checkout benchmark

The repository includes a downloadable, user-runnable comparison tool under
[benchmark_automation](benchmark_automation/dev_doc/README.md). It is deliberately
outside `src/yadof`: a Git clone or repository download contains the runner,
self-describing baseline templates, and focused tests, while `pip install yadof`,
wheel, and sdist do not. Complete `submit/optimization.py` files are supplied by an
external study; adding an algorithm requires no benchmark source change.

Use a Python environment containing the matching installed yadof distribution and
start with the no-write plan:

```powershell
python ".\benchmark_automation\benchmark.py" baselines
python ".\benchmark_automation\benchmark.py" plan --study D:\studies\comparison.toml
```

The study selects baseline IDs, strategies, seeds, one uniform budget, an optional
reference, and its run root. `plan` writes nothing. `run` snapshots the complete
driver, baselines, and strategy inputs; `resume --run PATH` executes only that
run-owned snapshot. Read [the study format](benchmark_automation/dev_doc/study_format.md)
and apply the normal cost/risk policy before starting real work.

## Package and workspace boundary

The package owns framework code, defaults, worker support, templates, adapters,
tools, and documentation. A workspace owns `config.py`, fixed `submit/`,
`job_template/`, jobs,
recorded raw evidence, surrogate checkpoints, logs, and tool output. Package files
are treated as read-only and there is no `project.*` compatibility namespace.
Cross-task invariant code belongs in yadof; workspace
`job_template/workflow.py`, `submit/calc_cost.py`, and
`submit/optimization.py`
contain only behavior that can change with the optimization task and call package
helpers for everything else.

The optional read-only surrogate checkpoint viewer is installed below
`yadof.tools.surrogate_viewer` and launched explicitly with
`yadof view surrogate`. It reads checkpoints and recorded evidence but does not
train models, run workflows, or write workspace state. Its interactive rawData
view lets users choose zero, one, or two dimensions for scalar, curve, or filled
two-dimensional color-contour display and set the remaining slice coordinates.

See [user_doc/README.md](user_doc/README.md) for the user-workflow guidance followed
primarily by the user's AI agent, and [dev_doc/README.md](dev_doc/README.md) for
architecture and contribution rules. The checked-in
[examples](examples/README.md) preserve complete reference workspaces, including
the former HFSS task; examples are tracked in Git but excluded from wheel and sdist
artifacts. The top-level benchmark automation follows the same distribution
exclusion but remains runnable directly from a source checkout.
