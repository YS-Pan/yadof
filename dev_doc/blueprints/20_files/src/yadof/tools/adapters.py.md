# File blueprint: src/yadof/tools/adapters.py

## Intent

- Copy one immutable packaged adapter resource into an explicit workspace without
  treating installed package files as editable task inputs.

## Functionalities

- List available adapter resource names in deterministic package-resource order.
- Resolve and validate a workspace through effective config loading.
- Copy a named adapter to `job_template/` with exclusive creation.
- Treat an existing byte-identical destination as an idempotent success and refuse
  to overwrite any different user-owned file.

## I/O Format

- `list_adapters()` returns a tuple of resource filenames.
- `copy_adapter(workspace, adapter)` accepts a `WorkspaceContext`, string, or path
  plus a resource name and returns frozen `AdapterCopyResult(name, destination,
  created)`.
- The only write is the selected workspace file at `job_template/<adapter-name>`.

## Non-Obvious Techniques

- Resource selection is delegated to `yadof.resources`, so traversal rejection and
  extension/name normalization remain package-resource contracts.
- Binary comparison and exclusive `xb` creation preserve exact resource bytes and
  close the usual check-then-overwrite race.

## Mutability Profile

- Never add task-specific project names, credentials, or objective logic here.
- Overwrite policy and destination ownership are safety contracts; changes require
  CLI and two-workspace tests.
