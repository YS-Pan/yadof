# yadof Runtime Source

`project/` contains the current modular optimization runtime described by the
architecture views and project/module blueprints under `../dev_doc/`. The
installable package and workspace/config/task-loading foundation lives under
`../src/yadof/`; it now includes safe generic workspace init/check, packaged job
preparation/local evaluation, and standalone local smoke. This tree remains the
transitional optimization, recording, surrogate, and distributed runtime until
their ordered package-migration stages are completed.

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
- `evaluate_manager/`: transitional source-layout local/HTCondor execution and
  recording handoff for the not-yet-migrated optimizer. New installed workspace
  local calls use `yadof.evaluate_manager` under `../src/`.
- `job_template/`: task-specific parameter definitions, workflow, rawData
  contract, optional simulator/input files, and rawData-to-cost logic. The
  active template decides which rawData items and objective costs exist for a
  given optimization task.
- `com_lib/`: optional adapter staging/reference files, including reference
  copies such as `hfss_com.py` and `test_com.py`. Jobs do not import this
  directory directly; copy a needed com file into `job_template/` before the
  workflow uses it. Reusable fixes made to an active adapter should be synced
  back to its `com_lib` reference copy.
- `recorded_data/`: durable archive of job names, raw variables, individual
  metadata in `indMeta.jsonl`, optimization metadata in `optMeta/`, and all
  rawData `.npz` members inside one `rawData.npz` archive. Normalized variables
  and costs are calculated dynamically through APIs.
- `surrogate/`: rawData-first surrogate training, prediction, ensemble member
  min/max intervals, and per-generation checkpoints.
- `tools/`: optional user-launched utilities. Generic tools stay directly under
  this folder; simulator-specific tools live under `tools/specific/<software>/`.
  Core runtime does not depend on tools. System-environment and HTCondor-pool
  administration tools are kept separately under `../admin_tool/`.
- `test/`: pytest coverage for local closed-loop behavior, rawData contracts,
  failure handling, dynamic history interpretation, surrogate behavior, and
  tools.
- `config/`: layered settings. `key.py` contains routine campaign choices,
  `all.py` provides the complete generic settings surface, and
  `specific/<software>.py` owns simulator-specific settings. Problem shape and
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

`project.config.all` is the full shared-settings import. Software-specific code
reads its matching module under `project.config.specific`. `job_template/` files
are intentionally mutable between optimization tasks.

## Quick Smoke Commands

```powershell
pytest -q
```

The committed suite contains framework-contract tests only. Tests tied to the
current optimization task do not belong under `project/test/`; use the ignored
root `temp/` directory for disposable task checks. After package/workspace
separation, run those checks from the relevant workspace instead.

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

- Installed package foundation: `../user_doc/package_foundation.md`
- Documentation entry point: `../dev_doc/README.md`
- Architecture views and current invariants: `../dev_doc/architecture/`
- Project blueprint overview: `../dev_doc/blueprints/00_project.md`
- Module blueprints and historical lineage: `../dev_doc/blueprints/10_modules/`
- Project terminology: `../dev_doc/terminology.md`
