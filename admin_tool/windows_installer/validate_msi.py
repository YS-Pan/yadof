"""Exercise an MSI in an explicit temporary prefix, then uninstall that product."""

from __future__ import annotations

import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
PROBE = r'''
import importlib.metadata as metadata
import importlib.util
import json
import pathlib
import site
import sys
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
prefix = pathlib.Path(sys.executable).resolve().parent.parent
manifest = json.loads((prefix.parent / 'dependency-manifest.json').read_text())
assert sys.flags.isolated and sys.flags.ignore_environment
assert not site.ENABLE_USER_SITE
assert 'yadof_env' == prefix.name
assert sys.prefix == sys.base_prefix == str(prefix)
assert importlib.util.find_spec('pyaedt') is None
assert all('site-packages' not in path.lower() or pathlib.Path(path).is_relative_to(prefix) for path in sys.path)
versions = {canonicalize_name(d.metadata['Name']): d.version for d in metadata.distributions() if d.metadata['Name']}
assert not ({'pyaedt','ansys-aedt-core','htcondor','pychrono','conda-pack'} & versions.keys())
for name, version in manifest['packages'].items():
    assert versions[name] == version, (name, versions.get(name), version)
for d in metadata.distributions():
    for value in d.requires or []:
        r = Requirement(value)
        if r.marker is None or r.marker.evaluate({'extra':''}):
            name = canonicalize_name(r.name)
            assert name in versions and r.specifier.contains(versions[name]), (d.metadata['Name'], str(r), versions.get(name))
import numpy as np
import scipy.linalg
import psutil
import pymoo
from pymoo.indicators.hv import HV
import torch
import sklearn
from sklearn.gaussian_process import GaussianProcessRegressor
import botorch
import gpytorch
import linear_operator
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt
assert np.allclose(scipy.linalg.solve(np.eye(2), np.ones(2)), [1,1])
assert HV(ref_point=np.ones(2))(np.array([[0.2,0.3]])) > 0
assert torch.ones(2).sum().item() == 2
GaussianProcessRegressor().fit(np.array([[0.],[1.]]), np.array([0.,1.])).predict(np.array([[0.5]]))
fig, ax = plt.subplots(); ax.plot([0,1],[0,1]); fig.savefig(pathlib.Path(sys.argv[1])/'plot.png'); plt.close(fig)
import tkinter as tk
root = tk.Tk(); root.withdraw()
from yadof.tools import condor_gui
condor_gui.query_status = lambda: []
controller = condor_gui.CondorGUI(root, pathlib.Path(sys.argv[1])/'gui workspace')
root.update(); root.destroy()
import yadof
assert pathlib.Path(yadof.__file__).is_relative_to(prefix)
result = {'python':sys.version,'executable':sys.executable,'yadof':yadof.__version__,'yadof_origin':yadof.__file__,'numpy':np.__version__,'torch':torch.__version__,'torch_cuda':torch.version.cuda,'matplotlib':matplotlib.__version__,'sklearn':sklearn.__version__,'isolated':sys.flags.isolated,'user_site':site.ENABLE_USER_SITE,'package_count':len(versions),'tk_gui':True}
(pathlib.Path(sys.argv[1])/'runtime-evidence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
'''


