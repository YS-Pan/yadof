# benchmark automation developer guide

`dev_doc/` is the entry point for maintaining the benchmark runner. It borrows
the current-view documentation approach from yadof while deliberately keeping a
smaller contract: this guide defines the development workflow, and
[`architecture.md`](architecture.md) describes the system shape and invariants.

Read the repository [`README.md`](../README.md) first for the benchmark's purpose,
command surface, evidence semantics, and execution-risk policy. Read
`architecture.md` before changing runner behavior, configuration structure,
baseline handling, execution state, collection, or reporting.

## Repository boundary

The repository tracks the runner, configuration, tests, strategy templates,
developer/user documentation, frozen baseline metadata, and frozen baseline task
inputs. A baseline is part of the reproducibility contract: never edit a baseline
in place; create a new identity and update `benchmark.toml` explicitly.

The following directories are local generated state and are intentionally ignored
by Git:

- `.assembled/` and `.staging/`: disposable baseline assembly and validation work;
- `runs/`: command logs, attempt workspaces, collected evidence, and reports.

Do not delete or rewrite existing generated evidence merely because Git ignores
it. Run immutability and retention are runtime contracts independent of version
control. `history_snapshots/` is not ignored because a future explicitly selected
snapshot is a benchmark input and must carry provenance like a baseline.

## Development environment

Use the outer workspace's fixed interpreter and run commands from the outer
workspace directory:

```powershell
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" --help
& ".\.venv\Scripts\python.exe" ".\benchmark_automation\benchmark.py" plan `
  --suite structural-canary
```

The runner consumes the regularly installed yadof package from that environment.
Do not edit `.venv/Lib/site-packages`, inject the yadof source checkout through
`PYTHONPATH`, or create a second copy of runner modules for testing.

## Change and verification workflow

1. Inspect the current Git status and preserve unrelated work.
2. Read the relevant runner/config/tests and the architecture sections affected by
   the change.
3. Keep benchmark-specific orchestration here. Reusable single-workspace yadof
   mechanisms belong in yadof, as described in the root README.
4. Add or update focused unit tests for behavior changes.
5. Run the unit suite with a fresh absolute pytest base directory and the cache
   provider disabled. For example, replace `<fresh-temp>` below with a new empty
   directory outside the repository:

   ```powershell
   & ".\.venv\Scripts\python.exe" -m pytest -q `
     ".\benchmark_automation\tests" `
     --basetemp "<fresh-temp>" -p no:cacheprovider
   ```

6. Run the no-write `plan` command for configuration or matrix changes. Run
   `preflight` when baseline, strategy, resource, or yadof integration changes.
7. Do not start smoke tests, optimization cells, collection-time model inference,
   or performance campaigns solely as a development check. Apply the cost/risk
   rules in the root README and obtain authorization when required.
8. Review the final diff and run `git diff --check` before committing.

Update `architecture.md` whenever file roles, data flow, persistence, public
schemas, or invariants change. Update the root README whenever operators need to
change how they configure, execute, resume, collect, interpret, or diagnose a
benchmark. Small prose corrections need only targeted link/path checks.

## Encoding and paths

Text files are UTF-8. Preserve non-ASCII paths and content, and use explicit UTF-8
when a PowerShell command reads text for editing. Resolve inputs from
`benchmark.toml` and the benchmark root rather than the caller's current directory.
Keep subprocess commands as argument lists; do not build shell command strings.
