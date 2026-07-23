# Blueprint Contract

## Purpose

Blueprints are generative project, module, and exceptional file descriptions. Their
central requirement is:

> A capable AI should be able to recreate a file or module with the same function
> from its blueprint, even if the current source file is not visible.

Blueprints must not merely summarize current source. They explain intent, expected
behavior, I/O shapes, non-obvious techniques, and mutability boundaries.

Use them to answer:

- What should this project, module, or file do?
- What shape should its inputs and outputs have?
- Which implementation techniques are easy to lose?
- Which parts may change often, and which contracts should stay stable?
- Which historical implementation ideas or reference ancestors still matter?

## Targeted Reading Contract

Do not read the entire blueprint tree by default. During the first `dev_doc/` pass:

1. List all filenames directly under `../blueprints/` and
   `../blueprints/10_modules/`, and recursively under
   `../blueprints/20_files/` when that folder exists.
2. Read `../blueprints/00_project.md` when work affects project-wide contracts,
   documentation rules, or multiple modules.
3. Read every module or file blueprint matching the modules or concepts being
   changed.

## Content And Layout Contract

Recommended module structure:

```text
# Module blueprint: module_name

## Intent
- Why this module exists.

## Functionalities
- What this module must provide.

## I/O Format
- Public data shapes, files, APIs, and return values.

## Non-Obvious Techniques
- Important implementation ideas that should survive rewrites.

## Mutability Profile
- Which parts may change often and which contracts should stay stable.
```

Keep blueprints module-level until the project stabilizes. Add a file-level
blueprint only when one file has a complex contract that cannot be captured by its
module blueprint. File-level blueprints under `blueprints/20_files/` mirror the
source path as folders, for example
`blueprints/20_files/src/yadof/surrogate/runtime.py.md`; never encode a source path
into one flattened filename such as `project_surrogate_runtime.py.md`.

Historical reference ancestry belongs in the relevant project or module blueprint
as natural-language context. Do not maintain a separate path map to old reference
trees unless those paths are present and actively useful in the current workspace.

## Maintenance Contract

Update relevant blueprints whenever a code or documentation change alters project
or module intent, responsibilities, dependencies, public I/O, non-obvious
techniques, lineage, or mutability boundaries. Documentation-only changes require a
blueprint update when the documentation system itself changes.
