# Baselines and packaged resources

`yadof-benchmark baselines` lists the baseline collection installed with the
package. Each recursively discovered `baseline.json` describes a complete yadof
workspace, its execution requirements, expected raw-data shapes, objective count,
rough resource estimates, and safe snapshot exclusions.

The package currently ships these editable source baselines:

- `chrono/trebuchet`
- `ngspice/saw-ladder`
- `test-com/synthetic-antenna`

Use `--baselines-root PATH` with `check`, `plan`, or `run` to select a separate
collection. Python callers pass `baselines_root=`. IDs remain decentralized: adding
a valid manifest below the selected root is sufficient; there is no central task
or algorithm registry.

Baseline manifests are JSON evidence contracts. This does not create a second
workflow configuration surface: comparison structure and execution flow remain in
workspace `benchmark.py`.
