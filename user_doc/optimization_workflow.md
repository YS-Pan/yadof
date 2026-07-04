# User Workflow For A New Optimization Task

This is the normal user-side path for turning a simulation or custom evaluator into
a yadof optimization run.

## 1. Prepare Simulator Or Custom Input Files

Put task files that the workflow needs directly under `project/job_template/`.

Examples:

- HFSS project: `project/job_template/your_model.aedt`
- Custom lookup tables or Python data files used by `workflow.py`
- Any simulator-specific auxiliary files that must be copied into each job folder

Do not put run outputs into `job_template/` by hand. Each prepared job gets its own
job folder under `project/jobs/` or the configured `JOBS_DIR`.

## 2. Prepare `parameters_constraints.py`

`project/job_template/parameters_constraints.py` defines optimization variables and
optional constraints.

For HFSS tasks, variables can often be generated from the `.aedt` file:

```powershell
python project\tools\hfss_get_para_and_range_direct.py --project project\job_template\your_model.aedt --design YourDesignName
```

If the `.aedt` project has exactly one design, `--design` can usually be omitted.
The direct tool tries to read optimization-enabled variables and writes the current
`Parameter(...)` format.

Constraints still need to be written by the user or by an AI assistant. A constraint
expression should be non-negative when it is satisfied. For example:

```python
CONSTRAINTS = (
    "slot_l - slot_w - 30",
)
```

A typical variable file looks like:

```python
from __future__ import annotations

try:
    from .parameters_constraints_class import Parameter
except ImportError:
    from parameters_constraints_class import Parameter

PARAMETERS = (
    Parameter("parameter_a", ((10, 30),), unit="mm"),
    Parameter("parameter_b", ((1, 3),), unit="mm"),
    Parameter("mode_index", (1, 2, 3), unit=""),
)

CONSTRAINTS = ()


def get_parameters() -> tuple[Parameter, ...]:
    return tuple(PARAMETERS)
```

Continuous ranges use `(low, high)`. Discrete choices use plain values. Mixed ranges
are also allowed because each range element maps to one segment of normalized `[0, 1]`.

## 3. Copy Needed `_com.py` Files Into `job_template`

Choose adapter files from `project/com_lib/`, read the matching document under
`user_doc/com_lib/`, then copy the needed files into `project/job_template/`.

Examples:

```text
project/com_lib/hfss_com.py  ->  project/job_template/hfss_com.py  ->  user_doc/com_lib/hfss_com.md
project/com_lib/test_com.py  ->  project/job_template/test_com.py  ->  user_doc/com_lib/test_com.md
```

`workflow.py` imports adapters from its own job folder, for example:

```python
from hfss_com import analyze, save_modal, solver_init
```

Do not import adapters from `project.com_lib` in `workflow.py`. Prepared jobs are
meant to be self-contained.

## 4. Write `workflow.py` And `calc_cost.py`

`workflow.py` owns:

- reading the current individual variables,
- calling HFSS or custom code,
- writing one or more `.npz` files directly under `rawData/`,
- writing `individual_metadata.json`,
- recording failure information when possible.

`calc_cost.py` owns:

- loading rawData,
- extracting the values that matter for objectives,
- returning a tuple of minimization costs,
- adding a constraint cost when `CONSTRAINTS` is non-empty.

The workflow must not calculate final cost. The job folder should not contain
`cost.json`.

## 5. Edit `project/config.py`

Common settings users edit:

- `EVALUATION_MODE`: `"local"` for local subprocess runs, `"distributed"` for HTCondor.
- `JOBS_DIR`: where prepared job folders are written.
- `EVALUATION_TIMEOUT_SEC`: generation-level timeout budget.
- `LOCAL_EVALUATION_MAX_WORKERS`: local subprocess concurrency; keep it at `1` for simulators that cannot run safely in parallel.
- `HTCONDOR_PYTHON_EXE`: Python executable available on every HTCondor worker.
- `HTCONDOR_REQUEST_CPUS`, `HTCONDOR_REQUEST_MEMORY`, `HTCONDOR_REQUEST_DISK`: distributed job resource requests.
- `OPTIMIZE_POPULATION_SIZE`: number of real evaluations per generation.
- `OPTIMIZE_SURROGATE_ALPHA` and `OPTIMIZE_SURROGATE_BETA`: surrogate-assistance pressure.

Problem shape, variable names, and objective names come from `job_template`, not from
`config.py`.

## 6. Run A Smoke Test Before A Full Optimization

Before a long run, test one individual.

For a real workflow smoke test in local mode:

```powershell
@'
from project.evaluate_manager.api import evaluate_population
from project.job_template import api as job_template_api

population = ((0.5,) * job_template_api.get_variable_count(),)
costs = evaluate_population(population, mode="local", timeout_sec=5400)
print(costs)
'@ | python -
```

For a lightweight framework test that should not start HFSS:

```powershell
pytest -q
```

When the smoke test is healthy, run the configured optimization:

```powershell
.\start_optimization_aedtopt.cmd
```

For a direct Python launch, set environment variables and call the launcher:

```powershell
$env:YADOF_GENERATIONS = "50"
$env:YADOF_START_GENERATION = "0"
$env:YADOF_PROGRESS = "1"
python -u start_optimization_from_config.py
```

## 7. Inspect And Adjust

After a run starts, inspect generated job folders and recorded history when needed:

- `project/jobs/<job_name>/individual_metadata.json`: workflow status and timing.
- `project/jobs/<job_name>/rawData/*.npz`: job-local rawData outputs.
- `project/recorded_data/indMeta.jsonl`: compact recorded individual metadata.
- `project/recorded_data/rawData.npz`: archived rawData from completed and recorded jobs.

If you change `calc_cost.py`, historical costs are recalculated from rawData. If you
change the simulation file or workflow so old rawData is no longer comparable, remove
or archive old recorded history before continuing.
