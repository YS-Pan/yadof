# Module blueprint: com_lib

## Intent
- Keep reusable adapter source/reference files for simulators and custom programs outside the generic runtime modules.
- Let a task opt into one or more adapters by copying the needed `*_com.py` files into `project/job_template/`, keeping each prepared job self-contained.
- Provide an explicitly software-specific location without making the yadof core depend on one simulator, vendor, or adapter.

## Historical Lineage
- The adapter-copy workflow descends from earlier fanyufei and huangzetao task layouts, where simulator automation helpers traveled with each prepared job.
- The current library preserves that self-contained-job technique while separating inactive references in `com_lib` from active task copies in `job_template`.

## Functionalities
- `hfss_com.py` is the reusable HFSS/PyAEDT adapter reference. Its current contents are synchronized from the active `project/job_template/hfss_com.py` after reusable adapter fixes are validated.
- `test_com.py` is a pure-Python simulator stand-in that can be copied into a task for synthetic workflow development and surrogate tests outside the generic framework suite.
- Additional adapters use descriptive `*_com.py` names and may target another simulator, a custom program, or one step in a multi-program workflow.
- Reusable adapter-specific contract tests live under `project/test/`, not in `project/com_lib/`. They use synthetic inputs or mocks and remain independent of the active optimization task.

## I/O Format
- Files in `project/com_lib/` are importable references for development and explicit tests, but active workflows must not import them through `project.com_lib`.
- A user copies each selected adapter into `project/job_template/`, and `job_template.api.copy_job_files()` then includes that active copy in prepared jobs.
- Adapters expose task-consumable functions for initialization, variable transfer, execution, rawData export, and cleanup as appropriate to that external program.
- Adapter-produced `.npz` files must satisfy the generic `job_template/rawdata_contract.py` schema; the adapter does not calculate or persist final cost.

## Non-Obvious Techniques
- `com_lib` is deliberately outside the core dependency graph. `optimize`, `evaluate_manager`, `recorded_data`, and `surrogate` must not select or import adapters from it.
- The active task copy and library reference serve different roles: `job_template/<adapter>` may contain temporary task-local edits, while `com_lib/<adapter>` should receive reusable fixes once they are known to be generally valid for that adapter.
- Synchronization is intentional rather than automatic. Replacing the library copy from an active adapter requires checking that no task-only project name, design name, objective, or workflow policy leaked into the reusable adapter.
- More than one adapter may be active in a task. Neither copy logic nor documentation may assume a single `*_com.py` file.

## Mutability Profile
- Adapter implementations may change with external software APIs and are allowed to be software-specific.
- The rule that `com_lib` is optional staging/reference content and never a core runtime dependency should remain stable.
- Update the matching `user_doc/com_lib/<adapter>.md` when an adapter's public calls, environment needs, or workflow usage changes.
