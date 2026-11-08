# Blueprint Contract

## Purpose

Blueprints are generative descriptions of the viewer, its modules, and the few
source files with exceptional contracts. A capable maintainer should be able to
recreate equivalent behavior from a blueprint without relying on the current
implementation's incidental structure.

Blueprints explain intent, required behavior, I/O shapes, non-obvious techniques,
dependency boundaries, and which details may change.

## Targeted Reading Contract

During the first context pass:

1. List filenames below `../blueprints/`, `../blueprints/10_modules/`, and
   `../blueprints/20_files/`.
2. Read `../blueprints/00_project.md` for project-wide, documentation, or
   multi-module work.
3. Read every module blueprint matching the code being changed.
4. Read a file blueprint when the named file or its specific contract is affected.

Do not read every file blueprint by default.

## Layout And Content

```text
blueprints/00_project.md
blueprints/10_modules/<module>.md
blueprints/20_files/<source path>.md
```

File blueprints mirror source paths. For example,
`blueprints/20_files/backend/checkpoints.py.md` describes
`backend/checkpoints.py`.
`blueprints/20_files/backend/hierarchical_checkpoints.py.md` describes the separate
experimental hierarchical-CAE reader and all-axis coordinate path.

Recommended module sections are:

```text
# Module blueprint: module_name
## Intent
## Functionalities
## I/O Format
## Non-Obvious Techniques
## Mutability Profile
```

Keep documentation at module level unless one file owns a complex compatibility,
concurrency, aggregation, or UI-state contract that is easy to lose during a
rewrite.

## Maintenance Contract

Update affected blueprints when intent, responsibilities, dependencies, public data
shapes, non-obvious techniques, or mutability boundaries change. Do not add
blueprints for trivial re-export or marker files.
