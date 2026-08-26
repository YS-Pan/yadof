# Reference development environment

## Scope

This page records the environment detected for the packaged yadof development
checkout on 2026-07-29. It is a reproducibility snapshot, not a minimum-version
contract. `pyproject.toml` remains authoritative for declared Python and dependency
compatibility, and administrators remain responsible for simulator, license, and
HTCondor deployment.

## Detected machine

| Component | Detected value |
|---|---|
| Operating system | Windows 11 Pro 25H2, build 26200.8875, x86-64 |
| Python | CPython 3.13.11 |
| Development interpreter | Repository sibling `..\.venv\Scripts\python.exe` |
| ANSYS Electronics Desktop | 2024 R1; product version `2024.1.0`, file version `2024.1.0.1` |
| AEDT executable | `C:\Program Files\AnsysEM\v241\Win64\ansysedt.exe` |
| PyAEDT | 0.24.1 |
| HTCondor client and Python package | 25.4.0 |

## Relevant Python packages

| Role | Package versions |
|---|---|
| Core numerical/optimizer | NumPy 2.2.6; pymoo 0.6.2 |
| Local resource measurement | psutil 7.2.2 |
| Optional surrogate/viewer | PyTorch 2.10.0+cu128; Matplotlib 3.11.1 |
| Build and test | build 1.5.0; hatchling 1.31.0; pytest 9.1.1 |

The installed yadof version was 0.1.0 when the snapshot was collected before the
installable-package work. Acceptance for the current packaged line must build and
force-install the 0.4.1 wheel into the same `.venv`, then verify that imports
resolve from `.venv\Lib\site-packages\yadof`.

## Detection notes

- Python and package versions were read from the repository sibling `.venv`.
- AEDT identity came from the installed `ansysedt.exe` version resource; AEDT was
  not launched.
- `ANSYSEM_ROOT241` pointed to the same AEDT 2024 R1 installation.
- `condor_version` reported the HTCondor client build; no live jobs were submitted.
- The Windows compatibility registry reports the legacy product string
  `Windows 10 Pro`, while Python identifies Windows 11 and the detected 25H2 build
  is recorded above.
