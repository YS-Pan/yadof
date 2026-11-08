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
