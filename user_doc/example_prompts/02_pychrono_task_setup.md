# Project Chrono task setup prompt

Use this after initializing a workspace and confirming that the evaluation hosts
have a separately provisioned `YADOF_PYCHRONO_PYTHON` interpreter.

```text
Prepare this yadof workspace for a Project Chrono optimization task. First run
`yadof docs show user README.md`, then read `user_doc/adapters/chrono_com.md` and
the task-authoring documents it references. Copy the packaged `chrono_com.py`
adapter with `yadof task copy-adapter`; do not reimplement its subprocess
protocol. Add a task-owned `chrono_worker.py` that imports PyChrono only inside the
validated worker callback, builds the model described below, and writes only the
schema-compatible rawData needed by current `submit/calc_cost.py`. Keep objective policy
out of the worker. Make local/prepared and fast paths use the same child mechanics,
with isolated candidate scratch, an explicit timeout, and diagnostic propagation.
Do not install yadof or any package into the PyChrono environment, activate Conda,
change PATH, or run a real simulation until I explicitly authorize it.

Model and task requirements:
- [describe bodies, joints, contact, loads, solver, and stepping]
- [list assigned parameters and units]
- [list measured raw evidence, arrays, axes, and units]
- [define objective interpretation separately for submit/calc_cost.py]
- [choose or retain the complete composition in submit/optimization.py]
```
