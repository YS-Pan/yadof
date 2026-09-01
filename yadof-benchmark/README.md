# yadof-benchmark

`yadof-benchmark` 0.4 is an independent, code-first runner for descriptive
comparisons of complete yadof 0.5 optimization programs. It requires yadof 0.5.0
or newer and accepts only literal explicit-program strategy sources.

The execution model is deliberately small:

- one benchmark workspace contains one `benchmark.py` and one execution;
- a second execution uses a newly initialized workspace;
- execution uses the currently installed `yadof-benchmark` and `yadof` packages;
- package versions, Python, host, and account are recorded once in `runtime.json`
  immediately before execution;
- there is no `runs/` layer, resume interface, attempt numbering, or copied
  benchmark-driver/workflow/strategy code snapshot.

`benchmark.py` explicitly classifies evidence as `structural` or
`performance`. Structural evidence validates integration only. Performance
evidence remains descriptive: the runner reports measurements and validity but
does not rank strategies or make acceptance decisions.

No-argument `init` materializes a wheel-contained portable preset (two canonical
strategies, synthetic antenna, seed 101, population 12, two generations). The
explicit complete preset contains 18 cells at population 200 and 25 generations;
`--budget-profile smoke` mechanically keeps that matrix and sets generations to
one. `init --blank` is the explicit custom-authoring path.

Custom comparisons default to seed `101`, population `200`, and `50` generations.
Mark a strategy `slow_surrogate=True` when it repeatedly trains a slow model such
as a neural network; a comparison containing such a strategy defaults to `15`
generations. Explicit seeds and budgets always take precedence. A single-seed
performance result is labeled exploratory.

A cell remains valid when all planned evaluations were attempted, at least one
finite result exists, the task contracts and generation-0 pairing contract match,
and the descriptive metric is available. Individual failed or non-finite
simulations are retained in counts and diagnostics but do not invalidate the
whole cell. Missing attempts, all-infinite output, or broken task/metric contracts
still invalidate it.

```powershell
$workspace = (yadof-benchmark init .\benchmarks\my-comparison |
  ConvertFrom-Json).workspace
yadof-benchmark check --workspace $workspace
yadof-benchmark plan --workspace $workspace
yadof-benchmark run --workspace $workspace
yadof-benchmark inspect --workspace $workspace

$complete = (yadof-benchmark init .\benchmarks\complete --preset complete |
  ConvertFrom-Json).workspace
yadof-benchmark run --workspace $complete --budget-profile smoke
```

On Windows, an AI agent must launch a long benchmark through host execution under
the interactive human user's account. A process started as the Codex sandbox user
belongs to a non-interactive session, so `--detach` cannot make its console
visible. Use host execution plus `--detach` for a visible independent console.
The visible console remains open after the benchmark finishes so its final output
can be reviewed; type `exit` or close it when done. `--hidden` is only an explicit
user-selected exception and exits automatically.

Each cell has a short path such as `cells/c0001`. Its full baseline, strategy,
and seed display label appears in terminal output, `spec.json`, state, inspect,
errors, results, and reports. Results, reports, and visualizations are direct
workspace outputs, so long comparison/baseline/strategy names no longer expand
artifact filenames.

Read the installed documentation with:

```powershell
yadof-benchmark docs show README.md
yadof-benchmark docs show execution.md
yadof-benchmark docs show api.md
```

Maintainers should start at [dev_doc/README.md](dev_doc/README.md). Users should
start at [user_doc/README.md](user_doc/README.md).
