# Real-only program

## Background and when to use it

`real_only.py` is the smallest conservative yadof 0.5 program. Every selected
individual is evaluated by the task's real evaluation path. Use it when no surrogate
is justified, while bringing up a new task, or as the comparison path for a more
complex program.

## Workspace dependencies

Copy the Python file to an initialized workspace as `submit/optimization.py`. The
workspace must retain its own `config.py`, `job_template/`, `submit/calc_cost.py`,
and evaluation implementation. GA is selected for one objective and NSGA-III for
two or more objectives, so the installed optimization dependencies are required.

## Data flow

The program reads the generation's recorded real-cost history through the framework
context, asks `full_real_search()` for a population, starts one evaluation handle,
waits and closes it, and commits exactly one result. It creates no predicted rows or
surrogate checkpoints.

## Concurrency and resources

Population-level concurrency remains controlled by the workspace evaluation mode
and worker settings. The program opens only the evaluation handle and closes it
before the generation boundary, so it is suitable for fast, local, and distributed
backends.

## Adoption

Review the identity literal, then replace the initialized workspace's
`submit/optimization.py` with `real_only.py`. Run `yadof check` before a bounded
smoke or campaign; do not run this source-checkout example in place.
