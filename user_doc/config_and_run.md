# Config And Run

`project/config/key.py` is the short, user-editable generic key config for a normal optimization campaign. `project/config/all.py` contains the full set of generic defaults grouped by area. Settings tied to one simulator live under `project/config/specific/`; the current HFSS task uses `project/config/specific/hfss.py`. Task physics, variables, objective names, rawData shape, and cost definitions still belong in `project/job_template/`.

`project/config/all.py` imports `project/config/key.py`, so values in `key.py` override matching generic defaults. Advanced users can inspect or edit `all.py`, but most new runs should only need `key.py` plus the matching file under `specific/` when their workflow uses one.

## Common Local Settings

```python
EVALUATION_MODE = "local"
EVALUATION_TIMEOUT_SEC = 6 * 60 * 60
OPTIMIZE_SMOKE_TEST_ENABLED = True
```

Local mode is best for first smoke tests. `OPTIMIZE_SMOKE_TEST_ENABLED` controls whether the normal optimization launcher runs one real midpoint individual before generation zero. The smoke test has no timeout. If you need local concurrency for a pure-Python or otherwise parallel-safe workflow, set `LOCAL_EVALUATION_MAX_WORKERS` in `all.py` or add that setting to `key.py`. Keep it at `1` for workflows whose external programs are not safe to run concurrently.

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
HTCONDOR_REQUEST_DISK_MULTIPLIER = 1.0
HTCONDOR_JOB_TIMEOUT_MODE = "auto"
HTCONDOR_JOB_TIMEOUT_SEC = 60 * 60
```

For the current HFSS adapter, the corresponding software-specific file contains:

```python
# project/config/specific/hfss.py
from .. import key as key_config

