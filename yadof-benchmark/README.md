# yadof-benchmark

`yadof-benchmark` is an independent Python package for reproducible,
code-first comparisons of complete yadof optimization strategies. A benchmark
workspace owns one `benchmark.py`; that Python file declares the whole workflow,
including strategies, comparison matrices, execution policy, and postprocessing.

```powershell
yadof-benchmark init D:\benchmarks\my-comparison
yadof-benchmark baselines
yadof-benchmark check --workspace D:\benchmarks\my-comparison
yadof-benchmark run --workspace D:\benchmarks\my-comparison
```

The package accepts only the Python workspace contract. It has no alternate study
configuration parser or migration path. Read the installed documentation with:

```powershell
yadof-benchmark docs show README.md
yadof-benchmark docs show api.md
```

Maintainers should start at [dev_doc/README.md](dev_doc/README.md). Users should
start at [user_doc/README.md](user_doc/README.md).
