# Module blueprint: job_template

`yadof.job_template` is stable framework support for task-owned workspace files.
It provides `Parameter`, normalization/denormalization, fresh task queries, rawData
schema/view/validation, cost helpers, and assignment materialization. A workspace
owns `parameters_constraints.py`, `workflow.py`, `calc_cost.py`, adapters, models,
and assets. Workflows create rawData and metadata, never authoritative cost files.
