# Configure, smoke, run, and inspect

## Configuration precedence

Effective values are loaded in this order:

1. validated package defaults;
2. uppercase settings in workspace `config.py`;
3. temporary API/CLI overrides for one invocation.

Unknown uppercase settings and invalid values fail before a batch starts. Loading
never rewrites config. Use `yadof check --workspace PATH` to see the selected mode
and validate paths.

Common workspace settings include `EVALUATION_MODE`, `EVALUATION_TIMEOUT_SEC`,
`LOCAL_EVALUATION_MAX_WORKERS`, `OPTIMIZE_POPULATION_SIZE`,
`OPTIMIZE_SMOKE_TEST_ENABLED`, HTCondor request/calibration/timeout settings, GPSAF
alpha/beta/gamma controls, and surrogate training controls. Task physics and problem
shape stay in `job_template/`.

## Standalone smoke

```powershell
yadof smoke-test --workspace PATH --mode local
yadof smoke-test --workspace PATH --mode distributed --real-task
```

A smoke evaluates exactly one midpoint individual with no generation index, no
per-job execution limit, and no submit-side whole-generation deadline. It succeeds
only if at least one finite objective is returned.

## Start or resume

```powershell
yadof run --workspace PATH --generations 5
yadof run --workspace PATH --start-generation 5 --generations 5
```

The pre-run real-task smoke default comes from
`OPTIMIZE_SMOKE_TEST_ENABLED`. `--smoke-test` and `--no-smoke-test` are opposite,
explicit overrides and take precedence. `--mode`, `--population-size`, and
`--random-seed` are also temporary. `--progress` enables detailed backend progress
for that invocation and restores the caller environment afterward.

When smoke is skipped, configured memory/disk and job-timeout baselines act as the
synthetic generation-zero calibration. Distributed normal jobs receive a scheduler
`allowed_execute_duration`; the submit side separately enforces a whole-generation
deadline. Memory/disk holds may be freshly resubmitted by yadof with bounded,
independent doubling. yadof diagnoses HTCondor but never installs or repairs it.

The Windows distributed submit contract runs `workflow.py` directly with
`transfer_executable=True`, `load_profile=True`, and `run_as_owner=False`. Input
transfer contains the task/job files and `worker_misc.py`, never a yadof runtime
package. Output transfer returns `rawData.zip` plus `individual_metadata.json` and
does not return `rawData/`. Missing, nested, or malformed zip contents become
per-individual diagnostics.

## History and tools

```powershell
yadof view cost --workspace PATH [--status completed] [-o NAME.png]
yadof view time --workspace PATH [--status all] [-o NAME.png]
yadof history clear --workspace PATH --yes
yadof task adapters
yadof task copy-adapter test_com.py --workspace PATH
```

Relative plot names are written below `.yadof/tool_output/`. Destructive history
clear requires interactive confirmation or `--yes`, validates its exact workspace
targets, clears only that workspace, and recreates the jobs directory.

## Python APIs

Every stateful public call takes a workspace:

```python
from yadof.evaluate_manager import evaluate_population, run_smoke_test
from yadof.optimize import run_generations

run_smoke_test("D:/work/study-a", mode="local")
run_generations("D:/work/study-a", 3, start_generation=0)
```
