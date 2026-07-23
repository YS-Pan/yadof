# Restore developer architecture and flat HTCondor rawData transport

## Context

The packaged `dev_doc` retained the current installed-package/workspace direction but
lost substantial responsibility, dependency, lifecycle, persistence, concurrency,
failure, and test detail during migration. The earlier `20260713 clean up/dev_doc`
was used as a recovery source. At the same time, distributed jobs had begun carrying
an archived copy of yadof plus bootstrap/launcher files, and HTCondor could return a
nested `rawData/` directory or use an older zip fallback.

## Documentation recovery

Current architecture and module blueprints were expanded with still-valid material
from the earlier documentation: rawData-first source truth, task/framework/admin
boundaries, module dependency direction, job lifecycle, dynamic costs, batch
recording, persistence locking/atomicity, failure isolation, optimizer/surrogate
responsibilities, test placement, and installed-wheel acceptance.

Outdated material was deliberately not restored: the repository-local `project/`
runtime namespace, implicit global project paths, copied `config/key/all/specific`
trees, active `com_lib` runtime dependencies, former `user_doc` audience, fixed
machine interpreter paths, direct cost output, and legacy output-transfer fallbacks.

## Execution and transport decision

- Preserve the administrator-validated Windows contract: HTCondor directly executes
  job-local `workflow.py` with `transfer_executable=True`, `load_profile=True`, and
  `run_as_owner=False`.
- Do not create, copy, or transfer a yadof package, wheel, runtime zip, worker config,
  compatibility bootstrap, or intermediary launcher.
- Copy only `worker_misc.py` as package-owned execute support. Generate a
  self-contained assigned parameter snapshot so worker task code does not import
  yadof.
- Require workflows to create `rawData.zip` in success and error paths. The archive
  contains only direct unique `.npz` basenames and no `rawData/` directory entry.
- Explicitly return `rawData.zip` and `individual_metadata.json`; never return the
  execute-side `rawData/` directory. Strictly validate and restore the archive into
  submit-side `rawData/` before normal rawData validation/recording.
- Reject nested rawData directories locally, during worker preparation/packaging,
  and during distributed archive restoration.

## Compatibility and operational impact

Workspace workflows intended for distributed execution must import only job-local
files, the standard library, and dependencies installed on workers. They must use
`rawData.zip`, not `rawData_outputs.zip`. Existing historical change records remain
unchanged as evidence, but current architecture, blueprints, agent docs, and
administrator contracts describe the new rule.

## Verification

Tests cover direct submit executable, absence of yadof runtime payloads,
self-contained parameter snapshots, explicit output list, direct workflow zip
creation, nested archive rejection, flat local rawData validation, artifact members,
and installed-package behavior.
