# yadot project v3 skeleton

This directory is the v3 modular optimization framework described by
`spec v3.md`.

## Module boundaries

- `optimize/`: optimizer-facing entry point. It works in normalized variable
  space and asks `evaluate_manager.api` for real evaluations.
- `evaluate_manager/`: job creation and execution management. Local mode is
  implemented; distributed/HTCondor is an explicit stub for later wiring.
- `job_template/`: task-specific files. `workflow.py` converts variables to
  flat `rawData/*.npz` files. `calc_cost.py` converts rawData to cost and is
  not copied into jobs.
- `recorded_data/`: durable real-evaluation archive. It stores raw variables,
  rawData, and metadata only. Costs and normalized variables are calculated
  dynamically through APIs.
- `surrogate/`: minimal nearest-rawData surrogate that preserves the
  `normalized variables -> rawData -> cost` interface.
- `tools/`: optional user tools. Core runtime does not depend on it.

## Quick smoke commands

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

