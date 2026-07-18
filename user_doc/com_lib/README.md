# com_lib User Docs

This folder documents `_com.py` adapter files one file at a time.

`project/com_lib/` is the adapter source/reference library. A file in that folder is
not active just because it exists there. To use an adapter in a task, copy the needed
`*_com.py` file into the active task's `job_template/` (under `project/` for the
transitional source runtime or under the selected installed workspace), then import
it from `workflow.py` by same-directory name.

When an active adapter receives a reusable fix, validate that the change contains no
task-only project/design/objective assumptions, then synchronize it back to the
matching `project/com_lib/` reference. Task-local experiments may remain only in
`job_template/`.

## Reading Guide

When choosing, copying, or calling a simulator/custom adapter, read this file first.
Then read the document for the specific adapter:

- `hfss_com.md` for `project/com_lib/hfss_com.py` and active HFSS/PyAEDT workflows.
- `test_com.md` for `project/com_lib/test_com.py` and pure-Python synthetic workflows.

When a new adapter is added under `project/com_lib/`, add a matching document here:

```text
project/com_lib/maxwell_com.py -> user_doc/com_lib/maxwell_com.md
```

## Activation Rule

Normal flow:

```text
project/com_lib/some_com.py
  -> copy to selected workspace/job_template/some_com.py
  -> workflow.py imports from some_com
  -> yadof.evaluate_manager copies it and any other active adapters/assets into each local job
```

Multiple task-local adapters are supported. Do not name an adapter
`worker_misc.py` or `yadof_worker_config.json`; those job-root filenames are
reserved for package worker support and composition fails rather than overwriting.

Use same-directory imports in `workflow.py`:

```python
from hfss_com import solver_init, set_variables, analyze
```

Avoid package imports such as:

```python
from project.com_lib.hfss_com import solver_init
```

Prepared jobs should be self-contained. They should not need to import from
`project/com_lib/`.

## Adding A New Adapter

For a new simulator or custom program:

1. Create `project/com_lib/yourtool_com.py`.
2. Give it small functions that are easy to call from `workflow.py`.
3. Return or save raw simulation outputs only, not final optimization cost.
4. Copy it into `project/job_template/yourtool_com.py` for active use.
5. Import it from `workflow.py` by same-directory name.
6. Add `user_doc/com_lib/yourtool_com.md` with workflow examples and any environment notes.

Keep adapter functions simulator-specific. Keep yadof framework decisions out of
adapter files.
