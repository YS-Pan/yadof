from __future__ import annotations

import getpass
import json
import os
import platform
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path


def env_int(name: str, default: int, *, minimum: int) -> int:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else max(minimum, int(raw))


def env_float(name: str, default: float, *, minimum: float) -> float:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else max(minimum, float(raw))


def env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None or not raw.strip() else raw.strip().lower() not in {"0", "false", "no", "off"}


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def write_json(path: str | Path, data: Mapping[str, object]) -> None:
    path = Path(path)
    temp_path = path.with_name(path.name + ".tmp")
    temp_path.write_text(json.dumps(dict(data), ensure_ascii=True, indent=2), encoding="utf-8", newline="\n")
    os.replace(temp_path, path)


def raw_data_file_names(raw_data_dir: str | Path) -> list[str]:
    return [path.name for path in sorted(Path(raw_data_dir).glob("*.npz"))]


def bootstrap_home_dirs(base_dir: str | Path, temp_dir: str | Path) -> None:
    base_dir, temp_dir = Path(base_dir), Path(temp_dir)
    home_dir = base_dir / "_home"
    for key, path in {
        "USERPROFILE": home_dir,
        "HOME": home_dir,
        "APPDATA": base_dir / "_appdata",
        "LOCALAPPDATA": base_dir / "_localappdata",
        "TEMP": temp_dir,
        "TMP": temp_dir,
        "TMPDIR": temp_dir,
    }.items():
        os.environ[key] = str(path)
        path.mkdir(parents=True, exist_ok=True)
    _pin_windows_known_folders_to_job_home(home_dir)


def _pin_windows_known_folders_to_job_home(home_dir: Path) -> None:
    """Point Windows Documents to the per-job profile for Condor HFSS runs."""

    if os.name != "nt" or not os.environ.get("_CONDOR_SCRATCH_DIR"):
        return
    try:
        import winreg
    except ImportError:
        return

    documents = Path(home_dir) / "Documents"
    (documents / "Ansoft").mkdir(parents=True, exist_ok=True)
    user_shell_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
    shell_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"
    document_values = ("Personal", "{F42EE2D3-909F-4907-8871-4C22FC0BF756}")

    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, user_shell_key) as key:
            for name in document_values:
                winreg.SetValueEx(key, name, 0, winreg.REG_EXPAND_SZ, r"%USERPROFILE%\Documents")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, shell_key) as key:
            for name in document_values:
                winreg.SetValueEx(key, name, 0, winreg.REG_SZ, str(documents))
    except OSError as exc:
        print(f"WARNING: could not pin Windows Documents folder to job home: {exc}", file=sys.stderr, flush=True)


def runtime_identity(
    base_dir: str | Path,
    *,
    environment: Mapping[str, str] | None = None,
    extra: Mapping[str, object] | None = None,
) -> dict[str, str]:
    try:
        whoami = subprocess.run(
            ["whoami"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.strip()
    except Exception:
        whoami = ""
    identity = {
        "runtime_user": getpass.getuser(),
        "runtime_whoami": whoami,
        "runtime_cwd": str(Path(base_dir)),
        "runtime_python_executable": sys.executable,
        "runtime_platform": platform.platform(),
        "runtime_condor_scratch_dir": os.environ.get("_CONDOR_SCRATCH_DIR", ""),
        "runtime_userprofile": os.environ.get("USERPROFILE", ""),
        "runtime_appdata": os.environ.get("APPDATA", ""),
        "runtime_localappdata": os.environ.get("LOCALAPPDATA", ""),
        "runtime_temp": os.environ.get("TEMP", ""),
    }
    identity.update({str(key): os.environ.get(str(env_name), "") for key, env_name in (environment or {}).items()})
    identity.update({str(key): str(value) for key, value in (extra or {}).items()})
    return identity


def prepare_rawdata_dir(raw_data_dir: str | Path, transfer_zip: str | Path) -> None:
    raw_data_dir, transfer_zip = Path(raw_data_dir), Path(transfer_zip)
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    for path in raw_data_dir.glob("*.npz"):
        path.unlink()
    transfer_zip.unlink(missing_ok=True)


def write_rawdata_transfer_zip(raw_data_dir: str | Path, transfer_zip: str | Path) -> None:
    raw_data_dir, transfer_zip = Path(raw_data_dir), Path(transfer_zip)
    files = sorted(raw_data_dir.glob("*.npz"))
    if not files:
        transfer_zip.unlink(missing_ok=True)
        return
    temp_path = transfer_zip.with_name(transfer_zip.name + ".tmp")
    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    os.replace(temp_path, transfer_zip)


__all__ = [
    "bootstrap_home_dirs",
    "env_bool",
    "env_float",
    "env_int",
    "now_text",
    "prepare_rawdata_dir",
    "raw_data_file_names",
    "runtime_identity",
    "write_json",
    "write_rawdata_transfer_zip",
]
