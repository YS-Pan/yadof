"""Build a solver-free Windows x64 MSI from an audited Python 3.11 reference.

The builder snapshots the dependency closure, not the reference environment.
Every redistributed file is owned by a Windows Installer component. No package
manager, network download, shell custom action, or nested MSI runs at installation.
Build-time msilib is provided by the pinned CPython 3.11 runtime.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import uuid
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
UPGRADE_ID = uuid.UUID("611dc371-55fa-44b7-b8b5-a356002c8906")
BASELINE = {
    "numpy": "2.4.6", "psutil": "7.2.2", "pymoo": "0.6.1.6",
    "torch": "2.12.1", "matplotlib": "3.11.0", "scipy": "1.17.1",
    "setuptools": "81.0.0",
}
# These framework features were absent from A2094; pin the submit-host versions.
ADDITIONAL = {
    "scikit-learn": "1.9.1", "threadpoolctl": "3.7.0", "botorch": "0.18.1",
    "gpytorch": "1.15.2", "linear-operator": "0.6.1",
}
FORBIDDEN = {"pyaedt", "ansys-aedt-core", "pychrono", "htcondor", "conda-pack"}
EXTRAS = ["surrogate", "plot", "viewer", "gp", "retrieval", "qnehvi"]
RUNTIME_PACKAGES = {
    "python", "bzip2", "ca-certificates", "libexpat", "libffi", "liblzma",
    "libsqlite", "libzlib", "openssl", "tk", "tzdata", "ucrt", "vc",
    "vc14_runtime", "vcomp14",
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(args, *, cwd=None, env=None):
    completed = subprocess.run([str(arg) for arg in args], cwd=cwd, check=True,
                               capture_output=True, text=True, encoding="utf-8", errors="replace", env=env)
    if completed.stdout.strip():
        print(completed.stdout.strip(), flush=True)
    return completed


def wheel_metadata(wheel: Path):
    from email.parser import BytesParser
    with zipfile.ZipFile(wheel) as archive:
        return BytesParser().parsebytes(archive.read(next(name for name in archive.namelist() if name.endswith(".dist-info/METADATA"))))


def closure(wheel: Path, reference_sites=()):
    selected = {}
    pins = {**BASELINE, **ADDITIONAL}
    overrides = {canonicalize_name(d.metadata["Name"]): d for directory in reference_sites
                 for d in metadata.distributions(path=[str(directory)]) if d.metadata["Name"]}
    pending = [Requirement(f"{name}=={version}") for name, version in {**BASELINE, **ADDITIONAL}.items()]
    for value in wheel_metadata(wheel).get_all("Requires-Dist", []):
        required = Requirement(value)
        if required.marker is None or any(required.marker.evaluate({"extra": extra}) for extra in ["", *EXTRAS]):
            pending.append(required)
    while pending:
        required = pending.pop()
        name = canonicalize_name(required.name)
        if name in selected:
            distribution = selected[name]
        else:
            distribution = overrides.get(name) or metadata.distribution(name)
            pin = pins.get(name)
            if not required.specifier.contains(distribution.version) or (pin and distribution.version != pin):
                alternatives = [d for d in metadata.distributions() if canonicalize_name(d.metadata.get("Name", "")) == name
                                and required.specifier.contains(d.version) and (not pin or d.version == pin)]
                if alternatives:
                    distribution = alternatives[0]
            selected[name] = distribution
            for value in distribution.requires or []:
                dependency = Requirement(value)
                if dependency.marker is None or dependency.marker.evaluate({"extra": ""}):
                    pending.append(dependency)
        if not required.specifier.contains(distribution.version):
            raise ValueError(f"Reference package {name}=={distribution.version} does not satisfy {required}")
    if FORBIDDEN.intersection(selected) or any(name.startswith("ansys-") for name in selected):
        raise ValueError("A solver/HTCondor dependency entered the framework closure")
    return selected


def copy_file(source: Path, destination: Path):
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def stage_runtime(prefix: Path, source: Path):
    records = []
    for path in sorted((source / "conda-meta").glob("*.json")):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["name"] not in RUNTIME_PACKAGES:
            continue
        if record["name"] == "python" and record["version"] != "3.11.15":
            raise ValueError("A2094 requires CPython 3.11.15")
        for relative in record["files"]:
            parts = PurePosixPath(relative.replace("\\", "/")).parts
            if ".." in parts or PurePosixPath(relative).is_absolute():
                raise ValueError(f"Unsafe runtime member: {relative}")
            if "site-packages" in parts or "__pycache__" in parts or relative.endswith((".pyc", ".pyo", ".pdb")):
                continue
            copy_file(source.joinpath(*parts), prefix.joinpath(*parts))
        records.append({key: record.get(key) for key in ("name", "version", "build", "url", "sha256", "license")})
    if {row["name"] for row in records} != RUNTIME_PACKAGES:
        raise ValueError("Reference prefix is missing required native Python runtime packages")
    # Make the CRT available before Python starts loading extension modules.
    for native in (prefix / "Library/bin").glob("*.dll"):
        if native.name.lower().startswith(("vcruntime", "msvcp", "vcomp", "concrt")):
            copy_file(native, prefix / native.name)
    configure_python_layout(prefix)
    return records


def configure_python_layout(prefix: Path):
    scripts = prefix / "Scripts"
    scripts.mkdir(exist_ok=True)
    for path in [prefix / "python.exe", prefix / "pythonw.exe", *prefix.glob("*.dll")]:
        shutil.move(str(path), scripts / path.name)
    (scripts / "python311._pth").write_text("..\n../DLLs\n../Lib\n../Lib/site-packages\nimport site\n", encoding="utf-8")
    (prefix / "pyvenv.cfg").write_text("include-system-site-packages = false\n", encoding="utf-8")


def stage_distribution(distribution, site: Path):
    source_root = Path(distribution.locate_file("")).resolve()
    count = 0
    for member in distribution.files or []:
        relative = PurePosixPath(str(member).replace("\\", "/"))
        if ".." in relative.parts or relative.is_absolute() or "__pycache__" in relative.parts or relative.suffix in (".pyc", ".pyo", ".pdb"):
            continue  # Old prefix's generated Scripts entries are rebuilt below.
        source = source_root.joinpath(*relative.parts)
        # A2094 has two setuptools metadata versions. Never label overwritten
        # shared package files as the selected release; use an extracted wheel
        # reference if this known collision fails its RECORD hashes.
        if canonicalize_name(distribution.metadata["Name"]) == "setuptools" and member.hash:
            expected = member.hash.value
            actual = base64.urlsafe_b64encode(bytes.fromhex(sha256(source))).decode().rstrip("=")
            if actual != expected:
                raise ValueError(f"setuptools RECORD mismatch: {source}; supply --reference-site from an exact wheel")
        copy_file(source, site.joinpath(*relative.parts))
        count += 1
    if not count:
        raise ValueError(f"No RECORD-owned files for {distribution.metadata['Name']}")
    return count


def install_wheel(wheel: Path, prefix: Path):
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            relative = PurePosixPath(member.filename)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError(f"Unsafe wheel member: {member.filename}")
            if member.is_dir():
                continue
            if relative.parts[0].endswith(".data"):
                if relative.parts[1] != "scripts":
                    raise ValueError(f"Unsupported wheel data: {member.filename}")
                destination = prefix / "Scripts" / Path(*relative.parts[2:])
            else:
                destination = prefix / "Lib/site-packages" / Path(*relative.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(archive.read(member))


def prepare_payload(wheel: Path, work: Path, runtime_source: Path, reference_sites=()):
    payload = work / "payload"
    payload.mkdir(exist_ok=False)
    prefix = payload / "yadof_env"
    prefix.mkdir()
    native = stage_runtime(prefix, runtime_source)
    packages = closure(wheel, reference_sites)
    for name, distribution in sorted(packages.items()):
        print(f"Snapshot {name}=={distribution.version}", flush=True)
        stage_distribution(distribution, prefix / "Lib/site-packages")
    install_wheel(wheel, prefix)
    copy_file(HERE / "private_sitecustomize.py", prefix / "Lib/site-packages/sitecustomize.py")
    compiler = Path(os.environ["WINDIR"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
    scripts = prefix / "Scripts"
    scripts.mkdir(exist_ok=True)
    for gui in (False, True):
        output = scripts / ("yadof-gui.exe" if gui else "yadof.exe")
        run([compiler, "/nologo", "/optimize+", "/platform:x64", f"/out:{output}",
             "/target:winexe" if gui else "/target:exe", *(["/define:GUI", "/reference:System.Windows.Forms.dll"] if gui else []), HERE / "Launcher.cs"])
    info = {"baseline": "DESKTOP-A2094, audited 2026-10-27", "python": "3.11.15",
            "framework_extras": EXTRAS,
            "excluded": ["HTCondor", "frp", "PyAEDT", "PyChrono", "simulators"],
            "wheel": wheel.name, "wheel_sha256": sha256(wheel), "native_runtime": native,
            "packages": {name: distribution.version for name, distribution in sorted(packages.items())},
            "additional_versions_source": "A2092 submit-host packages for framework features absent on A2094"}
    (payload / "dependency-manifest.json").write_text(json.dumps(info, indent=2), encoding="utf-8")
    (payload / "requirements.lock.txt").write_text("\n".join(f"{name}=={version}" for name, version in info["packages"].items()) + "\n", encoding="utf-8")
    run([prefix / "Scripts/python.exe", "-B", "-c",
         "import sys,site,ssl,sqlite3,ctypes,tkinter,numpy,scipy,torch,yadof; "
         "assert sys.flags.isolated and not site.ENABLE_USER_SITE; "
         "r=tkinter.Tk();r.withdraw();r.destroy(); "
         "print('Private runtime ready:',sys.version.split()[0],torch.__version__,yadof.__version__)"])
    return payload, info


def identifier(prefix: str, path: str) -> str:
    return prefix + hashlib.sha256(path.lower().encode("utf-8")).hexdigest()[:28]


def guid(value: str) -> str:
    return "{" + str(uuid.uuid5(UPGRADE_ID, value)).upper() + "}"


def file_version(path: Path):
    """Preserve PE versions so MSI does not treat a versioned runtime as data."""
    if path.suffix.lower() not in (".exe", ".dll", ".pyd"):
        return None, None
    native = ctypes.WinDLL("msi")
    native.MsiGetFileVersionW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint),
                                         ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_uint)]
    version, language = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(256)
    version_length, language_length = ctypes.c_uint(256), ctypes.c_uint(256)
    status = native.MsiGetFileVersionW(str(path), version, ctypes.byref(version_length), language, ctypes.byref(language_length))
    if status == 1006:  # ERROR_FILE_INVALID: this binary has no version resource.
        return None, None
    if status:
        raise OSError(status, f"Cannot read MSI file version: {path}")
    return version.value or None, language.value or None


def build_folder_picker(zig: Path, work: Path):
    version = run([zig, "version"]).stdout.strip()
    if version != "0.14.1":
        raise ValueError("Use the pinned Zig 0.14.1 build-time compiler")
    output = work / "FolderPicker.dll"
    environment = os.environ.copy()
    environment.update({"ZIG_GLOBAL_CACHE_DIR": str(work / "zig-global-cache"),
                        "ZIG_LOCAL_CACHE_DIR": str(work / "zig-local-cache")})
    run([zig, "cc", "-target", "x86_64-windows-gnu", "-std=c11", "-Os", "-s", "-shared",
         "-DUNICODE", "-D_UNICODE", HERE / "FolderPicker.c", "-lmsi", "-lole32", "-lshell32", "-luser32", "-luuid", "-o", output],
        cwd=work, env=environment)
    return output, {"toolchain": "Zig " + version, "sha256": sha256(output),
                    "source_sha256": sha256(HERE / "FolderPicker.c")}


def add_dialogs(msi, db):
    from msilib import text

    add = lambda table, rows: msi.add_data(db, table, rows)
    add("TextStyle", [("Normal", "Segoe UI", 10, None, 0), ("Heading", "Segoe UI", 16, None, 1)])
    add("Property", [("DefaultUIFont", "Normal"), ("ErrorDialog", "ErrorDlg")])
    add("ActionText", text.ActionText)
    for name, first, default in (("WelcomeDlg", "Browse", "Install"), ("MaintenanceDlg", "Repair", "Repair"),
                                  ("ExitDialog", "Finish", "Finish"), ("FatalError", "Finish", "Finish"), ("UserExit", "Finish", "Finish")):
        add("Dialog", [(name, 50, 50, 380, 220, 3, "[ProductName] Setup", first, default, "Cancel" if name in ("WelcomeDlg", "MaintenanceDlg") else "Finish")])
        add("Control", [(name, "Title", "Text", 18, 16, 344, 30, 3, None, "{\\Heading}Yadof", None, None)])
        if name == "WelcomeDlg":
            add("Control", [(name, "Description", "Text", 18, 55, 344, 55, 3, None,
                              "Install Yadof and its private yadof_env Python runtime.\nHTCondor, frp and solver packages are excluded.", None, None),
                             (name, "LocationLabel", "Text", 18, 109, 344, 14, 3, None, "Installation folder:", None, None),
                             (name, "Location", "Edit", 18, 127, 260, 36, 65537, "INSTALLDIR", None, None, None),
                             (name, "Browse", "PushButton", 286, 127, 76, 22, 3, None, "&Browse...", "Install", None),
                             (name, "Install", "PushButton", 214, 180, 70, 20, 3, None, "Install", "Cancel", None),
                             (name, "Cancel", "PushButton", 292, 180, 70, 20, 3, None, "Cancel", "Browse", None)])
            add("ControlEvent", [(name, "Browse", "DoAction", "PickInstallFolder", "1", 1),
                                 (name, "Install", "DoAction", "CheckInstallFolder", "1", 1),
                                 (name, "Install", "SetTargetPath", "INSTALLDIR", 'YADOFINSTALLDIROK = "1"', 2),
                                 (name, "Install", "EndDialog", "Return", 'YADOFINSTALLDIROK = "1"', 3),
                                 (name, "Cancel", "EndDialog", "Exit", "1", 1)])
        elif name == "MaintenanceDlg":
            add("Control", [(name, "Description", "Text", 18, 60, 344, 65, 3, None, "Repair or remove Yadof and its private environment.\nExternal workspaces and solver environments are retained.", None, None),
                             (name, "Repair", "PushButton", 120, 180, 70, 20, 3, None, "Repair", "Remove", None),
                             (name, "Remove", "PushButton", 198, 180, 70, 20, 3, None, "Remove", "Cancel", None),
                             (name, "Cancel", "PushButton", 276, 180, 70, 20, 3, None, "Cancel", "Repair", None)])
            add("ControlEvent", [(name, "Repair", "[REINSTALL]", "ALL", "1", 1), (name, "Repair", "[REINSTALLMODE]", "amus", "1", 2),
                                 (name, "Repair", "EndDialog", "Return", "1", 3), (name, "Remove", "[REMOVE]", "ALL", "1", 1),
                                 (name, "Remove", "EndDialog", "Return", "1", 2), (name, "Cancel", "EndDialog", "Exit", "1", 1)])
        else:
            message = {"ExitDialog": "Setup completed. Open Yadof from your desktop or Start menu.", "FatalError": "Setup failed. Review the Windows Installer log for details.", "UserExit": "Setup was cancelled."}[name]
            add("Control", [(name, "Description", "Text", 18, 65, 344, 70, 3, None, message, None, None),
                             (name, "Finish", "PushButton", 292, 180, 70, 20, 3, None, "Close", None, None)])
            add("ControlEvent", [(name, "Finish", "EndDialog", "Return", "1", 1)])

    # Modeless UI remains open while ExecuteAction sends real MSI progress ticks.
    add("Dialog", [("ProgressDlg", 50, 50, 380, 220, 1, "[ProductName] Setup", "Cancel", "Cancel", "Cancel")])
    add("Control", [("ProgressDlg", "Title", "Text", 18, 16, 344, 30, 3, None, "{\\Heading}Setting up Yadof", None, None),
                    ("ProgressDlg", "Description", "Text", 18, 56, 344, 24, 3, None, "Please wait while Setup updates Yadof and yadof_env.", None, None),
                    ("ProgressDlg", "ActionText", "Text", 18, 88, 344, 20, 3, None, "Preparing installation...", None, None),
                    ("ProgressDlg", "Progress", "ProgressBar", 18, 116, 344, 16, 1, None, None, None, None),
                    ("ProgressDlg", "ActionData", "Text", 18, 140, 344, 24, 3, None, None, None, None),
                    ("ProgressDlg", "Cancel", "PushButton", 292, 180, 70, 20, 3, None, "Cancel", "Cancel", None)])
    add("EventMapping", [("ProgressDlg", "Progress", "SetProgress", "Progress"),
                         ("ProgressDlg", "ActionText", "ActionText", "Text"),
                         ("ProgressDlg", "ActionData", "ActionData", "Text")])
    add("ControlEvent", [("ProgressDlg", "Cancel", "SpawnDialog", "CancelDlg", "1", 1)])
    add("Dialog", [("CancelDlg", 50, 50, 300, 110, 3, "Cancel setup", "No", "No", "No")])
    add("Control", [("CancelDlg", "Prompt", "Text", 18, 18, 264, 38, 3, None, "Cancel setup? Changes in progress will be rolled back.", None, None),
                    ("CancelDlg", "Yes", "PushButton", 132, 72, 70, 20, 3, None, "Yes", "No", None),
                    ("CancelDlg", "No", "PushButton", 212, 72, 70, 20, 3, None, "No", "Yes", None)])
    add("ControlEvent", [("CancelDlg", "Yes", "EndDialog", "Exit", "1", 1),
                         ("CancelDlg", "No", "EndDialog", "Return", "1", 1)])
    add("Dialog", [("ErrorDlg", 50, 50, 380, 220, 65539, "[ProductName] Setup", "ErrorText", None, None)])
    add("Control", [("ErrorDlg", "ErrorText", "Text", 18, 18, 344, 145, 3, None, None, None, None)])
    for result in ("Abort", "Cancel", "Ignore", "No", "Ok", "Retry", "Yes"):
        button = "Error" + result
        add("Control", [("ErrorDlg", button, "PushButton", 18, 180, 70, 20, 3, None, result, None, None)])
        add("ControlEvent", [("ErrorDlg", button, "EndDialog", button, "1", 1)])


def build_database(payload: Path, work: Path, destination: Path, version: str, folder_picker: Path):
    import msilib as msi
    from msilib import schema, sequence
    files = sorted(path for path in payload.rglob("*") if path.is_file())
    if len(files) >= 32767:
        raise ValueError("Payload exceeds this MSI schema's file sequence limit")
    inventory = [{"path": path.relative_to(payload).as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)} for path in files]
    fingerprint = hashlib.sha256(json.dumps(inventory, sort_keys=True).encode()).hexdigest()
    maximum_directory_length = 258 - max(len(row["path"].encode("utf-16-le")) // 2 for row in inventory)
    product = guid("product:" + fingerprint + ":" + sha256(Path(__file__)) + ":" + sha256(folder_picker))
    db = msi.init_database(str(destination), schema, "Yadof", product, version, "Yadof")
    for table in ("InstallExecuteSequence", "InstallUISequence"):
        rows = list(getattr(sequence, table))
        rows = [(action, condition, 1501 if action == "RemoveExistingProducts" else order) for action, condition, order in rows]
        rows = [(action, condition, 300 if action == "LaunchConditions" else order) for action, condition, order in rows]
        msi.add_data(db, table, rows)
    msi.add_data(db, "Property", [("UpgradeCode", "{" + str(UPGRADE_ID).upper() + "}"), ("INSTALLLEVEL", "1"),
        ("ARPCONTACT", "Yadof"), ("ARPURLINFOABOUT", "https://github.com/YS-Pan/yadof"), ("ARPSIZE", str(sum(row["bytes"] for row in inventory) // 1024)),
        ("SecureCustomProperties", "PREVIOUSFOUND;NEWERFOUND"), ("MSIFASTINSTALL", "7"), ("REINSTALLMODE", "amus"),
        ("MAXINSTALLDIRCHARS", str(maximum_directory_length))])
    msi.add_data(db, "LaunchCondition", [("VersionNT64", "Yadof requires 64-bit Windows."), ("NOT NEWERFOUND", "A newer Yadof MSI is already installed.")])
    msi.add_data(db, "Upgrade", [("{" + str(UPGRADE_ID).upper() + "}", None, version, None, 513, None, "PREVIOUSFOUND"),
                                  ("{" + str(UPGRADE_ID).upper() + "}", version, None, None, 2, None, "NEWERFOUND")])
    msi.add_data(db, "CustomAction", [("SetInstallLocation", 51, "ARPINSTALLLOCATION", "[INSTALLDIR]"),
        ("RememberInstallDirectory", 51, "INSTALLDIR", "[REMEMBEREDINSTALLDIR]"),
        ("PickInstallFolder", 1, "FolderPicker", "PickInstallFolder"),
        ("CheckInstallFolder", 1, "FolderPicker", "CheckInstallFolder"),
        ("CheckInstallFolderForExecute", 1, "FolderPicker", "CheckInstallFolderForExecute")])
    msi.add_data(db, "Binary", [("FolderPicker", msi.Binary(str(folder_picker)))])
    msi.add_data(db, "AppSearch", [("REMEMBEREDINSTALLDIR", "InstallDirectorySearch")])
    msi.add_data(db, "RegLocator", [("InstallDirectorySearch", 1, r"Software\Yadof\Installer", "InstallDir", 18)])
    for table in ("InstallExecuteSequence", "InstallUISequence"):
        msi.add_data(db, table, [("RememberInstallDirectory", "REMEMBEREDINSTALLDIR AND NOT INSTALLDIR", 401)])
    msi.add_data(db, "InstallExecuteSequence", [("SetInstallLocation", "NOT REMOVE", 1010)])
    msi.add_data(db, "InstallExecuteSequence", [("CheckInstallFolderForExecute", "NOT REMOVE", 1005)])
    msi.add_data(db, "InstallUISequence", [("WelcomeDlg", "NOT Installed", 1210), ("MaintenanceDlg", "Installed", 1210),
                                          ("ProgressDlg", None, 1290)])
    msi.add_data(db, "Feature", [("Yadof", None, "Yadof and yadof_env", "Private Python and framework dependencies", 1, 1, "INSTALLDIR", 0)])
    msi.add_data(db, "Directory", [("TARGETDIR", None, "SourceDir"), ("LocalAppDataFolder", "TARGETDIR", "."),
        ("ProgramsDir", "LocalAppDataFolder", "Programs"), ("INSTALLDIR", "ProgramsDir", "Yadof"),
        ("DesktopFolder", "TARGETDIR", "."), ("ProgramMenuFolder", "TARGETDIR", "."), ("StartMenuDir", "ProgramMenuFolder", "Yadof"),
        ("PersonalFolder", "TARGETDIR", ".")])
    directory_ids = {Path("."): "INSTALLDIR"}
    directory_rows = []
    for directory in sorted({p.parent for p in files} | {parent for p in files for parent in p.relative_to(payload).parents if parent != Path(".")}, key=lambda p: (len(p.parts), str(p))):
        relative = directory.relative_to(payload) if directory.is_absolute() else directory
        if relative == Path(".") or relative in directory_ids:
            continue
        # Ensure empty ancestor directories also have Directory rows.
        for ancestor in reversed([relative, *relative.parents]):
            if ancestor == Path(".") or ancestor in directory_ids:
                continue
            key = identifier("D", ancestor.as_posix())
            directory_ids[ancestor] = key
            directory_rows.append((key, directory_ids[ancestor.parent], ancestor.name))
    msi.add_data(db, "Directory", directory_rows)
    cabinet = []
    component_rows, feature_rows, file_rows = [], [], []
    cab_sources = work / "cab_sources"
    cab_sources.mkdir(exist_ok=True)
    for number, path in enumerate(files, 1):
        relative = path.relative_to(payload)
        fid = identifier("F", relative.as_posix())
        cid = identifier("C", relative.as_posix())
        component_rows.append((cid, guid("file:" + relative.as_posix().lower()), directory_ids[relative.parent], 256, None, fid))
        feature_rows.append(("Yadof", cid))
        version_info, language_info = file_version(path)
        file_rows.append((fid, cid, path.name, path.stat().st_size, version_info, language_info, 512, number))
        # FCI has legacy path-length limits; use short hard-link aliases for its
        # input while keeping the real relative directory/file names in MSI.
        alias = cab_sources / fid
        if not alias.exists() or not os.path.samefile(path, alias):
            if alias.exists():
                alias.unlink()
            os.link(path, alias)
        cabinet.append((str(alias), fid))
    msi.add_data(db, "Component", component_rows)
    msi.add_data(db, "FeatureComponents", feature_rows)
    msi.add_data(db, "File", file_rows)
    msi.add_data(db, "Component", [("Shortcuts", guid("shortcuts:per-user"), "INSTALLDIR", 260, None, "ShortcutRegistry")])
    msi.add_data(db, "FeatureComponents", [("Yadof", "Shortcuts")])
    msi.add_data(db, "Registry", [("ShortcutRegistry", 1, r"Software\Yadof\Installer", "Installed", "1", "Shortcuts"),
        ("InstallDirectoryRegistry", 1, r"Software\Yadof\Installer", "InstallDir", "[INSTALLDIR]", "Shortcuts")])
    gui_id = identifier("F", "yadof_env/Scripts/yadof-gui.exe")
    msi.add_data(db, "Shortcut", [(name, directory, "Yadof", "Shortcuts", f"[#{gui_id}]", None, "Yadof desktop GUI", None, None, None, 1, "PersonalFolder")
                                   for name, directory in (("DesktopGUI", "DesktopFolder"), ("StartGUI", "StartMenuDir"))])
    msi.add_data(db, "RemoveFile", [("RemoveStartMenuDir", "Shortcuts", None, "StartMenuDir", 2)])
    add_dialogs(msi, db)
    db.Commit()
    cab = work / "payload.cab"
    print(f"Compressing {len(files)} files ({sum(row['bytes'] for row in inventory) / 1024**2:.1f} MiB)", flush=True)
    msi.FCICreate(str(cab), cabinet)
    msi.add_stream(db, "payload.cab", str(cab))
    msi.add_data(db, "Media", [(1, len(files), None, "#payload.cab", None, None)])
    db.Commit()
    db.Close()
    return {"product_code": product, "upgrade_code": "{" + str(UPGRADE_ID).upper() + "}", "version": version,
            "installer_source_sha256": sha256(Path(__file__)),
            "payload_sha256": fingerprint, "file_count": len(files), "files": inventory}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--runtime-source", type=Path, default=Path(sys.base_prefix))
    parser.add_argument("--reference-site", type=Path, action="append", default=[], help="Additional audited/extracted wheel site used before the build environment")
    parser.add_argument("--zig", type=Path, required=True, help="Path to the pinned Zig 0.14.1 compiler; build-time only")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reuse-payload", action="store_true", help="Rebuild MSI from this work directory's already-staged payload")
    args = parser.parse_args()
    if os.name != "nt" or sys.version_info[:3] != (3, 11, 15):
        parser.error("Use the audited Windows x64 CPython 3.11.15 builder")
    work = args.work.resolve()
    work.relative_to((ROOT / "temp").resolve())
    work.mkdir(parents=True, exist_ok=True)
    if args.reuse_payload:
        payload = work / "payload"
        info = json.loads((payload / "dependency-manifest.json").read_text(encoding="utf-8"))
        if info["wheel_sha256"] != sha256(args.wheel):
            raise ValueError("The staged payload belongs to a different wheel; use a new work directory")
    else:
        payload, info = prepare_payload(args.wheel.resolve(), work, args.runtime_source.resolve(), args.reference_site)
    for name, version in {**BASELINE, **ADDITIONAL}.items():
        if info["packages"].get(name) != version:
            raise ValueError(f"Staged payload does not match the version pin for {name}")
    copy_file(HERE / "README.md", payload / "INSTALLATION.md")
    version = wheel_metadata(args.wheel)["Version"]
    output = (args.output or ROOT / "dist" / f"yadof-{version}-a2094-win-x64.msi").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    candidate = work / "package.msi"
    folder_picker, picker_info = build_folder_picker(args.zig.resolve(), work)
    result = build_database(payload, work, candidate, version, folder_picker)
    os.replace(candidate, output)
    result.update({"msi": str(output), "sha256": sha256(output), "bytes": output.stat().st_size,
                   "built_at_utc": datetime.now(timezone.utc).isoformat(), "dependencies": info,
                   "folder_picker": picker_info})
    manifest = output.with_suffix(".manifest.json")
    manifest.write_text(json.dumps(result, indent=2), encoding="utf-8")
    output.with_suffix(".sha256").write_text(f"{result['sha256']}  {output.name}\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("files", "dependencies")}, indent=2), flush=True)


if __name__ == "__main__":
    main()
