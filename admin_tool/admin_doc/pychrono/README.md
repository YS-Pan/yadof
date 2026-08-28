# Shared PyChrono Runtime

This administrator-only workflow installs one immutable Project Chrono runtime for
all local users. It does not install yadof into that runtime and does not modify
PATH, Python registration, shell profiles, `PYTHONHOME`, or `PYTHONPATH`.

The maintained installer script is
`install_shared_pychrono.ps1`. Its pinned inputs are:

- Miniforge `26.3.2-3`, Windows x86-64, from the official conda-forge GitHub
  release;
- PyChrono `10.0.0` build `py313h418371c_0` from
  `projectchrono/label/release`;
- Python 3.13, with the exact patch version and build selected by a recorded Conda
  dry run and then passed back to the real create command.

Before elevation, download both the versioned installer and its `.sha256` sidecar,
compare them with the digest published by the GitHub release API, and verify the
installer's Authenticode signature. Run the script only with that verified local
installer and a caller-owned audit directory outside `C:\ProgramData\Miniforge3`:

```powershell
$script = Resolve-Path .\admin_tool\pychrono_runtime\install_shared_pychrono.ps1
$installer = Resolve-Path <verified-installer-path>
$audit = <caller-owned-audit-directory>
Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"' + $script.Path + '"'),
    "-InstallerPath", ('"' + $installer.Path + '"'),
    "-AuditOutputPath", ('"' + $audit + '"')
)
```

The script refuses an existing Miniforge root rather than updating or overwriting
it. It installs all users at `C:\ProgramData\Miniforge3`, creates
`envs\pychrono-10` without default packages, validates a deterministic mechanics
step with an isolated child environment, exports the solver and installed package
metadata, and then gives only `SYSTEM` and `Administrators` full control. The
built-in `Users` group receives read and execute access. The machine-level
`YADOF_PYCHRONO_PYTHON` value is published only after the runtime passes the first
smoke test.

Audit copies are written both to the caller-owned directory and to the immutable
shared location `C:\ProgramData\Miniforge3\share\yadof\pychrono-10`. A separate
ordinary-user validation must still execute the absolute child interpreter and
prove that both shared prefixes reject writes before deployment is considered
complete. Run `validate_shared_pychrono.ps1` from a normal, non-elevated PowerShell
process with a caller-owned scratch path; it uses the same `pychrono_smoke.py`
mechanics probe as the installation stage and additionally performs explicit
write-denial probes against both shared prefixes.

If the first run installed Miniforge but stopped before creating `pychrono-10` or
publishing the machine setting, preserve its audit files and rerun with
`-ResumeExistingMiniforge`. That switch accepts only this narrow checkpoint: the
Miniforge root and `conda.exe` must exist, while the machine setting must still be
absent. It never reinstalls over the existing root. If the environment transaction
also finished before a later validation stopped the run, add
`-ResumeExistingPyChronoEnvironment`; the script then skips creation and requires
the complete installed package set to equal a fresh dry-run plan before continuing.

Windows DLL discovery is configured only in each child process. The validation
scripts construct a process-local PATH from the PyChrono prefix's standard Conda
runtime directories followed by the unchanged machine PATH. They never activate
Conda or publish those entries to user or machine PATH.
