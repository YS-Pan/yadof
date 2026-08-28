# yadof-benchmark developer guide

This directory describes the current independent package only. Start with
[architecture.md](architecture.md), then read [workspace_format.md](workspace_format.md)
for authoring/loading and [run_format.md](run_format.md) for persistence/recovery.
User-facing behavior is normative in `../user_doc/` and must change with the code.

The package boundary is intentional: `yadof-benchmark` depends on the public
installed `yadof` API, while `yadof` does not import benchmark orchestration or
ship simulator baselines. The source repository may develop both projects
together, but each has its own distribution, console script, wheel, tests, version,
and documentation resources.

Any change must preserve these invariants:

- the only editable workflow program is workspace `benchmark.py`;
- planning executes Python but performs no simulator work or run writes;
- strategies are opaque complete `optimization.py` files;
- runs freeze their workflow, resources, baselines, strategies, driver, and plan;
- resume uses only the run-owned driver and snapshots;
- postprocessing is durable attempt-based work after cell collection;
- algorithm-specific registries and acceptance decisions stay outside the runner.
