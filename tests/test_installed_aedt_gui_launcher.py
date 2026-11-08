"""The installed folder launcher must stay bound to its owning runtime."""

from pathlib import Path
import runpy
import sys

import pytest
import yadof


def _launcher():
    path = Path(yadof.__file__).resolve().parent / "tools/user_tools/aedt_parameters_gui.pyw"
    assert path.is_file()
    return runpy.run_path(str(path))


@pytest.mark.parametrize("runtime_path", ("Scripts/pythonw.exe", "pythonw.exe"))
def test_launcher_resolves_the_owning_runtime(tmp_path, runtime_path):
    namespace = _launcher()
    prefix = tmp_path / "安装 environment"
    script = prefix / "Lib/site-packages/yadof/tools/user_tools/aedt_parameters_gui.pyw"
    runtime = prefix / runtime_path
    runtime.parent.mkdir(parents=True)
    runtime.touch()

    assert namespace["_runtime"](script) == runtime


def test_launcher_does_not_fall_back_to_another_environment(tmp_path):
    runtime = _launcher()["_runtime"]
    with pytest.raises(FileNotFoundError, match="belonging to this yadof"):
        runtime(tmp_path / "Lib/site-packages/yadof/tools/user_tools/aedt_parameters_gui.pyw")
    with pytest.raises(FileNotFoundError, match="installed user_tools"):
        runtime(tmp_path / "source/yadof/tools/user_tools/aedt_parameters_gui.pyw")


def test_launcher_forwards_to_its_own_runtime_from_another_python(tmp_path, monkeypatch):
    namespace = _launcher()
    prefix = tmp_path / "安装 environment"
    script = prefix / "Lib/site-packages/yadof/tools/user_tools/aedt_parameters_gui.pyw"
    runtime = prefix / "Scripts/pythonw.exe"
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    namespace["main"].__globals__["__file__"] = str(script)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "other/pythonw.exe"))
    monkeypatch.setattr(sys, "argv", [str(script), "argument with spaces"])
    calls = []
    monkeypatch.setattr(namespace["subprocess"], "call", lambda args: calls.append(args) or 7)

    assert namespace["main"]() == 7
    assert calls == [[str(runtime), str(script), "argument with spaces"]]


def test_installed_launcher_uses_a_user_writable_default_backup(tmp_path, monkeypatch):
    namespace = _launcher()
    calls = []
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "用户数据"))
    root = type("Root", (), {"mainloop": lambda self: None})()
    monkeypatch.setattr(namespace["tk"], "Tk", lambda: root)
    monkeypatch.setitem(namespace["main"].__globals__, "AedtParametersApp", lambda parent, **kwargs: calls.append(kwargs))
    monkeypatch.setattr(sys, "executable", str(namespace["_runtime"](Path(namespace["__file__"]))))

    assert namespace["main"]() == 0
    assert calls == [{"script_dir": tmp_path / "用户数据/Yadof"}]
    assert not (tmp_path / "用户数据").exists()