HFSS_CPUCORE_MULTIPLIER = 2
HFSS_JOB_CPUCORE = int(getattr(key_config, "HTCONDOR_REQUEST_CPUS", 1)) * HFSS_CPUCORE_MULTIPLIER
HFSS_PARALLEL_TASKS = 1
HFSS_NON_GRAPHICAL = True
```

The generated submit file uses `executable = workflow.py` with `transfer_executable = True`. Do not set Python itself as the HTCondor submit `executable`; make sure the worker can run transferred `.py` files and that slot users can access the Python installation reached by the worker file association.

`HTCONDOR_REQUEST_CPUS` is always the user-selected scheduler request. The HFSS-specific `HFSS_CPUCORE_MULTIPLIER` defaults to `2`, so a request for `3` CPUs intentionally passes `6` cores to HFSS through `YADOF_HFSS_JOB_CPUCORE`. This does not reserve six Condor CPUs: depending on the worker's slot and affinity policy, it can contend with other work or run slower. Use it only when that throughput trade-off is acceptable.

### Automatic Memory And Disk Requests

Memory and disk start from `HTCONDOR_REQUEST_MEMORY` and `HTCONDOR_REQUEST_DISK`. A **distributed** smoke test (an evaluation with no generation index) returns HTCondor's `MemoryUsage` and `DiskUsage` through the submit side and records them in job metadata. The first optimizer generation uses each smoke measurement times `HTCONDOR_RESOURCE_BOOTSTRAP_MULTIPLIER` (default `2`). Each later generation uses the previous generation's corresponding measurements after removing the highest `HTCONDOR_RESOURCE_TRIM_TOP_FRACTION` (default `0.05`) and taking the remaining maximum.

If `OPTIMIZE_SMOKE_TEST_ENABLED = False`, generation zero treats the user-entered memory and disk requests as the smoke measurements, then applies the same bootstrap multiplier. This preserves the auto policy without launching an extra real job.

The submitter never rewrites your source config. It writes the calculated effective values and their source into each job's metadata, so a missing or unreadable Condor measurement safely falls back to the configured bootstrap values. `HTCONDOR_REQUEST_DISK_MULTIPLIER` is applied after either calculation; it is `1.0` by default and can be raised when scratch capacity is deliberately abundant.

Generated `job.sub` files contain only one concrete `request_memory` and
`request_disk`; they do not use HTCondor's `retry_request_*` settings. If HTCondor
holds a job with the standard out-of-resources code for memory or disk, yadof
removes that cluster and submits the same prepared individual again with only the
exhausted resource doubled. Memory and disk retry counts are independent.

`YADOF_RESOURCE_RETRY_DOUBLINGS` in `all.py` limits these fresh submissions per
resource and defaults to `4`, giving at most `2x`, `4x`, `8x`, and `16x` requests
after the initial attempt. Set it to `0` to disable resource retries. The job's
metadata records every attempt and the final exhausted resource. Workflow errors,
submit failures, timeouts, and unrelated Condor holds are never resource-retried.
Each retry starts the workflow from the beginning and remains inside the original
whole-generation wait budget, so the initial request should still be realistic.

### Automatic Per-Job Timeouts

`EVALUATION_TIMEOUT_SEC` remains the submit-side budget for waiting for a whole distributed generation. Each individual Condor job has a separate limit:

```python
# project/config/key.py
HTCONDOR_JOB_TIMEOUT_MODE = "auto"  # or "fixed"
HTCONDOR_JOB_TIMEOUT_SEC = 60 * 60
```

In `"fixed"` mode, every normal generation job receives the configured one-hour limit. In the default `"auto"` mode:

1. The smoke test has no timeout and records its actual execution duration.
2. Generation zero uses the smoke duration times `HTCONDOR_JOB_TIMEOUT_MULTIPLIER` (default `2.0` in `all.py`). If smoke is disabled, the configured `HTCONDOR_JOB_TIMEOUT_SEC` is treated as that smoke duration.
3. Each later generation uses the preceding generation's longest remaining duration after removing the highest `HTCONDOR_JOB_TIMEOUT_TRIM_TOP_FRACTION` (default `0.10`), then applies the same multiplier. Timed-out individuals count as infinity during trimming. If their count exceeds the trim capacity, the largest finite duration is used; if no finite duration exists, the configured one-hour value is used.

The generated submit file uses HTCondor's `allowed_execute_duration`. A job that exceeds it is held by HTCondor with hold code 47; yadof records it as `timeout`, removes it from the queue, and does not retry it. `RemoteWallClockTime - CumulativeSuspensionTime` is recorded when available and workflow timestamps are the fallback measurement.

The default `HTCONDOR_ENVIRONMENT` in `all.py` uses HTCondor's quoted, whitespace-separated environment syntax. It combines generic Windows profile/temp entries with environment entries contributed by active modules under `config/specific/`.

When `evaluate_manager` prepares a distributed or local job folder, it copies the cache-free `project/config/` package into that job folder. This keeps generic key/default settings and active software-specific context with the job payload.

## Optimizer Settings

```python
OPTIMIZE_POPULATION_SIZE = 200
```

Population size is the number of real evaluations requested per generation. Larger populations use more simulator time but provide more data per generation.

Advanced optimizer and surrogate settings, including random seeds, NSGA-III controls, and surrogate-assistance pressure, live in `project/config/all.py`.

## Smoke Tests

A lightweight default test run uses reusable framework and software-integration tests. Software-specific tests use synthetic inputs or mocks; the suite does not start real simulator software or contain current-task checks:

```powershell
pytest -q
```

A one-individual real local smoke test:

```powershell
@"
from project.evaluate_manager.api import run_smoke_test
print(run_smoke_test(mode="local"))
"@ | python -
```

This public smoke-test entry point deliberately disables both the generation wait timeout and the per-job timeout. The full launcher runs the same check in the configured evaluation mode when `OPTIMIZE_SMOKE_TEST_ENABLED = True`.

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
5. runs `start_optimization_from_config.py`, which executes the optional smoke test before optimization.

For a direct Python launch:

```powershell
$env:YADOF_GENERATIONS = "10"
$env:YADOF_START_GENERATION = "0"
$env:YADOF_PROGRESS = "1"
python -u start_optimization_from_config.py
```

`start_optimization_from_config.py` reads the full generic config from `project/config/all.py`, including active `config/specific/` environment contributions, prints the active settings, runs the no-timeout smoke test when enabled, then calls `project.optimize.api.run_generations()`. A failed smoke test stops before generation zero is submitted.

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
