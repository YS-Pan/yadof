# yadof-benchmark

`yadof-benchmark` is an independent Python package for reproducible,
code-first comparisons of complete yadof optimization strategies. A benchmark
workspace owns one `benchmark.py`; that Python file declares the whole workflow,
including strategies, comparison matrices, execution policy, and postprocessing.

```powershell
$workspace = (yadof-benchmark init D:\benchmarks\my-comparison |
  ConvertFrom-Json).workspace
yadof-benchmark baselines
yadof-benchmark check --workspace $workspace
yadof-benchmark run --workspace $workspace
```

`init` prints the actual `YYYYMMDD_HHMMSS-...` workspace path, and automatic or
explicit run names use the same local timestamp prefix. Each run keeps its complete
reports and grouped cost/domain visualizations under one run root; timestamped
indexes in the workspace's top-level `reports/` and `visualizations/` lead to it.

`benchmark.py` is the only workflow-definition surface. Distribution metadata in
`pyproject.toml` is not a benchmark workflow input. Read the installed
documentation with:

```powershell
yadof-benchmark docs show README.md
yadof-benchmark docs show api.md
```

Maintainers should start at [dev_doc/README.md](dev_doc/README.md). Users should
start at [user_doc/README.md](user_doc/README.md).
