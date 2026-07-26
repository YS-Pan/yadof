from __future__ import annotations

import getpass
import json
import os
import platform
import shutil
import subprocess
import sys
import traceback
import zipfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


RAWDATA_SCHEMA_VERSION = 1
_WORKFLOW_METADATA_KEYS = {
    "ended_at",
    "error_message",
    "error_type",
    "execute_machine",
    "raw_data_files",
    "secondary_errors",
    "started_at",
    "status",
    "traceback_tail",
}


@dataclass(frozen=True)
class WorkflowContext:
    """Fixed execute-side paths and provenance supplied to task-specific work."""

    base_dir: Path
    raw_data_dir: Path
    raw_data_transfer_zip: Path
    individual_metadata_path: Path
    temp_dir: Path
    started_at: str
    runtime_metadata: Mapping[str, str]


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


def execute_machine_name() -> str:
    """Return the computer name observed by the running execute-side process."""

    for value in (
        platform.node(),
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("HOSTNAME", ""),
    ):
        name = str(value or "").strip()
        if name:
            return name
    return "unknown"


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
        "execute_machine": execute_machine_name(),
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
    _merge_unique(
        identity,
        {
            str(key): os.environ.get(str(env_name), "")
            for key, env_name in (environment or {}).items()
        },
        source="runtime environment metadata",
    )
    _merge_unique(
        identity,
        {str(key): str(value) for key, value in (extra or {}).items()},
        source="runtime extra metadata",
    )
    return identity


def prepare_rawdata_dir(raw_data_dir: str | Path, transfer_zip: str | Path) -> None:
    raw_data_dir, transfer_zip = Path(raw_data_dir), Path(transfer_zip)
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    for path in raw_data_dir.iterdir():
        if path.is_dir():
            raise ValueError(
                f"rawData must be flat; remove nested directory: {path.name}"
            )
        path.unlink()
    transfer_zip.unlink(missing_ok=True)


def write_rawdata_transfer_zip(raw_data_dir: str | Path, transfer_zip: str | Path) -> None:
    raw_data_dir, transfer_zip = Path(raw_data_dir), Path(transfer_zip)
    raw_data_dir.mkdir(parents=True, exist_ok=True)
    entries = sorted(raw_data_dir.iterdir(), key=lambda path: path.name.casefold())
    invalid = [
        path.name
        for path in entries
        if path.is_dir() or not path.is_file() or path.suffix.casefold() != ".npz"
    ]
    files = [path for path in entries if path.is_file() and path.suffix.casefold() == ".npz"]
    temp_path = transfer_zip.with_name(transfer_zip.name + ".tmp")
    with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            archive.write(path, arcname=path.name)
    os.replace(temp_path, transfer_zip)
    if invalid:
        raise ValueError(
            "rawData must contain only direct .npz files; invalid entries: "
            + ", ".join(invalid)
        )


