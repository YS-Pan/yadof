# benchmark automation developer guide

`dev_doc/` is the entry point for maintaining the benchmark runner. It follows the
current-view, contract, and generative-blueprint discipline used by yadof's root
`dev_doc/`, while keeping ownership local to this source-checkout tool.

Read the repository [`README.md`](../README.md) first for the benchmark's purpose,
command surface, evidence semantics, and execution-risk policy. Read
[`AGENTS.md`](../AGENTS.md) for the bounded evidence route. The root yadof
architecture remains authoritative for the installed-package/workspace boundary;
these nested documents own benchmark planning, identity, execution, progress, ETA,
collection, reporting, and disclosure.

## Required reading order

Perform the first benchmark-development context pass in this order:

1. Read [the operator-document contract](skill/operator_doc.md), then the root
   benchmark `README.md` and `AGENTS.md`.
2. Read [the architecture contract](skill/architecture.md), then every file below
   `architecture/` in full, beginning with
   [the index](architecture/00_architecture_index.md). The former monolithic
   [`architecture.md`](architecture.md) remains as a compatibility orientation;
   the split views are authoritative.
3. Read [the terminology contract](skill/terminology.md), then
   [`terminology.md`](terminology.md) in full.
4. Read [the toDo contract](skill/toDo.md) and every benchmark-local toDo when a
   `toDo/` directory exists. An absent directory means there is no local pending
   work.
5. List the `blueprints/` tree, read
   [the blueprint contract](skill/blueprints.md), and perform its targeted pass.
6. Apply [the change-record contract](skill/change_records.md). One completed
   repository change receives one record under the root `dev_doc/change_records/`.

Do not start from generated runs or load large evidence to learn the runner. Use
architecture and blueprints for current contracts, source/tests for executable
detail, and one targeted run artifact only for a concrete runtime diagnosis.

## Source-checkout boundary

The yadof repository tracks this runner, configuration, tests, strategy templates,
developer/user documentation, and editable baseline task templates below top-level
`benchmark_automation/`. This tree is downloadable with a yadof source checkout but
is not an installed `yadof` package or runtime resource. Baselines may be edited in
place at any time. Reproducibility belongs to the immutable baseline snapshot copied
into each new run, not to the live source template.

The following directories are local generated state and are intentionally ignored
by Git:

- `.assembled/` and `.staging/`: disposable baseline assembly and validation work;
- checkout `temp/<run-id>/`: command logs, attempt workspaces, collected evidence,
  and reports, with no additional benchmark/task container layer.

Do not delete or rewrite existing generated evidence merely because Git ignores
it. Run immutability and retention are runtime contracts independent of version
control. `history_snapshots/` is not ignored because a future explicitly selected
snapshot is a benchmark input and must carry provenance like a baseline.

## Development environment

Run commands from the yadof source-checkout root with a Python environment holding
the matching regularly installed yadof distribution. Machine-specific agent
instructions may name that interpreter explicitly; public documentation does not
depend on a virtual-environment directory name.

```powershell
python ".\benchmark_automation\benchmark.py" --help
python ".\benchmark_automation\benchmark.py" plan `
  --suite structural-canary
```

The runner consumes the regularly installed yadof package from that environment.
Do not edit site-packages, inject the yadof source checkout through
`PYTHONPATH`, or create a second copy of runner modules for testing.

## Change and verification workflow

1. Inspect the current Git status and preserve unrelated work.
2. Read the relevant runner/config/tests and the architecture sections affected by
   the change. A baseline edit is ordinary source work: validate it and let the next
   run snapshot it; do not create fingerprint-named directories.
3. Keep benchmark-specific orchestration here. Reusable single-workspace yadof
   mechanisms belong in yadof, as described in the root README.
4. Add or update focused unit tests for behavior changes.
5. Run the unit suite with a fresh absolute pytest base directory and the cache
   provider disabled. For example, replace `<fresh-temp>` below with a new empty
   directory outside the repository:

   ```powershell
   python -m pytest -q `
     ".\benchmark_automation\tests" `
     --basetemp "<fresh-temp>" -p no:cacheprovider
   ```

6. Run the no-write `plan` command for configuration or matrix changes. Run
   `preflight` when baseline, strategy, resource, or yadof integration changes.
   For output changes, test both the bounded default and the explicit detailed
   flag; assert that large command streams/fingerprints are absent from summaries.
7. Do not start smoke tests, optimization cells, collection-time model inference,
   or performance campaigns solely as a development check. Apply the cost/risk
   rules in the root README and obtain authorization when required.
8. Review the final diff and run `git diff --check` before committing.

Update the relevant architecture views whenever file roles, data flow,
persistence, public schemas, ETA semantics, or invariants change. Update matching
blueprints when module intent, I/O, or non-obvious implementation changes. Update
the root README whenever operators need to
change how they configure, execute, resume, collect, interpret, or diagnose a
benchmark. Small prose corrections need only targeted link/path checks.

Terminal changes require an end-to-end child-stream-to-Rich regression, not only an
assertion over internal task values. Inspection/ETA changes require deterministic
fixtures for running, pending, terminal, low-evidence, and live-progress states.

## Encoding and paths

Text files are UTF-8. Preserve non-ASCII paths and content, and use explicit UTF-8
when a PowerShell command reads text for editing. Immutable inputs resolve from
`benchmark.toml` and the benchmark root. A command-line `--runs-dir` override is
the deliberate exception: relative overrides resolve from the invocation
directory, while the TOML default remains benchmark-root-relative. Keep subprocess
commands as argument lists; do not build shell command strings.

## Agent-facing output contract

Default CLI output is a bounded JSON view that carries the facts needed for the
next decision and points to deeper artifacts. Expanded plan/preflight/report JSON
requires `--full-json`. Child process stdout/stderr is logged but not forwarded by
default; `--stream-output` is an explicit opt-in. Run/resume use Rich to keep the
active cell's individual-evaluation bar above the global cell bar without replacing
lifecycle messages; both disappear cleanly when execution finishes, and interactive
execution waits for Enter after its final summary. Default report/inspect preserve
JSON stdout and add a bounded final cumulative-hypervolume Markdown table on stderr.

Maintain these disclosure layers when adding fields:

1. bounded CLI summary and `inspect`;
2. concise `report.md`;
3. stable `report.json`;
4. one-cell state, command metadata, and log tails;
5. large `metrics.json`/collection evidence.

Do not put raw rows, full command output, fingerprints, or multi-cell diagnostic
payloads into the default summary. Update `AGENTS.md` whenever the safe reading
route changes.
