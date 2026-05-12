# yadot project v3

`project/` contains the v3 modular optimization framework described by
`../spec 20260502.md`.

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
- `evaluate_manager/`: job creation, local execution, timeout/failure
  isolation, and handoff to `recorded_data`. Distributed/HTCondor mode is still
  a planned backend.
- `job_template/`: task-specific parameter definitions, workflow, rawData
  contract, simulator stand-in or adapter files, and rawData-to-cost logic.
  The default test task currently returns three bounded costs in `[0, 1]`.
- `recorded_data/`: durable archive of job names, raw variables, rawData files,
  rawData metadata, and job metadata. Normalized variables and costs are
  calculated dynamically through APIs.
- `surrogate/`: rawData-first surrogate training, prediction, uncertainty
  intervals, and per-generation checkpoints.
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

- Project prompt overview: `../prompt/00_project.md`
- Module prompts: `../prompt/10_modules/`
- Reference ancestry map: `../reference_map.md`
- Architecture views: `../architecture/`
- Highest-level specification: `../spec 20260502.md`
