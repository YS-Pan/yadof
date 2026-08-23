# dev_doc README

`dev_doc/` stores the project documents that help an AI or human maintainer understand
what the project is, how it is shaped, and why it changed over time.

The repository root remains the authoritative editable source for `dev_doc/` and
`user_doc/`. Package builds map both trees into read-only `yadof` wheel resources;
installed `yadof docs list|show|bundle` discovers and reads them without assuming a
Git checkout or writable package directory.

## System Roles

Only two roles interact with this codebase. Every tool and operational document
must be assigned to one of them.

### User

A **user** uses yadof to prepare optimization tasks, configure and run campaigns,
and inspect their results, normally by directing an AI coding agent that reads
`user_doc/` and performs the detailed task-authoring steps. A user may edit task
files and campaign settings, but does not install, configure, repair, or maintain
the system environment.

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

1. Read the [user-document contract](skill/user_doc.md), then read
   `../user_doc/README.md` and follow its user-workflow instructions, which are
   written primarily for an AI agent acting under the user's direction.
2. Read the [architecture contract](skill/architecture.md), then read every file in
   `architecture/` in full.
3. Read the [terminology contract](skill/terminology.md), then read
   `terminology.md` in full.
4. Read the [toDo and obsolete contract](skill/toDo.md), then read every Markdown
   file under `toDo/` recursively, including `toDo/auto/`, and apply automatic
   obsolete rules before treating an automatic toDo as active. Once normal task
   scope and findings are known, perform the contract's bounded automatic-trigger
   check before reporting completion.
5. List the complete `blueprints/` tree and perform the targeted reading pass
   defined by the [blueprint contract](skill/blueprints.md).
6. Apply the [change-record contract](skill/change_records.md). Do not read existing
   change records by default unless one of that contract's targeted-read conditions
   applies.

Do not read `obsolete/` by default. Its targeted-read and archival rules are defined
by the [toDo and obsolete contract](skill/toDo.md).

## Integrated Tool Documentation

The cost-history viewer is packaged as a reusable analysis/rendering subtree. Its
developer entry point is
[cost_viewer/dev_doc/README.md](../src/yadof/tools/cost_viewer/dev_doc/README.md);
read that tree before changing its API, history adaptation, analysis, reports,
plots, or future GUI integration.

The surrogate checkpoint viewer is packaged as a relatively independent tool
subtree. Its developer entry point remains
[surrogate_viewer/dev_doc/README.md](../src/yadof/tools/surrogate_viewer/dev_doc/README.md);
read that tree before changing the viewer backend, GUI, audit contracts, or its
package integration.

The repository also carries source-checkout-only benchmark automation outside the
installed package. Its developer entry point is
[benchmark_automation/dev_doc/README.md](../benchmark_automation/dev_doc/README.md).
Read the nested [agent instructions](../benchmark_automation/AGENTS.md) first when
changing its runner, schemas, frozen inputs, tests, or evidence policy. The
directory is downloadable with the repository but excluded from wheel and sdist.

## Installed Development Environment

The canonical local development/runtime environment for this checkout is the
repository sibling `../.venv`. It is based on the machine's system Python but owns
its installed packages. Use its interpreter by explicit path so tests, commands,
and wheel replacement cannot silently select another Python environment.

The exact machine and package versions detected for the current packaged line are
recorded in [development_environment.md](development_environment.md). Treat that
page as a reproducibility snapshot; `pyproject.toml` remains the compatibility
contract.

Create and populate it once from the repository root:

```powershell
& "C:\Program Files\Python313\python.exe" -m venv "..\.venv"
& "..\.venv\Scripts\python.exe" -m pip install ".[dev]"
```

Do not use an editable install for acceptance testing and do not add `src/` to
`PYTHONPATH`. Tests must import the regular yadof installation in `.venv`, including
its wheel documentation, templates, adapters, and console entry point.

After changing package code, tests, build configuration, resource mapping, or any
documentation mechanism that affects wheel contents or `yadof docs` behavior,
build first, then replace the installed yadof with the newest successful wheel
before testing:

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

### Documentation-only validation

