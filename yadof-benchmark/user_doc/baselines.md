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
complete strategy.

`materialize_excludes` may omit task-local nonbehavioral files from that copy.
It cannot omit `config.py`, `submit/`, `job_template/`, `postprocess.py`,
or the yadof workspace marker. Runtime directories such as jobs, recorded data,
and visualization outputs are always excluded.

Fast/local execution baselines must explicitly provide:

```json
"simulation_concurrency": {
  "max_workers": 4,
  "resource_autodetect": true
}
```

This worker limit is separate from workflow `cell_concurrency`. Distributed
modes leave simulation admission to their external scheduler.

Contracts declare expected objective count and rawData shapes. Estimates provide
a conservative evaluation-time lower bound for current-workspace inspection;
they never replace measured data or include unmeasured optimizer/surrogate
overhead.

Baseline semantic IDs and source digests are recorded in `spec.json`. The
materialized cell copy is not a versioned resume snapshot: the package has no
resume path and each new execution uses a new benchmark workspace.
