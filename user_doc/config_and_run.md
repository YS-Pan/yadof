# Config And Run

`project/config.py` is the main user-editable settings file for running optimization.
It should contain run settings, not task physics. Variables, objective names, rawData
shape, and cost definitions belong in `project/job_template/`.

## Common Local Settings

```python
EVALUATION_MODE = "local"
JOBS_DIR = PROJECT_ROOT / "jobs"
EVALUATION_TIMEOUT_SEC = 6 * 60 * 60
LOCAL_EVALUATION_MAX_WORKERS = 1
```

Use local mode for first smoke tests. Keep `LOCAL_EVALUATION_MAX_WORKERS = 1` for
HFSS or other simulators that may not run safely in parallel on one machine. Raise it
only for workflows that are known to be parallel-safe, such as pure-Python synthetic
workflows.

## Common Distributed Settings

```python
EVALUATION_MODE = "distributed"
HTCONDOR_PYTHON_EXE = "C:/ProgramData/miniconda3/envs/yadof/python.exe"
HTCONDOR_REQUEST_CPUS = 4
HTCONDOR_REQUEST_MEMORY = "8GB"
HTCONDOR_REQUEST_DISK = "5GB"
HTCONDOR_REQUIREMENTS = '(OpSys == "WINDOWS") && (TARGET.YADOF_RAMDISK =?= True)'
```

`HTCONDOR_PYTHON_EXE` must exist on every worker that can match the job. CPU and
memory requests should match the real simulator workload. For HFSS, keep
`HTCONDOR_REQUEST_CPUS` aligned with `YADOF_HFSS_JOB_CPUCORE` in `HTCONDOR_ENVIRONMENT`.

`JOBS_DIR` is the submit-side prepared-job folder. Worker scratch placement is an
HTCondor execute-machine setting, not `JOBS_DIR`.

## Optimizer Settings

```python
OPTIMIZE_POPULATION_SIZE = 200
OPTIMIZE_RANDOM_SEED = 20260624
```

Population size is the number of real evaluations requested per generation. Larger
populations use more simulator time but provide more data per generation.

## Surrogate Settings

```python
OPTIMIZE_SURROGATE_ALPHA = 3
OPTIMIZE_SURROGATE_BETA = 3
OPTIMIZE_SURROGATE_EXPLORATION_FRACTION = 0.10
```

To keep the GPSAF entry point but avoid surrogate calls, use:

```python
OPTIMIZE_SURROGATE_ALPHA = 1
OPTIMIZE_SURROGATE_BETA = 0
```

Increase surrogate settings only after the raw workflow and cost calculation are
healthy.

## Smoke Tests

A lightweight default test run should not start HFSS:

```powershell
pytest -q
```

A one-individual real local smoke test:

```powershell
@'
from project.evaluate_manager.api import evaluate_population
from project.job_template import api as job_template_api

population = ((0.5,) * job_template_api.get_variable_count(),)
costs = evaluate_population(population, mode="local", timeout_sec=5400)
print(costs)
'@ | python -
```

Check the newest job folder under `project/jobs/` after the smoke test:

- `individual_metadata.json` should end with `status = "done"`.
- `rawData/` should contain `.npz` files.
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

1. finds and activates Conda,
2. finds HTCondor,
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

`start_optimization_from_config.py` reads `project/config.py`, prints the active
settings, then calls `project.optimize.api.run_generations()`.

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
