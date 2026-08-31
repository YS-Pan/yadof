# Optimization program examples

The yadof source checkout contains copyable program references under
`examples/optimization-programs/`. They are intentionally excluded from installed
wheel and sdist resources: a pip-only installation contains this index, but not the
example files. Each Python file has a same-basename guide covering dependencies,
data flow, concurrency, and adoption.

- [`real_only.py`](../examples/optimization-programs/real_only.py) is the minimal
  authoritative real-evaluation GA/NSGA-III program.
- [`sequential_surrogate.py`](../examples/optimization-programs/sequential_surrogate.py)
  completes real evaluation before training PCA/SVD on current evidence.
- [`overlapped_surrogate.py`](../examples/optimization-programs/overlapped_surrogate.py)
  overlaps real evaluation with training from immutable prior evidence.
- [`split_cost_surrogate_data.py`](../examples/optimization-programs/split_cost_surrogate_data.py)
  keeps full optimizer cost history but passes an explicit subset to the surrogate.
- [`posterior_assisted_fallback.py`](../examples/optimization-programs/posterior_assisted_fallback.py)
  shows the current blocked qNEHVI readiness and full-real fail-closed result.

Initialize a real workspace first, copy exactly one program to
`submit/optimization.py`, bring along none of the example directory as runtime data,
and run `yadof check --workspace PATH`. The examples do not supply `config.py`,
`calc_cost.py`, `job_template/`, rawData, simulator assets, or credentials.
