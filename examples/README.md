# Example workspaces

`examples/` contains complete, Git-tracked workspace references for studying task
layout and adapting a real task. These directories are source-repository examples;
they are not installed package resources, are excluded from wheel and sdist
artifacts, and should not be edited or used in place as campaign workspaces.

## `hfss-newchoke`

`hfss-newchoke/` preserves the former HFSS optimization task after the package
conversion. It demonstrates:

- a versioned `.yadof/workspace.json` marker and task-level `config.py`;
- parameter definitions and workflow orchestration under `job_template/`, with
  cost and optimization composition under fixed `submit/`;
- task-variable HFSS/objective code calling yadof worker/cost helpers for invariant
  lifecycle, transport, rawData, and cost mechanics;
- an active task-local `hfss_com.py` copied from the packaged adapter resources;
- task-specific HFSS settings and an AEDT model asset;
- retained parameter-definition history useful for understanding the task's
  evolution.

The example defaults to distributed evaluation and expects a compatible HFSS/PyAEDT
environment, licensing, and HTCondor deployment. `yadof check` can inspect its
structure without launching the simulator, but smoke tests and runs may execute
expensive external software.

## Use an example

Copy the whole example to a user-owned location before editing or running it:

```powershell
Copy-Item -Recurse .\examples\hfss-newchoke D:\work\hfss-newchoke
yadof check --workspace D:\work\hfss-newchoke
```

Keep generated jobs, recorded data, checkpoints, logs, credentials, and private
task assets in the external copy unless they are intentionally curated as part of a
new repository example.

## Copyable optimization programs

`optimization-programs/` contains source-checkout-only `submit/optimization.py`
references rather than complete workspaces. Every Python program has a same-basename
Markdown guide:

- `real_only.py` uses only authoritative real GA/NSGA-III evaluation;
- `sequential_surrogate.py` evaluates first and then trains PCA/SVD on current data;
- `overlapped_surrogate.py` overlaps real evaluation with lag-one PCA/SVD training;
- `split_cost_surrogate_data.py` keeps full optimizer history while training on an
  explicit evidence subset;
- `posterior_assisted_fallback.py` demonstrates the current typed qNEHVI readiness
  block and honest full-real fallback.

Copy one Python file into a complete initialized workspace as
`submit/optimization.py`, review its program identity and dependencies, and run
`yadof check`. These files intentionally do not include configuration, costs,
simulator code, credentials, or task data.
