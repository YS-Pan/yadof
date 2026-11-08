"""An installer rebuilt from a prior runtime must regenerate its launchers."""
from pathlib import Path
import hashlib
import json
import runpy
import zipfile


def test_runtime_reuse_rebuilds_launchers_without_mutating_reference(tmp_path, monkeypatch):
    module = runpy.run_path(str(Path(__file__).with_name("build_msi.py")))
    source, work = tmp_path / "previous", tmp_path / "build"
    source.mkdir()
    work.mkdir()
    files = {
        "dependency-manifest.json": json.dumps({"packages": {"numpy": "2.4.6"}}).encode(),
        "yadof_env/Scripts/yadof-gui.exe": b"old launcher",
        "yadof_env/Lib/site-packages/yadof/old.py": b"old package",
    }
    inventory = []
    for name, content in files.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        inventory.append({"path": name, "sha256": hashlib.sha256(content).hexdigest()})
    manifest = tmp_path / "previous.manifest.json"
    manifest.write_text(json.dumps({"files": inventory}), encoding="utf-8")
    wheel = tmp_path / "yadof-0.8.1-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("yadof/new.py", b"current package")
    launches = []

    def launchers(prefix):
        launches.append(prefix)
        (prefix / "Scripts/yadof-gui.exe").write_bytes(b"current launcher")

    monkeypatch.setitem(module["payload_from_installation"].__globals__, "stage_launchers", launchers)
    payload, info = module["payload_from_installation"](wheel, work, source, manifest)
    assert launches == [payload / "yadof_env"]
    assert (payload / "yadof_env/Scripts/yadof-gui.exe").read_bytes() == b"current launcher"
    assert (source / "yadof_env/Scripts/yadof-gui.exe").read_bytes() == b"old launcher"
    assert not (payload / "yadof_env/Lib/site-packages/yadof/old.py").exists()
    assert (payload / "yadof_env/Lib/site-packages/yadof/new.py").read_bytes() == b"current package"
    assert info["wheel"] == wheel.name


def test_msi_declares_filename_codepage_before_localized_rows(tmp_path):
    import ctypes
    import pytest
    pytest.importorskip("_msi")
    import msilib
    from msilib import schema

    module = runpy.run_path(str(Path(__file__).with_name("build_msi.py")))
    package = tmp_path / "codepage.msi"
    database = msilib.init_database(str(package), schema, "Test", msilib.gen_uuid(), "0.8.1", "Test")
    database.Close()
    module["set_database_codepage"](package, tmp_path)
    database = msilib.OpenDatabase(str(package), msilib.MSIDBOPEN_TRANSACT)
    msilib.add_data(database, "Directory", [("Localized", None, "中文目录")])
    database.Commit()
    database.Close()
    database = msilib.OpenDatabase(str(package), msilib.MSIDBOPEN_READONLY)
    view = database.OpenView("SELECT `DefaultDir` FROM `Directory` WHERE `Directory` = 'Localized'")
    view.Execute(None)
    assert view.Fetch().GetString(1) == "中文目录"
    view.Close()
    database.Close()
    api = ctypes.WinDLL("msi")
    api.MsiOpenDatabaseW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint)]
    api.MsiDatabaseExportW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_wchar_p]
    api.MsiCloseHandle.argtypes = [ctypes.c_uint]
    handle = ctypes.c_uint()
    assert api.MsiOpenDatabaseW(str(package), None, ctypes.byref(handle)) == 0
    try:
        assert api.MsiDatabaseExportW(handle, "_ForceCodepage", str(tmp_path), "export.idt") == 0
    finally:
        api.MsiCloseHandle(handle)
    assert (tmp_path / "export.idt").read_bytes() == b"\r\n\r\n936\t_ForceCodepage\r\n"
