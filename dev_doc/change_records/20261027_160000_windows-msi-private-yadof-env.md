# 2026-10-27 - Windows MSI with private yadof_env

## Context

The user requested a double-click Windows MSI containing yadof and its own Python
environment named yadof_env, excluding HTCondor, frp and solver dependencies. They
selected the 2026-10-27 A2094 worker audit as the version baseline. Existing wheel
GUI entry points alone did not provision Python or an isolated dependency set.

## Change and rationale

Added source-checkout Windows installer tooling under admin_tool/windows_installer.
The offline, per-user MSI contains a self-contained CPython 3.11.15 prefix, exact
baseline numerical/CPU-Torch versions and the framework's non-solver extras.
Optional framework packages absent from A2094 use explicit submit-host pins.
The builder snapshots declared distribution files and native-runtime manifests,
never the whole shared development environment. Private startup excludes inherited
site packages and locates its own DLL/Tcl/Tk directories after relocation.

Relative CLI/GUI launchers preserve arguments and exit codes without changing
PATH, file associations or pool/solver configuration. Windows Installer owns
program files and shortcuts and provides repair, replacement and removal. Build
manifests retain file hashes, package versions and runtime provenance. Deployment
ownership is documented in architecture, the package blueprint and user foundation.
PE version/language metadata and explicit private-file replacement prevent
same-version upgrades from skipping Python binaries that the old product then
removes. Upgrades remember the previous per-user installation directory. Private
streams use UTF-8 so Chinese workspace paths survive CLI/GUI process boundaries.

## Verification

The release is dist/yadof-0.6.0-a2094-win-x64.msi (244,260,864 bytes), SHA-256
03c0eb7678d68c5e4269af6223cde81898521fb3891980c10b5a884c0309fbb7.
The sibling manifest, checksum and acceptance JSON retain build provenance and
the completed checks. Full local logs are under temp/msi-qa-1028/.

Actual per-user installation into a path with Chinese and spaces passed CLI,
GUI launcher/Tk controller, native imports and numerical operations, dependency
closure and foreign-Python isolation, installed docs, task init/check, local
smoke and a four-individual generation (4/4 successful). Repair restored a
deleted installer-owned module. A same-version replacement retained the custom
installation directory and passed the CLI and complete native/GUI runtime probe
again. Uninstall returned zero, left no registered related product, removed all
25,629 installer-owned files and preserved external workspaces and unknown user
files. The test installation is removed.

The installed-package foundation/GUI selection passed 56 unique tests; its
artifact-build test passed on an isolated retry after an initial timeout during
concurrent staging. Installer Python syntax, artifact/manifest/builder hashes and
git diff --check also passed. No simulator or real optimization campaign ran.

## Limits

The build-time msilib dependency is deliberately tied to the audited Python 3.11
line. Publisher signing requires a separately supplied certificate. This change
does not select or repair any external solver environment.
This host's Windows Installer logs contain non-fatal Error 1926 / access-denied
messages while securing rollback backups under D:\Config.Msi during repair,
upgrade and removal. Every operation returned zero with no failed action, and
the installed-file inventory and product registration were checked after removal.
No system ACLs were changed. Failure-injection rollback, a clean Windows VM and
interactive wizard visual acceptance were not performed.
