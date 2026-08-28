# Study format

A study is a TOML file outside `benchmark_automation/`. It is the complete request
for one comparison and is not a tool configuration file.

```toml
format = "yadof.benchmark.study"
name = "candidate-comparison"
baselines = ["test-com/synthetic-antenna", "ngspice/saw-ladder"]
seeds = [17, 29]
population = 100
generations = 20
reference = "reference-search"
fail_fast = false
runs_dir = "D:/studies/runs"

[[strategies]]
id = "reference-search"
name = "Reference search"
source = "strategies/reference.py"

[[strategies]]
id = "candidate"
name = "Candidate"
source = "strategies/candidate.py"
```

`name` and every strategy `id` are stable path-safe identifiers. `baselines`,
`strategies`, and `seeds` are non-empty and duplicate-free. `population` and
`generations` are positive integers applied uniformly to every cell. `reference`
is optional; when present it names one declared strategy. `fail_fast` defaults to
false.

`runs_dir`, `python`, and every strategy path may be absolute. Relative paths
resolve from the study file. When omitted, `runs_dir` is the checkout `temp/`
directory and `python` is the interpreter running `benchmark.py`.

Each strategy source is a complete `submit/optimization.py` with a top-level
`build_optimization()` function. The planner parses it but does not import it,
identify its components, or derive a category. The materialized cell copies the
file verbatim over the baseline's `submit/optimization.py`, then asks yadof to
construct and validate it.

One strategy can use a complete source selected by baseline:

```toml
[[strategies]]
id = "task-tuned"
name = "Task-tuned strategy"

[strategies.sources]
"test-com/synthetic-antenna" = "strategies/synthetic.py"
"ngspice/saw-ladder" = "strategies/filter.py"
```

A default `source` and a `sources` table may coexist. An exact baseline entry wins;
the default serves the remaining selected baselines. Every selected baseline must
resolve to one source.

Use the study through the CLI:

```powershell
python ".\benchmark_automation\benchmark.py" plan --study D:\studies\comparison.toml
python ".\benchmark_automation\benchmark.py" run --study D:\studies\comparison.toml
```

`plan` validates and prints the fully expanded RunSpec without writing. `run`
repeats the same planning function, snapshots its resolved inputs, and executes the
resulting cells. Editing the study or strategy files after run creation cannot
alter that run.
