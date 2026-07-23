# dev_doc README

`dev_doc/` stores the project documents that help an AI or human maintainer understand
what the project is, how it is shaped, and why it changed over time.

The repository root remains the authoritative editable source for `dev_doc/` and
`agent_doc/`. Package builds map both trees into read-only `yadof` wheel resources;
installed `yadof docs list|show|bundle` discovers and reads them without assuming a
Git checkout or writable package directory.

## System Roles

Only two roles interact with this codebase. Every tool and operational document
must be assigned to one of them.

### User

A **user** uses yadof to prepare optimization tasks, configure and run campaigns,
and inspect their results. A user may edit task files and campaign settings, but
does not install, configure, repair, or maintain the system environment.

### Administrator

An **administrator** configures and maintains the environment in which yadof runs.
This includes installing the package and its dependencies, and configuring or
maintaining the HTCondor cluster's software and hardware. Administrator-only
documents and tools live in `../admin_tool/`; they must not be placed in
the installed yadof CLI/tools.

The documents in this folder are not all read with the same priority. Use the rules
below before changing code or documentation. The canonical entry point is
`dev_doc/README.md`.

## Reading Guide

The module contracts under `skill/` are required operational instructions, not
optional summaries. When collecting project context, follow this order:

1. Read the [agent-document contract](skill/agent_doc.md), then read
   `../agent_doc/README.md` and follow its agent-facing task setup instructions.
2. Read the [architecture contract](skill/architecture.md), then read every file in
   `architecture/` in full.
3. Read the [terminology contract](skill/terminology.md), then read
   `terminology.md` in full.
4. Read the [toDo and obsolete contract](skill/toDo.md), then read every Markdown
   file under `toDo/` recursively, including `toDo/auto/`, and apply automatic
   obsolete rules before treating an automatic toDo as active.
5. List the complete `blueprints/` tree and perform the targeted reading pass
   defined by the [blueprint contract](skill/blueprints.md).
6. Apply the [change-record contract](skill/change_records.md). Do not read existing
   change records by default unless one of that contract's targeted-read conditions
   applies.

Do not read `obsolete/` by default. Its targeted-read and archival rules are defined
by the [toDo and obsolete contract](skill/toDo.md).

## Installed Development Environment

The canonical local development/runtime environment for this checkout is the
repository sibling `../.venv`. It is based on the machine's system Python but owns
its installed packages. Use its interpreter by explicit path so tests, commands,
and wheel replacement cannot silently select another Python environment.

Create and populate it once from the repository root:

```powershell
& "C:\Program Files\Python313\python.exe" -m venv "..\.venv"
& "..\.venv\Scripts\python.exe" -m pip install ".[dev]"
```

Do not use an editable install for acceptance testing and do not add `src/` to
`PYTHONPATH`. Tests must import the regular yadof installation in `.venv`, including
its wheel documentation, templates, adapters, and console entry point.

After changing source or documentation, build first, then replace the installed
yadof with the newest successful wheel before testing:

```powershell
& "..\.venv\Scripts\python.exe" -m build --wheel
$wheel = Get-ChildItem ".\dist\yadof-*.whl" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1
& "..\.venv\Scripts\python.exe" -m pip install `
  --force-reinstall --no-deps $wheel.FullName
```

Verify the import origin and run tests with repository-source injection disabled:

```powershell
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
& "..\.venv\Scripts\python.exe" -c `
  "import pathlib, yadof; print(yadof.__version__); print(pathlib.Path(yadof.__file__).resolve())"
& "..\.venv\Scripts\python.exe" -m pytest -q
```

The reported package path must be below `../.venv/Lib/site-packages/yadof`, never
below repository `src/`. Build/install failure stops the workflow; do not test the
previous installed copy as though it contained the current edits.

## Encoding And Mojibake

Markdown files in `dev_doc/` and `admin_tool/` should be treated as UTF-8 text. Some
documents contain Chinese, and reading them with a local ANSI/default code page can
produce mojibake instead of readable text.

When using PowerShell, prefer explicit UTF-8 reads:

```powershell
Get-Content -Raw -Encoding UTF8 dev_doc/README.md
Get-Content -Raw -Encoding UTF8 admin_tool/README.md
```

If text appears garbled, do not edit based on the garbled display. Re-read the file
with UTF-8 first, or use an editor that shows the file encoding. When writing these
documents from tools or scripts, preserve UTF-8 and avoid default-encoding commands
that depend on the current Windows code page.

## Module Contract Index

- [Agent documentation](skill/agent_doc.md): the one-way relationship between
  developer context and agent-facing task-authoring guidance.
- [Architecture](skill/architecture.md): current-view system maps, invariants, file
  roles, and update triggers.
- [Blueprints](skill/blueprints.md): generative module/file descriptions, targeted
  reading, path layout, and update triggers.
- [toDo and obsolete](skill/toDo.md): trigger types, expiry, completion, archival,
  and historical-use rules.
- [Terminology](skill/terminology.md): project-specific vocabulary and maintenance
  rules.
- [Change records](skill/change_records.md): append-only completed-change history,
  naming, structure, and targeted reading.

## Maintenance Workflow

After each code change:

1. Apply the update rules in the [architecture contract](skill/architecture.md).
2. Apply the update rules in the [blueprint contract](skill/blueprints.md).
3. Add the record required by the
   [change-record contract](skill/change_records.md).
4. Apply the vocabulary rules in the
   [terminology contract](skill/terminology.md).
5. Apply the completion and archival rules in the
   [toDo and obsolete contract](skill/toDo.md).
6. Update `agent_doc/` when task-authoring behavior changes, as defined by the
   [agent-document contract](skill/agent_doc.md).

For documentation-only changes, still update architecture and blueprints when the
documentation system itself changes, and add a change record.

When adding new future work, put manual-trigger work directly under `toDo/` and
automatic-trigger work under `toDo/auto/`, rather than putting either in
`change_records/`. `change_records/` explains completed changes; `toDo/` describes
pending work that should influence future technical choices.
