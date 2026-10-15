"""The double-click entry must use its own installed distribution."""

from __future__ import annotations

import os
import json
from pathlib import Path
import runpy
import subprocess
import sys
import venv

import pytest
import yadof


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = Path(yadof.__file__).parent / "tools/condor_gui.pyw"


@pytest.mark.parametrize("layout", ("Scripts", "Lib/site-packages/yadof/tools", "site-packages/yadof/tools"))
def test_launcher_resolves_only_its_installation(tmp_path, layout):
    installed = tmp_path / "环境 with spaces"
    launcher = installed / layout / "condor_gui.pyw"
    launcher.parent.mkdir(parents=True)
    executable = installed / "Scripts/yadof-gui.exe"
    executable.parent.mkdir(exist_ok=True)
    executable.touch()
    resolve = runpy.run_path(str(LAUNCHER))["_gui_executable"]

    assert resolve(launcher) == executable.resolve()

    executable.unlink()
    # An unrelated environment above this one must not be selected as a fallback.
    unrelated = tmp_path / "Scripts/yadof-gui.exe"
    unrelated.parent.mkdir()
    unrelated.touch()
    with pytest.raises(FileNotFoundError, match="Reinstall yadof"):
        resolve(launcher)


@pytest.mark.skipif(os.name != "nt", reason="Windows file association forwarding")
def test_launcher_preserves_arguments_and_exit_code(tmp_path, monkeypatch):
    launcher = tmp_path / "Scripts/condor_gui.pyw"
    launcher.parent.mkdir()
    launcher.write_bytes(LAUNCHER.read_bytes())
    executable = launcher.with_name("yadof-gui.exe")
    executable.touch()
    args = ["--workspace", str(tmp_path / "study 空格 folder")]
    monkeypatch.setattr(sys, "argv", [str(launcher), *args])
    calls = []
    monkeypatch.setattr(subprocess, "call", lambda command: calls.append(command) or 9)

    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(launcher), run_name="__main__")

    assert calls == [[str(executable.resolve()), *args]]
    assert stopped.value.code == 9


def _run(command, cwd, *, env_overrides=None):
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment["PYTHONIOENCODING"] = "utf-8"
    environment.update(env_overrides or {})
    return subprocess.run(
        [str(value) for value in command], cwd=cwd, env=environment,
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows installed double-click entry")
def test_normal_pip_install_publishes_source_independent_launcher(tmp_path):
    wheel_dir = tmp_path / "release"
    built = _run([
        sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", wheel_dir,
    ], ROOT)
    assert built.returncode == 0, built.stdout + built.stderr
    wheel = next(wheel_dir.glob("yadof-*.whl"))
    prefix = tmp_path / "安装 environment"
    # Dependencies are already provisioned; only yadof itself is installed here.
    venv.EnvBuilder(with_pip=True, system_site_packages=True).create(prefix)
    python = prefix / "Scripts/python.exe"
    installed = _run([
        python, "-m", "pip", "install", "--force-reinstall", "--no-deps", wheel,
    ], tmp_path)
    assert installed.returncode == 0, installed.stdout + installed.stderr
    launcher = prefix / "Scripts/condor_gui.pyw"
    assert launcher.is_file()
    probe = _run([
        python, "-c", "import pathlib,yadof; print(pathlib.Path(yadof.__file__).resolve())",
    ], tmp_path)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    package_file = Path(probe.stdout.strip())
    assert prefix in package_file.parents

    wheel.unlink()
    support = tmp_path / "probe_support"
    support.mkdir()
    (support / "sitecustomize.py").write_text(
        "import json,os,pathlib,sys,yadof\n"
        "pathlib.Path(os.environ['YADOF_TEST_LAUNCH_PROBE']).write_text("
        "json.dumps({'python':sys.executable,'package':yadof.__file__}), encoding='utf-8')\n",
        encoding="utf-8",
    )
    evidence = tmp_path / "launch.json"
    # Deliberately run both copies with another environment's Python, as file
    # associations may do. The executable they find remains bound to this prefix.
    for host in (Path(sys.executable), Path(sys.executable).with_name("pythonw.exe")):
        for entry in (launcher, package_file.parent / "tools/condor_gui.pyw"):
            launched = _run([host, entry, "--help"], tmp_path, env_overrides={
                "PYTHONPATH": str(support), "YADOF_TEST_LAUNCH_PROBE": str(evidence),
            })
            assert launched.returncode == 0, launched.stdout + launched.stderr
            observed = json.loads(evidence.read_text(encoding="utf-8"))
            assert Path(observed["python"]).parent == prefix / "Scripts"
            assert prefix in Path(observed["package"]).parents

    removed = _run([python, "-m", "pip", "uninstall", "--yes", "yadof"], tmp_path)
    assert removed.returncode == 0, removed.stdout + removed.stderr
    assert not launcher.exists()