A content-only edit under `dev_doc/`, `user_doc/`, or `admin_tool/` does not require
a wheel build, reinstall, import-origin check, or pytest run when no code, test,
build configuration, package-resource mapping, documentation command, or document
generation mechanism changed. Software tests provide little evidence for prose-
only changes and should not be run merely to satisfy a blanket workflow step.

Still perform lightweight checks appropriate to the edit: preserve UTF-8, inspect
the final diff, run `git diff --check`, and verify any paths, links, examples, or
cross-document references that were changed. If a documentation-only change alters
packaging/discovery, `yadof docs` routing, generated documentation, or executable
examples, run the corresponding focused build or command check. A code change still
uses the installed-wheel test workflow above even when most of its diff is
documentation.

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

- [User documentation](skill/user_doc.md): the one-way relationship between
  developer context and user-workflow task-authoring guidance that is primarily
  executed by the user's AI agent.
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

## Task/framework ownership rule

Code whose behavior is invariant across optimization tasks belongs under
`src/yadof/`, not in workspace/reference `evaluation.py`, `workflow.py`, or
`calc_cost.py`. Execute-
side invariant code must be exposed through the package-owned `worker_misc.py`
copied into prepared jobs, because distributed workers do not import yadof.
Submit-side invariant cost/rawData code must be exposed through
`yadof.job_template`.

Conversely, simulator/project/design selection, task measurements, rawData meaning,
objective definitions, thresholds, and other behavior that changes with the
optimization task belongs in `workflow.py` or `calc_cost.py`; it must not be
hard-coded into yadof. Task files call framework helpers but do not duplicate their
implementations.

Task mutability during a campaign is a core yadof capability, not an accidental
side effect of Python imports. A user may correct `calc_cost.py`, parameter
ranges/levels, configuration, workflow/evaluator code, or task helpers between
generations. The current contract keeps parameter identity/count and objective
count stable; structural dimension changes require separate future optimizer-state
work. Generation boundaries are the supported coherence point: the next generation
must use the current workspace definition consistently and reconstruct any affected
derived optimizer/history view. Yadof may detect source changes to invalidate
caches and may skip records that current code cannot mechanically interpret, but it
must not decide whether the old and new optimization problems are scientifically
equivalent. The user owns that judgment and decides whether to keep, clear, or
separate history.

The package boundary is not a destination for every extracted function. Add a
helper to yadof only when it represents a broadly recurring mechanism across
different optimization tasks or a stable framework contract. A one-off data shape,
task-specific grouping, simulator convention, or narrowly specialized objective
policy stays in the task file even when it can technically be factored out.

## Maintenance Workflow

After each code change:

1. Apply the update rules in the [architecture contract](skill/architecture.md).
2. Apply the update rules in the [blueprint contract](skill/blueprints.md).
3. Add the record required by the
   [change-record contract](skill/change_records.md).
4. Apply the vocabulary rules in the
   [terminology contract](skill/terminology.md).
5. Apply the automatic-trigger check plus the completion and archival rules in the
   [toDo and obsolete contract](skill/toDo.md).
6. Update `user_doc/` when task-authoring behavior changes, as defined by the
   [user-document contract](skill/user_doc.md).

For documentation-only changes, still update architecture and blueprints when the
documentation system itself changes. A trivial documentation correction may skip
both a change record and a Git commit only when all of these conditions hold:

- exactly one existing documentation file changes;
- the diff is a localized typo, grammar, formatting, or link correction;
- no file is added, deleted, renamed, or moved; and
- no architecture, blueprint, contract, workflow, toDo state, user instruction,
  public behavior, or historical decision changes.

Report the remaining uncommitted diff. Commit when the user explicitly requests it.
Every other documentation-only change remains a normal documented change: add its
change record and commit it. Do not create a change record for an exempt correction,
because doing so would make the change multi-file and defeat the exception.

When adding new future work, put manual-trigger work directly under `toDo/` and
automatic-trigger work under `toDo/auto/`, rather than putting either in
`change_records/`. `change_records/` explains completed changes; `toDo/` describes
pending work that should influence future technical choices.
