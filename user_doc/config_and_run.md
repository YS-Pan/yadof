# Config And Run

`project/config/key.py` is the short, user-editable generic key config for a normal optimization campaign. `project/config/all.py` contains the full set of generic defaults grouped by area. Settings tied to one simulator live under `project/config/specific/`; the current HFSS task uses `project/config/specific/hfss.py`. Task physics, variables, objective names, rawData shape, and cost definitions still belong in `project/job_template/`.

`project/config/all.py` imports `project/config/key.py`, so values in `key.py` override matching generic defaults. Advanced users can inspect or edit `all.py`, but most new runs should only need `key.py` plus the matching file under `specific/` when their workflow uses one.

## Common Local Settings

```python
EVALUATION_MODE = "local"
EVALUATION_TIMEOUT_SEC = 6 * 60 * 60
```

Local mode is best for first smoke tests. If you need local concurrency for a pure-Python or otherwise parallel-safe workflow, set `LOCAL_EVALUATION_MAX_WORKERS` in `all.py` or add that setting to `key.py`. Keep it at `1` for workflows whose external programs are not safe to run concurrently.

`JOBS_DIR` is the submit-side prepared-job folder. Worker scratch placement is an HTCondor execute-machine setting, not `JOBS_DIR`.

## Common Distributed Settings

This section assumes an administrator has already installed yadof and its
dependencies and has configured the HTCondor pool. Users select and use that
environment; they do not configure or repair its software or hardware.

```python
# project/config/key.py
EVALUATION_MODE = "distributed"
HTCONDOR_REQUEST_CPUS = 4
HTCONDOR_REQUEST_MEMORY = "8GB"
HTCONDOR_REQUEST_DISK = "5GB"
```

For the current HFSS adapter, the corresponding software-specific file contains:

```python
# project/config/specific/hfss.py
from .. import key as key_config

HFSS_JOB_CPUCORE = int(getattr(key_config, "HTCONDOR_REQUEST_CPUS", 1))
HFSS_PARALLEL_TASKS = 1
HFSS_NON_GRAPHICAL = True
```

The generated submit file uses `executable = workflow.py` with `transfer_executable = True`. Do not set Python itself as the HTCondor submit `executable`; make sure the worker can run transferred `.py` files and that slot users can access the Python installation reached by the worker file association.

For HFSS jobs, keep `HFSS_JOB_CPUCORE` aligned with `HTCONDOR_REQUEST_CPUS`. The submit file requests `HTCONDOR_REQUEST_CPUS`, and the generated HTCondor environment passes `HFSS_JOB_CPUCORE` to `workflow.py` as `YADOF_HFSS_JOB_CPUCORE`.

The default `HTCONDOR_ENVIRONMENT` in `all.py` uses HTCondor's quoted, whitespace-separated environment syntax. It combines generic Windows profile/temp entries with environment entries contributed by active modules under `config/specific/`.

When `evaluate_manager` prepares a distributed or local job folder, it copies the cache-free `project/config/` package into that job folder. This keeps generic key/default settings and active software-specific context with the job payload.

## Optimizer Settings

```python
OPTIMIZE_POPULATION_SIZE = 200
```

Population size is the number of real evaluations requested per generation. Larger populations use more simulator time but provide more data per generation.

Advanced optimizer and surrogate settings, including random seeds, NSGA-III controls, and surrogate-assistance pressure, live in `project/config/all.py`.

## Smoke Tests

A lightweight default test run uses only generic framework tests and does not contain current-task simulator checks:

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
- `config/key.py`, `config/all.py`, and the expected active files under `config/specific/` should be present.
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

`start_optimization_from_config.py` reads the full generic config from `project/config/all.py`, including active `config/specific/` environment contributions, prints the active settings, then calls `project.optimize.api.run_generations()`.

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