def rawdata_metadata(
    name: str,
    shape: Sequence[int],
    *,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Build the invariant metadata fields for one task-specific rawData item."""

    metadata = dict(extra or {})
    metadata.update(
        {
            "schema_version": RAWDATA_SCHEMA_VERSION,
            "rawdata_name": str(name),
            "shape": [int(size) for size in shape],
        }
    )
    return metadata


def run_workflow(
    operation: Callable[[WorkflowContext], object],
    *,
    cleanup: Callable[[WorkflowContext], None] | None = None,
    metadata: Mapping[str, object] | None = None,
    runtime_environment: Mapping[str, str] | None = None,
    runtime_extra: Mapping[str, object] | None = None,
) -> object:
    """Run task-specific work inside yadof's invariant worker lifecycle."""

    if not callable(operation):
        raise TypeError("operation must be callable")
    if cleanup is not None and not callable(cleanup):
        raise TypeError("cleanup must be callable")

    task_metadata = {str(key): value for key, value in (metadata or {}).items()}
    reserved = sorted(_WORKFLOW_METADATA_KEYS.intersection(task_metadata))
    if reserved:
        raise ValueError(
            "task metadata cannot override workflow-owned fields: "
            + ", ".join(reserved)
        )

    base_dir = Path(__file__).resolve().parent
    raw_data_dir = base_dir / "rawData"
    raw_data_transfer_zip = base_dir / "rawData.zip"
    individual_metadata_path = base_dir / "individual_metadata.json"
    temp_dir = base_dir / "_tmp"
    started_at = now_text()

    bootstrap_home_dirs(base_dir, temp_dir)
    runtime_metadata = runtime_identity(
        base_dir,
        environment=runtime_environment,
        extra=runtime_extra,
    )
    context = WorkflowContext(
        base_dir=base_dir,
        raw_data_dir=raw_data_dir,
        raw_data_transfer_zip=raw_data_transfer_zip,
        individual_metadata_path=individual_metadata_path,
        temp_dir=temp_dir,
        started_at=started_at,
        runtime_metadata=runtime_metadata,
    )
    write_json(
        individual_metadata_path,
        {
            **task_metadata,
            **runtime_metadata,
            "status": "running",
            "started_at": started_at,
        },
    )

    result: object = None
    primary_error: tuple[Exception, object, str] | None = None
    secondary_errors: list[str] = []
    try:
        prepare_rawdata_dir(raw_data_dir, raw_data_transfer_zip)
        result = operation(context)
    except Exception as exc:
        primary_error = (exc, exc.__traceback__, _exception_text(exc))

    try:
        write_rawdata_transfer_zip(raw_data_dir, raw_data_transfer_zip)
    except Exception as exc:
        if primary_error is None:
            primary_error = (exc, exc.__traceback__, _exception_text(exc))
        else:
            secondary_errors.append(f"rawData packaging failed: {exc}")

    if cleanup is not None:
        try:
            cleanup(context)
        except Exception as exc:
            if primary_error is None:
                primary_error = (exc, exc.__traceback__, _exception_text(exc))
            else:
                secondary_errors.append(f"workflow cleanup failed: {exc}")
                print(
                    f"WARNING: workflow cleanup failed after another error: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

    _remove_runtime_dirs(context)

    final_metadata: dict[str, object] = {
        **task_metadata,
        **runtime_metadata,
        "status": "done" if primary_error is None else "error",
        "started_at": started_at,
        "ended_at": now_text(),
        "raw_data_files": raw_data_file_names(raw_data_dir),
    }
    if primary_error is not None:
        error, error_traceback, traceback_text = primary_error
        final_metadata.update(
            {
                "error_type": type(error).__name__,
                "error_message": str(error),
                "traceback_tail": traceback_text[-4000:],
            }
        )
        if secondary_errors:
            final_metadata["secondary_errors"] = secondary_errors
    write_json(individual_metadata_path, final_metadata)

    if primary_error is not None:
        error, error_traceback, _traceback_text = primary_error
        raise error.with_traceback(error_traceback)
    return result


def _exception_text(error: Exception) -> str:
    return "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )


def _remove_runtime_dirs(context: WorkflowContext) -> None:
    for path in (
        context.base_dir / "_home",
        context.base_dir / "_appdata",
        context.base_dir / "_localappdata",
        context.temp_dir,
    ):
        shutil.rmtree(path, ignore_errors=True)


def _merge_unique(
    target: dict[str, str],
    values: Mapping[str, str],
    *,
    source: str,
) -> None:
    duplicates = sorted(set(target).intersection(values))
    if duplicates:
        raise ValueError(
            f"{source} cannot override runtime identity fields: "
            + ", ".join(duplicates)
        )
    target.update(values)


__all__ = [
    "bootstrap_home_dirs",
    "env_bool",
    "env_float",
    "env_int",
    "execute_machine_name",
    "now_text",
    "prepare_rawdata_dir",
    "rawdata_metadata",
    "raw_data_file_names",
    "run_workflow",
    "runtime_identity",
    "RAWDATA_SCHEMA_VERSION",
    "WorkflowContext",
    "write_json",
    "write_rawdata_transfer_zip",
]