def run(args, work: Path, label: str, *, expected=0, environment=None):
    command = [str(arg) for arg in args]
    if Path(command[0]).name.casefold() == "msiexec.exe":
        # msiexec parses MSI properties itself; quote the value, not the entire
        # NAME=value token, when a destination contains spaces.
        command = " ".join((arg.split("=", 1)[0] + "=" + subprocess.list2cmdline([arg.split("=", 1)[1]]))
                           if arg.startswith("INSTALLDIR=") else subprocess.list2cmdline([arg]) for arg in command)
    result = subprocess.run(command, cwd=work, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=600, env=environment)
    (work / f"{label}.txt").write_text(result.stdout + result.stderr, encoding="utf-8")
    if result.returncode != expected:
        raise RuntimeError(f"{label}: exit {result.returncode}, expected {expected}; see {work / (label + '.txt')}")
    print(f"PASS {label}", flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--msi", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.relative_to((ROOT / "temp").resolve())
    work.mkdir(parents=True, exist_ok=False)
    msi = args.msi.resolve()
    manifest = json.loads(msi.with_suffix(".manifest.json").read_text(encoding="utf-8"))
    product = manifest["product_code"]
    installer = ctypes.WinDLL("msi")
    installer.MsiQueryProductStateW.argtypes = [ctypes.c_wchar_p]
    if installer.MsiQueryProductStateW(product) != -1:
        raise RuntimeError("This exact MSI product is already registered; refusing to change its existing installation")
    related = ctypes.create_unicode_buffer(39)
    installer.MsiEnumRelatedProductsW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint, ctypes.c_wchar_p]
    if installer.MsiEnumRelatedProductsW(manifest["upgrade_code"], 0, 0, related) == 0:
        raise RuntimeError("An MSI in this upgrade family is already installed; acceptance must not replace a user's installation")
    shortcut_backups = {}
    shell = ctypes.WinDLL("shell32")
    for csidl, relative in ((0x10, "Yadof.lnk"), (0x02, "Yadof/Yadof.lnk")):
        folder = ctypes.create_unicode_buffer(260)
        if shell.SHGetFolderPathW(None, csidl, None, 0, folder) == 0:
            shortcut = Path(folder.value) / relative
            if shortcut.is_file():
                shortcut_backups[shortcut] = shortcut.read_bytes()
    destination = work / "安装 with spaces" / "Yadof"
    longest_relative_path = max(len(item["path"].encode("utf-16-le")) // 2 for item in manifest["files"])
    if len(str(destination).encode("utf-16-le")) // 2 + 1 + longest_relative_path >= 260:
        raise ValueError("Acceptance destination exceeds MSI path limits; choose a shorter --work path below temp/")
    cli = destination / "yadof_env/Scripts/yadof.exe"
    python = destination / "yadof_env/Scripts/python.exe"
    workspace = work / "external workspace 中文"
    sentinel = work / "external-user-data.txt"
    sentinel.write_text("preserve me", encoding="utf-8")
    upgrade_product = None
    try:
        run(["msiexec.exe", "/i", msi, "/qn", "/norestart", f"INSTALLDIR={destination}", "/L*v", work / "install.log"], work, "install")
        run([cli, "version"], work, "version")
        run([destination / "yadof_env/Scripts/yadof-gui.exe", "--help"], work, "gui-launcher")
        # Foreign Python settings must not make the private runtime import them.
        foreign = work / "foreign-python"
        foreign.mkdir()
        (foreign / "pyaedt.py").write_text("raise RuntimeError('foreign solver imported')", encoding="utf-8")
        environment = os.environ.copy()
        environment.update({"PYTHONPATH": str(foreign), "PYTHONHOME": str(foreign), "MPLCONFIGDIR": str(work / "matplotlib-cache"),
                            "PATH": str(Path(os.environ["WINDIR"]) / "System32") + os.pathsep + os.environ["WINDIR"],
                            "CONDA_PREFIX": str(foreign)})
        probe = work / "runtime_probe.py"
        probe.write_text(PROBE, encoding="utf-8")
        run([python, "-B", probe, work], work, "runtime", environment=environment)
        run([cli, "docs", "show", "user", "README.md"], work, "installed-docs")
        run([cli, "init", workspace], work, "init")
        run([cli, "check", "--workspace", workspace], work, "check")
        run([cli, "smoke-test", "--workspace", workspace], work, "generic-local-smoke")
        run([cli, "run", "--workspace", workspace, "--generations", "1", "--population-size", "4", "--no-smoke-test"], work, "generic-generation")
        # Test explicit repair of an installer-owned file only, under our temp prefix.
        repair_target = destination / "yadof_env/Lib/site-packages/yadof/_version.py"
        assert repair_target.resolve().is_relative_to(destination.resolve())
        repair_target.unlink()
        run(["msiexec.exe", "/fa", product, "/qn", "/norestart", "/L*v", work / "repair.log"], work, "repair")
        run([cli, "version"], work, "repaired-version")
        assert repair_target.is_file()
        # A second product with the same payload/version exercises the published
        # same-version upgrade policy without modifying the release artifact.
        import msilib
        upgrade_msi = work / "same-version-upgrade.msi"
        shutil.copy2(msi, upgrade_msi)
        upgrade_product = "{" + str(uuid.uuid4()).upper() + "}"
        db = msilib.OpenDatabase(str(upgrade_msi), msilib.MSIDBOPEN_TRANSACT)
        view = db.OpenView("UPDATE `Property` SET `Value` = ? WHERE `Property` = 'ProductCode'")
        record = msilib.CreateRecord(1)
        record.SetString(1, upgrade_product)
        view.Execute(record)
        view.Close()
        summary = db.GetSummaryInformation(20)
        summary.SetProperty(msilib.PID_REVNUMBER, "{" + str(uuid.uuid4()).upper() + "}")
        summary.Persist()
        del summary  # Release its MSI file handle before invoking another installer.
        db.Commit()
        db.Close()
        del db, view, record
        installer.MsiVerifyPackageW.argtypes = [ctypes.c_wchar_p]
        assert installer.MsiVerifyPackageW(str(upgrade_msi)) == 0
        unknown = destination / "user-not-owned.txt"
        unknown.write_text("retain unknown files", encoding="utf-8")
        run(["msiexec.exe", "/i", upgrade_msi, "/qn", "/norestart", "/L*v", work / "upgrade.log"], work, "same-version-upgrade")
        assert installer.MsiQueryProductStateW(product) == -1
        assert installer.MsiQueryProductStateW(upgrade_product) == 5
        run([cli, "version"], work, "upgraded-version")
        upgraded_evidence = work / "after-upgrade"
        upgraded_evidence.mkdir()
        run([python, "-B", probe, upgraded_evidence], work, "upgraded-runtime", environment=environment)
    finally:
        for candidate in (upgrade_product, product):
            if candidate and installer.MsiQueryProductStateW(candidate) != -1:
                label = "uninstall" if candidate == (upgrade_product or product) else "cleanup-original"
                run(["msiexec.exe", "/x", candidate, "/qn", "/norestart", "/L*v", work / (label + ".log")], work, label)
        for shortcut, content in shortcut_backups.items():
            shortcut.parent.mkdir(parents=True, exist_ok=True)
            shortcut.write_bytes(content)
    assert not python.exists()
    assert sentinel.read_text(encoding="utf-8") == "preserve me"
    assert (workspace / ".yadof/workspace.json").is_file()
    assert unknown.read_text(encoding="utf-8") == "retain unknown files"
    assert installer.MsiQueryProductStateW(product) == -1
    (work / "acceptance.json").write_text(json.dumps({"msi":str(msi), "sha256":manifest["sha256"], "product_code":product,
        "status":"passed", "checks":["installation", "CLI", "GUI launcher and Tk controller", "dependency/native imports", "isolation", "installed docs", "task init/check", "local smoke", "one four-individual generation", "repair", "same-version upgrade", "uninstall", "external and unknown data preserved"]},indent=2), encoding="utf-8")
    print(f"Acceptance passed: {work / 'acceptance.json'}", flush=True)


if __name__ == "__main__":
    main()
