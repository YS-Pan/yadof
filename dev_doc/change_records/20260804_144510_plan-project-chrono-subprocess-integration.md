# 2026-08-04 14:45 - Plan Project Chrono Subprocess Integration

## Context

- Project Chrono support needs PyChrono, whose Conda runtime should remain isolated
  from yadof, the system Python, and yadof's workspace virtual environment.
- The target Windows machine did not yet have Conda, Miniforge, or PyChrono, so the
  installation and integration assumptions needed to be grounded in the actual
  host before implementation.

## Change

- Recorded a future administrator-controlled installation plan for an all-users
  Miniforge base at `C:\ProgramData\Miniforge3` and a minimal shared PyChrono
  environment at `C:\ProgramData\Miniforge3\envs\pychrono-10`.
- Recorded isolation requirements that leave PATH, the registered system Python,
  shell initialization, yadof's `.venv`, and yadof's dependency metadata unchanged.
- Split the remaining work into four manual toDos: provision the shared runtime,
  define the subprocess protocol, implement the adapter, and validate a real
  mechanics workflow.
- Defined the intended architectural boundary: yadof launches the absolute
  PyChrono interpreter as an external process, communicates through versioned
  JSON/NPZ artifacts, and never imports PyChrono in its own runtime.

## Rationale

- A simulator-specific Conda environment should behave like an external software
  installation, not become the host for an orchestration package that also drives
  unrelated tools.
- A read-only, administrator-maintained shared prefix gives all users a stable
  executable while preventing ordinary simulations from silently mutating the
  runtime.
- Separate planning tasks allow package-side protocol and adapter tests to use fake
  workers without making the yadof test suite depend on a machine-global PyChrono
  installation.

## Impact

- No software was installed and no runtime behavior changed in this documentation
  update.
- Project Chrono is not yet a supported yadof adapter. Each manual toDo requires
  explicit selection before its work is performed.
- The planned implementation will keep task-specific mechanics and cost logic in
  workspaces and preserve rawData as the authoritative simulator evidence.

## Follow-Up

- Complete the four new manual toDos in dependency order when explicitly requested.
