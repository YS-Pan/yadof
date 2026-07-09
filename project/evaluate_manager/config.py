from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

try:
    from project import config_all as project_config
except ImportError:  # Allows running from inside the project package directory.
    from .. import config_all as project_config

PROJECT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_JOBS_DIR = PROJECT_DIR / "jobs"
DEFAULT_JOB_TEMPLATE_DIR = PROJECT_DIR / "job_template"

DEFAULT_TIMEOUT_SEC = float(getattr(project_config, "EVALUATION_TIMEOUT_SEC", 60.0 * 60.0))
DEFAULT_MODE = str(getattr(project_config, "EVALUATION_MODE", "local"))
DEFAULT_LOCAL_EVALUATION_MAX_WORKERS = int(getattr(project_config, "LOCAL_EVALUATION_MAX_WORKERS", 1))
DEFAULT_HTCONDOR_SUBMIT_EXE = str(getattr(project_config, "HTCONDOR_SUBMIT_EXE", "condor_submit"))
DEFAULT_HTCONDOR_REMOVE_EXE = str(getattr(project_config, "HTCONDOR_REMOVE_EXE", "condor_rm"))
DEFAULT_HTCONDOR_EXECUTABLE_MODE = str(getattr(project_config, "HTCONDOR_EXECUTABLE_MODE", "python"))
DEFAULT_HTCONDOR_PYTHON_EXE = str(getattr(project_config, "HTCONDOR_PYTHON_EXE", "python"))
DEFAULT_HTCONDOR_POLL_SEC = float(getattr(project_config, "HTCONDOR_POLL_SEC", 30.0))
DEFAULT_HTCONDOR_REQUEST_CPUS = int(getattr(project_config, "HTCONDOR_REQUEST_CPUS", 1))
DEFAULT_HTCONDOR_REQUEST_MEMORY = str(getattr(project_config, "HTCONDOR_REQUEST_MEMORY", "4GB"))
DEFAULT_HTCONDOR_REQUEST_DISK = str(getattr(project_config, "HTCONDOR_REQUEST_DISK", "2GB"))
DEFAULT_HTCONDOR_ENVIRONMENT = str(getattr(project_config, "HTCONDOR_ENVIRONMENT", ""))
DEFAULT_HTCONDOR_LOAD_PROFILE = bool(getattr(project_config, "HTCONDOR_LOAD_PROFILE", True))
DEFAULT_HTCONDOR_RUN_AS_OWNER = bool(getattr(project_config, "HTCONDOR_RUN_AS_OWNER", False))
DEFAULT_HTCONDOR_REQUIREMENTS = str(getattr(project_config, "HTCONDOR_REQUIREMENTS", '(OpSys == "WINDOWS")'))
DEFAULT_HTCONDOR_ALLOWED_MACHINES: tuple[str, ...] = tuple(getattr(project_config, "HTCONDOR_ALLOWED_MACHINES", ()))
DEFAULT_HTCONDOR_EXCLUDED_MACHINES: tuple[str, ...] = tuple(getattr(project_config, "HTCONDOR_EXCLUDED_MACHINES", ()))
FINAL_STATUSES = {"done", "error", "timeout"}
WORKFLOW_SCRIPT_NAME = "workflow.py"
PROJECT_CONFIG_FILE_NAME = "config.py"
PROJECT_CONFIG_ALL_FILE_NAME = "config_all.py"
RAW_DATA_DIR_NAME = "rawData"
RAW_DATA_TRANSFER_ZIP_NAME = "rawData_outputs.zip"
INDIVIDUAL_METADATA_FILE_NAME = "individual_metadata.json"
CONDOR_SUBMIT_FILE_NAME = "job.sub"
CONDOR_STDOUT_FILE_NAME = "stdout.txt"
CONDOR_STDERR_FILE_NAME = "stderr.txt"
CONDOR_LOG_FILE_NAME = "condor.log"
CONDOR_SUBMIT_STDOUT_FILE_NAME = "condor_submit.stdout.txt"
CONDOR_SUBMIT_STDERR_FILE_NAME = "condor_submit.stderr.txt"
CONDOR_CLUSTER_ID_FILE_NAME = "cluster.id"


def default_jobs_dir() -> Path:
    return Path(getattr(project_config, "JOBS_DIR", DEFAULT_JOBS_DIR))


def default_timeout_sec() -> float:
    return float(_first_config_value(("EVALUATION_TIMEOUT_SEC", "EVALUATE_TIMEOUT_SEC"), DEFAULT_TIMEOUT_SEC))


