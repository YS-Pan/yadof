# yadof-benchmark developer guide

This directory describes the independent `yadof-benchmark` package. Read
[architecture.md](architecture.md), [workspace_format.md](workspace_format.md),
and [run_format.md](run_format.md). User-facing behavior in `../user_doc/` is
normative and must change with the code.

The package depends only on public installed yadof behavior. yadof does not import
benchmark orchestration or ship simulator baselines.

Current invariants are:

- `benchmark.py` is the only editable workflow program;
- one workspace owns one execution and direct outputs;
- another execution means another workspace;
- execution uses installed packages and records their versions once in
  `runtime.json`;
- there is no run ID, `runs/`, resume command, attempt hierarchy, cross-run
  timing history, or copied driver/workflow/strategy snapshot;
- strategy modules are complete, opaque `optimization.py` files;
- default seeds are `[101]`;
- default standard budget is population 200 x 50 generations;
- a comparison containing `slow_surrogate=True` defaults to 15 generations;
- explicit positive budgets and explicit seed lists override defaults;
- cell IDs are short ordinals and semantic identity stays in `spec.json`;
- individual simulation failures/non-finite completions do not invalidate a cell
  when attempts are complete and finite contract-valid metric evidence remains;
- missing attempts, no finite evidence, contract failure, initial-population
  failure, or missing metric does invalidate a cell;
- same-baseline/same-seed arms require matching baseline input digest, planned and
  attempted budget, and generation-0 normalized population before pairing;
- planning performs no simulator work and writes no execution evidence;
- cell concurrency and baseline simulation concurrency are separate controls;
- terminal result publication is a fatal persistence boundary before FIFO refill;
- every collected cell owns a cost plot and baseline domain output;
- inspect is bounded, read-only, and uses only current-workspace timing evidence;
- a visible Windows detached console remains open after the benchmark command
  finishes so its terminal result can be reviewed; hidden detach remains automatic;
- a successful full-budget detached launch receipt is the AI-agent handoff
  boundary: absent an explicit monitoring request, the agent does not poll or keep
  its current turn open merely to await completion;
- algorithm rankings and acceptance decisions remain outside the runner.

The `0.2` workspace format intentionally makes no old-workspace compatibility
promise.
