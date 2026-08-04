# 2026-08-04 16:50 - Install Shared Miniforge and PyChrono Runtime

## Context

- The host needed one administrator-maintained Project Chrono runtime that every
  local user could execute without moving yadof into a simulator-specific Python
  environment.
- The machine-level `PYTHONPATH` points at HTCondor directories and could not be
  inherited by PyChrono. System Python, the workspace virtual environment, PATH,
  Python registration, and shell profiles also had to remain unchanged.

## Change

- Installed the signed conda-forge Miniforge `26.3.2-3` Windows x86-64 release at
  `C:\ProgramData\Miniforge3`. The installer SHA-256 is
  `14a8635465b5190537ddad6286746ffebbc55a1ed2a7bb14a506595fe3191e1e`.
- Created `envs\pychrono-10` from an exact recorded Conda solve with Python
  `3.13.14` build `h09917c8_100_cp313` and the official
  `projectchrono/label/release` PyChrono `10.0.0` build
  `py313h418371c_0`. The resulting environment has 69 solver-selected packages and
  does not contain yadof.
- Added `admin_tool/pychrono_runtime/` with the pinned elevated installer,
  deterministic mechanics probe, ordinary-user validation, resume checkpoints,
  audit exports, and explicit ACL management.
- Corrected the two in-scope pre-package `project/tools/` references in
  `admin_tool/README.md` to the current `src/yadof/tools/` path.
- Published machine-level `YADOF_PYCHRONO_PYTHON` only after the mechanics probe
  succeeded. Both shared prefixes now grant full control only to `SYSTEM` and
  `Administrators`, and read/execute access to built-in `Users`.
- Stored the explicit package list, package hashes, solver plan, environment
  metadata, installer provenance, ACL evidence, and validation results below
  `C:\ProgramData\Miniforge3\share\yadof\pychrono-10` and in the caller-owned
  installation audit directory.

## Rationale

- Project Chrono's released Conda build was selected over the Project Chrono main
  builds and the separate conda-forge package so the simulator runtime is both
  official and explicitly versioned.
- Windows PyChrono loads optional DLL-backed modules during top-level import. A
  process-local PATH containing the environment's standard Conda runtime
  directories is therefore required even when invoking the absolute interpreter;
  this leaves user and machine PATH unchanged and does not require activation.
- The shared installation is immutable to ordinary users so concurrent evaluations
  cannot install packages, create caches, or corrupt the simulator runtime.

## Impact

- A non-administrator validation under `DESKTOP-DERG5LD\CodexSandboxOffline`
  imported the official PyChrono release with `PYTHONPATH` absent and user site
  disabled, verified that yadof was not importable, and obtained deterministic
  vertical velocity `-0.0981` after a `0.01 s` gravity step.
- The same validation proved write denial at both the Miniforge root and PyChrono
  environment. The system Python and workspace `.venv` remain on Python `3.13.11`;
  yadof remains installed only in the workspace environment.
- Machine/user PATH, `PYTHONHOME`, the existing machine `PYTHONPATH`, Python
  launcher inventory, and monitored shell profiles are unchanged.

## Follow-Up

- The separate manual toDo for defining the PyChrono subprocess contract remains
  pending. It should reuse the validated absolute-interpreter and process-local DLL
  search-path requirements without adding Conda activation or global PATH changes.
