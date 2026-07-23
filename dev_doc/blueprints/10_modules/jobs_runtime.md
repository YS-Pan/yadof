# Module blueprint: prepared jobs

## Lifecycle and contents

Jobs are generated below the effective workspace jobs directory and are the only
unit sent to an execute backend. A prepared job contains copied task inputs,
assigned self-contained `parameters_constraints.py`, `workflow.py`, one
package-provided `worker_misc.py`, preparation metadata, and empty `rawData/`.
Task-owned models/adapters/assets may be files or required subdirectories below the
job; package support files themselves are direct files.

Runtime adds workflow metadata, local/Condor logs and submit diagnostics,
`rawData.zip` in distributed mode, and direct restored/locally generated
`rawData/*.npz`. `calc_cost.py`, workspace/global config packages, yadof source,
wheel/package archives, worker bootstraps/configs, and authoritative `cost.json` are
forbidden.

## Hash and provenance

`job_static_hash` is definition-oriented. It covers copied task/support bytes and
the canonical meaning of parameter definitions, but excludes lifecycle metadata,
rawData, temp/cache paths, costs, and per-candidate assigned values. Preparation
metadata records workspace identity, yadof version, effective execution summary, and
optional run/optimization/generation/population indices.

## Distributed transport

HTCondor executes the copied `workflow.py` directly. `workflow.py` imports the
same-directory `worker_misc.py` as needed and is responsible for generating a flat
top-level `rawData.zip` in success and error paths. The archive contains only member
names like `name.npz`; it never contains a `rawData/` directory. Condor returns that
zip and workflow metadata, not the rawData directory. Submit-side restoration is
strict and reports missing, corrupt, nested, non-`.npz`, or duplicate members.

## Invariants

- Reserved package support filenames cannot be supplied by the task, even with case
  differences on Windows.
- Every execute dependency is present in the job or deliberately installed on the
  execute node; jobs do not import yadof.
- The rawData output tree is flat in local, execute, restored, and recorded paths.
- Retries clear stale runtime outputs without changing static task inputs.
