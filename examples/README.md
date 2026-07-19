# Example workspaces

`examples/` contains complete, Git-tracked workspace references for studying task
layout and adapting a real task. These directories are source-repository examples;
they are not installed package resources, are excluded from wheel and sdist
artifacts, and should not be edited or used in place as campaign workspaces.

## `hfss-newchoke`

`hfss-newchoke/` preserves the former HFSS optimization task after the package
conversion. It demonstrates:

- a versioned `.yadof/workspace.json` marker and task-level `config.py`;
- parameter definitions, workflow orchestration, and cost calculation under
  `job_template/`;
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
