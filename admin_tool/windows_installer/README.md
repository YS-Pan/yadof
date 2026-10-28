# Windows MSI with a private yadof_env

The Windows x64 MSI installs the GUI, CLI and a complete private CPython 3.11.15
prefix named `yadof_env`. It is an offline, per-user installation, defaulting to
`%LOCALAPPDATA%\Programs\Yadof`. Double-click the MSI, use **Browse...** to choose
an installation folder, and select **Install**. The displayed path is read-only;
the folder browser is Windows' modern Common Item Dialog, as used by the main
GUI's workspace chooser, with an address bar, navigation pane and new folders. Cancelling
the browser retains the previous selection. During installation, a progress bar
and current-action text track Windows Installer's actual work. Desktop
and Start menu shortcuts open the GUI; the CLI is
`<installation>\yadof_env\Scripts\yadof.exe`. Python is
`<installation>\yadof_env\Scripts\python.exe`.

The runtime is self-contained, not a copied venv that depends on a Python install
elsewhere. The DLL's `python311._pth` and explicit `pyvenv.cfg` site policy exclude
registry, PYTHONPATH, system and user site packages. A private sitecustomize locates this prefix's DLLs and Tcl/Tk, and
allows a prepared task to import its own sibling modules. Launchers locate Python
relative to themselves; no activation, PATH or `.py` association changes occur.
They require the Windows-provided .NET Framework 4.x on Windows 10/11 x64.

## Included versions and exclusions

The A2094 audit of 2026-10-27 fixes Python 3.11.15, NumPy 2.4.6, psutil 7.2.2,
pymoo 0.6.1.6, CPU PyTorch 2.12.1, Matplotlib 3.11.0 and SciPy 1.17.1. Setuptools
81.0.0 is selected from A2094's duplicate metadata because Torch requires <82. The package
contains the framework extras surrogate, plot, viewer, gp, retrieval and qnehvi.
Additional framework features absent on A2094 use the audited submit host's
scikit-learn 1.9.1, threadpoolctl 3.7.0, BoTorch 0.18.1, GPyTorch 1.15.2 and
linear_operator 0.6.1. Installing these dependencies does not change the
experimental components' scientific readiness gates.

HTCondor, frp, PyAEDT, PyChrono, simulators, benchmark orchestration, development
tools, concrete workspaces and credentials are excluded. Distributed execution
continues to use an independently configured HTCondor installation and workers'
solver environments. The MSI never changes those services or file associations.
Solver tasks require separately provisioned solver dependencies; the bundled
environment is the yadof host runtime, not a general HFSS worker environment.

## Build

Use the checkout's audited Windows x64 Python 3.11.15 environment. The builder
uses the standard library msilib shipped with that pinned interpreter (removed
from later Python releases), Windows' .NET Framework C# compiler and the portable
Zig 0.14.1 C compiler for the small native folder-picker DLL. Zig is a build tool
and is not installed or shipped to users. It snapshots
only RECORD-owned files in the resolved framework dependency closure and the
allowlisted native-runtime files in the base prefix's conda-meta manifests.
It never copies an entire site-packages or environment directory. All required
baseline versions must already exist; mismatches or missing files stop the build.

First build and regularly install the current wheel following `dev_doc/README.md`.
Then, from the repository root:

```powershell
& '..\.venv\Scripts\python.exe' admin_tool/windows_installer/build_msi.py `
    --wheel dist/yadof-0.7.0-py3-none-any.whl `
    --work temp/msi-a2094-build `
    --zig temp/toolchains/zig-x86_64-windows-0.14.1/zig.exe
```

Obtain the compiler from the [official Zig download index](https://ziglang.org/download/index.json)
and verify the archive's published SHA-256 before extracting below root temp/.
The x86_64 Windows 0.14.1 archive SHA-256 is
`554f5378228923ffd558eac35e21af020c73789d87afeabf4bfd16f2e6feed2c`.

For a reference prefix with overwritten/duplicate setuptools metadata, download
the exact setuptools 81.0.0 wheel and extract it into a scratch directory. Pass
that directory with `--reference-site`; the builder verifies its RECORD hashes.
Do not relabel another setuptools release or modify the shared environment.

Use a new empty work directory for each payload. `--reuse-payload` rebuilds the MSI
from that work directory's existing snapshot. Work must remain below root temp/.
The MSI, SHA-256 file and manifest are published to dist/. The manifest records
every installed file and digest, dependency versions, original runtime package
identities, the source wheel digest and native folder-picker source/binary hashes.
The picker is embedded in the MSI Binary table and runs only from the Browse
button, before installation, without depending on a pre-existing Python runtime.
Retain the manifest with the release. Package license
files are included with their distributions and the Python/Tcl/Tk runtime.
Signing requires a publisher certificate and is separate from local construction.

## Installation and servicing

```powershell
msiexec /i yadof-0.7.0-a2094-win-x64.msi /qn INSTALLDIR="D:\Apps\Yadof" /L*v install.log
```

The MSI owns its installed program files and shortcuts. Repair and uninstall are
available from the MSI or Windows installed-app settings. Same-version rebuilt
MSIs upgrade the previous payload; a newer installed version blocks a downgrade.
Binary File rows retain their PE version/language metadata. Private-prefix
replacement uses `REINSTALLMODE=amus`, so same-version executables are restored
after removing the previous product. This applies only to installer-owned files.
Keep workspaces outside the installation directory. Uninstall removes only
registered installer files and shortcuts and does not recursively delete unknown
files, workspaces, external Python environments, services or user data. Runtime
bytecode writing is disabled so ordinary use does not leave Python caches behind.

Validate actual installation, private-runtime isolation, CLI/GUI dependencies,
task execution, repair and uninstall using a temporary installation and external
workspace before distributing an artifact. No simulator or real optimization
campaign is needed for that acceptance.

```powershell
& '..\.venv\Scripts\python.exe' admin_tool/windows_installer/validate_msi.py `
    --msi dist/yadof-0.7.0-a2094-win-x64.msi `
    --work temp/msi-qa
```

This command installs into the explicitly selected scratch directory (including
spaces and Chinese), exercises that product and uninstalls it in a finally block.
It refuses to run if that exact product is already registered. Logs, runtime
evidence and the external workspace are preserved under the acceptance directory.
Use a short work path: Windows Installer cannot write some deeply nested packaged
files when the complete target path reaches 260 UTF-16 code units. The MSI derives
the allowed installation-directory length from its longest payload path and checks
it before copying files, including silent installations. Browse asks for a shorter
folder when needed, and the full UI includes standard installer error dialogs.
