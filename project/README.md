# yadof project v3

`project/` contains the v3 modular optimization framework described by the
current architecture views and project/module blueprints under `../dev_doc/`.

The central contract is:
```text
normalized variables -> rawData -> cost
```

Real evaluations and surrogate predictions both pass through rawData. Cost is
always derived from rawData by the current `job_template/calc_cost.py`; it is
not stored as a durable source file.

## Modules

- `optimize/`: optimizer-facing entry points, GPSAF-style search, history warm
  start, and optional surrogate-assisted candidate selection.
- `evaluate_manager/`: job creation, local execution, optional
  Distributed/HTCondor execution, timeout/failure isolation, and handoff to
  `recorded_data`.
- `job_template/`: task-specific parameter definitions, workflow, rawData
  contract, optional simulator/input files, and rawData-to-cost logic. The
  active template decides which rawData items and objective costs exist for a
  given optimization task.
- `com_lib/`: optional adapter staging/reference files, including reference
  copies such as `hfss_com.py` and `test_com.py`. Jobs do not import this
  directory directly; copy a needed com file into `job_template/` before the
  workflow uses it.
- `recorded_data/`: durable archive of job names, raw variables, individual
  metadata in `indMeta.jsonl`, optimization metadata in `optMeta/`, and all
  rawData `.npz` members inside one `rawData.npz` archive. Normalized variables
  and costs are calculated dynamically through APIs.
- `surrogate/`: rawData-first surrogate training, prediction, ensemble member
  min/max intervals, and per-generation checkpoints.
- `tools/`: optional user-launched utilities. Core runtime does not import or
  depend on tools.
- `test/`: pytest coverage for local closed-loop behavior, rawData contracts,
  failure handling, dynamic history interpretation, surrogate behavior, and
  tools.
- `config.py`: shared runtime and optimizer settings. Problem shape and
  objective names come from `job_template.api`, not from config.

## API Boundary

Core modules should communicate through public API files:

```text
optimize/api.py
evaluate_manager/api.py
job_template/api.py
recorded_data/api.py
surrogate/api.py
```

`config.py` is the main allowed direct cross-module import. `job_template/`
files are intentionally mutable between optimization tasks.

## Quick Smoke Commands

```powershell
pytest -q
```

The real HFSS local-pipeline smoke test is skipped by default so ordinary test
runs do not launch AEDT. Set `YADOF_RUN_HFSS_TESTS=1` when you intentionally
want to run that smoke path on a machine with PyAEDT/AEDT configured.

```powershell
$env:YADOF_RUN_HFSS_TESTS = '1'
$env:YADOF_HFSS_SMOKE_TIMEOUT_SEC = '5400'
pytest -q project\test\test_real_local_pipeline.py
```

```powershell
@'
from project.optimize.api import run_one_generation
from project.surrogate.api import train

result = run_one_generation(generation_index=1, population_size=2)
state = train(generation_index=1)
print(result.costs)
print(state.checkpoint_path)
'@ | python -
```

## Useful Docs

- Documentation entry point: `../dev_doc/README.md`
- Architecture views and current invariants: `../dev_doc/architecture/`
- Project blueprint overview: `../dev_doc/blueprints/00_project.md`
- Module blueprints and historical lineage: `../dev_doc/blueprints/10_modules/`
- Project terminology: `../dev_doc/terminology.md`
