# Module blueprint: packaged adapter resources

## Resource and activation model

Reusable `*_com.py` references live in `src/yadof/_resources/adapters/` and are
immutable package resources. The CLI lists them and copies one selected adapter into
workspace `job_template/` without overwriting edits. A copied task-local adapter is
the active runtime file and is included in prepared jobs; jobs never import the
packaged resource in place.

## Adapter boundary

Adapters translate task values and simulator/custom APIs into neutral rawData saves.
They may own connection/setup/export mechanics and output dimensionality, but not a
concrete project/design, parameter set, objective name/count, cost threshold,
credential, or machine path. Those belong to the workspace workflow/config/cost.

Agent-facing usage references live under `agent_doc/adapters/`. Active reusable
adapter fixes are made in package resource source and copied into workspaces only by
explicit user action; existing workspace edits are not silently upgraded.

## Test adapter

The pure-Python `test_com` resource provides compact generic and HFSS-shaped profiles
plus a deterministic 30-input large-scale profile with distinct 0D, 1D, 2D, and 3D
blocks. It exercises workflow/rawData/surrogate mechanics without external software.
Profile output shape belongs to the adapter; objective windows and cost policy remain
workspace task concerns.

## Invariants

- Active adapter code is self-contained in the job folder.
- Adapter modules never import a concrete workspace or yadof runtime on workers.
- New simulator families do not change core optimization/evaluation contracts.
