# Baselines

A baseline is a self-describing task adapter discovered recursively from a
`baseline.json`. Its directory path below the baseline collection must match its
semantic ID.

Required manifest fields are:

- `format = "yadof.benchmark.baseline"`
- `id`, `name`, and `description`
- `workspace`
- `execution`
- `contract`
- `estimates`
- `materialize_excludes`

The selected yadof workspace must contain the complete task inputs and a uniform
`postprocess.py`. The runner materializes the clean workspace directly into each
short cell directory and replaces `submit/optimization.py` with the selected
strategy entry. For an explicit optimization program, it also copies every
declared helper to the same relative path below `submit/`.

`materialize_excludes` may omit task-local nonbehavioral files from that copy.
It cannot omit `config.py`, `submit/`, `job_template/`, `postprocess.py`,
or the yadof workspace marker. Runtime directories such as jobs, recorded data,
and visualization outputs are always excluded.

Fast/local execution baselines must explicitly provide:

```json
"simulation_concurrency": {
  "physical_core_multiplier": 2.0
}
```

At cell materialization time, the runner detects physical CPU cores with
`psutil.cpu_count(logical=False)`, multiplies by this finite positive value, and
rounds down to a positive worker count. The manifest therefore contains no fixed
worker count. `spec.json` preserves the portable multiplier; `state.json` and
reports record the detected physical cores, multiplier, rounding rule, and
resolved worker count. Detection failure is explicit rather than silently using
logical cores.

Packaged defaults are `2.0` for `chrono/trebuchet`, `2.0` for
`ngspice/saw-ladder`, and `1.0` for `test-com/synthetic-antenna`. These defaults
come from short 200-individual, one-generation throughput trials. A custom
baseline may use another positive multiplier, including a value below one when
that is faster or safer on its simulator.

This host-adaptive simulator limit is separate from workflow
`cell_concurrency`. yadof treats the resolved fast/local worker cap as the user's
decision; host resource observations are diagnostic and do not reduce it.
Distributed modes leave simulation admission to their external scheduler.

Contracts declare expected objective count and rawData shapes. Estimates provide
a conservative evaluation-time lower bound for current-workspace inspection;
they never replace measured data or include unmeasured optimizer/surrogate
overhead.

Baseline semantic IDs and source digests are recorded in `spec.json`. The
materialized cell copy is not a versioned resume snapshot: the package has no
resume path and each new execution uses a new benchmark workspace.
