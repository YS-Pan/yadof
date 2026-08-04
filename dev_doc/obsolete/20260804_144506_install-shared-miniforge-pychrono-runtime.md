# Install Shared Miniforge and PyChrono Runtime

## Context

- Execute this manual toDo only when the user explicitly authorizes installation
  and administrator-level machine changes. Planning this runtime does not itself
  authorize downloading installers, changing ACLs, or setting machine variables.
- The 2026-08-04 inspection found a 64-bit Windows 10.0.26200 host with about
  288.5 GiB free on the NTFS `C:` volume. The machine has a system Python 3.13 at
  `C:\Program Files\Python313\python.exe` and the workspace has its own `.venv`,
  but `conda`, `mamba`, `micromamba`, Miniforge, and PyChrono were not found.
- The current process was not elevated. An all-users installation will therefore
  require an explicit UAC-approved administrator operation.
- The machine currently defines `PYTHONPATH=C:\condor\lib\python;C:\condor\bin`.
  That value must not leak into the PyChrono child interpreter.
- Project Chrono is an external simulator runtime for yadof. The shared environment
  must not contain yadof and must not replace the system Python or workspace
  virtual environment.

## Goal

- Install Miniforge for all users at `C:\ProgramData\Miniforge3`.
- Create one clean, administrator-maintained PyChrono environment at
  `C:\ProgramData\Miniforge3\envs\pychrono-10`.
- Allow every local user to execute that runtime while preventing ordinary users
  from modifying the shared installation.
- Publish the absolute child-interpreter location through a machine-level setting
  such as
  `YADOF_PYCHRONO_PYTHON=C:\ProgramData\Miniforge3\envs\pychrono-10\python.exe`.
- Leave the system Python, the current workspace `.venv`, PATH, and shell startup
  files unchanged.

## Guidance

1. Re-check the operating system, architecture, free space, existing Conda
   installations, current official Miniforge release, and available Project Chrono
   release packages immediately before installation. Do not blindly reuse the
   versions observed while this toDo was written.
2. Download the Windows x86-64 Miniforge installer only from the official
   conda-forge Miniforge release. Record the release URL, version, file name, and
   SHA-256 digest, then verify the downloaded file before elevation.
3. Use the installer's all-users mode with the destination
   `C:\ProgramData\Miniforge3`. Do not add Miniforge to user or system PATH, do not
   register it as the system Python, and do not run `conda init`. Set base
   auto-activation off. Use absolute executable paths for all later administration.
4. Before creating the environment, query the official Project Chrono release
   channel and conda-forge for compatible Windows builds. Prefer a released,
   explicitly pinned PyChrono version and Python version; record the exact selected
   build. The initial target is PyChrono 10 with Python 3.13 if the fresh query still
   confirms that combination.
5. Create `pychrono-10` with no configured default packages. Install only the
   pinned Python, PyChrono, and dependencies selected by the Conda solver. Do not
   install yadof, Jupyter, plotting tools, test frameworks, editor helpers, or
   unrelated packages, and do not use `pip install pychrono`.
6. Export an explicit package list and environment metadata after creation so the
   runtime can be audited and reproduced. Treat the prefix as a versioned simulator
   installation; upgrades should be prepared and verified separately rather than
   mutating a working runtime in place without a rollback plan.
7. Inspect and explicitly set ACLs on both the Miniforge root and the PyChrono
   environment. `SYSTEM` and `Administrators` should retain full control; ordinary
   `Users` should have read and execute access but no ability to add, replace, or
   remove runtime files. Do not rely only on inherited `C:\ProgramData` ACLs.
8. Set `YADOF_PYCHRONO_PYTHON` at machine scope only after its target exists and
   passes validation. Do not modify `PYTHONHOME`, `PYTHONPATH`, the registered
   Python launcher, or the current workspace `.venv`.
9. Validate the runtime without activation by invoking its `python.exe` using the
   absolute path. The probe should import `pychrono`, report the expected version,
   run a minimal deterministic mechanics calculation, and work from a separate
   non-administrator user account or equivalent all-users execution context.
10. During validation, clear inherited `PYTHONPATH`, disable the user site and byte
    code writes, and write all temporary/output files to a caller-owned scratch
    directory rather than the read-only shared prefix.

## Completion Rule

- The official Miniforge installer and package provenance are recorded and their
  integrity has been checked.
- The two stated prefixes exist, and the PyChrono prefix contains only the pinned
  interpreter, PyChrono, and solver-required runtime dependencies.
- An ordinary user can execute the absolute PyChrono interpreter and complete the
  mechanics smoke test, but cannot modify either shared prefix.
- `YADOF_PYCHRONO_PYTHON` resolves to the verified interpreter for all users.
- The system Python, workspace `.venv`, PATH, shell profiles, and yadof installation
  remain unchanged, and yadof is not installed in the PyChrono environment.
