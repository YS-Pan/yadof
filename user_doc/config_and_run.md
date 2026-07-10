# Config And Run

`project/config.py` is the short, user-editable key config for a normal optimization campaign. `project/config_all.py` contains the full set of defaults grouped by area. Both files contain settings only; task physics, variables, objective names, rawData shape, and cost definitions belong in `project/job_template/`.

`project/config_all.py` imports `project/config.py`, so key values in `config.py` override the matching full defaults. Advanced users can inspect or edit `config_all.py`, but most new runs should only need `config.py`.

## Common Local Settings

```python
EVALUATION_MODE = "local"
EVALUATION_TIMEOUT_SEC = 6 * 60 * 60
```

Local mode is best for first smoke tests. If you need local concurrency for a pure-Python or otherwise parallel-safe workflow, set `LOCAL_EVALUATION_MAX_WORKERS` in `config_all.py` or add that setting to `config.py`. Keep it at `1` for HFSS unless you have confirmed multiple local simulator subprocesses are safe on that machine.

`JOBS_DIR` is the submit-side prepared-job folder. Worker scratch placement is an HTCondor execute-machine setting, not `JOBS_DIR`.

## Common Distributed Settings

```python
EVALUATION_MODE = "distributed"
HTCONDOR_EXECUTABLE_MODE = "workflow"
HTCONDOR_PYTHON_EXE = "python"
HTCONDOR_REQUEST_CPUS = 4
HTCONDOR_REQUEST_MEMORY = "8GB"
HTCONDOR_REQUEST_DISK = "5GB"
HFSS_JOB_CPUCORE = HTCONDOR_REQUEST_CPUS
HFSS_PARALLEL_TASKS = 1
HFSS_NON_GRAPHICAL = True
```

`HTCONDOR_EXECUTABLE_MODE = "workflow"` writes `executable = workflow.py` and `transfer_executable = True` in each submit file. This is the preferred Windows HTCondor pattern for this project because it avoids brittle absolute-interpreter submit paths. `HTCONDOR_PYTHON_EXE` is used only when `HTCONDOR_EXECUTABLE_MODE = "python"`; if you choose that fallback, use an executable name or path valid on every matching worker.

For HFSS jobs, keep `HFSS_JOB_CPUCORE` aligned with `HTCONDOR_REQUEST_CPUS`. The submit file requests `HTCONDOR_REQUEST_CPUS`, and the generated HTCondor environment passes `HFSS_JOB_CPUCORE` to `workflow.py` as `YADOF_HFSS_JOB_CPUCORE`.

The default `HTCONDOR_ENVIRONMENT` in `config_all.py` uses HTCondor's quoted, whitespace-separated environment syntax and redirects Windows profile/temp folders into job-local directories.

When `evaluate_manager` prepares a distributed or local job folder, it copies both `project/config.py` and `project/config_all.py` into that job folder. This keeps the key campaign settings and full default context with the job payload.

## Optimizer Settings

```python
OPTIMIZE_POPULATION_SIZE = 200
```

Population size is the number of real evaluations requested per generation. Larger populations use more simulator time but provide more data per generation.

Advanced optimizer and surrogate settings, including random seeds, NSGA-III controls, and surrogate-assistance pressure, live in `project/config_all.py`.

## Smoke Tests

A lightweight default test run should not start HFSS:

```powershell
pytest -q
```

A one-individual real local smoke test:

```powershell
@"
from project.evaluate_manager.api import evaluate_population
from project.job_template import api as job_template_api

population = ((0.5,) * job_template_api.get_variable_count(),)
costs = evaluate_population(population, mode="local", timeout_sec=5400)
print(costs)
"@ | python -
```

Check the newest job folder under `project/jobs/` after the smoke test:

- `individual_metadata.json` should end with `status = "done"`.
- `rawData/` should contain `.npz` files.
- `config.py` and `config_all.py` should be present.
- `cost.json` should not exist.
- `calc_cost.py` should not be copied into the job folder.

## Full Optimization Launch

The Windows launcher is:

```powershell
.\start_optimization_aedtopt.cmd
```

Before running it, check the constants near the top of the file:

```bat
set "CONDA_ENV_NAME=yadof"
set "GENERATION_COUNT=50"
set "START_GENERATION=0"
```

The launcher:

1. finds and activates Conda from the current machine's Conda/PATH setup,
2. finds HTCondor from `PATH`, existing `CONDOR_LOCATION`, or Program Files locations,
3. prints pool and queue status,
4. sets `YADOF_GENERATIONS`, `YADOF_START_GENERATION`, `YADOF_PROGRESS`, and `YADOF_FAIL_ON_ALL_INF`,
5. runs `start_optimization_from_config.py`.

For a direct Python launch:

```powershell
$env:YADOF_GENERATIONS = "10"
$env:YADOF_START_GENERATION = "0"
$env:YADOF_PROGRESS = "1"
python -u start_optimization_from_config.py
```

`start_optimization_from_config.py` reads the full config from `project/config_all.py`, prints the active settings, then calls `project.optimize.api.run_generations()`.

## Failure Clues

If a run fails, inspect:

- recent `project/jobs/<job_name>/metadata.json`,
- `project/jobs/<job_name>/individual_metadata.json`,
- `stdout.txt`, `stderr.txt`, `condor.log`, or `batch.log` when present,
- `project/recorded_data/indMeta.jsonl`.

Common causes:

- wrong `.aedt` project or design name in `workflow.py`,
- missing active `_com.py` file in `job_template`,
- missing or wrong Python/PyAEDT environment on workers,
- HTCondor resource requests too low,
- rawData `.npz` metadata missing `schema_version` or `shape`,
- `calc_cost.py` expecting rawData names that `workflow.py` did not write.
