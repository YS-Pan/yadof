# surrogate_viewer dev_doc

`dev_doc/` stores current developer-facing documentation for the surrogate
checkpoint viewer integrated below `yadof.tools`. It helps a human or AI maintainer
understand the
system boundary, runtime flows, source responsibilities, and contracts that should
survive refactoring.

The canonical entry point is this file. Source code remains authoritative for
implementation details; architecture and blueprints describe the intended current
design.

## Scope

This is deliberately smaller than yadof's root `dev_doc/`. It stays beside the
viewer code as a relatively independent maintenance tree:

- `architecture/`: current system views, invariants, and runtime flows;
- `blueprints/`: generative project, module, and exceptional-file descriptions;
- `terminology.md`: project-specific vocabulary;
- `skill/`: compact reading and maintenance contracts for the three sections above.

There is intentionally no local `toDo/`, `obsolete/`, or `change_records/`. Pending
and completed package-wide work follows yadof's root documentation lifecycle;
these folders should not be duplicated merely to mirror that larger tree.

## Reading Guide

For an initial project-context pass:

1. Read the [architecture contract](skill/architecture.md), then every file under
   `architecture/` in the order listed by
   [the architecture index](architecture/00_architecture_index.md).
2. Read the [terminology contract](skill/terminology.md), then
   [terminology.md](terminology.md).
3. List `blueprints/`, read the
   [blueprint contract](skill/blueprints.md), and perform its targeted reading
   pass. Read `blueprints/00_project.md` for cross-module changes.

Do not infer missing history-management infrastructure from yadof. This tree has no
automatic archival or change-record workflow.

## Development Environment

The viewer source lives at `src/yadof/tools/surrogate_viewer/` in the yadof
repository. Follow the root
[yadof developer guide](../../../../../dev_doc/README.md), including its installed
wheel acceptance workflow. From the yadof repository root, focused checks are:

```powershell
& "..\.venv\Scripts\python.exe" -m yadof.tools.surrogate_viewer --help
& "..\.venv\Scripts\python.exe" -m pytest tests/test_surrogate_viewer.py -q
```

The viewer imports the regularly installed yadof package from that environment.
Do not add yadof source directories to `PYTHONPATH`, and never edit yadof inside
`site-packages`. Because the viewer now ships inside yadof, every viewer code or
documentation change requires rebuilding and force-reinstalling the wheel before
acceptance tests.

## Project Boundary

The viewer is read-only with respect to a selected yadof workspace:

- it reads configuration, completed records, rawData, and surrogate checkpoints;
- it loads checkpoint artifacts and performs prediction/audit inference;
- it calculates displayed costs through the selected workspace's current task;
- it does not train models, launch a simulator, edit checkpoints, or write history.

The viewer deliberately depends on package-internal yadof checkpoint/model/rawData
mechanisms. Those imports remain isolated below `backend/`; UI modules consume only
viewer-local immutable contracts.

## Maintenance Workflow

After a code or documentation change:

1. Update architecture when module ownership, runtime flow, persistence,
   concurrency, failure behavior, or core invariants change.
2. Update affected blueprints when intent, dependencies, public data shapes,
   non-obvious techniques, or mutability boundaries change.
3. Update terminology only for new or corrected project-specific concepts.
4. Run the focused unit tests and an appropriate smoke check. Changes to inference
   or audit aggregation should also be checked against a real compatible workspace
   when available.

Viewer-local documentation changes also participate in yadof's root change-record
workflow. They require link, UTF-8, structure, wheel-membership, and installed-copy
validation.

## Encoding

All Markdown files in this tree are UTF-8. With PowerShell, use explicit UTF-8
reads when inspecting documents that may later contain Chinese:

```powershell
Get-Content -Raw -Encoding UTF8 `
  src\yadof\tools\surrogate_viewer\dev_doc\README.md
```