def default_mode() -> str:
    return str(getattr(project_config, "EVALUATION_MODE", DEFAULT_MODE))


def local_evaluation_max_workers() -> int:
    fresh_config = _fresh_project_config()
    raw = _first_config_value(
        ("LOCAL_EVALUATION_MAX_WORKERS", "EVALUATE_LOCAL_MAX_WORKERS", "LOCAL_EVALUATION_WORKERS"),
        DEFAULT_LOCAL_EVALUATION_MAX_WORKERS,
        config_module=fresh_config,
    )
    return max(1, int(raw))


def htcondor_submit_exe() -> str:
    return str(getattr(project_config, "HTCONDOR_SUBMIT_EXE", DEFAULT_HTCONDOR_SUBMIT_EXE))


def htcondor_remove_exe() -> str:
    return str(getattr(project_config, "HTCONDOR_REMOVE_EXE", DEFAULT_HTCONDOR_REMOVE_EXE))


def htcondor_python_exe() -> str:
    return str(getattr(project_config, "HTCONDOR_PYTHON_EXE", DEFAULT_HTCONDOR_PYTHON_EXE))


def htcondor_executable_mode() -> str:
    return str(getattr(project_config, "HTCONDOR_EXECUTABLE_MODE", DEFAULT_HTCONDOR_EXECUTABLE_MODE)).strip().lower()


def htcondor_poll_sec() -> float:
    return float(getattr(project_config, "HTCONDOR_POLL_SEC", DEFAULT_HTCONDOR_POLL_SEC))


def htcondor_request_cpus() -> int:
    return int(getattr(project_config, "HTCONDOR_REQUEST_CPUS", DEFAULT_HTCONDOR_REQUEST_CPUS))


def htcondor_request_memory() -> str:
    return str(getattr(project_config, "HTCONDOR_REQUEST_MEMORY", DEFAULT_HTCONDOR_REQUEST_MEMORY))


def htcondor_request_disk() -> str:
    return str(getattr(project_config, "HTCONDOR_REQUEST_DISK", DEFAULT_HTCONDOR_REQUEST_DISK))


def htcondor_environment() -> str:
    return str(getattr(project_config, "HTCONDOR_ENVIRONMENT", DEFAULT_HTCONDOR_ENVIRONMENT))


def htcondor_load_profile() -> bool:
    return _as_bool(getattr(project_config, "HTCONDOR_LOAD_PROFILE", DEFAULT_HTCONDOR_LOAD_PROFILE))


def htcondor_run_as_owner() -> bool:
    return _as_bool(getattr(project_config, "HTCONDOR_RUN_AS_OWNER", DEFAULT_HTCONDOR_RUN_AS_OWNER))


def htcondor_requirements() -> str:
    parts: list[str] = []
    base = str(getattr(project_config, "HTCONDOR_REQUIREMENTS", DEFAULT_HTCONDOR_REQUIREMENTS)).strip()
    if base:
        parts.append(base)
    allowed = _string_tuple(getattr(project_config, "HTCONDOR_ALLOWED_MACHINES", DEFAULT_HTCONDOR_ALLOWED_MACHINES))
    excluded = _string_tuple(getattr(project_config, "HTCONDOR_EXCLUDED_MACHINES", DEFAULT_HTCONDOR_EXCLUDED_MACHINES))
    if allowed:
        choices = " || ".join(f'Machine =?= "{_classad_string(machine)}"' for machine in allowed)
        parts.append(f"({choices})")
    for machine in excluded:
        parts.append(f'(Machine =!= "{_classad_string(machine)}")')
    return " && ".join(parts)


def _fresh_project_config():
    try:
        import project.config as key_config
        import project.config_all as all_config

        importlib.reload(key_config)
        return importlib.reload(all_config)
    except Exception:
        return project_config


def _first_config_value(names: tuple[str, ...], fallback: Any, *, config_module=None) -> Any:
    module = project_config if config_module is None else config_module
    for name in names:
        if hasattr(module, name):
            return getattr(module, name)
    return fallback


def _as_bool(value: Any, fallback: Any = False) -> bool:
    if value is None:
        value = fallback
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        if not text or text.lower() in {"*", "all", "none"}:
            return ()
        return tuple(item.strip() for item in text.split(",") if item.strip())
    try:
        return tuple(str(item).strip() for item in value if str(item).strip())
    except TypeError:
        text = str(value).strip()
        return (text,) if text else ()


def _classad_string(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')
